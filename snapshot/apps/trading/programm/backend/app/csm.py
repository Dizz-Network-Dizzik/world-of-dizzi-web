"""csm.py — Cross-Sectional-Momentum-Orchestrator (markt-neutral), DEMO/Simulation.

Eigenständige Engine NEBEN Freqtrade (Cross-Sectional passt nicht in dessen Per-Pair-Modell):
rankt täglich das liquide Perp-Universum nach Lookback-Return, hält **long Top-Quantil / short
Bottom-Quantil** (dollar-neutral). Hier NUR Simulation auf echten Preisen (read-only ccxt) — **0 echtes
Risiko, keine Orders**. Echtgeld-Ausführung (M6) bleibt ausdrückliche Freigabe.

Edge in `programm/research/` belegt+gehärtet (E2/E3): Netto-Sharpe ~1,2–1,3 (Gebühren+Funding+Subsampling).
Simulation in **reinem Python** (Backend-venv hat kein numpy) und damit dependency-leicht + testbar.
Caveats: nur Bitget-Überlebende (keine echt-delisteten Coins), ~2 J Historie, Stärke zeitvariabel.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone

from . import mn_base, stats

# Re-Export der geteilten Basis unter den historischen Namen, damit `csm._meta_get`/`csm._ensure`/
# `csm.DAY_MS`-Aufrufe (pairs/marketmaking, refresh_prices) unverändert gültig bleiben.
DAY_MS = mn_base.DAY_MS
_ensure = mn_base.ensure
_meta_get = mn_base.meta_get
_meta_set = mn_base.meta_set

DEFAULTS = {
    "lookback": 14,      # L: Momentum-Lookback in Tagen
    "hold": 1,           # H: Rebalancing-Intervall in Tagen
    "quantile": 0.30,    # Q: Anteil je Seite (Top/Bottom)
    "fee": 0.0006,       # Gebühr/Seite auf Turnover (Futures Taker)
    "universe_top": 80,  # Top-N Perps nach Volumen (breiter = weniger survivorship-optimistisch)
    "min_history": 300,  # Mindest-Tage Historie je Pair (jüngere zulassen -> ehrlicheres Universum)
    "capital": 10000.0,  # Demo-Startkapital (USDT)
    "vol_scaled": False, # Risk-adjusted Momentum: Signal /= Tagesvola über L (opt-in, default AUS = Live
                         # unverändert). OOS-validiert (R7/R7b, 14/14 Stresses: Sharpe 0.86->1.88 anchored
                         # WF, kosten-/universum-/parameter-robust). Aktivieren = set_config({"vol_scaled":true}).
    "signal_lag": 0,     # Skip-most-recent: Momentum-Fenster um N Tage zurückversetzt (Klassik „12-1": das
                         # Signal lässt die jüngsten N Tage aus, um Short-Term-Reversal zu dämpfen). 0 = AUS
                         # (Live unverändert). docs/47 §2-Feinschliff, proposal-only/OOS. Aktivieren = {"signal_lag":1}.
}


# ---------- Konfiguration ----------
def get_config() -> dict:
    return mn_base.config_get(DEFAULTS, "config")


def set_config(patch: dict) -> dict:
    return mn_base.config_set(DEFAULTS, "config", patch)


# ---------- Daten (ccxt, read-only) ----------
def _client():
    import ccxt  # lokal, damit Backend ohne ccxt-Call startet
    return ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def fetch_universe(top_n: int) -> list[str]:
    cl = _client()
    markets = cl.load_markets()
    tickers = cl.fetch_tickers()
    swaps = [(s, float((tickers.get(s) or {}).get("quoteVolume") or 0))
             for s, m in markets.items()
             if m.get("swap") and m.get("quote") == "USDT" and m.get("active") and ":USDT" in s]
    swaps.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in swaps[:top_n]]


def refresh_prices(days: int = 730) -> dict:
    """Holt/aktualisiert Daily-Closes des Universums inkrementell in `csm_prices` (paginiert)."""
    cfg = get_config()
    cl = _client()
    universe = fetch_universe(cfg["universe_top"])
    now = cl.milliseconds()
    window_start = now - (days + 5) * DAY_MS
    added = 0
    with stats._conn() as conn:
        _ensure(conn)
        for sym in universe:
            row = conn.execute("SELECT MAX(day) FROM csm_prices WHERE symbol=?", (sym,)).fetchone()
            cursor = max(window_start, (row[0] + DAY_MS) if row and row[0] else window_start)
            while cursor < now:
                try:
                    batch = cl.fetch_ohlcv(sym, timeframe="1d", since=cursor, limit=200)
                except Exception:
                    break
                if not batch:
                    break
                for r in batch:
                    conn.execute("INSERT OR REPLACE INTO csm_prices(symbol,day,close) VALUES(?,?,?)",
                                 (sym, int(r[0]), float(r[4])))
                    added += 1
                if batch[-1][0] <= cursor:
                    break
                cursor = batch[-1][0] + DAY_MS
        conn.commit()
    # Funding-Proxy: per-Pair-Mittel der (nur ~30T verfügbaren) Funding-Raten als Tagesrate cachen.
    # Bitget liefert keine mehrjährige Funding-Historie -> Mittel als Konstant-Proxy (E3-Methodik).
    funding_avg: dict[str, float] = {}
    for sym in universe:
        try:
            hist = cl.fetch_funding_rate_history(sym, limit=200)
            rates = [float(h["fundingRate"]) for h in hist if h.get("fundingRate") is not None]
            if rates:
                # Tagesrate = Summe je Tag; Bitget i.d.R. 3×/Tag (8h) -> Mittel×3 als Tagesäquivalent
                funding_avg[sym] = (sum(rates) / len(rates)) * 3.0
        except Exception:
            continue
    _meta_set("funding_avg", json.dumps(funding_avg))
    _meta_set("last_refresh", datetime.now(timezone.utc).isoformat())
    _meta_set("universe", json.dumps(universe))
    return {"universe": len(universe), "rows_upserted": added, "funding_pairs": len(funding_avg),
            "last_refresh": _meta_get("last_refresh")}


def _load_prices(min_history: int) -> tuple[list[str], list[int], dict]:
    with stats._conn() as c:
        _ensure(c)
        rows = c.execute("SELECT symbol, day, close FROM csm_prices ORDER BY day").fetchall()
    by_sym: dict[str, dict[int, float]] = {}
    for sym, day, close in rows:
        by_sym.setdefault(sym, {})[day] = close
    keep = {s: m for s, m in by_sym.items() if len(m) >= min_history}
    if not keep:
        return [], [], {}
    all_ts = sorted(set().union(*[set(m.keys()) for m in keep.values()]))
    syms = sorted(keep.keys())
    closes = {s: [keep[s].get(t) for t in all_ts] for s in syms}
    return syms, all_ts, closes


# ---------- Simulation (reines Python, lookahead-frei) ----------
def simulate(syms: list[str], ts: list[int], closes: dict,
             L: int, H: int, Q: float, fee: float, capital: float,
             funding: dict | None = None, vol_scaled: bool = False,
             signal_lag: int = 0) -> dict:
    T = len(ts)
    N = len(syms)
    lag = max(0, int(signal_lag))
    if T < L + lag + 3 or N < 6:
        return {"ok": False, "error": "zu wenig Daten/Pairs für die Simulation"}
    # Funding-Proxy je Pair (Tagesrate): Long zahlt pos. Funding, Short erhält -> P&L = -w*funding.
    fund = [float((funding or {}).get(s, 0.0)) for s in syms]
    # Forward-Fill je Reihe
    C = []
    for s in syms:
        row = list(closes[s])
        last = None
        for j in range(T):
            if row[j] is None:
                row[j] = last
            else:
                last = row[j]
        C.append(row)

    def ret(i, t):
        a, b = C[i][t - 1], C[i][t]
        return (b / a - 1.0) if (a and b and a > 0) else None

    w = [0.0] * N
    w_prev = [0.0] * N
    longs: list[str] = []
    shorts: list[str] = []
    mom_last: dict[str, float] = {}
    equity = []
    rets = []
    eq = capital
    start = L + lag + 1
    for t in range(start, T):
        # 1) Rendite mit den am Vortag gesetzten Gewichten (kein Lookahead)
        pr = 0.0
        for i in range(N):
            if w[i]:
                r = ret(i, t)
                if r is not None:
                    pr += w[i] * r
                pr -= w[i] * fund[i]  # Funding-P&L-Proxy
        # 2) danach ggf. rebalancen -> neue Gewichte gelten ab t+1
        cost = 0.0
        if (t - start) % H == 0:
            mom = []
            for i in range(N):
                # signal_lag: das Momentum-Fenster endet `lag` Tage VOR t (Skip-most-recent),
                # die jüngsten `lag` Tage fließen NICHT ins Signal (dämpft Short-Term-Reversal).
                a, b = C[i][t - L - lag], C[i][t - lag]
                mi = (b / a - 1.0) if (a and b and a > 0) else None
                if mi is not None and vol_scaled:
                    # Risk-adjusted Momentum: durch die Tagesvola über L teilen (dämpft hochvolatile
                    # Coins, OOS-robuster Lift R7b). Vola-frei/undefiniert -> Signal None (rausgefiltert).
                    dr = [C[i][j] / C[i][j - 1] - 1.0 for j in range(t - L - lag + 1, t - lag + 1)
                          if C[i][j - 1] and C[i][j] and C[i][j - 1] > 0]
                    sd = statistics.pstdev(dr) if len(dr) > 2 else None
                    mi = (mi / sd) if (sd and sd > 0) else None
                mom.append(mi)
            valid = [i for i in range(N) if mom[i] is not None]
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: mom[i])
                k = max(1, int(Q * len(valid)))
                sh, lo = order[:k], order[-k:]
                neww = [0.0] * N
                for i in lo:
                    neww[i] = 0.5 / len(lo)
                for i in sh:
                    neww[i] = -0.5 / len(sh)
                cost = fee * sum(abs(neww[i] - w_prev[i]) for i in range(N))
                w = neww
                w_prev = list(w)
                longs = [syms[i] for i in reversed(lo)]
                shorts = [syms[i] for i in sh]
                mom_last = {syms[i]: round(mom[i] * 100, 2) for i in valid}
        net = pr - cost
        eq *= (1.0 + net)
        equity.append([ts[t], round(eq, 2)])
        rets.append(net)

    return {
        "ok": True, "n_pairs": N, **mn_base.equity_stats(rets, equity, capital, eq),
        "equity": equity, "rets": rets,
        "current": {
            "longs": [{"symbol": s, "mom_pct": mom_last.get(s)} for s in longs],
            "shorts": [{"symbol": s, "mom_pct": mom_last.get(s)} for s in shorts],
            "per_side_weight_pct": round(50.0 / max(1, len(longs)), 2),
        },
    }


# ---------- Echter Forward-Track (realisierte OOS-Rendite/Tag, KEIN Voll-Sample-Re-Fit) ----------
# Abgrenzung zu `csm_equity_log`/`forward_track_days`: jenes loggt täglich die VOLL-SAMPLE-Sharpe (täglich
# neu gefittet -> KEIN OOS, schwankt mit Config/Re-Fit). `csm_forward` akkumuliert dagegen pro Tag die EINE
# realisierte Tagesrendite des Live-Signals (Vortags-Gewichte × heutiger Kursmove, Point-in-Time) ->
# eine echte Out-of-Sample-Equity-Kurve, die über Wochen die vol-Skalierung live bestätigt oder widerlegt.
def _forward_fp(cfg: dict) -> str:
    lag = int(cfg.get("signal_lag", 0) or 0)
    base = f"L{cfg['lookback']}H{cfg['hold']}Q{cfg['quantile']}v{int(bool(cfg.get('vol_scaled')))}"
    return base + (f"g{lag}" if lag else "")  # Lag nur anhängen, wenn aktiv (Alt-Fingerprints stabil)


def _forward_compute(rows, capital: float = 10000.0) -> dict:
    """Pure: rows = [(day, ret, config_fp), ...] aufsteigend -> OOS-Kennzahlen (testbar ohne DB)."""
    rows = [r for r in rows if r is not None]
    if not rows:
        return {"days": 0, "note": "Forward-Track leer — füllt sich ab dem ersten Tag nach Aktivierung "
                                   "(realisierte OOS-Rendite/Tag des Live-Signals, kein Re-Fit)."}
    rets = [float(r[1]) for r in rows]
    eq = []
    e = capital
    for (day, ret, _fp) in rows:
        e *= (1.0 + float(ret))
        eq.append([int(day), round(e, 2)])
    st = mn_base.equity_stats(rets, eq, capital, e)
    configs = sorted({r[2] for r in rows if len(r) > 2 and r[2]})
    return {
        "days": len(rets), "sharpe": st["sharpe"], "psr": st.get("psr"), "ann_pct": st["ann_pct"],
        "total_return_pct": st.get("total_return_pct"), "maxdd_pct": st.get("maxdd_pct"),
        "since": datetime.fromtimestamp(rows[0][0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "configs": configs, "config_changes": max(0, len(configs) - 1),
        "equity": mn_base.downsample(eq, 400),
        "note": "Realisierte OOS-Rendite/Tag (Vortags-Gewichte × Kursmove, kein Re-Fit). "
                "Über Wochen = der ehrliche Live-Test der vol-Skalierung.",
    }


def _forward_record(day: int, realized: float, cfg: dict) -> None:
    """Thin: realisierte Tagesrendite idempotent je Tag festhalten (INSERT OR REPLACE)."""
    with stats._conn() as c:
        _ensure(c)
        c.execute("INSERT OR REPLACE INTO csm_forward(day, ts, ret, config_fp) VALUES(?,?,?,?)",
                  (int(day), datetime.now(timezone.utc).isoformat(), float(realized), _forward_fp(cfg)))


def _forward_stats() -> dict:
    """Thin: DB lesen -> _forward_compute."""
    try:
        with stats._conn() as c:
            _ensure(c)
            rows = c.execute("SELECT day, ret, config_fp FROM csm_forward ORDER BY day").fetchall()
    except Exception:
        rows = []
    return _forward_compute([tuple(r) for r in rows])


# ---------- State / Status ----------
def get_state(equity_points: int = 400) -> dict:
    cfg = get_config()
    syms, ts, closes = _load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "ready": False,
                "note": "Noch keine Preis-Daten. Zuerst POST /api/csm/refresh ausführen (read-only ccxt, einmalig ~1 Min).",
                "config": cfg, "last_refresh": _meta_get("last_refresh")}
    try:
        funding = json.loads(_meta_get("funding_avg") or "{}")
    except Exception:
        funding = {}
    sim = simulate(syms, ts, closes, cfg["lookback"], cfg["hold"], cfg["quantile"], cfg["fee"],
                   cfg["capital"], funding=funding, vol_scaled=cfg.get("vol_scaled", False),
                   signal_lag=int(cfg.get("signal_lag", 0)))
    if not sim.get("ok"):
        return {"ok": False, "ready": False, "config": cfg, **sim}
    # Forward-Tracking: täglichen Demo-Snapshot festhalten (idempotent je Tag).
    try:
        today = (ts[-1] // DAY_MS) * DAY_MS
        with stats._conn() as c:
            _ensure(c)
            c.execute("INSERT OR REPLACE INTO csm_equity_log(day,ts,sharpe,ann_pct,total_return_pct) "
                      "VALUES(?,?,?,?,?)", (today, datetime.now(timezone.utc).isoformat(),
                      sim["sharpe"], sim["ann_pct"], sim["total_return_pct"]))
        with stats._conn() as c:
            track = c.execute("SELECT COUNT(*) FROM csm_equity_log").fetchone()[0]
    except Exception:
        track = 0
    # ECHTER Forward-Track (R13): realisierte Tagesrendite des Live-Signals festhalten + OOS-Kennzahlen lesen.
    try:
        _rets = sim.get("rets") or []
        if _rets:
            _forward_record((ts[-1] // DAY_MS) * DAY_MS, _rets[-1], cfg)
        forward = _forward_stats()
    except Exception:
        forward = {"days": 0}
    eq = mn_base.downsample(sim.pop("equity"), equity_points)  # für die UI ausdünnen
    return {
        "ok": True, "ready": True, "mode": "demo-simulation", "config": cfg,
        "last_refresh": _meta_get("last_refresh"), "forward_track_days": track, "forward": forward,
        "data_from": datetime.fromtimestamp(ts[0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "data_to": datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "stats": {k: sim[k] for k in ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct",
                                      "last_day_return_pct", "days", "n_pairs", "psr")},
        "current": sim["current"], "equity": eq,
        "explainer": "Markt-neutral: long Top-Quantil / short Bottom-Quantil nach Momentum, täglich rebalanciert. "
                     "DEMO-Simulation auf echten Preisen — keine Orders. Echtgeld nur mit ausdrücklicher Freigabe.",
        "caveats": ["Nur Bitget-Überlebende (keine echt-delisteten Coins) -> leicht optimistisch",
                    "Funding als per-Pair-Konstant-Proxy modelliert (~30T-Mittel; Bitget gibt keine Langhistorie)",
                    "Stärke zeitvariabel, ~2 J Historie",
                    "Slippage über die Pauschal-Fee hinaus nicht modelliert -> konservativ sizen",
                    "forward_track_days = Alt-Voll-Sample-Log (täglich neu gefittet, NICHT OOS); der echte "
                    "OOS-Live-Test ist 'forward' (realisierte Rendite/Tag, akkumuliert ab Aktivierung)"],
    }


def status() -> dict:
    """Leichte Zusammenfassung (ohne Equity-Kurve) für Dashboards/Integration."""
    st = get_state(equity_points=1)
    if not st.get("ready"):
        return {"ready": False, "note": st.get("note"), "last_refresh": st.get("last_refresh")}
    return {"ready": True, "mode": "demo-simulation", "stats": st["stats"],
            "longs": [x["symbol"] for x in st["current"]["longs"]],
            "shorts": [x["symbol"] for x in st["current"]["shorts"]],
            "last_refresh": st["last_refresh"]}


# ---------- Lern-Loop (Walk-Forward-Optimierung, proposal-only) ----------
def optimize(windows: int = 3) -> dict:
    """Optimiert die CSM-Parameter (lookback/hold/quantile) per Walk-Forward über N Out-of-Sample-
    Fenster (bester Ø-Sharpe). Proposal-only — Anwenden = set_config(winner)."""
    from . import mn_learn
    cfg = get_config()
    syms, ts, closes = _load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "note": "Keine Preis-Daten (zuerst /api/csm/refresh)."}
    try:
        funding = json.loads(_meta_get("funding_avg") or "{}")
    except Exception:
        funding = {}
    candidates = mn_learn.grid({"lookback": [7, 14, 21, 30], "hold": [1, 2, 3],
                                "quantile": [0.2, 0.3], "vol_scaled": [False, True],
                                "signal_lag": [0, 1]})

    def ev(c, a, b):
        cl = {s: closes[s][a:b] for s in syms}
        sim = simulate(syms, ts[a:b], cl, c["lookback"], c["hold"], c["quantile"],
                       cfg["fee"], cfg["capital"], funding=funding, vol_scaled=c.get("vol_scaled", False),
                       signal_lag=int(c.get("signal_lag", 0)))
        return sim["sharpe"] if sim.get("ok") else None

    baseline = {k: cfg[k] for k in ("lookback", "hold", "quantile", "vol_scaled", "signal_lag")}
    res = mn_learn.walk_forward(ev, len(ts), candidates, windows=windows, baseline=baseline)
    res.update({"ok": True, "engine": "csm", "current_config": baseline})
    return res
