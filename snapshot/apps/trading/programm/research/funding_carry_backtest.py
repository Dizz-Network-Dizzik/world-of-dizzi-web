"""funding_carry_backtest.py — EHRLICHE Validierung der Funding-Carry-Edge (Variante B, cross-sectional).

Frage: Trägt eine markt-neutrale Funding-Carry-Strategie NACH Kosten UND inklusive der Preis-Drift
der Beine einen echten OOS-Edge — genug, um als 2. MN-Engine zu qualifizieren (gehärtete Sharpe > ~0.83)?

Strategie (perp-only, dollar-neutral): je Tag ranke das Universum nach trailing Funding;
SHORT die Top-k (höchstes Funding → Short kassiert), LONG die Bottom-k (negativstes Funding → Long kassiert),
gleiche Notional je Seite. Halte 1 Tag, rebalance täglich.

EHRLICHKEIT (§0): zwei P&L-Komponenten werden GETRENNT und GEMEINSAM gemessen —
  (1) Funding-P&L (der gewünschte Carry)   (2) Preis-P&L der Long/Short-Beine (die Drift, die der Carry
  oft auffrisst, weil hohes Funding mit bullishem Preisdruck korreliert). Plus Turnover-Kosten (taker+slippage).
Nur die KOMBINIERTE, kosten-inklusive, OUT-OF-SAMPLE-Zahl zählt als Edge.

Read-only / public ccxt (kein Auth, keine Orders, 0 Echtgeld). Preise aus csm_prices (schon vorhanden, 2J).
Funding-Historie wird gezogen + als Snapshot (research/_funding_hist.json) eingefroren (Reproduzierbarkeit).
"""
from __future__ import annotations
import json, math, os, sys, time, datetime, statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> programm/
from backend.app import stats, mn_base  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "_funding_hist.json")
DAY_MS = 24 * 60 * 60 * 1000
FUND_DAYS = 365              # wie weit zurück Funding ziehen
TAKER_BPS = 6.0             # Bitget Futures Taker (0.06%)
SLIP_BPS = 2.0             # konservative Slippage je Trade-Seite


def _load_closes() -> dict[str, dict[int, float]]:
    """csm_prices -> {symbol: {day_ms: close}} (Tagesschlusskurse, schon in der DB)."""
    out: dict[str, dict[int, float]] = {}
    with stats._conn() as c:
        mn_base.ensure(c)
        for sym, day, close in c.execute("SELECT symbol, day, close FROM csm_prices").fetchall():
            if close and close > 0:
                day_floored = (int(day) // DAY_MS) * DAY_MS   # auf Mitternacht-UTC raster (Funding-Alignment)
                out.setdefault(sym, {})[day_floored] = float(close)
    return out


def _fetch_funding(symbols: list[str]) -> dict[str, dict[int, float]]:
    """ccxt Bitget fetch_funding_rate_history je Symbol -> {symbol: {day_ms: funding_sum_des_tages}}.
    Snapshot-Cache für Reproduzierbarkeit. Funding alle 8h -> Tagessumme = realer Tages-Carry."""
    if os.path.exists(SNAP):
        raw = json.load(open(SNAP))
        return {s: {int(k): v for k, v in d.items()} for s, d in raw.items()}
    import ccxt
    cl = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    since = cl.milliseconds() - FUND_DAYS * DAY_MS
    out: dict[str, dict[int, float]] = {}
    for i, sym in enumerate(symbols):
        try:
            hist = cl.fetch_funding_rate_history(sym, since=since, limit=1000)
            daily: dict[int, float] = {}
            for h in hist:
                fr = h.get("fundingRate")
                ts = h.get("timestamp")
                if fr is None or ts is None:
                    continue
                day = (int(ts) // DAY_MS) * DAY_MS
                daily[day] = daily.get(day, 0.0) + float(fr)
            if daily:
                out[sym] = daily
            print(f"  [{i+1}/{len(symbols)}] {sym}: {len(daily)} Tage", flush=True)
        except Exception as e:
            print(f"  [{i+1}/{len(symbols)}] {sym}: FEHLER {type(e).__name__}", flush=True)
    json.dump({s: {str(k): v for k, v in d.items()} for s, d in out.items()}, open(SNAP, "w"))
    return out


def _sharpe(rets: list[float]) -> float:
    if len(rets) < 2:
        return 0.0
    sd = statistics.pstdev(rets)
    return (statistics.mean(rets) / sd * math.sqrt(365)) if sd > 0 else 0.0


def _psr(rets: list[float]) -> float:
    if len(rets) < 3:
        return 0.0
    mean = statistics.mean(rets); sd = statistics.pstdev(rets)
    if sd <= 0:
        return 0.0
    sk, ku = mn_base._skew_kurt(rets, mean, sd)
    return mn_base.psr(mean / sd, sk, ku, len(rets))


def _maxdd(rets: list[float]) -> float:
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= (1.0 + r); peak = max(peak, eq); dd = min(dd, eq / peak - 1.0)
    return dd * 100


def backtest(closes, funding, days, lookback: int, k: int, cost_bps: float):
    """Cross-sectional Funding-Carry. Gibt (combined, funding_only, price_only, turnover_avg, beta_btc)."""
    prev_w: dict[str, float] = {}
    combined, fonly, ponly = [], [], []
    btc = "BTC/USDT:USDT"
    btc_rets, strat_rets_for_beta = [], []
    for ti in range(lookback, len(days) - 1):
        t, t1 = days[ti], days[ti + 1]
        # Signal: trailing-Funding-Mittel bis t-1 (point-in-time, KEIN Lookahead)
        sig = {}
        for s, fd in funding.items():
            window = [fd[days[j]] for j in range(ti - lookback, ti) if days[j] in fd]
            if len(window) >= max(3, lookback // 2) and t in closes.get(s, {}) and t1 in closes.get(s, {}) and t in fd:
                sig[s] = sum(window) / len(window)
        if len(sig) < 2 * k:
            continue
        ranked = sorted(sig, key=lambda s: sig[s])
        longs, shorts = ranked[:k], ranked[-k:]          # negativstes Funding long, höchstes short
        w = {s: 1.0 / k for s in longs}
        w.update({s: -1.0 / k for s in shorts})
        # Realisiert über [t, t1]
        f_pnl = p_pnl = 0.0
        for s, wi in w.items():
            side = 1.0 if wi > 0 else -1.0
            price_ret = closes[s][t1] / closes[s][t] - 1.0
            fund_real = funding[s].get(t, 0.0)
            p_pnl += side * abs(wi) * price_ret
            f_pnl += (-side) * abs(wi) * fund_real        # Short kassiert +Funding wenn Funding>0
        # Turnover-Kosten (positions-persistenz-bewusst): Σ|w_t − w_{t-1}| × (taker+slippage)
        keys = set(w) | set(prev_w)
        turnover = sum(abs(w.get(s, 0.0) - prev_w.get(s, 0.0)) for s in keys)
        cost = turnover * cost_bps / 1e4
        prev_w = w
        combined.append(f_pnl + p_pnl - cost)
        fonly.append(f_pnl)
        ponly.append(p_pnl)
        if btc in closes and t in closes[btc] and t1 in closes[btc]:
            btc_rets.append(closes[btc][t1] / closes[btc][t] - 1.0)
            strat_rets_for_beta.append(f_pnl + p_pnl - cost)
    # Markt-Neutralität: Beta Strategie<->BTC
    beta = 0.0
    if len(btc_rets) > 5:
        mb, ms = statistics.mean(btc_rets), statistics.mean(strat_rets_for_beta)
        cov = sum((a - mb) * (b - ms) for a, b in zip(btc_rets, strat_rets_for_beta)) / len(btc_rets)
        vb = statistics.pvariance(btc_rets)
        beta = cov / vb if vb > 0 else 0.0
    return {"combined": combined, "fonly": fonly, "ponly": ponly, "n": len(combined), "beta_btc": beta}


def main():
    closes = _load_closes()
    print(f"csm_prices: {len(closes)} Symbole")
    print(f"Funding ziehen (oder Snapshot laden) — {FUND_DAYS}d ...", flush=True)
    funding = _fetch_funding(list(closes.keys()))
    print(f"Funding-Historie: {len(funding)} Symbole mit Daten")
    # Gemeinsames Tagesraster: alle Funding-Tage, die bei >=1 Symbol auch einen Preis haben.
    # (Die Pro-Symbol-Validität & der >=2k-Querschnitt werden in backtest() je Tag geprüft.)
    all_days = set()
    for fd in funding.values():
        all_days |= set(fd.keys())
    days = sorted(d for d in all_days if any(d in closes.get(s, {}) for s in funding))
    if len(days) < 30:
        print(f"Zu wenig gemeinsame Tage ({len(days)})."); return
    span0 = datetime.datetime.utcfromtimestamp(days[0] / 1000).date()
    span1 = datetime.datetime.utcfromtimestamp(days[-1] / 1000).date()
    print(f"Backtest-Tage (Funding+Preis): {len(days)}  ({span0} -> {span1})")

    cost = TAKER_BPS + SLIP_BPS
    # Train/Test-Split (anchored): erste 60% Train (Param-Wahl), letzte 40% OOS-Test
    split = int(len(days) * 0.6)
    train_days, test_days = days[:split], days[split - 1:]   # 1 Tag Überlappung für Lookback-Kontext
    print(f"\nTrain: {len(train_days)}d  |  OOS-Test: {len(test_days)}d  |  Kosten {cost:.0f}bps/Seite\n")

    grid = [(lb, k) for lb in (3, 7, 14, 30) for k in (3, 5, 8)]
    print("=== TRAIN (Param-Selektion nach combined Sharpe) ===")
    print(f"{'lookback':>8}{'k':>4}{'n':>5}{'comb_Sh':>9}{'fund_Sh':>9}{'price_Sh':>9}")
    best = None
    for lb, k in grid:
        r = backtest(closes, funding, train_days, lb, k, cost)
        if r["n"] < 10:
            continue
        cs, fs, ps = _sharpe(r["combined"]), _sharpe(r["fonly"]), _sharpe(r["ponly"])
        print(f"{lb:>8}{k:>4}{r['n']:>5}{cs:>9.2f}{fs:>9.2f}{ps:>9.2f}")
        if best is None or cs > best[0]:
            best = (cs, lb, k)
    if not best:
        print("Zu wenig Daten."); return
    _, lb, k = best
    print(f"\nBester Train-Kandidat: lookback={lb}, k={k} (combined Sharpe {best[0]:.2f})")

    print("\n=== OOS-TEST (eingefrorene Params) ===")
    r = backtest(closes, funding, test_days, lb, k, cost)
    cs, fs, ps = _sharpe(r["combined"]), _sharpe(r["fonly"]), _sharpe(r["ponly"])
    print(f"  n_days={r['n']}")
    print(f"  Funding-ONLY Sharpe (NAIV, ignoriert Preis-Beine): {fs:>7.2f}   <- die Fata-Morgana-Zahl")
    print(f"  Preis-Beine-ONLY Sharpe:                           {ps:>7.2f}")
    print(f"  KOMBINIERT + Kosten Sharpe (EHRLICH):              {cs:>7.2f}   <- die einzige zählende Zahl")
    print(f"  PSR(combined): {_psr(r['combined']):.3f}   MaxDD(combined): {_maxdd(r['combined']):.1f}%   beta_BTC: {r['beta_btc']:+.3f}")
    # Härtungs-Schwelle: gehärtete Sharpe = combined - (haircut 0.5 + deflation ~0.78 bei N_eval=5)
    deflation_5 = 0.2 * math.sqrt(2 * math.log(5))
    threshold = 0.5 + deflation_5
    print(f"\n  Qualifikations-Schwelle (haircut 0.5 + Deflation {deflation_5:.2f} @ N_eval=5) = {threshold:.2f}")
    verdict = "QUALIFIZIERT" if cs > threshold else "qualifiziert NICHT"
    print(f"  Gehärtete Sharpe = {cs:.2f} - {threshold:.2f} = {cs - threshold:+.2f}  =>  {verdict}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\n[{time.time()-t0:.1f}s]")
