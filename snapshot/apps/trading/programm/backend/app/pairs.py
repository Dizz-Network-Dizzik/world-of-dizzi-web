"""pairs.py — Pairs-Trading (Spread-Mean-Reversion), markt-neutral, DEMO/Simulation.

Eigenständige Engine NEBEN Freqtrade (2-Bein-marktneutral passt NICHT in dessen Per-Pair-
Modell — gleiches Muster wie ``csm.py``). Wählt korrelierte Krypto-Paare und handelt deren
**Spread** (Log-Ratio, Z-Score): long das relativ schwache / short das relativ starke Bein bei
``|z| > entry_z``, schließt bei ``|z| < exit_z``. Dollar-neutral je Paar → richtungs-neutral.

NUR Simulation auf echten Tages-Closes — teilt sich die Datenbasis mit CSM (``csm_prices``),
also **0 echtes Risiko, keine Orders**. Echtgeld-Ausführung (M6) = ausdrückliche Freigabe.
Simulation in reinem Python (lookahead-frei, testbar). Caveats wie CSM (nur Bitget-Überlebende,
~2 J Historie, Stärke zeitvariabel, Slippage nur pauschal).
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone

from . import csm, mn_base, mn_learn

DAY_MS = mn_base.DAY_MS

DEFAULTS = {
    "lookback": 30,      # Z-Score-Fenster in Tagen
    "entry_z": 2.0,      # Einstieg, wenn |z| >= entry_z
    "exit_z": 0.5,       # Ausstieg (Konvergenz), wenn |z| <= exit_z
    "n_pairs": 8,        # Anzahl gehandelter Paare (höchste Korrelation)
    "min_corr": 0.5,     # Mindest-Return-Korrelation für ein Paar
    "fee": 0.0006,       # Gebühr/Seite auf Turnover
    "min_history": 300,  # Mindest-Tage Historie je Symbol (wie CSM)
    "capital": 10000.0,  # Demo-Startkapital (USDT)
    "formation_days": 180,  # Formation-Phase: Paar-Auswahl NUR aus diesen ersten Tagen (kausal)
    "coint_filter": False,  # Engle-Granger-Kointegrations-Gate ZUSÄTZLICH zur Korrelation (opt-in,
                            # default AUS = Live unverändert). Verlangt ein stationäres OLS-Hedge-
                            # Residuum (DF-t ≤ coint_adf_max) — echte Kointegration statt nur Korrelation.
                            # docs/47 §2-Feinschliff, proposal-only/OOS. Aktivieren = {"coint_filter":true}.
    "coint_adf_max": -3.34, # Schwelle der DF-t-Statistik des OLS-Residuums (negativer = strenger).
                            # -3.34 = Engle-Granger/Phillips-Ouliaris 5%-Kritikwert (1 Regressor + Konstante):
                            # für RESIDUUM-basierte Tests strenger als der reine DF-Wert (≈-2.9), weil das
                            # Hedge-Ratio geschätzt ist (sonst würden Schein-Paare durchrutschen).
}


def get_config() -> dict:
    return mn_base.config_get(DEFAULTS, "pairs_config")


def set_config(patch: dict) -> dict:
    return mn_base.config_set(DEFAULTS, "pairs_config", patch)


# ---------- Hilfen (rein, testbar) ----------
def _ffill(series: list) -> list:
    out, last = [], None
    for v in series:
        if v is None:
            out.append(last)
        else:
            out.append(v)
            last = v
    return out


def _logrets(series: list) -> list:
    out, prev = [], None
    for v in series:
        if v and prev and v > 0 and prev > 0:
            out.append(math.log(v / prev))
        else:
            out.append(None)
        if v:
            prev = v
    return out


def _corr(a: list, b: list) -> float | None:
    xy = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(xy) < 20:
        return None
    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in xy)
    return cov / (sx * sy)


def _ols_hedge(la: list, lb: list) -> tuple[float, float] | None:
    """Engle-Granger Schritt 1: OLS von Log-Preis A auf Log-Preis B (mit Konstante) →
    (alpha, beta). beta = Hedge-Ratio. Rein (Kovarianz/Varianz), kein numpy."""
    xy = [(a, b) for a, b in zip(la, lb) if a is not None and b is not None]
    if len(xy) < 20:
        return None
    xs = [b for _, b in xy]   # Regressor = Log-Preis B
    ys = [a for a, _ in xy]   # Ziel = Log-Preis A
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vb = sum((x - mx) ** 2 for x in xs)
    if vb <= 0:
        return None
    beta = sum((b - mx) * (a - my) for a, b in xy) / vb   # cov(A,B)/var(B); b=Regressor, a=Ziel
    alpha = my - beta * mx
    return alpha, beta


def _adf_tstat(resid: list) -> float | None:
    """Engle-Granger Schritt 2: Dickey-Fuller-t-Statistik (mit Konstante, keine Augmentation)
    auf dem Residuum. Δr_t = c + rho·r_{t-1} + e; t = rho / se(rho). Stark NEGATIV = stationär
    = kointegriert. Rein-Python OLS auf zwei Regressoren [1, r_{t-1}]."""
    r = [v for v in resid if v is not None]
    n = len(r)
    if n < 25:
        return None
    x = r[:-1]                                   # r_{t-1}
    y = [r[i] - r[i - 1] for i in range(1, n)]   # Δr_t
    m = len(y)
    mx = sum(x) / m
    my = sum(y) / m
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return None
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(m))
    rho = sxy / sxx                              # Steigung (mit Konstante = zentrierte Schätzung)
    c = my - rho * mx
    rss = sum((y[i] - (c + rho * x[i])) ** 2 for i in range(m))
    dof = m - 2
    if dof <= 0:
        return None
    se = (rss / dof / sxx) ** 0.5
    if se <= 0:
        return None
    return rho / se


def _formation_split(T: int, ts: list[int], formation_days: int) -> int:
    """Index-Schnitt der Formation-Phase: die ersten ``formation_days`` Tage dienen NUR der
    Paar-Auswahl, gehandelt/bewertet wird erst danach (kausal — die Auswahl sieht keine
    Bewertungsdaten). Gedeckelt auf die halbe Historie, mind. 20 Tage."""
    if T < 40:
        return 0
    limit = ts[0] + max(0, int(formation_days)) * DAY_MS
    f = sum(1 for t in ts if t < limit)
    return max(20, min(f, T // 2))


def _is_cointegrated(closes: dict, a: str, b: str, adf_max: float) -> bool:
    """Engle-Granger-Gate für ein Paar: OLS-Hedge-Residuum (Log-Preise) stationär?
    Schritt 1 (_ols_hedge) → Schritt 2 (_adf_tstat ≤ adf_max). Undefiniert ⇒ nicht bestanden."""
    la = [math.log(v) if (v and v > 0) else None for v in _ffill(list(closes[a]))]
    lb = [math.log(v) if (v and v > 0) else None for v in _ffill(list(closes[b]))]
    h = _ols_hedge(la, lb)
    if h is None:
        return False
    alpha, beta = h
    resid = [(la[t] - (alpha + beta * lb[t])) if (la[t] is not None and lb[t] is not None) else None
             for t in range(len(la))]
    tstat = _adf_tstat(resid)
    return tstat is not None and tstat <= adf_max


def select_pairs(syms: list[str], closes: dict, n_pairs: int, min_corr: float,
                 coint_filter: bool = False, coint_adf_max: float = -3.34) -> list[tuple]:
    """Wählt die n_pairs am stärksten korrelierten Symbol-Paare (Return-Korrelation),
    ohne ein Symbol zu oft wiederzuverwenden (kein Klumpenrisiko auf einem Coin).
    WICHTIG (kausal): nur mit Formation-Daten füttern (``_formation_split``) — eine Auswahl
    über die volle Historie würde die Bewertungs-Periode in die Selektion leaken.
    ``coint_filter`` (opt-in): verlangt ZUSÄTZLICH ein stationäres Engle-Granger-Hedge-Residuum
    (echte Kointegration statt nur Korrelation) — alles weiterhin nur aus den Formation-Daten."""
    lr = {s: _logrets(closes[s]) for s in syms}
    cand = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            c = _corr(lr[syms[i]], lr[syms[j]])
            if c is not None and c >= min_corr:
                cand.append((c, syms[i], syms[j]))
    cand.sort(reverse=True)
    used: dict[str, int] = {}
    out: list[tuple] = []
    for c, a, b in cand:
        if used.get(a, 0) >= 2 or used.get(b, 0) >= 2:
            continue
        if coint_filter and not _is_cointegrated(closes, a, b, coint_adf_max):
            continue   # korreliert, aber NICHT kointegriert -> überspringen (kein stabiler Spread)
        out.append((a, b))
        used[a] = used.get(a, 0) + 1
        used[b] = used.get(b, 0) + 1
        if len(out) >= n_pairs:
            break
    return out


# ---------- Simulation (rein, lookahead-frei) ----------
def simulate(pairs: list[tuple], ts: list[int], closes: dict,
             L: int, entry_z: float, exit_z: float, fee: float, capital: float) -> dict:
    T = len(ts)
    if not pairs or T < L + 5:
        return {"ok": False, "error": "zu wenig Daten/Paare für die Simulation"}
    C = {s: _ffill(list(closes[s])) for s in {x for pr in pairs for x in pr}}
    spreads = {}
    for a, b in pairs:
        sp = []
        for t in range(T):
            va, vb = C[a][t], C[b][t]
            sp.append(math.log(va / vb) if (va and vb and va > 0 and vb > 0) else None)
        spreads[(a, b)] = sp

    pos = {pr: 0 for pr in pairs}      # +1 long spread (long a/short b), -1 short spread
    zlast = {pr: 0.0 for pr in pairs}
    alloc = 1.0 / len(pairs)
    eq = capital
    equity, rets = [], []
    start = L + 1
    for t in range(start, T):
        day_ret, cost = 0.0, 0.0
        for pr in pairs:
            a, b = pr
            # 1) Rendite der am Vortag gesetzten Position bei t realisieren (kein Lookahead).
            if pos[pr] != 0 and C[a][t - 1] and C[b][t - 1] and C[a][t] and C[b][t]:
                ra = C[a][t] / C[a][t - 1] - 1.0
                rb = C[b][t] / C[b][t - 1] - 1.0
                day_ret += alloc * pos[pr] * 0.5 * (ra - rb)   # dollar-neutral (je Bein 50 %)
            # 2) Z-Score aus dem Fenster BIS t -> neue Position gilt ab t+1.
            window = [spreads[pr][k] for k in range(t - L, t) if spreads[pr][k] is not None]
            sp_t = spreads[pr][t]
            if sp_t is None or len(window) < max(5, L // 2):
                continue
            m = sum(window) / len(window)
            sd = statistics.pstdev(window) if len(window) > 1 else 0.0
            z = (sp_t - m) / sd if sd > 0 else 0.0
            zlast[pr] = z
            new = pos[pr]
            if pos[pr] == 0:
                if z <= -entry_z:
                    new = 1
                elif z >= entry_z:
                    new = -1
            elif abs(z) <= exit_z:
                new = 0
            if new != pos[pr]:
                cost += fee * alloc          # Turnover-Gebühr (Wechsel)
                pos[pr] = new
        net = day_ret - cost
        eq *= (1.0 + net)
        equity.append([ts[t], round(eq, 2)])
        rets.append(net)

    active = [{"pair": f"{a}~{b}", "side": ("long-spread" if pos[(a, b)] > 0 else "short-spread"),
               "z": round(zlast[(a, b)], 2)} for (a, b) in pairs if pos[(a, b)] != 0]
    return {
        "ok": True, "n_pairs": len(pairs), **mn_base.equity_stats(rets, equity, capital, eq),
        "equity": equity, "active": active,
        "pairs": [f"{a}~{b}" for a, b in pairs],
    }


# ---------- State / Status ----------
def get_state(equity_points: int = 400) -> dict:
    cfg = get_config()
    syms, ts, closes = csm._load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "ready": False, "config": cfg,
                "note": "Noch keine Preis-Daten. Zuerst POST /api/csm/refresh ausführen "
                        "(read-only ccxt; Pairs teilt sich die Datenbasis mit CSM).",
                "last_refresh": csm._meta_get("last_refresh")}
    # Kausale Trennung: Paar-Auswahl NUR aus der Formation-Phase, Simulation/Statistik erst danach.
    f = _formation_split(len(ts), ts, int(cfg.get("formation_days", 180)))
    pairs = select_pairs(syms, {s: closes[s][:f] for s in syms}, cfg["n_pairs"], cfg["min_corr"],
                         coint_filter=bool(cfg.get("coint_filter")),
                         coint_adf_max=float(cfg.get("coint_adf_max", -3.34)))
    if not pairs:
        return {"ok": False, "ready": False, "config": cfg,
                "note": ("Keine ausreichend korrelierten" + (" + kointegrierten" if cfg.get("coint_filter") else "")
                         + " Paare gefunden (min_corr senken" + (" / coint_filter lockern" if cfg.get("coint_filter") else "") + "?).")}
    sim = simulate(pairs, ts[f:], {s: closes[s][f:] for s in syms},
                   cfg["lookback"], cfg["entry_z"], cfg["exit_z"], cfg["fee"], cfg["capital"])
    if not sim.get("ok"):
        return {"ok": False, "ready": False, "config": cfg, **sim}
    eq = mn_base.downsample(sim.pop("equity"), equity_points)
    return {
        "ok": True, "ready": True, "mode": "demo-simulation", "config": cfg,
        "last_refresh": csm._meta_get("last_refresh"),
        "data_from": datetime.fromtimestamp(ts[0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "data_to": datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "formation_until": datetime.fromtimestamp(ts[max(0, f - 1)] / 1000,
                                                  timezone.utc).strftime("%Y-%m-%d"),
        "stats": {k: sim[k] for k in ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct",
                                      "last_day_return_pct", "days", "n_pairs", "psr")},
        "pairs": sim["pairs"], "active": sim["active"], "equity": eq,
        "explainer": "Markt-neutral: handelt den Spread korrelierter Paare (long schwaches / short "
                     "starkes Bein, Z-Score-Mean-Reversion). Paar-Auswahl kausal aus der Formation-"
                     "Phase, Statistik erst danach. DEMO-Simulation auf echten Preisen — keine Orders.",
        "caveats": ["Nur Bitget-Überlebende -> leicht optimistisch",
                    "Kointegration ist instabil -> Paar-Auswahl periodisch prüfen",
                    "Edge schwindet mit Crowding; Slippage nur pauschal (Fee) modelliert"],
    }


def status() -> dict:
    st = get_state(equity_points=1)
    if not st.get("ready"):
        return {"ready": False, "note": st.get("note"), "last_refresh": st.get("last_refresh")}
    return {"ready": True, "mode": "demo-simulation", "stats": st["stats"],
            "pairs": st["pairs"], "active": st["active"], "last_refresh": st["last_refresh"]}


# ======================= Statistical-Arbitrage (Korb-Reversion) =======================
# Cross-Sectional-Mean-Reversion: jedes Symbol vs. Korb-Mittel (gleichgewichtet); long die
# Nachzuegler (relativ guenstig, niedriger Z), short die Ausreisser (relativ teuer). Markt-
# neutral (dollar-neutral), taeglich rebalanciert. Spiegel von CSM, aber Mean-Reversion auf
# dem relativen (entmittelten) Log-Preis statt Momentum auf Roh-Returns.
STATARB_DEFAULTS = {
    "lookback": 20,       # Z-Score-Fenster (Tage)
    "quantile": 0.2,      # Anteil je Seite (Long-Nachzuegler / Short-Ausreisser)
    "fee": 0.0006,
    "slippage_bps": 0.0,  # Zusätzliche Slippage je Turnover in Basispunkten (opt-in, default 0 =
                          # Live unverändert). Kosten-Treue über die Pauschal-Fee hinaus — die
                          # Korb-Reversion handelt viele Beine, da zählt jeder bp. docs/47 §2, OOS.
    "min_history": 300,
    "capital": 10000.0,
}


def get_statarb_config() -> dict:
    return mn_base.config_get(STATARB_DEFAULTS, "statarb_config")


def set_statarb_config(patch: dict) -> dict:
    return mn_base.config_set(STATARB_DEFAULTS, "statarb_config", patch)


def simulate_basket(syms: list[str], ts: list[int], closes: dict,
                    L: int, Q: float, fee: float, capital: float,
                    slippage_bps: float = 0.0) -> dict:
    T, N = len(ts), len(syms)
    if T < L + 3 or N < 6:
        return {"ok": False, "error": "zu wenig Daten/Symbole für die Korb-Simulation"}
    turnover_cost = fee + max(0.0, float(slippage_bps)) / 1e4   # Fee + opt. Slippage je Turnover-Einheit
    C = [_ffill(list(closes[s])) for s in syms]
    LOG = [[(math.log(C[i][t]) if C[i][t] and C[i][t] > 0 else None) for t in range(T)] for i in range(N)]
    basket = []
    for t in range(T):
        vals = [LOG[i][t] for i in range(N) if LOG[i][t] is not None]
        basket.append(sum(vals) / len(vals) if vals else None)
    REL = [[(LOG[i][t] - basket[t]) if (LOG[i][t] is not None and basket[t] is not None) else None
            for t in range(T)] for i in range(N)]

    w = [0.0] * N
    w_prev = [0.0] * N
    eq = capital
    equity, rets = [], []
    longs, shorts, zlast = [], [], {}
    start = L + 1
    for t in range(start, T):
        pr = 0.0
        for i in range(N):
            if w[i] and C[i][t - 1] and C[i][t]:
                pr += w[i] * (C[i][t] / C[i][t - 1] - 1.0)
        z = [None] * N
        for i in range(N):
            win = [REL[i][k] for k in range(t - L, t) if REL[i][k] is not None]
            if REL[i][t] is None or len(win) < max(5, L // 2):
                continue
            m = sum(win) / len(win)
            sd = statistics.pstdev(win) if len(win) > 1 else 0.0
            z[i] = (REL[i][t] - m) / sd if sd > 0 else 0.0
        valid = [i for i in range(N) if z[i] is not None]
        cost = 0.0
        if len(valid) >= 6:
            order = sorted(valid, key=lambda i: z[i])     # aufsteigend: niedrigster Z = Nachzuegler
            k = max(1, int(Q * len(valid)))
            lo, hi = order[:k], order[-k:]
            neww = [0.0] * N
            for i in lo:
                neww[i] = 0.5 / len(lo)                    # long Nachzuegler
            for i in hi:
                neww[i] = -0.5 / len(hi)                   # short Ausreisser
            cost = turnover_cost * sum(abs(neww[i] - w_prev[i]) for i in range(N))
            w = neww
            w_prev = list(w)
            longs = [syms[i] for i in lo]
            shorts = [syms[i] for i in hi]
            zlast = {syms[i]: round(z[i], 2) for i in valid}
        net = pr - cost
        eq *= (1.0 + net)
        equity.append([ts[t], round(eq, 2)])
        rets.append(net)

    return {
        "ok": True, "n_pairs": N, **mn_base.equity_stats(rets, equity, capital, eq),
        "equity": equity,
        "current": {"longs": [{"symbol": s, "z": zlast.get(s)} for s in longs],
                    "shorts": [{"symbol": s, "z": zlast.get(s)} for s in shorts],
                    "per_side_weight_pct": round(50.0 / max(1, len(longs)), 2)},
    }


def get_statarb_state(equity_points: int = 400) -> dict:
    cfg = get_statarb_config()
    syms, ts, closes = csm._load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "ready": False, "config": cfg,
                "note": "Noch keine Preis-Daten. Zuerst POST /api/csm/refresh (Daten teilen sich mit CSM).",
                "last_refresh": csm._meta_get("last_refresh")}
    sim = simulate_basket(syms, ts, closes, cfg["lookback"], cfg["quantile"], cfg["fee"], cfg["capital"],
                          slippage_bps=float(cfg.get("slippage_bps", 0.0)))
    if not sim.get("ok"):
        return {"ok": False, "ready": False, "config": cfg, **sim}
    eq = mn_base.downsample(sim.pop("equity"), equity_points)
    return {
        "ok": True, "ready": True, "mode": "demo-simulation", "config": cfg,
        "last_refresh": csm._meta_get("last_refresh"),
        "data_from": datetime.fromtimestamp(ts[0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "data_to": datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "stats": {k: sim[k] for k in ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct",
                                      "last_day_return_pct", "days", "n_pairs", "psr")},
        "current": sim["current"], "equity": eq,
        "explainer": "Markt-neutral: jedes Symbol vs. Korb-Mittel — long Nachzügler (niedriger Z) / "
                     "short Ausreißer (hoher Z), Mean-Reversion, täglich rebalanciert. DEMO — keine Orders.",
        "caveats": ["Nur Bitget-Überlebende -> leicht optimistisch",
                    "Faktor-/Regime-Risiko; Selektions-Bias über viele Kombinationen beachten",
                    "Slippage nur pauschal (Fee) modelliert"],
    }


def statarb_status() -> dict:
    st = get_statarb_state(equity_points=1)
    if not st.get("ready"):
        return {"ready": False, "note": st.get("note"), "last_refresh": st.get("last_refresh")}
    return {"ready": True, "mode": "demo-simulation", "stats": st["stats"],
            "current": st["current"], "last_refresh": csm._meta_get("last_refresh")}


# ---------- Lern-Loop (Walk-Forward-Optimierung, proposal-only) ----------
def optimize(windows: int = 3) -> dict:
    """Optimiert die Pairs-Parameter (lookback/entry_z/exit_z) per anchored Walk-Forward.
    Die Paar-Auswahl je Fold ist **kausal**: nur Daten VOR dem Bewertungs-Slice (rollierende
    Formation, gecacht je Schnittpunkt). Proposal-only — Anwenden = set_config(winner)."""
    cfg = get_config()
    syms, ts, closes = csm._load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "note": "Keine Preis-Daten (zuerst /api/csm/refresh)."}
    candidates = mn_learn.grid({"lookback": [20, 30, 45], "entry_z": [1.5, 2.0, 2.5], "exit_z": [0.3, 0.5]})

    sel_cache: dict[int, list] = {}   # Paar-Auswahl ist kandidaten-unabhängig -> 1x je Schnittpunkt

    def _pairs_before(a: int) -> list[tuple]:
        if a not in sel_cache:
            sel_cache[a] = select_pairs(syms, {s: closes[s][:a] for s in syms},
                                        cfg["n_pairs"], cfg["min_corr"],
                                        coint_filter=bool(cfg.get("coint_filter")),
                                        coint_adf_max=float(cfg.get("coint_adf_max", -3.34)))
        return sel_cache[a]

    def ev(c, a, b):
        if a < 60:                    # ohne ausreichende Formation-Daten keine kausale Auswahl
            return None
        prs = _pairs_before(a)
        if not prs:
            return None
        used = {x for pr in prs for x in pr}
        cl = {s: closes[s][a:b] for s in used}
        sim = simulate(prs, ts[a:b], cl, c["lookback"], c["entry_z"], c["exit_z"],
                       cfg["fee"], cfg["capital"])
        return sim["sharpe"] if sim.get("ok") else None

    baseline = {k: cfg[k] for k in ("lookback", "entry_z", "exit_z")}
    res = mn_learn.walk_forward(ev, len(ts), candidates, windows=windows, baseline=baseline)
    res.update({"ok": True, "engine": "pairs", "current_config": baseline})
    return res


def optimize_statarb(windows: int = 3) -> dict:
    """Optimiert die StatArb-Korb-Parameter (lookback/quantile) per Walk-Forward. Proposal-only."""
    cfg = get_statarb_config()
    syms, ts, closes = csm._load_prices(cfg["min_history"])
    if not syms:
        return {"ok": False, "note": "Keine Preis-Daten (zuerst /api/csm/refresh)."}
    candidates = mn_learn.grid({"lookback": [15, 20, 30, 45], "quantile": [0.15, 0.2, 0.3]})

    def ev(c, a, b):
        cl = {s: closes[s][a:b] for s in syms}
        sim = simulate_basket(syms, ts[a:b], cl, c["lookback"], c["quantile"], cfg["fee"], cfg["capital"],
                              slippage_bps=float(cfg.get("slippage_bps", 0.0)))
        return sim["sharpe"] if sim.get("ok") else None

    baseline = {k: cfg[k] for k in ("lookback", "quantile")}
    res = mn_learn.walk_forward(ev, len(ts), candidates, windows=windows, baseline=baseline)
    res.update({"ok": True, "engine": "statarb", "current_config": baseline})
    return res
