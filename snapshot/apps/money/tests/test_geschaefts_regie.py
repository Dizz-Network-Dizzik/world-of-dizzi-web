"""RG-8 (docs/83 §6): Geschäfts-Kopplung money-Seite — beleg_vorschlagen (dormant) + Zeiger.

Beweist: der Vertrag ist als geld-Aktion registriert (Boden pre_approval, standalone-Freigabe
fail-closed), der Handler legt einen Beleg-ENTWURF an OHNE zu buchen (ledger/EÜR unberührt),
und ``beleg_angelegt`` reist als ZEIGER (kein Betrag/Gegenpartei/Zweck) in den Spine.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from appkit import ereignis_spine
from moneyapp import geschaefts_regie as gr
from moneyapp.main import build_app


def _register():
    reg = ereignis_spine.standard_register("finanzen")
    gr.registriere_ereignis_typen(reg)
    return reg


def test_beleg_vorschlagen_ist_hochsicher_registriert(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as c:
        kat = {a["name"]: a for a in c.get("/api/actions").json()["katalog"]}
        assert kat["beleg_vorschlagen"]["level"] == "hochsicher"   # ⇒ Klasse geld


def test_propose_dann_freigabe_standalone_fail_closed(tmp_path):
    """Boden-Beweis auf HITL-Ebene: ein geld-Vorschlag lässt sich standalone NICHT freigeben
    (hochsicher-Auth Pflicht) — der KLASSEN_BODEN greift, kein Pfad bucht ohne Freigabe."""
    with TestClient(build_app(data_dir=tmp_path)) as c:
        v = c.post("/api/actions/propose", json={
            "name": "beleg_vorschlagen", "source": "agent", "warum": "Rechnung erkannt",
            "params": {"betrag_minor": 12300, "gegenpartei": "ACME"}}).json()
        assert v["status"] == "pending" and v["level"] == "hochsicher"
        r = c.post(f"/api/actions/{v['id']}/approve")
        assert r.status_code == 403 and "hochsicher" in r.json()["error"]


def test_handler_legt_entwurf_an_bucht_nie_und_emittiert_zeiger(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as c:
        res = gr.beleg_vorschlag_anlegen(
            app.state.db, "dizzi", bereich_id="marke_a", betrag_minor=12300,
            gegenpartei="ACME GmbH", zweck="Rechnung 42", mail_ref="kommunikation:nachricht:x7",
            ereignis_register=_register())
        assert res["gebucht"] is False and res["status"] == "entwurf"

        # Review-Liste zeigt den Entwurf (Davids Belegs→EÜR-Strecke greift hier manuell):
        liste = c.get("/api/beleg-vorschlaege").json()
        assert len(liste) == 1
        assert liste[0]["gegenpartei"] == "ACME GmbH" and liste[0]["betrag_minor"] == 12300

        # beleg_angelegt als ZEIGER — kein Betrag/Gegenpartei/Zweck reist im Ereignis:
        ereignisse = c.get("/api/ereignisse").json()
        ev = [e for e in ereignisse["eintraege"] if e["typ"] == "beleg_angelegt"]
        assert len(ev) == 1 and ev[0]["ref"].startswith("finanzen:beleg_vorschlag:")
        assert ev[0]["payload"] == {"bereich_id": "marke_a", "status": "entwurf"}
        blob = json.dumps(ereignisse)
        assert "ACME" not in blob and "Rechnung 42" not in blob and "12300" not in blob

        # LEDGER/EÜR UNBERÜHRT: keine Buchung, kein Posting entstanden (docs/83 §6).
        conn = app.state.db.get_conn()
        assert conn.execute("SELECT COUNT(*) c FROM buchungen").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM postings").fetchone()["c"] == 0
