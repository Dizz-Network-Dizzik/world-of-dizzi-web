"""Tests des markt-neutralen Walk-Forward-Optimierers (rein, ohne Netz/DB)."""
from backend.app import mn_learn


def test_equal_folds_basic():
    folds = mn_learn.equal_folds(600, 3)
    assert len(folds) == 3
    assert folds[0][0] == 0 and folds[-1][1] == 600
    # lückenlos & aufsteigend
    for i in range(1, len(folds)):
        assert folds[i][0] == folds[i - 1][1]


def test_equal_folds_shrinks_when_small():
    # zu wenig Tage -> weniger Fenster (mind. ~90 je Fenster)
    assert len(mn_learn.equal_folds(120, 5)) <= 2
    assert len(mn_learn.equal_folds(80, 3)) == 1


def test_grid_cartesian():
    g = mn_learn.grid({"a": [1, 2], "b": [3, 4, 5]})
    assert len(g) == 6
    assert {"a": 1, "b": 3} in g and {"a": 2, "b": 5} in g


def test_walk_forward_picks_best():
    cands = mn_learn.grid({"x": [0.1, 0.5, 0.9]})
    # Sharpe = x (höher besser), unabhängig vom Fenster
    res = mn_learn.walk_forward(lambda c, a, b: c["x"], T=600, candidates=cands, windows=3)
    assert res["winner"]["params"]["x"] == 0.9
    assert res["winner"]["avg_sharpe"] == 0.9
    assert res["folds"] == 3 and res["candidates"] == 3
    # anchored: 2 Selektions-Folds, jüngster Fold = OOS-Test nur für den Gewinner
    assert res["selection_folds"] == 2
    assert res["winner"]["oos_sharpe"] == 0.9 and res["winner"]["oos_validated"] is True


def test_walk_forward_all_none():
    res = mn_learn.walk_forward(lambda c, a, b: None, T=600, candidates=[{"x": 1}], windows=2)
    assert res["winner"] is None


def test_walk_forward_tiebreak_worst_case():
    # zwei Kandidaten gleicher Ø, aber unterschiedlicher Worst-Case -> robusterer gewinnt.
    # windows=4 (T=600 -> 4 Folds gehen nicht, 600//4=150 >= 90 -> ok): 3 Selektions-Folds + 1 OOS.
    folds_score = {"A": [1.0, 1.0, 1.0], "B": [1.5, 1.0, 0.5]}   # beide Ø=1.0 über die Selektion
    res = mn_learn.walk_forward(
        lambda c, a, b: folds_score[c["k"]].pop(0) if folds_score[c["k"]] else 0.7,
        T=600, candidates=[{"k": "A"}, {"k": "B"}], windows=4)
    assert res["selection_folds"] == 3
    assert res["winner"]["params"]["k"] == "A"   # höherer Worst-Case (1.0 > 0.5)
    assert res["winner"]["oos_sharpe"] == 0.7    # OOS-Test lief NUR für den Gewinner


def test_walk_forward_oos_only_for_winner():
    # Der jüngste Fold darf NIE in die Selektion fließen: Kandidat B wäre dort top,
    # ist aber auf den Selektions-Folds schwächer -> A gewinnt, B bleibt ungetestet.
    def ev(c, a, b):
        is_last = b == 600
        if c["k"] == "B":
            return 9.9 if is_last else 0.1
        return 0.5
    res = mn_learn.walk_forward(ev, T=600, candidates=[{"k": "A"}, {"k": "B"}], windows=3)
    assert res["winner"]["params"]["k"] == "A"
    assert res["winner"]["oos_sharpe"] == 0.5


def test_walk_forward_single_fold_has_no_validation_claim():
    # Nur 1 Fold (zu wenig Historie): kein OOS-Test möglich -> oos_validated=None (kein Anspruch).
    res = mn_learn.walk_forward(lambda c, a, b: 1.0, T=80, candidates=[{"x": 1}], windows=3)
    assert res["folds"] == 1 and res["winner"]["oos_validated"] is None


def test_walk_forward_baseline_blocks_regression():
    # Gewinner ist auf den älteren Folds top, aber auf dem OOS-Fold SCHWÄCHER als die laufende
    # Config -> oos_validated kann True sein, apply_recommended muss False bleiben (keine Regression).
    def ev(c, a, b):
        is_last = b == 600
        if c["k"] == "W":            # Kandidat: stark in Selektion, mau (aber >0) im OOS
            return 0.2 if is_last else 5.0
        return 0.0                   # andere Kandidaten chancenlos
    base = {"k": "BASE"}             # laufende Config: im OOS klar besser
    ev2 = lambda c, a, b: (1.5 if (c.get("k") == "BASE" and b == 600) else ev(c, a, b))
    res = mn_learn.walk_forward(ev2, T=600, candidates=[{"k": "W"}, {"k": "X"}],
                                windows=3, baseline=base)
    w = res["winner"]
    assert w["params"]["k"] == "W"
    assert w["oos_sharpe"] == 0.2 and w["oos_validated"] is True   # absolut OOS-positiv
    assert w["baseline_oos_sharpe"] == 1.5
    assert w["improved_vs_current"] is False                       # schlägt den Status quo NICHT
    assert w["apply_recommended"] is False                         # -> nicht zum Anwenden empfohlen


def test_walk_forward_baseline_allows_genuine_improvement():
    # Gewinner schlägt die laufende Config auch im OOS -> apply_recommended True.
    def ev(c, a, b):
        return 2.0 if c["k"] == "W" else (0.5 if c.get("k") == "BASE" else 0.1)
    res = mn_learn.walk_forward(ev, T=600, candidates=[{"k": "W"}, {"k": "Y"}],
                                windows=3, baseline={"k": "BASE"})
    w = res["winner"]
    assert w["params"]["k"] == "W"
    assert w["improved_vs_current"] is True and w["apply_recommended"] is True
