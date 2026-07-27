"""UI/UX-Phase Vorarbeit (docs/28 §16): die Modul-Listen exponieren ``bereich_id``
in ihren ``_public``-Ausgaben UND akzeptieren einen ``?bereich_id=``-Filter
(None=alle · ''=nur „Allgemein" · id=Bereich). Das ist die Backend-Grundlage für
die bereichs-gruppierte/-gefilterte vereinte Oberfläche.
"""
from fastapi.testclient import TestClient

from adminapp import main as am


def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path))


def test_bereich_id_in_public_ausgaben(tmp_path):
    """Jede Modul-Liste trägt ``bereich_id`` je Eintrag (für die Sektions-Gruppierung)."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Studium Informatik", "art": "studium"}).json()["id"]
        pid = c.post("/api/projekte", json={"name": "Bachelorarbeit"}).json()["id"]
        aid = c.post("/api/aufgaben", json={"titel": "Exposé"}).json()["id"]
        tid = c.post("/api/termine", json={"titel": "Kolloquium", "beginn": "2026-09-01"}).json()["id"]
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("po.pdf", b"%PDF po", "application/pdf")},
                     data={"typ": "Sonstiges"}).json()["id"]
        kid = c.post("/api/kunden", json={"name": "ACME"}).json()["id"]
        for tab, rid in (("projekte", pid), ("aufgaben", aid), ("termine", tid),
                         ("dokumente", did), ("kunden", kid)):
            assert c.put("/api/bereiche/zuordnung",
                         json={"tabelle": tab, "id": rid, "bereich_id": b}).json()["ok"]
        # bereich_id reist in der jeweiligen Listen-Ausgabe mit
        assert c.get("/api/projekte").json()[0]["bereich_id"] == b
        assert c.get("/api/aufgaben").json()[0]["bereich_id"] == b
        assert c.get("/api/termine").json()[0]["bereich_id"] == b
        assert c.get("/api/dokumente").json()[0]["bereich_id"] == b
        assert c.get("/api/kunden").json()[0]["bereich_id"] == b


def test_bereich_id_filter_je_modul(tmp_path):
    """``?bereich_id=`` filtert serverseitig: id=Bereich · ''=nur „Allgemein" · ohne=alle."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Agentur", "art": "geschaeft"}).json()["id"]
        p_zu = c.post("/api/projekte", json={"name": "Kampagne"}).json()["id"]
        p_frei = c.post("/api/projekte", json={"name": "Sonstiges"}).json()["id"]
        c.put("/api/bereiche/zuordnung", json={"tabelle": "projekte", "id": p_zu, "bereich_id": b})

        alle = c.get("/api/projekte").json()
        assert {p["id"] for p in alle} == {p_zu, p_frei}        # ohne Filter = alles

        nur_b = c.get(f"/api/projekte?bereich_id={b}").json()
        assert [p["id"] for p in nur_b] == [p_zu]               # id = nur dieser Bereich

        allgemein = c.get("/api/projekte?bereich_id=").json()
        assert [p["id"] for p in allgemein] == [p_frei]         # '' = nur unzugeordnet

        # Tresor + Geschäft folgen demselben Vertrag
        d_zu = c.post("/api/dokumente/upload",
                      files={"datei": ("a.pdf", b"%PDF a", "application/pdf")},
                      data={"typ": "Rechnung"}).json()["id"]
        c.post("/api/dokumente/upload",
               files={"datei": ("b.pdf", b"%PDF b", "application/pdf")},
               data={"typ": "Sonstiges"})
        c.put("/api/bereiche/zuordnung", json={"tabelle": "dokumente", "id": d_zu, "bereich_id": b})
        assert [d["id"] for d in c.get(f"/api/dokumente?bereich_id={b}").json()] == [d_zu]
        assert len(c.get("/api/dokumente?bereich_id=").json()) == 1
