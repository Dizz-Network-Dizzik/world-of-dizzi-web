"""Tests: anchored Walk-Forward (meta), kausale Pairs-Formation, HMM-Warm-Start (2026-06-10).

Kern der Methodik-Härtung: Kandidaten-Selektion und OOS-Validierung laufen auf GETRENNTEN
Zeitfenstern — das Test-Fenster bleibt frei von Selektions-Bias.
"""
import math
import random

from backend.app import hmm, meta, pairs

SPECS = [
    {"name": "p", "min": 1, "max": 10, "default": 5},
]


# ---------------------------------------------------------------- _anchored_ranges
def test_anchored_ranges_train_before_test_with_embargo():
    rng = meta._anchored_ranges(days=90, windows=3, embargo_days=2)
    tr_start, tr_end = rng["train"].split("-")
    te_start, te_end = rng["test"].split("-")
    assert tr_start < tr_end <= te_start < te_end          # chronologisch, keine Überlappung
    assert rng["test_days"] == 30 and rng["train_days"] == 60
    assert rng["embargo_days"] == 2
    assert rng["total_days"] == 92


def test_anchored_ranges_min_test_window():
    rng = meta._anchored_ranges(days=30, windows=4, embargo_days=0)
    assert rng["test_days"] >= 20                           # Test-Fenster nie unter ~20 Tage


# ---------------------------------------------------------------- run_optimization (anchored)
def _patch_engine(monkeypatch, train_profit, oos_profit, calls):
    """Mockt die Engine: Trainings-Range liefert train_profit je Kandidat (dict param->profit
    oder Konstante), Test-Range liefert oos_profit. Protokolliert alle (timerange, params)."""
    monkeypatch.setattr("backend.app.engine.ensure_data",
                        lambda strategy, timeframe=None, days=120, config_name=None: ("cfg.json", "15m"))

    def fake_range(strategy, params, timerange, timeframe=None, config=None):
        calls.append((timerange, dict(params or {})))
        is_test = timerange == "TEST"
        profit = oos_profit if is_test else (
            train_profit(params) if callable(train_profit) else train_profit)
        return {"ok": True, "metrics": {"profit_total_pct": profit, "max_drawdown_pct": 5.0,
                                        "total_trades": 50, "winrate_pct": 50.0}}

    monkeypatch.setattr("backend.app.engine.run_backtest_range", fake_range)
    monkeypatch.setattr(meta, "_anchored_ranges",
                        lambda days, windows, embargo_days: {
                            "train": "TRAIN", "test": "TEST", "train_days": 60,
                            "test_days": 30, "embargo_days": 1, "total_days": 91})


def test_run_optimization_anchored_selects_on_train_tests_winner_once(monkeypatch):
    saved = {}
    monkeypatch.setattr("backend.app.stats.save_optimization",
                        lambda strat, winner, windows, timeframe=None: saved.update(
                            winner=winner, timeframe=timeframe))
    calls = []
    # Kandidat mit p=10 gewinnt das Training; OOS-Test positiv -> confident.
    _patch_engine(monkeypatch, train_profit=lambda prm: float(prm.get("p", 0)),
                  oos_profit=3.0, calls=calls)
    r = meta.run_optimization("X", SPECS, days=90, windows=2, explore=2)
    train_calls = [c for c in calls if c[0] == "TRAIN"]
    test_calls = [c for c in calls if c[0] == "TEST"]
    assert len(train_calls) == 3 + 2                    # alle Kandidaten NUR auf dem Training
    assert len(test_calls) == 1                          # genau EIN OOS-Test (nur der Gewinner)
    assert test_calls[0][1] == r["winner"]["params"]
    assert r["selection_bias"]["confident"] is True
    assert r["winner"]["oos_validated"] is True
    assert r["winner"]["profit_total_pct"] == 3.0        # nach außen zählt die OOS-Zahl
    assert r["winner"]["train_profit_total_pct"] == 10.0
    assert saved["timeframe"] == "15m" and saved["winner"]["oos_validated"] is True


def test_run_optimization_oos_fail_blocks_confidence(monkeypatch):
    monkeypatch.setattr("backend.app.stats.save_optimization", lambda *a, **k: None)
    calls = []
    _patch_engine(monkeypatch, train_profit=8.0, oos_profit=-2.0, calls=calls)
    r = meta.run_optimization("X", SPECS, days=90, windows=2, explore=1)
    assert r["selection_bias"]["confident"] is False
    assert r["winner"]["oos_validated"] is False
    assert "Overfit" in (r["selection_bias"]["warning"] or "")


def test_run_optimization_windows1_never_confident(monkeypatch):
    monkeypatch.setattr("backend.app.stats.save_optimization", lambda *a, **k: None)
    monkeypatch.setattr("backend.app.engine.run_backtest_with_params",
                        lambda s, p, days=90: {"ok": True, "metrics": {
                            "profit_total_pct": 9.0, "max_drawdown_pct": 2.0,
                            "total_trades": 30, "winrate_pct": 55.0}})
    r = meta.run_optimization("X", SPECS, days=30, windows=1, explore=1)
    assert r["anchored"] is False
    assert r["selection_bias"]["confident"] is False     # In-Sample nie auto-anwendbar
    assert r["winner"]["oos_validated"] is False


def test_run_evolution_generations_train_only_final_oos_once(monkeypatch):
    saved = []
    monkeypatch.setattr("backend.app.stats.save_optimization",
                        lambda strat, winner, windows, timeframe=None: saved.append(winner))
    monkeypatch.setattr("backend.app.engine._find_strategy_config",
                        lambda strategy: ("cfg.json", "15m"))
    calls = []
    # Training honoriert hohe p-Werte; Mutationen um den Gewinner finden bessere -> Evolution greift.
    _patch_engine(monkeypatch, train_profit=lambda prm: float(prm.get("p", 0)), oos_profit=2.5,
                  calls=calls)
    random.seed(7)
    r = meta.run_evolution("X", SPECS, generations=2, days=90, windows=2, pool=3)
    test_calls = [c for c in calls if c[0] == "TEST"]
    # 1 OOS-Test des Basis-Gewinners + höchstens 1 finaler OOS-Test des evolvierten Gewinners
    assert 1 <= len(test_calls) <= 2
    gen_calls = [c for c in calls if c[0] == "TRAIN"]
    assert len(gen_calls) >= 3 + 2 + 3                  # Basis-Kandidaten + 2 Generationen à pool=3
    assert r["winner"]["oos_validated"] in (True, False)
    assert r["anchored"] is True


# ---------------------------------------------------------------- Pairs: kausale Formation
def test_formation_split_bounds():
    ts = [i * pairs.DAY_MS for i in range(400)]
    f = pairs._formation_split(400, ts, 180)
    assert f == 180                                     # 180 Formation-Tage
    f2 = pairs._formation_split(400, ts, 9999)
    assert f2 == 200                                    # Deckel: halbe Historie
    assert pairs._formation_split(30, ts[:30], 180) == 0   # zu kurz -> kein Split


def test_pairs_optimize_eval_requires_formation_data(monkeypatch):
    # Der Eval-Slice ab a=0 hat keine Formation-Daten davor -> None (keine kausale Auswahl möglich).
    T = 360
    ts = [i * pairs.DAY_MS for i in range(T)]
    closes = {"A": [100 + math.sin(i / 9) for i in range(T)],
              "B": [100 + math.sin(i / 9 + 0.1) for i in range(T)],
              "C": [50 + math.cos(i / 7) for i in range(T)],
              "D": [50 + math.cos(i / 7 + 0.1) for i in range(T)]}
    monkeypatch.setattr("backend.app.csm._load_prices",
                        lambda mh: (list(closes), ts, closes))
    res = pairs.optimize(windows=3)
    assert res["ok"] is True
    # anchored: bei 3 Folds ist Fold 1 (a=0) für JEDEN Kandidaten None -> windows<=1 je Kandidat
    assert all(r["windows"] <= 1 for r in res["results"])


# ---------------------------------------------------------------- HMM: Warm-Start/Dual-Init
def _toy_obs(n=120, seed=3):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        regime = (i // 40) % 3
        mu = [-0.5, 0.0, 0.6][regime]
        r = rnd.gauss(mu, 0.3)
        out.append([r, abs(r) + 0.1])
    return out


def test_fit_mv_warm_start_never_worse_than_cold():
    obs = _toy_obs()
    cold = hmm.fit_mv(obs, n_states=3)
    warm = hmm.fit_mv(obs, n_states=3, init=cold)        # Vorgänger-Modell als 2. Init
    assert cold and warm
    assert warm["loglik"] >= cold["loglik"] - 1e-9       # best-of-two per Konstruktion


def test_fit_mv_rejects_incompatible_init():
    obs = _toy_obs()
    bad = {"n_states": 2, "dims": 2, "means": [[0, 0]], "vars": [[1, 1]],
           "start": [1.0], "trans": [[1.0]]}
    m = hmm.fit_mv(obs, n_states=3, init=bad)            # inkompatibel -> still ignoriert
    assert m is not None and m["n_states"] == 3


def test_classify_mv_exposes_model_for_persistence():
    rep = hmm.classify_mv(_toy_obs(), n_states=3)
    assert rep and "model" in rep
    mdl = rep["model"]
    assert mdl["n_states"] == 3 and mdl["dims"] == 2
    assert len(mdl["means"]) == 3 and len(mdl["trans"]) == 3
    # persistiertes Modell ist als Warm-Start wieder einsetzbar
    rep2 = hmm.classify_mv(_toy_obs(seed=4), n_states=3, init=mdl)
    assert rep2 and rep2["regime"] in ("trend_down", "range", "trend_up")
