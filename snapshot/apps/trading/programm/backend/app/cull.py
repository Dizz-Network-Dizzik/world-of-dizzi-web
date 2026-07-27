"""cull.py — automatisches Aussortieren chronisch schlechter DEMO-Bots (Selbst-Bewertung).

Idee (Nutzer-Wunsch): Jeder Bot bewertet in Korrespondenz mit der Lern-Schicht seinen eigenen Track —
„lohnt es sich, an dieser Strategie dranzubleiben?". Bots/Strategien, die **kritisch und nachhaltig**
schlecht laufen, werden im Demo-Betrieb **automatisch verworfen**. Bewusst KONSERVATIV: es braucht genug
Historie UND genug Trades UND einen klar negativen Schnitt UND einen weiter fallenden Trend — alle
Bedingungen zusammen. So trifft es nur echte Dauer-Verlierer, nie frische oder nur kurz schwache Bots.

GARANTIE: Cull löscht nur die Bot-Registrierung (über ``registry.delete_bot``) — die **Lern-DB
(stats.sqlite) und die Trade-Historie bleiben erhalten**. Das gesammelte Wissen geht nie verloren.
Ausgenommen: der MasterMeta-Singleton und alle Echtgeld-Bots (nur ``dry_run`` wird gecullt).
"""
from __future__ import annotations

import time

from . import audit, jsonstore, meta, registry, runner, stats
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "cull.json"

# Konservative Default-Schwellen (tunbar via set_config / API).
_DEFAULTS = {
    "enabled": True,
    "min_days": 5,            # Mindest-Historie (Tages-Snapshots) bevor überhaupt gecullt wird
    "min_trades": 20,         # Mindest-Zahl geschlossener Trades (statistische Aussagekraft)
    "max_avg_loss_pct": -15.0,  # Ø-Profit muss SCHLECHTER (≤) als dies sein → kritisch
    "max_trend_pct": -1.0,    # Equity-Trend muss weiter fallen (≤ %/Tag) → keine Erholung
    "min_interval_h": 12.0,   # Cull-Durchlauf höchstens alle N h (Debounce)
}
_MAX_HISTORY = 40


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("min_days", "min_trades", "max_avg_loss_pct", "max_trend_pct", "min_interval_h"):
        if k in patch:
            try:
                s[k] = type(_DEFAULTS[k])(patch[k])
            except (TypeError, ValueError):
                pass
    if "enabled" in patch:
        s["enabled"] = bool(patch["enabled"])
    jsonstore.write_atomic(STATE_FILE, s)
    audit.record("cull_config", **{k: s[k] for k in _DEFAULTS})
    return s


def _verdict_for(bot, cfg: dict) -> dict:
    """Selbst-Bewertung EINES Bots: keep | cull (+ Begründung + Kennzahlen). Reine Lese-Analyse."""
    cons = meta.consistency(bot.id)
    wallet = float(getattr(bot, "dry_run_wallet", 0.0) or 0.0)
    pnl = stats.bot_pnl(bot.id, wallet)
    days = cons.get("days_tracked", 0)
    avg = cons.get("avg_profit_pct")
    trend = cons.get("trend_slope_pct")
    closed = int(pnl.get("closed") or 0)
    metrics = {"days_tracked": days, "avg_profit_pct": avg, "trend_slope_pct": trend,
               "closed_trades": closed, "live_profit_pct": pnl.get("profit_pct")}

    protected = bot.id == registry.MASTER_BOT_ID
    if protected:
        return {"bot_id": bot.id, "name": bot.name, "strategy": bot.strategy,
                "verdict": "keep", "reason": "geschützt (MasterMeta-Singleton)", "metrics": metrics}
    if not bot.dry_run:
        return {"bot_id": bot.id, "name": bot.name, "strategy": bot.strategy,
                "verdict": "keep", "reason": "Echtgeld-Bot — Cull nur im Demo", "metrics": metrics}

    # ALLE Bedingungen müssen zutreffen (konservativ) — sonst behalten.
    enough_hist = days >= cfg["min_days"]
    enough_trades = closed >= cfg["min_trades"]
    clearly_bad = avg is not None and avg <= cfg["max_avg_loss_pct"]
    deteriorating = trend is not None and trend <= cfg["max_trend_pct"]
    cull = enough_hist and enough_trades and clearly_bad and deteriorating
    if cull:
        reason = (f"Selbst-Bewertung kritisch: Ø {avg}% über {days} Tage, Trend {trend:+}%/Tag, "
                  f"{closed} Trades → Strategie nicht tragbar, wird verworfen (Learnings bleiben).")
    elif not enough_hist:
        reason = f"behalten: zu junge Historie ({days}/{cfg['min_days']} Tage)"
    elif not enough_trades:
        reason = f"behalten: zu wenige Trades ({closed}/{cfg['min_trades']})"
    elif not clearly_bad:
        reason = f"behalten: Ø {avg}% nicht kritisch (Schwelle {cfg['max_avg_loss_pct']}%)"
    elif not deteriorating:
        reason = f"behalten: Trend nicht fallend ({trend}%/Tag)"
    else:
        reason = "behalten"
    return {"bot_id": bot.id, "name": bot.name, "strategy": bot.strategy,
            "verdict": "cull" if cull else "keep", "reason": reason, "metrics": metrics}


def evaluate() -> list[dict]:
    """Verdikte für ALLE Bots (read-only, ohne zu handeln) — für UI/Vorschau."""
    cfg = get_config()
    return [_verdict_for(b, cfg) for b in registry.list_bots()]


def run_once(reason: str = "schedule", force: bool = False) -> dict:
    """Führt einen Cull-Durchlauf aus: bewertet alle Bots, verwirft die kritisch schlechten Demo-Bots
    (stop + delete; Learnings bleiben). Debounced (min_interval_h), exception-fest pro Bot."""
    cfg = get_config()
    state = jsonstore.read_json(STATE_FILE, {}) or {}
    now = time.time()
    if not force:
        if not cfg.get("enabled"):
            return {"ok": True, "skipped": "deaktiviert"}
        last = state.get("last_run_ts") or 0
        if (now - last) < cfg["min_interval_h"] * 3600.0:
            return {"ok": True, "skipped": "debounce"}
    verdicts = [_verdict_for(b, cfg) for b in registry.list_bots()]
    culled = []
    for v in verdicts:
        if v["verdict"] != "cull":
            continue
        try:
            runner.stop(v["bot_id"])
            if registry.delete_bot(v["bot_id"]):
                culled.append({"bot_id": v["bot_id"], "name": v["name"],
                               "strategy": v["strategy"], "metrics": v["metrics"]})
                audit.record("bot_culled", bot_id=v["bot_id"], name=v["name"],
                             strategy=v["strategy"], reason=v["reason"])
        except Exception as exc:  # ein Fehler darf den Lauf nie abbrechen
            audit.record("cull_error", bot_id=v["bot_id"], error=f"{type(exc).__name__}: {exc}")
    report = {"ts": now, "reason": reason, "checked": len(verdicts),
              "culled": culled, "culled_count": len(culled)}
    state["last_run_ts"] = now
    state["last_report"] = report
    hist = (state.get("history") or [])
    hist.append(report)
    state["history"] = hist[-_MAX_HISTORY:]
    jsonstore.write_atomic(STATE_FILE, {**cfg, **state})
    return {"ok": True, **report}


def status() -> dict:
    """Cull-Status + aktuelle Verdikte (für die UI/Transparenz)."""
    cfg = get_config()
    state = jsonstore.read_json(STATE_FILE, {}) or {}
    return {"config": {k: cfg[k] for k in _DEFAULTS},
            "last_report": state.get("last_report"),
            "history": (state.get("history") or [])[-_MAX_HISTORY:][::-1],
            "verdicts": evaluate()}
