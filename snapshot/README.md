# the world of dizzi

**A personal, local-first AI network — one person, ten applications, one shared architecture.**

`the world of dizzi` is a self-hosted command centre for a whole life: money, communication,
health, knowledge, news, media, administration, and an autonomous trading fleet. Every
application runs on its own port, owns its own data, and plugs into the same contract — a
shared identity service, a shared UI kit, and an MCP tool bus that lets an AI assistant reach
every part of the network through a single connection.

It is built and maintained by **one person working with AI coding assistants**, using a written
method: laws before code, contracts before features, research protocols before decisions. The
documents in [`docs/`](docs/) are not an afterthought — they are the instrument that made a
system this size buildable by one human.

> **This is a curated public snapshot — some modules are intentionally not included.**
> **Source-visible showcase, not open source.** There is no LICENSE file: all rights reserved.
> You are welcome to read, study and evaluate the code. You may not copy, redistribute or use
> it in your own products.
>
> The snapshot lives inside the repository of the project's website; the source links on
> the site point into this folder. What you see here is a **state, not a history** — the
> commits that produced it are in a private working repository.

---

## The numbers

Measured on **27 July 2026**, against this snapshot, with the method written
next to each number — so the numbers can be reproduced instead of believed.

**Run the commands from inside this folder.** This snapshot is a folder in a
larger repository, so `git ls-files` at the repository root answers a different
question and returns larger numbers: it counts the website around this folder
as well.

| | | how it was counted |
|---|---|---|
| Applications | **10** (Core + 9) | directories under [`apps/`](apps) |
| Commits | **2,600+** since June 2026 | in the private working repository behind this snapshot — **not** the commit count of the repository you are reading this in. **The one figure on this page you cannot reproduce from this folder**, and stated as a floor for that reason |
| Python in this snapshot | **~100,000 lines** across **632** files | `git ls-files "*.py" \| wc -l` from this folder; the line figure counts non-blank lines (100,234 exactly; 119,249 with blanks). Lines are counted, not line breaks — two files here end without a closing newline, so a `wc -l` measurement loses their last line and reports 100,232. Same snapshot, two honest methods, two lines apart |
| Tests in this snapshot | **2,667** test functions in **309** files | functions whose name begins with `test_`, counted by parsing every tracked `.py` file in this folder — not by running the suite, so this is a count of tests written, not of tests passing |
| Tracked files | **966** | `git ls-files \| wc -l` from this folder |
| Built by | one person + AI coding assistants, local-first, no cloud dependency at the core | |

Each application runs independently. **Independently *sellable* is a design
goal, not a finished feature:** the export contract has design, stubs and
contract tests — the packaging tooling itself is not built yet
([`docs/66_APP_EXPORT_VERTRAG.md`](docs/66_APP_EXPORT_VERTRAG.md)).

## Architecture

A **headless Core service** (Python / FastAPI) holds the AI orchestrator, the panel registry,
the MCP hub and the health watch. Around it sit nine applications, each a FastAPI service with
its own SQLite database and its own web UI. Thin shells (desktop, mobile, browser) render the
same Core, so the whole network can move from a PC to a server unchanged.

```
        ┌──────────────── Shells: Desktop · Mobile · Browser ────────────────┐
        │                                                                    │
        │   ┌────────────────── Dizzi-Core  :8200 ──────────────────┐        │
        │   │  AI orchestrator · Panel registry · MCP hub           │        │
        │   │  Health watch · Dizzi-ID (single sign-on)             │        │
        │   └───────────────────────────────────────────────────────┘        │
        │        │        │        │        │        │        │              │
        │      Money   Comm.   Creating  Memory  Management  News  …         │
        │      :8210   :8218    :8214    :8212     :8213    :8216            │
        │                                                                    │
        └────────────────────────────────────────────────────────────────────┘
             shared: packages/appkit (contract, auth, security, deletion)
                     packages/ui-kit (design system, spin physics)
```

Three things hold it together:

- **The App Contract** ([`docs/16_APP_VERTRAG_SPEC.md`](docs/16_APP_VERTRAG_SPEC.md)) — every app
  exposes `/api/summary`, an MCP server, a Dizzi-ID relying-party hookup and a settings module.
  Write the contract, and the app appears in the dashboard automatically.
- **`packages/appkit`** — one shared library, no vendoring. Authentication, CSP hardening,
  account deletion proofs, security posture, area canon. Changed once, effective everywhere.
- **Cross-connections** ([`docs/26_QUERVERBINDUNGEN.md`](docs/26_QUERVERBINDUNGEN.md)) — data
  stays at its source; the Core only relays read-only; anything with outside effect needs an
  explicit human approval step.

## The applications

| App | Port | What it does |
|---|---|---|
| **Dizzi-Core** | 8200 | AI orchestrator, panel registry, MCP hub, health watch, agent orchestration |
| **Dizz Money** | 8210 | Finance manager: import, categorisation, budgets, EÜR/FX, a ledger care-core, German tax filing (ELSTER/UStVA), read-only bank sync over FinTS |
| **Dizz Communication** | 8218 | Unified inbox across e-mail and messengers, smart contacts, per-contact chat, appointment detection |
| **Dizz Creating** | 8214 | Local media workbench: image, video and music generation and editing over a shared GPU job queue, with asset management and AI labelling |
| **Dizz Memory** | 8212 | Knowledge store: markdown vault + SQLite/FTS5 + retrieval, area-level categorisation |
| **Dizz Management** | 8213 | AI agent administration: autonomy ladder, network inbox, editorial planning per area |
| **Dizz News** | 8216 | Sector-structured news digest from vetted sources, cross-source dedup, living watchlists |
| **Dizz Healthy** | 8217 | Health metrics, training, supplements, BLE wearables — the most sensitive data class |
| **Dizz Admin** | 8222 | Vault, projects, business, studies, deadlines — area-first, the home of the area-type model |
| **Dizz Trading** | 8137 | Autonomous trading bot fleet with a learning layer, Kelly sizing and a hard human-in-the-loop gate |

## Principles

- **Local-first.** The core runs offline. Cloud services are opt-in connectors —
  switchable off at any time, always shown as an external step.
- **Honesty over polish.** If a value was never measured, the system says so instead of
  showing a zero. This is written into the laws ([`docs/01_GRUNDGESETZE.md`](docs/01_GRUNDGESETZE.md)).
- **Nothing irreversible without a human.** Money, publishing and deletion sit behind explicit
  gates. The trading fleet proposes; a person decides.
- **Data at its source.** No central data lake. Apps hand over through written contracts.

## Where to look first

1. [`_netzwerk/SYSTEM_KARTE.html`](_netzwerk/SYSTEM_KARTE.html) — the interactive system map.
   Open it in a browser: it is self-contained, dark, responsive, and makes no external calls.
2. [`docs/12_GESAMTVERSTAENDNIS.md`](docs/12_GESAMTVERSTAENDNIS.md) — the whole system explained
   for someone with no prior knowledge.
3. [`docs/16_APP_VERTRAG_SPEC.md`](docs/16_APP_VERTRAG_SPEC.md) — the contract that makes ten
   applications behave like one.
4. [`packages/appkit/`](packages/appkit/) — the shared core library, where the care shows.

*The documentation is written in German; the code and its structure speak for themselves.*

---

# Deutsch

**Ein persönliches, lokal-first KI-Netzwerk — ein Mensch, zehn Anwendungen, eine Architektur.**

`the world of dizzi` ist eine selbst gehostete Kommandozentrale für ein ganzes Leben: Finanzen,
Kommunikation, Gesundheit, Wissen, Nachrichten, Medien, Verwaltung und eine autonome
Trading-Flotte. Jede App läuft auf einem eigenen Port, besitzt ihre eigenen Daten und dockt über
denselben **App-Vertrag** an: gemeinsamer Identitätsdienst, gemeinsames UI-Kit und ein
MCP-Werkzeugbus, über den eine KI mit **einer** Verbindung das ganze Netz erreicht.

Gebaut und gepflegt von **einem Menschen zusammen mit KI-Assistenten** — nach einer
geschriebenen Methode: erst Gesetze, dann Code; erst Verträge, dann Funktionen; erst
Recherche-Protokolle, dann Entscheidungen. Die Dokumente in [`docs/`](docs/) sind kein Beiwerk,
sondern das Instrument, das ein System dieser Größe für eine einzelne Person überhaupt baubar
gemacht hat.

> **Dies ist ein kuratierter öffentlicher Auszug — einzelne Module sind bewusst nicht enthalten.**
> **Einsehbarer Quellcode, keine Open-Source-Lizenz.** Es gibt keine LICENSE-Datei: alle Rechte
> vorbehalten. Lesen, studieren und bewerten ausdrücklich willkommen — kopieren, weitergeben
> oder in eigenen Produkten verwenden nicht.

### Die Zahlen

Gemessen am **27. Juli 2026**, an diesem Auszug; die Zählweise steht in der englischen
Tabelle oben neben jeder Zahl.

**10 Apps** (Core + 9) · **2.600+ Commits** seit Juni 2026 — im privaten Arbeits-Repository
hinter diesem Auszug — **nicht** die Commit-Zahl des Repositorys, in dem Sie das hier lesen ·
**~100.000 Zeilen Python** (ohne Leerzeilen) in **632** Dateien · **2.667 Test-Funktionen**
in **309** Dateien — gezählt, nicht ausgeführt: es sind geschriebene Tests, keine bestandenen ·
**966** versionierte Dateien · gebaut von einer Person mit KI-Assistenz, lokal-first, ohne
Cloud-Abhängigkeit im Kern.

### Die Architektur in einem Satz

Ein **headless Core-Service** (Python/FastAPI: KI-Orchestrator, Panel-Registry, MCP-Hub,
Health-Watch, Dizzi-ID) mit **dünnen Schalen** (Desktop → Mobile → Browser), sodass derselbe
Core unverändert vom PC auf einen Server umziehen kann — Windows wie Linux.

### Die drei tragenden Ideen

- **Der App-Vertrag** ([`docs/16`](docs/16_APP_VERTRAG_SPEC.md)): Wer ihn erfüllt, erscheint
  automatisch als Kachel im Dashboard und ist für die KI ansprechbar.
- **`packages/appkit`**: eine geteilte Bibliothek, kein Vendoring — einmal geändert, überall gültig.
- **Querverbindungen** ([`docs/26`](docs/26_QUERVERBINDUNGEN.md)): Daten bleiben bei der Quelle,
  Core-Relays nur lesend, Außenwirkung nur mit ausdrücklicher Freigabe durch den Menschen.

### Wo anfangen

1. [`_netzwerk/SYSTEM_KARTE.html`](_netzwerk/SYSTEM_KARTE.html) — die interaktive System-Karte
   (im Browser öffnen; self-contained, keine externen Aufrufe).
2. [`docs/12_GESAMTVERSTAENDNIS.md`](docs/12_GESAMTVERSTAENDNIS.md) — das Ganze ohne Vorwissen.
3. [`docs/README.md`](docs/README.md) — der Index aller netzweiten Normen und Verträge.
