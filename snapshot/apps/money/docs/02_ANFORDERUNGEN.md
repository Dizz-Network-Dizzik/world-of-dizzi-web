# Anforderungsliste — Dizz Money — Finanzmanagement

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss)
- [x] **Doppelte Buchführung — eigener Double-Entry-Kern GEBAUT (12.06., Architektur-KI)**:
  `moneyapp/ledger.py` (Minor-Units/Integer-Cents, nie Float; Posting/Buchung mit
  harter Invariante Summe=0; typ-orientierter Anzeige-Saldo; Property-getestet).
- [x] **Import (CSV/camt.053/MT940) GEBAUT (13.06., Bau-KI)**: `moneyapp/importers/`
  (reine Parser je Format + Dispatcher; tolerantes CSV-Spalten-Mapping über Profile
  DE/EN; stabiler Dedupe-Hash; `POST /api/import` → Buchung je Bewegung,
  Bankkonto ↔ Sammelkonto „Nicht zugeordnet"). Property-/Fixture-Tests.
- [x] **Kategorisierung + Budgets + Auswertung GEBAUT (13.06., Bau-KI)**:
  lernende Regel-Engine (`moneyapp/regeln.py`), Kategorien-CRUD, Budgets je
  Kategorie/Monat, deterministische Auswertungen (`moneyapp/auswertung.py`:
  Cashflow/Vermögen/Budget-Soll-Ist).
- [x] **Steuer-Sektor (licht) GEBAUT (13.06., Bau-KI)**: steuerrelevante Kategorie-Flags
  + EÜR-artige Jahres-Auswertung + Export JSON/CSV. **Kein Filing/keine Steuererklärung.**
- [x] **Frontend (tokenbasiert) GEBAUT (13.06., Bau-KI)**: `static/index.html` nach
  News-Muster (2 Achsen, Spin v4.3, Float-Treiber, #kontoModal 5 Gotchas, Mini-Dizzi).
- [x] **Wiederkehrende Posten GEBAUT (13.06., Bau-KI)**: `moneyapp/wiederkehr.py` (rein) erkennt
  Abos/Daueraufträge aus der Historie (Konfidenz-gefiltert) + plant Fälligkeiten + Monats-Fixlast.
- [x] **FX/Multi-Währung GEBAUT (13.06., Bau-KI)**: Ledger balanciert PRO WÄHRUNG (`fx_buchung` über
  Währungstausch-Konten, `umrechnen`); `wechselkurse` (Nutzer-gepflegt); Auswertung nach EUR (≈).
- [x] **App-Wächter-KI (A1) GEBAUT (13.06., Bau-KI)**: `_finanz_ki` via `set_app_ki` — deterministische
  Antworten aus echten Zahlen (Vermögen/Cashflow/Budget/Abos/Konten), sonst Ollama-Fallback.
- [x] Stats-Endpoint: Nettovermögen + Konten + Cashflow-30T-KPI (Saldo via Postings-Summe).
- [x] MCP-Tools (read-only): kontostand, nettovermoegen, cashflow, vermoegen, lebenszeichen.

## Quer (aus dem App-Vertrag, gilt für alle) — ✅ über appkit `create_app`
- [x] Stats-Endpoint `/api/summary` (Dashboard-Kachel) — live, in Dizzi angedockt
- [x] MCP-Server (read-only Tools) — `finanzen/mcp_server.py`
- [x] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login — `install_dizzi_id`
- [x] Account/Settings-Modul (Kernpaket K2) — generisch; KI-Routing default `lokal_only` (sensitivity hoch)
- [x] Daten user-scoped + sync-ready; sensible Daten lokal
- [x] **Dizz Defense (Vertrag 1.4)** — Per-App-Immunsystem aktiv
- [x] Tests + Doku-Sync (Gesetz 9) — 80 Tests (inkl. Property-Tests), grün

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener schlanker Double-Entry-Kern (Firefly-Modell als Blaupause; Decimal/Minor-Units,
  Splits-Invariante Summe = 0, Property-Tests). Keine OSS-Einbettung.
- **v1:** Konten/Vermögen + Budgets/Cashflow + Kategorien/Regeln; **Steuer-Sektor** (Belege/Fristen) liegt hier.
- **Bank-Anbindung: NUR LESEND (AISP), kein PISP/Zahlungen.** Fokus Hauptkonto + weitere **DE-Konten** →
  **FinTS/HBCI zuerst** (0 €); **Revolut** via Open-Banking. Import CSV/CAMT/MT940/OFX als Offline-Pfad.
- **Sensibilität:** HOCH → lokal; Echtgeld/Steuer hinter verifizierter Verbindung (K1).
- **Marke:** Dizz Money (bestätigt).
