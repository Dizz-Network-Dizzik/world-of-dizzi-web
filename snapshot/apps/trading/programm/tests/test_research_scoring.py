"""Tests des Recherchetool-2.0-Scorings (Sicherheit/Effizienz) — rein, Eigen-Evidenz injiziert."""
from backend.app import ai


def test_security_score_certainty_oos_and_count():
    s = {"certainty": "mittel", "backtest_evidence": "walk-forward über 3 Regime", "backtest_count": 150}
    sc, _basis, val = ai.security_score(s, own={})
    assert sc == 45 + 15 + 10 and val is False        # mittel + OOS-Bonus + >=100 Trades, kein Grounding


def test_security_score_bias_penalty():
    s = {"certainty": "hoch", "backtest_evidence": "nur in-sample, viele Parameter (overfit-Verdacht)"}
    sc, _b, _v = ai.security_score(s, own={})
    assert sc == 70 - 10                               # in-sample/Bias ohne OOS -> Abzug


def test_security_score_grounded_by_own_oos_overrides_low_certainty():
    s = {"certainty": "niedrig", "freqtrade_template": "FuturesBbandsBounce"}
    own = {"futuresbbandsbounce": {"profit_factor": 1.15, "windows": 3}}
    sc, basis, val = ai.security_score(s, own)
    assert val and sc >= 80 and "OOS" in basis         # eigene OOS hebt trotz certainty 'niedrig'


def test_efficiency_score_from_own_pf_overrides_label():
    s = {"freqtrade_template": "MeanReversionRsi", "efficiency": "niedrig"}
    eff, basis = ai.efficiency_score(s, {"meanreversionrsi": {"profit_factor": 1.5, "windows": 2}})
    assert eff == 50 and "PF" in basis                 # PF 1.5 -> 50, ueberschreibt Label 'niedrig'


def test_efficiency_score_label_fallback_with_risk_penalty():
    eff, _b = ai.efficiency_score({"efficiency": "hoch", "risk": "hoch"}, own={})
    assert eff == 72 - 8


def test_match_evidence_fuzzy_and_miss():
    assert ai._match_evidence({"freqtrade_template": "FuturesBbandsBounce"},
                              {"futuresbbandsbounce": {"profit_factor": 1.1}})
    assert ai._match_evidence({"name": "random"}, {"meanreversionrsi": {}}) is None
    assert ai._match_evidence({"freqtrade_template": "(Vorlage folgt)"}, {"x": {}}) is None


def test_attach_scores_adds_fields():
    out = ai.attach_scores([{"certainty": "mittel", "efficiency": "mittel"}], own={})
    assert {"security_score", "efficiency_score", "security_basis", "efficiency_basis",
            "system_validated", "metrics"} <= set(out[0])
    assert out[0]["metrics"] is None                    # ohne Eigen-Evidenz keine Metriken


def test_compute_metrics_expectancy_and_calmar():
    # PF 2.0, Trefferquote 50% -> RR = 2·0.5/0.5 = 2 -> Expectancy = 0.5·2 - 0.5 = 0.5 R
    m = ai.compute_metrics({"profit_factor": 2.0, "winrate_pct": 50.0,
                            "max_drawdown_pct": 10.0, "profit_total_pct": 30.0,
                            "total_trades": 120, "windows": 3})
    assert m["expectancy_r"] == 0.5
    assert m["calmar"] == 3.0                            # 30 / 10
    assert m["significant"] is True                      # >=100 Trades


def test_compute_metrics_none_without_pf():
    assert ai.compute_metrics(None) is None
    assert ai.compute_metrics({"winrate_pct": 50}) is None


def test_efficiency_composite_multi_metric():
    # Starke Evidenz: PF 2.2 (Basis 95) + gute Calmar + positive Expectancy + signifikant + niedrige DD
    own = {"x": {"profit_factor": 2.2, "winrate_pct": 55.0, "max_drawdown_pct": 8.0,
                 "profit_total_pct": 40.0, "total_trades": 200, "windows": 3}}
    eff, basis = ai.efficiency_score({"freqtrade_template": "x"}, own)
    assert eff >= 90 and "Calmar" in basis and "Exp" in basis
    # Schwache Evidenz: PF 1.1, tiefe DD, wenige Trades -> klar gedrückt
    own2 = {"y": {"profit_factor": 1.1, "winrate_pct": 40.0, "max_drawdown_pct": 35.0,
                  "profit_total_pct": 3.0, "total_trades": 40, "windows": 1}}
    eff2, _ = ai.efficiency_score({"freqtrade_template": "y"}, own2)
    assert eff2 < ai.efficiency_score({"freqtrade_template": "x"}, own)[0]
