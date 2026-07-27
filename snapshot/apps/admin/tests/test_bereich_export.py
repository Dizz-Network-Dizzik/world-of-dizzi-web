"""Tests Dizz Admin — A3 Bereichs-Export-Bundle (docs/30 B). Alle Inhalte eines
Bereichs als ZIP: bereich.json + je Modul JSON-Metadaten + Vault-Dateien der
Dokumente (verschlüsselte nur als Hinweis). DSGVO-Portabilität.
Lauf: pytest tests/ -q
"""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from adminapp import main as am


def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path))


def _zuordnen(c, tabelle, rid, bid):
    return c.put("/api/bereiche/zuordnung",
                 json={"tabelle": tabelle, "id": rid, "bereich_id": bid})


def test_export_bundelt_inhalte_und_dateien(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Mandant Müller", "art": "mandant"}).json()["id"]
        # Dokument mit bekanntem Inhalt
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("vertrag.pdf", b"%PDF-1.7 INHALT-XYZ", "application/pdf")},
                     data={"titel": "Vertrag", "typ": "Vertrag"}).json()["id"]
        _zuordnen(c, "dokumente", did, b)
        # Rechnung (gestellt) + Positionen
        rid = c.post("/api/rechnungen", json={
            "titel": "Leistung", "positionen": [{"einzelpreis_cent": 1000, "ust_satz": 19}]}).json()["id"]
        c.post(f"/api/rechnungen/{rid}/stellen")
        _zuordnen(c, "rechnungen", rid, b)
        # Projekt im selben Bereich
        pid = c.post("/api/projekte", json={"name": "Projekt Z"}).json()["id"]
        _zuordnen(c, "projekte", pid, b)

        r = c.get(f"/api/bereiche/{b}/export")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "dizz-admin-bereich-Mandant_M" in r.headers["content-disposition"]

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        namen = set(zf.namelist())
        assert {"manifest.json", "bereich.json", "dokumente.json",
                "rechnungen.json", "rechnung_positionen.json", "projekte.json"} <= namen
        # Datei-Inhalt 1:1 mit drin
        datei = [n for n in namen if n.startswith("dokumente/")][0]
        assert zf.read(datei) == b"%PDF-1.7 INHALT-XYZ"
        # Metadaten korrekt
        man = json.loads(zf.read("manifest.json"))
        assert man["bereich_id"] == b and man["dateien"] == 1
        assert man["tabellen"]["rechnung_positionen"] == 1
        ber = json.loads(zf.read("bereich.json"))
        assert ber["name"] == "Mandant Müller"
        rech = json.loads(zf.read("rechnungen.json"))
        assert len(rech) == 1 and rech[0]["id"] == rid


def test_export_nur_eigener_bereich(tmp_path):
    with _client(tmp_path) as c:
        b1 = c.post("/api/bereiche", json={"name": "B1"}).json()["id"]
        b2 = c.post("/api/bereiche", json={"name": "B2"}).json()["id"]
        d1 = c.post("/api/dokumente/upload",
                    files={"datei": ("a.pdf", b"%PDF a", "application/pdf")}).json()["id"]
        d2 = c.post("/api/dokumente/upload",
                    files={"datei": ("b.pdf", b"%PDF b", "application/pdf")}).json()["id"]
        _zuordnen(c, "dokumente", d1, b1)
        _zuordnen(c, "dokumente", d2, b2)
        zf = zipfile.ZipFile(io.BytesIO(c.get(f"/api/bereiche/{b1}/export").content))
        docs = json.loads(zf.read("dokumente.json"))
        assert len(docs) == 1 and docs[0]["id"] == d1
        # Nur die eine Datei dieses Bereichs
        assert len([n for n in zf.namelist() if n.startswith("dokumente/")]) == 1


def test_export_verschluesselt_nur_hinweis(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Safe"}).json()["id"]
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("geheim.pdf", b"%PDF geheim", "application/pdf")},
                     data={"verschluesselt": "1"}).json()["id"]
        _zuordnen(c, "dokumente", did, b)
        zf = zipfile.ZipFile(io.BytesIO(c.get(f"/api/bereiche/{b}/export").content))
        man = json.loads(zf.read("manifest.json"))
        # Metadaten dabei, Datei NICHT
        assert man["verschluesselt_uebersprungen"] == 1 and man["dateien"] == 0
        assert [n for n in zf.namelist() if n.startswith("dokumente/")] == []
        assert json.loads(zf.read("dokumente.json"))[0]["id"] == did


def test_export_unbekannter_bereich_404(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/bereiche/gibtsnicht/export").status_code == 404


def test_export_leerer_bereich(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Leer"}).json()["id"]
        zf = zipfile.ZipFile(io.BytesIO(c.get(f"/api/bereiche/{b}/export").content))
        # bereich.json + manifest.json immer dabei, keine Modul-Tabellen
        assert {"bereich.json", "manifest.json"} <= set(zf.namelist())
        assert json.loads(zf.read("manifest.json"))["tabellen"] == {}
