"""csm_pbo.py — Probability of Backtest Overfitting (PBO) für die CSM-Vol-Skalierung (López de Prado).

Strengster Overfitting-Test: vol-scaling wurde via anchored WF + 14/14-Robustheit + offiziellem Optimizer
validiert — PBO (Combinatorial Symmetric Cross-Validation, CSCV) prüft jetzt über ALLE möglichen
Train/Test-Block-Aufteilungen, wie wahrscheinlich es ist, dass die In-Sample-beste Config OOS
unter-median performt (= Selektion ist Overfitting-Artefakt).

CSCV (Bailey/López de Prado 2014):
  - Per-Perioden-Return-Matrix M[t][variant] aus je EINEM durchgehenden Backtest je Config-Variante.
  - Zeit in S Blöcke; für jede C(S,S/2)-Aufteilung Train/Test: wähle IS-beste Variante (Train-Sharpe),
    miss ihren relativen Rang OOS (Test). logit λ = ln(ω/(1-ω)); PBO = Anteil λ<0 (OOS unter Median).
  - PBO niedrig (≪0.5, ideal <0.1) ⇒ die Auswahl (vol-scaling) ist NICHT overfittet.

Read-only (csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
import csm_signal_research as csr                      # noqa: E402


def _sharpe(r):
    if len(r) < 3:
        return 0.0
    sd = statistics.pstdev(r)
    return (statistics.mean(r) / sd * math.sqrt(365)) if sd > 0 else 0.0


def main():
    m = csr._matrix()
    if not m:
        print("Keine Daten."); return
    syms, ts, C, fund = m
    FEE, CAP, Q = 0.0006, 10000.0, 0.30

    # Config-Universum: raw vs vol × L × H. Das ist die Menge, aus der "die Beste" gewählt wird.
    variants = [(L, H, vs) for L in (14, 21, 30, 60) for H in (1, 2) for vs in (False, True)]
    labels = [f"L{L}H{H}{'+vol' if vs else ''}" for L, H, vs in variants]

    # Durchgehende Per-Tag-Returns je Variante, auf gemeinsame Länge (ab größtem L) getrimmt.
    M = []
    for L, H, vs in variants:
        r = csr.simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=0, volscale=vs)["rets"]
        M.append(r)
    n = min(len(r) for r in M)
    M = [r[-n:] for r in M]
    V = len(variants)
    print(f"PBO/CSCV: {V} Config-Varianten, {n} gemeinsame OOS-Tage\n")

    S = 12
    bs = n // S
    blocks = [list(range(i * bs, (i + 1) * bs)) for i in range(S)]

    def sh_on(idx, v):
        return _sharpe([M[v][t] for t in idx])

    lambdas = []
    vol_picks = 0
    for train_b in itertools.combinations(range(S), S // 2):
        tr = [t for b in train_b for t in blocks[b]]
        te = [t for b in range(S) if b not in train_b for t in blocks[b]]
        tr_sh = [sh_on(tr, v) for v in range(V)]
        nstar = max(range(V), key=lambda v: tr_sh[v])          # IS-beste
        if variants[nstar][2]:
            vol_picks += 1
        te_sh = [sh_on(te, v) for v in range(V)]
        rank = sorted(range(V), key=lambda v: te_sh[v]).index(nstar)   # 0..V-1
        omega = (rank + 1) / (V + 1)                            # relativer OOS-Rang (0..1)
        lambdas.append(math.log(omega / (1.0 - omega)))
    n_splits = len(lambdas)
    pbo = sum(1 for l in lambdas if l < 0) / n_splits
    med_lam = statistics.median(lambdas)

    print(f"Splits (C({S},{S//2})): {n_splits}")
    print(f"IS-beste war eine VOL-Variante in: {100*vol_picks/n_splits:.0f}% der Splits")
    print(f"Median logit λ: {med_lam:+.2f}  (positiv = IS-beste meist OOS über Median = gut)")
    print(f"\n  ★ PBO = {pbo:.3f}  ({100*pbo:.0f}% der Splits: IS-beste fällt OOS unter Median)")
    verdict = ("WASSERDICHT (PBO<0.1)" if pbo < 0.1 else
               "robust (PBO<0.25)" if pbo < 0.25 else
               "fragwürdig (PBO 0.25–0.5)" if pbo < 0.5 else "OVERFITTET (PBO≥0.5)")
    print(f"  Verdikt: {verdict}")

    # Voll-Sample-Ranking als Kontext
    full = sorted(range(V), key=lambda v: _sharpe(M[v]), reverse=True)
    print("\n  Voll-Sample Top-5 Varianten (Kontext):")
    for v in full[:5]:
        print(f"    {labels[v]:12} Sharpe {_sharpe(M[v]):.2f}")


if __name__ == "__main__":
    main()
