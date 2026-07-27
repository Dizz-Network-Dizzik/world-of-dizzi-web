"""Tests der Session-/Eröffnungs-Zeitlogik (rein, ohne Netz/DB)."""
from datetime import datetime, timezone, timedelta

from backend.app import sessions


def _utc(h, m=0):
    return datetime(2026, 6, 8, h, m, tzinfo=timezone.utc)


def test_session_for_covers_all_hours():
    # Jede Stunde 0..23 faellt in genau ein Band.
    for h in range(24):
        assert sessions.session_for(_utc(h)) is not None


def test_session_for_band_boundaries():
    assert sessions.session_for(_utc(0)) == "asia"
    assert sessions.session_for(_utc(6, 59)) == "asia"
    assert sessions.session_for(_utc(7)) == "london"
    assert sessions.session_for(_utc(13)) == "eu_us_overlap"
    assert sessions.session_for(_utc(16)) == "us"
    assert sessions.session_for(_utc(21)) == "late_us"
    assert sessions.session_for(_utc(23, 59)) == "late_us"


def test_session_for_none():
    assert sessions.session_for(None) is None


def test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 6, 8, 13, 30)  # ohne tzinfo
    assert sessions.session_for(naive) == "eu_us_overlap"


def test_aware_non_utc_is_converted():
    # 09:30 in UTC+2 == 07:30 UTC -> london
    dt = datetime(2026, 6, 8, 9, 30, tzinfo=timezone(timedelta(hours=2)))
    assert sessions.session_for(dt) == "london"


def test_opening_window_hits_and_misses():
    assert sessions.opening_window(_utc(0, 30))["key"] == "asia"
    assert sessions.opening_window(_utc(8))["key"] == "london"
    assert sessions.opening_window(_utc(14, 59))["key"] == "us"
    # Ausserhalb der schmalen Open-Fenster -> None.
    assert sessions.opening_window(_utc(3)) is None
    assert sessions.opening_window(_utc(11)) is None
    assert sessions.opening_window(_utc(20)) is None
    assert sessions.opening_window(None) is None


def test_session_label():
    assert sessions.session_label("asia") == "Asien (Tokio)"
    assert sessions.session_label("unknown") == "unknown"
    assert sessions.session_label(None) == "—"


def test_opening_sessions_constant():
    assert {"asia", "london", "us", "eu_us_overlap", "none"} <= sessions.OPENING_SESSIONS
