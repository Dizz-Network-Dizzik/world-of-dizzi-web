"""csm_posweight_research.py — Verfeinerung des validierten CSM-vol: Positions-Gewichtung im Korb.

CSM-vol (R7/R8, dreifach validiert) gewichtet jede Position EQUAL (0.5/k je Seite). A-priori-Hypothese
(risk-parity-Standard): INVERSE-VOL-Gewichtung innerhalb der Körbe (ruhige Coins mehr Gewicht) glättet
die Returns ⇒ evtl. höhere Sharpe. Andere Dimension als das Signal ⇒ nicht-redundant zu R7.

EHRLICH: das ist ein ZUSÄTZLICHER Freiheitsgrad ⇒ Overfitting-Gefahr. Nur ein anchored-WF-OOS-Lift, der
ROBUST positiv ist, zählt — sonst lautet die ehrliche Antwort „equal-weight reicht" (kein Gate lockern).
Mechanik 1:1 wie csm-vol (forward-fill, Vortags-Gewichte, Turnover-Fee, Funding, vol-skaliertes Signal).
Read-only (csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402


def _vol(Ci, t, L):
    dr = [Ci[j] / Ci[j - 1] - 1.0 for j in range(t - L + 1, t + 1)
          if Ci[j - 1] and Ci[j] and Ci[j - 1] > 0]
    return statistics.pstdev(dr) if len(dr) > 2 else None


def simulate(syms, ts, C, fund, L, H, Q, fee, capital, inv_vol=False, a=None, b=None):
    """Signal = vol-skaliertes Momentum (wie R7). Gewichtung: equal oder inverse-vol je Seite."""
    a = a if a is not None else 0
    b = b if b is not None else len(ts)
    N = len(syms)
    w = [0.0] * N; w_prev = [0.0] * N
    rets = []; equity = []; eq = capital
    start = a + L + 1
    for t in range(start, b):
        pr = 0.0
        for i in range(N):
            if w[i]:
                af, bf = C[i][t - 1], C[i][t]
                if af and bf and af > 0:
                    pr += w[i] * (bf / af - 1.0)
                pr -= w[i] * fund[i]
        cost = 0.0
        if (t - start) % H == 0:
            mom = []
            vols = [None] * N
            for i in range(N):
                aa, bb = C[i][t - L], C[i][t]
                mi = (bb / aa - 1.0) if (aa and bb and aa > 0) else None
                v = _vol(C[i], t, L)
                vols[i] = v
                if mi is not None and v and v > 0:
                    mi = mi / v
                else:
                    mi = None
                mom.append(mi)
            valid = [i for i in range(N) if mom[i] is not None]
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: mom[i])
                k = max(1, int(Q * len(valid)))
                sh, lng = order[:k], order[-k:]
                neww = [0.0] * N

                def _assign(group, sign):
                    if inv_vol:
                        invs = [(i, 1.0 / vols[i]) for i in group if vols[i] and vols[i] > 0]
                        tot = sum(x for _, x in invs)
                        for i, x in invs:
                            neww[i] = sign * 0.5 * (x / tot) if tot > 0 else sign * 0.5 / len(group)
                    else:
                        for i in group:
                            neww[i] = sign * 0.5 / len(group)
                _assign(lng, 1.0)
                _assign(sh, -1.0)
                cost = fee * sum(abs(neww[i] - w_prev[i]) for i in range(N))
                w = neww; w_prev = list(w)
        net = pr - cost
        eq *= (1.0 + net)
        equity.append([ts[t], eq]); rets.append(net)
    st = mn_base.equity_stats(rets, equity, capital, eq)
    st["rets"] = rets
    return st


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


def wf_pooled(syms, ts, C, fund, L, H, Q, fee, inv_vol, n_windows=6):
    T = len(ts); test_len = (T - 150) // n_windows; pooled = []
    for w in range(n_windows):
        tr_end = 150 + w * test_len; te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 25:
            continue
        st = simulate(syms, ts, C, fund, L, H, Q, fee, 10000.0, inv_vol=inv_vol, a=tr_end - L - 1, b=te_end)
        pooled += st["rets"]
    return pooled


def main():
    m = csr._matrix()
    if not m:
        print("Keine Daten."); return
    syms, ts, C, fund = m
    print(f"Daten: {len(syms)} Symbole, {len(ts)} Tage  |  CSM-vol: equal-weight vs inverse-vol Korb-Gewichtung\n")
    FEE, CAP = 0.0006, 10000.0
    print(f"{'L':>4}{'H':>3}{'Q':>5}{'equal_OOS':>11}{'invvol_OOS':>12}{'lift':>8}{'inv_PSR':>9}")
    for L, H, Q in [(14, 2, 0.30), (14, 1, 0.30), (14, 2, 0.20), (21, 2, 0.30)]:
        eqp = wf_pooled(syms, ts, C, fund, L, H, Q, FEE, False)
        ivp = wf_pooled(syms, ts, C, fund, L, H, Q, FEE, True)
        print(f"{L:>4}{H:>3}{Q:>5}{_sh(eqp):>11.2f}{_sh(ivp):>12.2f}{_sh(ivp) - _sh(eqp):>+8.2f}{_psr(ivp):>9.3f}")

    print("\n=== KOSTEN-STRESS (L14/H2/Q0.3) — frisst inverse-vol mehr Turnover? ===")
    print(f"{'fee':>8}{'equal':>9}{'invvol':>9}{'lift':>8}")
    for bps in (6, 10, 20):
        eqp = wf_pooled(syms, ts, C, fund, 14, 2, 0.30, bps / 1e4, False)
        ivp = wf_pooled(syms, ts, C, fund, 14, 2, 0.30, bps / 1e4, True)
        print(f"{bps:>6}bp{_sh(eqp):>9.2f}{_sh(ivp):>9.2f}{_sh(ivp) - _sh(eqp):>+8.2f}")
    print("\nLesart: robust positiver Lift (über L/H/Q + Kosten) ⇒ inverse-vol-Gewichtung wert. Sonst: equal reicht.")


if __name__ == "__main__":
    main()
