"""Tests: Master-Algorithmus (Politik-Ableitung, Versionierung, keep-if-better) — temp DB."""
from backend.app import master, stats


def test_meta_split_mixed_signs_safe():
    """Gemischte Vorzeichen dürfen nicht crashen (Summe=0) oder Anteil außerhalb [0,1] liefern."""
    cfg = {"meta_temp": 0.0, "meta_floor": 0.0}
    # exakt entgegengesetzt -> früher ZeroDivision
    assert master._meta_split(1.0, -1.0, True, cfg) == 0.0          # nur gerichtet hat Edge
    assert master._meta_split(-1.0, 1.0, True, cfg) == 1.0          # nur Sockel hat Edge
    # früher share > 1 möglich (dir<0, mn>0)
    s = master._meta_split(-0.3, 0.5, True, cfg)
    assert 0.0 <= s <= 1.0 and s == 1.0
    # beide negativ -> definierter Fall (kein Edge)
    assert master._meta_split(-1.0, -1.0, True, cfg) in (0.0, 1.0)
    # beide positiv -> proportional, in (0,1)
    s2 = master._meta_split(1.0, 1.0, True, cfg)
    assert 0.0 < s2 < 1.0


def _setup(tmp_path):
    stats.DATA_DIR = tmp_path
    stats.DB_FILE = tmp_path / "t.sqlite"


def _seed(strat, pf, windows=3):
    stats.save_strategy_validation(strat, True, windows, {
        "profit_total_pct": -5.0, "max_drawdown_pct": 5.0, "total_trades": 100,
        "winrate_pct": 50.0, "profit_factor": pf})


def test_derive_policy_has_all_regimes_and_is_honest(tmp_path):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.61)
    _seed("MeanReversionRsi", 0.36)
    _seed("FuturesBbandsBounce", 0.59)
    pol = master.derive_policy()
    assert set(pol["allocations"]) == {"trend_up", "trend_down", "range"}
    # range: Bbands(0.59) schlägt MeanRev(0.36) bei gleichem Regime-Fit
    assert pol["allocations"]["range"]["strategy"] == "FuturesBbandsBounce"
    assert pol["profitable_any"] is False           # alle PF<1 -> ehrlich defensiv
    assert pol["fitness"] is not None


def test_derive_policy_gates_unvalidated_overfit_pf(tmp_path):
    # Eine NICHT-validierte Strategie mit Overfit-PF>3 bei negativer Rendite (z.B. DcaDip 3.49 / −5.9 %)
    # darf KEINEN gerichteten Edge tragen: eff. PF auf <=1 gekappt, nicht profitabel, dir_edge 0.
    _setup(tmp_path)
    stats.save_strategy_validation("DcaDip", False, 3, {
        "profit_total_pct": -5.9, "max_drawdown_pct": 8.0, "total_trades": 50,
        "winrate_pct": 40.0, "profit_factor": 3.49})
    pol = master.derive_policy()
    a = pol["allocations"]["range"]
    assert a["strategy"] == "DcaDip"           # bleibt die Anzeige-Allokation (am wenigsten schlecht)
    assert a["profit_factor"] == 3.49 and a["validated"] is False
    assert a["expected_pf"] <= 1.0             # Edge gekappt -> kein positiver Beitrag
    assert a["profitable"] is False
    assert pol["profitable_any"] is False
    assert pol["ensemble"]["dir_edge"] == 0.0  # keine gerichtete Edge aus einer durchgefallenen Strategie


def test_train_step_versions_and_keeps_better(tmp_path):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.5)
    r1 = master.train_step()
    assert r1["improved"] and r1["version"] >= 1
    r2 = master.train_step()                          # gleiche Evidenz -> keine neue Version
    assert r2["improved"] is False
    _seed("FuturesMacdRsiScalp", 1.4)                 # bessere Evidenz
    r3 = master.train_step()
    assert r3["improved"] and r3["version"] > r1["version"]
    assert master.get_current()["version"] == r3["version"]


def test_confidence_monotonic():
    assert master._confidence({"windows": 3, "profit_factor": 1.5}) > \
           master._confidence({"windows": 1, "profit_factor": 0.3})
    assert master._confidence(None) == 0.0


def test_confidence_penalizes_unvalidated():
    # Gleiche Kennzahlen, aber validated=False -> stark gedämpfte Konfidenz (Gate nicht bestanden).
    val_ok = {"windows": 3, "profit_factor": 1.2, "validated": 1}
    val_failed = {"windows": 3, "profit_factor": 1.2, "validated": 0}
    val_neutral = {"windows": 3, "profit_factor": 1.2}   # kein Flag -> neutral (wie validated=True)
    assert master._confidence(val_failed) < master._confidence(val_ok)
    assert master._confidence(val_ok) == master._confidence(val_neutral)
    assert master._confidence(val_failed) == round(master._confidence(val_ok) * master.UNVALIDATED_CONF_PENALTY, 3)


# ---------- Markt-neutraler Sockel / Ensemble (Schritt 2) ----------
def _fake_engine(ready, sharpe=None, days=720, ann=10.0, maxdd=-5.0):
    def fn():
        if not ready:
            return {"ready": False}
        return {"ready": True, "stats": {"sharpe": sharpe, "days": days,
                                         "ann_pct": ann, "maxdd_pct": maxdd}}
    return fn


def test_sharpe_pf_monotonic_and_floored():
    assert master._sharpe_pf(None) == 1.0          # kein/negativer Edge -> PF 1 (Breakeven)
    assert master._sharpe_pf(-3.0) == 1.0          # negative Sharpe zählt nicht
    assert master._sharpe_pf(6.0) > master._sharpe_pf(3.0) > 1.0


def test_mn_confidence_grows_with_oos_length():
    assert master._mn_confidence({"days": 720}) > master._mn_confidence({"days": 90})
    assert master._mn_confidence({}) == 0.2


def test_mn_sleeve_weights_only_positive_sharpe(monkeypatch):
    # csm +1.4 / mm +6.0 aktiv, pairs -0.5 / statarb nicht bereit -> nur die zwei positiven gewichtet.
    monkeypatch.setattr(master, "MN_ENGINES", [
        ("csm", _fake_engine(True, 1.4)), ("pairs", _fake_engine(True, -0.5)),
        ("statarb", _fake_engine(False)), ("marketmaking", _fake_engine(True, 6.0)),
    ])
    sl = master.mn_sleeve()
    wts = {m["engine"]: m["weight"] for m in sl["members"]}
    assert sl["active"] == 2
    assert wts["pairs"] == 0.0 and wts["statarb"] == 0.0     # Verlierer/nicht-bereit: Gewicht 0
    assert wts["csm"] > 0 and wts["marketmaking"] > wts["csm"]  # höhere Sharpe -> mehr Gewicht
    assert abs(wts["csm"] + wts["marketmaking"] - 1.0) < 1e-6   # auf 1 normiert
    assert sl["edge"] > 0 and sl["sleeve_pf"] > 1.0


def test_ensemble_leans_on_mn_when_directional_unprofitable(tmp_path, monkeypatch):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.6)               # gerichtet: alle PF<1 (unprofitabel)
    monkeypatch.setattr(master, "MN_ENGINES", [
        ("csm", _fake_engine(True, 1.4)), ("marketmaking", _fake_engine(True, 6.0)),
    ])
    pol = master.derive_policy()
    assert pol["profitable_any"] is False
    assert pol["ensemble"]["mn_share"] == 1.0       # kein gerichteter Edge -> Sockel trägt alles
    assert pol["ensemble"]["mn_fitness"] > 0
    assert pol["fitness"] == pol["ensemble"]["mn_fitness"]   # Ensemble-Fitness = Sockel-Fitness


def test_ensemble_no_mn_falls_back_to_directional(tmp_path, monkeypatch):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.6)
    monkeypatch.setattr(master, "MN_ENGINES", [("csm", _fake_engine(False))])  # kein aktiver Sockel
    pol = master.derive_policy()
    assert pol["ensemble"]["mn_share"] == 0.0 and pol["ensemble"]["dir_share"] == 1.0
    assert pol["fitness"] == pol["ensemble"]["dir_fitness"]


# ---------- Meta-Learner-Gewichtung + OOS-Härtung (Iteration nach Option A) ----------
_W = {"sharpe_to_pf": 3.0, "sharpe_haircut": 0.5, "conf_shrink": 1.0, "max_weight": 1.0, "weight_temp": 0.0}


def test_cap_weights_redistributes_excess():
    w = master._cap_weights({"a": 0.8, "b": 0.2}, 0.6)
    assert abs(w["a"] - 0.6) < 1e-9 and abs(w["b"] - 0.4) < 1e-9
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_haircut_drops_sharpe_below_threshold(monkeypatch):
    # csm-Sharpe 0.3 < Haircut 0.5 -> gehärtet 0 -> kein Beitrag; mm bleibt.
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 0.3)), ("marketmaking", _fake_engine(True, 5.0))])
    sl = master.mn_sleeve({**_W})
    wts = {m["engine"]: m["weight"] for m in sl["members"]}
    assert sl["active"] == 1 and wts["csm"] == 0.0 and wts["marketmaking"] == 1.0


def test_max_weight_cap_diversifies(monkeypatch):
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 2.0)), ("marketmaking", _fake_engine(True, 8.0))])
    sl = master.mn_sleeve({**_W, "sharpe_haircut": 0.0, "max_weight": 0.6})
    wts = {m["engine"]: m["weight"] for m in sl["members"]}
    assert wts["marketmaking"] <= 0.6 + 1e-9 and wts["csm"] >= 0.4 - 1e-9   # Dominanz gekappt


def test_sim_discount_scales_only_synthetic_engine(monkeypatch):
    # Struktureller Sim-Discount skaliert die Sharpe NUR der synthetischen Engine (marketmaking),
    # vor der Härtung; real-Preis-Engine (csm) bleibt unberührt.
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 2.0)), ("marketmaking", _fake_engine(True, 6.0))])
    base = {**_W, "sharpe_haircut": 0.0, "deflate_factor": 0.0, "psr_weight": 0.0}
    full = {m["engine"]: m for m in master.mn_sleeve({**base, "sim_discount": 1.0})["members"]}
    disc = {m["engine"]: m for m in master.mn_sleeve({**base, "sim_discount": 0.5})["members"]}
    assert full["csm"]["synthetic"] is False and full["marketmaking"]["synthetic"] is True
    assert disc["csm"]["haircut_sharpe"] == full["csm"]["haircut_sharpe"]      # real-data unberührt
    assert abs(disc["marketmaking"]["haircut_sharpe"] - 3.0) < 1e-6           # 6.0 * 0.5 = 3.0


def test_sim_discount_lowers_sleeve_fitness_at_n1(monkeypatch):
    # Nur MM aktiv (N=1): der Discount muss die SOCKEL-FITNESS senken, nicht bloß ein Gewicht
    # (bei N=1 ist Gewicht trivial 1.0) — sonst wäre er ehrlichkeits-wirkungslos.
    monkeypatch.setattr(master, "MN_ENGINES", [("marketmaking", _fake_engine(True, 6.0))])
    base = {**_W, "sharpe_haircut": 0.5, "deflate_factor": 0.0, "psr_weight": 0.0}
    f_full = master.mn_sleeve({**base, "sim_discount": 1.0})["fitness"]
    f_disc = master.mn_sleeve({**base, "sim_discount": 0.5})["fitness"]
    assert f_disc < f_full


def test_softmax_temperature_smooths_weights(monkeypatch):
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 2.0)), ("marketmaking", _fake_engine(True, 8.0))])
    base = {**_W, "sharpe_haircut": 0.0}
    lin = {m["engine"]: m["weight"] for m in master.mn_sleeve(base)["members"]}
    soft = {m["engine"]: m["weight"] for m in master.mn_sleeve({**base, "weight_temp": 5.0})["members"]}
    # Soft-Voting (hohe Temperatur) glättet -> der Spitzenreiter bekommt weniger als bei linear.
    assert soft["marketmaking"] < lin["marketmaking"]


def test_train_rebaselines_on_methodology_change(tmp_path, monkeypatch):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.6)
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 1.4)), ("marketmaking", _fake_engine(True, 6.0))])
    r1 = master.train_step()
    assert r1["improved"] and not r1["rebaselined"]
    master.set_config({"sharpe_haircut": 2.0})        # härtere Methodik -> Fitness evtl. niedriger
    r2 = master.train_step()
    assert r2["rebaselined"] is True and r2["version"] > r1["version"]   # neu versioniert trotzdem
    r3 = master.train_step()                          # gleiche Methodik + Evidenz -> kein Rebaseline
    assert r3["rebaselined"] is False and r3["improved"] is False


def test_regime_conditioning_prefers_current_regime_strategy(tmp_path):
    _setup(tmp_path)
    _seed("FuturesBbandsBounce", 1.8)        # range-getaggt, stark profitabel
    _seed("FuturesMacdRsiScalp", 1.2)        # trend-getaggt, profitabel (gewinnt sein eigenes Regime)
    pol_range = master.derive_policy(regime="range", regime_conf=0.95)
    pol_trend = master.derive_policy(regime="trend_up", regime_conf=0.95)
    assert pol_range["active_regime"]["allocation"]["strategy"] == "FuturesBbandsBounce"
    assert pol_trend["active_regime"]["allocation"]["strategy"] == "FuturesMacdRsiScalp"
    # range-Strategie profitabler -> gerichtete Fitness im range-Regime höher als im trend-Regime
    assert pol_range["ensemble"]["dir_fitness"] > pol_trend["ensemble"]["dir_fitness"]


def test_regime_conditioning_falls_back_without_snapshot(tmp_path):
    _setup(tmp_path)
    _seed("FuturesMacdRsiScalp", 0.6)
    pol = master.derive_policy()             # kein Snapshot -> kein aktives Regime, Mittel-Sicht
    assert pol["active_regime"]["regime"] is None


def test_regime_read_from_stored_snapshot(tmp_path):
    _setup(tmp_path)
    _seed("FuturesBbandsBounce", 1.5)
    stats.save_market_snapshot("BTC/USDT", 100.0, "range", 0.5,
                               vol_regime="calm", trend_z=0.2, regime_conf=0.9)
    pol = master.derive_policy()             # liest Regime+Konfidenz aus dem Snapshot
    assert pol["active_regime"]["regime"] == "range" and pol["active_regime"]["confidence"] == 0.9


def test_fundamental_overlay_dampens_directional_not_fitness(tmp_path, monkeypatch):
    _setup(tmp_path)
    _seed("FuturesBbandsBounce", 1.8)
    _seed("FuturesMacdRsiScalp", 1.2)
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 1.4)), ("marketmaking", _fake_engine(True, 6.0))])
    monkeypatch.setattr(master, "_fundamental_overlay",
                        lambda: {"available": True, "event_risk": "none", "macro_stance": "neutral", "total_scale": 1.0})
    p0 = master.derive_policy(regime="range", regime_conf=0.9)
    monkeypatch.setattr(master, "_fundamental_overlay",
                        lambda: {"available": True, "event_risk": "high", "macro_stance": "risk_off", "total_scale": 0.4})
    p1 = master.derive_policy(regime="range", regime_conf=0.9)
    assert p1["fundamental"]["event_risk"] == "high"
    # High-Event-Overlay dämpft das gerichtete Sleeve -> effektiv mehr markt-neutraler Sockel
    assert p1["fundamental"]["effective_mn_share"] > p0["fundamental"]["effective_mn_share"]
    # ... aber die persistierte Fitness bleibt unberührt (Overlay ist taktisch, kein Versions-Churn)
    assert p1["fitness"] == p0["fitness"]


def test_regime_anticipation_blends_next_regime(tmp_path):
    _setup(tmp_path)
    _seed("FuturesBbandsBounce", 1.8)        # range stark
    _seed("FuturesMacdRsiScalp", 1.2)        # trend schwächer, gewinnt aber sein Regime
    p_stay = master.derive_policy(regime="range", regime_conf=1.0, next_regime="range", stay_prob=1.0)
    p_switch = master.derive_policy(regime="range", regime_conf=1.0, next_regime="trend_up", stay_prob=0.3)
    assert p_switch["active_regime"]["anticipated"] is True
    assert p_switch["active_regime"]["next_regime"] == "trend_up"
    # antizipierter Wechsel zum schwächeren trend_up zieht die gerichtete Fitness herunter
    assert p_switch["ensemble"]["dir_fitness"] < p_stay["ensemble"]["dir_fitness"]


def test_deflated_sharpe_hardens_sleeve(monkeypatch):
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", _fake_engine(True, 1.0)), ("marketmaking", _fake_engine(True, 6.0))])
    base = {**_W, "deflate_factor": 0.0}
    sl0 = {m["engine"]: m["haircut_sharpe"] for m in master.mn_sleeve(base)["members"]}
    sl1full = master.mn_sleeve({**base, "deflate_factor": 0.6})
    sl1 = {m["engine"]: m["haircut_sharpe"] for m in sl1full["members"]}
    assert sl1full["weighting"]["deflation"] > 0
    assert sl1["csm"] < sl0["csm"] and sl1["marketmaking"] < sl0["marketmaking"]   # strenger gehärtet
    assert sl1["csm"] == 0.0                                                       # schwache Engine fällt raus


def test_meta_split_linear_floor_and_temp():
    lin = {"meta_temp": 0.0, "meta_floor": 0.0}
    assert master._meta_split(0.1, 0.9, True, lin) == 0.9           # linear edge-proportional
    assert master._meta_split(0.0, 0.0, True, lin) == 1.0           # keine Edge -> Sockel traegt
    assert master._meta_split(0.0, 0.0, False, lin) == 0.0
    # Floor hebt den schwachen Sleeve (Meta-Diversifikation)
    assert master._meta_split(0.1, 0.9, True, {"meta_temp": 0.0, "meta_floor": 0.2}) == 0.8
    # Softmax-Temperatur glaettet Richtung 0.5
    s_lin = master._meta_split(0.2, 0.8, True, lin)
    s_soft = master._meta_split(0.2, 0.8, True, {"meta_temp": 1.0, "meta_floor": 0.0})
    assert abs(s_soft - 0.5) < abs(s_lin - 0.5)


def test_psr_downweights_statistically_insignificant_engine(monkeypatch):
    def eng(sharpe, psr):
        return lambda: {"ready": True, "stats": {"sharpe": sharpe, "days": 300, "ann_pct": 10.0,
                                                 "maxdd_pct": -5.0, "psr": psr}}
    monkeypatch.setattr(master, "MN_ENGINES",
                        [("csm", eng(2.0, 0.99)), ("marketmaking", eng(2.0, 0.40))])
    cfg = {**_W, "psr_weight": 1.0, "max_weight": 1.0, "deflate_factor": 0.0}
    w = {m["engine"]: m["weight"] for m in master.mn_sleeve(cfg)["members"]}
    assert w["csm"] > w["marketmaking"]                   # gleiche Sharpe, aber mm statistisch unsicherer
    w0 = {m["engine"]: m["weight"] for m in master.mn_sleeve({**cfg, "psr_weight": 0.0})["members"]}
    assert abs(w0["csm"] - w0["marketmaking"]) < 1e-6     # PSR aus -> gleich gewichtet


# --- D1: Vol-Targeting-Exposure an die Hand (defensiv, opt-in) ---
def test_vol_target_factor_off_and_defensive(monkeypatch):
    from backend.app import stats
    # Default (vol_target_pct=0) -> 1.0 (kein Eingriff, egal welche Vola)
    assert master._vol_target_factor({"vol_target_pct": 0.0}) == 1.0
    # An + realisierte Vola ueber Ziel -> <1, defensiv gekappt bei 0.3
    monkeypatch.setattr(stats, "get_market_snapshots", lambda limit=1: [{"volatility": 4.0}])
    es = master._vol_target_factor({"vol_target_pct": 1.0})
    assert 0.3 <= es < 1.0
    monkeypatch.setattr(stats, "get_market_snapshots", lambda limit=1: [{"volatility": 100.0}])
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 0.3    # harte Untergrenze
    # Vola unter Ziel -> nie hochskalieren (<=1 Deckel)
    monkeypatch.setattr(stats, "get_market_snapshots", lambda limit=1: [{"volatility": 0.5}])
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 1.0
    # keine Snapshots -> sicher 1.0
    monkeypatch.setattr(stats, "get_market_snapshots", lambda limit=1: [])
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 1.0


def test_exposure_scale_delegates_to_vol_target(monkeypatch):
    # Der oeffentliche Hand-Wert delegiert an _vol_target_factor auf der aktuellen Config.
    monkeypatch.setattr(master, "get_config", lambda: {"vol_target_pct": 1.0})
    monkeypatch.setattr(master, "_vol_target_factor", lambda cfg: 0.42)
    assert master.exposure_scale() == 0.42


def test_vol_target_factor_scales_with_realized_vol(tmp_path):
    _setup(tmp_path)
    assert master._vol_target_factor({"vol_target_pct": 0.0}) == 1.0       # aus
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 1.0       # kein Snapshot
    stats.save_market_snapshot("BTC/USDT", 100.0, "range", 2.0)            # realisiert 2.0
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 0.5       # Ziel 1.0 / 2.0
    stats.save_market_snapshot("BTC/USDT", 100.0, "range", 0.4)            # ruhig
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 1.0       # kein Hebeln über 1
    stats.save_market_snapshot("BTC/USDT", 100.0, "range", 10.0)           # extrem
    assert master._vol_target_factor({"vol_target_pct": 1.0}) == 0.3       # Boden


def test_master_config_roundtrip(tmp_path):
    _setup(tmp_path)
    d = master.set_config({"max_weight": 0.5, "sharpe_haircut": 0.7})
    assert d["max_weight"] == 0.5 and d["sharpe_haircut"] == 0.7
    assert master.get_config()["max_weight"] == 0.5
    sl = master.mn_sleeve()   # nutzt die persistierte Config
    assert sl["weighting"]["max_weight"] == 0.5
