"""Tests F-DEF2 (Core-Seite): Dizzi als SOC-Dach — Verbund-Immunität
Ende-zu-Ende über zwei ECHTE Vertrags-Apps (appkit create_app)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db, defense_hub, panels
from app.main import app as core_app  # noqa: F401 — setzt sys.path für appkit


@pytest.fixture(autouse=True)
def _restore():
    registry_snapshot = dict(panels._registry)
    apps_snapshot = dict(panels._contract_apps)
    defense_hub._gemeldet.clear()
    yield
    panels._registry.clear()
    panels._registry.update(registry_snapshot)
    panels._contract_apps.clear()
    panels._contract_apps.update(apps_snapshot)
    defense_hub._gemeldet.clear()


def _vertrags_app(tmp_path, app_id: str, port: int) -> TestClient:
    from appkit.app import create_app
    from appkit.db import Database
    from appkit.manifest import AppManifest
    from appkit.summary import Kpi
    manifest = AppManifest(id=app_id, name=app_id, brand=f"Dizz {app_id}",
                           version="0.1.0", port=port)
    db_ = Database(tmp_path / f"{app_id}.sqlite")
    # Triage stumm: Test-Sperren sollen keine echten Ollama-Aufrufe feuern.
    db_.setting_put("dizzi", "defense_triage_aktiv", False)
    # F4: Hub-Tests simulieren den lokalen Reverse-Proxy (1 vertrauter Hop),
    # sonst würde XFF mit Default 0 ignoriert (fail-closed auf den TCP-Peer).
    db_.setting_put("dizzi", "defense_trusted_proxy_hops", 1)
    return TestClient(create_app(
        manifest, db_, summary_fn=lambda: [Kpi(id="n", label="N", value=1)]))


def test_angriff_auf_eine_app_immunisiert_alle(tmp_path):
    a = _vertrags_app(tmp_path, "defa", 8291)
    b = _vertrags_app(tmp_path, "defb", 8292)
    clients = {"http://127.0.0.1:8291": a, "http://127.0.0.1:8292": b}

    def http_get(url):
        base, _, pfad = url.partition("/api/")
        return clients[base].get(f"/api/{pfad}")

    def http_post(url, json):
        base, _, pfad = url.partition("/api/")
        return clients[base].post(f"/api/{pfad}", json=json)

    panels._contract_apps.clear()
    panels.register_contract_app("defa", "http://127.0.0.1:8291")
    panels.register_contract_app("defb", "http://127.0.0.1:8292")

    # Angriff NUR auf App A (Köder-Pfad, externer Client):
    angreifer = {"X-Forwarded-For": "198.51.100.77"}
    a.get("/wp-login.php", headers=angreifer)
    assert a.get("/api/summary", headers=angreifer).status_code == 403
    assert b.get("/api/summary", headers=angreifer).status_code == 200  # B noch offen

    stats = defense_hub.tick("dizzi", http_get=http_get, http_post=http_post)
    assert stats == {"apps": 2, "sperren": 1, "verteilt": 2}

    # Föderations-Immunität: B blockt den Angreifer jetzt auch.
    assert b.get("/api/summary", headers=angreifer).status_code == 403
    grund = b.get("/api/defense").json()["massnahmen"][0]["grund"]
    assert grund.startswith("verbund:defa:")

    # Glocke: genau EINE Meldung; zweiter Takt dedupet UND erzeugt kein Echo
    rows = db.get_conn().execute(
        "SELECT title FROM notices WHERE source='defa'").fetchall()
    assert len(rows) == 1 and "198.51.100.77" in rows[0]["title"]
    stats2 = defense_hub.tick("dizzi", http_get=http_get, http_post=http_post)
    assert stats2["sperren"] == 1  # B's verbund:-Sperre wird NICHT eingesammelt
    rows = db.get_conn().execute(
        "SELECT title FROM notices WHERE source IN ('defa','defb')").fetchall()
    assert len(rows) == 1


def test_offline_apps_stoeren_den_verbund_nicht(tmp_path):
    a = _vertrags_app(tmp_path, "defa", 8291)

    def http_get(url):
        if "8291" in url:
            return a.get("/api/defense")
        raise ConnectionError("offline")

    def http_post(url, json):
        if "8291" in url:
            return a.post("/api/defense/verbund", json=json)
        raise ConnectionError("offline")

    panels._contract_apps.clear()
    panels.register_contract_app("defa", "http://127.0.0.1:8291")
    panels.register_contract_app("tot", "http://127.0.0.1:8299")
    a.get("/.env", headers={"X-Forwarded-For": "198.51.100.78"})
    stats = defense_hub.tick("dizzi", http_get=http_get, http_post=http_post)
    assert stats["apps"] == 1 and stats["sperren"] == 1 and stats["verteilt"] == 1
