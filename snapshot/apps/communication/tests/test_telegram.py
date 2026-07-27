"""Telegram-Konnektor (Bot-API) — netzfreie Tests: Body-Builder, telegram_call,
updates_parse, der W4-Connector (dormant ohne Token, fail-closed, Versand/Abruf mit
Mock-http_post), die D1-channels-Integration und die App-Endpunkte (Status/Verbinden/
Trennen/Test-HITL/Sync-Polling/Prüfen). Kein echter API-Call: das app-seitige
``_default_post`` wird gemockt; Senden ist HITL + standalone fail-closed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit.connectors import KonnektorNichtVerbunden
from kommapp import telegram
from kommapp.main import build_app
from kommapp.telegram import (TelegramApiFehler, TelegramBotConnector,
                              baue_connector, telegram_body, updates_parse)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload if payload is not None else {"ok": True, "result": {}}
    def json(self):
        return self._p


def _fake_post(rec, status=200, payload=None):
    def post(url, *, json, headers):
        rec.update(url=url, json=json, headers=headers)
        return _Resp(status, payload if payload is not None else {"ok": True, "result": {"message_id": 7}})
    return post


def _update(uid=100, chat_id=12345, mid=5, text="Hallo per Telegram",
            username="max", first="Max", ts=1700000000):
    return {"update_id": uid, "message": {
        "message_id": mid, "from": {"id": chat_id, "username": username, "first_name": first},
        "chat": {"id": chat_id, "type": "private"}, "date": ts, "text": text}}


# ── Body-Builder ──────────────────────────────────────────────────────────────
def test_telegram_body():
    assert telegram_body(12345, "hi") == {"chat_id": "12345", "text": "hi"}
    assert telegram_body("999", None) == {"chat_id": "999", "text": ""}


# ── telegram_call ─────────────────────────────────────────────────────────────
def test_telegram_call_ok_gibt_result():
    rec = {}
    res = telegram.telegram_call("TOK", "sendMessage", {"chat_id": "1", "text": "x"},
                                 http_post=_fake_post(rec, payload={"ok": True, "result": {"message_id": 9}}))
    assert res == {"message_id": 9}
    assert rec["url"] == "https://api.telegram.org/botTOK/sendMessage"


def test_telegram_call_fehler_hebt():
    with pytest.raises(TelegramApiFehler):
        telegram.telegram_call("TOK", "sendMessage", {},
                               http_post=_fake_post({}, payload={"ok": False, "description": "chat not found"}))
    with pytest.raises(TelegramApiFehler):
        telegram.telegram_call("TOK", "sendMessage", {},
                               http_post=_fake_post({}, status=401, payload={"ok": False, "description": "Unauthorized"}))


# ── updates_parse ─────────────────────────────────────────────────────────────
def test_updates_parse_normiert_und_offset():
    nachrichten, off = updates_parse([_update(uid=100, chat_id=777, mid=3, text="hey", username="a")])
    assert off == 101
    n = nachrichten[0]
    assert n["kanal_typ"] == "telegram" and n["von_adresse"] == "777"
    assert n["text"] == "hey" and n["betreff"] == "@a"
    assert n["thread_schluessel"] == "telegram:777" and n["extern_id"] == "telegram:777:3"
    assert n["an_adressen"] == "ich"


def test_updates_parse_robust():
    # leere Liste, nicht-Nachricht-Update (edited_message), fehlende Felder ⇒ kein Crash
    assert updates_parse([]) == ([], None)
    assert updates_parse(None) == ([], None)
    leer, off = updates_parse([{"update_id": 5, "edited_message": {"x": 1}},
                               {"update_id": 6, "message": {"text": "ohne chat"}}])
    assert leer == [] and off == 7                     # höchste update_id +1, aber keine validen Nachrichten


def test_updates_parse_nicht_text_platzhalter():
    n, _ = updates_parse([{"update_id": 1, "message": {
        "message_id": 1, "chat": {"id": 1}, "date": 1, "photo": [{"file_id": "p"}]}}])
    assert n[0]["text"] == "[photo]"


# ── W4-Connector (direkt, netzfrei) ───────────────────────────────────────────
def test_connector_dormant_ohne_token():
    c = TelegramBotConnector(vault_get=lambda n: None)
    assert c.verfuegbar() is False
    assert c.abrufen(0) == ([], 0)
    assert c.bot_info() == {}
    with pytest.raises(KonnektorNichtVerbunden):
        c.senden("12345", "hi")


def test_connector_sendet_mit_token():
    rec = {}
    c = TelegramBotConnector(vault_get=lambda n: "TOK" if n == "telegram_bot_token" else None,
                             http_post=_fake_post(rec))
    assert c.verfuegbar() is True
    r = c.senden("12345", "hallo", template="ignoriert")   # template wird ignoriert
    assert rec["url"].endswith("/botTOK/sendMessage")
    assert rec["json"] == {"chat_id": "12345", "text": "hallo"}
    assert r["gesendet"] is True and r["an"] == "12345"


def test_connector_abrufen_mit_token():
    payload = {"ok": True, "result": [_update(uid=200, chat_id=42, text="ping")]}
    c = TelegramBotConnector(vault_get=lambda n: "TOK",
                             http_post=_fake_post({}, payload=payload))
    nachrichten, off = c.abrufen(0)
    assert off == 201 and nachrichten[0]["von_adresse"] == "42" and nachrichten[0]["text"] == "ping"


# ── D1 channels-Integration ───────────────────────────────────────────────────
def test_channels_telegram_ohne_adapter_dormant():
    from kommapp import channels
    reg = channels.registry()                          # kein adapter verdrahtet
    assert reg["telegram"].aktiv is False and reg["telegram"].verbunden() is False


def test_channels_telegram_mit_adapter_aktiv_dormant_ohne_token():
    from kommapp import channels
    from kommapp.channels import AusgehendeNachricht
    reg = channels.registry(adapter={"telegram": baue_connector(vault_get=lambda n: None)})
    tg = reg["telegram"]
    assert tg.aktiv is True and tg.verbunden() is False
    with pytest.raises(KonnektorNichtVerbunden):
        tg.senden(AusgehendeNachricht(an="12345", text="x", kanal_typ="telegram"))


def test_channels_telegram_sendet_mit_token():
    from kommapp import channels
    from kommapp.channels import AusgehendeNachricht
    rec = {}
    adapter = {"telegram": baue_connector(
        vault_get=lambda n: "TOK" if n == "telegram_bot_token" else None,
        http_post=_fake_post(rec))}
    tg = channels.registry(adapter=adapter)["telegram"]
    assert tg.verbunden() is True
    tg.senden(AusgehendeNachricht(an="12345", text="hi", kanal_typ="telegram"))
    assert rec["url"].endswith("/sendMessage") and rec["json"]["text"] == "hi"


# ── App-Ebene (Endpunkte, netzfrei) ───────────────────────────────────────────
def _client(tmp_path):
    return TestClient(build_app(data_dir=tmp_path))


def test_konnektoren_zeigt_telegram_dormant(tmp_path):
    with _client(tmp_path) as client:
        d = client.get("/api/konnektoren").json()
        assert "telegram" in {c["id"] for c in d["konnektoren"]}
        tg = next(c for c in d["konnektoren"] if c["id"] == "telegram")
        assert tg["verbunden"] is False and tg["dormant"] is True


def test_kanaele_telegram_aktiv_unverbunden(tmp_path):
    with _client(tmp_path) as client:
        tg = next(k for k in client.get("/api/kanaele").json() if k["kanal_typ"] == "telegram")
        assert tg["aktiv"] is True and tg["verbunden"] is False   # echter Adapter, kein Token


def test_telegram_status_initial(tmp_path):
    with _client(tmp_path) as client:
        st = client.get("/api/kanaele/telegram/status").json()
        assert st["token_gesetzt"] is False and st["verbunden"] is False
        assert "long-polling" in st["transport"] and st["offset"] == 0


def test_telegram_verbinden_und_trennen(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/telegram/verbinden", json={"token": "BOT:TOK"}).json()
        assert r["ok"] and r["verbunden"] is True
        tg = next(k for k in client.get("/api/kanaele").json() if k["kanal_typ"] == "telegram")
        assert tg["verbunden"] is True
        t = client.delete("/api/kanaele/telegram/verbinden").json()
        assert t["token_geloescht"] is True
        assert client.get("/api/kanaele/telegram/status").json()["verbunden"] is False


def test_telegram_verbinden_leer_400(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/telegram/verbinden", json={"token": "  "}).status_code == 400


def test_telegram_test_ist_hitl_und_dormant_gesperrt(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/telegram/test",
                        json={"an": "12345", "text": "hi"}).json()
        assert r["status"] == "pending" and r["kanal_typ"] == "telegram"
        assert r["gesperrt"] is True and r["kanal_verbunden"] is False
        e = next(a for a in client.get("/api/actions").json()["liste"] if a["id"] == r["id"])
        assert e["name"] == "nachricht_senden" and e["params"]["kanal_typ"] == "telegram"


def test_telegram_test_ohne_empfaenger_400(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/telegram/test", json={"an": "", "text": "x"}).status_code == 400


def test_telegram_sync_ohne_token_409(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/telegram/sync").status_code == 409


def test_telegram_sync_ingest_in_unified_inbox(tmp_path, monkeypatch):
    payload = {"ok": True, "result": [_update(uid=300, chat_id=98765, mid=2,
                                              text="Hallo per Telegram", username="maxi")]}
    monkeypatch.setattr(telegram, "_default_post", _fake_post({}, payload=payload))
    with _client(tmp_path) as client:
        client.post("/api/kanaele/telegram/verbinden", json={"token": "BOT:TOK"})
        r = client.post("/api/kanaele/telegram/sync").json()
        assert r["geholt"] == 1 and r["neu"] == 1 and r["offset"] == 301
        # Smart-Contact aus der chat_id + Verlauf mit Herkunfts-Label
        k = next(c for c in client.get("/api/smartkontakte").json() if c["name"] == "98765")
        assert k["kanaele"] == ["telegram"]
        v = client.get(f"/api/smartkontakte/{k['id']}/verlauf").json()
        assert v["nachrichten"][0]["kanal_typ"] == "telegram"
        assert v["nachrichten"][0]["text"] == "Hallo per Telegram"
        # /api/kanaele zählt es + Offset wird in den Settings persistiert
        tg = next(x for x in client.get("/api/kanaele").json() if x["kanal_typ"] == "telegram")
        assert tg["nachrichten"] == 1 and tg["kontakte"] == 1
        assert client.get("/api/kanaele/telegram/status").json()["offset"] == 301
        # zweiter Sync ohne neue Updates ⇒ idempotent (kein Doppel)
        monkeypatch.setattr(telegram, "_default_post", _fake_post({}, payload={"ok": True, "result": []}))
        r2 = client.post("/api/kanaele/telegram/sync").json()
        assert r2["neu"] == 0


def test_telegram_pruefen_zeigt_bot(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "_default_post",
                        _fake_post({}, payload={"ok": True, "result": {"id": 42, "username": "DizzBot",
                                                                       "first_name": "Dizz"}}))
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/telegram/pruefen").status_code == 409   # dormant
        client.post("/api/kanaele/telegram/verbinden", json={"token": "BOT:TOK"})
        p = client.post("/api/kanaele/telegram/pruefen").json()
        assert p["ok"] and p["bot_username"] == "DizzBot" and p["bot_name"] == "Dizz"


def test_telegram_config_ui_marker(tmp_path):
    with _client(tmp_path) as client:
        html = client.get("/").text
        for marker in ('id="tg-status"', "function ladeTgStatus", "function tgVerbinden",
                       "function tgTrennen", "function tgTest", "function tgSync",
                       'data-dz-act="tgVerbinden"', 'data-dz-act="tgSync"',
                       "/api/kanaele/telegram/status", "/api/kanaele/telegram/verbinden",
                       "/api/kanaele/telegram/sync", "ladeTgStatus();"):
            assert marker in html, marker
        import re
        assert re.search(r"\son[a-z]+=[\"']", html) is None     # CSP-strikt: keine inline-Handler
