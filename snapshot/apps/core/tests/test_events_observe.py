"""Tests K4 (Core-Seite): Event-Push App→Dizzi + L4-Beobachtung der Vertrags-Apps."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import panels
from app.ai import observe
from app.main import app


@pytest.fixture(autouse=True)
def _registry_restore():
    snapshot = dict(panels._registry)
    apps_snapshot = dict(panels._contract_apps)
    observe._seen_actions.clear()
    yield
    panels._registry.clear()
    panels._registry.update(snapshot)
    panels._contract_apps.clear()
    panels._contract_apps.update(apps_snapshot)
    observe._seen_actions.clear()


def test_event_push_landet_in_glocke_und_l4():
    with TestClient(app) as c:
        r = c.post("/api/events", json={
            "app": "news", "severity": "warn",
            "title": "Quelle nicht erreichbar", "detail": {"quelle": "xyz"}})
        assert r.status_code == 200
        assert c.post("/api/events", json={
            "app": "news", "severity": "panik", "title": "x"}).status_code == 400

    obs = observe.recent("dizzi", source="news")
    assert obs and obs[0]["daten"]["event"] == "Quelle nicht erreichbar"


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def test_observe_contract_apps_und_vorschlags_glocke(monkeypatch):
    def fake_get(url, timeout):
        if url.endswith("/api/summary"):
            return _Resp({"app": "k4app", "status": "ok",
                          "kpis": [{"id": "n", "label": "N", "value": 3}]})
        return _Resp({"katalog": [], "liste": [
            {"id": "act-1", "name": "post_veroeffentlichen",
             "level": "verifiziert", "params": {"text": "hi"}}]})
    monkeypatch.setattr(httpx, "get", fake_get)

    # Isolieren: real angebundene Apps (z. B. news via .env) ausblenden —
    # die Fixture restauriert den Zustand nach dem Test.
    panels._contract_apps.clear()
    panels.register_contract_app("management", "http://127.0.0.1:8213")
    assert observe.observe_contract_apps("dizzi") == 1

    obs = observe.recent("dizzi", source="management")
    assert obs and obs[0]["daten"]["kpis"][0]["value"] == 3

    from app import db
    rows = db.get_conn().execute(
        "SELECT title FROM notices WHERE source='management'").fetchall()
    assert len(rows) == 1 and "post_veroeffentlichen" in rows[0]["title"]

    # Zweiter Lauf: derselbe Vorschlag klingelt NICHT erneut (Dedupe)
    observe.observe_contract_apps("dizzi")
    rows = db.get_conn().execute(
        "SELECT title FROM notices WHERE source='management'").fetchall()
    assert len(rows) == 1
