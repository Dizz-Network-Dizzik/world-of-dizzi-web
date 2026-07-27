"""appkit — die geteilte Kern-Bibliothek des App-Vertrags (Kernpaket K3).

Jede App des Dizzi-Netzwerks erfüllt denselben Vertrag (docs/16_APP_VERTRAG_SPEC.md):
Manifest, Stats-Endpoint, MCP-Server, Identitäts-Slot (K1), Settings-Modul (K2),
Datenkonventionen (K5-Basis). Diese Bibliothek implementiert den Vertrag EINMAL;
Apps konsumieren sie und ENTHALTEN sie selbst (Föderation): die kanonische Quelle
liegt im Dizzi-Repo, `ops/sync_appkit.py` vendort sie versions-gestempelt in jede
App — dadurch bleibt jede App eigenständig lauffähig und einzeln verkaufbar.

Spätere Kernpakete docken hier an, ohne dass Apps umgebaut werden müssen:
- K1 (Dizzi-ID): ersetzt den Identitäts-Provider in ``auth`` (set_identity_provider).
- K2 (Account/Settings-Core): baut auf dem ``app_settings``-Schema + Endpoints auf.
- K4 (KI-Protokoll): erweitert ``mcp`` um Aktions-Tools mit Human-in-the-Loop.
- K5 (Datenmodelle/Sync): vertieft die ``db``-Konventionen (Sensibel-Routing, Sync).
"""

from __future__ import annotations

__version__ = "1.27.0"
# 1.27.0 (VLM-Vision-Naht, KA-M7 C3, 10.07., World-Admin-Bau): appkit/vision.py —
# ocr_bild()/beschreibe_bild() (Bild→Text über lokales Ollama-VLM qwen2.5vl:7b,
# schema-constrained, fail-safe → None) + verfuegbar()-Ping. OllamaRuntime.strukturiert
# bekommt die Liskov-sichere Adapter-Extension `bilder=` (base64 ins images-Feld von
# /api/chat; nur-Keyword, Default None ⇒ Payload byte-gleich — wie http_post/verlauf,
# bewusst NICHT im ABC-Vertrag; nur Ollama ist heute vision-fähig). extract._bild_ocr:
# VLM→tesseract→keiner; verfuegbarkeit()["ocr"] jetzt "vlm"|"tesseract"|False. Damit
# kriegt der Admin-Tresor VLM-OCR geschenkt (pytesseract fehlt im venv). Additiv, Vertrag bleibt 1.5.
# 1.26.0 (Extraktions-Naht geteilt, KA-M7 C1, 10.07., World-Admin-Bau): appkit/extract.py —
# die „Datei → Text"-Naht (DOCX/TXT stdlib · PDF pypdf · Bild-OCR) aus adminapp/extract.py
# nach appkit promoted (W-1-„net_safe"-Muster); adminapp/extract.py re-exportiert 1:1 (Tresor
# unberührt). EINE Quelle für Admin-Tresor UND Memory-RAG-Ingestion (C2). _bild_ocr auf den
# (text, methode)-Vertrag gehoben (VLM-OCR-Stufe folgt in C3, appkit/vision.py); verfuegbarkeit()
# ["ocr"] jetzt dreiwertig "tesseract"|False (C3 ergänzt "vlm"). Additiv, Vertrag bleibt 1.5.
# 1.25.0 (Lösch-Invariante-Prüfkit KA-H1, 10.07., Bau-KI-Bau-Chat): appkit/loesch_pruefung.py
# — zwei pytest-freie Prüf-Funktionen, die die App-Suiten importieren, um die DSGVO-Art.-17-
# Invariante zu beweisen: user_tabellen_ohne_deckung() (STATIK: jede user_id-Tabelle ohne
# deleted_at, die kein on_delete-Hook hart löscht und keine Ausnahme ist ⇒ Liste ≠ [] ⇒ Suite
# rot; fängt die Fehlerklasse „neue Tabelle, niemand räumt sie" für immer) + pruefe_hook_loescht()
# (DYNAMIK: nach Konto-Löschung COUNT(*) je Hook-Tabelle = 0). Nackte sqlite3-conn (auch Core
# nutzbar, eigene conn-Verwaltung). Additiv, Vertrag bleibt 1.5.
# 1.24.1 (CSP style-src-Fix, 21.06., World-Admin-Chat): build_csp behält style-src IMMER
# 'self' 'unsafe-inline' (auch voll-strikt) — Nonce gilt NICHT für inline style="…"-ATTRIBUTE
# (nur <style>-Elemente), strikte style-src hätte alle Stil-Attribute blockiert ⇒ Layout-Bruch
# (empirisch vom finanzen-Chat belegt). „Voll-strikt" = nur script-src nonce (Google-strict-csp).
# 1.24.0 (CSP-Baseline-Stufe, 20.06., World-Admin-Chat, D4): csp.build_csp/install_csp +
# create_app bekommen `strikt`/`csp_strikt`. strikt=False (BASELINE, Default) = 'unsafe-inline'
# für script/style (lässt Bestands-Inline-Handler onclick=… laufen), blockt aber extern/object/
# frame/base-Injektion ⇒ nicht-brechende Real-Härtung für die Inline-lastigen Frontends.
# strikt=True (Nonce) erst nach Inline-Handler-Umbau je App (§5d). docs/36 D4.
# 1.23.0 (Connector-Gerüst, 20.06., World-Admin-Chat, Arbeitsblock W4): appkit/connectors.py —
# universelles ExternalConnector-Interface + DormantConnector + ConnectorRegistry +
# connectors_router (GET /api/konnektoren, read-only). Fundament der Konnektivitäts-Vision
# (docs/35 §5.1): jede App erbt das standalone-konnektiv; LESEN read-only/best-effort,
# SENDEN nur über App-K4-HITL, Tokens im Tresor, echte Plattform-APIs = Stecker (dormant).
# 1.22.0 (Nonce-CSP, 20.06., World-Admin-Chat, Arbeitsblock W2): appkit/csp.py — nonce-
# basierte Content-Security-Policy (install_csp + serve_html_mit_csp + build_csp/inject_nonce),
# opt-in je App über create_app(csp_mode=) [aus|report-only|enforce], Default 'aus' (kein
# Verhaltenswechsel bis die App ihre index.html mit Nonce ausliefert). Sicherheits-Fundament
# der Konnektivitäts-Vision (docs/35/36); per-App-Allowlist-Scharfschaltung = Paket D4.
# 1.21.2 (db busy_timeout, 20.06., World-Admin-Chat, Kern-Dauerschleife R3): get_conn
# setzt PRAGMA busy_timeout=5000 — parallele Writer (User-Write + Querverbindungs-/
# Relay-Write aus anderem Request-Thread) warten bis 5 s statt sofort SQLITE_BUSY
# („database is locked") an den Nutzer durchzureichen. synchronous bleibt FULL.
# 1.21.1 (defense Loopback-Ausnahme, 20.06., World-Admin-Chat): defense.py drosselt
# lokale Poller (127.0.0.1: Desktop-Monitor, Core-Health-Watch/-Panels, Admin-Aggregator)
# auch innerhalb Stufe 1 NICHT mehr (sonst 429-Flackern im Netzwerk-Cockpit trotz
# laufender App); externe Clients bleiben bei S1 unverändert gedrosselt. Reine
# Bugfix-Vendor-Welle (Inhalt war seit 1.21.0 nur in der Kanon-Quelle gefixt).
# 1.21.0 (A5 Bereichs-Querverbindungs-Helfer, 20.06., World-Admin-Chat): querverbindung.py
# +finanzspur_holen (V17) / bereich_social_holen (V18) / kategorie_holen (V19) — die Admin-
# seitigen RÜCK-LESE-Helfer, die die neuen Core-Relays (core/app/main.py) aufrufen, um je
# Bereich (bereich.money_kontext / management_kontext / memory_ref) Finanzspur / Social /
# Wissen read-only zu ziehen (Muster memory_suche/belege_holen, best-effort, wirft nie).
# Additiv, Vertrag bleibt 1.5. (Vendoring + App-Aggregations-Endpunkte = A5-Phase-2, sobald
# die aktuell aktiven App-Repos frei sind; docs/34.)
# 1.20.0 (Gateway-Settings ins base_schema, 20.06., World-Admin-Chat): die zwei
# Per-App-MCP-Gateway-Settings (mcp_gateway_mode + mcp_gateway_freigabe_hochsicher)
# wandern aus Dizz Admins lokalem extra-Schema in settings_core.base_schema (Kategorie
# vernetzung) ⇒ JEDE App zeigt sie im Einstellungsfenster; app_gateway liest sie
# unverändert. Additiv (Vertrag bleibt 1.5); Apps mit eigenem Gateway-Mount erben sie,
# Dizz Admin definiert sie nicht mehr lokal (Doppel-Schlüssel-Schutz).
# 1.19.0 (Querverbindung-Default + Per-App-MCP-Gateway, 20.06., World-Admin-Chat):
# (a) querverbindung.sende_termin Default-Ziel "plans" -> "admin": die Kalender-Ziel-
#     App ist nach dem Plans+Admin+Leading-Merge (docs/28/29) "admin"; "plans" war tot
#     (jeder Aufruf OHNE explizites ziel sendete ins Leere). Reine Default-Aenderung,
#     additiv; Aufrufer mit explizitem ziel= (Admins Ruecksender) sind unberuehrt. Die
#     Default-relevanten Live-Aufrufer (Communication-V5, Healthy-Termin) werden per
#     Re-Vendoring korrekt; ihre Tests ziehen mit (docs/29 §4.1/§4.2/§7.1).
# (b) appkit/app_gateway.py (build_app_gateway) ist Teil des vendorten appkit-Satzes:
#     Standalone-Per-App-MCP-Gate (read-only, Bearer-Token, Hochsicher-Gate, auto-
#     Abschaltung im Verbund). Inert bis eine App es in ihrer main.py mountet (docs/31
#     §7) -> Vendoring ist nebenwirkungsfrei; die Pro-App-Verdrahtung folgt separat (A3).
# 1.18.0 (HTML-no-cache, 18.06., UI-Kit-Vereinheitlichung): headers-Middleware setzt
# Cache-Control:no-cache auf text/html-Antworten (index.html) -> Frontend-Edits
# (Kit/Settings/Header) schlagen netzwerkweit zuverlaessig durch (kein Heuristik-Cache).
# 1.17.0 (Push-Helfer-Timeout, 17.06., Audit-Runde 4 / docs/25 H-18): die POST-
# Querverbindungs-Helfer (querverbindung.archiviere / sende_termin / verknuepfe /
# loese_verknuepfung) nehmen jetzt — wie die GET-Helfer memory_suche/belege_holen —
# einen optionalen ``timeout``-Parameter (Default 5,0 s). Der Storno-/Beleg-Lösch-Pfad
# (Money _loese_beleg_verknuepfung) ruft mit 2,5 s, damit ein OFFLINE Ziel/Core die
# Storno-Antwort nicht spürbar verzögert (war die offene H-16-Latenz). Additiv (Default
# unverändert), Vertrag bleibt 1.5; best-effort/wirft nie.
# 1.16.0 (CSV-Formel-Injection-Schutz, 17.06., Audit-Runde 3): appkit.csv_safe.csv_safe()
# entschärft CSV-Zellwerte, die mit =,+,-,@ beginnen (Excel/Calc würde sie als Formel
# ausführen), per führendem Apostroph. Netzwerkweites Sicherheits-Util für die Steuer-/
# Geschäfts-Exporte (EÜR/Buchungen/Trading/GoBD), die an Dritte gehen. Vertrag bleibt 1.5.
# 1.15.0 (V15 Storno-Cleanup, 17.06., Audit H-15a): querverbindung.loese_verknuepfung()
# meldet dem Ziel das Auflösen einer Beleg-Verknüpfung (von_ref↔ziel_ref, aktion="loesen"
# im selben verknuepfung-Umschlag) ⇒ kein verwaister „verwendet in N"-Hinweis nach Storno/
# Beleg-Entfernen. Additiv (verknuepfe sendet jetzt aktion="anlegen"), Vertrag bleibt 1.5.
# 1.14.0 (V15 Beleg-Verknüpfung, 17.06., docs/26 §12): querverbindung.verknuepfe() legt
# beim Ziel eine Rück-Referenz an (bidirektionaler Beleg-Link Money↔Admin, Core-Relay
# POST /api/querverbindung/{ziel}/verknuepfung) + querverbindung.belege_holen() zieht die
# verknüpfbaren Belege/Dokumente vom Ziel (GET /api/querverbindung/{ziel}/belege). Dritter
# Vertragstyp neben Archiv + Kalender; additiv, Vertrag bleibt 1.5, best-effort/wirft nie.
# 1.13.1 (Rück-Lese-Timeout, 17.06., H-Scan): querverbindung.memory_suche nimmt einen
# optionalen ``timeout``-Parameter (Default 5,0 s für explizite Suchen); der mini_dizzi-
# Rück-Lese-Pfad (_rueck_lese) ruft mit 2,5 s, damit ein träger Core/Memory die KI-Antwort
# nicht spürbar verzögert — degradiert weiter sauber zu leer. Additiv, Vertrag bleibt 1.5.
# 1.13.0 (Rück-Lese in Mini-Dizzi, 16.06., docs/26 §4c): mini_dizzi._fallback zieht
# gegated (Setting ``ki_wissen_rueck_lese``, Default an) app-übergreifendes Wissen aus
# Dizz Memory (querverbindung.memory_suche) in den Ollama-Kontext — best-effort, wirft nie,
# `memory_get`-Injektion für Tests. Vertrag unverändert 1.5 (additiv). Alle Apps erben es beim Re-Vendoring.
# 1.12.0 (Security-Header H-2, 16.06., docs/25 / docs/18): appkit/headers.py
# ``install_security_headers(app)`` — Middleware, die auf JEDE Antwort drei
# Defense-in-Depth-Header setzt: X-Content-Type-Options=nosniff ·
# Referrer-Policy=no-referrer · X-Frame-Options=SAMEORIGIN (setdefault, bricht
# Passkey/IdP-Flows nicht). In create_app als ZULETZT registrierte = äußerste
# Middleware (stempelt auch Guard-/Defense-Abweisungen); der Core hängt sie
# ebenfalls ein. CSP bewusst später. Additiv, Vertrag bleibt 1.5.
# 1.11.0 (Daten-Hygiene on_delete-Hook, 16.06., docs/25 H-7): create_app/
# contract_router nehmen einen optionalen ``on_delete(user_id)``-Hook, den
# POST /api/account/loeschen NACH der DB-Soft-Delete-Kaskade + Tresor-Wipe
# aufruft — damit eine App ihre EXTERNEN Artefakte (Dateien/Indizes außerhalb
# der DB) mit-räumt (DSGVO „weg = weg"). Memory hängt dort Vault-Verzeichnis-
# Räumung + RAG-Index-Reset des Nutzers ein; Creating-DAM/Admin-Vault nutzen
# denselben Hook. Best-effort: ein Hook-Fehler bricht die (rechtlich maßgebliche)
# Konto-Löschung NICHT, sondern wird auditiert + ehrlich gemeldet
# (``artefakte_geraeumt``). Additiv, Vertrag bleibt 1.5.
# 1.10.0 (Querverbindungen Rück-Lese, 15.06.): die „↔"-Richtung der Querverbindungen
# (V5–V11, docs/26 §10.1). appkit/querverbindung.py +``memory_suche(q, semantisch=…)``
# = Lesehelfer (Gegenstück zu ``archiviere``): fragt das zentrale Archiv App→Core→Ziel
# ab, über den Core-Relay GET /api/querverbindung/{ziel}/suche. Best-effort (wirft nie,
# leere Treffer bei Fehler). appkit/mcp.py: ``build_http_mcp(..., query_tools=…)`` —
# PARAMETRISCHE read-only MCP-Tools (Suchtext ``q`` + ``anzahl``), damit der Core-Agent
# das Memory-Archiv parametrisch abfragt (Memory mcp_server: ``memory_suche``/
# ``memory_semantisch``). Additiv, Vertrag bleibt 1.5. Zugleich appkit-Drift-
# Vereinheitlichung (docs/25 H-9): in alle 9 aktiven Apps auf 1.10.0 vendort.
# 1.9.0 (Querverbindungen V5, 15.06.): appkit/querverbindung.py +``sende_termin(…)``
# — ZWEITER Vertragstyp (Kalender-Event) neben ``archiviere``: trägt ein Event
# App→Core→Ziel-Kalender-App (Default Dizz Plans) ein, über den Core-Relay
# POST /api/querverbindung/{ziel}/kalender. Best-effort (wirft nie), idempotent
# per ``ref``. Spec docs/26. Additiv, Vertrag bleibt 1.5.
# 1.8.0 (Robustheit, 15.06.): db.Database._apply_schema — Schema-Anwendung ist
# tolerant gegen eine einzelne DDL-Anweisung, die auf einer ALT-DB scheitert,
# weil sie auf eine erst per App-Migration nachgerüstete Spalte verweist
# (z. B. CREATE INDEX auf neuer Spalte). Happy-Path unverändert (executescript);
# nur im Fehlerfall Statement-für-Statement, Einzelfehler überspringen. Schließt
# die Bug-Klasse „Schema-DDL auf Migrations-Spalte = Restart-Block auf Alt-DBs"
# netzwerkweit (docs/25 H-8). Additiv, Vertrag bleibt 1.5.
# 1.7.0 (Querverbindungen Phase 2, 15.06.): appkit/querverbindung.py —
# Übergabe-Helfer ``archiviere(app_id, titel, inhalt, …)`` reicht ein Element
# App→Core→Ziel-Archiv (Default Dizz Memory) weiter. Best-effort (wirft nie),
# single-user/localhost-Guard (kein Token), HITL/Sensitivität via ``sensibel``
# (Ziel-KI lokal_only). Gegenstück = Core-Relay POST /api/querverbindung/{ziel}
# (auditiert zentral). Spec docs/26. Additiv, Vertrag bleibt 1.5 (optionaler
# Client — keine neue App-Pflicht; Empfänger ist eine Memory-Eigenschaft).
# 1.6.0 (MCP-Namensraum, 13.06.): MCP-Tools tragen den App-Namensraum
# `<app_id>_<tool>` (appkit/mcp.py:namespaced + build_http_mcp praefixt
# automatisch) — verhindert Kollisionen, sobald ein Host mehrere App-Server
# buendelt (Leading/Core-Agent). Least-Privilege als Norm (docs/16 §6, docs/23
# R-3). Additiv, Vertrag bleibt 1.5 (kein Manifest-Schema-Bruch).
# 1.5.0 (K2.2-b Katalog v1.1, 13.06.): auf 10×10 erweitert (Nutzer-Feedback) —
# +2 farbige Grunddesigns (inferno=Magma-Rot · kobalt=Royalblau) + 2 stechende
# Paletten (toxic=Neon-Acid · voltage=Elektro); feuer von koralle entkoppelt
# (pures Orange→Scharlach statt orange-pink). Werte: shared/dizz-tokens.css. Vertrag 1.5.
# 1.4.0 (K2.2-b Katalog, 13.06.): Theme-/Farb-Katalog ausgebaut (Nutzer-Katalog-
# Session) — 8 Design-Themes (metall|neon|flach|tag|carbon|pergament|synthwave|
# lagune; die letzten beiden tragen Farbe im Grunddesign) × 8 Farbschemata
# (cyan-magenta|smaragd-gold|violett-eis|bernstein|arktis|koralle|limette|feuer).
# Token-Master mit allen Werten: shared/dizz-tokens.css (kanonische Single Source).
# Weiterhin additiv (nur Choices erweitert), Vertrag unverändert (1.5).
# 1.3.0 (K2.2, 13.06.): Übergreifendes Design-System — base_schema trägt jetzt
# die ZWEI getrennten Design-Achsen als typisierte Settings (darstellung):
# design_vorlage (metall|neon) + farb_schema (cyan-magenta|smaragd-gold|
# violett-eis). Werte = 1:1 die <html>-Attribute des Token-Vertrags
# (ui-kit/tokens.css), darum mappingsfrei. RÜCKWÄRTSKOMPATIBEL (additiv, mit
# Defaults) ⇒ Vertrag unverändert (1.5). Apps hängen ihre freien
# x_design_vorlage/x_farb_schema beim UI-Bau nur auf diese Schlüssel um.
# 1.2.0 (H10, 13.06.): Browser-Nav des RP auf localhost (DEFAULT_NAV_ISSUER —
# Passkey-RP-ID + EINE Cookie-Welt) + redirect_uri HOST-KONSISTENT aus dem
# Request abgeleitet (PKCE-Cookie-Host; Fallback Manifest-URI). iss bleibt
# 127.0.0.1 (nur Identifier). Vertrag unverändert (1.5).
# 1.1.0 (Tiefen-Review 12.06.): Datenhygiene Database.retention_lauf
# (aufbewahrung_tage wird im create_app-Lifespan DURCHGESETZT) · Vault-Lock
# gegen parallele Read-Modify-Writes · Defense-Speicher-Pruning
# (_vorfall_dedupe/_sperr_historie). Vertrag unverändert (1.5).

# Vertrags-Version: ändert sich nur bei inkompatiblen Änderungen an Endpoints/
# Schemata. Apps melden sie in /api/health und /api/manifest; Dizzi kann damit
# inkompatible Apps erkennen, statt still falsch zu rendern.
# 1.1 (K2): /api/settings typisiert (PUT strikt, freier Namensraum x_…),
#           + /api/settings/schema, /api/account, /api/vault (Token-Tresor).
# 1.2 (K4): /api/actions (Aktions-Vorschläge mit Human-in-the-Loop-Stufen:
#           propose→pending→approve/reject; Freigabe verlangt HITL-Stufe)
#           + Event-Push App→Dizzi (appkit/events.py, Core /api/events).
# 1.3 (K2.1b): Datenrechte — POST /api/account/export (DSGVO-Export, JSON)
#           + POST /api/account/loeschen (Soft-Delete-Kaskade + Tresor-Wipe);
#           beide hinter require_fresh_stepup('verifiziert') = Re-Auth Pflicht,
#           fail-closed standalone (docs/19 §1+§3).
# 1.4 (F-DEF1): Dizz Defense — Per-App-Immunsystem (appkit/defense.py,
#           docs/20): Sensorik-Middleware + Regel-Engine/Basislinie +
#           Stufenwerk S0–S5 mit Autonomie-Politik (S1–S3 autonom befristet,
#           S4/S5 HITL; Lokal-Schonung) + /api/defense-Cockpit + Journal.
#           Pflicht für create_app-Apps (default an); Bestands-Apps rüsten
#           via install_defense() nach (TB = O-DEF).
# 1.5 (Mini-Dizzi): KI-Stimme/Sprach-Brücke je App (appkit/mini_dizzi.py):
#           App-KI-Slot (set_app_ki) + generischer Ollama-Fallback +
#           POST /api/ki/frage + GET /api/ki/status + Verbund-Gating
#           (lauscht_lokal: standalone selbst, im Verbund nur zentral Dizzi).
#           Per-App-Mikro = vorbereiteter Slot. create_app default an.
CONTRACT_VERSION = "1.5"


def ui_kit_path():
    """Pfad zum GETEILTEN UI-Kit (controls.css/collapse.js/tokens.css/spinfling.js/…).
    Aufgelöst als Schwester des appkit-Pakets: Monorepo ``packages/ui-kit``,
    Einzel-App-Export ``<root>/ui-kit``. Override per Env ``DIZZ_UI_KIT_DIR``.
    Ersetzt die früheren per-App-vendorierten ``<app>/ui-kit``-Kopien (Single-Source)."""
    import os
    from pathlib import Path
    env = os.environ.get("DIZZ_UI_KIT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "ui-kit"
