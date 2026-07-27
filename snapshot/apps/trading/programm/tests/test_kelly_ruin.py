"""Tests: FP-2 Ruin-Risiko-Analyse — Drawdown-Verteilung unter Kelly-Fraktionen (SPEC §5).

Monte-Carlo (reine Stdlib, seeded ⇒ deterministisch): Zwei-Punkt-Trade-Verteilung (Gewinn +b·R mit
Wahrscheinlichkeit p, Verlust −R), Equity multiplikativ ``×(1+f·X)``. Kelly-Optimum f* = p−(1−p)/b.

Die Assertions sind die BELEGE hinter den Design-Defaults (λ=0.25, kelly_cap, kelly_floor):
Ruin-Wahrscheinlichkeit steigt monoton in der Fraktion; Viertel-Kelly drückt sie um Größenordnungen
bei weiter positivem Wachstum; negativer Edge verliert bei JEDER Fraktion (⇒ nie hochhebeln);
fraktionaler Kelly schlägt fixed-stake im Median (Kompoundierung). Die Zahlen-Tabelle für die Doku
(docs/KELLY_SIZING_SPEC.md §6) stammt aus demselben Code mit mehr Pfaden."""
import random

# Bewusst klein gehalten (Suite-Laufzeit): 400 Pfade × 250 Trades reichen für die groben,
# weit getrennten Ordnungs-Aussagen unten. Doku-Tabelle: n_paths=2000.
N_PATHS = 400
N_TRADES = 250


def simulate_kelly(p: float, b: float, f: float, n_trades: int = N_TRADES,
                   n_paths: int = N_PATHS, seed: int = 7) -> dict:
    """Kompoundierende Pfade: Equity ×(1+f·X) je Trade. Liefert Median-Endkapital (Start 1.0),
    Median-Max-Drawdown und P(Max-DD ≥ 50 %) / P(Max-DD ≥ 80 %) (Ruin-Proxys)."""
    rng = random.Random(seed)
    terminals, max_dds = [], []
    for _ in range(n_paths):
        eq, peak, mdd = 1.0, 1.0, 0.0
        for _ in range(n_trades):
            x = b if rng.random() < p else -1.0
            eq = max(1e-12, eq * (1.0 + f * x))
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > mdd:
                mdd = dd
        terminals.append(eq)
        max_dds.append(mdd)
    terminals.sort()
    max_dds.sort()
    mid = n_paths // 2
    return {"median_terminal": terminals[mid], "median_max_dd": max_dds[mid],
            "p_dd50": sum(1 for d in max_dds if d >= 0.5) / n_paths,
            "p_dd80": sum(1 for d in max_dds if d >= 0.8) / n_paths}


def simulate_fixed(p: float, b: float, f0: float, n_trades: int = N_TRADES,
                   n_paths: int = N_PATHS, seed: int = 7) -> dict:
    """NICHT-kompoundierend (fixed-stake, heutiges Verhalten): Wealth += f0·X je Trade,
    f0 als Anteil des STARTkapitals. Vergleichsbasis für den Sim-Vergleich Kelly vs. fixed."""
    rng = random.Random(seed)
    terminals, max_dds = [], []
    for _ in range(n_paths):
        w, peak, mdd = 1.0, 1.0, 0.0
        for _ in range(n_trades):
            x = b if rng.random() < p else -1.0
            w += f0 * x
            if w > peak:
                peak = w
            dd = (peak - w) / peak if peak > 0 else 1.0
            if dd > mdd:
                mdd = dd
        terminals.append(w)
        max_dds.append(mdd)
    terminals.sort()
    max_dds.sort()
    mid = n_paths // 2
    return {"median_terminal": terminals[mid], "median_max_dd": max_dds[mid],
            "p_dd50": sum(1 for d in max_dds if d >= 0.5) / n_paths}


# Szenario A: solider positiver Edge (p=0.55, b=1.2 ⇒ f* = 0.55 − 0.45/1.2 = 0.175).
_P, _B = 0.55, 1.2
_F_STAR = _P - (1 - _P) / _B


def test_ruin_probability_monotone_in_kelly_fraction():
    fracs = [0.1, 0.25, 0.5, 1.0]
    p50 = [simulate_kelly(_P, _B, lam * _F_STAR)["p_dd50"] for lam in fracs]
    for a, c in zip(p50, p50[1:]):
        assert a <= c + 1e-9, f"P(DD≥50%) nicht monoton: {p50}"
    assert p50[-1] > 0.5           # Voll-Kelly: Halbierung des Kapitals ist der NORMALFALL
    assert p50[1] < 0.10           # Viertel-Kelly: seltenes Ereignis — Größenordnungen dazwischen


def test_quarter_kelly_keeps_positive_growth():
    r = simulate_kelly(_P, _B, 0.25 * _F_STAR)
    assert r["median_terminal"] > 1.5          # deutlich positives Median-Wachstum …
    assert r["median_max_dd"] < 0.35           # … bei erträglichem Median-Drawdown
    full = simulate_kelly(_P, _B, _F_STAR)
    assert full["median_max_dd"] > 0.5         # Voll-Kelly-Drawdowns sind praktisch untragbar


def test_negative_edge_loses_at_every_fraction_monotonically():
    # „Pennies vor der Dampfwalze": p=0.9, b=0.05 ⇒ E = 0.9·0.05 − 0.1 < 0, f* < 0.
    meds = [simulate_kelly(0.9, 0.05, f)["median_terminal"] for f in (0.05, 0.1, 0.2)]
    assert all(m < 1.0 for m in meds), f"negativer Edge darf nie wachsen: {meds}"
    for a, c in zip(meds, meds[1:]):
        assert a >= c - 1e-9                   # mehr Einsatz ⇒ schneller kaputt (monoton)
    # Beleg für kelly_floor: der Sizer darf so einen Bot nur VERKLEINERN (mult<1), nie hebeln.


def test_fractional_kelly_beats_fixed_stake_median_growth():
    kelly = simulate_kelly(_P, _B, 0.25 * _F_STAR)
    fixed = simulate_fixed(_P, _B, 0.25 * _F_STAR)
    # Kompoundierung: gleicher Einsatz-Anteil, aber Kelly reinvestiert — Median-Endkapital klar höher.
    assert kelly["median_terminal"] > fixed["median_terminal"]
    assert fixed["median_terminal"] > 1.0      # fixed gewinnt auch (positiver Edge), nur langsamer


def test_simulation_deterministic_seeded():
    a = simulate_kelly(_P, _B, 0.25 * _F_STAR, n_paths=50)
    c = simulate_kelly(_P, _B, 0.25 * _F_STAR, n_paths=50)
    assert a == c                              # seeded ⇒ reproduzierbare Belege (kein Flaki-Test)
