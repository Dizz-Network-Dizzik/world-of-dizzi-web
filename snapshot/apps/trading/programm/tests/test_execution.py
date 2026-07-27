"""Tests: Execution-/Slippage-Tracking (P4) — Slippage-Mathematik + Aggregation/Flags."""
import sqlite3
from types import SimpleNamespace

from backend.app import execution, stats


# ---------------------------------------------------------------- stats.execution_costs (DB-Mathematik)
def _make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE trades (pair TEXT, is_short INT, is_open INT, close_date TEXT,
        open_rate REAL, open_rate_requested REAL, close_rate REAL, close_rate_requested REAL,
        open_trade_value REAL, fee_open_cost REAL, fee_close_cost REAL)""")
    con.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_execution_costs_direction_aware_slippage(tmp_path, monkeypatch):
    base = tmp_path / "engine" / "user_data"
    base.mkdir(parents=True)
    db = base / "tradesv3_b1.sqlite"
    _make_db(db, [
        # Long: Kauf 0.5 teurer (adverse), Verkauf 0.5 billiger (adverse). +Gebühr 0.08/200 = 4 bps.
        ("BTC/USDT", 0, 0, "2026-06-01 10:00:00", 100.5, 100.0, 109.5, 110.0, 200.0, 0.02, 0.06),
        # Short: Verkauf 0.5 billiger (adverse), Rückkauf 0.5 teurer (adverse).
        ("ETH/USDT", 1, 0, "2026-06-02 10:00:00", 99.5, 100.0, 90.5, 90.0, 200.0, 0.02, 0.06),
        # Dry-Run: Fill == angefordert → Slippage 0.
        ("SOL/USDT", 0, 0, "2026-06-03 10:00:00", 50.0, 50.0, 55.0, 55.0, 200.0, 0.02, 0.06),
    ])
    monkeypatch.setattr(stats, "PROJECT_ROOT", tmp_path)
    out = stats.execution_costs("b1")
    assert len(out) == 3
    # Long: (0.5/100 + 0.5/110)*1e4 ≈ 95.45 bps.
    assert abs(out[0]["slippage_bps"] - 95.45) < 0.1
    # Short: (0.5/100 + 0.5/90)*1e4 ≈ 105.56 bps.
    assert abs(out[1]["slippage_bps"] - 105.56) < 0.1
    # Dry-Run: 0 Slippage, aber reale Gebühr 4 bps.
    assert out[2]["slippage_bps"] == 0.0 and out[2]["fee_bps"] == 4.0
    assert out[2]["cost_bps"] == 4.0


def test_execution_costs_missing_db_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "PROJECT_ROOT", tmp_path)
    assert stats.execution_costs("nope") == []


# ---------------------------------------------------------------- execution.analyze (Aggregation)
def _bot(bid, tag=1):
    return SimpleNamespace(id=bid, tag=tag, name=bid.upper(), strategy="S")


def _patch(monkeypatch, tmp_path, bots, costs_map):
    monkeypatch.setattr(execution, "STATE_FILE", tmp_path / "execution.json")
    monkeypatch.setattr(execution.registry, "list_bots", lambda: list(bots))
    monkeypatch.setattr(execution.stats, "execution_costs",
                        lambda bid, limit=500: list(costs_map.get(bid, [])))


def _trade(slip, fee=4.0):
    return {"slippage_bps": slip, "fee_bps": fee, "cost_bps": (slip + fee)}


def test_analyze_flags_rising_slippage(tmp_path, monkeypatch):
    # 10 ruhige Trades (Slippage 1) + 20 jüngste mit hoher Slippage (30) → Trend rauf → Flag.
    trades = [_trade(1.0) for _ in range(15)] + [_trade(30.0) for _ in range(20)]
    _patch(monkeypatch, tmp_path, [_bot("b1")], {"b1": trades})
    a = execution.analyze()
    assert a["severity"] == "warn"
    assert any("steigende Slippage" in f for f in a["flags"])
    assert a["bots"][0]["trend_bps"] is not None and a["bots"][0]["trend_bps"] > 0


def test_analyze_ok_when_clean(tmp_path, monkeypatch):
    trades = [_trade(0.0) for _ in range(12)]
    _patch(monkeypatch, tmp_path, [_bot("b1")], {"b1": trades})
    a = execution.analyze()
    assert a["severity"] == "ok" and not a["flags"]
    assert a["avg_slippage_bps"] == 0.0 and a["avg_fee_bps"] == 4.0


def test_analyze_weighted_fleet_average(tmp_path, monkeypatch):
    # b1: 1 Trade Slippage 10; b2: 3 Trades Slippage 2 → gewichtet (10·1+2·3)/4 = 4.0.
    _patch(monkeypatch, tmp_path, [_bot("b1"), _bot("b2")],
           {"b1": [_trade(10.0)], "b2": [_trade(2.0), _trade(2.0), _trade(2.0)]})
    a = execution.analyze()
    assert a["avg_slippage_bps"] == 4.0 and a["total_trades"] == 4 and a["n_bots_with_trades"] == 2
