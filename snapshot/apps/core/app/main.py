"""FastAPI-App des Core-Service.

Start (Entwicklung):
    C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m uvicorn app.main:app
        --host 127.0.0.1 --port 8200 --app-dir core

Das gebaute Frontend (shell/dist) wird, falls vorhanden, unter ``/``
ausgeliefert — gleiches Muster wie beim Trading Bot.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, db, konto_loeschung, panels
from .verzeichnis import rollen as verzeichnis_rollen
from .ai.agenten_routes import router as agenten_router
from .ai.mcp_gateway import router as mcp_gateway_router
from .ai.routes import router as ai_router
from .config import DEFAULT_USER_ID, settings
from .id import store
from .id.routes import _SESSION_COOKIE, router as id_router  # _SESSION_COOKIE: kanonischer SSO-Cookie-Name (kein Literal-Duplikat)

_SHELL_DIST = Path(__file__).resolve().parents[3] / "shell" / "dist"  # Monorepo-Wurzel (apps/core/app -> ../../../shell)


async def _consolidation_tick() -> None:
    """EIN Konsolidierungs-Durchlauf über ALLE Nutzer (per-Nutzer-Fälligkeit, P6.1).
    Aus dem Loop herausgezogen ⇒ testbar. Memory L2 + LLM-Vorschläge + Retention sind
    je Nutzer eigenständig; ``consolidate`` setzt ``last_consolidation`` pro Nutzer.
    Single-User ⇒ Liste ``[dizzi]`` (Verhalten unverändert)."""
    from datetime import datetime, timedelta, timezone

    from .ai import analyst, memory
    for user_id in db.alle_user_ids():
        last = db.setting_get(user_id, "last_consolidation")
        due = last is None or (
            datetime.now(timezone.utc) - datetime.fromisoformat(last)
            > timedelta(hours=24)
        )
        if due:
            await memory.consolidate(user_id)
            await analyst.suggest(user_id)          # 1×/Tag LLM-Vorschläge (Trading-spezifisch)
            await analyst.suggest_netz(user_id)     # KA-M8: 1×/Tag netzweite KPI-Vorschläge (lokal)
            _retention(user_id)                     # Datenhygiene (Review 12.06.)


async def _consolidation_loop() -> None:
    """Nacht-Konsolidierung (Memory L2): 1× täglich JE NUTZER; holt verpasste Läufe
    beim Start nach (PC war aus). Fehler werden geschluckt — der Job darf den Core
    nie beeinträchtigen."""
    while True:
        try:
            await _consolidation_tick()
        except Exception:
            pass
        await asyncio.sleep(3600)  # stündlich prüfen, ob 24 h um sind


def _retention(user_id: str) -> None:
    """Setzt ``aufbewahrung_tage`` (Default 365) im Core durch: Audit-Log und
    gelesene Glocken-Meldungen wachsen sonst unbegrenzt. Gedächtnis (Fakten/
    Episoden/Chat) wird bewusst NICHT angefasst — das verwaltet Memory L1–L4."""
    from datetime import datetime, timedelta, timezone
    tage = int(db.setting_get(user_id, "aufbewahrung_tage", 365) or 365)
    if tage < 1:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=tage)
              ).isoformat(timespec="seconds")
    conn = db.get_conn()
    n_a = conn.execute("DELETE FROM audit_log WHERE user_id=? AND created_at<?",
                       (user_id, cutoff)).rowcount
    n_n = conn.execute("DELETE FROM notices WHERE user_id=? AND created_at<? "
                       "AND read_at IS NOT NULL", (user_id, cutoff)).rowcount
    conn.commit()
    from .ai import observe                       # P1.5: Beobachtungs-Retention hier (statt pro Insert)
    n_o = observe.observations_retention(user_id)
    if n_a or n_n or n_o:
        db.audit(user_id, "system", "retention_gelaufen",
                 {"tage": tage, "audit": n_a, "notices": n_n, "observations": n_o})


async def _observer_loop() -> None:
    """L4-Beobachter: periodische Schnappschüsse der Panel-KI-Zustände
    (Trading Bot via MCP-Tools). Fehler dürfen den Core nie beeinträchtigen."""
    from .ai import analyst, observe
    await asyncio.sleep(60)  # Core erst sauber hochfahren lassen
    while True:
        try:
            if await observe.observe_tradingbot(DEFAULT_USER_ID):
                analyst.analyze(DEFAULT_USER_ID)  # Regeln direkt nach jedem Schnappschuss
            # SYNC-HTTP (bis zu n Apps × Timeout) gehört NICHT in den Event-Loop —
            # sonst hängen währenddessen alle Requests inkl. Dizzi-ID-Login.
            await asyncio.to_thread(observe.observe_contract_apps, DEFAULT_USER_ID)
            analyst.analyze_netz(DEFAULT_USER_ID)  # KA-M8: Delta-Regeln je App nach dem Schnappschuss
        except Exception:
            pass
        await asyncio.sleep(observe.OBSERVE_INTERVAL_S)


async def _defense_verbund_loop() -> None:
    """F-DEF2: Dizzi = SOC-Dach — sammelt im Minuten-Takt die Sperren aller
    Vertrags-Apps und verteilt sie an alle (Föderations-Immunität). Bewusst
    schneller als der L4-Beobachter: Abwehr-Signale dürfen nicht 30 min warten.
    Fehler dürfen den Core nie beeinträchtigen."""
    from . import defense_hub
    await asyncio.sleep(20)
    while True:
        try:
            # SYNC-HTTP im Thread halten (s. _observer_loop): der Minuten-Takt
            # darf den Event-Loop nie blockieren, auch wenn Apps offline sind.
            await asyncio.to_thread(defense_hub.tick, DEFAULT_USER_ID)
        except Exception:
            pass
        await asyncio.sleep(60)


async def _health_watch_loop() -> None:
    """Core-Health-Watch (R-4/R-5): pingt im Minuten-Takt die Vertrags-Apps +
    Ollama (geteilter Single-Point aller App-KIs), meldet Zustands-Wechsel an die
    Glocke und reanimiert Ollama bei Ausfall. SYNC-Pings im Thread (s.
    _observer_loop). Fehler dürfen den Core nie beeinträchtigen."""
    from .ai import health_watch
    await asyncio.sleep(45)  # Core erst hochfahren lassen
    while True:
        try:
            await asyncio.to_thread(health_watch.tick, DEFAULT_USER_ID)
            await asyncio.to_thread(panels.discover_contract_apps)  # KA-M2: fehlende Vertrags-Apps auto-anbinden
        except Exception:
            pass
        await asyncio.sleep(health_watch.WATCH_INTERVAL_S)


async def _regie_pull(quelle_app: str, cursor: int) -> "list[dict[str, Any]] | None":
    """Ereignis-Pull einer Quell-App ab ``cursor`` (docs/83 §2: ``GET /api/ereignisse``,
    localhost/SSO). Nicht angedockt/unerreichbar/Timeout ⇒ ``None`` (Quelle offline —
    der Scheduler überspringt sie ehrlich, nie still leer)."""
    base = panels.contract_apps().get(quelle_app)
    if not base:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{base}/api/ereignisse",
                            params={"seit": cursor, "limit": 200})
            r.raise_for_status()
            return list(r.json().get("eintraege", []))
    except Exception:
        return None


async def _regie_loop() -> None:
    """Agenten-Regie-Scheduler (RG-3b, docs/83 §2/§3): zieht im Tick-Takt Ereignisse
    aus den Quell-Apps, plant Zündungen (Cursor+Zündung in EINER Tx) und startet
    budgetierte Läufe — NUR wenn der Master-Schalter ``agenten_regie_aktiv`` an ist
    (Default AUS = Not-Aus: schauen, Cursor rückt vor, aber nicht zünden). Der
    Scheduler EXISTIERT immer, zündet nur gegated; ohne gepushte Abos tut er nichts.
    Fehler dürfen den Core nie beeinträchtigen (wie jeder Hintergrund-Loop)."""
    from .ai import agenten_regie as regie
    from .ai.agenten_routes import lauf_aus_regie
    await asyncio.sleep(50)  # Core + Quell-Apps erst sauber hochfahren lassen

    async def _run(snapshot: dict[str, Any], auftrag: str, sensitive: bool) -> str:
        return await lauf_aus_regie(DEFAULT_USER_ID, snapshot, auftrag, sensitive=sensitive)

    while True:
        try:
            aktiv = bool(db.setting_get(DEFAULT_USER_ID, regie.SETTING_AKTIV, False))
            karte = regie.regie_karte_holen(DEFAULT_USER_ID)
            if karte.get("abos"):          # nichts zu tun, solange keine Abos gepusht sind
                await regie.tick(DEFAULT_USER_ID, ist_aktiv=aktiv,
                                 pull_fn=_regie_pull, run_fn=_run)
        except Exception:
            pass
        tick_s = db.setting_get(DEFAULT_USER_ID, regie.SETTING_TICK_S, regie.TICK_S_DEFAULT)
        await asyncio.sleep(max(1, int(tick_s or regie.TICK_S_DEFAULT)))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db.get_conn()  # legt Schema an
    db.audit(DEFAULT_USER_ID, "system", "core_started", {"version": __version__})
    tasks = [asyncio.create_task(_consolidation_loop()),
             asyncio.create_task(_observer_loop()),
             asyncio.create_task(_defense_verbund_loop()),
             asyncio.create_task(_health_watch_loop()),
             asyncio.create_task(_regie_loop())]
    # Weckwort-Lauschen automatisch nachstarten, wenn der Nutzer es aktiviert
    # hat (opt-in, Mikrofon). Fehlt das Mikro/sounddevice, ruht es fail-safe.
    if db.setting_get(DEFAULT_USER_ID, "voice_wake_aktiv"):
        try:
            from .ai.routes import start_wake_from_settings
            start_wake_from_settings()
        except Exception:
            pass
    yield
    from .ai import wakeword
    wakeword.daemon.stop()
    for t in tasks:
        t.cancel()


app = FastAPI(title=settings.app_name, version=__version__, lifespan=_lifespan)

# Local-Guard (Härtung H1, docs/18): Host-Allowlist + Origin-Prüfung — schützt
# die localhost-APIs (inkl. Dizzi-ID!) vor DNS-Rebinding/Browser-CSRF.
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]  # Monorepo-Wurzel (apps/core/app -> ../../..)
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))
from appkit.guard import install_local_guard  # noqa: E402
from appkit import ui_kit_path
install_local_guard(app)
# M-4 (docs/20 + docs/36): Der Hub bekam bisher WEDER Defense NOCH CSP — anders als jede
# create_app-App —, obwohl er den SSO-/Dizzi-ID-Cookie hält und das MCP-Gateway trägt.
# Reihenfolge exakt wie create_app (Guard → Defense → Header → CSP): spätere Registrierung
# = äußere Middleware ⇒ Header/CSP stempeln auch Defense-/Guard-Abweisungen, während die
# Defense-Sensorik den Request weiterhin als erstes sieht. Defense bekommt das Core-eigene
# db-Modul: es bietet get_conn/audit/setting_get — genau die Trias, die install_defense
# nutzt — und DEFAULT_USER='dizzi' deckt sich mit dem Core-Nutzer, sodass das Aktiv-Setting
# (defense_aktiv/-autonomie/-hops) greift. registry=None: die S1–S3-Automatik + der
# Cockpit-Lockdown reichen; die S4/S5-HITL-Vorschläge braucht der Hub nicht (Core hat keine
# appkit-Aktions-Registry).
from appkit.defense import install_defense  # noqa: E402
install_defense(app, db, "core")  # Defense-Tabellen werden je Verbindung in db.get_conn() gesichert
from appkit.headers import install_security_headers  # noqa: E402  (H-2, docs/25)
install_security_headers(app)  # nach Guard+Defense ⇒ äußerster Response-Stempel, jede Antwort
# CSP NUR Baseline (strikt=False): Core liefert die Shell-SPA (shell/dist, React) aus —
# strikte Nonce-CSP bräche die Bundles (kein Nonce). Baseline blockt externe Skripte/<object>/
# <base>/Framing, erlaubt aber 'unsafe-inline'; alle Shell-Fetches sind self (auditiert:
# shell/src/api.ts nur relative /api-Pfade, kein Cross-Origin/SSE) ⇒ connect-src 'self' trägt.
# style/font_extra: die Shell lädt Chakra Petch/Orbitron von Google Fonts (shell/index.html
# Z.19-22) — ohne diese zwei Origins fiele die Optik unter enforce auf System-Fonts zurück
# (Feel-Änderung ohne David-Go). Ausnahme entfällt, sobald die Fonts self-hosted sind
# (P4-Empfehlung); Skript-Quellen bleiben ausnahmslos zu.
from appkit.csp import install_csp  # noqa: E402
install_csp(app, mode="enforce", strikt=False,
            style_extra=["https://fonts.googleapis.com"],
            font_extra=["https://fonts.gstatic.com"])

app.include_router(ai_router)
app.include_router(id_router)  # Dizzi-ID: OIDC-Provider des Netzwerks (K1)
app.include_router(mcp_gateway_router)  # Remote-MCP-Gateway: 1 Verbindung → ganzes Netzwerk (docs/30 §H1)
app.include_router(agenten_router)  # Agenten-Regie: Ausführungs-API (Z4.2-D, docs/63 §3)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__, "ts": db.now_iso()}


@app.get("/api/health/watch")
def health_watch_status() -> dict[str, Any]:
    """Core-Health-Watch (R-4/R-5): zuletzt bekannter Zustand je Ziel
    (Vertrags-Apps + Ollama). Leer, bis der erste Wächter-Lauf durch ist."""
    from .ai import health_watch
    return {"ziele": health_watch.status(), "ts": db.now_iso()}


@app.get("/api/panels")
def list_panels() -> list[panels.PanelManifest]:
    return panels.manifests()


@app.get("/api/panels/{panel_id}/stats")
def panel_stats(panel_id: str) -> dict[str, Any]:
    stats = panels.stats_for(panel_id)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"Unbekanntes Panel: {panel_id}")
    return stats


class SettingIn(BaseModel):
    key: str
    value: Any


# KA-N1: Geheimnis-artige Settings-Keys werden beim Lesen deny-by-default maskiert —
# auch wenn /api/settings localhost-only ist (Defense-in-Depth); Schreiben (PUT) bleibt roh.
_GEHEIM_KEY_MUSTER = ("token", "secret", "key", "passwort", "password")


def _key_ist_geheim(key: str) -> bool:
    k = key.lower()
    return any(m in k for m in _GEHEIM_KEY_MUSTER)


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    """Settings des Nutzers; Geheimnis-artige Keys (token/secret/key/passwort) kommen
    maskiert (``•••``, wenn gesetzt) — die echten Werte verlassen die DB nie über GET."""
    roh = db.settings_all(DEFAULT_USER_ID)
    return {k: ("•••" if (_key_ist_geheim(k) and v not in (None, "")) else v)
            for k, v in roh.items()}


@app.put("/api/settings")
def put_setting(body: SettingIn) -> dict[str, Any]:
    db.setting_put(DEFAULT_USER_ID, body.key, body.value)
    db.audit(DEFAULT_USER_ID, "user", "setting_changed", {"key": body.key})
    return {"ok": True, "key": body.key}


@app.get("/api/audit")
def get_audit(limit: int = 50) -> list[dict[str, Any]]:
    return db.audit_recent(DEFAULT_USER_ID, limit=min(limit, 500))


@app.get("/api/verzeichnis/rollen")
def get_verzeichnis_rollen(zum: str | None = None) -> dict[str, Any]:
    """Verzeichnis-KEIM (§B4/D2): die Subjekt-Quelle der aktuellen Identität —
    Rollen + Bereiche, die ``charta.antrag_bauen`` speisen (kein Client liefert je
    eigene Attribute, CH-5). Leer bis Rollen gesetzt sind ⇒ Charta deny-default
    (fail-closed, ehrlich). ``zum`` (ISO) = Replay-Zeitpunkt."""
    return verzeichnis_rollen.rollen_von(DEFAULT_USER_ID, zum=zum)


@app.get("/api/verzeichnis/belegschaft")
def get_verzeichnis_belegschaft(edition: str = "bizzi",
                                zum: str | None = None) -> list[dict[str, Any]]:
    """Basis des Erreichbarkeits-Enumerators (CH-14): Rollen/Bereiche je Identität
    (Assurance/Frische = best case) — speist die „tote Artikel"-/SoD-Berichte."""
    return verzeichnis_rollen.belegschaft(edition=edition, zum=zum)


@app.get("/api/sicherheit/lage")
def sicherheit_lage() -> dict[str, Any]:
    """SF-1 (docs/82 §3): Sicherheits-Ampel des Core/Hubs — reine Lese-/Status-
    anzeige (localhost-guarded, wie /api/health). Zeigt an, ändert nichts. Core
    hält IdP-Schlüssel + Netz-Orchestrierung ⇒ Sensibilität 'hoch' fürs Urteil."""
    from appkit.security_posture import AUTOLOCK_SETTING, pruefe_lage
    autolock = db.setting_get(DEFAULT_USER_ID, AUTOLOCK_SETTING, None)
    return pruefe_lage("core", settings.db_path, settings.data_dir, "hoch",
                       autolock_minuten=autolock)


@app.get("/sicherheit", include_in_schema=False)
def sicherheit_seite() -> FileResponse:
    """SF-1 (docs/82 §3): geführte Sicherheits-Ampel-Seite (Einrichtungs-Assistent
    v1). Self-contained aus ui-kit; liest /api/sicherheit/lage relativ, zeigt nur an.
    Läuft unter Cores Baseline-CSP (inline-Style/Script bei strikt=False erlaubt)."""
    p = ui_kit_path() / "sicherheit.html"
    if not p.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


# --- Konto-Löschung (KA-H1 / DSGVO Art. 17) ----------------------------------
class KontoLoeschenIn(BaseModel):
    """Re-Auth-Gate der Löschung (KA-H1/A2, Option A — lokal-single-user): GENAU EIN
    Credential-Pfad pro Request. Ist ``passwort`` gesetzt, zählt nur der Passwort-Pfad,
    sonst der TOTP-Pfad — saubere H4-Lockout-Buchführung, kein Doppel-Fehlversuch."""
    passwort: str | None = None
    totp: str | None = None


@app.post("/api/account/loeschen")
def account_loeschen(body: KontoLoeschenIn, response: Response) -> dict[str, Any]:
    """DSGVO-Art.-17-Konto-Löschung mit EXPLIZITER Re-Auth (Option A): verlangt das
    lokale Passwort ODER einen frischen TOTP-Code IM REQUEST. Der Core IST der IdP und
    kann den Credential-Beweis an der Quelle verlangen (auth_time = jetzt — die stärkste
    Form der appkit-„Frische", ohne neue /api/-Auth-Schicht oder Session-Umbau).
    Fail-closed: fehlendes/falsches Credential ⇒ 403, generisch (kein Leak, ob gesetzt
    oder falsch); der H4-Lockout greift auf beiden Pfaden. Erst NACH bestandenem Gate
    räumt die getestete Engine ``konto_loeschung.loesche_konto`` (Kaskade + harte
    id_/agent-Räumung + RAG-Purge + Löschbeleg im behaltenen audit_log). Der SSO-Cookie
    wird zuletzt gelöscht — die Session-Row ist da schon hart weg (reine Client-Hygiene;
    die Antwort ist noch zustellbar, erst der Folge-Request findet keine Session mehr)."""
    if body.passwort:
        ok = store.check_local_password(body.passwort)
    elif body.totp:
        ok = store.totp_verify(body.totp)
    else:
        ok = False
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Re-Auth fehlgeschlagen — lokales Passwort oder frischer TOTP-Code nötig.")
    ergebnis = konto_loeschung.loesche_konto(DEFAULT_USER_ID)  # Audit schreibt die Engine selbst
    response.delete_cookie(_SESSION_COOKIE, path="/")          # Row schon hart gelöscht — reine Client-Hygiene
    return ergebnis


class EventIn(BaseModel):
    """Event-Push einer Vertrags-App (K4): landet in Glocke + L4-Gedächtnis."""
    app: str
    severity: str  # 'info' | 'warn' | 'vorschlag'
    title: str
    detail: dict[str, Any] = {}


class AppFrageIn(BaseModel):
    """Mini-Dizzi-Verbund (Vertrag 1.5): das zentrale Dizzi leitet eine Frage
    an die KI einer angedockten App weiter (``frage_app_ki``)."""
    frage: str


@app.post("/api/events")
def post_event(body: EventIn) -> dict[str, Any]:
    if body.severity not in ("info", "warn", "vorschlag"):
        raise HTTPException(status_code=400, detail="severity: info|warn|vorschlag")
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), DEFAULT_USER_ID, body.app, body.severity, body.title,
         json.dumps(body.detail, ensure_ascii=False), db.now_iso()))
    conn.commit()
    from .ai import observe
    observe.record(DEFAULT_USER_ID, body.app,
                   {"event": body.title, "severity": body.severity, **body.detail})
    db.audit(DEFAULT_USER_ID, "system", "app_event_empfangen",
             {"app": body.app, "severity": body.severity})
    return {"ok": True}


@app.post("/api/ki/app/{app_id}")
def frage_app_ki(app_id: str, body: AppFrageIn) -> dict[str, Any]:
    """Mini-Dizzi-Verbund (Vertrag 1.5): „im Netzwerk lauscht nur das zentrale
    Dizzi" — diese Route reicht die erkannte Anfrage an die KI der angedockten
    App weiter (deren ``POST /api/ki/frage``). Unbekannte App ⇒ 404; App offline
    ⇒ ehrlicher Hinweis statt Absturz."""
    base = panels.contract_apps().get(app_id)
    if base is None:
        raise HTTPException(status_code=404, detail=f"App nicht angedockt: {app_id}")
    try:
        import httpx
        r = httpx.post(f"{base}/api/ki/frage", json={"frage": body.frage}, timeout=90.0)
        antwort = r.json() if r.status_code == 200 else {
            "antwort": f"{app_id} antwortet nicht (HTTP {r.status_code}).",
            "quelle": "fehler"}
    except Exception:
        antwort = {"antwort": f"{app_id} ist gerade nicht erreichbar.",
                   "quelle": "offline"}
    db.audit(DEFAULT_USER_ID, "ki", "mini_dizzi_weiterleitung",
             {"app": app_id, "quelle": antwort.get("quelle")})
    return {"app": app_id, **antwort}


class QuervRelayIn(BaseModel):
    """Querverbindungs-Umschlag (Phase 2, docs/11 §5c / docs/26): ein Element,
    das eine App an eine Ziel-Archiv-App weiterreicht. Spiegelt Memorys Empfangs-
    Modell (``_QuervIn``)."""
    titel: str = ""
    inhalt: str = ""
    quelle: str = ""           # Referenz/URL beim Absender
    app: str = ""              # absendende App-id
    tags: list[str] = []
    ordner: str = ""           # Ziel-Ordner-Pfad (Default beim Ziel = app)
    ref: str | None = None     # externer Idempotenz-Schlüssel
    sensibel: bool = False     # markiert sensibel ⇒ Ziel-KI lokal_only
    strom: str = ""            # Strom-/Inhalts-Typ (Archiv-Regel je app,strom — docs/26 §8)
    explizit: bool = False     # Nutzer-Zuruf „archivieren" ⇒ schlägt jede Regel


class KalenderRelayIn(BaseModel):
    """Zweiter Vertragstyp (V5, docs/26): ein Kalender-Event (z. B. aus einer Mail-
    Einladung), das eine App an eine Ziel-App MIT Kalender weiterreicht (Default
    Dizz Plans). Anderer Umschlag als das Memory-Archiv (``QuervRelayIn``)."""
    titel: str = ""
    beginn: str = ""           # ISO-8601 (Start)
    ende: str = ""
    ganztags: bool = False
    ort: str = ""
    beschreibung: str = ""
    app: str = ""              # absendende App-id
    quelle: str = ""           # Referenz/URL beim Absender
    ref: str | None = None     # Idempotenz-Schlüssel (→ extern_id beim Ziel)


class VerknuepfungRelayIn(BaseModel):
    """Dritter Vertragstyp (V15, docs/26 §12): ein bidirektionaler Beleg-Link.
    Die treibende App (z. B. Money) hält ihre Vorwärts-Referenz selbst und teilt
    dem Ziel (z. B. Admin) mit, dass ``von_ref`` auf dessen ``ziel_ref`` zeigt —
    das Ziel legt eine Rück-Referenz an. Nur Daten, kein Aktions-Auslöser."""
    von_app: str = ""          # absendende App-id (z. B. finanzen)
    von_ref: str = ""          # Referenz beim Absender (z. B. finanzen:buchung:42)
    von_titel: str = ""        # menschenlesbarer Titel der Quelle (z. B. Buchungstext)
    ziel_ref: str = ""         # Referenz beim Ziel (z. B. admin:dokument:7)
    notiz: str = ""
    aktion: str = "anlegen"    # anlegen | loesen (Storno/Beleg-Entfernen ⇒ Rück-Ref räumen)


@app.post("/api/querverbindung/{ziel}")
def querverbindung_relay(ziel: str, body: QuervRelayIn) -> dict[str, Any]:
    """Querverbindungs-Drehscheibe (Phase 2, docs/11 §5c, Transport = über Core):
    reicht ein Element einer App an die ZIEL-App weiter (deren ``POST /api/
    querverbindung/archivieren``; Default-Ziel ist Dizz Memory als zentrales
    Archiv) und auditiert den Fluss zentral. Ziel nicht angedockt ⇒ 404; Ziel
    offline ⇒ ehrlicher Hinweis statt Absturz. Auth: localhost-Guard + Single-
    User (kein Token) — wie Mini-Dizzi/Defense-Hub."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    umschlag = {"titel": body.titel, "inhalt": body.inhalt, "quelle": body.quelle,
                "app": body.app, "tags": body.tags, "ordner": body.ordner,
                "ref": body.ref, "sensibel": body.sensibel,
                "strom": body.strom, "explizit": body.explizit}
    try:
        import httpx
        r = httpx.post(f"{base}/api/querverbindung/archivieren",
                       json=umschlag, timeout=10.0)
        ergebnis = r.json() if r.status_code == 200 else {
            "ok": False, "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"}
    except Exception:
        ergebnis = {"ok": False, "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_relay",
             {"von": body.app or "?", "ziel": ziel, "ref": body.ref,
              "strom": body.strom, "explizit": body.explizit,
              "sensibel": body.sensibel, "status": ergebnis.get("status", "fehler")})
    return {"ziel": ziel, **ergebnis}


@app.post("/api/querverbindung/{ziel}/kalender")
def querverbindung_kalender_relay(ziel: str, body: KalenderRelayIn) -> dict[str, Any]:
    """Querverbindungs-Drehscheibe für den ZWEITEN Vertragstyp (V5, docs/26):
    reicht ein Kalender-Event an die ZIEL-App mit Kalender weiter (deren ``POST
    /api/querverbindung/kalender``; Default Dizz Plans) und auditiert zentral.
    Additiv zum Archiv-Relay (``/api/querverbindung/{ziel}`` → ``/archivieren``)."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    umschlag = {"titel": body.titel, "beginn": body.beginn, "ende": body.ende,
                "ganztags": body.ganztags, "ort": body.ort,
                "beschreibung": body.beschreibung, "app": body.app,
                "quelle": body.quelle, "ref": body.ref}
    try:
        import httpx
        r = httpx.post(f"{base}/api/querverbindung/kalender", json=umschlag, timeout=10.0)
        ergebnis = r.json() if r.status_code == 200 else {
            "ok": False, "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"}
    except Exception:
        ergebnis = {"ok": False, "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_kalender_relay",
             {"von": body.app or "?", "ziel": ziel, "ref": body.ref,
              "titel": body.titel, "status": ergebnis.get("status", "fehler")})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/suche")
def querverbindung_suche_relay(ziel: str, q: str = "", semantisch: bool = False,
                               limit: int = 8) -> dict[str, Any]:
    """RÜCK-LESE-Drehscheibe (das „↔" der Querverbindungen V5–V11, docs/26 §10.1):
    fragt das zentrale Archiv (Default Dizz Memory) ab und auditiert zentral.
    ``semantisch=False`` ⇒ Memorys ``GET /api/suche`` (FTS5, Param ``limit``);
    ``semantisch=True`` ⇒ ``GET /api/suche/semantisch`` (RAG, Param ``k``). Ziel
    nicht angedockt ⇒ 404; Ziel offline ⇒ ehrlicher Hinweis (leere Treffer) statt
    Absturz. Gegenstück zum Archiv-Relay (``POST …/{ziel}`` → ``/archivieren``)."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    pfad = "/api/suche/semantisch" if semantisch else "/api/suche"
    param = {"q": q, ("k" if semantisch else "limit"): limit}
    try:
        import httpx
        r = httpx.get(f"{base}{pfad}", params=param, timeout=10.0)
        treffer = r.json() if r.status_code == 200 else []
        ergebnis: dict[str, Any] = (
            {"ok": True, "treffer": treffer, "anzahl": len(treffer)}
            if r.status_code == 200 else
            {"ok": False, "treffer": [],
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "treffer": [],
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_suche_relay",
             {"ziel": ziel, "q": q, "semantisch": semantisch,
              "anzahl": ergebnis.get("anzahl", 0)})
    return {"ziel": ziel, **ergebnis}


@app.post("/api/querverbindung/{ziel}/verknuepfung")
def querverbindung_verknuepfung_relay(ziel: str, body: VerknuepfungRelayIn) -> dict[str, Any]:
    """Querverbindungs-Drehscheibe für den DRITTEN Vertragstyp (V15, docs/26 §12):
    legt beim ZIEL eine Rück-Referenz an (bidirektionaler Beleg-Link) und auditiert
    zentral. Ziel = App-id (Default Dizz Admin). Additiv zu Archiv- + Kalender-Relay."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    umschlag = {"von_app": body.von_app, "von_ref": body.von_ref,
                "von_titel": body.von_titel, "ziel_ref": body.ziel_ref,
                "notiz": body.notiz, "aktion": body.aktion}
    try:
        import httpx
        r = httpx.post(f"{base}/api/querverbindung/verknuepfung", json=umschlag, timeout=10.0)
        ergebnis = r.json() if r.status_code == 200 else {
            "ok": False, "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"}
    except Exception:
        ergebnis = {"ok": False, "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_verknuepfung_relay",
             {"von": body.von_app or "?", "ziel": ziel, "von_ref": body.von_ref,
              "ziel_ref": body.ziel_ref, "status": ergebnis.get("status", "fehler")})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/belege")
def querverbindung_belege_relay(ziel: str, q: str = "", limit: int = 50) -> dict[str, Any]:
    """LOOKUP-Drehscheibe (V15, docs/26 §12): holt die verknüpfbaren Belege/Dokumente
    der ZIEL-App (Default Dizz Admin) über deren ``GET /api/belege`` und auditiert
    zentral. So füllt die treibende App (Money) ihre Beleg-Auswahl. Ziel nicht
    angedockt ⇒ 404; Ziel offline ⇒ ehrlicher Hinweis (leere Liste)."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        r = httpx.get(f"{base}/api/belege", params={"q": q, "limit": limit}, timeout=10.0)
        belege = r.json() if r.status_code == 200 else []
        ergebnis: dict[str, Any] = (
            {"ok": True, "belege": belege} if r.status_code == 200 else
            {"ok": False, "belege": [],
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "belege": [],
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_belege_relay",
             {"ziel": ziel, "q": q, "anzahl": len(ergebnis.get("belege", []))})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/euer")
def querverbindung_euer_relay(ziel: str, jahr: int = 0) -> dict[str, Any]:
    """LESE-Drehscheibe (V16, docs/26 / docs/11 §5c): zieht die EÜR-artige Jahres-
    Auswertung der ZIEL-Finanz-App (Default Dizz Money, ``GET /api/steuer/jahr`` mit
    ``nur_steuer=1``) und auditiert zentral — die Grundlage der Leading-EÜR-Ausgaben-
    seite (Aggregation statt Doppeln). Ziel nicht angedockt ⇒ 404; offline ⇒ ehrlich leer."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        r = httpx.get(f"{base}/api/steuer/jahr",
                      params={"jahr": jahr, "nur_steuer": 1}, timeout=10.0)
        ergebnis: dict[str, Any] = (
            {"ok": True, "euer": r.json()} if r.status_code == 200 else
            {"ok": False, "euer": {},
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "euer": {},
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_euer_relay",
             {"ziel": ziel, "jahr": jahr, "ok": ergebnis.get("ok")})
    return {"ziel": ziel, **ergebnis}


# ── A5: Bereichs-Querverbindungen V17/V18/V19 (docs/34) ───────────────────────
# Drei read-only LESE-Drehscheiben, die die Bereichs-/Kategorie-Achse von Dizz Admin
# an Money/Management/Memory anbinden — Aggregat statt Doppeln, Außenwirkung bleibt
# in der Quell-App (HITL). App-seitige Aggregations-Endpunkte = A5-Phase-2 (je App).
@app.get("/api/querverbindung/{ziel}/finanzspur")
def querverbindung_finanzspur_relay(ziel: str, kontext: str = "", jahr: int = 0, kanon: str = "") -> dict[str, Any]:
    """V17 (docs/34): zieht die per-Bereich-Finanzspur der ZIEL-Finanz-App (Default Dizz
    Money, ``GET /api/bereich/finanzspur`` — Einnahmen/Ausgaben/Saldo je ``kontext`` =
    ``bereich.money_kontext``) und auditiert zentral. So zeigt Dizz Admins Bereichs-
    Cockpit die Finanzspur eines Bereichs. Ziel nicht angedockt ⇒ 404; offline ⇒ leer."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        params: dict[str, Any] = {"kontext": kontext, "jahr": jahr}
        if kanon:                                  # docs/67 §3.3 — nur wenn gesetzt (byte-gleich sonst)
            params["kanon"] = kanon
        r = httpx.get(f"{base}/api/bereich/finanzspur", params=params, timeout=10.0)
        ergebnis: dict[str, Any] = (
            {"ok": True, "finanzspur": r.json()} if r.status_code == 200 else
            {"ok": False, "finanzspur": {},
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "finanzspur": {},
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_finanzspur_relay",
             {"ziel": ziel, "kontext": kontext, "jahr": jahr, "kanon": kanon, "ok": ergebnis.get("ok")})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/bereich-social")
def querverbindung_bereich_social_relay(ziel: str, kontext: str = "", kanon: str = "") -> dict[str, Any]:
    """V18 (docs/34): zieht die per-Bereich-Social-Aktivität der ZIEL-App (Default Dizz
    Management, ``GET /api/bereich/social`` — geplante/veröffentlichte Posts, aktive Bots
    je ``kontext``) und auditiert zentral. Read-only — Veröffentlichen bleibt Management-
    HITL. Ziel nicht angedockt ⇒ 404; offline ⇒ leer."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        params: dict[str, Any] = {"kontext": kontext}
        if kanon:
            params["kanon"] = kanon
        r = httpx.get(f"{base}/api/bereich/social", params=params, timeout=10.0)
        ergebnis: dict[str, Any] = (
            {"ok": True, "social": r.json()} if r.status_code == 200 else
            {"ok": False, "social": {},
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "social": {},
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_bereich_social_relay",
             {"ziel": ziel, "kontext": kontext, "kanon": kanon, "ok": ergebnis.get("ok")})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/kategorie")
def querverbindung_kategorie_relay(ziel: str, ordner: str = "", limit: int = 12, kanon: str = "") -> dict[str, Any]:
    """V19 (docs/34): zieht die Notizen einer Memory-Kategorie/eines Ordners (= ``bereich.
    memory_ref``) aus der ZIEL-App (Default Dizz Memory, ``GET /api/kategorie?ordner=``)
    und auditiert zentral. So zeigt Dizz Admins Bereichs-Cockpit das „Wissen dieses
    Bereichs". Sensibel — read-only. Ziel nicht angedockt ⇒ 404; offline ⇒ leer."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        params: dict[str, Any] = {"ordner": ordner, "limit": limit}
        if kanon:
            params["kanon"] = kanon
        r = httpx.get(f"{base}/api/kategorie", params=params, timeout=10.0)
        treffer = r.json() if r.status_code == 200 else []
        ergebnis: dict[str, Any] = (
            {"ok": True, "notizen": treffer, "anzahl": len(treffer)}
            if r.status_code == 200 else
            {"ok": False, "notizen": [],
             "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"})
    except Exception:
        ergebnis = {"ok": False, "notizen": [],
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_kategorie_relay",
             {"ziel": ziel, "ordner": ordner, "kanon": kanon, "anzahl": ergebnis.get("anzahl", 0)})
    return {"ziel": ziel, **ergebnis}


@app.get("/api/querverbindung/{ziel}/kanon-status")
def querverbindung_kanon_status_relay(ziel: str) -> dict[str, Any]:
    """BER-1 (docs/67 §3.3/§3.4): zieht den kanon-status-Feed der ZIEL-App
    (GET /api/bereiche/kanon-status) für Admins Broken-Link-Wächter und auditiert
    zentral. Ziel nicht angedockt ⇒ 404; offline ⇒ ehrlich leer (Kante 'unbekannt')."""
    base = panels.contract_apps().get(ziel)
    if base is None:
        raise HTTPException(status_code=404, detail=f"Ziel nicht angedockt: {ziel}")
    try:
        import httpx
        r = httpx.get(f"{base}/api/bereiche/kanon-status", timeout=10.0)
        if r.status_code == 200:
            body = r.json()
            ergebnis: dict[str, Any] = {"ok": True, "bereiche": body.get("bereiche", []),
                                        "anker_extra": body.get("anker_extra", {})}
        else:
            ergebnis = {"ok": False, "bereiche": [], "anker_extra": {},
                        "fehler": f"{ziel} antwortet nicht (HTTP {r.status_code})"}
    except Exception:
        ergebnis = {"ok": False, "bereiche": [], "anker_extra": {},
                    "fehler": f"{ziel} ist gerade nicht erreichbar"}
    db.audit(DEFAULT_USER_ID, "system", "querverbindung_kanon_status_relay",
             {"ziel": ziel, "ok": ergebnis.get("ok"), "anzahl": len(ergebnis.get("bereiche", []))})
    return {"ziel": ziel, **ergebnis}


if _SHELL_DIST.is_dir():  # Frontend nur ausliefern, wenn gebaut
    app.mount("/assets", StaticFiles(directory=_SHELL_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        # no-cache: index.html IMMER revalidieren (ETag), damit nach einem Shell-Rebuild
        # sofort die neuen gehashten Bundles geladen werden. Sonst hält der Browser eine alte
        # index.html → altes Bundle → veralteter Code (war die Ursache der „alten Hitbox").
        return FileResponse(_SHELL_DIST / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.png", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(_SHELL_DIST / "favicon.png")

    # Schlankes /ui-kit-Fenster (kein allgemeiner Static-Server, Whitelist): UI Builder Tool
    # (netzwerkweites Tool aus tools/) zur Bearbeitung der Core-Oberfläche + DzHalter-Andock-
    # Schale (float_dock, Spin-Physik v4.4) für die Shell-Floats. Same-origin nötig (UI Builder
    # liest die echte Core-DOM; externe Skripte laufen unter script-src 'self').
    @app.get("/ui-kit/{fname}", include_in_schema=False)
    def ui_kit_tool(fname: str) -> FileResponse:
        if fname not in ("ui-builder-tool.html", "ui-builder-tool.js",
                         "float_dock.js", "float_dock.css"):
            raise HTTPException(status_code=404)
        p = ui_kit_path() / fname
        if not p.is_file():
            raise HTTPException(status_code=404)
        media = ("text/html; charset=utf-8" if fname.endswith(".html")
                 else "text/css; charset=utf-8" if fname.endswith(".css")
                 else "text/javascript; charset=utf-8")
        # no-cache wie die App-seitigen Kit-Routen: Browser revalidiert via ETag (kein ?v=-Bump).
        return FileResponse(p, media_type=media, headers={"Cache-Control": "no-cache"})

    # Netz-Ansichten (Gesamtsystem-Karte + Projektplan/PROJEKT_STAND) aus `_netzwerk/` same-origin
    # ausliefern, damit sie aus der Shell-Kopfzeile verlinkbar sind. Whitelist (kein allgemeiner
    # Static-Server); beide HTML sind self-contained, ihre gegenseitigen Relativ-Links bleiben unter /netz/ gültig.
    @app.get("/netz/{fname}", include_in_schema=False)
    def netz_ansicht(fname: str) -> FileResponse:
        if fname not in ("SYSTEM_KARTE.html", "PROJEKT_STAND.html"):
            raise HTTPException(status_code=404)
        p = _repo_root / "_netzwerk" / fname
        if not p.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(p, media_type="text/html; charset=utf-8",
                            headers={"Cache-Control": "no-cache"})
