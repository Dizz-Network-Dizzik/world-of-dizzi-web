"""Vektorisierter market-neutraler Cross-Sectional-Momentum-Backtest auf Daily-Closes.
Signal: Return ueber Lookback L (optional Skip S juengste Tage). Long Top-Quantil / Short Bottom-Quantil,
gleichgewichtet, dollar-neutral. Rebalancing alle H Tage. Gebuehr auf Turnover. IS/OOS-Split + Sweep.
"""
import json
import math
import os
import sys

import numpy as np

os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open("_csm_data.json"))
ts = d["ts"]
syms = sorted(d["closes"].keys())
C = np.array([[ (v if v is not None else np.nan) for v in d["closes"][s]] for s in syms], float)  # pairs x days
# Forward-fill innerhalb jeder Reihe (Luecken), fuehrende NaNs bleiben
for i in range(C.shape[0]):
    last = np.nan
    for j in range(C.shape[1]):
        if np.isnan(C[i, j]):
            C[i, j] = last
        else:
            last = C[i, j]
R = np.full_like(C, np.nan)
R[:, 1:] = C[:, 1:] / C[:, :-1] - 1.0  # taegliche Returns
N, T = C.shape
FEE = 0.0006  # pro Seite (Futures Taker), auf Turnover


def backtest(L, S, H, Qfrac, fee=FEE, lo=0, hi=None):
    hi = hi if hi is not None else T
    w_prev = np.zeros(N)
    daily, costs = [], 0.0
    w = np.zeros(N)
    for t in range(lo, hi):
        # 1) ZUERST Tagesrendite mit den AM VORTAG gesetzten Gewichten kassieren (kein Lookahead)
        rt = R[:, t]
        pr = np.nansum(w * np.where(np.isnan(rt), 0.0, rt))
        daily.append(pr)
        # 2) DANN ggf. rebalancen: Signal aus Closes bis t -> neue Gewichte gelten ab t+1
        if t >= L + 1 and (t - lo) % H == 0:
            base = C[:, t - L]
            top = C[:, t - S] if S > 0 else C[:, t]
            mom = np.where((base > 0) & ~np.isnan(base) & ~np.isnan(top), top / base - 1.0, np.nan)
            valid = ~np.isnan(mom)
            nv = valid.sum()
            if nv >= 6:
                order = np.argsort(np.where(valid, mom, -np.inf))
                k = max(1, int(Qfrac * nv))
                longs = order[-k:]
                shorts = [s for s in order[:k] if valid[s]]
                w = np.zeros(N)
                if len(longs) and len(shorts):
                    w[longs] = 0.5 / len(longs)
                    w[shorts] = -0.5 / len(shorts)
            costs += fee * np.abs(w - w_prev).sum()
            w_prev = w.copy()
    daily = np.array(daily)
    # Kosten gleichmaessig nicht verteilen, sondern als Gesamt-Drag abziehen:
    gross = daily.sum()
    net_curve = np.cumsum(daily) - np.linspace(0, costs, len(daily))
    net_ret = net_curve[-1]
    ann = net_ret / (len(daily) / 365.0)
    sd = daily.std() * math.sqrt(365) if daily.std() > 0 else 1e-9
    sharpe = (net_ret / (len(daily) / 365.0)) / sd if sd > 0 else 0.0
    # Max Drawdown auf Netto-Kurve
    peak = np.maximum.accumulate(net_curve)
    dd = (net_curve - peak)
    maxdd = dd.min()
    wins = (daily > 0).sum() / len(daily) * 100
    return {"ann_pct": ann * 100, "sharpe": round(sharpe, 2), "maxdd_pct": maxdd * 100,
            "gross_pct": gross * 100, "cost_pct": costs * 100, "winrate": round(wins, 1),
            "days": len(daily)}


print(f"Universum {N} Pairs, {T} Tage. Fee {FEE*100:.2f}%/Seite auf Turnover.")
# 4-Fenster-Walk-Forward: je Setup Sharpe pro Fenster + Mittel/Min
nwin = 4
edges = [int(round(x)) for x in np.linspace(0, T, nwin + 1)]
print(f"\n4 Fenster a ~{edges[1]-edges[0]} Tage. Spalten = Sharpe je Fenster (Mittel|Min) + Gesamt-ann%/DD%\n")
print(f"{'L':>3}{'S':>3}{'H':>3}{'Q':>5} | {'w1':>6}{'w2':>6}{'w3':>6}{'w4':>6} | {'meanSh':>7}{'minSh':>7} | {'ann%':>7}{'DD%':>7}")
configs = [(14,0,7,0.30),(14,0,1,0.30),(30,0,7,0.30),(30,0,7,0.20),(60,0,7,0.30),(60,0,7,0.20),(30,0,1,0.30),(20,0,3,0.25)]
for (L,S,H,Q) in configs:
    shs = []
    for wi in range(nwin):
        lo = max(L + 1, edges[wi]); hi = edges[wi + 1]
        if hi - lo < 20:
            shs.append(0.0); continue
        shs.append(backtest(L, S, H, Q, lo=lo, hi=hi)["sharpe"])
    full = backtest(L, S, H, Q, lo=L + 1, hi=T)
    meanSh = sum(shs)/len(shs)
    print(f"{L:>3}{S:>3}{H:>3}{Q:>5.2f} | " + "".join(f"{x:>6.2f}" for x in shs) +
          f" | {meanSh:>7.2f}{min(shs):>7.2f} | {full['ann_pct']:>7.1f}{full['maxdd_pct']:>7.1f}")

# Gebuehren-/Turnover-Sensitivitaet des Top-Setups (L=14,H=1,Q=0.30) — entscheidend bei taeglichem Rebalancing
print("\nGebuehren-Sensitivitaet Top-Setup L=14 H=1 Q=0.30 (Gesamtzeitraum):")
print(f"{'fee/Seite':>10}{'ann%':>8}{'sharpe':>8}{'DD%':>8}{'cost%':>8}")
for f in (0.0004, 0.0006, 0.0010, 0.0015, 0.0020, 0.0030):
    r = backtest(14, 0, 1, 0.30, fee=f, lo=15, hi=T)
    print(f"{f*100:>9.2f}%{r['ann_pct']:>8.1f}{r['sharpe']:>8.2f}{r['maxdd_pct']:>8.1f}{r['cost_pct']:>8.0f}")
