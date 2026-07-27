"""Tests: Horizont-Modell (2026-06-10) — Ableitung, Migration, Spot→Futures-Konvertierung, Kategorie."""
import json
from types import SimpleNamespace

from backend.app import models, registry
from backend.app.models import BotCreate


# ---------------------------------------------------------------- Ableitung
def test_tf_minutes():
    assert models.tf_minutes("1m") == 1
    assert models.tf_minutes("15m") == 15
    assert models.tf_minutes("1h") == 60
    assert models.tf_minutes("4h") == 240
    assert models.tf_minutes("1d") == 1440
    assert models.tf_minutes("bad") is None


def test_derive_horizon_boundaries():
    assert models.derive_horizon("1m") == "scalping"
    assert models.derive_horizon("5m") == "scalping"
    assert models.derive_horizon("15m") == "intraday"
    assert models.derive_horizon("1h") == "intraday"
    assert models.derive_horizon("4h") == "swing"
    assert models.derive_horizon("1d") == "swing"
    assert models.derive_horizon("") == "intraday"  # Fallback


def test_pairs_to_futures():
    assert registry._pairs_to_futures(["BTC/USDT", "ETH/USDT"]) == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    # idempotent: bereits :USDT bleibt unverändert
    assert registry._pairs_to_futures(["BTC/USDT:USDT"]) == ["BTC/USDT:USDT"]


# ---------------------------------------------------------------- Registry-Migrationen (isoliert)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "BOTS_FILE", tmp_path / "bots.json")
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_bot1_dryrun.json").write_text('{"exchange": {}}', encoding="utf-8")


def test_create_sets_horizon_from_timeframe(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    b = registry.create_bot(BotCreate(name="Scalp", strategy="FuturesMacdRsiScalp", timeframe="1m"))
    assert b.horizon == "scalping"
    b2 = registry.create_bot(BotCreate(name="Swing", strategy="TrendFollowEma", timeframe="4h"))
    assert b2.horizon == "swing"


def test_assign_missing_horizons(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    # Bots OHNE horizon direkt in die Datei schreiben (Altbestand-Simulation).
    raw = {
        "a": {"id": "a", "name": "A", "strategy": "S", "timeframe": "5m"},
        "b": {"id": "b", "name": "B", "strategy": "S", "timeframe": "1h"},
        "c": {"id": "c", "name": "C", "strategy": "S", "timeframe": "4h"},
    }
    (tmp_path / "bots.json").write_text(json.dumps(raw), encoding="utf-8")
    n = registry.assign_missing_horizons()
    assert n == 3
    bots = {b.id: b for b in registry.list_bots()}
    assert bots["a"].horizon == "scalping" and bots["b"].horizon == "intraday" and bots["c"].horizon == "swing"
    # idempotent: zweiter Lauf ändert nichts
    assert registry.assign_missing_horizons() == 0


def test_convert_spot_to_futures(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    raw = {
        "s1": {"id": "s1", "name": "S1", "strategy": "TrendFollowEma", "timeframe": "1h",
               "trading_mode": "spot", "pairs": ["BTC/USDT", "ETH/USDT"], "horizon": "intraday"},
        "f1": {"id": "f1", "name": "F1", "strategy": "FuturesMacdRsiScalp", "timeframe": "1m",
               "trading_mode": "futures", "pairs": ["BTC/USDT:USDT"], "horizon": "scalping"},
    }
    (tmp_path / "bots.json").write_text(json.dumps(raw), encoding="utf-8")
    converted = registry.convert_spot_to_futures()
    assert converted == ["s1"]  # nur der Spot-Bot
    bots = {b.id: b for b in registry.list_bots()}
    assert bots["s1"].trading_mode == "futures"
    assert bots["s1"].pairs == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert bots["f1"].pairs == ["BTC/USDT:USDT"]  # unverändert
    # idempotent: kein Spot mehr → zweiter Lauf leer
    assert registry.convert_spot_to_futures() == []
