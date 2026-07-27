"""Tests: Vola-skaliertes Positions-Sizing (P3) — Stake invers zur realisierten Volatilität."""
from types import SimpleNamespace

from backend.app import sizing


def _bot(bid="b1", stake=100.0, tag=1):
    return SimpleNamespace(id=bid, tag=tag, name=bid.upper(), strategy="S", stake_amount=stake)


def _patch(monkeypatch, tmp_path, cons_map, bots=None):
    """cons_map: {bot_id: {'volatility':..,'days_tracked':..}}."""
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    monkeypatch.setattr(sizing.meta, "consistency", lambda bid: cons_map.get(bid, {}))
    if bots is not None:
        monkeypatch.setattr(sizing.registry, "list_bots", lambda: list(bots))


def test_high_vol_shrinks_stake(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 4.0, "days_tracked": 5}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    # ref 100 × ziel 2 / vol 4 = 50.
    assert r["recommended_stake"] == 50.0 and r["factor"] == 0.5 and r["change"] is True


def test_low_vol_grows_stake(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 1.0, "days_tracked": 5}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 200.0 and r["factor"] == 2.0


def test_clamped_to_max(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 0.5, "days_tracked": 9}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 250.0  # 100×2/0.5=400 → Deckel 250


def test_clamped_to_min(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 16.0, "days_tracked": 9}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 25.0  # 100×2/16=12.5 → Unterkante 25


def test_neutral_when_too_few_days(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 4.0, "days_tracked": 2}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 100.0 and r["change"] is False and "Historie" in r["reason"]


def test_neutral_when_vol_unknown(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": None, "days_tracked": 9}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 100.0 and r["change"] is False


def test_small_change_not_flagged(tmp_path, monkeypatch):
    # vol 1.9 vs ziel 2.0 → ~105.3, nur ~5% Abweichung vom Stake 100 → keine „Änderung" (<10%).
    _patch(monkeypatch, tmp_path, {"b1": {"volatility_pct": 1.9, "days_tracked": 5}})
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["change"] is False


def test_recommend_aggregates_changes(tmp_path, monkeypatch):
    bots = [_bot("b1", 100.0, 1), _bot("b2", 100.0, 2), _bot("b3", 100.0, 3)]
    cons = {"b1": {"volatility_pct": 4.0, "days_tracked": 5},   # → 50, change
            "b2": {"volatility_pct": 2.0, "days_tracked": 5},   # → 100, neutral, no change
            "b3": {"volatility_pct": 0.5, "days_tracked": 5}}   # → 250, change
    _patch(monkeypatch, tmp_path, cons, bots=bots)
    out = sizing.recommend()
    assert out["n_bots"] == 3 and out["n_with_vol"] == 3 and out["n_changes"] == 2
