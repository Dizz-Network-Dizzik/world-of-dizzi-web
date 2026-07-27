"""Liest die letzten Backtest-Kennzahlen aus Freqtrades Ergebnisordner als JSON.

Wird vom Orchestrator-Backend in der Engine-venv aufgerufen (dort ist Freqtrade
installiert). Ausgabe: eine JSON-Zeile mit den wichtigsten Kennzahlen.

Aufruf:
    python read_backtest_stats.py [results_dir]
"""

import json
import sys

from freqtrade.data.btanalysis import load_backtest_stats

results_dir = sys.argv[1] if len(sys.argv) > 1 else "user_data/backtest_results"

try:
    stats = load_backtest_stats(results_dir)
    strat = stats.get("strategy", {})
    if not strat:
        print(json.dumps({}))
        sys.exit(0)
    name, s = next(iter(strat.items()))

    def g(key, default=None):
        return s.get(key, default)

    def pct(key):
        v = g(key)
        return round(v * 100, 2) if v is not None else None

    out = {
        "strategy": name,
        "total_trades": g("total_trades"),
        "profit_total_pct": pct("profit_total"),
        "profit_total_abs": g("profit_total_abs"),
        "sharpe": g("sharpe"),
        "sortino": g("sortino"),
        "profit_factor": g("profit_factor"),
        "max_drawdown_pct": pct("max_drawdown_account") or pct("max_relative_drawdown"),
        "market_change_pct": pct("market_change"),
        "winrate_pct": round((g("winrate") or 0) * 100, 1),
    }
    print(json.dumps(out))
except Exception as exc:  # pragma: no cover
    print(json.dumps({"_error": f"{type(exc).__name__}: {exc}"}))
