"""Meta-Konnektor (docs/38) — Schicht-Tests, netzfrei: Body-Builder, Webhook
(Verify/Signatur/Parse) und die W4-Connectoren (dormant ohne Token, fail-closed,
Versand mit Mock-http_post)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from appkit.connectors import KonnektorNichtVerbunden
from kommapp import meta
from kommapp.meta import (InstagramConnector, MetaApiFehler, WhatsAppConnector,
                          baue_connectoren, instagram_body, pruefe_signatur,
                          webhook_parse, webhook_verify, whatsapp_body)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}
    def json(self):
        return self._p


def _fake_post(rec, status=200, payload=None):
    def post(url, *, json, headers):
        rec.update(url=url, json=json, headers=headers)
        return _Resp(status, payload or {"messages": [{"id": "wamid.X"}]})
    return post


# ── Body-Builder ──────────────────────────────────────────────────────────────
def test_whatsapp_body_session_und_template():
    b = whatsapp_body("4915123", text="hallo")
    assert b == {"messaging_product": "whatsapp", "recipient_type": "individual",
                 "to": "4915123", "type": "text", "text": {"body": "hallo"}}
    t = whatsapp_body("4915123", template="willkommen", sprache="de")
    assert t["type"] == "template" and t["template"]["name"] == "willkommen"
    assert t["template"]["language"]["code"] == "de"


def test_instagram_body():
    assert instagram_body("178414", "hi") == {"recipient": {"id": "178414"},
                                              "message": {"text": "hi"}}


# ── Webhook ───────────────────────────────────────────────────────────────────
def test_webhook_verify():
    assert meta.webhook_verify("subscribe", "geheim", "CHAL", "geheim") == "CHAL"
    assert meta.webhook_verify("subscribe", "falsch", "CHAL", "geheim") is None
    assert meta.webhook_verify("subscribe", "geheim", "CHAL", "") is None


def test_signatur_pruefung():
    raw = b'{"a":1}'; sec = "appsecret"
    sig = "sha256=" + hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
    assert pruefe_signatur(raw, sig, sec) is True
    assert pruefe_signatur(raw, "sha256=deadbeef", sec) is False
    assert pruefe_signatur(raw, None, sec) is False
    assert pruefe_signatur(raw, None, "") is False         # fail-closed: ohne Secret nicht verifizierbar ⇒ abgelehnt
    assert pruefe_signatur(raw, sig, "") is False          # auch mit Header: ohne Secret kein Durchwinken


def test_webhook_parse_whatsapp():
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages",
        "value": {"messaging_product": "whatsapp",
                  "contacts": [{"wa_id": "4915123", "profile": {"name": "Max"}}],
                  "messages": [{"from": "4915123", "id": "wamid.1", "timestamp": "1700000000",
                                "type": "text", "text": {"body": "Hallo per WA"}}]}}]}]}
    ns = webhook_parse(payload)
    assert len(ns) == 1
    n = ns[0]
    assert n["kanal_typ"] == "whatsapp" and n["von_adresse"] == "4915123"
    assert n["text"] == "Hallo per WA" and n["extern_id"] == "wamid.1"
    assert n["thread_schluessel"] == "whatsapp:4915123"


def test_webhook_parse_instagram_und_echo_ignoriert():
    payload = {"object": "instagram", "entry": [{"messaging": [
        {"sender": {"id": "IGSID9"}, "message": {"mid": "m1", "text": "Hi per IG"}},
        {"sender": {"id": "self"}, "message": {"mid": "m2", "text": "echo", "is_echo": True}},
    ]}]}
    ns = webhook_parse(payload)
    assert len(ns) == 1 and ns[0]["kanal_typ"] == "instagram"
    assert ns[0]["von_adresse"] == "IGSID9" and ns[0]["text"] == "Hi per IG"


def test_webhook_parse_robust_leer():
    assert webhook_parse({}) == []
    assert webhook_parse({"entry": [{}]}) == []


# ── Connectoren (dormant / fail-closed / Versand mit Mock) ────────────────────
def test_connector_dormant_ohne_token():
    wa = WhatsAppConnector(vault_get=lambda n: None)
    assert wa.verfuegbar() is False
    inf = wa.status()
    assert inf["dormant"] is True and inf["verbunden"] is False
    assert inf["extra"]["token_name"] == "meta_whatsapp_token"
    assert "whatsapp_business_messaging" in inf["extra"]["permissions"]
    with pytest.raises(KonnektorNichtVerbunden):
        wa.senden("4915123", text="x")


def test_whatsapp_senden_mit_token_baut_korrekten_call():
    rec = {}
    wa = WhatsAppConnector(
        vault_get=lambda n: "TOK" if n == "meta_whatsapp_token" else None,
        config_get=lambda k, d=None: {"whatsapp_phone_number_id": "PNID",
                                      "graph_version": "v23.0"}.get(k, d),
        http_post=_fake_post(rec))
    assert wa.verfuegbar() is True
    erg = wa.senden("4915123", text="hallo")
    assert rec["url"] == "https://graph.facebook.com/v23.0/PNID/messages"
    assert rec["headers"]["Authorization"] == "Bearer TOK"
    assert rec["json"]["to"] == "4915123" and rec["json"]["text"]["body"] == "hallo"
    assert erg["messages"][0]["id"] == "wamid.X"


def test_whatsapp_senden_ohne_phone_number_id_fail_closed():
    wa = WhatsAppConnector(vault_get=lambda n: "TOK",
                           config_get=lambda k, d=None: d)   # keine pnid
    with pytest.raises(KonnektorNichtVerbunden):
        wa.senden("4915123", text="x")


def test_instagram_senden_mit_token():
    rec = {}
    ig = InstagramConnector(
        vault_get=lambda n: "TOK" if n == "meta_instagram_token" else None,
        config_get=lambda k, d=None: {"instagram_user_id": "IGID"}.get(k, d),
        http_post=_fake_post(rec, payload={"message_id": "ig.1"}))
    ig.senden("IGSID9", text="hi")
    assert rec["url"].endswith("/IGID/messages")
    assert rec["json"] == {"recipient": {"id": "IGSID9"}, "message": {"text": "hi"}}


def test_graph_fehler_wird_gehoben():
    rec = {}
    wa = WhatsAppConnector(
        vault_get=lambda n: "TOK",
        config_get=lambda k, d=None: {"whatsapp_phone_number_id": "PNID"}.get(k, d),
        http_post=_fake_post(rec, status=400,
                             payload={"error": {"message": "Invalid OAuth token"}}))
    with pytest.raises(MetaApiFehler) as ex:
        wa.senden("4915123", text="x")
    assert "Invalid OAuth token" in str(ex.value)


def test_baue_connectoren():
    cs = baue_connectoren()
    assert set(cs) == set(meta.META_KANAELE)
    assert cs["whatsapp"].id == "whatsapp" and cs["instagram"].id == "instagram"


# ── Integration in D1 channels.py (Unified-Reply-Routing) ─────────────────────
def test_channels_ohne_meta_bleibt_dormant():
    from kommapp import channels
    reg = channels.registry()                       # kein adapter verdrahtet
    assert reg["whatsapp"].aktiv is False and reg["whatsapp"].verbunden() is False


def test_channels_mit_meta_aktiv_aber_dormant_ohne_token():
    from kommapp import channels
    from kommapp.channels import AusgehendeNachricht
    reg = channels.registry(adapter=baue_connectoren(vault_get=lambda n: None))
    wa = reg["whatsapp"]
    assert wa.aktiv is True and wa.verbunden() is False     # Adapter da, Token fehlt
    st = wa.status()
    assert st["aktivierung"] and "whatsapp_business_messaging" in st["permissions"]
    with pytest.raises(KonnektorNichtVerbunden):
        wa.senden(AusgehendeNachricht(an="49151", text="x", kanal_typ="whatsapp"))


def test_channels_mit_token_sendet_ueber_graph():
    from kommapp import channels
    from kommapp.channels import AusgehendeNachricht
    rec = {}
    metac = baue_connectoren(
        vault_get=lambda n: "TOK" if n == "meta_whatsapp_token" else None,
        config_get=lambda k, d=None: {"whatsapp_phone_number_id": "PN"}.get(k, d),
        http_post=_fake_post(rec))
    wa = channels.registry(adapter=metac)["whatsapp"]
    assert wa.verbunden() is True
    wa.senden(AusgehendeNachricht(an="49151", text="hi", kanal_typ="whatsapp"))
    assert rec["url"].endswith("/PN/messages") and rec["json"]["text"]["body"] == "hi"
