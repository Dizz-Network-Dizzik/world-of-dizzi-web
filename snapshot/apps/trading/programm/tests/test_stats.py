"""Kernlogik-Tests: stats-Migration + profit_factor-Persistenz + Read-Only-DB + Once-Schema (temporäre DB)."""
import sqlite3

import pytest

from backend.app import stats


def test_profit_factor_roundtrip_and_idempotent_migration(tmp_path):
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "t.sqlite"
    stats.save_strategy_validation("X", True, 3, {
        "profit_total_pct": -2.0, "max_drawdown_pct": 4.0,
        "total_trades": 50, "winrate_pct": 55.0, "profit_factor": 1.4,
    })
    row = stats.get_strategy_validation("X")
    assert row is not None
    assert row["profit_factor"] == 1.4
    assert row["windows"] == 3
    assert bool(row["validated"]) is True
    # zweiter Zugriff darf nicht crashen (ALTER bereits angewandt -> OperationalError gefangen)
    assert stats.get_strategy_validation("X")["profit_factor"] == 1.4


def test_missing_strategy_returns_none(tmp_path):
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "t2.sqlite"
    assert stats.get_strategy_validation("does-not-exist") is None


def test_ro_connect_reads_but_blocks_writes(tmp_path):
    # #2: Trade-DBs werden read-only geöffnet → Lesen ok, Schreiben/Anlegen schlägt fehl (kein Write-Lock).
    db = tmp_path / "tradesv3_x.sqlite"
    c = sqlite3.connect(db); c.execute("CREATE TABLE t(x)"); c.execute("INSERT INTO t VALUES(1)")
    c.commit(); c.close()
    ro = stats._ro_connect(db)
    try:
        assert ro.execute("SELECT x FROM t").fetchone()[0] == 1     # lesen geht
        with pytest.raises(sqlite3.OperationalError):                # schreiben verboten
            ro.execute("INSERT INTO t VALUES(2)")
    finally:
        ro.close()


def test_schema_initialized_once_per_path(tmp_path):
    # #1: Schema/Migration laufen genau einmal pro DB-Pfad (Guard), wiederholter Zugriff bleibt fehlerfrei.
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "once.sqlite"
    stats._inited.discard(str(stats.DB_FILE))
    stats.save_strategy_validation("Y", True, 2, {"profit_factor": 1.1, "total_trades": 10})
    assert str(stats.DB_FILE) in stats._inited                      # nach erstem Zugriff initialisiert
    assert stats.get_strategy_validation("Y")["profit_factor"] == 1.1   # zweiter Zugriff: Guard greift, kein Fehler
