"""mn_base.py — geteilte Basis der markt-neutralen Sim-Engines (CSM / Pairs / StatArb / MarketMaking).

DRY-Sockel: die vier Engines teilten zuvor jeweils dieselbe Boilerplate — Config-Laden/-Setzen
(mit Typ-Coercion), den identischen Equity-Statistik-Block (Sharpe/Ann/TotalReturn/MaxDD) am Ende
jeder ``simulate`` und das UI-Ausdünnen der Equity-Kurve. Hier zentralisiert (eine Quelle der
Wahrheit, leichter erweiterbar). Alles read-only/rein — kein echtes Risiko, keine Orders.

Der gemeinsame SQLite-Schema-Sockel (``csm_*``-Tabellen, Meta-KV) lebt ebenfalls hier; ``csm.py``
re-exportiert die Helfer unter ihren alten Namen, damit bestehende ``csm._meta_get``-Aufrufe gültig
bleiben. Reines Python (Backend-venv ohne numpy), dependency-leicht, testbar.
"""
from __future__ import annotations

import json
import math
import statistics

from . import stats

DAY_MS = 24 * 60 * 60 * 1000


def ensure(conn) -> None:
    """Legt den gemeinsamen markt-neutralen Schema-Sockel an (idempotent)."""
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS csm_prices(
              symbol TEXT, day INTEGER, close REAL, PRIMARY KEY(symbol, day));
           CREATE TABLE IF NOT EXISTS csm_meta(key TEXT PRIMARY KEY, value TEXT);
           CREATE TABLE IF NOT EXISTS csm_equity_log(
              day INTEGER PRIMARY KEY, ts TEXT, sharpe REAL, ann_pct REAL, total_return_pct REAL);
           CREATE TABLE IF NOT EXISTS csm_forward(
              day INTEGER PRIMARY KEY, ts TEXT, ret REAL, config_fp TEXT);"""
    )


# ---------- Meta-KV (geteilter Schlüssel-Wert-Speicher) ----------
def meta_get(key: str) -> str | None:
    with stats._conn() as c:
        ensure(c)
        row = c.execute("SELECT value FROM csm_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(key: str, value: str) -> None:
    with stats._conn() as c:
        ensure(c)
        c.execute("INSERT INTO csm_meta(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------- Config (laden/setzen mit Typ-Coercion) ----------
def config_get(defaults: dict, meta_key: str) -> dict:
    """Engine-Config = DEFAULTS, überschrieben mit dem unter ``meta_key`` gespeicherten Patch."""
    cfg = dict(defaults)
    raw = meta_get(meta_key)
    if raw:
        try:
            cfg.update(json.loads(raw))
        except Exception:
            pass
    return cfg


def config_set(defaults: dict, meta_key: str, patch: dict) -> dict:
    """Übernimmt nur bekannte Keys aus ``patch`` (auf den DEFAULTS-Typ gecastet) und persistiert."""
    cfg = config_get(defaults, meta_key)
    for k in defaults:
        if k in patch and patch[k] is not None:
            cfg[k] = type(defaults[k])(patch[k])
    meta_set(meta_key, json.dumps(cfg))
    return cfg


# ---------- Equity-Statistik (geteilter Auswertungs-Block) ----------
def equity_stats(rets: list[float], equity: list, capital: float, final_eq: float) -> dict:
    """Verdichtet eine Renditereihe + Equity-Kurve zu den Standard-Kennzahlen aller MN-Engines.

    ``final_eq`` ist die UNGERUNDETE finale Equity (die Kurve trägt gerundete Werte); so bleibt die
    Numerik bit-genau identisch zu den vorherigen Inline-Blöcken. Sharpe/Ann annualisiert (×√365 /
    365-Tage-Compounding), MaxDD aus der Equity-Kurve.
    """
    days = len(rets)
    total_ret = final_eq / capital - 1.0
    mean = statistics.mean(rets) if rets else 0.0
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    sr_period = (mean / sd) if sd > 0 else 0.0          # Periode-Sharpe (nicht annualisiert) für PSR
    sharpe = sr_period * math.sqrt(365)
    ann = ((final_eq / capital) ** (365.0 / days) - 1.0) if days > 0 else 0.0
    skew, kurt = _skew_kurt(rets, mean, sd)
    peak, maxdd = -1e18, 0.0
    for _, v in equity:
        peak = max(peak, v)
        maxdd = min(maxdd, v / peak - 1.0)
    return {
        "days": days,
        "sharpe": round(sharpe, 2),
        "ann_pct": round(ann * 100, 1),
        "total_return_pct": round(total_ret * 100, 1),
        "maxdd_pct": round(maxdd * 100, 1),
        "last_day_return_pct": round(rets[-1] * 100, 3) if rets else 0.0,
        "skew": round(skew, 3), "kurtosis": round(kurt, 3),
        "psr": round(psr(sr_period, skew, kurt, days), 3),   # P(true Sharpe > 0), nicht-normal-korrigiert
    }


def _skew_kurt(rets: list[float], mean: float, sd: float) -> tuple[float, float]:
    """Stichproben-Schiefe + (Nicht-Exzess-)Kurtosis (Normal=3). (0, 3) bei zu wenig Daten."""
    n = len(rets)
    if n < 3 or sd <= 0:
        return 0.0, 3.0
    m3 = sum((r - mean) ** 3 for r in rets) / n
    m4 = sum((r - mean) ** 4 for r in rets) / n
    return m3 / sd ** 3, m4 / sd ** 4


def _phi(x: float) -> float:
    """Standardnormal-Verteilungsfunktion Φ (via erf, ohne scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def psr(sr_period: float, skew: float, kurt: float, n: int, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (López de Prado): P(wahre Sharpe > ``sr_benchmark``), korrigiert für
    Stichprobenlänge n + Schiefe + Kurtosis (fat tails). ``sr_period`` = NICHT-annualisierte Sharpe,
    ``kurt`` = Nicht-Exzess-Kurtosis (Normal=3). 0..1."""
    if n < 3:
        return 0.0
    denom_sq = 1.0 - skew * sr_period + ((kurt - 1.0) / 4.0) * sr_period ** 2
    if denom_sq <= 0:
        return 0.0
    sr_std = math.sqrt(denom_sq / (n - 1))
    if sr_std <= 0:
        return 1.0 if sr_period > sr_benchmark else 0.0
    return _phi((sr_period - sr_benchmark) / sr_std)


def downsample(eq: list, equity_points: int) -> list:
    """Dünnt eine Equity-Kurve gleichmäßig auf ~``equity_points`` Punkte aus (für die UI)."""
    if len(eq) > equity_points:
        step = len(eq) / equity_points
        eq = [eq[int(i * step)] for i in range(equity_points)] + [eq[-1]]
    return eq
