"""csm_signal_research.py — EHRLICHE Suche nach einem besseren CSM-Signal (auf 2J Echtdaten).

Das Live-CSM nutzt mom = C[t]/C[t-L]-1 mit L=14 Tagen; der Optimizer variiert nur L∈{7..30}/hold/quantile.
Akademisches Cross-Sectional-Momentum nutzt 3-12 MONATE (60-250 Tage) UND einen Skip (jüngste Periode
überspringen, da dort kurzfristig Reversal dominiert) UND oft Vol-Skalierung (risk-adjusted). Diese
STRUKTUREN fehlen im Live-CSM. Hier ehrlich getestet — kosten- + funding-inklusiv, OUT-OF-SAMPLE.

Mechanik 1:1 wie csm.simulate (forward-fill, Rendite mit Vortags-Gewichten = kein Lookahead, Turnover-Fee,
Funding-Proxy −w·funding). Geändert wird NUR das Momentum-Signal. Ziel-Frage: hebt eine STRUKTUR die
OOS-Sharpe über die Live-Baseline (L=14) — idealerweise über die Härtungs-Schwelle ~0.83?

Read-only (csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, json, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
from backend.app import csm, mn_base, stats  # noqa: E402


def _matrix(min_history=300):
    syms, ts, closes = csm._load_prices(min_history)
    if not syms:
        return None
    T = len(ts)
    C = []
    for s in syms:
        row = list(closes[s]); last = None
        for j in range(T):
            if row[j] is None:
                row[j] = last
            else:
                last = row[j]
        C.append(row)
    try:
        funding = json.loads(mn_base.meta_get("funding_avg") or "{}")
    except Exception:
        funding = {}
    fund = [float(funding.get(s, 0.0)) for s in syms]
    return syms, ts, C, fund


def _vol(Ci, t, L):
    rets = []
    for j in range(t - L + 1, t + 1):
        a, b = Ci[j - 1], Ci[j]
        if a and b and a > 0:
            rets.append(b / a - 1.0)
    return statistics.pstdev(rets) if len(rets) > 2 else None


def simulate(syms, ts, C, fund, L, H, Q, fee, capital, skip=0, volscale=False,
             a=None, b=None):
    """CSM-Mechanik mit konfigurierbarem Signal. mom = C[t-skip]/C[t-L]-1 (optional /vol)."""
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
            for i in range(N):
                hi, lo = C[i][t - skip], C[i][t - L]
                m = (hi / lo - 1.0) if (hi and lo and lo > 0) else None
                if m is not None and volscale:
                    v = _vol(C[i], t, L)
                    m = (m / v) if (v and v > 0) else None
                mom.append(m)
            valid = [i for i in range(N) if mom[i] is not None]
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: mom[i])
                k = max(1, int(Q * len(valid)))
                sh, lng = order[:k], order[-k:]
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


def main():
    m = _matrix()
    if not m:
        print("Keine Preis-Daten."); return
    syms, ts, C, fund = m
    T = len(ts)
    print(f"Daten: {len(syms)} Symbole, {T} Tage")
    FEE, CAP, H, Q = 0.0006, 10000.0, 1, 0.30

    # ---- 1) IN-SAMPLE-Exploration (Hypothesen-Generierung, klar als in-sample markiert) ----
    print("\n=== IN-SAMPLE Sharpe (volle 2J) — nur Hypothese, NICHT die Entscheidung ===")
    print(f"{'L':>4}{'skip':>5}{'vol':>5}{'Sharpe':>9}{'PSR':>7}{'annPct':>9}")
    grid = [(L, sk, vs) for L in (14, 30, 60, 90, 120) for sk in (0, 1, 3, 7) for vs in (False, True)]
    insample = []
    for L, sk, vs in grid:
        st = simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=sk, volscale=vs)
        insample.append(((L, sk, vs), st["sharpe"], st.get("psr"), st.get("ann_pct")))
    for (L, sk, vs), sh, psr, ann in sorted(insample, key=lambda x: -x[1])[:12]:
        print(f"{L:>4}{sk:>5}{str(vs):>5}{sh:>9.2f}{(psr or 0):>7.3f}{(ann or 0):>9.1f}")
    base_is = next(sh for (k, sh, _, _) in insample if k == (14, 0, False))
    print(f"  [Referenz] Live-Baseline L=14/skip0/vol-off in-sample Sharpe: {base_is:.2f}")

    # ---- 2) EHRLICHE OOS-Validierung: anchored Walk-Forward mit Struktur-SELEKTION auf Train ----
    # Kandidaten-Grid; je OOS-Fenster Bester nach Train-Sharpe -> auf Test angewandt -> OOS-Returns gepoolt.
    print("\n=== ANCHORED WALK-FORWARD (Selektion auf Train, OOS-Test) ===")
    candidates = [(L, sk, vs) for L in (14, 30, 60, 90) for sk in (0, 1, 3) for vs in (False, True)]
    n_windows = 4
    test_len = (T - 150) // n_windows          # 150 Tage Mindest-Train-Anker
    pooled_oos, pooled_base, pooled_volfix, picks = [], [], [], []
    for wnd in range(n_windows):
        tr_end = 150 + wnd * test_len
        te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 30:
            continue
        # Selektion auf Train [0, tr_end]
        best, best_sh = None, -1e9
        for cand in candidates:
            L, sk, vs = cand
            st = simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=sk, volscale=vs, a=0, b=tr_end)
            if st.get("sharpe") is not None and st["sharpe"] > best_sh:
                best_sh, best = st["sharpe"], cand
        # OOS auf [tr_end, te_end]: adaptive Selektion · Baseline L14 · L14+vol FIX (a-priori)
        L, sk, vs = best
        oos = simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=sk, volscale=vs, a=tr_end - L - 1, b=te_end)
        base = simulate(syms, ts, C, fund, 14, H, Q, FEE, CAP, skip=0, volscale=False, a=tr_end - 15, b=te_end)
        vfix = simulate(syms, ts, C, fund, 14, H, Q, FEE, CAP, skip=0, volscale=True, a=tr_end - 15, b=te_end)
        pooled_oos += oos["rets"]; pooled_base += base["rets"]; pooled_volfix += vfix["rets"]
        picks.append((wnd, best, round(oos["sharpe"], 2), round(base["sharpe"], 2)))
        print(f"  Fenster {wnd}: train->pick L={best[0]} skip={best[1]} vol={best[2]} | "
              f"OOS-Sh adaptiv={oos['sharpe']:.2f} · BaselineL14={base['sharpe']:.2f} · L14+vol-fix={vfix['sharpe']:.2f}")

    def _sh(r):
        sd = statistics.pstdev(r) if len(r) > 1 else 0
        return (statistics.mean(r) / sd * math.sqrt(365)) if sd > 0 else 0.0

    def _psr(r):
        if len(r) < 3:
            return 0.0
        mean = statistics.mean(r); sd = statistics.pstdev(r)
        if sd <= 0:
            return 0.0
        sk, ku = mn_base._skew_kurt(r, mean, sd)
        return mn_base.psr(mean / sd, sk, ku, len(r))

    print("\n=== GEPOOLTE OOS-BILANZ (über 4 anchored Fenster) ===")
    print(f"  Adaptive Struktur-Selektion: OOS-Sharpe {_sh(pooled_oos):.2f}  PSR {_psr(pooled_oos):.3f}  (n={len(pooled_oos)})")
    print(f"  Baseline L=14 (Live):        OOS-Sharpe {_sh(pooled_base):.2f}  PSR {_psr(pooled_base):.3f}")
    print(f"  L14 +vol FIX (a-priori):     OOS-Sharpe {_sh(pooled_volfix):.2f}  PSR {_psr(pooled_volfix):.3f}  <- die EINE Strukturänderung")
    thr = 0.5 + 0.2 * math.sqrt(2 * math.log(4))
    print(f"  Härtungs-Schwelle (Haircut 0.5 + Deflation {0.2*math.sqrt(2*math.log(4)):.2f} @ N=4) ≈ {thr:.2f}")
    win = _sh(pooled_oos)
    print(f"  Verdikt: adaptive OOS-Sharpe {win:.2f} {'>' if win>thr else '<'} Schwelle {thr:.2f} ⇒ "
          f"{'QUALIFIZIERT (echte 2. Engine!)' if win>thr else 'qualifiziert NICHT (aber Fortschritt messbar?)'}")

    # ---- 3) FIXED-VARIANT HOLD-OUT (a-priori-Hypothesen, KEIN Train-Picking) ----
    # Isoliert die Frage „hilft eine BESTIMMTE Struktur OOS?" ohne Selektions-Overfitting.
    split = int(T * 0.6)
    print(f"\n=== FIXED-VARIANT HOLD-OUT: Train[0:{split}] nur Kontext · Test[{split}:{T}] ehrlich ===")
    hyp = [("Baseline L14 (Live)", 14, 0, False), ("L14 +vol", 14, 0, True),
           ("L14 +skip1", 14, 1, False), ("L14 +skip1 +vol", 14, 1, True),
           ("L30 +vol", 30, 0, True), ("L60", 60, 0, False), ("L90 +skip3", 90, 3, False)]
    print(f"{'Variante':22}{'train_Sh':>9}{'TEST_Sh':>9}{'TEST_PSR':>10}")
    for name, L, sk, vs in hyp:
        tr = simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=sk, volscale=vs, a=0, b=split)
        te = simulate(syms, ts, C, fund, L, H, Q, FEE, CAP, skip=sk, volscale=vs, a=split - L - 1, b=T)
        print(f"{name:22}{tr['sharpe']:>9.2f}{te['sharpe']:>9.2f}{(te.get('psr') or 0):>10.3f}")
    print("\nLesart: schlägt eine fixe Variante die Baseline im TEST robust (train≈test, kein Einbruch)?")


if __name__ == "__main__":
    main()
