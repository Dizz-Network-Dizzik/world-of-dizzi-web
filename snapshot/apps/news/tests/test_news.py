"""Tests Dizz News (R2.1): Vertrags-Konformität + Feed-Domäne (Abruf gemockt,
Dedupe, Sektor-Filter, Kachel-KPIs, Automatik-Settings)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit import conformance
from newsapp import main as nm


def _client(tmp_path, monkeypatch, feeds=None):
    if feeds is not None:
        monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    app = nm.build_app(data_dir=tmp_path, start_timer=False)
    return TestClient(app)


def test_vertrag_konform(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        conformance.check_contract(c, "news")
        assert c.get("/auth/me").json()["level"] == "lokal"


def test_abruf_dedupe_und_kachel(tmp_path, monkeypatch):
    feeds = {
        nm.SEED_QUELLEN[0][1]: [
            {"titel": "A", "link": "https://x/a", "zusammenfassung": "aa", "published": "2026-06-12"},
            {"titel": "B", "link": "https://x/b", "zusammenfassung": "bb", "published": "2026-06-12"},
        ],
        nm.SEED_QUELLEN[1][1]: [
            {"titel": "C", "link": "https://x/c", "zusammenfassung": "cc", "published": None},
        ],
        nm.SEED_QUELLEN[2][1]: [],
        nm.SEED_QUELLEN[3][1]: [],
        nm.SEED_QUELLEN[4][1]: [],
    }
    with _client(tmp_path, monkeypatch, feeds) as c:
        r = c.post("/api/abrufen").json()
        assert r["neu"] == 3 and r["quellen"] == len(nm.SEED_QUELLEN) and r["fehler"] == 0
        # Zweiter Abruf: alles Duplikat ⇒ 0 neu
        assert c.post("/api/abrufen").json()["neu"] == 0

        arts = c.get("/api/artikel").json()
        assert len(arts) == 3 and {a["titel"] for a in arts} == {"A", "B", "C"}
        tech = c.get("/api/artikel?sektor=tech").json()
        assert [a["titel"] for a in tech] == ["C"]

        s = c.get("/api/summary").json()
        kpis = {k["id"]: k["value"] for k in s["kpis"]}
        assert kpis["quellen"] == len(nm.SEED_QUELLEN) and kpis["artikel"] == 3
        assert kpis["abruf"] != "—"

        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "feeds_abgerufen" in actions


def test_quellen_fehler_stoppen_nicht(tmp_path, monkeypatch):
    def kaputt(url):
        if url == nm.SEED_QUELLEN[0][1]:
            raise RuntimeError("offline")
        return [{"titel": "X", "link": "https://x/x", "zusammenfassung": "", "published": None}]
    monkeypatch.setattr(nm, "_lade_feed", kaputt)
    app = nm.build_app(data_dir=tmp_path, start_timer=False)
    with TestClient(app) as c:
        r = c.post("/api/abrufen").json()
        # 2 intakte Quellen liefern denselben Link ⇒ Dedupe behält genau 1
        assert r["fehler"] == 1 and r["neu"] == 1


def test_eigene_quelle_und_settings(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        assert c.post("/api/quellen", json={"name": "Eigene", "url": "https://q/rss",
                                            "sektor": "finanzen"}).json()["ok"]
        assert any(q["name"] == "Eigene" for q in c.get("/api/quellen").json())

        s = c.get("/api/settings").json()
        assert s["abruf_intervall_min"] == 60 and s["automatik_aktiv"] is True
        assert c.put("/api/settings", json={"key": "abruf_intervall_min", "value": 2}).status_code == 400
        assert c.put("/api/settings", json={"key": "abruf_intervall_min", "value": 30}).status_code == 200
