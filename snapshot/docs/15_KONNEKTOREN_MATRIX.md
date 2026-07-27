# Konnektoren- & Integrations-Matrix (alle Apps) · Stand 11.06.2026

> Quer-schneidende Synthese der 9 App-Recherche-Dossiers (`<app>/docs/RECHERCHE.md`,
> Dizz Trading: `Trading Bot eins/programm/docs/RECHERCHE_DIZZ_TRADING.md`).
> Zweck: zeigen, **was die Apps teilen** und **was die geteilte Kern-Architektur (K1–K6) generisch
> tragen** muss — damit jeder Konnektor ein *Stecker* ist und kein Sonderbau (Gesetz 4: kein Spaghetti).

## 1. Konnektoren-Matrix
| App | Standard-Konnektoren (web-recherchiert) | Offene Standards | Sensibilität | 0-€-Pfad |
|---|---|---|---|---|
| **Dizz Money** | FinTS/HBCI (DE-direkt), Open Banking/PSD2 (Nordigen/Tink/TrueLayer/Salt Edge), Firefly III-Modell | CAMT/ISO 20022, OFX/QIF, MT940, FinTS | **HOCH** (Echtgeld/Steuer) | FinTS direkt + Nordigen-Free |
| **Dizz Healthy** | Apple HealthKit, Google Health Connect, Unified-API (Terra/Spike/Vital), Hersteller (Fitbit/Garmin/Oura), **BLE** | **HL7 FHIR**, BLE-GATT | **HÖCHST** (Gesundheit) | Apple/Google nativ + manuell |
| **Dizz Management** | Plattform-APIs (Meta/X/LinkedIn/TikTok/YouTube…), Unified (Ayrshare/Outstand), Postiz (OSS) | OAuth2, AT-Protokoll (Bluesky) | mittel (Fremd-Tokens) | direkte APIs / Postiz selfhost |
| **Dizz Plans** | CalDAV, Google/MS-Kalender, GitHub/GitLab Issues, Import Todoist/Trello | **CalDAV/iCalendar (RFC 5545)**, OPML n/a | niedrig–mittel | CalDAV/iCal lokal |
| **Dizz Admin** | Paperless-ngx-Modell, IMAP-Inbox, Scan/OCR, ELSTER (Belege/Fristen) | PDF/A, IMAP, OCR (Tesseract) | **HOCH** (amtlich) | Paperless-Modell + Tesseract |
| **Dizz Knowledge** | Markdown-Vault, Readwise/Zotero/Raindrop, Web-Clip, **MCP** | **Markdown + Frontmatter**, BibTeX | mittel (privat) | lokaler Vault + RAG (L3) |
| **Dizz Creating** | Generatoren: Ollama/Piper/SD lokal, ElevenLabs/Runway/HeyGen Cloud; DAM | — (Medienformate) | mittel | lokal SD/Piper/Ollama |
| **Dizz News** | RSS/Atom/JSON Feed, WebSub-Push, XPath-Scrape, NewsAPI (opt.) | **RSS/Atom/JSON Feed, OPML, WebSub** | niedrig (öffentl.) | RSS/Atom + Ollama-Summary |
| **Dizz Trading** | **CCXT** (100+ Exchanges), FRED/On-Chain/DVOL, read-only MCP (vorhanden) | CCXT-Unified | **HÖCHST** (Echtgeld) | Demo/Sim; Live gegated |
| **Dizz Communication** *(neu 12.06.)* | IMAP/SMTP+XOAUTH2, Gmail-API, JMAP-Slot; **Matrix+mautrix-Bridges** (WhatsApp/Signal/Telegram/Insta); Webview (WhatsApp Web & Co.); Jitsi (Video) | **IMAP/SMTP, OAuth2, JMAP, Matrix, WebRTC/Jitsi** | **HÖCHST** (private Kommunikation) | IMAP+Matrix self-hosted+Jitsi |
| **Dizz Leading** *(neu 12.06., exklusiv)* | E-Rechnung (XRechnung/ZUGFeRD), DATEV/CSV-Export, Zahlungs-/MoR-Slot; **konsumiert Admin/Money/Communication per MCP** (Zuweisung „geschäftlich") | **GoBD, XRechnung/ZUGFeRD, EÜR/UStVA** | **HOCH** (Geschäft/Steuer) | Eigen-Kern, sevdesk/Lexware nur Blaupause |
| **Dizz Music** *(neu 12.06.)* | ACE-Step 1.5 (LoRA eigener Stil), Stable Audio Open, MusicGen (lokal); librosa/essentia (BPM/Key/Beat), demucs (Stems); gemeinsame creator/engine-JobQueue | **MIDI**, JSON-Patterns | normal (eigene Werke vertraulich) | komplett lokal auf RTX 5070 Ti |

## 2. Geteilte Muster — das trägt der Kern generisch (NICHT je App neu bauen)
1. **Adapter-Interface-Pattern (überall gleich):** je Integrations-Klasse genau **ein** Interface
   (`BankSource`, `HealthSource`, `SocialChannel`, `CalendarSource`, `DocumentSource`, `KnowledgeImporter`,
   `Generator`, `FeedSource`, Exchange-Layer). Anbieter sind austauschbare Implementierungen → kein
   Lock-in, kein if/else-Wildwuchs. **v1 liefert je App eine `Manual`/lokale Impl; echte Konnektoren
   docken später an.**
2. **OAuth-Token-Tresor (K1/K2):** viele Apps brauchen fremde OAuth-Tokens (Social, Kalender, Banking,
   Health-Cloud). → **ein** sicherer Token-Store mit Scope-Minimierung + Refresh-Rotation im Account-Core.
3. **Human-in-the-Loop-Aktions-Tools (K4):** jede Außenwirkungs-Aktion (posten, zahlen/PISP, live traden,
   Termin anlegen) läuft über dieselbe Bestätigungs-/Stufen-Mechanik. Lesen = frei, Handeln = gegated.
4. **Sensibel-Routing (K5):** Daten tragen eine **Sensibilität** (siehe Matrix). HOCH/HÖCHST ⇒ **nur
   lokale KI**, nie Boost; Zugriff nur bei **verifizierter Verbindung** (K1). Ein Mechanismus, alle Apps.
5. **Sync-ready-Schema (K5):** UUID / user_id / created_at·updated_at / **Soft-Delete** ab Tag 1 — überall
   identisch, damit Multi-Device-Sync (Stufe 3) nachrüstbar ist.
6. **Stats-Endpoint + read-only MCP (K3/K4):** jede App liefert `/api/summary` (Dashboard-Kachel) und
   read-only MCP-Tools — Dizz Trading ist die lebende Referenz.
7. **Lokale KI-Bausteine wiederverwenden:** Ollama (Text/Kategorisierung/Summary), **Piper** (Stimme →
   Creating), **sqlite-vec + bge-m3** (RAG → Knowledge). Kein Neubau je App.

## 3. Querverbindungen zwischen den Apps (Daten-/Tool-Flüsse)
- **Money ↔ Trading:** Vermögens-Posten (read-only) aus Trading → Money.
- **Money ↔ Admin:** Steuer-Sektor — Belege/Fristen/ELSTER (Federführung klären).
- **Admin ↔ Plans:** extrahierte Fristen → Termine/Erinnerungen.
- **Plans ↔ Healthy:** Routinen/Termine (Arzt, Training).
- **News → Knowledge:** Artikel/Highlights als Markdown-Clip.
- **Knowledge → Creating:** Recherche-Material; **Knowledge ↔ Dizzi-L3-RAG** (primäre Wissensquelle).
- **Creating → Management:** fertiges Asset + Metadaten → Scheduling/Verteilung.
- **Alle → Dizzi:** Stats-Kachel + MCP-Tools + L4-Beobachtung + Ereignis-Push (Analyst/Glocke).

## 4. Architektur-Empfehlungen (Professionalität & Effizienz, gegen Spaghetti)
- **Standards vor Eigenbau:** FinTS/CAMT, FHIR, CalDAV/iCal, RSS/Atom/OPML, OAuth2, CCXT, Markdown.
- **Eigener schlanker Python/FastAPI-Kern je App** statt Fremd-Backends einbetten (Firefly/Paperless als
  *Daten-Blaupause*, nicht als Laufzeit-Fremdstack) → Stack-Konsistenz, volle Kontrolle, ein Deploy-Muster.
- **Geld = Decimal/Minor-Units**, Zeit = UTC + saubere Zeitzonen, **idempotente** Außen-Aktionen.
- **Lokal-first als Default**, Cloud/Boost nur opt-in für nicht-sensible Daten (0-€-Linie hält).
- **Mobile-Abhängigkeit** bewusst: Health (HealthKit/Health Connect) braucht die Tauri-Mobile-Schale
  (Rust noch offen) → Reihenfolge einplanen.

## 5. Wo entscheidet der Nutzer? → Fragerunde
Jedes Dossier endet mit „Offene Entscheidungsfragen". Gebündelt in der Fragerunde (siehe Chat):
Schwerpunkte = (a) Embedding vs. Eigen-Kern (Money/Admin), (b) konkrete Geräte/Dienste des Nutzers
(Banken/Wearables/Kalender/Social), (c) 0-€-lokal vs. Komfort-Cloud je App, (d) Mobile-Schale-Priorität.

## Quellen
Siehe die je-App-Dossiers (`<app>/docs/RECHERCHE.md`) — dort sind alle Web-Quellen verlinkt.
