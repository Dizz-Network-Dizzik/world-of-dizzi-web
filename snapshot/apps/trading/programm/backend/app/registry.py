"""Bot-Registry — persistente Verwaltung aller Bots.

Speichert Bots als JSON unter ``data/bots.json`` und erzeugt für jeden Bot
eine passende Freqtrade-Config unter ``engine/user_data/config_<id>.json``
(abgeleitet aus der Vorlage). Damit ist die Grundlage für Multi-Bot (M4)
gelegt: jeder Bot ist isoliert konfigurierbar.
"""

from __future__ import annotations

import functools
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import audit, jsonstore, universe
from .config import DATA_DIR, PROJECT_ROOT
from .models import BotConfig, BotCreate, RiskParams, derive_horizon

BOTS_FILE = DATA_DIR / "bots.json"
ENGINE_USERDIR = PROJECT_ROOT / "engine" / "user_data"

# Serialisiert die mutierenden Read-Modify-Write-Operationen (create/update/delete/...): der
# Autopilot-Hintergrund-Thread und der HTTP-Threadpool dürfen bots.json nicht gleichzeitig ändern
# (sonst „lost update"). RLock = reentrant. Lock-Reihenfolge: runner._state_lock → registry._lock
# (registry ruft nie runner) → kein Deadlock.
_lock = threading.RLock()


def _synchronized(fn):
    """Hält ``_lock`` über die gesamte mutierende Funktion (atomares Read-Modify-Write von bots.json)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


def _load() -> dict[str, dict]:
    return jsonstore.read_json(BOTS_FILE, {})  # resilient: Ziel → .bak → {}


def _save(data: dict[str, dict]) -> None:
    jsonstore.write_atomic(BOTS_FILE, data)    # atomar (tmp+os.replace) + .bak


def list_bots() -> list[BotConfig]:
    return [BotConfig(**raw) for raw in _load().values()]


def get_bot(bot_id: str) -> BotConfig | None:
    raw = _load().get(bot_id)
    return BotConfig(**raw) if raw else None


# Reaktivität -> Freqtrade internals.process_throttle_secs (niedriger = reaktiver).
REACTIVITY_THROTTLE = {"hoch": 1, "standard": 5, "ruhig": 15}

# Hänger-Schutz: expliziter ccxt-Call-Timeout (ms). Ein blockierender Exchange-Call (z. B. nach 429/
# DDoS-Backoff) würde den freqtrade-Worker-Loop sonst unbegrenzt einfrieren ("Bot tot, aber Prozess läuft").
# 30 s = 3× über dem ccxt-Default (10 s, mit dem die Flotte heute läuft) ⇒ keine Fehl-Timeouts bei gesunden
# Calls, aber ein echter Hänger bricht nach ~30 s (× freqtrade-Retries) ab statt nach Stunden.
EXCHANGE_TIMEOUT_MS = 30000


def _derive_reactivity(timeframe: str) -> str:
    """Leitet eine sinnvolle Reaktivität aus dem Timeframe ab — Scalping (niedrige TF)
    bekommt eine hohe Reaktivität, damit Ein-/Ausstiege nicht durch zu langes
    Loop-Intervall verschlechtert werden."""
    tf = (timeframe or "").lower().replace("min", "m")
    if tf in ("1m", "3m"):
        return "hoch"
    if tf in ("5m", "15m"):
        return "standard"
    return "ruhig"  # 30m/1h+ — kein schnelles Loop noetig


def _next_tag(data: dict[str, dict]) -> int:
    """Naechster freier Nummern-Tag (#NN) — max bestehender + 1."""
    return max((int(r.get("tag") or 0) for r in data.values()), default=0) + 1


@_synchronized
def assign_missing_tags() -> int:
    """Vergibt einen stabilen Nummern-Tag an Bots ohne tag (>0). Bevorzugt eine im Namen fuehrende
    Zahl (z. B. '03 ...'), sonst die naechste freie. Idempotent (schreibt nur bei Bedarf)."""
    data = _load()
    used = {int(r.get("tag") or 0) for r in data.values() if int(r.get("tag") or 0) > 0}
    items = sorted(data.items(), key=lambda kv: kv[1].get("created_at", ""))
    changed = 0
    for _bid, raw in items:  # 1) fuehrende Namens-Zahl (erwartbar/stabil)
        if int(raw.get("tag") or 0) > 0:
            continue
        lead = (raw.get("name") or "").strip().split(" ")[0]
        n = int(lead) if lead.isdigit() else 0
        if n and n not in used:
            raw["tag"] = n; used.add(n); changed += 1
    nxt = 1
    for _bid, raw in items:  # 2) Rest: naechste freie Nummer
        if int(raw.get("tag") or 0) > 0:
            continue
        while nxt in used:
            nxt += 1
        raw["tag"] = nxt; used.add(nxt); changed += 1
    if changed:
        _save(data)
    return changed


@_synchronized
def assign_missing_horizons() -> int:
    """Trägt den Zeit-Horizont (scalping/intraday/swing) für alle Bots nach, die noch keinen gespeichert
    haben — abgeleitet aus dem Timeframe. Idempotent (schreibt nur bei Bedarf)."""
    data = _load()
    changed = 0
    for raw in data.values():
        if not raw.get("horizon"):
            raw["horizon"] = derive_horizon(raw.get("timeframe", ""))
            changed += 1
    if changed:
        _save(data)
    return changed


def _pairs_to_futures(pairs: list[str]) -> list[str]:
    """Spot-Pairs ins Futures-Format bringen: 'BTC/USDT' → 'BTC/USDT:USDT' (idempotent)."""
    out = []
    for p in pairs or []:
        if "/" in p and ":" not in p:
            quote = p.split("/", 1)[1]
            out.append(f"{p}:{quote}")
        else:
            out.append(p)
    return out


@_synchronized
def convert_spot_to_futures() -> list[str]:
    """Einmal-Migration (Horizont-Umbau 2026-06-10): konvertiert alle verbliebenen Spot-Bots auf Futures
    (trading_mode=futures, Pairs ins :USDT-Format, Config neu). Idempotent — nach dem Lauf gibt es keine
    Spot-Bots mehr, also tut ein erneuter Aufruf nichts. Die Lern-DB bleibt unangetastet. Gibt die Liste der
    konvertierten Bot-IDs zurück (Aufrufer startet sie neu, damit die Engine die Futures-Config liest)."""
    data = _load()
    converted: list[str] = []
    for bid, raw in data.items():
        if raw.get("trading_mode") == "futures":
            continue
        raw["trading_mode"] = "futures"
        raw["pairs"] = _pairs_to_futures(raw.get("pairs") or [])
        raw["updated_at"] = datetime.now(timezone.utc).isoformat()
        converted.append(bid)
    if converted:
        _save(data)
        for bid in converted:
            try:
                _write_engine_config(BotConfig(**data[bid]))
            except Exception:
                pass
        audit.record("spot_to_futures_migrated", count=len(converted), bot_ids=converted)
    return converted


def _diversify_raw(raw: dict) -> bool:
    """Setzt einen Bot-Rohdatensatz auf den gestreuten, dynamischen Volumen-Modus (in-place).
    Gibt True zurück, wenn sich etwas geändert hat. Idempotent."""
    horizon = raw.get("horizon") or derive_horizon(raw.get("timeframe", ""))
    cands = universe.candidates_for(horizon, raw.get("trading_mode", "futures"))
    if raw.get("pair_mode") == "dynamic" and (raw.get("pairs") or []) == cands:
        return False
    raw["pair_mode"] = "dynamic"
    raw["pairs"] = cands
    raw["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


@_synchronized
def diversify_bot(bot_id: str) -> BotConfig | None:
    """Stellt EINEN Bot auf das gestreute, dynamische Volumen-Universum um (Config neu geschrieben).
    Aufrufer startet den Bot neu, damit die Engine die neue Pairlist liest. Idempotent."""
    data = _load()
    if bot_id not in data:
        return None
    if _diversify_raw(data[bot_id]):
        _save(data)
        audit.record("bot_diversified", bot_id=bot_id, pairs=data[bot_id].get("pairs"))
    bot = BotConfig(**data[bot_id])
    _write_engine_config(bot)
    return bot


@_synchronized
def diversify_fleet() -> list[str]:
    """„Pairs streuen" für die GANZE Flotte: jeden Bot auf das gestreute, dynamische Volumen-Universum
    seines Horizonts umstellen (inkl. MasterMeta). Idempotent — gibt die Liste geänderter Bot-IDs zurück
    (Aufrufer startet sie neu). Die Lern-DB bleibt unangetastet."""
    data = _load()
    changed: list[str] = []
    for bid, raw in data.items():
        if _diversify_raw(raw):
            changed.append(bid)
    if changed:
        _save(data)
        for bid in changed:
            try:
                _write_engine_config(BotConfig(**data[bid]))
            except Exception:
                pass
        audit.record("fleet_diversified", count=len(changed), bot_ids=changed)
    return changed


@_synchronized
def create_bot(payload: BotCreate) -> BotConfig:
    data = _load()
    reactivity = payload.reactivity or _derive_reactivity(payload.timeframe)
    horizon = payload.horizon or derive_horizon(payload.timeframe)
    # „Pairs streuen": ohne explizit vorgegebene Pairs wird der Bot per Default gestreut (dynamisches
    # Volumen-Universum für seinen Horizont). Werden Pairs explizit gesetzt, bleibt er statisch (genau die).
    if payload.pairs:
        pair_mode = payload.pair_mode or "static"
        pairs = payload.pairs
    else:
        pair_mode = payload.pair_mode or "dynamic"
        pairs = (universe.candidates_for(horizon, payload.trading_mode) if pair_mode == "dynamic"
                 else BotConfig.model_fields["pairs"].default_factory())
    bot = BotConfig(
        name=payload.name,
        tag=payload.tag or _next_tag(data),
        strategy=payload.strategy,
        pairs=pairs,
        pair_mode=pair_mode,
        timeframe=payload.timeframe,
        timeframes=payload.timeframes or [],
        stake_amount=payload.stake_amount,
        max_open_trades=payload.max_open_trades,
        dry_run=payload.dry_run,
        dry_run_wallet=payload.dry_run_wallet,
        trading_mode=payload.trading_mode,
        horizon=horizon,
        reactivity=reactivity,
        leverage=getattr(payload, "leverage", None),
        risk=payload.risk or RiskParams(),
    )
    data[bot.id] = bot.model_dump()
    _save(data)
    _write_engine_config(bot)
    audit.record("bot_created", bot_id=bot.id, name=bot.name, strategy=bot.strategy, dry_run=bot.dry_run)
    return bot


# Singleton-„MasterMeta"-Bot: feste, menschenlesbare ID (statt Hash) — der übergeordnete,
# sich selbst per Lern-Loop verbessernde Regime-Switching-Bot. Bekommt im UI einen Sonderplatz.
MASTER_BOT_ID = "mastermeta"


# Aggressiv-Profil des MasterMeta-Bots (Nutzer-Wunsch): Futures, Hebel-Basis >=5 (dynamisch nach
# HMM-Konfidenz bis max in der leverage()-Callback der Strategie hochgeschraubt), Long+Short.
MASTER_FUTURES_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
MASTER_OPT_DEFAULTS = {"base_leverage": 5, "max_leverage": 10}


@_synchronized
def ensure_master_bot() -> BotConfig:
    """Stellt den dedizierten, **aggressiven** MasterMeta-Singleton-Bot sicher (idempotent + konvergent).

    Fixe ID ``mastermeta``, Name „MasterMeta", Strategie ``MasterMeta`` (Regime-Switching, live ans
    Gaussian-HMM gekoppelt). **Aggressiv-Profil:** Futures, Hebel-Basis 5 (dynamisch hoch nach
    HMM-Konfidenz), Long+Short. Existiert der Bot bereits, wird er auf dieses Profil **migriert**
    (Modus/Pairs/Hebel-Defaults), falls noch nicht gesetzt — so greift die Umstellung beim nächsten
    Startup automatisch. Der Autopilot (``autopilot.py``) verbessert ihn laufend weiter.
    """
    data = _load()
    if MASTER_BOT_ID in data:
        raw = data[MASTER_BOT_ID]
        changed = False
        if raw.get("trading_mode") != "futures":
            raw["trading_mode"] = "futures"; raw["pairs"] = list(MASTER_FUTURES_PAIRS); changed = True
        op = dict(raw.get("opt_params") or {})
        for k, v in MASTER_OPT_DEFAULTS.items():
            op.setdefault(k, v)
        if op != (raw.get("opt_params") or {}):
            raw["opt_params"] = op; changed = True
        if changed:
            data[MASTER_BOT_ID] = raw
            _save(data)
            bot = BotConfig(**raw)
            _write_engine_config(bot)
            audit.record("master_bot_migrated", bot_id=MASTER_BOT_ID, trading_mode="futures")
            return bot
        bot = BotConfig(**raw)
        _write_engine_config(bot)   # idempotent: Config stets auf aktuellen Standard (z. B. Notfall-Stop)
        return bot
    bot = BotConfig(
        id=MASTER_BOT_ID,
        tag=_next_tag(data),
        name="MasterMeta",
        strategy="MasterMeta",
        pairs=list(MASTER_FUTURES_PAIRS),
        timeframe="15m",
        trading_mode="futures",
        dry_run=True,
        reactivity="standard",
        opt_params=dict(MASTER_OPT_DEFAULTS),
        risk=RiskParams(),
    )
    data[bot.id] = bot.model_dump()
    _save(data)
    _write_engine_config(bot)
    audit.record("master_bot_ensured", bot_id=bot.id, strategy=bot.strategy, trading_mode="futures")
    return bot


@_synchronized
def delete_bot(bot_id: str) -> bool:
    """Entfernt NUR die Bot-Registrierung + die (regenerierbare) Engine-Config.

    GARANTIE: Die **Lern-Datenbank bleibt unangetastet** — weder die ``stats.sqlite`` (Tages-Snapshots,
    Validierungen, Optimierungen, Upgrade-Changelog) noch die historische Trade-DB ``tradesv3_<id>.sqlite``
    werden gelöscht. So gehen die akkumulierten KI-Learnings nicht verloren, wenn ein Bot entfernt wird
    (auch nicht beim Auto-Cull). Die Config ist aus Vorlage+Registry jederzeit reproduzierbar.
    """
    data = _load()
    if bot_id not in data:
        return False
    name = data[bot_id].get("name")
    del data[bot_id]
    _save(data)
    cfg = ENGINE_USERDIR / f"config_{bot_id}.json"
    if cfg.exists():
        cfg.unlink()   # nur die generierte Config; KEINE stats/Trade-DB anfassen
    audit.record("bot_deleted", bot_id=bot_id, name=name)
    return True


@_synchronized
def update_bot(bot_id: str, changes: dict) -> BotConfig | None:
    """Aktualisiert Felder eines Bots (inkl. verschachteltem ``risk``).

    Erlaubt sind die Top-Level-Felder von BotConfig sowie ``risk`` als Teil-Dict.
    Nicht erlaubte/unbekannte Schlüssel werden ignoriert.
    """
    data = _load()
    if bot_id not in data:
        return None
    raw = data[bot_id]
    allowed = {"name", "strategy", "pairs", "pair_mode", "timeframe", "timeframes", "stake_amount",
               "max_open_trades", "dry_run", "dry_run_wallet", "trading_mode", "horizon",
               "subaccount", "opt_params", "opt_version", "auto_upgrade", "reactivity", "manual_params", "leverage"}
    for key, value in changes.items():
        if key == "risk" and isinstance(value, dict):
            raw.setdefault("risk", {}).update(value)
        elif key in allowed:
            raw[key] = value
    raw["updated_at"] = datetime.now(timezone.utc).isoformat()
    bot = BotConfig(**raw)              # validiert die Änderungen
    data[bot_id] = bot.model_dump()
    _save(data)
    _write_engine_config(bot)          # Engine-Config konsistent halten
    audit.record("bot_updated", bot_id=bot_id, changes=list(changes.keys()))
    return bot


@_synchronized
def update_status(bot_id: str, status: str) -> BotConfig | None:
    data = _load()
    if bot_id not in data:
        return None
    data[bot_id]["status"] = status
    data[bot_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    audit.record("bot_status_changed", bot_id=bot_id, status=status)
    return BotConfig(**data[bot_id])


def _write_engine_config(bot: BotConfig) -> Path:
    """Erzeugt eine Freqtrade-Config für diesen Bot aus der Dry-Run-Vorlage."""
    template_path = ENGINE_USERDIR / "config_bot1_dryrun.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    template["max_open_trades"] = bot.max_open_trades
    template["stake_amount"] = bot.stake_amount
    template["dry_run"] = bot.dry_run
    template["dry_run_wallet"] = bot.dry_run_wallet
    template["timeframe"] = bot.timeframe
    template["trading_mode"] = bot.trading_mode
    # Futures braucht isolierte Margin; Spot leer.
    template["margin_mode"] = "isolated" if bot.trading_mode == "futures" else ""
    # Reaktivität: Loop-Intervall (Scalping reaktiver).
    template.setdefault("internals", {})["process_throttle_secs"] = \
        REACTIVITY_THROTTLE.get(getattr(bot, "reactivity", "standard"), 5)
    # NOTFALL-ABSICHERUNG: harter Stop-Loss als ECHTE Order an der Börse (stoploss_on_exchange).
    # Er liegt am Strategie-Stoploss — also ein Stück UNTER den normalen (Gewinn-)Ausstiegen (ROI/Trailing/
    # Signal) — und bleibt bestehen, selbst wenn der Bot/das System ausfällt (Stromausfall, Absturz). So kann
    # ein offener Trade nicht endlos weiterlaufen. Im Dry-Run simuliert Freqtrade dies; ab Echtgeld real wirksam.
    template["order_types"] = {
        "entry": "limit", "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_limit_ratio": 0.99,
    }
    template["exchange"]["pair_whitelist"] = bot.pairs
    # 429-Schutz (Bitget): ~51 unabhängige Bot-Prozesse teilen EINE IP — jeder hat seinen eigenen,
    # unkoordinierten Rate-Limiter. Ohne Drossel sprengt das Aggregat (v. a. am Candle-Schluss, wenn alle
    # gleichzeitig OHLCV ziehen) Bitgets Limit → „Too Many Requests" + Retry-Kaskaden + Datenlücken-Risiko.
    # Jeder Bot drosselt sich daher selbst (enableRateLimit + großzügiges rateLimit ms): glättet die Bursts,
    # senkt das Aggregat deutlich. Freqtrade/ccxt-dokumentierte Abhilfe. (Dry-Run: ms ≪ Candle-Timeframe.)
    # HÄNGER-SCHUTZ (15.06.): expliziter `timeout` (ms) je Exchange-Call. Ohne ihn kann ein blockierender
    # Call (z. B. nach 429/DDoS-Backoff) den Worker-Loop EWIG einfrieren → Bot „tot, aber Prozess läuft"
    # (Heartbeat versiegt). Mit Timeout bricht ccxt nach EXCHANGE_TIMEOUT_MS ab → freqtrade loggt + macht
    # weiter (Heartbeat lebt). 3× über ccxt-Default (10 s) ⇒ keine Fehl-Timeouts bei gesunden Calls.
    template["exchange"]["ccxt_config"] = {"enableRateLimit": True, "rateLimit": 500, "timeout": EXCHANGE_TIMEOUT_MS}
    template["exchange"]["ccxt_async_config"] = {"enableRateLimit": True, "rateLimit": 500, "timeout": EXCHANGE_TIMEOUT_MS}
    # „Pairs streuen": dynamischer, volumengerankter Pairlist-Modus (StaticPairList lädt das kuratierte
    # Kandidaten-Universum aus pair_whitelist, VolumePairList wählt die liquidesten horizont-gedeckelt).
    # Statischer Modus = klassische feste Whitelist. Idempotent — spiegelt stets bot.pair_mode.
    if getattr(bot, "pair_mode", "static") == "dynamic":
        template["pairlists"] = universe.pairlists_for(getattr(bot, "horizon", None)
                                                       or derive_horizon(bot.timeframe))
    else:
        template["pairlists"] = [{"method": "StaticPairList"}]
    template["_comment"] = f"Auto-generiert fuer Bot '{bot.name}' (id={bot.id}). dry_run={bot.dry_run}."
    out = ENGINE_USERDIR / f"config_{bot.id}.json"
    out.write_text(json.dumps(template, ensure_ascii=False, indent=4), encoding="utf-8")
    return out


def ensure_ccxt_timeout() -> int:
    """Idempotente Migration: trägt den Hänger-Schutz-`timeout` in BESTEHENDE Bot-Configs nach.

    Patcht nur das fehlende ``exchange.ccxt_config.timeout`` / ``ccxt_async_config.timeout`` — lässt
    alles andere unberührt. Eine LAUFENDE freqtrade-Instanz liest ihre Config erst beim (Neu-)Start neu,
    d. h. der Timeout greift je Bot ab seinem nächsten Start (Auto-Resume zieht prozess-tote Bots nach).
    Gibt die Zahl der gepatchten Dateien zurück. Exception-fest je Datei (eine kaputte Config bricht den
    Lauf nicht ab). Fasst KEINE stats/Trade-DB an."""
    patched = 0
    try:
        files = list(ENGINE_USERDIR.glob("config_*.json"))
    except Exception:
        return 0
    # Getrackte Referenz-Configs auslassen: die Dry-Run-Vorlage (überschreibt der Builder ohnehin) und die
    # Research-Configs (nur für Backtests — durch die Engine-Backtest-Timeouts bereits begrenzt, kein Live-Loop).
    # So patcht die Migration NUR die generierten (gitignorierten) Bot-Configs — kein Versionskontroll-Rauschen.
    SKIP = {"config_bot1_dryrun.json", "config_research_futures.json", "config_research_spot.json"}
    for cfgp in files:
        if cfgp.name in SKIP:
            continue
        try:
            cfg = json.loads(cfgp.read_text(encoding="utf-8"))
            ex = cfg.get("exchange")
            if not isinstance(ex, dict):
                continue
            changed = False
            for key in ("ccxt_config", "ccxt_async_config"):
                sub = ex.get(key)
                if isinstance(sub, dict) and "timeout" not in sub:
                    sub["timeout"] = EXCHANGE_TIMEOUT_MS
                    changed = True
            if changed:
                cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
                patched += 1
        except Exception as exc:
            audit.record("ccxt_timeout_migrate_error", config=cfgp.name,
                         error=f"{type(exc).__name__}: {exc}")
    if patched:
        audit.record("ccxt_timeout_migrated", count=patched, timeout_ms=EXCHANGE_TIMEOUT_MS)
    return patched
