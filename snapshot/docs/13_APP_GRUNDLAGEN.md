# App-Grundlagen — Konzept & Anforderungen je Einzel-App (Stand 11.06.2026)

> Maßgebliche Grundlage für den Bau der Sub-Apps („Dizz …"). Hält fest, was der Nutzer als
> Grundkonzept will, plus recherche-gestützte Bausteine. Eine Kopie liegt in jedem App-Ordner
> (damit auch eine isolierte Session die Tiefe kennt). Quelle: `the world of dizzi/docs/`.
> Ergänzt [12_GESAMTVERSTAENDNIS.md](12_GESAMTVERSTAENDNIS.md) und den App-Vertrag.

## A. Universelle Prinzipien (gelten für JEDE App)

### A1 — Eigener Wächter-/Lern-KI-Kern (Pflicht)
Jede App hat einen **eigenen übergeordneten KI-Kern**, der — auf die App zugeschnitten, kleiner
als Dizzi, aber gleicher Geist — **alles überwacht, beobachtet, Daten sammelt und auswertet**,
bei der Verwaltung hilft und **dazulernt**. Dieser Kern **interagiert mit Dizzi** (über den
MCP-/App-Vertrag), damit Dizzi als Gesamt-Terminal funktioniert.
Baumuster (aus Dizzi übernehmen, app-skaliert): **L4-Beobachter** (periodische Schnappschüsse) +
**Analyst** (Regel-Meldungen + LLM-Vorschläge) + **Gedächtnis** (Fakten/Episoden/RAG, je nach App).
Sicherheits-Regel überall: **beobachten + vorschlagen, nie eigenmächtiger Eingriff**; sensible
Aktionen nur bei verifizierter Verbindung.

### A2 — Geteilte Design-Baseline (vorbereitet in jeder App)
- „Mattglanz-Metall": Graphit + **Cyan/Magenta**-Akzente, scharfe Kanten, Glow erlaubt
  (Design-Quelle: `the world of dizzi/docs/06_DESIGN_SYSTEM.md`).
- **Schwebender, schleuderbarer Settings-+Account-Knopf** als wiederkehrendes Element —
  in jeder App vor-implementiert/vorbereitet (Muster: Dizzis FloatingSettings).
- **Panel-Spin-Physik** (greifen → mobile Achse → Schwingen → Schleudern → Impuls-Übertrag aufs
  schwebende Element): einheitlich nach `docs/14_SPIN_PHYSIK_SPEC.md` (nicht in diesem Auszug)
  (erst kanonisch in Dizzi perfektioniert, dann überall portiert).

### A3 — Vernetzung (App-Vertrag)
Eigenständig + vernetzt: Dizzi-ID-SSO, read-only Stats-Endpoint (Dashboard-Kachel), MCP-Server,
Deep-Link, Vernetzungs-Manifest. **Cross-Zugriff auf Anfrage** (z. B. Projekte/Archiv brauchen ein
sicher in Bürokratie liegendes Dokument; Finanzen ↔ Bürokratie in gegenseitiger Rückfrage) —
geregelt, protokolliert, hinter verifizierter Verbindung bei sensiblen Daten.

---

## B. Anforderungen je App

### Dizz Money (Finanzen) — HOHE Anforderung, SENSIBEL/Echtgeld
Gigantisches Finanz- **und Business-Management**-/Übersichtstool. **Validierte Datensammlung +
Verwaltung mit hoher Sicherheit.** Klärt **rechtliche/steuerliche** Fragen (was ist absetzbar),
Steuer-Reports. **Konten-Aggregation** über alle Quellen (Bank, Investment, Kredit, Krypto) →
einheitlicher, strukturierter Tracking-Überblick; agiert mit Bank-/Account-Anbindungen.
- Recherche-Bausteine: Open-Banking/Account-Aggregation (Konsens-Anbieter Plaid-Klasse; in
  Deutschland PSD2/FinTS prüfen), Cashflow-Forecast, Steuer-/Absetzbarkeits-Erkennung, Reports.
  Lokale Alternative bewertet: doppelte Buchführung (Firefly III) als Backend-Option.
- Sicherheit: Daten lokal, harte Dizzi-ID-Stufe (Passkey/MFA) — Echtgeld-Vorbereitung.
- Wächter-KI: Cashflow-/Budget-Anomalien, Frist-/Steuer-Hinweise, Vorschläge.

### Dizz Admin (Bürokratie) — SENSIBEL
Wie „Archiv plus", aber **nur Verträge & wichtige Dokumente**, **absolut sicher gelagert**.
Andere Projekte erhalten **für nötige Fälle geregelten Zugriff**; trotzdem **separat verwaltbar**
(fernab vom Archiv). Fristen/Anträge/Vorgänge mit Erinnerungen (Push an Dizzi-Meldungen).
- Vernetzung zentral: **Finanzen ↔ Bürokratie** gegenseitige Rückfrage; Projekte/Archiv → Doku-Zugriff.
- Wächter-KI: Frist-Wächter, Vollständigkeits-Checks, Dokument-Klassifikation.

### Dizz Knowledge (Archiv + Notizen) — zwei Säulen, teils SENSIBEL
Intelligente **KI-Verarbeitungsbasis für alle Arten von Informationen** — übergreifend gesammelt,
verarbeitet, dargestellt; **permanent von Dizzi verarbeitbar**.
- **Säule 1 — Archiv**: kategorisierte archivische Funktionen (abgeschlossene Projektpläne,
  Vorgangsbeschreibungen ablegen) **und** „wilde" Ablage (Videos, Bilder).
- **Säule 2 — Notiz-App** (Mem-ähnlich, aber besser): **übergeordneter KI-Interaktionschat für
  alles**; **verschachtelte/hierarchische Projektordner**; **Labels** für Cross-Verweise/
  Verknüpfungen. Recherche-Muster: Obsidian-Backlinks/Graph, Mem-Auto-Organisation, „cited
  answers" (RAG mit Quellenbeleg). Private Notizen = sensibel → lokal.
- Wächter-KI: Auto-Verschlagwortung, Querverweis-Vorschläge, RAG über alles.

### Dizz Management (Social Media) — Multi-Agent
**Viele Unter-Agenten**, jeder verwaltet **seinen eigenen Social-Media-Account**; der Nutzer
**interagiert mit jedem einzeln** (Input-Quellen nennen/geben). Alle Einzel-Manager speisen in
einen **großen übergeordneten Manager**, der hilft, alle zu verwalten. Jeder Manager verwaltet
**komplette Kanal-Suiten** (mehrere Channels: LinkedIn, Instagram, …) gleichzeitig.
- Recherche-Muster: **Orchestrierungs-Schicht** über spezialisierten Per-Channel-Agenten;
  Inhalts-Recycling über Plattformen (ein Produktionszyklus → mehrere Formate); Bereiche
  Erstellung/Planung/Engagement/Analytics; OAuth-Konnektoren (vorbereitet, deaktiviert).
- Vernetzung: erhält Inhalte von **Dizz Creating**; gibt diesem Richtung vor.
- Wächter-KI: der übergeordnete Manager = Beobachter/Analyst über alle Kanal-Agenten.

### Dizz Creating (Creator) — HOHE Anforderung, Eigenbau mit Open-Source-AI (0 €)
Selbst gebautes System auf **Open-Source-KI** (kostenlos), das **Bilder UND Videos erstellt UND
bearbeitet**: Footage **schneiden** bis zum **fertigen YouTube-Videoprodukt**, Bilder bearbeiten,
und **von Grund auf erstellen**. Eine **starke** Bild-/Video-KI.
- Recherche-Bausteine: **ComfyUI** (node-basiert, Bild- + Video-Pipelines, Batch-Automation,
  RTX-50-Serie optimiert — ideal für die RTX 5070 Ti) als Backbone; **LTX** lokaler Open-Source-
  Video-Editor/Engine; ControlNet/Upscaling-Ketten; alles lokal/0 €.
- Vernetzung: an die Social-Media-Accounts + **einzelnen Social-AIs** gekoppelt → Creator bekommt
  **klare Richtung** für seine Arbeiten über den Bezug zu den Accounts.
- Wächter-KI: Job-/Asset-Überwachung, Stil-/Qualitäts-Lernen aus Account-Feedback.

### Dizz Healthy (Health) — HOCHSENSIBEL, strikt lokal
Gesundheits-Watching: **Vitalwerte** (Blutdruck, Puls, Glukose, Gewicht/Körperzusammensetzung,
SpO2, Schlaf …), **Gewohnheiten + Verhaltensmuster-Analyse**, **Korrelationen Gewohnheit ↔ Vitalwert**,
Termine/Erinnerungen.
- Recherche-Bausteine: Vitals als Zeitpunkt-/Intervall-Datensätze; zentrales Dashboard, das
  Quellen bündelt; später **Wearable-Anbindung** (OAuth/Normalisierung); Self-hosted-Vorbild
  HealthLog (**AES-256**, Docker). Strikt lokal, minimale Berechtigungen.
- Wächter-KI: Trend-/Anomalie-Beobachtung, sanfte Hinweise (nie Diagnose).

### Dizz News (News) — auf Basis des /news-Skills
Kompakter, **nach Sektoren** gegliederter Nachrichten-Überblick aus **seriösen Fixquellen**
(Vorbild: ein kuratierter News-Skill); stichpunktartige Reports, kuratiert, kein Rauschen.
- Vernetzung: liefert **Kontext** an andere Apps (Trading Bot, Finanzen).
- Wächter-KI: Relevanz-Filter, Sektor-Trends, Push wichtiger Ereignisse an Dizzi-Meldungen.

---

## C. Hinweise für den Bau
- Reihenfolge & Modell-Split: siehe `docs/11_GESAMTPLAN.md` (Kern zuerst mit Architektur-KI, dann Apps).
- Jede App erfüllt den App-Vertrag (`<app>/docs/01_APP_VERTRAG.md`) inkl. Wächter-KI-Kern (A1)
  und Design-Baseline (A2).
- Tiefe je App wird vor dem jeweiligen Bau in einer kurzen App-Fragerunde finalisiert
  (offene Punkte stehen in `<app>/docs/02_ANFORDERUNGEN.md`).
