"""reversal_research.py — (D) Suche nach einer 2. ECHTEN real-data MN-Engine: Short-Term Reversal.

A-priori-Hypothese (theorie-fundiert, NICHT aus diesen Daten erfunden): kurzfristige Überreaktionen
mean-reverten. Cross-sectional, market-neutral: LONG die jüngsten Verlierer (Bottom-Q über R Tage),
SHORT die jüngsten Gewinner (Top-Q), dollar-neutral. Das ist strukturell das GEGENTEIL von CSM-Momentum
⇒ Kandidat für einen UNKORRELIERTEN 2. Sockel-Edge.

EHRLICHE Failure-Modes, die der Test explizit prüft:
  1) KOSTEN: STR hat hohen Turnover (täglich neue Verlierer/Gewinner) — Fees fressen den Edge oft ganz.
     ⇒ kosten-inklusiv (fee×Turnover), Kosten-Stress 6/10/20 bps.
  2) DIVERSIFIKATION: nur nützlich, wenn die STR-Returns UNKORRELIERT (idealerweise leicht negativ) zu
     CSM-Momentum sind ⇒ expliziter Korrelations-Check gegen die beste CSM-Variante (vol-skaliert).
  3) PERIOD-FRAGILITÄT: anchored WF über mehrere Fenster; ein period-abhängiger Lift ist KEIN Edge.
Mechanik 1:1 wie csm.simulate (forward-fill, Rendite mit Vortags-Gewichten = kein Lookahead, Turnover-Fee,
Funding-Proxy). Read-only (csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402  (_matrix + CSM-simulate wiederverwenden)


def simulate_reversal(syms, ts, C, fund, R, H, Q, fee, capital, a=None, b=None):
    """Cross-sectional Short-Term Reversal: LONG Bottom-Q (Verlierer über R Tage), SHORT Top-Q (Gewinner)."""
    a = a if a is not None else 0
    b = b if b is not None else len(ts)
    N = len(syms)
    w = [0.0] * N; w_prev = [0.0] * N
    rets = []; equity = []; eq = capital
    start = a + R + 1
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
            sig = []
            for i in range(N):
                lo, hi = C[i][t - R], C[i][t]
                sig.append((hi / lo - 1.0) if (lo and hi and lo > 0) else None)
            valid = [i for i in range(N) if sig[i] is not None]
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: sig[i])     # aufsteigend: vorne = Verlierer
                k = max(1, int(Q * len(valid)))
                lng, sh = order[:k], order[-k:]                  # LONG Verlierer, SHORT Gewinner (REVERSAL)
                neww = [0.0] * N
                for i in lng:
                    neww[i] = 0.5 / len(lng)
                for i in sh:
                    neww[i] = -0.5 / len(sh)
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


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 5:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = statistics.mean(a), statistics.mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
    sa, sb = statistics.pstdev(a), statistics.pstdev(b)
    return cov / (sa * sb) if (sa > 0 and sb > 0) else 0.0


def wf_pooled(syms, ts, C, fund, R, H, Q, fee, n_windows=6):
    T = len(ts); test_len = (T - 150) // n_windows; pooled = []
    for w in range(n_windows):
        tr_end = 150 + w * test_len; te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 25:
            continue
        st = simulate_reversal(syms, ts, C, fund, R, H, Q, fee, 10000.0, a=tr_end - R - 1, b=te_end)
        pooled += st["rets"]
    return pooled


def main():
    m = csr._matrix()
    if not m:
        print("Keine Daten."); return
    syms, ts, C, fund = m
    T = len(ts)
    print(f"Daten: {len(syms)} Symbole, {T} Tage  |  Short-Term Reversal (long Verlierer / short Gewinner)\n")
    FEE, CAP, Q = 0.0006, 10000.0, 0.30

    print("=== IN-SAMPLE Sharpe (volle 2J, Hypothese — NICHT die Entscheidung) ===")
    print(f"{'R':>3}{'H':>3}{'Sharpe':>9}{'PSR':>7}{'annPct':>9}")
    for R in (1, 2, 3, 5):
        for H in (1, 2):
            st = simulate_reversal(syms, ts, C, fund, R, H, Q, FEE, CAP)
            print(f"{R:>3}{H:>3}{st['sharpe']:>9.2f}{(st.get('psr') or 0):>7.3f}{(st.get('ann_pct') or 0):>9.1f}")

    print("\n=== ANCHORED WF (a-priori fixe R, 6 Fenster, gepoolt OOS) + KOSTEN-STRESS ===")
    print(f"{'Variante':16}{'6bps':>8}{'10bps':>8}{'20bps':>8}{'PSR@6':>9}")
    for R, H in [(1, 1), (2, 1), (3, 1), (5, 1)]:
        shs = []
        p6 = None
        for bps in (6, 10, 20):
            pooled = wf_pooled(syms, ts, C, fund, R, H, Q, bps / 1e4)
            shs.append(_sh(pooled))
            if bps == 6:
                p6 = _psr(pooled)
        print(f"  R={R} H={H}        {shs[0]:>8.2f}{shs[1]:>8.2f}{shs[2]:>8.2f}{p6:>9.3f}")

    # --- Korrelation zu CSM-Momentum (vol-skaliert, beste Variante) über das OOS-Segment ---
    print("\n=== DIVERSIFIKATION: Korrelation STR <-> CSM-Momentum (vol-skaliert) ===")
    split = 150
    rev = simulate_reversal(syms, ts, C, fund, 1, 1, Q, FEE, CAP, a=split - 2, b=T)
    csm = csr.simulate(syms, ts, C, fund, 14, 1, Q, FEE, CAP, skip=0, volscale=True, a=split - 15, b=T)
    c = _corr(rev["rets"], csm["rets"])
    print(f"  corr(STR R=1, CSM L14+vol) ueber OOS-Segment = {c:+.3f}  "
          f"({'unkorreliert -> Diversifizierer' if abs(c) < 0.3 else 'korreliert -> wenig Diversifikations-Nutzen'})")

    thr = 0.5 + 0.2 * math.sqrt(2 * math.log(5))
    print(f"\n  Härtungs-Schwelle ~{thr:.2f}. Verdikt-Regel: nur ein NACH KOSTEN positiver, period-robuster,")
    print("  zu CSM unkorrelierter OOS-Lift zählt als 2.-Engine-Kandidat. Sonst ehrliches 'tot' (wie Funding R3).")


if __name__ == "__main__":
    main()
