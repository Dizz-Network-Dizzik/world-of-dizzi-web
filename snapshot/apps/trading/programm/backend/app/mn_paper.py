"""mn_paper.py — persistente **MN-Paper-Bots** über den markt-neutralen Sim-Engines (CSM/Pairs/StatArb/MM).

Die markt-neutralen Engines (``csm`` / ``pairs`` / ``statarb`` / ``marketmaking``) sind KEINE
Freqtrade-Bots, sondern eigenständige Simulationen mit je EINER globalen Config. Dieses Modul macht
sie als **benannte, persistente Paper-Bots** anlegbar: jeder Paper-Bot trägt seine EIGENE Config
(unabhängig von der globalen Engine-Config) und seine EIGENE, ehrlich simulierte PnL/Winrate.

**Ehrlich (Gesetz 2):** Ein Paper-Bot ist eine *Simulation auf echten Preisen* — 0 echtes Risiko,
keine Orders, kein Freqtrade-Prozess. PnL/Winrate = die Sim-Kennzahlen der zugrundeliegenden Engine
mit der Bot-Config über die verfügbare Historie. Daher das ``mode: "demo-simulation"``-Label überall.

Abgrenzung „Funding": Funding-Carry wurde als *eigenständiger* Edge OOS **refutiert** (siehe
``programm/research/`` + [[trading-bot-eins-stand]]); Funding lebt nur als Kosten-Proxy IN der CSM-Sim
weiter. Es gibt deshalb bewusst KEINEN „funding"-Paper-Bot — das wäre nicht ehrlich.

Persistenz: ``data/mn_paper_bots.json`` (atomar via ``jsonstore``, wie die Freqtrade-Registry). Der
PnL-Verlauf je Bot (Kalender-Track) liegt idempotent-pro-Tag IM Datensatz (gedeckelt), damit alles in
einer Quelle bleibt und ohne neue DB-Tabelle testbar ist. Rein-Python, dependency-leicht, testbar.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import audit, cache, csm, jsonstore, marketmaking, mn_base, pairs
from .config import DATA_DIR

PAPER_FILE = DATA_DIR / "mn_paper_bots.json"

# Track-Deckel (Kalender-PnL-Punkte je Bot) — reicht für >1 Jahr tägliche Snapshots.
_TRACK_CAP = 400
# evaluate() läuft eine volle Sim → kurzer TTL-Memo gegen UI-/Listen-Bursts (config-abhängiger Key).
_EVAL_TTL = 60.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Engine-Katalog: Anzeige + Default-Config + die per-Bot tunebaren Schlüssel.
# DEFAULTS werden aus den Engine-Modulen gezogen (eine Quelle der Wahrheit).
# ---------------------------------------------------------------------------
ENGINES: dict[str, dict] = {
    "csm": {
        "label": "Cross-Sectional Momentum",
        "defaults": csm.DEFAULTS,
        "tunable": ["lookback", "hold", "quantile", "fee", "universe_top", "min_history", "signal_lag",
                    "capital", "vol_scaled"],
        "explainer": "Long Top-Quantil / short Bottom-Quantil nach Momentum, täglich rebalanciert "
                     "(dollar-neutral). Belegter Netto-Sharpe ~1,2–1,3.",
    },
    "pairs": {
        "label": "Pairs-Trading (Spread-Reversion)",
        "defaults": pairs.DEFAULTS,
        "tunable": ["lookback", "entry_z", "exit_z", "n_pairs", "min_corr", "coint_filter", "fee",
                    "min_history", "capital", "formation_days"],
        "explainer": "Handelt den Spread korrelierter Paare (Z-Score-Mean-Reversion, kausale "
                     "Paar-Auswahl aus der Formation-Phase). Dollar-neutral je Paar.",
    },
    "statarb": {
        "label": "Statistical Arbitrage (Korb-Reversion)",
        "defaults": pairs.STATARB_DEFAULTS,
        "tunable": ["lookback", "quantile", "slippage_bps", "fee", "min_history", "capital"],
        "explainer": "Jedes Symbol vs. Korb-Mittel — long Nachzügler / short Ausreißer "
                     "(Mean-Reversion, täglich rebalanciert).",
    },
    "mm": {
        "label": "Market-Making (Avellaneda-Stoikov)",
        "defaults": marketmaking.DEFAULTS,
        "tunable": ["gamma", "k", "A", "order_size", "inventory_limit", "steps", "episodes",
                    "maker_rebate_bps", "adverse_frac", "vol_recal", "symbol", "min_history", "capital"],
        "explainer": "Beidseitige Quotes um den inventar-skewten Reservationspreis, Fills als "
                     "Poisson-Prozess. Modell-Simulation auf kalibrierter Vola.",
    },
}

# Statistik-Schlüssel, die jede Engine-Sim liefert (für eine einheitliche Bot-Ansicht).
_STAT_KEYS = ("sharpe", "ann_pct", "total_return_pct", "maxdd_pct", "psr", "days", "n_pairs")


def engines_catalog() -> list[dict]:
    """Die anlegbaren MN-Engines + Default-Config + tunebare Schlüssel (für das Anlege-Formular)."""
    return [{"engine": key, "label": m["label"], "explainer": m["explainer"],
             "tunable": list(m["tunable"]),
             "defaults": {k: m["defaults"][k] for k in m["tunable"]}}
            for key, m in ENGINES.items()]


# ---------------------------------------------------------------------------
# Config-Coercion: nur bekannte Keys, auf den DEFAULTS-Typ gecastet (wie mn_base.config_set).
# ---------------------------------------------------------------------------
def _coerce_config(engine: str, patch: dict | None) -> dict:
    if engine not in ENGINES:
        raise ValueError(f"unbekannte MN-Engine: {engine!r}")
    defaults = ENGINES[engine]["defaults"]
    cfg = {k: defaults[k] for k in ENGINES[engine]["tunable"]}
    for k, v in (patch or {}).items():
        if k in cfg and v is not None:
            try:
                cfg[k] = type(defaults[k])(v)
            except (TypeError, ValueError):
                pass
    return cfg


# ---------------------------------------------------------------------------
# Simulation (reiner Dispatch auf die vorhandenen Engine-simulate-Funktionen).
# Gegeben Preise (bzw. sigma für MM) → das rohe Sim-Ergebnis-Dict der Engine.
# ---------------------------------------------------------------------------
def _simulate(engine: str, cfg: dict, syms, ts, closes, sigma: float | None = None) -> dict:
    if engine == "csm":
        try:
            import json
            funding = json.loads(csm._meta_get("funding_avg") or "{}")
        except Exception:
            funding = {}
        return csm.simulate(syms, ts, closes, cfg["lookback"], cfg["hold"], cfg["quantile"],
                            cfg["fee"], cfg["capital"], funding=funding,
                            vol_scaled=bool(cfg.get("vol_scaled")),
                            signal_lag=int(cfg.get("signal_lag", 0) or 0))
    if engine == "pairs":
        f = pairs._formation_split(len(ts), ts, int(cfg["formation_days"]))
        prs = pairs.select_pairs(syms, {s: closes[s][:f] for s in syms},
                                 cfg["n_pairs"], cfg["min_corr"],
                                 coint_filter=bool(cfg.get("coint_filter")),
                                 coint_adf_max=float(cfg.get("coint_adf_max", -3.34)))
        if not prs:
            return {"ok": False, "error": "keine ausreichend korrelierten Paare (min_corr senken?)"}
        return pairs.simulate(prs, ts[f:], {s: closes[s][f:] for s in syms},
                              cfg["lookback"], cfg["entry_z"], cfg["exit_z"], cfg["fee"], cfg["capital"])
    if engine == "statarb":
        return pairs.simulate_basket(syms, ts, closes, cfg["lookback"], cfg["quantile"],
                                     cfg["fee"], cfg["capital"],
                                     slippage_bps=float(cfg.get("slippage_bps", 0.0)))
    if engine == "mm":
        return marketmaking.simulate(sigma, cfg["gamma"], cfg["k"], cfg["A"], cfg["order_size"],
                                     cfg["inventory_limit"], cfg["steps"], cfg["episodes"],
                                     cfg["maker_rebate_bps"], cfg["capital"], cfg["adverse_frac"], seed=42,
                                     vol_recal=bool(cfg.get("vol_recal")))
    raise ValueError(f"unbekannte MN-Engine: {engine!r}")


def _winrate(equity: list, rets: list | None = None) -> tuple[float, int, int]:
    """Anteil profitabler Perioden (Tage bzw. MM-Sessions). Bevorzugt die exakten ``rets`` (CSM),
    sonst aus der Equity-Kurve abgeleitet (Diffs). Gibt (winrate_pct, gewonnene, gesamt)."""
    if rets is not None:
        series = list(rets)
    else:
        series = []
        prev = None
        for point in equity:
            v = point[1]
            if prev is not None and prev:
                series.append(v / prev - 1.0)
            prev = v
    n = len(series)
    up = sum(1 for r in series if r > 0)
    return (round(100.0 * up / n, 1) if n else 0.0), up, n


def evaluate(engine: str, config_patch: dict | None) -> dict:
    """Ehrliche Sim-Bewertung einer (engine, config) — PnL/Winrate/Equity über die verfügbare Historie.

    Gecacht (kurzer TTL) je (engine, config) gegen Listen-/UI-Bursts. ``mode: demo-simulation``.
    """
    cfg = _coerce_config(engine, config_patch)
    ckey = "mnpaper:" + engine + ":" + ":".join(f"{k}={cfg[k]}" for k in sorted(cfg))
    return cache.ttl_get(ckey, _EVAL_TTL, lambda: _evaluate_uncached(engine, cfg))


def _evaluate_uncached(engine: str, cfg: dict) -> dict:
    meta: dict = {}
    if engine == "mm":
        sigma, used = marketmaking.calib_sigma(cfg["symbol"], cfg["min_history"])
        if sigma <= 0:
            return {"ok": False, "ready": False,
                    "note": "Keine Preis-Daten zur Vola-Kalibrierung. Zuerst POST /api/csm/refresh."}
        sim = _simulate(engine, cfg, None, None, None, sigma=sigma)
        meta = {"calibrated_symbol": used, "sigma_daily_pct": round(sigma * 100, 2)}
    else:
        syms, ts, closes = csm._load_prices(cfg["min_history"])
        if not syms:
            return {"ok": False, "ready": False,
                    "note": "Noch keine Preis-Daten. Zuerst POST /api/csm/refresh (read-only ccxt, ~1 Min)."}
        sim = _simulate(engine, cfg, syms, ts, closes)
        meta = {"data_from": datetime.fromtimestamp(ts[0] / 1000, timezone.utc).strftime("%Y-%m-%d"),
                "data_to": datetime.fromtimestamp(ts[-1] / 1000, timezone.utc).strftime("%Y-%m-%d")}
    if not sim.get("ok"):
        return {"ok": False, "ready": False, "note": sim.get("error", "Simulation fehlgeschlagen")}
    equity = sim.get("equity") or []
    wr, up, n = _winrate(equity, sim.get("rets"))
    cap = float(cfg["capital"])
    total = float(sim.get("total_return_pct", 0.0))
    return {
        "ok": True, "ready": True, "mode": "demo-simulation", "engine": engine,
        "stats": {k: sim.get(k) for k in _STAT_KEYS},
        "winrate_pct": wr, "win_periods": up, "n_periods": n,
        "pnl_pct": total, "pnl_abs": round(cap * total / 100.0, 2), "capital": cap,
        "equity": mn_base.downsample(list(equity), 200), "current": sim.get("current"),
        "last_refresh": csm._meta_get("last_refresh"), **meta,
    }


# ---------------------------------------------------------------------------
# Persistenz (JSON, atomar) + CRUD
# ---------------------------------------------------------------------------
def _load() -> dict[str, dict]:
    return jsonstore.read_json(PAPER_FILE, {})


def _save(data: dict[str, dict]) -> None:
    jsonstore.write_atomic(PAPER_FILE, data)


def _next_tag(data: dict[str, dict]) -> int:
    return max((int(r.get("tag") or 0) for r in data.values()), default=0) + 1


def list_bots() -> list[dict]:
    return list(_load().values())


def get(bot_id: str) -> dict | None:
    return _load().get(bot_id)


def create(name: str, engine: str, config_patch: dict | None = None, note: str = "") -> dict:
    """Legt einen persistenten MN-Paper-Bot an (eigene Config; ehrlich simuliert, kein Freqtrade-Bot)."""
    cfg = _coerce_config(engine, config_patch)   # validiert engine + castet config
    data = _load()
    rec = {
        "id": uuid.uuid4().hex[:8],
        "tag": _next_tag(data),
        "name": name,
        "engine": engine,
        "config": cfg,
        "status": "stopped",          # angelegt = gestoppt; Start beginnt den Kalender-Track
        "started_at": None,
        "note": note or "",
        "track": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    data[rec["id"]] = rec
    _save(data)
    audit.record("mn_paper_created", bot_id=rec["id"], engine=engine, name=name)
    return rec


def update_config(bot_id: str, patch: dict) -> dict | None:
    data = _load()
    rec = data.get(bot_id)
    if rec is None:
        return None
    rec["config"] = _coerce_config(rec["engine"], {**rec.get("config", {}), **(patch or {})})
    rec["updated_at"] = _now()
    _save(data)
    audit.record("mn_paper_config", bot_id=bot_id, keys=list((patch or {}).keys()))
    return rec


def rename(bot_id: str, name: str) -> dict | None:
    data = _load()
    rec = data.get(bot_id)
    if rec is None:
        return None
    rec["name"] = name
    rec["updated_at"] = _now()
    _save(data)
    return rec


def set_status(bot_id: str, status: str) -> dict | None:
    """``running`` | ``stopped``. ``running`` startet/aktiviert den Kalender-PnL-Track."""
    if status not in ("running", "stopped"):
        raise ValueError("status muss 'running' oder 'stopped' sein")
    data = _load()
    rec = data.get(bot_id)
    if rec is None:
        return None
    rec["status"] = status
    if status == "running" and not rec.get("started_at"):
        rec["started_at"] = _now()
    rec["updated_at"] = _now()
    _save(data)
    audit.record("mn_paper_status", bot_id=bot_id, status=status)
    return rec


def delete(bot_id: str) -> bool:
    data = _load()
    if bot_id not in data:
        return False
    name = data[bot_id].get("name")
    del data[bot_id]
    _save(data)
    audit.record("mn_paper_deleted", bot_id=bot_id, name=name)
    return True


# ---------------------------------------------------------------------------
# Kalender-PnL-Track (idempotent pro UTC-Tag, gedeckelt) — die „eigene PnL" über die Zeit.
# ---------------------------------------------------------------------------
def _track_entry(ev: dict) -> dict:
    return {
        "day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ts": _now(),
        "pnl_pct": ev.get("pnl_pct"),
        "pnl_abs": ev.get("pnl_abs"),
        "winrate_pct": ev.get("winrate_pct"),
        "sharpe": (ev.get("stats") or {}).get("sharpe"),
    }


def _append_track(rec: dict, ev: dict) -> None:
    """Hängt den heutigen Snapshot an (ersetzt einen schon vorhandenen desselben Tags). In-place."""
    entry = _track_entry(ev)
    track = [t for t in rec.get("track", []) if t.get("day") != entry["day"]]
    track.append(entry)
    rec["track"] = track[-_TRACK_CAP:]


def state(bot_id: str) -> dict | None:
    """Voller Bot-Zustand für die UI: Stammdaten + frische Sim-Bewertung (+ Track-Snapshot wenn running)."""
    data = _load()
    rec = data.get(bot_id)
    if rec is None:
        return None
    ev = evaluate(rec["engine"], rec.get("config"))
    if ev.get("ok") and rec.get("status") == "running":
        _append_track(rec, ev)          # idempotent pro Tag
        rec["updated_at"] = _now()
        _save(data)
    label = ENGINES.get(rec["engine"], {}).get("label", rec["engine"])
    return {**rec, "engine_label": label, "evaluation": ev}


def summary() -> list[dict]:
    """Leichte Liste aller Paper-Bots mit PnL%/Winrate (für Dashboard/Übersicht). Sim-gecacht."""
    out = []
    for rec in _load().values():
        ev = evaluate(rec["engine"], rec.get("config"))
        out.append({
            "id": rec["id"], "tag": rec.get("tag"), "name": rec["name"],
            "engine": rec["engine"], "engine_label": ENGINES.get(rec["engine"], {}).get("label"),
            "status": rec.get("status", "stopped"),
            "ok": ev.get("ok", False),
            "pnl_pct": ev.get("pnl_pct"), "pnl_abs": ev.get("pnl_abs"),
            "winrate_pct": ev.get("winrate_pct"),
            "sharpe": (ev.get("stats") or {}).get("sharpe"),
            "note_if_not_ready": None if ev.get("ok") else ev.get("note"),
        })
    out.sort(key=lambda r: (r.get("tag") or 0))
    return out


def seed_defaults() -> list[dict]:
    """Idempotenter Komfort: legt je MN-Engine EINEN Paper-Bot mit Default-Config an, falls für die
    Engine noch keiner existiert. Gibt die neu erzeugten Datensätze zurück (leere Liste = nichts getan).
    Das ist die ehrliche Umsetzung von „alle MN-Vorlage-Systeme → je 1 Bot"."""
    have = {r.get("engine") for r in _load().values()}
    created = []
    for engine, meta in ENGINES.items():
        if engine in have:
            continue
        created.append(create(f"{meta['label']} (Demo)", engine, {},
                              note="Auto-Seed (Default-Config) — markt-neutrale Demo-Simulation."))
    return created
