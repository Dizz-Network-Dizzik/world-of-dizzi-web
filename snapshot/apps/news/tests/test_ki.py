"""KI-Ebene Stufe 2: Briefing + Fragen — Schema-Prüfung, Fallbacks, Endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from newsapp.ki import briefing, frage
from newsapp.main import build_app


class _Antwort:
    def __init__(self, status_code: int, inhalt: str):
        self.status_code = status_code
        self._inhalt = inhalt

    def json(self):
        return {"message": {"content": self._inhalt}}


def _post_mit(inhalt: str, status: int = 200):
    return lambda url, daten: _Antwort(status, inhalt)


_ARTIKEL = [{"titel": "Zinsentscheid vertagt", "quelle": "tagesschau",
             "sektor": "allgemein", "zusammenfassung": "Die EZB wartet ab."}]


def test_briefing_gueltig_und_leer():
    out = briefing(_ARTIKEL, http_post=_post_mit(json.dumps({
        "ueberblick": "Ruhige Lage, EZB wartet.",
        "wichtig": [{"titel": "Zinsentscheid vertagt", "warum": "Märkte"}]})))
    assert out["ueberblick"] == "Ruhige Lage, EZB wartet."
    assert out["wichtig"][0]["titel"] == "Zinsentscheid vertagt"
    assert out["artikel_betrachtet"] == 1
    # leerer Bestand braucht kein LLM
    assert briefing([], http_post=None)["wichtig"] == []


def test_briefing_ehrlich_bei_ausfall():
    assert "error" in briefing(_ARTIKEL, http_post=_post_mit("kein json"))
    assert "error" in briefing(_ARTIKEL, http_post=_post_mit("{}", status=500))

    def kaputt(url, daten):
        raise ConnectionError("down")
    assert "error" in briefing(_ARTIKEL, http_post=kaputt)


def test_frage_gueltig_und_ohne_beleg():
    out = frage(_ARTIKEL, "Was macht die EZB?", http_post=_post_mit(json.dumps({
        "antwort": "Sie vertagt den Zinsentscheid.",
        "belege": ["Zinsentscheid vertagt"]})))
    assert out["antwort"].startswith("Sie vertagt")
    assert out["belege"] == ["Zinsentscheid vertagt"]
    assert frage([], "x", http_post=None)["belege"] == []


def test_endpoints(tmp_path, monkeypatch):
    # Feeds nicht ins Netz: _lade_feed liefert einen festen Artikel
    import newsapp.main as m
    monkeypatch.setattr(m, "_lade_feed", lambda url: [{
        "titel": "Test-Artikel", "link": f"https://x.test/{hash(url)}",
        "zusammenfassung": "Inhalt", "published": None}])
    app = build_app(data_dir=tmp_path, start_timer=False,
                    http_post=_post_mit(json.dumps({
                        "ueberblick": "Alles ruhig.", "wichtig": [],
                        "antwort": "42", "belege": []})))
    with TestClient(app) as client:
        client.post("/api/abrufen")
        b = client.post("/api/briefing").json()
        assert b["ueberblick"] == "Alles ruhig."
        f = client.post("/api/fragen", json={"frage": "Wie viel?"}).json()
        assert f["antwort"] == "42"
        audit = [e["action"] for e in client.get("/api/audit").json()]
        assert "briefing_erstellt" in audit and "frage_beantwortet" in audit
        # UI wird ausgeliefert
        r = client.get("/")
        assert r.status_code == 200 and "Dizz News" in r.text

def test_pydantic_single_source_validierung():
    """P2.1: Pydantic-Modell = Schema + Validierung. Fehlendes Pflichtfeld -> ehrlicher
    Fehler; Extra-Felder werden ignoriert (extra='ignore'-Default)."""
    assert "error" in briefing(_ARTIKEL, http_post=_post_mit(json.dumps({"wichtig": []})))
    out = briefing(_ARTIKEL, http_post=_post_mit(json.dumps({
        "ueberblick": "ok", "wichtig": [], "extra_feld": 99})))
    assert out["ueberblick"] == "ok" and out["wichtig"] == []
