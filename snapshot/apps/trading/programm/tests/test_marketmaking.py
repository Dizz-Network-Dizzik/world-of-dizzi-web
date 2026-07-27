"""Tests der Avellaneda-Stoikov Market-Making-Simulation (rein, deterministisch via Seed)."""
from backend.app import marketmaking as mm


def test_simulate_structure():
    r = mm.simulate(sigma_daily=0.03, gamma=0.1, k=1.5, A=22, order_size=1, inventory_limit=8,
                    steps=200, episodes=200, rebate_bps=1.0, capital=10000.0, seed=7)
    assert r["ok"] and r["days"] == 200
    for key in ("sharpe", "total_return_pct", "maxdd_pct", "avg_fills_per_session", "avg_peak_inventory"):
        assert key in r


def test_captures_spread_in_idealized_model():
    # Idealisiertes AS-Modell (Mid = Random Walk, keine Adverse-Selection): der MM verdient
    # im Schnitt den Spread -> über viele Sessions strukturell positiv.
    r = mm.simulate(sigma_daily=0.02, gamma=0.08, k=1.2, A=40, order_size=1, inventory_limit=10,
                    steps=200, episodes=400, rebate_bps=1.0, capital=10000.0, seed=3)
    assert r["ok"]
    assert r["avg_fills_per_session"] > 0
    assert r["total_return_pct"] > 0


def test_inventory_respects_limit():
    r = mm.simulate(sigma_daily=0.03, gamma=0.05, k=1.0, A=60, order_size=1, inventory_limit=5,
                    steps=200, episodes=50, rebate_bps=0.0, capital=10000.0, seed=1)
    assert r["ok"]
    assert r["avg_peak_inventory"] <= 5.0001   # Inventar-Limit eingehalten


def test_deterministic_seed():
    a = mm.simulate(0.03, 0.1, 1.5, 22, 1, 8, 150, 100, 1.0, 10000.0, seed=99)
    b = mm.simulate(0.03, 0.1, 1.5, 22, 1, 8, 150, 100, 1.0, 10000.0, seed=99)
    assert a["total_return_pct"] == b["total_return_pct"]   # gleicher Seed -> gleiches Ergebnis


def test_reject_bad_sigma():
    assert mm.simulate(0.0, 0.1, 1.5, 22, 1, 8, 200, 100, 1.0, 10000.0)["ok"] is False


def test_config_defaults():
    assert mm.DEFAULTS["gamma"] > 0 and mm.DEFAULTS["inventory_limit"] >= 1


def test_vol_recal_default_off_is_noop():
    # Default (vol_recal weggelassen) MUSS identisch zu explizit False sein -> Live unverändert.
    a = mm.simulate(0.03, 0.1, 1.5, 22, 1, 8, 200, 200, 1.0, 10000.0, seed=7)
    b = mm.simulate(0.03, 0.1, 1.5, 22, 1, 8, 200, 200, 1.0, 10000.0, seed=7, vol_recal=False)
    assert a["total_return_pct"] == b["total_return_pct"] and a["sharpe"] == b["sharpe"]


def test_vol_recal_changes_quoting():
    # Adaptive Vola-Nachführung quotiert anders als die statische Vola -> anderes Ergebnis (gleicher Seed).
    off = mm.simulate(0.05, 0.1, 1.5, 22, 1, 8, 200, 200, 1.0, 10000.0, seed=7, vol_recal=False)
    on = mm.simulate(0.05, 0.1, 1.5, 22, 1, 8, 200, 200, 1.0, 10000.0, seed=7, vol_recal=True)
    assert off["ok"] and on["ok"]
    assert off["total_return_pct"] != on["total_return_pct"]


def test_ensemble_averages_over_seeds():
    # Seed-Ensemble: gemittelte Sharpe + Seed-Streuung; robuster als ein einzelner Lucky-Seed.
    cfg = {**mm.DEFAULTS, "episodes": 60}   # klein für den Test
    ens = mm._ensemble(0.024, cfg, seeds=(1, 7, 13, 42))
    assert ens is not None
    st = ens["stats"]
    assert st["seeds"] == 4
    assert "sharpe_seed_stdev" in st and st["sharpe_seed_stdev"] >= 0.0
    # Gemittelte Sharpe liegt zwischen Min und Max der Einzelläufe (echtes Mittel).
    singles = [mm.simulate(0.024, cfg["gamma"], cfg["k"], cfg["A"], cfg["order_size"],
                           cfg["inventory_limit"], cfg["steps"], cfg["episodes"],
                           cfg["maker_rebate_bps"], cfg["capital"], cfg["adverse_frac"], seed=s)["sharpe"]
               for s in (1, 7, 13, 42)]
    assert min(singles) - 1e-6 <= st["sharpe"] <= max(singles) + 1e-6
    # repräsentativer Lauf trägt eine Equity-Kurve für die UI.
    assert ens["rep"].get("equity")
