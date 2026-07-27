"""Tests der Bot-Subprozess-Env (venv-übergreifende Brücken) — rein, ohne Popen/Netz/DB."""
from types import SimpleNamespace

from backend.app import runner, tracker


def test_regime_bridge_always_injected():
    # Auch ohne Lern-Parameter MUSS TBT_REGIME_FILE gesetzt sein, sonst findet master_meta.py
    # die HMM-Regime-Bridge nicht (genau die zuvor offene B5-Lücke).
    env = runner._subprocess_env(SimpleNamespace(opt_params=None, timeframes=None))
    assert env["TBT_REGIME_FILE"] == str(tracker.REGIME_BRIDGE_FILE)
    assert "TBT_OPT_PARAMS" not in env and "TBT_INFORMATIVE_TFS" not in env


def test_opt_params_and_timeframes_added_alongside_bridge():
    bot = SimpleNamespace(opt_params={"sma_period": 50}, timeframes=["1h", "4h"])
    env = runner._subprocess_env(bot)
    assert env["TBT_REGIME_FILE"] == str(tracker.REGIME_BRIDGE_FILE)
    assert env["TBT_OPT_PARAMS"] == '{"sma_period": 50}'
    assert env["TBT_INFORMATIVE_TFS"] == '["1h", "4h"]'


def test_inherits_parent_env(monkeypatch):
    monkeypatch.setenv("TBT_SOME_MARKER", "xyz")
    env = runner._subprocess_env(SimpleNamespace(opt_params=None, timeframes=None))
    assert env.get("TBT_SOME_MARKER") == "xyz"  # Parent-Env wird durchgereicht, nicht ersetzt


def test_runner_and_tracker_agree_on_bridge_path():
    # Single source of truth: der vom runner injizierte Pfad ist exakt der, den das Backend beschreibt.
    env = runner._subprocess_env(SimpleNamespace(opt_params=None, timeframes=None))
    assert env["TBT_REGIME_FILE"] == str(tracker.REGIME_BRIDGE_FILE)
    assert tracker.REGIME_BRIDGE_FILE.name == "hmm_regime.json"
