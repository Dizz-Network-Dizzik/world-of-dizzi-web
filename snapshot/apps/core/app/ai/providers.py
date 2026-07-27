"""Provider-Abstraktion: EIN Client für alle Modell-Quellen.

Alle Provider sprechen die OpenAI-kompatible Chat-API (/v1/chat/completions).
Die Kette wird der Reihe nach versucht; fällt ein Provider aus, übernimmt der
nächste. Lokal (Ollama) steht IMMER am Ende als Boden, der funktioniert.

Boost-Provider sind vorbereitete Anschlüsse (Systemübersicht §4): aktiv erst,
wenn der jeweilige API-Key als Umgebungsvariable gesetzt ist. 0-€-Strategie:
alle gelisteten Boost-Tiers sind kostenlose Kontingente (Stand docs/02).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from appkit import modellprofil as mp
from appkit.runtime import (
    DEFAULT_RUNTIME,
    LocalRuntime,
    OllamaRuntime,
    registriere_runtime,
    runtime_holen,
)

from .. import db
from ..config import DEFAULT_USER_ID

OLLAMA_URL = os.environ.get("DIZZI_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_LOCAL_MODEL = "qwen3:14b"
FAST_LOCAL_MODEL = "qwen3:4b"  # für Blitz-Aufgaben (Memory-Extraktion etc.)

# --- Circuit-Breaker für Boost-Provider (docs/50 P3.3b) ----------------------
# Ein zickender Cloud-Provider (Key abgelaufen, Rate-Limit, Netz weg) soll nicht
# jede Anfrage erst in den Timeout laufen lassen. Nach CB_SCHWELLE Fehlern IN FOLGE
# wird er für CB_COOLDOWN_S übersprungen; ein Erfolg schließt sofort wieder. In-
# memory, prozess-lokal, fail-safe. **Lokal (Ollama) wird NIE ausgesperrt** — der
# Boden muss immer erreichbar bleiben (sonst hätte der Chat keine Quelle mehr).
CB_SCHWELLE = 3
CB_COOLDOWN_S = 30.0
_cb_state: dict[str, dict] = {}     # provider_id -> {"fails": int, "bis": monotonic-ts}


def _cb_eintrag(pid: str) -> dict:
    return _cb_state.setdefault(pid, {"fails": 0, "bis": 0.0})


def circuit_offen(spec: "ProviderSpec") -> bool:
    """True ⇒ Provider gerade im Cooldown (überspringen). Lokal nie."""
    if spec.kind == "lokal":
        return False
    return time.monotonic() < _cb_eintrag(spec.id)["bis"]


def cb_fehler(spec: "ProviderSpec") -> None:
    """Fehlversuch zählen; ab CB_SCHWELLE in Folge den Provider öffnen (Cooldown)."""
    if spec.kind == "lokal":
        return
    e = _cb_eintrag(spec.id)
    e["fails"] += 1
    if e["fails"] >= CB_SCHWELLE:
        e["bis"] = time.monotonic() + CB_COOLDOWN_S


def cb_erfolg(spec: "ProviderSpec") -> None:
    """Erfolg ⇒ Zähler/Cooldown zurücksetzen (Breaker schließt sofort)."""
    _cb_state[spec.id] = {"fails": 0, "bis": 0.0}


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    base_url: str           # OpenAI-kompatible Basis (…/v1)
    api_key_env: str | None  # None = lokal, kein Key
    default_model: str
    kind: str               # 'lokal' | 'boost'

    @property
    def available(self) -> bool:
        if self.api_key_env is None:
            return True
        return bool(os.environ.get(self.api_key_env))


PROVIDERS: list[ProviderSpec] = [
    ProviderSpec("nim", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1",
                 "DIZZI_NIM_KEY", "moonshotai/kimi-k2.6", "boost"),
    ProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1",
                 "DIZZI_GROQ_KEY", "llama-3.3-70b-versatile", "boost"),
    ProviderSpec("cerebras", "Cerebras", "https://api.cerebras.ai/v1",
                 "DIZZI_CEREBRAS_KEY", "llama-3.3-70b", "boost"),
    ProviderSpec("lokal", "Ollama (lokal)", f"{OLLAMA_URL}/v1",
                 None, DEFAULT_LOCAL_MODEL, "lokal"),
]


def local_model() -> str:
    """Aktives lokales Chat-Modell. Präzedenz (docs/62 M8/C3, 0-Verhaltenswechsel-
    Anker): Nutzer-Setting ``ai_model`` > Profil-Slot ``chat`` (Stufe 0) > Konstante
    ``DEFAULT_LOCAL_MODEL``. Ein gesetztes ``ai_model`` gewinnt weiter wie zuvor; das
    Profil ersetzt nur die Konstante als Default-Quelle. Pin: ``STUFE_0.modell_fuer
    ('chat') == DEFAULT_LOCAL_MODEL`` (test_profil_paritaet_mit_konstanten)."""
    return db.setting_get(DEFAULT_USER_ID, "ai_model",
                          mp.STUFE_0.modell_fuer("chat") or DEFAULT_LOCAL_MODEL)


def fast_model() -> str:
    """Aktives ``schnell``-Modell (Triage/Blitz-Aufgaben, heutige FAST_LOCAL_MODEL-
    Rolle). Präzedenz (docs/62 M8/C3): Profil-Slot ``schnell`` (Stufe 0) > Konstante
    ``FAST_LOCAL_MODEL``. Kein eigenes Nutzer-Setting heute (anders als ``ai_model``)
    ⇒ Profil > Konstante. 0-Verhaltenswechsel: ``STUFE_0.modell_fuer('schnell') ==
    FAST_LOCAL_MODEL`` (Pin)."""
    return mp.STUFE_0.modell_fuer("schnell") or FAST_LOCAL_MODEL


# --- Lokale KI-Runtime (docs/62 M4–M7) ---------------------------------------
# Die drei hartverdrahteten Ollama-Stellen in core (agent · rag · und die lokalen
# Nähte hier) sprechen seit M4–M6 NICHT mehr direkt httpx, sondern EINE
# ``LocalRuntime``. M7 (C2): WELCHE Runtime das ist, entscheidet jetzt das Setting
# ``runtime`` über die appkit-Registry (``runtime_holen``) — Default/unbekannt/leer
# ⇒ Ollama (fail-safe: ein kaputtes Setting ändert das Verhalten nie).
#
# ENV-Split (docs/62 §0): der appkit-Default-Ollama läse ``DIZZ_OLLAMA_URL``; core
# MUSS aber seine ``DIZZI_OLLAMA_URL`` (``OLLAMA_URL``) behalten. Darum registriert
# core hier seine EIGENE, URL-gepinnte Ollama-Fabrik — sie ersetzt (im core-Prozess)
# die appkit-Default-Registrierung, sodass ``runtime_holen("ollama")`` die core-URL-
# Instanz liefert. Die Registry cacht eine Instanz je Name (der Adapter ist
# zustandsarm) ⇒ kein eigener ``_runtime_cache`` mehr nötig; der Default-Pfad ist
# byte-gleich zu M4–M6 (dieselbe ``OllamaRuntime(url=OLLAMA_URL)``-Instanz).
registriere_runtime("ollama", lambda: OllamaRuntime(url=OLLAMA_URL))


def runtime() -> LocalRuntime:
    """Die aktive lokale KI-Runtime (docs/62 M7/C2).

    Das Setting ``runtime`` (core-DB, Default ``ollama``) wählt den Adapter über
    die appkit-Registry. Fail-safe: ``None``/leer/unbekannt ⇒ Ollama (ein kaputtes
    Setting ändert das Verhalten nie). 0-Verhaltenswechsel: der Default-Pfad
    liefert exakt die core-URL-gepinnte ``OllamaRuntime`` wie in M4–M6 — dieselbe
    gecachte Instanz, dieselben ``/api``-Endpunkte."""
    return runtime_holen(db.setting_get(DEFAULT_USER_ID, "runtime", DEFAULT_RUNTIME))


def chain(sensitive: bool) -> list[ProviderSpec]:
    """Provider-Reihenfolge für eine Anfrage. Sensibel ⇒ NUR lokal."""
    if sensitive:
        return [p for p in PROVIDERS if p.kind == "lokal"]
    boost_on = db.setting_get(DEFAULT_USER_ID, "ai_boost", True)
    out = [p for p in PROVIDERS if p.available and (boost_on or p.kind == "lokal")]
    # Circuit-Breaker: offene Boost-Provider überspringen; lokal bleibt IMMER drin
    # (circuit_offen ist für 'lokal' stets False ⇒ der Boden geht nie verloren).
    return [p for p in out if not circuit_offen(p)]


def _payload(spec: ProviderSpec, messages: list[dict], stream: bool) -> dict:
    if spec.kind == "lokal":
        model = local_model()
    else:  # Boost-Modell je Provider per Setting übersteuerbar
        model = db.setting_get(DEFAULT_USER_ID, f"boost_model_{spec.id}", spec.default_model)
    return {"model": model, "messages": messages, "stream": stream}


def _headers(spec: ProviderSpec) -> dict:
    h = {"Content-Type": "application/json"}
    if spec.api_key_env:
        h["Authorization"] = f"Bearer {os.environ[spec.api_key_env]}"
    return h


async def stream_chat(messages: list[dict], sensitive: bool) -> AsyncIterator[tuple[str, str]]:
    """Streamt Antwort-Tokens als (provider_id, text_chunk).

    Probiert die Kette der Reihe nach; ein Provider gilt als gescheitert,
    solange noch kein Token geflossen ist (danach kein stiller Wechsel mehr —
    halbe Antworten aus zwei Quellen wären schlimmer als ein Abbruch).
    """
    last_err: Exception | None = None
    for spec in chain(sensitive):
        emitted = False
        try:
            if spec.kind == "lokal":
                # Lokal-Bein über die LocalRuntime (docs/62 M5) — nativer /api/chat-
                # Stream statt /v1; Modell wie _payload(lokal): local_model(). Timeout
                # 180 s wie bisher. Die Boost-Kette bleibt bewusst /v1-httpx (unten):
                # Provider-Kette + Failover ist providers-Politik (docs/62 §6), nicht
                # Runtime. chat_stream WIRFT bei Transportfehler ⇒ dieselbe emitted-Regel.
                async for ev in runtime().chat_stream(
                        messages, modell=local_model(), timeout=180.0):
                    if ev.art == "text" and ev.text:
                        emitted = True
                        yield (spec.id, ev.text)
            else:
                async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=8.0)) as client:
                    async with client.stream(
                        "POST", f"{spec.base_url}/chat/completions",
                        json=_payload(spec, messages, stream=True), headers=_headers(spec),
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            delta = (json.loads(data).get("choices") or [{}])[0].get("delta", {})
                            chunk = delta.get("content")
                            if chunk:
                                emitted = True
                                yield (spec.id, chunk)
            cb_erfolg(spec)      # sauber durchgelaufen ⇒ Breaker schließen
            return
        except Exception as e:  # Provider down/Key ungültig/Netz weg → nächster
            last_err = e
            cb_fehler(spec)     # Fehlversuch zählen (öffnet ab CB_SCHWELLE; lokal no-op)
            if emitted:
                raise
    raise RuntimeError(f"Kein Provider erreichbar (zuletzt: {last_err})")


async def quick_chat(messages: list[dict], model: str | None = None,
                     *, format: dict | None = None) -> str:
    """Eine kleine, nicht gestreamte Lokal-Anfrage (Memory-Extraktion etc.).

    ``format`` (optional, docs/50 P2.1): ein JSON-Schema erzwingt die Antwort-
    Struktur per Grammatik (constrained decoding). Mit Schema läuft die Anfrage
    über Ollamas **nativen** ``/api/chat``-``format``-Slot — der nimmt beliebige
    Schemata zuverlässig (auch Wurzel-Array/``$ref``), anders als die strikte
    OpenAI-``/v1``-``response_format``-Variante (Wurzel muss ``object`` sein).

    Ohne Schema läuft die Anfrage über die LocalRuntime (docs/62 M5, ``a_chat`` =
    chat_stream eingesammelt); ``strikt=True`` reicht Transportfehler durch, quick_chat
    WIRFT also weiter wie zuvor. Der ``format``-Pfad bleibt bewusst der native
    ``/api/chat``-httpx-Call: der 5-Methoden-Runtime-Vertrag hat keine „strukturierter-
    Chat-liefert-Rohstring"-Methode — ``a_strukturiert`` validiert in ein Pydantic-Modell
    und braucht dessen KLASSE, die quick_chats eingefrorene ``format: dict``-Signatur
    nicht liefert (die Aufrufer trimmen + validieren selbst). Diese Naht wandert erst
    mit dem Aufrufer-Umbau (analyst/memory → ``a_strukturiert``), NICHT in M5."""
    mdl = model or fast_model()
    if format is not None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json={
                "model": mdl, "messages": messages, "stream": False, "format": format})
            r.raise_for_status()
            return (r.json().get("message") or {}).get("content", "")
    return await runtime().a_chat(messages, modell=mdl, strikt=True, timeout=60.0)


# --- Modell-Profil-Kanal (docs/62 M9/C4) -------------------------------------
# Die hardware-bewusste Kanal-Stufe (welches Profil passt auf diese Maschine) ist
# REIN informativ fürs UI/Status — sie ändert NICHTS am Laufzeit-Modell (das bleibt
# Setting > Profil > Konstante, s. local_model/fast_model). GESAMT-VRAM ist je
# Maschine konstant ⇒ EINMAL proben (die nvidia-smi-Probe soll nicht bei jedem
# /api/status-Poll neu forken); der Pin (Setting) ist veränderlich ⇒ je Aufruf frisch.
_vram_geprueft: bool = False
_vram_gesamt: int | None = None


def _vram_bytes() -> int | None:
    """Gecachtes Gesamt-VRAM (konstant je Maschine). ``mp.vram_probe`` ist
    fail-safe (wirft nie ⇒ None ⇒ Boden Stufe 0)."""
    global _vram_geprueft, _vram_gesamt
    if not _vram_geprueft:
        _vram_gesamt = mp.vram_probe()
        _vram_geprueft = True
    return _vram_gesamt


def _vram_reset() -> None:
    """Test-Haken: verwirft den VRAM-Cache (nächster Zugriff probt neu). Produktiv
    ungenutzt — Gesamt-VRAM ändert sich zur Laufzeit nicht."""
    global _vram_geprueft
    _vram_geprueft = False


def _profil_stufe_pin() -> int | None:
    """Optionaler Nutzer-Pin der Profil-Stufe (Setting ``modell_profil_stufe``),
    fail-safe zu ``int|None`` (Garbage ⇒ None ⇒ auto-Auflösung; Release-Gate
    schlägt den Pin ohnehin, s. modellprofil.aufloese_stufe)."""
    roh = db.setting_get(DEFAULT_USER_ID, "modell_profil_stufe", None)
    try:
        return int(roh) if roh is not None else None
    except (TypeError, ValueError):
        return None


def kanal() -> dict:
    """Aufgelöste Modell-Profil-Stufe (docs/62 M9/C4): hardware-bewusste Wahl über
    ``vram_probe`` (Gesamt-VRAM) + optionalen Pin ``modell_profil_stufe``.

    REIN informativ — ändert das Laufzeit-Modell NICHT (das bleibt
    ``local_model``/``fast_model``). ``reindex_noetig`` ist ein GATE-HINWEIS (der
    embed-Slot der Zielstufe ≠ das heute indizierte bge-m3): **KEIN Auto-Lauf** —
    der teure Re-Index bleibt nutzer-gegated, das Verwerfen erledigt
    ``rag._migriere_modellwechsel`` gegated (VEC_SCHEMA-Disziplin). Vergleichs-
    Basis ist Stufe 0 (== die heute deployten ``rag.EMBED_MODEL``/``EMBED_DIM``).
    Heute enthält ``STUFEN`` nur Stufe 0 ⇒ stets Stufe 0, ``reindex_noetig=False``;
    das Feld ist die vorverdrahtete Infrastruktur für spätere Kanal-Releases."""
    vram = _vram_bytes()
    profil = mp.aufloese_stufe(vram, pin=_profil_stufe_pin())
    folgen = mp.profil_wechsel_folgen(mp.STUFE_0, profil)
    return {
        "stufe": profil.stufe,
        "name": profil.name,
        "vram_bytes": vram,
        "reindex_noetig": folgen.reindex_noetig,
        "reindex_hinweis": folgen.hinweis,
    }


async def status() -> dict:
    """Zustand der Modell-Schicht fürs UI / Health.

    Läuft über die Selbstauskunft der LocalRuntime (docs/62 M5): ``health()`` =
    Liveness (``/api/version``, 3 s, wirft nie), ``modelle()`` = verfügbare Modelle
    (``/api/tags``, [] bei Fehler). ``ollama_ok`` spiegelt jetzt die Liveness-Probe;
    für ein laufendes Ollama identisch zum bisherigen ``/api/tags``-Erfolg.

    M7/M9 (additiv, 0 Verhaltenswechsel): ``runtime`` = aktiver Runtime-Name
    (Setting-getrieben), ``kanal`` = aufgelöste Modell-Profil-Stufe + Re-Index-
    Gate-Hinweis. Die Bestandsfelder bleiben unverändert."""
    rt = runtime()
    gesundheit = await rt.a_health()
    modelle = await rt.a_modelle()
    return {
        "ollama_ok": gesundheit.ok,
        "models": [m.name for m in modelle],
        "active_model": local_model(),
        "runtime": db.setting_get(DEFAULT_USER_ID, "runtime", DEFAULT_RUNTIME),
        "kanal": kanal(),
        "providers": [
            {"id": p.id, "label": p.label, "kind": p.kind, "available": p.available}
            for p in PROVIDERS
        ],
    }
