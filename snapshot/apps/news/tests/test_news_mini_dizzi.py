"""Tests Mini-Dizzi-Brücke (Vertrag 1.5) — die Server-Hälfte der News-Sprechblase.

Die App registriert ihre echte KI über ``set_app_ki`` (main.build_app); der
Endpoint ``POST /api/ki/frage`` muss diese Antwort durchreichen. Ohne Ollama
fällt die News-KI auf einen ehrlichen Hinweis zurück — nie eine Halluzination.
Die Frontend-Sprechblase (static/index.html → dizziFragen) spricht genau diesen
Endpoint an; dieser Test verankert den Vertrag.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsapp import main as nm


def _client(tmp_path, monkeypatch, feeds=None):
    if feeds is not None:
        monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    return TestClient(nm.build_app(data_dir=tmp_path, start_timer=False))


def test_ki_frage_leerer_bestand_ehrlich(tmp_path, monkeypatch):
    """Ohne Artikel antwortet die News-KI ehrlich (kein Erfinden) — Quelle app_ki."""
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        r = c.post("/api/ki/frage", json={"frage": "Was ist heute wichtig?"})
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("antwort"), str) and body["antwort"]
        # Die App-KI ist registriert ⇒ die Antwort kommt aus der News-KI,
        # nicht aus dem generischen Fallback.
        assert body.get("quelle") == "app_ki"
        # Ehrlicher Hinweis bei leerem Bestand (keine erfundenen Nachrichten).
        assert "Artikel" in body["antwort"]


def test_ki_frage_auditiert(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        c.post("/api/ki/frage", json={"frage": "Test"})
        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "mini_dizzi_frage" in actions


def test_ki_status_erreichbar(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        s = c.get("/api/ki/status").json()
        assert s["app"] == "news" and s["app_ki_registriert"] is True
