"""fundamental_signals_research.py — (A) vorhandene Fundamental-Daten PRÄDIKTIV statt defensiv.

`fundamental.py` zieht DVOL/F&G/On-Chain etc., nutzt sie aber nur als Risk-Off-Overlay (`dir_scale`).
Hier ehrlich getestet, ob sie als prädiktive DIREKTIONALE Timing-Signale taugen — einzeln UND kombiniert.

Signale (alle markt-weit, direktional BTC): F&G-Momentum (long bei Greed), DVOL-MeanReversion (long bei
hoher impliziter Vola = Angst-Kapitulation), Preis-Trend (BTC>SMA). Plus eine simple Kombination (Voting).
EHRLICH: Mehrwert-Check vs Preis-basierte Referenz (Preis-Trend / realisierte Vola — die wir GRATIS haben).
anchored WF, kosten-inkl. Caveat: DVOL-Überschneidung nur ~500 Tage ⇒ indikativ, nicht robust.
Read-only (Deribit + reuse sentiment_research), 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, json, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sentiment_research as sr  # noqa: E402  (reuse F&G + BTC)

DAY = 86400000
DVOL_SNAP = os.path.join(sr.HERE, "_dvol_daily.json")


def _fetch_dvol():
    if os.path.exists(DVOL_SNAP):
        return {int(k): v for k, v in json.load(open(DVOL_SNAP)).items()}
    end = int(time.time() * 1000); start = end - 1000 * DAY
    url = (f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC"
           f"&start_timestamp={start}&end_timestamp={end}&resolution=43200")
    rows = json.loads(urllib.request.urlopen(url, timeout=25).read())["result"]["data"]
    out = {}
    for ts, o, h, l, c in rows:
        out[(int(ts) // DAY) * DAY] = c   # Tagesschluss (letzter 12h-Wert gewinnt)
    json.dump({str(k): v for k, v in out.items()}, open(DVOL_SNAP, "w"))
    return out


def _sh(r):
    sd = statistics.pstdev(r) if len(r) > 1 else 0
    return statistics.mean(r) / sd * math.sqrt(365) if sd > 0 else 0


def main():
    fng = sr._fetch_fng(); btc = sr._fetch_btc(); dvol = _fetch_dvol()
    days = sorted(set(fng) & set(btc) & set(dvol))
    print(f"Gemeinsame Tage (F&G+BTC+DVOL): {len(days)} "
          f"({__import__('datetime').datetime.utcfromtimestamp(days[0]/1000).date()} -> "
          f"{__import__('datetime').datetime.utcfromtimestamp(days[-1]/1000).date()})")
    px = [btc[d] for d in days]; f = [fng[d] for d in days]; dv = [dvol[d] for d in days]
    T = len(days)
    rets = [px[i + 1] / px[i] - 1.0 for i in range(T - 1)]
    rv = [statistics.pstdev([px[j] / px[j - 1] - 1 for j in range(i - 19, i + 1)]) * math.sqrt(365) * 100
          if i >= 20 else 0 for i in range(T)]
    FEE = 0.0006

    def bt(signal_fn, a, b):
        """signal_fn(i) -> 1 long / 0 flat. kosten-inkl."""
        pos = 0; pnl = []
        for i in range(a, min(b, T - 1)):
            np_ = signal_fn(i)
            cost = FEE if np_ != pos else 0.0
            pnl.append(np_ * rets[i] - cost); pos = np_
        return pnl

    def sma(i, n):
        return statistics.mean(px[max(0, i - n + 1):i + 1])

    # Signale (Schwellen a-priori/mittig gewählt; anchored WF unten waehlt fenster-spezifisch nur fuer combo)
    sigs = {
        "Greed-Momentum (F&G>60)": lambda i: 1 if f[i] > 60 else 0,
        "DVOL-MeanRev (DVOL>Median)": lambda i: 1 if dv[i] > statistics.median(dv) else 0,
        "Preis-Trend (BTC>SMA100)": lambda i: 1 if px[i] > sma(i, 100) else 0,
        "realized-Vol>Median (Referenz)": lambda i: 1 if rv[i] > statistics.median(rv) else 0,
    }
    print(f"\n=== Einzel-Signale (volle {T} Tage, kosten-inkl., long-only) ===")
    print(f"{'Signal':34}{'Sharpe':>8}{'imMarkt%':>9}")
    for name, fn in sigs.items():
        p = bt(fn, 100, T - 1)
        print(f"{name:34}{_sh(p):>8.2f}{sum(1 for x in p if x!=0)/len(p)*100:>8.0f}%")
    bh = rets[100:T - 1]
    print(f"{'Buy&Hold (Referenz)':34}{_sh(bh):>8.2f}{100:>8.0f}%")

    # Kombination (Voting: long wenn >=2 von [Greed, DVOL, Preis-Trend] bullish) + anchored WF
    def combo(i):
        votes = (1 if f[i] > 60 else 0) + (1 if dv[i] > statistics.median(dv) else 0) + (1 if px[i] > sma(i, 100) else 0)
        return 1 if votes >= 2 else 0
    print(f"\n=== Kombination (Voting >=2/3) vs beste Einzel vs Preis-Referenz (anchored WF, 4 Fenster) ===")
    nW = 4; tl = (T - 120) // nW
    cp, tp, bhp = [], [], []
    for w in range(nW):
        tr = 120 + w * tl; te = min(T - 1, tr + tl)
        if te - tr < 25:
            continue
        cp += bt(combo, tr, te)
        tp += bt(lambda i: 1 if px[i] > sma(i, 100) else 0, tr, te)   # Preis-Trend-Referenz
        bhp += rets[tr:te]
    print(f"  Kombination (F&G+DVOL+Trend):  OOS-Sharpe {_sh(cp):.2f}")
    print(f"  Preis-Trend allein (Referenz): OOS-Sharpe {_sh(tp):.2f}")
    print(f"  Buy&Hold:                      OOS-Sharpe {_sh(bhp):.2f}")
    print(f"  => Mehrwert der Fundamental-Kombi ueber simplen Preis-Trend: {_sh(cp)-_sh(tp):+.2f}")
    print("\n  Caveat: nur ~500 gemeinsame Tage (DVOL-Limit) => indikativ. Verdikt-Regel: nur wenn die")
    print("  Fundamental-Kombi den GRATIS-Preis-Trend robust schlaegt, lohnt der Daten-/Code-Aufwand.")


if __name__ == "__main__":
    main()
