"""Tests Dizz Admin — A5 Frist→Aufgabe (in-Prozess, docs/30 B).
Aus einer Cockpit-Frist (Rechnung/Geschäfts-Frist/Studien-Frist/Termin) wird per
Klick eine Aufgabe im Projekte-Modul erzeugt — idempotent, mit Frist + Bereich.
Lauf: pytest tests/ -q
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as lm


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def test_geschaefts_frist_wird_aufgabe(tmp_path):
    with _client(tmp_path) as c:
        bald = (date.today() + timedelta(days=3)).isoformat()
        fid = c.post("/api/fristen", json={"titel": "USt-Voranmeldung",
                                           "kategorie": "steuer", "faellig_am": bald}).json()["id"]
        ref = f"admin:frist:{fid}"
        r = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": ref})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and body["status"] == "angelegt"
        aid = body["aufgabe_id"]
        # Aufgabe trägt Titel der Frist + dieselbe Fälligkeit + Herkunfts-Referenz.
        auf = c.get("/api/aufgaben").json()
        treffer = [a for a in auf if a["id"] == aid][0]
        assert treffer["titel"] == "USt-Voranmeldung"
        assert treffer["faellig"] == bald
        assert treffer["quelle_ref"] == ref


def test_idempotent_keine_doppelte_aufgabe(tmp_path):
    with _client(tmp_path) as c:
        bald = (date.today() + timedelta(days=3)).isoformat()
        fid = c.post("/api/fristen", json={"titel": "Frist X", "faellig_am": bald}).json()["id"]
        ref = f"admin:frist:{fid}"
        a1 = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": ref}).json()
        a2 = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": ref}).json()
        assert a1["status"] == "angelegt" and a2["status"] == "vorhanden"
        assert a1["aufgabe_id"] == a2["aufgabe_id"]
        assert len([a for a in c.get("/api/aufgaben").json() if a["quelle_ref"] == ref]) == 1


def test_rechnung_wird_aufgabe_mit_bereich(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        b = c.post("/api/bereiche", json={"name": "Geschäft A", "art": "geschaeft"}).json()["id"]
        rid = c.post("/api/rechnungen", json={
            "titel": "Beratung Mai", "faellig_am": gestern,
            "positionen": [{"einzelpreis_cent": 5000, "ust_satz": 19}]}).json()["id"]
        c.post(f"/api/rechnungen/{rid}/stellen")
        c.put("/api/bereiche/zuordnung", json={"tabelle": "rechnungen", "id": rid, "bereich_id": b})
        res = c.post("/api/fristen-cockpit/zu-aufgabe",
                     json={"ref": f"admin:rechnung:{rid}", "prioritaet": "hoch"}).json()
        assert res["ok"] and res["bereich_id"] == b
        treffer = [a for a in c.get("/api/aufgaben").json() if a["id"] == res["aufgabe_id"]][0]
        assert treffer["bereich_id"] == b and treffer["prioritaet"] == "hoch"
        assert treffer["faellig"] == gestern
        # Bereichs-Filter im Cockpit erfasst die neue Aufgabe (gleiche Achse)
        co_b = c.get(f"/api/fristen-cockpit?bereich_id={b}").json()
        assert any(it["ref"] == f"admin:aufgabe:{res['aufgabe_id']}"
                   for g in co_b["gruppen"].values() for it in g)


def test_titel_ueberschreiben(tmp_path):
    with _client(tmp_path) as c:
        bald = (date.today() + timedelta(days=5)).isoformat()
        fid = c.post("/api/fristen", json={"titel": "Roh", "faellig_am": bald}).json()["id"]
        res = c.post("/api/fristen-cockpit/zu-aufgabe",
                     json={"ref": f"admin:frist:{fid}", "titel": "Eigener Titel"}).json()
        treffer = [a for a in c.get("/api/aufgaben").json() if a["id"] == res["aufgabe_id"]][0]
        assert treffer["titel"] == "Eigener Titel"


def test_aufgabe_ref_wird_abgelehnt(tmp_path):
    with _client(tmp_path) as c:
        aid = c.post("/api/aufgaben", json={"titel": "Schon eine Aufgabe"}).json()["id"]
        r = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": f"admin:aufgabe:{aid}"})
        assert r.status_code == 400 and not r.json()["ok"]


def test_unbekannte_ref_404(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": "admin:frist:gibtsnicht"})
        assert r.status_code == 404
        r2 = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": "müll"})
        assert r2.status_code == 404
