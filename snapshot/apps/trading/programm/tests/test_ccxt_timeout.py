"""Tests des Hänger-Schutzes: expliziter ccxt-Call-Timeout in Bot-Configs (Heilung „Bot tot aber läuft").

Die Migration ``ensure_ccxt_timeout`` trägt den Timeout idempotent in BESTEHENDE Configs nach, ohne
sonst etwas zu ändern; eine kaputte Datei bricht den Lauf nicht ab. Isoliert über gepatchtes ENGINE_USERDIR.
"""
import json

from backend.app import registry


def _cfg(timeout=False):
    ex = {"name": "bitget",
          "pair_whitelist": ["BTC/USDT:USDT"],
          "ccxt_config": {"enableRateLimit": True, "rateLimit": 500},
          "ccxt_async_config": {"enableRateLimit": True, "rateLimit": 500}}
    if timeout:
        ex["ccxt_config"]["timeout"] = registry.EXCHANGE_TIMEOUT_MS
        ex["ccxt_async_config"]["timeout"] = registry.EXCHANGE_TIMEOUT_MS
    return {"exchange": ex, "max_open_trades": 3, "dry_run": True}


def test_timeout_value_sane():
    assert isinstance(registry.EXCHANGE_TIMEOUT_MS, int)
    assert 10000 <= registry.EXCHANGE_TIMEOUT_MS <= 120000  # > ccxt-Default (10 s), nicht absurd hoch


def test_migration_adds_timeout_preserving_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_aaa111.json").write_text(json.dumps(_cfg(timeout=False)), encoding="utf-8")
    assert registry.ensure_ccxt_timeout() == 1
    out = json.loads((tmp_path / "config_aaa111.json").read_text(encoding="utf-8"))
    assert out["exchange"]["ccxt_config"]["timeout"] == registry.EXCHANGE_TIMEOUT_MS
    assert out["exchange"]["ccxt_async_config"]["timeout"] == registry.EXCHANGE_TIMEOUT_MS
    # alles andere bleibt unberührt
    assert out["exchange"]["ccxt_config"]["rateLimit"] == 500
    assert out["exchange"]["pair_whitelist"] == ["BTC/USDT:USDT"]
    assert out["max_open_trades"] == 3


def test_migration_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_bbb222.json").write_text(json.dumps(_cfg(timeout=True)), encoding="utf-8")
    assert registry.ensure_ccxt_timeout() == 0  # bereits vorhanden → kein erneutes Schreiben


def test_migration_skips_reference_configs(tmp_path, monkeypatch):
    """Vorlage + getrackte Research-Configs werden NICHT angefasst (kein Versionskontroll-Rauschen)."""
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    for nm in ("config_bot1_dryrun.json", "config_research_futures.json", "config_research_spot.json"):
        (tmp_path / nm).write_text(json.dumps(_cfg(timeout=False)), encoding="utf-8")
    assert registry.ensure_ccxt_timeout() == 0
    # unverändert geblieben (kein timeout nachgetragen)
    ref = json.loads((tmp_path / "config_research_futures.json").read_text(encoding="utf-8"))
    assert "timeout" not in ref["exchange"]["ccxt_config"]


def test_migration_survives_broken_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_ccc333.json").write_text("{ kaputt ", encoding="utf-8")          # defekt
    (tmp_path / "config_ddd444.json").write_text(json.dumps(_cfg(timeout=False)), encoding="utf-8")
    assert registry.ensure_ccxt_timeout() == 1  # kaputte Datei stoppt den Lauf nicht, gute wird gepatcht
