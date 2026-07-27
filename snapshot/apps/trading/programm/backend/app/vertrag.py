"""Dizzi-App-Vertrag für Dizz Trading (Kernpaket K6 — architektonische Angleichung).

Dizz Trading wird Teil der Dizzi-Föderation (the world of dizzi/docs/16):
- **Dizzi-ID-Relying-Party**: /auth/login|callback|logout|me — einmal auf
  Dizzi anmelden ⇒ hier angemeldet (Stufen lokal < verifiziert < hochsicher).
- **Vertrags-Endpoints** (vendiertes appkit, programm/appkit): /api/manifest,
  /api/settings(+schema), /api/vault (Token-Tresor, z. B. Bitget-Keys),
  /api/actions (HITL-Vorschläge). BEWUSSTE AUSLASSUNGEN (Bestands-Routen der
  App bleiben unangetastet): /api/summary, /api/account, /api/audit, /api/health
  — Dizzi konsumiert die Kachel weiter über den Legacy-Mapper, bis die
  Voll-Angleichung (R2.0) das TB-Frontend umzieht.
- **Echtgeld-Gate (R-B/K1+)**: ein ECHTER Transfer (Bitget konfiguriert, kein
  dry_run) verlangt die Schutzstufe ``hochsicher`` (Dizzi-ID + TOTP-Step-up).
  Paper-Transfers bleiben frei (simulieren bewegt kein Geld). Fail-closed:
  ohne Login ist die Stufe 'lokal' ⇒ echte Transfers unmöglich.

Vertrags-Daten (Settings/Tresor/Aktionen) liegen getrennt von den Trading-
Daten unter C:\\Dizzik\\data\\apps\\tradingbot\\ — kanonischer Pfad (28.06.2026
von der Junction C:\\dizzi-world-data auf den Echt-Ordner umgestellt; gleiche
Dateien), außerhalb von OneDrive und ohne Berührung der Bot-/Lern-Datenbanken.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Vendiertes appkit auffindbar machen (programm/appkit; Föderation).
_programm = Path(__file__).resolve().parents[2]
if (_programm / "appkit" / "__init__.py").is_file() and str(_programm) not in sys.path:
    sys.path.insert(0, str(_programm))

from fastapi import FastAPI  # noqa: E402

from appkit import auth as appkit_auth  # noqa: E402
from appkit.app import contract_router  # noqa: E402
from appkit.db import Database, default_db_path  # noqa: E402
from appkit.dizzi_id import install_dizzi_id  # noqa: E402
from appkit.manifest import AppManifest, AuthInfo, McpInfo, Shares  # noqa: E402
from appkit.settings_core import SettingDef, make_schema  # noqa: E402
from appkit.summary import Kpi  # noqa: E402

DATA_ROOT = Path(r"C:\Dizzik\data")

# Exposed für main.py → build_app_gateway (gesetzt in install_vertrag).
_db: Database | None = None


def build_manifest(version: str) -> AppManifest:
    return AppManifest(
        id="tradingbot", name="Trading Bot", brand="Dizz Trading",
        version=version, port=8137, icon="chart", sensitivity="hoechst",
        auth=AuthInfo(sso="dizzi-id", standalone=True, status="vorbereitet"),
        # Tool-Namen im App-Namensraum "tradingbot_" (docs/16 §6) — konsistent
        # mit connectors/tradingbot/mcp_server.py; Kollisionsschutz beim Bündeln.
        mcp=McpInfo(command=["<dizzi-venv-python>",
                             "connectors/tradingbot/mcp_server.py"],
                    tools=["tradingbot_fleet_status", "tradingbot_master_status",
                           "tradingbot_mastermeta_status", "tradingbot_governor_status",
                           "tradingbot_konzentration", "tradingbot_alerts"]),
        shares=Shares(summary=True,
                      tools=["tradingbot_fleet_status", "tradingbot_master_status",
                             "tradingbot_governor_status"]),
        depends=[],
    )


def _schema():
    """Vertrags-Settings (K2) — Trading-spezifische Ergänzungen der 6 Kategorien.
    Die eigentliche Trading-Konfiguration bleibt im bestehenden TB-System."""
    return make_schema(sensitivity="hoechst", extra=[
        SettingDef(key="echtgeld_freigabe_hinweis", category="sicherheit",
                   type="bool", default=True,
                   label="Vor Echtgeld-Aktionen Warnhinweis zeigen"),
        SettingDef(key="dizzi_kachel_detail", category="vernetzung",
                   type="choice", choices=["kompakt", "voll"], default="kompakt",
                   label="Detailgrad der Dizzi-Dashboard-Kachel"),
    ])


def install_vertrag(app: FastAPI, version: str) -> AppManifest:
    """Hängt den App-Vertrag an die bestehende Dizz-Trading-App (additiv)."""
    global _db
    manifest = build_manifest(version)
    db = Database(default_db_path("tradingbot", data_root=DATA_ROOT))
    _db = db  # für build_app_gateway in main.py

    # MCP-Gateway: Ceiling-Default auf "hoechst" setzen (nur wenn noch nicht gesetzt).
    # TB Monitoring-Endpunkte (Flotte/Master/Alerts) sind read-only + kein Echtgeld-Pfad;
    # "hoechst" erlaubt deren Export. hochsicher-Inhalte bleiben weiterhin gegatekeepert.
    _anon = appkit_auth.DEFAULT_USER_ID
    if not db.setting_get(_anon, "mcp_gateway_ceiling", None):
        db.setting_put(_anon, "mcp_gateway_ceiling", "hoechst")

    def _kachel() -> list[Kpi]:
        # Platzhalter bis zur Voll-Angleichung (R2.0): die echte Kachel liefert
        # weiterhin TB-/api/summary über Dizzis Legacy-Mapper.
        return [Kpi(id="vertrag", label="App-Vertrag", value="aktiv")]

    # Mini-Dizzi (Vertrag 1.5): KI-Stimme + Settings ins Schema aufnehmen.
    # Folgt dem create_app-Muster (app.py) — TB hat ein eigenes main.py ⇒ hier.
    from appkit.mini_dizzi import MiniDizzi, mini_dizzi_router, mini_dizzi_settings
    schema = _schema()
    vorhanden = {d.key for d in schema.defs}
    zusatz = [d for d in mini_dizzi_settings() if d.key not in vorhanden]
    if zusatz:
        schema = schema.model_copy(update={"defs": list(schema.defs) + zusatz})
    md = MiniDizzi(manifest, db, summary_fn=_kachel)
    app.state.mini_dizzi = md
    app.include_router(mini_dizzi_router(md))

    app.include_router(contract_router(
        manifest, db, _kachel,
        schema=schema,
        # Kollisionsfrei zum Legacy (summary/account/audit/health bleiben TB);
        # "datenrechte" (Vertrag 1.3) kollidiert nicht: eigene POST-Pfade
        # unter /api/account/… — Export/Löschen betreffen die VERTRAGS-Daten
        # (Settings/Tresor/Aktionen), nicht die Trading-Historie.
        include={"manifest", "settings", "vault", "actions", "datenrechte"},
    ))
    install_dizzi_id(app, manifest, data_root=DATA_ROOT)
    from appkit.guard import install_local_guard
    install_local_guard(app)  # H1: DNS-Rebinding/CSRF-Schutz (docs/18 §4.1)
    # O-DEF: Dizz-Defense — Sensorik-Middleware + /api/defense-Cockpit (appkit 1.6.0). Muster:
    # news/komm/finanzen verdrahten es in appkit.create_app; TB hat ein eigenes main.py ⇒ hier.
    # Settings-gegated (defense_aktiv, Default an) + Loopback-Schonung (lokal max. Drosselung, nie
    # Sperre). WICHTIG: greift ERST nach :8137-Neustart (= World-Chat). Trading-Logik unberührt.
    from appkit.defense import install_defense
    install_defense(app, db, manifest.id)
    return manifest


def require_hochsicher_fuer_echtgeld(request, settings) -> str | None:
    """Echtgeld-Gate (K6): None = darf weiter; sonst Fehlertext.

    Ein Transfer ist ECHT, wenn Bitget konfiguriert ist und kein dry_run läuft —
    genau dann gilt die R-B-Linie: nur mit Stufe ``hochsicher`` (Dizzi-ID +
    TOTP). Paper-/Simulations-Transfers bleiben auf Stufe 'lokal' möglich.
    """
    echt = bool(getattr(settings, "bitget_configured", False)) and \
        not bool(getattr(settings, "dry_run", True))
    if not echt:
        return None
    ctx = appkit_auth.current_user(request)
    if appkit_auth.LEVELS.get(ctx.level, -1) < appkit_auth.LEVELS["hochsicher"]:
        return ("Echtgeld-Transfer verlangt Schutzstufe 'hochsicher' "
                f"(aktuell: '{ctx.level}'). Über Dizzi-ID anmelden und "
                "TOTP-Step-up durchführen: /auth/login?level=hochsicher")
    return None


def require_steuerstufe(request) -> str | None:
    """Härtung DESTRUKTIVER Flotten-Steuerbefehle (component/command pause_all/
    resume_all): None = darf weiter; sonst Fehlertext.

    Verlangt eine **verifizierte** Verbindung (Dizzi-ID), damit kein nicht-
    angemeldeter lokaler Aufrufer die ganze Flotte stoppen/starten kann (F2-
    Härtung). Bewusst 'verifiziert' (nicht 'hochsicher'): kein Echtgeld, aber ein
    massiver Betriebseingriff. Einzel-Bot-Steuerung (Dashboard) bleibt unberührt.
    Fail-closed: ohne Login ist die Stufe 'lokal' ⇒ blockiert.
    """
    ctx = appkit_auth.current_user(request)
    if appkit_auth.LEVELS.get(ctx.level, -1) < appkit_auth.LEVELS["verifiziert"]:
        return ("Destruktiver Flotten-Befehl (pause_all/resume_all) verlangt "
                f"Schutzstufe 'verifiziert' (aktuell: '{ctx.level}'). Über "
                "Dizzi-ID anmelden: /auth/login")
    return None
