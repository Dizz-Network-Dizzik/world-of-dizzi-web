"""Tests für den MasterMeta-Autopilot (Hintergrund-Selbstverbesserung) + den Singleton-Bot.

Rein/isoliert: Modul-Pfade per ``monkeypatch`` auf tmp_path (auto-restore → keine Wirkung auf
Live-`bots.json` oder andere Tests), kein Netz, keine Freqtrade-Backtests (die schwere step_fn wird
durch eine Stub-Funktion ersetzt)."""
import json

from backend.app import autopilot, registry


def test_state_defaults_and_set(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "ap.json")
    s = autopilot.get_state()
    assert s["enabled"] is True and s["interval_h"] == 6.0
    s2 = autopilot.set_state({"enabled": False, "interval_h": 2})
    assert s2["enabled"] is False and s2["interval_h"] == 2.0
    assert autopilot.get_state()["enabled"] is False  # persistiert


def test_interval_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "ap.json")
    assert autopilot.set_state({"interval_h": 0.01})["interval_h"] >= 0.25


def test_step_records_result_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "ap.json")
    calls = []
    monkeypatch.setattr(autopilot, "_step_fn",
                        lambda reason: (calls.append(reason) or {"ok": True, "applied": False, "reason": reason}))
    res = autopilot._run_step("unittest")
    assert res["ok"] and res["reason"] == "unittest" and calls == ["unittest"]
    st = autopilot.status()
    assert st["last_run_ts"] is not None
    assert st["history"][0]["reason"] == "unittest"           # neueste zuerst
    assert st["next_run_ts"] and st["next_run_ts"] > st["last_run_ts"]


def test_step_swallows_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "ap.json")

    def boom(reason):
        raise ValueError("nope")

    monkeypatch.setattr(autopilot, "_step_fn", boom)
    res = autopilot._run_step("x")
    assert res["ok"] is False and "ValueError" in res["error"]
    assert autopilot._last_error and "ValueError" in autopilot._last_error


def test_step_without_fn(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "STATE_FILE", tmp_path / "ap.json")
    monkeypatch.setattr(autopilot, "_step_fn", None)
    assert autopilot._run_step("x")["ok"] is False


def test_ensure_master_bot_singleton(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "BOTS_FILE", tmp_path / "bots.json")
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_bot1_dryrun.json").write_text(json.dumps({"exchange": {}}), encoding="utf-8")
    b1 = registry.ensure_master_bot()
    assert b1.id == registry.MASTER_BOT_ID == "mastermeta"
    assert b1.name == "MasterMeta" and b1.strategy == "MasterMeta"
    # Aggressiv-Profil: Futures, Hebel-Defaults gesetzt, Futures-Pairs (:USDT)
    assert b1.trading_mode == "futures"
    assert b1.opt_params.get("base_leverage") == 5 and b1.opt_params.get("max_leverage") == 10
    assert all(p.endswith(":USDT") for p in b1.pairs)
    b2 = registry.ensure_master_bot()                      # idempotent: kein zweiter Bot
    assert b2.id == b1.id and len(json.loads((tmp_path / "bots.json").read_text())) == 1
    assert (tmp_path / "config_mastermeta.json").exists()  # Engine-Config geschrieben


def test_ensure_master_bot_migrates_spot_to_futures(tmp_path, monkeypatch):
    # Bestehender (alter) Spot-Bot wird beim ensure auf das Aggressiv-Futures-Profil migriert.
    monkeypatch.setattr(registry, "BOTS_FILE", tmp_path / "bots.json")
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_bot1_dryrun.json").write_text(json.dumps({"exchange": {}}), encoding="utf-8")
    from backend.app.models import BotConfig
    old = BotConfig(id="mastermeta", name="MasterMeta", strategy="MasterMeta",
                    trading_mode="spot", pairs=["BTC/USDT"], timeframe="15m")
    (tmp_path / "bots.json").write_text(json.dumps({"mastermeta": old.model_dump()}), encoding="utf-8")
    migrated = registry.ensure_master_bot()
    assert migrated.trading_mode == "futures"
    assert migrated.opt_params.get("base_leverage") == 5
    assert all(p.endswith(":USDT") for p in migrated.pairs)
