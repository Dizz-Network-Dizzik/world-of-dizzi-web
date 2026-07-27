"""governor.py — Portfolio-Risk-Governor: eine Schicht ÜBER allen Bots.

Einzelstrategie-Logik (jeder Bot, der Cull, die Lern-Loops) sieht immer nur den eigenen Track.
Der Governor schaut auf das **Gesamt-Portfolio**: aggregierter Drawdown, Tagesverlust über die ganze
Flotte und **ungewöhnliches Bot-Verhalten** (Ausreißer ggü. der Flotte). Bei Überschreitung harter
Grenzen greift er ein — **Alert**, **De-Risk** (die schlechtesten Demo-Bots pausieren) oder **Pause**
(alle Demo-Bots stoppen). Das ist der „Copilot auf Portfolio-Ebene", den die Einzel-Logik nicht hat.

Bewusst KONSERVATIV und transparent:
- Es wird zwischen **warn** (nur Alert) und **breach** (Eingriff) getrennt — zwei Schwellen.
- Eingriffe sind **debounced** (``min_interval_h``) und **exception-fest pro Bot** (ein Fehler bricht
  den Lauf nie ab).
- Geschützt: der **MasterMeta-Singleton** (optional) und **alle Echtgeld-Bots** — der Governor pausiert
  ausschließlich ``dry_run``-Bots. Keine Registrierung/Lern-DB wird je angefasst (nur ``runner.stop``).

GARANTIE: 0 Risiko. Reiner Demo/Paper-Betrieb; der Governor stoppt höchstens Bots, er löscht nie etwas.
Die Alerts (auch ohne Eingriff) landen im Audit-Log und speisen das proaktive Monitoring (P5).
"""
from __future__ import annotations

import time

from . import audit, cache, concentration, jsonstore, registry, runner, stats
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "governor.json"
_EVAL_TTL = 3.0  # s — kollabiert die Mehrfach-Aufrufe eines UI-Refresh auf eine Berechnung (read-only)

# Konservative Default-Schwellen (tunbar via set_config / API).
_DEFAULTS = {
    "enabled": True,
    # Gesamt-Drawdown der Portfolio-Equity-Kurve (vom Hoch). warn < breach.
    "warn_drawdown_pct": 10.0,    # ab hier nur Alert (Frühwarnung)
    "max_drawdown_pct": 18.0,     # ab hier Eingriff (De-Risk/Pause)
    # Aggregierter realisierter Tagesverlust über die ganze Flotte (% des Gesamt-Wallets).
    "max_daily_loss_pct": 8.0,    # ab hier Eingriff
    # Reaktion bei breach: "alert" (nur melden) | "derisk" (schlechteste N stoppen) | "pause" (alle stoppen).
    "action": "derisk",
    "derisk_count": 3,            # bei "derisk": so viele der schlechtesten laufenden Demo-Bots pausieren
    # Anomalie ("ungewöhnliches Bot-Verhalten"): robuster Z-Score des Live-Profits ggü. der Flotte.
    "anomaly_z": 3.5,             # |robust-z| ab dem ein Bot als Ausreißer gilt
    "anomaly_floor_pct": -10.0,   # zusätzlich muss der Profit absolut darunter liegen (kein Fehlalarm)
    "min_interval_h": 1.0,        # Eingriffe höchstens alle N h (Debounce)
    "protect_master": True,       # MasterMeta-Singleton nie automatisch pausieren
}
_MAX_HISTORY = 40


def get_config() -> dict:
    return {**_DEFAULTS, **(jsonstore.read_json(STATE_FILE, {}) or {})}


def set_config(patch: dict) -> dict:
    s = get_config()
    for k in ("warn_drawdown_pct", "max_drawdown_pct", "max_daily_loss_pct",
              "derisk_count", "anomaly_z", "anomaly_floor_pct", "min_interval_h"):
        if k in patch:
            try:
                s[k] = type(_DEFAULTS[k])(patch[k])
            except (TypeError, ValueError):
                pass
    if "action" in patch and patch["action"] in ("alert", "derisk", "pause"):
        s["action"] = patch["action"]
    for k in ("enabled", "protect_master"):
        if k in patch:
            s[k] = bool(patch[k])
    # warn darf nie über breach liegen (sonst nie Frühwarnung) — sanft korrigieren.
    if s["warn_drawdown_pct"] > s["max_drawdown_pct"]:
        s["warn_drawdown_pct"] = s["max_drawdown_pct"]
    jsonstore.write_atomic(STATE_FILE, s)
    audit.record("governor_config", **{k: s[k] for k in _DEFAULTS})
    return s


# ------------------------------------------------------------------ Kennzahlen (read-only)
def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def portfolio_drawdown() -> dict:
    """Aggregierter Drawdown der **Portfolio-Equity** aus den Tages-Snapshots aller Bots.

    Für jeden Tag wird die Equity aller Bots summiert → eine Portfolio-Equity-Reihe;
    Drawdown = (Hoch − aktuell) / Hoch · 100.

    WICHTIG (Robustheit): die Equity jedes Bots wird über die Tagesachse **forward-gefüllt** (letzter
    bekannter Wert). Sonst würde ein einzelner fehlender Bot-Tag (transienter Snapshot-Fehler) die
    Tagessumme künstlich einbrechen lassen → falscher Drawdown → falscher Eingriff. Bots, die an einem
    Tag noch nicht existierten (vor ihrem ersten Snapshot), tragen 0 bei (die Kurve wächst, wenn Bots
    dazukommen — das verursacht **keinen** falschen Drawdown, nur konservativ untertriebenen)."""
    per_bot: dict[str, dict[str, float]] = {}
    all_days: set[str] = set()
    for b in registry.list_bots():
        try:
            day_eq: dict[str, float] = {}
            for snap in stats.get_snapshots(b.id, limit=365):
                eq, day = snap.get("equity"), snap.get("day")
                if eq is None or not day:
                    continue
                day_eq[day] = float(eq)
            if day_eq:
                per_bot[b.id] = day_eq
                all_days.update(day_eq)
        except Exception:
            continue
    if not all_days:
        return {"drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
                "peak_equity": 0.0, "current_equity": 0.0, "days": 0}
    days = sorted(all_days)
    series = [0.0] * len(days)
    for day_eq in per_bot.values():
        bot_days = sorted(day_eq)            # chronologisch
        j, last = 0, None                    # Pointer-Walk: ein Durchlauf über die globale Tagesachse
        for i, d in enumerate(days):
            while j < len(bot_days) and bot_days[j] <= d:
                last = day_eq[bot_days[j]]    # forward-fill: jüngster Wert ≤ d
                j += 1
            if last is not None:             # vor dem ersten Snapshot trägt der Bot 0 bei
                series[i] += last
    peak = 0.0
    max_dd = 0.0
    for eq in series:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak * 100.0)
    current = series[-1]
    cur_dd = ((peak - current) / peak * 100.0) if peak > 0 else 0.0
    return {"drawdown_pct": round(cur_dd, 2), "max_drawdown_pct": round(max_dd, 2),
            "peak_equity": round(peak, 2), "current_equity": round(current, 2),
            "days": len(series)}


def _bot_live_profit(bot) -> tuple[float | None, int, float]:
    """(profit_pct, closed_trades, profit_abs) eines Bots aus der Trade-DB (Demo-Wallet-relativ)."""
    wallet = float(getattr(bot, "dry_run_wallet", 0.0) or 0.0)
    pnl = stats.bot_pnl(bot.id, wallet, since_days=1)
    return pnl.get("profit_pct"), int(pnl.get("closed") or 0), float(pnl.get("profit_abs") or 0.0)


def evaluate(use_cache: bool = False) -> dict:
    """Portfolio-Gesundheit (read-only, ohne zu handeln) — für UI/Vorschau und den Eingriffs-Entscheid.

    Liefert: aggregierten Drawdown, aggregierten Tagesverlust, je-Bot-Live-Profit + Anomalie-Flags
    (robuster Z-Score ggü. der Flotte) und die abgeleitete Schwere (``ok``/``warn``/``breach``).

    ``use_cache``: für UI/Status-Pfade kurz memoisieren (``_EVAL_TTL``) — der eingreifende ``run_once``
    ruft IMMER frisch (Default False) und invalidiert danach."""
    if use_cache:
        return cache.ttl_get("governor.evaluate", _EVAL_TTL, lambda: evaluate(use_cache=False))
    cfg = get_config()
    bots = list(registry.list_bots())

    dd = portfolio_drawdown()
    drawdown_pct = float(dd.get("drawdown_pct") or 0.0)

    # Aggregierter realisierter Tagesverlust (heute) über die Flotte.
    total_wallet = 0.0
    total_today_abs = 0.0
    rows: list[dict] = []
    profits: list[float] = []
    for b in bots:
        try:
            running = bool(runner.status(b.id).get("running"))
        except Exception:
            running = False
        profit_pct, closed, profit_abs = _bot_live_profit(b)
        wallet = float(getattr(b, "dry_run_wallet", 0.0) or 0.0)
        total_wallet += wallet
        total_today_abs += profit_abs
        if profit_pct is not None:
            profits.append(profit_pct)
        rows.append({"bot_id": b.id, "tag": getattr(b, "tag", None), "name": b.name,
                     "strategy": b.strategy, "dry_run": bool(getattr(b, "dry_run", True)),
                     "running": running, "profit_pct": profit_pct, "profit_abs": profit_abs,
                     "closed_trades": closed, "anomaly": False, "robust_z": None})

    daily_loss_pct = round(-total_today_abs / total_wallet * 100.0, 2) if total_wallet else 0.0

    # Anomalie-Erkennung: robuster Z-Score (Median + MAD) des Live-Profits über die Flotte.
    med = _median(profits) if profits else 0.0
    mad = _median([abs(p - med) for p in profits]) if profits else 0.0
    anomalies: list[dict] = []
    for r in rows:
        p = r["profit_pct"]
        if p is None or mad <= 0:
            continue
        z = 0.6745 * (p - med) / mad
        r["robust_z"] = round(z, 2)
        if z <= -float(cfg["anomaly_z"]) and p <= float(cfg["anomaly_floor_pct"]):
            r["anomaly"] = True
            anomalies.append({"bot_id": r["bot_id"], "name": r["name"], "profit_pct": p,
                              "robust_z": r["robust_z"]})

    # Schwere bestimmen.
    breach_reasons: list[str] = []
    if drawdown_pct >= cfg["max_drawdown_pct"]:
        breach_reasons.append(
            f"Portfolio-Drawdown {drawdown_pct:.1f}% ≥ Limit {cfg['max_drawdown_pct']:.1f}%")
    if daily_loss_pct >= cfg["max_daily_loss_pct"]:
        breach_reasons.append(
            f"Tagesverlust {daily_loss_pct:.1f}% ≥ Limit {cfg['max_daily_loss_pct']:.1f}%")
    warn_reasons: list[str] = []
    if drawdown_pct >= cfg["warn_drawdown_pct"] and drawdown_pct < cfg["max_drawdown_pct"]:
        warn_reasons.append(
            f"Portfolio-Drawdown {drawdown_pct:.1f}% ≥ Frühwarnung {cfg['warn_drawdown_pct']:.1f}%")

    # Korrelations-/Konzentrations-Klumpen (P2) als zusätzliches Frühwarn-Signal einziehen.
    # Strukturelles Risiko → Warnung + Streuungs-Hinweis, KEIN automatisches Pausieren von Bots.
    try:
        conc = concentration.analyze()
    except Exception:
        conc = {"severity": "ok", "flags": []}
    if conc.get("severity") == "warn":
        for f in conc.get("flags", []):
            warn_reasons.append(f"Konzentration: {f}")

    severity = "breach" if breach_reasons else ("warn" if warn_reasons else "ok")
    return {
        "severity": severity,
        "drawdown_pct": drawdown_pct,
        "max_drawdown_pct_seen": dd.get("max_drawdown_pct"),
        "daily_loss_pct": daily_loss_pct,
        "peak_equity": dd.get("peak_equity"),
        "current_equity": dd.get("current_equity"),
        "days_tracked": dd.get("days"),
        "total_wallet": round(total_wallet, 2),
        "breach_reasons": breach_reasons,
        "warn_reasons": warn_reasons,
        "anomalies": anomalies,
        "concentration": {"severity": conc.get("severity"), "hhi": conc.get("hhi"),
                          "top_asset": conc.get("top_asset"), "clusters": conc.get("clusters"),
                          "flags": conc.get("flags"), "suggestions": conc.get("suggestions")},
        "bots": rows,
        "config": {k: cfg[k] for k in _DEFAULTS},
    }


# ------------------------------------------------------------------ Eingriff
def _derisk_targets(report: dict, cfg: dict) -> list[dict]:
    """Wählt die Bots, die bei De-Risk pausiert werden: alle Anomalie-Bots zuerst, dann die
    schlechtesten laufenden Demo-Bots, bis ``derisk_count`` erreicht ist. Geschützte raus."""
    master_id = registry.MASTER_BOT_ID
    protect_master = bool(cfg.get("protect_master", True))

    def _selectable(r: dict) -> bool:
        if not r.get("running") or not r.get("dry_run"):
            return False
        if protect_master and r.get("bot_id") == master_id:
            return False
        return True

    selectable = [r for r in report["bots"] if _selectable(r)]
    anomaly_ids = {a["bot_id"] for a in report.get("anomalies", [])}
    targets: list[dict] = [r for r in selectable if r["bot_id"] in anomaly_ids]
    # Rest nach Live-Profit aufsteigend (schlechteste zuerst); None ans Ende.
    rest = sorted((r for r in selectable if r["bot_id"] not in anomaly_ids),
                  key=lambda r: (r["profit_pct"] is None, r["profit_pct"] if r["profit_pct"] is not None else 0.0))
    for r in rest:
        if len(targets) >= int(cfg.get("derisk_count", 3)):
            break
        targets.append(r)
    return targets


def run_once(reason: str = "schedule", force: bool = False) -> dict:
    """Bewertet das Portfolio und greift bei breach gemäß ``action`` ein (debounced, exception-fest).

    - ``alert``  → nur Alert ins Audit-Log (kein Stopp).
    - ``derisk`` → die schlechtesten/auffälligsten laufenden Demo-Bots pausieren (``derisk_count``).
    - ``pause``  → alle laufenden Demo-Bots pausieren (geschützte ausgenommen).
    Warnungen/Anomalien werden IMMER als Alert protokolliert (auch ohne Eingriff) → speist Monitoring."""
    cfg = get_config()
    state = jsonstore.read_json(STATE_FILE, {}) or {}
    now = time.time()
    report = evaluate()
    severity = report["severity"]

    # Alerts immer protokollieren (Frühwarnung + Anomalien), auch wenn (noch) nicht eingegriffen wird.
    for a in report.get("anomalies", []):
        audit.record("governor_anomaly", bot_id=a["bot_id"], name=a["name"],
                     profit_pct=a["profit_pct"], robust_z=a["robust_z"])
    if severity == "warn":
        audit.record("governor_warn", reasons=report["warn_reasons"],
                     drawdown_pct=report["drawdown_pct"], daily_loss_pct=report["daily_loss_pct"])

    acted = False
    paused: list[dict] = []
    skipped = None
    if severity == "breach":
        audit.record("governor_breach", reasons=report["breach_reasons"],
                     drawdown_pct=report["drawdown_pct"], daily_loss_pct=report["daily_loss_pct"],
                     action=cfg["action"])
        if not cfg.get("enabled") and not force:
            skipped = "deaktiviert"
        else:
            last = state.get("last_action_ts") or 0
            if not force and (now - last) < cfg["min_interval_h"] * 3600.0:
                skipped = "debounce"
            elif cfg["action"] == "alert":
                skipped = "action=alert (nur Frühwarnung, kein Eingriff)"
            else:
                if cfg["action"] == "pause":
                    master_id = registry.MASTER_BOT_ID
                    protect_master = bool(cfg.get("protect_master", True))
                    targets = [r for r in report["bots"] if r.get("running") and r.get("dry_run")
                               and not (protect_master and r["bot_id"] == master_id)]
                else:  # derisk
                    targets = _derisk_targets(report, cfg)
                for r in targets:
                    try:
                        runner.stop(r["bot_id"])
                        paused.append({"bot_id": r["bot_id"], "name": r["name"],
                                       "profit_pct": r["profit_pct"], "anomaly": r["anomaly"]})
                        audit.record("governor_paused_bot", bot_id=r["bot_id"], name=r["name"],
                                     action=cfg["action"], profit_pct=r["profit_pct"], reason=reason)
                    except Exception as exc:  # ein Fehler darf den Lauf nie abbrechen
                        audit.record("governor_pause_error", bot_id=r["bot_id"],
                                     error=f"{type(exc).__name__}: {exc}")
                acted = True
                state["last_action_ts"] = now
                cache.invalidate("governor.evaluate")  # nach Pausieren: nächster Read sieht die neue Lage

    out = {"ts": now, "reason": reason, "severity": severity, "acted": acted,
           "action": cfg["action"], "paused": paused, "paused_count": len(paused),
           "skipped": skipped, "drawdown_pct": report["drawdown_pct"],
           "daily_loss_pct": report["daily_loss_pct"], "breach_reasons": report["breach_reasons"],
           "warn_reasons": report["warn_reasons"], "anomaly_count": len(report.get("anomalies", []))}
    state["last_run_ts"] = now
    state["last_report"] = out
    hist = (state.get("history") or [])
    if severity != "ok" or acted:  # nur „interessante" Läufe in die Historie (kein Rauschen)
        hist.append(out)
    state["history"] = hist[-_MAX_HISTORY:]
    jsonstore.write_atomic(STATE_FILE, {**cfg, **state})
    return {"ok": True, **out}


def status() -> dict:
    """Governor-Status + aktuelle Portfolio-Bewertung (für UI/Transparenz)."""
    cfg = get_config()
    state = jsonstore.read_json(STATE_FILE, {}) or {}
    return {"config": {k: cfg[k] for k in _DEFAULTS},
            "last_report": state.get("last_report"),
            "last_action_ts": state.get("last_action_ts"),
            "history": (state.get("history") or [])[-_MAX_HISTORY:][::-1],
            "evaluation": evaluate(use_cache=True)}
