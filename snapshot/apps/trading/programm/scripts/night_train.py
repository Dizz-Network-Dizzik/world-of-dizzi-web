"""night_train.py — autonomer Trainings-Treiber (KI-Nachtlauf).

Fährt sequenziell die anchored Lern-Schleifen über alle parametrisierbaren Strategien
(optimize ODER evolve) und protokolliert je Lauf das ehrliche Ergebnis (selection_bias,
winner, oos_validated) als JSONL nach ``data/training_log_<date>.jsonl``. Proposal-only:
schreibt NUR in strategy/optimizations (Vorschläge) — wendet nichts auf Live-Bots an,
fasst keine Trade-DBs an. Backtest-Lock im Backend serialisiert ohnehin.

Aufruf:
    python scripts/night_train.py optimize   # anchored optimize je Strategie (days=120, windows=3)
    python scripts/night_train.py evolve      # anchored evolve je Strategie (days=180, windows=3, gen=2)
    python scripts/night_train.py validate    # Walk-Forward-Validierung je Strategie (groundet Master/Gate)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8137"
# Reihenfolge: schnellere zuerst, der langsame 1m-Scalper FuturesMacdRsiScalp ZULETZT (sein
# 1m×14-Pairs-Backtest kann hängen/timeouten -> so sind alle anderen sicher fertig, bevor er dran ist).
STRATS = ["MeanReversionRsi", "TrendFollowEma", "MomentumMacd", "FuturesBreakoutVol",
          "FuturesBbandsBounce", "GridRange", "DcaDip", "SessionOpenBreakout", "MasterMeta",
          "FuturesMacdRsiScalp"]

LOG = Path(__file__).resolve().parents[1] / "data" / f"training_log_{datetime.now(timezone.utc):%Y%m%d}.jsonl"


def _post(path: str, timeout: float = 2700.0) -> dict:
    req = urllib.request.Request(BASE + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _already_done(mode: str) -> set:
    """Resume: Strategien, die für diesen Modus heute schon FEHLERFREI geloggt sind (überspringen)."""
    done = set()
    if not LOG.exists():
        return done
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("mode") == mode and e.get("strategy") and not e.get("error"):
            done.add(e["strategy"])
    return done


def _log(entry: dict) -> None:
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['ts']}] {entry.get('mode')} {entry.get('strategy')}: "
          f"oos_validated={entry.get('oos_validated')} winner_profit={entry.get('winner_profit_pct')} "
          f"confident={entry.get('confident')} err={entry.get('error')}", flush=True)


def run(mode: str) -> None:
    if mode == "optimize":
        path_tpl = "/api/meta/optimize/{t}/run?days=120&windows=3"
    elif mode == "evolve":
        path_tpl = "/api/meta/evolve/{t}/run?days=180&windows=3&generations=2&embargo_days=3"
    elif mode == "validate":
        path_tpl = "/api/strategies/{t}/validate?days=120&windows=3&embargo=1"
    else:
        print("usage: night_train.py [optimize|evolve|validate]"); sys.exit(1)

    done = _already_done(mode)
    todo = [t for t in STRATS if t not in done]
    _log({"mode": mode, "event": "batch_start", "todo": todo, "skipped_done": sorted(done)})
    for t in todo:
        t0 = time.time()
        try:
            r = _post(path_tpl.format(t=t))
            secs = round(time.time() - t0, 1)
            if mode == "validate":
                m = r.get("metrics") or {}
                _log({"mode": mode, "strategy": t, "secs": secs,
                      "validated": bool(r.get("validated")), "profit_factor": m.get("profit_factor"),
                      "profit_total_pct": m.get("profit_total_pct"), "trades": m.get("total_trades"),
                      "passed_windows": r.get("passed_windows"), "reason": r.get("reason"),
                      "error": r.get("error")})
            else:
                w = r.get("winner") or {}
                bias = r.get("selection_bias") or {}
                _log({"mode": mode, "strategy": t, "secs": secs,
                      "oos_validated": bool(w.get("oos_validated")),
                      "winner_profit_pct": w.get("profit_total_pct"),
                      "winner_dd_pct": w.get("max_drawdown_pct"),
                      "winner_trades": w.get("total_trades"),
                      "winner_params": w.get("params"),
                      "confident": bias.get("confident"),
                      "valid_trials": bias.get("valid_trials"),
                      "train_window": bias.get("train_window"), "test_window": bias.get("test_window")})
        except Exception as exc:
            _log({"mode": mode, "strategy": t, "secs": round(time.time() - t0, 1),
                  "error": f"{type(exc).__name__}: {exc}"})
    _log({"mode": mode, "event": "batch_done"})


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "optimize")
