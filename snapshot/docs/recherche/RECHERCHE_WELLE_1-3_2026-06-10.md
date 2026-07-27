# Recherche-Protokoll — Wellen 1–3 (10.06.2026)

> 15 Suchläufe über Architektur, KI-Kern, Integration, Datenhaltung, Sicherheit.
> Destillat in 02_TECHNOLOGIE_EMPFEHLUNG.md.

## Welle 1 — Architektur & Fundament

### 1.1 Personal-AI-Assistant-Landschaft (Open Source, self-hosted)
- Markt 2026 ist reif: **Khoj** (Second Brain, lokale LLMs via Ollama/llama.cpp), **OpenClaw**
  (self-hosted Agent-Runtime/Message-Router, Node.js), **QwenPaw** (Multi-Agent, Qwen-Ökosystem),
  **Jan.ai** (5,5 Mio+ Downloads), **Open WebUI** (290 Mio+ Downloads — self-hosted AI ist Mainstream).
- Kernprinzipien überall: Auditierbarkeit, Kontrolle (self-hosting), Kostenfreiheit;
  **MCP** als Tool-Standard, A2A für Agent-zu-Agent.
- **Bedeutung für uns**: Wir erfinden kein Rad neu — wir bauen die Über-Schicht (Dashboard + eigene
  Lern-KI + Panel-Ökosystem), können aber Komponenten/Patterns dieser Projekte studieren/übernehmen.

### 1.2 App-Rahmen (Desktop + Mobile + Linux)
- **Tauri 2**: ~2,5–10 MB Bundles (Electron 80–150 MB), 30–40 MB Idle-RAM (Electron 200–300),
  EIN Codebase für **Windows + macOS + Linux + iOS + Android**. Rust-Backend, System-Webview.
- Electron: desktop-only, am battle-tested. Flutter: eigenes Rendering (kein Web-Tech, anderes Skill-Set).
- **Bedeutung für uns**: Tauri 2 erfüllt exakt die Stufen 1–2 (PC + Handy-App) und die
  Linux-Portabilitäts-Anforderung mit einem Codebase. Web-Frontend-Skills aus dem Trading Bot
  bleiben verwertbar.

### 1.3 Lokale LLMs (Open Source, 0 €)
- Hardware-Stufen: 8 GB VRAM → 7–8B-Modelle; 24 GB VRAM (RTX 3090/4090/5090) → 30B-Klasse;
  64 GB RAM → 70B (≈ GPT-4o-mini-Qualität). Q4_K_M-Quantisierung halbiert VRAM nahezu verlustfrei.
- Top-Empfehlungen 2026: Qwen-3.x-Reihe, Llama-3.3/4-Reihe, Mistral, Phi-Reihe (klein).
- **Ollama** als De-facto-Standard-Runtime (einfach, API-kompatibel, Modellwechsel trivial).
- **Bedeutung für uns**: Modellwahl hängt an der konkreten Nutzer-Hardware → OFFENE FRAGE.
  Architektur muss modell-agnostisch sein (Ollama-API als Abstraktion).

### 1.4 KI-Langzeitgedächtnis
- **Mem0**: Memory-Layer zum Anstecken an beliebige Agent-Frameworks; automatische Fakten-Extraktion;
  Vector+Graph+KV kombiniert; 47k+ Stars; LOCOMO 67 %, p95-Suche 0,2 s, 90 %+ Token-Ersparnis
  vs. Full-Context. Empfohlener Default für „remember the user"-Apps.
- **Letta (MemGPT)**: kompletter Agent-Runtime, Agent editiert sein Memory selbst — richtig für
  autonome Langzeit-Agenten, schwergewichtiger.
- **Bedeutung für uns**: Mem0(-Pattern) als Startpunkt für die Lern-Ebene „Nutzer-Wissen";
  Letta-Pattern später für autonome Verwaltungs-Agenten prüfen.

### 1.5 Local-first Sync (Stufe 3: Server)
- Reifes Feld: **sqlite-sync** (CRDT-Extension, konfliktfrei, sync zu Postgres/Supabase/SQLite Cloud),
  **PowerSync** (SDKs für React Native/Flutter/Web/Kotlin), **ElectricSQL**, **cr-sqlite**, **Turso Sync**.
- Kernfrage 2026: nicht mehr „CRDT oder nicht", sondern „wo liegt die Sync-Grenze".
- **Bedeutung für uns**: Stufe 1 = reine lokale SQLite. Schema von Tag 1 sync-fähig entwerfen
  (IDs/Timestamps/Soft-Delete), damit Stufe 3 ein Aufsatz wird, kein Umbau.

## Welle 2 — Fähigkeiten & Integration

### 2.1 Sprache (offline, Deutsch)
- Standard-Stack 2026: **whisper.cpp / faster-whisper** (STT, Deutsch stark) + **Piper** (TTS,
  lokal, CPU-fähig, 35+ Sprachen inkl. Deutsch, ONNX/VITS) + lokales LLM dazwischen.
- Latenz-Referenz: RTX 3060 → 1–2 s End-to-End. Läuft sogar auf Raspberry Pi (5–8 s).
- **Bedeutung für uns**: Sprachschicht ist ein gelöstes Problem; als eigenes Modul (Audio-I/O-Service)
  einplanen, Push-to-talk vs. Wake-Word = OFFENE FRAGE.

### 2.2 MCP (Model Context Protocol)
- De-facto-Standard (97 Mio+ SDK-Downloads/Monat, alle großen Anbieter). JSON-RPC 2.0,
  Transporte: stdio (lokal) + Streamable HTTP (remote). 500+ fertige Server (Gmail, Drive,
  Kalender, DBs, Slack, …).
- **Bedeutung für uns — ARCHITEKTUR-SCHLÜSSEL**: Wenn jedes Panel/Tool seine Fähigkeiten als
  **MCP-Server** exponiert, dann (a) kann UNSERE KI alle Tools einheitlich steuern,
  (b) kann **Claude (Code) dieselben Server nutzen** → die gewünschte Claude-Interoperabilität
  fällt gratis ab, (c) externe Dienste (Gmail etc.) sind via fertige MCP-Server anbindbar.

### 2.3 Bestehende Dashboard-Lösungen (Studienobjekte, keine Basis)
- **Glance** (Go, 31k+ Stars, sehr leicht), **Homepage** (Next.js, Integrationstiefe),
  **Dashy**, **Homarr** (Drag-and-drop-Editor).
- **Bedeutung für uns**: Unser Dashboard ist interaktiver/KI-zentrierter als diese (reine Anzeige-
  Tools) → Eigenbau richtig, aber Widget-/Config-Patterns (YAML-Config, Service-Widgets) abschauen.

### 2.4 Sicherheit / Multi-User (Stufe 3 vorbereiten)
- Self-hosted Auth 2026: **Authentik / Keycloak / SuperTokens**; Pflicht-Features: OAuth2/OIDC,
  MFA (TOTP/WebAuthn, Default an), Refresh-Token-Rotation mit Reuse-Detection, Passkeys für Admins.
- **Bedeutung für uns**: Stufe 1 lokal = einfacher lokaler Schutz; aber **Datenmodell von Tag 1
  user-scoped** (user_id überall), API-Schicht mit Auth-Middleware-Slot → Multi-User wird Aufsatz.

### 2.5 Plugin-/Panel-Architektur
- Best Practice: **Monorepo** (pnpm workspaces/Turborepo), Core-Plugin-Pattern (alle Panels hängen
  an einem Kern, klare Public APIs, strikte Dependency-Hygiene), type-safe lazy Plugin-Loading.
- **Bedeutung für uns**: Panels = Plugins mit definiertem Vertrag (Manifest: Stats-Endpoint,
  Detail-View, Aktionen, MCP-Server). Platzhalter-Panels = Manifest ohne Implementierung.

## Welle 3 — Lerntechnik, Daten, Bausteine

### 3.1 „Lernende KI" — was 2026 real funktioniert
- Personalisierung lokal = **3 Hebel**: (1) RAG/Kontext-Injektion, (2) Fine-tuning, (3) Hybrid.
- Konsens: Für „passt sich an den Nutzer an" ist **Memory-Layer + personalisiertes RAG** der
  richtige, wartbare Weg (Mem0-Pattern: lernt aktiv aus Interaktionen, hält Präferenzen über
  Sessions). Fine-tuning lokal = teuer, schwer aktuell zu halten → erst viel später, wenn überhaupt.
- **Bedeutung für uns**: „Smart lernende KI" = geschichtetes Gedächtnis (Profil/Präferenzen,
  Episoden, Wissen/RAG über Projektordner) + Feedback-Schleifen — KEIN Modell-Training. Ehrlich
  dokumentieren, dass das der State of the Art für diesen Anwendungsfall ist.

### 3.2 Vektor-Datenbank (lokal)
- **Chroma** = „SQLite der Vektor-DBs", embedded, zero-config, reicht bis ~Millionen Chunks;
  **sqlite-vec** = Extension direkt in SQLite; **Qdrant** = eigener Service, stark bei Filtern, 5M+.
- **Bedeutung für uns**: Start mit **sqlite-vec oder Chroma** (alles bleibt in einer Datei-DB-Welt);
  Qdrant erst bei Server-Skalierung.

### 3.3 Agent-Orchestrierung
- 2026 dominieren **LangGraph** (Kontrolle, stateful Graphen, Produktions-Empfehlung),
  CrewAI (Zugänglichkeit), AutoGen (Forschung); Smolagents für leichte Single-Agent-Loops.
- Rat der Quellen: nach Constraints wählen, nicht nach GitHub-Stars.
- **Bedeutung für uns**: Start mit **eigenem schlanken Agent-Loop + MCP** (volle Kontrolle, kein
  Framework-Lock-in); LangGraph als Option, wenn Multi-Agent-Komplexität real wird.

### 3.4 Finanz-Baustein (Panel Finanzmanagement)
- **Firefly III** (PHP, doppelte Buchführung, komplett lokal), **Actual Budget**, **ezBookkeeping**.
- **Bedeutung für uns**: Erst Eigenbau-Light (Stats + Erfassung) im Panel; Firefly III ggf. als
  angebundenes Backend statt Neuentwicklung der Buchhaltung. Entscheidung in Phase 5.

### 3.5 Backups
- **restic**: AES-256-GCM, zero-knowledge, Dedup, lokal → später SFTP/S3; Append-only gegen
  Ransomware; Regel: Restores regelmäßig TESTEN.
- **Bedeutung für uns**: restic als Backup-Standard des Projekts (Code via git + Daten via restic).

## Quellen (Auswahl)
- Vellum: Best Open-Source Personal AI Assistants — https://www.vellum.ai/blog/best-open-source-personal-ai-assistants
- Tauri vs Electron 2026 — https://tech-insider.org/tauri-vs-electron-2026/ · https://codenote.net/en/posts/cross-platform-dev-tools-comparison-2026/
- Lokale LLMs/Hardware — https://pristren.com/blog/best-local-llm-2026/ · https://localaimaster.com/blog/ollama-system-requirements
- Memory: Mem0 vs Letta — https://vectorize.io/articles/mem0-vs-letta · https://mem0.ai/blog/state-of-ai-agent-memory-2026
- Local-first/Sync — https://github.com/sqliteai/sqlite-sync · https://www.smashingmagazine.com/2026/05/architecture-local-first-web-development/
- Voice — https://github.com/rhasspy/piper · https://www.promptquorum.com/power-local-llm/build-local-voice-assistant-2026
- MCP — https://www.anthropic.com/news/model-context-protocol · https://dev.to/x4nent/complete-guide-to-mcp-model-context-protocol-in-2026-architecture-implementation-and-4a11
- Dashboards — https://www.pistack.xyz/posts/self-hosted-homepage-dashboards-homepage-dashy-homarr-guide/ · https://sumguy.com/glance-vs-homepage-vs-dashy/
- Auth — https://supertokens.com/blog/self-hosted-auth-solutions-in-2026 · https://www.cerbos.dev/blog/best-open-source-auth-tools-and-software-for-enterprises-2026
- Plugin/Monorepo — https://feature-sliced.design/blog/frontend-monorepo-explained · https://www.freecodecamp.org/news/how-to-design-a-type-safe-lazy-and-secure-plugin-architecture-in-react/
- RAG vs Fine-tuning — https://is4.ai/blog/our-blog-1/rag-vs-fine-tuning-comparison-2026-287
- Vektor-DBs — https://zenvanriel.com/ai-engineer-blog/chroma-vs-qdrant-local-development/ · https://4xxi.com/articles/vector-database-comparison/
- Agent-Frameworks — https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
- Finanzen — https://firefly-iii.org/ · https://ezbookkeeping.mayswind.net/comparison/
- Backup — https://helgeklein.com/blog/restic-encrypted-offsite-backup-with-ransomware-protection-for-your-homeserver/
