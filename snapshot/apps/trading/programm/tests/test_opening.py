"""Tests des Sonder-Trade-Typs „Börseneröffnung" (Normalisierung + Seed)."""
from backend.app import ai


def test_normalize_defaults_signal():
    out = ai._normalize_system({"id": "x", "name": "X"})
    assert out["trigger_type"] == "signal"
    assert out["opening_session"] == "none"
    assert out["opening_range_min"] is None


def test_normalize_session_open_defaults_to_us():
    out = ai._normalize_system({"id": "x", "name": "X", "trigger_type": "session_open"})
    assert out["trigger_type"] == "session_open"
    assert out["opening_session"] == "us"  # ohne explizite Session -> liquideste Annahme


def test_normalize_invalid_trigger_falls_back():
    out = ai._normalize_system({"id": "x", "name": "X", "trigger_type": "magic",
                                "opening_session": "mars", "opening_range_min": 20})
    assert out["trigger_type"] == "signal"
    assert out["opening_session"] == "none"
    # Signal-System darf keine Opening-Range tragen.
    assert out["opening_range_min"] is None


def test_normalize_session_open_keeps_range_and_session():
    out = ai._normalize_system({"id": "x", "name": "X", "trigger_type": "session_open",
                                "opening_session": "london", "opening_range_min": 30})
    assert out["opening_session"] == "london"
    assert out["opening_range_min"] == 30


def test_opening_seed_systems_exist():
    ids = {s["id"] for s in ai.OPENING_SEED_SYSTEMS}
    assert {"opening_range_breakout", "session_open_momentum",
            "monday_asia_open_trend", "opening_fade_reversion"} <= ids
    for s in ai.OPENING_SEED_SYSTEMS:
        assert s["trigger_type"] == "session_open"
        assert s["freqtrade_template"] == "SessionOpenBreakout"


def test_ensure_opening_systems_idempotent():
    base = [ai._normalize_system(s) for s in ai.OPENING_SEED_SYSTEMS]
    merged, changed = ai._ensure_opening_systems(base)
    assert changed is False and len(merged) == len(base)
    merged2, changed2 = ai._ensure_opening_systems([])
    assert changed2 is True and len(merged2) == len(ai.OPENING_SEED_SYSTEMS)
