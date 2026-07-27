"""Tests Dizz News OPML-Import/-Export (Backlog docs/33).

Deckt ab: valider Export + Round-trip, Dedup über die url (vorhandene /
gelöschte / datei-interne Doubletten), Robustheit gegen fehlende Attribute,
und vor allem die SICHERHEIT — Billion-Laughs/DTD wird abgewiesen, Größen-
Limit greift, kaputtes XML ⇒ 400 (kein Datenschreiben)."""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from appkit.db import default_db_path
from newsapp import main as nm


def _client(data_dir):
    app = nm.build_app(data_dir=data_dir, start_timer=False)
    return TestClient(app)


def test_opml_export_valide_und_seeds(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/api/quellen/opml-export")
        assert r.status_code == 200
        assert "opml" in r.headers["content-type"]
        root = ET.fromstring(r.content)            # valides XML
        assert root.tag == "opml"
        assert root.find("head/title") is not None
        urls = {o.attrib.get("xmlUrl") for o in root.iter("outline")}
        for _name, url, _sektor in nm.SEED_QUELLEN:
            assert url in urls                     # alle aktiven Quellen exportiert


def test_opml_import_neu_dedup_und_attribute(tmp_path):
    with _client(tmp_path) as c:
        c.get("/api/quellen")                      # Seeds anlegen
        seed_url = nm.SEED_QUELLEN[0][1]
        opml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<opml version="2.0"><head><title>x</title></head><body>'
            '  <outline text="Ordner">'             # verschachtelte Gruppe ohne Feed
            '    <outline title="Neu Eins" xmlUrl="https://neu/eins.xml" category="finanzen"/>'
            '  </outline>'
            '  <outline title="Eins Doppelt" xmlUrl="https://neu/eins.xml"/>'  # Datei-Doublette
            '  <outline text="Ohne Sektor" xmlUrl="https://neu/zwei.xml"/>'    # text→name, Default-Sektor
            '  <outline text="Kein Feed (Gruppe)"/>'                           # ohne xmlUrl ⇒ ignoriert
            f' <outline title="Schon da" xmlUrl="{seed_url}"/>'               # bereits vorhanden
            '</body></opml>'
        ).encode("utf-8")
        r = c.post("/api/quellen/opml-import", content=opml).json()
        assert r["neu"] == 2                        # eins.xml + zwei.xml
        assert r["uebersprungen"] >= 2              # Datei-Doublette + Seed-URL

        qs = {q["url"]: q for q in c.get("/api/quellen").json()}
        assert qs["https://neu/eins.xml"]["sektor"] == "finanzen"
        assert qs["https://neu/zwei.xml"]["sektor"] == "allgemein"   # Default
        assert qs["https://neu/zwei.xml"]["name"] == "Ohne Sektor"   # text→name

        # Re-Import derselben Datei ⇒ alles bekannt, nichts neu
        r2 = c.post("/api/quellen/opml-import", content=opml).json()
        assert r2["neu"] == 0

        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "quellen_opml_import" in actions


def test_opml_dedup_geloeschte_quelle(tmp_path):
    """Eine bewusst gelöschte Quelle (deleted_at) darf per Re-Import NICHT
    zurückkommen — der Dedup-Abgleich läuft ohne deleted_at-Filter."""
    with _client(tmp_path) as c:
        c.post("/api/quellen", json={"name": "Weg", "url": "https://weg/f.xml",
                                     "sektor": "tech"})
    # direkt im DB-File soft-löschen (kein per-Quelle-Delete-Endpoint nötig)
    con = sqlite3.connect(str(default_db_path(nm.APP_ID, data_root=tmp_path)))
    con.execute("UPDATE quellen SET deleted_at='2026-01-01T00:00:00Z' "
                "WHERE url='https://weg/f.xml'")
    con.commit()
    con.close()
    with _client(tmp_path) as c:
        opml = ('<opml version="2.0"><body>'
                '<outline title="Weg" xmlUrl="https://weg/f.xml"/>'
                '</body></opml>').encode("utf-8")
        r = c.post("/api/quellen/opml-import", content=opml).json()
        assert r["neu"] == 0 and r["uebersprungen"] == 1
        urls = {q["url"] for q in c.get("/api/quellen").json()}
        assert "https://weg/f.xml" not in urls      # bleibt gelöscht


def test_opml_roundtrip(tmp_path):
    with _client(tmp_path / "a") as c:
        c.post("/api/quellen", json={"name": "RT & Co <x>", "url": "https://rt/feed.xml",
                                     "sektor": "tech"})
        xml = c.get("/api/quellen/opml-export").content
    with _client(tmp_path / "b") as c2:
        c2.get("/api/quellen")                      # b's eigene Seeds anlegen
        r = c2.post("/api/quellen/opml-import", content=xml).json()
        assert r["neu"] == 1                        # nur die RT-Quelle ist neu (Seeds dedupt)
        qs = {q["url"]: q for q in c2.get("/api/quellen").json()}
        assert qs["https://rt/feed.xml"]["name"] == "RT & Co <x>"   # Sonderzeichen round-trip-fest


def test_opml_billion_laughs_abgewiesen(tmp_path):
    lol = ('<?xml version="1.0"?>'
           '<!DOCTYPE lolz [<!ENTITY a "AAAAAAAAAA">'
           '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
           '<opml version="2.0"><body>'
           '<outline title="&b;" xmlUrl="https://evil/feed.xml"/></body></opml>'
           ).encode("utf-8")
    with _client(tmp_path) as c:
        r = c.post("/api/quellen/opml-import", content=lol)
        assert r.status_code == 400                 # DTD ⇒ Abweisung
        urls = {q["url"] for q in c.get("/api/quellen").json()}
        assert not any("evil" in u for u in urls)   # nichts angelegt


def test_opml_groessen_limit(tmp_path):
    big = b"<opml><body>" + b" " * (nm._OPML_MAX_BYTES + 16) + b"</body></opml>"
    with _client(tmp_path) as c:
        r = c.post("/api/quellen/opml-import", content=big)
        assert r.status_code == 413


def test_opml_kaputtes_xml(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/quellen/opml-import", content=b"<opml><body><outline title=")
        assert r.status_code == 400
