"""E3-Backtest: Cross-Sectional Momentum MIT Perp-Funding-P&L + Universums-Robustheit.
Funding-P&L/Tag = -sum(w * daily_funding)  (Long zahlt pos. Funding, Short erhaelt).
Robustheit: Random-Subsampling + Leave-one-out (Survivorship-Proxy).
"""
import json
import math
import os
import random

import numpy as np

os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open("_e3_data.json"))
ts = d["ts"]
ALL = sorted(d["closes"].keys())


FUNDING_MODE = "const"  # 'sparse' = Rohdaten (nur ~30T befuellt, ungueltig) | 'const' = per-Pair-Mittel als Proxy


def build(syms):
    C = np.array([[(v if v is not None else np.nan) for v in d["closes"][s]] for s in syms], float)
    F = np.array([[(v if v is not None else 0.0) for v in d["funding"][s]] for s in syms], float)
    if FUNDING_MODE == "const":
        # Bitget liefert nur ~30T Funding-Historie -> per-Pair-Mittel der verfuegbaren (nonzero) Werte
        # als konstanten Proxy ueber den ganzen Zeitraum anwenden (ehrliche Drag-Abschaetzung).
        for i in range(F.shape[0]):
            nz = F[i][F[i] != 0.0]
            F[i, :] = (nz.mean() if len(nz) else 0.0)
    for i in range(C.shape[0]):
        last = np.nan
        for j in range(C.shape[1]):
            if np.isnan(C[i, j]):
                C[i, j] = last
            else:
                last = C[i, j]
    R = np.full_like(C, np.nan)
    R[:, 1:] = C[:, 1:] / C[:, :-1] - 1.0
    return C, R, F


def backtest(syms, L=14, S=0, H=1, Qfrac=0.30, fee=0.0006, lo=None, hi=None, use_funding=True):
    C, R, F = build(syms)
    N, T = C.shape
    lo = L + 1 if lo is None else lo
    hi = T if hi is None else hi
    w = np.zeros(N); w_prev = np.zeros(N); daily = []; costs = 0.0
    for t in range(lo, hi):
        rt = R[:, t]
        pr = np.nansum(w * np.where(np.isnan(rt), 0.0, rt))
        if use_funding:
            pr += -np.nansum(w * F[:, t])  # Funding-P&L
        daily.append(pr)
        if t >= L + 1 and (t - lo) % H == 0:
            base = C[:, t - L]; top = C[:, t - S] if S > 0 else C[:, t]
            mom = np.where((base > 0) & ~np.isnan(base) & ~np.isnan(top), top / base - 1.0, np.nan)
            valid = ~np.isnan(mom); nv = int(valid.sum())
            if nv >= 6:
                order = np.argsort(np.where(valid, mom, -np.inf))
                k = max(1, int(Qfrac * nv))
                longs = order[-k:]; shorts = [s for s in order[:k] if valid[s]]
                w = np.zeros(N)
                if len(longs) and len(shorts):
                    w[longs] = 0.5 / len(longs); w[np.array(shorts)] = -0.5 / len(shorts)
            costs += fee * np.abs(w - w_prev).sum(); w_prev = w.copy()
    daily = np.array(daily)
    net = np.cumsum(daily) - np.linspace(0, costs, len(daily))
    ann = net[-1] / (len(daily) / 365.0)
    sd = daily.std() * math.sqrt(365)
    sharpe = ann / sd if sd > 0 else 0.0
    peak = np.maximum.accumulate(net); maxdd = (net - peak).min()
    return {"sharpe": round(sharpe, 2), "ann_pct": round(ann * 100, 1), "maxdd_pct": round(maxdd * 100, 1)}


print(f"Universum {len(ALL)} Pairs, {len(ts)} Tage. Setup L=14 H=1 Q=0.30, fee 0.06%/Seite.\n")
print("== Funding-Effekt (Gesamtzeitraum) ==")
nf = backtest(ALL, use_funding=False)
wf = backtest(ALL, use_funding=True)
print(f"  OHNE Funding: Sharpe {nf['sharpe']}  ann {nf['ann_pct']}%  DD {nf['maxdd_pct']}%")
print(f"  MIT  Funding: Sharpe {wf['sharpe']}  ann {wf['ann_pct']}%  DD {wf['maxdd_pct']}%")

print("\n== 4-Fenster-WF (mit Funding) ==")
T = len(ts); edges = [int(round(x)) for x in np.linspace(0, T, 5)]
shs = []
for wi in range(4):
    lo = max(15, edges[wi]); hi = edges[wi + 1]
    r = backtest(ALL, lo=lo, hi=hi, use_funding=True)
    shs.append(r["sharpe"])
    print(f"  Fenster {wi+1}: Sharpe {r['sharpe']}  ann {r['ann_pct']}%")
print(f"  -> mean {sum(shs)/4:.2f}  min {min(shs):.2f}")

print("\n== Survivorship-Robustheit: 60 Random-Subsets (je 18 von 31 Pairs), mit Funding ==")
random.seed(42)
subs = []
for _ in range(60):
    sample = random.sample(ALL, 18)
    subs.append(backtest(sample, use_funding=True)["sharpe"])
subs.sort()
pos = sum(1 for s in subs if s > 0) / len(subs) * 100
print(f"  Sharpe-Verteilung: median {subs[len(subs)//2]:.2f}  25%={subs[len(subs)//4]:.2f}  "
      f"75%={subs[3*len(subs)//4]:.2f}  min={subs[0]:.2f}  max={subs[-1]:.2f}  >0: {pos:.0f}%")

print("\n== Leave-one-out (entferne je 1 Pair, mit Funding) ==")
loo = sorted([(s.split('/')[0], backtest([x for x in ALL if x != s], use_funding=True)["sharpe"]) for s in ALL],
             key=lambda x: x[1])
print(f"  schlechteste 3 (Pair raus -> Sharpe): {loo[:3]}")
print(f"  beste 3: {loo[-3:]}  (voll={wf['sharpe']})")
