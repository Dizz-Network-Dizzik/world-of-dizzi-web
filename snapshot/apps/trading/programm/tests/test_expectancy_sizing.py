"""Tests: Erwartungswert-/Kelly-basiertes Sizing (Task 4).

Zwei Ebenen: (1) die reine Expectancy-Berechnung in stats._expectancy_from_profits, (2) der
Kelly-Tilt in sizing (opt-in). Kernforderung (Gesetz 2): ein Bot mit NEGATIVEM Erwartungswert
wird trotz hoher Winrate NIE hochgehebelt (winrate-naives Sizing ist ruinös)."""
from types import SimpleNamespace

from backend.app import sizing, stats


# ----------------------- stats._expectancy_from_profits (rein) -----------------------
def test_expectancy_balanced_positive():
    # 3 Gewinner à +2 %, 1 Verlierer −2 %: W=0.75, payoff=1 → Kelly=0.75-0.25/1=0.5
    ex = stats._expectancy_from_profits([2.0, 2.0, 2.0, -2.0])
    assert ex["winrate"] == 0.75 and ex["payoff"] == 1.0
    assert ex["kelly"] == 0.5 and ex["expectancy_r"] == 0.5
    assert ex["n_decided"] == 4


def test_high_winrate_but_negative_expectancy():
    # „Picking up pennies": 9× +1 %, 1× −20 %. Winrate 90 %, ABER Erwartungswert NEGATIV.
    ex = stats._expectancy_from_profits([1.0] * 9 + [-20.0])
    assert ex["winrate"] == 0.9
    assert ex["payoff"] == 0.05            # avg_win 1 / avg_loss 20
    assert ex["kelly"] is not None and ex["kelly"] < 0    # Kelly negativ trotz 90 % Winrate
    assert ex["expectancy_pct"] < 0        # Ø-Rendite je Trade negativ


def test_expectancy_no_losses_undefined():
    ex = stats._expectancy_from_profits([1.0, 2.0, 0.5])
    assert ex["payoff"] is None and ex["kelly"] is None and ex["expectancy_r"] is None
    assert ex["n_decided"] == 3


def test_expectancy_zero_profit_is_neutral():
    ex = stats._expectancy_from_profits([2.0, 0.0, -1.0])
    assert ex["n_trades"] == 3 and ex["n_decided"] == 2   # 0 zählt nicht als entschieden


def test_expectancy_empty():
    ex = stats._expectancy_from_profits([])
    assert ex["n_trades"] == 0 and ex["kelly"] is None


# ----------------------- sizing-Tilt (opt-in) -----------------------
def _bot(bid="b1", stake=100.0):
    return SimpleNamespace(id=bid, tag=1, name=bid.upper(), strategy="S", stake_amount=stake)


def _patch(monkeypatch, tmp_path, vol, days, expectancy):
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    monkeypatch.setattr(sizing.meta, "consistency",
                        lambda bid: {"volatility_pct": vol, "days_tracked": days})
    monkeypatch.setattr(sizing.stats, "trade_expectancy", lambda bid: expectancy)


def test_disabled_by_default_no_db_read_no_change(tmp_path, monkeypatch):
    # Default OFF: ex-Faktor 1.0, KEIN trade_expectancy-Aufruf (würde hier werfen).
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    monkeypatch.setattr(sizing.meta, "consistency", lambda bid: {"volatility_pct": 2.0, "days_tracked": 9})
    def _boom(bid):
        raise AssertionError("trade_expectancy darf bei deaktiviertem Tilt NICHT gelesen werden")
    monkeypatch.setattr(sizing.stats, "trade_expectancy", _boom)
    r = sizing.recommend_for(_bot(stake=100.0), sizing.get_config())
    assert r["recommended_stake"] == 100.0 and r["expectancy_mult"] == 1.0 and r["expectancy"] is None


def test_positive_edge_sizes_up_but_capped(tmp_path, monkeypatch):
    # Vol auf Ziel (Faktor 1) + starker positiver Kelly → moderat hoch, hart auf kelly_cap gedeckelt.
    ex = {"n_decided": 50, "kelly": 1.0, "winrate": 0.6, "payoff": 2.0}
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})  # fraction 0.25, cap 1.5, floor 0.5
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    # 1 + 0.25*1.0 = 1.25 → ref 100 × 1 × 1.25 = 125
    assert r["expectancy_mult"] == 1.25 and r["recommended_stake"] == 125.0


def test_huge_edge_hits_hard_cap(tmp_path, monkeypatch):
    ex = {"n_decided": 80, "kelly": 5.0}      # 1 + 0.25*5 = 2.25 → gedeckelt auf 1.5
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    assert r["expectancy_mult"] == 1.5    # harte Obergrenze greift


def test_negative_edge_never_levers_up(tmp_path, monkeypatch):
    # KERNFORDERUNG: hohe Winrate, aber negativer Kelly → Multiplikator < 1 (verkleinern, NIE hoch).
    ex = {"n_decided": 60, "kelly": -0.8, "winrate": 0.9, "payoff": 0.05}
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    assert r["expectancy_mult"] < 1.0          # 1 - 0.25*0.8 = 0.8
    assert r["recommended_stake"] < 100.0      # verkleinert statt vergrößert


def test_negative_edge_floored(tmp_path, monkeypatch):
    ex = {"n_decided": 60, "kelly": -10.0}     # 1 - 0.25*10 = -1.5 → Floor 0.5
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    assert r["expectancy_mult"] == 0.5         # harte Untergrenze greift


def test_too_few_trades_neutral(tmp_path, monkeypatch):
    ex = {"n_decided": 5, "kelly": 1.0}        # < min_trades_kelly (20) → neutral
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    assert r["expectancy_mult"] == 1.0 and r["recommended_stake"] == 100.0


def test_undefined_kelly_neutral(tmp_path, monkeypatch):
    ex = {"n_decided": 40, "kelly": None}      # reiner Gewinner-Track → Kelly undefiniert → neutral
    _patch(monkeypatch, tmp_path, vol=2.0, days=9, expectancy=ex)
    cfg = sizing.set_config({"expectancy_enabled": True})
    r = sizing.recommend_for(_bot(stake=100.0), cfg)
    assert r["expectancy_mult"] == 1.0


def test_config_caps_kept_consistent(tmp_path, monkeypatch):
    monkeypatch.setattr(sizing, "STATE_FILE", tmp_path / "sizing.json")
    cfg = sizing.set_config({"kelly_floor": 2.0, "kelly_cap": 0.5})   # vertauscht → getauscht
    assert cfg["kelly_floor"] == 0.5 and cfg["kelly_cap"] == 2.0
