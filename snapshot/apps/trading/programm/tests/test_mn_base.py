"""Tests der geteilten MN-Basis — Probabilistic Sharpe Ratio + equity_stats (rein)."""
from backend.app import mn_base


def test_psr_bounds_and_more_data_more_certain():
    assert mn_base.psr(0.1, 0.0, 3.0, 2) == 0.0          # n<3 -> 0
    p_short = mn_base.psr(0.1, 0.0, 3.0, 30)
    p_long = mn_base.psr(0.1, 0.0, 3.0, 500)
    assert 0.5 < p_short < p_long <= 1.0                 # positive Sharpe -> >0.5; mehr Daten -> sicherer
    assert mn_base.psr(-0.1, 0.0, 3.0, 500) < 0.5        # negative Sharpe -> <0.5


def test_psr_penalizes_negative_skew_and_fat_tails():
    base = mn_base.psr(0.15, 0.0, 3.0, 200)
    risky = mn_base.psr(0.15, -1.0, 8.0, 200)            # linksschief + fat tails
    assert risky < base                                  # mehr Tail-Risiko -> niedrigere Wahrscheinlichkeit


def test_equity_stats_includes_psr_skew_kurtosis():
    rets = [0.01, -0.004, 0.012, 0.007, -0.002, 0.009] * 40
    eq, v = [], 100.0
    for i, r in enumerate(rets):
        v *= (1.0 + r)
        eq.append([i, round(v, 4)])
    st = mn_base.equity_stats(rets, eq, 100.0, v)
    assert {"psr", "skew", "kurtosis"} <= set(st)
    assert 0.0 <= st["psr"] <= 1.0 and st["psr"] > 0.5   # positiver Drift -> PSR > 0.5
