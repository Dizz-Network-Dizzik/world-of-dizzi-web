"""Tagesnotiz-Landing (P2.2): Notiz des Tages im Ordner „Tagebuch", idempotent."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def test_tagesnotiz_idempotent_und_ordner(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/tagesnotiz", json={"datum": "2026-06-15"}).json()
        assert a["neu"] is True and a["titel"] == "2026-06-15"
        # zweiter Aufruf desselben Tages ⇒ dieselbe Notiz (idempotent)
        b = c.post("/api/tagesnotiz", json={"datum": "2026-06-15"}).json()
        assert b["neu"] is False and b["id"] == a["id"]
        # liegt im Ordner „Tagebuch"
        assert "Tagebuch" in {o["name"] for o in c.get("/api/ordner").json()}
        det = c.get("/api/notizen/" + a["id"]).json()
        assert det["ordner_id"] == a["ordner_id"] and det["titel"] == "2026-06-15"


def test_tagesnotiz_default_heute(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/tagesnotiz", json={}).json()
        assert r["titel"] == date.today().isoformat() and r["neu"] is True
