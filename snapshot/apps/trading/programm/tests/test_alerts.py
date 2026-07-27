"""Tests: Proaktives Monitoring/Alerting (P5) — Aggregation + Priorisierung der Signale."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.app import alerts


def _patch(monkeypatch, tmp_path, *, gov=None, exec_=None, bots=None, running=None,
           market=None, regime=None):
    monkeypatch.setattr(alerts, "STATE_FILE", tmp_path / "alerts.json")
    monkeypatch.setattr(alerts.governor, "evaluate", lambda use_cache=False: (gov if gov is not None else
                        {"breach_reasons": [], "warn_reasons": [], "anomalies": []}))
    monkeypatch.setattr(alerts.execution, "analyze",
                        lambda use_cache=False: (exec_ if exec_ is not None else {"flags": []}))
    bots = bots if bots is not None else []
    monkeypatch.setattr(alerts.registry, "list_bots", lambda: list(bots))
    run_map = running or {getattr(b, "id", None): True for b in bots}
    monkeypatch.setattr(alerts.runner, "status", lambda bid: {"running": run_map.get(bid, True)})
    monkeypatch.setattr(alerts.stats, "get_market_snapshots", lambda limit=1: list(market or []))
    monkeypatch.setattr(alerts.tracker, "read_regime_bridge", lambda: regime)


def _fresh_market():
    return [{"ts": datetime.now(timezone.utc).isoformat()}]


def test_governor_breach_is_critical(tmp_path, monkeypatch):
    gov = {"breach_reasons": ["Portfolio-Drawdown 20% ≥ Limit 18%"], "warn_reasons": [], "anomalies": []}
    _patch(monkeypatch, tmp_path, gov=gov, market=_fresh_market(), regime={"regime": "range"})
    out = alerts.collect()
    assert out["status"] == "critical" and out["counts"]["critical"] == 1
    assert out["alerts"][0]["category"] == "portfolio"


def test_warn_and_anomaly_and_execution(tmp_path, monkeypatch):
    gov = {"breach_reasons": [], "warn_reasons": ["Konzentration: Cluster zu groß"],
           "anomalies": [{"name": "F07", "profit_pct": -25.0, "robust_z": -18.0}]}
    _patch(monkeypatch, tmp_path, gov=gov, exec_={"flags": ["S03: hohe Slippage (Ø 50 bps)"]},
           market=_fresh_market(), regime={"regime": "range"})
    out = alerts.collect()
    cats = {a["category"] for a in out["alerts"]}
    assert {"portfolio", "anomalie", "ausführung"} <= cats
    assert out["status"] == "warn" and out["counts"]["warn"] == 3


def test_stale_market_feed_warns(tmp_path, monkeypatch):
    old = [{"ts": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}]
    _patch(monkeypatch, tmp_path, market=old, regime={"regime": "range"})
    out = alerts.collect()
    assert any(a["category"] == "datenfeed" and "alt" in a["message"] for a in out["alerts"])


def test_missing_regime_bridge_is_info(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, market=_fresh_market(), regime=None)
    out = alerts.collect()
    assert any(a["category"] == "datenfeed" and a["level"] == "info" for a in out["alerts"])


def test_stopped_bots_warn(tmp_path, monkeypatch):
    bots = [SimpleNamespace(id="b1", name="B1"), SimpleNamespace(id="b2", name="B2")]
    _patch(monkeypatch, tmp_path, bots=bots, running={"b1": True, "b2": False},
           market=_fresh_market(), regime={"regime": "range"})
    out = alerts.collect()
    assert any(a["category"] == "betrieb" and "gestoppt" in a["message"] for a in out["alerts"])


def test_critical_sorted_before_warn(tmp_path, monkeypatch):
    gov = {"breach_reasons": ["DD"], "warn_reasons": ["W"], "anomalies": []}
    _patch(monkeypatch, tmp_path, gov=gov, market=_fresh_market(), regime={"regime": "range"})
    out = alerts.collect()
    assert out["alerts"][0]["level"] == "critical"


def test_disabled_returns_empty(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, market=_fresh_market(), regime={"regime": "range"})
    alerts.set_config({"enabled": False})
    out = alerts.collect()
    assert out["enabled"] is False and out["alerts"] == [] and out["status"] == "ok"
