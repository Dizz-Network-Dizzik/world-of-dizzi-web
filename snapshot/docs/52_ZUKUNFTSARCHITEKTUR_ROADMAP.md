# 52 · ZUKUNFTSARCHITEKTUR & ROADMAP — „Gott-Netzwerk" (Modell-Flexibilität · Deployment-Modi · Bidirektionale Vernetzung · Agenten-Regie · App-Builder)

> **Status: GROSSE VORAUSPLANUNG — REINE PLANUNG/RECHERCHE/DOKU, NICHTS hier ist gebaut.**
> Erstellt 27.06.2026 (World-Admin-Planungs-Chat, Worktree `chat/zukunft`, basiert auf `chat/loop`).
> **Eingang:** der Zukunfts-Brief docs/51. **Abgrenzung:** dieses Dokument
> KOLLIDIERT NICHT mit der A–E-Umsetzung (docs/50; Phasen 1–6 **28.06. in master gemergt**,
> Go-Live #2 vollzogen) — es ist die *nächste, größere* Vorausplanung, die auf deren Härtungs-Schritten **aufbaut**.
> **Gesetz 2 (Ehrlichkeit):** die „Ist"-Blöcke sagen, was HEUTE im Code existiert (verifiziert, mit Datei-
> Referenzen); „gebaut" vs. „Slot vorhanden" vs. „nicht gebaut" sind sauber getrennt. **Gesetz 9:** README-
> Index ergänzt; widersprechende Altpläne markiert. **Quellen:** §13 (2026-Recherche, datiert).

---

## §0 · RAHMEN, METHODE, ABGRENZUNG

### 0.1 Zielbild (Nutzer-Kriterien, docs/51 §0)
„the world of dizzi" soll werden: **perfekt zukunftsorientiert · benutzerfreundlich · systematisch · professionell
codiert · effizient · leistungsstark · lokal-möglich · hochsicher · maximal vernetzt (rein UND raus) · organisch
einpflegbar · flexibel-upgradebar nach Stand der Technik** — ein Ultra-/„Gott"-Netzwerk, geschäftsfähig als Fernziel.

### 0.2 Methode (Mehr-Perspektiven, Kern-Dauerschleife-Geist, docs/32)
Je Thema §1–§5: **Ist verifiziert am realen Code** → **mehrfache 2026-Web-Recherche** (Quellen §13) → **Architektur-
Entscheidung mit Alternativen/Trade-offs** → **Risiken** → **per-App-Bedeutung** (§7) → **Phasen mit Gates** (§8).
Vier Perspektiven liegen über jeder Entscheidung: **Nutzer-Erlebnis · Sicherheit/Datenschutz · Code-Qualität/Wartung
· Geschäftsfähigkeit.**

### 0.3 ★ Die EINE verbindende Erkenntnis (Leitsatz dieses Dokuments)
Die fünf Themen sehen verschieden aus, stehen aber auf **einem gemeinsamen Fundament**: einer sauberen
**Mehrmandanten-/Isolations-Härtung**. Server-Kommerz (§2), fremde Agenten-Regime (§4) und fremde Apps (§5)
brauchen **alle dasselbe**: harte Daten-Isolation je Mandant/Quelle, App-zu-App-Auth, Render-Sanitization,
CSP-secure-by-default, echte Multi-User-Identität. Genau diese Bausteine sind in docs/50 als **gegatete Schritte
schon entworfen** (P6.2 Relay-Token · P6.3 Render-Sanitization · P6.4 CSP-Flip · K1 Dizzi-ID-Multi-User). ⇒
**Kritischer Pfad: erst die docs/50-Härtungs-Gates schließen, dann nach außen bauen.** Das verzahnt neue Roadmap ↔
laufendes A–E ohne Doppelarbeit und ohne Kollision.

### 0.4 Phasen-Namensraum
Neue Phasen heißen **`Z…`** (Zukunft), klar getrennt von docs/50 `P…`. Reihenfolge/Gates: §8. Jede Z-Phase nennt,
welche docs/50-Schritte sie voraussetzt.

---

## §1 · THEMEN-MATRIX (Überblick + Kern-Entscheidung je Thema)

| # | Thema (docs/51) | Ist-Kürzel (verifiziert) | Kern-Entscheidung | Voraussetzung | Gate für Nutzer |
|---|---|---|---|---|---|
| §1 | Modell-Flexibilität / Runtime | Modell-Swap config-getrieben ✅; Runtime **Ollama hartverdrahtet** ❌ | `appkit/runtime.py` = `LocalRuntime`-Interface; Ollama = 1. Adapter; **Modell-Profil-System** je Task-Klasse | — | **Modell-Standard** (lokal-Default) |
| §2 | Deployment lokal/hybrid/server + Mobile | lokal-first Single-User; Identitäts-/User-Nähte ✅; Server/Multi-Tenant/Hybrid ❌ | Betriebsart = first-class; **Silo (DB-pro-Mandant)**; Tauri-2-Desktop-Shell; schlanke Mobile; Hybrid zuletzt | docs/50 K1 · P6.2/3/4 | **Deployment-Priorität** + **Datenschutz-Modell** |
| §3 | MCP bidirektional + Outbound | INBOUND-Gateway ✅; OUTBOUND nur eigene Boost-Keys ◐; „Nutzer-KI als Tool" ❌ | **3 Outbound-Modi** unter EINER „externe-KI"-Abstraktion: **MCP-Sampling** · API-Provider · MCP-Client | P4.2-Aktivierung | **Welche externen KIs / Daten-Governance** |
| §4 | Management → Agenten-Workflow-Regie | Management=Social ◐; Agent-Loop+Tools+HITL+Connectors ✅; Regime/Workflow ❌ | Management = **Agenten-Regie pro Bereich** (docs/49) auf Core-Agent-Runtime; Orchestrator-Worker + HITL | docs/49 · §3 | **Pilot-Bereich + Autonomie-Grad** |
| §5 | UI-Builder → App-Builder + Marktplatz | UI-Builder Standalone ◐; App-Vertrag/appkit/CSP/MCP ✅; Builder/Markt ❌ | App-Vertrag → **SDK**; Fremd-App-Sandbox = **dieselbe** Mandanten-Isolation; Review+Markt | §2 + §5-Härtung | **Geschäfts-/Beteiligungs-Modell** |

Legende: ✅ gebaut · ◐ teilweise/Slot · ❌ nicht gebaut.

---

## §2 · THEMA §1 — MODELL-FLEXIBILITÄT / KI-RUNTIME-ABSTRAKTION

### Ist (verifiziert, 27.06.)
- **Provider-Kette gebaut** — `apps/core/app/ai/providers.py`: `PROVIDERS` =
  Boost (NVIDIA NIM/Groq/Cerebras, OpenAI-kompatibel `/v1`, opt-in per Key) + `lokal` (Ollama) als **immer-erreichbarer
  Boden**; `chain(sensitive)` (sensibel ⇒ NUR lokal) + Circuit-Breaker (P3.3b, lokal nie ausgesperrt).
- **Modell-Wahl ist HEUTE config-getrieben:** `local_model()` liest Setting `ai_model` (Default `qwen3:14b`),
  Schnell-Tasks `qwen3:4b`; Boost-Modell je Provider per Setting `boost_model_<id>`. **Embedding swappbar** über
  `apps/memory/archivapp/rag.py` `EMBED_MODELLE` (Registry Name→Dim; bge-m3 Default;
  qwen3-embedding/arctic/mxbai dim-gleich ⇒ Tausch ohne Migration).
- **Constrained decoding gebaut** — `packages/appkit/ollama.py` `strukturiert()`:
  `format=schema.model_json_schema()` über Ollamas **nativen** `/api/chat`-`format`-Slot (nimmt auch `$ref`/Wurzel-Array,
  anders als die strikte `/v1`-`response_format`-Variante); `providers.quick_chat(format=)` analog.
- **LÜCKE (ehrlich):** Die **Runtime Ollama selbst** ist NICHT abstrahiert. Stellen sind hart auf Ollama verdrahtet:
  `providers` (Ollama-`/v1` + `/api/tags`), `ollama.py` (`/api/chat`-`format`), `agent.py` (`/api/chat` natives
  Tool-Calling). Ein Tausch gegen vLLM/llama.cpp-server/LM-Studio/TGI bräuchte EINE Abstraktion.
  > **★ Korrektur (03.07., FP-3/docs/62 §0, Gesetz 2):** es sind **VIER** Stellen, nicht drei — core
  > `app/ai/rag.py` (`/api/embed`, async) kam als vierte hinzu. Vollständige Karte + Migrations-Nähte:
  > `docs/62_RUNTIME_VERTRAG.md` §0 (✅ gemergt 03.07., `1ba4c80` — Vertrag + Stubs liegen auf master).

### Recherche-Befund (2026, Quellen §13-A)
- **Runtimes:** *Ollama* = Single-User/Desktop, „in 5 Min lauffähig", aber skaliert nicht über Einzel-Nutzer
  (~41 tok/s nebenläufig). *vLLM* = Produktions-Default, **16–20× nebenläufiger Durchsatz** (PagedAttention +
  continuous batching), **prä-allokiert ~90 % VRAM**. *SGLang* = +29 % bei geteiltem Kontext (RadixAttention) —
  ideal für Agenten/RAG. *llama.cpp* = volle Kontrolle, GGUF/GBNF, embedded. *LM Studio* = GUI-first.
  *TGI* = **seit 11.12.2025 Maintenance-Mode** ⇒ für Neues NICHT mehr wählen.
- **Constrained decoding standardisiert auf JSON-Schema.** **XGrammar** ist seit ~März 2026 Default-Backend in
  **vLLM/SGLang/TensorRT-LLM** (<40 µs/Token). **llguidance** (Microsoft, Rust-Earley) noch robuster (0,12 % invalid
  vs. XGrammar 2,21 %). **llama.cpp = GBNF** (BNF + Zeichenklassen/Wiederholung), ideal lokal. vLLM-Parameter:
  `guided_json`/`guided_grammar`/`guided_regex`. ⇒ **Jede ernstzunehmende Runtime kann constrained decoding** — die
  Abstraktion muss nur je Adapter auf den nativen Mechanismus mappen.
- **Modelle 2026:** Qwen3 stark unter 8B; **Qwen3.5** (122B-MoE, 10B aktiv) läuft auf 64-GB-Rechner, schlägt
  GPT-5-mini. ⇒ „bestes lokales Modell reinsetzen" bleibt config-getrieben sinnvoll.

### Architektur-Entscheidung
**E1.1 — `packages/appkit/runtime.py` = `LocalRuntime`-Interface** mit 5 Methoden:
`strukturiert(system,nutzer,schema,…)·chat_stream(messages,tools?)·embed(texts)·modelle()·health()`. **Ollama wird der
erste Adapter** (`OllamaRuntime`, kapselt die heute verstreuten Calls aus `providers`/`ollama.py`/`agent.py` — rein
additiv, kein Verhaltenswechsel). vLLM/llama.cpp-server/LM-Studio = spätere Adapter (Stecker, wie connectors für externe
Quellen). **Constrained decoding bleibt Vertrags-Bestandteil**: jeder Adapter mappt auf seinen nativen Weg
(Ollama `format` / vLLM `guided_json` / llama.cpp GBNF), fail-safe → `None` wie heute.

**E1.2 — Modell-Profil-System** je **Task-Klasse** (`chat · schnell/strukturiert · embed · rerank · vision · voice`)
mit **Capability-Flags** (Kontextlänge, Tool-Calling, Sprachen, constrained-decoding-Fähigkeit) statt fixer Namen.
Settings-getrieben; Default-Profil = heutiges Verhalten (qwen3:14b/4b/bge-m3). Auf dem Server kann ein Mandant ein
anderes Profil (z. B. vLLM + größeres Modell) wählen.

**E1.3 — „Immer das Beste"-Modell-Liefer-/Auto-Update-Kanal (★ Nutzer-Entscheid G-MODELL, 27.06.):** das System soll
**stets das beste verfügbare Modell** fahren — lokal UND serverseitig — und **upgradebar** sein. Konkret:
- **Lokaler Client:** ein **Modell-Update-Kanal** (Teil des Profil-Systems) zieht das jeweils beste **lokal lauffähige**
  Modell automatisch nach — als Download/Update beim Installieren/Aktualisieren des Clients (hardware-bewusst: das beste
  Modell, das auf die Maschine des Nutzers passt). **Release-gegatet** („durch Nachrichten freigegeben"): ein neues
  Standard-Modell wird erst als kuratiertes Release ausgerollt, nicht blind.
- **Server (kommerziell):** serverseitig läuft das **beste Modell, das wir bereitstellen können** (größere Profile, vgl.
  Z1.3/vLLM), zentral gepflegt; neue Modelle werden serverseitig aufgespielt und je Mandanten-Profil verfügbar.
- **Mechanik:** Default-Profil ist **keine fixe Modell-Konstante mehr**, sondern ein **Kanal-Verweis** („bestes lokales
  Profil Stufe N"), den ein Release hebt — heutiges qwen3:14b/4b/bge-m3 = Stufe 0, unverändert bis zum ersten Release.
  Embed-Modell-Wechsel respektiert die `VEC_SCHEMA`-Re-Index-Disziplin (rag.py).

### Alternativen & Trade-offs
| Option | Pro | Contra | Urteil |
|---|---|---|---|
| Ollama-only bleiben | einfachste Wartung | blockt Server/Skalierung + Best-Modell-Upgrade | ✗ |
| Überall vLLM | Top-Durchsatz | VRAM-Hunger, schwer für Single-User-Desktop | ✗ (nur Server) |
| **Abstraktion (Ollama lokal · vLLM Server)** | beides; Best-of-Breed wählbar | eine Indirektion mehr | ✓ **gewählt** |

### Risiken
- Subtile Semantik-Unterschiede constrained decoding ($ref/verschachtelt) je Runtime → **Capability-Flag** + bestehende
  fail-safe-Degradierung (→ ehrlicher Fallback). Risiko: niedrig.
- Abstraktions-Leck (Adapter unterscheiden sich in Tool-Call-Streaming) → Vertrag eng halten, Adapter-Tests. Mittel.

### Phasen
- **Z1.1** `runtime.py` + `OllamaRuntime` (additiv, 0-Verhaltenswechsel; `providers`/`agent`/`ollama` rufen den Adapter).
- **Z1.2** Modell-Profil-System (Task-Klasse → Modell + Capabilities).
- **Z1.3** vLLM-/llama.cpp-server-Adapter (**gegatet, nur Server-/Power-Modus**; Embed-Vektorraum-Kompatibilität prüfen,
  vgl. `VEC_SCHEMA`-Re-Index-Disziplin in rag.py).
- **Z1.4** **Modell-Liefer-/Auto-Update-Kanal** (E1.3): Profil-Default als release-gegateter Kanal-Verweis; lokaler
  hardware-bewusster Auto-Download des besten lauffähigen Modells; serverseitig zentral gepflegtes Top-Profil.

**Gate G-MODELL — ✅ beantwortet (27.06.):** „immer das Beste, upgradebar" → **E1.3 Modell-Liefer-Kanal** (lokal
auto-aktualisiert/release-gegatet, server top-gepflegt). qwen3:14b/4b/bge-m3 bleibt Stufe-0-Default bis zum 1. Release.

---

## §3 · THEMA §2 — DEPLOYMENT-MODI: LOKAL · HYBRID · SERVER + FRONTENDS

> **★ Kommerzielle Produkt-/Paketierungs-Schicht über diesen technischen Modi: docs/56** — drei Editionen (Lokal-pur = Kauf · Hybrid · Vollserver = Abo) + **modulare Auslieferung** („Core immer dabei" + per-App/Gesamtnetz) + Modell-Lizenz-Ankauf je Edition. Nutzer-Directive 29.06.2026: **maximale Flexibilität über alle drei Stufen**. *(docs/56 un-parkt nichts — G-DEPLOY-2 bleibt offen; E-LOKAL-Desktop in Welle 1, Hybrid/Server in Welle 3.)*

### Ist (verifiziert)
- **Lokal-first, Single-User** (localhost = Vertrauensgrenze; `DEFAULT_USER_ID="dizzi"`; Stufe `lokal`).
- **Identitäts-Naht GEBAUT** — `packages/appkit/auth.py`: pluggbarer Provider
  (`set_identity_provider`), Stufen `lokal<verifiziert<hochsicher` **fail-closed**, `require_level`/`require_fresh_stepup`.
  **Dizzi-ID (K1) existiert** — `docs/17` (nicht in diesem Auszug): OIDC-Provider im Core (PKCE/Ed25519/Refresh-Rotation,
  Google-Broker + lokales Passwort + TOTP/WebAuthn), RP-Anschluss `install_dizzi_id(...)`.
- **Multi-User-Nähte angelegt:** `user_id` durchgängig, `db.alle_user_ids()` (docs/50 P6.1), per-Nutzer-Loops.
  **Per-Daten-Wurzel-Architektur:** jede App hat ihr eigenes `data\apps\<id>` (eigene SQLite-Datei je App/Daten-Wurzel).
- **NICHT gebaut:** Multi-Tenant-Server, Hybrid-Failover, Mobile-App, Datenschutz-Mandanten-Trennung (reine Zukunft).

### Recherche-Befund (2026, Quellen §13-B)
- **Isolations-Muster:** *Silo* (DB-pro-Mandant) = höchste Isolation, **Standard für GDPR/Datenresidenz**, aber Ops-Last
  wächst linear; *Pool* (geteiltes Schema + Row-Level-Security) = günstig/skalierend; *Bridge* (Schema-pro-Mandant) =
  Mitte. **Dynamische Mehrmandanten-Promotion:** klein als Pool starten, „schwere" Mandanten in Silo heben.
- **5 Deployment-Stufen** T1 Public-SaaS → T5 Air-Gapped; **self-hosted/on-prem = „compliant by design"** (Daten
  verlassen den Perimeter nie).
- **Local-first-Sync:** *ElectricSQL „Electric Next"* = Durable-Sync-Layer für Postgres (Server→Client-Streaming);
  *Automerge 3.0* (10× weniger Speicher), *Yjs* (Text), *PowerSync/RxDB*. Muster: **Gerät = Sofortigkeit/Privatsphäre/
  Resilienz, Cloud = Persistenz/Teilen/Skalierung.**
- **Shells:** **Tauri 2** (stabil seit 10/2024, 6 Plattformen **inkl. iOS/Android**, 0,6–10 MB Bundle, 30–40 MB idle,
  Rust-Backend, **scoped native commands** = kleine Angriffsfläche; empfohlen für Tools/interne Utilities; Mobile
  funktional, aber weniger reif). *Electron* = reif/Chromium, **desktop-only**. *Flutter/React-Native* = tiefste
  Mobile-Integration. Das Netz ist **web-first** (FastAPI + statische HTML/JS-Frontends) ⇒ Tauri umhüllt das Bestehende
  **ohne Rewrite**.
- **Regulatorik:** **EU-AI-Act ab 02.08.2026 voll anwendbar** (Daten-Governance Art. 10, Transparenz, menschliche
  Aufsicht, automatisches Record-Keeping; Bußgeld bis 35 Mio €/7 %). **GDPR + AI-Act gelten parallel.** Nötig: DPA mit
  Prozessoren, **lückenloses Audit-Log** (haben wir als Pflicht-Baustein, docs/18). Self-hosted löst Residenz.

### Architektur-Entscheidung
**E2.1 — Betriebsart als first-class-Konzept** (Core-Setting `betriebsart ∈ {lokal, hybrid, server}` + Onboarding-
Wahl). Default `lokal` (Versprechen unangetastet, docs/35 §1). Die Betriebsart steuert Identitäts-Provider, Daten-
Routing und welche Hintergrundprozesse server-fähig sind.

**E2.2 — Multi-Tenant = SILO-FIRST.** Begründung: die **bestehende Per-Daten-Wurzel-Architektur IST praktisch schon
Silo** — jede App schreibt in ihre eigene Datei unter `data\apps\<id>`. Ein Mandant = **eine Daten-Wurzel** (`data\
tenants\<tid>\apps\<id>`), Identität über K1/Dizzi-ID (`user_id`→`tenant_id`-Routing). Das ergibt höchste Isolation,
Datenresidenz pro Mandant und **0 RLS-Retrofit-Risiko** für die sensiblen Apps (health `hoechst`, money, communication).
Dynamische Pool→Silo-Promotion erst, wenn Skalierung es erzwingt. Baut direkt auf **docs/50 P6.2** (Relay-Token: App-zu-
App-Auth) + **K1 Multi-User** auf.

**E2.3 — Frontend = Tauri-2-Desktop-Shell** um die bestehenden Web-Frontends (klein, scoped-native, sicher, web-first =
kein Rewrite). **Mobile bewusst schlanker** (docs/51 §2: Trading reduziert): Stufe 1 = **PWA/Tauri-Mobile** der nicht-
Trading-Apps gegen das Server-Backend; native RN/Flutter-Shell nur falls Mobile-Tiefe es verlangt. **Server-gebundener
Handy-only-Betrieb** möglich (Backend im Server-Modus); **lokal-only-übers-Handy bleibt offen** (technisch fraglich,
docs/51 §2).

**E2.4 — Hybrid-Failover (zuletzt, am härtesten gegatet).** Nur ein **klein definierter Satz „gesicherter Hintergrund-
prozesse"** läuft server-seitig weiter, wenn der PC aus ist: Health-Watch, Konnektor-Polling (read-only), Defense.
**Echtgeld/Trading-Live und jede Außenwirkung NIE autonom** server-seitig (HITL bleibt, K4). State-Sync lokal↔Server
über **append-only-Event-Log / CRDT-vorbereitete db** (Local-first-Muster). Jeder server-seitige Prozess hinter
expliziter Freigabe + Audit (docs/51 §2 „gesicherte Outreaches").

### Alternativen & Trade-offs
| Frage | Optionen | Urteil |
|---|---|---|
| Isolation | Pool+RLS · Bridge · **Silo** | **Silo** (passt zur Ist-Architektur, GDPR, sensible Apps) |
| Desktop-Shell | Electron · **Tauri 2** | **Tauri 2** (klein, sicher, hat Mobile, web-first) |
| Mobile | **PWA/Tauri-Mobile zuerst** · RN/Flutter | **PWA/Tauri-Mobile** (schlank, Trading reduziert); RN/Flutter optional |
| Sync | nur Server-Stream · **Event-Log/CRDT-ready** | **Event-Log/CRDT-ready** (offline-fähig, local-first) |

### Risiken
- **Hybrid-Failover = größtes Risiko** (Split-Brain, Daten-Divergenz, Außenwirkung bei PC-aus). ⇒ **zuletzt**, eng
  gegatet, read-only-Prozesse zuerst. **Hoch.**
- Mandanten-Ops-Last (Silo) wächst mit Mandantenzahl → Automatisierung/Promotion-Pfad. Mittel.
- **Same-User-Malware bleibt prinzipielles Restrisiko** (docs/18 §5) — ehrlich benannt, nicht wegplanbar.
- Regulatorik (EU-AI-Act/GDPR) für Server-Kommerz: DPA, Audit, Löschkonzept (`vault.purge_user` existiert in memory!).

### Phasen
- **Z2.1** Betriebsart-Setting + Onboarding (lokal Default).
- **Z2.2** Mandanten-Daten-Routing (`tenant_id`) + K1-Multi-User scharf + **docs/50 P6.2 Relay-Token aktivieren**.
- **Z2.3** Tauri-2-Desktop-Shell um die Web-Frontends.
- **Z2.4** Schlanke Mobile (PWA/Tauri-Mobile, Trading reduziert).
- **Z2.5** Hybrid-Failover (gesicherte Hintergrundprozesse, Event-Log-Sync) — **letzter, härtester Schritt**.

**Gate G-DEPLOY:** **Deployment-Priorität** (was zuerst: Desktop-Politur / Mobile / Server-Kommerz?) + **Datenschutz-
Modell** (Silo bestätigen? Datenresidenz-Region? Lösch-/DPA-Politik?) = Nutzer-Entscheide.

---

## §4 · THEMA §3 — MCP-BIDIREKTIONALITÄT + OUTBOUND AUF EXTERNE KI

### Ist (verifiziert)
- **INBOUND ✅** — `apps/core/app/ai/mcp_gateway.py`: ausgehender MCP-Server
  (Streamable-HTTP, JSON-RPC 2.0, **read-only v1**), Bearer-Token, **Sensitivitäts-Gate** (`_tool_stufe`/`_erlaubt`,
  hochsicher gesperrt ohne Freigabe), Aktions-Gate (Schreib-Tools extern gesperrt), MCP-**2025-06-18** structuredContent/
  Annotationen, Audit. OAuth-2.1/DCR = dokumentierter **v2-Slot**.
- **OUTBOUND ◐** — `providers.chain` eskaliert auf Boost-Cloud (NIM/Groq/Cerebras) mit **eigenen** Keys; Tool
  `boost_frage`. **NICHT gebaut:** dizzi ruft die **vom Nutzer genutzte** KI (deren Claude/GPT/Gemini-Abo via MCP/API).

### Recherche-Befund (2026, Quellen §13-C)
- **★ MCP-Sampling (`sampling/createMessage`, Spec 2025-06-18):** ein **Server fordert eine LLM-Completion vom CLIENT**
  an — der Server sieht **nie API-Keys**, **HITL by design** (Client wählt Modell, darf Prompt prüfen/ändern/ablehnen).
  ⇒ **Das ist die elegante Antwort auf docs/51 §3:** weil dizzis Core **schon ein Inbound-MCP-Server ist**, kann er —
  wenn der Nutzer via seinem Claude verbunden ist — eine schwere/nicht-sensible Aufgabe an **die KI des Nutzers
  zurückreichen**, ohne eigene Keys, ohne Daten-Leak über das hinaus, was der Nutzer ohnehin mit seinem Claude teilt.
- **Elicitation (`elicitation/create`)**: strukturierte Nutzer-Eingabe (accept/decline/cancel); **Form-Mode NIE für
  Secrets** (URL-Mode). **Roots**: Workspace-Grenzen. **Outbound-MCP-Client**: dizzi als Client zu externen MCP-Servern;
  Multi-Provider-Clients (Anthropic/OpenAI/Gemini) verbreitet.
- **Sicherheit:** der Client unterscheidet server-originierte nicht von nutzer-originierten Prompts → **Injektions-
  Risiko**. ⇒ exakt der Vektor, gegen den **docs/50 P4.2 `pruefe_prompt`** bereitsteht (heute noch ohne Live-Caller).
- Hinweis: es existiert bereits eine **2026-07-Spec** — die Adapter-Schicht muss versionierbar bleiben (heute Code auf
  2025-06-18, vom Gateway korrekt verhandelt).

### Architektur-Entscheidung
**E3.1 — EINE „externe-KI"-Abstraktion mit DREI Outbound-Modi**, vereint mit `providers.chain` + appkit/connectors
(docs/35 auf KI ausgeweitet):
1. **MCP-Sampling (Default, elegantester Win):** Sampling-Capability in das Inbound-Gateway. Eskaliert über die **schon
   bestehende** Nutzer-Verbindung an dessen Claude/GPT — **keine Keys, governed, HITL**. Bestes Kosten-/Datenschutz-
   Profil.
2. **Outbound-API-Provider:** Claude/OpenAI/Gemini als Eskalations-Provider in `chain()` (Nutzer-Key im **Tresor**,
   appkit/vault). Für „PC verbunden, aber kein MCP-Client offen".
3. **Outbound-MCP-Client:** dizzi als Client zu externen MCP-Servern (fremde-Quelle/-KI als Tool, via connectors).

**E3.2 — Governance-Gate (verbindlich, fail-closed):** **sensibel/hoechst verlässt NIE** den Rechner (Gate aus
`providers.chain(sensitive)` + `mcp_gateway`-Sensitivität wiederverwendet); Outbound nur nach **Nutzer-Freigabe**;
**`pruefe_prompt` (P4.2) wird hier scharf** auf zurückkommenden Fremd-Text (schließt die docs/50-P4.2-Ehrlichkeits-
Lücke = „kein Live-Caller"); **alles auditiert** (db.audit ist Pflicht).

### Alternativen & Trade-offs
| Option | Pro | Contra | Urteil |
|---|---|---|---|
| Nur Boost (heute) | gebaut | nicht das **Abo des Nutzers**; eigene Keys/Kosten | ◐ Basis |
| Nur Sampling | keine Keys, top Datenschutz | braucht **aktive** Client-Verbindung | Teil 1 |
| **Vereinte 3 Modi** | deckt alle Fälle, eine Governance | mehr Oberfläche | ✓ **gewählt** |

### Risiken
- **Daten-Governance bei Outreach** (was verlässt den Rechner) → Sensitivitäts-Gate fail-closed + Audit + Freigabe.
- **Prompt-Injection** des zurückkommenden Inhalts → `pruefe_prompt` scharf (P4.2-Aktivierung). Mittel→niedrig.
- Kosten/Quota bei API-Modus → Modus 1 (Sampling) bevorzugen; Budgets/Limits.

### Phasen
- **Z3.1** **MCP-Sampling** im Gateway (größter Win, keine Keys).
- **Z3.2** Outbound-API-Provider in `chain` + Tresor-Keys + Governance-Gate + **P4.2 scharf**.
- **Z3.3** Outbound-MCP-Client (externe MCP-Server als Tool/Connector).
- **Z3.4** Gateway v2: OAuth-2.1/DCR über Dizzi-ID (echtes Remote, docs/31-Slot) — koppelt an §2 Server.

**Gate G-MCP:** **welche externen KIs** zugelassen + **Daten-Governance-Politik** (was darf je Sensitivität raus) =
Nutzer-Entscheid.

---

## §5 · THEMA §4 — MANAGEMENT → CROSS-DOMAIN-KI-AGENTEN-WORKFLOW-REGIE

### Ist (verifiziert)
- **Management = Social-Media** ([ME-Stand]): Kanäle/Bots/Posts/Zeitplan + Creating-Empfang + Redaktion + Bereich-Achse.
- **Bausteine für Agenten DA:** Core-Agent-Loop — `apps/core/app/ai/agent.py`
  (natives Tool-Calling, **Runden-Tools parallel** via `asyncio.gather`, `MAX_ROUNDS`, Fehler isoliert); `tools.registry`
  (MCP-Hub); **appkit/connectors** (externe Quelle/Senke, HITL-Senden); **K4-HITL** (appkit/actions); **Bereich-Typ-Modell**
  ([docs/49](49_BEREICH_TYP_MODELL.md): `art` schaltet Module frei; Typen geschaeft/mandant/studium/…).
- **NICHT gebaut:** Multi-Agenten-Regime, Workflow-Definitionen, externe-Dienst-Workflows pro Bereich,
  „Geschäftsmodell als Bereich", Management↔Admin-Geschäfts-Kopplung.

### Recherche-Befund (2026, Quellen §13-D)
- **Topologien:** Supervisor/hierarchisch · **Orchestrator-Worker (~70 % der Produktions-Systeme)** · Swarm. Sechs
  Muster: sequentiell · parallel-fan-out · supervisor/worker · hierarchische Delegation · Konsens/Debatte · HITL.
- **Governance verschiebt sich** von *human-in-the-loop* zu **human-on-the-loop** (Aufsicht statt Einzel-Freigabe) — aber
  **High-Stakes/Schreibpfade bleiben HITL**. Bausteine: **Planning-/Policy-/Execution-Units**.
- Frameworks: LangGraph/CrewAI/AutoGen (Dev), managed (Cloud), n8n/Zapier (visuell).

### Architektur-Entscheidung
**E4.1 — Management wird die Agenten-/Workflow-REGIE pro Bereich**, gebaut **auf dem Bestehenden** (kein neues
Schwergewicht): ein **Bereich** (v. a. Typ `geschaeft`/`mandant`, docs/49) kann eine **Workflow-Definition** tragen =
**Orchestrator-Worker-Graph** aus Agenten; jeder Agent = `(Rolle, Tool-Teilmenge aus tools.registry + Connectors,
Sensitivität, HITL-Politik)`. **Ausführung läuft auf der Core-Agent-Runtime** (`agent.py` als EINE Quelle — schon
parallel-fähig, MCP-fähig, HITL-fähig). **Management = die Regie-/Governance-UI** (definieren, beobachten, freigeben);
**Admin = Geschäftsmodell-Kopplung** (Rechnungen/EÜR/Fristen, docs/49 Modul `geschaeft`).

**E4.2 — Rollen-Abgrenzung (wer orchestriert was):** **Core** = Agent-Runtime/Ausführung · **Management** = Regie +
Governance + Außen-Workflows · **Admin** = Geschäfts-/Bereichs-Kopplung · **Creating-Direktor** = domänen-spezifischer
Bild-Orchestrator (bleibt eigenständig, NICHT von Management übernommen) · **Communication** = Kanal-Ausführung der
Outreach-Schritte.

**E4.3 — Autonomie-Stufen:** read/plan = **human-on-the-loop**; **jede Außenwirkung/Schreibpfad = HITL `verifiziert`
fail-closed** (K4). Pilot startet **HITL-überall**, lockert erst nach Vertrauen auf on-the-loop.

### Alternativen & Trade-offs
| Option | Pro | Contra | Urteil |
|---|---|---|---|
| Externes Framework (LangGraph) übernehmen | fertige Muster | schwere Dependency (gegen F-Q1 kleine Abhängigkeitsfläche), Fremd-Governance | ✗ als Laufzeit |
| **Eigene Runtime erweitern + Muster leihen** | nutzt Vorhandenes (parallel/MCP/HITL/Sensitivität), schlank | Muster selbst bauen | ✓ **gewählt** |
| Graph nur als Datenmodell (LangGraph-Stil) | klare Semantik | — | ✓ als Definitions-Schema |

### Risiken
- Komplexität/Runaway-Agenten/Kosten/Governance → **Pilot mit EINEM Bereich** (E-Mail-Manager einer `geschaeft`-Marke,
  docs/51 §4-Beispiel), HITL-überall, Budgets, Audit. **Hoch** bis bewiesen.
- Abgrenzungs-Drift (Management vs. Core vs. Creating) → E4.2 fixiert die Verantwortungen.

### Phasen
- **Z4.1** Workflow-Datenmodell (Bereich → Workflow → Agenten/Tools/HITL) + **read-only-Visualisierung**.
- **Z4.2** Orchestrator-Worker-Ausführung auf Core-Runtime, **HITL-gegatet**.
- **Z4.3** Externe-Dienst-Workflows über Connectors (**E-Mail-Manager-Pilot**, docs/38-Meta/JMAP-Slots).
- **Z4.4** Admin-Geschäftsmodell-Kopplung (Bereich `geschaeft` ↔ Workflow ↔ Rechnung/EÜR/Frist).

**Gate G-AGENT:** **Pilot-Bereich** + **Autonomie-Grad** (wie viel on-the-loop ab wann) = Nutzer-Entscheid.

---

## §6 · THEMA §5 — UI-BUILDER → APP-BUILDING + APP-MARKTPLATZ (Fernziel)

### Ist (verifiziert)
- **UI-Builder = Standalone** (`tools/ui-builder-tool`, „bei weitem noch nicht wie gewollt", [UI-Builder-Notiz]).
- **Bausteine DA:** **App-Vertrag** ([docs/16]) · **appkit/ui-kit** (Single-Source) · **CSP-Recipe** ([docs/37]) · **MCP**.
- **NICHT gebaut:** App-Builder, Einreichung, Review, Sandbox für Fremd-Apps, Marktplatz/Beteiligung. **Bewusst ganz
  hinten** (docs/51 §5).

### Recherche-Befund (2026, Quellen §13-E)
- **Sandboxing untrusted code:** **WASM** (lineare, bounds-checked Speicher-Isolation; WebContainers/Shopify/Fastly) ·
  **iframe + CSP** (Claude-Artifacts-Muster: CSP-Meta in sandboxed iframe, auch gegen späteres JS) · Pydantic *Monty*
  (Python-in-Rust). **Low-Code 2026:** Betty Blocks (WASM-Actions unter IT-Guardrails), Bubble (Plugin-Marktplatz).

### Architektur-Entscheidung
**E5.1 — Sequenz (strikt zuletzt):** (1) **App-Vertrag → „SDK"** für Fremd-Entwickler härten (Manifest + appkit/ui-kit +
CSP + MCP + Sandbox-Vertrag, docs/16 als Basis). (2) **Fremd-App-Sandbox = DIESELBE Mandanten-Isolation wie Server (§2):**
Fremd-Backend = eigener Prozess hinter eigener Daten-Wurzel + **CSP-strikt** + Sensitivitäts-Routing + **Relay-Token
(docs/50 P6.2)**; Fremd-Frontend-Panels = **iframe + CSP** (Artifacts-Muster); WASM als spätere In-Process-Option.
(3) **Review-/Security-Gate** für Einreichungen. (4) **Marktplatz + Beteiligungs-Modell**. **UI-Builder-Qualität zuerst
heben.**

**E5.2 — Schlüssel-Synergie:** §5 braucht **keinen eigenen Isolations-Stack** — es erbt **exakt** die Härtung, die §2
(Server-Multi-Tenant) ohnehin baut (P6.2/3/4 + K1). ⇒ App-Builder wird erst **nach** dem Server-/Kommerz-Schritt
realistisch und dann **billig**.

### Alternativen & Trade-offs
| Frage | Optionen | Urteil |
|---|---|---|
| Fremd-Backend-Sandbox | **Prozess-Isolation + Daten-Wurzel + Relay-Token** · WASM · gVisor | **Prozess+Relay-Token** (passt zur Ist-Arch); WASM später |
| Fremd-Frontend | **iframe + CSP** · WASM-UI | **iframe + CSP** (Artifacts-Muster) |

### Risiken
- **Riesige Sicherheits-Oberfläche** — nur tragbar **nach** §2-Härtung. **Sehr hoch** bis dahin. ⇒ Gate: erst im
  geschäftsfähigen Bereich.

### Phasen (alle nach §2)
- **Z5.1** App-Vertrag → SDK-Doku + UI-Builder-Qualität.
- **Z5.2** Fremd-App-Sandbox (erbt §2-Isolation).
- **Z5.3** Review + Marktplatz + Beteiligung.

**Gate G-BUILDER:** **Geschäfts-/Beteiligungs-Modell** + Eintrittszeitpunkt = Nutzer-Entscheid (frühestens nach §2).

---

## §7 · PER-APP-TIEFENRUNDE (jedes Thema × jede App + appkit/ui-kit)

> Was bedeutet jedes Thema konkret je Komponente — welche Naht fehlt, welcher Umbau, welches Risiko, welche Reihenfolge.
> `creating`/`trading` = **nur lesen** (eigene Chats; nicht anfassen). Sensitivität aus der Netz-Doku.

| Komponente | §1 Runtime/Modell | §2 Deployment | §3 MCP-Outbound | §4 Agenten-Regie | §5 App-Builder |
|---|---|---|---|---|---|
| **core** :8200 | **Heimat** runtime.py + Modell-Profil; agent/providers/ollama rufen Adapter | **Heimat** Betriebsart-Setting + tenant-Routing + K1; Gateway-v2-OAuth | **Heimat** Sampling + Outbound-Chain + Governance | **Heimat** Agent-Runtime (agent.py) | **Heimat** App-Vertrag/SDK + MCP-Hub |
| **appkit** (pkg) | **NEU `runtime.py`**; ollama.py = 1. Adapter | auth.py Multi-User; connectors; vault.purge_user (Lösch) | **NEU „externe-KI"-Abstraktion**; pruefe_prompt scharf (P4.2) | connectors + actions(HITL) + Workflow-Primitive | App-Vertrag→SDK + Sandbox-Vertrag |
| **ui-kit** (pkg) | — | **Render-Sanitization (P6.3)** + CSP-Härtung (P6.4) | — | Workflow-/Agenten-Visualisierung (Komponenten) | iframe-Panel-Host + Builder-Komponenten |
| **news** :8216 normal | Embed/Chat-Profil swappen | Multi-Tenant unkritisch | Outbound OK (nicht-sensibel: Zusammenfassung) | „News-Watch"-Agent je Bereich | **Template-App-Kandidat** (Vanilla-Muster) |
| **money** :8210 normal→sensibel | Schnell-strukturiert (Kategorisierung) | Silo; **Ledger-Residenz** (Sorgfaltskern) | **NIE Outbound** (Finanz sensibel) | Rechnungs-/EÜR-Agent (Admin-gekoppelt) | n/a (sensibel) |
| **communication** :8218 hoechst | Triage-Modelle | hoechst→**lokal_only**; **Inbound-Webhook braucht Tunnel/Server ⇒ Hybrid-Treiber** (docs/38 §2) | **hoechst NIE raus**; Senden bleibt HITL | **E-Mail-Manager = DER §4-Pilot** | n/a |
| **creating** :8214 *(nur lesen)* | **Eigener Vision/Image-Runtime-Pfad** (ComfyUI ≠ LLM-Runtime) | normal | — | **Creating-Direktor bleibt eigener Orchestrator** | n/a |
| **memory** :8212 normal | **Embed-Registry = Modell-Flex-Vorbild**; `VEC_SCHEMA u2`-Re-Index-Gate | Vault-Residenz; `purge_user` da | RAG-Kontext könnte eskalieren (nicht-sensibel) | Wissens-Agent | n/a |
| **management** :8213 hoch→lokal_only | KI-Modelle | hoch→lokal_only; Silo | Social-Outbound via HITL | **Heimat der Agenten-Regie-UI** | n/a |
| **healthy** :8217 höchst→lokal_only | **Lokal-only-Modelle** (höchst) | höchst→**nie Server ohne starkes Gate** | **NIE Outbound** | Lokaler Gesundheits-Coach-Agent (nie Diagnose) | n/a |
| **admin** :8222 hoch | KI-Modelle | hoch; Silo | vorsichtig | **Geschäftsmodell-Kopplung + Bereich-Typ-Heimat** (docs/49) | n/a |
| **trading** :8137 *(read-only)* | **Eigener Stack** | **Mobile reduziert** (docs/51 §2) | Externe Daten/KI-Inputs (docs/35 §4) | eigenes Bot-Regime (nicht Management) | n/a |

**Querschnitt-Erkenntnis:** Die **sensiblen Apps** (health höchst, money/communication, management/admin hoch) sind der
Grund, warum **Silo + lokal_only + Outbound-Sperre** nicht verhandelbar sind — sie diktieren die konservativste
Isolations-Wahl fürs ganze Netz.

---

## §8 · PHASEN-GESAMTPLAN + ABGRENZUNG ZUM LAUFENDEN A–E

### 8.1 Kritischer Pfad (Reihenfolge mit Voraussetzungen)
```
docs/50-FUNDAMENT (läuft, gegatet):  Go-Live  →  P6.2 Relay-Token  →  P6.3 Render-Sani  →  P6.4 CSP-Flip  →  K1 Multi-User
                                                          │                                              │
ZUKUNFT (dieses Doc):                                     ▼                                              ▼
   Z1 Runtime-Abstraktion (unabhängig, jederzeit) ── kann parallel früh starten
   Z3 MCP-Outbound (Z3.1 Sampling früh; Z3.2 braucht P4.2) ── teils parallel
   Z2 Deployment ── Z2.2 braucht P6.2 + K1 · Z2.5 Hybrid zuletzt
   Z4 Agenten-Regie ── braucht docs/49 (✅) + Z3 · Pilot HITL-only
   Z5 App-Builder ── braucht Z2 (Server-Isolation) KOMPLETT · strikt letztes
```
**Frühstarter (risikoarm, additiv, lokal):** **Z1.1** (Runtime-Adapter) und **Z3.1** (MCP-Sampling) — beide ohne
Server/Multi-User, beide hoher Wert. **Schwergewichte zuletzt:** **Z2.5** (Hybrid) und **Z5** (App-Builder).

### 8.2 Abgrenzung neue Roadmap ↔ docs/50 (KEINE Kollision, Gesetz 9)
| docs/50 (laufend) | docs/52 (Zukunft) | Beziehung |
|---|---|---|
| K1 Dizzi-ID (gebaut) · P6.1 Multi-User-Loops | Z2.2 Mandanten-Routing | docs/52 **aktiviert** die Naht |
| P6.2 Relay-Token (entworfen, gegatet) | Z2.2 + Z5.2 | **Voraussetzung** — docs/52 schaltet scharf |
| P6.3 Render-Sani · P6.4 CSP-Flip (gegatet) | ui-kit-Härtung (§7) | **Voraussetzung** für Server/App-Builder |
| P4.2 pruefe_prompt (gebaut, kein Caller) | Z3.2 (scharf auf Fremd-Text) | docs/52 **liefert den Live-Caller** |
| P5.1 ExternalConnector (gebaut) | §3 Modus 3 + §4 Workflows | docs/52 **nutzt** das Gerüst |
| Go-Live (gegatet) + Creating-Nachzug §9 | — | **muss zuerst**; docs/52 wartet nicht darauf für Z1/Z3.1 |

**Wichtig:** docs/52 ersetzt **nichts** aus docs/50; es **verlängert** den Bogen nach dem A–E-Go-Live. Bis Go-Live +
Creating-Nachzug stehen, bleiben Z2.2+/Z4/Z5 **geparkt** (sie brauchen das Fundament). Z1.1 + Z3.1 könnten als nächste
additive Wins direkt nach Go-Live beginnen.

### 8.3 Keine veralteten kollidierenden Pläne
Geprüft: docs/35 (Konnektivität-Vision) bleibt **Nordstern** und wird hier auf KI/Server **erweitert, nicht ersetzt**;
docs/31 (MCP-Gateway) v2-OAuth-Slot wird hier **konkretisiert** (Z3.4); docs/49 (Bereich-Typ) wird **Fundament** für §4.
**Kein Altplan widerspricht** dieser Roadmap. (Falls künftig ein Altplan kollidiert: hier als überholt markieren.)

---

## §9 · RISIKO-REGISTER (verdichtet)

| ID | Risiko | Thema | Höhe | Minderung |
|---|---|---|---|---|
| R1 | Hybrid-Failover Split-Brain / Außenwirkung bei PC-aus | §2 | **Hoch** | zuletzt; nur read-only-Prozesse server-seitig; Event-Log-Sync; HITL bleibt |
| R2 | Multi-Tenant-Daten-Leak zwischen Mandanten | §2/§5 | **Hoch** | Silo (DB-pro-Mandant); Relay-Token; Audit |
| R3 | Fremd-App-Sicherheit (Builder) | §5 | **Sehr hoch** | erst nach §2-Härtung; Prozess-Isolation + CSP + Review-Gate |
| R4 | Runaway-/teure Agenten | §4 | **Hoch** | Pilot HITL-only; Budgets; Sensitivitäts-Gate; Audit |
| R5 | Daten-Leak bei KI-Outreach | §3 | Mittel | sensibel/hoechst NIE raus (fail-closed); Freigabe; Audit |
| R6 | Prompt-Injection (Sampling/Fremd-Text) | §3/§4 | Mittel | P4.2 `pruefe_prompt` scharf; Tool-Output als untrusted |
| R7 | Runtime-Abstraktions-Leck (constrained decoding) | §1 | Niedrig | Capability-Flags; fail-safe→Fallback; Adapter-Tests |
| R8 | Regulatorik EU-AI-Act/GDPR (Server-Kommerz) | §2 | Mittel | self-hosted/Residenz; DPA; Audit-Log (Pflicht); `purge_user` |
| R9 | Same-User-Malware (Restrisiko) | alle | **Hoch (unvermeidbar)** | docs/18 §5 — ehrlich benannt; DPAPI/Keyring mildern |

---

## §10 · GATES (Nutzer-Entscheide — NICHT raten, Gesetz 2)

| Gate | Frage | Status / Antwort (27.06.) |
|---|---|---|
| **G-MODELL** | Lokaler Default-Standard (Modell/Profil)? | **✅ Nutzer: „immer das Beste, upgradebar"** → E1.3 Modell-Liefer-Kanal (lokal auto-update/release-gegatet; server top-gepflegt). Stufe-0 = qwen3:14b/4b/bge-m3 bis 1. Release |
| **G-DEPLOY-1** | Deployment-Priorität: Desktop / Mobile / Server-Kommerz zuerst? | **✅ Nutzer: „lege die Reihenfolge selbst sinnvoll fest"** → **Desktop (Tauri) + Z1 Runtime/E1.3 + Z3.1 Sampling zuerst** (risikoarm/lokal); Mobile danach; Server-Kommerz später |
| **G-DEPLOY-2** | Datenschutz-/Mandanten-Modell? | **✅ Nutzer: „vorerst lokal bleiben"** → Server/Multi-Tenant **geparkt**; Silo bleibt die *vorgesehene* Wahl, wenn der Server-Schritt kommt (nicht jetzt entscheiden) |
| **G-MCP** | Welche externen KIs zulassen? Daten-Governance je Sensitivität? | offen — Empfehlung: Sampling (Nutzer-Claude) zuerst; sensibel/hoechst NIE raus; API-Modus opt-in |
| **G-AGENT** | §4-Pilot-Bereich + Autonomie-Grad? | offen — Empfehlung: E-Mail-Manager einer `geschaeft`-Marke; **HITL-only** Start |
| **G-BUILDER** | App-Builder-Geschäfts-/Beteiligungs-Modell + Zeitpunkt? | offen — Empfehlung: erst nach §2-Server-Härtung; Beteiligungs-Modell später |

> **Folge der Antworten für die Reihenfolge (§8):** weil **„vorerst lokal"** + **Desktop zuerst** → der nahe Weg ist
> **Z1 (Runtime + E1.3 Modell-Kanal) · Z3.1 (MCP-Sampling) · Tauri-Desktop-Shell**; **Z2.2+/Z4/Z5 bleiben geparkt**
> (Server/Multi-Tenant/Agenten-Regie/App-Builder) bis der Nutzer den Server-Schritt freigibt. G-MCP/G-AGENT/G-BUILDER
> bleiben offen, bis ihr Thema an der Reihe ist.

---

## §11 · QUELLEN (2026-Recherche, 27.06.2026)

**A · Modelle/Runtime/Constrained-Decoding (§2):**
- [vLLM vs llama.cpp vs Ollama Benchmarks 2026 (quantizelab)](https://www.quantizelab.dev/articles/vllm-vs-llama-cpp-vs-ollama-benchmark-guide)
- [Red Hat: llama.cpp vs vLLM — right local inference engine (06/2026)](https://developers.redhat.com/articles/2026/06/15/llamacpp-vs-vllm-choosing-right-local-llm-inference-engine)
- [vLLM vs Ollama vs LM Studio — 2026 Production Self-Host Benchmark (codersera)](https://codersera.com/blog/vllm-vs-ollama-vs-lm-studio-production-2026/)
- [Hivenet: vLLM vs TGI vs TensorRT-LLM vs Ollama (TGI Maintenance-Mode)](https://www.hivenet.com/post/vllm-vs-tgi-vs-tensorrt-llm-vs-ollama)
- [Grammar-Constrained Generation (TianPan, 04/2026)](https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability)
- [XGrammar als Default-Backend (DeepWiki Structured Outputs)](https://deepwiki.com/sihyeong/Awesome-LLM-Inference-Engine/4.7-structured-outputs)
- [Best Local LLM Models 2026 (sitepoint)](https://www.sitepoint.com/best-local-llm-models-2026/)

**B · Deployment/Multi-Tenant/Sync/Shells/Regulatorik (§3):**
- [Database-Per-Tenant = neuer SaaS-Standard (ve3.global)](https://www.ve3.global/the-multi-tenancy-why-a-database-per-tenant-model-is-the-new-standard-for-saas/)
- [Multi-Tenant SaaS Deployment 2026 (Northflank)](https://northflank.com/blog/multi-tenant-saas-platform-deployment)
- [Self-Hosted AI: T1–T5 Deployment-Stufen (Arvo AI, 2026)](https://www.arvoai.ca/blog/self-hosted-ai-sre)
- [Best Offline-First Tech Stack 2026 (cssauthor)](https://cssauthor.com/offline-first-tech-stack/)
- [Tauri vs Electron 2026 (tech-insider)](https://tech-insider.org/tauri-vs-electron-2026/)
- [Cross-Platform-Tools-Vergleich 2026 (codenote: Tauri 2 / Flutter 3.41 / RN)](https://codenote.net/en/posts/cross-platform-dev-tools-comparison-2026/)
- [EU-AI-Act Deadlines 2026–2027 (legiscope)](https://www.legiscope.com/blog/eu-ai-act-timeline-deadlines.html)
- [AI & GDPR 2026 — was sich für LLM-Provider ändert (regolo.ai)](https://regolo.ai/ai-privacy-and-compliance-in-2026-what-changes-for-llm-providers/)

**C · MCP bidirektional / Sampling / Outbound (§4):**
- [MCP Sampling (2025-06-18 Spec)](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling)
- [MCP Features: Tools/Resources/Prompts/Sampling/Roots/Elicitation (WorkOS)](https://workos.com/blog/mcp-features-guide)
- [Was sich in der 2026-07-MCP-Spec ändert (Stacktree)](https://stacktr.ee/blog/mcp-2026-spec-changes)
- [Beyond Claude: OpenAI + Gemini mit MCP-Servern (Medium)](https://thesof.medium.com/beyond-claude-using-openai-and-google-gemini-models-with-mcp-servers-eea3bc218ed0)

**D · Multi-Agent-Orchestrierung/Governance (§5):**
- [AI-Agent-Orchestration-Patterns 2026 (jobsbyculture)](https://jobsbyculture.com/blog/ai-agent-orchestration-patterns-2026)
- [Best Multi-Agent Frameworks 2026: LangGraph/CrewAI/AutoGen (gurusup)](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [AI-Agent-Orchestration Enterprise-Guide 2026 (viston)](https://viston.tech/ai-agent-orchestration-in-2026-moving-from-pilots-to-enterprise-wide-execution/)

**E · App-Builder/Sandboxing/Marktplatz (§6):**
- [WebAssembly löst AI-Agenten-Sicherheitslücke (The New Stack)](https://thenewstack.io/webassembly-sandboxing-ai-agents/)
- [Awesome Code Sandboxing for AI (GitHub restyler)](https://github.com/restyler/awesome-sandbox)
- [iframe-Sicherheit + CSP (qrvey)](https://qrvey.com/blog/iframe-security/)
- [14 Best Low-Code Development Platforms 2026 (weweb)](https://www.weweb.io/blog/low-code-development-platforms-buyers-guide)

---

## §12 · LIVE-STATUS (mitgeführt, Gesetz 9)

- **27.06.2026 · Erstellung:** Recherche (§11) + Ist-Verifikation am Code (providers/ollama/mcp_gateway/auth/connectors/
  agent/rag + docs 17/18/35/38/49/50) abgeschlossen; Architektur-Entscheidungen E1.1–E5.2, Per-App-Matrix §7, Phasen §8,
  Risiken §9, Gates §10 festgehalten. **Reine Planung — 0 Code-Umbau, 0 Live-Neustart** (docs/51-Auftrag). Worktree
  `chat/zukunft`. README-Index ergänzt.
- **27.06.2026 · 3 Strategie-Gates beantwortet (Nutzer):** **G-MODELL** = „immer das beste Modell, upgradebar" →
  E1.3 Modell-Liefer-/Auto-Update-Kanal (lokal hardware-bewusst auto-update + release-gegatet; server top-gepflegt;
  Stufe-0 = qwen3:14b/4b/bge-m3 bis 1. Release). **G-DEPLOY-1** = „Reihenfolge selbst sinnvoll festlegen" → Desktop +
  Z1 + Z3.1 zuerst. **G-DEPLOY-2** = „vorerst lokal bleiben" → Server/Multi-Tenant geparkt; Silo bleibt die vorgesehene
  Wahl für später. Doc §2/§8/§10 entsprechend nachgeführt.
- **OFFEN (nächster Schritt):** Gates **G-MCP / G-AGENT / G-BUILDER** bleiben offen bis ihr Thema dran ist. Erste
  additive Wins (frühestens nach docs/50-Go-Live): **Z1.1 Runtime-Adapter · Z1.4 Modell-Kanal · Z3.1 MCP-Sampling**.
- **GEPARKT bis Fundament/Server-Freigabe:** Z2.2+/Z4/Z5 (brauchen docs/50 P6.2/3/4 + K1-Multi-User + Go-Live + den
  bewusst aufgeschobenen Server-Schritt).
- **NIE angefasst:** `apps/creating` (Training) · `apps/trading` (Geld-System) — nur lesend referenziert.
- **27.06.2026 · Vertiefungs-Schleife (modifizierte Kern-Dauerschleife, docs/32):** zweiter Tiefen-Durchgang über die
  ganze Planung — tiefere Code-Verifikation (db/tools/actions/guard/vault) + 11 Lücken-Recherchen (2026) + Mehr-
  Perspektiven-Synthese. Ergebnis = **§13 (9 Querschnitt-Säulen Q1–Q9 + Wert-Karte + Per-App-Höchstwert + Abhängigkeits-
  DAG + Aufwand) und §14 (verdichtete Übersichts-Roadmap in Wellen)**. Architektur-Kern §1–§12 bestätigt, nichts revidiert
  — nur ergänzt/verfestigt. Commit-Folge dokumentiert.
- **02.07.:** Kernanalyse docs/58 → §16.

---

## §13 · VERTIEFUNGSRUNDE — QUERSCHNITT-SÄULEN, WERT, AUFWAND (Loop 27.06.)

> Der erste Durchgang (§1–§12) deckte die **fünf Brief-Themen** ab. Die Schleife fand: die Themen brauchen **neun
> querschnittliche Säulen**, die durch ALLE Themen laufen und im ersten Durchgang nur implizit waren. Drei davon sind
> **echte Lücken** (heute 0 Infra), sechs **vertiefen Vorhandenes**. Plus die vom Nutzer erbetene **Wert-Karte**.

### 13.1 Die neun Querschnitt-Säulen (Q1–Q9)

| Q | Säule | Ist (verifiziert) | 2026-Befund (Quellen §13.6) | Entscheidung | Status |
|---|---|---|---|---|---|
| **Q1** | **Observability & Kosten-Governance** | nur `db.audit` (Wirkungs-/Auth-Log); **kein Token-/Kosten-/Latenz-Tracking** (grep: 0 Infra) | **OpenTelemetry GenAI Semantic Conventions** (`gen_ai.usage.*`, cost, agent-steps); self-hosted **Langfuse**; OTel-Collector-**Redaction vor Verlassen** | **NEU `appkit/observ.py`**: OTel-GenAI-Spans um runtime/agent/tool; Token/Latenz/Kosten je Call; lokale Senke default, Langfuse opt-in; **sensibel/hoechst → nur lokal**. **Cost-Budgets gaten §3-Outbound + §4-Agenten** | **❗LÜCKE** |
| **Q2** | **Agenten-Eval & Test-Disziplin** | starke Unit-Test-Kultur (X grün/App); **keine Agenten-/Nichtdeterminismus-Evals** | Non-Determinismus + Multi-Turn-Kaskaden brechen klass. Tests; **Eval-driven Dev = 60–80 % Aufwand**; Regression-CI | **Eval-Harness** für §4-Workflows (Szenario-Fixtures, Trajektorien-/Tool-Sequenz-Asserts, lokaler LLM-Judge opt.); **Evals BEVOR Autonomie gelockert** wird | **✅ GEBAUT (RG-4, gemergt 13.07.: `managementapp/agenten_eval.py`+`agenten_eichung.py` — Golden+Injection-Suite, def_hash-Gate, Eval-Schwellen VOR Autonomie exakt wie gefordert; Vermerk 20.07. Kernanalyse-R7)** |
| **Q3** | **Reaktive Kopplung / Event-Spine** | Querverbindungen V2–V19 = **Pull-Relays**; `updated_at`/`deleted_at`(Soft-Delete)+`audit_log` = Keim Append-Log | EDA/Pub-Sub = Rückgrat agentischer Systeme (Dapr/Kafka/NATS); Fanout, Fehler-Isolation | **Hybrid:** Pull-Relays behalten + **NEU leichter lokaler `appkit/events.py`** (Append-Only-SQLite-Log, in-proc pub/sub) für Agenten-Reaktionen, Hybrid-Sync, CRDT-Prep. **Kein Kafka** (Overkill); Server → NATS/Redis | **✅ GEBAUT (RG-1, gemergt 13.07.: als `appkit/ereignis_spine.py` — Append-Only-SQLite-Outbox + Cursor-Pull statt in-proc pub/sub, Hybrid wie empfohlen, „Zeiger nie Inhalt"-Whitelist; Vermerk 20.07. Kernanalyse-R7. Offen aus R5/R6: Retention `aufraeumen()` verdrahten)** |
| **Q4** | **Feingranulare Autorisierung (Rollen/Teilen)** | `auth.py` LEVELS = **vertikale Assurance**, NICHT horizontale Rollen/Sharing (Single-User moot) | RBAC bricht bei Sharing/Hierarchie/Multi-Tenancy; **ReBAC (Zanzibar/OpenFGA/Cedar)** = Superset | Levels behalten; **additiv ReBAC-Beziehungsmodell** (Bereich/App/Workflow geteilt mit Rolle). Lokal trivial; Server = OpenFGA-Stil. Koppelt §2/§4/§5 | Vertiefung (Server) |
| **Q5** | **Wissens-/Kontext-Rückgrat** | Core-Memory **L1–L4** (chat/episodes/observations/notices) + Memory-App (Vault+RAG-L3 bge-m3); RAG-Hybrid P3.1 + Link-Index P2.4 da | Agenten brauchen einheitlichen, sensitivitäts-bewussten Kontext | **Kontext-Broker** (appkit-Lesepfad): je Agent/Task Bereich-scoped + sensitivitäts-gefilterter Wissens-Kontext; nutzt vorhandenes RAG+Relays. Memory: Speicher → **aktiver Kontext-Dienst** | Vertiefung |
| **Q6** | **Ingress / Networking** | **Local-Guard** (Host-Allowlist+Origin) schützt localhost; Inbound-Webhooks brauchen öffentliche URL (docs/38) | Reverse-Proxy/TLS, cloudflared-Tunnel, Rate-Limit, mTLS | **Ingress-Schicht** je Betriebsart: lokal=Guard; **hybrid=getunnelter Webhook hinter Signatur** (Meta-Sig schon gebaut!); server=Proxy+TLS+Rate-Limit+per-Mandant-Origin | NEU (Hybrid/Server) |
| **Q7** | **Backup/DR & Migration/Release** | **backup-service** (`ops/backup_apps.py`, WAL-safe, täglich); vault DPAPI; **keine PITR/Replikation/Drills** | **Litestream** (WAL→S3-Streaming, **PITR, niedriger RPO, kein DB-Server**) — ideal für SQLite-pro-App/-Mandant | täglich-Backup behalten; **Litestream additiv** → Server-PITR + **löst NEBENBEI Hybrid-Off-PC-Sync**; versionierte idempotente Migrationen (Muster: `migriere_*`/`VEC_SCHEMA`) für E1.3+Multi-Tenant | Vertiefung + NEU |
| **Q8** | **UX-Systematik / Onboarding** | Settings/Fenster-Norm (docs/19) + Systemkarte-Erlebnis vorhanden | docs/51: „intuitiv, selbsterklärend, macht Spaß" | **Betriebsart-Onboarding** (lokal/hybrid/server) + konsistente Mode-Anzeige netzweit; Mobile = reduzierte geführte UX | Vertiefung |
| **Q9** | **Multimodal / Voice-Achse** | `voice.py` (wakeword) vorhanden; Runtime-Profil listet vision/voice (E1.2) | lokal/realtime machbar: **Parakeet-TDT/Moonshine 27 MB** STT, Chatterbox-Turbo/RealtimeTTS, RealtimeSTT-Wakeword | Voice/Vision als **Runtime-Profil-Task-Klassen** (E1.2) + opt. lokale Realtime-Voice-Schale (hoechst lokal_only); Vision bleibt Creating-eigen | Vorbereitet |

**Verzahnung mit den fünf Themen:** Q1+Q2 sind **Voraussetzung**, dass §3-Outbound + §4-Agenten *verantwortbar/verkäuflich*
werden (Kosten+Verlässlichkeit). Q3 macht §4 **reaktiv** + liefert den §2-Hybrid-Sync. Q4+Q6+Q7 sind **Server-Säulen** (§2/§5).
Q5 ist das **Gehirn** für §4. Q8+Q9 sind **Erlebnis/Differenzierung**.

### 13.2 Neue ehrliche Befunde aus der Code-Verifikation (Gesetz 2)
- **✅ bestätigt:** `db.py` trägt auf JEDER Tabelle `user_id` + `created_at/updated_at/deleted_at` (Soft-Delete) ⇒ die in
  §2/§3 angenommene **CRDT-/Sync-/Event-Reife ist real** (nicht nur behauptet). `actions.py` (K4-HITL: propose→approve→
  executing, at-most-once) + `vault.py` (Fernet+DPAPI, `purge_user`-fähig) + `guard.py` (Local-Guard) = solides
  Sicherheits-Fundament für §2/§4.
- **❗BESTÄTIGT (27.06., verifiziert):** `apps/core/app/ai/tools.py::MCP_SERVERS` referenziert durchgängig **Vor-Monorepo-
  Pfade** (`_CONNECTORS=parents[3]/"connectors"` statt Repo-Wurzel; `_APPS=parents[4]` + Alt-Namen
  `news/finanzen/creator/archiv/kommunikation/social-media/health/leading`). `_mcp_toolspecs` überspringt nicht-
  existente Pfade, **kein Laufzeit-Override** ⇒ **Agent + Inbound-Gateway laden aktuell KEINE App-Tools** (nur die
  internen). Das ist ein **Fundament-Loch für §3/§4** → als **Prerequisite W2.0** in docs/54 §0
  dokumentiert (gehört evtl. in den docs/50-A–E-Strang). *Caveat: nicht live getestet; Health-Watch hängt nicht daran.*
  **In dieser Planungs-Phase NICHT gefixt** (read-only, gegatet).

### 13.3 ★ WERT-/AUSBAU-KARTE (Nutzer-Frage „was am Wert geplant? wie ausbauen?")

| Fähigkeit (Phase) | Wert-Art | Ausbau-Hebel |
|---|---|---|
| Runtime-Abstraktion + **„immer bestes Modell"-Kanal** (Z1) | **Eigen-Nutzen + Verkaufsargument** je App (immer State-of-the-Art) | Modell-Releases als wiederkehrender Update-Strom; Server-Top-Modell als Premium |
| **MCP-Sampling** Outbound (Z3.1) | Eigen-Nutzen (perfekte Antworten via eigener Abo-KI, **0 Mehrkosten**) | später API-Provider-Modus als Komfort-Option |
| Observability/Cost (Q1) | **Voraussetzung Kommerz** (Abrechnung/Kostendeckel) + Qualitäts-Sicht | Mandanten-Kosten-Dashboards; Usage-based-Pricing möglich |
| **Agenten-Regie pro Bereich** (§4) | **Produktivitäts-Sprung** + Kern eines Abo-Produkts | je Bereichs-Typ vorgefertigte Workflow-Vorlagen (Markt!) |
| Desktop-Shell (Tauri) + Mobile (Z2.3/2.4) | **Distributier-/Verkaufsfähigkeit** (Installer, App-Stores) | Auto-Update-Kanal (mit Modell-Kanal koppeln) |
| Server-Multi-Tenant + DR (Z2.2/Q7) | **SaaS-Abo-Umsatz** (wiederkehrend) | Tiers T1–T5 (Shared→Air-Gapped) als Preisstufen |
| Einzel-App-Verkauf (heute schon Ziel) | **Direkt-Umsatz** je App standalone | jede App trägt Konnektivität+Sicherheit selbst (docs/35) ⇒ einzeln paketierbar |
| **App-Builder + Marktplatz** (§5) | **Plattform-/Beteiligungs-Umsatz** (Dritte liefern Apps) | Revenue-Share; Netzwerk-Effekt (organisches Wachstum) |

### 13.4 Per-App höchster Zukunfts-Wert (eine Naht je App)
- **core:** der **Hub** — Runtime-Abstraktion, Sampling, Agent-Runtime, Observability, Event-Spine wohnen hier.
- **communication:** **das §4-Aushängeschild** (E-Mail-Manager-Agent) + **der konkrete Hybrid-Treiber** (Inbound-Webhook).
- **management:** **Heimat der Agenten-Regie-UI** — vom Social-Tool zum Cross-Domain-Dirigenten.
- **admin:** **Geschäftsmodell-Kopplung** (Bereich-Typ `geschaeft`/`mandant` ↔ Workflow ↔ Rechnung/EÜR) = Geschäftsfähigkeit.
- **memory:** **Kontext-Rückgrat** (Q5) + Modell-Flex-Vorbild (Embed-Registry).
- **money:** sicherer Finanz-Agent (Kategorisierung/EÜR), **nie Outbound** — Vertrauens-Anker.
- **healthy:** lokaler Gesundheits-Coach (höchst, lokal_only) — Datenschutz-Differenzierung.
- **news:** **Template-App** (Vanilla-Muster) für den App-Builder + News-Watch-Agent.
- **creating** *(nur lesen):* eigener Vision-Runtime-Pfad; Direktor bleibt eigener Orchestrator.
- **trading** *(read-only):* Mobile-reduziert; externe-Daten/KI-Inputs optional.
- **appkit:** **wo die meisten neuen Nähte wohnen** (runtime/observ/events/externe-KI/ReBAC/SDK).
- **ui-kit:** Render-Sani (P6.3) + CSP (P6.4) + Workflow-Viz + iframe-Panel-Host (Builder).

### 13.5 Abhängigkeits-DAG + Aufwands-Grobschätzung (ehrlich „grob", relativ)
```
docs/50-FUNDAMENT (Go-Live · P6.2 · P6.3 · P6.4 · K1 · Creating-§9)        [läuft, gegatet]
        │
   ┌────┴──────────────── lokal, additiv (keine Server-Voraussetzung) ───────────────┐
   ▼                                                                                   ▼
 Z1.1 Runtime [M] → Z1.2 Profile [M] → Z1.4 Modell-Kanal [L]        Z3.1 MCP-Sampling [M]
   │                       │                                                │
 Q9 Voice-Profil [M]   Q1 Observability/Cost [L]  ──────────────► gatet ──► Z3.2 API-Provider [M] (+P4.2 [S])
   │                       │                                                │
 Z2.3 Tauri-Desktop [L]    └────► Q2 Eval-Harness [L] ──┐                 Z3.3 MCP-Client [M]
                                                         ▼
 Q5 Kontext-Broker [M] ──► Z4.1 Workflow-Modell [L] ──► Z4.2 Orchestrator [XL] ──► Z4.3 E-Mail-Pilot [L] ──► Z4.4 Admin-Kopplung [M]
                                  ▲                          ▲
                          Q3 Event-Spine [L] ───────────────┘
   ┌─── GEPARKT bis Nutzer-Server-Freigabe (braucht P6.2/3/4 + K1) ───────────────────────┐
   ▼                                                                                        ▼
 Z2.1 Betriebsart [M] → Z2.2 Mandanten-Routing [XL] → Q4 ReBAC [L] · Q6 Ingress [L] · Q7 Litestream/DR [L]
        │                                                     │
   Z1.3 vLLM-Adapter [M]   Z3.4 Gateway-v2-OAuth [L]   Z2.4 Mobile [L] → Z2.5 Hybrid-Failover [XL]
        └──────────────────────────────────────────────────────────┐
                                                                     ▼
                              Z5.1 SDK [M] → Z5.2 Fremd-App-Sandbox [XL] → Z5.3 Marktplatz [XL]
```
Größen: **S**≈klein · **M**≈mittel · **L**≈groß · **XL**≈sehr groß. *(Relative Grob-Orientierung, keine Zusage.)*
**Kritische Risiken liegen auf den XL-Knoten:** Z4.2 Orchestrator, Z2.2 Mandanten, Z2.5 Hybrid, Z5.2 Fremd-App-Sandbox.

### 13.6 Quellen Vertiefungsrunde (2026)
- [OpenTelemetry GenAI Observability (opentelemetry.io, 2026)](https://opentelemetry.io/blog/2026/genai-observability/) · [OTel for LLMs SRE-Guide 2026 (openobserve)](https://openobserve.ai/blog/opentelemetry-for-llms/) · [Top LLM Observability Tools 2026 (Confident AI)](https://www.confident-ai.com/knowledge-base/compare/top-7-llm-observability-tools)
- [Eval-driven Development (Red Hat, 03/2026)](https://developers.redhat.com/articles/2026/03/23/eval-driven-development-build-evaluate-ai-agents) · [AgentAssay: Regression Testing non-deterministic Agents (arXiv)](https://arxiv.org/pdf/2603.02601) · [Best AI Agent Evaluation Platforms 2026 (Galileo)](https://galileo.ai/blog/best-ai-agent-evaluation-platforms)
- [Event-Driven AI Agent Architecture 2026 (Fastio)](https://fast.io/resources/ai-agent-event-driven-architecture/) · [Dapr Agents Pub/Sub](https://docs.dapr.io/developing-ai/dapr-agents/dapr-agents-why/)
- [OpenFGA — Fine-Grained Authorization / Zanzibar](https://openfga.dev/docs/fga) · [OPA vs Cedar vs Zanzibar (Oso)](https://www.osohq.com/learn/opa-vs-cedar-vs-zanzibar)
- [Litestream — DR/PITR für SQLite](https://litestream.io/how-it-works/) · [SQLite-per-Tenant 2026 (Pockit)](https://pockit.tools/blog/sqlite-renaissance-turso-d1-libsql-production-guide/)
- [Best Open-Source STT 2026 / Parakeet/Moonshine (Northflank)](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks) · [RealtimeSTT (GitHub)](https://github.com/KoljaB/RealtimeSTT)

---

## §14 · ÜBERSICHTS-ROADMAP (verdichtet, in Wellen) — der konkrete Plan

> Geordnet nach den Nutzer-Entscheiden (§10): **„vorerst lokal" + Desktop zuerst + immer bestes Modell**. Server/Multi-
> Tenant/App-Builder bewusst in spätere Wellen geparkt. Jede Welle ist für sich auslieferbar (Wert am Ende jeder Welle).

### Welle 0 — FUNDAMENT *(läuft, docs/50, gegatet — Voraussetzung für Server-Wellen)*
Go-Live (Merge→master + Neustarts + Memory-RAG-Re-Index `VEC_SCHEMA u2`) · P6.2 Relay-Token · P6.3 Render-Sani ·
P6.4 CSP-Flip · K1-Multi-User scharf · Creating-§9-Nachzug. → **Ergebnis:** gehärtete Basis, auf der alles Weitere steht.

### Welle 1 — LOKALE HEBEL *(nach Go-Live; risikoarm, additiv, 100 % lokal)*
| Schritt | Liefert |
|---|---|
| **Z1.1** Runtime-Abstraktion + Ollama-Adapter · **Z1.2** Modell-Profile · **Z1.4** „immer bestes Modell"-Update-Kanal | Best-of-Breed-Modelle, upgradebar, hardware-bewusst auto-aktualisiert |
| **Z3.2** Outbound-API-Provider (+P4.2 scharf) | dizzi eskaliert schwere/nicht-sensible Aufgaben an Claude/GPT/Gemini (Nutzer-Key im Tresor), governed · *Sampling/MRT (Z3.1) vorbereitet, dormant — s. §15-K1* |
| **Q1** Observability/Cost (lokal) · **Q5** Kontext-Broker · **Q9** Voice-Profil | Kosten/Qualitäts-Sicht · klügerer Kontext · Sprach-Bedienung |
| **Z2.3** Tauri-2-Desktop-Shell | echte, kleine, sichere **Desktop-App** (Installer, Auto-Update) |
→ **Wert:** State-of-the-Art-Modelle + KI-Outreach gratis + Desktop-Produkt — alles lokal.

### Welle 2 — AGENTEN-REGIE *(lokal, HITL-zuerst)*
| Schritt | Liefert |
|---|---|
| **Q3** Event-Spine · **Q2** Eval-Harness | reaktives Netz + verlässliche, getestete Agenten |
| **Z4.1** Workflow-Modell → **Z4.2** Orchestrator-Worker (Core) → **Z4.3** E-Mail-Manager-Pilot → **Z4.4** Admin-Kopplung | **Management = Cross-Domain-Agenten-Regie pro Bereich** |
| **Z3.2** Outbound-API-Provider (+P4.2 scharf) · **Z3.3** Outbound-MCP-Client | vollständige bidirektionale KI-Vernetzung |
→ **Wert:** komplexe Geschäfts-/Bereichs-Workflows automatisiert, menschlich überwacht.

### Welle 3 — SERVER / KOMMERZ / MOBILE *(GEPARKT bis Nutzer-Server-Freigabe; braucht Welle 0)*
| Schritt | Liefert |
|---|---|
| **Z2.1** Betriebsart-Setting · **Z2.2** Mandanten-Routing (Silo) + K1 · **Q4** ReBAC | Multi-Tenant-Server, Rollen/Teilen |
| **Q6** Ingress (Proxy/TLS/Tunnel) · **Q7** Litestream-DR + Multi-Tenant-Backup | Inbound-Webhooks live · PITR · **Hybrid-Sync nebenbei** |
| **Z1.3** vLLM-Adapter · **Z3.4** Gateway-v2-OAuth · **Z2.4** Mobile (schlank) · **Z2.5** Hybrid-Failover *(zuletzt)* | Server-Top-Modell · echtes Remote · Handy-App · PC-aus-Weiterbetrieb |
→ **Wert:** wiederkehrender SaaS-Abo-Umsatz, Mobile-Reichweite, Ausfallsicherheit.

### Welle 4 — APP-BUILDER / MARKTPLATZ *(strikt zuletzt; erbt Welle-3-Isolation)*
**Z5.1** App-Vertrag→SDK + UI-Builder-Qualität · **Z5.2** Fremd-App-Sandbox (erbt Mandanten-Isolation) · **Z5.3** Review +
Marktplatz + Beteiligung. → **Wert:** Plattform-/Netzwerk-Effekt; Dritte liefern Apps; organisches Wachstum.

### Offene Gates (Nutzer-Entscheid, wenn die Welle dran ist)
- **G-MCP** (Welle 1/2): welche externen KIs + Daten-Governance je Sensitivität.
- **G-AGENT** (Welle 2): Pilot-Bereich + Autonomie-Grad (HITL → on-the-loop).
- **G-DEPLOY-2 / Server-Freigabe** (Welle 3): „vorerst lokal" aufheben? Silo bestätigen, Residenz, DPA.
- **G-BUILDER** (Welle 4): Geschäfts-/Beteiligungs-Modell + Eintrittszeitpunkt.

> **Nächster konkreter Schritt nach docs/50-Go-Live:** Welle 1 beginnen mit **Z1.1 (Runtime-Adapter)** +
> **Z3.2 (Outbound-API-Provider)** — beide additiv, lokal, hoher Wert, kein Gate offen. *(MCP-Sampling Z3.1 ist heute
> nicht client-fähig + spec-seitig auslaufend — s. §15-K1; daher vorbereiten, nicht starten.)*

---

## §15 · KORREKTUREN AUS EINZEL-RECHERCHE (Loop 27.06., Gesetz 2 — überschreibt frühere Stellen)

> Die Welle-1-Einzelrecherche (für die feine Umsetzungs-Ebene docs/53) hat drei Annahmen
> präzisiert/überholt. Hier offen festgehalten; die betroffenen Stellen oben sind angepasst.

- **K1 · MCP-Sampling ist KEIN „erster Win" mehr.** Die neueste Spec **2026-07-28 (SEP-2577) markiert Sampling als
  *deprecated*** (≥12 Mon. Auslauf), Nachfolger = **Multi-Round-Trip Requests (SEP-2322)**; zusätzlich **unterstützen
  Claude Desktop/Code Sampling heute NICHT** (offene Feature-Requests). ⇒ §4-Modus-1 + §14-Welle-1 **umgestellt**: der
  **Outbound-Win in Welle 1 ist der API-Provider-Modus (Z3.2)** (Nutzer-Key im Tresor, Governance-Gate, P4.2 scharf);
  **Sampling/MRT = vorbereiten/dormant**, scharf sobald Client-Support da ist. *(Quelle: modelcontextprotocol.io/
  specification + github.com/anthropics/claude-code#1785.)*
- **K2 · LiteLLM existiert als reife Runtime-/Provider-Abstraktion** (OpenAI-kompatibel, 140+ Provider inkl. Ollama+vLLM,
  Cost-Tracking, Router/Fallback). **Entscheidung bleibt: dünne `appkit/runtime.py` SELBST bauen** — wegen der nativen
  Ollama-Pfade (constrained-decoding-`format`-Slot + Tool-Call-Streaming, die der OpenAI-Kompat-Layer nicht zuverlässig
  trägt) **und** der kleinen Dependency-Fläche (F-Q1, docs/18). **LiteLLM = Kandidat für den SERVER/Multi-Provider-Adapter
  (Z1.3)**, nicht für den lokalen Kern. *(Quelle: github.com/BerriAI/litellm.)*
- **K3 · Observability (Q1) konkretisiert:** `opentelemetry-instrumentation-openai-v2` (offiziell, Contrib) bzw.
  **OpenLLMetry** (traceloop, OTel-basiert) + **Langfuse self-hosted als OTLP-Backend** (`/api/public/otel`); Kosten =
  Token×Preis als Span-Attribut; sensibel/hoechst → nur lokale Senke (Collector-Redaction). *(Quelle: langfuse.com/
  integrations/native/opentelemetry + traceloop/openllmetry.)*
- **★ Feine Umsetzungs-Ebene:** Welle 1 ist jetzt in **commit-große Arbeitspakete + Commit-Plan** zerlegt →
  **docs/53_WELLE1_ARBEITSPAKETE**.

---

## §16 · KERNANALYSE-QUERVERWEIS (02.07.2026, docs/58)

> docs/58_GESAMTSYSTEM_KERNANALYSE hat diese Roadmap gegen den Code geprüft.
1. Die **Z/Q-Architektur (§13/§14) ist code-verifiziert bestätigt** — Fan-out-Analyse fand keine Abweichung.
2. **★ Das §13.2-„Fundament-Loch" (W2.0) ist GESCHLOSSEN-verifiziert** (`tools.py` `parents[3]`-Monorepo-Pfade +
   `_connector_env()`-PYTHONPATH-Reinjektion, doppelt test-gesichert) — überschreibt §13.2; docs/54-C12 ist erledigt.
3. **Z1.1 `runtime.py`:** Architektur-KI-Paket = **nur der Interface-Vertrag** (FP-3, docs/58 §5.1); Ausbau C1–C11 = Bau-KI (VO-10).
4. **Welle-2-Z4-Agenten-Regie:** UX-Kanon + Bau-Verordnung = **docs/58 VO-3/§3.F**, Zündung als **FP-4**.
5. **Ausführungs-Modus +U (Ultracode)** neu für F★/XL-Bau-Pakete + netzweite Verify-Sweeps (docs/58 §5-Kopf).
6. **VO-4-Ergänzung §3/E2:** Handy-Biometrie braucht RP-ID-Hebung von `localhost` auf eine echte
   **Tailnet-HTTPS-Domain** (Tailscale MagicDNS + `tailscale cert`, ROR localhost∥ts.net) — s. docs/58 §3.H/VO-4.
