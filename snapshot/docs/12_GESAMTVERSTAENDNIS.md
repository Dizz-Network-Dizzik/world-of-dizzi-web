# the world of dizzi — Gesamtverständnis (Master-Dokument)

> **Zweck:** Dieses Dokument erklärt das **Gesamtvorhaben** so vollständig, dass eine Person
> oder ein KI-Assistent **ohne Vorwissen** versteht, was hier
> gebaut wird, wie alles zusammenhängt und wie man an **einem einzelnen Teilprojekt** arbeiten kann.
> Eine Kopie liegt in JEDEM App-Ordner. Quelle der Wahrheit ist diese Datei in `the world of dizzi/docs/`.
> Stand 11.06.2026.

---

## 1. Was wird hier gebaut?
Ein **Netzwerk eigenständiger Apps** für die Verwaltung des gesamten Lebens des Nutzers (dizzi) —
Alltag, Projekte, Finanzen, Bürokratie, Gesundheit, Social Media, Trading u. v. m.

Zwei Wahrheiten gelten gleichzeitig:
1. **Jede App ist eigenständig** — eigener Ordner, eigene Doku, eigenes Konto + Einstellungen,
   einzeln lauffähig und sogar **einzeln verkaufbar**.
2. **Alle Apps bilden ein nahtloses Gesamtsystem** — verbunden über eine gemeinsame Identität
   (Single-Sign-On), einen gemeinsamen „App-Vertrag" und ein KI-Interaktions-Protokoll.

Über allem steht **Dizzi** (die App „the world of dizzi") als **Dach + Kommandozentrale**: ein
Panel-Dashboard mit einer lernenden, lokalen KI namens **Dizzi**, die mit allen Apps redet, ihre
Daten überblickt, beobachtet, berät und (auf Wunsch) steuert.

Anspruch (Grundprämisse): **professionell, funktional, effizient — vom Code bis zur Oberfläche.**
Runde Einzelsysteme, ein rundes Gesamtsystem. Verkaufs-/Service-tauglich.

## 2. Die Architektur in einem Bild
```
        ┌─────────────────────── DIZZI (Dach + Kommandozentrale) ───────────────────────┐
        │  Panel-Dashboard · lokale KI „Dizzi" (Ollama+Boost) · Gedächtnis L1–L4         │
        │  ┌───────────────┐  ┌────────────────┐  ┌──────────────────────────────────┐  │
        │  │  DIZZI-ID     │  │  MCP-TOOL-BUS  │  │  ACCOUNT/SETTINGS-CORE (Muster)  │  │
        │  │  (OIDC, SSO,  │  │  KI ↔ App-KIs  │  │  je App eingebettet (Föderation) │  │
        │  │  Google-Broker)│  └────────────────┘  └──────────────────────────────────┘  │
        │  └───────┬───────┘                                                              │
        └──────────┼──────────────────────────────────────────────────────────────────┘
                   │  Single-Sign-On (ein Login → überall) · App-Vertrag · MCP
   ┌───────────────┼───────────────┬───────────────┬───────────────┬─────────────────┐
┌──┴──┐        ┌───┴───┐       ┌────┴────┐     ┌────┴────┐     ┌────┴────┐       ┌────┴────┐
│Trading│      │Finanzen│      │Bürokratie│    │Projekte │     │ Health  │  …    │ (weitere)│
│ Bot   │      │        │      │          │    │         │     │         │       │          │
└───────┘      └────────┘      └──────────┘    └─────────┘     └─────────┘       └──────────┘
 (jede App: eigenständig + eigener Ordner + eigenes Konto/Settings + MCP-Server + Deep-Link)
```

## 3. Die drei verbindenden Säulen (die „geteilte Kern-Architektur")
1. **Dizzi-ID (Identität & Single-Sign-On).** Ein schlanker OIDC-Identitäts-Dienst im Dizzi-Kern.
   Anmeldung per **Google** (Loopback-IP + PKCE, Googles empfohlener Desktop-Weg); für hochsensible
   Bereiche (Echtgeld) zusätzlich **Passkey/MFA (FIDO2)**. **Einmal auf Dizzi anmelden → automatisch
   in allen verbundenen Apps eingeloggt.** Jede App akzeptiert den Dizzi-ID-Ausweis (Relying Party);
   standalone hat jede App ihren eigenen Login als Rückfall.
2. **App-Vertrag (das Andock-Skelett).** Jede App erfüllt denselben Vertrag (Details in jeder App
   unter `docs/01_APP_VERTRAG.md`): eigener Ordner+Doku, read-only **Stats-Endpoint** (Dizzi-
   Dashboard-Kachel), **MCP-Server** (KI-Interaktion), **Dizzi-ID-Anbindung**, **Account/Settings-
   Modul**, **Deep-Link**, **Vernetzungs-Manifest**.
3. **KI-Interaktions-Protokoll (MCP).** Dizzi ist MCP-Host; jede App exponiert read-only Tools
   (später Aktions-Tools mit **Human-in-the-Loop**). Dizzi beobachtet über die Zeit (Gedächtnis L4),
   meldet Trends und macht Vorschläge — **beobachten + vorschlagen, nie eigenmächtiger Eingriff**.
   Sensible Aktionen nur hinter verifizierter Verbindung.

**Wichtig:** Jede App hat zusätzlich ihren **eigenen Wächter-/Lern-KI-Kern** (app-skaliert,
gleicher Geist wie Dizzi: beobachten/sammeln/auswerten/dazulernen), der nach oben mit Dizzi
interagiert. Details + Anforderungen je App: [13_APP_GRUNDLAGEN.md](13_APP_GRUNDLAGEN.md)
(liegt als Kopie in jedem App-Ordner).

## 4. Sicherheits-Grundsätze
- Lokal-first: läuft auf dem PC des Nutzers; Laufzeitdaten unter `C:\Dizzik\data\`
  (außerhalb von OneDrive — wichtig wegen Datei-Sperren); Secrets in `.env` außerhalb des Repos.
- **Sensible Domänen** (Finanzen, Bürokratie, Gesundheit, private Notizen, Echtgeld) bleiben
  **standardmäßig lokal** (kein Cloud-/Boost-Modell); Zugriff nur bei **verifizierter Verbindung**.
- **0 € Betriebskosten** strikt: lokale KI (Ollama) als Boden + kostenlose Boost-APIs
  (NVIDIA NIM/Groq/Cerebras) als Eskalation; nie auf einen Anbieter angewiesen.
- KI-Aktionen mit Außenwirkung erfordern Bestätigung (Human-in-the-Loop-Stufen pro Tool).

## 5. Technischer Stack (für alle Apps gleich gedacht)
- **Core/Backend**: Python 3.12 + FastAPI (headless Service je App; Muster: Dizzi-Core auf :8200,
  Trading Bot auf :8137).
- **Frontend/Schale**: TypeScript + React + Vite; Design „Mattglanz-Metall" (Graphit, Cyan #2fe7ff +
  Magenta #ff3df0, scharfe Kanten, Glow erlaubt); später Tauri-2-Desktop/Mobile.
- **Daten**: SQLite (+ sqlite-vec für Embeddings); Schema **user-scoped + sync-ready** ab Tag 1
  (UUID, user_id, created_at/updated_at, deleted_at/Soft-Delete).
- **KI**: Ollama lokal (qwen3:14b Arbeitstier, qwen3:4b Blitz) + Boost-Kette; Memory L1 Fakten,
  L2 Episoden+Nacht-Konsolidierung, L3 RAG (bge-m3), L4 Beobachtungen; MCP-Tools; Sprache
  faster-whisper (STT) + Piper (TTS).
- **Werkzeuge ohne Admin**: venv + portables Node unter `C:\Dizzik\data\tools\`.

## 6. Die Gesetze (verbindlich in JEDEM Ordner: `GESETZE.md`)
Kurz: (1) Sicherungsrunden, (2) ehrliche Bewertungen, (3) regelmäßige Recherche,
(4) Perfektions-Code, (5) Vorbereitungen dokumentieren, (6) bessere Optionen sofort melden,
(7) Über-Nacht-Pakete mit Plan-Bestätigung, (8) „weiter" ohne offene Pakete = Systemcheck,
(9) **nach jeder Bearbeitung gesamte Doku synchronisieren**, (10) **Bau-KI ist Standard, bei
eindeutigen Architektur-KI-Schritten sofort den Wechsel empfehlen**. Volltext: `GESETZE.md`.

## 7. Modell-Strategie (wichtig fürs Arbeiten)
- **Bau-KI 4.8 = Standard.** Für UI, Muster-Ausfüllen, Feature-Fill, Doku, kleine Fixes.
- **Architektur-KI 5 = nur Kern-Architektur** (subtile, schwer-nachrüstbare Fundamente) und **nur bis 21.06.2026**
  verfügbar → in diesem Fenster werden die geteilten Kernpakete (Dizzi-ID, App-Vertrag, KI-Protokoll,
  Datenmodelle) gebaut. Plan: `the world of dizzi/docs/11_GESAMTPLAN.md`.

## 8. Stand der Projekte (12.06.2026, spätnachts)
- **Dizzi** (`the world of dizzi`): Phasen 0–4 + **Architektur-KI-Kern R1 (K1–K6) komplett** + **Dizz Defense
  (F-DEF1/2)** + **WebAuthn/Passkey live** + **„Hey Dizzi"-Weckwort live** (Auto-Start) +
  **Mini-Dizzi** (KI-Stimme/Brücke je App). Dashboard, KI L1–L4, RAG, Sprache, Dizzi-ID (OIDC/MFA/
  WebAuthn), Defense-Hub. Läuft :8200. 184 Tests.
- **Trading Bot** (`Trading Bot eins`): Demo-Flotte 51/51, KI-Ebenen, Portfolio-Schicht; als
  **Dizz Trading** an App-Vertrag angeglichen (Dizzi-ID-RP/SSO, Echtgeld-Gate hochsicher). :8137,
  340 Tests. Nativer **Dizz-Network-Monitor** (`ops/monitor/monitor_app.cs`, netzweit, mit Dizzi-Sprachzeile).
- **GEBAUTE Apps** (eigene Repos, Vertrag 1.5, je Dizz Defense + Mini-Dizzi): **Dizz News** :8216
  (KI-Briefing/Sektor-Reports) · **Dizz Communication** :8218 (Gmail live) · **Dizz Money** :8210
  (eigener Double-Entry-Ledger, Property-getestet). Der **Music-4-Ebenen-Kern** (:8220) ist gebaut,
  wird aber per **PLAN-REVISION 13.06. (docs/11 §5b REV-1) zum MUSIK-MODUS von Dizz Creating**
  eingeschmolzen (keine eigenständige Music-App mehr). Alle generisch in Dizzi angedockt.
- **Geplante Apps** (scaffolded, Bau-KI-Fill): **Dizz Plans** · **Dizz Memory** (REV-5, vorm. Knowledge:
  Mem-ähnliches Wissens-/Notiz-Tool) · **Dizz Healthy** · **Dizz Creating** (REV-1: Medien-SUITE
  Video/Bild **+ Musik**-Modus, Sound-Symbiose, DAM — Engine+Musik-Kern
  gebaut; **Architektur-KI-Schwergewicht**) · **Dizz Management** · **Dizz Admin** · **Dizz Leading**
  (Aggregator, zuletzt) ·
  **Dizz Communication** (Kommunikation, NEU 12.06.: E-Mail + Messenger + Social-DMs + Video-Calls,
  Port 8218, Zwei-Schienen-Architektur s. `kommunikation/docs/RECHERCHE.md`) ·
  **Dizz Leading** (Geschäftsführung, NEU 12.06., **exklusiv beim Nutzer**: das Netzwerk als
  GESCHÄFT verwalten — GoBD/EÜR, Lizenzen/Kunden, KPIs; Aggregator über Admin/Money/Communication;
  Port 8219, Bau spät; s. `leading/docs/RECHERCHE.md`).
  Jede mit eigenem Ordner (`finanzen`, `projekte`, … in „C:\Dizzik\code") + dieser Doku-Struktur.
  Detail-Ports/-Marken: Money 8210 · Admin 8211 · Plans 8212 · Management(social) 8213 ·
  **Creating 8214** (= Medien-Suite Bild/Video **+ Musik**; 8220 wird frei, Musik läuft im
  Creating-Prozess) · **Memory**(archiv) 8215 (vorm. Knowledge) · Healthy(health) 8217.

## 9. Wie arbeite ich an EINER App? (auch ohne Vorwissen)
1. Lies in der App: `GESAMTVERSTAENDNIS.md` (diese Datei), `GESETZE.md`, `WIEDEREINSTIEG_PROMPT.md`.
2. Lies `docs/00_VISION.md` (was die App tut), `docs/01_APP_VERTRAG.md` (wie sie andockt),
   `docs/02_ANFORDERUNGEN.md` (Kern-Umfang).
3. Halte dich an die Gesetze (v. a. 9 = Doku-Sync, 10 = Modell-Wahl).
4. Erfülle den App-Vertrag: Stats-Endpoint, MCP-Server, Dizzi-ID-Anbindung, Account/Settings-Modul,
   Deep-Link — kompatibel zum Dizzi-Kern (siehe Trading Bot als Referenz für Stats+MCP).
5. Daten user-scoped + sync-ready; sensible Daten lokal; 0-€-KI-Strategie.
6. Nach jedem Arbeitspaket: Tests, Commit, Doku-Sync.

## 10. Wo finde ich was?
- Gesamtvision/Anforderungen Dizzi: `the world of dizzi/docs/00_VISION_UND_ANFORDERUNGEN.md`
- Gesetze (Volltext): `the world of dizzi/docs/01_GRUNDGESETZE.md`
- Tech-Empfehlung / Systemübersicht: `docs/02_…` / `docs/03_…`
- Riesenpaket-Briefing + Gesamtplan: `docs/_archiv/10_…` / `docs/11_…`
- Dieses Master-Dokument: `docs/12_GESAMTVERSTAENDNIS.md` (Kopie in jedem App-Ordner)
