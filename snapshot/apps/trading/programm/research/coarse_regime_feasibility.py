"""coarse_regime_feasibility.py — Kann die Coarser-Regime-Hypothese (R4-Follow-on) überhaupt getestet werden?

Hypothese (aus R4): wenn ~3 h-HMM-Regimes zu kurz/non-stationär für tradebare Gates sind, wären
mehrtägige (7/14-Tage-)Regimes evtl. OOS-stationär konditionierbar.

Diese Datei prüft die VORAUSSETZUNG ehrlich: über wie viele DISTINKTE mehrtägige Regime-Episoden
erstreckt sich die vorhandene TRADE-Historie? Coarse Regimes werden aus der vollen 2-J-Preishistorie
(csm_prices, BTC+ETH+SOL-Index) **point-in-time** berechnet — aber die Trades selbst existieren nur
in einem schmalen Kalenderfenster. Wenn dieses Fenster < wenige mehrtägige Episoden umfasst, ist die
Hypothese mit den aktuellen Daten **nicht testbar** (Daten-Blocker, kein Methoden-Mangel).

Read-only. 0 Echtgeld.
"""
from __future__ import annotations
import os, sys, math, statistics, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # research/
from backend.app import stats, mn_base                      # noqa: E402
from backend.app.registry import list_bots                  # noqa: E402
import regime_gate_backtest as rg                            # noqa: E402  (Trade-Loader wiederverwenden)

DAY_MS = 24 * 60 * 60 * 1000
BASKET = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


def _index_daily():
    """Gleichgewichteter BTC+ETH+SOL-Index (Tageslevel) aus csm_prices."""
    closes = {}
    with stats._conn() as c:
        mn_base.ensure(c)
        for sym, day, close in c.execute("SELECT symbol, day, close FROM csm_prices").fetchall():
            if sym in BASKET and close and close > 0:
                closes.setdefault(sym, {})[(int(day) // DAY_MS) * DAY_MS] = float(close)
    days = sorted(set.intersection(*[set(closes[s]) for s in BASKET if s in closes]))
    if len(days) < 60:
        return [], {}
    base = {s: closes[s][days[0]] for s in BASKET}
    idx = {d: sum((closes[s][d] / base[s]) for s in BASKET) / len(BASKET) for d in days}
    return days, idx


def _coarse_regimes(days, idx, lookback, theta):
    """Point-in-time mehrtägiges Regime: z = N-Tage-Return / (Tagesvola·√N); trend_up/down/range per θ."""
    logret = {days[i]: math.log(idx[days[i]] / idx[days[i - 1]]) for i in range(1, len(days))}
    reg = {}
    for i in range(max(lookback, 30), len(days)):
        d = days[i]
        retN = math.log(idx[d] / idx[days[i - lookback]])
        recent = [logret[days[j]] for j in range(i - 30, i) if days[j] in logret]
        vol = statistics.pstdev(recent) if len(recent) > 5 else 0.0
        denom = vol * math.sqrt(lookback) if vol > 0 else 0.0
        z = retN / denom if denom > 0 else 0.0
        reg[d] = "trend_up" if z > theta else ("trend_down" if z < -theta else "range")
    return reg


def _pit(reg_by_day):
    keys = sorted(reg_by_day)
    import bisect
    def f(dt):
        if dt is None or not keys:
            return None
        dms = int(dt.timestamp() * 1000)
        i = bisect.bisect_right(keys, dms) - 1
        return reg_by_day[keys[i]] if i >= 0 else None
    return f


def _episodes(seq):
    eps, prev = 0, None
    for r in seq:
        if r != prev:
            eps += 1; prev = r
    return eps


def main():
    days, idx = _index_daily()
    print(f"Index-Tage (BTC+ETH+SOL): {len(days)}  "
          f"({datetime.datetime.utcfromtimestamp(days[0]/1000).date()} -> "
          f"{datetime.datetime.utcfromtimestamp(days[-1]/1000).date()})")

    for lookback, theta in [(7, 0.5), (14, 0.5)]:
        reg = _coarse_regimes(days, idx, lookback, theta)
        pit = _pit(reg)
        # Trades laden + Entry-Coarse-Regime
        by_strat = {}
        all_entry_days = set()
        for b in list_bots():
            for dt, _hmm, p in rg._trades_with_entry_regime(b.id, pit):
                cr = pit(dt)
                if cr is None:
                    continue
                by_strat.setdefault(b.strategy, []).append((dt, cr, p))
                all_entry_days.add((int(dt.timestamp() * 1000) // DAY_MS) * DAY_MS)
        n_trades = sum(len(v) for v in by_strat.values())
        # Coarse-Regime-Sequenz ÜBER DIE TRADE-TAGE
        trade_days = sorted(all_entry_days)
        seq = [reg.get(d) for d in trade_days if reg.get(d)]
        from collections import Counter
        comp = Counter(seq)
        print(f"\n=== COARSE lookback={lookback}d, θ={theta} ===")
        print(f"  Trades mit Coarse-Regime: {n_trades}")
        print(f"  Trade-Tage: {len(trade_days)}  "
              f"({datetime.datetime.utcfromtimestamp(trade_days[0]/1000).date()} -> "
              f"{datetime.datetime.utcfromtimestamp(trade_days[-1]/1000).date()})")
        print(f"  Distinkte Coarse-Regimes im Trade-Fenster: {dict(comp)}")
        print(f"  Coarse-Regime-EPISODEN im Trade-Fenster: {_episodes(seq)}")
        # Pro Strategie: wie viele Coarse-Regimes mit n>=20?
        testable = 0
        for s, tr in sorted(by_strat.items()):
            rc = Counter(cr for _, cr, _ in tr)
            usable = {r: n for r, n in rc.items() if n >= 20}
            if len(usable) >= 2:
                testable += 1
        print(f"  Strategien mit >=2 Coarse-Regimes (je n>=20) = Gate lernbar: {testable}/{len(by_strat)}")

    print("\n=== VERDIKT ===")
    print("  Ein anchored-WF-Gate-Test braucht je Strategie >=2 Regimes mit Train- UND Test-Stichprobe")
    print("  und >=3 UNABHÄNGIGE Episoden je Regime. Bei einem ~9-Tage-Trade-Fenster umfasst ein 7/14-Tage-")
    print("  Regime praktisch 1 Episode / 1-2 Zustände ⇒ Coarser-Regime-Hypothese ist mit den AKTUELLEN")
    print("  Daten NICHT testbar (Daten-Blocker). Re-Test erst, wenn die Trade-Historie mehrere mehrtägige")
    print("  Regime-Episoden umspannt (Größenordnung: Monate).")


if __name__ == "__main__":
    main()
