# App-Vertrag — Dizz Management — KI-Agenten-Verwaltung (erste Domäne: Social Media)

> Verbindlich: So dockt diese App ans Gesamtsystem an. (Generalisierung des Panel-/MCP-Musters,
> **Spezifikation GEBAUT (K3, 12.06.2026):** Norm = `the world of dizzi/docs/16_APP_VERTRAG_SPEC.md` ·
> Bibliothek = `packages/appkit/` (Single-Source im Monorepo — kein Vendoring) · Kopier-Vorlage = `templates/refapp/`.)

## Pflicht-Bestandteile
1. **Eigener Core-Service** (FastAPI), Port-Vorschlag **8213** (lokal, localhost-gebunden).
2. **Read-only Stats-Endpoint** `/api/summary` → liefert die Kennzahlen für Dizzis Dashboard-Kachel
   `social` (Muster: Trading Bot `:8137/api/summary`).
3. **MCP-Server** (stdio, read-only zuerst) mit den App-Tools für Dizzis KI
   (Muster: `the world of dizzi/connectors/tradingbot/mcp_server.py`).
4. **Dizzi-ID-Anbindung** (Relying Party): akzeptiert den SSO-Ausweis von Dizzi-ID; eigener
   lokaler Login als Standalone-Rückfall. Sensible Aktionen nur bei verifizierter Verbindung.
5. **Account/Settings-Modul** (eingebettetes Muster aus dem Kernpaket K2): Konto-Profil +
   typisiertes Einstellungs-Schema; Secrets in `.env` außerhalb des Repos.
6. **Deep-Link**: öffnet die eigenständige App-Oberfläche aus Dizzi heraus.
7. **Vernetzungs-Manifest** (`docs/03_VERNETZUNG.md`, folgt): welche Daten/Tools die App teilt und
   wovon sie abhängt.

## Datenkonventionen
- SQLite, **user-scoped + sync-ready**: UUID-PK, `user_id`, `created_at`/`updated_at`, `deleted_at`.
- Laufzeitdaten unter `C:\Dizzik\data\` (außerhalb OneDrive).
- Sensible Daten lokal; 0-€-KI-Strategie (Ollama + Boost-Kette).

## KI-Interaktion
- Dizzi ist MCP-Host; diese App exponiert read-only Tools (später Aktions-Tools mit
  Human-in-the-Loop). Beobachten + vorschlagen, nie eigenmächtiger Eingriff.

## Universelle Pflicht-Prinzipien (Details: APP_GRUNDLAGEN.md §A)
- **Eigener Wächter-/Lern-KI-Kern (A1)**: app-eigene übergeordnete KI, die alles überwacht,
  beobachtet, Daten sammelt/auswertet, dazulernt und mit Dizzi interagiert (Muster: Dizzis
  L4-Beobachter + Analyst + Gedächtnis, app-skaliert).
- **Design-Baseline (A2)**: Mattglanz-Metall + Cyan/Magenta + scharfe Kanten; **schwebender,
  schleuderbarer Settings-+Account-Knopf** in jeder App vorbereitet.
- **Vernetzung (A3)**: geregelter Cross-Zugriff auf Anfrage, protokolliert, sensible Daten hinter
  verifizierter Verbindung.
