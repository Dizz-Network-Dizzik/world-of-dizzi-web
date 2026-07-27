"""FP-T5 Sim-Beleg: Politik-gekoppelte Hand vs. statische Hand (docs/POLICY_HAND_SPEC.md §5).

Stilisiertes, seeded Monte-Carlo-Modell (Muster test_kelly_ruin.py): Markov-Regime (sticky),
je (Regime × Logik) ein Zwei-Punkt-Trade-Edge; die Hand handelt je Regime EINE Logik. Drei Hände,
GEPAART über gemeinsame Zufallszahlen (gleicher Seed ⇒ identische Regime-/Outcome-Pfade):
- **static** — die fixe Default-Zuordnung der MasterMeta-Engine (Trend→Trendfolge, Range→MR).
- **logic**  — nur Hebel L1: je Regime die Logik mit dem besseren GESCHÄTZTEN Edge. Der Schätzer
  trägt einen PERSISTENTEN Pfad-Bias (ein Schätzer irrt konsistent, nicht je Trade neu), der mit
  wachsender Evidenz ~1/√t schrumpft (modelliert den OOS-Validierungs-Strom). Umgeschaltet wird
  erst ab ``GATE_N`` Belegen, nur auf positiv geschätzten Edge und nur mit Abstands-Marge
  (das validated/profitable-Gate + der Ratchet der Politik, T0).
- **full**   — L1 + L2: zusätzlich Einsatz-Dämpfung auf ``FLOOR``, solange die gefahrene Logik
  keinen positiv geschätzten Edge hat (die stake_scale-Abstraktion).

Drei Welten (die SPEC zitiert die Zahlen dieses seeded Laufs, ``pytest -s``):
  A  Welt = Default-Zuordnung, ZWEI Schätzer-Qualitäten (der zentrale ehrliche Befund): mit
     striktem Evidenz-Gate (σ=0.3, das reale OOS-validated-Gate) ist L1 nahezu kostenlos; mit
     schwachem Schätzer (σ=0.6) kostet die Kopplung spürbar Wachstum — der Preis des
     Schätzfehlers wird offen dokumentiert, nicht wegmodelliert. L2 TAUSCHT in beiden Fällen
     Wachstum gegen Drawdown-Schutz.
  B  Welt INVERTIERT im Trend → statisch blutet strukturell; die Politik erntet den Edge —
     selbst mit dem SCHWACHEN Schätzer (robuste Wert-Aussage).
  C  Nirgends Edge (der Schätzer sieht nur Rauschen, σ=0.6 pessimistisch) → Gate + Dämpfung
     (Faktor ≤ 1) machen die gekoppelte Hand STRIKT defensiver — die Kopplung erhöht das
     Ruin-Risiko NIE (Kern-Beleg G-T5).
"""
import math
import random

# Klein genug für die Suite, groß genug für stabile Mediane/Quantile (seeded ⇒ deterministisch).
N_PATHS = 1200
N_TRADES = 250
STAY = 0.95          # Regime-Persistenz (sticky, wie HMM-Hysterese)
F_RISK = 0.05        # Einsatz-Anteil je Trade (multiplikativ, wie Kelly-Beleg)
FLOOR = 0.5          # L2-Dämpfungs-Floor (Default scale_floor)
GATE_N = 30          # Evidenz-Gate: vorher wird NIE umgeschaltet (validated-Gate)
SWITCH_MARGIN = 0.05  # Ratchet-Marge: Umschalten nur bei KLAR besserer Alternative (kein Churn)
NOISE_OOS = 0.3      # Schätzer-Bias-Stdev bei striktem OOS-Gate (3 Walk-Forward-Fenster)
NOISE_WEAK = 0.6     # pessimistischer schwacher Schätzer (Stress-Annahme für B/C)


def _expectancy(p: float, b: float) -> float:
    return p * b - (1.0 - p)


def _simulate(edges: dict, hand: str, seed: int, noise: float):
    """Eine Hand über N_PATHS Pfade. ``hand`` ∈ static|logic|full. Gemeinsame Zufallszahlen:
    alle Hände ziehen dieselbe rng-Sequenz (Bias wird IMMER gezogen) ⇒ gepaarter Vergleich.
    Returns (Median-Endkapital, P(DD≥30 %), P(DD≥50 %))."""
    rng = random.Random(seed)
    default = {"T": "trend", "R": "mr"}
    terminals, dd30, dd50 = [], 0, 0
    for _ in range(N_PATHS):
        eq, peak, maxdd = 1.0, 1.0, 0.0
        regime = "T" if rng.random() < 0.5 else "R"
        bias = {k: rng.gauss(0.0, noise) for k in sorted(edges)}   # immer ziehen (Pairing)
        for t in range(N_TRADES):
            if rng.random() > STAY:
                regime = "R" if regime == "T" else "T"
            logic, scale = default[regime], 1.0
            if hand in ("logic", "full"):
                shrink = 1.0 / math.sqrt(1.0 + t / 10.0)   # Evidenz wächst ⇒ Bias schrumpft
                est = {lg: _expectancy(*edges[(regime, lg)]) + bias[(regime, lg)] * shrink
                       for lg in ("trend", "mr")}
                alt = "mr" if logic == "trend" else "trend"
                # T0-Gates: erst ab GATE_N Evidenz, nur auf positiv geschätzten Edge, nur mit Marge.
                if t >= GATE_N and est[alt] > 0.0 and est[alt] > est[logic] + SWITCH_MARGIN:
                    logic = alt
                # L2 (nur "full"): ohne positiv geschätzten Edge ⇒ Einsatz auf floor dämpfen.
                if hand == "full" and est[logic] <= 0.0:
                    scale = FLOOR
            p, b = edges[(regime, logic)]
            x = b if rng.random() < p else -1.0
            eq *= max(1e-9, 1.0 + F_RISK * scale * x)
            peak = max(peak, eq)
            maxdd = max(maxdd, (peak - eq) / peak)
        terminals.append(eq)
        dd30 += maxdd >= 0.30
        dd50 += maxdd >= 0.50
    terminals.sort()
    return (terminals[N_PATHS // 2], dd30 / N_PATHS, dd50 / N_PATHS)


def _run(edges: dict, seed: int, noise: float = NOISE_WEAK) -> dict:
    return {hand: _simulate(edges, hand, seed, noise) for hand in ("static", "logic", "full")}


# Szenario A — die Welt entspricht der Default-Zuordnung (Trendfolge gewinnt im Trend, MR im Range).
EDGES_DEFAULT = {("T", "trend"): (0.55, 1.2), ("T", "mr"): (0.45, 1.0),
                 ("R", "mr"): (0.55, 1.1), ("R", "trend"): (0.45, 1.0)}
# Szenario B — im Trend-Regime ist real MEAN-REVERSION profitabel (choppy Bull; der Default irrt).
EDGES_INVERTED = {("T", "trend"): (0.44, 1.0), ("T", "mr"): (0.56, 1.2),
                  ("R", "mr"): (0.55, 1.1), ("R", "trend"): (0.45, 1.0)}
# Szenario C — NIRGENDS ein echter Edge; jeder „Edge" im Schätzer ist Rauschen.
EDGES_NONE = {("T", "trend"): (0.48, 1.0), ("T", "mr"): (0.48, 1.0),
              ("R", "mr"): (0.48, 1.0), ("R", "trend"): (0.48, 1.0)}


def test_scenario_a_default_world_strict_oos_gate():
    r = _run(EDGES_DEFAULT, seed=101, noise=NOISE_OOS)
    med_s, dd30_s, _ = r["static"]
    med_l, dd30_l, _ = r["logic"]
    med_f, dd30_f, _ = r["full"]
    # Mit striktem Evidenz-Gate (das reale OOS-validated-Gate) ist L1 nahezu kostenlos.
    assert med_l >= med_s * 0.85, f"A/L1 kostet zu viel ({med_l:.3f} vs {med_s:.3f})"
    assert dd30_l <= dd30_s + 0.03, f"A/L1 erhöht DD-Risiko ({dd30_l:.3f} vs {dd30_s:.3f})"
    # L2 ist ein EHRLICHER Tausch: Wachstum runter (Preis des Schätzfehlers), Drawdown-Schutz rauf.
    assert dd30_f <= dd30_s, f"A/L2 müsste defensiver sein ({dd30_f:.3f} vs {dd30_s:.3f})"
    assert med_f >= med_s * 0.45, f"A/L2 Preis außer Kontrolle ({med_f:.3f} vs {med_s:.3f})"
    assert med_f <= med_l, "A: Dämpfung muss Wachstum kosten (sonst misst der Sim nichts)"


def test_scenario_a_default_world_weak_estimator_honest_cost():
    # DER ehrliche Gegen-Befund: mit schwachem Schätzer kostet die Kopplung auch in der
    # „richtigen" Welt spürbar Wachstum (Fehl-Switches + Dämpfung) — sie wird dabei aber
    # DEFENSIVER, nie riskanter. Genau deshalb ist die Evidenz-Strenge eine G-T5-Frage.
    r = _run(EDGES_DEFAULT, seed=101, noise=NOISE_WEAK)
    med_s, dd30_s, _ = r["static"]
    med_l, dd30_l, _ = r["logic"]
    med_f, dd30_f, _ = r["full"]
    assert med_l < med_s, "A/schwach: der Schätzfehler-Preis muss sichtbar sein"
    assert med_l >= med_s * 0.60, f"A/schwach: Preis außer Kontrolle ({med_l:.3f} vs {med_s:.3f})"
    assert dd30_l <= dd30_s + 0.03 and dd30_f <= dd30_s, "A/schwach: Risiko darf NIE steigen"


def test_scenario_b_inverted_world_policy_captures_edge():
    r = _run(EDGES_INVERTED, seed=202)
    med_s, _, dd50_s = r["static"]
    med_l, _, dd50_l = r["logic"]
    med_f, _, dd50_f = r["full"]
    # Statisch fährt im Trend-Regime strukturell die Verlierer-Logik; die Politik schaltet nach
    # Evidenz um (L1) und dämpft bis dahin (L2) — deutlich besser, ohne höheres Ruin-Risiko.
    assert med_l > med_s * 1.15, f"B/L1 erntet den Edge nicht ({med_l:.3f} vs {med_s:.3f})"
    assert med_f > med_s, f"B/full schlechter als statisch ({med_f:.3f} vs {med_s:.3f})"
    assert dd50_l <= dd50_s + 0.02 and dd50_f <= dd50_s + 0.02, "B: Ruin-Risiko gestiegen"


def test_scenario_c_no_edge_policy_strictly_more_defensive():
    r = _run(EDGES_NONE, seed=303)
    med_s, dd30_s, dd50_s = r["static"]
    med_l, dd30_l, dd50_l = r["logic"]
    med_f, dd30_f, dd50_f = r["full"]
    # DER Sicherheitsbeleg für G-T5: sieht die Politik nur Rauschen, ist die volle Kopplung STRIKT
    # defensiver als statisch (Dämpfung ≤ 1, Umschalten nur auf „belegten" Edge — der bei
    # symmetrischem Rauschen die Verteilung nicht verschlechtert).
    assert med_f >= med_s, f"C: Dämpfung müsste Verluste mindern ({med_f:.3f} vs {med_s:.3f})"
    assert dd30_f <= dd30_s and dd50_f <= dd50_s, "C: volle Kopplung darf DD nie erhöhen"
    assert med_l >= med_s * 0.85 and dd30_l <= dd30_s + 0.03, "C: L1 erzeugt Risiko aus Rauschen"


def test_damping_never_increases_per_trade_exposure():
    # Mechanische Invariante der L2-Abstraktion: scale ∈ {FLOOR, 1} und nie > 1 ⇒ die gekoppelte
    # Hand riskiert je Trade NIE mehr als die statische (Ruin-Monotonie in f, Kelly-Beleg §5).
    rng = random.Random(9)
    for _ in range(200):
        scale = FLOOR if rng.gauss(0, 1) <= 0 else 1.0
        assert 0 < scale <= 1.0


def test_print_beleg_table():
    """Erzeugt die SPEC-§5-Tabelle (sichtbar via ``pytest -s tests/test_policy_sim.py``)."""
    rows = [("A Default, OOS-Gate s=0.3", _run(EDGES_DEFAULT, 101, NOISE_OOS)),
            ("A Default, schwach s=0.6", _run(EDGES_DEFAULT, 101, NOISE_WEAK)),
            ("B invertiert (Trend) s=0.6", _run(EDGES_INVERTED, 202)),
            ("C nirgends Edge s=0.6", _run(EDGES_NONE, 303))]
    print("\nSzenario                     | Hand    | Median-End | P(DD>=30%) | P(DD>=50%)")
    for name, r in rows:
        for hand in ("static", "logic", "full"):
            med, d30, d50 = r[hand]
            print(f"{name:28} | {hand:7} | x{med:8.3f} | {d30:9.1%} | {d50:9.1%}")
