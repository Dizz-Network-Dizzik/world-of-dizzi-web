"""marketmaking.py — Market-Making (Avellaneda-Stoikov), markt-neutral, DEMO/Simulation.

Letzter markt-neutraler Archetyp. Market-Making braucht eine ORDERBUCH-/Fill-Dynamik, die nicht
in Freqtrades Per-Pair-Signal-Modell passt — daher als eigene Simulation (Muster wie csm/pairs).

Implementiert das **kanonische Avellaneda-Stoikov-Modell** (2008): der MM quotiert beidseitig um
einen **Reservationspreis** (Mid, nach Inventar & Risikoaversion verschoben) mit optimalem Spread;
Fills kommen als **Poisson-Prozess** mit Intensität ``A·exp(-k·δ)`` (näher am Mid = mehr Fills);
Inventar wird systematisch neutral gehalten. Verdient Spread + Maker-Rebate, Risiko = Inventar/Vola.

Die Volatilität wird aus ECHTEN Tages-Returns eines Symbols (``csm_prices``) kalibriert; der Mid
ist ein darauf kalibrierter stochastischer Pfad (Monte-Carlo über viele Sessions). **Modell-Sim,
NICHT echte Bitget-Microstruktur** — 0 Risiko, keine Orders. Reines Python, deterministisch (Seed), testbar.
"""

from __future__ import annotations

import math
import random
import statistics

from . import cache, csm, mn_base

DEFAULTS = {
    "gamma": 0.1,          # Risikoaversion (Inventar-Strafe); höher = engeres Inventar, breiterer Skew
    "k": 1.5,              # Orderbuch-Liquiditäts-Decay (höher = Fills nur sehr nah am Mid)
    "A": 22.0,             # Basis-Fill-Intensität (bewusst niedrig -> realistische Fill-Frequenz)
    "order_size": 1.0,     # Einheiten je Fill
    "inventory_limit": 8,  # max. |Inventar| (begrenzt Risiko + definiert die Kapitalbasis)
    "steps": 200,          # Schritte je Handels-Session
    "episodes": 300,       # Monte-Carlo-Sessions
    "maker_rebate_bps": 1.0,  # Maker-Rebate je Fill (bps vom Notional)
    "adverse_frac": 0.92,  # Adverse-Selection als ANTEIL des gequoteten Abstands, der gegen den MM driftet
                           # (stochastisch). Koppelt die Kosten an die Quote-Breite -> kein Gratis-Edge durchs Verbreitern.
    "symbol": "BTC/USDT:USDT",  # Vola-Kalibrierung aus echten Daten
    "min_history": 200,
    "capital": 10000.0,
    "vol_recal": False,    # Vola-getriggerte Re-Kalibrierung: statt der statischen Tages-Vola schätzt
                           # der MM die Vola INNERHALB der Session adaptiv (EWMA der Mid-Moves) und
                           # quotiert danach — bei Vola-Spikes weiten sich Spread+Inventar-Skew (Adverse-
                           # Selection-Schutz). Default AUS = statische Vola = Live unverändert. docs/47 §2, OOS.
}
S0 = 100.0  # normierter Mid-Startpreis (P&L wird relativ zur Positions-Notional berichtet)


def get_config() -> dict:
    return mn_base.config_get(DEFAULTS, "mm_config")


def set_config(patch: dict) -> dict:
    return mn_base.config_set(DEFAULTS, "mm_config", patch)


def calib_sigma(symbol: str, min_history: int) -> tuple[float, str]:
    """Tages-Vola (Return-Stdev) eines Symbols aus csm_prices. Fallback: liquidestes verfügbares."""
    syms, ts, closes = csm._load_prices(min_history)
    if not syms:
        return 0.0, ""
    use = symbol if symbol in closes else None
    if use is None:
        # nimm das Symbol mit der meisten Historie
        use = max(syms, key=lambda s: sum(1 for v in closes[s] if v is not None))
    series = [v for v in closes[use] if v is not None]
    rets = [math.log(series[i] / series[i - 1]) for i in range(1, len(series))
            if series[i] and series[i - 1] and series[i] > 0 and series[i - 1] > 0]
    if len(rets) < 20:
        return 0.0, use
    return statistics.pstdev(rets), use


def simulate(sigma_daily: float, gamma: float, k: float, A: float, order_size: float,
             inventory_limit: int, steps: int, episodes: int, rebate_bps: float,
             capital: float, adverse_frac: float = 0.0, seed: int = 42,
             vol_recal: bool = False) -> dict:
    """Avellaneda-Stoikov Monte-Carlo. Returns Equity (je Session ein Punkt), Stats, Fill-Rate, Inventar.

    ``vol_recal`` (opt-in): die für Reservationspreis/Spread genutzte Varianz wird NICHT statisch
    gehalten, sondern je Schritt aus einer EWMA der realisierten Mid-Increments nachgeführt (auf
    [0.25×, 4×] der Basis gedeckelt). Default False = exakt das statische Verhalten (Live unverändert)."""
    if sigma_daily <= 0 or steps < 10 or episodes < 1:
        return {"ok": False, "error": "Kalibrierung/Parameter unzureichend"}
    rng = random.Random(seed)
    sig = sigma_daily * S0           # Vola in Preis-Einheiten über eine Session (~1 Tag)
    var = sig * sig
    dt = 1.0 / steps
    sqrt_dt = math.sqrt(dt)
    var_step0 = var * dt             # Basis-Varianz je Schritt (Referenz für die EWMA-Nachführung)
    recal_lambda = 0.06              # EWMA-Gewicht (~Halbwertszeit 11 Schritte) für vol_recal
    cap_base = max(1.0, inventory_limit * S0)   # Kapitalbasis = max. Positions-Notional
    spread_const = (2.0 / gamma) * math.log(1.0 + gamma / k) if (gamma > 0 and k > 0) else 0.01

    sess_returns = []
    fills_sum = 0
    inv_abs_sum = 0.0
    eq = capital
    equity = []
    for ep in range(episodes):
        s = S0
        q = 0.0
        cash = 0.0
        rebate = 0.0
        ep_fills = 0
        inv_peak = 0.0
        ewma_step = var_step0                             # adaptive Schritt-Varianz (nur bei vol_recal genutzt)
        for i in range(steps):
            s_before = s
            var_q = var                                   # Quoting-Varianz: statisch (Default) ...
            if vol_recal:                                 # ... oder adaptiv aus der realisierten Mid-Vola
                ratio = (ewma_step / var_step0) if var_step0 > 0 else 1.0
                var_q = var * min(4.0, max(0.25, ratio))
            tau = 1.0 - i / steps                         # Restzeit (T-t), normiert
            res = s - q * gamma * var_q * tau             # Reservationspreis (Inventar-Skew)
            half = 0.5 * (gamma * var_q * tau + spread_const)
            half = max(half, 0.01)
            bid = res - half
            ask = res + half
            d_bid = max(0.0, s - bid)                     # Abstand der Quote zum Mid
            d_ask = max(0.0, ask - s)
            p_bid = 1.0 - math.exp(-A * math.exp(-k * d_bid) * dt)
            p_ask = 1.0 - math.exp(-A * math.exp(-k * d_ask) * dt)
            if q < inventory_limit and rng.random() < p_bid:     # Kauf zum Bid
                cash -= bid * order_size
                q += order_size
                rebate += rebate_bps / 1e4 * bid * order_size
                ep_fills += 1
                s -= adverse_frac * d_bid * abs(rng.gauss(1.0, 0.5))   # Adverse-Selection ∝ Quote-Abstand (stochastisch): Mid fällt nach Kauf
            if q > -inventory_limit and rng.random() < p_ask:    # Verkauf zum Ask
                cash += ask * order_size
                q -= order_size
                rebate += rebate_bps / 1e4 * ask * order_size
                ep_fills += 1
                s += adverse_frac * d_ask * abs(rng.gauss(1.0, 0.5))   # Adverse-Selection ∝ Quote-Abstand (stochastisch): Mid steigt nach Verkauf
            if s <= 1.0:
                s = 1.0
            inv_peak = max(inv_peak, abs(q))
            s += sig * sqrt_dt * rng.gauss(0.0, 1.0)      # Mid-Random-Walk
            if s <= 1.0:
                s = 1.0
            if vol_recal:                                 # EWMA der realisierten Schritt-Varianz nachführen
                ds = s - s_before
                ewma_step = (1.0 - recal_lambda) * ewma_step + recal_lambda * ds * ds
        pnl = cash + q * s + rebate                       # Inventar zum Schluss liquidieren
        ret = pnl / cap_base
        sess_returns.append(ret)
        fills_sum += ep_fills
        inv_abs_sum += inv_peak
        eq *= (1.0 + ret)
        equity.append([ep, round(eq, 2)])

    st = mn_base.equity_stats(sess_returns, equity, capital, eq)
    days = st["days"]
    return {
        "ok": True, "n_pairs": 1, **st,
        "avg_fills_per_session": round(fills_sum / days, 1) if days else 0,
        "avg_peak_inventory": round(inv_abs_sum / days, 2) if days else 0,
        "equity": equity,
    }


def _ts_axis(n: int) -> list[int]:
    return [i * csm.DAY_MS for i in range(n)]


# Deterministische Seed-Liste für die seed-gemittelte Status-Schätzung (Reproduzierbarkeit + Test).
# 20 Seeds: der Sharpe-Mittelwert konvergiert empirisch ab ~20 Seeds (~5.4, Std ~1.35); weniger
# Seeds streuen den Mittelwert selbst zu stark (7 Seeds: 6.0–6.4 je nach Set → Lucky-Set-Bias).
STATUS_SEEDS = tuple(42 + 100 * i for i in range(20))


def _ensemble(sigma: float, cfg: dict, seeds=STATUS_SEEDS) -> dict | None:
    """Mehrere Monte-Carlo-Läufe (unterschiedliche Seeds) → **seed-gemittelte** Kennzahlen.

    Hintergrund (empirisch belegt): die Sharpe eines EINZELNEN MC-Laufs streut stark (über
    Seeds ~2.5…7.9, Mittel ~5.2, Std ~1.7), während die PSR je Lauf ~1.0 bleibt (sie misst
    nur Signifikanz innerhalb eines Laufs, nicht die Seed-Streuung — falsch beruhigend). Der
    Master darf NICHT von einem Lucky-Seed gespeist werden; deshalb liefert ``get_state``/
    ``status`` die über ``seeds`` gemittelte Sharpe + die Seed-Streuung (``sharpe_seed_stdev``).
    Die repräsentative Equity-Kurve (Seed mit Sharpe am Mittel) bleibt für die UI erhalten."""
    runs = []
    for sd in seeds:
        s = simulate(sigma, cfg["gamma"], cfg["k"], cfg["A"], cfg["order_size"], cfg["inventory_limit"],
                     cfg["steps"], cfg["episodes"], cfg["maker_rebate_bps"], cfg["capital"],
                     cfg["adverse_frac"], seed=sd, vol_recal=bool(cfg.get("vol_recal")))
        if s.get("ok"):
            runs.append(s)
    if not runs:
        return None
    keys = ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct", "last_day_return_pct", "psr")
    avg = {k: round(sum(r[k] for r in runs) / len(runs), 3) for k in keys}
    sharpes = [r["sharpe"] for r in runs]
    avg["sharpe_seed_stdev"] = round(statistics.pstdev(sharpes), 3) if len(sharpes) > 1 else 0.0
    avg["seeds"] = len(runs)
    avg["days"] = runs[0]["days"]
    avg["n_pairs"] = 1
    rep = min(runs, key=lambda r: abs(r["sharpe"] - avg["sharpe"]))   # repräsentativer Lauf für die Kurve
    return {"stats": avg, "rep": rep}


def get_state(equity_points: int = 400) -> dict:
    cfg = get_config()
    sigma, used = calib_sigma(cfg["symbol"], cfg["min_history"])
    if sigma <= 0:
        return {"ok": False, "ready": False, "config": cfg,
                "note": "Keine Preis-Daten zur Vola-Kalibrierung. Zuerst /api/csm/refresh.",
                "last_refresh": csm._meta_get("last_refresh")}
    # Seed-Ensemble ist teurer (20 Sims) → kurzer TTL-Memo gegen UI-/Master-Bursts (config-abhängig).
    ekey = ("mm_ensemble:" + ":".join(str(cfg[k]) for k in
            ("gamma", "k", "A", "order_size", "inventory_limit", "steps", "episodes",
             "maker_rebate_bps", "adverse_frac", "capital")) + f":{sigma:.6f}")
    ens = cache.ttl_get(ekey, 60.0, lambda: _ensemble(sigma, cfg))
    if ens is None:
        return {"ok": False, "ready": False, "config": cfg, "error": "Simulation fehlgeschlagen"}
    sim = ens["rep"]          # repräsentativer Lauf (Equity/Fills/Inventar für die Anzeige)
    ens_stats = ens["stats"]  # seed-gemittelte Kennzahlen für den Master
    # x-Achse auf Session-Index -> ts-artig für die UI-Grafik. sim ist der gecachte repräsentative
    # Lauf → NICHT mutieren (kein pop), nur lesen, sonst fehlt beim warmen Cache-Hit die Equity.
    eq = [[i, v[1]] for i, v in enumerate(sim["equity"])]
    eq = mn_base.downsample(eq, equity_points)
    eq = [[t * mn_base.DAY_MS, v] for t, v in eq]
    return {
        "ok": True, "ready": True, "mode": "demo-simulation", "config": cfg,
        "calibrated_symbol": used, "sigma_daily_pct": round(sigma * 100, 2),
        "stats": {k: ens_stats[k] for k in ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct",
                                            "last_day_return_pct", "days", "psr", "n_pairs",
                                            "sharpe_seed_stdev", "seeds")},
        "fills": sim["avg_fills_per_session"], "avg_peak_inventory": sim["avg_peak_inventory"],
        "equity": eq, "last_refresh": csm._meta_get("last_refresh"),
        "explainer": "Avellaneda-Stoikov Market-Making: quotiert beidseitig um den inventar-skewten "
                     "Reservationspreis, Fills als Poisson-Prozess (A·e^(−k·δ)), Inventar systematisch neutral. "
                     "Modell-Simulation auf kalibrierter Vola — keine Orders.",
        "caveats": ["MODELL-Simulation (Avellaneda-Stoikov), NICHT echte Orderbuch-Microstruktur",
                    "Vola aus Tages-Returns kalibriert; Intraday-Dynamik/Adverse-Selection idealisiert",
                    "Reale MM-Profitabilität hängt stark an Maker-Fees/Rebate, Latenz, Queue-Position",
                    "Slippage/partielle Fills nicht modelliert -> optimistisch"],
    }


def status() -> dict:
    st = get_state(equity_points=1)
    if not st.get("ready"):
        return {"ready": False, "note": st.get("note"), "last_refresh": st.get("last_refresh")}
    return {"ready": True, "mode": "demo-simulation", "stats": st["stats"],
            "fills": st["fills"], "avg_peak_inventory": st["avg_peak_inventory"],
            "calibrated_symbol": st["calibrated_symbol"], "last_refresh": st["last_refresh"]}


def optimize(windows: int = 3) -> dict:
    """Lern-Loop: Raster über (gamma, k); bewertet jeden Kandidaten mit MEHREREN Seeds (Out-of-
    Sample gegen Zufalls-Overfit) und kürt den besten Ø-Sharpe. Proposal-only."""
    cfg = get_config()
    sigma, used = calib_sigma(cfg["symbol"], cfg["min_history"])
    if sigma <= 0:
        return {"ok": False, "note": "Keine Preis-Daten zur Vola-Kalibrierung (zuerst /api/csm/refresh)."}
    seeds = [11 * (j + 1) for j in range(max(1, int(windows)))]
    candidates = [{"gamma": g, "k": kk} for g in (0.05, 0.1, 0.2) for kk in (1.0, 1.5, 2.5)]
    results = []
    for c in candidates:
        scores = []
        for sd in seeds:
            sim = simulate(sigma, c["gamma"], c["k"], cfg["A"], cfg["order_size"], cfg["inventory_limit"],
                           cfg["steps"], max(120, cfg["episodes"] // 2), cfg["maker_rebate_bps"],
                           cfg["capital"], cfg["adverse_frac"], seed=sd, vol_recal=bool(cfg.get("vol_recal")))
            if sim.get("ok"):
                scores.append(sim["sharpe"])
        avg = round(sum(scores) / len(scores), 3) if scores else None
        worst = round(min(scores), 3) if scores else None
        results.append({"params": c, "avg_sharpe": avg, "worst_sharpe": worst, "windows": len(scores)})
    valid = [r for r in results if r["avg_sharpe"] is not None]
    winner = max(valid, key=lambda r: (r["avg_sharpe"], r["worst_sharpe"])) if valid else None
    results.sort(key=lambda r: (r["avg_sharpe"] is not None, r["avg_sharpe"] or -1e9), reverse=True)
    return {"ok": True, "engine": "mm", "folds": len(seeds), "candidates": len(candidates),
            "results": results, "winner": winner,
            "current_config": {k: cfg[k] for k in ("gamma", "k")},
            "note": "Proposal-only: bestes (gamma,k) nach Ø-Sharpe über mehrere Seeds. Anwenden = Engine-Config setzen."}
