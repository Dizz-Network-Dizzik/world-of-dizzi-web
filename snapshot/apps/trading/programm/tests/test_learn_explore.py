"""Tests: Lern-Loop-Verbesserungen — Random-Search-Startpool, Embargo-Default, Auto-Validierung."""
from backend.app import main, meta

SPECS = [
    {"name": "rsi_period", "min": 5, "max": 30, "default": 14},
    {"name": "stop_loss_pct", "min": 0.5, "max": 5.0, "default": 2.0},
    {"name": "mode", "default": "x"},                      # ohne Spanne -> Default bleibt
]


def test_sample_params_bounds_types_and_count():
    cands = meta.sample_params(SPECS, n=20)
    assert len(cands) == 20
    for c in cands:
        assert 5 <= c["rsi_period"] <= 30 and isinstance(c["rsi_period"], int)   # int-erhaltend, in Spanne
        assert 0.5 <= c["stop_loss_pct"] <= 5.0 and isinstance(c["stop_loss_pct"], float)
        assert c["mode"] == "x"                                                   # ohne min/max -> Default
    # Random-Search: Kandidaten streuen (nicht alle identisch)
    assert len({c["rsi_period"] for c in cands}) > 1


def test_run_optimization_includes_explore_candidates(monkeypatch):
    # Engine + Persistenz mocken -> es zählt nur, WIE VIELE Kandidaten real getestet werden.
    tested = []

    def fake_bt(strategy, params, days=90):
        tested.append(params)
        return {"ok": True, "metrics": {"profit_total_pct": 1.0, "max_drawdown_pct": 2.0,
                                        "total_trades": 10, "winrate_pct": 50.0}}

    monkeypatch.setattr("backend.app.engine.run_backtest_with_params", fake_bt)
    monkeypatch.setattr("backend.app.stats.save_optimization", lambda *a, **k: None)
    r = meta.run_optimization("X", SPECS, days=30, windows=1, explore=4)
    assert len(tested) == 3 + 4                       # 3 Anker (min/default/max) + 4 explorierte
    labels = [x["label"] for x in r["results"]]
    assert sum(1 for l in labels if l.startswith("exploriert")) == 4
    assert r["selection_bias"]["trials"] == 7         # Anti-Overfit-Marge skaliert mit allen Trials


def test_embargo_default_is_one():
    import inspect
    assert inspect.signature(meta.run_optimization).parameters["embargo_days"].default == 1
    assert inspect.signature(meta.run_evolution).parameters["embargo_days"].default == 1


def test_auto_validate_picks_first_unvalidated(monkeypatch):
    monkeypatch.setattr(main.engine, "engine_available", lambda: True)
    monkeypatch.setattr(main.audit, "record", lambda *a, **k: None)
    monkeypatch.setattr(main, "IMPLEMENTED_STRATEGIES", {"Bbb", "Aaa", "Ccc"})
    # Aaa hat schon Evidenz -> Bbb ist die erste unvalidierte
    monkeypatch.setattr(main.stats, "get_strategy_validation",
                        lambda t: {"profit_factor": 1.2} if t == "Aaa" else None)
    called = {}

    def fake_validate(template, days, windows, **kw):
        called["template"] = template
        return {"ok": True, "validated": True}

    monkeypatch.setattr(main, "_validate_strategy", fake_validate)
    res = main._auto_validate_strategy("test")
    assert called["template"] == "Bbb" and res["ran"] is True
    assert res["validated"] is True and res["remaining"] == 1     # Ccc bleibt für den nächsten Tick


def test_auto_validate_noop_when_all_covered(monkeypatch):
    monkeypatch.setattr(main.engine, "engine_available", lambda: True)
    monkeypatch.setattr(main, "IMPLEMENTED_STRATEGIES", {"Aaa"})
    monkeypatch.setattr(main.stats, "get_strategy_validation", lambda t: {"profit_factor": 1.0})
    res = main._auto_validate_strategy("test")
    assert res["ran"] is False
