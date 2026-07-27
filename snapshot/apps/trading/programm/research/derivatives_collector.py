"""derivatives_collector.py — (B) Forward-Daten-Track für Derivate-Signale (OI/Funding/Sentiment).

Die wertvollsten Derivate-Daten (Open Interest, Liquidations, Funding-Langhistorie) sind bei Bitget
NICHT historisch via ccxt abrufbar (geprüft: fetchOpenInterestHistory=False, Funding nur ~30 T,
fetchLiquidations=False). ⇒ Der EINZIGE ehrliche Weg zum dokumentierten Derivate-Edge (Funding/OI-Extreme
= Mean-Reversion) ist, sie **forward zu sammeln**, bis genug Historie für einen anchored-WF-Backtest da ist.

Dieses Skript zieht EINEN Tages-Snapshot (read-only, public ccxt + alternative.me) und hängt ihn an
`data/derivatives_track.jsonl` an. **Täglich laufen lassen** (Cron/geplante Aufgabe). Nach ~60–90 Tagen
ist der Track backtestbar (Funding/OI-Extreme + Dispersion als cross-sectional/timing-Signal).

Read-only / 0 Echtgeld / KEIN Live-Eingriff (schreibt nur in die eigene Track-Datei, nicht stats.sqlite).
"""
from __future__ import annotations
import os, sys, json, time, statistics, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # programm/
from backend.app import mn_base  # noqa: E402

TRACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "derivatives_track.jsonl")


def _fng_now():
    try:
        d = json.loads(urllib.request.urlopen("https://api.alternative.me/fng/?limit=1", timeout=15).read())
        return int(d["data"][0]["value"])
    except Exception:
        return None


def collect() -> dict:
    import ccxt
    cl = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    # Universum = die csm-Symbole (konsistent mit dem Rest der Research)
    try:
        universe = json.loads(mn_base.meta_get("universe") or "[]")
    except Exception:
        universe = []
    universe = [s for s in universe if ":USDT" in s][:50] or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    # Preise batch-weise vorab ziehen: bitget fetch_funding_rate liefert KEINEN markPrice/indexPrice
    # (verifiziert 20.06.) -> ohne diese Zeile bleibt price=None und der Track ist später NICHT gegen
    # Forward-Returns backtestbar (= der ganze Sinn des Tracks). 1 Batch-Call statt N Einzel-Calls.
    tickers = {}
    try:
        tickers = cl.fetch_tickers(universe)
    except Exception:
        tickers = {}
    per = {}
    for sym in universe:
        rec = {}
        try:
            oi = cl.fetch_open_interest(sym)
            rec["oi"] = oi.get("openInterestAmount") or oi.get("openInterestValue")
            rec["oi_value"] = oi.get("openInterestValue")     # USD-Wert, falls vorhanden
            rec["oi_amount"] = oi.get("openInterestAmount")   # Kontrakt-Menge, falls vorhanden
        except Exception:
            pass
        try:
            fr = cl.fetch_funding_rate(sym)
            rec["funding"] = fr.get("fundingRate")
        except Exception:
            pass
        # Preis: bevorzugt Batch-Ticker (last/close), Einzel-Fallback, sonst markPrice der OI-Antwort.
        t = tickers.get(sym) or {}
        px = t.get("last") or t.get("close")
        if px is None:
            try:
                tt = cl.fetch_ticker(sym)
                px = tt.get("last") or tt.get("close")
            except Exception:
                px = None
        if px is not None:
            rec["price"] = px
        if rec:
            per[sym] = rec
    fundings = [r["funding"] for r in per.values() if r.get("funding") is not None]
    now = int(time.time() * 1000)
    snap = {
        "ts": now,
        "date": datetime.datetime.fromtimestamp(now / 1000, datetime.timezone.utc).strftime("%Y-%m-%d"),
        "fng": _fng_now(),
        "n_symbols": len(per),
        "n_priced": sum(1 for r in per.values() if r.get("price") is not None),
        "funding_mean": round(statistics.mean(fundings), 8) if fundings else None,
        "funding_dispersion": round(statistics.pstdev(fundings), 8) if len(fundings) > 1 else None,
        "funding_max": round(max(fundings), 8) if fundings else None,
        "funding_min": round(min(fundings), 8) if fundings else None,
        "oi_total": round(sum(r["oi"] for r in per.values() if r.get("oi")), 2),
        "per_symbol": per,   # für cross-sectional Funding/OI-Ranking später
    }
    return snap


def _setup_output():
    """Eine geplante Aufgabe hat KEINE Konsole -> ein print() auf den toten stdout-Handle
    erzeugt beim Flush `0xC000013A` (Lauf meldet faelschlich „failed", schreibt evtl. nicht).
    Loesung: alle Ausgaben in `data/derivatives_track.log` lenken und nur bei interaktivem
    Lauf zusaetzlich auf die Konsole (best-effort, jeder Schritt crash-sicher gekapselt)."""
    log_path = os.path.join(os.path.dirname(TRACK), "derivatives_track.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logf = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:
        return
    console = None
    try:
        if sys.stdout is not None and sys.stdout.isatty():
            console = sys.stdout
    except Exception:
        console = None

    class _Tee:
        def write(self, s):
            try:
                logf.write(s)
            except Exception:
                pass
            if console is not None:
                try:
                    console.write(s)
                except Exception:
                    pass

        def flush(self):
            for f in (logf, console):
                if f is not None:
                    try:
                        f.flush()
                    except Exception:
                        pass

    sys.stdout = sys.stderr = _Tee()
    print("--- run " + datetime.datetime.now(datetime.timezone.utc).isoformat() + " ---")


def main():
    _setup_output()
    snap = collect()
    os.makedirs(os.path.dirname(TRACK), exist_ok=True)
    # Idempotent je Tag: einen evtl. schon vorhandenen Eintrag desselben Datums ersetzen (letzter gewinnt),
    # damit Task-Lauf + manueller Lauf am selben Tag KEINE Duplikat-Zeile erzeugen.
    existing = []
    if os.path.exists(TRACK):
        with open(TRACK, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    if json.loads(ln).get("date") != snap["date"]:
                        existing.append(ln)
                except Exception:
                    existing.append(ln)
    existing.append(json.dumps(snap))
    with open(TRACK, "w", encoding="utf-8") as fh:
        fh.write("\n".join(existing) + "\n")
    n_lines = len(existing)
    print(f"Snapshot {snap['date']} angehängt -> {TRACK}")
    print(f"  F&G={snap['fng']} | Symbole={snap['n_symbols']} (mit Preis: {snap['n_priced']}) | "
          f"funding_mean={snap['funding_mean']} disp={snap['funding_dispersion']} | OI_total={snap['oi_total']}")
    print(f"  Track jetzt {n_lines} Tag(e). Backtestbar ab ~60–90 Tagen (Funding/OI-Extreme als Signal).")
    print("  → TÄGLICH laufen lassen (geplante Aufgabe): "
          "programm/.venv/Scripts/python.exe research/derivatives_collector.py")


if __name__ == "__main__":
    main()
