import pytest

from app.ai import analyst, observe, providers


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _snap(regime="range", aktionen=5, roi=-0.4):
    return {
        "mastermeta": {"regime": regime, "regime_konfidenz": 0.9},
        "governor": {"aktionen_gesamt": aktionen, "letzte_aktionen": []},
        "flotte": {"roi_pct": roi, "offene_trades": 30},
    }


def test_analyze_needs_two_snapshots():
    observe.record("dizzi", "tradingbot", _snap())
    assert analyst.analyze("dizzi") == 0


def test_regime_change_creates_info():
    observe.record("dizzi", "tradingbot", _snap(regime="range"))
    observe.record("dizzi", "tradingbot", _snap(regime="trend_up"))
    assert analyst.analyze("dizzi") == 1
    n = analyst.notices("dizzi")[0]
    assert n["severity"] == "info"
    assert "range" in n["title"] and "trend_up" in n["title"]


def test_governor_action_creates_warn():
    observe.record("dizzi", "tradingbot", _snap(aktionen=5))
    observe.record("dizzi", "tradingbot", _snap(aktionen=7))
    analyst.analyze("dizzi")
    sev = [n["severity"] for n in analyst.notices("dizzi")]
    assert "warn" in sev


def test_roi_drop_creates_warn():
    observe.record("dizzi", "tradingbot", _snap(roi=-0.2))
    observe.record("dizzi", "tradingbot", _snap(roi=-0.9))
    analyst.analyze("dizzi")
    assert any("ROI" in n["title"] for n in analyst.notices("dizzi"))


def test_no_change_no_notice():
    observe.record("dizzi", "tradingbot", _snap())
    observe.record("dizzi", "tradingbot", _snap())
    assert analyst.analyze("dizzi") == 0


def test_notice_dedup():
    assert analyst.add_notice("dizzi", "x", "info", "Gleicher Titel", "a") is True
    assert analyst.add_notice("dizzi", "x", "info", "Gleicher Titel", "b") is False
    assert len(analyst.notices("dizzi")) == 1


def test_mark_read():
    analyst.add_notice("dizzi", "x", "info", "T", "d")
    assert len(analyst.notices("dizzi", unread_only=True)) == 1
    assert analyst.mark_read("dizzi") == 1
    assert analyst.notices("dizzi", unread_only=True) == []


@pytest.mark.anyio
async def test_suggest_parses_llm_json(monkeypatch):
    observe.record("dizzi", "tradingbot", _snap())
    observe.record("dizzi", "tradingbot", _snap(regime="trend_up"))

    async def fake_quick(messages, model=None, *, format=None):
        return '[{"titel": "Scalping-Exposure prüfen", "begruendung": "ROI-Serie negativ."}]'
    monkeypatch.setattr(providers, "quick_chat", fake_quick)
    assert await analyst.suggest("dizzi") == 1
    n = analyst.notices("dizzi")[0]
    assert n["severity"] == "vorschlag"


@pytest.mark.anyio
async def test_suggest_survives_broken_llm(monkeypatch):
    observe.record("dizzi", "tradingbot", _snap())
    observe.record("dizzi", "tradingbot", _snap())

    async def broken(messages, model=None, *, format=None):
        raise RuntimeError("weg")
    monkeypatch.setattr(providers, "quick_chat", broken)
    assert await analyst.suggest("dizzi") == 0
