"""FastAPI-Orchestrator — Einstiegspunkt (M2).

Stellt die REST-API für Bot-Registry, Kontoübersicht, Risiko, Backtest und
Audit bereit und liefert das Web-Dashboard (inkl. Kommandozeile) aus.

Start (Entwicklung):
    uvicorn backend.app.main:app --reload --port 8137
"""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from . import (__version__, ai, alerts, audit, autopilot, cache, concentration, csm, cull, engine,
               execution, fundamental, governor, integration, introspect, maintenance, marketmaking,
               master, meta, mn_paper, pairs, policy_bridge, registry, report, runner, sizing, stats,
               tracker, transfer, universe, vertrag)
from .config import get_settings
from .exchange import get_account_overview
from .models import BotCreate
from .risk import evaluate_bot, evaluate_global

@asynccontextmanager
async def _lifespan(app):  # FastAPI-Lifespan — ersetzt das deprecatete @app.on_event('startup')
    _run_startup()
    yield


app = FastAPI(title="Dizz Trading — Orchestrator", version=__version__, lifespan=_lifespan)

# Dizzi-App-Vertrag (K6): Dizzi-ID-SSO (/auth/*), /api/manifest, Vertrags-
# Settings/Tresor/Aktionen + Mini-Dizzi — additiv; Bestands-Routen bleiben unberührt.
VERTRAG_MANIFEST = vertrag.install_vertrag(app, __version__)

# Per-App-MCP-Gateway (docs/31 §7): Standalone-/mcp, schaltet im Verbund auto ab.
# Strikt read-only — kein Tool startet/stoppt/ändert Trading; Echtgeld-Gate unberührt.
from appkit.app_gateway import build_app_gateway  # noqa: E402
from . import mcp_tools as _mcp_tools             # noqa: E402
app.include_router(build_app_gateway(
    VERTRAG_MANIFEST, vertrag._db, tools=_mcp_tools.MCP_TOOLS,
    base_url=f"http://127.0.0.1:{VERTRAG_MANIFEST.port}"))

STATIC_DIR = Path(__file__).parent / "static"

# --- Produkt-Vorbereitung (Server/App): API-Versionierung + optionaler CORS-Schalter ---
# `/api/v1/...` ist der stabile, versionierte Vertrag und wird intern auf die bestehenden
# `/api/...`-Routen abgebildet (rückwärtskompatibel — alte Clients laufen unverändert weiter).
@app.middleware("http")
async def _api_version_alias(request, call_next):
    p = request.scope.get("path", "")
    if p.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + p[len("/api/v1/"):]
    elif p == "/api/v1":
        request.scope["path"] = "/api"
    return await call_next(request)

_settings0 = get_settings()
_API_TOKEN = _settings0.api_token

# Owner-Token-Schutz: WENN `TBT_API_TOKEN` gesetzt ist, brauchen alle MUTIERENDEN /api-Aufrufe
# (POST/PUT/DELETE/PATCH) `Authorization: Bearer <token>`. Default leer = aus (Lokalbetrieb unverändert).
# Vorbereitung für „nur ich steuere" / Server-Betrieb (später durch echte User-Auth ersetzbar).
@app.middleware("http")
async def _owner_auth(request, call_next):
    if _API_TOKEN and request.method in ("POST", "PUT", "DELETE", "PATCH") \
            and request.url.path.startswith("/api/"):
        # T-1: konstant-zeitiger Vergleich (hmac.compare_digest) statt '!=' — kein Timing-
        # Seitenkanal aufs Owner-Token, konsistent mit dem restlichen Netz (dizzi_id/appkit).
        if not hmac.compare_digest(request.headers.get("authorization", ""),
                                   f"Bearer {_API_TOKEN}"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Nicht autorisiert (Owner-Token erforderlich)."}, status_code=401)
    return await call_next(request)


# View-Cache-Invalidierung: nach einer erfolgreichen MUTIERENDEN /api-Aktion (Start/Stop/Upgrade/Sizing/…)
# werden die kurzlebigen Read-Caches (summary/meta/concentration/sizing/execution/governor) verworfen, damit
# die Panels SOFORT den neuen Stand zeigen statt bis zu ~TTL den alten (sonst self-healing nach 2–3 s).
@app.middleware("http")
async def _invalidate_views_after_mutation(request, call_next):
    response = await call_next(request)
    if request.method in ("POST", "PUT", "DELETE", "PATCH") \
            and request.url.path.startswith("/api/") and response.status_code < 400:
        cache.invalidate()  # ganzer Mini-Cache (wenige Keys) → nächster Read rechnet frisch
    return response

# CORS nur wenn explizit per Env gesetzt (Default: aus → reiner Lokalbetrieb bleibt unverändert).
_cors = [o.strip() for o in (_settings0.cors_origins or "").split(",") if o.strip()]
if _cors:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=_cors, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

# --- Security-Header + CSP (Netzwerk-Standard, analog appkit/headers.py + csp.py) -----------
# TB ist ein eigener Stack (kein appkit-create_app) ⇒ TB-native Middleware, gleiche Policy wie
# das Netzwerk. BASELINE (_TB_CSP): script/style 'self' 'unsafe-inline' — für alle HTML-Antworten
# außer dem Dashboard (z. B. UI-Builder-Tool mit eigenen, nicht-noncten Inline-Skripten).
# VOLL-STRIKT (_TB_CSP_STRICT): das Dashboard ("/") wird serve-seitig mit per-Request-Nonce
# ausgeliefert (dashboard()): alle 4 inline <script> tragen den Nonce, script-src = 'self'
# 'nonce-…' OHNE 'unsafe-inline' (0 Inline-on*-Handler dank C2-Delegation, docs/46). style-src
# behält IMMER 'unsafe-inline' (TB nutzt inline style=-Attribute; appkit-Norm, [[csp-strikt-style-src-blocker]]).
# Google-Fonts-CDN erlaubt (Orbitron/Chakra Petch von fonts.googleapis.com/gstatic.com).
_TB_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
)

# Voll-strikt fürs Dashboard: {nonce} wird per Request gefüllt; script-src ohne 'unsafe-inline'.
_TB_CSP_STRICT = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
)


@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers.setdefault("Cache-Control", "no-cache")
        resp.headers.setdefault("Content-Security-Policy", _TB_CSP)
    return resp


def _run_startup() -> None:
    # Test-Isolation: unter pytest darf der Lifespan KEINE realen Seiteneffekte auslösen. test_vertrag nutzt
    # `with TestClient(main.app)` → das triggert sonst _run_startup gegen das ECHTE System (backend_started-
    # Spam, Config-Migrationen, ensure_master_bot/runner.start, Resume-/Watchdog-Threads auf der Live-Flotte).
    # Die Vertrags-Routen werden beim App-Bau installiert (install_vertrag), NICHT hier — Tests bleiben grün.
    if os.environ.get("TBT_NO_STARTUP"):
        return
    # Mini-Dizzi App-KI (Vertrag 1.5): TB-KI als App-Stimme registrieren.
    # Läuft nur beim echten Start (TBT_NO_STARTUP guard oben) — Tests sind ausgenommen.
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _tb_ki(frage_text: str) -> dict:
            s = get_settings()
            api_key = getattr(s, "anthropic_api_key", None)
            if not api_key:
                return {"antwort": ""}  # Ollama-Fallback via MiniDizzi
            try:
                import anthropic as _ant
                ctx_parts: list[str] = []
                try:
                    ctx_parts.append(f"Master: {master.status()}")
                except Exception:
                    pass
                try:
                    ctx_parts.append(f"Alerts: {alerts.collect()}")
                except Exception:
                    pass
                ctx = " | ".join(ctx_parts) or "Kein Systemstatus verfügbar."
                client = _ant.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=400,
                    system=(
                        "Du bist Mini-Dizzi, die KI-Stimme von Dizz Trading "
                        "(Krypto-Algorithmus-Handelssystem, proposal-only, kein Echtgeld). "
                        "Antworte kurz und sachlich auf Deutsch. "
                        "Schlage KEINE konkreten Trades vor und leiste KEINE Finanzberatung. "
                        f"Aktueller Systemzustand: {ctx}"
                    ),
                    messages=[{"role": "user", "content": frage_text}],
                )
                return {"antwort": (msg.content[0].text if msg.content else "")}
            except Exception:
                return {"antwort": ""}
        app.state.mini_dizzi.set_app_ki(_tb_ki)
    audit.record("backend_started", version=__version__)
    try:  # Bots ohne stabilen Nummern-Tag (#NN) einmalig nachtragen (idempotent).
        n = registry.assign_missing_tags()
        if n:
            audit.record("bot_tags_assigned", count=n)
    except Exception:
        pass
    try:  # Zeit-Horizont (scalping/intraday/swing) für Altbestand nachtragen (idempotent).
        h = registry.assign_missing_horizons()
        if h:
            audit.record("bot_horizons_assigned", count=h)
    except Exception:
        pass
    try:  # Hänger-Schutz: ccxt-Call-Timeout in Bestands-Configs nachtragen (idempotent). Greift je Bot
        # ab dessen nächstem (Neu-)Start — verhindert die „Bot tot, aber Prozess läuft"-Hänger an der Wurzel.
        t = registry.ensure_ccxt_timeout()
        if t:
            audit.record("ccxt_timeout_backfilled", count=t)
    except Exception:
        pass
    try:  # Horizont-Umbau: verbliebene Spot-Bots auf Futures migrieren + gezielt neu starten (einmalig).
        converted = registry.convert_spot_to_futures()
        if converted and engine.engine_available():
            for bid in converted:
                try:
                    if runner.status(bid)["running"]:
                        runner.stop(bid)
                    runner.start(bid)
                except Exception as exc:
                    audit.record("spot_to_futures_restart_error", bot_id=bid,
                                 error=f"{type(exc).__name__}: {exc}")
            audit.record("spot_to_futures_done", count=len(converted))
    except Exception as exc:
        audit.record("spot_to_futures_error", error=f"{type(exc).__name__}: {exc}")
    try:  # MasterMeta-Singleton sicherstellen + starten + selbst-verbessernden Autopilot starten.
        mb = registry.ensure_master_bot()
        if engine.engine_available() and not runner.status(mb.id)["running"]:
            runner.start(mb.id)
        autopilot.start(step_fn=_autopilot_step)
    except Exception as exc:
        audit.record("mastermeta_startup_error", error=f"{type(exc).__name__}: {exc}")
    try:  # AUTO-RESUME nach Systemausfall: Flotte im Hintergrund gestaffelt nachstarten (blockiert den
        # Serverstart nicht). Beim normalen Backend-Neustart (Bots laufen weiter) ist das ein No-op.
        # PLUS Resume-Watchdog: gleicht die Flotte fortlaufend ab (nicht nur einmalig beim Startup).
        if engine.engine_available():
            threading.Thread(target=_resume_fleet, name="fleet-resume", daemon=True).start()
            threading.Thread(target=_resume_watchdog, name="resume-watchdog", daemon=True).start()
    except Exception as exc:
        audit.record("fleet_resume_error", error=f"{type(exc).__name__}: {exc}")


# Resume-Watchdog: tote „running"-Bots werden nicht nur EINMAL beim Startup, sondern KONTINUIERLICH
# nachgestartet. Hintergrund (Vorfall O15 „Eröffnung US"): ein Bot starb bei einem Reboot, sein einmaliges
# Startup-Resume schlug fehl — und wurde NIE wiederholt → er blieb ~5 Tage inaktiv, der Fehlschlag wurde
# zudem ohne Grund geloggt. Jetzt: periodischer Abgleich + Fehlschlag MIT Grund + Crash-Loop-Schutz.
RESUME_WATCHDOG_INTERVAL_S = 600.0   # alle 10 min Soll/Ist abgleichen
RESUME_MAX_TRIES_PER_HOUR = 4        # je Bot im Watchdog: danach Backoff (kein Hämmern auf einen kaputten Bot)
_resume_attempts: dict[str, list[float]] = {}   # bot_id -> Zeitstempel der Watchdog-Startversuche


def _reconcile_fleet(trigger: str, stagger_s: float = 0.6) -> dict:
    """Gleicht das Registry-Soll (``paper_running``/``live_running``) mit dem echten Lauf-Status ab und
    startet tote Bots nach. Bewusst gestoppte/neue Bots bleiben aus. Fehlschläge werden MIT GRUND
    auditiert (vorher still gezählt). Im ``watchdog``-Modus Crash-Loop-Schutz: max. ``RESUME_MAX_TRIES_PER_HOUR``
    Versuche je Bot/Stunde, danach Backoff + Meldung. Exception-fest je Bot."""
    resumed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    now = time.time()
    for b in registry.list_bots():
        if b.status not in ("paper_running", "live_running"):
            continue   # bewusst gestoppte/neue Bots NICHT anfassen
        try:
            if runner.status(b.id)["running"]:
                continue
            if trigger == "watchdog":
                recent = [t for t in _resume_attempts.get(b.id, []) if now - t < 3600.0]
                if len(recent) >= RESUME_MAX_TRIES_PER_HOUR:
                    skipped.append(b.id)   # Backoff: erst nach Ablauf des Fensters wieder versuchen
                    continue
                recent.append(now)
                _resume_attempts[b.id] = recent
            r = runner.start(b.id) or {}
            if r.get("ok"):
                resumed.append(b.id)
            else:   # NICHT mehr still: Grund festhalten (schließt die „failed=1 ohne Grund"-Lücke)
                failed.append(b.id)
                audit.record("fleet_resume_failed", bot_id=b.id, name=getattr(b, "name", b.id),
                             reason=str(r.get("error")), trigger=trigger)
            time.sleep(max(0.0, stagger_s))
        except Exception as exc:  # ein Bot-Fehler darf den Resume nie abbrechen
            failed.append(b.id)
            audit.record("fleet_resume_bot_error", bot_id=b.id,
                         error=f"{type(exc).__name__}: {exc}", trigger=trigger)
    if resumed or failed or skipped:
        audit.record("fleet_reconciled", trigger=trigger, resumed=len(resumed),
                     failed=len(failed), skipped=len(skipped), bot_ids=resumed)
    return {"resumed": resumed, "failed": failed, "skipped": skipped}


def _resume_fleet(stagger_s: float = 0.6, initial_delay_s: float = 8.0) -> dict:
    """Startup-Auto-Resume (einmalig, nach kurzem Anlauf-Delay, damit der Server sofort bedienbar ist).
    Delegiert an ``_reconcile_fleet`` — der Watchdog setzt danach fortlaufend nach."""
    time.sleep(max(0.0, initial_delay_s))
    return _reconcile_fleet("startup", stagger_s=stagger_s)


def _resume_watchdog() -> None:
    """Daemon-Thread: gleicht die Flotte alle ``RESUME_WATCHDOG_INTERVAL_S`` ab (schließt die
    „nur-beim-Startup"-Lücke). Exception-fest — der Watchdog darf nie sterben."""
    while True:
        time.sleep(RESUME_WATCHDOG_INTERVAL_S)
        try:
            _reconcile_fleet("watchdog")
        except Exception as exc:
            audit.record("resume_watchdog_error", error=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- System
@app.get("/health")
def health() -> dict[str, object]:
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "milestone": "M2 — Orchestrator + Dashboard",
        "dry_run": s.dry_run,
        "bitget_configured": s.bitget_configured,
        "ai_module_configured": bool(s.anthropic_api_key),
        "engine_available": engine.engine_available(),
        "bots": len(registry.list_bots()),
    }


@app.get("/api/risk")
def risk_status() -> dict:
    s = get_settings()
    # Reale Portfolio-Kennzahlen kommen jetzt vom Portfolio-Risk-Governor (aggregierter Drawdown über
    # die Tages-Snapshots aller Bots). Kapital bleibt 0 EUR (reiner Demo/Paper-Betrieb, kein echtes Geld).
    try:
        gov = governor.evaluate(use_cache=True)
        drawdown_pct = float(gov.get("drawdown_pct") or 0.0)
    except Exception:
        gov, drawdown_pct = {}, 0.0
    return {
        "global_max_drawdown_pct": s.global_max_drawdown_pct,
        "global_capital_cap_eur": s.global_capital_cap_eur,
        "portfolio_drawdown_pct": drawdown_pct,
        "portfolio_daily_loss_pct": gov.get("daily_loss_pct"),
        "governor_severity": gov.get("severity"),
        "evaluation": evaluate_global(s, total_invested_eur=0.0, drawdown_pct=drawdown_pct),
    }


@app.get("/api/account")
def account() -> dict:
    return get_account_overview(get_settings())


@app.get("/api/audit")
def audit_log(limit: int = 50) -> dict:
    entries = audit.read_all()
    return {"count": len(entries), "entries": entries[-limit:][::-1]}


# ---------------------------------------------------------------- Bots
@app.get("/api/bots")
def list_bots() -> list[dict]:
    out = []
    for b in registry.list_bots():
        d = b.model_dump()
        st = runner.status(b.id)
        d["running"] = st["running"]
        d["health"] = st.get("health")          # ok | stale | unknown | stopped (funktionale Lebendigkeit)
        d["log_age_s"] = st.get("log_age_s")     # Sek. seit letztem Heartbeat (None = kein Log)
        out.append(d)
    return out


# --- V11 Trading→Memory (NUR Sendeseite) ----------------------------------------------------------
# Expliziter HITL-Knopf: legt einen READ-ONLY-Status-Report über den Core-Relay in Dizz Memory ab.
# Best-effort (report.archivieren wirft NIE) ⇒ Core/Memory offline lässt den Trading-Pfad unberührt.
# KEIN Trade-/Aktions-Auslöser. Empfangs-/Transportseite ist World-Chat-seitig fertig (docs/26 §11).
@app.post("/api/report/archivieren")
def report_archivieren() -> dict:
    return report.archivieren(explizit=True)


# --- V11 ↔ RÜCK-LESE (F5): Trading liest aus dem zentralen Archiv (Dizz Memory) -------------------
# Gegenstück zum Report-Sender: best-effort GET über den Core-Relay (appkit.querverbindung.memory_suche).
# Strikt READ-ONLY, wirft NIE in den Trading-Pfad; Core/Memory offline ⇒ leere Treffer. Kein Aktions-Auslöser.
@app.get("/api/wissen/suche")
def wissen_suche(q: str = "", semantisch: bool = False, limit: int = 8) -> dict:
    begriff = (q or "").strip()
    if not begriff:
        return {"ok": False, "treffer": [], "fehler": "Suchbegriff fehlt."}
    from appkit import querverbindung  # lazy: appkit-Pfad ist erst nach dem vertrag-Import gesetzt
    core = os.environ.get("DIZZI_CORE_URL", "http://127.0.0.1:8200").rstrip("/")
    return querverbindung.memory_suche(begriff, semantisch=bool(semantisch),
                                       limit=max(1, min(int(limit), 50)), core_url=core)


# Echtgeld-Gate (schaerfer als Demo-`validated`): validiert != profitabel.
LIVE_MIN_WINDOWS = 2          # mind. 2 bestandene Out-of-Sample-Fenster (Walk-Forward)
LIVE_MIN_PROFIT_FACTOR = 1.0  # Profit-Faktor > 1 (Strategie strukturell nicht verlustreich)


def _live_ready(v: dict | None) -> tuple[bool, str]:
    """Echtgeld-Reife einer Strategie aus ihrem Validierungs-Record.

    Strenger als der laxe Demo-`validated`-Flag (der nur Trades>0 & DD<50% prueft):
    fuer Echtgeld zusaetzlich **Mehr-Fenster-Walk-Forward** (>= ``LIVE_MIN_WINDOWS``)
    UND **Profit-Faktor > ``LIVE_MIN_PROFIT_FACTOR``** (sonst strukturell verlierend).
    Gibt (ok, Begruendung) zurueck. Demo-Bots durchlaufen dieses Gate nicht.
    """
    if not (v and v.get("validated")):
        return False, ("Strategie nicht validiert. Bitte zuerst im Strategie-Katalog "
                       "'Validieren' (Walk-Forward) ausfuehren.")
    windows = int(v.get("windows") or 1)
    if windows < LIVE_MIN_WINDOWS:
        return False, (f"Echtgeld verlangt Mehr-Fenster-Validierung (>= {LIVE_MIN_WINDOWS} "
                       f"Out-of-Sample-Fenster); zuletzt nur {windows}. Mit windows>=2 neu validieren.")
    pf = v.get("profit_factor")
    if pf is None:
        return False, ("Kein Profit-Faktor erfasst (alte Validierung). Bitte mit windows>=2 "
                       "neu validieren — Echtgeld verlangt Profit-Faktor > 1.")
    if float(pf) <= LIVE_MIN_PROFIT_FACTOR:
        return False, (f"Profit-Faktor {round(float(pf), 2)} <= {LIVE_MIN_PROFIT_FACTOR}: Strategie "
                       "strukturell verlustreich — nicht echtgeldreif (validiert != profitabel).")
    return True, (f"Echtgeld-reif: validiert, {windows} Fenster, Profit-Faktor "
                  f"{round(float(pf), 2)} > {LIVE_MIN_PROFIT_FACTOR}.")


@app.post("/api/bots")
def create_bot(payload: BotCreate) -> dict:
    # Echtgeld-Gate: Live-Bots nur mit echtgeldreifer Strategie (Walk-Forward + Profit-Faktor>1).
    if not payload.dry_run:
        ready, reason = _live_ready(stats.get_strategy_validation(payload.strategy))
        if not ready:
            raise HTTPException(status_code=400, detail="Echtgeld-Bot blockiert: " + reason)
    return registry.create_bot(payload).model_dump()


@app.post("/api/bots/{bot_id}/promote")
def promote_bot(bot_id: str, payload: dict | None = None) -> dict:
    """„Algorithmus auf Echtgeld heben": erzeugt aus einem Demo-Bot einen NEUEN
    Echtgeld-Bot (gestoppt) mit denselben gelernten `opt_params`, Strategie, Paaren
    und einem Kapital-Cap. Gate: Strategie muss validiert sein. Startet NICHT
    automatisch — bewusster manueller Start nötig.
    """
    payload = payload or {}
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    if not bot.dry_run:
        return {"ok": False, "error": "Bot ist bereits ein Echtgeld-Bot."}
    ready, reason = _live_ready(stats.get_strategy_validation(bot.strategy))
    if not ready:
        return {"ok": False, "error": reason}
    cons = meta.consistency(bot_id)
    if not cons["consistent"]:
        return {"ok": False, "error": "Konsistenz-Gate: " + cons["reason"], "consistency": cons}
    cap = float(payload.get("capital_cap_eur", 100) or 100)
    stake = float(payload.get("stake_amount", bot.stake_amount) or bot.stake_amount)
    risk = bot.risk.model_copy(update={"capital_cap_eur": cap})
    new = registry.create_bot(BotCreate(
        name=f"{bot.name}-LIVE", strategy=bot.strategy, pairs=bot.pairs,
        timeframe=bot.timeframe, stake_amount=stake, max_open_trades=bot.max_open_trades,
        dry_run=False, trading_mode=bot.trading_mode, risk=risk))
    if bot.opt_params:
        registry.update_bot(new.id, {"opt_params": bot.opt_params})
    audit.record("bot_promoted", source=bot_id, new_bot=new.id, strategy=bot.strategy)
    return {"ok": True, "new_bot": new.id, "strategy": bot.strategy,
            "opt_params": bot.opt_params,
            "note": "Echtgeld-Bot angelegt und GESTOPPT. Erst nach Pruefung manuell starten. "
                    "Kapital-Cap gesetzt; gelernte Parameter uebernommen."}


def _apply_learned_params(bot, params: dict, profit_pct=None, restart: bool = True) -> int:
    """Wendet gelernte Parameter auf EINEN Bot an (DRY-Kern aller Apply-Pfade).

    MERGE statt REPLACE: die Basis-Config (System-Setup, z. B. die Session eines Eröffnungs-Bots)
    bleibt erhalten; der gelernte Gewinner überlagert nur die getunten Parameter. Bei
    ``SessionOpenBreakout`` ist die SESSION Identität (London/US/Asia) und wird nie überschrieben.
    Zählt die Version hoch, startet den Bot optional neu (damit die Engine ``TBT_OPT_PARAMS`` neu
    liest) und schreibt einen Changelog-Eintrag. Gibt die neue Versionsnummer zurück.
    """
    new_version = int(getattr(bot, "opt_version", 0) or 0) + 1
    base = dict(getattr(bot, "opt_params", None) or {})
    merged = {**base, **(params or {})}
    if bot.strategy == "SessionOpenBreakout" and "session" in base:
        merged["session"] = base["session"]
    registry.update_bot(bot.id, {"opt_params": merged, "opt_version": new_version})
    if restart and engine.engine_available():
        runner.stop(bot.id)
        runner.start(bot.id)
    stats.record_upgrade(bot.id, getattr(bot, "tag", None), bot.name, bot.strategy,
                         new_version, merged, profit_pct)
    return new_version


@app.post("/api/bots/{bot_id}/apply_opt")
def bot_apply_opt(bot_id: str) -> dict:
    """Wendet den zuletzt gelernten Gewinner-Vorschlag für die Strategie DIESES Bots
    auf genau diesen Bot an (Neustart, damit die Engine die Parameter liest)."""
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    opt = stats.get_optimization(bot.strategy)
    if not opt or not opt.get("params"):
        return {"ok": False, "error": "Kein gelernter Gewinner fuer diese Strategie - erst 'Loop ausfuehren'."}
    new_version = _apply_learned_params(bot, opt["params"], opt.get("profit_total_pct"))
    # Auto-Upgrade scharf schalten: ab jetzt übernimmt dieser Bot weitere validierte Gewinner automatisch.
    if not getattr(bot, "auto_upgrade", False):
        registry.update_bot(bot_id, {"auto_upgrade": True})
    audit.record("opt_applied_bot", bot_id=bot_id, strategy=bot.strategy,
                 version=new_version, params=opt["params"])
    note = (f"Angewandt → Version v{new_version}, Bot neu gestartet. Auto-Upgrade aktiv: "
            f"weitere OOS-validierte Verbesserungen werden künftig automatisch übernommen.")
    if not opt.get("oos_validated"):
        note += (" ⚠ Dieser Gewinner hat KEINE bestandene OOS-Validierung (Test-Fenster) — "
                 "manuell erlaubt, aber Overfit-Risiko.")
    opt_tf = opt.get("timeframe")
    if opt_tf and bot.timeframe and bot.timeframe != opt_tf:
        note += (f" ⚠ Getunt auf Timeframe {opt_tf}, dieser Bot läuft {bot.timeframe} — "
                 f"Parameter passen evtl. nicht.")
    return {"ok": True, "bot_id": bot_id, "version": new_version, "params": opt["params"],
            "auto_upgrade": True, "oos_validated": bool(opt.get("oos_validated")), "note": note}


def _auto_upgrade_bots() -> dict:
    """Wendet für alle Bots mit ``auto_upgrade=True`` den aktuellen Gewinner ihrer Strategie
    automatisch an, falls sie ihn noch nicht haben (idempotent über Parameter-Vergleich). Version++ +
    Changelog + Neustart laufen über ``_apply_learned_params`` — exakt wie beim manuellen Upgrade, nur
    ohne Knopfdruck. Exception-fest pro Bot. Gibt eine Zusammenfassung zurück.

    ZWEI GATES (beide hart, nur für den Auto-Pfad — manuell bleibt Nutzer-Entscheidung):
    1. ``oos_validated`` — nur Gewinner, die das ungesehene OOS-Test-Fenster bestanden haben
       (anchored Walk-Forward); In-Sample-best-of-N wird nie automatisch ausgerollt.
    2. Timeframe-Match — der Gewinner wurde auf EINER Config/Timeframe getunt; Bots mit anderem
       Timeframe bekommen ihn nicht automatisch (1m-Scalper ≠ 15m-Intraday)."""
    applied: list[dict] = []
    skipped_gate = 0
    for bot in registry.list_bots():
        if not getattr(bot, "auto_upgrade", False):
            continue
        try:
            opt = stats.get_optimization(bot.strategy)
            params = (opt or {}).get("params")
            if not params:
                continue
            if not opt.get("oos_validated"):
                skipped_gate += 1
                continue
            opt_tf = opt.get("timeframe")
            if opt_tf and getattr(bot, "timeframe", None) and bot.timeframe != opt_tf:
                skipped_gate += 1
                continue
            current = getattr(bot, "opt_params", None) or {}
            # schon angewandt? (alle Gewinner-Parameter bereits im Bot — robust ggü. Session-Merge)
            if all(current.get(k) == v for k, v in params.items()):
                continue
            new_version = _apply_learned_params(bot, params, opt.get("profit_total_pct"))
            audit.record("auto_upgrade_applied", bot_id=bot.id, strategy=bot.strategy,
                         version=new_version, params=params)
            applied.append({"bot_id": bot.id, "name": bot.name, "strategy": bot.strategy,
                            "version": new_version})
        except Exception as exc:  # ein Fehler darf den Tick nie abbrechen
            audit.record("auto_upgrade_error", bot_id=bot.id, error=f"{type(exc).__name__}: {exc}")
    return {"applied_count": len(applied), "applied": applied, "skipped_gate": skipped_gate}


@app.get("/api/upgrades")
def upgrades(limit: int = 60) -> dict:
    """C3: Changelog der angewandten Verbesserungen (Upgrades) je Bot — neueste zuerst."""
    return {"upgrades": stats.get_upgrades(limit=limit)}


@app.post("/api/bots/{bot_id}/reset_opt")
def bot_reset_opt(bot_id: str) -> dict:
    """Setzt die gelernten ``opt_params`` dieses Bots zurück (None) → der Bot läuft
    wieder mit den Engine-Defaults. War der Bot aktiv, wird er neu gestartet, damit
    die Engine ohne ``TBT_OPT_PARAMS`` neu lädt."""
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    if not bot.opt_params:
        return {"ok": False, "error": "Keine Lern-Parameter gesetzt - nichts zurueckzusetzen."}
    was_running = runner.status(bot_id)["running"]
    registry.update_bot(bot_id, {"opt_params": None})
    if was_running:
        runner.stop(bot_id)
        runner.start(bot_id)
    audit.record("opt_reset_bot", bot_id=bot_id, restarted=was_running)
    return {"ok": True, "bot_id": bot_id, "restarted": was_running,
            "note": "Lern-Parameter zurueckgesetzt" + (" + Bot neu gestartet." if was_running
                    else " (Bot war gestoppt).")}


@app.get("/api/bots/{bot_id}")
def get_bot(bot_id: str) -> dict:
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return bot.model_dump()


@app.post("/api/bots/{bot_id}/reset_stats")
def reset_bot_stats(bot_id: str) -> dict:
    """Setzt die angezeigten Statistiken eines Bots zurueck (loescht seine Trade-DB).
    Lern-Daten (snapshots/Validierungen/Gewinner) bleiben unberuehrt. Bot wird kurz gestoppt,
    DB geleert, und falls er lief neu gestartet."""
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    was_running = bool((runner.status(bot_id) or {}).get("running"))
    if was_running:
        runner.stop(bot_id)
    res = stats.reset_bot_trades(bot_id)
    if was_running:
        runner.start(bot_id)
    audit.record("bot_stats_reset", bot_id=bot_id, removed=res.get("removed"), restarted=was_running)
    return {"ok": True, "bot_id": bot_id, "restarted": was_running, **res,
            "note": "Statistiken zurueckgesetzt (Lern-Daten unberuehrt)" + (" + Bot neu gestartet." if was_running else ".")}


@app.delete("/api/bots/{bot_id}")
def delete_bot(bot_id: str) -> dict:
    if not registry.delete_bot(bot_id):
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return {"deleted": bot_id}


@app.put("/api/bots/{bot_id}")
def update_bot(bot_id: str, changes: dict) -> dict:
    bot = registry.update_bot(bot_id, changes)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return bot.model_dump()


@app.get("/api/bots/{bot_id}/stats")
def bot_stats(bot_id: str) -> dict:
    if registry.get_bot(bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return {
        "bot_id": bot_id,
        "latest": stats.get_latest(bot_id),
        "summary": stats.summary(bot_id),
        "history": stats.get_runs(bot_id, limit=10),
    }


@app.post("/api/bots/{bot_id}/kill")
def kill_bot(bot_id: str, reason: str = "manueller Kill-Switch") -> dict:
    """SOFT-Kill-Switch: markiert den Bot in der Registry als ``stopped`` (Soll-Zustand) — der laufende
    Prozess wird BEWUSST NICHT beendet (kein ``taskkill``). Zweck: den Bot vom Resume-Watchdog
    ausnehmen (der startet nur ``*_running``-Bots nach), ohne in die Laufzeit einzugreifen.

    WICHTIG: ``/kill`` HEILT KEINEN Zombie und stoppt keinen Handel — der Prozess läuft weiter und wird
    von ``status()`` per Kommandozeile weiter als laufend erkannt (ein direktes ``/start`` meldet dann
    „Bot läuft bereits"). Zum tatsächlichen Beenden/Heilen ``/stop`` (echter Prozess-Kill) bzw.
    ``/stop``→``/start`` verwenden.
    """
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    registry.update_status(bot_id, "stopped")
    audit.record("kill_switch_triggered", bot_id=bot_id, reason=reason, source="manual")
    return {"bot_id": bot_id, "status": "stopped", "reason": reason, "process_stopped": False,
            "note": "Soft-Kill: nur als 'stopped' markiert, Prozess NICHT beendet. Zum echten "
                    "Beenden/Heilen /stop bzw. /stop→/start verwenden."}


@app.post("/api/bots/{bot_id}/start")
def start_bot(bot_id: str) -> dict:
    if registry.get_bot(bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return runner.start(bot_id)


@app.post("/api/bots/{bot_id}/stop")
def stop_bot(bot_id: str) -> dict:
    if registry.get_bot(bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return runner.stop(bot_id)


@app.get("/api/bots/{bot_id}/logs")
def bot_logs(bot_id: str, lines: int = 40) -> dict:
    if registry.get_bot(bot_id) is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    return runner.tail_log(bot_id, lines=lines)


@app.get("/api/catalog")
def catalog() -> dict:
    return ai.get_catalog()


@app.post("/api/catalog/refresh")
def catalog_refresh(max_systems: int | None = None, max_tokens: int | None = None,
                    critique: bool = True, focus: str | None = None) -> dict:
    """Katalog-Refresh. Optional `max_systems`/`max_tokens` für „Max-Power"-Läufe
    (größerer Output; gegen max_tokens-Truncation großzügiger Default). `critique`
    (Default an) schaltet den Self-Critique-Pass (2. Claude-Call) zu — sortiert schwache/
    overfit-verdächtige Systeme aus und senkt unsichere Certainty (kostet etwas mehr Token).
    `focus` = optionaler Freitext-Schwerpunkt des Nutzers (B4), der mit hoher Priorität in den
    Recherche-Prompt einfließt (z. B. „Markt negativ → vorrangig Short-Systeme")."""
    return ai.refresh_catalog(get_settings(), max_systems=max_systems,
                              max_tokens=max_tokens, critique=critique, focus=(focus or None))


@app.get("/api/research/config")
def research_config_get() -> dict:
    return ai.get_research_config()


@app.post("/api/research/config")
def research_config_set(payload: dict) -> dict:
    return ai.set_research_config(payload)


@app.get("/api/research/sources")
def research_sources() -> dict:
    return ai.get_research_sources()


@app.post("/api/research/sources")
def research_source_add(payload: dict) -> dict:
    name = str(payload.get("name", "")).strip()
    url = str(payload.get("url", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name fehlt")
    return ai.add_research_source(name, url, str(payload.get("note", "")))


@app.delete("/api/research/sources/{name}")
def research_source_remove(name: str) -> dict:
    return ai.remove_research_source(name)


@app.post("/api/catalog/{system_id}/pin")
def catalog_pin(system_id: str, pinned: bool = True) -> dict:
    return ai.set_pin(system_id, pinned)


@app.post("/api/catalog/{system_id}/activate")
def catalog_activate(system_id: str, payload: dict) -> dict:
    """Aktiviert eine Recherche-Strategie über eine vorhandene Engine-Vorlage."""
    tpl = str(payload.get("engine_template", "")).strip()
    if tpl not in IMPLEMENTED_STRATEGIES:
        raise HTTPException(status_code=400, detail="Unbekannte/nicht erlaubte Engine-Vorlage")
    return ai.activate_system(system_id, tpl)


def _validate_strategy(strategy: str, days: int, windows: int, timeframe: str | None = None,
                       embargo: int = 0, config: str | None = None) -> dict:
    """Validiert eine Engine-Strategie per Backtest (Pass je Fenster: Trades>0, DD<50 %
    UND Profit>0 — eine Verluststrategie ist nicht „validiert"). `windows>1` →
    Walk-Forward-Prüfung (Mehrheit der Fenster) UND Aggregat-Profit > 0 (Befund E: das
    Mehrheits-Gate allein reicht nicht, wenn 2 knappe Fenster-Gewinne von einem großen
    dritten Verlust überwogen werden — PF-Overfit bei DCA/High-Winrate-Strategien).
    Optional: `timeframe`, `embargo` und `config`. Persistiert je Strategie."""
    if windows and windows > 1:
        res = engine.run_walkforward(strategy, windows=windows, window_days=max(20, days // windows),
                                     timeframe=timeframe, embargo_days=embargo, config_name=config)
        m = res.get("metrics", {}) or {}
        if not res.get("ok"):
            stats.save_strategy_validation(strategy, False, windows, m)
            return {"ok": False, "validated": False, "error": res.get("error", "Backtest fehlgeschlagen")}
        passed = bool(res.get("validated"))
        # Befund E: Mehrheits-Gate + Aggregat-Profit > 0 (avg über alle Fenster).
        # Eine Strategie mit negativem Gesamt-Ergebnis ist trotz 2/3 Fenster-Passes nicht „validiert".
        if passed and float(m.get("profit_total_pct") or 0.0) <= 0.0:
            passed = False
        stats.save_strategy_validation(strategy, passed, windows, m)
        return {"ok": True, "validated": passed, "windows": windows,
                "passed_windows": res.get("passed_windows"), "metrics": m,
                "windows_detail": res.get("windows_detail"),
                "reason": f"{res.get('passed_windows')}/{windows} Fenster bestanden"}
    res = engine.run_strategy_backtest(strategy, days=days)
    m = res.get("metrics", {}) or {}
    if not res.get("ok"):
        stats.save_strategy_validation(strategy, False, 1, m)
        return {"ok": False, "validated": False, "error": res.get("error", "Backtest fehlgeschlagen"),
                "report_tail": res.get("report_tail")}
    passed = (int(m.get("total_trades") or 0) > 0
              and float(m.get("max_drawdown_pct") or 0.0) < 50.0
              and float(m.get("profit_total_pct") or 0.0) > 0.0)
    stats.save_strategy_validation(strategy, passed, 1, m)
    return {"ok": True, "validated": passed, "windows": 1, "metrics": m,
            "reason": ("bestanden" if passed
                       else "nicht bestanden (zu wenig Trades, Drawdown ≥ 50 % oder kein Profit)")}


@app.post("/api/catalog/{system_id}/validate")
def catalog_validate(system_id: str, days: int = 120, windows: int = 1, timeframe: str | None = None,
                     embargo: int = 0, config: str | None = None) -> dict:
    """Validierungs-Gate für eine aktivierte Katalog-Strategie (Backtest/Walk-Forward)."""
    systems = {s["id"]: s for s in ai.get_catalog()["systems"]}
    s = systems.get(system_id)
    if s is None:
        raise HTTPException(status_code=404, detail="System nicht gefunden")
    tpl = s.get("freqtrade_template")
    if tpl not in IMPLEMENTED_STRATEGIES:
        return {"ok": False, "error": "Erst aktivieren (Engine-Vorlage zuordnen), dann validieren."}
    out = _validate_strategy(tpl, days, windows, timeframe=timeframe, embargo=embargo, config=config)
    ai.set_validation(system_id, bool(out.get("validated")), out.get("metrics"))
    return out


@app.post("/api/strategies/{template}/validate")
def strategy_validate(template: str, days: int = 120, windows: int = 1, timeframe: str | None = None,
                      embargo: int = 0, config: str | None = None) -> dict:
    """Validiert eine implementierte Engine-Strategie direkt (für Echtgeld-Freigabe).

    Optional: `timeframe` (z. B. `15m` — einheitliche WF-Basis), `embargo` (Tage Lücke gegen
    Leakage) und `config` (z. B. `config_research_spot.json` für eine breitere Pairliste)."""
    if template not in IMPLEMENTED_STRATEGIES:
        raise HTTPException(status_code=400, detail="Unbekannte Engine-Vorlage")
    return _validate_strategy(template, days, windows, timeframe=timeframe, embargo=embargo, config=config)


@app.get("/api/bots/{bot_id}/analyze")
def analyze_bot(bot_id: str) -> dict:
    return ai.analyze_performance(get_settings(), bot_id)


@app.get("/api/bots/{bot_id}/equity")
def bot_equity(bot_id: str) -> dict:
    bot = registry.get_bot(bot_id)
    starting = bot.dry_run_wallet if (bot and bot.dry_run) else 0.0
    return stats.equity_curve(bot_id, starting)


@app.get("/api/bots/{bot_id}/trades")
def bot_trades(bot_id: str, limit: int = 10) -> dict:
    return stats.recent_trades(bot_id, limit=limit)


@app.get("/api/bots/{bot_id}/snapshots")
def bot_snapshots(bot_id: str, limit: int = 90) -> dict:
    """Tages-Snapshots eines Bots (schlanke Lern-Datenbasis)."""
    return {"bot_id": bot_id, "snapshots": stats.get_snapshots(bot_id, limit=limit)}


@app.post("/api/chat")
def chat(payload: dict) -> dict:
    msg = str(payload.get("message", "")).strip()
    if not msg:
        return {"ok": False, "reply": "Bitte eine Frage eingeben."}
    bots = registry.list_bots()
    ctx = "Vorhandene Bots: " + (", ".join(
        f"{b.name} ({'Demo' if b.dry_run else 'Echtgeld'}, {b.strategy})" for b in bots) or "keine")
    return ai.chat(get_settings(), msg, ctx)


# Tatsaechlich implementierte, lauffaehige Engine-Vorlagen (immer auswaehlbar).
# template -> (Anzeigename, Gruppe, market_type, default_leverage)
IMPLEMENTED_STRATEGIES = {
    "TrendFollowEma": ("Trendfolge (EMA + RSI)", "allgemein", "spot", 1),
    "MeanReversionRsi": ("Mean-Reversion (RSI)", "allgemein", "spot", 1),
    "MomentumMacd": ("Momentum (MACD)", "allgemein", "spot", 1),
    "FuturesMacdRsiScalp": ("Futures MACD-RSI Scalping", "krypto", "futures", 3),
    "FuturesBreakoutVol": ("Futures Volatility-Breakout", "krypto", "futures", 3),
    "FuturesBbandsBounce": ("Futures Bollinger-Bounce", "allgemein", "futures", 3),
    "SessionOpenBreakout": ("Session-Open-Breakout (Börseneröffnung)", "krypto", "futures", 2),
    "GridRange": ("Grid (Raster-Trading)", "krypto", "spot", 1),
    "DcaDip": ("DCA (gestaffeltes Nachkaufen)", "krypto", "spot", 1),
    "Supertrend": ("Supertrend (ATR-Trend)", "allgemein", "futures", 3),
    "VwapReversion": ("VWAP-Reversion (Mean-Reversion)", "allgemein", "spot", 1),
    "TtmSqueeze": ("TTM-Squeeze-Release (Volatilitäts-Kompression)", "krypto", "futures", 3),
    "EmaAdxTrend": ("EMA-Cross + ADX-Trendfilter", "allgemein", "futures", 3),
    "UtBotEma": ("UT-Bot (ATR-Trailing) + EMA", "krypto", "futures", 3),
    "AsianRangeScalp": ("Asian-Range-Fade (Session-Scalp)", "krypto", "futures", 2),
    "RsiDivergence": ("RSI-Divergenz (bestätigte Pivots)", "allgemein", "futures", 2),
    "GaussianScalp": ("Gauß-Filter + SMA + PMO", "allgemein", "futures", 2),
    "MasterMeta": ("🧬 Master-Meta (Regime-Switching · aggressiv Futures)", "krypto", "futures", 5),
}


def _p(name: str, role: str, category: str, default, mn, mx, optional: bool = False) -> dict:
    """Kurz-Helfer fuer einen kategorisierten Strategie-Parameter."""
    return {"name": name, "role": role, "category": category,
            "default": default, "min": mn, "max": mx, "optional": optional}


# Recherchierte, KATEGORISIERTE Parameter je lauffaehiger Strategie.
# category: indikator | volumen | risiko | session | krypto. optional => einklappbar.
# Irrelevante Kategorien werden je Strategie schlicht weggelassen.
STRATEGY_PARAMS: dict[str, list[dict]] = {
    "TrendFollowEma": [
        _p("ema_fast", "Schnelle EMA-Periode", "indikator", 12, 8, 20),
        _p("ema_slow", "Langsame EMA-Periode", "indikator", 26, 21, 60),
        _p("rsi_period", "RSI-Periode", "indikator", 14, 7, 21),
        _p("rsi_entry_min", "RSI-Mindestwert fuer Entry", "indikator", 50, 45, 60),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 4.0, 2.0, 8.0),
        _p("trailing_start_pct", "Trailing aktiv ab Gewinn %", "risiko", 2.0, 1.0, 5.0, True),
        _p("trailing_distance_pct", "Trailing-Abstand %", "risiko", 1.5, 0.5, 3.0, True),
    ],
    "MeanReversionRsi": [  # nur engine-gemappte Keys (take_profit nutzt minimal_roi -> entfernt)
        _p("rsi_period", "RSI-Periode", "indikator", 14, 7, 21),
        _p("macro_sma_period", "Makro-Trendfilter-SMA (nur Dip-Buy im Aufwärtstrend; 0=aus)", "indikator", 150, 100, 200),
        _p("rsi_oversold", "RSI-Oversold (Kauf)", "indikator", 30, 18, 35),
        _p("rsi_exit", "RSI-Exit (Rueckkehr Mitte)", "indikator", 50, 45, 60),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 3.0, 1.5, 6.0),
    ],
    "MomentumMacd": [  # nur engine-gemappte Keys (rsi_filter_max ungenutzt -> entfernt)
        _p("macd_fast", "MACD schnelle EMA", "indikator", 12, 8, 16),
        _p("macd_slow", "MACD langsame EMA", "indikator", 26, 20, 34),
        _p("macd_signal", "MACD Signal-Glaettung", "indikator", 9, 7, 12),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 4.0, 2.0, 7.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16),
    ],
    "FuturesMacdRsiScalp": [  # nur engine-gemappte Keys (rsi_sell/take_profit/leverage ungenutzt -> entfernt)
        _p("macd_fast", "MACD schnelle EMA", "indikator", 8, 5, 12),
        _p("macd_slow", "MACD langsame EMA", "indikator", 21, 15, 26),
        _p("macd_signal", "MACD Signal-Glaettung", "indikator", 9, 5, 12),
        _p("rsi_period", "RSI-Periode", "indikator", 10, 7, 14),
        _p("rsi_buy_threshold", "RSI-Kaufschwelle (max)", "indikator", 45, 40, 50),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 0.8, 0.5, 1.5),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16),
    ],
    "FuturesBreakoutVol": [  # Engine = Donchian+Volumen: nur bb_period(->Kanal)/volume_multiplier/stop_loss gemappt
        _p("bb_period", "Donchian-Kanal-Laenge", "indikator", 20, 15, 25),
        _p("volume_multiplier", "Volumen vs. Schnitt (Breakout)", "volumen", 2.0, 1.5, 2.5),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 1.0, 0.7, 1.5),
    ],
    "FuturesBbandsBounce": [  # Mean-Reversion (Band-Bounce) + opt-in Qualitaetsfilter (RSI/Makro)
        _p("bb_period", "Bollinger-Band-Periode", "indikator", 20, 18, 22),
        _p("bb_std", "Bollinger-Standardabweichung", "indikator", 2.0, 1.8, 2.2),
        _p("rsi_oversold", "RSI-Oversold-Bestätigung (0=aus; gegen schwache Band-Durchstiche)", "indikator", 35, 25, 38),
        _p("macro_sma_period", "Makro-Trendfilter-SMA (nur Dip-Buy im Aufwärtstrend; 0=aus)", "indikator", 150, 100, 200),
        _p("stop_loss_pct", "Stop-Loss jenseits Band %", "risiko", 0.8, 0.5, 1.2),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16),
    ],
    "SessionOpenBreakout": [  # Sonder-Trade-Typ „Börseneröffnung": Opening-Range-Breakout (zeit-getriggert)
        _p("session", "Session-Open (0=Asia 00:00, 1=London 07:00, 2=US 13:00 UTC)", "session", 2, 0, 2),
        _p("opening_range_min", "Länge der Eröffnungs-Range (Min)", "session", 15, 5, 60),
        _p("session_window_min", "Handelsfenster nach Open (Min)", "session", 90, 30, 180, True),
        _p("volume_multiplier", "Volumen vs. Schnitt (Ausbruch-Bestätigung)", "volumen", 1.5, 1.2, 2.5),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 2.0, 1.0, 5.0),
        _p("take_profit_pct", "Take-Profit in %", "risiko", 3.0, 1.0, 6.0, True),
        _p("ema_period", "Momentum-EMA-Filter (0=aus)", "indikator", 0, 0, 50, True),
    ],
    "GridRange": [  # Grid/Raster (range-gebundene Mean-Reversion): Dip kaufen / Grid-Step-Gewinn verkaufen
        _p("grid_levels", "Anzahl Raster-Stufen", "indikator", 7, 4, 20),
        _p("grid_span_pct", "Gesamtspanne des Rasters %", "indikator", 7.0, 2.0, 15.0),
        _p("ref_period", "Referenz-SMA-Periode (Range-Mitte)", "indikator", 60, 20, 120),
        _p("rsi_floor", "RSI-Untergrenze (kein Fall-Kauf)", "indikator", 33, 20, 40),
        _p("range_stop_pct", "Stop bei Range-Bruch %", "risiko", 3.0, 1.0, 6.0),
    ],
    "DcaDip": [  # DCA: Erst-Einstieg (RSI-Dip) + gestaffelte Safety-Orders (Position-Adjustment), Exit per ROI
        _p("rsi_oversold", "RSI-Oversold (Erst-Einstieg)", "indikator", 35, 20, 45),
        _p("max_safety_orders", "Max. Nachkauf-Tranchen", "risiko", 3, 1, 6),
        _p("step_pct", "Rücksetzer-Abstand je Tranche %", "risiko", 2.5, 1.0, 5.0),
        _p("take_profit_pct", "Gesamt-ROI Take-Profit %", "risiko", 2.0, 1.0, 5.0),
        _p("dca_stop_pct", "Stop (weit, DCA mittelt) %", "risiko", 18.0, 8.0, 30.0),
    ],
    "Supertrend": [  # ATR-Trendfolge (Supertrend-Flip): selektiver als EMA-/MACD-Kreuz
        _p("atr_period", "ATR-Periode (Supertrend)", "indikator", 10, 7, 14),
        _p("atr_mult", "ATR-Multiplikator (Band-Abstand)", "indikator", 3.0, 2.0, 4.0),
        _p("macro_sma_period", "Makro-Trendfilter-SMA (nur Long im Aufwärtstrend; 0=aus)", "indikator", 0, 0, 200, True),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 6.0, 3.0, 10.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "VwapReversion": [  # Mean-Reversion zum gleitenden VWAP mit Sigma-Bändern (volumen-gewichtet)
        _p("vwap_window", "VWAP-/Band-Fenster (Kerzen)", "indikator", 48, 20, 120),
        _p("band_k", "Band-Abstand (σ vom VWAP)", "indikator", 2.0, 1.5, 3.0),
        _p("rsi_oversold", "RSI-Oversold-Bestätigung (0=aus)", "indikator", 0, 0, 40, True),
        _p("macro_sma_period", "Makro-Trendfilter-SMA (Dip-Buy nur im Aufwärtstrend; 0=aus)", "indikator", 0, 0, 200, True),
        _p("stop_loss_pct", "Stop-Loss jenseits Band %", "risiko", 3.0, 1.5, 5.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "TtmSqueeze": [  # TTM-Squeeze-Release: BB-in-KC-Kompression löst sich -> Entry in Momentum-Richtung
        _p("bb_period", "Bollinger-/Keltner-Periode", "indikator", 20, 15, 30),
        _p("bb_std", "Bollinger-Standardabweichung", "indikator", 2.0, 1.8, 2.4),
        _p("kc_mult", "Keltner-ATR-Multiplikator", "indikator", 1.5, 1.0, 2.0),
        _p("mom_period", "Momentum-Regressions-Fenster", "indikator", 20, 10, 30),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 2.5, 1.0, 5.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "EmaAdxTrend": [  # EMA-Cross nur bei bestätigter Trendstärke (ADX) -> weniger Seitwärts-Sägen
        _p("ema_fast", "Schnelle EMA-Periode", "indikator", 9, 5, 15),
        _p("ema_slow", "Langsame EMA-Periode", "indikator", 21, 16, 50),
        _p("adx_period", "ADX-Periode", "indikator", 14, 7, 21),
        _p("adx_min", "Min. Trendstärke (ADX) für Entry", "indikator", 25, 18, 35),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 5.0, 2.0, 8.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "UtBotEma": [  # UT-Bot ATR-Trailing-Stop-Signal + EMA-Trendfilter
        _p("key_value", "ATR-Stop-Faktor (Sensitivität)", "indikator", 1.0, 0.5, 3.0),
        _p("atr_period", "ATR-Periode", "indikator", 10, 7, 21),
        _p("ema_fast", "Schnelle EMA (Trendfilter)", "indikator", 9, 5, 15),
        _p("ema_slow", "Langsame EMA (Trendfilter)", "indikator", 21, 16, 50),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 2.0, 0.8, 4.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "AsianRangeScalp": [  # Session-Range-Fade: überverkauft im unteren / überkauft im oberen Range-Drittel
        _p("session", "Session-Open (0=Asia 00:00, 1=London 07:00, 2=US 13:00 UTC)", "session", 0, 0, 2),
        _p("range_min", "Länge der Range-Bildung (Min)", "session", 30, 15, 90),
        _p("session_window_min", "Handelsfenster nach Range (Min)", "session", 180, 60, 300, True),
        _p("rsi_oversold", "RSI-Oversold (Long-Fade; Short spiegelt zu 100−x)", "indikator", 30, 20, 40),
        _p("stoch_oversold", "Stochastic-Oversold (Long-Fade; Short spiegelt)", "indikator", 20, 10, 30),
        _p("stop_loss_pct", "Stop-Loss jenseits Range %", "risiko", 1.2, 0.6, 2.5),
    ],
    "RsiDivergence": [  # Bullische/bärische RSI-Divergenz auf BESTÄTIGTEN Pivots (Lag = pivot_lag)
        _p("rsi_period", "RSI-Periode", "indikator", 14, 7, 21),
        _p("pivot_lag", "Pivot-Bestätigungs-Lag (Kerzen je Seite)", "indikator", 5, 3, 10),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 1.0, 0.5, 2.0),
        _p("take_profit_pct", "Take-Profit in %", "risiko", 2.0, 1.0, 4.0, True),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "GaussianScalp": [  # Ehlers-Gauß-Filter-Slope + SMA-Trendbias + PMO-Momentum
        _p("gauss_period", "Gauß-Filter-Periode", "indikator", 20, 10, 40),
        _p("gauss_poles", "Gauß-Filter-Pole (Glätte)", "indikator", 4, 1, 4),
        _p("sma_period", "Trend-SMA-Periode", "indikator", 149, 100, 200),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 1.8, 0.8, 3.5),
        _p("take_profit_pct", "Take-Profit in %", "risiko", 2.5, 1.0, 5.0, True),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16, True),
    ],
    "MasterMeta": [  # Regime-Switching: SMA-Regime + Trend(MACD+ADX)/Range(BBANDS+RSI)-Sublogik
        _p("sma_period", "Regime-SMA-Periode", "indikator", 50, 30, 80),
        _p("macro_sma_period", "Makro-Trendfilter-SMA (nur Long im Aufwärtstrend; 0=aus)", "indikator", 150, 100, 200),
        _p("adx_min", "Min. Trendstärke (ADX) für Trend-Entry", "indikator", 25, 18, 35),
        _p("macd_fast", "MACD schnell (Trend-Logik)", "indikator", 12, 8, 16),
        _p("macd_slow", "MACD langsam (Trend-Logik)", "indikator", 26, 20, 34),
        _p("macd_signal", "MACD-Signal", "indikator", 9, 7, 12),
        _p("bb_period", "Bollinger-Periode (Range-Logik)", "indikator", 20, 15, 25),
        _p("bb_std", "Bollinger-Standardabweichung", "indikator", 2.0, 1.8, 2.4),
        _p("rsi_period", "RSI-Periode (Range-Bestätigung)", "indikator", 14, 7, 21),
        _p("rsi_oversold", "RSI-Oversold (Range-Entry)", "indikator", 35, 20, 40),
        _p("stop_loss_pct", "Stop-Loss in %", "risiko", 4.0, 2.0, 7.0),
        _p("min_bars_between", "Mindest-Kerzen zwischen Trades (Overtrading-Bremse)", "risiko", 0, 0, 16),
    ],
}


@app.get("/api/strategies")
def strategies() -> list[dict]:
    """Strategien fuer die Bot-Anlage: implementierte (lauffaehig) + Katalog (Recherche)."""
    systems = ai.get_catalog()["systems"]
    params_by_tpl = {s.get("freqtrade_template"): s.get("params", []) for s in systems}
    out, seen = [], set()
    # 1) Immer die implementierten Vorlagen (runnable=True)
    for tpl, (nm, grp, mkt, lev) in IMPLEMENTED_STRATEGIES.items():
        val = stats.get_strategy_validation(tpl) or {}
        live_ok, live_reason = _live_ready(val)
        out.append({"id": tpl, "name": nm, "template": tpl, "runnable": True, "group": grp,
                    "market_type": mkt, "leverage": lev, "crypto_applicable": True, "risk": None,
                    "description": "Lauffaehige Engine-Vorlage",
                    "validated": bool(val.get("validated")),
                    "live_ready": live_ok, "live_reason": live_reason,
                    "profit_factor": val.get("profit_factor"), "windows": val.get("windows"),
                    "params": STRATEGY_PARAMS.get(tpl) or params_by_tpl.get(tpl, [])})
        seen.add(tpl)
    # 2) Recherche-Systeme (nur Info, runnable nur falls implementiert)
    for s in systems:
        tpl = s.get("freqtrade_template", "(Vorlage folgt)")
        if tpl in seen:
            continue
        out.append({"id": s["id"], "name": s["name"], "template": tpl,
                    "runnable": tpl in IMPLEMENTED_STRATEGIES, "group": s.get("group", "allgemein"),
                    "market_type": s.get("market_type", "spot"), "leverage": s.get("leverage"),
                    "crypto_applicable": s.get("crypto_applicable", True),
                    "risk": s.get("risk"), "description": s.get("description") or s.get("context"),
                    "params": s.get("params", [])})
    return out


def _strategy_leverage(strategy: str, trading_mode: str) -> int:
    """Hebel je Strategie aus den implementierten Vorlagen (Spot = 1)."""
    impl = IMPLEMENTED_STRATEGIES.get(strategy)
    if impl:
        return impl[3]
    return 1 if trading_mode == "spot" else 3


_SESSION_IDX = {0: "asia", 1: "london", 2: "us"}

# Primäre Gruppierungs-Kategorien seit dem Horizont-Umbau (2026-06-10): Zeit-Horizont + Börsenöffnung
# als eigene Kategorie. Spot/Futures ist KEINE Gruppe mehr (nur noch technisches Attribut/Hebel-Icon).
BOT_CATEGORIES = ("scalping", "intraday", "swing", "boersenoeffnung")


def _bot_category(b) -> str:
    """Gruppierungs-Kategorie eines Bots: Börsenöffnung (SessionOpenBreakout) hat Vorrang, sonst der
    Zeit-Horizont (scalping/intraday/swing)."""
    if getattr(b, "strategy", None) == "SessionOpenBreakout":
        return "boersenoeffnung"
    h = getattr(b, "horizon", None)
    return h if h in ("scalping", "intraday", "swing") else "intraday"


def _bot_session(b) -> str | None:
    """Session-Schlüssel eines Eröffnungs-Bots (aus opt_params.session) — sonst None.
    Erlaubt der Statistik-Übersicht, Eröffnungs-Bots nach Session zu gruppieren."""
    if getattr(b, "strategy", None) != "SessionOpenBreakout":
        return None
    try:
        idx = int((getattr(b, "opt_params", None) or {}).get("session", 2))
    except (TypeError, ValueError):
        idx = 2
    return _SESSION_IDX.get(idx, "us")


def _meta_insights(rep: dict) -> dict:
    """Aggregierender Meta-Algorithmus (Synthese-Schicht): verdichtet das über ALLE Strategien
    Gelernte zu einer konsolidierten Einschätzung + Lehren. Proposal-only, keine Auto-Aktion.
    (Erster Baustein des „übergeordneten Algorithmus"; ein selbst-trainierender Agent ist der
    spätere, größere Ausbau.)"""
    aggs = {s["strategy"]: s for s in rep.get("strategies", [])}
    opts = {o["strategy"]: o for o in rep.get("optimizations", [])}
    per = []
    for tpl, (nm, grp, mkt, lev) in IMPLEMENTED_STRATEGIES.items():
        val = stats.get_strategy_validation(tpl) or {}
        ready, _ = _live_ready(val)
        a = aggs.get(tpl, {})
        per.append({"strategy": tpl, "name": nm, "market_type": mkt,
                    "profit_factor": val.get("profit_factor"), "windows": val.get("windows"),
                    "live_ready": ready, "validated": bool(val.get("validated")),
                    "avg_winrate_pct": a.get("avg_winrate_pct"),
                    "learned_params": (opts.get(tpl) or {}).get("params")})
    with_pf = [p for p in per if p["profit_factor"] is not None]
    best = max(with_pf, key=lambda p: p["profit_factor"]) if with_pf else None
    ready_n = sum(1 for p in per if p["live_ready"])
    ra = rep.get("regime_advice") or {}
    st = rep.get("status") or {}
    # Datengetriebene Lehren
    lessons = []
    lessons.append(f"Datenreife {st.get('readiness_pct',0)} % — Aussagen werden mit mehr Laufzeit belastbarer.")
    lessons.append(f"{ready_n}/{len(per)} Strategien echtgeldreif (Profit-Faktor > 1 nötig)"
                   + (f"; bestes System aktuell {best['name']} (PF {best['profit_factor']})." if best else "."))
    if any((p.get("avg_winrate_pct") or 0) >= 50 and (p.get("profit_factor") or 99) < 1 for p in per):
        lessons.append("Hohe Trefferquote ≠ profitabel: mehrere Strategien > 50 % Winrate, aber Profit-Faktor < 1 "
                       "(kleine Gewinne, seltene große Verluste).")
    cooldowners = [p["name"] for p in per if (p.get("learned_params") or {}).get("min_bars_between")]
    if cooldowners:
        lessons.append("Trade-Bremse (min_bars_between) ist in gelernten Gewinnern aktiv → Overtrading-Reduktion zahlt sich aus: "
                       + ", ".join(cooldowners) + ".")
    # Börseneröffnungen strukturell in der Master-Synthese: aktive Session + beste Eröffnung je Strategie.
    sa = rep.get("session_advice") or {}
    bbs = sa.get("best_by_strategy") or {}
    if sa.get("in_opening_window"):
        lessons.append(f"Aktive Börseneröffnung ({sa.get('opening_window')}) — Session-Open-Systeme sind jetzt strukturell im Element.")
    if bbs:
        top = sorted(bbs.items(), key=lambda kv: (kv[1].get("avg_profit_pct") or -1e9), reverse=True)[:2]
        lessons.append("Session-Lernen (beste Eröffnung je Strategie): "
                       + " · ".join(f"{k}→{v.get('session_label')} ({v.get('avg_profit_pct')}%)" for k, v in top) + ".")
    elif rep.get("session_data_points"):
        lessons.append(f"Session-/Eröffnungs-Lernen sammelt ({rep.get('session_data_points')} Trades) — beste Eröffnung je Strategie wird mit mehr Historie belastbar.")
    regime = (rep.get("market") or {}).get("regime")
    headline = (f"Meta-Algorithmus: Markt-Regime {regime or '–'} → empfohlen {', '.join(ra.get('recommended',[]) or ['—'])}. "
                + (f"Bestes System {best['name']} (PF {best['profit_factor']}); " if best else "")
                + (f"{ready_n} echtgeldreif." if ready_n else "noch keine Strategie echtgeldreif."))
    return {"headline": headline, "best_strategy": best, "echtgeldreif_count": ready_n,
            "regime": {"current": regime, "recommended": ra.get("recommended", []),
                       "source": ra.get("source")},
            "session": {"current": sa.get("current_session_label"),
                        "in_opening_window": sa.get("in_opening_window"),
                        "opening_window": sa.get("opening_window"),
                        "best_by_strategy": bbs},
            "lessons": lessons, "per_strategy": per,
            "note": "Synthese aus validierten Strategie-Erkenntnissen (proposal-only). "
                    "Selbst-trainierender Master-Agent = späterer Ausbau (Blueprint §6)."}


@app.get("/api/introspect")
def introspect_report() -> dict:
    """Selbst-Analyse: Struktur in Unterkategorien + Health + Verbesserungs-Hebel + Lern-Ziel."""
    return introspect.assess()


@app.post("/api/introspect/collect")
def introspect_collect() -> dict:
    """Sammelt die wichtigsten Selbst-Audit-Schlüsse kompakt ins Learning-Ledger ein."""
    return introspect.self_collect()


@app.get("/api/component/descriptor")
def component_descriptor() -> dict:
    """Selbstbeschreibung für ein übergeordnetes Verwaltungssystem (Capabilities/Contract)."""
    return integration.descriptor()


@app.get("/api/component/state")
def component_state() -> dict:
    """Konsolidierter, standardisierter Zustand für die übergeordnete Verwaltungsinstanz."""
    return integration.state()


@app.post("/api/component/command")
def component_command(request: Request, payload: dict | None = None) -> dict:
    """Direktive der übergeordneten Verwaltungsinstanz (owner-token-gated; destruktive
    Befehle zusätzlich confirm=true UND Schutzstufe 'verifiziert' — F2-Härtung)."""
    payload = payload or {}
    action = payload.get("action", "")
    if action in integration.DESTRUCTIVE:
        gate_error = vertrag.require_steuerstufe(request)
        if gate_error:
            raise HTTPException(status_code=403, detail=gate_error)
    return integration.command(action, payload.get("params"))


@app.get("/api/master")
def master_status() -> dict:
    """Master-Algorithmus (U7): aktuelle Regime→Strategie-Politik + Fitness-Verlauf (proposal-only)."""
    return master.status()


@app.get("/api/regime")
def regime_state(symbol: str = "BTC/USDT") -> dict:
    """Live-Markt-Regime: Gaussian-HMM (Baum-Welch + Viterbi) über die 1h-Renditen, primär; Schwellen-
    Modell als Fallback + relatives Vola-Regime. Holt frische ccxt-Public-Daten (read-only, keine Orders)."""
    return tracker.regime_report(symbol)


@app.post("/api/regime/config")
def regime_set_config(patch: dict | None = None) -> dict:
    """Setzt die HMM-Regime-Parameter (n_states) — wirkt beim nächsten Markt-Snapshot/Regime-Report."""
    return {"ok": True, "config": tracker.set_hmm_config(patch or {})}


@app.get("/api/fundamental")
def fundamental_state() -> dict:
    """Fundamental-Schicht: vorausschauendes Event-Risiko aus dem Wirtschaftskalender (FOMC/CPI/NFP),
    key-frei (faireconomy + Seed-Fallback). Dämpft im Master defensiv das gerichtete Sleeve."""
    return fundamental.report()


@app.post("/api/fundamental/config")
def fundamental_set_config(patch: dict | None = None) -> dict:
    """Setzt die Fundamental-Parameter (pre/post/elevated_window_h, include_medium, cache_hours, dampen)
    und triggert einen Master-Trainingsschritt (Overlay wirkt sofort)."""
    cfg = fundamental.set_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("fundamental_config")}


def _high_vol() -> bool:
    """Volatilitäts-Regime aus dem jüngsten Markt-Snapshot (für die Master-Allokation).

    Bevorzugt das neue **relative** Vola-Regime (turbulent vs. eigener Baseline); fällt für
    Alt-Snapshots ohne `vol_regime` auf die absolute Return-Stdev-Schwelle zurück."""
    market = stats.get_market_snapshots(limit=1)
    if not market:
        return False
    last = market[-1]
    vr = last.get("vol_regime")
    if vr:
        return vr == "turbulent"
    return (last.get("volatility") or 0) >= 1.0


def _auto_train(trigger: str) -> dict:
    """Auto-Trainingsschritt nach einem Lern-Loop: die Ensemble-Politik wächst mit der neuen
    Evidenz mit. Fehler werden geschluckt — ein Lern-Loop darf daran nie scheitern."""
    try:
        r = master.train_step(high_vol=_high_vol())
        audit.record("master_autotrain", trigger=trigger, version=r.get("version"),
                     improved=r.get("improved"), fitness=r.get("candidate_fitness"))
        return {"improved": r.get("improved"), "version": r.get("version"),
                "fitness": r.get("candidate_fitness")}
    except Exception as exc:  # nie den Lern-Loop brechen
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------- MasterMeta-Bot (Autopilot)
def _mastermeta_consult() -> dict:
    """Rücksprache mit den Unter-AIs (reine Lese-Synthese): HMM-Regime + Konfidenz, Master-Ensemble-
    Politik, Fundamental-Event-Risiko — und **Beobachtung**, welche anderen Engines sich zuletzt
    verbessert haben (zum Mitlernen). Liefert den Kontext, den der Verbesserungs-Schritt nutzt."""
    ctx: dict = {}
    reg = tracker.read_regime_bridge() or {}
    ctx["regime"], ctx["regime_confidence"] = reg.get("regime"), reg.get("confidence")
    try:
        ctx["event_risk"] = fundamental.event_risk().get("event_risk")
    except Exception:
        ctx["event_risk"] = None
    try:
        pol = master.status().get("policy") or {}
        ar = pol.get("active_regime") or {}
        ctx["master_version"] = pol.get("version")
        ctx["master_active_strategy"] = ((pol.get("allocations") or {}).get(ar.get("regime")) or {}).get("strategy")
    except Exception:
        pass
    peers = []
    try:
        for t in sorted(PARAMETRIZABLE_STRATEGIES):
            if t == "MasterMeta":
                continue
            o = stats.get_optimization(t)
            if o and o.get("params"):
                peers.append({"strategy": t, "winner_label": o.get("winner_label"),
                              "profit_total_pct": o.get("profit_total_pct")})
    except Exception:
        pass
    ctx["peer_optimizations"] = peers
    return ctx


def _mastermeta_improve(reason: str) -> dict:
    """EIN Selbst-Verbesserungs-Schritt des aggressiven MasterMeta-Bots (vom Autopilot-Thread).

    Hält zuerst **Rücksprache mit den Unter-AIs** (HMM/Master/Fundamental) und beobachtet die
    Peer-Engines. Testet dann die MasterMeta-Parameter per **Walk-Forward** (OOS) und wendet den
    Gewinner NUR an, wenn er **validiert** ist (Selektions-Bias-Schwelle) UND kein High-Impact-Event
    unmittelbar bevorsteht (Fundamental-Gate — aggressiv, aber nicht blind ins Event). Bei Anwendung:
    Version++, Bot-Neustart, Changelog + Master-Train. Auto-Apply bewusst auf validierte Gewinner begrenzt.
    """
    bot = registry.get_bot(registry.MASTER_BOT_ID)
    if bot is None:
        bot = registry.ensure_master_bot()
    ctx = _mastermeta_consult()
    spec = STRATEGY_PARAMS.get("MasterMeta", [])
    out = meta.run_optimization("MasterMeta", spec, days=90, windows=2)
    winner = out.get("winner")
    bias = out.get("selection_bias") or {}
    confident = bool(bias.get("confident"))
    event_block = (ctx.get("event_risk") == "high")
    result: dict = {"ok": True, "reason": reason, "tested": True,
                    "confident": confident, "trials": bias.get("valid_trials"),
                    "winner_profit_pct": (winner or {}).get("profit_total_pct"),
                    "applied": False, "version": int(getattr(bot, "opt_version", 0) or 0),
                    "consulted": ctx}
    if winner and winner.get("params") and confident and not event_block:
        new_version = _apply_learned_params(bot, winner["params"], winner.get("profit_total_pct"))
        audit.record("mastermeta_auto_improved", version=new_version, reason=reason,
                     params=winner["params"], profit_pct=winner.get("profit_total_pct"))
        result.update(applied=True, version=new_version, params=winner["params"])
    elif event_block and winner and confident:
        result["deferred"] = "High-Impact-Event nahe (Fundamental-AI) → aggressive Anwendung verschoben."
    result["master"] = _auto_train(f"mastermeta_autopilot:{reason}")
    return result


def _autopilot_step(reason: str) -> dict:
    """Periodischer Autopilot-Tick: (1) Portfolio-Risk-Governor (Gesamt-Risiko überwachen, bei breach
    de-risken/pausieren), (2) MasterMeta selbst verbessern, (3) Auto-Upgrade aller dafür freigeschalteten
    Bots (validierte Gewinner automatisch übernehmen), (4) chronisch schlechte Demo-Bots auto-cullen
    (Selbst-Bewertung; Learnings bleiben). Alle Teile exception-fest voneinander getrennt.

    Reihenfolge bewusst: der Governor läuft ZUERST — sieht ein breach das Gesamt-Portfolio, wird de-riskt,
    bevor die Verbesserungs-/Cull-Logik auf einer entgleisten Lage weiterarbeitet."""
    out: dict = {}
    try:
        out["governor"] = governor.run_once(reason=reason)
    except Exception as exc:
        out["governor"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        # FP-2 Sizing-Bridge (SPEC docs/KELLY_SIZING_SPEC.md §4): direkt NACH dem Governor, damit
        # eine frische breach-Lage die Brücke sofort auf proposal degradiert. Default AUS (no-op).
        out["sizing_bridge"] = sizing.write_bridge_auto()
    except Exception as exc:
        out["sizing_bridge"] = {"written": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        # FP-T5 Politik-Bridge (SPEC docs/POLICY_HAND_SPEC.md §4): ebenfalls NACH dem Governor
        # (breach ⇒ proposal-Degradation, warn ⇒ Logik-Freeze im Payload). Default AUS (no-op).
        out["policy_bridge"] = policy_bridge.write_bridge_auto()
    except Exception as exc:
        out["policy_bridge"] = {"written": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        out["mastermeta"] = _mastermeta_improve(reason)
    except Exception as exc:
        out["mastermeta"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        out["auto_upgrade"] = _auto_upgrade_bots()
    except Exception as exc:
        out["auto_upgrade"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        out["cull"] = cull.run_once(reason=reason)
    except Exception as exc:
        out["cull"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        out["auto_validate"] = _auto_validate_strategy(reason)
    except Exception as exc:
        out["auto_validate"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


def _auto_validate_strategy(reason: str = "schedule") -> dict:
    """Auto-Validierung (schließt den Recherche→Evidenz-Loop): je Autopilot-Tick wird EINE lauffähige
    Engine-Strategie, die noch KEINE eigene OOS-Validierung hat, per Walk-Forward validiert.

    Hintergrund: das System preist Eigen-Evidenz überall ein (Katalog-Scores, Echtgeld-Gate,
    Master-Gewichte) — aber ``strategy_validations`` entstand bisher nur durch manuell angestoßene
    Validierungen; recherchierte Systeme blieben ungegroundet. Eine Strategie pro Tick begrenzt das
    Compute (~Minuten); sind alle abgedeckt, ist der Schritt ein No-op. Proposal-only (validiert nur,
    wendet nichts an)."""
    if not engine.engine_available():
        return {"ran": False, "note": "Engine nicht verfügbar"}
    pending = sorted(t for t in IMPLEMENTED_STRATEGIES
                     if stats.get_strategy_validation(t) is None)
    if not pending:
        return {"ran": False, "note": "alle Engine-Strategien haben bereits eine Validierung"}
    template = pending[0]
    audit.record("auto_validate_started", strategy=template, reason=reason, pending=len(pending))
    res = _validate_strategy(template, days=120, windows=3, embargo=1)
    audit.record("auto_validate_done", strategy=template, validated=bool(res.get("validated")),
                 ok=bool(res.get("ok")))
    return {"ran": True, "strategy": template, "validated": res.get("validated"),
            "ok": res.get("ok"), "remaining": len(pending) - 1}


def _mastermeta_status() -> dict:
    """Live-Status des MasterMeta-Bots (Registry + Laufzeit + Summary-Kennzahlen) + Autopilot-Zustand."""
    bot = registry.get_bot(registry.MASTER_BOT_ID)
    if bot is None:
        bot = registry.ensure_master_bot()
    run = runner.status(bot.id)
    wallet = float(getattr(bot, "dry_run_wallet", 0.0) or 0.0)
    pnl = stats.bot_pnl(bot.id, wallet)
    latest = stats.get_latest(bot.id) or {}
    regime = tracker.read_regime_bridge() or {}
    op = getattr(bot, "opt_params", None) or {}
    # Aggressiver dynamischer Hebel: base + (max-base)·HMM-Konfidenz, gedrosselt nach Event-Scale
    # (spiegelt master_meta.leverage() für die Anzeige).
    base_lev = float(op.get("base_leverage", 5) or 5)
    max_lev = max(base_lev, float(op.get("max_leverage", 10) or 10))
    conf = regime.get("confidence")
    try:
        conff = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        conff = 0.5
    eff_lev = base_lev + (max_lev - base_lev) * max(0.0, min(1.0, conff))
    scale = regime.get("lev_scale")
    try:
        if scale is not None:
            eff_lev *= max(0.2, min(1.0, float(scale)))
    except (TypeError, ValueError):
        pass
    return {
        "bot": {
            "id": bot.id, "tag": getattr(bot, "tag", None), "name": bot.name,
            "strategy": bot.strategy, "trading_mode": bot.trading_mode, "timeframe": bot.timeframe,
            "running": run.get("running"), "opt_version": int(getattr(bot, "opt_version", 0) or 0),
            "opt_params": op or None,
            "profit_live_pct": pnl.get("profit_pct"), "profit_abs": pnl.get("profit_abs"),
            "trades_open": pnl.get("open"), "trades_closed": pnl.get("closed"),
            "wins": pnl.get("wins"),
            "max_drawdown_pct": latest.get("max_drawdown_pct"),
        },
        "leverage": {"base": base_lev, "max": max_lev, "current_est": round(eff_lev, 1),
                     "aggressive": True, "can_short": True},
        "current_regime": regime.get("regime"),
        "regime_confidence": regime.get("confidence"),
        "event_risk": regime.get("event_risk"),
        "autopilot": autopilot.status(),
        "optimization": stats.get_optimization("MasterMeta"),
    }


@app.get("/api/mastermeta")
def mastermeta_status() -> dict:
    """Status des dedizierten MasterMeta-Bots + selbst-verbessernder Autopilot (für KI-Tool-Panel)."""
    return _mastermeta_status()


@app.post("/api/mastermeta/improve")
def mastermeta_improve() -> dict:
    """Stößt sofort einen Verbesserungs-Schritt an (Hintergrund, nicht-blockierend)."""
    return autopilot.trigger_now("manual")


@app.post("/api/mastermeta/autopilot")
def mastermeta_autopilot(patch: dict | None = None) -> dict:
    """Autopilot konfigurieren: ``{enabled: bool, interval_h: float}``."""
    return {"ok": True, "autopilot": autopilot.set_state(patch or {})}


@app.get("/api/cull")
def cull_status() -> dict:
    """Auto-Cull: aktuelle Selbst-Bewertungen aller Bots + Konfiguration + letzter Durchlauf."""
    return cull.status()


@app.post("/api/cull/run")
def cull_run(force: bool = False) -> dict:
    """Cull-Durchlauf jetzt ausführen (verwirft kritisch schlechte Demo-Bots; Learnings bleiben)."""
    return cull.run_once(reason="manual", force=force)


@app.post("/api/cull/config")
def cull_set_config(patch: dict | None = None) -> dict:
    """Cull-Schwellen tunen: ``{enabled, min_days, min_trades, max_avg_loss_pct, max_trend_pct, min_interval_h}``."""
    return {"ok": True, "config": cull.set_config(patch or {})}


# ---------------------------------------------------------------- Portfolio-Risk-Governor (P1)
@app.get("/api/governor")
def governor_status() -> dict:
    """Portfolio-Risk-Governor: aggregierter Drawdown/Tagesverlust, Anomalien, Schwere + Konfiguration."""
    return governor.status()


@app.post("/api/governor/run")
def governor_run(force: bool = False) -> dict:
    """Governor-Durchlauf jetzt ausführen (greift bei breach gemäß ``action`` ein: alert/derisk/pause)."""
    return governor.run_once(reason="manual", force=force)


@app.post("/api/governor/config")
def governor_set_config(patch: dict | None = None) -> dict:
    """Governor-Schwellen tunen: ``{enabled, warn_drawdown_pct, max_drawdown_pct, max_daily_loss_pct,
    action, derisk_count, anomaly_z, anomaly_floor_pct, min_interval_h, protect_master}``."""
    return {"ok": True, "config": governor.set_config(patch or {})}


# ---------------------------------------------------------------- Konzentrations-/Korrelations-Bewusstsein (P2)
@app.get("/api/concentration")
def concentration_status() -> dict:
    """Konzentrations-Analyse über die Flotte: Exposure je Basis-Asset, HHI, Korrelations-Cluster,
    Deckel-Flags + Streuungs-Hinweise. Kurzer TTL-Cache (3 s) gegen Burst-Refreshes (read-only)."""
    return cache.ttl_get("concentration", 3.0, concentration.analyze)


@app.post("/api/concentration/config")
def concentration_set_config(patch: dict | None = None) -> dict:
    """Konzentrations-Deckel tunen: ``{enabled, max_asset_share_pct, max_cluster_share_pct, clusters}``."""
    return {"ok": True, "config": concentration.set_config(patch or {})}


# ---------------------------------------------------------------- Coin-Universum / „Pairs streuen"
@app.get("/api/universe")
def universe_model() -> dict:
    """Das kuratierte, gestreute Coin-Universum (Single Source of Truth): Tiers, Kandidaten und der
    dynamische, volumengerankte Auswahl-Modus je Horizont. Für UI-Anzeige + KI/Recherchetool."""
    return universe.model()


@app.post("/api/universe/diversify")
def universe_diversify(body: dict | None = None) -> dict:
    """„Pairs streuen" anwenden: einen Bot (``{bot_id}``) oder die GANZE Flotte auf das gestreute,
    dynamische Volumen-Universum umstellen. Startet die geänderten Bots neu (``restart``, Default True),
    damit die Engine die neue Pairlist liest. Idempotent — gibt die geänderten Bot-IDs zurück."""
    body = body or {}
    bot_id = body.get("bot_id")
    restart = bool(body.get("restart", True))
    if bot_id:
        bot = registry.diversify_bot(bot_id)
        if bot is None:
            raise HTTPException(status_code=404, detail="Bot nicht gefunden")
        changed = [bot_id]
    else:
        changed = registry.diversify_fleet()
    restarted: list[str] = []
    errors: list[dict] = []
    if restart and engine.engine_available():
        for bid in changed:
            try:
                if (runner.status(bid) or {}).get("running"):
                    runner.stop(bid)
                runner.start(bid)
                restarted.append(bid)
            except Exception as exc:
                errors.append({"bot_id": bid, "error": f"{type(exc).__name__}: {exc}"})
    audit.record("universe_diversify", count=len(changed), restarted=len(restarted),
                 errors=len(errors), bot_id=bot_id or "fleet")
    return {"ok": True, "changed": changed, "restarted": restarted, "errors": errors,
            "universe": universe.model()}


# ---------------------------------------------------------------- Vola-skaliertes Positions-Sizing (P3)
def _apply_sizing(bot, recommended_stake: float) -> dict:
    """Setzt den empfohlenen Stake auf EINEN Bot (Registry → Config neu) und startet ihn bei Bedarf neu,
    damit die Engine den neuen Stake liest. Gibt alten/neuen Stake zurück. Proposal-only/Demo."""
    old = float(getattr(bot, "stake_amount", 0.0) or 0.0)
    new = round(float(recommended_stake), 2)
    registry.update_bot(bot.id, {"stake_amount": new})   # update_bot schreibt die Engine-Config neu
    restarted = False
    if engine.engine_available() and runner.status(bot.id)["running"]:
        runner.stop(bot.id)
        runner.start(bot.id)
        restarted = True
    audit.record("sizing_applied", bot_id=bot.id, name=bot.name,
                 old_stake=old, new_stake=new, restarted=restarted)
    return {"bot_id": bot.id, "name": bot.name, "old_stake": old, "new_stake": new, "restarted": restarted}


@app.get("/api/sizing")
def sizing_status() -> dict:
    """Vola-skaliertes Positions-Sizing: Empfehlung je Bot (Stake invers zur realisierten Volatilität).

    Iteriert die Flotte (je Bot ``meta.consistency`` → Snapshot-Read) → kurzer TTL-Cache (3 s) kollabiert
    Burst-Refreshes des KI-Tools auf eine Berechnung (wie summary/meta/concentration/execution)."""
    return cache.ttl_get("sizing", 3.0, sizing.recommend)


@app.post("/api/sizing/config")
def sizing_set_config(patch: dict | None = None) -> dict:
    """Sizing tunen: Vol-Targeting ``{enabled, reference_stake, target_vol_pct, min_stake, max_stake,
    min_returns, min_change_pct}`` + Erwartungswert-Tilt (opt-in, gegated) ``{expectancy_enabled,
    kelly_fraction, kelly_cap, kelly_floor, min_trades_kelly}`` + FP-2 (SPEC, Defaults inert):
    Edge-Quelle/Abschlag ``{edge_source, min_trades_strategy, shrink_trades, sim_discount}``,
    Klemmkette ``{portfolio_budget_pct, concentration_clamp, governor_clamp}``, Brücke
    ``{bridge_enabled, bridge_mode, bridge_max_age_s}``."""
    return {"ok": True, "config": sizing.set_config(patch or {})}


@app.get("/api/sizing/plan")
def sizing_plan() -> dict:
    """FP-2 Portfolio-Sizing-Plan (read-only): per-Bot-Empfehlungen + Klemmkette K4→K5→K6
    (Budget/Konzentration/Governor, Reihenfolge normativ — docs/KELLY_SIZING_SPEC.md §3) inkl.
    je-Bot-Klemm-Protokoll (``clamps``) und ``trace``. Kurzer TTL-Cache wie /api/sizing."""
    return cache.ttl_get("sizing.plan", 3.0, sizing.portfolio_plan)


def _plan_row(bot_id: str) -> dict | None:
    plan = sizing.portfolio_plan()
    return next((r for r in plan.get("rows") or [] if r.get("bot_id") == bot_id), None)


@app.post("/api/bots/{bot_id}/sizing/apply")
def sizing_apply_bot(bot_id: str, plan: bool = False) -> dict:
    """Wendet die Sizing-Empfehlung auf genau diesen Bot an (Stake setzen + Neustart).

    ``?plan=1`` (FP-2, expliziter per-Call-Opt-in): wendet statt der nackten per-Bot-Empfehlung den
    **geklemmten** Portfolio-Plan-Stake an (K4–K6). Default false = Verhalten unverändert."""
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot nicht gefunden")
    if plan:
        row = _plan_row(bot_id)
        if row is None:   # z. B. Echtgeld-Bot — der Plan plant nur dry_run (SPEC §3)
            raise HTTPException(status_code=409, detail="Bot ist nicht im Portfolio-Plan (Echtgeld?)")
        res = _apply_sizing(bot, row["planned_stake"])
        return {"ok": True, **res, "factor": row["factor"], "clamps": row.get("clamps"),
                "realized_vol_pct": row["realized_vol_pct"]}
    rec = sizing.recommend_for(bot, sizing.get_config())
    res = _apply_sizing(bot, rec["recommended_stake"])
    return {"ok": True, **res, "factor": rec["factor"], "realized_vol_pct": rec["realized_vol_pct"]}


@app.post("/api/sizing/apply_all")
def sizing_apply_all(plan: bool = False) -> dict:
    """Wendet die Sizing-Empfehlung auf alle Bots mit signifikanter Abweichung an (Stake + Neustart).

    ``?plan=1`` (FP-2): wie oben, aber mit den **geklemmten** Plan-Stakes (K4–K6) statt der nackten
    per-Bot-Empfehlungen. Default false = Verhalten unverändert."""
    applied = []
    if plan:
        for row in (sizing.portfolio_plan().get("rows") or []):
            if row["change"]:
                b = registry.get_bot(row["bot_id"])
                if b is None:
                    continue
                try:
                    applied.append(_apply_sizing(b, row["planned_stake"]))
                except Exception as exc:
                    audit.record("sizing_apply_error", bot_id=row["bot_id"],
                                 error=f"{type(exc).__name__}: {exc}")
        return {"ok": True, "applied_count": len(applied), "applied": applied, "plan": True}
    cfg = sizing.get_config()
    for b in registry.list_bots():
        rec = sizing.recommend_for(b, cfg)
        if rec["change"]:
            try:
                applied.append(_apply_sizing(b, rec["recommended_stake"]))
            except Exception as exc:
                audit.record("sizing_apply_error", bot_id=b.id, error=f"{type(exc).__name__}: {exc}")
    return {"ok": True, "applied_count": len(applied), "applied": applied}


# ---------------------------------------------------------------- Execution-/Slippage-Tracking (P4)
@app.get("/api/execution")
def execution_status() -> dict:
    """Execution-/Slippage-Tracking: Ist- vs. Erwartungspreis (Slippage) + Gebühren je Bot/Flotte."""
    return execution.analyze(use_cache=True)


@app.post("/api/execution/config")
def execution_set_config(patch: dict | None = None) -> dict:
    """Execution-Schwellen tunen: ``{enabled, warn_slippage_bps, warn_cost_bps, warn_trend_bps,
    min_trades, recent_window}``."""
    return {"ok": True, "config": execution.set_config(patch or {})}


@app.get("/api/bots/{bot_id}/execution")
def bot_execution(bot_id: str, limit: int = 100) -> dict:
    """Execution-Qualität je Trade dieses Bots (Slippage-bps + Gebühren-bps, ältest→neuest)."""
    return {"bot_id": bot_id, "trades": stats.execution_costs(bot_id, limit=limit)}


# ---------------------------------------------------------------- Proaktives Monitoring/Alerting (P5)
@app.get("/api/alerts")
def alerts_status() -> dict:
    """Aktive Alerts (priorisiert): Portfolio-Risiko, Ausführung, Datenfeed-Gesundheit, Betrieb."""
    return alerts.collect()


@app.post("/api/alerts/config")
def alerts_set_config(patch: dict | None = None) -> dict:
    """Alert-Schwellen tunen: ``{enabled, stale_market_min, stale_regime_min}``."""
    return {"ok": True, "config": alerts.set_config(patch or {})}


@app.post("/api/master/config")
def master_set_config(patch: dict | None = None) -> dict:
    """Setzt die Meta-Learner-Parameter der Sockel-Gewichtung (sharpe_haircut/conf_shrink/max_weight/
    weight_temp/sharpe_to_pf) und triggert direkt einen Trainingsschritt (Politik wächst mit)."""
    cfg = master.set_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("master_config")}


@app.post("/api/master/train")
def master_train() -> dict:
    """Ein Trainingsschritt: Politik neu ableiten → bewerten → nur behalten wenn besser (versioniert)."""
    r = master.train_step(high_vol=_high_vol())
    audit.record("master_train", version=r.get("version"), improved=r.get("improved"),
                 fitness=r.get("candidate_fitness"))
    return {"ok": True, **r}


@app.get("/api/master/policy-bridge")
def policy_bridge_status() -> dict:
    """FP-T5 Politik→Hand-Brücke: Config + Live-Vorschau des geklemmten Payloads (ohne zu schreiben).

    Zeigt, WAS die Politik der MasterMeta-Engine vorschlagen würde (Sub-Logik je Regime, Stake-
    Dämpfung, Edge-Gating) und welche Klemmen greifen (Governor/Konzentration) — Gate G-T5:
    Defaults inert/proposal-only bis Nutzer-Entscheid. Details docs/POLICY_HAND_SPEC.md."""
    return cache.ttl_get("policy_bridge.status", 3.0, policy_bridge.status)


@app.post("/api/master/policy-bridge/config")
def policy_bridge_set_config(patch: dict | None = None) -> dict:
    """FP-T5 Politik-Brücke tunen: ``{bridge_enabled, bridge_mode, bridge_max_age_s}`` + Hebel
    ``{apply_logic, apply_stake, gate_unprofitable, scale_floor}`` (alle Defaults inert; ``apply``
    wirkt nur dry_run + Engine-Opt-in ``use_policy_bridge`` — SPEC §4)."""
    return {"ok": True, "config": policy_bridge.set_config(patch or {})}


@app.get("/api/csm")
def csm_state() -> dict:
    """Cross-Sectional-Momentum-Engine (markt-neutral, DEMO-Simulation): Equity, Stats, aktuelles L/S-Signal.
    Edge belegt+gehärtet in `programm/research/` (Netto-Sharpe ~1,2–1,3). Keine Orders — Echtgeld = Freigabe."""
    return csm.get_state()


@app.get("/api/csm/signal")
def csm_signal() -> dict:
    """Nur das aktuelle handelbare Signal (welche Pairs long/short) + Kurz-Stats."""
    return csm.status()


@app.post("/api/csm/refresh")
def csm_refresh(days: int = 730) -> dict:
    """Aktualisiert die Daily-Close-Daten des Universums (read-only ccxt, inkrementell). Erstlauf ~1 Min."""
    r = csm.refresh_prices(days=days)
    audit.record("csm_refresh", universe=r.get("universe"), rows=r.get("rows_upserted"))
    return {"ok": True, **r}


@app.post("/api/csm/config")
def csm_set_config(patch: dict) -> dict:
    """Setzt CSM-Parameter (lookback/hold/quantile/fee/universe_top/min_history/capital)."""
    cfg = csm.set_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("csm_config")}


@app.get("/api/csm/optimize")
def csm_optimize(windows: int = 3) -> dict:
    """Lern-Loop: Walk-Forward-Optimierung der CSM-Parameter (proposal-only, schnelle Sim)."""
    return csm.optimize(windows=windows)


# --- Pairs-Trading (markt-neutral, DEMO-Simulation) — teilt die Datenbasis mit CSM ---
@app.get("/api/pairs")
def pairs_state() -> dict:
    """Pairs-Engine (markt-neutral, DEMO-Simulation): Equity, Stats, gehandelte Paare + aktive Spreads.
    Handelt den Spread korrelierter Paare (Z-Score-Mean-Reversion). Keine Orders — Echtgeld = Freigabe."""
    return pairs.get_state()


@app.get("/api/pairs/signal")
def pairs_signal() -> dict:
    """Nur das aktuelle Signal (gehandelte Paare + aktive Spread-Positionen) + Kurz-Stats."""
    return pairs.status()


@app.post("/api/pairs/config")
def pairs_set_config(patch: dict) -> dict:
    """Setzt Pairs-Parameter (lookback/entry_z/exit_z/n_pairs/min_corr/fee/min_history/capital)."""
    cfg = pairs.set_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("pairs_config")}


@app.get("/api/pairs/optimize")
def pairs_optimize(windows: int = 3) -> dict:
    """Lern-Loop: Walk-Forward-Optimierung der Pairs-Parameter (proposal-only)."""
    return pairs.optimize(windows=windows)


@app.get("/api/statarb")
def statarb_state() -> dict:
    """Statistical-Arbitrage (Korb-Reversion, markt-neutral, DEMO-Simulation): jedes Symbol vs.
    Korb-Mittel — long Nachzügler / short Ausreißer (Z-Score-Mean-Reversion). Keine Orders."""
    return pairs.get_statarb_state()


@app.get("/api/statarb/signal")
def statarb_signal() -> dict:
    """Nur das aktuelle Korb-Signal (long Nachzügler / short Ausreißer) + Kurz-Stats."""
    return pairs.statarb_status()


@app.post("/api/statarb/config")
def statarb_set_config(patch: dict) -> dict:
    """Setzt StatArb-Parameter (lookback/quantile/fee/min_history/capital)."""
    cfg = pairs.set_statarb_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("statarb_config")}


@app.get("/api/statarb/optimize")
def statarb_optimize(windows: int = 3) -> dict:
    """Lern-Loop: Walk-Forward-Optimierung der StatArb-Korb-Parameter (proposal-only)."""
    return pairs.optimize_statarb(windows=windows)


# --- Market-Making (Avellaneda-Stoikov, markt-neutral, DEMO-Modell-Simulation) ---
@app.get("/api/mm")
def mm_state() -> dict:
    """Market-Making-Engine (Avellaneda-Stoikov, DEMO-Modell-Simulation, markt-neutral):
    Equity, Stats, Fill-Rate, Inventar. Modell-Sim auf kalibrierter Vola — keine Orders."""
    return marketmaking.get_state()


@app.get("/api/mm/signal")
def mm_signal() -> dict:
    """Kurz-Status der Market-Making-Simulation (Stats + Fills + Inventar)."""
    return marketmaking.status()


@app.post("/api/mm/config")
def mm_set_config(patch: dict) -> dict:
    """Setzt MM-Parameter (gamma/k/A/order_size/inventory_limit/steps/episodes/maker_rebate_bps/symbol/capital)."""
    cfg = marketmaking.set_config(patch or {})
    return {"ok": True, "config": cfg, "master": _auto_train("mm_config")}


@app.get("/api/mm/optimize")
def mm_optimize(windows: int = 3) -> dict:
    """Lern-Loop: Raster über (gamma,k), bewertet über mehrere Seeds (proposal-only)."""
    return marketmaking.optimize(windows=windows)


# --- MN-Paper-Bots: persistente, benannte Bots über den markt-neutralen Sim-Engines ---
# Ehrlich (Gesetz 2): SIMULATION auf echten Preisen, 0 echtes Risiko, KEINE Orders, kein
# Freqtrade-Prozess. Jeder Paper-Bot trägt seine eigene Config + seine eigene simulierte PnL/Winrate.
@app.get("/api/mn-paper")
def mn_paper_list() -> dict:
    """Liste aller MN-Paper-Bots mit PnL%/Winrate (Sim-gecacht) + der anlegbare Engine-Katalog."""
    return {"bots": mn_paper.summary(), "engines": mn_paper.engines_catalog(),
            "mode": "demo-simulation"}


@app.post("/api/mn-paper")
def mn_paper_create(payload: dict) -> dict:
    """Legt einen MN-Paper-Bot an. Pflicht: ``engine`` (csm/pairs/statarb/mm) + ``name``;
    optional ``config`` (Teil-Patch der Engine-Defaults) + ``note``."""
    engine = (payload or {}).get("engine")
    name = (payload or {}).get("name")
    if not engine or engine not in mn_paper.ENGINES:
        raise HTTPException(status_code=400, detail="unbekannte oder fehlende MN-Engine (csm/pairs/statarb/mm)")
    if not name:
        raise HTTPException(status_code=400, detail="name fehlt")
    rec = mn_paper.create(name, engine, payload.get("config"), note=payload.get("note", ""))
    return {"ok": True, **rec}


@app.post("/api/mn-paper/seed")
def mn_paper_seed() -> dict:
    """Komfort: je MN-Engine einen Default-Paper-Bot anlegen, falls noch keiner existiert (idempotent)."""
    created = mn_paper.seed_defaults()
    return {"ok": True, "created": created, "count": len(created)}


@app.get("/api/mn-paper/{bot_id}")
def mn_paper_state(bot_id: str) -> dict:
    """Voller Zustand eines Paper-Bots: Stammdaten + frische Sim-Bewertung (Equity/Stats/Winrate) + Track."""
    st = mn_paper.state(bot_id)
    if st is None:
        raise HTTPException(status_code=404, detail="Paper-Bot nicht gefunden")
    return st


@app.put("/api/mn-paper/{bot_id}")
def mn_paper_update(bot_id: str, changes: dict) -> dict:
    """Aktualisiert Config (``config``-Teil-Patch) und/oder ``name`` eines Paper-Bots."""
    rec = None
    if isinstance(changes, dict) and "name" in changes:
        rec = mn_paper.rename(bot_id, changes["name"])
    if isinstance(changes, dict) and changes.get("config"):
        rec = mn_paper.update_config(bot_id, changes["config"])
    if rec is None:
        raise HTTPException(status_code=404, detail="Paper-Bot nicht gefunden (oder nichts zu ändern)")
    return {"ok": True, **rec}


@app.post("/api/mn-paper/{bot_id}/start")
def mn_paper_start(bot_id: str) -> dict:
    """Aktiviert den Paper-Bot (Status running) — beginnt seinen Kalender-PnL-Track."""
    rec = mn_paper.set_status(bot_id, "running")
    if rec is None:
        raise HTTPException(status_code=404, detail="Paper-Bot nicht gefunden")
    return {"ok": True, **rec}


@app.post("/api/mn-paper/{bot_id}/stop")
def mn_paper_stop(bot_id: str) -> dict:
    """Pausiert den Paper-Bot (Status stopped) — der bisherige Track bleibt erhalten."""
    rec = mn_paper.set_status(bot_id, "stopped")
    if rec is None:
        raise HTTPException(status_code=404, detail="Paper-Bot nicht gefunden")
    return {"ok": True, **rec}


@app.delete("/api/mn-paper/{bot_id}")
def mn_paper_delete(bot_id: str) -> dict:
    if not mn_paper.delete(bot_id):
        raise HTTPException(status_code=404, detail="Paper-Bot nicht gefunden")
    return {"deleted": bot_id}


@app.get("/api/maintenance/report")
def maintenance_report() -> dict:
    """Lern-Gedächtnis-/Speicher-Karte (read-only) + Lifecycle-Vorschau (dry-run)."""
    rep = maintenance.storage_report()
    rep["preview"] = maintenance.run_all(dry_run=True)
    rep["ledger"] = maintenance.get_ledger(limit=30)
    return rep


@app.post("/api/maintenance/run")
def maintenance_run(dry_run: bool = True) -> dict:
    """Lifecycle ausführen: verdichten + pruning + Audit-Rotation. Default dry_run=True (Vorschau)."""
    return {"ok": True, **maintenance.run_all(dry_run=dry_run)}


@app.get("/api/meta")
def meta_report() -> dict:
    """Lern-Bot: Aggregation je Strategie + Daten-Reife + Vorschläge + Meta-Synthese (`insights`).

    Schwerster Endpoint (mehrere Voll-Flotten-Sweeps + große DB-Reads), vom KI-Tool gepollt → kurzer
    TTL-Cache (3 s) kollabiert Burst-Refreshes auf EINE Berechnung (wie summary/governor)."""
    return cache.ttl_get("meta_report", 3.0, _meta_report_compute)


def _meta_report_compute() -> dict:
    rep = meta.report()
    try:
        rep["insights"] = _meta_insights(rep)
    except Exception as exc:  # Synthese darf den Report nie brechen
        rep["insights"] = {"error": f"{type(exc).__name__}: {exc}"}
    return rep


# Engine-Vorlagen, die Optimierungs-Parameter aus der Umgebung lesen (Lern-Loop testbar).
PARAMETRIZABLE_STRATEGIES = {
    "MeanReversionRsi", "TrendFollowEma", "MomentumMacd",
    "FuturesMacdRsiScalp", "FuturesBreakoutVol", "FuturesBbandsBounce", "MasterMeta",
    "SessionOpenBreakout", "GridRange", "DcaDip", "Supertrend", "VwapReversion",
}


@app.get("/api/meta/optimize/{template}")
def meta_optimize(template: str) -> dict:
    """Lern-Loop Stufe 2 (proposal-only): Kandidaten-Parametersätze je Strategie."""
    if template not in STRATEGY_PARAMS:
        raise HTTPException(status_code=404, detail="Keine Parameter-Spezifikation für diese Strategie")
    out = meta.optimize_proposals(template, STRATEGY_PARAMS.get(template, []))
    out["parametrizable"] = template in PARAMETRIZABLE_STRATEGIES
    return out


@app.post("/api/meta/optimize/{template}/run")
def meta_optimize_run(template: str, days: int = 90, windows: int = 2) -> dict:
    """Schließt den Loop ANCHORED: Kandidaten-Selektion auf dem Trainings-Fenster, einmaliger
    OOS-Test des Gewinners auf dem ungesehenen Test-Fenster (proposal-only, persistiert mit
    `oos_validated`). `windows<=1` = reiner In-Sample-Vergleich (nie auto-anwendbar)."""
    if template not in STRATEGY_PARAMS:
        raise HTTPException(status_code=404, detail="Keine Parameter-Spezifikation für diese Strategie")
    if template not in PARAMETRIZABLE_STRATEGIES:
        return {"ok": False, "error": "Diese Engine-Vorlage liest noch keine Parameter aus der Config "
                                      "(nur MeanReversionRsi ist als Prototyp parametrisierbar)."}
    out = meta.run_optimization(template, STRATEGY_PARAMS.get(template, []), days=days, windows=windows)
    return {"ok": True, **out, "master": _auto_train(f"meta_optimize:{template}")}


@app.post("/api/meta/evolve/{template}/run")
def meta_evolve_run(template: str, days: int = 180, windows: int = 3, generations: int = 2,
                    pool: int = 4, timeframe: str = "15m", embargo_days: int = 3,
                    scale: float = 0.25) -> dict:
    """Evolutionaerer Lern-Loop, ANCHORED (proposal-only): Mutation + Selektion NUR auf dem
    Trainings-Fenster, finaler einmaliger OOS-Test des Gewinners auf dem ungesehenen
    Test-Fenster. Persistiert mit `oos_validated`; wird NICHT automatisch angewandt."""
    if template not in STRATEGY_PARAMS:
        raise HTTPException(status_code=404, detail="Keine Parameter-Spezifikation für diese Strategie")
    if template not in PARAMETRIZABLE_STRATEGIES:
        return {"ok": False, "error": "Diese Engine-Vorlage liest keine Parameter aus der Config."}
    out = meta.run_evolution(template, STRATEGY_PARAMS.get(template, []),
                             generations=generations, days=days, windows=windows,
                             pool=pool, timeframe=(timeframe or None),
                             embargo_days=embargo_days, scale=scale)
    return {"ok": True, **out, "master": _auto_train(f"meta_evolve:{template}")}


@app.post("/api/strategies/{template}/apply_opt")
def strategy_apply_opt(template: str) -> dict:
    """Wendet den persistierten Gewinner-Vorschlag auf alle DEMO-Bots dieser Strategie
    an (mit Neustart, damit die Engine die Parameter liest). Live-Bots bleiben unberührt."""
    if template not in PARAMETRIZABLE_STRATEGIES:
        return {"ok": False, "error": "Strategie ist nicht parametrisierbar."}
    opt = stats.get_optimization(template)
    if not opt or not opt.get("params"):
        return {"ok": False, "error": "Kein Gewinner-Vorschlag vorhanden - erst 'Loop ausfuehren'."}
    params = opt["params"]
    applied = []
    for b in registry.list_bots():
        if b.strategy == template and b.dry_run:
            # MERGE + Session-Erhalt via gemeinsamen Helfer (vorher REPLACE → hätte die Session
            # von Eröffnungs-Bots gelöscht). Konsistent mit dem Einzel-Apply.
            _apply_learned_params(b, params, opt.get("profit_total_pct"))
            applied.append(b.id)
    audit.record("opt_applied", strategy=template, bots=applied, params=params)
    note = "Auf Demo-Bot(s) angewandt (Neustart). Live-Bots unberührt."
    if not opt.get("oos_validated"):
        note += (" ⚠ Gewinner OHNE bestandene OOS-Validierung — manuell erlaubt, "
                 "aber Overfit-Risiko.")
    return {"ok": True, "applied_bots": applied, "params": params,
            "oos_validated": bool(opt.get("oos_validated")), "note": note}


@app.get("/api/summary")
def summary(days: int | None = None) -> dict:
    """Aggregierte Kurzübersicht über alle Bots (für das obere Statistik-Panel).

    Liefert die Bot-Zeilen inkl. `trading_mode`/`leverage` sowie nach Kategorie getrennte Aggregate
    (`groups`). Kurzer TTL-Cache (2 s) kollabiert Burst-Refreshes (Statistik- + Bots-Tab) auf EINE
    Berechnung — sonst liest jeder Aufruf alle ~51 Trade-DBs neu (`stats.bot_pnl` je Bot)."""
    return cache.ttl_get(f"summary:{days}", 2.0, lambda: _summary_compute(days))


def _summary_compute(days: int | None) -> dict:
    bots = registry.list_bots()
    rows, profits, running, stale = [], [], 0, 0   # stale = läuft prozessual, aber Heartbeat eingefroren
    # Aggregate je KATEGORIE (Zeit-Horizont + Börsenöffnung) inkl. Live-Trades/Profit.
    groups = {cat: {"bots": 0, "running": 0, "profits": [],
                    "open": 0, "closed": 0, "wins": 0, "profit_abs": 0.0, "wallet": 0.0}
              for cat in BOT_CATEGORIES}
    tot = {"open": 0, "closed": 0, "wins": 0, "profit_abs": 0.0, "wallet": 0.0}
    # "Bots failed due to drawdown" aus dem Audit-Log ableiten (Kill-Switch wegen DD).
    failed_ids: set[str] = set()
    try:
        for e in audit.read_all():
            if e.get("event") == "kill_switch_triggered" and \
               "drawdown" in str(e.get("reason") or "").lower():
                bid = e.get("bot_id") or e.get("source")
                if bid:
                    failed_ids.add(str(bid))
    except Exception:
        pass
    for b in bots:
        _st = runner.status(b.id)
        is_running = _st["running"]
        bot_health = _st.get("health")            # ok | stale | unknown | stopped
        is_stale = bot_health == "stale"          # läuft prozessual, aber Heartbeat eingefroren (Zombie)
        running += 1 if is_running else 0
        stale += 1 if is_stale else 0
        latest = stats.get_latest(b.id)
        profit = latest.get("profit_total_pct") if latest else None  # Backtest-Profit (Anzeige BT)
        if profit is not None:
            profits.append(profit)
        wallet = float(getattr(b, "dry_run_wallet", 0.0) or 0.0)
        pnl = stats.bot_pnl(b.id, wallet, since_days=days)
        mode = b.trading_mode  # technisches Exchange-Attribut (Hebel-Icon), KEINE Gruppe mehr
        category = _bot_category(b)
        g = groups[category]
        g["bots"] += 1
        g["running"] += 1 if is_running else 0
        if profit is not None:
            g["profits"].append(profit)
        g["open"] += pnl["open"]; g["closed"] += pnl["closed"]; g["wins"] += pnl["wins"]
        g["profit_abs"] += pnl["profit_abs"] or 0.0; g["wallet"] += wallet
        tot["open"] += pnl["open"]; tot["closed"] += pnl["closed"]; tot["wins"] += pnl["wins"]
        tot["profit_abs"] += pnl["profit_abs"] or 0.0; tot["wallet"] += wallet
        rows.append({
            "id": b.id, "tag": getattr(b, "tag", 0), "name": b.name, "running": is_running,
            "health": bot_health, "log_age_s": _st.get("log_age_s"),  # funktionale Lebendigkeit (Zombie-Erkennung)
            "dry_run": b.dry_run, "strategy": b.strategy,
            # Lern-Version + Auto-Upgrade-Flag → Upgrade-Badge auch in der Statistik-Übersicht (wie Bots-Tab).
            "opt_version": getattr(b, "opt_version", 0),
            "auto_upgrade": getattr(b, "auto_upgrade", False),
            "trading_mode": mode,
            "horizon": getattr(b, "horizon", None),
            "category": category,
            "session": _bot_session(b),
            "leverage": _strategy_leverage(b.strategy, mode),
            # „Pairs streuen": welche Coins der Bot handelt (Universum) + dynamischer Auswahl-Modus.
            "pair_mode": getattr(b, "pair_mode", "static"),
            "pairs": list(getattr(b, "pairs", []) or []),
            "pair_max": (universe.number_assets_for(getattr(b, "horizon", None))
                         if getattr(b, "pair_mode", "static") == "dynamic" else None),
            "timeframe": getattr(b, "timeframe", None),
            "timeframes": list(getattr(b, "timeframes", []) or []),
            "profit_total_pct": profit,
            "profit_live_pct": pnl["profit_pct"],
            "profit_abs": pnl["profit_abs"],
            "max_drawdown_pct": latest.get("max_drawdown_pct") if latest else None,
            "trades_open": pnl["open"], "trades_closed": pnl["closed"],
            "wins": pnl["wins"],
            "failed_drawdown": b.id in failed_ids,
        })

    def _avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    def _pct(abs_: float, wallet: float) -> float | None:
        return round(abs_ / wallet * 100, 2) if wallet else None

    tracker.maybe_snapshot_all()  # debounced: schlanke Lern-Datenbasis pflegen
    return {
        "bots": len(bots), "running": running, "stale": stale, "with_stats": len(profits),
        "avg_profit_pct": _avg(profits),
        "trades_open": tot["open"], "trades_closed": tot["closed"],
        "trades_done": tot["closed"], "wins": tot["wins"],
        "profit_abs": round(tot["profit_abs"], 2),
        "profit_pct": _pct(tot["profit_abs"], tot["wallet"]),
        "failed_drawdown": len(failed_ids),
        "groups": {
            cat: {
                "bots": g["bots"], "running": g["running"],
                "with_stats": len(g["profits"]), "avg_profit_pct": _avg(g["profits"]),
                "trades_open": g["open"], "trades_closed": g["closed"], "wins": g["wins"],
                "profit_abs": round(g["profit_abs"], 2),
                "profit_pct": _pct(g["profit_abs"], g["wallet"]),
            }
            for cat, g in groups.items()
        },
        "categories": list(BOT_CATEGORIES),
        "rows": rows,
    }


@app.post("/api/transfer")
def make_transfer(payload: dict, request: Request) -> dict:
    settings = get_settings()
    # Echtgeld-Gate (K6/R-B): ECHTE Transfers nur mit Stufe 'hochsicher'
    # (Dizzi-ID + TOTP); Paper-Transfers bleiben frei (bewegen kein Geld).
    gate_error = vertrag.require_hochsicher_fuer_echtgeld(request, settings)
    if gate_error:
        raise HTTPException(status_code=403, detail=gate_error)
    return transfer.transfer(
        settings,
        from_acc=str(payload.get("from", "main")),
        to_acc=str(payload.get("to", "")),
        asset=str(payload.get("asset", "USDT")),
        amount=float(payload.get("amount", 0) or 0),
        confirm=bool(payload.get("confirm", False)),
    )


@app.post("/api/bots/{bot_id}/backtest")
def backtest_bot(bot_id: str, days: int = 180) -> dict:
    result = engine.run_backtest(bot_id, days=days)
    if not result.get("ok"):
        return result

    bot = registry.get_bot(bot_id)
    metrics = result.get("metrics", {})
    stats.save_backtest_run(bot_id, result.get("strategy", ""), metrics)

    # Aktiver Risiko-Wächter: Backtest-Drawdown gegen Bot-Limit prüfen.
    drawdown = float(metrics.get("max_drawdown_pct") or 0.0)
    risk = evaluate_bot(bot, daily_loss_pct=0.0, drawdown_pct=drawdown, trades_today=0)
    if risk["kill_switch"]:
        # Nur Hinweis aus dem Backtest — ein laufender Live-Bot wird hier NICHT gestoppt.
        audit.record("backtest_risk_warning", bot_id=bot_id, violations=risk["violations"])
    result["risk"] = risk
    return result


# ---------------------------------------------------------------- Konsole
_CONSOLE_HELP = (
    "Befehle: help | status | bots | balance | risk | audit | "
    "newbot <name> | stats <bot_id> | "
    "setrisk <bot_id> <feld> <wert> | start <bot_id> | stop <bot_id> | "
    "logs <bot_id> | kill <bot_id> | delbot <bot_id> | "
    "catalog | refresh | pin <sys_id> | unpin <sys_id> | analyze <bot_id>"
)


@app.post("/api/console")
def console(payload: dict) -> dict:
    """Whitelist-basierte Kommandozeile (KEIN Shell-Zugriff)."""
    raw = str(payload.get("command", "")).strip()
    parts = raw.split()
    if not parts:
        return {"output": _CONSOLE_HELP}
    cmd, args = parts[0].lower(), parts[1:]

    if cmd in ("help", "?"):
        return {"output": _CONSOLE_HELP}
    if cmd == "status":
        return {"output": health()}
    if cmd == "bots":
        return {"output": [f"{b.id}  {b.name}  [{b.strategy}]  {b.status}" for b in registry.list_bots()]}
    if cmd == "balance":
        return {"output": get_account_overview(get_settings())}
    if cmd == "risk":
        return {"output": risk_status()}
    if cmd == "audit":
        return {"output": audit.read_all()[-10:][::-1]}
    if cmd == "newbot" and args:
        bot = registry.create_bot(BotCreate(name=" ".join(args)))
        return {"output": f"Bot angelegt: {bot.id} ({bot.name})"}
    if cmd == "stats" and args:
        return {"output": bot_stats(args[0])}
    if cmd == "setrisk" and len(args) >= 3:
        field, value = args[1], args[2]
        try:
            num: float | int = int(value) if field == "max_trades_per_day" else float(value)
        except ValueError:
            return {"output": f"Ungueltiger Wert: {value}"}
        bot = registry.update_bot(args[0], {"risk": {field: num}})
        if bot is None:
            return {"output": f"Bot nicht gefunden: {args[0]}"}
        return {"output": f"{args[0]}: risk.{field} = {num}"}
    if cmd == "start" and args:
        return {"output": runner.start(args[0])}
    if cmd == "stop" and args:
        return {"output": runner.stop(args[0])}
    if cmd == "logs" and args:
        return {"output": runner.tail_log(args[0], lines=20)}
    if cmd == "catalog":
        return {"output": [f"{s['id']}  {s['name']}{'  📌' if s.get('pinned') else ''}" for s in ai.get_catalog()["systems"]]}
    if cmd == "refresh":
        doc = ai.refresh_catalog(get_settings())
        return {"output": f"Katalog aktualisiert (Quelle: {doc['source']}, {len(doc['systems'])} Systeme)"}
    if cmd == "pin" and args:
        return {"output": ai.set_pin(args[0], True)}
    if cmd == "unpin" and args:
        return {"output": ai.set_pin(args[0], False)}
    if cmd == "analyze" and args:
        return {"output": ai.analyze_performance(get_settings(), args[0])}
    if cmd == "kill" and args:
        return {"output": kill_bot(args[0])}
    if cmd == "delbot" and args:
        ok = registry.delete_bot(args[0])
        return {"output": f"geloescht: {args[0]}" if ok else f"nicht gefunden: {args[0]}"}
    return {"output": f"Unbekannter Befehl: {raw}\n{_CONSOLE_HELP}"}


# ---------------------------------------------------------------- UI
@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Dizz Trading</h1><p>Dashboard fehlt (static/index.html).</p>")
    html = index.read_text(encoding="utf-8")
    # CSP voll-strikt: per-Request-Nonce an jedes inline <script> (alle 4 öffnen mit exakt "<script>");
    # script-src = 'self' 'nonce-…' OHNE 'unsafe-inline'. 0 Inline-on*-Handler dank C2-Delegation.
    nonce = secrets.token_urlsafe(16)
    html = html.replace("<script>", f'<script nonce="{nonce}">')
    return HTMLResponse(html, headers={"Content-Security-Policy": _TB_CSP_STRICT.format(nonce=nonce)})


# Schlankes UI Builder Tool (netzwerkweites Tool aus 'the world of dizzi/tools', vormals Panel-Bautool)
# zur Bearbeitung der TB-Oberflaeche: nur die zwei bekannten Dateien, kein allgemeiner Static-Server.
# Same-origin noetig, damit "App-UI laden" die echte TB-DOM lesen kann (TB-CSP erlaubt 'self'-Skripte).
# Geteilte Kit-Assets (Single-Source aus packages/ui-kit, via appkit.ui_kit_path) — fuer den
# controls.css-De-Fork. ui-builder-tool bleibt TB-eigen (static/ui-kit).
_SHARED_KIT = {"controls.css", "tokens.css", "collapse.js", "spinfling.js", "clickwave.css", "clickwave.js"}


@app.get("/ui-kit/{fname}")
def ui_kit_tool(fname: str) -> Response:
    if fname in ("ui-builder-tool.html", "ui-builder-tool.js"):
        p = STATIC_DIR / "ui-kit" / fname
    elif fname in _SHARED_KIT:
        from appkit import ui_kit_path
        p = ui_kit_path() / fname
    else:
        raise HTTPException(status_code=404)
    if not p.exists():
        raise HTTPException(status_code=404)
    media = ("text/css; charset=utf-8" if fname.endswith(".css")
             else "text/html; charset=utf-8" if fname.endswith(".html")
             else "text/javascript; charset=utf-8")
    return Response(p.read_text(encoding="utf-8"), media_type=media)
