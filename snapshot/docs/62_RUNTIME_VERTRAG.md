# 62 · LocalRuntime-VERTRAG — Bau-Spec für Bau-KI C1–C11 (Z1.1/FP-3)

> **Status: FERTIG designt (FP-3, Architektur-KI, 03.07.2026, Worktree `chat/runtime`).** Dies ist der
> Interface-VERTRAG (docs/52 E1.1–E1.3, VO-10) — **kein Umbau erfolgt**. Verträge-als-Code liegen als
> Stubs: `packages/appkit/runtime.py` +
> `packages/appkit/modellprofil.py` (+ Vertrags-Tests, Ollama-frei).
> **Bau-KI baut danach C1–C11 (docs/53 §5)** — dieses Dokument beantwortet jede Baufrage vorab; die
> Docstrings der Stubs sind normativ. Budget-Rahmen: docs/58 §5.1 · Zünd-Prompt: docs/59 §A FP-3.

## §0 · Geltung + die 4 (nicht 3) hartverdrahteten Stellen

docs/52 §2 nennt 3 Stellen — **verifiziert sind es 4** (Gesetz 2, Korrektur):

| # | Stelle | Ollama-Pfad heute | Ziel-Naht |
|---|---|---|---|
| 1 | `apps/core/app/ai/providers.py` | `/v1/chat/completions` (Kette) · `/api/chat`+format (quick_chat) · `/api/tags` (status) | `chat_stream` · `a_strukturiert`/`a_chat` · `modelle`+`health` |
| 2 | `apps/core/app/ai/agent.py` | `/api/chat` natives Tool-Streaming | `chat_stream` |
| 3 | `packages/appkit/ollama.py` | `/api/chat`+format, sync, injizierbares `http_post` | `strukturiert` |
| 4 | **`apps/core/app/ai/rag.py`** (in docs/52 fehlend) | `/api/embed`, async | `a_embed` |

Dazu App-seitig: `archivapp/rag.py::ollama_embed` (sync, bereits über `embed_fn` injizierbar — Migration
ist dort nur ein Einstiegs-Tausch in `main.app_factory`, kein Strukturbruch).

**ENV-Split (Stolperfalle, bleibt erhalten):** core nutzt `DIZZI_OLLAMA_URL`, appkit+memory `DIZZ_OLLAMA_URL`.
Vertrag: `OllamaRuntime(url=None)` liest den appkit-Kanon (`DIZZ_OLLAMA_URL` → `127.0.0.1:11434`); **core
konstruiert seine Instanz explizit mit `url=providers.OLLAMA_URL`** ⇒ beide Env-Namen wirken weiter, kein
stiller Konfigurationsbruch.

## §1 · Der Vertrag: 5 Methoden (E1.1) — Signaturen + Fehler-Vertrag

Normative Quelle: `appkit/runtime.py` (ABC `LocalRuntime`). Kurzform + Begründungen (je 1 Zeile):

| Methode | Signatur (Kern) | Fehler-Vertrag |
|---|---|---|
| `strukturiert` | `(system, nutzer, *, schema: type[M], modell: str, temperature=0.0, timeout=90, strikt=False) -> M \| None` | `None` bei JEDEM Fehler, wirft NIE; `strikt=True` reicht Original-Exception durch |
| `chat_stream` | `(messages, *, modell, tools=None, optionen=None, timeout=300) -> AsyncIterator[RuntimeEreignis]` | **WIRFT** bei Transport-/Engine-Fehler (vor wie nach 1. Token) |
| `embed` | `(texts, *, modell, timeout=120) -> list[list[float]] \| None` | leer ⇒ `[]` ohne Call; Fehler ⇒ `None`, wirft NIE; **roh, KEINE L2-Norm** |
| `modelle` | `() -> list[ModellInfo]` | `[]` bei Fehler, wirft NIE |
| `health` | `() -> RuntimeHealth` | wirft NIE (`ok=False` + ehrliches `detail`), Timeout 3 s |

Dazu **nicht-abstrakte Defaults** (Adapter-Pflicht bleibt exakt 5): `a_strukturiert`/`a_embed`/`a_modelle`/
`a_health` (Zwillinge via `asyncio.to_thread`; Adapter mit `httpx.AsyncClient` überschreiben nativ) und
`a_chat(messages, *, modell, optionen, strikt=False) -> str | None` (= `chat_stream` eingesammelt).

**Entscheidungen (je 1-Zeilen-Begründung):**
- **ABC statt `typing.Protocol`** — trägt die geerbten Async-Defaults + `isinstance` in der Registry; Hausmuster `connectors.ExternalConnector` (docs/53 W1.1 „Protokoll" ist umgangssprachlich gemeint).
- **Sync-Kern + `a_`-Zwillinge** — beide Welten existieren heute real (7 sync-App-Triagen vs. async core); Zwillinge statt Doppel-Interface hält die Pflicht-Fläche bei 5.
- **`chat_stream` nur async** — kein sync-Aufrufer streamt heute; sync-Streaming in FastAPI wäre erfundene Fläche.
- **fail-safe → `None`** (`strukturiert`/`embed`) — exakt der heutige appkit/ollama.py-Vertrag („Wirft NIE"), auf den 7 App-Suiten + rag-Degradierung gebaut sind.
- **`strikt=True` als Opt-in statt zweiter Methodenfamilie** — `providers.quick_chat` WIRFT heute (httpx-Exceptions, Aufrufer fangen breit); Parität ohne Vertragsbruch für alle anderen.
- **`chat_stream` wirft** — ein Stream kann nicht ehrlich zu `None` degradieren; die Failover-Entscheidung („schon Tokens geflossen?" = emitted-Regel) ist Aufrufer-Politik in `providers.stream_chat` und bleibt dort.
- **`modell` = Pflicht-kwarg** — Runtime = Transport, Profil = Politik (§3); Kopplung würde C1 auf C3 warten lassen.
- **Ereignis-Datenmodell statt Roh-Tupel** — `RuntimeEreignis(art='text'|'tool_aufrufe'|'ende')`; `ende.nutzung` = rohe Engine-Zähler ⇒ C5-Observability muss später nichts neu verkabeln.
- **Tool-Aufrufe IMMER komplett** (nie Deltas) — agent.py und jeder künftige Konsument darf nie Delta-Zusammenbau nachbauen; Puffern ist Adapter-Pflicht (§2). `ToolAufruf.argumente` ist IMMER geparstes dict (heutige `_normalize_args`-Logik wandert in den Adapter); `als_ollama()` liefert die Konversations-Echo-Form.
- **Nachrichten-Form-Pin = Ollama-nativ** (`role/content` + `assistant.tool_calls` + `role='tool'` mit `tool_name`) — 0-Verhaltenswechsel heute; Nicht-Ollama-Adapter mappen später (`tool_name`→`tool_call_id`), nicht umgekehrt. Tools-Format = OpenAI-Function (`ToolSpec.payload` unverändert).
- **Adapter dürfen zusätzliche NUR-Keyword-Params mit Defaults ergänzen** (Liskov-sicher) — so überlebt die positional-`http_post(url, daten)`-Fake-Konvention der 7 App-Suiten an `OllamaRuntime.strukturiert(…, http_post=…)`.

**Registry (C2):** `registriere_runtime(name, fabrik)` + `runtime_holen(name) -> LocalRuntime`; `None`/leer/
unbekannt ⇒ `DEFAULT_RUNTIME='ollama'` (fail-safe — kaputtes Setting ändert nie das Verhalten); eine gecachte
Instanz je Name; Setting-Lesen bleibt beim Aufrufer (core liest `runtime` aus SEINER DB — appkit kennt keine
core-Settings). Im Stub wirft `runtime_holen` ehrlich `LookupError`, bis C1 `ollama` registriert.

## §2 · Capability-Flags + Adapter-Mapping (Ollama · vLLM · llama.cpp)

**Zwei Ebenen, bewusst getrennt** (die docs blurren das): `RuntimeFaehigkeiten` = statisch je ADAPTER-Klasse
(cd-Dialekt, Tool-Streaming-Quelle, Kontext-STEUERBARKEIT); `modellprofil.ModellFaehigkeiten` = je MODELL
(kontext_max, tools, cd, mehrsprachig, dim). **Effektiver Kontext = min(Modell, Runtime-Konfiguration)** —
Komposition macht der Aufrufer. Begründung: „Kontextlänge" ist beides — das Modell hat ein Maximum, die
Runtime deckelt (Ollama `num_ctx` per Request steuerbar; vLLM `max_model_len` server-fix).

| Fähigkeit | **OllamaRuntime (C1)** | VllmRuntime (Z1.3, später) | LlamaCppRuntime (Z1.3, später) |
|---|---|---|---|
| constrained decoding | `/api/chat` `format`=JSON-Schema — **$ref + Wurzel-Array-fähig** (intern Schema→Grammatik) | `/v1/chat/completions` + `guided_json` in `extra_body` (XGrammar-Default seit ~03/2026); **strikte `response_format`-json_schema-Variante MEIDEN** (Wurzel-Array/$ref-Grenzen) | `grammar`=**GBNF** bzw. `json_schema`-Feld (Server konvertiert Schema→GBNF); $ref löst der Konverter auf |
| `cd_dialekt` / `$ref` / Wurzel-Array | `json_schema` / ✓ / ✓ | `guided_json` / ✓ / ✓ (via guided_json, nicht response_format) | `gbnf` / ✓ (konvertiert) / ✓ |
| Tool-Streaming-Quelle | **`komplett`** — native vollständige `message.tool_calls` im NDJSON-Stream | **`deltas`** — OpenAI-Stil, index-fragmentierte Argument-Chunks ⇒ **Adapter puffert bis komplett** | versionsabhängig ⇒ Adapter puffert defensiv |
| Chat-Transport | `/api/chat`, NDJSON (eine Zeile = ein JSON-Objekt) | `/v1/chat/completions`, SSE (`data:`-Zeilen) | `/v1`-kompatibel SSE |
| embed | `/api/embed` `{model, input:[…]}` (Batch) | `/v1/embeddings` (OpenAI-Form) | `/v1/embeddings` bzw. `/embedding` |
| modelle | `/api/tags` (Name + **size** + Details — speist E1.3-VRAM-Wahl) | `/v1/models` (nur IDs) | `/v1/models` (das geladene Modell) |
| health | `GET /api/version`, 3 s | `GET /health` | `GET /health` |
| Kontext | `kontext_steuerbar=True` (`options.num_ctx` je Request) | server-fix (`max_model_len`) | server-fix (`-c`) |
| batching | `einzeln` | `kontinuierlich` (continuous batching) | `einzeln` |

**Normalisierungs-REGEL (der Kern gegen das Abstraktions-Leck aus docs/52 §2-Risiken):** Was auch immer die
Engine roh liefert — am Vertrag kommen NUR `RuntimeEreignis` mit kompletten Tool-Aufrufen an; `optionen` ist
Adapter-Durchreiche (unbekannte Schlüssel werden kommentarlos ignoriert, kein Vertragsbruch).

**OllamaRuntime-Baudetail (C1, damit Bau-KI nicht raten muss):**
```python
class OllamaRuntime(LocalRuntime):
    name = "ollama"
    faehigkeiten = RuntimeFaehigkeiten(
        cd_dialekt="json_schema", cd_ref_faehig=True, cd_wurzel_array=True,
        tool_streaming_quelle="komplett", tools=True, kontext_steuerbar=True,
        embed=True, batching="einzeln")
    def __init__(self, url: str | None = None, *,
                 http_post: Callable | None = None,        # sync-Naht (Fake-Konvention!)
                 zeilen_stream: Callable | None = None): … # async-Naht: (url, payload) -> AsyncIterator[str]
```
- `strukturiert`: Körper BYTE-GLEICH zu `appkit/ollama.strukturiert` heute (`format=schema.model_json_schema()`,
  `options={temperature}`, Validierung `schema.model_validate_json`); `http_post` bleibt POSITIONAL `(url, daten)`
  gerufen + zusätzlich als per-Call-kwarg erlaubt (Fake-Kompatibilität).
- `a_strukturiert`: Override mit `httpx.AsyncClient` — deckt den heutigen `quick_chat`-format-Pfad.
- `chat_stream`: NDJSON-Zeilen aus `zeilen_stream` (Default: `httpx.AsyncClient.stream`, `Timeout(300, connect=8)`
  wie agent.py); Mapping `message.content`→`text`-Events · `message.tool_calls`→`tool_aufrufe` (Argumente durch
  `_normalize_args`-Logik) · `done:true`→`ende` mit `nutzung` = alle rohen Zähler-Felder (`eval_count`,
  `prompt_eval_count`, `total_duration`, `eval_duration`, `load_duration`, …).
- `embed`: `POST /api/embed` — Körper wie `archivapp.rag.ollama_embed`; `modelle`: `GET /api/tags` →
  `ModellInfo(name, groesse_bytes=size, details=rest)`; `health`: `GET /api/version` (3 s).
- `a_chat`: Default (Stream einsammeln) genügt — kein Override nötig.

## §3 · Modell-Profil (E1.2) + Kanal-Verweis (E1.3)

Normative Quelle: `appkit/modellprofil.py`. Task-Klassen = `chat · schnell · embed · rerank · vision · voice`
(„schnell" deckt strukturiert/Triage — die heutige `FAST_LOCAL_MODEL`-Rolle; Apps dürfen weiter EXPLIZITE
Modelle je Aufruf setzen, das Profil ist nur der Netz-Default).

- **Stufe 0 = heutiges Live-Verhalten wertgleich:** chat=`qwen3:14b` · schnell=`qwen3:4b` · embed=`bge-m3`
  (dim 1024 — MUSS `rag.EMBED_MODELLE['bge-m3']` spiegeln); **rerank/vision/voice = dormant** (fehlender Slot;
  ehrlich: heute ist kein Default-Reranker verdrahtet — memory injiziert `rerank_fn` optional, Default `None`).
- **Präzedenz (0-Verhaltenswechsel-Anker für C3): Nutzer-Setting (`ai_model`) > Profil-Slot > alte Konstante.**
  Ein heute gesetztes `ai_model` gewinnt weiter; das Profil ersetzt nur die Konstanten als Default-Quelle.
- **Kanal (E1.3):** `STUFEN` = kuratierte Release-Liste; wächst NUR per appkit-Release („durch Nachrichten
  freigegeben"), nie zur Laufzeit. `aufloese_stufe(vram, stufen, pin)` = pure/deterministisch: Pin (Setting
  `modell_profil_stufe`) gewinnt nur unter FREIGEGEBENEN Stufen (Release-Gate ist nicht per Setting umgehbar);
  sonst höchste freigegebene Stufe mit `vram_min_bytes <= vram`; `vram=None` ⇒ Boden. Stufe 0 (`vram_min=0`,
  freigegeben) ist der unbedingte Boden — `vram_probe()` (Stub → `None`; echt ab C4) darf nie werfen.
- **Re-Index-Disziplin (VEC_SCHEMA):** `profil_wechsel_folgen(alt, neu)` ⇒ `reindex_noetig`, sobald der
  embed-Slot sich in Modell ODER dim ändert (auch erscheint/verschwindet). Ein solcher Stufen-Wechsel wird
  **NIE still angewendet** — das Verwerfen erledigt `rag._migriere_modellwechsel` selbst, aber der teure
  Re-Index-LAUF bleibt nutzer-gegated (wie Neustarts). Betrifft core-L3 UND memory-RAG (gleiche bge-m3-Räume).

## §4 · Migrations-Reihenfolge (additiv, 0 Verhaltenswechsel) + Test-Strategie je Schritt

> Feiner als docs/53 (C1 → fünf Teil-Commits a–e): jeder Schritt einzeln grün + rollbackfähig — kompatibel
> mit „commit-große Schnitte" (docs/53 §0), senkt nur Risiko. **Kein Live-Neustart nötig** (alles Code-Pfad,
> Deployment bleibt gegated wie immer).

| Schritt | = | Inhalt | Test-Strategie (Akzeptanz) |
|---|---|---|---|
| **M1 ✅** | FP-3 | Vertrag + Stubs (`runtime.py`, `modellprofil.py`) — niemand ruft sie | Vertrags-Tests (dieser Commit); Bestands-Suiten unberührt |
| **M2** | C1a | `OllamaRuntime` in `runtime.py` + `registriere_runtime("ollama", …)` — **niemand ruft ihn** | NEUE Adapter-Tests gegen Fakes (`http_post`-Fake sync; `zeilen_stream`-Fake = Liste NDJSON-Zeilen): strukturiert-Parität zu `test_ollama.py`-Fällen · chat_stream-Mapping (text/tool_aufrufe/ende, kaputte Argumente ⇒ `{}`) · embed leer/Fehler · health-Fehlerpfad. appkit-Suite grün |
| **M3** | C1b | `appkit/ollama.strukturiert` → delegiert an `OllamaRuntime.strukturiert` (Modul-Funktion = eingefrorener Shim; Signatur + positional-`http_post`-Konvention UNVERÄNDERT) | appkit-Suite (`test_ollama.py` UNVERÄNDERT grün — das ist der Paritäts-Beweis) + **alle 7 App-Suiten unverändert grün** (deren Fakes sind der eigentliche Vertrag) |
| **M4** | C1c | core `agent.py`: `_ollama_chat_stream` raus, `stream_agent(…, runtime: LocalRuntime \| None = None)` (None ⇒ `runtime_holen()`); Events→bestehende `("t",…)`/`("tool",…)`-Tupel; convo-Echo via `ToolAufruf.als_ollama()` | **Test-Naht wandert (einzige ehrliche Naht-Änderung):** `test_tools_agent.py` monkeypatcht heute `agent._ollama_chat_stream` (6 Stellen) → wird mechanisch zu FakeRuntime-Injektion (gleiche Konserven-Events ⇒ gleiche Tupel/Runden/MAX_ROUNDS). Verhalten identisch, core-Suite grün |
| **M5** | C1d | core `providers.py`: `quick_chat` → `a_strukturiert(strikt=True)` (format-Pfad) / `a_chat(strikt=True)` (ohne Schema — wirft weiter wie heute); `status()` → `health()`+`modelle()` (Feld-Mapping: `ollama_ok=h.ok`, `models=[m.name …]`, Rest identisch); `stream_chat`-**lokal-Bein** → `chat_stream` (Boost-Kette bleibt unverändert `/v1`-httpx!) | Bestands-Tests, die `providers.quick_chat` monkeypatchen, bleiben UNVERÄNDERT grün (Naht = Signatur). Lokal-Bein: Paritäts-Test gleiche Fake-Zeilen ⇒ gleiche `(id, chunk)`-Folge; emitted-Regel-Test bleibt. Transport-Wechsel `/v1`→`/api/chat` ist token-identisch (beide nutzen Modelfile-Defaults) — Restrisiko benannt, durch Paritäts-Fake gedeckt |
| **M6** | C1e | core `rag.py` (4. Stelle): `/api/embed`-httpx → `a_embed`; **memory optional:** `use_ollama`-Zweig in `archivapp/main.py` tauscht `ollama_embed` gegen `runtime.embed`-partial (embed_fn-Injektion bleibt!) | core-Suite; memory-Suite (RAG-Tests bleiben Ollama-frei, da embed_fn-Injektion unangetastet) |
| **M7** | C2 | core liest Setting `runtime` (`db.setting_get`, Default `"ollama"`) und reicht ihn an `runtime_holen` | Default-Pfad == heutiges Verhalten; Setting unbekannt/leer ⇒ Ollama (fail-safe-Test) |
| **M8** | C3 | `modellprofil` verdrahten: `providers.local_model` = Setting > `STUFE_0.modell_fuer("chat")` > Konstante; `FAST_LOCAL_MODEL`-Nutzer → `modell_fuer("schnell")`; rag-Default bleibt (Stufe-0 == bge-m3, kein Drift) | Paritäts-Pins App-seitig: Profil-Werte == `providers.DEFAULT_LOCAL_MODEL`/`FAST_LOCAL_MODEL`/`rag.EMBED_MODELL` (Import-Seite Apps); Setting-Präzedenz-Test |
| **M9** | C4 | `vram_probe()` echt (fail-safe) + Kanal-Auflösung in Status/Settings + Re-Index-Gate-Hinweis bei `reindex_noetig` | Probe wirft nie (Fehler ⇒ None ⇒ Stufe 0); Kanal deterministisch (Fixture-Stufen); Gate-Hinweis erscheint, KEIN Auto-Lauf |

C5–C11 (observ/Budget/Outbound/Sampling-Slot/Kontext/Voice/Tauri) bauen auf diesem Vertrag, ändern ihn nicht:
C5 hängt Spans an `runtime`-Calls + `ende.nutzung`; C7 bleibt in `providers` (Kette = Politik, §6); C10 füllt
die dormanten Profil-Slots `vision`/`voice`.

## §5 · LiteLLM-Abgrenzung (docs/52 §15-K2) — **BESTÄTIGT, keine Revision**

1. **Constrained decoding:** `appkit/ollama.strukturiert` + `quick_chat(format=)` nutzen Ollamas NATIVEN
   `/api/chat`-`format`-Slot, weil die OpenAI-`response_format`-Schiene $ref/Wurzel-Array NICHT trägt —
   im Code verifiziert (providers.py-Docstring, Z. 166–172). LiteLLM routet durch die OpenAI-Kompat-Fläche;
   die Fähigkeit bliebe nur über provider-spezifische Durchgriffe erhalten = Abstraktion ohne Gewinn.
2. **Tool-Call-Streaming:** agent.py-Docstring (Recherche Welle 6, im Code): Ollamas `/v1`-Pfad streamt
   Tool-Deltas nicht zuverlässig — der Vertrag braucht den nativen NDJSON-Pfad, den LiteLLM nicht spricht.
3. **Dependency-Fläche (F-Q1, docs/18):** LiteLLM = schweres Paket (Router/Proxy/140+ Provider) gegen
   unsere Eigenbau-Fläche von exakt 5 Methoden + 1 Adapter.
4. **Rollenklarheit:** Die Provider-KETTE (Boost/Outbound/CB/Failover) ist UNSERE Politik in `providers.py`
   und bleibt dort (§6) — genau die Schicht, die LiteLLM ersetzen wollen würde.

**Unverändert gültig:** LiteLLM bleibt Z1.3-Kandidat **als EIN Adapter HINTER dem Vertrag** (`LiteLlmRuntime`
für Server-/Multi-Provider-Szenarien) — nie als Ersatz des Vertrags.

## §6 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

- **Provider-Kette/Boost/Outbound/Circuit-Breaker** — Politik in `providers.py` (LocalRuntime = nur der lokale Boden; C7 erweitert die Kette, nicht den Vertrag).
- **L2-Normalisierung/Chunking/RRF** — Index-Politik in `rag.py` (VEC_SCHEMA-Disziplin), nicht Transport.
- **Modell-Wahl/Profil-Auflösung** — `modellprofil` (Politik), Runtime bekommt `modell` immer explizit.
- **`message.thinking`** (qwen3-Denkmodus) — heute ungenutzt (agent liest nur `content`); Erweiterungs-Slot: neues `art='denken'`-Ereignis wäre additiv, JETZT nicht bauen.
- **Sync-`chat`** — kein sync-Aufrufer braucht unären Chat; Fläche klein halten.
- **Setting-Zugriff in appkit** — Namen/Settings liest der Aufrufer (core-DB bleibt core).

## §7 · Akzeptanz-Checkliste je Bau-KI-Commit

- [ ] Jeder M-Schritt: **alle betroffenen Suiten grün** (`PYTHONPATH=packages`, venv-pytest) + kein Verhaltens-Diff (Paritäts-Tests wie §4).
- [ ] M3: `test_ollama.py` + 7 App-Suiten laufen UNVERÄNDERT (Dateien nicht angefasst) grün.
- [ ] M4: `test_tools_agent.py`-Umbau ist rein mechanisch (gleiche Konserven ⇒ gleiche Events); `stream_agent`-Signatur nur um optionalen `runtime`-Param erweitert.
- [ ] M5: `quick_chat`/`stream_chat`/`status` Signaturen UNVERÄNDERT (Monkeypatch-Nähte der Bestands-Tests intakt).
- [ ] Kein `git push`; Merge→master gebündelt + gegated (docs/50-Go-Live-Muster); Trading unberührt.
- [ ] Doku-Sync nach Abschluss: docs/53 §6 + docs/52 §2-LÜCKE (3→4 Stellen) nachziehen.
