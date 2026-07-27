"""Tests: FP-2 Brücke zur Hand — suggested_sizing.json (SPEC §4, Muster hmm_regime.json).

Backend-Seite: Writer-Gates (Default AUS ⇒ keine Datei · proposal · apply · breach-Degradation P5)
+ runner-Env-Vertrag (TBT_SIZING_FILE/TBT_BOT_ID). Engine-Seite: master_meta.py wird mit gestubbten
Fremd-Modulen (talib/pandas/freqtrade fehlen im Backend-venv) via importlib geladen und die
komplette Gate-Kette von ``custom_stake_amount`` durchgetestet — jede Stufe fail-safe auf
``proposed_stake`` (= byte-identisches Verhalten ohne Opt-in)."""
import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

from backend.app import sizing

_PROGRAMM = Path(__file__).resolve().parents[1]


# ----------------------- Backend: Writer-Gates -----------------------
def _setup(monkeypatch, tmp_path, plan):
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    monkeypatch.setattr(sizing, "SIZING_BRIDGE_FILE", tmp_path / "suggested_sizing.json")
    monkeypatch.setattr(sizing, "portfolio_plan", lambda use_cache=True: plan)
    return tmp_path / "suggested_sizing.json"


def _plan(severity="ok"):
    return {"governor_severity": severity, "budget": {"pct": 0.0},
            "rows": [{"bot_id": "b1", "planned_stake": 87.5, "current_stake": 100.0},
                     {"bot_id": "b2", "planned_stake": 42.0, "current_stake": 40.0}]}


def test_bridge_disabled_by_default_writes_nothing(monkeypatch, tmp_path):
    f = _setup(monkeypatch, tmp_path, _plan())
    res = sizing.write_bridge_auto()
    assert res["written"] is False and not f.exists()      # 0 Verhaltensänderung ohne Opt-in


def test_bridge_proposal_mode_never_apply(monkeypatch, tmp_path):
    f = _setup(monkeypatch, tmp_path, _plan())
    sizing.set_config({"bridge_enabled": True})            # bridge_mode bleibt Default "proposal"
    res = sizing.write_bridge_auto()
    d = json.loads(f.read_text(encoding="utf-8"))
    assert res["written"] and d["mode"] == "proposal"
    assert d["stakes"]["b1"] == {"stake": 87.5, "current": 100.0}
    assert isinstance(d["ts"], int) and d["ts"] > 0


def test_bridge_apply_mode_when_ok(monkeypatch, tmp_path):
    f = _setup(monkeypatch, tmp_path, _plan("ok"))
    sizing.set_config({"bridge_enabled": True, "bridge_mode": "apply"})
    res = sizing.write_bridge_auto()
    assert res["mode"] == "apply" and not res["degraded"]
    assert json.loads(f.read_text(encoding="utf-8"))["mode"] == "apply"


def test_bridge_breach_degrades_to_proposal(monkeypatch, tmp_path):
    # P5: in einer Breach-Lage wendet die Hand nichts Neues an — Backend degradiert die Datei selbst.
    f = _setup(monkeypatch, tmp_path, _plan("breach"))
    sizing.set_config({"bridge_enabled": True, "bridge_mode": "apply"})
    res = sizing.write_bridge_auto()
    assert res["mode"] == "proposal" and res["degraded"] is True
    assert json.loads(f.read_text(encoding="utf-8"))["mode"] == "proposal"


# ----------------------- runner: Env-Vertrag -----------------------
def test_runner_env_carries_sizing_bridge_contract():
    from backend.app import runner
    bot = SimpleNamespace(id="b7", opt_params=None, manual_params=None, timeframes=None, leverage=None)
    env = runner._subprocess_env(bot)
    assert env["TBT_BOT_ID"] == "b7"
    assert env["TBT_SIZING_FILE"].endswith("suggested_sizing.json")
    assert env["TBT_REGIME_FILE"]                          # bestehender Vertrag unangetastet


# ----------------------- Engine: master_meta.custom_stake_amount (gestubbter Import) -----------------------
def _load_master_meta(monkeypatch):
    """Lädt die Engine-Strategie im Backend-venv: talib/pandas/freqtrade werden gestubbt (die
    Gate-Logik der Brücke ist reine Stdlib — genau die wird hier getestet)."""
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
    spec = importlib.util.spec_from_file_location("master_meta_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bridge_file(tmp_path, monkeypatch, *, mode="apply", bot_id="b1", stake=87.5, age_s=0.0):
    f = tmp_path / "suggested_sizing.json"
    f.write_text(json.dumps({"ts": int((time.time() - age_s) * 1000), "mode": mode,
                             "stakes": {bot_id: {"stake": stake, "current": 100.0}}}),
                 encoding="utf-8")
    monkeypatch.setenv("TBT_SIZING_FILE", str(f))
    return f


def _strategy(mm, dry_run=True):
    return mm.MasterMeta({"dry_run": dry_run})


def _stake(strategy, proposed=55.0, min_stake=None, max_stake=None):
    return strategy.custom_stake_amount("BTC/USDT:USDT", None, 50000.0, proposed,
                                        min_stake, max_stake, 5.0, "trend_macd", "long")


def test_engine_gate1_optin_default_off(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _bridge_file(tmp_path, monkeypatch)                    # gültige apply-Datei liegt bereit …
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.delenv("TBT_OPT_PARAMS", raising=False)    # … aber KEIN Opt-in
    assert _stake(_strategy(mm)) == 55.0                   # byte-identisch: proposed_stake


def test_engine_gate2_real_money_hard_excluded(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    _bridge_file(tmp_path, monkeypatch)
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_sizing_bridge": 1}))
    assert _stake(_strategy(mm, dry_run=False)) == 55.0    # Echtgeld ⇒ Brücke tot (M6/G-T5 tabu)


def test_engine_gate3_proposal_stale_foreign_all_failsafe(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_sizing_bridge": 1}))
    strat = _strategy(mm)
    _bridge_file(tmp_path, monkeypatch, mode="proposal")
    assert _stake(strat) == 55.0                           # proposal ⇒ nie anwenden
    _bridge_file(tmp_path, monkeypatch, age_s=1800.0)
    assert _stake(strat) == 55.0                           # veraltet (> 900 s) ⇒ ignorieren
    _bridge_file(tmp_path, monkeypatch, bot_id="fremd")
    assert _stake(strat) == 55.0                           # fremder Bot ⇒ ignorieren
    _bridge_file(tmp_path, monkeypatch, stake=-5.0)
    assert _stake(strat) == 55.0                           # unsinniger Wert ⇒ ignorieren
    monkeypatch.setenv("TBT_SIZING_FILE", str(tmp_path / "gibts_nicht.json"))
    assert _stake(strat) == 55.0                           # fehlende Datei ⇒ ignorieren


def test_engine_happy_path_applies_and_clips(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_sizing_bridge": 1}))
    strat = _strategy(mm)
    _bridge_file(tmp_path, monkeypatch, stake=87.5)
    assert _stake(strat) == 87.5                           # frisch + apply + eigener Bot ⇒ anwenden
    assert _stake(strat, max_stake=60.0) == 60.0           # freqtrade-Obergrenze klemmt
    assert _stake(strat, min_stake=100.0) == 100.0         # freqtrade-Untergrenze klemmt


def test_engine_custom_max_age_via_opt_param(monkeypatch, tmp_path):
    mm = _load_master_meta(monkeypatch)
    monkeypatch.setenv("TBT_BOT_ID", "b1")
    monkeypatch.setenv("TBT_OPT_PARAMS", json.dumps({"use_sizing_bridge": 1, "sizing_max_age_s": 60}))
    _bridge_file(tmp_path, monkeypatch, age_s=120.0)       # 120 s alt, Limit 60 s
    assert _stake(_strategy(mm)) == 55.0
