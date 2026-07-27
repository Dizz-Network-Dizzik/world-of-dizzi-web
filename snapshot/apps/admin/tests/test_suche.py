"""Tests Dizz Admin — globale Cross-Modul-Suche (docs/30 A2): EINE Suche über
Dokumente · Projekte · Aufgaben · Rechnungen · Kunden · Studium, bereich-gefiltert.
"""
from fastapi.testclient import TestClient

from adminapp import main as am


def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path))


def test_suche_findet_ueber_module(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/projekte", json={"name": "Akquise Nordpol", "beschreibung": "Kampagne"})
        c.post("/api/aufgaben", json={"titel": "Nordpol-Logo entwerfen"})
        c.post("/api/kunden", json={"name": "Nordpol GmbH", "firma": "Nordpol"})
        c.post("/api/dokumente/upload",
               files={"datei": ("v.pdf", b"%PDF v", "application/pdf")},
               data={"titel": "Vertrag Nordpol", "typ": "Vertrag"})
        c.post("/api/aufgaben", json={"titel": "Etwas ganz anderes"})

        res = c.get("/api/suche?q=nordpol").json()
        typen = {t["typ"] for t in res["treffer"]}
        assert {"projekt", "aufgabe", "kunde", "dokument"} <= typen
        assert res["je_typ"]["aufgabe"] == 1          # nur die Nordpol-Aufgabe
        assert all("nordpol" in (t["titel"] + t["untertitel"]).lower()
                   or t["typ"] == "dokument" for t in res["treffer"])
        # leere Query ⇒ keine Treffer (kein Voll-Scan)
        assert c.get("/api/suche?q=").json()["anzahl"] == 0
        # case-insensitiv
        assert c.get("/api/suche?q=NORDPOL").json()["anzahl"] == res["anzahl"]


def test_suche_bereich_filter(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Geschäft X", "art": "geschaeft"}).json()["id"]
        p1 = c.post("/api/projekte", json={"name": "Solar Projekt"}).json()["id"]
        c.post("/api/projekte", json={"name": "Solar Hobby"})       # Allgemein
        c.put("/api/bereiche/zuordnung", json={"tabelle": "projekte", "id": p1, "bereich_id": b})

        assert c.get("/api/suche?q=solar").json()["anzahl"] == 2
        nur_b = c.get(f"/api/suche?q=solar&bereich_id={b}").json()
        assert nur_b["anzahl"] == 1 and nur_b["treffer"][0]["id"] == p1
        assert c.get("/api/suche?q=solar&bereich_id=").json()["anzahl"] == 1   # nur Allgemein
