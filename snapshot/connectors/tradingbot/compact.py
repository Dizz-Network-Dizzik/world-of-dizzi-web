"""Kompakt-Mapper für Trading-Bot-API-Antworten.

Die rohen Endpoints liefern 6–14 KB JSON — zu viel für den Modell-Kontext.
Diese Mapper reduzieren auf das, was eine beratende KI wirklich braucht.
Wird vom MCP-Server (Subprozess) UND vom L4-Beobachter im Core genutzt.
"""

from __future__ import annotations

from typing import Any


def _r(v: Any, nd: int = 3) -> Any:
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def compact_fleet(s: dict) -> dict:
    closed = s.get("trades_closed") or 0
    return {
        "bots": s.get("bots"), "laufend": s.get("running"),
        "offene_trades": s.get("trades_open"), "geschlossene_trades": closed,
        "trefferquote_pct": _r((s.get("wins") or 0) / closed * 100, 1) if closed else 0,
        "gewinn_usdt": _r(s.get("profit_abs"), 2), "roi_pct": _r(s.get("profit_pct"), 2),
        "kategorien": {
            k: {"bots": g.get("bots"), "roi_pct": _r(g.get("profit_pct"), 2)}
            for k, g in (s.get("groups") or {}).items()
        },
    }


def compact_master(m: dict) -> dict:
    policy = m.get("policy") or {}
    fitness = m.get("fitness_history") or []
    evidence = m.get("evidence") or {}
    return {
        "aktives_regime": policy.get("active_regime"),
        "mn_sockel_anteil": _r(policy.get("mn_share")),
        "gewichte": {k: _r(v) for k, v in (policy.get("weights") or {}).items()},
        "fitness_aktuell": _r(fitness[-1].get("fitness")) if fitness and isinstance(fitness[-1], dict) else None,
        "fitness_punkte": len(fitness),
        "evidenz_zusammenfassung": {k: evidence[k] for k in list(evidence)[:6]}
        if isinstance(evidence, dict) else None,
    }


def compact_governor(g: dict) -> dict:
    report = g.get("last_report") or {}
    history = g.get("history") or []
    return {
        "konfig": {k: _r(v) for k, v in (g.get("config") or {}).items() if not isinstance(v, (dict, list))},
        "letzter_report": {k: _r(v) for k, v in report.items() if not isinstance(v, (dict, list))},
        "letzte_aktion_ts": g.get("last_action_ts"),
        "aktionen_gesamt": len(history),
        "letzte_aktionen": history[-3:] if isinstance(history, list) else [],
    }


def compact_mastermeta(mm: dict) -> dict:
    bot = mm.get("bot") or {}
    autopilot = mm.get("autopilot") or {}
    return {
        "regime": mm.get("current_regime"),
        "regime_konfidenz": _r(mm.get("regime_confidence")),
        "hebel": mm.get("leverage"),
        "event_risiko": mm.get("event_risk"),
        "bot_laeuft": bot.get("running"),
        "autopilot": {k: autopilot[k] for k in list(autopilot)[:6]} if isinstance(autopilot, dict) else autopilot,
    }


def compact_concentration(c: dict) -> dict:
    return {k: _r(v) for k, v in c.items() if not isinstance(v, (dict, list))} | {
        k: v for k, v in c.items() if isinstance(v, list) and len(str(v)) < 400
    }


def compact_alerts(a: Any) -> Any:
    if isinstance(a, list):
        return a[:10]
    if isinstance(a, dict):
        return {k: (v[:10] if isinstance(v, list) else v) for k, v in a.items()}
    return a
