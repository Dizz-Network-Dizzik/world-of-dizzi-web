"""Tests: registry — Engine-Config-Erzeugung (Pairlist + 429-Rate-Limit + Notfall-Stop), create_bot, Helfer.

Vollständig isoliert: ENGINE_USERDIR + BOTS_FILE auf tmp, audit.record stummgeschaltet (keine Seiteneffekte)."""
import json

from backend.app import registry, universe
from backend.app.models import BotConfig, BotCreate


def _isolate(monkeypatch, tmp_path):
    eng = tmp_path / "engine_user_data"
    eng.mkdir()
    (eng / "config_bot1_dryrun.json").write_text(json.dumps({"exchange": {}}), encoding="utf-8")
    monkeypatch.setattr(registry, "ENGINE_USERDIR", eng)
    monkeypatch.setattr(registry, "BOTS_FILE", tmp_path / "bots.json")
    monkeypatch.setattr(registry.audit, "record", lambda *a, **k: None)
    return eng


def test_pairs_to_futures_idempotent():
    assert registry._pairs_to_futures(["BTC/USDT", "ETH/USDT:USDT"]) == ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def test_next_tag():
    assert registry._next_tag({}) == 1
    assert registry._next_tag({"a": {"tag": 3}, "b": {"tag": 7}}) == 8


def test_write_engine_config_dynamic_has_ratelimit_pairlist_and_stop(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bot = BotConfig(name="X", strategy="FuturesBbandsBounce", pair_mode="dynamic",
                    pairs=universe.candidates_for("scalping"), timeframe="5m", horizon="scalping",
                    trading_mode="futures")
    cfg = json.loads(registry._write_engine_config(bot).read_text(encoding="utf-8"))
    # #1 429-Schutz: enableRateLimit + rateLimit in beiden ccxt-Configs
    assert cfg["exchange"]["ccxt_async_config"]["enableRateLimit"] is True
    assert cfg["exchange"]["ccxt_config"]["rateLimit"] >= 1
    # dynamische, volumengerankte Pairlist-Kette + horizont-gedeckelte Anzahl
    assert [p["method"] for p in cfg["pairlists"]] == ["StaticPairList", "VolumePairList", "SpreadFilter"]
    assert cfg["pairlists"][1]["number_assets"] == universe.number_assets_for("scalping")
    # Whitelist = gestreutes Kandidaten-Universum; Notfall-Stop bleibt erhalten
    assert cfg["exchange"]["pair_whitelist"] == bot.pairs
    assert cfg["order_types"]["stoploss_on_exchange"] is True


def test_write_engine_config_static_uses_staticpairlist(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bot = BotConfig(name="S", pair_mode="static", pairs=["BTC/USDT:USDT"], timeframe="1h", trading_mode="futures")
    cfg = json.loads(registry._write_engine_config(bot).read_text(encoding="utf-8"))
    assert [p["method"] for p in cfg["pairlists"]] == ["StaticPairList"]   # kein Volume/Spread im statischen Modus
    assert cfg["exchange"]["ccxt_async_config"]["enableRateLimit"] is True  # Rate-Limit greift modusunabhängig


def test_create_bot_defaults_dynamic_diversified(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bot = registry.create_bot(BotCreate(name="Neu", strategy="FuturesBbandsBounce",
                                        timeframe="5m", trading_mode="futures"))
    assert bot.pair_mode == "dynamic"
    assert bot.pairs == universe.candidates_for("scalping", "futures")    # gestreut, nicht 3 Majors
    assert len(bot.pairs) > 3 and bot.horizon == "scalping"


def test_create_bot_explicit_pairs_stay_static(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bot = registry.create_bot(BotCreate(name="Fix", pairs=["BTC/USDT:USDT", "ETH/USDT:USDT"],
                                        timeframe="1h", trading_mode="futures"))
    assert bot.pair_mode == "static" and bot.pairs == ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def test_update_bot_filters_unknown_keys(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    bot = registry.create_bot(BotCreate(name="U", timeframe="5m", trading_mode="futures"))
    upd = registry.update_bot(bot.id, {"stake_amount": 250.0, "bogus_field": 1, "max_open_trades": 5})
    assert upd.stake_amount == 250.0 and upd.max_open_trades == 5
    assert not hasattr(upd, "bogus_field")
