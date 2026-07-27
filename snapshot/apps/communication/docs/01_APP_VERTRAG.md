# App-Vertrag — Dizz Communication — Kommunikation

> Verbindlich: So dockt diese App ans Gesamtsystem an. **Spezifikation GEBAUT (K3, 12.06.2026):**
> Norm = `the world of dizzi/docs/16_APP_VERTRAG_SPEC.md` · Bibliothek = `the world of dizzi/appkit/`
> (wird hierher vendort) · Kopier-Vorlage = `the world of dizzi/templates/refapp/`.

## Pflicht-Bestandteile
1. **Eigener Core-Service** (FastAPI), Port-Vorschlag **8218** (lokal, localhost-gebunden).
2. **Read-only Stats-Endpoint** `/api/summary` → Kachel-Kennzahlen (ungelesen je Kanal,
   letzte Synchronisation) für Dizzis Dashboard.
3. **MCP-Server** (stdio, read-only zuerst): posteingang_uebersicht, ungelesen, letzte_nachrichten
   (Metadaten — INHALTE nur lokal, nie automatisch an Modelle).
4. **Dizzi-ID-Anbindung** (Relying Party) + lokaler Standalone-Login; sensible Bereiche nur bei
   verifizierter Verbindung.
5. **Account/Settings-Modul** (K2): Konten-/Kanal-Verwaltung; OAuth-Tokens NUR im Token-Tresor.
6. **Deep-Link**: öffnet die eigenständige App-Oberfläche aus Dizzi heraus.
7. **Vernetzungs-Manifest**: sensitivity **hoechst** (private Kommunikation).

## Datenkonventionen
- SQLite, **user-scoped + sync-ready**: UUID-PK, `user_id`, `created_at`/`updated_at`, `deleted_at`.
- Laufzeitdaten unter `C:\Dizzik\data\apps\kommunikation\` (außerhalb OneDrive).
- Inhalte (Mails/Nachrichten) strikt lokal; 0-€-KI-Strategie nur mit lokalen Modellen.

## KI-Interaktion
- Dizzi ist MCP-Host; diese App exponiert read-only Tools (Metadaten/Zähler). Antwort-Entwürfe/
  Senden = Aktions-Tools mit **Human-in-the-Loop** (K4) — Senden ist Außenwirkung, IMMER bestätigt.

## Universelle Pflicht-Prinzipien (Details: APP_GRUNDLAGEN.md §A)
- **Eigener Wächter-/Lern-KI-Kern (A1)**: lokale Triage/Beobachtung, interagiert mit Dizzi.
- **Design-Baseline (A2)**: Mattglanz-Metall + Cyan/Magenta + scharfe Kanten; **schwebender,
  schleuderbarer Settings-+Account-Knopf** vorbereitet.
- **Vernetzung (A3)**: geregelter Cross-Zugriff auf Anfrage, protokolliert, hinter
  verifizierter Verbindung.
