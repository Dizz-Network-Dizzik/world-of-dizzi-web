"""Tests der Fundamental-Schicht — Kalender-Parsing/Seed/Event-Risiko (rein, ohne Netz)."""
from datetime import datetime, timedelta, timezone

from backend.app import fundamental as fnd

_SAMPLE = [
    {"title": "FOMC Statement", "country": "USD", "date": "2026-06-17T14:00:00-04:00",
     "impact": "High", "forecast": "", "previous": ""},
    {"title": "Bank Holiday", "country": "AUD", "date": "2026-06-08T17:00:00-04:00",
     "impact": "Holiday", "forecast": "", "previous": ""},
    {"title": "Flash PMI", "country": "EUR", "date": "2026-06-10T04:00:00-04:00",
     "impact": "Medium", "forecast": "51.2", "previous": "50.8"},
]


def test_to_utc_ms_handles_offsets_and_z():
    a = fnd._to_utc_ms("2026-06-17T14:00:00-04:00")
    b = fnd._to_utc_ms("2026-06-17T18:00:00+00:00")
    c = fnd._to_utc_ms("2026-06-17T18:00:00Z")
    assert a == b == c                       # gleicher Moment, verschiedene Schreibweisen
    assert fnd._to_utc_ms("kaputt") is None


def test_parse_faireconomy_normalizes_and_sorts():
    evs = fnd.parse_faireconomy(_SAMPLE)
    assert [e["title"] for e in evs] == ["Bank Holiday", "Flash PMI", "FOMC Statement"]  # zeitlich sortiert
    assert all({"title", "country", "impact", "ts"} <= set(e) for e in evs)
    assert evs[-1]["impact"] == "High" and evs[-1]["country"] == "USD"


def test_is_high_impact_filter():
    hi = {"impact": "High"}
    med = {"impact": "Medium"}
    hol = {"impact": "Holiday"}
    assert fnd.is_high_impact(hi)
    assert not fnd.is_high_impact(med)
    assert fnd.is_high_impact(med, include_medium=True)
    assert not fnd.is_high_impact(hol, include_medium=True)


def test_seed_events_are_future_high_impact():
    now = int(datetime(2026, 6, 8, tzinfo=timezone.utc).timestamp() * 1000)
    evs = fnd._seed_events(now, horizon_days=45)
    assert evs, "Seed sollte kommende Events liefern"
    assert all(e["ts"] >= now for e in evs)              # nur zukünftige
    assert all(e["impact"] == "High" for e in evs)       # nur High-Impact
    assert any("FOMC" in e["title"] for e in evs)        # FOMC 2026-06-17 liegt im Fenster
    assert all(e.get("approx") for e in evs)             # als approximativ markiert


def test_first_friday_is_a_friday():
    f = fnd._first_friday(2026, 7)
    assert f.weekday() == 4                               # Freitag


# ---------- Event-Risiko (F2) ----------
_CFG = {"pre_window_h": 12.0, "post_window_h": 6.0, "elevated_window_h": 36.0,
        "include_medium": 0, "cache_hours": 6.0, "dampen": 0.5}


def _ev(hours_from_now, now_ms, impact="High", title="FOMC"):
    return {"title": title, "country": "USD", "impact": impact,
            "ts": now_ms + int(hours_from_now * 3.6e6)}


def test_event_risk_high_inside_pre_window():
    now = 1_750_000_000_000
    r = fnd.event_risk(now, [_ev(5, now)], _CFG)          # Event in 5 h < pre 12 h
    assert r["event_risk"] == "high"
    assert _CFG["dampen"] <= r["dir_scale"] < 1.0         # gedämpft (stetig), nie unter den Boden
    assert r["next_event"]["hours_until"] == 5.0


def test_event_risk_high_inside_post_window():
    now = 1_750_000_000_000
    r = fnd.event_risk(now, [_ev(-3, now)], _CFG)         # Event vor 3 h < post 6 h
    assert r["event_risk"] == "high"


def test_event_risk_elevated_then_none():
    now = 1_750_000_000_000
    r_elev = fnd.event_risk(now, [_ev(24, now)], _CFG)    # in 24 h: < elevated 36, > pre 12
    assert r_elev["event_risk"] == "elevated" and 0.5 < r_elev["dir_scale"] < 1.0
    r_none = fnd.event_risk(now, [_ev(100, now)], _CFG)   # weit weg
    assert r_none["event_risk"] == "none" and r_none["dir_scale"] == 1.0


def test_event_risk_ignores_low_and_medium_by_default():
    now = 1_750_000_000_000
    r = fnd.event_risk(now, [_ev(2, now, impact="Medium"), _ev(3, now, impact="Low")], _CFG)
    assert r["event_risk"] == "none"                      # ohne include_medium kein Risiko
    r2 = fnd.event_risk(now, [_ev(2, now, impact="Medium")], {**_CFG, "include_medium": 1})
    assert r2["event_risk"] == "high"


def test_dir_scale_monotonic():
    assert fnd.dir_scale("none", _CFG) == 1.0
    assert fnd.dir_scale("high", _CFG) == 0.5
    assert fnd.dir_scale("none", _CFG) > fnd.dir_scale("elevated", _CFG) > fnd.dir_scale("high", _CFG)


def test_event_weight_ordering():
    assert fnd._event_weight("FOMC Statement & Rate Decision") == 1.0
    assert fnd._event_weight("Core CPI m/m") == 0.85
    assert fnd._event_weight("Non-Farm Employment Change") == 0.7
    assert fnd._event_weight("Some Random Event") == 0.5


def test_event_risk_dampening_event_type_and_proximity():
    now = 1_750_000_000_000
    r_fomc = fnd.event_risk(now, [_ev(2, now, title="FOMC Rate Decision")], _CFG)
    r_cpi = fnd.event_risk(now, [_ev(2, now, title="CPI m/m")], _CFG)
    assert r_fomc["dir_scale"] < r_cpi["dir_scale"]               # FOMC dämpft stärker als CPI
    r_close = fnd.event_risk(now, [_ev(1, now, title="FOMC")], _CFG)
    r_far = fnd.event_risk(now, [_ev(10, now, title="FOMC")], _CFG)   # 10h < pre 12 -> noch high
    assert r_close["dir_scale"] < r_far["dir_scale"]             # näher dämpft stärker
    assert r_close["dir_scale"] >= _CFG["dampen"] - 0.01         # nie unter den Boden


# ---------- Krypto-Fundamentals + Makro-Stance (F4/F5) ----------
_CG = {"data": {"market_cap_percentage": {"btc": 54.3, "eth": 17.1},
                "total_market_cap": {"usd": 2.4e12}, "market_cap_change_percentage_24h_usd": -3.1}}


def test_parse_global_extracts_fields():
    cf = fnd._parse_global(_CG)
    assert cf["btc_dominance"] == 54.3 and cf["mcap_change_24h_pct"] == -3.1
    assert cf["total_mcap_usd"] == 2.4e12


def test_crypto_risk_thresholds():
    assert fnd._crypto_risk({"ok": True, "mcap_change_24h_pct": -3.1}) == "risk_off"
    assert fnd._crypto_risk({"ok": True, "mcap_change_24h_pct": 2.0}) == "risk_on"
    assert fnd._crypto_risk({"ok": True, "mcap_change_24h_pct": 0.3}) == "neutral"
    assert fnd._crypto_risk({"ok": False}) == "unknown"


def test_macro_stance_risk_off_on_crypto_drawdown():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": -3.1, "btc_dominance": 54.3, "source": "given"}
    st = fnd.macro_stance(er=er, cf=cf)
    assert st["stance"] == "risk_off" and st["crypto_risk"] == "risk_off"


def test_macro_stance_risk_off_on_high_event():
    er = {"event_risk": "high", "high_impact_upcoming": [{"hours_until": 3.0}], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 0.2, "source": "given"}
    assert fnd.macro_stance(er=er, cf=cf)["stance"] == "risk_off"   # High-Impact-Event dominiert


def test_parse_num_and_suffixes():
    assert fnd._parse_num("3.2%") == 3.2
    assert fnd._parse_num("150K") == 150000.0
    assert fnd._parse_num("-0.3") == -0.3
    assert fnd._parse_num("") is None and fnd._parse_num("n/a") is None


def test_surprise_direction():
    assert fnd._surprise_direction("Core CPI m/m", 3.5, 3.2) == "hawkish"   # heißer = hawkish
    assert fnd._surprise_direction("CPI y/y", 3.0, 3.2) == "dovish"
    assert fnd._surprise_direction("Unemployment Rate", 4.2, 4.0) == "dovish"
    assert fnd._surprise_direction("Random Gauge", 1.0, 2.0) == "neutral"


def test_macro_surprise_picks_recent_event_with_actual():
    now = 1_750_000_000_000
    evs = [{"title": "Core CPI m/m", "impact": "High", "ts": now - int(3 * 3.6e6),
            "actual": "3.5", "forecast": "3.2"},
           {"title": "Old CPI", "impact": "High", "ts": now - int(40 * 3.6e6),
            "actual": "2", "forecast": "2"}]
    sup = fnd.macro_surprise(evs, now)
    assert sup and sup["title"] == "Core CPI m/m" and sup["direction"] == "hawkish"
    assert sup["surprise"] == 0.3
    # ohne actual -> kein Surprise
    assert fnd.macro_surprise([{"title": "CPI", "impact": "High", "ts": now - int(2 * 3.6e6),
                                "actual": "", "forecast": "3.2"}], now) is None


def test_macro_stance_hawkish_surprise_forces_risk_off():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 2.5, "source": "given"}        # eigentlich risk_on
    assert fnd.macro_stance(er=er, cf=cf, sup={"direction": "hawkish"})["stance"] == "risk_off"


def test_onchain_signal_thresholds():
    assert fnd._onchain_signal(20.0, 200.0) == "stretched"      # NVT hoch
    assert fnd._onchain_signal(-15.0, 50.0) == "stretched"      # Adoption fällt
    assert fnd._onchain_signal(10.0, 60.0) == "healthy"
    assert fnd._onchain_signal(1.0, 95.0) == "neutral"


def test_macro_stance_onchain_stretched_blocks_risk_on():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 2.5, "source": "given"}    # eigentlich risk_on
    assert fnd.macro_stance(er=er, cf=cf, oc={"signal": "healthy"})["stance"] == "risk_on"
    assert fnd.macro_stance(er=er, cf=cf, oc={"signal": "stretched"})["stance"] == "risk_off"


def test_dvol_from_rows_parses_close_and_median():
    rows = [[1, 40, 41, 39, 40.0], [2, 40, 46, 40, 45.0], [3, 45, 48, 44, 47.0]]
    cur, base = fnd._dvol_from_rows(rows)
    assert cur == 47.0 and base == 45.0                 # letzter Close + Median (exerziert statistics.median)
    assert fnd._dvol_from_rows([]) is None


def test_iv_signal_thresholds():
    assert fnd._iv_signal(60.0, 40.0) == "elevated"     # 1.5x Baseline
    assert fnd._iv_signal(30.0, 50.0) == "calm"         # 0.6x
    assert fnd._iv_signal(45.0, 42.0) == "normal"
    assert fnd._iv_signal(None, 40.0) == "normal"


def test_macro_stance_elevated_iv_blocks_risk_on():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 2.5, "source": "given"}    # eigentlich risk_on
    assert fnd.macro_stance(er=er, cf=cf, fv={"signal": "normal"})["stance"] == "risk_on"
    assert fnd.macro_stance(er=er, cf=cf, fv={"signal": "elevated"})["stance"] == "risk_off"


def test_fred_regime_logic():
    assert fnd._fred_regime(0.3, 0.0, 0.0) == "tightening"      # NFCI > 0 = straff
    assert fnd._fred_regime(-0.05, 0.05, 0.0) == "tightening"   # NFCI steigt
    assert fnd._fred_regime(-0.2, -0.02, 0.0) == "easing"       # locker + fallend
    assert fnd._fred_regime(-0.05, 0.0, 0.0) == "neutral"
    assert fnd._fred_regime(None, None, None) == "unbekannt"


def test_macro_stance_real_macro_overrides():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 2.5, "source": "given"}    # eigentlich risk_on
    assert fnd.macro_stance(er=er, cf=cf, mr={"regime": "tightening"})["stance"] == "risk_off"
    assert fnd.macro_stance(er=er, cf=cf, mr={"regime": "easing"})["stance"] == "risk_on"


def test_macro_stance_risk_on_only_when_calm():
    er = {"event_risk": "none", "high_impact_upcoming": [], "source": "given"}
    cf = {"ok": True, "mcap_change_24h_pct": 2.5, "source": "given"}
    assert fnd.macro_stance(er=er, cf=cf)["stance"] == "risk_on"
    # ... aber NICHT risk_on, wenn ein Event-Druck besteht
    er2 = {"event_risk": "elevated", "high_impact_upcoming": [{"hours_until": 20.0}], "source": "given"}
    assert fnd.macro_stance(er=er2, cf=cf)["stance"] == "neutral"
