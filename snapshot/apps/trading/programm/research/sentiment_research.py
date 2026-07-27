"""sentiment_research.py — (C) Fear&Greed-Index als prädiktives Timing-Signal (key-frei, 8 J Historie).

A-priori-Hypothese (klassisch): Extreme Fear = Überverkauft → Mean-Reversion nach oben; Extreme Greed =
Überhitzt → Korrektur. Fear&Greed (alternative.me, key-frei, seit 2018) ist ein MARKT-WEITES Timing-Signal
(ein Wert/Tag) ⇒ informiert eine DIREKTIONALE BTC-Wette (nicht die markt-neutralen Engines).

EHRLICHE Reihenfolge: (1) IST F&G überhaupt prädiktiv? — Forward-Return-Korrelation + Quantil-Buckets
(deskriptiv, vor jeder Optimierung). (2) anchored-WF-Timing-Backtest (Threshold auf Train, OOS-Test),
kosten-inklusiv, vs Buy&Hold. Ein period-abhängiger/ausgepreister Effekt ist KEIN Edge.
Read-only (alternative.me + ccxt public), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
from backend.app import mn_base  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DAY_MS = 24 * 60 * 60 * 1000
FNG_SNAP = os.path.join(HERE, "_fng_hist.json")
BTC_SNAP = os.path.join(HERE, "_btc_daily.json")


def _fetch_fng():
    if os.path.exists(FNG_SNAP):
        return {int(k): v for k, v in json.load(open(FNG_SNAP)).items()}
    import urllib.request
    u = urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json", timeout=30)
    data = json.loads(u.read()).get("data", [])
    # alternative.me-Timestamp ist in SEKUNDEN -> *1000 fuer ms, dann auf Tag floored
    out = {(int(x["timestamp"]) * 1000 // DAY_MS) * DAY_MS: int(x["value"]) for x in data}
    json.dump({str(k): v for k, v in out.items()}, open(FNG_SNAP, "w"))
    return out


def _fetch_btc():
    if os.path.exists(BTC_SNAP):
        return {int(k): v for k, v in json.load(open(BTC_SNAP)).items()}
    import ccxt
    cl = ccxt.binance()
    out = {}
    since = cl.parse8601("2018-01-01T00:00:00Z")
    while since < cl.milliseconds():
        try:
            batch = cl.fetch_ohlcv("BTC/USDT", "1d", since=since, limit=1000)
        except Exception:
            break
        if not batch:
            break
        for ts, o, h, l, c, v in batch:
            out[(int(ts) // DAY_MS) * DAY_MS] = float(c)
        if batch[-1][0] <= since:
            break
        since = batch[-1][0] + DAY_MS
    json.dump({str(k): v for k, v in out.items()}, open(BTC_SNAP, "w"))
    return out


def main():
    fng = _fetch_fng()
    btc = _fetch_btc()
    days = sorted(set(fng) & set(btc))
    print(f"Fear&Greed: {len(fng)} | BTC daily: {len(btc)} | gemeinsam: {len(days)} Tage "
          f"({__import__('datetime').datetime.utcfromtimestamp(days[0]/1000).date()} -> "
          f"{__import__('datetime').datetime.utcfromtimestamp(days[-1]/1000).date()})")
    f = [fng[d] for d in days]
    px = [btc[d] for d in days]
    T = len(days)

    def fwd_ret(i, h):
        if i + h >= T:
            return None
        return px[i + h] / px[i] - 1.0

    # (1) IST F&G prädiktiv? Korrelation F&G[t] <-> Forward-Return[t->t+h]
    print("\n=== (1) DESKRIPTIV: ist F&G prädiktiv? (vor jeder Optimierung) ===")
    print("Forward-Return-Korrelation (negativ = Mean-Reversion: low F&G/fear -> hohe fwd returns):")
    for h in (1, 3, 7, 14, 30):
        pairs = [(f[i], fwd_ret(i, h)) for i in range(T) if fwd_ret(i, h) is not None]
        xs = [a for a, b in pairs]; ys = [b for a, b in pairs]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in pairs) / len(pairs)
        sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
        c = cov / (sx * sy) if sx > 0 and sy > 0 else 0
        print(f"  h={h:>2}d: corr={c:+.3f}  (n={len(pairs)})")

    # Quantil-Buckets: Ø 14d-Forward-Return je F&G-Bereich
    print("\nØ 14d-Forward-Return je F&G-Bucket:")
    buckets = [("Extreme Fear <20", lambda v: v < 20), ("Fear 20-40", lambda v: 20 <= v < 40),
               ("Neutral 40-60", lambda v: 40 <= v < 60), ("Greed 60-80", lambda v: 60 <= v < 80),
               ("Extreme Greed >=80", lambda v: v >= 80)]
    for name, pred in buckets:
        rs = [fwd_ret(i, 14) for i in range(T) if pred(f[i]) and fwd_ret(i, 14) is not None]
        if rs:
            print(f"  {name:22} n={len(rs):>4}  Ø14d={statistics.mean(rs)*100:+.2f}%  "
                  f"Trefferquote+={sum(1 for r in rs if r>0)/len(rs)*100:.0f}%")

    # (2) Timing-Backtest: long-only bei Fear, anchored WF (Threshold auf Train, OOS-Test)
    print("\n=== (2) TIMING-BACKTEST (anchored WF, kosten-inkl., long-only bei Fear) ===")
    FEE = 0.0006
    rets = [px[i + 1] / px[i] - 1.0 for i in range(T - 1)]

    def run(thr_low, hold, a, b):
        """Long BTC wenn F&G[t] < thr_low (Mean-Reversion), sonst flat. Hold-Tage. Kosten bei Wechsel."""
        pos = 0; days_held = 0; pnl = []
        for i in range(a, min(b, T - 1)):
            want = 1 if f[i] < thr_low else 0
            if want == 1:
                days_held = hold
            new_pos = 1 if days_held > 0 else 0
            cost = FEE if new_pos != pos else 0.0
            pnl.append(new_pos * rets[i] - cost)
            pos = new_pos
            days_held = max(0, days_held - 1)
        return pnl

    def sh(r):
        sd = statistics.pstdev(r) if len(r) > 1 else 0
        return statistics.mean(r) / sd * math.sqrt(365) if sd > 0 else 0

    # anchored WF: 5 Fenster, Threshold/hold auf Train wählen, OOS poolen. + Baselines.
    nW = 5; tl = (T - 200) // nW
    pooled, bh = [], []
    for w in range(nW):
        tr_end = 200 + w * tl; te_end = min(T - 1, tr_end + tl)
        if te_end - tr_end < 30:
            continue
        best, bs = None, -9
        for thr in (15, 20, 25, 30, 40):
            for hold in (3, 7, 14):
                s = sh(run(thr, hold, 0, tr_end))
                if s > bs:
                    bs, best = s, (thr, hold)
        pooled += run(best[0], best[1], tr_end, te_end)
        bh += rets[tr_end:te_end]
    print(f"  Fear-Timing (adaptiv):   OOS-Sharpe {sh(pooled):.2f}  (n={len(pooled)}, im Markt {sum(1 for x in pooled if x!=0)/len(pooled)*100:.0f}% der Zeit)")
    print(f"  Buy&Hold BTC (Referenz): Sharpe {sh(bh):.2f}")
    # fixe a-priori-Variante (Extreme Fear <20, hold 14) ueber denselben OOS-Bereich
    fix = run(20, 14, 200, T - 1)
    print(f"  Fix 'Extreme Fear <20, hold14': Sharpe {sh(fix):.2f}  (im Markt {sum(1 for x in fix if x!=0)/len(fix)*100:.0f}%)")
    # Gegentest: long bei GREED (Momentum, da corr positiv) + kontinuierliches F&G-Tilt
    def run_greed(thr_high, a, b):
        pos = 0; pnl = []
        for i in range(a, min(b, T - 1)):
            new_pos = 1 if f[i] > thr_high else 0
            cost = FEE if new_pos != pos else 0.0
            pnl.append(new_pos * rets[i] - cost); pos = new_pos
        return pnl
    print(f"  [in-sample, fix thr60] long bei GREED: Sharpe {sh(run_greed(60,200,T-1)):.2f}  -> verlockend, JETZT falsifizieren:")

    # ★ EHRLICHE HÄRTUNG des Greed-Momentum (anchored WF + Fenster-Stabilität + PBO)
    print("\n=== ★ FALSIFIKATION GREED-MOMENTUM (anchored WF: thr auf Train, OOS-Test) ===")
    gp, bh2, perwin = [], [], []
    for w in range(nW):
        tr_end = 200 + w * tl; te_end = min(T - 1, tr_end + tl)
        if te_end - tr_end < 30:
            continue
        best, bs = 60, -9
        for thr in (40, 50, 55, 60, 65, 70):
            s = sh(run_greed(thr, 0, tr_end))
            if s > bs:
                bs, best = s, thr
        seg = run_greed(best, tr_end, te_end)
        gp += seg; bh2 += rets[tr_end:te_end]; perwin.append((best, round(sh(seg), 2), round(sh(rets[tr_end:te_end]), 2)))
    print(f"  Fenster (pick_thr, greed_OOS_Sh, B&H_OOS_Sh): {perwin}")
    print(f"  GEPOOLT OOS: Greed-Timing Sharpe {sh(gp):.2f}  vs  Buy&Hold {sh(bh2):.2f}  (Lift {sh(gp)-sh(bh2):+.2f})")
    pos_w = sum(1 for _, g, b in perwin if g > b)
    print(f"  Fenster wo Greed > B&H: {pos_w}/{len(perwin)}")
    # PBO ueber Greed-Thresholds (CSCV-light): wechselt der beste thr period-spezifisch?
    # ★ ENTSCHEIDEND: hat F&G Mehrwert UEBER simples Preis-Trend-Following? (F&G ist ein Momentum-Proxy)
    def run_sma(n, a, b):
        pos = 0; pnl = []
        for i in range(a, min(b, T - 1)):
            sma = statistics.mean(px[i - n + 1:i + 1]) if i >= n else px[i]
            new_pos = 1 if px[i] > sma else 0
            cost = FEE if new_pos != pos else 0.0
            pnl.append(new_pos * rets[i] - cost); pos = new_pos
        return pnl
    sp, _bh = [], []
    for w in range(nW):
        tr_end = 200 + w * tl; te_end = min(T - 1, tr_end + tl)
        if te_end - tr_end < 30:
            continue
        best, bs = 100, -9
        for n in (20, 50, 100, 150, 200):
            s = sh(run_sma(n, max(n, 200 - n), tr_end))
            if s > bs:
                bs, best = s, n
        sp += run_sma(best, tr_end, te_end)
    print(f"\n=== ★ MEHRWERT-CHECK: F&G vs simples Preis-Trend (BTC>SMA) ===")
    print(f"  Greed-Timing (F&G):      OOS-Sharpe {sh(gp):.2f}")
    print(f"  Preis-Trend (BTC>SMA):   OOS-Sharpe {sh(sp):.2f}")
    print(f"  Buy&Hold:                OOS-Sharpe {sh(bh2):.2f}")
    print(f"  => F&G-Mehrwert ueber Preis-Trend: {sh(gp)-sh(sp):+.2f}  "
          f"({'JA, eigener Edge' if sh(gp)-sh(sp)>0.15 else 'NEIN -> F&G ist redundanter Momentum-Proxy' if sh(gp)-sh(sp)<0.05 else 'marginal'})")
    print("\n  Verdikt-Regel: nur wenn F&G den simplen Preis-Trend ROBUST schlaegt, hat es eigenen Daten-Mehrwert.")
    print("  Sonst ehrlich: F&G ist nur ein (redundanter) Proxy fuer Preis-Momentum, das wir schon haben.")


if __name__ == "__main__":
    main()
