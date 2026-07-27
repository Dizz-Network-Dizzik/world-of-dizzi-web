"""V4 (docs/26): Konversation → Dizz Memory archivieren (auf Zuruf)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


def _mail(betreff, mid, schluessel=None, von="alice@example.org"):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": "dizzi@local", "betreff": betreff,
            "text": "Inhalt " + betreff, "gesendet_at": "2026-06-12",
            "thread_schluessel": schluessel or mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([_mail("Projekt", "<a@x>"),
                     _mail("Re: Projekt", "<b@x>", schluessel="<a@x>",
                           von="bob@example.org")],
                    OrdnerZustand(2, 3))
        return ([], zustand)


def _archiv_capture(store):
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "archiviert", "id": "m1"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post


def test_v4_konversation_archivieren(tmp_path):
    archiv = []
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle(),
                    archiv_post=_archiv_capture(archiv))
    with TestClient(app) as c:
        kid = c.post("/api/konten", json={"name": "K", "host": "h",
                     "benutzer": "u", "geheimnis": "g"}).json()["id"]
        c.post("/api/sync", json={"konto_id": kid})
        konv_id = next(k["id"] for k in c.get("/api/konversationen").json()
                       if k["titel"] == "Projekt")

        r = c.post(f"/api/konversationen/{konv_id}/archivieren").json()
        assert r["status"] == "archiviert"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "kommunikation" and u["strom"] == "mail"
        assert u["explizit"] is True and u["ref"] == "komm:konv:" + konv_id
        assert "email" in u["tags"]
        assert "Projekt" in u["titel"] and "Inhalt" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        assert c.post("/api/konversationen/fehlt/archivieren").status_code == 404


def _kalender_capture(store):
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "eingetragen", "id": "t9"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post


def test_v5_konversation_in_plans_kalender(tmp_path):
    """V5 (docs/26): aus einer Konversation einen Termin in den Admin-Kalender —
    ZWEITER Vertragstyp, Umschlag mit beginn/ende/ort an den Kalender-Relay."""
    relay = []
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle(),
                    archiv_post=_kalender_capture(relay))
    with TestClient(app) as c:
        kid = c.post("/api/konten", json={"name": "K", "host": "h",
                     "benutzer": "u", "geheimnis": "g"}).json()["id"]
        c.post("/api/sync", json={"konto_id": kid})
        konv_id = next(k["id"] for k in c.get("/api/konversationen").json()
                       if k["titel"] == "Projekt")

        r = c.post(f"/api/konversationen/{konv_id}/kalender",
                   json={"beginn": "2026-07-01T15:00", "ende": "2026-07-01T16:00",
                         "ort": "Jitsi"}).json()
        assert r["status"] == "eingetragen"
        u = relay[-1]["umschlag"]
        assert relay[-1]["url"].endswith("/api/querverbindung/admin/kalender")
        assert u["app"] == "kommunikation" and u["titel"] == "Projekt"
        assert u["beginn"] == "2026-07-01T15:00" and u["ende"] == "2026-07-01T16:00"
        assert u["ort"] == "Jitsi" and u["ref"] == "komm:termin:" + konv_id
        assert "Inhalt" in u["beschreibung"]          # Auszug der ersten Nachricht
        # beginn ist Pflicht + unbekannte Konversation ⇒ 404
        assert c.post(f"/api/konversationen/{konv_id}/kalender", json={}).status_code == 400
        assert c.post("/api/konversationen/fehlt/kalender",
                      json={"beginn": "2026-07-01T15:00"}).status_code == 404


def _smart_capture():
    """Relay-Fake, der je nach Ziel-URL den passenden Status liefert."""
    def post(url, json):
        class _R:
            status_code = 200

            def json(self):
                if "admin" in url:
                    return {"ok": True, "status": "eingetragen", "id": "t9"}
                return {"ok": True, "status": "archiviert", "id": "m1"}
        return _R()
    return post


def test_verknuepfungen_aufgezeichnet_und_sichtbar(tmp_path):
    """Leitlinie 17.06: jede Querverbindung wird lokal festgehalten und ist über
    GET /verknuepfungen sichtbar (Drill-down via ref) — idempotent je Ziel."""
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle(),
                    archiv_post=_smart_capture())
    with TestClient(app) as c:
        kid = c.post("/api/konten", json={"name": "K", "host": "h",
                     "benutzer": "u", "geheimnis": "g"}).json()["id"]
        c.post("/api/sync", json={"konto_id": kid})
        konv = next(k["id"] for k in c.get("/api/konversationen").json()
                    if k["titel"] == "Projekt")

        # vor jeder Aktion: keine Verknüpfungen
        assert c.get(f"/api/konversationen/{konv}/verknuepfungen").json() == []
        c.post(f"/api/konversationen/{konv}/archivieren")
        c.post(f"/api/konversationen/{konv}/kalender",
               json={"beginn": "2026-07-01T15:00"})

        by = {l["ziel"]: l for l in
              c.get(f"/api/konversationen/{konv}/verknuepfungen").json()}
        assert set(by) == {"memory", "admin"}
        assert by["memory"]["ref"] == "komm:konv:" + konv and by["memory"]["extern_id"] == "m1"
        assert by["admin"]["ref"] == "komm:termin:" + konv and by["admin"]["extern_id"] == "t9"
        # idempotent: zweites Archivieren legt keinen zweiten memory-Link an
        c.post(f"/api/konversationen/{konv}/archivieren")
        links = c.get(f"/api/konversationen/{konv}/verknuepfungen").json()
        assert sum(1 for l in links if l["ziel"] == "memory") == 1
