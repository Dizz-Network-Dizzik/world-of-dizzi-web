"""Tests: FP-T5 Politik→Hand-Brücke — suggested_policy.json (docs/POLICY_HAND_SPEC.md).

Kern = PROPERTY-Tests (seeded random, 200 Fälle) gegen die reine Payload-Ableitung
``policy_bridge.derive_payload``: die normative Klemmkette T0→T1→T2 ist über Invarianten am
ENDZUSTAND abgesichert (PT1–PT7, SPEC §2) — nicht über Implementierungs-Interna. Dazu Writer-Gates
(Default AUS ⇒ keine Datei · proposal · breach-Degradation · warn/Konzentration-Logik-Freeze),
runner-Env-Vertrag (TBT_POLICY_FILE) und die komplette Engine-Gate-Kette (``_policy_levers`` +
``custom_stake_amount``-Komposition) mit gestubbten Fremd-Modulen — jede Stufe fail-safe auf das
Default-Verhalten (= byte-identisch ohne Opt-in). Byte-Identitäts-Anker der Sizing-Seite:
test_sizing_bridge.py läuft UNVERÄNDERT grün gegen die umstrukturierte ``custom_stake_amount``."""
import importlib.util
import json
import random
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

from backend.app import policy_bridge
from backend.app.meta import STRAT_REGIME

_PROGRAMM = Path(__file__).resolve().parents[1]


# ----------------------- Config-Validierung -----------------------
def _cfg_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(policy_bridge, "STATE_FILE", tmp_path / "policy_bridge.json")


def test_set_config_clamps_and_whitelists(monkeypatch, tmp_path):
    _cfg_isolated(monkeypatch, tmp_path)
    cfg = policy_bridge.set_config({"scale_floor": 7.0, "bridge_mode": "yolo",
                                    "bridge_max_age_s": 5, "apply_logic": 1})
    assert cfg["scale_floor"] == 1.0                      # Faktor nie > 1 (nie hochhebeln)
    assert cfg["bridge_mode"] == "proposal"               # Whitelist hält
    assert cfg["bridge_max_age_s"] == 60                  # Frische-Gate nie unter 60 s
    assert cfg["apply_logic"] is True
    cfg = policy_bridge.set_config({"scale_floor": -3})
    assert cfg["scale_floor"] == 0.1                      # nie unter 10 % drücken


def test_defaults_all_inert(monkeypatch, tmp_path):
    _cfg_isolated(monkeypatch, tmp_path)
    cfg = policy_bridge.get_config()
    assert cfg["bridge_enabled"] is False and cfg["bridge_mode"] == "proposal"
    assert not cfg["apply_logic"] and not cfg["apply_stake"] and not cfg["gate_unprofitable"]


# ----------------------- T0: Stake-Scale-Mathematik -----------------------
def test_stake_scale_math():
    assert policy_bridge._stake_scale(True, 0.6, 0.5) == 0.8      # floor + (1-floor)·conf
    assert policy_bridge._stake_scale(False, 0.9, 0.5) == 0.5     # ohne Beleg ⇒ floor
    assert policy_bridge._stake_scale(True, 5.0, 0.5) == 1.0      # conf-Klemme oben
    assert policy_bridge._stake_scale(True, -1.0, 0.5) == 0.5     # conf-Klemme unten
    assert policy_bridge._stake_scale(True, 1.0, 1.0) == 1.0      # floor 1.0 = Dämpfung neutral
    # Monotonie in der Konfidenz.
    scales = [policy_bridge._stake_scale(True, c, 0.4) for c in (0.0, 0.3, 0.7, 1.0)]
    assert scales == sorted(scales) and scales[0] == 0.4 and scales[-1] == 1.0


# ----------------------- derive_payload: Units -----------------------
def _alloc(strategy, profitable=False, conf=0.4, pf=1.0, params=None):
    return {"strategy": strategy, "score": 1.0, "expected_pf": pf, "profit_factor": pf,
            "validated": profitable, "regime_fit": 1.0, "confidence": conf,
            "params": params, "profitable": profitable}


def _policy(tu="TrendFollowEma", rg="FuturesBbandsBounce", td="Supertrend",
            active="range", active_conf=0.7, **flags):
    return {"allocations": {"trend_up": _alloc(tu, **flags), "range": _alloc(rg, **flags),
                            "trend_down": _alloc(td, **flags)},
            "active_regime": {"regime": active, "confidence": active_conf},
            "ensemble": {"dir_share": 0.3, "mn_share": 0.7},
            "fundamental": {"suggested_exposure": 0.9}}


def _cfg(**over):
    cfg = dict(policy_bridge._DEFAULTS)
    cfg.update(over)
    return cfg


def test_payload_default_mapping_no_switch():
    pl = policy_bridge.derive_payload(_policy(), cfg=_cfg())
    assert pl["regimes"]["trend_up"]["logic"] == "trend_macd"
    assert pl["regimes"]["range"]["logic"] == "range_bb"
    assert pl["regimes"]["trend_down"]["logic"] == "trend_macd_short"
    assert not any(r["switched"] for r in pl["regimes"].values())
    assert pl["mode"] == "proposal" and pl["logic_frozen"] is False


def test_payload_tag_map_switches_logic():
    # Bestauswahl in trend_up ist range-getaggt (Mean-Reversion) ⇒ die Hand soll BB-MR fahren;
    # Bestauswahl in range ist trend-getaggt ⇒ MACD-Trendfolge in der Seitwärtsphase.
    pl = policy_bridge.derive_payload(_policy(tu="MeanReversionRsi", rg="TrendFollowEma"),
                                      cfg=_cfg(bridge_mode="apply"))
    assert pl["regimes"]["trend_up"]["logic"] == "range_bb" and pl["regimes"]["trend_up"]["switched"]
    assert pl["regimes"]["range"]["logic"] == "trend_macd" and pl["regimes"]["range"]["switched"]
    assert pl["mode"] == "apply"


def test_payload_volatil_and_unknown_keep_default():
    pl = policy_bridge.derive_payload(_policy(tu="FuturesBreakoutVol", rg="StrategieDieEsNichtGibt"),
                                      cfg=_cfg())
    assert pl["regimes"]["trend_up"]["logic"] == "trend_macd"       # volatil: kein Hand-Pendant
    assert not pl["regimes"]["trend_up"]["switched"]
    assert "note" in pl["regimes"]["trend_up"]
    assert pl["regimes"]["range"]["logic"] == "range_bb"            # unbekannt: Default
    assert not pl["regimes"]["range"]["switched"]


def test_payload_short_has_no_alternative():
    pl = policy_bridge.derive_payload(_policy(td="MeanReversionRsi"), cfg=_cfg())
    r = pl["regimes"]["trend_down"]
    assert r["logic"] == "trend_macd_short" and not r["switched"] and "note" in r


def test_payload_governor_breach_degrades_to_proposal():
    pl = policy_bridge.derive_payload(_policy(tu="MeanReversionRsi"),
                                      governor_severity="breach", cfg=_cfg(bridge_mode="apply"))
    assert pl["mode"] == "proposal" and pl["logic_frozen"] is True


def test_payload_governor_warn_freezes_logic_keeps_apply():
    # T1: warn ⇒ kein Verhaltens-Churn (Logik = Default), aber die rein defensive Stake-Dämpfung
    # bleibt anwendbar (mode bleibt apply).
    pl = policy_bridge.derive_payload(_policy(tu="MeanReversionRsi", rg="TrendFollowEma"),
                                      governor_severity="warn", cfg=_cfg(bridge_mode="apply"))
    assert pl["mode"] == "apply" and pl["logic_frozen"] is True
    assert pl["regimes"]["trend_up"]["logic"] == "trend_macd"
    assert pl["regimes"]["range"]["logic"] == "range_bb"
    assert not any(r["switched"] for r in pl["regimes"].values())


def test_payload_concentration_hit_freezes_logic():
    pl = policy_bridge.derive_payload(_policy(rg="TrendFollowEma"),
                                      concentration_hit=True, cfg=_cfg(bridge_mode="apply"))
    assert pl["logic_frozen"] and pl["regimes"]["range"]["logic"] == "range_bb"
    assert pl["mode"] == "apply"


def test_payload_gate_unprofitable_and_scale():
    pl = policy_bridge.derive_payload(_policy(profitable=False, conf=0.9),
                                      cfg=_cfg(gate_unprofitable=True, apply_stake=True))
    assert all(r["enabled"] is False for r in pl["regimes"].values())   # kein belegter Edge
    assert all(r["stake_scale"] == 0.5 for r in pl["regimes"].values())  # floor
    pl2 = policy_bridge.derive_payload(_policy(profitable=True, conf=0.6),
                                       cfg=_cfg(gate_unprofitable=True))
    assert all(r["enabled"] is True for r in pl2["regimes"].values())
    assert all(r["stake_scale"] == 0.8 for r in pl2["regimes"].values())  # 0.5 + 0.5·0.6


def test_payload_active_block_mirrors_regime():
    pl = policy_bridge.derive_payload(_policy(active="range", active_conf=0.7), cfg=_cfg())
    assert pl["active"]["regime"] == "range"
    assert pl["active"]["stake_scale"] == pl["regimes"]["range"]["stake_scale"]
    assert pl["active"]["logic"] == pl["regimes"]["range"]["logic"]
    pl2 = policy_bridge.derive_payload(_policy(active=None), cfg=_cfg())
    assert pl2["active"] is None                            # kein Regime ⇒ Engine no-op


def test_payload_levers_and_transparency_fields():
    pl = policy_bridge.derive_payload(_policy(), cfg=_cfg(apply_logic=True, apply_stake=True,
                                                          gate_unprofitable=True))
    assert pl["levers"] == {"apply_logic": True, "apply_stake": True, "gate_unprofitable": True}
    assert pl["ensemble"] == {"dir_share": 0.3, "mn_share": 0.7}
    assert pl["suggested_exposure"] == 0.9
    assert pl["regimes"]["trend_up"]["params"] is None       # Params fließen mit (Transparenz) …
    pl2 = policy_bridge.derive_payload(_policy(params={"bb_period": 18}), cfg=_cfg())
    assert pl2["regimes"]["range"]["params"] == {"bb_period": 18}   # … werden aber nie angewendet


# ----------------------- Klemmkette T0–T2: Property-Tests (seeded) -----------------------
def _rand_policy(rng: random.Random):
    strats = list(STRAT_REGIME) + ["Unbekannt", None]
    def a():
        return _alloc(rng.choice(strats), profitable=rng.random() < 0.4,
                      conf=rng.uniform(-0.2, 1.4), pf=rng.uniform(0.5, 3.0))
    return {"allocations": {"trend_up": a(), "range": a(), "trend_down": a()},
            "active_regime": {"regime": rng.choice(["trend_up", "range", "trend_down", None]),
                              "confidence": rng.uniform(0, 1)},
            "ensemble": {"dir_share": rng.random(), "mn_share": rng.random()},
            "fundamental": {"suggested_exposure": rng.uniform(0.3, 1.0)}}


def test_payload_properties_seeded():
    rng = random.Random(4711)
    for case in range(200):
        policy = _rand_policy(rng)
        sev = rng.choice(["ok", "ok", "warn", "breach"])
        hit = rng.random() < 0.3
        cfg = _cfg(bridge_mode=rng.choice(["proposal", "apply"]),
                   apply_logic=rng.random() < 0.5, apply_stake=rng.random() < 0.5,
                   gate_unprofitable=rng.random() < 0.5,
                   scale_floor=rng.choice([0.1, 0.25, 0.5, 0.8, 1.0]))
        pl = policy_bridge.derive_payload(policy, governor_severity=sev,
                                          concentration_hit=hit, cfg=cfg)
        floor = cfg["scale_floor"]
        for reg, r in pl["regimes"].items():
            # PT1: Stake-Scale IMMER in [floor, 1.0] — die Politik kann nie hochhebeln.
            assert floor - 1e-9 <= r["stake_scale"] <= 1.0 + 1e-9, f"Fall {case}/{reg}: scale"
            # PT4: Logik nur aus der Hand-Whitelist; trend_down IMMER Default (kein Short-Pendant).
            assert r["logic"] in ("trend_macd", "range_bb", "trend_macd_short")
            if reg == "trend_down":
                assert r["logic"] == "trend_macd_short" and not r["switched"]
            # PT3: Governor warn/breach oder Konzentrations-Treffer ⇒ Logik-Freeze auf Default.
            if sev in ("warn", "breach") or hit:
                assert r["logic"] == policy_bridge.DEFAULT_LOGIC[reg], f"Fall {case}/{reg}: Freeze"
                assert not r["switched"]
            # PT5: Edge-Gating-Semantik.
            if cfg["gate_unprofitable"]:
                assert r["enabled"] == r["profitable"], f"Fall {case}/{reg}: Gate"
            else:
                assert r["enabled"] is True
        # PT2: breach ⇒ NIE apply (Degradation, letztes Wort des Governors).
        if sev == "breach":
            assert pl["mode"] == "proposal", f"Fall {case}: breach nicht degradiert"
        assert pl["mode"] in ("proposal", "apply")
        if pl["mode"] == "apply":
            assert cfg["bridge_mode"] == "apply" and sev != "breach"
        # PT6: Frozen-Flag konsistent.
        assert pl["logic_frozen"] == (sev in ("warn", "breach") or hit)
        # PT7: Determinismus (modulo ts): gleiche Inputs ⇒ gleicher Payload.
        pl2 = policy_bridge.derive_payload(policy, governor_severity=sev,
                                           concentration_hit=hit, cfg=cfg)
        assert {k: v for k, v in pl.items() if k != "ts"} == \
               {k: v for k, v in pl2.items() if k != "ts"}, f"Fall {case}: nicht deterministisch"


# ----------------------- T2-Input: Konzentrations-Treffer -----------------------
def _conc(severity="warn", asset="BTC", share=61.0):
    return {"severity": severity, "config": {"max_asset_share_pct": 50.0},
            "assets": [{"asset": asset, "share_pct": share}], "clusters": []}


def test_concentration_hit_only_when_hand_assets_touched(monkeypatch):
    monkeypatch.setattr(policy_bridge.registry, "get_bot",
                        lambda bid: SimpleNamespace(pairs=["BTC/USDT:USDT", "ETH/USDT:USDT"]))
    assert policy_bridge._concentration_hit(_conc()) is True            # BTC über Deckel + Hand hält BTC
    assert policy_bridge._concentration_hit(_conc(asset="XRP")) is False  # Klumpen woanders
    assert policy_bridge._concentration_hit(_conc(severity="ok")) is False


def test_concentration_hit_falls_back_to_majors(monkeypatch):
    monkeypatch.setattr(policy_bridge.registry, "get_bot",
                        lambda bid: (_ for _ in ()).throw(RuntimeError("Registry kaputt")))
    assert policy_bridge._concentration_hit(_conc()) is True            # defensiv: Majors angenommen


# ----------------------- Writer-Gates (write_bridge_auto) -----------------------
def _setup_writer(monkeypatch, tmp_path, *, severity="ok", conc=None):
    monkeypatch.setattr(policy_bridge, "STATE_FILE", tmp_path / "policy_bridge.json")
    monkeypatch.setattr(policy_bridge, "POLICY_BRIDGE_FILE", tmp_path / "suggested_policy.json")
    monkeypatch.setattr(policy_bridge.master, "derive_policy",
                        lambda high_vol=False: _policy(tu="MeanReversionRsi"))
    monkeypatch.setattr(policy_bridge.governor, "evaluate",
                        lambda use_cache=True: {"severity": severity})
    monkeypatch.setattr(policy_bridge.concentration, "analyze", lambda: conc or {"severity": "ok"})
    monkeypatch.setattr(policy_bridge.registry, "get_bot",
                        lambda bid: SimpleNamespace(pairs=["BTC/USDT:USDT"]))
    return tmp_path / "suggested_policy.json"


def test_writer_disabled_by_default_writes_nothing(monkeypatch, tmp_path):
    f = _setup_writer(monkeypatch, tmp_path)
    res = policy_bridge.write_bridge_auto()
    assert res["written"] is False and not f.exists()       # 0 Verhaltensänderung ohne Opt-in


def test_writer_proposal_mode_default(monkeypatch, tmp_path):
    f = _setup_writer(monkeypatch, tmp_path)
    policy_bridge.set_config({"bridge_enabled": True})      # bridge_mode bleibt Default "proposal"
    res = policy_bridge.write_bridge_auto()
    d = json.loads(f.read_text(encoding="utf-8"))
    assert res["written"] and d["mode"] == "proposal"
    assert d["regimes"]["trend_up"]["logic"] == "range_bb"  # Vorschlag sichtbar (MR-Best in trend_up)
    assert isinstance(d["ts"], int) and d["ts"] > 0


def test_writer_apply_and_breach_degradation(monkeypatch, tmp_path):
    f = _setup_writer(monkeypatch, tmp_path, severity="breach")
    policy_bridge.set_config({"bridge_enabled": True, "bridge_mode": "apply"})
    res = policy_bridge.write_bridge_auto()
    assert res["mode"] == "proposal" and res["degraded"] is True
    assert json.loads(f.read_text(encoding="utf-8"))["mode"] == "proposal"


def test_writer_warn_freezes_logic_in_file(monkeypatch, tmp_path):
    f = _setup_writer(monkeypatch, tmp_path, severity="warn")
    policy_bridge.set_config({"bridge_enabled": True, "bridge_mode": "apply", "apply_logic": True})
    res = policy_bridge.write_bridge_auto()
    d = json.loads(f.read_text(encoding="utf-8"))
    assert res["mode"] == "apply" and res["logic_frozen"] is True
    assert d["regimes"]["trend_up"]["logic"] == "trend_macd"   # Freeze: Default statt Umschaltung


def test_writer_injectable_policy_for_tests(monkeypatch, tmp_path):
    f = _setup_writer(monkeypatch, tmp_path)
    policy_bridge.set_config({"bridge_enabled": True})
    monkeypatch.setattr(policy_bridge.master, "derive_policy",
                        lambda high_vol=False: (_ for _ in ()).throw(AssertionError("nicht ableiten")))
    res = policy_bridge.write_bridge_auto(policy=_policy())    # injizierte Politik gewinnt
    assert res["written"] and json.loads(f.read_text(encoding="utf-8"))["regimes"]


# ----------------------- Entwaffnungs-Latenz (Disarm bei Abschalten) -----------------------
def test_set_config_disarms_on_disable(monkeypatch, tmp_path):
    """Abschalten (enabled→disabled) schreibt SOFORT eine neutrale mode='proposal'-Payload —
    ohne sie läse die Engine die alte apply-Datei bis zum Frische-Gate (≤7 h) weiter."""
    monkeypatch.setattr(policy_bridge, "STATE_FILE", tmp_path / "policy_bridge.json")
    monkeypatch.setattr(policy_bridge, "POLICY_BRIDGE_FILE", tmp_path / "suggested_policy.json")
    # scharfe Altdatei simulieren (mode=apply)
    (tmp_path / "suggested_policy.json").write_text(
        json.dumps({"ts": 1, "mode": "apply", "regimes": {}}), encoding="utf-8")
    policy_bridge.set_config({"bridge_enabled": True})
    policy_bridge.set_config({"bridge_enabled": False})       # <- Abschalt-Transition
    d = json.loads((tmp_path / "suggested_policy.json").read_text(encoding="utf-8"))
    assert d["mode"] == "proposal" and d["disabled"] is True  # sofort entwaffnet


def test_set_config_no_disarm_without_transition(monkeypatch, tmp_path):
    """Kein Disarm-Schreiben, wenn bridge_enabled gar nicht von True→False wechselt
    (schützt die POLICY_BRIDGE_FILE-untouched-Invariante der reinen Config-Tests)."""
    monkeypatch.setattr(policy_bridge, "STATE_FILE", tmp_path / "policy_bridge.json")
    monkeypatch.setattr(policy_bridge, "POLICY_BRIDGE_FILE", tmp_path / "suggested_policy.json")
    policy_bridge.set_config({"scale_floor": 0.7})            # enabled bleibt False (Default)
    assert not (tmp_path / "suggested_policy.json").exists()


def test_writer_disarms_stale_apply_file(monkeypatch, tmp_path):
    """Fallback-Pfad: ist beim Abschalten kein set_config-Disarm gelaufen (z. B. Neustart),
    neutralisiert der nächste Autopilot-Tick eine noch scharfe Altdatei — idempotent."""
    f = _setup_writer(monkeypatch, tmp_path)                  # bridge_enabled bleibt False (Default)
    f.write_text(json.dumps({"ts": 1, "mode": "apply", "regimes": {}}), encoding="utf-8")
    res = policy_bridge.write_bridge_auto()
    assert res["written"] is False and res.get("disarmed") is True
    assert json.loads(f.read_text(encoding="utf-8"))["mode"] == "proposal"
    # 2. Lauf: Datei ist bereits proposal ⇒ nichts mehr zu tun (idempotent, kein Disarm-Flag)
    res2 = policy_bridge.write_bridge_auto()
    assert res2["written"] is False and "disarmed" not in res2


# ----------------------- runner: Env-Vertrag -----------------------
def test_runner_env_carries_policy_bridge_contract():
    from backend.app import runner
    bot = SimpleNamespace(id="b7", opt_params=None, manual_params=None, timeframes=None, leverage=None)
    env = runner._subprocess_env(bot)
    assert env["TBT_POLICY_FILE"] == str(policy_bridge.POLICY_BRIDGE_FILE)
    assert env["TBT_POLICY_FILE"].endswith("suggested_policy.json")
    assert env["TBT_SIZING_FILE"] and env["TBT_REGIME_FILE"]   # bestehende Verträge unangetastet


# ----------------------- Autopilot-Hook -----------------------
def test_autopilot_step_writes_policy_bridge(monkeypatch):
    from backend.app import main
    for name in ("_mastermeta_improve", "_auto_upgrade_bots", "_auto_validate_strategy"):
        monkeypatch.setattr(main, name, lambda *a, **k: {"ok": True})
    monkeypatch.setattr(main.governor, "run_once", lambda reason: {"ok": True, "severity": "ok"})
    monkeypatch.setattr(main.cull, "run_once", lambda reason: {"ok": True})
    monkeypatch.setattr(main.sizing, "write_bridge_auto", lambda: {"written": False})
    marker = {"written": False, "reason": "Test"}
    monkeypatch.setattr(main.policy_bridge, "write_bridge_auto", lambda: marker)
    out = main._autopilot_step("test")
    assert out["policy_bridge"] is marker                     # Hook sitzt NACH dem Governor
    assert "sizing_bridge" in out


def test_autopilot_step_survives_policy_bridge_error(monkeypatch):
    from backend.app import main
    for name in ("_mastermeta_improve", "_auto_upgrade_bots", "_auto_validate_strategy"):
        monkeypatch.setattr(main, name, lambda *a, **k: {"ok": True})
    monkeypatch.setattr(main.governor, "run_once", lambda reason: {"ok": True})
    monkeypatch.setattr(main.cull, "run_once", lambda reason: {"ok": True})
    monkeypatch.setattr(main.sizing, "write_bridge_auto", lambda: {"written": False})
    monkeypatch.setattr(main.policy_bridge, "write_bridge_auto",
                        lambda: (_ for _ in ()).throw(RuntimeError("kaputt")))
    out = main._autopilot_step("test")
    assert out["policy_bridge"]["written"] is False and "error" in out["policy_bridge"]


# ----------------------- Engine: _policy_levers + custom_stake_amount (gestubbter Import) -----------------------
def _load_master_meta(monkeypatch):
    """Lädt die Engine-Strategie im Backend-venv: talib/pandas/freqtrade werden gestubbt (die
    Gate-Logik der Politik-Brücke ist reine Stdlib — genau die wird hier getestet)."""
    talib = types.ModuleType("talib")
    talib_abstract = types.ModuleType("talib.abstract")
    talib.abstract = talib_abstract
    pandas = types.ModuleType("pandas")
    pandas.DataFrame = object
    ft = types.ModuleType("freqtrade")
    ft_strategy = types.ModuleType("freqtrade.strategy")

    class IStrategy:
        def __init__(self, config):
            self.config = config
    ft_strategy.IStrategy = IStrategy
    for name, mod in {"talib": talib, "talib.abstract": talib_abstract, "pandas": pandas,
                      "freqtrade": ft, "freqtrade.strategy": ft_strategy}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    path = _PROGRAMM / "engine" / "user_data" / "strategies" / "master_meta.py"
    spec = importlib.util.spec_from_file_location("master_meta_policy_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _policy_file(tmp_path, monkeypatch, *, mode="apply", age_s=0.0, scale=0.8,
                 levers=None, logic=None, enabled=None, raw=None):
    f = tmp_path / "suggested_policy.json"
    if raw is not None:
        f.write_text(raw, encoding="utf-8")
    else:
        regimes = {}
        for reg, dflt in (("trend_up", "trend_macd"), ("range", "range_bb"),
                          ("trend_down", "trend_macd_short")):
            regimes[reg] = {"logic": (logic or {}).get(reg, dflt),
                            "enabled": (enabled or {}).get(reg, True)}
        f.write_text(json.dumps({
            "ts": int((time.time() - age_s) * 1000), "mode": mode,
            "levers": levers or {"apply_logic": True, "apply_stake": True,
                                 "gate_unprofitable": True},
            "active": {"regime": "range", "stake_scale": scale},
            "regimes": regimes}), encoding="utf-8")
    monkeypatch.setenv("TBT_POLICY_FILE", str(f))
    return f


def _levers(mm, dry_run=True, opt=None):
    return mm._policy_levers({"dry_run": dry_run}, opt if opt is not None
                             else {"use_policy_bridge": 1})


def test_engine_gate1_optin_default_off(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch)                     # gültige apply-Datei liegt bereit …
    assert _levers(mm, opt={}) is None                      # … aber KEIN Opt-in ⇒ nie gelesen


def test_engine_gate2_real_money_hard_excluded(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch)
    assert _levers(mm, dry_run=False) is None               # Echtgeld ⇒ Brücke tot (M6/G-T5 tabu)


def test_engine_gate3_proposal_stale_broken_missing_all_failsafe(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch, mode="proposal")
    assert _levers(mm) is None                              # proposal ⇒ nie anwenden
    _policy_file(tmp_path, monkeypatch, age_s=30000.0)
    assert _levers(mm) is None                              # veraltet (> 25200 s Default) ⇒ ignorieren
    _policy_file(tmp_path, monkeypatch, raw="{kaputt")
    assert _levers(mm) is None                              # kaputtes JSON ⇒ ignorieren
    monkeypatch.setenv("TBT_POLICY_FILE", str(tmp_path / "gibts_nicht.json"))
    assert _levers(mm) is None                              # fehlende Datei ⇒ ignorieren


def test_engine_custom_max_age_via_opt_param(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch, age_s=120.0)        # 120 s alt, Limit 60 s
    assert mm._policy_levers({"dry_run": True},
                             {"use_policy_bridge": 1, "policy_max_age_s": 60}) is None


def test_engine_validates_and_hard_clamps_payload(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch, scale=3.0, logic={"trend_up": "quatsch"})
    lv = _levers(mm)
    assert lv["active_scale"] == 1.0                        # Hard-Klemme: nie > 1 (nie hochhebeln)
    assert lv["logic"]["trend_up"] is None                  # unbekannte Logik ⇒ Default bleibt
    assert lv["logic"]["range"] == "range_bb"
    _policy_file(tmp_path, monkeypatch, scale=0.01)
    assert _levers(mm)["active_scale"] == 0.1               # Hard-Klemme: nie < 0.1


def _strategy(mm, dry_run=True):
    return mm.MasterMeta({"dry_run": dry_run})


def _stake(strategy, proposed=55.0, min_stake=None, max_stake=None):
    return strategy.custom_stake_amount("BTC/USDT:USDT", None, 50000.0, proposed,
                                        min_stake, max_stake, 5.0, "trend_macd", "long")


def test_engine_stake_policy_damping(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_policy_bridge": 1}))
    monkeypatch.delenv("TBT_SIZING_FILE", raising=False)
    _policy_file(tmp_path, monkeypatch, scale=0.8)
    assert _stake(_strategy(mm)) == 44.0                    # 55 × 0.8 (L2-Dämpfung)
    assert _stake(_strategy(mm), min_stake=50.0) == 50.0    # freqtrade-Untergrenze klemmt zuletzt
    _policy_file(tmp_path, monkeypatch, levers={"apply_stake": False})
    assert _stake(_strategy(mm)) == 55.0                    # Hebel L2 aus ⇒ unverändert
    _policy_file(tmp_path, monkeypatch, raw=json.dumps({
        "ts": int(time.time() * 1000), "mode": "apply", "levers": {"apply_stake": True},
        "active": None, "regimes": {}}))
    assert _stake(_strategy(mm)) == 55.0                    # kein aktives Regime ⇒ no-op


def test_engine_stake_composes_with_sizing_bridge(monkeypatch, tmp_path):
    # T3: Politik dämpft den SIZING-Grundwert (Kelly-Bridge-Stake), nie darüber hinaus.
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.setenv("TBT_OPT_PARAMS",
                       json.dumps({"use_policy_bridge": 1, "use_sizing_bridge": 1}))
    sz = tmp_path / "suggested_sizing.json"
    sz.write_text(json.dumps({"ts": int(time.time() * 1000), "mode": "apply",
                              "stakes": {"b1": {"stake": 87.5, "current": 100.0}}}),
                  encoding="utf-8")
    monkeypatch.setenv("TBT_SIZING_FILE", str(sz))
    _policy_file(tmp_path, monkeypatch, scale=0.5)
    assert _stake(_strategy(mm)) == 43.75                   # 87.5 (Kelly) × 0.5 (Politik)


def test_engine_stake_monotone_never_increases(monkeypatch, tmp_path):
    # PT-Monotonie engine-seitig: für JEDEN Payload-Scale gilt final ≤ Grundwert (seeded random).
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_policy_bridge": 1}))
    monkeypatch.delenv("TBT_SIZING_FILE", raising=False)
    rng = random.Random(77)
    strat = _strategy(mm)
    for _ in range(50):
        scale = rng.uniform(-2.0, 5.0)
        _policy_file(tmp_path, monkeypatch, scale=scale)
        assert _stake(strat) <= 55.0 + 1e-9                 # nie über den Grundwert hebeln


def test_engine_no_optin_stake_byte_identical(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _policy_file(tmp_path, monkeypatch, scale=0.5)          # Datei da, aber kein Opt-in
    monkeypatch.delenv("TBT_OPT_PARAMS", raising=False)
    monkeypatch.delenv("TBT_SIZING_FILE", raising=False)
    assert _stake(_strategy(mm)) == 55.0                    # byte-identisch: proposed_stake
