"""Tests: generischer Konsum vertragskonformer Apps (K3) in der Panel-Registry."""

from __future__ import annotations

import httpx
import pytest

from app import panels


@pytest.fixture(autouse=True)
def _registry_restore():
    """Registry-Snapshot je Test — register_contract_app übersteuert Einträge
    UND trägt in _contract_apps ein (L4-Beobachter); beides restaurieren."""
    snapshot = dict(panels._registry)
    apps_snapshot = dict(panels._contract_apps)
    panels._contract_cache.clear()
    yield
    panels._registry.clear()
    panels._registry.update(snapshot)
    panels._contract_apps.clear()
    panels._contract_apps.update(apps_snapshot)
    panels._contract_cache.clear()


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_contract_app_uebersteuert_platzhalter_und_mappt(monkeypatch):
    payload = {
        "ok": True, "app": "finanzen", "name": "Finanzmanagement",
        "contract": "1.0", "ts": "2026-06-11T00:00:00+00:00", "status": "ok",
        "kpis": [{"id": "saldo", "label": "Saldo", "value": 1234.5, "unit": "€"}],
    }
    monkeypatch.setattr(httpx, "get", lambda url, timeout: _Resp(payload))

    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")

    m = {p.id: p for p in panels.manifests()}["finanzen"]
    assert m.status == "aktiv"
    assert m.name == "Finanzmanagement"          # Optik vom Platzhalter übernommen
    assert m.icon == "coins"

    stats = panels.stats_for("finanzen")
    assert stats["status"] == "ok" and stats["online"] is True
    assert stats["kpis"][0]["id"] == "saldo"
    assert stats["url"] == "http://127.0.0.1:8210"


def test_contract_app_offline_bleibt_ruhig(monkeypatch):
    def _boom(url, timeout):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "get", _boom)

    panels.register_contract_app("news", "http://127.0.0.1:8216")
    stats = panels.stats_for("news")
    assert stats["online"] is False              # kein 500, kein Crash
    assert stats["url"] == "http://127.0.0.1:8216"


def test_env_seed_parst_liste(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout: _Resp(
        {"app": "x", "status": "ok", "kpis": []}))
    monkeypatch.setenv("DIZZI_CONTRACT_APPS",
                       "projekte=http://127.0.0.1:8212, archiv=http://127.0.0.1:8215/")
    panels._seed_contract_apps()
    ids = {p.id: p.status for p in panels.manifests()}
    assert ids["projekte"] == "aktiv" and ids["archiv"] == "aktiv"
    assert panels.stats_for("archiv")["url"] == "http://127.0.0.1:8215"  # Slash getrimmt
