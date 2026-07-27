"""Einmal-Skript: re-validiert ALLE Engine-Strategien mit dem ehrlichen Gate (Profit>0 je Fenster).

Hintergrund (2026-06-10): Die bestehende Evidenz-Basis (strategy_validations) entstand mit dem
alten schwachen Gate bzw. während die Backtests gegen Dynamik-Configs still kaputt waren
(VolumePairList nicht backtestbar). Dieses Skript läuft entkoppelt vom Backend gegen die API,
sequentiell (Backtest-Lock serialisiert ohnehin), und schreibt je Strategie eine Fortschritts-
Zeile nach stdout (vom Aufrufer in eine Log-Datei umgeleitet).
"""
import json
import urllib.request

STRATEGIES = [
    "TrendFollowEma", "MeanReversionRsi", "MomentumMacd", "FuturesMacdRsiScalp",
    "FuturesBreakoutVol", "FuturesBbandsBounce", "SessionOpenBreakout",
    "GridRange", "DcaDip", "MasterMeta",
]
BASE = "http://127.0.0.1:8137"

for s in STRATEGIES:
    url = f"{BASE}/api/strategies/{s}/validate?days=120&windows=3&embargo=1"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=1800) as r:
            d = json.loads(r.read().decode("utf-8"))
        m = d.get("metrics") or {}
        print(f"{s}: validated={d.get('validated')} ({d.get('reason')}) "
              f"profit={m.get('profit_total_pct')} pf={m.get('profit_factor')} "
              f"dd={m.get('max_drawdown_pct')} trades={m.get('total_trades')}", flush=True)
    except Exception as exc:
        print(f"{s}: FEHLER {type(exc).__name__}: {exc}", flush=True)

print("=== Re-Validierung komplett ===", flush=True)
