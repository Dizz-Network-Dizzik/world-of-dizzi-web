"""LocalRuntime — Vertrag der lokalen KI-Runtime (Z1.1/E1.1, docs/62 = Bau-Spec).

**Status: VERTRAG (FP-3, Architektur-KI 02–03.07.).** Diese Datei definiert das Interface +
die Datenmodelle; der erste Adapter (``OllamaRuntime``) kommt mit Commit C1
(docs/53), gebaut von Bau-KI nach docs/62. Bis dahin ruft NIEMAND dieses Modul im
Produktiv-Pfad — rein additiv, 0 Verhaltenswechsel.

WARUM: Ollama ist heute an 4 Stellen hartverdrahtet (core ``providers.py`` ·
``agent.py`` · ``rag.py`` + appkit ``ollama.py``). EIN Vertrag macht die Runtime
zum Stecker (vLLM/llama.cpp-server später, Z1.3) — wie ``connectors.py`` externe
Quellen zu Steckern macht. Bewusst EIGENBAU statt LiteLLM (docs/52 §15-K2): die
nativen Ollama-Pfade (constrained-decoding-``format``-Slot mit $ref/Wurzel-Array,
komplette tool_calls im Stream) trägt der OpenAI-Kompat-Layer nicht zuverlässig,
und die Dependency-Fläche bleibt klein (F-Q1).

Die 5 Vertrags-Methoden (E1.1): ``strukturiert · chat_stream · embed · modelle ·
health``. Dazu Async-Zwillinge (``a_*``) mit ehrlichen Defaults (``to_thread``)
und ``a_chat`` als Nicht-abstrakte Convenience — die Adapter-Pflicht-Fläche
bleibt 5 Methoden.

Fehler-Vertrag (fail-safe wie heute, appkit/ollama.py-Linie):
- ``strukturiert``/``embed`` → ``None`` bei JEDEM Fehler (wirft NIE; ``strikt=True``
  opt-in reicht die Original-Exception durch — für quick_chat-Parität).
- ``modelle`` → ``[]`` bei Fehler (wirft NIE). ``health`` → ``ok=False`` (wirft NIE).
- ``chat_stream`` WIRFT bei Transportfehlern: ein Stream kann nicht ehrlich zu
  ``None`` degradieren, und die Failover-Entscheidung (»schon Tokens geflossen?«)
  gehört dem Aufrufer (providers-Kette, emitted-Regel) — nicht dem Adapter.
"""

from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, ClassVar, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)

# Task-agnostische Vertrags-Defaults (heutige Live-Werte der 4 Stellen):
TIMEOUT_STRUKTURIERT_S = 90.0   # appkit/ollama.py (erster Lauf lädt Modell in VRAM)
TIMEOUT_EMBED_S = 120.0         # rag.ollama_embed (beide rag.py)
TIMEOUT_STREAM_S = 300.0        # agent._ollama_chat_stream (Werkzeug-Runden)
TIMEOUT_HEALTH_S = 3.0          # providers.status (Health darf nie blockieren)


# --- Ereignis-Datenmodell (chat_stream) ---------------------------------------

@dataclass(frozen=True)
class ToolAufruf:
    """EIN kompletter Tool-Aufruf. ``argumente`` ist IMMER ein geparstes dict —
    das heutige ``agent._normalize_args`` (Roh-String → dict, kaputt → {})
    wandert in den Adapter. ``id`` = Provider-Call-ID falls vorhanden (Ollama:
    leer; OpenAI-Kompat-Engines liefern eine)."""
    name: str
    argumente: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def als_ollama(self) -> dict[str, Any]:
        """Rückform fürs Konversations-Echo (assistant.tool_calls) — exakt die
        Gestalt, die Ollama /api/chat versteht und agent.py heute anhängt."""
        return {"function": {"name": self.name, "arguments": self.argumente}}


@dataclass(frozen=True)
class RuntimeEreignis:
    """Neutrales Stream-Ereignis — die EINE Form, auf die jeder Adapter sein
    natives Streaming mappt (Ollama NDJSON · vLLM SSE-Deltas · llama.cpp).

    - ``art='text'``: ein Antwort-Token/-Chunk in ``text``.
    - ``art='tool_aufrufe'``: KOMPLETTE Aufrufe in ``tool_aufrufe`` — NIE Deltas.
      Engines, die Tool-Argumente fragmentiert streamen (OpenAI-Delta-Stil),
      puffern ADAPTER-INTERN bis zur Vollständigkeit. Kein Konsument (agent.py!)
      soll je Delta-Zusammenbau nachbauen müssen.
    - ``art='ende'``: Abschluss; ``nutzung`` = rohe Engine-Zähler (Ollama:
      eval_count/prompt_eval_count/…) — der Anker für Observability (C5),
      damit Token/Kosten nicht später neu verkabelt werden müssen."""
    art: str                                        # 'text' | 'tool_aufrufe' | 'ende'
    text: str = ""
    tool_aufrufe: tuple[ToolAufruf, ...] = ()
    nutzung: dict[str, Any] | None = None


# --- Selbstauskunft (modelle/health/Fähigkeiten) -------------------------------

@dataclass(frozen=True)
class ModellInfo:
    """Ein bei der Runtime verfügbares Modell. ``groesse_bytes`` speist die
    hardware-bewusste Kanal-Wahl (E1.3/C4, VRAM-Passung); ``details`` = roh
    (Ollama /api/tags: family/quant/…), damit nichts verloren geht."""
    name: str
    groesse_bytes: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeHealth:
    """Liveness-Auskunft — dynamisch (Fähigkeiten sind STATISCH deklariert, s.
    ``RuntimeFaehigkeiten``). ``detail`` ist ehrlich (»connect refused«), nie
    geraten. Timeout klein (``TIMEOUT_HEALTH_S``) — Health-Watch darf nie hängen."""
    ok: bool
    laufzeit: str = ""              # Registry-Name des Adapters ('ollama', …)
    url: str = ""
    version: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class RuntimeFaehigkeiten:
    """Statische Capability-Flags der ADAPTER-KLASSE (nicht des Modells! Modell-
    Fähigkeiten wie kontext_max/tools/dim stehen im Modell-Profil,
    ``modellprofil.ModellFaehigkeiten``). Effektiver Kontext = min(Modell,
    Runtime-Konfiguration) — die Komposition macht der Aufrufer.

    ``cd_dialekt``: WIE der Adapter constrained decoding nativ erzwingt —
    'json_schema' (Ollama /api/chat-format) · 'guided_json' (vLLM) · 'gbnf'
    (llama.cpp) · 'keins'. Die Mapping-Tabelle je Adapter: docs/62 §2.
    ``tool_streaming_quelle``: was die ENGINE roh liefert ('komplett' |
    'deltas' | 'keins') — der VERTRAG liefert nach außen IMMER komplette
    Aufrufe; 'deltas' heißt nur: der Adapter puffert intern."""
    cd_dialekt: str = "keins"
    cd_ref_faehig: bool = False          # $ref im Schema ok?
    cd_wurzel_array: bool = False        # Wurzel-Array ok? (OpenAI-strict: nein)
    tool_streaming_quelle: str = "keins"
    tools: bool = False
    kontext_steuerbar: bool = False      # per Request steuerbar (num_ctx) vs. Server-fix
    embed: bool = False
    batching: str = "einzeln"            # 'einzeln' | 'kontinuierlich' (vLLM)


# --- Der Vertrag ---------------------------------------------------------------

class LocalRuntime(ABC):
    """Vertrag der lokalen KI-Runtime — 5 Pflicht-Methoden (E1.1), Rest sind
    Defaults. ABC statt typing.Protocol, weil die Async-Zwillinge als geerbte
    Defaults mitkommen und die Registry ``isinstance`` prüfen kann
    (Hausmuster ``connectors.ExternalConnector``).

    Adapter-Regeln:
    - ``name``/``faehigkeiten`` als Klassen-Attribute deklarieren (ehrlich).
    - Vertrags-Signaturen sind FIX; Adapter DÜRFEN zusätzliche nur-Keyword-
      Parameter mit Defaults ergänzen (Liskov-sicher) — so überlebt die
      positional-``http_post(url, daten)``-Fake-Konvention der 7 App-Suiten
      als ``OllamaRuntime.strukturiert(…, http_post=…)``.
    - ``modell`` ist PFLICHT-Argument: Runtime = Transport (WIE spreche ich
      mit der Engine), Profil = Politik (WELCHES Modell für welchen Task,
      ``modellprofil``) — die Entkopplung hält C1 unabhängig von C3.
    - Nachrichten-Form = die heutige Ollama-native Gestalt (``role``/``content``
      + ``assistant.tool_calls`` + ``role='tool'`` mit ``tool_name``); Nicht-
      Ollama-Adapter mappen (z. B. tool_name → tool_call_id). Tools = OpenAI-
      Function-Format (``{"type":"function","function":{…}}`` — exakt
      ``tools.ToolSpec.payload`` heute).
    """

    name: ClassVar[str] = "runtime"
    faehigkeiten: ClassVar[RuntimeFaehigkeiten] = RuntimeFaehigkeiten()

    # --- 1/5: strukturiert ----------------------------------------------------
    @abstractmethod
    def strukturiert(self, system: str, nutzer: str, *, schema: type[M],
                     modell: str, temperature: float = 0.0,
                     timeout: float = TIMEOUT_STRUKTURIERT_S,
                     strikt: bool = False) -> M | None:
        """Struktur-erzwungener Chat: Antwort MUSS ``schema`` (Pydantic-Modell)
        erfüllen — erzwungen über den NATIVEN constrained-decoding-Weg des
        Adapters (``faehigkeiten.cd_dialekt``), validiert über DASSELBE Modell
        (``schema.model_validate_json``).

        Fehler-Vertrag: Engine weg / HTTP≠200 / Antwort schema-ungültig ⇒
        ``None`` — wirft NIE (Aufrufer degradieren auf ihren ehrlichen
        Fallback, wie die 7 App-Triagen heute). ``strikt=True`` reicht die
        Original-Exception durch (Parität für Aufrufer, die heute werfen,
        z. B. ``providers.quick_chat``)."""

    # --- 2/5: chat_stream -------------------------------------------------------
    @abstractmethod
    def chat_stream(self, messages: list[dict], *, modell: str,
                    tools: list[dict] | None = None,
                    optionen: dict[str, Any] | None = None,
                    timeout: float = TIMEOUT_STREAM_S,
                    ) -> AsyncIterator[RuntimeEreignis]:
        """Streamender Chat, optional mit Tools — liefert ``RuntimeEreignis``
        (Reihenfolge: 0..n ``text``/``tool_aufrufe``, dann genau ein ``ende``).
        Reguläre Methode, die einen AsyncIterator ZURÜCKGIBT (async-Generator-
        Funktion erfüllt das; Aufruf ohne ``await``, Konsum per ``async for``).

        Tool-Aufrufe kommen IMMER komplett (nie Deltas — Adapter puffern);
        ``ende.nutzung`` trägt die rohen Engine-Zähler. ``optionen`` = Adapter-
        Durchreiche (Ollama: ``options`` wie num_ctx/temperature); unbekannte
        Schlüssel ignoriert ein Adapter kommentarlos (kein Vertragsbruch).

        Fehler-Vertrag: WIRFT bei Transport-/Engine-Fehlern (vor wie nach dem
        ersten Token) — die Failover-/Abbruch-Entscheidung (emitted-Regel)
        liegt beim Aufrufer, wie heute in ``providers.stream_chat``."""

    # --- 3/5: embed -------------------------------------------------------------
    @abstractmethod
    def embed(self, texts: list[str], *, modell: str,
              timeout: float = TIMEOUT_EMBED_S) -> list[list[float]] | None:
        """Embeddings für ``texts`` (Reihenfolge erhalten, eine Liste je Text).
        ROHE Vektoren — KEINE L2-Normalisierung: die ist Index-Politik und
        bleibt in ``rag.py`` (VEC_SCHEMA-u2-Disziplin), nicht im Transport.

        Fehler-Vertrag: leere Eingabe ⇒ ``[]`` ohne Netz-Call; Engine-Fehler ⇒
        ``None`` — wirft NIE. (``rag._embed`` behandelt ``None`` bereits wie
        heute eine Exception: Degradierung auf FTS.)"""

    # --- 4/5: modelle -----------------------------------------------------------
    @abstractmethod
    def modelle(self) -> list[ModellInfo]:
        """Verfügbare Modelle der Runtime (Ollama /api/tags · vLLM /v1/models).
        Fehler-Vertrag: ``[]`` bei jedem Fehler — wirft NIE (der ok-Status
        gehört ``health()``, nicht hierher)."""

    # --- 5/5: health ------------------------------------------------------------
    @abstractmethod
    def health(self) -> RuntimeHealth:
        """Liveness (kleines Timeout, ``TIMEOUT_HEALTH_S``). Wirft NIE — eine
        nicht erreichbare Engine ist ``ok=False`` + ehrliches ``detail``,
        kein Crash (Health-Watch-Regel)."""

    # --- Async-Zwillinge (Defaults ehrlich via Thread; Adapter mit nativem
    # Async-Client — httpx.AsyncClient — überschreiben sie) ----------------------
    async def a_strukturiert(self, system: str, nutzer: str, *, schema: type[M],
                             modell: str, temperature: float = 0.0,
                             timeout: float = TIMEOUT_STRUKTURIERT_S,
                             strikt: bool = False) -> M | None:
        """Async-Zwilling von ``strukturiert`` (gleicher Fehler-Vertrag)."""
        return await asyncio.to_thread(
            self.strukturiert, system, nutzer, schema=schema, modell=modell,
            temperature=temperature, timeout=timeout, strikt=strikt)

    async def a_embed(self, texts: list[str], *, modell: str,
                      timeout: float = TIMEOUT_EMBED_S) -> list[list[float]] | None:
        """Async-Zwilling von ``embed`` (gleicher Fehler-Vertrag) — Ziel-Naht
        für core ``rag.py`` (die 4. hartverdrahtete Ollama-Stelle)."""
        return await asyncio.to_thread(self.embed, texts, modell=modell, timeout=timeout)

    async def a_modelle(self) -> list[ModellInfo]:
        """Async-Zwilling von ``modelle``."""
        return await asyncio.to_thread(self.modelle)

    async def a_health(self) -> RuntimeHealth:
        """Async-Zwilling von ``health``."""
        return await asyncio.to_thread(self.health)

    async def a_chat(self, messages: list[dict], *, modell: str,
                     optionen: dict[str, Any] | None = None,
                     timeout: float = TIMEOUT_STREAM_S,
                     strikt: bool = False) -> str | None:
        """Unärer Chat (Convenience, NICHT abstrakt): ``chat_stream`` komplett
        eingesammelt — deckt den No-Schema-Pfad von ``providers.quick_chat``,
        ohne die Adapter-Pflicht-Fläche über 5 Methoden zu heben.

        Fehler-Vertrag: ``None`` bei Fehler; ``strikt=True`` reicht durch
        (quick_chat-Parität: der wirft heute)."""
        teile: list[str] = []
        try:
            async for ev in self.chat_stream(messages, modell=modell,
                                             optionen=optionen, timeout=timeout):
                if ev.art == "text":
                    teile.append(ev.text)
        except Exception:
            if strikt:
                raise
            return None
        return "".join(teile)


# --- Registry (C2: Adapter-Auswahl per Setting) ---------------------------------
# Setting-Lesen bleibt beim AUFRUFER (core liest `runtime` aus seiner DB und
# reicht den Namen herein) — appkit kennt keine core-Settings. Fail-safe:
# unbekannt/leer ⇒ DEFAULT_RUNTIME. Eine gecachte Instanz je Name (Adapter sind
# leichtgewichtig/zustandsarm; GIL-atomare dict-Ops, bewusst ohne Lock — eine
# harmlose Doppel-Konstruktion im Rennen wäre folgenlos).

DEFAULT_RUNTIME = "ollama"

_FABRIKEN: dict[str, Callable[[], LocalRuntime]] = {}
_INSTANZEN: dict[str, LocalRuntime] = {}


def registriere_runtime(name: str, fabrik: Callable[[], LocalRuntime]) -> None:
    """Adapter anmelden (C1 registriert 'ollama'; Z1.3 später vllm/llamacpp).
    Re-Registrierung ersetzt Fabrik UND verwirft die gecachte Instanz (Tests)."""
    _FABRIKEN[name] = fabrik
    _INSTANZEN.pop(name, None)


def runtime_holen(name: str | None = None) -> LocalRuntime:
    """Aktiven Adapter holen — fail-safe: ``None``/leer/unbekannt ⇒
    ``DEFAULT_RUNTIME`` (Default-Verhalten ändert sich nie durch ein kaputtes
    Setting). Wirft ``LookupError`` NUR, wenn selbst der Default fehlt —
    im Vertrags-Stub der ehrliche Zustand, bis C1 'ollama' registriert."""
    kandidat = (name or "").strip() or DEFAULT_RUNTIME
    if kandidat not in _FABRIKEN:
        kandidat = DEFAULT_RUNTIME
    if kandidat not in _FABRIKEN:
        raise LookupError(
            f"Keine Runtime registriert (gesucht: {kandidat!r}) — "
            f"OllamaRuntime kommt mit Commit C1 (docs/62 §4 M1).")
    if kandidat not in _INSTANZEN:
        _INSTANZEN[kandidat] = _FABRIKEN[kandidat]()
    return _INSTANZEN[kandidat]


# ==============================================================================
# Ollama-Adapter (C1 / docs/62 §4 M2) — der erste konkrete LocalRuntime.
# ==============================================================================
# Rein additiv: die Klasse erfüllt den Vertrag oben, ändert aber NICHTS am Netz-
# Verhalten — bis M4–M8 die 4 hartverdrahteten Ollama-Stellen (core providers/
# agent/rag + der appkit/ollama-Shim, M3) auf sie umstellen, ruft sie NIEMAND im
# Produktiv-Pfad. Alle I/O-Nähte sind injizierbar (Fakes), damit der Adapter
# Ollama-frei testbar ist und die positional-``http_post(url, daten)``-Konvention
# der 7 App-Suiten 1:1 an ``OllamaRuntime.strukturiert`` überlebt (§0-Liskov).

# appkit-Kanon der Ollama-URL (ENV-Split, docs/62 §0): appkit + memory nutzen
# DIZZ_OLLAMA_URL; core konstruiert seine Instanz explizit mit providers.OLLAMA_URL
# (DIZZI_OLLAMA_URL) — so wirken beide Env-Namen weiter, kein stiller Bruch.
OLLAMA_STANDARD_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")


def _ollama_post(url: str, daten: dict[str, Any], *, timeout: float):
    """Default-Poster: synchroner httpx-Call (Körper wie appkit/ollama.post —
    ``json=daten``). Lazy-Import, damit ``import appkit.runtime`` httpx-frei bleibt
    UND kein Import-Zyklus mit ollama.py (dem Shim ab M3) entsteht."""
    import httpx
    return httpx.post(url, json=daten, timeout=timeout)


def _ollama_get(url: str, *, timeout: float):
    """Default-GETter für modelle/health (Selbstauskunft). Lazy-Import wie oben."""
    import httpx
    return httpx.get(url, timeout=timeout)


def _normalize_args(raw: Any) -> dict[str, Any]:
    """Tool-Argumente → geparstes dict (die heutige ``agent._normalize_args``-
    Logik, per Vertrag in den Adapter gewandert): dict bleibt dict; nicht-leerer
    String wird als JSON geparst; kaputtes/leeres JSON ⇒ ``{}``. So baut kein
    Konsument (agent.py!) je Parse-/Delta-Logik nach."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


class OllamaRuntime(LocalRuntime):
    """LocalRuntime-Adapter für Ollama (native ``/api``-Pfade, docs/62 §2).

    Die 5 Vertrags-Methoden sprechen Ollamas native Endpunkte: ``/api/chat``
    (strukturiert = ``format``-constrained · chat_stream = NDJSON), ``/api/embed``
    (embed), ``/api/tags`` (modelle), ``/api/version`` (health). Die Fehler-
    Verträge sind exakt die des Vertrags oben (strukturiert/embed/modelle/health
    fail-safe → None/[]; chat_stream WIRFT).

    Drei injizierbare I/O-Nähte (Default: httpx; Tests/alternative Clients geben
    Fakes) — je Instanz (``__init__``) und, für die beiden Poster-Methoden, auch
    je Aufruf (``http_post=``/``http_get=`` als Liskov-sichere Extra-kwargs, damit
    die App-Suiten-Fakes an genau der Methode landen). ``http_post`` wird POSITIONAL
    ``(url, daten)`` gerufen — kompatibel mit ALLEN App-Test-Fakes; ``zeilen_stream(
    url, payload) -> AsyncIterator[str]`` liefert die rohen NDJSON-Zeilen (Parsen +
    Mappen macht ``chat_stream``).

    Die Async-Zwillinge (``a_strukturiert``/``a_embed``/``a_modelle``/``a_health``/
    ``a_chat``) bleiben bewusst die geerbten ``to_thread``-Defaults: sie sind
    wertgleich (delegieren an den getesteten Sync-Kern). Native ``httpx.AsyncClient``-
    Overrides gehören zu M5/M6, wo ihre echten async-Konsumenten (core providers/
    rag) sie im Event-Loop pinnen — hier wäre das ungetestete Fläche."""

    name: ClassVar[str] = "ollama"
    faehigkeiten: ClassVar[RuntimeFaehigkeiten] = RuntimeFaehigkeiten(
        cd_dialekt="json_schema", cd_ref_faehig=True, cd_wurzel_array=True,
        tool_streaming_quelle="komplett", tools=True, kontext_steuerbar=True,
        embed=True, batching="einzeln")

    def __init__(self, url: str | None = None, *,
                 http_post: Callable | None = None,
                 http_get: Callable | None = None,
                 zeilen_stream: Callable | None = None) -> None:
        # KEIN rstrip('/') — byte-gleich zu appkit/ollama.py (``f"{url}/api/chat"``);
        # der appkit-Kanon (und core mit providers.OLLAMA_URL) trägt keinen Schrägstrich.
        self.url = url or OLLAMA_STANDARD_URL
        self._http_post = http_post
        self._http_get = http_get
        self._zeilen_stream = zeilen_stream

    # --- 1/5: strukturiert (Körper byte-gleich zu appkit/ollama.strukturiert) --
    def strukturiert(self, system: str, nutzer: str, *, schema: type[M],
                     modell: str, temperature: float = 0.0,
                     timeout: float = TIMEOUT_STRUKTURIERT_S,
                     strikt: bool = False,
                     http_post: Callable | None = None,
                     verlauf: list[dict[str, str]] | None = None,
                     bilder: list[bytes] | None = None) -> M | None:
        # ``verlauf`` / ``bilder`` = Liskov-sichere Adapter-Erweiterungen (nur-
        # Keyword, Default None) wie ``http_post`` (§1) — NICHT im ABC-Vertrag.
        # ``verlauf`` spleißt vorherige Gesprächs-Turns (role/content) ZWISCHEN
        # System- und User-Turn (memory-Vault-Chat, docs/62 P3.1). ``bilder`` hängt
        # base64-Bilder ans ``images``-Feld der User-Message (Ollama-Vision
        # /api/chat, KA-M7 C3 — appkit.vision; NUR Ollama ist heute vision-fähig).
        # Beide Default None ⇒ Payload byte-gleich zu [system, user] — 0 Verhaltens-
        # wechsel für alle anderen Aufrufer (der eingefrorene ollama.py-Shim + die
        # 7 App-Suiten reichen sie nie).
        try:
            poster = (http_post or self._http_post
                      or (lambda u, d: _ollama_post(u, d, timeout=timeout)))
            nutzer_msg: dict[str, Any] = {"role": "user", "content": nutzer}
            if bilder:
                import base64
                nutzer_msg["images"] = [base64.b64encode(b).decode("ascii") for b in bilder]
            r = poster(f"{self.url}/api/chat", {
                "model": modell, "stream": False, "format": schema.model_json_schema(),
                "options": {"temperature": temperature},
                "messages": [{"role": "system", "content": system},
                             *(verlauf or []),
                             nutzer_msg]})
            if getattr(r, "status_code", 0) != 200:
                return None
            return schema.model_validate_json((r.json().get("message") or {}).get("content", ""))
        except Exception:
            if strikt:                       # Opt-in: Original-Exception durchreichen
                raise                        # (quick_chat-Parität, M5) — Default wirft NIE
            return None

    # --- 2/5: chat_stream (NDJSON → RuntimeEreignis) ---------------------------
    async def chat_stream(self, messages: list[dict], *, modell: str,
                          tools: list[dict] | None = None,
                          optionen: dict[str, Any] | None = None,
                          timeout: float = TIMEOUT_STREAM_S,
                          ) -> AsyncIterator[RuntimeEreignis]:
        payload: dict[str, Any] = {"model": modell, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if optionen:
            payload["options"] = optionen
        url = f"{self.url}/api/chat"
        quelle = (self._zeilen_stream(url, payload) if self._zeilen_stream is not None
                  else self._default_zeilen_stream(url, payload, timeout))
        async for line in quelle:
            if not line or not line.strip():
                continue
            obj = json.loads(line)           # kaputte Zeile = Engine-Fehler ⇒ WIRFT (Vertrag)
            msg = obj.get("message") or {}
            chunk = msg.get("content")
            if chunk:
                yield RuntimeEreignis("text", text=chunk)
            roh_calls = msg.get("tool_calls") or []
            if roh_calls:                    # Ollama liefert 'komplett' ⇒ 1 Ereignis/Zeile
                yield RuntimeEreignis("tool_aufrufe", tool_aufrufe=tuple(
                    ToolAufruf(
                        name=(tc.get("function") or {}).get("name", "?"),
                        argumente=_normalize_args((tc.get("function") or {}).get("arguments")),
                        id=str(tc.get("id") or ""))
                    for tc in roh_calls))
            if obj.get("done"):
                # nutzung = ALLE rohen Engine-Felder außer der Nachricht selbst
                # (Zähler + model/created_at/done_reason) — der C5-Observability-
                # Anker; nichts geht verloren, nichts muss später neu verkabelt werden.
                yield RuntimeEreignis(
                    "ende", nutzung={k: v for k, v in obj.items() if k != "message"})
                return

    async def _default_zeilen_stream(self, url: str, payload: dict,
                                     timeout: float) -> AsyncIterator[str]:
        """Default-NDJSON-Transport (Timeout wie agent.py: 300 s, connect 8 s).
        Liefert die rohen Zeilen; leere filtert + geparst wird in ``chat_stream``."""
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8.0)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    yield line

    # --- 3/5: embed (roh, KEINE L2-Norm — Index-Politik bleibt in rag.py) ------
    def embed(self, texts: list[str], *, modell: str,
              timeout: float = TIMEOUT_EMBED_S,
              http_post: Callable | None = None) -> list[list[float]] | None:
        if not texts:
            return []                        # leer ⇒ [] OHNE Netz-Call (Vertrag)
        try:
            poster = (http_post or self._http_post
                      or (lambda u, d: _ollama_post(u, d, timeout=timeout)))
            r = poster(f"{self.url}/api/embed", {"model": modell, "input": texts})
            if getattr(r, "status_code", 0) != 200:
                return None
            return r.json()["embeddings"]
        except Exception:
            return None

    # --- 4/5: modelle (/api/tags → ModellInfo; Fehler ⇒ []) --------------------
    def modelle(self, *, http_get: Callable | None = None) -> list[ModellInfo]:
        try:
            getter = (http_get or self._http_get
                      or (lambda u: _ollama_get(u, timeout=TIMEOUT_HEALTH_S)))
            r = getter(f"{self.url}/api/tags")
            if getattr(r, "status_code", 0) != 200:
                return []
            out: list[ModellInfo] = []
            for m in (r.json().get("models") or []):
                name = m.get("name")
                if not name:
                    continue
                out.append(ModellInfo(
                    name=name, groesse_bytes=m.get("size"),
                    details={k: v for k, v in m.items() if k not in ("name", "size")}))
            return out
        except Exception:
            return []

    # --- 5/5: health (/api/version, kleines Timeout; wirft NIE) ----------------
    def health(self, *, http_get: Callable | None = None) -> RuntimeHealth:
        getter = (http_get or self._http_get
                  or (lambda u: _ollama_get(u, timeout=TIMEOUT_HEALTH_S)))
        try:
            r = getter(f"{self.url}/api/version")
            code = getattr(r, "status_code", 0)
            if code != 200:
                return RuntimeHealth(ok=False, laufzeit=self.name, url=self.url,
                                     detail=f"HTTP {code}")
            try:
                version = (r.json() or {}).get("version")
            except Exception:
                version = None
            return RuntimeHealth(ok=True, laufzeit=self.name, url=self.url, version=version)
        except Exception as e:               # unerreichbar ⇒ ok=False + ehrliches detail
            return RuntimeHealth(ok=False, laufzeit=self.name, url=self.url,
                                 detail=f"{type(e).__name__}: {e}")


# C1/M2: den Ollama-Adapter als Default-Runtime anmelden. Ab hier liefert
# ``runtime_holen()`` eine OllamaRuntime statt des ehrlichen Stub-LookupError —
# aber es RUFT sie noch niemand (die 4 Stellen wandern erst in M4–M8 hierher).
registriere_runtime("ollama", OllamaRuntime)


# ==============================================================================
# OpenAI-kompatible Adapter (Z1.3 / docs/62 §2) — vLLM (+ llama.cpp, Folge-Commit).
# ==============================================================================
# Der zweite Stecker HINTER demselben LocalRuntime-Vertrag. Rein additiv wie
# OllamaRuntime: die Klassen erfüllen den Vertrag oben, ändern aber NICHTS am Netz-
# Verhalten — ``DEFAULT_RUNTIME`` bleibt 'ollama', und bis ein Setting 'vllm' wählt
# UND ein vLLM-Server wirklich deployt ist (Welle 1/3), ruft sie NIEMAND im
# Produktiv-Pfad. Der Wert JETZT: die Runtime-Abstraktion ist damit komplett (der
# Stecker passt), zünd-bereit sobald ein Backend da ist.
#
# EHRLICHE GRENZE (Gesetz 2): ohne laufenden vLLM-Server ist das DESIGN + fake-
# getriebene Tests — exakt wie der Ollama-Adapter (M2), den anfangs auch niemand
# rief. Echtes e2e gegen eine Live-Engine gehört an die Deploy-Uhr, ist KEIN Mangel
# dieses Baus.

# appkit-Kanon der OpenAI-kompat-URLs (ENV-Split analog Ollama, docs/62 §0): eigene
# Ports, weil vLLM/llama.cpp typischerweise getrennt von Ollama laufen. Die echten
# Werte reicht der Aufrufer (core) explizit herein (wie ``providers.OLLAMA_URL`` für
# Ollama), sobald ein Server steht — die Defaults sind nur der lokale Standard.
VLLM_STANDARD_URL = os.environ.get("DIZZ_VLLM_URL", "http://127.0.0.1:8000")
LLAMACPP_STANDARD_URL = os.environ.get("DIZZ_LLAMACPP_URL", "http://127.0.0.1:8080")


def _oai_post(url: str, daten: dict[str, Any], *, timeout: float):
    """Default-Poster (OpenAI-kompat): synchroner httpx-Call, ``json=daten`` —
    Körper-gleich zu ``_ollama_post``. Lazy-Import, damit ``import appkit.runtime``
    httpx-frei bleibt."""
    import httpx
    return httpx.post(url, json=daten, timeout=timeout)


def _oai_get(url: str, *, timeout: float):
    """Default-GETter (OpenAI-kompat) für modelle/health. Lazy-Import wie oben."""
    import httpx
    return httpx.get(url, timeout=timeout)


def _zu_openai_nachrichten(messages: list[dict]) -> list[dict]:
    """Vertrags-Nachrichten (Ollama-nativ) → OpenAI-Chat-Form (docs/62 §1-Pin).

    Der Vertrag pinnt die Ollama-native Gestalt: ``role``/``content`` +
    ``assistant.tool_calls`` als ``{"function": {"name", "arguments": <dict>}}``
    (die ``ToolAufruf.als_ollama()``-Echo-Form) + Tool-Ergebnis als ``role='tool'``
    mit ``tool_name``. OpenAI-kompatible Engines wollen dagegen:
    - ``assistant.tool_calls[i]`` = ``{"id", "type": "function", "function":
      {"name", "arguments": <JSON-STRING>}}`` (Argumente STRING, ``id`` Pflicht),
    - ``role='tool'`` mit ``tool_call_id`` (statt ``tool_name``).

    Die Echo-Form trägt KEINE id ⇒ der Mapper synthetisiert deterministisch je
    Durchlauf ids und korreliert Tool-Ergebnis→Aufruf über den Namen als **FIFO je
    Name** (das erste offene ``suche`` bekommt das erste ``role='tool'``-Ergebnis
    mit ``tool_name='suche'`` …). Das deckt exakt, wie agent.py Ergebnisse anhängt
    (in Aufruf-Reihenfolge) — auch für zwei gleichnamige Parallel-Aufrufe einer
    Runde. Eine bereits gesetzte ``id``/``tool_call_id`` (OpenAI-Form von außen)
    wird respektiert und gewinnt."""
    out: list[dict] = []
    offene_ids: dict[str, list[str]] = {}     # tool_name -> FIFO noch offener call-ids
    zaehler = 0
    for m in messages:
        rolle = m.get("role")
        roh_calls = m.get("tool_calls") if rolle == "assistant" else None
        if roh_calls:
            calls: list[dict] = []
            for tc in roh_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                cid = str(tc.get("id") or f"call_{zaehler}")
                zaehler += 1
                args = fn.get("arguments")
                args_str = args if isinstance(args, str) else json.dumps(
                    args or {}, ensure_ascii=False)
                calls.append({"id": cid, "type": "function",
                              "function": {"name": name, "arguments": args_str}})
                offene_ids.setdefault(name, []).append(cid)
            out.append({"role": "assistant", "content": m.get("content") or "",
                        "tool_calls": calls})
        elif rolle == "tool":
            name = m.get("tool_name") or m.get("name") or ""
            explizit = m.get("tool_call_id")
            if explizit:
                cid = str(explizit)
            else:
                warteschlange = offene_ids.get(name) or []
                cid = warteschlange.pop(0) if warteschlange else f"call_{name}"
            out.append({"role": "tool", "content": m.get("content") or "",
                        "tool_call_id": cid})
        else:
            neu: dict[str, Any] = {"role": rolle, "content": m.get("content") or ""}
            if m.get("name"):                 # optionaler few-shot-Name verlustfrei durch
                neu["name"] = m["name"]
            out.append(neu)
    return out


def _baue_tool_ereignis(puffer: dict[int, dict[str, str]],
                        reihenfolge: list[int]) -> RuntimeEreignis:
    """Gepufferte OpenAI-Delta-Fragmente → EIN ``tool_aufrufe``-Ereignis mit
    KOMPLETTEN ``ToolAufruf``. Argumente durch ``_normalize_args`` (akkumulierter
    JSON-String → dict; leer/kaputt ⇒ ``{}`` — dieselbe Logik wie beim Ollama-
    Adapter, nur die Quelle ist gepuffert statt komplett)."""
    aufrufe = tuple(
        ToolAufruf(name=puffer[idx]["name"] or "?",
                   argumente=_normalize_args(puffer[idx]["args"]),
                   id=puffer[idx]["id"])
        for idx in reihenfolge)
    return RuntimeEreignis("tool_aufrufe", tool_aufrufe=aufrufe)


class _OpenAIKompatRuntime(LocalRuntime):
    """Gemeinsame Basis der OpenAI-kompatiblen Adapter (vLLM · llama.cpp, docs/62
    §2). Spricht die OpenAI-``/v1``-Wire-Form: ``/v1/chat/completions`` (strukturiert
    = constrained via ``_cd_schluessel`` · chat_stream = SSE-Deltas), ``/v1/embeddings``
    (embed, roh), ``/v1/models`` (modelle), ``/health`` (health).

    Warum EINE Basis: vLLM und llama.cpp unterscheiden sich NUR in (a) ``name``,
    (b) ``faehigkeiten`` und (c) dem constrained-decoding-Feldnamen (``_cd_schluessel``
    = ``guided_json`` bei vLLM vs ``json_schema`` bei llama.cpp). Die harte Logik —
    SSE-Delta-Pufferung zu KOMPLETTEN Tool-Aufrufen (``tool_streaming_quelle='deltas'``)
    + das Ollama-nativ→OpenAI-Nachrichten-Mapping — ist identisch und lebt genau
    einmal hier. Die konkreten Stecker sind zwei dünne Unterklassen.

    Fehler-Verträge = exakt der ABC (strukturiert/embed → None fail-safe, modelle
    → [], health → ok=False, chat_stream WIRFT). Alle I/O-Nähte injizierbar
    (``http_post``/``http_get`` sync, ``sse_stream`` async) ⇒ OHNE laufenden Server
    testbar (wie OllamaRuntime). Die Liskov-sicheren Extra-kwargs (``http_post=``/
    ``http_get=`` je Aufruf, ``verlauf=`` bei strukturiert) spiegeln OllamaRuntime,
    damit die Adapter an JEDER heutigen Ollama-Naht 1:1 einsetzbar sind. Die Async-
    Zwillinge bleiben die geerbten ``to_thread``-Defaults (wertgleich; native
    ``httpx.AsyncClient``-Overrides erst, wenn ein echter async-Konsument sie pinnt —
    heute ruft NIEMAND diese Adapter). ``name``/``faehigkeiten`` bleiben hier bewusst
    der neutrale ABC-Default — die KONKRETEN Flags deklariert jede Unterklasse selbst.
    """

    name: ClassVar[str] = "openai-kompat"
    standard_url: ClassVar[str] = VLLM_STANDARD_URL   # Unterklassen überschreiben
    _cd_schluessel: ClassVar[str] = "guided_json"     # funktionaler Default; Unterklassen pinnen

    def __init__(self, url: str | None = None, *,
                 http_post: Callable | None = None,
                 http_get: Callable | None = None,
                 sse_stream: Callable | None = None) -> None:
        # KEIN rstrip('/') — Konvention wie OllamaRuntime (der Kanon trägt keinen
        # Schrägstrich; der Aufrufer reicht die konfigurierte URL herein).
        self.url = url or self.standard_url
        self._http_post = http_post
        self._http_get = http_get
        self._sse_stream = sse_stream

    # --- 1/5: strukturiert (constrained via _cd_schluessel) --------------------
    def strukturiert(self, system: str, nutzer: str, *, schema: type[M],
                     modell: str, temperature: float = 0.0,
                     timeout: float = TIMEOUT_STRUKTURIERT_S,
                     strikt: bool = False,
                     http_post: Callable | None = None,
                     verlauf: list[dict[str, str]] | None = None) -> M | None:
        # ``verlauf`` (Liskov-sichere Erweiterung wie bei OllamaRuntime, NICHT im
        # ABC): plain role/content-Turns, ZWISCHEN System- und User-Turn gespleißt
        # (memory-Vault-Chat). Für OpenAI-kompat sind plain-Turns formgleich ⇒ roher
        # Splice genügt (Ollama-Form-Tool-Turns gehören NICHT in verlauf, sondern in
        # chat_stream, das sie mappt). Default None ⇒ [system, user], 0 Wechsel.
        try:
            poster = (http_post or self._http_post
                      or (lambda u, d: _oai_post(u, d, timeout=timeout)))
            r = poster(f"{self.url}/v1/chat/completions", {
                "model": modell, "stream": False, "temperature": temperature,
                self._cd_schluessel: schema.model_json_schema(),
                "messages": [{"role": "system", "content": system},
                             *(verlauf or []),
                             {"role": "user", "content": nutzer}]})
            if getattr(r, "status_code", 0) != 200:
                return None
            inhalt = (((r.json().get("choices") or [{}])[0].get("message")
                       or {}).get("content")) or ""
            return schema.model_validate_json(inhalt)
        except Exception:
            if strikt:                        # Opt-in: Original-Exception durchreichen
                raise                         # (quick_chat-Parität) — Default wirft NIE
            return None

    # --- 2/5: chat_stream (SSE-Deltas → gepufferte KOMPLETTE Tool-Aufrufe) -----
    async def chat_stream(self, messages: list[dict], *, modell: str,
                          tools: list[dict] | None = None,
                          optionen: dict[str, Any] | None = None,
                          timeout: float = TIMEOUT_STREAM_S,
                          ) -> AsyncIterator[RuntimeEreignis]:
        payload: dict[str, Any] = {}
        if optionen:
            payload.update(optionen)          # Sampling-Durchreiche (temperature/max_tokens/…)
        payload["model"] = modell             # autoritative Keys gewinnen über optionen
        payload["messages"] = _zu_openai_nachrichten(messages)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}   # ende.nutzung-Anker (C5)
        if tools:
            payload["tools"] = tools
        url = f"{self.url}/v1/chat/completions"
        quelle = (self._sse_stream(url, payload) if self._sse_stream is not None
                  else self._default_sse_stream(url, payload, timeout))

        puffer: dict[int, dict[str, str]] = {}    # tool-call-index -> {id,name,args}
        reihenfolge: list[int] = []               # Erst-Sicht-Reihenfolge halten
        nutzung: dict[str, Any] | None = None
        tools_geflushed = False

        async for line in quelle:
            if not line or not line.startswith("data:"):
                continue                      # Blank-/Kommentar-/event:-Zeilen ignorieren
            daten = line[5:].strip()          # 'data:'-Präfix abschneiden
            if not daten:
                continue                      # leerer data-Frame (Keepalive)
            if daten == "[DONE]":
                break
            obj = json.loads(daten)           # kaputter Frame = Engine-Fehler ⇒ WIRFT (Vertrag)
            if obj.get("usage"):
                nutzung = obj["usage"]        # choices-loser include_usage-Chunk
            choices = obj.get("choices") or []
            if not choices:
                continue
            ch = choices[0]
            delta = ch.get("delta") or {}
            inhalt = delta.get("content")
            if inhalt:
                yield RuntimeEreignis("text", text=inhalt)
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)      # OpenAI: stabiler Delta-Index je Aufruf
                slot = puffer.get(idx)
                if slot is None:
                    slot = {"id": "", "name": "", "args": ""}
                    puffer[idx] = slot
                    reihenfolge.append(idx)
                if tc.get("id"):
                    slot["id"] = str(tc["id"])
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                stueck = fn.get("arguments")
                if stueck:
                    slot["args"] += stueck
            # finish_reason ⇒ die gepufferten Tools sind komplett: als EIN Ereignis raus
            if ch.get("finish_reason") and puffer and not tools_geflushed:
                yield _baue_tool_ereignis(puffer, reihenfolge)
                tools_geflushed = True
        # Defensiv: Stream endete ohne finish_reason-Flush (nur [DONE]/Abriss)
        if puffer and not tools_geflushed:
            yield _baue_tool_ereignis(puffer, reihenfolge)
        yield RuntimeEreignis("ende", nutzung=nutzung)

    async def _default_sse_stream(self, url: str, payload: dict,
                                  timeout: float) -> AsyncIterator[str]:
        """Default-SSE-Transport (Timeout wie agent.py: 300 s, connect 8 s).
        Liefert die rohen ``data:``-Zeilen; Parsen/Puffern/Mappen macht ``chat_stream``."""
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8.0)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    yield line

    # --- 3/5: embed (/v1/embeddings, roh — KEINE L2-Norm) ----------------------
    def embed(self, texts: list[str], *, modell: str,
              timeout: float = TIMEOUT_EMBED_S,
              http_post: Callable | None = None) -> list[list[float]] | None:
        if not texts:
            return []                         # leer ⇒ [] OHNE Netz-Call (Vertrag)
        try:
            poster = (http_post or self._http_post
                      or (lambda u, d: _oai_post(u, d, timeout=timeout)))
            r = poster(f"{self.url}/v1/embeddings", {"model": modell, "input": texts})
            if getattr(r, "status_code", 0) != 200:
                return None
            daten = r.json().get("data") or []
            # OpenAI liefert je Eintrag einen ``index`` — nach ihm ordnen hält die
            # Eingabe-Reihenfolge (roh, keine Normalisierung — Index-Politik = rag.py).
            geordnet = sorted(daten, key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in geordnet]
        except Exception:
            return None

    # --- 4/5: modelle (/v1/models → ModellInfo; Fehler ⇒ []) -------------------
    def modelle(self, *, http_get: Callable | None = None) -> list[ModellInfo]:
        try:
            getter = (http_get or self._http_get
                      or (lambda u: _oai_get(u, timeout=TIMEOUT_HEALTH_S)))
            r = getter(f"{self.url}/v1/models")
            if getattr(r, "status_code", 0) != 200:
                return []
            out: list[ModellInfo] = []
            for m in (r.json().get("data") or []):
                name = m.get("id")            # OpenAI: Modell-ID im 'id'-Feld
                if not name:
                    continue
                # /v1/models trägt KEINE Größe (docs/62 §2: „nur IDs") ⇒ None ehrlich.
                out.append(ModellInfo(
                    name=name, groesse_bytes=None,
                    details={k: v for k, v in m.items() if k != "id"}))
            return out
        except Exception:
            return []

    # --- 5/5: health (/health, kleines Timeout; wirft NIE) ---------------------
    def health(self, *, http_get: Callable | None = None) -> RuntimeHealth:
        getter = (http_get or self._http_get
                  or (lambda u: _oai_get(u, timeout=TIMEOUT_HEALTH_S)))
        try:
            r = getter(f"{self.url}/health")
            code = getattr(r, "status_code", 0)
            if code != 200:
                return RuntimeHealth(ok=False, laufzeit=self.name, url=self.url,
                                     detail=f"HTTP {code}")
            # vLLM/llama.cpp /health = leerer 200 (keine Version im Body) ⇒ version
            # bleibt None ehrlich (anders als Ollama /api/version).
            return RuntimeHealth(ok=True, laufzeit=self.name, url=self.url)
        except Exception as e:                # unerreichbar ⇒ ok=False + ehrliches detail
            return RuntimeHealth(ok=False, laufzeit=self.name, url=self.url,
                                 detail=f"{type(e).__name__}: {e}")


class VLLMRuntime(_OpenAIKompatRuntime):
    """LocalRuntime-Adapter für **vLLM** (OpenAI-kompatibler ``/v1``-Server, docs/62
    §2). Constrained decoding über ``guided_json`` (XGrammar-Default; die strikte
    ``response_format``-json_schema-Schiene wird bewusst gemieden — Wurzel-Array/
    $ref-Grenzen). Tool-Aufrufe streamen als OpenAI-Deltas ⇒ die geerbte chat_stream-
    Logik puffert sie intern zu KOMPLETTEN ``ToolAufruf``. Continuous batching;
    Kontext server-fix (``max_model_len``, NICHT per Request steuerbar).

    ``cd_wurzel_array=False`` ist bewusst konservativ deklariert (docs/62 §2 führt
    guided_json als wurzel-array-fähig ✓ — hier under-claimed, weil die Fähigkeit
    backend-/versionsabhängig ist und Unterschätzen die sichere Richtung: ein
    Aufrufer mit Wurzel-Array-Schema wrappt dann defensiv, was immer trägt)."""

    name: ClassVar[str] = "vllm"
    standard_url: ClassVar[str] = VLLM_STANDARD_URL
    _cd_schluessel: ClassVar[str] = "guided_json"
    faehigkeiten: ClassVar[RuntimeFaehigkeiten] = RuntimeFaehigkeiten(
        cd_dialekt="guided_json", cd_ref_faehig=True, cd_wurzel_array=False,
        tool_streaming_quelle="deltas", tools=True, kontext_steuerbar=False,
        embed=True, batching="kontinuierlich")


# Z1.3 / docs/62 §2: vLLM additiv anmelden — NICHT als Default (``DEFAULT_RUNTIME``
# bleibt 'ollama'). Bis ein Setting 'vllm' wählt UND ein vLLM-Server deployt ist,
# ruft ihn NIEMAND ⇒ netzweiter 0-Verhaltenswechsel (der core-fail-safe-Test nutzt
# bewusst 'vllm-gibts-noch-nicht', nicht 'vllm' — kollidiert also nicht). Core wird
# ihn später URL-gebunden re-registrieren (wie 'ollama' in providers.py), sobald der
# Server steht — das ist der Deploy-Schritt, nicht dieser Bau.
registriere_runtime("vllm", VLLMRuntime)


class LlamaCppRuntime(_OpenAIKompatRuntime):
    """LocalRuntime-Adapter für **llama.cpp** (``llama-server``, OpenAI-kompatibler
    ``/v1``, docs/62 §2). Constrained decoding über das ``json_schema``-Feld (der
    Server konvertiert Schema→GBNF; ``cd_dialekt='gbnf'``, $ref/Wurzel-Array löst
    der Konverter auf — daher ``cd_wurzel_array=True``, anders als beim vLLM-
    ``guided_json``-Pfad). Tool-Streaming ist versionsabhängig ⇒ die geerbte Delta-
    Pufferung greift defensiv (liefert nach außen wie immer KOMPLETTE Aufrufe).
    Einzel-Batching (kein continuous batching wie vLLM); Kontext server-fix (``-c``).

    Teilt die GESAMTE Transport-/Mapping-/Pufferungs-Logik mit ``VLLMRuntime`` über
    ``_OpenAIKompatRuntime`` — der einzige Code-Unterschied ist ``_cd_schluessel``
    (``json_schema`` statt ``guided_json``) plus die ehrlichen Capability-Flags."""

    name: ClassVar[str] = "llamacpp"
    standard_url: ClassVar[str] = LLAMACPP_STANDARD_URL
    _cd_schluessel: ClassVar[str] = "json_schema"
    faehigkeiten: ClassVar[RuntimeFaehigkeiten] = RuntimeFaehigkeiten(
        cd_dialekt="gbnf", cd_ref_faehig=True, cd_wurzel_array=True,
        tool_streaming_quelle="deltas", tools=True, kontext_steuerbar=False,
        embed=True, batching="einzeln")


# Z1.3 / docs/62 §2: llama.cpp ebenfalls additiv anmelden — NICHT als Default. Wie
# vLLM ruft ihn NIEMAND, bis ein Setting 'llamacpp' wählt UND ein llama-server steht
# ⇒ 0 Verhaltenswechsel. Damit ist die Runtime-Abstraktion vollständig (drei Stecker:
# ollama · vllm · llamacpp); der nächste Adapter-Kandidat (LiteLlmRuntime, docs/62 §5)
# säße genauso HINTER dem Vertrag, nie als Ersatz.
registriere_runtime("llamacpp", LlamaCppRuntime)
