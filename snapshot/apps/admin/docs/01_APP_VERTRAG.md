# App-Vertrag — Dizz Leading — Geschäftsführung

> Verbindlich: So dockt diese App ans Gesamtsystem an. **Spezifikation GEBAUT (K3, 12.06.2026):**
> Norm = `the world of dizzi/docs/16_APP_VERTRAG_SPEC.md` · Bibliothek = `the world of dizzi/appkit/`
> (wird hierher vendort) · Kopier-Vorlage = `the world of dizzi/templates/refapp/`.

## Pflicht-Bestandteile
1. **Eigener Core-Service** (FastAPI), Port-Vorschlag **8219** (lokal, localhost-gebunden).
2. **Read-only Stats-Endpoint** `/api/summary` → Geschäfts-Kachel (Umsatz, offene Rechnungen,
   Fristen, Support-Last).
3. **MCP-Server** (stdio, read-only zuerst): geschaefts_kpis, offene_rechnungen, naechste_fristen.
4. **Dizzi-ID-Anbindung** (Relying Party) + lokaler Standalone-Login; Geschäftsbereiche hinter
   verifizierter Verbindung; Steuer-/Export-Aktionen mit Re-Auth (K2.1 `reauth_sensibel`).
5. **Account/Settings-Modul** (K2) + Konten-/Quellen-ZUWEISUNG („geschäftlich") als Settings-Sektion.
6. **Deep-Link** + **Vernetzungs-Manifest**: sensitivity **hoch**; `depends`: admin, finanzen,
   kommunikation (liest per MCP/Vertrag — Kern-Eigenschaft dieser App).

## Datenkonventionen
- SQLite, **user-scoped + sync-ready**: UUID-PK, `user_id`, `created_at`/`updated_at`, `deleted_at`.
- Laufzeitdaten unter `C:\Dizzik\data\apps\leading\`; GoBD-relevante Artefakte unveränderbar
  archiviert (Append-only-Ablage + Audit).

## KI-Interaktion
- Read-only Tools Standard; Aktionen (Rechnung stellen/versenden, Export) = **Human-in-the-Loop**
  (K4), sensible auf Stufe `verifiziert`+ mit frischem Step-up.

## Universelle Pflicht-Prinzipien (Details: APP_GRUNDLAGEN.md §A)
- **Eigener Wächter-/Lern-KI-Kern (A1)** · **Design-Baseline (A2)** inkl. schwebendem
  Settings-+Account-Knopf · **Vernetzung (A3)**: Cross-Zugriff geregelt, protokolliert.
