"""Tests Dizz Admin — A8 Mahnwesen (docs/30 B). Eigene Mahn-Entität NEBEN der
GoBD-Rechnung: eskalierende Stufen + neue Zahlungsfrist + Gebühr, read-only auf die
Rechnung (verändert sie nie). Mahn-Fristen fließen in Wächter + Fristen-Cockpit.
Lauf: pytest tests/ -q
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as lm


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def _gestellte_rechnung(c, faellig_am):
    rid = c.post("/api/rechnungen", json={
        "titel": "Leistung", "faellig_am": faellig_am,
        "positionen": [{"einzelpreis_cent": 10000, "ust_satz": 19}]}).json()["id"]
    c.post(f"/api/rechnungen/{rid}/stellen")
    return rid


def test_vorschlag_und_eskalation(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        rid = _gestellte_rechnung(c, gestern)                 # überfällig
        # Vorschlag: erste Stufe (Zahlungserinnerung)
        v = c.get("/api/mahnungen/vorschlaege").json()
        assert v["max_stufe"] == 3
        assert len(v["vorschlaege"]) == 1
        assert v["vorschlaege"][0]["naechste_stufe"] == 1
        assert v["vorschlaege"][0]["rechnung_id"] == rid

        # Stufe 1 anlegen (auto-Stufe, Standard-Frist in der Zukunft)
        m1 = c.post("/api/mahnungen", json={"rechnung_id": rid}).json()
        assert m1["ok"] and m1["stufe"] == 1 and m1["gebuehr_cent"] == 0
        assert m1["frist_am"] > date.today().isoformat()
        # Solange die Mahnfrist läuft, KEIN neuer Vorschlag
        assert c.get("/api/mahnungen/vorschlaege").json()["vorschlaege"] == []

        # Mahnfrist künstlich in die Vergangenheit ziehen ⇒ Eskalation auf Stufe 2
        c.patch(f"/api/mahnungen/{m1['id']}", json={"frist_am": gestern})
        v2 = c.get("/api/mahnungen/vorschlaege").json()["vorschlaege"]
        assert len(v2) == 1 and v2[0]["naechste_stufe"] == 2
        m2 = c.post("/api/mahnungen", json={"rechnung_id": rid}).json()
        assert m2["stufe"] == 2 and m2["gebuehr_cent"] == 500


def test_rechnung_bleibt_unangetastet(tmp_path):
    """GoBD: das Mahnen ändert die gestellte Rechnung in keinem Feld."""
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        rid = _gestellte_rechnung(c, gestern)
        vorher = c.get(f"/api/rechnungen/{rid}").json()
        c.post("/api/mahnungen", json={"rechnung_id": rid})
        nachher = c.get(f"/api/rechnungen/{rid}").json()
        for k in ("nummer", "status", "netto_cent", "ust_cent", "brutto_cent", "datum", "faellig_am"):
            assert vorher[k] == nachher[k]


def test_nur_offene_rechnung_mahnbar(tmp_path):
    with _client(tmp_path) as c:
        # Entwurf (nicht gestellt) ⇒ nicht mahnbar
        rid = c.post("/api/rechnungen", json={
            "positionen": [{"einzelpreis_cent": 100, "ust_satz": 0}]}).json()["id"]
        r = c.post("/api/mahnungen", json={"rechnung_id": rid})
        assert r.status_code == 409
        # unbekannte Rechnung ⇒ 404
        assert c.post("/api/mahnungen", json={"rechnung_id": "x"}).status_code == 404


def test_bezahlt_schliesst_offene_mahnungen(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        rid = _gestellte_rechnung(c, gestern)
        c.post("/api/mahnungen", json={"rechnung_id": rid})
        assert len(c.get("/api/mahnungen?status=offen").json()) == 1
        c.post(f"/api/rechnungen/{rid}/bezahlt")
        assert c.get("/api/mahnungen?status=offen").json() == []
        assert len(c.get("/api/mahnungen?status=erledigt").json()) == 1


def test_mahnfrist_im_cockpit_und_waechter(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        rid = _gestellte_rechnung(c, gestern)
        m = c.post("/api/mahnungen", json={"rechnung_id": rid, "frist_am": gestern}).json()
        ref = f"admin:mahnung:{m['id']}"
        # Fristen-Cockpit zeigt die Mahn-Frist (überfällig)
        co = c.get("/api/fristen-cockpit").json()
        alle = [it for g in co["gruppen"].values() for it in g]
        assert any(it["ref"] == ref and it["art"] == "mahnung" for it in alle)
        # Wächter zählt fällige Mahnungen
        w = c.get("/api/waechter").json()
        assert any(x["id"] == m["id"] for x in w["faellige_mahnungen"])
        # A5: aus der Mahn-Frist eine Aufgabe machen
        res = c.post("/api/fristen-cockpit/zu-aufgabe", json={"ref": ref}).json()
        assert res["ok"] and res["faellig"] == gestern


def test_gebuehr_und_titel_override(tmp_path):
    with _client(tmp_path) as c:
        gestern = (date.today() - timedelta(days=1)).isoformat()
        rid = _gestellte_rechnung(c, gestern)
        m = c.post("/api/mahnungen", json={
            "rechnung_id": rid, "stufe": 3, "gebuehr_cent": 2500,
            "titel": "Letzte Mahnung vor Inkasso"}).json()
        assert m["stufe"] == 3 and m["gebuehr_cent"] == 2500
        liste = c.get(f"/api/mahnungen?rechnung_id={rid}").json()
        assert liste[0]["titel"] == "Letzte Mahnung vor Inkasso"
        assert liste[0]["nummer"]  # Rechnungs-Kontext mitgeliefert
