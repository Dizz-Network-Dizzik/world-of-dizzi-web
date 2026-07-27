# Recherche-Dossier — Dizz Leading (Geschäftsführung) · 12.06.2026

> **EXKLUSIV-App des Nutzers** (nicht verkaufbar — sie VERWALTET das Verkaufen):
> die Geschäftsführungs-Zentrale für den Fall, dass das Dizz-Netzwerk Produkt/
> Service/Geschäft wird. Web-recherchiert (Quellen unten). Sensibilität **hoch**.

## 1. Zweck & Abgrenzung
Dizz Leading = **Meta-Ebene über dem Netzwerk**: alles Geschäftliche an einem Ort —
Geschäfts-Bürokratie, Produkt-/Netzwerk-Verwaltung, Kunden/Lizenzen, Geschäftszahlen.
**Abgrenzung:** Dizz Admin = persönliche Bürokratie · Dizz Money = persönliche Finanzen ·
Leading = GESCHÄFTS-Sicht; es KONSUMIERT die Schwestern (interne Vernetzung per MCP/Vertrag)
statt sie zu doppeln: Geschäfts-Mails via **Communication** (Konten-Zuweisung „geschäftlich"),
Geschäfts-Belege via **Admin**, Geschäftskonto via **Money**.

## 2. Feature-Baseline (Markt: sevdesk/Lexware/Papierkram + Indie-SaaS-Ops)
**Deutsche Geschäfts-Pflichten (Solo-Gründer):**
- **Angebote/Rechnungen** mit **GoBD-konformer Archivierung** (unveränderbar, nachvollziehbar);
  **E-Rechnungs-Pflicht**: seit 2025 müssen auch Kleinunternehmer E-Rechnungen (XRechnung/ZUGFeRD)
  **empfangen/verarbeiten** können · **EÜR** (Einnahmen-Überschuss-Rechnung) · **UStVA**-Vorbereitung
  (bzw. Kleinunternehmer-Regelung §19) · Beleg-Archiv · Fristen (Steuer, Meldungen).
**Indie-SaaS-/Produkt-Ops:**
- **Produkt-Registry**: die Dizz-Apps als Produkte (Version, Release-Stand, Changelog)
- **Lizenz-/Abo-Verwaltung** (License-Keys, Laufzeiten, Dunning-Gedanke), **Kunden-CRM light**
  (Kontakte, Verträge, Support-Verlauf) · Support-Posteingang (via Communication-Zuweisung)
- **Geschäfts-KPIs**: Umsatz/MRR, Kunden, offene Rechnungen, Support-Last, Release-Gesundheit
- Merchant-of-Record/Zahlungsanbieter als spätere Konnektor-Slots (Stripe/Creem/…)

## 3. Verbindungs-Vorbereitungen (Gesetz 5)
- **`GeschaeftSource`-Slots**: Buchhaltungs-Export (DATEV/CSV für Steuerberater), E-Rechnung
  (XRechnung/ZUGFeRD-Parser+Writer), Zahlungsanbieter-Slot, Bank-Geschäftskonto (via Money-Muster).
- **Interne Vernetzung (der Kern!)**: Leading liest per **MCP/App-Vertrag** aus Admin (Belege/
  Fristen mit Tag „geschäftlich"), Money (Geschäftskonto-Posten), Communication (zugewiesene
  Geschäfts-Mail-Konten), News (Markt-Kontext) — **Konten-/Quellen-ZUWEISUNG** je App
  („dieses Postfach/Konto = geschäftlich") als gemeinsames Muster (cross_app_zugriff, K2.1).
- **Produkt-Telemetrie-Slot** (opt-in, später): Versions-/Fehlerstand der verkauften Apps.

## 4. App-eigene Lern-KI (Wächter)
Triage des Geschäfts-Posteingangs, Rechnungs-/Fristen-Erinnerungen, KPI-Anomalien
(„Umsatz-Knick", „Support-Stau"), Quartals-/Steuer-Vorbereitung als Checklisten-Vorschläge,
Untersektionen-Management (je Geschäftsbereich eine Beobachtungs-Sicht). HITL wie überall.

## 5. Sicherheit
sensitivity **hoch** (Geschäftsdaten/Steuern): lokal-first, KI nur lokal; Verträge/Kunden-PII im
verschlüsselten Bereich; Re-Auth (K2.1 `reauth_sensibel`) vor Export/Steuer-Aktionen; Audit Pflicht.

## 6. Bau-Einordnung (WICHTIG)
Leading ist **Aggregator** → baut auf Admin/Money/Communication auf ⇒ **späte R2-Position**
(nach deren v1; Scaffold+Fundament JETZT, damit Schema/Slots überall mitgedacht werden).
Eigene Fragerunde vor Bau: Rechtsform/Kleinunternehmer? Steuerberater-Export? Zahlungsanbieter?

## Quellen
- [sevdesk — GoBD-Anforderungen](https://sevdesk.de/gobd/) · [Buchhaltungssoftware-Vergleich 2026 (E-Rechnungs-Pflicht, EÜR/UStVA)](https://sevdesk.de/ratgeber/buchhaltung-finanzen/rechnung-buchhaltung-programme/buchhaltungssoftware-kleinunternehmer-vergleich/)
- [Papierkram — Funktionsumfang Freiberufler](https://www.papierkram.de/aktuelles/beste-buchhaltungssoftware-freiberufler/)
- [SaaS-Subscription-Management 2026 (Lizenz/Abo/Dunning)](https://www.zenskar.com/blog/saas-subscription-management-solutions) · [Merchant of Record für SaaS](https://www.creem.io/blog/best-merchant-of-record-saas-2026)
- [Indie-Hacker-Ops 2026 (Low-Support-Prinzip, Stack)](https://www.tldl.io/resources/indie-hacker-saas-stack-2026)
