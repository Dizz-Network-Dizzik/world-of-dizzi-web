"""Daten-Lifecycle / Lern-Gedächtnis-Pflege.

Intelligente Verdichtung statt Datenhaufen: alte Rohdaten -> kompakte Aggregate, dann Roh löschen;
Nicht-Tragfähiges kompakt im Learning-Ledger vermerken; Müll (Orphans/Logs) beseitigen.
Alles **idempotent**, **transaktional** und **dry-run-fähig** (Vorschau ohne Änderung).
Konzept: ../../10_LERN_GEDAECHTNIS_UND_LIFECYCLE.md
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timedelta, timezone

from . import audit, stats
from .config import DATA_DIR, PROJECT_ROOT

RETAIN_SNAPSHOT_DAYS = 90   # Tages-Snapshots länger als das -> Monats-Rollup
RETAIN_MARKET_DAYS = 90     # Markt-Snapshots länger als das -> Tages-Rollup
AUDIT_KEEP_LINES = 2000     # audit.log auf die letzten N Zeilen kappen


def _ensure_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots_monthly(
            bot_id TEXT, month TEXT, strategy TEXT, avg_profit_pct REAL, last_equity REAL,
            trades_closed INTEGER, avg_winrate_pct REAL, max_drawdown_pct REAL, n_days INTEGER,
            PRIMARY KEY(bot_id, month));
        CREATE TABLE IF NOT EXISTS market_daily(
            day TEXT PRIMARY KEY, dominant_regime TEXT, avg_volatility REAL, n INTEGER);
        CREATE TABLE IF NOT EXISTS learning_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, subject TEXT,
            conclusion TEXT, metrics TEXT);
        """
    )


def storage_report() -> dict:
    """Read-only Speicher-/Gedächtnis-Karte (Zeilen je Tabelle, Größen, Müll-Kandidaten)."""
    rep: dict = {"tables": {}, "files": {}}
    tables = ["snapshots", "market_snapshots", "backtest_runs", "strategy_validations",
              "optimizations", "snapshots_monthly", "market_daily", "learning_ledger"]
    with stats._conn() as c:
        _ensure_tables(c)
        for t in tables:
            try:
                rep["tables"][t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                rep["tables"][t] = None
    rep["db_kb"] = round(os.path.getsize(stats.DB_FILE) / 1024, 1) if os.path.exists(stats.DB_FILE) else 0
    al = DATA_DIR / "audit.log"
    if al.exists():
        with open(al, encoding="utf-8", errors="replace") as fh:
            rep["audit_lines"] = sum(1 for _ in fh)
        rep["audit_kb"] = round(al.stat().st_size / 1024, 1)
    rep["stray_logs"] = [os.path.basename(p) for p in glob.glob(str(DATA_DIR / "uvicorn_*.log"))]
    rep["baks"] = [os.path.basename(p) for p in glob.glob(str(DATA_DIR / "*.bak"))]
    from .registry import list_bots
    ids = {b.id for b in list_bots()}
    with stats._conn() as c:
        bt = [r[0] for r in c.execute("SELECT DISTINCT bot_id FROM backtest_runs").fetchall()]
    rep["orphan_backtest_bots"] = [b for b in bt if b not in ids]
    ud = PROJECT_ROOT / "engine" / "user_data"
    tdbs = glob.glob(str(ud / "tradesv3_*.sqlite"))
    rep["trade_dbs"] = len(tdbs)
    rep["orphan_trade_dbs"] = [os.path.basename(p) for p in tdbs
                               if not any(b in os.path.basename(p) for b in ids)]
    return rep


def prune_orphans(dry_run: bool = True) -> dict:
    """Karteileichen gelöschter Bots aus backtest_runs entfernen."""
    from .registry import list_bots
    ids = {b.id for b in list_bots()}
    with stats._conn() as c:
        bt = [r[0] for r in c.execute("SELECT DISTINCT bot_id FROM backtest_runs").fetchall()]
        orphan = [b for b in bt if b not in ids]
        if not dry_run and orphan:
            c.executemany("DELETE FROM backtest_runs WHERE bot_id=?", [(o,) for o in orphan])
    if not dry_run and orphan:
        audit.record("maintenance_prune_orphans", count=len(orphan))
    return {"orphan_backtest_bots": orphan, "would_delete": len(orphan), "dry_run": dry_run}


def compact_snapshots(retain_days: int = RETAIN_SNAPSHOT_DAYS, dry_run: bool = True) -> dict:
    """Tages-Snapshots älter als ``retain_days`` zu Monats-Aggregaten verdichten, Roh löschen.

    Der Cutoff wird auf den **Monatsanfang** gesnappt: nur VOLLSTÄNDIGE (ganz ältere) Monate werden
    rollupt. Sonst würde ein Grenz-Monat über mehrere Läufe inkrementell verdichtet und der unten
    stehende ``ON CONFLICT … DO UPDATE SET = excluded.*``-Replace verlöre die früher rollupten Tage
    (n_days/avg spiegelten nur die letzte Charge). Mit dem Monats-Snap wird jeder Monat genau EINMAL &
    vollständig verdichtet → die ``excluded.*``-Ersetzung ist korrekt UND idempotent."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).replace(day=1).strftime("%Y-%m-%d")
    with stats._conn() as c:
        _ensure_tables(c)
        old = c.execute(
            "SELECT bot_id, day, strategy, equity, profit_pct, trades_closed, winrate_pct, "
            "max_drawdown_pct FROM snapshots WHERE day < ?", (cutoff,)).fetchall()
        agg: dict = {}
        for bot, day, strat, eq, pp, tc, wr, dd in old:
            g = agg.setdefault((bot, (day or "")[:7]),
                               {"strategy": strat, "p": [], "eq": None, "tr": 0, "wr": [], "dd": [], "n": 0})
            if pp is not None:
                g["p"].append(pp)
            if eq is not None:
                g["eq"] = eq
            g["tr"] = max(g["tr"], tc or 0)
            if wr is not None:
                g["wr"].append(wr)
            if dd is not None:
                g["dd"].append(dd)
            g["n"] += 1
        if not dry_run and old:
            for (bot, month), g in agg.items():
                c.execute(
                    """INSERT INTO snapshots_monthly(bot_id,month,strategy,avg_profit_pct,last_equity,
                       trades_closed,avg_winrate_pct,max_drawdown_pct,n_days) VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(bot_id,month) DO UPDATE SET avg_profit_pct=excluded.avg_profit_pct,
                       last_equity=excluded.last_equity,trades_closed=excluded.trades_closed,
                       avg_winrate_pct=excluded.avg_winrate_pct,max_drawdown_pct=excluded.max_drawdown_pct,
                       n_days=excluded.n_days""",
                    (bot, month, g["strategy"],
                     round(sum(g["p"]) / len(g["p"]), 3) if g["p"] else None, g["eq"], g["tr"],
                     round(sum(g["wr"]) / len(g["wr"]), 2) if g["wr"] else None,
                     max(g["dd"]) if g["dd"] else None, g["n"]))
            c.execute("DELETE FROM snapshots WHERE day < ?", (cutoff,))
            audit.record("maintenance_compact_snapshots", rollups=len(agg), raw_deleted=len(old))
    return {"cutoff": cutoff, "raw_rows": len(old), "monthly_rollups": len(agg), "dry_run": dry_run}


def compact_market(retain_days: int = RETAIN_MARKET_DAYS, dry_run: bool = True) -> dict:
    """Stündliche Markt-Snapshots älter als ``retain_days`` zu Tages-Aggregaten verdichten, Roh löschen.

    Cutoff auf **Tages-Mitternacht** gesnappt: nur VOLLSTÄNDIGE (ganz ältere) Tage werden rollupt — analog
    ``compact_snapshots`` gegen inkrementelle Tages-Rollup-Überschreibung; so wird jeder Tag genau einmal &
    vollständig verdichtet (``excluded.*``-Replace korrekt + idempotent)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    with stats._conn() as c:
        _ensure_tables(c)
        old = c.execute("SELECT ts, regime, volatility FROM market_snapshots WHERE ts < ?",
                        (cutoff,)).fetchall()
        agg: dict = {}
        for ts, reg, vol in old:
            g = agg.setdefault((ts or "")[:10], {"reg": {}, "v": []})
            g["reg"][reg] = g["reg"].get(reg, 0) + 1
            if vol is not None:
                g["v"].append(vol)
        if not dry_run and old:
            for day, g in agg.items():
                dom = max(g["reg"], key=g["reg"].get) if g["reg"] else None
                c.execute(
                    """INSERT INTO market_daily(day,dominant_regime,avg_volatility,n) VALUES(?,?,?,?)
                       ON CONFLICT(day) DO UPDATE SET dominant_regime=excluded.dominant_regime,
                       avg_volatility=excluded.avg_volatility,n=excluded.n""",
                    (day, dom, round(sum(g["v"]) / len(g["v"]), 4) if g["v"] else None,
                     sum(g["reg"].values())))
            c.execute("DELETE FROM market_snapshots WHERE ts < ?", (cutoff,))
            audit.record("maintenance_compact_market", rollups=len(agg), raw_deleted=len(old))
    return {"cutoff": cutoff[:10], "raw_rows": len(old), "daily_rollups": len(agg), "dry_run": dry_run}


def rotate_audit(keep_lines: int = AUDIT_KEEP_LINES, dry_run: bool = True) -> dict:
    """audit.log auf die letzten ``keep_lines`` Zeilen kappen (Rest als 1 Kompakt-Vermerk)."""
    al = DATA_DIR / "audit.log"
    if not al.exists():
        return {"lines": 0, "trimmed": 0, "dry_run": dry_run}
    with open(al, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    trimmed = max(0, len(lines) - keep_lines)
    if not dry_run and trimmed:
        summary = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                              "event": "audit_rotated", "trimmed": trimmed}) + "\n"
        with open(al, "w", encoding="utf-8") as fh:
            fh.write(summary)
            fh.writelines(lines[-keep_lines:])
    return {"lines": len(lines), "kept": min(len(lines), keep_lines), "trimmed": trimmed, "dry_run": dry_run}


def record_ledger(kind: str, subject: str, conclusion: str, metrics: dict | None = None) -> dict:
    """Kompakter, dauerhafter Schluss-Vermerk (z. B. „Strategie X nicht tragfähig")."""
    with stats._conn() as c:
        _ensure_tables(c)
        c.execute("INSERT INTO learning_ledger(ts,kind,subject,conclusion,metrics) VALUES(?,?,?,?,?)",
                  (datetime.now(timezone.utc).isoformat(), kind, subject, conclusion,
                   json.dumps(metrics or {})))
    return {"ok": True, "subject": subject}


def get_ledger(limit: int = 50) -> list[dict]:
    with stats._conn() as c:
        _ensure_tables(c)
        rows = c.execute("SELECT ts,kind,subject,conclusion,metrics FROM learning_ledger "
                         "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for ts, kind, subj, concl, met in rows:
        try:
            m = json.loads(met or "{}")
        except Exception:
            m = {}
        out.append({"ts": ts, "kind": kind, "subject": subj, "conclusion": concl, "metrics": m})
    return out


def run_all(dry_run: bool = True) -> dict:
    """Kompletter Lifecycle-Durchlauf (Vorschau per dry_run=True)."""
    return {"dry_run": dry_run,
            "prune_orphans": prune_orphans(dry_run),
            "compact_snapshots": compact_snapshots(dry_run=dry_run),
            "compact_market": compact_market(dry_run=dry_run),
            "rotate_audit": rotate_audit(dry_run=dry_run)}
