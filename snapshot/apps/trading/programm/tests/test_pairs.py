"""Tests der Pairs-Spread-Simulation (rein, ohne Netz/DB) — synthetische Daten."""
import math
import random

from backend.app import pairs

DAY = 24 * 60 * 60 * 1000


def _ts(n):
    return [i * DAY for i in range(n)]


def _meanrev_pair(n=600):
    """DOMINANTER gemeinsamer Trend (positive Return-Korrelation) + KLEINER, AR(1)-mean-
    revertierender Log-Spread (stationär um 0). a/b teilen den Trend; log(a/b) kehrt zur Mitte
    zurück -> die Pairs-Engine soll profitieren (Trailing-Mean ≈ 0, gut getimter Z-Score)."""
    common, p = [], 100.0
    a, b, spread = [], [], 0.0
    for i in range(n):
        # gemeinsamer Trend mit ~±3 % Tages-Variation (dominiert die Korrelation)
        cret = 0.02 * math.sin(i * 0.4) + 0.013 * math.sin(i * 0.13 + 1.0)
        p *= (1.0 + cret)
        common.append(p)
        # AR(1)-Spread (mean-reverting um 0): kleine, oszillierende Innovationen
        spread = 0.8 * spread + 0.010 * math.sin(i * 0.9) + 0.008 * math.sin(i * 0.31 + 0.5)
        a.append(round(p * math.exp(spread / 2), 6))
        b.append(round(p * math.exp(-spread / 2), 6))
    return a, b


def test_logrets_corr_positive():
    a, b = _meanrev_pair()
    c = pairs._corr(pairs._logrets(a), pairs._logrets(b))
    assert c is not None and c > 0   # gemeinsamer Trend -> positiv korreliert


def test_select_pairs_picks_correlated():
    a, b = _meanrev_pair()
    noise = [round(100 * (1.0 + 0.01 * math.sin(i * 1.7)), 6) for i in range(len(a))]
    syms = ["A", "B", "C"]
    closes = {"A": a, "B": b, "C": noise}
    sel = pairs.select_pairs(syms, closes, n_pairs=1, min_corr=0.3)
    assert ("A", "B") in sel or ("B", "A") in sel


def test_simulate_profits_on_meanreverting_spread():
    a, b = _meanrev_pair(n=600)
    ts = _ts(len(a))
    sim = pairs.simulate([("A", "B")], ts, {"A": a, "B": b},
                         L=20, entry_z=1.0, exit_z=0.3, fee=0.0, capital=10000.0)
    assert sim["ok"] and sim["days"] > 0
    # Mean-revertierender Spread, 0 Fee -> Strategie muss Geld verdienen (lookahead-frei).
    assert sim["total_return_pct"] > 0


def test_simulate_rejects_too_little_data():
    sim = pairs.simulate([("A", "B")], [0, DAY, 2 * DAY], {"A": [1, 2, 3], "B": [1, 2, 3]},
                         L=20, entry_z=2.0, exit_z=0.5, fee=0.0, capital=100.0)
    assert sim["ok"] is False


def test_config_defaults():
    cfg = dict(pairs.DEFAULTS)
    assert cfg["entry_z"] > cfg["exit_z"] and cfg["n_pairs"] >= 1


def _basket_universe(n_coins=8, days=400):
    """Gemeinsamer Trend + kleine, coin-spezifische mean-revertierende Abweichungen."""
    closes = {}
    common, p = [], 100.0
    for i in range(days):
        p *= (1.0 + 0.015 * math.sin(i * 0.3))
        common.append(p)
    for c in range(n_coins):
        dev = 0.0
        series = []
        for i in range(days):
            dev = 0.85 * dev + 0.012 * math.sin(i * (0.5 + 0.2 * c) + c)
            series.append(round(common[i] * math.exp(dev), 6))
        closes["C%d" % c] = series
    syms = list(closes)
    return syms, _ts(days), closes


def test_simulate_basket_runs_and_is_neutral():
    syms, ts, closes = _basket_universe(8, 400)
    sim = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0, capital=10000.0)
    assert sim["ok"] and sim["days"] > 0
    cur = sim["current"]
    assert len(cur["longs"]) >= 1 and len(cur["shorts"]) >= 1   # markt-neutral: beide Seiten


def test_simulate_basket_rejects_small_universe():
    syms, ts, closes = _basket_universe(4, 100)
    sim = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0, capital=10000.0)
    assert sim["ok"] is False


# ---------- A4: Engle-Granger Kointegrations-Gate (opt-in) ----------
def _noncoint_correlated_pair(n=600, seed=5):
    """Zwei Log-Random-Walks mit GEMEINSAMEM Schock (Return-Korrelation) + UNABHÄNGIGEN
    permanenten Drifts -> der Spread log(a/b) ist selbst ein Random-Walk (NICHT stationär,
    also NICHT kointegriert), obwohl die Returns korrelieren."""
    rng = random.Random(seed)
    a, b, la, lb = [], [], 0.0, 0.0
    for _ in range(n):
        shock = rng.gauss(0.0, 0.012)        # gemeinsam -> Korrelation
        la += shock + rng.gauss(0.0, 0.006)  # unabhängiger permanenter Drift
        lb += shock + rng.gauss(0.0, 0.006)
        a.append(round(100 * math.exp(la), 6))
        b.append(round(100 * math.exp(lb), 6))
    return a, b


def test_ols_hedge_recovers_beta():
    rng = random.Random(1)
    lb = [math.log(100) + 0.01 * i for i in range(200)]
    la = [2.0 + 1.5 * x + rng.gauss(0.0, 0.001) for x in lb]   # la = 2 + 1.5*lb + Rauschen
    alpha, beta = pairs._ols_hedge(la, lb)
    assert abs(beta - 1.5) < 0.05 and abs(alpha - 2.0) < 0.2


def test_adf_tstat_stationary_more_negative_than_randomwalk():
    rng = random.Random(2)
    stat = [0.0]
    for _ in range(400):
        stat.append(0.5 * stat[-1] + rng.gauss(0.0, 1.0))     # AR(1), stationär
    rw = [0.0]
    for _ in range(400):
        rw.append(rw[-1] + rng.gauss(0.0, 1.0))               # Random-Walk, nicht stationär
    t_stat = pairs._adf_tstat(stat)
    t_rw = pairs._adf_tstat(rw)
    assert t_stat is not None and t_rw is not None
    assert t_stat < -3.0          # klar stationär
    assert t_stat < t_rw          # stationär deutlich negativer als Random-Walk


def test_coint_filter_default_off_is_noop():
    a, b = _meanrev_pair()
    syms, closes = ["A", "B"], {"A": a, "B": b}
    off = pairs.select_pairs(syms, closes, n_pairs=1, min_corr=0.3)
    expl = pairs.select_pairs(syms, closes, n_pairs=1, min_corr=0.3, coint_filter=False)
    assert off == expl   # Default == explizit False -> Live unverändert


def test_coint_filter_keeps_cointegrated_pair():
    a, b = _meanrev_pair()
    sel = pairs.select_pairs(["A", "B"], {"A": a, "B": b}, n_pairs=1, min_corr=0.3, coint_filter=True)
    assert ("A", "B") in sel or ("B", "A") in sel   # gemeinsamer Trend + stationärer Spread = kointegriert


def test_coint_filter_rejects_correlated_but_noncointegrated():
    a, b = _noncoint_correlated_pair()
    syms, closes = ["A", "B"], {"A": a, "B": b}
    # korreliert -> ohne Gate ausgewählt; nicht kointegriert -> mit Gate verworfen.
    assert len(pairs.select_pairs(syms, closes, n_pairs=1, min_corr=0.3, coint_filter=False)) == 1
    assert len(pairs.select_pairs(syms, closes, n_pairs=1, min_corr=0.3, coint_filter=True)) == 0


# ---------- A4: StatArb Kosten-/Slippage-Treue (opt-in) ----------
def test_statarb_slippage_default_off_is_noop():
    syms, ts, closes = _basket_universe(8, 400)
    a = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0006, capital=10000.0)
    b = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0006, capital=10000.0, slippage_bps=0.0)
    assert a["total_return_pct"] == b["total_return_pct"] and a["sharpe"] == b["sharpe"]


def test_statarb_slippage_reduces_return():
    syms, ts, closes = _basket_universe(8, 400)
    base = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0006, capital=10000.0)
    slip = pairs.simulate_basket(syms, ts, closes, L=20, Q=0.25, fee=0.0006, capital=10000.0, slippage_bps=10.0)
    assert slip["ok"] and base["ok"]
    assert slip["total_return_pct"] < base["total_return_pct"]   # zusätzliche Kosten schmälern die Rendite
