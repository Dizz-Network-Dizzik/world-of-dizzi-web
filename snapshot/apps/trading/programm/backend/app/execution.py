"""execution.py — Execution-/Slippage-Tracking über die Flotte (P4, M6-Vorbereitung).

Beobachtbarkeit der **Ausführungsqualität**: je geschlossenem Trade misst ``stats.execution_costs`` die
**Slippage** (Ist-Fill vs. angeforderter Preis, richtungsbewusst, in Basispunkten) und die realen
**Gebühren**. Dieses Modul verdichtet das pro Bot und über die ganze Flotte, erkennt **steigende**
Slippage (= sinkende Liquidität) und markiert teure/auffällige Bots.

Im Dry-Run ist die Slippage typischerweise 0 (der Fill entspricht dem angeforderten Preis) — die
Gebühren sind dagegen schon real. Der Wert liegt in der **Vorbereitung auf Echtgeld (M6)**: dieselbe
Messung zeigt live die echte Slippage und warnt, bevor schlechte Liquidität die Rendite auffrisst.
Read-only/Analyse — 0 Risiko."""
from __future__ import annotations

from . import cache, jsonstore, registry, stats
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "execution.json"
_ANALYZE_TTL = 3.0  # s — Mehrfach-Aufrufe je UI-Refresh auf eine Berechnung kollabieren (read-only)

_DEFAULTS = {
    "enabled": True,
    "warn_slippage_bps": 15.0,   # Ø-Slippage je Trade darüber → Warnung
    "warn_cost_bps": 45.0,       # Ø-Gesamtkosten (Slippage+Gebühr) je Trade darüber → Warnung
    "warn_trend_bps": 8.0,       # Anstieg jüngste vs. ältere Slippage darüber → Liquidität sinkt
    "min_trades": 10,            # so viele geschlossene Trades für einen belastbaren Trend
    "recent_window": 20,         # „jüngste" Trades für den Trend-Vergleich
}


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("warn_slippage_bps", "warn_cost_bps", "warn_trend_bps"):
        if k in patch:
            try:
                s[k] = float(patch[k])
            except (TypeError, ValueError):
                pass
    for k in ("min_trades", "recent_window"):
        if k in patch:
            try:
                s[k] = max(1, int(patch[k]))
            except (TypeError, ValueError):
                pass
    if "enabled" in patch:
        s["enabled"] = bool(patch["enabled"])
    jsonstore.write_atomic(STATE_FILE, s)
    return s


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def execution_for(bot, cfg: dict) -> dict:
    """Execution-Kennzahlen EINES Bots (read-only) aus seinen geschlossenen Trades."""
    trades = stats.execution_costs(bot.id, limit=500)
    slips = [t["slippage_bps"] for t in trades if t["slippage_bps"] is not None]
    fees = [t["fee_bps"] for t in trades if t["fee_bps"] is not None]
    costs = [t["cost_bps"] for t in trades if t["cost_bps"] is not None]

    trend = None
    win = int(cfg["recent_window"])
    if len(slips) >= int(cfg["min_trades"]) and len(slips) > win:
        recent = slips[-win:]
        baseline = slips[:-win]
        ra, ba = _avg(recent), _avg(baseline)
        if ra is not None and ba is not None:
            trend = round(ra - ba, 2)

    avg_slip = _avg(slips)
    avg_cost = _avg(costs)
    flag = None
    if cfg.get("enabled"):
        if trend is not None and trend >= cfg["warn_trend_bps"]:
            flag = f"steigende Slippage (+{trend} bps jüngst) → Liquidität sinkt"
        elif avg_slip is not None and avg_slip >= cfg["warn_slippage_bps"]:
            flag = f"hohe Slippage (Ø {avg_slip} bps)"
        elif avg_cost is not None and avg_cost >= cfg["warn_cost_bps"]:
            flag = f"hohe Ausführungskosten (Ø {avg_cost} bps)"
    return {"bot_id": bot.id, "tag": getattr(bot, "tag", None), "name": bot.name,
            "strategy": bot.strategy, "n_trades": len(trades),
            "avg_slippage_bps": avg_slip, "avg_fee_bps": _avg(fees), "avg_cost_bps": avg_cost,
            "worst_slippage_bps": (max(slips) if slips else None), "trend_bps": trend, "flag": flag}


def analyze(use_cache: bool = False) -> dict:
    """Execution-/Slippage-Analyse über alle Bots (read-only) + Flotten-Aggregat + Flags.

    ``use_cache``: für UI/Status-Pfade kurz memoisieren (``_ANALYZE_TTL``)."""
    if use_cache:
        return cache.ttl_get("execution.analyze", _ANALYZE_TTL, lambda: analyze(use_cache=False))
    cfg = get_config()
    rows = [execution_for(b, cfg) for b in registry.list_bots()]
    active = [r for r in rows if r["n_trades"] > 0]

    # Flotten-Aggregat = trade-gewichteter Mittelwert über alle Bots (jede Kennzahl × n_trades).
    def _weighted(field: str) -> float | None:
        num = den = 0.0
        for r in rows:
            v, n = r.get(field), r["n_trades"]
            if v is not None and n:
                num += v * n
                den += n
        return round(num / den, 2) if den else None

    flags: list[str] = []
    for r in active:
        if r["flag"]:
            flags.append(f"{r['name']}: {r['flag']}")
    severity = "warn" if (cfg.get("enabled") and flags) else "ok"
    total_trades = sum(r["n_trades"] for r in rows)
    return {"enabled": bool(cfg["enabled"]), "config": {k: cfg[k] for k in _DEFAULTS},
            "severity": severity, "n_bots_with_trades": len(active), "total_trades": total_trades,
            "avg_slippage_bps": _weighted("avg_slippage_bps"), "avg_fee_bps": _weighted("avg_fee_bps"),
            "avg_cost_bps": _weighted("avg_cost_bps"), "bots": rows, "flags": flags,
            "note": "Dry-Run: Slippage i. d. R. 0 (Fill == angefordert); Gebühren sind real. "
                    "Ab Echtgeld zeigt die Messung echte Slippage (M6)."}
