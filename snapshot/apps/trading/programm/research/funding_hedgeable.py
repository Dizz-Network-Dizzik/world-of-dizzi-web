"""Schnitt: welche positiv-Netto-Carry-Perps sind ueberhaupt HEDGEBAR (liquides Spot-Market da)?
Echtes Carry-Universum = positiv-Netto-Carry UND Spot existiert UND Spot-Volumen ausreichend.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccxt  # noqa: E402

rows = json.load(open("_funding_scan_out.json"))
client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "spot"}})
spot_markets = client.load_markets()  # spot
spot_tickers = client.fetch_tickers()

pos = [r for r in rows if r["net_pct"] > 0]
print(f"{'PAIR':<16}{'net%/yr':>8}{'pos%':>6}  {'SPOT?':<7}{'spot_vol_USDT':>16}")
hedgeable = []
for r in sorted(pos, key=lambda x: x["net_pct"], reverse=True):
    base = r["sym"].split("/")[0]
    spot_sym = f"{base}/USDT"
    has_spot = spot_sym in spot_markets and spot_markets[spot_sym].get("active")
    vol = 0.0
    if has_spot:
        t = spot_tickers.get(spot_sym) or {}
        vol = float(t.get("quoteVolume") or 0)
    flag = "JA" if has_spot else "—"
    print(f"{r['sym']:<16}{r['net_pct']:>8.1f}{r['pos_share']:>6.0f}  {flag:<7}{vol:>16,.0f}")
    if has_spot and vol > 1_000_000:  # >1 Mio USDT/24h Spot-Liquiditaet als Mindestschwelle
        hedgeable.append({**r, "spot_vol": vol})

print(f"\nHEDGEBAR (Spot da & >1 Mio USDT/24h) & Netto-Carry>0: {len(hedgeable)}")
print(f"davon stabil (pos_share>=80% & net>5%): {sum(1 for r in hedgeable if r['pos_share']>=80 and r['net_pct']>5)}")
print("\nTop hedgebare Kandidaten:")
for r in sorted(hedgeable, key=lambda x: x["net_pct"], reverse=True)[:12]:
    print(f"  {r['sym']:<16} net {r['net_pct']:.1f}%/yr  pos {r['pos_share']:.0f}%  spot-vol {r['spot_vol']:,.0f} USDT")
