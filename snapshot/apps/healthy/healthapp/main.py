"""Dizz Healthy — App-Fabrik (Gesundheits-Watching: Vitalwerte · Supplements ·
Verletzungen · Training · Termine).

Start (Entwicklung):
    <venv-python> -m uvicorn healthapp.main:app_factory --factory
        --host 127.0.0.1 --port 8217 --app-dir <health-ordner>

Alles Vertragliche (Health/Summary/Settings/Account/Datenrechte/Defense/
Mini-Dizzi) kommt aus appkit über ``create_app``. Diese Datei verdrahtet nur die
App-Stellen: Manifest (manifest.py), Domäne (domain.py), KI (ki.py) — plus die
HOCHSENSIBEL-Schalter (sensitivity='hoechst' ⇒ KI lokal_only).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.staticfiles import StaticFiles

from . import __version__, ki
from .domain import SCHEMA, build_domain
from .manifest import APP_ID, MANIFEST

from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit import ui_kit_path
from appkit.auth import DEFAULT_USER_ID
from appkit.db import Database, default_db_path
from appkit.dizzi_id import install_dizzi_id
from appkit.settings_core import SettingDef, make_schema


def _schema():
    """Vertrags-Basis (6 Kategorien) + Domänen-Settings von Dizz Healthy.

    Wegen ``sensitivity='hoechst'`` startet ``ki_routing`` aus der Basis bereits
    auf ``lokal_only`` — hier werden nur App-spezifische Schalter ergänzt. Die
    Wearable-Quelle ist ein VORBEREITETER Slot (Gesetz 5): Schalter da, aktiv wird
    sie erst mit Mobile-Brücke/Tresor-Token (sources.py)."""
    return make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="llm_modell", category="ki", type="str",
                   default="qwen3:4b", label="Ollama-Modell (Gesundheits-KI)",
                   description="Lokales Modell für Hinweise/Mini-Dizzi (0 €, strikt lokal)."),
        SettingDef(key="analyse_fenster_tage", category="ki", type="int",
                   default=30, min=3, max=365, label="Auswertungs-Zeitfenster (Tage)",
                   description="Zeitfenster für Trends und KI-Hinweise."),
        # Aktivitäts-Tracker (P1d): Tages-Ziele der drei Ringe (Apple-Health-Muster).
        SettingDef(key="ziel_schritte", category="daten", type="int",
                   default=8000, min=1000, max=50000, label="Tagesziel Schritte"),
        SettingDef(key="ziel_aktive_minuten", category="daten", type="int",
                   default=30, min=5, max=300, label="Tagesziel aktive Minuten"),
        SettingDef(key="ziel_stehstunden", category="daten", type="int",
                   default=12, min=1, max=24, label="Tagesziel Stehstunden"),
        # P3: Geburtsjahr für die (NICHT-medizinische) Fitness-/Bio-Alter-Schätzung.
        # 0 = nicht hinterlegt ⇒ Score bleibt aus (ehrlich) statt zu raten.
        SettingDef(key="geburtsjahr", category="konto", type="int", default=0, min=0,
                   max=2026, label="Geburtsjahr (für Fitness-Alter, optional)",
                   description="Nur lokal. Basis der nicht-medizinischen Fitness-Alter-"
                               "Schätzung; 0 = aus."),
        # Vorbereiteter Slot (Gesetz 5): Wearable-Quelle. v1 = manuell; die Adapter
        # (Apple/Health-Connect/Terra/BLE) sind dormant (sources.py).
        SettingDef(key="wearable_quelle", category="vernetzung", type="choice",
                   choices=["manuell", "apple_health", "health_connect", "terra", "ble"],
                   default="manuell", label="Wearable-Quelle (vorbereitet)",
                   description="v1: manuell. Vorbereitet: apple_health/health_connect "
                               "(Mobile-Brücke) · terra (Tresor-Token) · ble (GATT-Slot). "
                               "Siehe docs/04_WEARABLE_VORBEREITUNG.md."),
        # Lokale Erinnerungen/Vorschläge (in-App, NIE Diagnose, kein OS-/Cross-App-Push,
        # da `hoechst`). Speisen den Übersicht-Strip via GET /api/vorschlaege (deterministisch);
        # jede Art einzeln abschaltbar. erinnerung_vorlauf_tage steuert die Termin-Erinnerung.
        SettingDef(key="erinnerung_vorlauf_tage", category="daten", type="int",
                   default=3, min=0, max=90, label="Termin-Erinnerung: Vorlauf (Tage)",
                   description="Ab wie vielen Tagen vor einem Termin in der Übersicht "
                               "erinnert wird (lokal, in-App)."),
        SettingDef(key="erinnerung_termine", category="daten", type="bool", default=True,
                   label="Erinnerung: anstehende Termine"),
        SettingDef(key="erinnerung_training", category="daten", type="bool", default=True,
                   label="Erinnerung: Training nicht vergessen"),
        SettingDef(key="erinnerung_training_tage", category="daten", type="int",
                   default=4, min=1, max=60, label="Trainings-Erinnerung ab (Tagen ohne Training)",
                   description="Nach wie vielen Tagen ohne Training sanft erinnert wird."),
        SettingDef(key="erinnerung_supplements", category="daten", type="bool", default=True,
                   label="Erinnerung: tägliche Supplements"),
        SettingDef(key="erinnerung_bewegung", category="daten", type="bool", default=True,
                   label="Erinnerung: offene Tagesziele (abends)"),
        SettingDef(key="vorschlag_mahlzeit", category="daten", type="bool", default=True,
                   label="Vorschlag: Mahlzeiten-Hinweis nach Training"),
    ])


def build_app(data_dir: Path | None = None, http_post=None, archiv_post=None,
              kalender_post=None):
    """Baut die vertragskonforme App. ``data_dir``/``http_post`` sind
    Injektionspunkte für Tests; ``archiv_post`` injiziert den Querverbindungs-POST
    (V10 Healthy→Memory) und ``kalender_post`` den Kalender-POST (V13 Healthy→Plans),
    docs/26. Produktion nutzt ``DIZZ_HEALTH_DATA_DIR``/Standardwerte."""
    root = data_dir or Path(os.environ.get("DIZZ_HEALTH_DATA_DIR",
                                           r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root), extra_schema=SCHEMA)
    dom = build_domain(db, http_post=http_post, archiv_post=archiv_post,
                       kalender_post=kalender_post)

    app = create_app(MANIFEST, db, summary_fn=dom.summary, routers=[dom.router],
                     version=__version__, schema=_schema(),
                     csp_mode="enforce", csp_strikt=True)  # CSP VOLL-STRIKT (Nonce);
    # Inline-Handler → DzActions-Delegation (data-dz-act), GET / liefert Nonce (docs/37).
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
    app.state.domain = dom            # Tests/MCP-Prozesse

    base = Path(__file__).resolve().parents[1]

    @app.get("/", include_in_schema=False)
    def startseite(request: Request):
        """Gesundheits-Oberfläche — CSP voll-strikt: index.html mit Per-Request-Nonce
        ausliefern (jeder inline <script>/<style> bekommt das Nonce; enforce blockt sonst)."""
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

    # Mini-Dizzi (Vertrag 1.5): die ECHTE Gesundheits-KI als App-KI registrieren,
    # damit „frag Dizz Healthy nach …" aus den eingetragenen Werten antwortet
    # (statt des generischen Fallbacks). HOCHSENSIBEL ⇒ strikt lokal (ki.py).
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _health_ki(frage_text: str) -> dict[str, Any]:
            modell = db.setting_get(DEFAULT_USER_ID, "llm_modell", "qwen3:4b")
            tage = int(db.setting_get(DEFAULT_USER_ID, "analyse_fenster_tage", 30))
            out = ki.frage(dom.ki_kontext(DEFAULT_USER_ID, tage), frage_text,
                           modell=modell, http_post=http_post)
            return {"antwort": (out or {}).get("antwort", "")}
        app.state.mini_dizzi.set_app_ki(_health_ki)

    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): Import der Datei hat keine Seiteneffekte."""
    return build_app()
