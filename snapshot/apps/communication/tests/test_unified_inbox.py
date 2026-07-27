"""Paket D1 (3/4) — Unified Inbox: ein Kontakt-Thread über alle Kanäle (docs/35 §2).

E-Mail ist real (Sync), die anderen Kanäle werden simuliert (Demo-Ingest,
docs/35 §6 — keine Plattform-Anbindung). Getestet: der kontaktzentrierte
Verlauf führt Nachrichten ALLER Kanäle chronologisch mit Herkunfts-Label
zusammen; die Simulation legt/dedupet Kontakte korrekt; der „letzte Kanal" steht
für die Unified-Reply-Default-Wahl bereit."""

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
                      "betreff": "Projekt", "text": "Mail-Inhalt",
                      "gesendet_at": "2026-06-12", "thread_schluessel": "<a@x>"}],
                    OrdnerZustand(3, 4))
        return ([], zustand)


def _client(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    client = TestClient(app)
    kid = client.post("/api/konten", json={
        "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
    client.post("/api/sync", json={"konto_id": kid})
    return client


def _alice(client):
    return next(k for k in client.get("/api/smartkontakte").json()
                if k["name"] == "alice@example.org")


def test_unified_verlauf_fuehrt_kanaele_zusammen(tmp_path):
    with _client(tmp_path) as client:
        alice = _alice(client)
        # Telegram-Identität an alice hängen, dann eine Telegram-Nachricht simulieren
        client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                    json={"kanal_typ": "telegram", "adresse": "@alice_tg"})
        sim = client.post("/api/kanaele/telegram/simulieren",
                          json={"von": "@alice_tg", "text": "Hi über Telegram"}).json()
        assert sim["ok"] and sim["neu"] == 1
        v = client.get(f"/api/smartkontakte/{alice['id']}/verlauf").json()
        kanaele = [n["kanal_typ"] for n in v["nachrichten"]]
        assert kanaele == ["email", "telegram"]            # chronologisch, je mit Label
        assert v["nachrichten"][1]["text"] == "Hi über Telegram"
        assert v["kontakt"]["letzter_kanal"] == "telegram"  # Default für Unified Reply
        assert set(v["kontakt"]["kanaele"]) == {"email", "telegram"}


def test_simulation_legt_neuen_kanal_kontakt_an(tmp_path):
    with _client(tmp_path) as client:
        # Telegram von einem FRISCHEN Handle ⇒ neuer Kontakt mit Telegram-Kanal
        client.post("/api/kanaele/whatsapp/simulieren",
                    json={"von": "+49160123", "text": "Moin"})
        ks = {k["name"]: k for k in client.get("/api/smartkontakte").json()}
        assert "+49160123" in ks
        assert ks["+49160123"]["kanaele"] == ["whatsapp"]
        assert ks["+49160123"]["nachrichten"] == 1


def test_simulation_zaehlt_in_kanaele_uebersicht(tmp_path):
    with _client(tmp_path) as client:
        client.post("/api/kanaele/telegram/simulieren",
                    json={"von": "@x", "text": "a"})
        tele = next(k for k in client.get("/api/kanaele").json()
                    if k["kanal_typ"] == "telegram")
        assert tele["nachrichten"] == 1 and tele["kontakte"] == 1
        assert tele["verbunden"] is False                  # weiterhin dormant (nur simuliert)


def test_simulation_lehnt_email_und_unbekannt_ab(tmp_path):
    with _client(tmp_path) as client:
        assert client.post("/api/kanaele/email/simulieren",
                           json={"von": "x@y.z"}).status_code == 400
        assert client.post("/api/kanaele/fax/simulieren",
                           json={"von": "x"}).status_code == 400
        assert client.post("/api/kanaele/telegram/simulieren",
                           json={"von": ""}).status_code == 400


def test_simuliertes_konto_wird_nicht_imap_gesynct(tmp_path):
    with _client(tmp_path) as client:
        sim = client.post("/api/kanaele/telegram/simulieren",
                          json={"von": "@x", "text": "a"}).json()
        r = client.post("/api/sync", json={"konto_id": sim["konto_id"]})
        assert r.status_code == 200 and "simulierter Kanal" in r.json()["hinweis"]


def test_verlauf_unbekannter_kontakt_404(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/api/smartkontakte/gibtsnicht/verlauf").status_code == 404
