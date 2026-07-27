"""Dizz Admin — App-Fabrik (vereinte Verwaltung: Bereiche · Tresor · Projekte ·
Geschäftsführung · Studium · Fristen; Plans+Admin+Leading verschmolzen, docs/28).
VOLL verdrahtet: Geschäft/Studium (domain) + Tresor (tresor) + Projekte (projekte)
+ Bereiche + Fristen-Cockpit + globale Suche + Konnektoren — Modul-Migration durch.

Start (Entwicklung):
    <venv-python> -m uvicorn adminapp.main:app_factory --factory
        --host 127.0.0.1 --port 8222 --app-dir <admin-ordner>

Alles Vertragliche (Summary/Settings/Account/Datenrechte/Defense/Mini-Dizzi) kommt
aus appkit über ``create_app``; diese Datei verdrahtet nur die App-Stellen:
Manifest (manifest.py), Domäne (domain.py), Geschäfts-KI (ki.py), Aggregator
(aggregat.py — die Schwestern read-only über den Core).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, Request
from fastapi.staticfiles import StaticFiles

from . import (__version__, bereiche, fristen, ki, konnektoren, mcp_tools, projekte,
               suche, tresor)
from . import geschaefts_regie      # RG-8: Geschäfts-Kopplung (frist_vorschlagen + frist_naht)
from .aggregat import cockpit_uebersicht, geschaeft_ausgaben, netzwerk_uebersicht
from .domain import SCHEMA, build_domain
from .manifest import APP_ID, MANIFEST

from appkit.app import create_app  # noqa: E402  (Pfad-Shim in __init__)
from appkit import ui_kit_path
from appkit.app_gateway import build_app_gateway  # noqa: E402
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, default_db_path
from appkit import ereignis_spine   # RG-8: Ereignis-Spine (frist_naht-Zeiger)
from appkit.dizzi_id import install_dizzi_id
from appkit.settings_core import SettingDef, make_schema


def _schema():
    """Vertrags-Basis (6 Kategorien, ``sensitivity='hoch'`` ⇒ KI lokal-first) +
    Modul-Settings (Geschäft/Studium aus Leading · Projekte aus Plans · Tresor aus Admin)."""
    return make_schema(sensitivity=MANIFEST.sensitivity, extra=[
        SettingDef(key="llm_modell", category="ki", type="str",
                   default="qwen3:4b", label="Ollama-Modell (Geschäfts-KI)",
                   description="Lokales Modell für Hinweise/Mini-Dizzi (0 €, strikt lokal)."),
        SettingDef(key="kleinunternehmer", category="daten", type="bool",
                   default=False, label="Kleinunternehmer (§19 UStG)",
                   description="Vorbereitet: Rechnungen ohne USt-Ausweis."),
        SettingDef(key="frist_vorlauf_tage", category="daten", type="int",
                   default=7, min=0, max=90, label="Frist-Vorlauf (Tage)",
                   description="Vorlauf für den Frist-Wächter (Push an Dizzi-Meldungen)."),
        # Projekte-Modul (aus Plans, docs/28 §13):
        SettingDef(key="standard_prioritaet", category="daten", type="choice",
                   choices=["hoch", "mittel", "niedrig"], default="mittel",
                   label="Voreingestellte Aufgaben-Priorität"),
        SettingDef(key="ki_wissen_rueck_lese", category="ki", type="bool",
                   default=True, label="KI zieht Projekt-Wissen aus Memory",
                   description="Mini-Dizzi ergänzt Antworten um Treffer aus dem "
                               "zentralen Archiv (Dizz Memory). Aus = nur App-Bestand."),
        SettingDef(key="kalender_quelle", category="vernetzung", type="choice",
                   choices=["lokal", "google", "ical"], default="lokal",
                   label="Kalender-Quelle",
                   description="Vorbereitet: lokal (v1) · google (OAuth-Token im "
                               "Tresor nötig) · ical (Import). CalDAV folgt als Slot."),
        SettingDef(key="erinnerung_vorlauf_tage", category="daten", type="int",
                   default=2, min=0, max=90, label="Erinnerungs-Vorlauf (Tage)",
                   description="Vorlauf für Termin-/Frist-Erinnerungen (Projekte-Wächter)."),
        # Tresor-Modul (aus Admin, docs/28 §13): Dokument-Typ + Quellen-Stecker.
        SettingDef(key="standard_dok_typ", category="daten", type="choice",
                   choices=["Rechnung", "Vertrag", "Steuer", "Sonstiges"],
                   default="Sonstiges", label="Voreingestellter Dokument-Typ"),
        SettingDef(key="ki_memory_ruecklese", category="ki", type="bool", default=True,
                   label="Tresor-KI liest Dizz Memory mit",
                   description="Rück-Lese: passende Treffer aus dem Dizz-Memory-Archiv "
                               "(best-effort; ohne laufenden Core ohne Wirkung)."),
        SettingDef(key="ki_klassifikation_upload", category="ki", type="bool", default=False,
                   label="Dokumente beim Upload per KI klassifizieren",
                   description="A4: schlägt beim Einzug Typ/Korrespondent/Tags vor (lokales "
                               "Ollama, 0 €) und legt den Vorschlag zur Bestätigung in den "
                               "Posteingang (HITL — nie automatisch angewendet). Aus = kein "
                               "KI-Aufruf beim Upload. Verschlüsselte Dokumente bleiben außen vor."),
        SettingDef(key="watch_ordner", category="daten", type="str", default="",
                   label="Watch-Ordner (Pfad)",
                   description="Lokaler Posteingang-Ordner (PDF/JPG/PNG/DOCX) für den "
                               "manuellen Tresor-Scan."),
        SettingDef(key="watch_aktiv", category="daten", type="bool", default=False,
                   label="Ordner automatisch einlesen (Slot)"),
        SettingDef(key="imap_host", category="vernetzung", type="str", default="",
                   label="IMAP-Host", description="z. B. imap.gmail.com (App-Passwort "
                               "im Tresor 'imap_passwort')."),
        SettingDef(key="imap_user", category="vernetzung", type="str", default="",
                   label="IMAP-Benutzer (E-Mail)"),
        SettingDef(key="imap_ordner", category="vernetzung", type="str",
                   default="INBOX", label="IMAP-Ordner"),
        SettingDef(key="imap_aktiv", category="vernetzung", type="bool", default=False,
                   label="Postfach automatisch abrufen (Slot)"),
        # mcp_gateway_mode + mcp_gateway_freigabe_hochsicher liegen ab appkit 1.20.0 im
        # gemeinsamen settings_core.base_schema (docs/31 §7) — JEDE App erbt sie ⇒ hier
        # NICHT mehr lokal definieren (sonst „Doppelte Setting-Schlüssel").
    ])


def build_app(data_dir: Path | None = None, http_post=None, http_get=None,
              archiv_post=None, memory_get=None, kalender_post=None,
              event_post=None, regie_karte_fetch=None,
              max_upload_bytes: int = tresor.MAX_UPLOAD_BYTES,
              start_wachter: bool = False):
    """Baut die vertragskonforme App. ``data_dir``/``http_post``/``http_get`` sind
    Test-Injektionspunkte (KI bzw. Aggregator-Core-Abruf); ``archiv_post``/``memory_get``/
    ``kalender_post`` injizieren die Projekte-/Tresor-Querverbindungen (V6/V7 →Memory,
    RÜCK-LESE, V5 Kalender). ``max_upload_bytes`` begrenzt den Tresor-Upload. ``event_post``/
    ``start_wachter`` sind v3-Kompat-Slots (der Dokument-Auto-Poll-Tick ist verschoben,
    docs/28 §13). Produktion nutzt ``DIZZ_ADMIN_DATA_DIR``/Standardwerte."""
    root = data_dir or Path(os.environ.get("DIZZ_ADMIN_DATA_DIR", r"C:\Dizzik\data"))
    db = Database(default_db_path(APP_ID, data_root=root),
                  extra_schema=SCHEMA + bereiche.SCHEMA_BEREICHE + projekte.SCHEMA_PROJEKTE
                  + tresor.SCHEMA_TRESOR + konnektoren.SCHEMA_KONNEKTOREN
                  + geschaefts_regie.SCHEMA_FRIST_VORSCHLAG   # RG-8: Fristen-Entwurf-Review
                  + ereignis_spine.SCHEMA_EREIGNISSE_SQL)     # RG-8: Ereignis-Spine (§6)
    # Bereichs-Rückgrat (docs/28 §2): bereich_id-FK idempotent an die Domänen-Tabellen
    # nachrüsten (Struktur ready; per-Entity-CRUD folgt mit der Zuordnungs-Phase 3).
    bereiche.migriere_bereich_fk(db)
    # V16: die EÜR-Ausgabenseite zieht die geschäftlichen Ausgaben aus Dizz Money über
    # den Core-Relay (gleicher http_get-Injektionspunkt wie der Aggregator). Best-effort.
    dom = build_domain(db, http_post=http_post,
                       ausgaben_reader=lambda jahr: geschaeft_ausgaben(jahr, http_get=http_get))
    # vault_root = Dokument-Verzeichnis (außerhalb der DB); Bereiche braucht es für
    # das A3-Export-Bundle (Vault-Dateien der Bereichs-Dokumente mitpacken).
    vault_root = root / "apps" / APP_ID / "vault"
    ber = bereiche.Bereiche(db, vault_root=vault_root)
    # Projekte-Modul (aus Plans, docs/28 §13): eigener Router + K4-Aktionen; die
    # Querverbindungen (→Memory/RÜCK-LESE/Kalender-Rücksync) über dieselben Injektionen.
    proj = projekte.build_projekte(db, archiv_post=archiv_post, memory_get=memory_get,
                                   kalender_post=kalender_post)
    # Tresor-Modul (aus Admin, docs/28 §13): Dokument-Vault + FTS5 + V15-Beleg-Link-
    # Empfang. ``vault_root`` (oben) = das Datei-Verzeichnis (außerhalb der DB);
    # ki_post = Ollama für die Dokument-Klassifikation. on_delete räumt Vault+FTS (DSGVO).
    tdom = tresor.build_tresor(db, vault_root, max_upload_bytes=max_upload_bytes,
                               archiv_post=archiv_post, memory_get=memory_get, ki_post=http_post)
    # Fristen-Cockpit (docs/28 §3, Phase 3): EINE kategorie-gefilterte Frist-Sicht über
    # alle Module (Aufgaben/Termine/Rechnungen/Geschäfts-/Studien-Fristen/Aufbewahrung).
    # ``projekte`` = A5 Frist→Aufgabe (in-Prozess: eine Frist wird zur Aufgabe).
    fr = fristen.FristenCockpit(db, projekte=proj)
    # Globale Cross-Modul-Suche (docs/30 A2): EINE Suche über alle Module, bereich-gefiltert.
    such = suche.GlobalSuche(db)
    # Externe-Tool-Konnektoren (docs/35 §3, D2): externe Kalender-/Projekt-/Office-Tools
    # in die Bereichs-/Fristen-Sicht einklinken — Datenmodell + dormante Adapter +
    # Sichtbarkeit. ``vault`` (Token-Status) wird nach create_app gesetzt (s. u.).
    konn = konnektoren.build_konnektoren(db)

    # RG-8 (docs/83 §6): Geschäfts-Kopplung — dormante Nähte. ``frist_vorschlagen`` (Registry-
    # Vertrag, level lokal ⇒ Klasse entwurf) auf der Projekte-Aktions-Registry; Ereignis-Spine
    # (frist_naht-Zeiger + netzweit hitl_entschieden). Legt NIE eine echte Aufgabe/Frist an.
    _EREIGNIS_REGISTER = ereignis_spine.standard_register(APP_ID)
    geschaefts_regie.registriere_ereignis_typen(_EREIGNIS_REGISTER)
    geschaefts_regie.registriere(proj.actions, db)

    # Kachel-KPIs = Geschäft+Studium (dom) UND Projekte (proj) UND Tresor (tdom)
    # zusammengefaltet, damit die Dashboard-Kachel die ganze vereinte App zeigt.
    def _summary():
        return dom.summary() + proj.summary() + tdom.summary()

    app = create_app(MANIFEST, db, summary_fn=_summary,
                     routers=[dom.router, ber.build_router(), proj.router, tdom.router,
                              fr.build_router(), such.build_router(), konn.build_router(),
                              geschaefts_regie.build_router(   # RG-8 (§6)
                                  db, regie_karte_fetch=regie_karte_fetch)],
                     version=__version__, schema=_schema(), actions=proj.actions,
                     ereignis_register=_EREIGNIS_REGISTER,          # RG-8: Spine (frist_naht + hitl)
                     on_delete=tdom.on_delete,
                     # CSP-Scharfschaltung (D4): Baseline-Enforce — erlaubt die Bestands-
                     # Inline-Handler ('unsafe-inline'), blockt aber externe Skripte/Styles,
                     # <object>/<embed>, <base>-Injektion und Framing. Voll-strikt (Nonce)
                     # erst nach Inline-Handler-Umbau (§5d). Lokale App ⇒ connect-src self genügt.
                     csp_mode="enforce", csp_strikt=True)  # CSP voll-strikt (Nonce); Inline-Handler→data-dz-act
    install_dizzi_id(app, MANIFEST, data_root=root)
    app.state.domain = dom            # Tests/MCP-Prozesse
    app.state.bereiche = ber
    app.state.projekte = proj
    app.state.tresor = tdom
    app.state.fristen = fr
    app.state.suche = such
    app.state.konnektoren = konn

    # Per-App-MCP-Gateway (docs/31 §7): im Standalone-Betrieb bietet Dizz Admin sein
    # EIGENES MCP-Gate (`/mcp`) an — eine externe KI verbindet sich direkt mit dieser
    # App. Im Verbund schaltet es sich im Modus 'auto' ab, sobald der Core sein
    # zentrales Gateway aktiv hat (dann ist der Core die EINE Verbindung). Gleiche
    # Tool-Quelle wie der stdio-MCP (mcp_tools.MCP_TOOLS). opt-in/Token/Hochsicher-Gate.
    app.include_router(build_app_gateway(
        MANIFEST, db, tools=mcp_tools.MCP_TOOLS,
        base_url=f"http://127.0.0.1:{MANIFEST.port}"))
    tdom.vault = app.state.vault      # EINE Tresor-Instanz (IMAP-Passwort für Abrufen)
    konn.vault = app.state.vault      # Konnektoren lesen den Token-Status aus demselben Tresor

    # Aggregator (Kern-Idee): Schwester-Apps read-only über den Core konsumieren.
    @app.get("/api/netzwerk")
    def netzwerk(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Kuratierte Netzwerk-Übersicht (online + Kachel-Status je Schwester-App),
        gezogen aus den Core-Panels — best-effort (Core offline ⇒ leer + Hinweis)."""
        return netzwerk_uebersicht(http_get=http_get)

    # Executive-Cockpit (UI/UX P1a): je Geschäfts-Domäne die führungsrelevante
    # Kennzahl der Quell-App + Deep-Link — der Aggregator-Gedanke, visuell.
    @app.get("/api/cockpit")
    def cockpit(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Cockpit-Kacheln (Money-Liquidität · Plans-Fristen · Communication-Support ·
        Management-Social) read-only über den Core — best-effort."""
        return cockpit_uebersicht(http_get=http_get)

    base = Path(__file__).resolve().parents[1]

    @app.get("/", include_in_schema=False)
    def startseite(request: Request):
        # CSP voll-strikt (docs/37): index.html mit Per-Request-Nonce ausliefern
        # (inline <script>/<style> bekommen das Nonce injiziert) statt nacktem FileResponse.
        from appkit.csp import serve_html_mit_csp
        return serve_html_mit_csp(request, base / "static" / "index.html")

    # K2.4: ui-kit-Bundle same-origin servieren (H-1: no-cache/ETag).
    ui_kit_dir = ui_kit_path()
    if ui_kit_dir.is_dir():
        class _UiKitFiles(StaticFiles):
            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-cache"
                return resp
        app.mount("/ui-kit", _UiKitFiles(directory=str(ui_kit_dir)), name="ui-kit")

    # Mini-Dizzi (Vertrag 1.5): die App-KI antwortet jetzt über ALLE Module der
    # vereinten App (Geschäft+Studium · Projekte · Tresor) — ein kombinierter,
    # kompakter Kontext speist die Verwaltungs-KI ``ki.frage`` (lokal-first).
    # Mini-Dizzi erfindet nichts dazu; sensible Daten bleiben lokal.
    if getattr(app.state, "mini_dizzi", None) is not None:
        def _admin_ki(frage_text: str) -> dict[str, Any]:
            modell = db.setting_get(DEFAULT_USER_ID, "llm_modell", "qwen3:4b")
            teile = [dom.ki_kontext(DEFAULT_USER_ID)]            # Geschäft + Studium (Text)
            pk = proj.ki_kontext(DEFAULT_USER_ID)               # Projekte (dict)
            if pk["projekte"]:
                teile.append("PROJEKTE: " + ", ".join(
                    f"{p['name']} ({p.get('fortschritt', 0)}%)" for p in pk["projekte"][:8]))
            if pk["aufgaben"]:
                teile.append("Offene Aufgaben: " + "; ".join(
                    a["titel"] + (f" (fällig {a['faellig']})" if a["faellig"] else "")
                    for a in pk["aufgaben"][:10]))
            if pk["termine"]:
                teile.append("Nächste Termine: " + "; ".join(
                    f"{t['titel']} {t['beginn']}" for t in pk["termine"][:6]))
            tk = tdom.ki_kontext(DEFAULT_USER_ID)               # Tresor (dict)
            if tk["dokumente"]:
                teile.append("Tresor-Dokumente (neueste): " + ", ".join(tk["dokumente"][:10]))
            out = ki.frage("\n".join(teile), frage_text, modell=modell, http_post=http_post)
            return {"antwort": (out or {}).get("antwort", "")}
        app.state.mini_dizzi.set_app_ki(_admin_ki)

    return app


def app_factory():
    """Uvicorn-Einstieg (``--factory``): Import der Datei hat keine Seiteneffekte."""
    return build_app()
