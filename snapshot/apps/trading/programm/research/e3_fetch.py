"""E3-Fetch: Daily-Closes + tagesaggregierte Funding-Raten fuer das liquide Perp-Universum (ccxt, read-only).
Cache _e3_data.json: {ts:[...], closes:{sym:[...]}, funding:{sym:[...]}}  (funding = Tagessumme der 8h-Raten).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccxt  # noqa: E402

TOPN = int(sys.argv[1]) if len(sys.argv) > 1 else 80
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 730
MINCOV = int(sys.argv[3]) if len(sys.argv) > 3 else 400
DAY_MS = 24 * 60 * 60 * 1000

client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
markets = client.load_markets()
tickers = client.fetch_tickers()
swaps = sorted(
    [(s, float((tickers.get(s) or {}).get("quoteVolume") or 0)) for s, m in markets.items()
     if m.get("swap") and m.get("quote") == "USDT" and m.get("active") and ":USDT" in s],
    key=lambda x: x[1], reverse=True)
universe = [s for s, _ in swaps[:TOPN]]
start = client.milliseconds() - (DAYS + 5) * DAY_MS
now = client.milliseconds()


def paginate(fn, sym, key):
    cursor, rows = start, {}
    while cursor < now:
        try:
            batch = fn(sym, since=cursor, limit=200)
        except Exception:
            break
        if not batch:
            break
        for r in batch:
            if isinstance(r, dict):  # funding
                ts = int(r["timestamp"]); day = ts - (ts % DAY_MS)
                rows[day] = rows.get(day, 0.0) + float(r.get("fundingRate") or 0.0)
            else:  # ohlcv
                rows[int(r[0])] = float(r[4])
        last = batch[-1]["timestamp"] if isinstance(batch[-1], dict) else batch[-1][0]
        if last <= cursor:
            break
        cursor = last + DAY_MS
        if len(batch) < 2:
            break
    return rows


closes, funding = {}, {}
for sym in universe:
    try:
        cc = {}
        cursor = start
        while cursor < now:
            b = client.fetch_ohlcv(sym, timeframe="1d", since=cursor, limit=200)
            if not b:
                break
            for r in b:
                cc[int(r[0])] = float(r[4])
            if b[-1][0] <= cursor:
                break
            cursor = b[-1][0] + DAY_MS
        if len(cc) >= MINCOV:
            closes[sym] = cc
            funding[sym] = paginate(client.fetch_funding_rate_history, sym, "f")
    except Exception:
        continue

all_ts = sorted(set().union(*[set(c.keys()) for c in closes.values()]))
def col(d, fill=None):
    return [d.get(ts, fill) for ts in all_ts]
out = {"ts": all_ts,
       "closes": {s: col(closes[s]) for s in closes},
       "funding": {s: col(funding.get(s, {}), 0.0) for s in closes}}
json.dump(out, open("_e3_data.json", "w"))
print(f"Universum {len(universe)} -> {len(closes)} mit >= {MINCOV} Tagen ({len(all_ts)} Tage gesamt).")
print("Pairs:", ", ".join(sorted(s.split('/')[0] for s in closes)))
# Funding-Sanity: durchschnittliche annualisierte Funding je Pair (Tagessumme x365)
import statistics
favg = {s: statistics.mean([f for f in funding.get(s, {}).values()]) * 365 * 100 for s in closes if funding.get(s)}
top = sorted(favg.items(), key=lambda x: x[1], reverse=True)
print("hoechstes Funding (annual %):", [(s.split('/')[0], round(v, 1)) for s, v in top[:5]])
print("niedrigstes:", [(s.split('/')[0], round(v, 1)) for s, v in top[-5:]])
