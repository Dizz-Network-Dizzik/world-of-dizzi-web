"""tsmom_research.py — (D) 2.-Engine-Falsifikation: Time-Series-Momentum (TSMOM).

A-priori-Hypothese (theorie-fundiert, Moskowitz/Ooi/Pedersen 2012): jedes Asset EINZELN ist long, wenn
seine eigene Trailing-Rendite über L positiv ist, sonst short. Anders als CSM (cross-sectional: long Top-Q
/ short Bottom-Q RELATIV zu den Peers) ist TSMOM ein ABSOLUT-Trend-Signal.

ERWARTETE WIDERLEGUNG (vor dem Test offengelegt — der Test versucht sie zu bestätigen ODER zu brechen):
  1) TSMOM ist NICHT markt-neutral. Wenn (wie in Krypto meist) alle Assets gemeinsam mit BTC trenden, ist
     TSMOM netto LONG/SHORT den ganzen Markt -> es trägt MARKT-BETA, kein orthogonaler MN-Edge. Der MN-Sockel
     braucht aber dollar-neutrale Engines. ⇒ Test misst die AVG-NETTO-EXPOSURE explizit.
  2) TSMOM lebt auf derselben RETURN-ACHSE wie CSM (beides Momentum). ⇒ Test misst corr(TSMOM, CSM-vol).
     Hohe Korrelation = kein Diversifikations-Nutzen (= R8-Befund „Orthogonalität braucht NICHT-Return-Achse").
  3) Die dollar-neutrale Variante (demeaned TSMOM) ENTFERNT das Beta — sollte dann aber ≈ CSM sein
     (cross-sectionales Momentum). ⇒ Test misst auch deren corr zu CSM.
Ein echter 2.-Engine-Kandidat müsste: nach Kosten OOS-positiv ÜBER der Härtungs-Schwelle, period-robust, UND
zu CSM unkorreliert sein — UND markt-neutral. Sonst ehrliches „tot" (wie Funding R3 / Reversal R8).

Mechanik 1:1 wie csm.simulate (Vortags-Gewichte = kein Lookahead, Turnover-Fee, Funding-Proxy −w·funding).
Geändert wird NUR die Portfolio-Konstruktion (per-Asset-Trend statt Cross-Section). Read-only (csm_prices),
0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402  (_matrix + _vol + CSM-simulate)


def simulate_tsmom(syms, ts, C, fund, L, H, fee, capital, mode="raw", volscale=False, a=None, b=None):
    """Per-Asset Time-Series-Momentum. mode='raw' (netto-Beta erlaubt) | 'neutral' (demeaned, dollar-neutral).
    Gross-Exposure auf sum|w|=1.0 normiert => direkt mit CSM (gross 1.0) vergleichbar."""
    a = a if a is not None else 0
    b = b if b is not None else len(ts)
    N = len(syms)
    w = [0.0] * N; w_prev = [0.0] * N
    rets = []; tss = []; equity = []; eq = capital
    nets = []; gross = []
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
            val = [None] * N
            for i in range(N):
                lo, hi = C[i][t - L], C[i][t]
                m = (hi / lo - 1.0) if (lo and hi and lo > 0) else None
                if m is None:
                    continue
                s = 1.0 if m > 0 else (-1.0 if m < 0 else 0.0)
                if volscale:
                    v = csr._vol(C[i], t, L)
                    if not (v and v > 0):
                        continue
                    s = s / v                       # vol-Targeting: Größe ~ 1/Vola, Vorzeichen = Trend
                val[i] = s
            valid = [i for i in range(N) if val[i] is not None]
            if len(valid) >= 6:
                if mode == "neutral":               # demean => dollar-neutral (entfernt Markt-Beta)
                    mean_s = statistics.mean(val[i] for i in valid)
                    vals = {i: (val[i] - mean_s) for i in valid}
                else:                               # raw => Netto-Exposure (Markt-Beta) erlaubt
                    vals = {i: val[i] for i in valid}
                gsum = sum(abs(v) for v in vals.values())
                neww = [0.0] * N
                if gsum > 0:
                    for i, v in vals.items():
                        neww[i] = v / gsum          # sum|w| = 1.0
                cost = fee * sum(abs(neww[i] - w_prev[i]) for i in range(N))
                w = neww; w_prev = list(w)
        net = pr - cost
        eq *= (1.0 + net)
        equity.append([ts[t], eq]); rets.append(net); tss.append(ts[t])
        nets.append(sum(w)); gross.append(sum(abs(x) for x in w))
    st = mn_base.equity_stats(rets, equity, capital, eq)
    st["rets"] = rets; st["ts"] = tss
    st["avg_net"] = statistics.mean(nets) if nets else 0.0
    st["avg_abs_net"] = statistics.mean(abs(x) for x in nets) if nets else 0.0
    st["avg_gross"] = statistics.mean(gross) if gross else 0.0
    return st


def _sh(r):
    sd = statistics.pstdev(r) if len(r) > 1 else 0.0
    return (statistics.mean(r) / sd * math.sqrt(365)) if sd > 0 else 0.0


def _psr(r):
    if len(r) < 3:
        return 0.0
    mean = statistics.mean(r); sd = statistics.pstdev(r)
    if sd <= 0:
        return 0.0
    sk, ku = mn_base._skew_kurt(r, mean, sd)
    return mn_base.psr(mean / sd, sk, ku, len(r))


def _corr_ts(ts_a, ra, ts_b, rb):
    """Pearson-Korrelation zweier Renditereihen, ausgerichtet auf gemeinsame Zeitstempel."""
    da = dict(zip(ts_a, ra)); db = dict(zip(ts_b, rb))
    common = [t for t in da if t in db]
    if len(common) < 10:
        return 0.0, len(common)
    x = [da[t] for t in common]; y = [db[t] for t in common]
    mx, my = statistics.mean(x), statistics.mean(y)
    cov = sum((u - mx) * (v - my) for u, v in zip(x, y)) / len(common)
    sx, sy = statistics.pstdev(x), statistics.pstdev(y)
    return (cov / (sx * sy) if (sx > 0 and sy > 0) else 0.0), len(common)


def _market_series(syms, ts, C, a, b):
    """Equal-Weight-Markt-Tagesrendite (Proxy für Markt-Beta-Exposure)."""
    N = len(syms); out_ts = []; out_r = []
    for t in range(a + 1, b):
        rs = []
        for i in range(N):
            af, bf = C[i][t - 1], C[i][t]
            if af and bf and af > 0:
                rs.append(bf / af - 1.0)
        if rs:
            out_ts.append(ts[t]); out_r.append(statistics.mean(rs))
    return out_ts, out_r


def wf_pooled(syms, ts, C, fund, candidates, mode, fee, n_windows=4, min_train=150):
    """Anchored WF: je Fenster Selektion (bestes (L,H,vol) nach Train-Sharpe) -> OOS-Test -> Returns gepoolt."""
    T = len(ts); test_len = (T - min_train) // n_windows
    pooled = []; pooled_ts = []; picks = []
    for wnd in range(n_windows):
        tr_end = min_train + wnd * test_len
        te_end = min(T, tr_end + test_len)
        if te_end - tr_end < 30:
            continue
        best, best_sh = None, -1e9
        for (L, H, vs) in candidates:
            st = simulate_tsmom(syms, ts, C, fund, L, H, fee, 10000.0, mode=mode, volscale=vs, a=0, b=tr_end)
            if st.get("sharpe") is not None and st["sharpe"] > best_sh:
                best_sh, best = st["sharpe"], (L, H, vs)
        L, H, vs = best
        oos = simulate_tsmom(syms, ts, C, fund, L, H, fee, 10000.0, mode=mode, volscale=vs, a=tr_end - L - 1, b=te_end)
        pooled += oos["rets"]; pooled_ts += oos["ts"]
        picks.append((wnd, best, round(oos["sharpe"], 2)))
    return pooled, pooled_ts, picks


def main():
    try:  # Konsole kann cp1252 sein -> Unicode in Prints nicht crashen lassen
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    m = csr._matrix()
    if not m:
        print("Keine Preis-Daten."); return
    syms, ts, C, fund = m
    T = len(ts)
    FEE, CAP = 0.0006, 10000.0
    print(f"Daten: {len(syms)} Symbole, {T} Tage  |  TSMOM (per-Asset Trend), kosten-/funding-inklusiv\n")

    # ---- 1) IN-SAMPLE (Hypothese, NICHT die Entscheidung) + EXPOSURE-DIAGNOSE ----
    print("=== IN-SAMPLE (volle 2J) — Sharpe + AVG-NETTO-EXPOSURE (Markt-Beta-Test) ===")
    print(f"{'mode':>8}{'L':>4}{'vol':>6}{'Sharpe':>8}{'PSR':>7}{'annPct':>8}{'avgNet':>8}{'avgGross':>9}")
    for mode in ("raw", "neutral"):
        for L in (30, 60, 90, 120):
            for vs in (False, True):
                st = simulate_tsmom(syms, ts, C, fund, L, 1, FEE, CAP, mode=mode, volscale=vs)
                print(f"{mode:>8}{L:>4}{str(vs):>6}{st['sharpe']:>8.2f}{(st.get('psr') or 0):>7.3f}"
                      f"{(st.get('ann_pct') or 0):>8.1f}{st['avg_net']:>8.2f}{st['avg_gross']:>9.2f}")
    print("  Lesart avgNet: ~0 => dollar-neutral; |avgNet| groß => trägt Markt-Beta (kein MN-Edge).")

    # ---- 2) ANCHORED WF (Selektion auf Train, OOS-Test) + KOSTEN-STRESS, je mode ----
    cands = [(L, H, vs) for L in (30, 60, 90, 120) for H in (1, 5) for vs in (False, True)]
    K = len(cands)
    thr = 0.5 + 0.2 * math.sqrt(2 * math.log(max(2, K)))
    print(f"\n=== ANCHORED WF (4 Fenster, gepoolt OOS) + KOSTEN-STRESS | {K} Kandidaten, Schwelle ~{thr:.2f} ===")
    print(f"{'mode':>8}{'OOS@6bps':>10}{'OOS@10':>9}{'OOS@20':>9}{'PSR@6':>8}{'n':>6}  picks")
    oos_store = {}
    for mode in ("raw", "neutral"):
        shs = []; p6 = None; store = None
        for bps in (6, 10, 20):
            pooled, pooled_ts, picks = wf_pooled(syms, ts, C, fund, cands, mode, bps / 1e4)
            shs.append(_sh(pooled))
            if bps == 6:
                p6 = _psr(pooled); store = (pooled, pooled_ts, picks)
        oos_store[mode] = store
        pk = " ".join(f"w{w}:L{b[0]}H{b[1]}v{int(b[2])}={s}" for (w, b, s) in store[2])
        print(f"{mode:>8}{shs[0]:>10.2f}{shs[1]:>9.2f}{shs[2]:>9.2f}{p6:>8.3f}{len(store[0]):>6}  {pk}")

    # ---- 3) DIVERSIFIKATION: corr(TSMOM, CSM-vol) + corr(TSMOM, Markt) über langes OOS-Segment ----
    print("\n=== DIVERSIFIKATION + MARKT-BETA (festes OOS-Segment ab Tag 150) ===")
    split = 150
    csm = csr.simulate(syms, ts, C, fund, 14, 1, 0.30, FEE, CAP, skip=0, volscale=True, a=split - 15, b=T)
    csm_ts = ts[split:T]   # csr.simulate-Start = a+L+1 = (split-15)+14+1 = split -> rets decken ts[split:T]
    mkt_ts, mkt_r = _market_series(syms, ts, C, split, T)
    for mode in ("raw", "neutral"):
        seg = simulate_tsmom(syms, ts, C, fund, 90, 1, FEE, CAP, mode=mode, volscale=False, a=split - 91, b=T)
        c_csm, n1 = _corr_ts(seg["ts"], seg["rets"], csm_ts, csm["rets"])
        c_mkt, n2 = _corr_ts(seg["ts"], seg["rets"], mkt_ts, mkt_r)
        tag_csm = "unkorreliert" if abs(c_csm) < 0.3 else "KORRELIERT"
        tag_mkt = "markt-neutral" if abs(c_mkt) < 0.3 else "MARKT-BETA"
        print(f"  TSMOM-{mode:7} L90: corr(CSM-vol)={c_csm:+.3f} [{tag_csm}]  "
              f"corr(Markt)={c_mkt:+.3f} [{tag_mkt}]  avgNet={seg['avg_net']:+.2f}  (n~{n1})")

    # ---- 4) VERDIKT ----
    print("\n=== VERDIKT ===")
    raw_oos = _sh(oos_store["raw"][0]); neu_oos = _sh(oos_store["neutral"][0])
    print(f"  raw     OOS-Sharpe(6bps) {raw_oos:>5.2f}  {'>' if raw_oos > thr else '<'} Schwelle {thr:.2f}")
    print(f"  neutral OOS-Sharpe(6bps) {neu_oos:>5.2f}  {'>' if neu_oos > thr else '<'} Schwelle {thr:.2f}")
    print("  Ein 2.-Engine-Kandidat muss: OOS > Schwelle (period-/kosten-robust) UND markt-neutral (|corr(Markt)|<0.3)")
    print("  UND zu CSM unkorreliert (|corr(CSM)|<0.3). Trifft NICHT alles zu => ehrliche Sackgasse (kein Bauen).")


if __name__ == "__main__":
    main()
