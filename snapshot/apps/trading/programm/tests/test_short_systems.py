"""Tests: klar deklarierte Handelsrichtung (direction) + short-spezialisierte Seed-Systeme (Task 3).

Hermetisch (in-memory, kein Katalog-File-I/O — wie test_opening): nur _normalize_system + die
SHORT_SEED_SYSTEMS-/_ensure-Logik."""
from backend.app import ai


# ----------------------- direction-Normalisierung -----------------------
def test_direction_defaults_to_long():
    out = ai._normalize_system({"id": "x", "name": "X"})
    assert out["direction"] == "long"


def test_market_neutral_forces_neutral_direction():
    out = ai._normalize_system({"id": "x", "name": "X", "market_neutral": True})
    assert out["direction"] == "neutral"
    # auch wenn faelschlich 'long' deklariert -> market_neutral gewinnt
    out2 = ai._normalize_system({"id": "x", "name": "X", "market_neutral": True, "direction": "long"})
    assert out2["direction"] == "neutral"


def test_direction_short_and_both_kept():
    assert ai._normalize_system({"id": "x", "name": "X", "direction": "short"})["direction"] == "short"
    assert ai._normalize_system({"id": "x", "name": "X", "direction": "both"})["direction"] == "both"


def test_invalid_direction_falls_back_to_long():
    assert ai._normalize_system({"id": "x", "name": "X", "direction": "sideways"})["direction"] == "long"


def test_neutral_without_market_neutral_is_contradiction_long():
    # 'neutral' ohne market_neutral ist widerspruechlich -> auf 'long' korrigiert.
    out = ai._normalize_system({"id": "x", "name": "X", "direction": "neutral"})
    assert out["direction"] == "long"


# ----------------------- Short-Seed-Systeme -----------------------
def test_short_seed_systems_declared():
    ids = {s["id"] for s in ai.SHORT_SEED_SYSTEMS}
    assert {"downside_breakout_short", "trend_flip_short",
            "funding_aware_short", "squeeze_momentum_release"} <= ids
    for s in ai.SHORT_SEED_SYSTEMS:
        assert s["direction"] in ("short", "both")
        assert not s.get("market_neutral")          # gerichtet, NICHT markt-neutral


def test_short_seeds_map_to_real_engines_where_buildable():
    by_id = {s["id"]: s for s in ai.SHORT_SEED_SYSTEMS}
    # Diese beiden bilden vorhandene short-faehige Engines ab -> tatsaechlich baubar.
    assert by_id["downside_breakout_short"]["freqtrade_template"] == "FuturesBreakoutVol"
    assert by_id["trend_flip_short"]["freqtrade_template"] == "Supertrend"


def test_funding_aware_short_is_honest_low_certainty():
    fa = next(s for s in ai.SHORT_SEED_SYSTEMS if s["id"] == "funding_aware_short")
    # Ehrlich (Gesetz 2): reiner gerichteter Short gegen den Krypto-Drift -> niedrige certainty.
    assert fa["direction"] == "short" and fa["certainty"] == "niedrig"


def test_ensure_short_systems_idempotent():
    base = [ai._normalize_system(s) for s in ai.SHORT_SEED_SYSTEMS]
    merged, changed = ai._ensure_short_systems(base)
    assert changed is False and len(merged) == len(base)
    merged2, changed2 = ai._ensure_short_systems([])
    assert changed2 is True and len(merged2) == len(ai.SHORT_SEED_SYSTEMS)


def test_seed_version_bumped_for_direction():
    assert ai.SEED_VERSION >= 8
