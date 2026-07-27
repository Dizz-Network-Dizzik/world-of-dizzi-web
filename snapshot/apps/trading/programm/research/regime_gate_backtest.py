"""regime_gate_backtest.py — EHRLICHE OOS-Validierung der Regime-Gates (anchored Walk-Forward).

Frage: Bringt ein Regime-Gate (eine Strategie nur in „guten" Regimes handeln lassen) einen ECHTEN
OUT-OF-SAMPLE-Lift — oder sind die Round-2-Split-Mittel nur In-Sample-Deskription?

Methode (kein Leakage):
- Jedem geschlossenen Trade wird das Regime bei **ENTRY** (open_date) zugeordnet — **point-in-time**:
  der letzte Markt-Snapshot ZEITLICH VOR/BEI open_date (kein close-Lookahead, kein Future-Snapshot).
- Pro Strategie zeitlich sortiert, **anchored Split**: erste 60 % TRAIN (Gate lernen) → letzte 40 % TEST.
- Gate wird NUR auf TRAIN gelernt: erlaubte Regimes = {Regime mit TRAIN-n≥MIN ∧ TRAIN-avg>0}.
- Auf TEST verglichen: always-on (alle Trades) vs. gated (nur erlaubte Entry-Regimes). Plus Welch-t-Test
  (erlaubte vs. gesperrte Test-Trades) = ist das Regime-Label OOS überhaupt prädiktiv?

Read-only (RO-SQLite gegen tradesv3 + market_snapshots). 0 Echtgeld, keine Writes. profit_pct = freqtrade
close_profit (netto Gebühren; Paper-Slippage idealisiert). Per-Trade-Unabhängigkeit nicht garantiert
(überlappende Trades) ⇒ t-Werte indikativ, nicht endgültig.
"""
from __future__ import annotations
import os, sys, math, sqlite3, bisect, statistics
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> programm/
from backend.app import stats, meta  # noqa: E402
from backend.app.registry import list_bots  # noqa: E402

TOL_HOURS = 6.0
MIN_TRAIN_REGIME = 20    # Mindest-Train-Trades je Regime, um es ins Gate aufzunehmen
MIN_TEST = 60            # Mindest-Test-Trades, damit eine Strategie berichtet wird
REGIMES = ("trend_up", "trend_down", "range")


def _snapshots():
    snaps = [(meta._to_utc(r.get("ts")), r.get("regime"))
             for r in stats.get_market_snapshots(limit=100000)]
    snaps = sorted([(dt, rg) for dt, rg in snaps if dt and rg in REGIMES], key=lambda x: x[0])
    return [s[0] for s in snaps], [s[1] for s in snaps]


def _make_regime_at_pit(times, regs):
    tol = timedelta(hours=TOL_HOURS)

    def regime_at_pit(dt):
        """Letzter Snapshot mit ts <= dt (point-in-time, kein Future), innerhalb Toleranz."""
        if not times or dt is None:
            return None
        i = bisect.bisect_right(times, dt) - 1   # letzter <= dt
        if i < 0:
            return None
        return regs[i] if (dt - times[i]) <= tol else None
    return regime_at_pit


def _trades_with_entry_regime(bot_id, regime_at_pit):
    db = stats.PROJECT_ROOT / "engine" / "user_data" / f"tradesv3_{bot_id}.sqlite"
    if not db.exists():
        return []
    con = sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT open_date, close_profit FROM trades "
            "WHERE is_open=0 AND open_date IS NOT NULL AND close_profit IS NOT NULL "
            "ORDER BY open_date").fetchall()
    except Exception:
        return []
    finally:
        con.close()
    out = []
    for r in rows:
        dt = meta._to_utc(str(r["open_date"]))
        reg = regime_at_pit(dt)
        if reg is None or dt is None:
            continue
        out.append((dt, reg, round(float(r["close_profit"]) * 100, 4)))
    return out


def _welch_t(a, b):
    if len(a) < 2 or len(b) < 2:
        return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.pvariance(a), statistics.pvariance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (ma - mb) / se if se > 0 else 0.0


def main():
    times, regs = _snapshots()
    print(f"Snapshots: {len(times)} (Regime-Zeitachse)")
    regime_at_pit = _make_regime_at_pit(times, regs)

    # Trades je Strategie sammeln (Entry-Regime, point-in-time)
    by_strat: dict[str, list] = {}
    for b in list_bots():
        for tr in _trades_with_entry_regime(b.id, regime_at_pit):
            by_strat.setdefault(b.strategy, []).append(tr)
    for s in by_strat:
        by_strat[s].sort(key=lambda x: x[0])

    print(f"\n{'Strategie':22s}{'test_n':>7}{'gate(train)':>26}{'allOn%':>9}{'gated%':>9}{'lift':>8}{'t(in/out)':>10}{'keep%':>7}")
    print("-" * 100)
    pooled_kept, pooled_out, pooled_all = [], [], []
    helped = hurt = 0
    for strat, trades in sorted(by_strat.items()):
        if len(trades) < int(MIN_TEST / 0.4):   # genug für 60/40 mit MIN_TEST im Test
            continue
        split = int(len(trades) * 0.6)
        train, test = trades[:split], trades[split:]
        if len(test) < MIN_TEST:
            continue
        # Gate auf TRAIN lernen
        tr_by_reg: dict[str, list] = {}
        for _, reg, p in train:
            tr_by_reg.setdefault(reg, []).append(p)
        allowed = {reg for reg, ps in tr_by_reg.items()
                   if len(ps) >= MIN_TRAIN_REGIME and statistics.mean(ps) > 0}
        if not allowed:
            allowed = set(REGIMES)   # Gate lernt „nichts gut" → kein Gate (alles an), ehrlich
        # TEST auswerten
        all_p = [p for _, _, p in test]
        kept = [p for _, reg, p in test if reg in allowed]
        out = [p for _, reg, p in test if reg not in allowed]
        if not kept:
            continue
        mean_all = statistics.mean(all_p)
        mean_kept = statistics.mean(kept)
        lift = mean_kept - mean_all
        t = _welch_t(kept, out) if out else float("nan")
        keep_pct = 100.0 * len(kept) / len(all_p)
        gate_str = "+".join(sorted(r[:5] for r in allowed)) if allowed != set(REGIMES) else "(alle)"
        print(f"{strat:22s}{len(test):>7}{gate_str:>26}{mean_all:>9.3f}{mean_kept:>9.3f}{lift:>+8.3f}"
              f"{t:>10.2f}{keep_pct:>7.0f}")
        pooled_kept += kept; pooled_out += out; pooled_all += all_p
        if lift > 0:
            helped += 1
        elif lift < 0:
            hurt += 1

    print("-" * 100)
    if pooled_all:
        mk, ma = statistics.mean(pooled_kept), statistics.mean(pooled_all)
        print(f"\nPOOLED (trade-gewichtet, OOS-Test):")
        print(f"  always-on  Ø={ma:+.4f}%  (n={len(pooled_all)})")
        print(f"  gated      Ø={mk:+.4f}%  (n_kept={len(pooled_kept)})")
        print(f"  gated-out  Ø={statistics.mean(pooled_out):+.4f}%  (n_out={len(pooled_out)})" if pooled_out else "  (nichts gesperrt)")
        print(f"  OOS-Lift (gated − always-on) = {mk - ma:+.4f}%/Trade   "
              f"Welch-t(kept vs out) = {_welch_t(pooled_kept, pooled_out):.2f}")
        print(f"  Strategien mit OOS-Lift>0: {helped} | mit Lift<0: {hurt}")
        print("\nLesart: Lift>0 UND t>~2 (erlaubte Trades signifikant besser als gesperrte) = Gate trägt OOS.")
        print("        Lift≈0/t≈0 = Regime-Label OOS NICHT prädiktiv ⇒ Gate ist In-Sample-Artefakt.")

    # --- Non-Stationaritäts-Diagnose: kippt die Regime-Performance zwischen TRAIN und TEST? ---
    print("\n=== NON-STATIONARITÄT (Ø profit% je Regime: TRAIN vs TEST) ===")
    print(f"{'Strategie':22s}{'Regime':12s}{'train_n':>8}{'train_avg':>10}{'test_n':>8}{'test_avg':>10}{'flip?':>7}")
    for strat, trades in sorted(by_strat.items()):
        if len(trades) < int(MIN_TEST / 0.4):
            continue
        split = int(len(trades) * 0.6)
        train, test = trades[:split], trades[split:]
        if len(test) < MIN_TEST:
            continue
        for reg in REGIMES:
            tr = [p for _, r, p in train if r == reg]
            te = [p for _, r, p in test if r == reg]
            if len(tr) < 10 or len(te) < 10:
                continue
            ta, tea = statistics.mean(tr), statistics.mean(te)
            flip = "JA" if (ta > 0) != (tea > 0) else ""
            print(f"{strat:22s}{reg:12s}{len(tr):>8}{ta:>+10.3f}{len(te):>8}{tea:>+10.3f}{flip:>7}")


if __name__ == "__main__":
    main()
