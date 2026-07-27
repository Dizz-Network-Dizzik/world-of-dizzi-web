"""Meta-Konnektor — App-Ebene (docs/38): /api/konnektoren + /api/kanaele-Status,
Verbinden/Trennen (Secrets→Tresor), Webhook (Verify/Signatur/Ingest in die
Unified-Inbox), Test-Sende (HITL). Alles netzfrei (kein echter Graph-Call: Senden
ist HITL + standalone fail-closed)."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from kommapp.main import build_app


def _client(tmp_path):
    return TestClient(build_app(data_dir=tmp_path))


def test_konnektoren_zeigt_meta_dormant(tmp_path):
    with _client(tmp_path) as client:
        d = client.get("/api/konnektoren").json()
        ids = {c["id"] for c in d["konnektoren"]}
        assert {"whatsapp", "instagram"} <= ids
        assert d["verbunden"] == 0                       # dormant (keine Tokens)


def test_kanaele_whatsapp_aktiv_aber_unverbunden(tmp_path):
    with _client(tmp_path) as client:
        wa = next(k for k in client.get("/api/kanaele").json()
                  if k["kanal_typ"] == "whatsapp")
        assert wa["aktiv"] is True and wa["verbunden"] is False   # echter Adapter, kein Token
        assert "whatsapp_business_messaging" in wa.get("permissions", [])


def test_meta_status_initial(tmp_path):
    with _client(tmp_path) as client:
        st = client.get("/api/kanaele/meta/status").json()
        assert st["webhook_pfad"] == "/api/kanaele/meta/webhook"
        assert st["app_secret_gesetzt"] is False and st["verify_token_gesetzt"] is False
        wa = next(k for k in st["kanaele"] if k["kanal_typ"] == "whatsapp")
        assert wa["token_gesetzt"] is False and wa["verbunden"] is False


def test_verbinden_und_trennen(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/meta/verbinden", json={
            "kanal": "whatsapp", "token": "TOK123", "phone_number_id": "PNID"}).json()
        assert r["ok"] and "token" in r["gesetzt"] and "phone_number_id" in r["gesetzt"]
        assert r["verbunden"] is True
        # /api/kanaele spiegelt den verbundenen Zustand
        wa = next(k for k in client.get("/api/kanaele").json() if k["kanal_typ"] == "whatsapp")
        assert wa["verbunden"] is True
        # Setting gesetzt, Token NICHT über /api/settings sichtbar (liegt im Tresor)
        assert client.get("/api/kanaele/meta/status").json()["kanaele"][0]["phone_number_id"] == "PNID"
        # Trennen ⇒ wieder dormant
        t = client.delete("/api/kanaele/meta/verbinden", params={"kanal": "whatsapp"}).json()
        assert t["token_geloescht"] is True
        wa2 = next(k for k in client.get("/api/kanaele").json() if k["kanal_typ"] == "whatsapp")
        assert wa2["verbunden"] is False


def test_verbinden_unbekannter_kanal_400(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/meta/verbinden",
                           json={"kanal": "telegram", "token": "x"}).status_code == 400


def test_webhook_verify_challenge(tmp_path):
    with _client(tmp_path) as client:
        # ohne hinterlegten Verify-Token ⇒ 403
        assert client.get("/api/kanaele/meta/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "C"}
        ).status_code == 403
        client.post("/api/kanaele/meta/verbinden",
                    json={"kanal": "whatsapp", "verify_token": "geheim"})
        ok = client.get("/api/kanaele/meta/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "geheim", "hub.challenge": "CH42"})
        assert ok.status_code == 200 and ok.text == "CH42"
        assert client.get("/api/kanaele/meta/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "falsch", "hub.challenge": "CH"}
        ).status_code == 403


_WA_PAYLOAD = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages",
    "value": {"messaging_product": "whatsapp",
              "contacts": [{"wa_id": "4915123", "profile": {"name": "Max"}}],
              "messages": [{"from": "4915123", "id": "wamid.7", "timestamp": "1700000000",
                            "type": "text", "text": {"body": "Hallo per WhatsApp"}}]}}]}]}


def test_webhook_ohne_secret_abgelehnt(tmp_path):
    """Fail-closed: ohne hinterlegtes App-Secret weist der Webhook-POST ab (403) —
    ein unverifizierbarer Eingang darf keine gefälschten Events einschleusen."""
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/meta/webhook", json=_WA_PAYLOAD)
        assert r.status_code == 403
        # nichts gelandet
        wa = [x for x in client.get("/api/kanaele").json() if x["kanal_typ"] == "whatsapp"]
        assert not wa or wa[0]["nachrichten"] == 0


def test_webhook_ingest_landet_in_unified_inbox(tmp_path):
    with _client(tmp_path) as client:
        # Fail-closed: Eingang nur mit App-Secret + gültiger X-Hub-Signatur
        client.post("/api/kanaele/meta/verbinden",
                    json={"kanal": "whatsapp", "app_secret": "s3cret"})
        raw = json.dumps(_WA_PAYLOAD).encode("utf-8")
        sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        r = client.post("/api/kanaele/meta/webhook", content=raw,
                        headers={"x-hub-signature-256": sig,
                                 "content-type": "application/json"}).json()
        assert r["ok"] and r["empfangen"] == 1 and r["neu"] == 1
        # Smart-Contact aus der Telefonnummer + Verlauf mit Herkunfts-Label
        k = next(c for c in client.get("/api/smartkontakte").json()
                 if c["name"] == "4915123")
        assert k["kanaele"] == ["whatsapp"]
        v = client.get(f"/api/smartkontakte/{k['id']}/verlauf").json()
        assert v["nachrichten"][0]["kanal_typ"] == "whatsapp"
        assert v["nachrichten"][0]["text"] == "Hallo per WhatsApp"
        # /api/kanaele zählt es
        wa = next(x for x in client.get("/api/kanaele").json() if x["kanal_typ"] == "whatsapp")
        assert wa["nachrichten"] == 1 and wa["kontakte"] == 1


def test_webhook_signatur_erzwungen_mit_app_secret(tmp_path):
    with _client(tmp_path) as client:
        client.post("/api/kanaele/meta/verbinden",
                    json={"kanal": "whatsapp", "app_secret": "s3cret"})
        raw = json.dumps(_WA_PAYLOAD).encode("utf-8")
        # falsche Signatur ⇒ 403
        assert client.post("/api/kanaele/meta/webhook", content=raw,
                           headers={"x-hub-signature-256": "sha256=deadbeef",
                                    "content-type": "application/json"}).status_code == 403
        # korrekte Signatur ⇒ angenommen
        sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        ok = client.post("/api/kanaele/meta/webhook", content=raw,
                         headers={"x-hub-signature-256": sig,
                                  "content-type": "application/json"})
        assert ok.status_code == 200 and ok.json()["neu"] == 1


def test_meta_config_ui_marker(tmp_path):
    with _client(tmp_path) as client:
        html = client.get("/").text
        for marker in ('id="meta-status"', "function ladeMetaStatus",
                       "function metaVerbinden", "function metaTrennen",
                       "function metaTest", 'data-dz-act="metaVerbinden"',
                       'data-dz-act="metaTest"', "/api/kanaele/meta/status",
                       "/api/kanaele/meta/verbinden", "/api/kanaele/meta/test",
                       "ladeMetaStatus();"):
            assert marker in html, marker
        # CSP-strikt: keine inline-Handler eingeschleppt
        import re
        assert re.search(r"\son[a-z]+=[\"']", html) is None


def test_test_sende_ist_hitl_und_dormant_gesperrt(tmp_path):
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/meta/test",
                        json={"kanal": "whatsapp", "an": "4915123", "text": "hi"}).json()
        assert r["status"] == "pending" and r["kanal_typ"] == "whatsapp"
        assert r["gesperrt"] is True and r["kanal_verbunden"] is False
        # als nachricht_senden im HITL-Listing
        e = next(a for a in client.get("/api/actions").json()["liste"] if a["id"] == r["id"])
        assert e["name"] == "nachricht_senden" and e["params"]["kanal_typ"] == "whatsapp"


def test_test_sende_reicht_template_in_die_params(tmp_path):
    """Fix docs/39 §5: das WA-Template muss in die nachricht_senden-Params fließen —
    sonst kann der freigegebene Versand außerhalb des 24-h-Fensters nichts ausliefern
    (Meta liefert dann nur genehmigte Templates aus, freier Text bleibt liegen)."""
    with _client(tmp_path) as client:
        r = client.post("/api/kanaele/meta/test", json={
            "kanal": "whatsapp", "an": "4915123", "text": "hi",
            "template": "hello_world"}).json()
        e = next(a for a in client.get("/api/actions").json()["liste"] if a["id"] == r["id"])
        assert e["params"]["template"] == "hello_world"
        # ohne Template-Angabe bleibt das Feld leer (freier Text, nur im 24-h-Fenster)
        r2 = client.post("/api/kanaele/meta/test",
                         json={"kanal": "whatsapp", "an": "4915123", "text": "hi"}).json()
        e2 = next(a for a in client.get("/api/actions").json()["liste"] if a["id"] == r2["id"])
        assert e2["params"]["template"] == ""
