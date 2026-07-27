# RAG-Embedding-Modell — Kandidaten & Vorschlag (Dizz Memory, D3)

> **App-Chat-Evaluation (20.06.2026).** Dies ist der **Vorschlag** der Memory-App
> als Eingabe für **W5** (docs/_archiv/36): der World-Chat liefert die finale Empfehlung
> „bestes lokales Embedding-Modell 2026" in `the world of dizzi/docs/_archiv/30` (Anhang).
> Bis dahin bleibt **`bge-m3` Default**; die Embedding-Schicht ist seit D3 **swappbar**
> (Modellname + Dimension als Setting/Env, automatische vec-Tabellen-Migration) und
> das **Re-Index-Werkzeug** steht — der Tausch ist damit ein 1-Zeilen-Wechsel + Re-Index.

## Ausgangslage
RAG-L3 = `sqlite-vec` + Ollama-Embeddings, aktuell **`bge-m3` (1024-dim)**, identisch
zum Core-L3 (Vektorräume kompatibel). Der Vault ist **deutsch + englisch** ⇒ ein
**multilinguales** Modell ist Pflicht; „läuft überall einwandfrei" (bescheidene Hardware)
⇒ Ressourcenbedarf zählt. Bewertungsachsen: Qualität (Retrieval) · Multilingualität ·
Dimension (↔ Migrationsaufwand + Speicher) · RAM/Latenz · Lizenz · Ollama-Verfügbarkeit.

## Kandidaten (2026, alle Ollama-fähig)
| Modell | Dim | Multiling. | Profil | Bewertung für Memory |
|---|---|---|---|---|
| **bge-m3** (Baseline) | 1024 | ✅ 100+ | 8K-Ctx, hybrid dense+sparse, ~1.2 GB | Solider multilingualer Baseline-Stand; bleibt sicherer Fallback. |
| **qwen3-embedding:0.6b** | 1024* | ✅ stark | beste multilinguale MTEB-Qualität 2026 (dt./frz. top), Matryoshka | **Primärer Upgrade-Kandidat** — **dim-gleich (1024) ⇒ Tausch OHNE Dim-Migration**, nur Re-Index. Qualitätssprung bei ~gleichem Footprint-Rang. |
| **embeddinggemma** (~300M) | 768 | ✅ | Google, sehr leicht/effizient, Matryoshka (768→512/256/128) | **„Läuft-überall"-Alternative** (geringster Ressourcenbedarf); exerziert den Dim-Migrationspfad (768). |
| snowflake-arctic-embed2 | 1024 | ✅ | retrieval-stark (BEIR) | dim-gleich; starke Alternative falls reine Retrieval-Qualität zählt. |
| mxbai-embed-large | 1024 | ⚠️ en-first | Genauigkeit (English) | für dt. Vault NICHT erste Wahl. |
| nomic-embed-text | 768 | ⚠️ en-lastig | klein/schnell, sehr verbreitet | leicht, aber englisch-lastig ⇒ für dt. Notizen zweite Wahl. |

\* Qwen3-Embedding nutzt Matryoshka; die 0.6B-Variante liefert per Default **1024** Dimensionen
(in `EMBED_MODELLE` registriert). Bei abweichender Konfiguration greift die Auto-Dimensions-Probe.

## Vorschlag (vorbehaltlich W5)
1. **Primär: `qwen3-embedding:0.6b`** — beste multilinguale Qualität 2026 und **1024-dim wie bge-m3**,
   d. h. der Tausch braucht **keine** Dimensions-Migration, nur einen Re-Index. Bestes Verhältnis
   Leistung↔Aufwand für unseren deutsch/englischen Vault.
2. **Ressourcen-schonend: `embeddinggemma`** — wenn „muss auf schwacher Hardware laufen" dominiert
   (768-dim, sehr klein); guter Test des Dim-Migrationspfads.
3. **Fallback/Baseline: `bge-m3`** bleibt, bis die A/B-Messung einen Gewinner bestätigt.

## A/B-RAG-Qualität — Status
Ehrlich: ein echter A/B-Vergleich (bge-m3 ↔ Kandidat) braucht ein **erreichbares Ollama mit dem
jeweiligen Modell**; im Dev-Env war Ollama **nicht erreichbar** (Embedder-Probe negativ). Der A/B
gehört daher in den **gegateten Lauf** (Ollama + echter Vault vorhanden): pro Modell `ollama pull`,
`embed_modell` setzen, `python -m archivapp.reindex`, dann dieselben Such-/Frage-Anfragen
gegenüberstellen (Treffer-Relevanz, Score-Trennschärfe). **Werkzeug + Migration stehen bereit.**

## So wird getauscht (1-Zeilen-Wechsel)
1. `ollama pull <modell>` (z. B. `qwen3-embedding:0.6b`).
2. Modell setzen — **Env** `DIZZ_MEMORY_EMBED_MODELL=<modell>` ODER **Setting** `embed_modell` (KI-Kategorie).
3. (gegateter) Neustart: die vec-Tabelle migriert automatisch bei Dim-Wechsel (Chunks werden verworfen).
4. Re-Index: `python -m archivapp.reindex` **oder** `POST /api/rag/reindex` (Fortschritt/Abbruch via API).

## Quellen (2026)
- [Best Ollama Embedding Models 2026 (MTEB/VRAM/Dim) — morphllm](https://www.morphllm.com/ollama-embedding-models)
- [Embedding Models 2026: Benchmark & Comparison — Ailog](https://app.ailog.fr/en/blog/news/embedding-models-2026)
- [bge-m3 — Ollama Library](https://ollama.com/library/bge-m3)
