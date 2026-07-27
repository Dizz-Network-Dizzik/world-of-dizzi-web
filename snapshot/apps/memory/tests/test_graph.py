"""Wissens-Graph (P2.3): Knoten=Notiz, Kanten=[[Wikilinks]] (aufgelöst), grad,
herkunft-Flag (Farbachse)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _neu(c, titel, inhalt=""):
    return c.post("/api/notizen", json={"titel": titel, "inhalt": inhalt}).json()["id"]


def test_graph_knoten_und_kanten(tmp_path):
    with _client(tmp_path) as c:
        a = _neu(c, "Ziel", "Inhalt.")
        b = _neu(c, "Quelle", "Link auf [[Ziel]].")
        _neu(c, "Insel", "ohne Verknüpfung")          # isolierter Knoten bleibt im Graph
        g = c.get("/api/graph").json()
        assert len(g["nodes"]) == 3
        assert {"von": b, "nach": a} in g["edges"] and len(g["edges"]) == 1
        grad = {n["id"]: n["grad"] for n in g["nodes"]}
        assert grad[a] == 1 and grad[b] == 1
        # unaufgelöste Links erzeugen keine Kante
        _neu(c, "Lose", "verweist auf [[Gibt Es Nicht]]")
        assert len(c.get("/api/graph").json()["edges"]) == 1


def test_graph_herkunft_flag(tmp_path):
    with _client(tmp_path) as c:
        _neu(c, "Eigene", "x")
        c.post("/api/querverbindung/archivieren",
               json={"titel": "Aus News", "inhalt": "y", "app": "news", "explizit": True})
        g = c.get("/api/graph").json()
        herk = {n["titel"]: n["herkunft"] for n in g["nodes"]}
        assert herk["Aus News"] is True and herk["Eigene"] is False
