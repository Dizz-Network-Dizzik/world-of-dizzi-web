"""Teil C — Senden-UI (HITL sichtbar): Verfassen erzeugt den Vorschlag
mail_senden (Stufe verifiziert), er erscheint im /api/actions-Listing (das die
kontoModal-Sektion rendert), Freigabe ist standalone fail-closed (403),
Ablehnen funktioniert. Das 403-Verhalten selbst gehört appkit (test_app),
hier zählt der für die UI sichtbare Vorschlags-/Freigabe-Fluss."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app


def _client_mit_konto(tmp_path):
    app = build_app(data_dir=tmp_path)
    client = TestClient(app)
    kid = client.post("/api/konten", json={
        "name": "Versand", "host": "imap.example.org",
        "benutzer": "dizzi@example.org", "geheimnis": "pw",
        "smtp_host": "smtp.example.org"}).json()["id"]
    return client, kid


def test_compose_vorschlag_im_listing_und_fail_closed(tmp_path):
    client, kid = _client_mit_konto(tmp_path)
    with client:
        vorschlag = client.post("/api/actions/propose", json={
            "name": "mail_senden", "source": "user",
            "params": {"konto_id": kid, "an": "ziel@example.org",
                       "betreff": "Hallo", "text": "Text"}}).json()
        assert vorschlag["status"] == "pending"
        assert vorschlag["level"] == "verifiziert"
        # Genau das, was die kontoModal-Sektion „Vernetzung & KI-Aktivität" rendert:
        actions = client.get("/api/actions").json()
        assert any(a["name"] == "mail_senden" for a in actions["katalog"])
        eintrag = next(a for a in actions["liste"] if a["id"] == vorschlag["id"])
        assert eintrag["status"] == "pending" and eintrag["source"] == "user"
        assert eintrag["params"]["an"] == "ziel@example.org"
        # Freigabe standalone (lokal) ⇒ fail-closed 403, Aktion bleibt liegen.
        r = client.post(f"/api/actions/{vorschlag['id']}/approve")
        assert r.status_code == 403 and "verifiziert" in r.json()["error"]
        assert next(a for a in client.get("/api/actions").json()["liste"]
                    if a["id"] == vorschlag["id"])["status"] == "pending"


def test_compose_vorschlag_ablehnen(tmp_path):
    client, kid = _client_mit_konto(tmp_path)
    with client:
        vid = client.post("/api/actions/propose", json={
            "name": "mail_senden", "source": "user",
            "params": {"konto_id": kid, "an": "z@example.org"}}).json()["id"]
        assert client.post(f"/api/actions/{vid}/reject").json()["status"] == "rejected"
        assert next(a for a in client.get("/api/actions").json()["liste"]
                    if a["id"] == vid)["status"] == "rejected"


def test_ui_senden_marker(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in ('function verfassen', 'function sendenVorschlag',
                       'function aktionFreigeben', 'function aktionAblehnen',
                       "name:'mail_senden'", 'id="compose"', '/api/actions/propose',
                       'function kiEntwurf', '/entwurf'):
            assert marker in html, marker
