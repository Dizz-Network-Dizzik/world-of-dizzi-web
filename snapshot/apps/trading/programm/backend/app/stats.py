"""Statistik-DB (SQLite, stdlib) — persistiert Backtest-Läufe je Bot.

Bewusst ohne ORM gehalten (sqlite3 aus der Standardbibliothek), um Abhängigkeiten
und Setup klein zu halten. Migration auf Postgres (M7) bleibt möglich, da der
Zugriff hier gekapselt ist.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROJECT_ROOT

DB_FILE: Path = DATA_DIR / "stats.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    strategy TEXT,
    ts TEXT NOT NULL,
    profit_total_pct REAL,
    profit_total_abs REAL,
    total_trades INTEGER,
    sharpe REAL,
    profit_factor REAL,
    max_drawdown_pct REAL,
    market_change_pct REAL,
    winrate_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_bot ON backtest_runs(bot_id);

-- Schlanke Lern-Datenbasis (Nordstern): EIN kompakter Snapshot je Bot/Tag.
-- Bewusst wenige Spalten, kein Tick-/Minutendaten -> < wenige MB/Jahr.
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    day TEXT NOT NULL,            -- UTC-Datum (YYYY-MM-DD), 1 Zeile/Bot/Tag
    ts TEXT NOT NULL,             -- exakter Zeitstempel des Snapshots
    strategy TEXT,
    trading_mode TEXT,
    equity REAL,
    profit_pct REAL,
    trades_closed INTEGER,
    trades_open INTEGER,
    winrate_pct REAL,
    max_drawdown_pct REAL,
    UNIQUE(bot_id, day)
);
CREATE INDEX IF NOT EXISTS idx_snap_bot ON snapshots(bot_id);

-- Validierungs-Status je Strategie/Engine (Backtest-Gate vor Echtgeld).
CREATE TABLE IF NOT EXISTS strategy_validations (
    strategy TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    validated INTEGER,
    windows INTEGER,
    profit_total_pct REAL,
    max_drawdown_pct REAL,
    total_trades INTEGER,
    winrate_pct REAL,
    profit_factor REAL
);

-- Gewinner-Vorschlag des Lern-Loops je Strategie (proposal-only, persistiert).
CREATE TABLE IF NOT EXISTS optimizations (
    strategy TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    winner_label TEXT,
    params TEXT,                 -- JSON
    profit_total_pct REAL,       -- OOS-Test-Profit (anchored) bzw. In-Sample-Profit (Legacy)
    max_drawdown_pct REAL,
    total_trades INTEGER,
    windows INTEGER,
    timeframe TEXT,              -- Timeframe der Tuning-Config (Gate: Auto-Upgrade nur bei Match)
    oos_validated INTEGER,       -- 1 = Gewinner hat das ungesehene Test-Fenster bestanden
    train_profit_pct REAL        -- Trainings-Fenster-Profit (zur Overfit-Diagnose Train vs. OOS)
);

-- C2/C3: Changelog der angewandten Verbesserungen (Upgrades) je Bot -> Versionsverlauf.
CREATE TABLE IF NOT EXISTS bot_upgrades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    tag INTEGER,
    name TEXT,
    strategy TEXT,
    version INTEGER,
    params TEXT,                 -- JSON
    profit_total_pct REAL
);

-- Optionaler Markt-Kontext (z.B. 1x/Stunde) fuer spaeteres Regime-Lernen.
CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL,
    regime TEXT,
    volatility REAL
);
CREATE INDEX IF NOT EXISTS idx_market_sym ON market_snapshots(symbol);
"""

_FIELDS = [
    "profit_total_pct", "profit_total_abs", "total_trades", "sharpe",
    "profit_factor", "max_drawdown_pct", "market_change_pct", "winrate_pct",
]


# Schema/Migration laufen EINMAL pro DB-Pfad (nicht bei jedem Read): /api/meta löste das sonst hunderte
# Male pro Aufruf aus (6+ Flotten-Schleifen × stats-Calls × executescript + 7 ALTER-Versuche). Keyed auf
# DB_FILE-Pfad → test-sicher (jede tmp-DB wird neu initialisiert). Idempotente Ops, daher Lock nur kosmetisch.
_inited: set[str] = set()
_init_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    key = str(DB_FILE)
    if key not in _inited:
        with _init_lock:
            if key not in _inited:
                conn.executescript(_SCHEMA)
                _migrate(conn)
                _inited.add(key)
    return conn


def _ro_connect(db: Path) -> sqlite3.Connection:
    """Read-only-Verbindung zu einer vom Freqtrade-Prozess beschriebenen WAL-Trade-DB.

    Das Backend liest diese DBs nur — read-only (``mode=ro``) ist Best-Practice (sqlite WAL): keine
    Write-Lock-Interaktion mit dem schreibenden Prozess, kein versehentliches Anlegen/Schreiben.
    Voraussetzung: die Datei existiert (jeder Aufrufer prüft das vorher)."""
    con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotente Mini-Migrationen für bestehende DBs (neue Spalten additiv)."""
    # profit_factor zu strategy_validations (Echtgeld-Gate, ab 07.06.2026).
    try:
        conn.execute("ALTER TABLE strategy_validations ADD COLUMN profit_factor REAL")
    except sqlite3.OperationalError:
        pass  # Spalte existiert bereits
    # Reicheres Markt-Regime (08.06.2026): relatives Vola-Regime + vola-normierte Trendstärke,
    # + HMM-Konfidenz des aktuellen Regimes (für die regime-bedingte Master-Allokation).
    for col, typ in (("vol_regime", "TEXT"), ("trend_z", "REAL"), ("regime_conf", "REAL"),
                     ("next_regime", "TEXT"), ("regime_stay_prob", "REAL")):
        try:
            conn.execute(f"ALTER TABLE market_snapshots ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    # Anchored-Walk-Forward-Felder (10.06.2026): Tuning-Timeframe (Auto-Upgrade-Gate),
    # OOS-Validierung des Gewinners + Trainings-Profit (Overfit-Diagnose Train vs. OOS).
    for col, typ in (("timeframe", "TEXT"), ("oos_validated", "INTEGER"),
                     ("train_profit_pct", "REAL")):
        try:
            conn.execute(f"ALTER TABLE optimizations ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass


def save_backtest_run(bot_id: str, strategy: str, metrics: dict[str, Any]) -> None:
    """Speichert die Kennzahlen eines Backtest-Laufs."""
    row = {f: metrics.get(f) for f in _FIELDS}
    with _conn() as conn:
        conn.execute(
            f"""INSERT INTO backtest_runs
                (bot_id, strategy, ts, {', '.join(_FIELDS)})
                VALUES (?, ?, ?, {', '.join(['?'] * len(_FIELDS))})""",
            [bot_id, strategy, datetime.now(timezone.utc).isoformat(), *row.values()],
        )


def get_runs(bot_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with _conn() as conn:
        cur = conn.execute(
            "SELECT * FROM backtest_runs WHERE bot_id=? ORDER BY id DESC LIMIT ?",
            (bot_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_latest(bot_id: str) -> dict[str, Any] | None:
    runs = get_runs(bot_id, limit=1)
    return runs[0] if runs else None


def equity_curve(bot_id: str, starting: float = 0.0) -> dict[str, Any]:
    """Kontoverlauf eines Bots aus dessen Freqtrade-Trade-DB (kumulierter PnL)."""
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return {"points": [], "starting": starting, "note": "Noch keine Trades (Bot nie gelaufen?)."}
    con = _ro_connect(db)
    try:
        rows = con.execute(
            "SELECT close_date, close_profit_abs FROM trades "
            "WHERE is_open=0 AND close_date IS NOT NULL ORDER BY close_date"
        ).fetchall()
    except Exception:
        return {"points": [], "starting": starting}
    finally:
        con.close()
    eq, pts = starting, [{"t": "Start", "equity": round(starting, 2)}]
    for r in rows:
        eq += float(r["close_profit_abs"] or 0)
        pts.append({"t": str(r["close_date"])[:16], "equity": round(eq, 2)})
    return {"points": pts, "starting": starting, "closed_trades": len(rows)}


def recent_trades(bot_id: str, limit: int = 10) -> dict[str, Any]:
    """Liefert die letzten Trades eines Bots + Zaehlung offen/geschlossen."""
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return {"trades": [], "open": 0, "closed": 0, "note": "Noch keine Trades."}
    con = _ro_connect(db)
    try:
        rows = con.execute(
            "SELECT pair, open_date, close_date, open_rate, close_rate, amount, "
            "close_profit, close_profit_abs, is_open, exit_reason, enter_tag, "
            "leverage, is_short "
            "FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        c = con.execute(
            "SELECT SUM(CASE WHEN is_open=1 THEN 1 ELSE 0 END) o, "
            "SUM(CASE WHEN is_open=0 THEN 1 ELSE 0 END) c FROM trades"
        ).fetchone()
    except Exception as exc:
        return {"trades": [], "error": str(exc)}
    finally:
        con.close()
    trades = [{
        "pair": r["pair"],
        "open_date": str(r["open_date"])[:16],
        "close_date": (str(r["close_date"])[:16] if r["close_date"] else None),
        "is_open": bool(r["is_open"]),
        "open_rate": (round(r["open_rate"], 6) if r["open_rate"] is not None else None),
        "close_rate": (round(r["close_rate"], 6) if r["close_rate"] is not None else None),
        "profit_pct": (round(r["close_profit"] * 100, 2) if r["close_profit"] is not None else None),
        "profit_abs": (round(r["close_profit_abs"], 2) if r["close_profit_abs"] is not None else None),
        "exit_reason": r["exit_reason"],
        "enter_tag": r["enter_tag"],
        "leverage": (r["leverage"] if r["leverage"] is not None else None),
        "is_short": (bool(r["is_short"]) if r["is_short"] is not None else False),
    } for r in rows]
    return {"trades": trades, "open": c["o"] or 0, "closed": c["c"] or 0}


def bot_pnl(bot_id: str, wallet: float = 0.0, since_days: int | None = None) -> dict[str, Any]:
    """Live-PnL eines Bots aus der Trade-DB: offene/geschlossene Trades + realisierter Profit.

    ``profit_abs`` = Summe ``close_profit_abs`` (realisiert, geschlossene Trades).
    ``profit_pct`` = relativ zum (Demo-)Wallet, falls bekannt. Schlank (eine Query).
    ``since_days`` filtert die GESCHLOSSENEN Trades auf die letzten N Tage (Zeitraum-Auswahl der UI);
    offene Trades bleiben immer enthalten (sie sind aktuell).
    """
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    out: dict[str, Any] = {"open": 0, "closed": 0, "wins": 0, "profit_abs": None, "profit_pct": None}
    if not db.exists():
        return out
    cutoff = None
    if since_days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d %H:%M:%S")
    con = _ro_connect(db)
    try:
        out["open"] = con.execute("SELECT COUNT(*) FROM trades WHERE is_open=1").fetchone()[0] or 0
        if cutoff:
            r = con.execute("SELECT COUNT(*) c, SUM(CASE WHEN close_profit>0 THEN 1 ELSE 0 END) w, "
                            "COALESCE(SUM(close_profit_abs),0) pabs FROM trades "
                            "WHERE is_open=0 AND close_date>=?", (cutoff,)).fetchone()
        else:
            r = con.execute("SELECT COUNT(*) c, SUM(CASE WHEN close_profit>0 THEN 1 ELSE 0 END) w, "
                            "COALESCE(SUM(close_profit_abs),0) pabs FROM trades WHERE is_open=0").fetchone()
    except Exception:
        return out
    finally:
        con.close()
    pabs = float(r["pabs"] or 0.0)
    out["closed"] = r["c"] or 0
    out["wins"] = r["w"] or 0
    out["profit_abs"] = round(pabs, 2)
    out["profit_pct"] = round(pabs / wallet * 100, 2) if wallet else None
    return out


def open_positions(bot_id: str) -> list[dict[str, Any]]:
    """OFFENE Positionen eines Bots aus der Trade-DB: Pair + Notional (Positionsgröße).

    Notional = ``stake_amount × leverage`` (Margin × Hebel = tatsächliches Markt-Exposure);
    Fallback ``amount × open_rate``, falls stake_amount fehlt. Grundlage für die ehrliche
    Konzentrations-Messung (echtes Klumpenrisiko der GEHALTENEN Positionen statt des
    zulässigen Universums). Read-only, eine Query."""
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return []
    con = _ro_connect(db)
    try:
        rows = con.execute(
            "SELECT pair, stake_amount, amount, open_rate, leverage, is_short "
            "FROM trades WHERE is_open=1"
        ).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    out = []
    for r in rows:
        lev = float(r["leverage"] or 1.0) or 1.0
        stake = r["stake_amount"]
        if stake is not None:
            notional = float(stake) * lev
        else:
            notional = float(r["amount"] or 0.0) * float(r["open_rate"] or 0.0)
        out.append({"pair": r["pair"], "notional": round(notional, 2),
                    "is_short": bool(r["is_short"]) if r["is_short"] is not None else False})
    return out


def closed_trades_for_regime(bot_id: str) -> list[dict[str, Any]]:
    """Geschlossene Trades eines Bots mit Schlusszeit + Profit% (fuer Per-Trade-Regime).

    Liefert nur die fuer die Regime-Zuordnung noetigen Felder (``close_date`` als
    roher Zeitstempel-String, ``profit_pct`` aus ``close_profit``). Bewusst schlank
    und aeltest->neuest sortiert.
    """
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return []
    con = _ro_connect(db)
    try:
        rows = con.execute(
            "SELECT pair, close_date, close_profit FROM trades "
            "WHERE is_open=0 AND close_date IS NOT NULL AND close_profit IS NOT NULL "
            "ORDER BY close_date"
        ).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    return [{"pair": r["pair"], "close_date": str(r["close_date"]),
             "profit_pct": round(float(r["close_profit"]) * 100, 4)} for r in rows]


def _expectancy_from_profits(profits_pct: list[float]) -> dict[str, Any]:
    """Erwartungswert-Kennzahlen aus geschlossenen Trade-Renditen (%). REIN (testbar ohne DB).

    Liefert Winrate, Ø-Gewinn/Ø-Verlust (Beträge, %), **Payoff** b = Ø-Gewinn/Ø-Verlust, den
    **Erwartungswert in R** (Verlust-Einheiten) E = W·b − (1−W) und den **klassischen Kelly**
    f* = W − (1−W)/b. Trades mit profit==0 zählen weder als Gewinn noch Verlust (neutral). Ohne
    Verluste (b undefiniert) bleiben Payoff/E/Kelly None — kein Hochrechnen aus reinen Gewinnern."""
    n = len(profits_pct)
    wins = [p for p in profits_pct if p > 0]
    losses = [-p for p in profits_pct if p < 0]      # Verluste als positive Beträge
    n_win, n_loss = len(wins), len(losses)
    decided = n_win + n_loss
    winrate = (n_win / decided) if decided else 0.0
    avg_win = (sum(wins) / n_win) if n_win else 0.0
    avg_loss = (sum(losses) / n_loss) if n_loss else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else None
    expectancy_r = (winrate * payoff - (1.0 - winrate)) if payoff is not None else None
    kelly = (winrate - (1.0 - winrate) / payoff) if (payoff and payoff > 0) else None
    exp_pct = (sum(profits_pct) / n) if n else 0.0   # Ø-Rendite je Trade (direkt, %)
    return {"n_trades": n, "n_decided": decided, "winrate": round(winrate, 4),
            "avg_win_pct": round(avg_win, 4), "avg_loss_pct": round(avg_loss, 4),
            "payoff": round(payoff, 4) if payoff is not None else None,
            "expectancy_r": round(expectancy_r, 4) if expectancy_r is not None else None,
            "expectancy_pct": round(exp_pct, 4),
            "kelly": round(kelly, 4) if kelly is not None else None}


def trade_expectancy(bot_id: str) -> dict[str, Any]:
    """Per-Trade-Erwartungswert eines Bots aus der Live-Trade-DB (geschlossene Trades). Read-only.

    Edge-Quelle für expectancy-basiertes Sizing (NICHT winrate-naiv): eine hohe Winrate mit winzigem
    Ø-Gewinn und großem Ø-Verlust ergibt **negativen** Kelly/Erwartungswert → der Sizer darf so einen
    Bot NICHT hochhebeln. Verdichtet die Profit%-Reihe via ``_expectancy_from_profits``."""
    profits = [t["profit_pct"] for t in closed_trades_for_regime(bot_id)]
    return _expectancy_from_profits(profits)


def pooled_expectancy(bot_ids: list[str]) -> dict[str, Any]:
    """Gepoolter Per-Trade-Erwartungswert über MEHRERE Bots (read-only): verkettet die geschlossenen
    Trades aller übergebenen Bots zu EINER Profit%-Reihe. Gedacht für Bots derselben STRATEGIE
    (gleicher Signalgeber ⇒ gleiche Edge-Hypothese): mehr Stichprobe → stabilerer Kelly, bevor ein
    einzelner Bot genug eigene Trades hat. Registry-frei (Aufrufer liefert die Bot-Ids und gated
    die Mindest-Stichprobe) — kein Import-Zyklus."""
    profits: list[float] = []
    for bid in bot_ids:
        profits.extend(t["profit_pct"] for t in closed_trades_for_regime(bid))
    return _expectancy_from_profits(profits)


def execution_costs(bot_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Execution-Qualität je geschlossenem Trade (P4): **Ist- vs. Erwartungspreis** (Slippage) + Gebühren.

    Freqtrade speichert pro Trade den **angeforderten** Preis (``open_rate_requested`` /
    ``close_rate_requested``) UND den **tatsächlichen** Fill (``open_rate`` / ``close_rate``). Daraus
    wird die **richtungsbewusste** (kostenpositive) Slippage in Basispunkten berechnet — Long zahlt beim
    Kauf bei höherem Fill drauf, Short beim Verkauf bei niedrigerem Fill usw. Dazu die realen Gebühren
    (``fee_open_cost`` + ``fee_close_cost``) relativ zum Trade-Wert. Im Dry-Run ist die Slippage i. d. R.
    0 (Fill == angefordert) — die Messung ist die **M6-Vorbereitung**: ab Echtgeld zeigt sie echte
    Slippage; steigende Slippage = sinkende Liquidität. Ältest→neuest sortiert."""
    db = PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return []
    con = _ro_connect(db)
    try:
        rows = con.execute(
            "SELECT pair, is_short, close_date, open_rate, open_rate_requested, close_rate, "
            "close_rate_requested, open_trade_value, fee_open_cost, fee_close_cost "
            "FROM trades WHERE is_open=0 AND close_date IS NOT NULL ORDER BY close_date LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        short = bool(r["is_short"])
        oreq, ofill = r["open_rate_requested"], r["open_rate"]
        creq, cfill = r["close_rate_requested"], r["close_rate"]
        slip = None
        if oreq and creq and ofill is not None and cfill is not None:
            # kostenpositive (adverse) Slippage je Seite, richtungsbewusst:
            entry = (ofill - oreq) if not short else (oreq - ofill)
            exit_ = (creq - cfill) if not short else (cfill - creq)
            slip = round((entry / oreq + exit_ / creq) * 10000.0, 2)  # Basispunkte
        value = float(r["open_trade_value"] or 0.0)
        fees = float(r["fee_open_cost"] or 0.0) + float(r["fee_close_cost"] or 0.0)
        fee_bps = round(fees / value * 10000.0, 2) if value else None
        out.append({"pair": r["pair"], "close_date": str(r["close_date"]),
                    "slippage_bps": slip, "fee_bps": fee_bps,
                    "cost_bps": (round((slip or 0.0) + (fee_bps or 0.0), 2)
                                 if (slip is not None or fee_bps is not None) else None)})
    return out


def reset_bot_trades(bot_id: str) -> dict[str, Any]:
    """Setzt die ANGEZEIGTEN Statistiken eines Bots zurueck: loescht seine Trade-DB
    (``tradesv3_<id>.sqlite`` + WAL/SHM). Freqtrade legt sie beim naechsten Start leer neu an.
    **Lern-Tabellen (snapshots/validations/optimizations/ledger) bleiben unberuehrt** -> der
    Lernalgorithmus wird nicht zurueckgesetzt. Aufrufer sollte den Bot vorher stoppen.
    """
    base = PROJECT_ROOT / "engine" / "user_data"
    removed = []
    for suffix in ("", "-wal", "-shm"):
        f = base / f"tradesv3_{bot_id}.sqlite{suffix}"
        try:
            if f.exists():
                f.unlink()
                removed.append(f.name)
        except Exception:
            pass
    return {"reset": True, "removed": removed}


_SNAP_FIELDS = [
    "strategy", "trading_mode", "equity", "profit_pct",
    "trades_closed", "trades_open", "winrate_pct", "max_drawdown_pct",
]


def has_snapshot_today(bot_id: str, day: str | None = None) -> bool:
    """True, wenn fuer heute (UTC) bereits ein Snapshot dieses Bots existiert."""
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM snapshots WHERE bot_id=? AND day=? LIMIT 1", (bot_id, day)
        )
        return cur.fetchone() is not None


def save_snapshot(bot_id: str, fields: dict[str, Any]) -> None:
    """Schreibt/aktualisiert den Tages-Snapshot eines Bots (1 Zeile/Bot/Tag)."""
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    row = {f: fields.get(f) for f in _SNAP_FIELDS}
    with _conn() as conn:
        conn.execute(
            f"""INSERT INTO snapshots (bot_id, day, ts, {', '.join(_SNAP_FIELDS)})
                VALUES (?, ?, ?, {', '.join(['?'] * len(_SNAP_FIELDS))})
                ON CONFLICT(bot_id, day) DO UPDATE SET
                ts=excluded.ts, {', '.join(f'{f}=excluded.{f}' for f in _SNAP_FIELDS)}""",
            [bot_id, day, now.isoformat(), *row.values()],
        )


def get_snapshots(bot_id: str, limit: int = 90) -> list[dict[str, Any]]:
    """Liefert die letzten Tages-Snapshots eines Bots (aelteste->neueste)."""
    with _conn() as conn:
        cur = conn.execute(
            "SELECT * FROM snapshots WHERE bot_id=? ORDER BY day DESC LIMIT ?",
            (bot_id, limit),
        )
        return [dict(r) for r in cur.fetchall()][::-1]


def save_strategy_validation(strategy: str, validated: bool, windows: int, metrics: dict[str, Any]) -> None:
    """Speichert/aktualisiert den Validierungs-Status einer Strategie (1 Zeile/Strategie)."""
    with _conn() as conn:
        conn.execute(
            """INSERT INTO strategy_validations
               (strategy, ts, validated, windows, profit_total_pct, max_drawdown_pct,
                total_trades, winrate_pct, profit_factor)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(strategy) DO UPDATE SET
               ts=excluded.ts, validated=excluded.validated, windows=excluded.windows,
               profit_total_pct=excluded.profit_total_pct, max_drawdown_pct=excluded.max_drawdown_pct,
               total_trades=excluded.total_trades, winrate_pct=excluded.winrate_pct,
               profit_factor=excluded.profit_factor""",
            [strategy, datetime.now(timezone.utc).isoformat(), 1 if validated else 0, int(windows),
             metrics.get("profit_total_pct"), metrics.get("max_drawdown_pct"),
             metrics.get("total_trades"), metrics.get("winrate_pct"), metrics.get("profit_factor")],
        )


def get_strategy_validation(strategy: str) -> dict[str, Any] | None:
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM strategy_validations WHERE strategy=?", (strategy,))
        row = cur.fetchone()
        return dict(row) if row else None


def save_optimization(strategy: str, winner: dict, windows: int,
                      timeframe: str | None = None) -> None:
    """Persistiert den Gewinner-Vorschlag des Lern-Loops je Strategie (1 Zeile).

    ``profit_total_pct`` trägt beim anchored Loop die ehrliche OOS-Test-Zahl; ``train_profit_pct``
    den Trainings-Wert. ``oos_validated`` + ``timeframe`` gaten die Auto-Anwendung."""
    with _conn() as conn:
        conn.execute(
            """INSERT INTO optimizations
               (strategy, ts, winner_label, params, profit_total_pct, max_drawdown_pct,
                total_trades, windows, timeframe, oos_validated, train_profit_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(strategy) DO UPDATE SET
               ts=excluded.ts, winner_label=excluded.winner_label, params=excluded.params,
               profit_total_pct=excluded.profit_total_pct, max_drawdown_pct=excluded.max_drawdown_pct,
               total_trades=excluded.total_trades, windows=excluded.windows,
               timeframe=excluded.timeframe, oos_validated=excluded.oos_validated,
               train_profit_pct=excluded.train_profit_pct""",
            [strategy, datetime.now(timezone.utc).isoformat(), winner.get("label"),
             json.dumps(winner.get("params") or {}), winner.get("profit_total_pct"),
             winner.get("max_drawdown_pct"), winner.get("total_trades"), int(windows),
             timeframe, 1 if winner.get("oos_validated") else 0,
             winner.get("train_profit_total_pct")],
        )


def record_upgrade(bot_id: str, tag: int | None, name: str | None, strategy: str | None,
                   version: int, params: dict | None, profit_total_pct: float | None = None) -> None:
    """C2/C3: protokolliert ein angewandtes Upgrade (Verbesserung) eines Bots im Changelog."""
    with _conn() as conn:
        conn.execute(
            """INSERT INTO bot_upgrades (ts, bot_id, tag, name, strategy, version, params, profit_total_pct)
               VALUES (?,?,?,?,?,?,?,?)""",
            [datetime.now(timezone.utc).isoformat(), bot_id, tag, name, strategy, int(version),
             json.dumps(params or {}), profit_total_pct],
        )


def get_upgrades(limit: int = 60) -> list[dict[str, Any]]:
    """Changelog: jüngste angewandte Upgrades (neueste zuerst)."""
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM bot_upgrades ORDER BY id DESC LIMIT ?", (int(limit),))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["params"] = json.loads(d.get("params") or "{}")
            except Exception:
                d["params"] = {}
            out.append(d)
        return out


def get_all_optimizations() -> list[dict[str, Any]]:
    """Alle persistierten Gewinner-Vorschläge (je Strategie)."""
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM optimizations ORDER BY strategy")
        out = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["params"] = json.loads(d.get("params") or "{}")
            except Exception:
                d["params"] = {}
            out.append(d)
        return out


def get_optimization(strategy: str) -> dict[str, Any] | None:
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM optimizations WHERE strategy=?", (strategy,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["params"] = json.loads(d.get("params") or "{}")
        except Exception:
            d["params"] = {}
        return d


def save_market_snapshot(symbol: str, price: float | None,
                         regime: str | None = None, volatility: float | None = None,
                         vol_regime: str | None = None, trend_z: float | None = None,
                         regime_conf: float | None = None, next_regime: str | None = None,
                         regime_stay_prob: float | None = None) -> None:
    """Optionaler Markt-Kontext-Snapshot (sparsam aufrufen, z.B. 1x/Stunde).

    ``regime`` = Richtungs-Regime (trend_up/down/range, primär HMM), ``vol_regime`` = relatives
    Volatilitäts-Regime (calm/normal/turbulent gegen die eigene Baseline), ``trend_z`` = vola-
    normierte Trendstärke (Signed-z), ``regime_conf`` = HMM-Konfidenz des Regimes (0..1; speist die
    regime-bedingte Master-Allokation). ``volatility`` bleibt die absolute Return-Stdev in %.
    """
    with _conn() as conn:
        conn.execute(
            "INSERT INTO market_snapshots (ts, symbol, price, regime, volatility, vol_regime, "
            "trend_z, regime_conf, next_regime, regime_stay_prob) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [datetime.now(timezone.utc).isoformat(), symbol, price, regime, volatility,
             vol_regime, trend_z, regime_conf, next_regime, regime_stay_prob],
        )


def get_market_snapshots(limit: int = 48) -> list[dict[str, Any]]:
    """Liefert die letzten Markt-Snapshots (aelteste->neueste)."""
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()][::-1]


def summary(bot_id: str) -> dict[str, Any]:
    """Aggregierte Übersicht über alle Läufe eines Bots."""
    with _conn() as conn:
        cur = conn.execute(
            """SELECT COUNT(*) AS runs,
                      AVG(profit_total_pct) AS avg_profit_pct,
                      MAX(profit_total_pct) AS best_profit_pct,
                      MAX(max_drawdown_pct) AS worst_drawdown_pct
               FROM backtest_runs WHERE bot_id=?""",
            (bot_id,),
        )
        return dict(cur.fetchone())
