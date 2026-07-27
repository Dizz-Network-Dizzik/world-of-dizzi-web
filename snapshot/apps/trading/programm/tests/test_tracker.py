"""Tests der verbesserten Regime-Erkennung (rein, ohne Netz/DB) — vola-normiert + Hysterese."""
from backend.app import tracker


def _trend(rate, n, p0=100.0):
    out, p = [], p0
    for _ in range(n):
        out.append(round(p, 6))
        p *= rate
    return out


def _flat(n, p0=100.0, jitter=0.0):
    # leicht oszillierend um p0 (range), optional mit Amplitude jitter
    import math
    return [round(p0 * (1.0 + jitter * math.sin(i * 0.7)), 6) for i in range(n)]


def test_uptrend_classified_trend_up():
    reg, z = tracker.classify_regime(_trend(1.01, 60))
    assert reg == "trend_up" and z > 0


def test_downtrend_classified_trend_down():
    reg, z = tracker.classify_regime(_trend(0.99, 60))
    assert reg == "trend_down" and z < 0


def test_flat_is_range():
    reg, z = tracker.classify_regime(_flat(60, jitter=0.002))
    assert reg == "range"
    assert abs(z) < tracker._TREND_ENTER


def test_vol_normalization_same_deviation_smaller_z_when_noisier():
    # Kernidee der Verbesserung: gleiche absolute Abweichung vom Slow-SMA (Schlusskurs 102),
    # aber höhere Streuung -> kleineres |z| (das Trendband ist vola-skaliert, nicht fix).
    import math
    calm = [100.0] * 29 + [102.0]
    noisy = [round(100.0 + 6.0 * math.sin(i), 6) for i in range(29)] + [102.0]
    _, z_calm = tracker.classify_regime(calm)
    _, z_noisy = tracker.classify_regime(noisy)
    assert abs(z_calm) > abs(z_noisy)


def test_hysteresis_keeps_weakening_uptrend():
    # z liegt zwischen EXIT und ENTER und der Vortrend war up -> bleibt sticky trend_up.
    import math
    # sanft steigend, sodass z im Halteband (0.3..0.8) liegt
    closes = [round(100 + i * 0.06 + 0.3 * math.sin(i * 0.5), 6) for i in range(60)]
    reg_no_prev, z = tracker.classify_regime(closes, prev_regime=None)
    reg_prev_up, _ = tracker.classify_regime(closes, prev_regime="trend_up")
    # Persistenz darf nie schwächer einstufen als ohne Vorzustand
    assert reg_prev_up in ("trend_up", reg_no_prev)
    if tracker._TREND_EXIT < z < tracker._TREND_ENTER:
        assert reg_prev_up == "trend_up" and reg_no_prev == "range"


def test_volatility_regime_relative_to_baseline():
    calm = [0.001, -0.001, 0.0012, -0.0008] * 6
    turbulent = [0.05, -0.04, 0.06, -0.05] * 6
    base = calm + calm
    reg_t, ratio_t = tracker.classify_volatility(turbulent, base)
    reg_c, ratio_c = tracker.classify_volatility(calm, turbulent)
    assert reg_t == "turbulent" and ratio_t >= tracker._VOL_HIGH
    assert reg_c == "calm" and ratio_c <= tracker._VOL_LOW


def test_short_series_defaults_range():
    reg, z = tracker.classify_regime([100.0, 101.0])
    assert reg == "range" and z == 0.0


def test_decode_regime_uses_hmm_and_reports_detail():
    # Klarer Aufwärts-Pfad -> HMM-Regime trend_up, Quelle "hmm", Detail vorhanden.
    closes = _trend(1.004, 220)
    rep = tracker.decode_regime(closes)
    assert rep is not None and rep["source"] == "hmm"
    assert rep["regime"] == "trend_up" and rep["hmm"]["regime"] == "trend_up"
    assert "vol_regime" in rep and "trend_z" in rep and "threshold_regime" in rep
    assert 0.0 <= rep["hmm"]["confidence"] <= 1.0


def test_decode_regime_falls_back_without_hmm(monkeypatch):
    # Schlägt das HMM fehl (beide Pfade), greift das Schwellen-Modell (source="threshold").
    monkeypatch.setattr(tracker.hmm, "classify", lambda *a, **k: None)
    monkeypatch.setattr(tracker.hmm, "classify_mv", lambda *a, **k: None)
    rep = tracker.decode_regime(_trend(0.996, 220))
    assert rep["source"] == "threshold" and rep["hmm"] is None
    assert rep["regime"] == rep["threshold_regime"] == "trend_down"


def test_decode_regime_too_short():
    assert tracker.decode_regime([100.0] * 10) is None


def test_decode_regime_honors_hmm_n_states(monkeypatch):
    monkeypatch.setattr(tracker, "get_hmm_config", lambda: {"n_states": 2})
    rep = tracker.decode_regime(_trend(1.004, 220))
    assert rep["source"] == "hmm" and rep["hmm"]["n_states"] == 2   # Config-n_states wird genutzt


def test_regime_bridge_roundtrip(tmp_path):
    p = tmp_path / "hmm_regime.json"
    assert tracker.write_regime_bridge("trend_up", 0.95, path=p)
    d = tracker.read_regime_bridge(path=p)
    assert d and d["regime"] == "trend_up" and d["confidence"] == 0.95


def test_regime_bridge_carries_exposure_scale(tmp_path):
    # D1: der Vol-Targeting-Exposure-Skalierer wird mitgeschrieben + gelesen (Gehirn→Hand).
    p = tmp_path / "b.json"
    assert tracker.write_regime_bridge("trend_down", 0.8, path=p, exposure_scale=0.6)
    d = tracker.read_regime_bridge(path=p)
    assert d and d["exposure_scale"] == 0.6
    # Default (kein exposure_scale) -> Feld None (Hand interpretiert None als "aus").
    assert tracker.write_regime_bridge("range", 0.5, path=p)
    assert tracker.read_regime_bridge(path=p)["exposure_scale"] is None


def test_regime_bridge_stale_and_missing(tmp_path):
    import json as _j
    import time as _t
    p = tmp_path / "r.json"
    p.write_text(_j.dumps({"regime": "range", "confidence": 0.9, "ts": int((_t.time() - 99999) * 1000)}))
    assert tracker.read_regime_bridge(path=p, max_age_s=3600) is None   # veraltet
    assert tracker.read_regime_bridge(path=tmp_path / "nope.json") is None  # fehlend
