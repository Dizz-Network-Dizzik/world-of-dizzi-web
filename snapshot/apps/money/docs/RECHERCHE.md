# Recherche-Dossier — Dizz Money (Finanzen)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> Zweck: Konnektoren, Standards und **jetzt vorzusehende** Verbindungs-Vorbereitungen für einen
> sauberen, effizienten Bau (keine Nachrüst-Schulden). SENSIBLE App → lokal-first.

## 1. Feature-Baseline (Marktstandard)
Etablierte Referenz für sauberen Finanz-Kern ist **Firefly III** (Open Source, self-hosted):
konsequente **doppelte Buchführung** (jede Buchung hat Quelle + Ziel), Konten/Vermögensübersicht,
Budgets (Envelope/Zero-Based), Kategorien + Tags, **Regel-Engine** (Auto-Kategorisierung),
wiederkehrende Posten, Reports/Trends, REST-JSON-API über fast alles. Pflicht-Baseline für v1:
- Konten- & Vermögensübersicht (manuell zuerst, Bank-Anbindung als Stufe 2)
- Budgets + Cashflow (Monat), Kategorien/Regeln, wiederkehrende Posten
- Import + Auto-Kategorisierung; Reporting; Beleg-/Steuer-Sektor als Ausbaustufe

## 2. Standard-Datenquellen & Konnektoren
- **Deutschland zuerst: FinTS/HBCI** — direkter, **kostenloser** Bank-Standard (kein Aggregator, keine
  Lizenz nötig), ideal für die 0-€-Prämisse. Bestpassend für einen DE-Nutzer.
- **Open Banking / PSD2 (EU)** über Aggregator als breitere Option: **GoCardless/Nordigen** (free-Tier
  für EU-Banken, von Firefly nativ unterstützt), **Tink** (Visa), **TrueLayer**, **Salt Edge/Spectre**.
  Rollen: **AISP** (Kontodaten lesen) reicht; **PISP** (Zahlungen auslösen) nur später, hart gegated.
- **Datei-Import-Standards**: CSV, **OFX/QIF**, **MT940**, **CAMT.053** (SEPA-Kontoauszug) — robuster
  Offline-Pfad ganz ohne API.
- **Krypto/Trading**: nicht selbst anbinden → über **Dizz Trading** (MCP) als Vermögens-Posten ziehen.
- **Steuer**: **ELSTER** (Belege/Übermittlung) — Überschneidung mit **Dizz Admin** (dort federführend,
  Money konsumiert).

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **Konto-Aggregator-Adapter-Slot** (Interface `BankSource`): zwei Implementierungen vorgesehen —
  `FinTSSource` (DE-direkt) und `OpenBankingSource` (Nordigen/Tink), austauschbar; v1 liefert nur den
  `ManualSource`. So ist die Bank-Anbindung ein Stecker, kein Umbau.
- **CAMT.053/MT940-Parser** als eigenständiges Import-Modul (auch ohne Live-Banking nützlich).
- **PISP-/Zahlungs-Slot** vorgesehen, aber deaktiviert hinter Echtgeld-Gate (Passkey/MFA, K1).
- **Steuer-Brücke** zu Dizz Admin (Beleg-Referenzen statt Doppel-Haltung).

## 4. App-eigener KI-Wächter-Kern
Beobachtet/lernt: Ausgaben-Anomalien, **Abo-/Dauerauftrag-Erkennung**, Budget-Drift, Cashflow-Prognose,
Spar-/Umschichtungs-Vorschläge, Doppelbuchungen. Meldet nach oben an Dizzi (L4-Beobachtung) — nur
**vorschlagen**, nie eigenmächtig buchen.

## 5. Sensible Daten & Sicherheit (lokal-first)
Konto-/Steuer-/Echtgeld-Daten bleiben **standardmäßig lokal**, **nie** an Boost-/Cloud-Modelle.
Zugriff nur bei **verifizierter Verbindung**; Echtgeld-Aktionen (PISP) hinter **Passkey/MFA** (K1).
Bank-Zugangsdaten/Tokens nur in `.env`-Secret-Ablage außerhalb Repo/OneDrive.

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **Geld = Integer-Minor-Units oder `Decimal`, NIE float** (Rundungs-/Buchungsfehler).
- **Double-Entry-Schema** als Fundament (Firefly-inspiriert): Transaktion = Quelle→Ziel, Konten-Typen,
  Splits; user-scoped + sync-ready (UUID/Timestamps/Soft-Delete) ab Tag 1.
- Standards nutzen statt erfinden: **FinTS**, **CAMT/ISO 20022**, **OFX**. Aggregator hinter einem
  schmalen Interface kapseln (kein Anbieter-Lock-in).
- 0-€-Pfad: FinTS-direkt + Nordigen-Free; lokale KI für Kategorisierung (sensibel → kein Boost).

## 7. Offene Entscheidungsfragen → Fragerunde
1. **✅ ENTSCHIEDEN (F-Q1, Architektur-KI 11.06., docs/11 §6b): eigener schlanker Double-Entry-Kern** —
   Firefly-Datenmodell nur als Blaupause + Firefly-CSV-Import-Kompatibilität. Gründe: kein Docker/PHP
   auf der Maschine, Firefly = AGPL-3.0 (kollidiert mit Einzel-Verkaufbarkeit), App-Vertrag (K1–K6)
   in Fremd-Schema nicht nachrüstbar. Ledger mit Decimal + Splits-Invariante Summe=0 + Property-Tests.
2. **Bank-Anbindung v1**: FinTS-direkt (DE, 0 €) zuerst — Aggregator später? Oder beides als Slot, v1 manuell?
3. **PISP/Zahlungen** überhaupt je gewünscht, oder bewusst nur lesen (AISP)?
4. **Steuer-Sektor**: in Dizz Money oder in Dizz Admin (Belege/Fristen/ELSTER)?

## Quellen
- [Open Banking Tracker — Aggregatoren/PSD2](https://www.openbankingtracker.com/banking-data-aggregation)
- [Plaid — PSD2 & Open Banking](https://plaid.com/open-banking/)
- [Plaid vs Tink vs TrueLayer (2026)](https://www.fintegrationfs.com/post/plaid-vs-tink-vs-truelayer-which-open-banking-api-is-best-for-your-fintech)
- [Firefly III — GitHub](https://github.com/firefly-iii/firefly-iii) · [Doku/Intro](https://docs.firefly-iii.org/explanation/firefly-iii/about/introduction/)
