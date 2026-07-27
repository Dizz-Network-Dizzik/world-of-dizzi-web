"""RG-8 (docs/83 §6): Geschäfts-Kopplung admin-Seite.

frist_vorschlagen (dormant, level lokal ⇒ entwurf) legt einen Fristen-ENTWURF an OHNE eine
echte Aufgabe zu erzeugen; frist_naht reist als Zeiger in den Spine; die „Geschäfts-Regie"-
Projektion ist read-only + offline-ehrlich (Management-Regie-Karte injizierbar).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from appkit import ereignis_spine
from adminapp import geschaefts_regie as gr
from adminapp.main import build_app


def _register():
    reg = ereignis_spine.standard_register("admin")
    gr.registriere_ereignis_typen(reg)
    return reg


def test_frist_vorschlagen_ist_lokal_registriert(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        kat = {a["name"]: a for a in c.get("/api/actions").json()["katalog"]}
        assert kat["frist_vorschlagen"]["level"] == "lokal"   # ⇒ Klasse entwurf


def test_frist_vorschlagen_freigabe_legt_entwurf_an_keine_aufgabe(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as c:
        v = c.post("/api/actions/propose", json={
            "name": "frist_vorschlagen", "source": "agent", "warum": "Termin erkannt",
            "params": {"titel": "Steuer-Frist", "faellig": "2026-07-31",
                       "bereich_id": "marke_a", "mail_ref": "kommunikation:nachricht:x"}}).json()
        assert v["status"] == "pending" and v["level"] == "lokal"
        res = c.post(f"/api/actions/{v['id']}/approve").json()   # lokal ⇒ standalone frei
        assert res["status"] == "executed"

        liste = c.get("/api/frist-vorschlaege").json()
        assert len(liste) == 1 and liste[0]["titel"] == "Steuer-Frist"
        # KEINE echte Aufgabe/Frist entstanden — Admins Cockpit/Aufgaben bleiben unberührt:
        conn = app.state.db.get_conn()
        assert conn.execute("SELECT COUNT(*) c FROM aufgaben").fetchone()["c"] == 0


def test_frist_naht_pruefen_emittiert_nur_nahende_als_zeiger(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as c:
        fristen = [
            {"art": "rechnung", "titel": "Rg 42", "faellig": "2026-07-20",
             "bereich_id": "marke_a", "ref": "r1", "dringlichkeit": "heute"},
            {"art": "aufgabe", "titel": "ferner Plan", "faellig": "2027-01-01",
             "bereich_id": "", "ref": "a9", "dringlichkeit": "spaeter"},
        ]
        n = gr.frist_naht_pruefen(app.state.db, fristen, ereignis_register=_register())
        assert n == 1                                   # nur die nahende, nicht die ferne
        ereignisse = c.get("/api/ereignisse").json()
        ev = [e for e in ereignisse["eintraege"] if e["typ"] == "frist_naht"]
        assert len(ev) == 1 and ev[0]["ref"] == "admin:frist:r1"
        assert ev[0]["payload"] == {"bereich_id": "marke_a", "art": "rechnung"}
        assert "Rg 42" not in json.dumps(ereignisse)     # Zeiger, kein Titel-Freitext


def test_geschaefts_regie_offline_ehrlich(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        r = c.get("/api/geschaefts-regie?bereich_id=marke_a").json()
        assert r["verbunden"] is False and "nicht verbunden" in r["hinweis"]


def test_geschaefts_regie_projiziert_mit_fetch(tmp_path):
    def fake(bereich_id):
        return {"agenten": [{"name": "E-Mail-Manager"}],
                "abos": [{"quelle_app": "kommunikation", "aktiv": False}], "laeufe": []}
    with TestClient(build_app(data_dir=tmp_path, regie_karte_fetch=fake)) as c:
        r = c.get("/api/geschaefts-regie?bereich_id=marke_a").json()
        assert r["verbunden"] is True
        assert r["agenten"][0]["name"] == "E-Mail-Manager"
        assert r["abos"][0]["aktiv"] is False            # Standard-Abos AUS (fail-closed)
