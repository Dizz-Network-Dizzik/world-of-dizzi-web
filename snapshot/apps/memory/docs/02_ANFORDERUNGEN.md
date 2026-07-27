# Anforderungsliste — Dizz Knowledge — Archiv

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss) — Stand 14.06.2026
- [x] Notiz-/Archiv-Modell (**Markdown-Vault** kanonisch + SQLite-Index) + **FTS5-Volltextsuche**
- [x] **RAG/Vektor-Index L3** (`rag.py`, sqlite-vec + Ollama **bge-m3** 1024-dim) — semantische Suche,
      identischer Stack wie Core-L3 (kein Duplikat); `/api/suche/semantisch`, Retrieval semantisch-zuerst
- [x] Ordner (hierarchisch) + **Labels** (Cross-Verweise) — KI-gestützt strukturierbar
- [x] Brücke zu Dizzi-Memory: App-KI (Mini-Dizzi-Slot) quellen-gestützt; L3-RAG-Verbund-Andockpunkt
      dokumentiert (`rag.py`, denselben Vault mit-indexieren / `memory_suche`-MCP = nächster Schritt)
- [x] **Import**: Markdown/Mem-Frontmatter + **lokaler Ordner/Mem.ai-Export** (Pfad-Allow-List,
      SHA-256-Dedupe, Ordner-Hierarchie, Mem.ai-Mapping) **+ getaktete Automatik** (opt-in, Env-Ordner)
- [x] **Querverbindungs-Empfang** `/api/querverbindung/archivieren` (andere Apps archivieren Elemente;
      idempotent, auditiert) — Gegenseite/Vertrag = FÜR WORLD-CHAT
- [x] Stats-Endpoint: Notizen/Ordner/Labels/Zuletzt
- [x] MCP-Tools: `memory_letzte_notizen`, `memory_ordner`, `memory_labels`, `memory_kachel_stats`
      (parametrisierte `memory_suche`/`memory_semantisch` = appkit-Erweiterung, FÜR WORLD-CHAT)

## Quer (aus dem App-Vertrag, gilt für alle)
- [x] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [x] MCP-Server (read-only Tools, Namensraum `memory_`)
- [x] Dizzi-ID-Anbindung (SSO-Slot) + lokaler Standalone-Login (`install_dizzi_id`)
- [x] Account/Settings-Modul (Kernpaket K2, generisch aus appkit) — UI-Formular folgt mit K2.4
- [x] Daten user-scoped + sync-ready; sensible Daten lokal (`sensitivity="hoch"`, lokal-first)
- [x] Tests (27 grün, Ollama-frei) + Doku-Sync (Gesetz 9) + `requirements.txt`/`-lock.txt`

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener Kern mit **Markdown-Vault als nativem Speicherformat** (Obsidian-kompatibel, kein
  DB-Lock-in) + RAG-Index (sqlite-vec/bge-m3, Brücke zu Dizzi-L3).
- **v1:** Notiz-/Archiv-Modell + Suche/RAG; **Import aus Mem (mem.ai)** (via MCP bereits verbunden) —
  Struktur nach Nutzer-Vorgaben.
- **Externe Dienste:** Mem-Import; Readwise/Zotero als spätere Importer-Slots.
- **Sensibilität:** privat → lokal.
- **Marke:** Dizz Knowledge (bestätigt).
