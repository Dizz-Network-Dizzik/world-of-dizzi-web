"""Holt Daily-OHLCV fuer die liquidesten Bitget-Perps (ccxt, read-only) und cached eine
Close-Matrix (pairs x days) als JSON. Basis fuer den Cross-Sectional-Momentum-Backtest.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccxt  # noqa: E402

TOPN = int(sys.argv[1]) if len(sys.argv) > 1 else 45
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 730

client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
markets = client.load_markets()
tickers = client.fetch_tickers()
swaps = []
for sym, m in markets.items():
    if m.get("swap") and m.get("quote") == "USDT" and m.get("active") and ":USDT" in sym:
        qv = float((tickers.get(sym) or {}).get("quoteVolume") or 0)
        swaps.append((sym, qv))
swaps.sort(key=lambda x: x[1], reverse=True)
universe = [s for s, _ in swaps[:TOPN]]

DAY_MS = 24 * 60 * 60 * 1000
start = client.milliseconds() - (DAYS + 5) * DAY_MS
now = client.milliseconds()
series = {}
for sym in universe:
    try:
        cursor = start
        rows = {}
        while cursor < now:
            batch = client.fetch_ohlcv(sym, timeframe="1d", since=cursor, limit=200)
            if not batch:
                break
            for c in batch:
                rows[int(c[0])] = float(c[4])
            last = batch[-1][0]
            if last <= cursor:
                break
            cursor = last + DAY_MS
            if len(batch) < 2:
                break
        if len(rows) > 60:
            series[sym] = rows  # ts -> close
    except Exception:
        continue

# gemeinsame Zeitachse (alle Tage); Pairs mit >= MINCOV Tagen behalten (juengere zugelassen -> weniger Survivorship-Bias)
MINCOV = int(sys.argv[3]) if len(sys.argv) > 3 else 150
all_ts = sorted(set().union(*[set(s.keys()) for s in series.values()]))
keep = {sym: s for sym, s in series.items() if len(s) >= MINCOV}
matrix = {sym: [s.get(ts) for ts in all_ts] for sym, s in keep.items()}
out = {"ts": all_ts, "closes": matrix}
json.dump(out, open("_csm_data.json", "w"))
print(f"Universum: {len(universe)} angefragt -> {len(keep)} mit voller Historie ({len(all_ts)} Tage).")
print("Behaltene Pairs:", ", ".join(sorted(k.split('/')[0] for k in keep))[:400])
