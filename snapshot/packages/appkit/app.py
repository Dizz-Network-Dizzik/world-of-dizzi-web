"""App-Fabrik + einbettbarer Vertrags-Router.

Zwei Einstiege (K6 machte den zweiten nötig):
- ``create_app(...)``   — NEUE Apps: komplette vertragskonforme FastAPI-App.
- ``contract_router(...)`` — BESTANDS-Apps (z. B. Dizz Trading): der Vertrag
  als APIRouter zum Einhängen in eine existierende App. Über ``include`` lassen
  sich Endpoints auslassen, die die Bestands-App bereits selbst anbietet
  (Kollisionen; die Abweichung gehört ins Manifest/die App-Doku dokumentiert).

Eine neue App liefert nur: Manifest, Datenbank (mit Domänen-Schema),
``summary_fn`` und eigene Router — alles Vertragliche kommt aus EINER Stelle.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterable

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import CONTRACT_VERSION
from .actions import (ActionRegistry, decide, listing, migriere_actions_inbox,
                      propose)
from .auth import LEVELS, DEFAULT_USER_ID, UserContext, current_user
from .db import Database, now_iso
from .manifest import AppManifest
from .settings_core import MASK, SettingsSchema, make_schema
from .summary import Summary, normalize
from .vault import Vault

if TYPE_CHECKING:  # nur für Annotationen — kein Laufzeit-Import (docs/83 §1)
    from .ereignis_spine import EreignisTypRegister

SummaryFn = Callable[[], Any]  # liefert list[Kpi] | Summary | dict (s. summary.py)

ALL_ENDPOINTS = frozenset({"health", "manifest", "summary", "settings",
                           "account", "vault", "actions", "audit",
                           "datenrechte"})


class _SettingIn(BaseModel):
    key: str
    value: Any


class _VaultIn(BaseModel):
    name: str
    value: str


class _ProposeIn(BaseModel):
    # Modul-Ebene zwingend (PEP-563-Falle, s. templates/refapp/README).
    name: str
    params: dict[str, Any] = {}
    source: str = "ki"
    # Agenten-Herkunft (docs/63 §2, additiv): bei source='agent' ist warum Pflicht.
    agent_id: str = ""
    warum: str = ""
    lauf_id: str = ""


def _spine_entscheidungshook(manifest: AppManifest, db: Database,
                             ereignis_register: "EreignisTypRegister | None"):
    """Baut den ``on_entscheidung``-Hook für ``decide`` (docs/83 §4): schreibt bei
    jeder Nutzer-Entscheidung ``hitl_entschieden`` in den Ereignis-Spine der App —
    netzweit, weil er in der zentralen ``/api/actions``-Route sitzt. Liefert
    ``None``, wenn die App den Spine (noch) nicht nutzt (0-Bruch). Nur Zeiger +
    Skalare (``klasse`` in eigener Spalte); eigene Tx, best-effort (der
    ``decide``-Hook schluckt Fehler bereits)."""
    if ereignis_register is None or not ereignis_register.kennt("hitl_entschieden"):
        return None
    from .ereignis_spine import ereignis_anlegen
    from .agenten import klasse_von_level

    def hook(info: dict[str, Any]) -> None:
        with db.transaktion() as conn:
            ereignis_anlegen(
                conn, info["user_id"], "hitl_entschieden",
                register=ereignis_register,
                ref=f"{manifest.id}:aktion:{info['action_id']}",
                klasse=klasse_von_level(info.get("level", "")),
                payload={"aktion": info["name"], "approve": bool(info["approve"]),
                         "status": info["status"], "agent_id": info["agent_id"],
                         "lauf_id": info["lauf_id"]},
                quelle_sens=manifest.sensitivity)
    return hook


def contract_router(
    manifest: AppManifest,
    db: Database,
    summary_fn: SummaryFn,
    *,
    schema: SettingsSchema | None = None,
    actions: ActionRegistry | None = None,
    vault: Vault | None = None,
    version: str | None = None,
    include: frozenset[str] | set[str] = ALL_ENDPOINTS,
    on_delete: Callable[[str], None] | None = None,
    bewahre_bei_loeschung: tuple[str, ...] = (),
    ereignis_register: "EreignisTypRegister | None" = None,
) -> APIRouter:
    """Der App-Vertrag als einbettbarer Router (Endpoints siehe docs/16 §2)."""
    unknown = set(include) - ALL_ENDPOINTS
    if unknown:
        raise ValueError(f"Unbekannte Vertrags-Endpoints: {sorted(unknown)}")
    app_version = version or manifest.version
    schema = schema or make_schema(sensitivity=manifest.sensitivity)
    defs = schema.by_key()
    vault = vault or Vault(db.db_path.parent)
    actions = actions or ActionRegistry()
    r = APIRouter(tags=["vertrag"])

    if "health" in include:
        @r.get("/api/health")
        def health() -> dict[str, Any]:
            return {"ok": True, "app": manifest.id, "version": app_version,
                    "contract": CONTRACT_VERSION, "ts": now_iso()}

    if "manifest" in include:
        @r.get("/api/manifest")
        def get_manifest() -> AppManifest:
            return manifest

    if "summary" in include:
        @r.get("/api/summary")
        def get_summary() -> Summary:
            """Dashboard-Kachel. IMMER HTTP 200 — Zustand steckt in ``status``."""
            ts = now_iso()
            try:
                return normalize(manifest.id, manifest.name, ts, summary_fn())
            except Exception as e:  # kaputte App darf das Dashboard nie fluten
                return Summary(ok=False, app=manifest.id, name=manifest.name,
                               ts=ts, status="fehler",
                               note=f"{type(e).__name__}: {e}")

    if "settings" in include:
        @r.get("/api/settings")
        def get_settings(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Werte = Defaults aus dem Schema, übersteuert durch Gespeichertes.
            ``sensitive``-Werte werden maskiert (write-only)."""
            stored = db.settings_all(user.user_id)
            out = {d.key: d.default for d in schema.defs}
            out.update(stored)
            for key, d in defs.items():
                if d.sensitive and out.get(key) not in (None, d.default):
                    out[key] = MASK
            return out

        @r.get("/api/settings/schema")
        def get_settings_schema() -> dict[str, Any]:
            """Schema fürs generische Settings-Panel (K2): 6 Kategorien, typisiert."""
            return {"version": schema.version, "kategorien": schema.grouped()}

        @r.put("/api/settings")
        def put_setting(body: _SettingIn,
                        user: UserContext = Depends(current_user)):
            """Vertrag v1.1: bekannte Schlüssel STRIKT validiert; ``x_…`` frei;
            alles andere 400 (Tippfehler-Schutz)."""
            d = defs.get(body.key)
            if d is not None:
                try:
                    value = d.validate_value(body.value)
                except ValueError as e:
                    return JSONResponse({"error": str(e)}, status_code=400)
            elif body.key.startswith("x_"):
                value = body.value
            else:
                return JSONResponse(
                    {"error": f"Unbekannter Setting-Schlüssel: {body.key!r} "
                              "(Schema siehe /api/settings/schema; frei: x_…)"},
                    status_code=400)
            db.setting_put(user.user_id, body.key, value)
            db.audit(user.user_id, "user", "setting_changed", {"key": body.key})
            return {"ok": True, "key": body.key}

    if "account" in include:
        @r.get("/api/account")
        def get_account(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Konto-Übersicht (K2): Profil + aktuelle Identität + SSO-Zustand."""
            return {
                "profil": {"anzeigename": db.setting_get(
                    user.user_id, "anzeigename",
                    defs["anzeigename"].default if "anzeigename" in defs else "dizzi")},
                "identitaet": {"user_id": user.user_id, "level": user.level,
                               "via": user.via},
                "sso": manifest.auth.model_dump(),
                "tresor_eintraege": len(vault.names()),
            }

    if "vault" in include:
        @r.get("/api/vault")
        def vault_names(user: UserContext = Depends(current_user)) -> list[str]:
            """NUR Namen — Werte verlassen den Tresor nie über HTTP."""
            return vault.names()

        @r.put("/api/vault")
        def vault_put(body: _VaultIn,
                      user: UserContext = Depends(current_user)) -> dict[str, Any]:
            vault.put(body.name, body.value)
            db.audit(user.user_id, "user", "vault_eintrag_gesetzt", {"name": body.name})
            return {"ok": True, "name": body.name}

        @r.delete("/api/vault/{name}")
        def vault_delete(name: str,
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            ok = vault.delete(name)
            if ok:
                db.audit(user.user_id, "user", "vault_eintrag_geloescht", {"name": name})
            return {"ok": ok, "name": name}

    if "actions" in include:
        _on_entscheidung = _spine_entscheidungshook(manifest, db, ereignis_register)

        @r.get("/api/actions")
        def get_actions(status: str | None = None,
                        user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Katalog (was die App KANN) + Vorschlags-Liste (was ansteht/war)."""
            return {"katalog": actions.catalog(),
                    "liste": listing(db, user.user_id, actions, status=status)}

        @r.post("/api/actions/propose")
        def post_propose(body: _ProposeIn,
                         user: UserContext = Depends(current_user)):
            """Vorschlagen ist harmlos (führt nichts aus) ⇒ Stufe 'lokal' reicht."""
            try:
                return propose(db, actions, user.user_id, body.name, body.params,
                               source=body.source, agent_id=body.agent_id,
                               warum=body.warum, lauf_id=body.lauf_id)
            except KeyError as e:
                return JSONResponse({"error": str(e)}, status_code=404)
            except ValueError as e:   # source='agent' ohne WARUM ⇒ abgelehnt (docs/63 §2)
                return JSONResponse({"error": str(e)}, status_code=422)

        @r.post("/api/actions/{action_id}/approve")
        def post_approve(action_id: str,
                         user: UserContext = Depends(current_user)):
            """Freigabe = die Wirkung ⇒ verlangt die HITL-Stufe der Aktion."""
            pending = {a["id"]: a for a in
                       listing(db, user.user_id, actions, status="pending")}
            a = pending.get(action_id)
            if a is None:
                return JSONResponse({"error": "nicht pending/unbekannt"},
                                    status_code=404)
            if LEVELS.get(user.level, -1) < LEVELS[a["level"]]:
                return JSONResponse(
                    {"error": f"Aktion '{a['name']}' verlangt Stufe '{a['level']}' "
                              f"(aktuell '{user.level}') — Anmeldung über Dizzi-ID nötig."},
                    status_code=403)
            result = decide(db, actions, user.user_id, action_id, approve=True,
                            on_entscheidung=_on_entscheidung)
            if result is None:   # Rennen verloren: parallel schon entschieden/in Ausführung (F-A)
                return JSONResponse({"error": "nicht mehr pending — parallel bereits entschieden"},
                                    status_code=409)
            return result

        @r.post("/api/actions/{action_id}/reject")
        def post_reject(action_id: str,
                        user: UserContext = Depends(current_user)):
            result = decide(db, actions, user.user_id, action_id, approve=False,
                            on_entscheidung=_on_entscheidung)
            if result is None:
                return JSONResponse({"error": "nicht pending/unbekannt"},
                                    status_code=404)
            return result

    if "audit" in include:
        @r.get("/api/audit")
        def get_audit(limit: int = 50,
                      user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            return db.audit_recent(user.user_id, limit=min(limit, 500))

    if "datenrechte" in include:
        # K2.1b (Vertrag 1.3, docs/19 §1+§3): Export + Löschen sind SENSIBLE
        # Aktionen ⇒ Re-Auth Pflicht (frischer Login/Step-up, fail-closed
        # standalone). POST statt GET: keine Caches/Logs mit Vollexporten.
        from .auth import require_fresh_stepup
        _frisch = require_fresh_stepup("verifiziert", 300.0)

        @r.post("/api/account/export")
        def account_export(user: UserContext = Depends(_frisch)) -> dict[str, Any]:
            """DSGVO-Export: alle App-Daten des Nutzers, maschinenlesbar.
            Tresor liefert nur NAMEN — Geheimnisse verlassen ihn nie."""
            daten = db.export_user(user.user_id)
            db.audit(user.user_id, "user", "daten_exportiert",
                     {"tabellen": sorted(daten)})
            return {"app": manifest.id, "format": "json", "ts": now_iso(),
                    "tresor_namen": vault.names(), "daten": daten}

        @r.post("/api/account/loeschen")
        def account_loeschen(user: UserContext = Depends(_frisch)) -> dict[str, Any]:
            """Lösch-Kaskade: Soft-Delete aller Nutzer-Daten + Tresor-Wipe +
            optionaler ``on_delete``-Hook für APP-EIGENE Artefakte AUSSERHALB der DB
            (H-7, docs/25): die DB-Konvention kennt z. B. Memorys Vault-`.md`-Dateien
            oder den RAG-Index nicht. Der Hook läuft NACH der DB-/Tresor-Löschung und
            ist best-effort: schlägt er fehl, ist die (rechtlich maßgebliche) Konto-
            Löschung trotzdem erfolgt; die Artefakt-Räumung wird ehrlich gemeldet.
            Das Audit-Log bleibt — die Löschung selbst muss belegbar sein.

            ``bewahre_bei_loeschung`` (BZ-C-7, docs/80 §6.3): eine App kann Tabellen von der
            Soft-Delete-Kaskade AUSNEHMEN, für die eine gesetzliche Aufbewahrungspflicht die DSGVO-
            Löschung überlagert (Art. 17(3)(b)) — z. B. Dizz Money: ``buchungen/postings/festschreibungen``
            bleiben als pseudonymes Gerippe (subjekt-UUID ohne Auflösungstabelle) bis Fristablauf."""
            zaehler = db.soft_delete_user(user.user_id, behalten=("audit_log", *bewahre_bei_loeschung))
            for name in vault.names():
                vault.delete(name)
            artefakte_ok = True
            if on_delete is not None:
                try:
                    on_delete(user.user_id)
                except Exception as e:  # noqa: BLE001 — Konto-Löschung darf nie scheitern
                    artefakte_ok = False
                    db.audit(user.user_id, "system", "on_delete_fehler",
                             {"fehler": str(e)})
            db.audit(user.user_id, "user", "daten_geloescht",
                     {"tabellen": zaehler, "artefakte_geraeumt": artefakte_ok})
            return {"ok": True, "geloescht": zaehler, "tresor_geleert": True,
                    "artefakte_geraeumt": artefakte_ok}

    if ereignis_register is not None:
        # docs/83 §1: read-only Pull-Router GET /api/ereignisse (Spine-Konsumenten
        # ziehen per Cursor). KEIN HTTP-Schreibpfad — Ereignisse entstehen nur in
        # der Domain-Tx der App (ereignis_anlegen), nie über die API.
        from .ereignis_spine import router_factory
        r.include_router(router_factory(db, ereignis_register, user_dep=current_user))

    return r


def create_app(
    manifest: AppManifest,
    db: Database,
    summary_fn: SummaryFn,
    routers: Iterable[APIRouter] = (),
    version: str | None = None,
    schema: SettingsSchema | None = None,
    actions: ActionRegistry | None = None,
    defense: bool = True,
    mini_dizzi: bool = True,
    on_delete: Callable[[str], None] | None = None,
    bewahre_bei_loeschung: tuple[str, ...] = (),
    ereignis_register: "EreignisTypRegister | None" = None,
    csp_mode: str = "aus",
    csp_strikt: bool = False,
    fehlerseite: bool = True,
    netz: bool = True,
    sicherheit: bool = True,
) -> FastAPI:
    """Baut die vertragskonforme FastAPI-App einer NEUEN Netzwerk-App.

    ``on_delete(user_id)`` (optional, H-7): Hook, den ``POST /api/account/loeschen``
    nach der DB-/Tresor-Löschung aufruft, damit die App ihre EXTERNEN Artefakte
    (Dateien/Indizes außerhalb der DB) mit-räumt (z. B. Memory: Vault + RAG).

    ``fehlerseite``/``netz`` (docs/70 F-4/F-1): HTML-Fehlerseite für Browser-
    Navigationen (API-Clients bekommen unverändert JSON, strikte Content-
    Negotiation) + ``GET /api/netz/apps`` (kanonisches App-Verzeichnis für die
    ui-kit-Netz-Leiste). Beides additiv; wirkt erst beim gegateten Neustart."""
    app_version = version or manifest.version
    schema = schema or make_schema(sensitivity=manifest.sensitivity)
    vault = Vault(db.db_path.parent)  # Token-Tresor neben der App-DB (K2)
    actions = actions or ActionRegistry()  # K4: leer = nur Lese-App
    if defense:  # F-DEF1 (Vertrag 1.4): Dizz-Defense-Settings ins Schema
        from .defense import defense_settings
        vorhanden = {d.key for d in schema.defs}
        zusatz = [d for d in defense_settings() if d.key not in vorhanden]
        if zusatz:
            schema = schema.model_copy(update={"defs": list(schema.defs) + zusatz})
    if mini_dizzi:  # Vertrag 1.5: Mini-Dizzi-Settings (KI-Stimme) ins Schema
        from .mini_dizzi import mini_dizzi_settings
        vorhanden = {d.key for d in schema.defs}
        zusatz = [d for d in mini_dizzi_settings() if d.key not in vorhanden]
        if zusatz:
            schema = schema.model_copy(update={"defs": list(schema.defs) + zusatz})

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        db.get_conn()  # legt Schema an
        migriere_actions_inbox(db)  # docs/63 §2: Inbox-Zusatzspalten netzweit nachrüsten
        db.audit(DEFAULT_USER_ID, "system", "app_started",
                 {"app": manifest.id, "version": app_version})
        try:  # Datenhygiene: aufbewahrung_tage durchsetzen (K2, Review 12.06.)
            tage = int(db.setting_get(DEFAULT_USER_ID, "aufbewahrung_tage", 365))
            db.retention_lauf(DEFAULT_USER_ID, tage)
        except Exception:
            pass  # Hygiene darf den Start nie verhindern
        yield

    app = FastAPI(title=manifest.brand, version=app_version, lifespan=_lifespan)
    from .guard import install_local_guard
    install_local_guard(app)  # H1: DNS-Rebinding/CSRF-Schutz (docs/18)
    if defense:
        # F-DEF1: Dizz Defense NACH dem Guard registrieren ⇒ äußerste
        # Middleware — die Sensorik sieht auch Guard-Abweisungen (H1-Treffer
        # sind Angriffs-Signale) und setzt Sperren VOR allem anderen durch.
        from .defense import install_defense
        install_defense(app, db, manifest.id, registry=actions)
    # H-2 (docs/25): Security-Header als ZULETZT registrierte = äußerste Middleware
    # ⇒ stempelt JEDE Antwort, auch Guard-/Defense-Abweisungen (reiner Response-
    # Stempler; ändert nichts am Request-Pfad, den Defense weiterhin als erstes sieht).
    from .headers import install_security_headers
    install_security_headers(app)
    # H-CSP (docs/36 W2): Nonce-CSP, opt-in je App. Default 'aus' ⇒ kein Verhaltens-
    # wechsel, bis die App ihre index.html über csp.serve_html_mit_csp ausliefert und
    # csp_mode='report-only'/'enforce' setzt. connect-src bleibt self (lokal); eine App
    # mit Core-Relay-Bedarf kann das später erweitern.
    from .csp import install_csp
    install_csp(app, mode=csp_mode, strikt=csp_strikt)
    app.state.manifest = manifest
    app.state.db = db
    app.state.vault = vault          # Domänen-Code: app.state.vault.get("…")
    app.state.settings_schema = schema

    if mini_dizzi:
        # Vertrag 1.5: Mini-Dizzi (KI-Stimme). Die App registriert ihre eigene
        # KI über app.state.mini_dizzi.set_app_ki(fn); ohne das antwortet der
        # generische lokale Ollama-Fallback mit App-Kontext.
        from .mini_dizzi import MiniDizzi, mini_dizzi_router
        md = MiniDizzi(manifest, db, summary_fn=summary_fn)
        app.state.mini_dizzi = md
        app.include_router(mini_dizzi_router(md))

    app.include_router(contract_router(
        manifest, db, summary_fn, schema=schema, actions=actions,
        vault=vault, version=app_version, on_delete=on_delete,
        bewahre_bei_loeschung=bewahre_bei_loeschung,
        ereignis_register=ereignis_register))
    for r in routers:
        app.include_router(r)
    if sicherheit:
        # SF-1 (docs/82 §3): Sicherheits-Ampel GET /api/sicherheit/lage — reine
        # Lese-/Statusanzeige (Stufe 'lokal', localhost-guarded), additiv. Zeigt an,
        # ändert nichts; ohne diese Route bliebe die Ampel im Cockpit leer.
        from .security_posture import posture_router
        app.include_router(posture_router(manifest, db))
    if netz:
        # F-1 (docs/70 §3.1): App-Verzeichnis NACH den App-Routern registrieren,
        # damit eine App-eigene /api/netz/apps-Route gewinnen würde (First-Match).
        from .netz import netz_router
        app.include_router(netz_router())
    if fehlerseite:
        # F-4 (docs/70 §3.4): HTML nur für Browser-Navigationen; /api/* + alle
        # Nicht-text/html-Clients erhalten byte-gleich die bisherige JSON-Antwort.
        from .fehlerseite import install_fehlerseiten
        install_fehlerseiten(app, manifest)
    return app
