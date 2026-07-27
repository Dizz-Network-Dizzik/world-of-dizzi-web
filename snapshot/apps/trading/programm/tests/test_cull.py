"""Tests: Auto-Cull (Selbst-Bewertung, konservativ) + Garantie, dass Löschen die Lern-DB nicht antastet."""
from types import SimpleNamespace

from backend.app import cull, registry, stats


def _bot(bid="b1", dry=True):
    return SimpleNamespace(id=bid, name="X", strategy="S", dry_run=dry, dry_run_wallet=1000.0)


def _patch(monkeypatch, tmp_path, *, days, avg, trend, closed):
    monkeypatch.setattr(cull, "STATE_FILE", tmp_path / "cull.json")           # Defaults, isoliert
    monkeypatch.setattr(cull.meta, "consistency",
                        lambda bid: {"days_tracked": days, "avg_profit_pct": avg, "trend_slope_pct": trend})
    monkeypatch.setattr(cull.stats, "bot_pnl", lambda bid, w: {"closed": closed, "profit_pct": avg})


def test_cull_when_clearly_and_persistently_bad(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=10, avg=-20.0, trend=-2.0, closed=50)
    assert cull._verdict_for(_bot(), cull.get_config())["verdict"] == "cull"


def test_keep_when_history_too_young(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=2, avg=-30.0, trend=-5.0, closed=100)
    assert cull._verdict_for(_bot(), cull.get_config())["verdict"] == "keep"


def test_keep_when_too_few_trades(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=20, avg=-30.0, trend=-5.0, closed=5)
    assert cull._verdict_for(_bot(), cull.get_config())["verdict"] == "keep"


def test_keep_when_loss_not_critical(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=20, avg=-5.0, trend=-5.0, closed=100)
    assert cull._verdict_for(_bot(), cull.get_config())["verdict"] == "keep"


def test_keep_when_recovering(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=20, avg=-30.0, trend=1.5, closed=100)
    assert cull._verdict_for(_bot(), cull.get_config())["verdict"] == "keep"


def test_master_is_protected(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=99, avg=-99.0, trend=-9.0, closed=999)
    v = cull._verdict_for(_bot(registry.MASTER_BOT_ID), cull.get_config())
    assert v["verdict"] == "keep" and "geschützt" in v["reason"]


def test_live_bot_is_protected(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, days=99, avg=-99.0, trend=-9.0, closed=999)
    assert cull._verdict_for(_bot(dry=False), cull.get_config())["verdict"] == "keep"


def test_delete_bot_does_not_touch_learning_db(tmp_path, monkeypatch):
    # GARANTIE: ein gelöschter Bot lässt stats.sqlite (Validierungen/Snapshots) unangetastet.
    monkeypatch.setattr(stats, "DATA_DIR", tmp_path)
    monkeypatch.setattr(stats, "DB_FILE", tmp_path / "stats.sqlite")
    monkeypatch.setattr(registry, "BOTS_FILE", tmp_path / "bots.json")
    monkeypatch.setattr(registry, "ENGINE_USERDIR", tmp_path)
    (tmp_path / "config_bot1_dryrun.json").write_text('{"exchange": {}}', encoding="utf-8")
    stats.save_strategy_validation("TrendFollowEma", True, 3, {
        "profit_factor": 1.2, "profit_total_pct": 5.0, "max_drawdown_pct": 3.0,
        "total_trades": 50, "winrate_pct": 55.0})
    from backend.app.models import BotCreate
    b = registry.create_bot(BotCreate(name="T", strategy="TrendFollowEma"))
    assert registry.delete_bot(b.id) is True
    # Learnings müssen die Löschung überleben:
    assert stats.get_strategy_validation("TrendFollowEma") is not None
