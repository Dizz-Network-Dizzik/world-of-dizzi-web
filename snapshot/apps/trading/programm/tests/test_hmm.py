"""Tests des leichtgewichtigen Gaussian-HMM (rein, deterministisch via fixem Seed in den Daten)."""
import random

from backend.app import hmm


def _two_regime_series(n_each=120, seed=7):
    """Erst ruhiger Abwärts-Drift, dann klarer Aufwärts-Drift (zwei gut trennbare Regimes)."""
    rng = random.Random(seed)
    down = [rng.gauss(-0.4, 0.3) for _ in range(n_each)]   # negativer Mittelwert
    up = [rng.gauss(0.5, 0.3) for _ in range(n_each)]      # positiver Mittelwert
    return down + up


def _three_segments(order, n=80, seed=11):
    """Baut eine Reihe aus drei klar getrennten Segmenten in der gewünschten Reihenfolge.
    ``order`` z.B. ('down','range','up') -> endet im up-Regime."""
    rng = random.Random(seed)
    spec = {"down": (-0.5, 0.2), "range": (0.0, 0.2), "up": (0.5, 0.2)}
    out = []
    for seg in order:
        mu, sd = spec[seg]
        out += [rng.gauss(mu, sd) for _ in range(n)]
    return out


def test_fit_returns_none_on_tiny_input():
    assert hmm.fit([0.1, 0.2, 0.3], n_states=3) is None


def test_fit_recovers_separated_means():
    obs = _two_regime_series()
    m = hmm.fit(obs, n_states=2)
    assert m is not None
    means = sorted(m["means"])
    assert means[0] < 0 < means[1]                  # ein negativer, ein positiver Zustand
    # Übergangs-Persistenz: Selbst-Übergänge dominieren (klebrige Regimes)
    assert all(m["trans"][i][i] > 0.5 for i in range(2))


def test_viterbi_decodes_current_regime_up():
    obs = _two_regime_series()                      # endet im Aufwärts-Regime
    m = hmm.fit(obs, n_states=2)
    path = hmm.viterbi(obs, m)
    hi = max(range(2), key=lambda i: m["means"][i])
    assert path[-1] == hi
    assert sum(1 for s in path[-20:] if s == hi) >= 15


def test_classify_labels_uptrend():
    res = hmm.classify(_three_segments(("down", "range", "up")), n_states=3)
    assert res is not None and res["regime"] == "trend_up"
    assert 0.0 <= res["confidence"] <= 1.0 and res["persistence"] > 0.5


def test_classify_labels_downtrend():
    res = hmm.classify(_three_segments(("up", "range", "down")), n_states=3)
    assert res["regime"] == "trend_down"


def test_classify_ends_in_range():
    res = hmm.classify(_three_segments(("down", "up", "range")), n_states=3)
    assert res["regime"] == "range"


def _mv_two(seed=5):
    rng = random.Random(seed)
    up = [[rng.gauss(0.4, 0.2), abs(rng.gauss(0.2, 0.05))] for _ in range(120)]   # ruhiger Aufwärts
    dn = [[rng.gauss(-0.5, 0.6), abs(rng.gauss(0.6, 0.1))] for _ in range(120)]   # volatiler Abwärts
    return up + dn


def test_fit_mv_recovers_two_states():
    m = hmm.fit_mv(_mv_two(), n_states=2)
    assert m is not None and m["dims"] == 2
    # ein Zustand mit negativem Rendite-Mittel, einer mit positivem
    r = sorted(s[0] for s in m["means"])
    assert r[0] < 0 < r[1]


def test_classify_mv_labels_downtrend_and_reports_vol():
    res = hmm.classify_mv(_mv_two(), n_states=2)        # endet im volatilen Abwärts-Segment
    assert res and res["multivariate"] and res["regime"] == "trend_down"
    assert res["state_vol"] is not None and res["state_vol"] > 0


def test_classify_includes_next_regime_anticipation():
    res = hmm.classify(_three_segments(("down", "range", "up")), n_states=3)
    assert "next_regime" in res and "stay_prob" in res and "transition_dist" in res
    assert 0.0 <= res["stay_prob"] <= 1.0
    assert res["next_regime"] in ("trend_up", "range", "trend_down")
    assert abs(sum(res["transition_dist"].values()) - 1.0) < 0.05    # Übergangszeile ~ Wahrscheinlichkeit


def test_viterbi_global_decode_robust_to_interior_spike():
    # Ein einzelner Ausreißer MITTEN in der Reihe darf das aktuelle Regime (Terminal) nicht kippen:
    # interne Punkte sind durch die Zukunft verankert (Forward+Backward bzw. Viterbi-Pfad).
    obs = _two_regime_series()
    m = hmm.fit(obs, n_states=2)
    base_last = hmm.viterbi(obs, m)[-1]
    spiked = obs[:]
    spiked[140] = -5.0          # Ausreißer tief im Aufwärts-Regime (Index 140 > 120)
    assert hmm.viterbi(spiked, m)[-1] == base_last     # Terminal-Regime unverändert
