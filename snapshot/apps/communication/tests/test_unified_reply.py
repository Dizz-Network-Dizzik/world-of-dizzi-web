"""Paket D1 (4/4) — Unified Reply: aus dem einen Kontakt-Thread auf jeden Kanal
antworten (docs/35 §2). Kanal = explizit ODER „letzter eingegangener". Senden ist
IMMER HITL (nachricht_senden, verifiziert): es entsteht ein PENDING-Vorschlag.
Dormante Kanäle werden vorbereitet/angezeigt, aber als ``gesperrt`` markiert und
scheitern bei Freigabe fail-closed (Gesetz 5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([{"kanal_typ": "email", "extern_id": "<a@x>",
                      "von_adresse": "alice@example.org", "an_adressen": "ich",
                      "betreff": "Projekt", "text": "Mail", "gesendet_at": "2026-06-12",
                      "thread_schluessel": "<a@x>"}], OrdnerZustand(3, 4))
        return ([], zustand)


def _client(tmp_path):
    """Konto MIT SMTP-Host ⇒ E-Mail-Kanal gilt als verbunden."""
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    client = TestClient(app)
    kid = client.post("/api/konten", json={
        "name": "K", "host": "h", "benutzer": "dizzi@example.org",
        "geheimnis": "g", "smtp_host": "smtp.example.org"}).json()["id"]
    client.post("/api/sync", json={"konto_id": kid})
    return client


def _alice(client):
    return next(k for k in client.get("/api/smartkontakte").json()
                if k["name"] == "alice@example.org")


def test_nachricht_senden_im_katalog(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        kat = {a["name"] for a in client.get("/api/actions").json()["katalog"]}
        assert "nachricht_senden" in kat and "mail_senden" in kat


def test_email_reply_pending_verbunden_und_fail_closed(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        r = client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                        json={"text": "Hallo zurück"}).json()
        assert r["status"] == "pending" and r["kanal_typ"] == "email"
        assert r["an"] == "alice@example.org"           # aus dem Kontakt-Alias abgeleitet
        assert r["kanal_verbunden"] is True and r["gesperrt"] is False
        # erscheint im HITL-Listing als nachricht_senden mit den Params
        eintrag = next(a for a in client.get("/api/actions").json()["liste"]
                       if a["id"] == r["id"])
        assert eintrag["name"] == "nachricht_senden"
        assert eintrag["params"]["an"] == "alice@example.org"
        assert eintrag["params"]["kanal_typ"] == "email"
        # Freigabe standalone ⇒ fail-closed (verifiziert), Vorschlag bleibt liegen
        assert client.post(f"/api/actions/{r['id']}/approve").status_code == 403


def test_reply_auto_letzter_kanal_dormant_gesperrt(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                    json={"kanal_typ": "telegram", "adresse": "@alice_tg"})
        client.post("/api/kanaele/telegram/simulieren",
                    json={"von": "@alice_tg", "text": "hi"})
        r = client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                        json={"text": "zurück"}).json()
        # letzter eingegangener Kanal = telegram (dormant)
        assert r["kanal_typ"] == "telegram" and r["an"] == "@alice_tg"
        assert r["status"] == "pending"                 # vorbereitet/angezeigt …
        assert r["gesperrt"] is True and r["kanal_verbunden"] is False
        assert "verbunden" in r["hinweis"]              # … aber geblockt


def test_reply_expliziter_kanal_ueberschreibt_letzten(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                    json={"kanal_typ": "telegram", "adresse": "@alice_tg"})
        client.post("/api/kanaele/telegram/simulieren",
                    json={"von": "@alice_tg", "text": "hi"})
        # explizit E-Mail, obwohl der letzte Eingang Telegram war
        r = client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                        json={"text": "x", "kanal_typ": "email"}).json()
        assert r["kanal_typ"] == "email" and r["an"] == "alice@example.org"
        assert r["gesperrt"] is False


def test_reply_expliziter_empfaenger_und_betreff(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        r = client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                        json={"text": "x", "an": "anders@example.org",
                              "betreff": "Thema"}).json()
        assert r["an"] == "anders@example.org"
        eintrag = next(a for a in client.get("/api/actions").json()["liste"]
                       if a["id"] == r["id"])
        assert eintrag["params"]["betreff"] == "Thema"


def test_reply_validierung(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        assert client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                           json={"text": ""}).status_code == 400
        assert client.post("/api/smartkontakte/nope/antwort",
                           json={"text": "x"}).status_code == 404
        # Kanal, den der Kontakt nicht hat ⇒ kein Empfänger ableitbar ⇒ 400
        assert client.post(f"/api/smartkontakte/{alice['id']}/antwort",
                           json={"text": "x", "kanal_typ": "snapchat"}).status_code == 400
