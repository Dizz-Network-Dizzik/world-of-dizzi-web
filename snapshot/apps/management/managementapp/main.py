"""Dizz Management — App-Fabrik (KI-Agenten-Verwaltung, D13; erste Agenten-Domäne
Social Media: Kanäle · Social-Bots · Posts/Entwürfe · Zeitplan · Creating-Empfang).

Start (Entwicklung):
    <venv-python> -m uvicorn managementapp.main:app_factory --factory
        --host 127.0.0.1 --port 8213 --app-dir apps/management

Alles Vertragliche (Health/Summary/Settings/Account/Datenrechte/Defense/Aktionen/
Mini-Dizzi) kommt aus appkit über ``create_app``. Diese Datei verdrahtet nur die
App-Stellen: Manifest (manifest.py), Domäne (domain.py), KI (ki.py), die HITL-
Aktions-Registry (post_veroeffentlichen) — plus den SENSIBEL-Schalter
(sensitivity='hoch' ⇒ KI lokal-first).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.staticfiles import StaticFiles

from . import __version__, ki
from . import bereiche as bereichmodul
from . import agenten_domain
from . import agenten_eval, agenten_eichung
from . import agenten_preset            # RG-7: Ton-Preset + VIP-Liste je Bereich (docs/83 §5.6)
from .domain import SCHEMA, build_domain
from .manifest import APP_ID, MANIFEST

from appkit.actions import ActionRegistry
from appkit import ui_kit_path
from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit.auth import DEFAULT_USER_ID
from appkit.db import Database, default_db_path
from appkit.dizzi_id import install_dizzi_id
from appkit.settings_core import SettingDef, make_schema


def _schema():
    """Vertrags-Basis (6 Kategorien) + Domänen-Settings von Dizz Management.

    Wegen ``sensitivity='hoch'`` startet ``ki_routing`` aus der Basis bereits auf
    ``lokal_only`` (lokal-first) — hier werden nur App-spezifische Schalter ergänzt.
    Der Unified-Provider ist ein VORBEREITETER Slot (Gesetz 5): per Default
    ``aus`` (lokal-first), opt-in auf Ayrshare/Postiz (channels.py)."""
    return make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="llm_modell", category="ki", type="str",
                   default="qwen3:4b", label="Ollama-Modell (Social-KI)",
                   description="Lokales Modell für Planung/Mini-Dizzi (0 €, lokal-first)."),
        SettingDef(key="plan_horizont_tage", category="ki", type="int",
                   default=30, min=1, max=365, label="Planungs-Horizont (Tage)",
                   description="Vorausschau-Fenster für Redaktionsplan/KI-Vorschläge."),
        # Vorbereiteter Slot (Gesetz 5): Unified-Posting-Provider. Default aus =
        # lokal-first (direkte Plattform-APIs / nichts scharf). Opt-in kostet (Ayrshare)
        # bzw. Selfhost (Postiz). Posten bleibt v1 DORMANT (channels.py).
        SettingDef(key="unified_provider", category="vernetzung", type="choice",
                   choices=["aus", "ayrshare", "postiz"], default="aus",
                   label="Unified-Posting-Provider (vorbereitet)",
                   description="aus = lokal-first/direkte Plattform-APIs. ayrshare "
                               "(opt-in, kostet, eigener MCP) · postiz (OSS-Selfhost, 0 €). "
                               "Siehe docs/04_CHANNEL_VORBEREITUNG.md. v1: Posten DORMANT."),
        # Vorbereiteter Slot: Vorlauf für Zeitplan-/Posting-Erinnerungen (Push an
        # Dizzi-Meldungen) — der Scheduler/Wächter folgt (analog Plans/Admin).
        SettingDef(key="erinnerung_vorlauf_min", category="daten", type="int",
                   default=30, min=0, max=10080, label="Erinnerungs-Vorlauf (Minuten)",
                   description="Vorbereitet: Vorlauf für Zeitplan-Erinnerungen "
                               "(Push an Dizzi-Meldungen) — Scheduler-Wächter folgt."),
        # RG-5 (docs/83 §4): Golden-/Injection-Gate der Agenten-Eichung. Fail-closed AUS —
        # erst wenn die Golden-Suite (apps/core/tests/eval) bestätigt grün ist, DARF eine
        # Eichung grün werden. Bewusster deploy-/CI-Akt; steuert KEINE Live-Aktivierung.
        SettingDef(key=agenten_domain.EICHUNG_GOLDEN_SETTING, category="ki", type="bool",
                   default=False, label="Golden-Eval-Suite bestätigt grün",
                   description="Fail-closed-Gate der Agenten-Eichung: ohne bestätigte "
                               "Golden-/Injection-Suite bleibt jede Ampel ungrün, egal wie "
                               "gut die Betriebs-Metriken sind (docs/83 §4)."),
    ])


def build_app(data_dir: Path | None = None, http_post=None, archiv_post=None,
              agent_inbox_fetch=None, agent_core_client=None, agent_event_push=None,
              agent_eichung_fetch=None):
    """Baut die vertragskonforme App. ``data_dir``/``http_post`` sind
    Injektionspunkte für Tests; ``archiv_post`` injiziert den Querverbindungs-POST
    (V8 Management→Memory, docs/26); ``agent_inbox_fetch`` injiziert den Netz-Inbox-Poll
    (Z4.1-D, docs/63 §2); ``agent_core_client`` injiziert die Core-Ausführungs-Brücke
    (Z4.2-D, docs/63 §3 — Running-Tab/Läufe). Produktion nutzt Standardwerte."""
    root = data_dir or Path(os.environ.get("DIZZ_MANAGEMENT_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root),
                  extra_schema=SCHEMA + bereichmodul.SCHEMA_BEREICHE
                  + agenten_domain.SCHEMA_AGENTEN + agenten_domain.SCHEMA_AUTONOMIE
                  + agenten_domain.SCHEMA_AGENT_ABOS     # RG-3b: reaktive Regie (Abos)
                  + agenten_eval.SCHEMA_AGENT_EVALS      # RG-5: Eichung (agent_evals)
                  + agenten_eichung.SCHEMA_EVAL_POLL     # RG-5: Eichungs-Poll (Cursor+Beobachtung)
                  + agenten_preset.SCHEMA_BEREICH_PRESET)  # RG-7: Ton-Preset + VIP je Bereich
    # Bereich-Achse: ``bereich_id`` an Kanäle/Bots/Posts + Bot-Plattform-Slot idempotent
    # nachrüsten (Bestands- wie Frisch-DB; lässt das domain.py-SCHEMA unangetastet).
    bereichmodul.migriere_bereich(db)

    # K4: die HITL-Aktions-Registry; die Domäne registriert ``post_veroeffentlichen``.
    registry = ActionRegistry()
    dom = build_domain(db, registry, http_post=http_post, archiv_post=archiv_post)
    bereiche = bereichmodul.Bereiche(db)   # Bereich-Achse (CRUD-Router unten in routers=[…])
    # Agenten-Regie (D13, docs/63): Definitions-Schicht (CRUD /api/agenten) + Netz-Inbox-
    # Aggregation (§2, read-only). Rein additiv, keine Ausführung (die wohnt beim Core, Z4.2).
    # ``registry`` = eigene K4-Registry (own pending direkt); ``agent_inbox_fetch`` injizierbar.
    agenten = agenten_domain.AgentenDomaene(db, registry=registry,
                                            inbox_fetch=agent_inbox_fetch,
                                            core_client=agent_core_client,
                                            event_push=agent_event_push,
                                            eichung_fetch=agent_eichung_fetch)

    app = create_app(MANIFEST, db, summary_fn=dom.summary,
                     routers=[dom.router, bereiche.build_router(), agenten.build_router(),
                              agenten_preset.build_preset_router(db)],
                     version=__version__, schema=_schema(), actions=registry,
                     csp_mode="enforce", csp_strikt=True)  # CSP voll-strikt (Nonce, docs/37)
    # Dizzi-ID-Anschluss (K1): /auth/login|callback|logout|me + Identitäts-
    # Provider. Ohne laufenden IdP bleibt die App standalone auf Stufe 'lokal'.
    install_dizzi_id(app, MANIFEST, data_root=root)

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet die App ihr EIGENES
    # read-only MCP-Gate (/mcp) an; im Verbund (Modus 'auto') schaltet es ab, sobald der
    # Core sein zentrales Gateway führt. Gleiche Tool-Quelle wie der stdio-MCP. opt-in/Token.
    from . import mcp_tools  # noqa: E402  (Tool-Quelle, lokal importiert)
    from appkit.app_gateway import build_app_gateway  # noqa: E402
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))
    app.state.domain = dom
    dom.set_vault(app.state.vault)    # Token-Prüfung im Publish-Handler (channels.py)

    base = Path(__file__).resolve().parents[1]

    @app.get("/", include_in_schema=False)
    def startseite(request: Request):
        """Management-Oberfläche (Social-Media-Domäne; Design-Baseline, eigenständig nutzbar).
        CSP voll-strikt (docs/37): serve_html_mit_csp injiziert den Per-Request-Nonce
        in die inline <script>/<style> (ersetzt FileResponse(index.html))."""
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, base / "static" / "index.html")

    # K2.4: das ui-kit-Bundle (tokens.css/controls.css/collapse.js …) same-origin
    # servieren, damit das Frontend die kanonische Komponenten-Schicht referenziert
    # statt sie zu kopieren (docs/06 §6). H-1: no-cache (ETag-Revalidierung).
    ui_kit_dir = ui_kit_path()
    if ui_kit_dir.is_dir():
        class _UiKitFiles(StaticFiles):
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit_dir)), name="ui-kit")

    # Mini-Dizzi (Vertrag 1.5): die ECHTE Social-KI als App-KI registrieren, damit
    # „frag Dizz Management nach …" aus Kanälen/Bots/Posts/Zeitplan antwortet (statt
    # des generischen Fallbacks). sensitivity='hoch' ⇒ lokal-first (ki.py).
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _management_ki(frage_text: str) -> dict[str, Any]:
            modell = db.setting_get(DEFAULT_USER_ID, "llm_modell", "qwen3:4b")
            out = ki.frage(dom.ki_kontext(DEFAULT_USER_ID), frage_text,
                           modell=modell, http_post=http_post)
            return {"antwort": (out or {}).get("antwort", "")}
        app.state.mini_dizzi.set_app_ki(_management_ki)

    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): Import der Datei hat keine Seiteneffekte."""
    return build_app()
