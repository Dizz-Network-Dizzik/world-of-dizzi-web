"""volume_research.py — (D) 2.-MN-Engine via VOLUMEN-Achse (neue Datendimension): Amihud-Illiquidität.

Bisher nur Preis-Achsen getestet (Return→CSM, Vola→LowVol). VOLUMEN ist eine genuin andere Dimension
⇒ echte Chance auf einen zu Preis-Edges orthogonalen 2. Sockel-Edge. ccxt-OHLCV liefert Volumen
(Basis-Währung); Dollar-Volumen = close×volume (geprüft: BTC ~3.8 Mrd/Tag).

A-priori-Hypothese (Amihud 2002, gut belegt): illiquide Assets tragen eine Liquiditätsprämie.
Amihud-Illiquidität illiq_i = Ø(|Tagesrendite| / Dollar-Volumen) über V Tage. Cross-sectional,
market-neutral: LONG high-illiq (Prämie), SHORT low-illiq, dollar-neutral.

EHRLICHE Failure-Modes (Test prüft): (1) „long illiquid" könnte in sterbenden Small-Caps sitzen
(Survivorship/Liquidität) ⇒ Sub-Universum. (2) Korreliert Illiq mit Vola/Momentum? ⇒ Korr-Check.
(3) Period-Fragilität ⇒ anchored WF. Kosten-inklusiv. Volumen-Snapshot eingefroren (reproduzierbar).
Read-only (ccxt public + csm_prices), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import mn_base                       # noqa: E402
import csm_signal_research as csr                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "_volume_hist.json")
DAY_MS = 24 * 60 * 60 * 1000


def _fetch_volume(syms):
    """Frische Tages-OHLCV je Symbol -> {sym: {day_ms: dollar_volume}}. Snapshot-Cache."""
    if os.path.exists(SNAP):
        raw = json.load(open(SNAP))
        return {s: {int(k): v for k, v in d.items()} for s, d in raw.items()}
    import ccxt
    cl = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    since0 = cl.milliseconds() - 760 * DAY_MS
    out = {}
    for i, sym in enumerate(syms):
        dv = {}
        cursor = since0
        while cursor < cl.milliseconds():
            try:
                batch = cl.fetch_ohlcv(sym, "1d", since=cursor, limit=200)
            except Exception:
                break
            if not batch:
                break
            for ts, o, h, l, c, v in batch:
                day = (int(ts) // DAY_MS) * DAY_MS
                if c and v:
                    dv[day] = float(c) * float(v)
            if batch[-1][0] <= cursor:
                break
            cursor = batch[-1][0] + DAY_MS
        if dv:
            # letzten (laufenden, unvollständigen) Tag droppen
            mx = max(dv)
            dv.pop(mx, None)
            out[sym] = dv
        if (i + 1) % 10 == 0:
            print(f"  ...{i+1}/{len(syms)} gefetcht", flush=True)
    json.dump({s: {str(k): v for k, v in d.items()} for s, d in out.items()}, open(SNAP, "w"))
    return out


def simulate_amihud(syms, ts, C, DV, fund, V, H, Q, fee, capital, a=None, b=None, sub=None):
    """LONG high-Amihud-Illiq (Prämie) / SHORT low-Illiq. Illiq = Ø(|ret|/dollar_vol) über V."""
    idx = list(range(len(syms))) if not sub else sub
    a = a if a is not None else 0
    b = b if b is not None else len(ts)
    N = len(syms)
    w = [0.0] * N; w_prev = [0.0] * N
    rets = []; equity = []; eq = capital
    start = a + V + 1
    for t in range(start, b):
        pr = 0.0
        for i in idx:
            if w[i]:
                af, bf = C[i][t - 1], C[i][t]
                if af and bf and af > 0:
                    pr += w[i] * (bf / af - 1.0)
                pr -= w[i] * fund[i]
        cost = 0.0
        if (t - start) % H == 0:
            sig = {}
            for i in idx:
                vals = []
                for j in range(t - V + 1, t + 1):
                    aa, bb, dv = C[i][j - 1], C[i][j], DV[i][j]
                    if aa and bb and aa > 0 and dv and dv > 0:
                        vals.append(abs(bb / aa - 1.0) / dv)
                if len(vals) >= max(3, V // 2):
                    sig[i] = sum(vals) / len(vals)
            valid = list(sig)
            if len(valid) >= 6:
                order = sorted(valid, key=lambda i: sig[i])    # aufsteigend: vorne = liquide (low illiq)
                k = max(1, int(Q * len(valid)))
                sh, lng = order[:k], order[-k:]                # SHORT low-illiq, LONG high-illiq
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
    a, b = a[-n:], b[-n:]
    ma, mb = statistics.mean(a), statistics.mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
    sa, sb = statistics.pstdev(a), statistics.pstdev(b)
    return cov / (sa * sb) if (sa > 0 and sb > 0) else 0.0


def wf(syms, ts, C, DV, fund, V, H, Q, fee, n_windows=6, sub=None):
    T = len(ts); tl = (T - 150) // n_windows; pooled = []
    for w in range(n_windows):
        tr = 150 + w * tl; te = min(T, tr + tl)
        if te - tr < 25:
            continue
        st = simulate_amihud(syms, ts, C, DV, fund, V, H, Q, fee, 10000.0, a=tr - V - 1, b=te, sub=sub)
        pooled += st["rets"]
    return pooled


def main():
    m = csr._matrix()
    if not m:
        print("Keine Preis-Daten."); return
    syms, ts, C, fund = m
    print(f"Preis-Matrix: {len(syms)} Symbole, {len(ts)} Tage. Volumen fetchen/laden ...", flush=True)
    vol = _fetch_volume(syms)
    print(f"Volumen-Historie: {len(vol)} Symbole")
    # DV-Matrix aligniert auf ts (forward-fill)
    DV = []
    for s in syms:
        d = vol.get(s, {})
        row = []
        last = None
        for tday in ts:
            key = (tday // DAY_MS) * DAY_MS
            v = d.get(key)
            if v is not None:
                last = v
            row.append(last)
        DV.append(row)
    FEE, CAP, Q = 0.0006, 10000.0, 0.30

    print("\n=== IN-SAMPLE Sharpe (Amihud-Illiquidität, volle 2J) ===")
    print(f"{'V':>4}{'H':>3}{'Sharpe':>9}{'PSR':>7}{'annPct':>9}")
    for V in (10, 20, 30, 60):
        for H in (5, 10):
            st = simulate_amihud(syms, ts, C, DV, fund, V, H, Q, FEE, CAP)
            print(f"{V:>4}{H:>3}{st['sharpe']:>9.2f}{(st.get('psr') or 0):>7.3f}{(st.get('ann_pct') or 0):>9.1f}")

    print("\n=== ANCHORED WF (6 Fenster, gepoolt OOS) + KOSTEN-STRESS ===")
    print(f"{'Variante':14}{'6bps':>8}{'10bps':>8}{'20bps':>8}{'PSR@6':>9}")
    for V, H in [(20, 5), (30, 5), (30, 10), (60, 5)]:
        shs = [_sh(wf(syms, ts, C, DV, fund, V, H, Q, bps / 1e4)) for bps in (6, 10, 20)]
        p6 = wf(syms, ts, C, DV, fund, V, H, Q, 0.0006)
        print(f"  V={V} H={H}      {shs[0]:>8.2f}{shs[1]:>8.2f}{shs[2]:>8.2f}{_psr(p6):>9.3f}")

    print("\n=== DIVERSIFIKATION: Korr Amihud <-> CSM-Momentum (vol-skaliert) ===")
    am = simulate_amihud(syms, ts, C, DV, fund, 30, 5, Q, FEE, CAP, a=148, b=len(ts))
    cm = csr.simulate(syms, ts, C, fund, 14, 2, Q, FEE, CAP, skip=0, volscale=True, a=133, b=len(ts))
    print(f"  corr(Amihud, CSM) OOS = {_corr(am['rets'], cm['rets']):+.3f}")

    print("\n=== SUB-UNIVERSUM (sitzt 'long illiquid' in toten Small-Caps?) ===")
    try:
        uni = json.loads(mn_base.meta_get("universe") or "[]")
    except Exception:
        uni = []
    liquid = [s for s in uni if s in set(syms)]
    for topk in (15, 25):
        keep = set(liquid[:topk])
        if len(keep) >= 12:
            sub = [i for i, s in enumerate(syms) if s in keep]
            print(f"  Top-{topk} liquide ({len(keep)}): OOS-Sharpe {_sh(wf(syms, ts, C, DV, fund, 30, 5, Q, 0.0006, sub=sub)):>6.2f}")

    # --- HÄRTUNG des liquiden Sub-Universums (der 0.90-Befund: period-stabil oder Artefakt?) ---
    print("\n=== ★ HÄRTUNG Top-20 liquide (Falsifikation des 0.90-Befunds) ===")
    keep20 = set(liquid[:20])
    sub20 = [i for i, s in enumerate(syms) if s in keep20]
    if len(sub20) >= 12:
        # (a) Fenster-fuer-Fenster Sharpe (kommt der Edge aus EINEM Fenster?)
        T = len(ts); nw = 6; tl = (T - 150) // nw
        perwin = []
        for w in range(nw):
            tr = 150 + w * tl; te = min(T, tr + tl)
            if te - tr < 25:
                continue
            st = simulate_amihud(syms, ts, C, DV, fund, 30, 5, Q, 0.0006, 10000.0, a=tr - 31, b=te, sub=sub20)
            perwin.append(_sh(st["rets"]))
        print(f"  Fenster-fuer-Fenster Sharpe (V30/H5): {[round(x,2) for x in perwin]}")
        pos = sum(1 for x in perwin if x > 0)
        print(f"    -> {pos}/{len(perwin)} Fenster positiv (period-stabil?)")
        # (b) Fenster-Sensitivitaet + PSR
        for nwv in (4, 6, 8):
            pooled = wf(syms, ts, C, DV, fund, 30, 5, Q, 0.0006, n_windows=nwv, sub=sub20)
            print(f"  {nwv} Fenster: OOS-Sharpe {_sh(pooled):.2f}  PSR {_psr(pooled):.3f}")
        # (c) Kosten-Stress auf Top-20
        sc = [_sh(wf(syms, ts, C, DV, fund, 30, 5, Q, bps/1e4, sub=sub20)) for bps in (6, 10, 20)]
        print(f"  Kosten 6/10/20bps: {sc[0]:.2f} / {sc[1]:.2f} / {sc[2]:.2f}")
        # (d) Korr zu CSM auf Top-20
        ams = simulate_amihud(syms, ts, C, DV, fund, 30, 5, Q, 0.0006, 10000.0, a=148, b=T, sub=sub20)
        cms = csr.simulate(syms, ts, C, fund, 14, 2, Q, 0.0006, 10000.0, skip=0, volscale=True, a=133, b=T)
        print(f"  Korr zu CSM (Top-20): {_corr(ams['rets'], cms['rets']):+.3f}")

    thr = 0.5 + 0.2 * math.sqrt(2 * math.log(5))
    print(f"\n  Härtungs-Schwelle ~{thr:.2f}. 2.-Engine-Kandidat NUR bei kosten-robustem, zu CSM unkorreliertem,")
    print("  nicht-illiquide-konzentriertem, period-stabilem OOS-Lift > Schwelle. Sonst ehrliches 'tot'.")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\n[{time.time()-t0:.0f}s]")
