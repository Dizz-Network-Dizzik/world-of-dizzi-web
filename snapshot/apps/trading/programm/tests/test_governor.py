"""Tests: Portfolio-Risk-Governor (P1) — aggregierter Drawdown, Tagesverlust, Anomalien + Eingriff.

Der Governor fasst nur read-only Kennzahlen zusammen und stoppt höchstens Demo-Bots (nie löschen).
Diese Tests isolieren ihn vollständig (STATE_FILE in tmp; registry/stats/runner gemockt)."""
from types import SimpleNamespace

from backend.app import governor, registry


def _bot(bid, *, dry=True, wallet=1000.0, name=None):
    return SimpleNamespace(id=bid, tag=0, name=name or bid.upper(), strategy="S",
                           dry_run=dry, dry_run_wallet=wallet)


def _patch(monkeypatch, tmp_path, bots, *, pnl, snapshots=None, running=None):
    """pnl: {bot_id: (profit_pct, profit_abs, closed)}; snapshots: {bot_id: [{day,equity},...]}."""
    monkeypatch.setattr(governor, "STATE_FILE", tmp_path / "governor.json")
    monkeypatch.setattr(governor.registry, "list_bots", lambda: list(bots))
    snapshots = snapshots or {}
    monkeypatch.setattr(governor.stats, "get_snapshots",
                        lambda bid, limit=365: list(snapshots.get(bid, [])))

    def _pnl(bid, wallet=0.0, since_days=None):
        p, a, c = pnl.get(bid, (None, 0.0, 0))
        return {"open": 0, "closed": c, "wins": 0, "profit_abs": a, "profit_pct": p}
    monkeypatch.setattr(governor.stats, "bot_pnl", _pnl)
    run_map = running or {b.id: True for b in bots}
    monkeypatch.setattr(governor.runner, "status", lambda bid: {"running": run_map.get(bid, False)})


# ------------------------------------------------------------------ Kennzahlen
def test_portfolio_drawdown_aggregates_by_day(tmp_path, monkeypatch):
    bots = [_bot("b1"), _bot("b2")]
    snaps = {
        "b1": [{"day": "2026-06-01", "equity": 1000.0}, {"day": "2026-06-02", "equity": 1200.0},
               {"day": "2026-06-03", "equity": 1000.0}],
        "b2": [{"day": "2026-06-01", "equity": 1000.0}, {"day": "2026-06-02", "equity": 1000.0},
               {"day": "2026-06-03", "equity": 900.0}],
    }
    _patch(monkeypatch, tmp_path, bots, pnl={}, snapshots=snaps)
    dd = governor.portfolio_drawdown()
    # Aggregat: 2000 → 2200 (Hoch) → 1900. Aktueller DD = (2200-1900)/2200*100 ≈ 13.64%.
    assert dd["peak_equity"] == 2200.0
    assert dd["current_equity"] == 1900.0
    assert abs(dd["drawdown_pct"] - 13.64) < 0.05


def test_portfolio_drawdown_forward_fills_missing_day(tmp_path, monkeypatch):
    # b2 fehlt der mittlere Tag (transienter Snapshot-Fehler). Ohne Forward-Fill bräche die
    # Tagessumme an Tag 2 ein → falscher Drawdown. Mit Forward-Fill bleibt b2 bei 1000 → kein DD.
    bots = [_bot("b1"), _bot("b2")]
    snaps = {
        "b1": [{"day": "2026-06-01", "equity": 1000.0}, {"day": "2026-06-02", "equity": 1000.0},
               {"day": "2026-06-03", "equity": 1000.0}],
        "b2": [{"day": "2026-06-01", "equity": 1000.0}, {"day": "2026-06-03", "equity": 1000.0}],
    }
    _patch(monkeypatch, tmp_path, bots, pnl={}, snapshots=snaps)
    dd = governor.portfolio_drawdown()
    assert dd["drawdown_pct"] == 0.0 and dd["peak_equity"] == 2000.0


def test_evaluate_ok_when_healthy(tmp_path, monkeypatch):
    bots = [_bot("b1"), _bot("b2")]
    _patch(monkeypatch, tmp_path, bots, pnl={"b1": (0.5, 5.0, 3), "b2": (0.3, 3.0, 2)})
    rep = governor.evaluate()
    assert rep["severity"] == "ok" and not rep["breach_reasons"]


def test_evaluate_breach_on_daily_loss(tmp_path, monkeypatch):
    bots = [_bot("b1"), _bot("b2")]
    # Gesamtverlust heute -600 EUR / 2000 EUR Wallet = 30% ≥ 8% → breach.
    _patch(monkeypatch, tmp_path, bots, pnl={"b1": (-30.0, -300.0, 5), "b2": (-30.0, -300.0, 5)})
    rep = governor.evaluate()
    assert rep["severity"] == "breach"
    assert any("Tagesverlust" in r for r in rep["breach_reasons"])
    assert rep["daily_loss_pct"] == 30.0


def test_anomaly_flags_extreme_outlier(tmp_path, monkeypatch):
    bots = [_bot(b) for b in ("b1", "b2", "b3", "b4", "b5", "b6")]
    pnl = {"b1": (0.5, 5.0, 3), "b2": (1.0, 10.0, 3), "b3": (-0.5, -5.0, 3),
           "b4": (0.8, 8.0, 3), "b5": (-1.0, -10.0, 3), "b6": (-25.0, -50.0, 3)}
    _patch(monkeypatch, tmp_path, bots, pnl=pnl)
    rep = governor.evaluate()
    anomaly_ids = {a["bot_id"] for a in rep["anomalies"]}
    assert anomaly_ids == {"b6"}


# ------------------------------------------------------------------ Eingriff
def test_derisk_stops_worst_n_and_protects_master_and_live(tmp_path, monkeypatch):
    master = _bot(registry.MASTER_BOT_ID, name="MasterMeta")
    live = _bot("live1", dry=False)
    bots = [master, live, _bot("b1"), _bot("b2"), _bot("b3"), _bot("b4")]
    # breach via Tagesverlust; b4 ist der schlechteste, b1 der beste der Demo-Bots.
    pnl = {registry.MASTER_BOT_ID: (-40.0, -400.0, 5), "live1": (-40.0, -400.0, 5),
           "b1": (1.0, 10.0, 5), "b2": (-2.0, -20.0, 5), "b3": (-5.0, -50.0, 5), "b4": (-9.0, -90.0, 5)}
    _patch(monkeypatch, tmp_path, bots, pnl=pnl)
    governor.set_config({"action": "derisk", "derisk_count": 2, "protect_master": True})
    stopped: list[str] = []
    monkeypatch.setattr(governor.runner, "stop", lambda bid: stopped.append(bid))
    out = governor.run_once(force=True)
    assert out["acted"] and out["severity"] == "breach"
    # Nur die 2 schlechtesten DEMO-Bots; Master + Echtgeld bleiben unangetastet.
    assert set(stopped) == {"b3", "b4"}
    assert registry.MASTER_BOT_ID not in stopped and "live1" not in stopped


def test_pause_stops_all_demo_except_master(tmp_path, monkeypatch):
    master = _bot(registry.MASTER_BOT_ID, name="MasterMeta")
    bots = [master, _bot("b1"), _bot("b2"), _bot("b3")]
    pnl = {registry.MASTER_BOT_ID: (-40.0, -400.0, 5), "b1": (-40.0, -400.0, 5),
           "b2": (-40.0, -400.0, 5), "b3": (-40.0, -400.0, 5)}
    _patch(monkeypatch, tmp_path, bots, pnl=pnl)
    governor.set_config({"action": "pause", "protect_master": True})
    stopped: list[str] = []
    monkeypatch.setattr(governor.runner, "stop", lambda bid: stopped.append(bid))
    out = governor.run_once(force=True)
    assert out["acted"] and set(stopped) == {"b1", "b2", "b3"}


def test_alert_action_does_not_stop(tmp_path, monkeypatch):
    bots = [_bot("b1"), _bot("b2")]
    _patch(monkeypatch, tmp_path, bots, pnl={"b1": (-30.0, -300.0, 5), "b2": (-30.0, -300.0, 5)})
    governor.set_config({"action": "alert"})
    stopped: list[str] = []
    monkeypatch.setattr(governor.runner, "stop", lambda bid: stopped.append(bid))
    out = governor.run_once(force=True)
    assert out["severity"] == "breach" and not out["acted"] and stopped == []
    assert "alert" in (out["skipped"] or "")


def test_debounce_blocks_second_action(tmp_path, monkeypatch):
    bots = [_bot("b1"), _bot("b2"), _bot("b3")]
    pnl = {b.id: (-30.0, -300.0, 5) for b in bots}
    _patch(monkeypatch, tmp_path, bots, pnl=pnl)
    governor.set_config({"action": "derisk", "derisk_count": 1})
    stopped: list[str] = []
    monkeypatch.setattr(governor.runner, "stop", lambda bid: stopped.append(bid))
    first = governor.run_once()          # nicht force → setzt last_action_ts
    assert first["acted"]
    second = governor.run_once()         # sofort danach → debounce
    assert not second["acted"] and second["skipped"] == "debounce"
