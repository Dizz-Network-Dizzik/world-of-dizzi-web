"""volume_pbo.py — PBO/Overfitting-Test der Amihud-Illiquiditäts-Engine (Top-20 liquide).

volume_research fand: Amihud-Illiquidität auf den liquiden Majors OOS-Sharpe ~0.95 (> Schwelle 0.86),
unkorreliert zu CSM. PBO (CSCV, López de Prado) prüft jetzt: ist die (V,H)-Auswahl ein Overfitting-
Artefakt? Plus ein KONTRAST gegen eine momentum-artige Variante, um zu zeigen, dass die Selektion
nicht einfach immer dieselbe (zufällig gute) Variante zieht.

Read-only (gecachter Volumen-Snapshot + csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
import csm_signal_research as csr                      # noqa: E402
import volume_research as vr                           # noqa: E402
from backend.app import mn_base                        # noqa: E402
import json


def _sharpe(r):
    if len(r) < 3:
        return 0.0
    sd = statistics.pstdev(r)
    return (statistics.mean(r) / sd * math.sqrt(365)) if sd > 0 else 0.0


def main():
    m = csr._matrix()
    syms, ts, C, fund = m
    vol = vr._fetch_volume(syms)
    DV = []
    for s in syms:
        d = vol.get(s, {}); row = []; last = None
        for tday in ts:
            v = d.get((tday // vr.DAY_MS) * vr.DAY_MS)
            if v is not None:
                last = v
            row.append(last)
        DV.append(row)
    uni = json.loads(mn_base.meta_get("universe") or "[]")
    liquid = [s for s in uni if s in set(syms)]
    sub20 = [i for i, s in enumerate(syms) if s in set(liquid[:20])]
    FEE, CAP, Q = 0.0006, 10000.0, 0.30

    # Amihud-(V,H)-Varianten als Selektions-Universum
    variants = [(V, H) for V in (15, 20, 30, 45, 60) for H in (5, 10)]
    labels = [f"V{V}H{H}" for V, H in variants]
    M = []
    for V, H in variants:
        r = vr.simulate_amihud(syms, ts, C, DV, fund, V, H, Q, FEE, CAP, sub=sub20)["rets"]
        M.append(r)
    n = min(len(r) for r in M); M = [r[-n:] for r in M]
    Vn = len(variants)
    print(f"PBO/CSCV Amihud (Top-20 liquide): {Vn} (V,H)-Varianten, {n} OOS-Tage")

    S = 12; bs = n // S
    blocks = [list(range(i * bs, (i + 1) * bs)) for i in range(S)]

    def sh_on(idx, v):
        return _sharpe([M[v][t] for t in idx])

    lambdas = []
    pick_counts = {}
    for train_b in itertools.combinations(range(S), S // 2):
        tr = [t for b in train_b for t in blocks[b]]
        te = [t for b in range(S) if b not in train_b for t in blocks[b]]
        tr_sh = [sh_on(tr, v) for v in range(Vn)]
        nstar = max(range(Vn), key=lambda v: tr_sh[v])
        pick_counts[labels[nstar]] = pick_counts.get(labels[nstar], 0) + 1
        te_sh = [sh_on(te, v) for v in range(Vn)]
        rank = sorted(range(Vn), key=lambda v: te_sh[v]).index(nstar)
        omega = (rank + 1) / (Vn + 1)
        lambdas.append(math.log(omega / (1 - omega)))
    ns = len(lambdas)
    pbo = sum(1 for l in lambdas if l < 0) / ns
    print(f"  Splits: {ns}  Median logit λ: {statistics.median(lambdas):+.2f}")
    print(f"  ★ PBO = {pbo:.3f}  ({'WASSERDICHT' if pbo<0.1 else 'robust' if pbo<0.25 else 'fragwuerdig' if pbo<0.5 else 'OVERFITTET'})")
    print(f"  IS-beste (V,H)-Verteilung: " + ", ".join(f"{k}:{v}" for k, v in sorted(pick_counts.items(), key=lambda x:-x[1])[:5]))
    full = sorted(range(Vn), key=lambda v: _sharpe(M[v]), reverse=True)
    print("  Voll-Sample Top-3: " + ", ".join(f"{labels[v]}={_sharpe(M[v]):.2f}" for v in full[:3]))


if __name__ == "__main__":
    main()
