"""V5-Rücksync (docs/26 §4b): Communication ist die ZIEL-Seite des Kalender-Vertrags.
Dizz Admin (Kalender) schickt einen Termin als read-only Erinnerung hierher (seit dem
Plans+Admin+Leading-Merge ist Admin der Kalender-Absender, nicht mehr Plans); der
Empfänger ist idempotent (quelle×extern_id) und die GET-Sicht zeigt anstehende Termine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app


def _umschlag(**over):
    u = {"titel": "Kickoff", "beginn": "2026-07-01T15:00",
         "ende": "2026-07-01T16:00", "ganztags": False, "ort": "Büro",
         "beschreibung": "Projektstart", "app": "admin",
         "quelle": "admin:termin:t1", "ref": "admin:termin:t1"}
    u.update(over)
    return u


def test_kalender_empfang_eintragen_und_idempotent(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        r1 = c.post("/api/querverbindung/kalender", json=_umschlag())
        assert r1.status_code == 200
        j1 = r1.json()
        assert j1["ok"] is True and j1["status"] == "eingetragen"

        # zweites Senden mit gleichem ref ⇒ vorhanden, gleiche id (idempotent)
        j2 = c.post("/api/querverbindung/kalender", json=_umschlag()).json()
        assert j2["status"] == "vorhanden" and j2["id"] == j1["id"]

        # Read-only-Sicht zeigt genau einen Termin samt Quelle in der Beschreibung
        liste = c.get("/api/kalender/termine").json()
        assert len(liste) == 1
        t = liste[0]
        assert t["titel"] == "Kickoff" and t["ort"] == "Büro"
        assert t["quelle"] == "admin" and t["beginn"] == "2026-07-01T15:00"
        assert "Projektstart" in t["beschreibung"]
        assert "Quelle: admin:termin:t1" in t["beschreibung"]


def test_kalender_empfang_beginn_pflicht(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        r = c.post("/api/querverbindung/kalender",
                   json=_umschlag(beginn=""))
        assert r.status_code == 400
        assert r.json()["ok"] is False
        # nichts eingetragen
        assert c.get("/api/kalender/termine").json() == []


def test_kalender_termin_loeschen(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/querverbindung/kalender", json=_umschlag()).json()["id"]
        assert len(c.get("/api/kalender/termine").json()) == 1
        r = c.delete(f"/api/kalender/termine/{tid}")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert c.get("/api/kalender/termine").json() == []
        # zweites Löschen ⇒ 404 (schon weg)
        assert c.delete(f"/api/kalender/termine/{tid}").status_code == 404


def test_kalender_sicht_von_filter(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        c.post("/api/querverbindung/kalender",
               json=_umschlag(beginn="2026-06-01T09:00", ref="admin:termin:alt"))
        c.post("/api/querverbindung/kalender",
               json=_umschlag(beginn="2026-08-01T09:00", ref="admin:termin:neu"))
        # ab 2026-07-01 darf nur der August-Termin auftauchen
        ab_juli = c.get("/api/kalender/termine", params={"von": "2026-07-01"}).json()
        assert len(ab_juli) == 1 and ab_juli[0]["beginn"] == "2026-08-01T09:00"
        # ohne Filter beide, aufsteigend nach beginn
        alle = c.get("/api/kalender/termine").json()
        assert [t["beginn"] for t in alle] == ["2026-06-01T09:00", "2026-08-01T09:00"]
