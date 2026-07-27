"""Tests: Daten-Lifecycle (Verdichtung/Pruning/Ledger) — temporäre DB, idempotent & dry-run."""
from datetime import datetime, timedelta, timezone

from backend.app import maintenance, stats


def _setup(tmp_path):
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "t.sqlite"


def _ins_snap(c, bot, day, profit):
    c.execute("INSERT INTO snapshots(bot_id,day,ts,strategy,equity,profit_pct,trades_closed,"
              "winrate_pct,max_drawdown_pct) VALUES(?,?,?,?,?,?,?,?,?)",
              (bot, day.strftime("%Y-%m-%d"), day.isoformat(), "S", 1000, profit, 5, 50.0, 3.0))


def test_compact_snapshots_rolls_up_and_deletes_raw(tmp_path):
    _setup(tmp_path)
    # Auf Monatsmitte ankern, damit `old` und `old+1 Tag` IMMER im selben Kalendermonat liegen
    # (sonst flaky, wenn „heute − 200 Tage" auf den Monatsletzten fällt → +1 Tag = nächster Monat).
    old = (datetime.now(timezone.utc) - timedelta(days=200)).replace(day=15)
    now = datetime.now(timezone.utc)
    with stats._conn() as c:
        _ins_snap(c, "bot1", old, -1.0)
        _ins_snap(c, "bot1", old + timedelta(days=1), -3.0)   # gleicher Monat
        _ins_snap(c, "bot1", now, 0.5)                        # frisch -> bleibt
    # Vorschau ändert nichts
    pre = maintenance.compact_snapshots(retain_days=90, dry_run=True)
    assert pre["raw_rows"] == 2 and pre["monthly_rollups"] == 1
    with stats._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 3
    # Anwenden: 2 alte -> 1 Monats-Rollup, Roh weg, frische bleibt
    maintenance.compact_snapshots(retain_days=90, dry_run=False)
    with stats._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM snapshots_monthly").fetchone()[0] == 1
        avg = c.execute("SELECT avg_profit_pct FROM snapshots_monthly").fetchone()[0]
        assert abs(avg - (-2.0)) < 1e-6   # Mittel aus -1 und -3


def test_compact_snapshots_only_complete_months(tmp_path):
    """Regression: der Cutoff wird auf den Monatsanfang gesnappt ⇒ ein GRENZ-Monat (der den rohen
    Cutoff-Tag enthält) wird NICHT teil-verdichtet, sondern komplett roh behalten, bis er ganz alt ist.
    Auf dem alten Tages-Cutoff wäre der Grenz-Monat partiell rollupt + die früheren Tage durch den
    ON-CONFLICT-Replace beim nächsten Lauf verloren gegangen."""
    _setup(tmp_path)
    now = datetime.now(timezone.utc)
    m = (now - timedelta(days=150)).replace(day=15)        # Grenz-Monat M, Tag 15
    prev = m - timedelta(days=40)                          # ein Tag im vollständig-älteren Monat M-1
    with stats._conn() as c:
        _ins_snap(c, "b", m - timedelta(days=10), -1.0)    # M, Tag ~5
        _ins_snap(c, "b", m, -2.0)                         # M, Tag 15
        _ins_snap(c, "b", m + timedelta(days=10), -3.0)    # M, Tag ~25
        _ins_snap(c, "b", prev, -5.0)                      # M-1 (vollständig vergangen)
    retain = (now - m).days                                # roher Cutoff fiele mitten in M (Tag ~15)
    maintenance.compact_snapshots(retain_days=retain, dry_run=False)
    with stats._conn() as c:
        # Grenz-Monat M bleibt KOMPLETT roh (alle 3 Tage), KEINE M-Monatszeile.
        m_raw = c.execute("SELECT COUNT(*) FROM snapshots WHERE substr(day,1,7)=?",
                          (m.strftime("%Y-%m"),)).fetchone()[0]
        assert m_raw == 3
        m_rollups = c.execute("SELECT COUNT(*) FROM snapshots_monthly WHERE month=?",
                              (m.strftime("%Y-%m"),)).fetchone()[0]
        assert m_rollups == 0
        # Der vollständige Vormonat M-1 IST verdichtet + roh weg.
        assert c.execute("SELECT COUNT(*) FROM snapshots_monthly WHERE month=?",
                         (prev.strftime("%Y-%m"),)).fetchone()[0] == 1
    # Idempotent: zweiter Lauf ändert nichts (M weiter roh, M-1-Rollup unverändert).
    maintenance.compact_snapshots(retain_days=retain, dry_run=False)
    with stats._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM snapshots WHERE substr(day,1,7)=?",
                        (m.strftime("%Y-%m"),)).fetchone()[0] == 3
        assert c.execute("SELECT COUNT(*) FROM snapshots_monthly").fetchone()[0] == 1


def test_prune_orphans(tmp_path):
    _setup(tmp_path)
    with stats._conn() as c:
        c.execute("INSERT INTO backtest_runs(bot_id,strategy,ts) VALUES(?,?,?)",
                  ("ghostbot", "S", "2026-01-01T00:00:00"))
    assert "ghostbot" in maintenance.prune_orphans(dry_run=True)["orphan_backtest_bots"]
    with stats._conn() as c:   # dry-run hat nichts gelöscht
        assert c.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 1
    maintenance.prune_orphans(dry_run=False)
    with stats._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 0


def test_learning_ledger(tmp_path):
    _setup(tmp_path)
    maintenance.record_ledger("non_viable", "MomentumMacd", "PF 0.26 über 3 Fenster", {"pf": 0.26})
    led = maintenance.get_ledger()
    assert led and led[0]["subject"] == "MomentumMacd" and led[0]["metrics"]["pf"] == 0.26


def test_storage_report_keys(tmp_path):
    _setup(tmp_path)
    rep = maintenance.storage_report()
    assert "tables" in rep and "db_kb" in rep and "orphan_backtest_bots" in rep
