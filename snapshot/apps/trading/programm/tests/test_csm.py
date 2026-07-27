"""Tests der Cross-Sectional-Momentum-Simulation (rein, ohne Netz/DB)."""
from backend.app import csm

DAY = 24 * 60 * 60 * 1000


def _ts(n):
    return [i * DAY for i in range(n)]


def _trend(rate, n, p0=100.0):
    out, p = [], p0
    for _ in range(n):
        out.append(round(p, 6))
        p *= rate
    return out


def _universe(n=60):
    """4 Aufwaerts- + 4 Abwaertstrender mit klar gestaffelten Raten."""
    rates = {"UP0": 1.005, "UP1": 1.008, "UP2": 1.012, "UP3": 1.015,
             "DN0": 0.995, "DN1": 0.992, "DN2": 0.988, "DN3": 0.985}
    return list(rates), _ts(n), {s: _trend(r, n) for s, r in rates.items()}


def test_ranks_longs_winners_shorts_losers():
    syms, ts, closes = _universe()
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert r["ok"]
    longs = {x["symbol"] for x in r["current"]["longs"]}
    shorts = {x["symbol"] for x in r["current"]["shorts"]}
    # Top-2 = staerkste Aufwaerts, Bottom-2 = staerkste Abwaerts (k=int(0.3*8)=2)
    assert longs == {"UP3", "UP2"}
    assert shorts == {"DN3", "DN2"}
    assert longs.isdisjoint(shorts)


def test_dollar_neutral_equal_sides():
    syms, ts, closes = _universe()
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    cur = r["current"]
    assert len(cur["longs"]) == len(cur["shorts"]) >= 1
    # je Seite 50% -> Einzelgewicht = 50/Anzahl
    assert abs(cur["per_side_weight_pct"] - 50.0 / len(cur["longs"])) < 1e-6


def test_trending_universe_is_profitable():
    """Bei klaren Trends muss long-Winner/short-Loser positiv sein (Sanity)."""
    syms, ts, closes = _universe()
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert r["total_return_pct"] > 0
    assert r["sharpe"] > 0


def test_flat_prices_no_edge_no_lookahead():
    """Konstante Preise -> keine Bewegung zum 'vorhersehen' -> Rendite ~0 (nur Mini-Fee)."""
    syms = [f"P{i}" for i in range(8)]
    ts = _ts(60)
    closes = {s: [100.0] * 60 for s in syms}
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert r["ok"]
    assert abs(r["total_return_pct"]) < 1.0  # praktisch null (kein Lookahead-Gewinn aus flachen Preisen)


def _vol_universe(n=80):
    """6 Coins, gleiche Drift paarweise, aber unterschiedliche Tages-Vola (Zacken) —
    damit Risk-adjusted Momentum NACHWEISLICH anders rankt als Roh-Momentum."""
    base = {"A": 1.006, "B": 1.006, "C": 1.004, "D": 1.004, "E": 0.994, "F": 0.994}
    amp = {"A": 0.0, "B": 0.03, "C": 0.0, "D": 0.02, "E": 0.0, "F": 0.025}
    out = {}
    for s, r in base.items():
        p, row = 100.0, []
        for k in range(n):
            row.append(round(p, 6))
            p *= r * (1.0 + (amp[s] if k % 2 == 0 else -amp[s]))
        out[s] = row
    return list(base), _ts(n), out


def test_vol_scaling_default_off_is_noop():
    # Default (vol_scaled weggelassen) MUSS identisch zu explizit False sein -> Live unverändert.
    syms, ts, closes = _universe()
    a = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    b = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, vol_scaled=False)
    assert a["sharpe"] == b["sharpe"] and a["total_return_pct"] == b["total_return_pct"]


def test_vol_scaling_reweights_signal():
    # Risk-adjusted Momentum bevorzugt die ruhigeren Trender -> andere Auswahl/Sharpe als Roh.
    syms, ts, closes = _vol_universe()
    off = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, vol_scaled=False)
    on = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, vol_scaled=True)
    assert off["ok"] and on["ok"]
    longs_off = {x["symbol"] for x in off["current"]["longs"]}
    longs_on = {x["symbol"] for x in on["current"]["longs"]}
    assert longs_off != longs_on or off["sharpe"] != on["sharpe"]


def test_simulate_exposes_realized_rets():
    """get_state braucht die exakte realisierte Tagesrendite (rets[-1]) für den echten Forward-Track."""
    syms, ts, closes = _universe()
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert "rets" in r and len(r["rets"]) == r["days"]
    prod = 1.0
    for x in r["rets"]:
        prod *= (1.0 + x)
    assert abs((prod - 1.0) * 100 - r["total_return_pct"]) < 0.06   # bis auf 1-Dezimal-Rundung exakt
    assert abs(r["rets"][-1] * 100 - r["last_day_return_pct"]) < 1e-6


def test_forward_compute_accumulates_realized_oos():
    """Echter Forward-Track: kumuliert realisierte Tagesrenditen zu einer OOS-Equity (kein Re-Fit)."""
    D = csm.DAY_MS
    rows = [(0 * D, 0.01, "L14H1Q0.3v1"), (1 * D, -0.005, "L14H1Q0.3v1"), (2 * D, 0.02, "L14H1Q0.3v1")]
    f = csm._forward_compute(rows, capital=10000.0)
    assert f["days"] == 3
    assert f["total_return_pct"] == round((1.01 * 0.995 * 1.02 - 1.0) * 100, 1)
    assert f["config_changes"] == 0 and f["configs"] == ["L14H1Q0.3v1"]
    assert f["sharpe"] > 0


def test_forward_compute_empty_has_note():
    f = csm._forward_compute([])
    assert f["days"] == 0 and "note" in f


def test_forward_compute_flags_config_change():
    D = csm.DAY_MS
    rows = [(0 * D, 0.01, "L14H1Q0.3v0"), (1 * D, 0.01, "L14H2Q0.3v1")]
    f = csm._forward_compute(rows)
    assert f["config_changes"] == 1 and len(f["configs"]) == 2


def test_forward_fp_reflects_vol_scaled():
    assert csm._forward_fp({"lookback": 14, "hold": 2, "quantile": 0.3, "vol_scaled": True}).endswith("v1")
    assert csm._forward_fp({"lookback": 14, "hold": 2, "quantile": 0.3, "vol_scaled": False}).endswith("v0")


def test_insufficient_data():
    syms, ts, closes = _universe(n=8)  # < L+3
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert not r["ok"]
    r2 = csm.simulate(["A", "B"], _ts(40), {"A": _trend(1.01, 40), "B": _trend(0.99, 40)},
                      L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    assert not r2["ok"]  # < 6 Pairs


def test_signal_lag_default_off_is_noop():
    # Default (signal_lag weggelassen) MUSS identisch zu explizit 0 sein -> Live unverändert.
    syms, ts, closes = _vol_universe()
    a = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000)
    b = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, signal_lag=0)
    assert a["sharpe"] == b["sharpe"] and a["total_return_pct"] == b["total_return_pct"]


def test_signal_lag_shifts_window():
    # Skip-most-recent: das um lag zurückversetzte Momentum-Fenster ändert Auswahl/Sharpe
    # (auf einem nicht-monoton-trendenden Universum mit oszillierender Vola).
    syms, ts, closes = _vol_universe()
    off = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, signal_lag=0)
    on = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, signal_lag=2)
    assert off["ok"] and on["ok"]
    longs_off = {x["symbol"] for x in off["current"]["longs"]}
    longs_on = {x["symbol"] for x in on["current"]["longs"]}
    assert longs_off != longs_on or off["total_return_pct"] != on["total_return_pct"]


def test_signal_lag_needs_more_history():
    # Mit lag braucht die Sim L+lag+3 Tage; knapp darunter -> nicht ok.
    syms, ts, closes = _universe(n=17)  # L=14, lag=2 -> Bedarf 19 > 17
    r = csm.simulate(syms, ts, closes, L=14, H=1, Q=0.30, fee=0.0006, capital=10000, signal_lag=2)
    assert not r["ok"]


def test_forward_fp_appends_lag_only_when_active():
    base = {"lookback": 14, "hold": 1, "quantile": 0.3, "vol_scaled": False}
    assert csm._forward_fp(base) == csm._forward_fp({**base, "signal_lag": 0})  # 0 = kein Suffix (stabil)
    assert csm._forward_fp({**base, "signal_lag": 1}).endswith("g1")
