"""csm_vol_robustness.py — Stress-Test des Vol-Skalierungs-Lifts (R7) VOR jeder Live-Änderung.

R7 fand: L14 + Vol-Skalierung hebt CSM OOS 0.86 → 1.88 (anchored WF, 4 Fenster). Bevor das die
Live-Engine ändern darf, härten wir es ehrlich gegen die typischen Fragilitäts-Quellen:
  A) Fenster-Sensitivität (4/6/8) — getragen von wenigen großen Fenstern oder stabil?
  B) Sub-Universum (Top-20/30/all liquideste) — hängt der Lift an survivorship-verzerrten Small-Caps?
  C) Kosten-Stress (6/10/20 bps) — überlebt der Lift höhere Fees (mehr Turnover bei volatilen Coins)?
  D) Parameter-Robustheit (Q × H) — konsistenter Lift oder nur bei einem Sweet-Spot?

Jeweils Vol-Skalierung (L14+vol) GEGEN Baseline (L14 raw), gepoolte OOS-Sharpe. Honest = der Lift
muss in der MEHRZAHL der Stresses bestehen, nicht nur im Basis-Setup. Read-only, 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, json, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402  (simulate/_matrix wiederverwenden)


def _sh(r):
    if len(r) < 2:
        return 0.0
    sd = statistics.pstdev(r)
    return (statistics.mean(r) / sd * math.sqrt(365)) if sd > 0 else 0.0


def _psr(r):
    if len(r) < 3:
        return 0.0
    mean = statistics.mean(r); sd = statistics.pstdev(r)
    if sd <= 0:
        return 0.0
    sk, ku = mn_base._skew_kurt(r, mean, sd)
    return mn_base.psr(mean / sd, sk, ku, len(r))


def wf_pooled(syms, ts, C, fund, L, sk, vs, n_windows, fee, Q, H):
    """Gepoolte OOS-Returns über n anchored Fenster (fixe Variante, kein Picking)."""
    T = len(ts)
    test_len = (T - 150) // n_windows
    pooled = []
    for w in range(n_windows):
        tr_end = 150 + w * test_len
        te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 25:
            continue
        st = csr.simulate(syms, ts, C, fund, L, H, Q, fee, 10000.0, skip=sk, volscale=vs,
                          a=tr_end - L - 1, b=te_end)
        pooled += st["rets"]
    return pooled


def _subset(syms, C, fund, keep):
    idx = [i for i, s in enumerate(syms) if s in keep]
    return [syms[i] for i in idx], [C[i] for i in idx], [fund[i] for i in idx]


def _row(label, syms, ts, C, fund, n_windows=6, fee=0.0006, Q=0.30, H=1):
    base = wf_pooled(syms, ts, C, fund, 14, 0, False, n_windows, fee, Q, H)
    vol = wf_pooled(syms, ts, C, fund, 14, 0, True, n_windows, fee, Q, H)
    b, v = _sh(base), _sh(vol)
    flag = "OK" if v > b and v > 0.83 else ("lift" if v > b else "—")
    print(f"{label:28}{b:>8.2f}{v:>9.2f}{v - b:>+8.2f}{_psr(vol):>9.3f}{flag:>7}")


def main():
    m = csr._matrix()
    if not m:
        print("Keine Daten."); return
    syms, ts, C, fund = m
    print(f"Daten: {len(syms)} Symbole, {len(ts)} Tage  |  Vol-Skalierung (L14+vol) vs Baseline (L14 raw)\n")
    hdr = f"{'Stress':28}{'base_Sh':>8}{'vol_Sh':>9}{'lift':>8}{'vol_PSR':>9}{'':>7}"

    print("=== A) FENSTER-SENSITIVITÄT ===")
    print(hdr)
    for nw in (4, 6, 8):
        _row(f"  {nw} anchored Fenster", syms, ts, C, fund, n_windows=nw)

    print("\n=== B) SUB-UNIVERSUM (Survivorship/Liquidität) ===")
    print(hdr)
    try:
        uni = json.loads(mn_base.meta_get("universe") or "[]")   # Volumen-sortiert
    except Exception:
        uni = []
    sset = set(syms)
    liquid = [s for s in uni if s in sset]   # vorhandene Symbole in Volumen-Reihenfolge (liquideste zuerst)
    for topk in (15, 25):
        keep = set(liquid[:topk])
        if len(keep) >= 12:
            ssyms, sC, sfund = _subset(syms, C, fund, keep)
            _row(f"  Top-{topk} liquide ({len(keep)})", ssyms, ts, sC, sfund)
    _row("  alle 50 (Referenz)", syms, ts, C, fund)

    print("\n=== C) KOSTEN-STRESS ===")
    print(hdr)
    for bps in (6, 10, 20):
        _row(f"  fee {bps} bps/Seite", syms, ts, C, fund, fee=bps / 1e4)

    print("\n=== D) PARAMETER-ROBUSTHEIT (Q × H) ===")
    print(hdr)
    for Q in (0.2, 0.3):
        for H in (1, 2, 3):
            _row(f"  Q={Q} H={H}", syms, ts, C, fund, Q=Q, H=H)

    print("\nLesart: der Lift (vol−base > 0) MUSS in der Mehrzahl der Stresses bestehen und vol_Sh möglichst")
    print("        > 0.83 (Härtungs-Schwelle). Bricht er bei Top-20 / höheren Fees / anderem Q,H ein → fragil.")


if __name__ == "__main__":
    main()
