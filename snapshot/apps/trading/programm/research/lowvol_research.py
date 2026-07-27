"""lowvol_research.py — (D) 2.-MN-Engine-Kandidat: Cross-Sectional Low-Volatility-Anomalie.

A-priori-Hypothese (Aktien-Literatur gut belegt; in Krypto offen): niedrig-volatile Assets liefern
bessere risk-adjusted Returns als hoch-volatile. Cross-sectional, market-neutral: LONG Bottom-Q nach
realisierter Vola (ruhige Coins), SHORT Top-Q (zappelige Coins), dollar-neutral.

WARUM nach Reversal (R8a): Reversal/Momentum sind beide RETURN-basiert = dieselbe Achse (corr −0.33).
Low-Vol ist VOLA-basiert ⇒ echte Chance auf UNkorreliertheit zu CSM-Momentum (= Diversifikations-Wert).
Bonus: Vola ist persistent ⇒ niedriger Turnover ⇒ kosten-unkritischer als Reversal.

EHRLICHE Failure-Modes, die der Test prüft:
  1) „Long low-vol" könnte in toten/illiquiden Coins sitzen (Survivorship/Liquidität) ⇒ Sub-Universum-Test.
  2) „Short high-vol" = short die pumpenden Memes ⇒ in Bull-Runs brutal ⇒ Subperioden/Worst-Window.
  3) Period-Fragilität ⇒ anchored WF mehrere Fenster. Kosten-inklusiv + Korrelation zu CSM.
Mechanik 1:1 wie csm.simulate. Read-only (csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402


def _volof(Ci, t, V):
    dr = [Ci[j] / Ci[j - 1] - 1.0 for j in range(t - V + 1, t + 1)
          if Ci[j - 1] and Ci[j] and Ci[j - 1] > 0]
    return statistics.pstdev(dr) if len(dr) > 2 else None


def simulate_lowvol(syms, ts, C, fund, V, H, Q, fee, capital, a=None, b=None):
    """LONG Bottom-Q nach realisierter Vola (V Tage), SHORT Top-Q. Dollar-neutral."""
    a = a if a is not None else 0
    b = b if b is not None else len(ts)
    N = len(syms)
    w = [0.0] * N; w_prev = [0.0] * N
    rets = []; equity = []; eq = capital
    start = a + V + 1
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
            sig = [_volof(C[i], t, V) for i in range(N)]
            valid = [i for i in range(N) if sig[i] is not None and sig[i] > 0]
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: sig[i])     # aufsteigend: vorne = niedrigste Vola
                k = max(1, int(Q * len(valid)))
                lng, sh = order[:k], order[-k:]                  # LONG low-vol, SHORT high-vol
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


def _maxdd(r):
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in r:
        eq *= (1 + x); peak = max(peak, eq); dd = min(dd, eq / peak - 1)
    return dd * 100


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 5:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = statistics.mean(a), statistics.mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
    sa, sb = statistics.pstdev(a), statistics.pstdev(b)
    return cov / (sa * sb) if (sa > 0 and sb > 0) else 0.0


def wf_pooled(syms, ts, C, fund, V, H, Q, fee, n_windows=6, sub=None):
    sy, CC, fu = (sub if sub else (syms, C, fund))
    T = len(ts); test_len = (T - 150) // n_windows; pooled = []
    for w in range(n_windows):
        tr_end = 150 + w * test_len; te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 25:
            continue
        st = simulate_lowvol(sy, ts, CC, fu, V, H, Q, fee, 10000.0, a=tr_end - V - 1, b=te_end)
        pooled += st["rets"]
    return pooled


def main():
    m = csr._matrix()
    if not m:
        print("Keine Daten."); return
    syms, ts, C, fund = m
    T = len(ts)
    print(f"Daten: {len(syms)} Symbole, {T} Tage  |  Low-Vol-Anomalie (long low-vol / short high-vol)\n")
    FEE, CAP, Q = 0.0006, 10000.0, 0.30

    print("=== IN-SAMPLE Sharpe (volle 2J, Hypothese) ===")
    print(f"{'V':>4}{'H':>3}{'Sharpe':>9}{'PSR':>7}{'annPct':>9}{'maxDD':>9}")
    for V in (10, 20, 30, 60):
        for H in (1, 5):
            st = simulate_lowvol(syms, ts, C, fund, V, H, Q, FEE, CAP)
            print(f"{V:>4}{H:>3}{st['sharpe']:>9.2f}{(st.get('psr') or 0):>7.3f}{(st.get('ann_pct') or 0):>9.1f}{(st.get('maxdd_pct') or 0):>9.1f}")

    print("\n=== ANCHORED WF (a-priori fixe V, 6 Fenster, gepoolt OOS) + KOSTEN-STRESS ===")
    print(f"{'Variante':16}{'6bps':>8}{'10bps':>8}{'20bps':>8}{'PSR@6':>9}{'maxDD':>9}")
    for V, H in [(20, 5), (30, 5), (60, 5), (30, 1)]:
        shs = []
        for bps in (6, 10, 20):
            pooled = wf_pooled(syms, ts, C, fund, V, H, Q, bps / 1e4)
            shs.append(_sh(pooled))
        p6 = wf_pooled(syms, ts, C, fund, V, H, Q, 0.0006)
        print(f"  V={V} H={H}        {shs[0]:>8.2f}{shs[1]:>8.2f}{shs[2]:>8.2f}{_psr(p6):>9.3f}{_maxdd(p6):>9.1f}")

    # Korrelation zu CSM-Momentum (vol-skaliert)
    print("\n=== DIVERSIFIKATION: Korrelation Low-Vol <-> CSM-Momentum (vol-skaliert) ===")
    lv = simulate_lowvol(syms, ts, C, fund, 30, 5, Q, FEE, CAP, a=148, b=T)
    cm = csr.simulate(syms, ts, C, fund, 14, 1, Q, FEE, CAP, skip=0, volscale=True, a=135, b=T)
    c = _corr(lv["rets"], cm["rets"])
    print(f"  corr(LowVol V=30, CSM L14+vol) OOS = {c:+.3f}  "
          f"({'UNKORRELIERT -> echter Diversifizierer!' if abs(c) < 0.3 else 'korreliert -> wenig Nutzen'})")

    # Sub-Universum (Liquiditaet): liegt der Edge in toten Small-Caps?
    print("\n=== SUB-UNIVERSUM (sitzt 'long low-vol' in illiquiden Coins?) ===")
    try:
        uni = json.loads(mn_base.meta_get("universe") or "[]")
    except Exception:
        uni = []
    liquid = [s for s in uni if s in set(syms)]
    for topk in (15, 25):
        keep = set(liquid[:topk])
        if len(keep) >= 12:
            idx = [i for i, s in enumerate(syms) if s in keep]
            sub = ([syms[i] for i in idx], [C[i] for i in idx], [fund[i] for i in idx])
            pooled = wf_pooled(syms, ts, C, fund, 30, 5, Q, FEE, sub=sub)
            print(f"  Top-{topk} liquide ({len(keep)}): OOS-Sharpe {_sh(pooled):>6.2f}  PSR {_psr(pooled):.3f}")

    thr = 0.5 + 0.2 * math.sqrt(2 * math.log(5))
    print(f"\n  Härtungs-Schwelle ~{thr:.2f}. 2.-Engine-Kandidat NUR bei: OOS-Lift nach Kosten > Schwelle,")
    print("  zu CSM unkorreliert, NICHT in illiquiden Coins konzentriert, period-robust. Sonst ehrliches 'tot'.")


if __name__ == "__main__":
    main()
