"""Tests: Auto-Upgrade pro Bot (2026-06-10) — nach 1× manuell automatisch OOS-validierte
Gewinner übernehmen. Gates: oos_validated (anchored Walk-Forward) + Timeframe-Match."""
from types import SimpleNamespace

from backend.app import main


def _bot(bid, *, auto, opt_params=None, strategy="S", timeframe="15m"):
    return SimpleNamespace(id=bid, name=bid.upper(), strategy=strategy,
                           auto_upgrade=auto, opt_params=opt_params or {}, timeframe=timeframe)


def _patch(monkeypatch, bots, winner, *, oos_validated=1, opt_timeframe="15m"):
    monkeypatch.setattr(main.registry, "list_bots", lambda: list(bots))
    monkeypatch.setattr(main.stats, "get_optimization",
                        lambda strat: ({"params": winner, "profit_total_pct": 5.0,
                                        "oos_validated": oos_validated,
                                        "timeframe": opt_timeframe} if winner else None))
    calls = []
    monkeypatch.setattr(main, "_apply_learned_params",
                        lambda bot, params, profit_pct=None, restart=True: calls.append((bot.id, params)) or 1)
    return calls


def test_skips_when_auto_upgrade_off(monkeypatch):
    calls = _patch(monkeypatch, [_bot("b1", auto=False)], {"x": 2})
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == []


def test_applies_new_winner_when_on(monkeypatch):
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={})], {"x": 2})
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 1 and calls == [("b1", {"x": 2})]


def test_idempotent_when_already_applied(monkeypatch):
    # Bot hat den Gewinner schon → kein erneutes Anwenden.
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={"x": 2})], {"x": 2})
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == []


def test_session_merge_robust(monkeypatch):
    # Session-Bot hat zusätzlich 'session' in opt_params — Gewinner trotzdem als angewandt erkennen.
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={"x": 2, "session": 1})], {"x": 2})
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == []


def test_applies_when_winner_changed(monkeypatch):
    # Neuer Gewinner (anderer Wert) → anwenden.
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={"x": 2})], {"x": 3})
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 1 and calls == [("b1", {"x": 3})]


def test_no_winner_no_apply(monkeypatch):
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={})], None)
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == []


def test_gate_blocks_unvalidated_winner(monkeypatch):
    # Gewinner OHNE bestandene OOS-Validierung → Auto-Pfad wendet NICHT an (In-Sample-best-of-N).
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={})], {"x": 2}, oos_validated=0)
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == [] and out["skipped_gate"] == 1


def test_gate_blocks_timeframe_mismatch(monkeypatch):
    # Gewinner wurde auf 15m getunt, Bot läuft 1m → kein Auto-Rollout (Config-Mismatch).
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={}, timeframe="1m")],
                   {"x": 2}, opt_timeframe="15m")
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 0 and calls == [] and out["skipped_gate"] == 1


def test_gate_allows_legacy_without_timeframe(monkeypatch):
    # Legacy-Record ohne Timeframe-Feld: OOS-validiert reicht (kein Mismatch feststellbar).
    calls = _patch(monkeypatch, [_bot("b1", auto=True, opt_params={}, timeframe="1m")],
                   {"x": 2}, opt_timeframe=None)
    out = main._auto_upgrade_bots()
    assert out["applied_count"] == 1 and calls == [("b1", {"x": 2})]
