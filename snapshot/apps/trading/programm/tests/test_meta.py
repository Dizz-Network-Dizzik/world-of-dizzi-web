"""Kernlogik-Tests: Multi-Objective-Score + Mutations-Generator (Lern-Loop)."""
from backend.app import meta


def test_opt_score_prefers_robust_over_overtrader():
    # Overtrader hat minimal besseren Roh-Profit, aber hohen DD + viele Trades -> schlechterer Score.
    robust = {"ok": True, "profit_total_pct": -6.0, "max_drawdown_pct": 8.0, "total_trades": 200}
    overtrader = {"ok": True, "profit_total_pct": -4.0, "max_drawdown_pct": 20.0, "total_trades": 1000}
    assert meta._opt_score(robust) > meta._opt_score(overtrader)


def test_opt_score_invalid_is_sentinel():
    assert meta._opt_score({"ok": False, "profit_total_pct": 5}) == -1e9
    assert meta._opt_score({"ok": True, "profit_total_pct": None}) == -1e9


def test_mutate_params_stays_in_bounds_and_int():
    specs = [{"name": "rsi", "min": 10, "max": 20, "default": 14},
             {"name": "sl", "min": 1.0, "max": 3.0, "default": 2.0}]
    base = {"rsi": 14, "sl": 2.0}
    cands = meta.mutate_params(base, specs, n=30, scale=0.6)
    assert len(cands) == 30
    for c in cands:
        assert 10 <= c["rsi"] <= 20 and isinstance(c["rsi"], int)
        assert 1.0 <= c["sl"] <= 3.0


# --- Regime-/Session-Advice: Mindest-Stichprobe + Positiv-Expectancy-Filter (_MIN_ADVICE_N) ---
# Live-Bug (17.06.): regime_advice empfahl FuturesMacdRsiScalp für RANGE, obwohl avg=-0.09 %
# (n≥3 + reine avg-Sortierung kürte die „am wenigsten schlechte" Verlust-Strategie). Fix: nur
# Zellen mit n≥_MIN_ADVICE_N UND avg>0 zählen als empirische Empfehlung; sonst regelbasiert.

def test_regime_advice_excludes_negative_expectancy_cells(monkeypatch):
    # Alle range-Zellen negativ → KEINE empirische Empfehlung (Fallback regelbasiert), NIE ein Verlierer.
    monkeypatch.setattr(meta.stats, "get_market_snapshots",
                        lambda limit=1: [{"regime": "range", "volatility": 0.5}])
    rp_trade = {"data_sufficient": True, "data_points": 800, "table": [
        {"strategy": "FuturesMacdRsiScalp", "regime": "range", "avg_profit_pct": -0.05, "n": 600},
        {"strategy": "FuturesBbandsBounce", "regime": "range", "avg_profit_pct": -0.36, "n": 200},
    ]}
    rp_day = {"data_sufficient": False, "data_points": 0, "table": []}
    out = meta.regime_advice(rp_trade, rp_day)
    assert out["source"] == "regelbasiert"
    assert "FuturesMacdRsiScalp" not in out["recommended"]


def test_regime_advice_requires_min_sample(monkeypatch):
    # Tiny-n-Positiv (n=6) darf die large-n-Positiv (n=120) NICHT verdrängen.
    monkeypatch.setattr(meta.stats, "get_market_snapshots",
                        lambda limit=1: [{"regime": "range", "volatility": 0.5}])
    rp_trade = {"data_sufficient": True, "data_points": 200, "table": [
        {"strategy": "DcaDip", "regime": "range", "avg_profit_pct": 2.0, "n": 6},
        {"strategy": "GridRange", "regime": "range", "avg_profit_pct": 0.3, "n": 120},
    ]}
    rp_day = {"data_sufficient": False, "data_points": 0, "table": []}
    out = meta.regime_advice(rp_trade, rp_day)
    assert out["source"] == "empirisch (Trades)"
    assert out["recommended"] == ["GridRange"]


def test_session_advice_excludes_negative_and_small_n(monkeypatch):
    # Gleiches Filter-Gesetz auf dem Session-Pfad: nur n≥_MIN_ADVICE_N UND avg>0.
    monkeypatch.setattr(meta.sessions, "session_for", lambda now: "asia")
    monkeypatch.setattr(meta.sessions, "opening_window", lambda now: None)
    monkeypatch.setattr(meta.sessions, "session_label", lambda s: s)
    sp = {"data_sufficient": True, "data_points": 300, "table": [
        {"strategy": "FuturesBreakoutVol", "session": "asia", "session_label": "asia", "avg_profit_pct": -0.32, "n": 350},
        {"strategy": "DcaDip", "session": "asia", "session_label": "asia", "avg_profit_pct": 1.5, "n": 5},
        {"strategy": "FuturesBbandsBounce", "session": "asia", "session_label": "asia", "avg_profit_pct": 0.16, "n": 180},
    ]}
    out = meta.session_advice(sp)
    assert out["source"] == "empirisch (Trades)"
    assert out["recommended"] == ["FuturesBbandsBounce"]
