"""alerts.py — Proaktives Monitoring/Alerting (P5): Beobachtbarkeit als Kernfeature.

Statt nur ein passives Audit-Log zu führen, **verdichtet** dieser Aggregator die wichtigsten Signale des
Systems zu einer priorisierten Alert-Liste — damit Probleme auffallen, **bevor** sie wehtun:

- **Portfolio-Risiko** (P1): nahender/überschrittener Gesamt-Drawdown, Tagesverlust, Konzentrations-Klumpen
  (P2) und ungewöhnliches Bot-Verhalten (Anomalien) — direkt aus ``governor.evaluate``.
- **Ausführung** (P4): steigende Slippage / hohe Ausführungskosten — aus ``execution.analyze``.
- **Datenfeed-Gesundheit**: veralteter Markt-Snapshot-Feed, fehlende/veraltete Regime-Bridge.
- **Betrieb**: gestoppte Bots (laufen weniger als angelegt).

Jeder Alert hat eine Stufe (``critical`` / ``warn`` / ``info``), eine Kategorie, eine klare Meldung und
die Quelle. Read-only — der Aggregator handelt nicht; er macht sichtbar. Die eigentlichen Eingriffe macht
der Governor (P1). 0 Risiko."""
from __future__ import annotations

from datetime import datetime, timezone

from . import execution, governor, jsonstore, registry, runner, stats, tracker
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "alerts.json"

_DEFAULTS = {
    "enabled": True,
    "stale_market_min": 45.0,   # Markt-Snapshot älter als N Minuten → Feed gilt als veraltet
    "stale_regime_min": 180.0,  # Regime-Bridge älter als N Minuten → veraltet
}
_LEVEL_RANK = {"critical": 0, "warn": 1, "info": 2}


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("stale_market_min", "stale_regime_min"):
        if k in patch:
            try:
                s[k] = float(patch[k])
            except (TypeError, ValueError):
                pass
    if "enabled" in patch:
        s["enabled"] = bool(patch["enabled"])
    jsonstore.write_atomic(STATE_FILE, s)
    return s


def _age_min(ts: str | None) -> float | None:
    """Alter eines ISO-Zeitstempels in Minuten (None bei fehlend/unparsebar)."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
    except (TypeError, ValueError):
        return None


def _alert(level: str, category: str, message: str, source: str) -> dict:
    return {"level": level, "category": category, "message": message, "source": source}


def data_feed_health(cfg: dict) -> list[dict]:
    """Datenfeed-Gesundheit: Frische des Markt-Snapshots + der Regime-Bridge."""
    out: list[dict] = []
    try:
        market = stats.get_market_snapshots(limit=1)
        age = _age_min(market[-1].get("ts")) if market else None
        if age is None:
            out.append(_alert("warn", "datenfeed", "Kein Markt-Snapshot vorhanden — Feed inaktiv?",
                              "tracker.market_snapshot"))
        elif age > cfg["stale_market_min"]:
            out.append(_alert("warn", "datenfeed",
                              f"Markt-Snapshot {age:.0f} min alt (> {cfg['stale_market_min']:.0f} min) "
                              f"— Datenfeed möglicherweise gestört.", "tracker.market_snapshot"))
    except Exception:
        pass
    try:
        reg = tracker.read_regime_bridge()
        if reg is None:
            out.append(_alert("info", "datenfeed",
                              "Regime-Bridge fehlt/veraltet — HMM-Regime aktuell ohne Live-Kopplung.",
                              "tracker.regime_bridge"))
    except Exception:
        pass
    return out


def operational_health(rows: list[dict] | None = None) -> list[dict]:
    """Betriebs-Gesundheit: gestoppte Bots (laufen weniger als angelegt).

    Nutzt bevorzugt die **bereits vom Governor berechneten** Bot-Zeilen (``rows`` mit ``name``/``running``)
    — vermeidet einen redundanten zweiten ``runner.status``-Durchlauf über alle Bots. Fällt nur ohne
    ``rows`` auf eine eigene Abfrage zurück."""
    out: list[dict] = []
    try:
        if rows is not None:
            total = len(rows)
            stopped_names = [r.get("name") or r.get("bot_id") for r in rows if not r.get("running")]
        else:
            bots = list(registry.list_bots())
            total = len(bots)
            stopped_names = []
            for b in bots:
                try:
                    if not runner.status(b.id).get("running"):
                        stopped_names.append(getattr(b, "name", b.id))
                except Exception:
                    continue
        if stopped_names:
            names = ", ".join(stopped_names[:6])
            more = f" (+{len(stopped_names) - 6})" if len(stopped_names) > 6 else ""
            out.append(_alert("warn", "betrieb",
                              f"{len(stopped_names)} von {total} Bots gestoppt: {names}{more}",
                              "runner"))
    except Exception:
        pass
    # Zombie-Erkennung: Bot läuft prozessual, aber der freqtrade-Heartbeat ist eingefroren
    # (hängt nach Exchange-/Netz-Stall) → würde sonst weiter als „läuft" gelten, bis jemand neu startet.
    # Kontinuierlich gemeldet (schließt die Lücke „Warnung kam erst beim Neustart"). Eigener Scan
    # (runner.status cached) — die Governor-rows tragen die Gesundheit nicht.
    try:
        stale = []
        for b in list(registry.list_bots()):
            try:
                st = runner.status(b.id)
                if st.get("health") == "stale":
                    mins = (st.get("log_age_s") or 0) / 60.0
                    stale.append((getattr(b, "name", b.id), mins))
            except Exception:
                continue
        if stale:
            stale.sort(key=lambda x: -x[1])
            label = ", ".join(f"{n} ({m:.0f} min)" for n, m in stale[:6])
            more = f" (+{len(stale) - 6})" if len(stale) > 6 else ""
            out.append(_alert("bad", "betrieb",
                              f"{len(stale)} Bot(s) HÄNGEN (Prozess lebt, aber kein Heartbeat): "
                              f"{label}{more} — funktional tot, Neustart prüfen.",
                              "runner.health"))
    except Exception:
        pass
    return out


def collect() -> dict:
    """Sammelt alle aktiven Alerts (read-only), priorisiert nach Stufe. Liefert Liste + Zählung + Status."""
    cfg = get_config()
    alerts: list[dict] = []
    if not cfg.get("enabled"):
        return {"enabled": False, "alerts": [], "counts": {"critical": 0, "warn": 0, "info": 0},
                "status": "ok", "config": {k: cfg[k] for k in _DEFAULTS}}

    # 1) Portfolio-Risiko (Governor: Drawdown/Tagesverlust/Konzentration/Anomalien).
    gov_rows = None
    try:
        gov = governor.evaluate(use_cache=True)
        gov_rows = gov.get("bots")
        for r in gov.get("breach_reasons", []):
            alerts.append(_alert("critical", "portfolio", r, "governor"))
        for r in gov.get("warn_reasons", []):
            alerts.append(_alert("warn", "portfolio", r, "governor"))
        for a in gov.get("anomalies", []):
            alerts.append(_alert("warn", "anomalie",
                                 f"{a['name']}: ungewöhnlich (Profit {a['profit_pct']}%, Z {a['robust_z']})",
                                 "governor"))
    except Exception:
        pass

    # 2) Ausführungsqualität (Slippage/Kosten).
    try:
        ex = execution.analyze(use_cache=True)
        for f in ex.get("flags", []):
            alerts.append(_alert("warn", "ausführung", f, "execution"))
    except Exception:
        pass

    # 3) Datenfeed- + 4) Betriebs-Gesundheit (Betrieb nutzt die schon berechneten Governor-Bot-Zeilen).
    alerts.extend(data_feed_health(cfg))
    alerts.extend(operational_health(gov_rows))

    alerts.sort(key=lambda a: _LEVEL_RANK.get(a["level"], 9))
    counts = {lv: sum(1 for a in alerts if a["level"] == lv) for lv in ("critical", "warn", "info")}
    status = "critical" if counts["critical"] else ("warn" if counts["warn"] else "ok")
    return {"enabled": True, "alerts": alerts, "counts": counts, "status": status,
            "config": {k: cfg[k] for k in _DEFAULTS}}
