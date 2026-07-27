"""A5/V19 (docs/34) — /api/kategorie: read-only Liste der Notizen eines Ordners
(= ``bereich.memory_ref``) für Dizz Admins Bereichs-Cockpit. Ordner-Name
case-insensitiv; sensible Notizen werden gelistet, aber OHNE Inhalts-Auszug."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def test_kategorie_listet_nur_diesen_ordner(tmp_path):
    with _client(tmp_path) as c:
        oid = c.post("/api/ordner", json={"name": "Studium Informatik"}).json()["id"]
        andere = c.post("/api/ordner", json={"name": "Privat"}).json()["id"]
        c.post("/api/notizen", json={"titel": "Vorlesung 1", "inhalt": "Inhalt A",
                                     "ordner_id": oid})
        c.post("/api/notizen", json={"titel": "Geheim", "inhalt": "PIN 1234",
                                     "ordner_id": oid, "sensibel": True})
        c.post("/api/notizen", json={"titel": "Lose", "inhalt": "ohne Ordner"})
        c.post("/api/notizen", json={"titel": "Urlaub", "inhalt": "X", "ordner_id": andere})

        r = c.get("/api/kategorie?ordner=studium informatik").json()    # case-insensitiv
        assert {n["titel"] for n in r} == {"Vorlesung 1", "Geheim"}
        eintr = {n["titel"]: n for n in r}
        assert eintr["Vorlesung 1"]["auszug"] == "Inhalt A"
        # sensible Notiz: gelistet, aber Inhalt unterdrückt (kein Leak nach außen)
        assert eintr["Geheim"]["sensibel"] is True and eintr["Geheim"]["auszug"] == ""
        # limit greift
        assert len(c.get("/api/kategorie?ordner=Studium Informatik&limit=1").json()) == 1


def test_kategorie_unbekannt_und_leer(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/kategorie?ordner=gibtsnicht").json() == []
        assert c.get("/api/kategorie").json() == []


def test_kategorie_kanon_pfad(tmp_path):
    """V19-Kantenvertrag (docs/67 §6): kanon-only Auflösung + Vererbung Ordner→Notiz;
    dangling kanon fällt auf den Ordner-Namen durch."""
    with _client(tmp_path) as c:
        oid = c.post("/api/ordner", json={"name": "Studium Informatik"}).json()["id"]
        c.post("/api/notizen", json={"titel": "Vorlesung 1", "inhalt": "Inhalt A", "ordner_id": oid})
        c.post("/api/notizen", json={"titel": "Geheim", "inhalt": "PIN 1234",
                                     "ordner_id": oid, "sensibel": True})
        b = c.post("/api/bereiche", json={"name": "Studium", "art": "wissen"}).json()["id"]
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "ordner", "id": oid, "bereich_id": b}).json()["ok"]
        assert c.put(f"/api/bereiche/{b}/kanon", json={"kanon_id": "A-7"}).json()["ok"]
        # kanon-Pfad: beide Notizen (über den Ordner geerbt), sensibel ohne Auszug
        r = c.get("/api/kategorie?kanon=A-7").json()
        assert {n["titel"] for n in r} == {"Vorlesung 1", "Geheim"}
        assert {n["titel"]: n for n in r}["Geheim"]["auszug"] == ""
        # kanon gewinnt gegen einen falschen ordner:
        assert {n["titel"] for n in c.get("/api/kategorie?kanon=A-7&ordner=gibtsnicht").json()} \
            == {"Vorlesung 1", "Geheim"}
        # dangling kanon ⇒ Ordner-Fallback greift:
        assert {n["titel"] for n in
                c.get("/api/kategorie?kanon=GIBTSNICHT&ordner=studium informatik").json()} \
            == {"Vorlesung 1", "Geheim"}
        # dangling kanon ohne ordner ⇒ []
        assert c.get("/api/kategorie?kanon=GIBTSNICHT").json() == []
