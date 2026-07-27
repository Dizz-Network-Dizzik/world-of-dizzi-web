"""Funding-Carry Universums-Scan (read-only, public): ranke liquide Bitget-Perpetuals nach
annualisiertem NETTO-Carry (Funding - Gebuehren-Drag) + Stabilitaet. Ehrliche Decke-Messung.
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccxt  # noqa: E402

TOPN = int(sys.argv[1]) if len(sys.argv) > 1 else 50
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 90
# Konservative Gebuehren: Roundtrip = enter(spot+perp)+exit(spot+perp) Taker.
SPOT_TAKER, FUT_TAKER = 0.0010, 0.0006
ROUND_TRIP = 2 * (SPOT_TAKER + FUT_TAKER)  # = 0.32%
HOLD_YEARS = DAYS / 365.0
FEE_DRAG_ANNUAL = ROUND_TRIP / HOLD_YEARS  # Drag bei einmaligem Ein-/Ausstieg ueber DAYS

client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
markets = client.load_markets()
# Liquide USDT-Perpetuals nach 24h-Quote-Volumen ranken
tickers = client.fetch_tickers()
swaps = []
for sym, m in markets.items():
    if m.get("swap") and m.get("quote") == "USDT" and m.get("active") and ":USDT" in sym:
        t = tickers.get(sym) or {}
        qv = t.get("quoteVolume") or 0
        swaps.append((sym, float(qv)))
swaps.sort(key=lambda x: x[1], reverse=True)
universe = [s for s, _ in swaps[:TOPN]]
print(f"Scan: Top {len(universe)} Perpetuals nach Volumen, {DAYS}T Funding-Historie. "
      f"Fee-Drag(annual,1x Hold)≈{FEE_DRAG_ANNUAL*100:.2f}%")

since = client.milliseconds() - DAYS * 24 * 60 * 60 * 1000
rows = []
for sym in universe:
    try:
        hist = client.fetch_funding_rate_history(sym, since=since, limit=1000)
        rates = [h["fundingRate"] for h in hist if h.get("fundingRate") is not None]
        if len(rates) < 30:
            continue
        n = len(rates)
        per_year = n / HOLD_YEARS  # tatsaechliche Perioden/Jahr aus den Daten
        avg = statistics.mean(rates)
        gross_annual = avg * per_year
        net_annual = gross_annual - FEE_DRAG_ANNUAL
        pos = sum(1 for r in rates if r > 0) / n
        sd = statistics.pstdev(rates) * per_year  # annualisierte Funding-Streuung
        rows.append({"sym": sym, "n": n, "gross_pct": gross_annual * 100, "net_pct": net_annual * 100,
                     "pos_share": pos * 100, "vol_pct": sd * 100})
    except Exception:
        continue

rows.sort(key=lambda r: r["net_pct"], reverse=True)
print(f"\n{'PAIR':<18}{'net%/yr':>9}{'gross%':>9}{'pos%':>7}{'fund-vol%':>11}{'n':>5}")
for r in rows[:25]:
    print(f"{r['sym']:<18}{r['net_pct']:>9.1f}{r['gross_pct']:>9.1f}{r['pos_share']:>7.0f}{r['vol_pct']:>11.0f}{r['n']:>5}")
pos_net = [r for r in rows if r["net_pct"] > 0]
print(f"\nPaare mit NETTO-Carry > 0: {len(pos_net)}/{len(rows)}")
print(f"davon robust (pos_share>=70% & net>5%): {sum(1 for r in pos_net if r['pos_share']>=70 and r['net_pct']>5)}")
json.dump(rows, open("_funding_scan_out.json", "w"))
