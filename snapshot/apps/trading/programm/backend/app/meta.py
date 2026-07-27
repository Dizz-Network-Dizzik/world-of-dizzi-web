"""Meta / Lern-Bot (Nordstern, Stufe 1) — daten-getriebene Auswertung.

Liest die schlanke Lern-Datenbasis (``stats.snapshots`` + Backtest-Läufe +
Trade-DBs) und liefert:
- **Aggregation je Strategie** (Ø Profit/Drawdown/Winrate, #Bots, Datenpunkte),
- **Daten-Reife** (wie viel Historie liegt vor),
- **Vorschläge** (regelbasiert, **proposal-only** — kein Auto-Apply).

Bewusst Stufe 1: solange wenig Historie vorliegt, sind die Aussagen heuristisch.
Mit wachsenden Snapshots wird hier später ein **Walk-Forward-validierter**
Lern-/Optimierungs-Loop andocken (Parameter-Mutationen vorschlagen → out-of-sample
testen → Gewinner behalten). Echtgeld nur per ausdrücklicher Freigabe.
"""

from __future__ import annotations

import bisect
import random
from datetime import datetime, timedelta, timezone

from . import sessions, stats
from .registry import list_bots


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def _stdev(xs: list[float]) -> float | None:
    """Stichproben-Standardabweichung (n-1); None bei < 2 Werten."""
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def _slope_per_step(ys: list[float]) -> float | None:
    """Least-squares-Steigung von ``ys`` über den Index (x = 0..n-1); None bei < 2 Werten."""
    n = len(ys)
    if n < 2:
        return None
    mx = (n - 1) / 2.0
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in range(n))
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(range(n), ys)) / denom


def aggregate() -> dict:
    """Aggregiert die letzten Kennzahlen je Strategie über alle Bots."""
    bots = list_bots()
    by_strat: dict[str, dict] = {}
    total_snaps = 0
    for b in bots:
        snaps = stats.get_snapshots(b.id, limit=365)
        total_snaps += len(snaps)
        latest = stats.get_latest(b.id) or {}
        tr = stats.recent_trades(b.id, limit=1)
        d = by_strat.setdefault(b.strategy, {
            "strategy": b.strategy, "trading_mode": getattr(b, "trading_mode", "spot"),
            "bots": 0, "snapshots": 0, "trades_closed": 0,
            "profits": [], "drawdowns": [], "winrates": [], "live_profits": [],
        })
        d["bots"] += 1
        d["snapshots"] += len(snaps)
        d["trades_closed"] += tr.get("closed", 0)
        # Live-Profit aus dem juengsten Tages-Snapshot (echte Demo-Performance, nicht Backtest).
        if snaps and snaps[-1].get("profit_pct") is not None:
            d["live_profits"].append(snaps[-1]["profit_pct"])
        if latest.get("profit_total_pct") is not None:
            d["profits"].append(latest["profit_total_pct"])
        if latest.get("max_drawdown_pct") is not None:
            d["drawdowns"].append(latest["max_drawdown_pct"])
        if latest.get("winrate_pct") is not None:
            d["winrates"].append(latest["winrate_pct"])
    rows = [{
        "strategy": d["strategy"], "trading_mode": d["trading_mode"], "bots": d["bots"],
        "snapshots": d["snapshots"], "trades_closed": d["trades_closed"],
        "avg_profit_pct": _avg(d["profits"]), "avg_drawdown_pct": _avg(d["drawdowns"]),
        "avg_winrate_pct": _avg(d["winrates"]),
        "avg_live_profit_pct": _avg(d["live_profits"]),
    } for d in by_strat.values()]
    rows.sort(key=lambda r: (r["avg_profit_pct"] if r["avg_profit_pct"] is not None else -1e9), reverse=True)
    return {"strategies": rows, "total_snapshots": total_snaps, "bots": len(bots)}


def proposals(agg: dict | None = None) -> list[dict]:
    """Regelbasierte Vorschläge (proposal-only). Werden NIE automatisch angewandt."""
    out: list[dict] = []
    agg = agg or aggregate()
    for b in list_bots():
        latest = stats.get_latest(b.id)
        if not latest:
            continue
        dd = latest.get("max_drawdown_pct") or 0.0
        pf = latest.get("profit_factor")
        wr = latest.get("winrate_pct") or 0.0
        if dd >= b.risk.max_drawdown_pct * 0.75:
            out.append({"bot": b.name, "type": "Risiko",
                        "text": f"Drawdown {dd:.1f}% nähert sich Limit ({b.risk.max_drawdown_pct:.0f}%) → Positionsgröße/Stop senken."})
        if pf is not None and pf < 1.0:
            out.append({"bot": b.name, "type": "Strategie",
                        "text": f"Profit-Faktor {pf:.2f} < 1 → Exit/Filter überarbeiten oder pausieren."})
        if wr and wr < 40:
            out.append({"bot": b.name, "type": "Entry",
                        "text": f"Trefferquote {wr:.0f}% niedrig → Entry-Filter verschärfen."})
    ranked = [r for r in agg["strategies"] if r["avg_profit_pct"] is not None]
    if ranked:
        best = ranked[0]
        out.append({"bot": "—", "type": "Ranking",
                    "text": f"Beste Strategie bisher: {best['strategy']} (Ø {best['avg_profit_pct']}% BT). Kapital tendenziell dorthin — erst nach mehr Daten bestätigen."})
    if not out:
        out.append({"bot": "—", "type": "Info",
                    "text": "Noch keine belastbaren Auffälligkeiten — der Lern-Bot sammelt weiter Daten."})
    return out


def learning_status(agg: dict | None = None) -> dict:
    """Daten-Reife: wie viel Historie liegt vor (heuristische Prozent-Anzeige)."""
    agg = agg or aggregate()
    bots = agg["bots"] or 1
    target = bots * 30  # Ziel: ~30 Tages-Snapshots je Bot fuer erste Belastbarkeit
    ready = max(0, min(100, int(agg["total_snapshots"] / target * 100))) if target else 0
    return {"total_snapshots": agg["total_snapshots"], "bots": agg["bots"],
            "readiness_pct": ready,
            "note": "Sammelt täglich kompakte Snapshots. Mit mehr Historie werden Vorschläge belastbarer; "
                    "echtes (Walk-Forward-validiertes) Algorithmus-Lernen dockt hier an. Echtgeld nur per Freigabe."}


def optimize_proposals(strategy: str, params: list[dict]) -> dict:
    """Lern-Loop Stufe 2 (proposal-only): erzeugt ein Explorations-Raster aus
    Kandidaten-Parametersätzen je Strategie. **Kein** Auto-Backtest — das echte
    Schließen des Loops (Walk-Forward je Kandidat → Gewinner behalten) braucht
    zuvor parametrisierbare Engine-Vorlagen (Params aus Config). Bis dahin dienen
    die Kandidaten als Start-Raster fürs (manuell ausgelöste) Tuning.
    """
    def grid(which: str) -> dict:
        return {p["name"]: (p.get(which) if p.get(which) is not None else p.get("default")) for p in params}

    standard = {p["name"]: p.get("default") for p in params}
    candidates = [
        {"label": "konservativ (eng)", "rationale": "engere Spannen — weniger Risiko/Frequenz", "params": grid("min")},
        {"label": "Standard", "rationale": "recherchierte Defaults", "params": standard},
        {"label": "aggressiv (weit)", "rationale": "weitere Spannen — mehr Risiko/Frequenz", "params": grid("max")},
    ]
    return {
        "strategy": strategy, "candidates": candidates,
        "next_step": "Auto-Bewertung je Kandidat via Walk-Forward (run_walkforward) — sobald die "
                     "Engine-Vorlagen Parameter aus der Config lesen. Dann: Gewinner behalten (proposal-only).",
        "note": "Vorschläge — werden NICHT automatisch angewandt.",
    }


# Multi-Objective-Score fuer den Optimierungs-Loop: belohnt Profit, bestraft Drawdown UND
# Overtrading (vgl. Multi-Objective-Reward in Meta-RL). Ersetzt reines Roh-Profit-Ranking →
# robustere Gewinner (z. B. wird ein Overtrading-Verlierer wie MomentumMacd abgewertet).
OPT_DD_WEIGHT = 0.5          # Gewicht des |Drawdown|
OPT_OVERTRADE_REF = 400      # Trades ueber dieser Referenz gelten als Overtrading
OPT_OVERTRADE_WEIGHT = 0.01  # Strafe je Trade ueber der Referenz


def _opt_score(r: dict) -> float:
    """Komposit-Score eines Optimierungs-Kandidaten (hoeher = besser)."""
    p = r.get("profit_total_pct")
    if p is None or not r.get("ok"):
        return -1e9
    dd = abs(r.get("max_drawdown_pct") or 0.0)
    over = max(0, (r.get("total_trades") or 0) - OPT_OVERTRADE_REF) * OPT_OVERTRADE_WEIGHT
    return round(p - OPT_DD_WEIGHT * dd - over, 4)


def sample_params(specs: list[dict], n: int = 4) -> list[dict]:
    """``n`` zufällig im [min,max]-Raum gesampelte Kandidaten (uniform je Parameter, int-erhaltend).

    Hintergrund: Das 3-Ecken-Raster (alle Parameter gleichzeitig min/default/max) deckt nur die
    unwahrscheinlichsten Punkte des Suchraums ab. Random Search findet bei gleichem Budget bessere
    Konfigurationen als Raster-Suche — v. a. wenn nur wenige Parameter wirklich Einfluss haben
    (Bergstra & Bengio 2012, JMLR). Parameter ohne [min,max]-Spanne behalten ihren Default."""
    out: list[dict] = []
    for _ in range(max(0, int(n))):
        cand: dict = {}
        for p in (specs or []):
            name, default = p.get("name"), p.get("default")
            lo, hi = p.get("min"), p.get("max")
            if name is None:
                continue
            try:
                flo, fhi = float(lo), float(hi)
            except (TypeError, ValueError):
                cand[name] = default
                continue
            if fhi <= flo:
                cand[name] = default
                continue
            v = random.uniform(flo, fhi)
            cand[name] = int(round(v)) if isinstance(default, int) else round(v, 4)
        out.append(cand)
    return out


def _anchored_ranges(days: int, windows: int, embargo_days: int) -> dict:
    """Zeitfenster des **anchored Walk-Forward**: Training (ältere Daten) → Embargo → Test (jüngste).

    Die Kandidaten-Selektion sieht NUR das Trainings-Fenster; das Test-Fenster bleibt bis zum
    einmaligen Gewinner-Test ungesehen — so misst der Test echte Out-of-Sample-Leistung statt
    den Selektions-Bias eines best-of-N. ``windows`` steuert den Schnitt: Test ≈ days/windows
    (mind. 20 Tage), Training = Rest; ``embargo_days`` Lücke gegen fenster-übergreifende Trades."""
    now = datetime.now(timezone.utc)
    test_days = max(20, days // max(2, int(windows)))
    train_days = max(test_days, days - test_days)
    emb = max(0, int(embargo_days))
    test_start = now - timedelta(days=test_days)
    train_end = test_start - timedelta(days=emb)
    train_start = train_end - timedelta(days=train_days)

    def _fmt(a, b):
        return f"{a.strftime('%Y%m%d')}-{b.strftime('%Y%m%d')}"

    return {"train": _fmt(train_start, train_end), "test": _fmt(test_start, now),
            "train_days": train_days, "test_days": test_days, "embargo_days": emb,
            "total_days": train_days + emb + test_days}


def _oos_passed(m: dict | None) -> bool:
    """OOS-Test-Kriterium des Gewinners: handelt, Drawdown < 50 % UND Profit > 0."""
    if not m:
        return False
    return (int(m.get("total_trades") or 0) > 0
            and float(m.get("max_drawdown_pct") or 0) < 50.0
            and float(m.get("profit_total_pct") or 0) > 0.0)


def run_optimization(strategy: str, params: list[dict], days: int = 90, windows: int = 2,
                     timeframe: str | None = None, embargo_days: int = 1,
                     explore: int = 4) -> dict:
    """Schließt den Lern-Loop **anchored**: alle Kandidaten (3 Anker + ``explore`` Random-Search-
    Sample) werden auf dem TRAININGS-Fenster verglichen; nur der Gewinner wird EINMAL auf dem
    späteren, in der Selektion ungesehenen TEST-Fenster geprüft. ``confident`` = Test bestanden
    (= ``oos_validated`` des persistierten Gewinners). Vorher wurden alle Kandidaten auf denselben
    Fenstern selektiert UND „validiert" — der Gewinner war damit ein best-of-N auf den
    Validierungsdaten (Selektions-Bias). ``windows<=1`` = reiner In-Sample-Vergleich (nie
    confident, nur experimentell). Proposal-only; Auto-Anwendung gated auf ``oos_validated``."""
    from . import engine, stats

    grids = optimize_proposals(strategy, params)["candidates"]
    for i, cp in enumerate(sample_params(params, n=explore), start=1):
        grids.append({"label": f"exploriert #{i}", "rationale": "Random-Search im [min,max]-Raum",
                      "params": cp})
    anchored = bool(windows and windows > 1)
    rng = _anchored_ranges(days, windows, embargo_days) if anchored else None
    config = tf = None
    if anchored:
        config, tf = engine.ensure_data(strategy, timeframe, days=rng["total_days"] + 5)
    results = []
    for c in grids:
        if anchored:
            r = engine.run_backtest_range(strategy, c["params"], rng["train"],
                                          timeframe=tf, config=config)
        else:
            r = engine.run_backtest_with_params(strategy, c["params"], days=days)
        m = r.get("metrics") or {}
        results.append({
            "label": c["label"], "params": c["params"], "ok": bool(r.get("ok")),
            "profit_total_pct": m.get("profit_total_pct"), "max_drawdown_pct": m.get("max_drawdown_pct"),
            "total_trades": m.get("total_trades"), "winrate_pct": m.get("winrate_pct"),
        })
    for x in results:
        x["score"] = _opt_score(x)
    valid = [x for x in results if x["ok"] and (x["total_trades"] or 0) > 0]
    winner = None
    selection_bias = {
        "trials": len(results), "valid_trials": len(valid),
        "method": "anchored_walkforward" if anchored else "in_sample",
        "train_window": (rng or {}).get("train"), "test_window": (rng or {}).get("test"),
        "confident": False, "warning": None,
        "note": ("Anchored: Selektion (best-of-N) NUR auf dem Trainings-Fenster; 'confident' = der "
                 "Gewinner besteht das davon getrennte, jüngere Test-Fenster (Profit>0, DD<50%, "
                 "Trades>0). Das Test-Fenster bleibt frei von Selektions-Bias (Walk-Forward-Prinzip)."
                 if anchored else
                 "In-Sample-Vergleich (windows<=1): keine OOS-Bestätigung möglich → nie confident; "
                 "Auto-Anwendung bleibt gesperrt."),
    }
    if valid:
        # Trainings-Gewinner nach Multi-Objective-Score, Tie-break: geringerer Drawdown.
        winner = dict(sorted(
            valid,
            key=lambda x: (x["score"], -(x["max_drawdown_pct"] or 0.0)),
            reverse=True,
        )[0])
        winner["train_profit_total_pct"] = winner["profit_total_pct"]
        if anchored:
            t = engine.run_backtest_range(strategy, winner["params"], rng["test"],
                                          timeframe=tf, config=config)
            tm = (t.get("metrics") or {}) if t.get("ok") else {}
            oos_ok = bool(t.get("ok")) and _oos_passed(tm)
            # Nach außen zählen die ehrlichen OOS-Zahlen des Test-Fensters, nicht die Trainings-Werte.
            winner.update({
                "profit_total_pct": tm.get("profit_total_pct"),
                "max_drawdown_pct": tm.get("max_drawdown_pct"),
                "total_trades": tm.get("total_trades"), "winrate_pct": tm.get("winrate_pct"),
                "oos_validated": oos_ok, "oos_window": rng["test"],
            })
            selection_bias["confident"] = oos_ok
            if not oos_ok:
                selection_bias["warning"] = (
                    "Trainings-Gewinner besteht das Out-of-Sample-Test-Fenster NICHT "
                    "(kein Profit/keine Trades) → Overfit-Verdacht; wird NICHT automatisch angewandt.")
        else:
            winner["oos_validated"] = False
            selection_bias["warning"] = ("In-Sample-Gewinner ohne OOS-Test — nur manuell/"
                                         "experimentell nutzen.")
        stats.save_optimization(strategy, winner, windows or 1, timeframe=tf)
    return {
        "strategy": strategy, "days": days, "windows": windows or 1, "results": results,
        "winner": winner, "anchored": anchored, "ranges": rng,
        "selection_bias": selection_bias,
        "note": "Gewinner ist ein VORSCHLAG (proposal-only) — automatisch übernehmen dürfen ihn "
                "nur Auto-Upgrade-Pfade, wenn er OOS-validiert ist.",
    }


def mutate_params(base: dict, specs: list[dict], n: int = 4, scale: float = 0.25) -> list[dict]:
    """Erzeugt ``n`` mutierte Kandidaten-Parametersaetze rund um ``base`` (lokale Suche
    fuer den evolutionaeren Loop). Jeder numerische Parameter wird innerhalb seiner
    ``[min, max]``-Spanne gejittert (Gauss, Std = ``scale``·Spanne), auf die Grenzen
    geklemmt; ganzzahlige Werte bleiben int. Nicht-numerische bleiben unveraendert.
    """
    by_name = {s.get("name"): s for s in (specs or [])}
    out: list[dict] = []
    for _ in range(max(1, int(n))):
        cand: dict = {}
        for name, val in (base or {}).items():
            spec = by_name.get(name, {})
            lo, hi = spec.get("min"), spec.get("max")
            try:
                v = float(val)
            except (TypeError, ValueError):
                cand[name] = val
                continue
            if lo is not None and hi is not None and float(hi) > float(lo):
                v = v + random.gauss(0, scale * (float(hi) - float(lo)))
                v = max(float(lo), min(float(hi), v))
            is_int = isinstance(val, int) or isinstance(spec.get("default"), int)
            cand[name] = int(round(v)) if is_int else round(v, 4)
        out.append(cand)
    return out


def run_evolution(strategy: str, params: list[dict], generations: int = 2,
                  days: int = 90, windows: int = 2, pool: int = 4,
                  timeframe: str | None = None, embargo_days: int = 1,
                  scale: float = 0.25) -> dict:
    """Evolutionaerer Lern-Loop, **anchored** (proposal-only, QuantEvolve-light).

    Start = anchored ``run_optimization``; danach mutieren/selektieren ALLE Generationen
    ausschließlich auf dem TRAININGS-Fenster (würde je Generation auf dem Test-Fenster selektiert,
    wäre es durch die wiederholte Auswahl selbst kontaminiert). Erst der FINALE Gewinner wird
    EINMAL auf dem Test-Fenster geprüft und mit den ehrlichen OOS-Zahlen persistiert.
    Verglichen wird über den TRAININGS-Score (``score``-Feld) — die OOS-Zahlen des Basis-
    Gewinners fließen nie in die Generationen-Vergleiche ein. **Kein Auto-Apply** ohne
    ``oos_validated``."""
    from . import engine, stats

    windows = max(2, int(windows or 2))      # Evolution läuft immer anchored
    history: list[dict] = []
    base_run = run_optimization(strategy, params, days=days, windows=windows,
                                timeframe=timeframe, embargo_days=embargo_days)
    best = base_run.get("winner")
    rng = base_run.get("ranges")
    history.append({"generation": 0, "winner": best, "selection_bias": base_run.get("selection_bias")})
    if not best or not rng:
        return {"strategy": strategy, "generations": 0, "history": history, "winner": None,
                "note": "Keine valide Basis — Evolution abgebrochen."}
    # Daten sind durch run_optimization bereits geladen — Config/Timeframe nur auflösen.
    config, tf = engine._find_strategy_config(strategy)
    tf = timeframe or tf
    best_score = float(best.get("score") or -1e9)    # Trainings-Score (vor dem OOS-Zahlen-Swap)
    evolved = False
    for g in range(1, max(1, int(generations)) + 1):
        results = []
        for cp in mutate_params(best.get("params", {}), params, n=pool, scale=scale):
            r = engine.run_backtest_range(strategy, cp, rng["train"], timeframe=tf, config=config)
            m = r.get("metrics") or {}
            res = {"params": cp, "ok": bool(r.get("ok")),
                   "profit_total_pct": m.get("profit_total_pct"), "max_drawdown_pct": m.get("max_drawdown_pct"),
                   "total_trades": m.get("total_trades"), "winrate_pct": m.get("winrate_pct")}
            res["score"] = _opt_score(res)
            results.append(res)
        valid = [x for x in results if x["ok"] and (x["total_trades"] or 0) > 0]
        improved = False
        if valid:
            cb = sorted(valid, key=lambda x: (x["score"], -(x["max_drawdown_pct"] or 0.0)), reverse=True)[0]
            if cb["score"] > best_score:
                best = {**cb, "label": "evolviert", "train_profit_total_pct": cb["profit_total_pct"]}
                best_score, improved, evolved = cb["score"], True, True
        history.append({"generation": g, "pool": len(results), "improved": improved,
                        "best_score": best_score})
    if evolved:
        # Finaler einmaliger OOS-Test des evolvierten Gewinners auf dem ungesehenen Test-Fenster.
        t = engine.run_backtest_range(strategy, best["params"], rng["test"], timeframe=tf, config=config)
        tm = (t.get("metrics") or {}) if t.get("ok") else {}
        oos_ok = bool(t.get("ok")) and _oos_passed(tm)
        best.update({"profit_total_pct": tm.get("profit_total_pct"),
                     "max_drawdown_pct": tm.get("max_drawdown_pct"),
                     "total_trades": tm.get("total_trades"), "winrate_pct": tm.get("winrate_pct"),
                     "oos_validated": oos_ok, "oos_window": rng["test"]})
        stats.save_optimization(strategy, best, windows, timeframe=tf)
    return {"strategy": strategy, "generations": generations, "pool": pool, "scale": scale,
            "history": history, "winner": best, "anchored": True, "ranges": rng,
            "oos_validated": bool(best.get("oos_validated")),
            "note": "Evolutionärer Gewinner (proposal-only): Mutation + Selektion nur auf dem "
                    "Trainings-Fenster; finaler OOS-Test auf dem ungesehenen Test-Fenster."}


CONSISTENCY_MIN_DAYS = 3  # Mindest-Historie (Tages-Snapshots) vor Echtgeld-Freigabe
CONSISTENCY_MAX_AVG_LOSS = -10.0   # Ø-Profit darf nicht stark negativ sein
CONSISTENCY_MAX_DECLINE_PCT = -2.0  # Equity-Trend (% je Tag) darf nicht stark fallen
CONSISTENCY_MAX_VOL_PCT = 8.0       # Stdev der Tagesrenditen (%) — darüber zu unruhig


def consistency(bot_id: str, min_days: int = CONSISTENCY_MIN_DAYS) -> dict:
    """Konsistenz-Check vor „Auf Echtgeld heben" — datengetrieben aus den Tages-Snapshots.

    Verlangt nicht nur **genug Historie** + **Ø nicht stark negativ**, sondern bewertet
    zusätzlich **Trend** und **Stabilität** der Equity-Kurve:
    - *Trend* = Least-squares-Steigung der Equity je Tag (normiert auf % der mittleren
      Equity). Stark fallend (< ``CONSISTENCY_MAX_DECLINE_PCT`` %/Tag) → nicht freigabereif.
    - *Stabilität* = Standardabweichung der Tagesrenditen (%). Zu unruhig
      (> ``CONSISTENCY_MAX_VOL_PCT`` %) → nicht freigabereif.
    Trend/Stabilität greifen nur, wenn sie berechenbar sind (≥2 Equity-Punkte bzw.
    ≥2 Tagesrenditen) — mit wachsender Historie werden sie belastbarer.
    """
    snaps = stats.get_snapshots(bot_id, limit=365)  # aeltest -> neuest
    days = len(snaps)
    profits = [s.get("profit_pct") for s in snaps if s.get("profit_pct") is not None]
    avg = round(sum(profits) / len(profits), 2) if profits else None
    last = profits[-1] if profits else None

    # Trend + Stabilität aus der Equity-Reihe (chronologisch).
    eq = [s.get("equity") for s in snaps if s.get("equity") is not None]
    daily_returns = [(eq[i] - eq[i - 1]) / eq[i - 1] * 100
                     for i in range(1, len(eq)) if eq[i - 1]]
    volatility = round(_stdev(daily_returns), 3) if len(daily_returns) >= 2 else None
    slope_abs = _slope_per_step(eq)
    mean_eq = sum(eq) / len(eq) if eq else None
    trend_slope_pct = (round(slope_abs / mean_eq * 100, 3)
                       if slope_abs is not None and mean_eq else None)

    # Gates (defensive None-Behandlung: unberechenbare Kriterien blockieren nicht).
    enough = days >= min_days
    avg_ok = avg is None or avg > CONSISTENCY_MAX_AVG_LOSS
    trending_ok = trend_slope_pct is None or trend_slope_pct >= CONSISTENCY_MAX_DECLINE_PCT
    stable = volatility is None or volatility <= CONSISTENCY_MAX_VOL_PCT
    ok = enough and avg_ok and trending_ok and stable

    if not enough:
        reason = f"Noch zu wenig Historie: {days}/{min_days} Tages-Snapshots. Demo länger laufen lassen."
    elif not avg_ok:
        reason = f"Ergebnisse zu schwach (Ø {avg}%). Erst stabilisieren."
    elif not trending_ok:
        reason = f"Equity-Trend fällt ({trend_slope_pct:+}%/Tag). Erst stabilisieren."
    elif not stable:
        reason = f"Verlauf zu unruhig (Tagesrenditen-Stdev {volatility}%). Erst stabilisieren."
    else:
        bits = [f"{days} Tage Historie", f"Ø {avg}%"]
        if trend_slope_pct is not None:
            bits.append(f"Trend {trend_slope_pct:+}%/Tag")
        if volatility is not None:
            bits.append(f"Stdev {volatility}%")
        reason = "Konsistent: " + ", ".join(bits) + "."
    return {"consistent": ok, "days_tracked": days, "avg_profit_pct": avg,
            "last_profit_pct": last, "min_days": min_days,
            "trend_slope_pct": trend_slope_pct, "volatility_pct": volatility,
            "trending_ok": trending_ok, "stable": stable, "reason": reason}


# Regime-Eignung je implementierter Strategie (trend | range | volatil).
STRAT_REGIME = {
    "TrendFollowEma": "trend", "MomentumMacd": "trend", "FuturesMacdRsiScalp": "trend",
    "MeanReversionRsi": "range", "FuturesBbandsBounce": "range",
    "FuturesBreakoutVol": "volatil", "SessionOpenBreakout": "volatil",
    "GridRange": "range", "DcaDip": "range",
    "Supertrend": "trend", "VwapReversion": "range",
    "TtmSqueeze": "volatil", "EmaAdxTrend": "trend", "UtBotEma": "trend",
    "AsianRangeScalp": "range", "RsiDivergence": "range", "GaussianScalp": "trend",
}
_VOL_HIGH = 1.0  # Schwelle (1h-Return-Stdev in %) ab der „volatil" bevorzugt wird
# Mindest-Stichprobe je (Strategie×Regime/Session)-Zelle, bevor eine EMPIRISCHE Empfehlung zählt.
# Ehrlichkeit: n≥3 war statistisch bedeutungslos (z.B. DcaDip mit n=6 als „beste" Regime-Strategie).
# Zudem darf eine Zelle mit NEGATIVER Ø-Rendite NIE empfohlen werden (sonst wird die „am wenigsten
# schlechte" Verlust-Strategie empfohlen — live beobachtet: FuturesMacdRsiScalp in range).
_MIN_ADVICE_N = 30


def regime_performance() -> dict:
    """Empirische Performance je (Strategie × Markt-Regime) aus der eigenen Historie.

    Verknüpft Tages-Renditen der Bots (Equity-Delta aufeinanderfolgender Tages-
    Snapshots) mit dem **dominanten Markt-Regime** des jeweiligen Tages
    (aus `market_snapshots`). Wird mit wachsender Historie aussagekräftig.
    """
    # Tag -> dominantes Markt-Regime
    by_day: dict[str, list] = {}
    for r in stats.get_market_snapshots(limit=5000):
        day = (r.get("ts") or "")[:10]
        if r.get("regime"):
            by_day.setdefault(day, []).append(r["regime"])
    day_regime = {d: max(set(rs), key=rs.count) for d, rs in by_day.items() if rs}

    agg: dict[tuple, list] = {}
    points = 0
    for b in list_bots():
        snaps = stats.get_snapshots(b.id, limit=5000)  # aelteste -> neueste
        for i in range(1, len(snaps)):
            prev, cur = snaps[i - 1].get("equity"), snaps[i].get("equity")
            reg = day_regime.get(snaps[i].get("day"))
            if prev and cur is not None and reg:
                agg.setdefault((b.strategy, reg), []).append((cur - prev) / prev * 100)
                points += 1
    table = [{"strategy": s, "regime": rg, "avg_return_pct": round(sum(v) / len(v), 3), "n": len(v)}
             for (s, rg), v in agg.items()]
    table.sort(key=lambda x: (x["regime"], -x["avg_return_pct"]))
    return {"data_points": points, "data_sufficient": points >= 10, "table": table,
            "note": "Tages-Renditen je Strategie x Tages-Regime — wird mit mehr Historie belastbar."}


PER_TRADE_TOLERANCE_H = 6  # max. Abstand Trade-Schluss <-> Markt-Snapshot fuer Regime-Zuordnung


def _to_utc(s: str | None) -> datetime | None:
    """Parst einen Zeitstempel (ISO mit/ohne TZ, auch 'YYYY-MM-DD HH:MM:SS.ffffff')
    zu einem aware-UTC-datetime. Naive Stempel werden als UTC interpretiert
    (Freqtrade-Trade-DBs speichern UTC)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace(" ", "T"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def regime_performance_per_trade(tolerance_hours: int = PER_TRADE_TOLERANCE_H) -> dict:
    """Empirische Performance je (Strategie x Regime) **pro Trade** — feiner als das
    Tages-Aggregat in ``regime_performance``.

    Jedem geschlossenen Trade wird das Markt-Regime des zeitlich naechsten
    ``market_snapshots``-Eintrags zugeordnet (nur, wenn dieser binnen
    ``tolerance_hours`` liegt), dann der Trade-Profit je (Strategie x Regime)
    gemittelt. Nutzt die echten Handelsergebnisse statt der Tages-Equity-Deltas
    → erfasst auch Intraday-Regimewechsel. Wird mit wachsender Markt-/Trade-
    Historie aussagekraeftig.
    """
    snaps = [(_to_utc(r.get("ts")), r.get("regime"))
             for r in stats.get_market_snapshots(limit=100000)]
    snaps = sorted([(dt, rg) for dt, rg in snaps if dt and rg], key=lambda x: x[0])
    times = [s[0] for s in snaps]
    tol = timedelta(hours=tolerance_hours)

    def regime_at(dt: datetime | None) -> str | None:
        """Nächster Snapshot via bisect (O(log n) statt Linearsuche über alle Snapshots je Trade)."""
        if not snaps or dt is None:
            return None
        i = bisect.bisect_left(times, dt)
        best: tuple | None = None
        for j in (i - 1, i):
            if 0 <= j < len(times):
                d = abs(times[j] - dt)
                if best is None or d < best[0]:
                    best = (d, snaps[j][1])
        return best[1] if best and best[0] <= tol else None

    agg: dict[tuple, list] = {}
    points = 0
    for b in list_bots():
        for t in stats.closed_trades_for_regime(b.id):
            reg = regime_at(_to_utc(t.get("close_date")))
            if reg is None or t.get("profit_pct") is None:
                continue
            agg.setdefault((b.strategy, reg), []).append(t["profit_pct"])
            points += 1
    table = [{"strategy": s, "regime": rg, "avg_profit_pct": round(sum(v) / len(v), 3), "n": len(v)}
             for (s, rg), v in agg.items()]
    table.sort(key=lambda x: (x["regime"], -x["avg_profit_pct"]))
    return {"data_points": points, "data_sufficient": points >= 10,
            "tolerance_hours": tolerance_hours, "table": table,
            "note": f"Ø Trade-Profit je Strategie x Regime (Regime des naechsten Markt-Snapshots "
                    f"binnen {tolerance_hours} h) — feiner als das Tages-Aggregat."}


def regime_advice(rp_trade: dict | None = None, rp_day: dict | None = None) -> dict:
    """Empfiehlt regime-passende Strategien. **Empirisch**, sobald genug Historie
    vorliegt (beste Ø-Tagesrendite im aktuellen Regime), sonst **regelbasiert**
    (Strategie-Regime-Tags × aktuelles Markt-Regime).
    """
    market = stats.get_market_snapshots(limit=1)
    cur = market[-1] if market else None
    mregime = cur.get("regime") if cur else None
    vol = cur.get("volatility") if cur else None
    want = {"trend_up": "trend", "trend_down": "trend", "range": "range"}.get(mregime)
    high_vol = vol is not None and vol >= _VOL_HIGH
    detail = []
    for s, tag in STRAT_REGIME.items():
        fit = (tag == want) or (high_vol and tag == "volatil")
        detail.append({"strategy": s, "regime_tag": tag, "fit": bool(fit)})
    recommended = [d["strategy"] for d in detail if d["fit"]]
    source = "regelbasiert"
    data_points = 0
    # Bevorzugt **pro Trade** (feiner), dann **Tages-Aggregat**, sonst regelbasiert.
    rp_trade = rp_trade if rp_trade is not None else regime_performance_per_trade()
    rp_day = rp_day if rp_day is not None else regime_performance()
    if mregime:
        if rp_trade["data_sufficient"]:
            emp = sorted([r for r in rp_trade["table"]
                          if r["regime"] == mregime and r["n"] >= _MIN_ADVICE_N and r["avg_profit_pct"] > 0],
                         key=lambda x: x["avg_profit_pct"], reverse=True)
            if emp:
                recommended = [e["strategy"] for e in emp[:3]]
                source, data_points = "empirisch (Trades)", rp_trade["data_points"]
        if source == "regelbasiert" and rp_day["data_sufficient"]:
            emp = sorted([r for r in rp_day["table"]
                          if r["regime"] == mregime and r["n"] >= _MIN_ADVICE_N and r["avg_return_pct"] > 0],
                         key=lambda x: x["avg_return_pct"], reverse=True)
            if emp:
                recommended = [e["strategy"] for e in emp[:3]]
                source, data_points = "empirisch (Tage)", rp_day["data_points"]
    note = {
        "empirisch (Trades)": "Empirisch pro Trade (Regime zum Trade-Schluss) aus eigener Historie.",
        "empirisch (Tage)": "Empirisch aus Tages-Aggregat; Per-Trade-Verfeinerung aktiviert sich mit mehr Trade-Historie.",
        "regelbasiert": "Regelbasiert; empirische Verfeinerung aktiviert sich automatisch mit mehr Historie.",
    }[source]
    return {"market_regime": mregime, "volatility": vol, "high_vol": high_vol,
            "recommended": recommended, "detail": detail, "source": source,
            "data_points": data_points, "note": note}


# ----------------------------------------------------- Börseneröffnungen / Sessions
def session_performance_per_trade() -> dict:
    """Empirische Performance je (Strategie × Session-Eröffnung) **pro Trade**.

    Ordnet jeden geschlossenen Trade über seinen Schluss-Zeitpunkt einem der
    Session-Bänder (Asia/London/EU↔US-Overlap/US/late-US, siehe ``sessions.py``)
    zu und mittelt den Trade-Profit je (Strategie × Session). Das ist die
    Lern-Grundlage für das Sonder-Thema **Börseneröffnungen**: in welcher
    Session-Phase trägt eine Strategie? Wird mit wachsender Trade-Historie
    aussagekräftig. Kein Netz/keine Markt-Snapshots nötig (Session = reine Zeit).
    """
    agg: dict[tuple, list] = {}
    points = 0
    for b in list_bots():
        for t in stats.closed_trades_for_regime(b.id):
            sess = sessions.session_for(_to_utc(t.get("close_date")))
            if sess is None or t.get("profit_pct") is None:
                continue
            agg.setdefault((b.strategy, sess), []).append(t["profit_pct"])
            points += 1
    table = [{"strategy": s, "session": sess, "session_label": sessions.session_label(sess),
              "avg_profit_pct": round(sum(v) / len(v), 3), "n": len(v)}
             for (s, sess), v in agg.items()]
    table.sort(key=lambda x: (x["session"], -x["avg_profit_pct"]))
    return {"data_points": points, "data_sufficient": points >= 10, "table": table,
            "note": "Ø Trade-Profit je Strategie × Session-Eröffnung (Session aus Trade-Schlusszeit, UTC). "
                    "Lern-Basis für das Sonder-Thema Börseneröffnungen — wird mit mehr Trade-Historie belastbar."}


def session_advice(sp: dict | None = None) -> dict:
    """Empfiehlt session-passende Strategien für die **aktuelle** Eröffnungs-Phase
    und nennt je Strategie die historisch **beste Session** (Präzisions-Hinweis für
    die Lern-Instanz). Empirisch, sobald genug Trade-Historie vorliegt; sonst nur
    die aktuelle Session als Kontext.
    """
    now = datetime.now(timezone.utc)
    cur = sessions.session_for(now)
    ow = sessions.opening_window(now)
    sp = sp if sp is not None else session_performance_per_trade()

    # Beste Session je Strategie (höchste Ø-Trade-Rendite mit ausreichend Trades).
    best_by_strategy: dict[str, dict] = {}
    for r in sp["table"]:
        if r["n"] < 3:
            continue
        cur_best = best_by_strategy.get(r["strategy"])
        if cur_best is None or r["avg_profit_pct"] > cur_best["avg_profit_pct"]:
            best_by_strategy[r["strategy"]] = {"session": r["session"],
                                               "session_label": r["session_label"],
                                               "avg_profit_pct": r["avg_profit_pct"], "n": r["n"]}
    # Für die aktuelle Session: beste Strategien (empirisch).
    recommended: list[str] = []
    source = "regelbasiert"
    if sp["data_sufficient"]:
        emp = sorted([r for r in sp["table"]
                      if r["session"] == cur and r["n"] >= _MIN_ADVICE_N and r["avg_profit_pct"] > 0],
                     key=lambda x: x["avg_profit_pct"], reverse=True)
        if emp:
            recommended = [e["strategy"] for e in emp[:3]]
            source = "empirisch (Trades)"
    if not recommended:
        # Fallback: in/um eine Eröffnung sind Session-Open-Systeme strukturell passend.
        recommended = ["SessionOpenBreakout"] if ow else []
    return {
        "current_session": cur, "current_session_label": sessions.session_label(cur),
        "in_opening_window": bool(ow), "opening_window": (ow["label"] if ow else None),
        "recommended": recommended, "best_by_strategy": best_by_strategy,
        "source": source, "data_points": sp["data_points"],
        "note": ("In einer Börseneröffnung (" + ow["label"] + ") — Session-Open-Systeme sind hier strukturell im Element."
                 if ow else
                 "Aktuell keine schmale Eröffnungs-Phase; empirische Session-Stärken sammeln sich mit mehr Trades."),
    }


def report() -> dict:
    agg = aggregate()
    # Alle zuletzt gelernten Gewinner (auch Strategien ohne aktiven Bot).
    opts = [{"strategy": o["strategy"], "winner_label": o.get("winner_label"),
             "params": o.get("params"), "profit_total_pct": o.get("profit_total_pct"),
             "oos_validated": bool(o.get("oos_validated")), "timeframe": o.get("timeframe"),
             "ts": o.get("ts")} for o in stats.get_all_optimizations()]
    # Echtgeld-Reife je Demo-Bot (Validierung + Konsistenz).
    readiness = []
    for b in list_bots():
        if not b.dry_run:
            continue
        c = consistency(b.id)
        v = stats.get_strategy_validation(b.strategy)
        readiness.append({
            "bot_id": b.id, "name": b.name, "strategy": b.strategy,
            "validated": bool(v and v.get("validated")),
            "consistent": c["consistent"], "days_tracked": c["days_tracked"],
            "min_days": c["min_days"], "avg_profit_pct": c["avg_profit_pct"],
            "trend_slope_pct": c["trend_slope_pct"], "volatility_pct": c["volatility_pct"],
            "ready": bool(v and v.get("validated")) and c["consistent"],
        })
    market = stats.get_market_snapshots(limit=24)
    rp = regime_performance()
    rpt = regime_performance_per_trade()
    sp = session_performance_per_trade()
    return {"status": learning_status(agg), "strategies": agg["strategies"],
            "proposals": proposals(agg), "optimizations": opts, "readiness": readiness,
            "market": market[-1] if market else None, "regime_advice": regime_advice(rpt, rp),
            "regime_performance": rp["table"], "regime_data_points": rp["data_points"],
            "regime_performance_trades": rpt["table"], "regime_trade_data_points": rpt["data_points"],
            "regime_trade_tolerance_h": rpt["tolerance_hours"],
            "session_advice": session_advice(sp),
            "session_performance": sp["table"], "session_data_points": sp["data_points"]}
