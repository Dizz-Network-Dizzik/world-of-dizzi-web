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

> **This folder holds documents, not code.** Until 6 August 2026 it carried a curated code
> extract of 966 tracked files. It was cut back on purpose to the **38 documents** that show
> how the network is built and governed: the laws, the vision, the architecture papers, the
> written contracts, and one README per application.
>
> **All rights reserved.** There is no LICENSE file. You are welcome to read, study and
> evaluate what is here. You may not copy, redistribute or use it in your own products.
>
> The folder lives inside the repository of the project's website; the source links on
> the site point into it. What you see here is a **state, not a history** — the
> commits that produced it are in a private working repository.

---

## The numbers

**Run the commands from inside this folder.** This folder sits inside a larger
repository, so `git ls-files` at the repository root answers a different
question and returns larger numbers: it counts the website around this folder
as well.

| | | how it was counted |
|---|---|---|
| Applications | **10** (Core + 9) | one row each in *The applications* below. Nine of them also carry their own README under [`apps/`](apps); the trading fleet's papers are deliberately not published |
| Documents here | **38** | `git ls-files` from this folder, counted 6 August 2026 |
| Commits | **2,600+** since June 2026 | in the private working repository behind this folder — **not** the commit count of the repository you are reading this in. Stated as a floor, because it cannot be reproduced from here |
| Python, measured 27 July 2026 | **~100,000 lines** across **632** files | measured in the code extract that stood here until 6 August 2026 and **is no longer published**, so this can no longer be reproduced. It counted non-blank lines (100,234 exactly; 119,249 with blanks) |
| Tests, measured 27 July 2026 | **2,667** test functions in **309** files | same withdrawn extract: functions whose name begins with `test_`, counted by parsing every tracked `.py` file — not by running the suite, so a count of tests written, not of tests passing |
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
  The library itself is not published; the contract it has to satisfy is.
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

1. [`docs/12_GESAMTVERSTAENDNIS.md`](docs/12_GESAMTVERSTAENDNIS.md) — the whole system explained
   for someone with no prior knowledge.
2. [`docs/01_GRUNDGESETZE.md`](docs/01_GRUNDGESETZE.md) — the written laws the work obeys. The
   most unusual thing here, and the reason the rest exists.
3. [`docs/16_APP_VERTRAG_SPEC.md`](docs/16_APP_VERTRAG_SPEC.md) — the contract that makes ten
   applications behave like one.
4. [`docs/README.md`](docs/README.md) — the index of every network-wide norm and contract.

The interactive system map is on the website: <https://worldofdizzi.netlify.app/karte/>

*The documentation is written in German.*

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

> **Dieser Ordner enthält Dokumente, keinen Code.** Bis zum 6. August 2026 lag hier ein
> kuratierter Code-Auszug mit 966 versionierten Dateien. Er wurde bewusst auf die **38
> Dokumente** zurückgeschnitten, die zeigen, wie das Netz gebaut ist und wonach es sich
> richtet. **Alle Rechte vorbehalten**, es gibt keine LICENSE-Datei. Lesen, studieren und
> bewerten ausdrücklich willkommen — kopieren, weitergeben oder in eigenen Produkten
> verwenden nicht.

### Die Zahlen

**10 Apps** (Core + 9) · **38 Dokumente** in diesem Ordner (Stand 6. August 2026) ·
**2.600+ Commits** seit Juni 2026 — im privaten Arbeits-Repository
hinter diesem Ordner — **nicht** die Commit-Zahl des Repositorys, in dem Sie das hier lesen ·
**~100.000 Zeilen Python** (ohne Leerzeilen) in **632** Dateien und **2.667 Test-Funktionen**
in **309** Dateien — beides am 27. Juli 2026 im inzwischen zurückgezogenen Code-Auszug
gemessen und von außen **nicht mehr nachprüfbar** · gebaut von einer Person mit KI-Assistenz,
lokal-first, ohne Cloud-Abhängigkeit im Kern.

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

1. [`docs/12_GESAMTVERSTAENDNIS.md`](docs/12_GESAMTVERSTAENDNIS.md) — das Ganze ohne Vorwissen.
2. [`docs/01_GRUNDGESETZE.md`](docs/01_GRUNDGESETZE.md) — die geschriebenen Gesetze.
3. [`docs/README.md`](docs/README.md) — der Index aller netzweiten Normen und Verträge.

Die interaktive System-Karte steht auf der Website: <https://worldofdizzi.netlify.app/karte/>
