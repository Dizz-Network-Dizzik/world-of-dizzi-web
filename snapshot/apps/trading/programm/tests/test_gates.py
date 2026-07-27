"""Kernlogik-Tests: Echtgeld-Gate (_live_ready) — validiert != echtgeldreif."""
import pytest

from backend.app.main import _live_ready, LIVE_MIN_WINDOWS, LIVE_MIN_PROFIT_FACTOR


@pytest.mark.parametrize("v,expected", [
    (None, False),
    ({"validated": 0}, False),
    ({"validated": 1, "windows": 1, "profit_factor": 2.0}, False),          # zu wenig Fenster
    ({"validated": 1, "windows": 3, "profit_factor": None}, False),         # kein PF (alt)
    ({"validated": 1, "windows": 3, "profit_factor": 0.8}, False),          # PF < 1
    ({"validated": 1, "windows": 3, "profit_factor": 1.0}, False),          # PF == 1 (Grenze)
    ({"validated": 1, "windows": 2, "profit_factor": 1.3}, True),           # reif
])
def test_live_ready(v, expected):
    ok, reason = _live_ready(v)
    assert ok is expected
    assert isinstance(reason, str) and reason


def test_thresholds_sane():
    assert LIVE_MIN_WINDOWS >= 2
    assert LIVE_MIN_PROFIT_FACTOR >= 1.0


# ───────── Befund E — Aggregat-Profit-Gate ─────────────────────────────────

def _wf_result(profit_total_pct: float) -> dict:
    return {
        "ok": True, "validated": True, "passed_windows": 2,
        "metrics": {
            "profit_total_pct": profit_total_pct,
            "profit_factor": 5.23,
            "total_trades": 95,
            "max_drawdown_pct": 12.0,
            "winrate_pct": 88.0,
        },
    }


def test_befund_e_negative_aggregate_blocks_validation(monkeypatch):
    """Mehrheit der Fenster positiv, Aggregat-Profit negativ → validated=False."""
    saved = {}
    monkeypatch.setattr("backend.app.engine.run_walkforward", lambda s, **kw: _wf_result(-4.55))
    monkeypatch.setattr("backend.app.stats.save_strategy_validation",
                        lambda s, v, w, m: saved.update(validated=v))

    from backend.app.main import _validate_strategy
    res = _validate_strategy("DcaDip", days=120, windows=3, embargo=1)
    assert res["validated"] is False, "Befund E: negativer Aggregat-Profit muss gate schließen"
    assert saved.get("validated") is False


def test_befund_e_zero_aggregate_blocks_validation(monkeypatch):
    """Aggregat-Profit genau 0,0 → validated=False (Grenzfall)."""
    saved = {}
    monkeypatch.setattr("backend.app.engine.run_walkforward", lambda s, **kw: _wf_result(0.0))
    monkeypatch.setattr("backend.app.stats.save_strategy_validation",
                        lambda s, v, w, m: saved.update(validated=v))

    from backend.app.main import _validate_strategy
    res = _validate_strategy("DcaDip", days=120, windows=3, embargo=1)
    assert res["validated"] is False
    assert saved.get("validated") is False


def test_befund_e_positive_aggregate_passes(monkeypatch):
    """Mehrheit UND Aggregat-Profit positiv → validated=True bleibt erhalten."""
    saved = {}
    monkeypatch.setattr("backend.app.engine.run_walkforward", lambda s, **kw: _wf_result(1.5))
    monkeypatch.setattr("backend.app.stats.save_strategy_validation",
                        lambda s, v, w, m: saved.update(validated=v))

    from backend.app.main import _validate_strategy
    res = _validate_strategy("DcaDip", days=120, windows=3, embargo=1)
    assert res["validated"] is True
    assert saved.get("validated") is True
