"""Bidirektionale Wikilinks (P1a): ausgehende [[Links]] aufgelöst + „Erwähnt in"-
Backlinks. Obsidian/Logseq-Muster, case-insensitiv, Alias + Dedupe."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _neu(c, titel, inhalt=""):
    return c.post("/api/notizen", json={"titel": titel, "inhalt": inhalt}).json()["id"]


def test_backlinks_und_ausgehend(tmp_path):
    with _client(tmp_path) as c:
        a = _neu(c, "Projekt Alpha", "Das Hauptprojekt.")
        b = _neu(c, "Notiz B", "Siehe [[Projekt Alpha]] für Details.")
        # B verweist auf A (aufgelöst)
        vb = c.get(f"/api/notizen/{b}/verknuepfungen").json()
        assert vb["ausgehend"] == [{"titel": "Projekt Alpha", "id": a}]
        # A wird in B erwähnt (Backlink)
        va = c.get(f"/api/notizen/{a}/verknuepfungen").json()
        assert {"id": b, "titel": "Notiz B"} in va["erwaehnt_in"]
        assert va["ausgehend"] == []


def test_unaufgeloester_link(tmp_path):
    with _client(tmp_path) as c:
        n = _neu(c, "Quelle", "Verweis auf [[Existiert Nicht]].")
        v = c.get(f"/api/notizen/{n}/verknuepfungen").json()
        assert v["ausgehend"] == [{"titel": "Existiert Nicht", "id": None}]


def test_alias_dedupe_und_case(tmp_path):
    with _client(tmp_path) as c:
        z = _neu(c, "Ziel", "Inhalt.")
        n = _neu(c, "Mehrfach", "[[ziel|der Alias]] und nochmal [[Ziel]] und [[ZIEL]].")
        v = c.get(f"/api/notizen/{n}/verknuepfungen").json()
        # dedupliziert (case-insensitiv), Alias abgeschnitten, auf Ziel aufgelöst
        assert len(v["ausgehend"]) == 1
        assert v["ausgehend"][0]["id"] == z
        # Backlink von „Ziel" zeigt „Mehrfach"
        vz = c.get(f"/api/notizen/{z}/verknuepfungen").json()
        assert [e["titel"] for e in vz["erwaehnt_in"]] == ["Mehrfach"]
