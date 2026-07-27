"""Adapter-Tests für ``runtime.OllamaRuntime`` (C1 / docs/62 §4 M2).

Ollama-frei: ALLE I/O-Nähte (``http_post``/``http_get`` sync, ``zeilen_stream``
async) sind gefakt. Beweist (a) strukturiert-Parität zum eingefrorenen
``appkit/ollama.strukturiert``-Vertrag (dieselben Fälle wie ``test_ollama.py``),
(b) das chat_stream/embed/modelle/health-Mapping und die Fehler-Verträge. async
über ``asyncio.run`` (keine pytest-asyncio-Annahme, wie ``test_runtime_vertrag.py``).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from appkit import runtime as rt


class _Antwort(BaseModel):
    antwort: str
    belege: list[str] = []


def _resp(payload, status=200):
    """POST-Antwort-Fake wie in test_ollama.py (message.content = JSON-Dump)."""
    class _R:
        status_code = status

        def json(self):
            return {"message": {"content": json.dumps(payload)
                                if not isinstance(payload, str) else payload}}
    return _R()


def _roh_resp(payload, status=200):
    """GET-/roher-Body-Antwort-Fake für modelle/health/embed."""
    class _R:
        status_code = status

        def json(self):
            return payload
    return _R()


async def _sammle(aiter):
    return [ev async for ev in aiter]


def _zeilen(lines):
    """``zeilen_stream``-Fake: AsyncIterator über feste NDJSON-Zeilen."""
    def fabrik(url, payload):
        async def gen():
            for ln in lines:
                yield ln
        return gen()
    return fabrik


# --- strukturiert: Parität zu test_ollama.py ---------------------------------

def test_strukturiert_gueltige_antwort_wird_validiert():
    gesehen = {}

    def fake(url, daten):
        gesehen["url"], gesehen["daten"] = url, daten
        return _resp({"antwort": "Hallo", "belege": ["A"]})

    res = rt.OllamaRuntime().strukturiert(
        "sys", "frage", schema=_Antwort, modell="qwen3:4b", http_post=fake)
    assert res is not None and res.antwort == "Hallo" and res.belege == ["A"]
    assert gesehen["url"].endswith("/api/chat")
    assert gesehen["daten"]["format"] == _Antwort.model_json_schema()
    assert gesehen["daten"]["model"] == "qwen3:4b"
    assert gesehen["daten"]["stream"] is False


def test_strukturiert_fehlerpfade_ergeben_none():
    r = rt.OllamaRuntime()
    # HTTP != 200 ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _resp({}, status=500)) is None

    # Poster wirft ⇒ None (fail-safe)
    def boom(u, d):
        raise OSError("ollama weg")
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m", http_post=boom) is None

    # schema-ungültige Antwort (Pflichtfeld fehlt) ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _resp({"falsch": 1})) is None
    # gar kein JSON ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _resp("kein json")) is None


def test_strukturiert_temperature_durchgereicht():
    gesehen = {}

    def fake(url, daten):
        gesehen["t"] = daten["options"]["temperature"]
        return _resp({"antwort": "x"})

    rt.OllamaRuntime().strukturiert("s", "f", schema=_Antwort, modell="m",
                                    http_post=fake, temperature=0.3)
    assert gesehen["t"] == 0.3


def test_strukturiert_poster_positional_kompatibel_mit_keyword_json_fake():
    """Module, die ihren echten Poster mit ``json=`` füttern, deklarieren im Test
    ``def fake(url, json)`` — der POSITIONALE Aufruf bindet ``daten`` korrekt (die
    App-Suiten-Fake-Konvention überlebt an OllamaRuntime.strukturiert)."""
    def fake(url, json):
        return _resp({"antwort": json["model"]})
    res = rt.OllamaRuntime().strukturiert("s", "f", schema=_Antwort, modell="qwen3:4b",
                                          http_post=fake)
    assert res is not None and res.antwort == "qwen3:4b"


def test_strukturiert_instanz_naht_und_strikt_durchreiche():
    # Instanz-Naht (http_post via __init__) statt per-Aufruf
    r = rt.OllamaRuntime(http_post=lambda u, d: _resp({"antwort": "inst"}))
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m").antwort == "inst"

    # strikt=True reicht die Original-Exception durch (quick_chat-Parität, M5)
    def boom(u, d):
        raise OSError("weg")
    with pytest.raises(OSError):
        rt.OllamaRuntime().strukturiert("s", "f", schema=_Antwort, modell="m",
                                        http_post=boom, strikt=True)


def test_strukturiert_verlauf_wird_zwischen_system_und_user_gespleisst():
    """docs/62 runtime-Konsistenz (memory-Vault-Chat): der optionale ``verlauf``-
    kwarg (Liskov-sichere Adapter-Erweiterung wie ``http_post``, NICHT im ABC) spleißt
    vorherige Gesprächs-Messages ZWISCHEN System- und User-Turn. Ohne ihn bleibt es
    byte-gleich bei [system, user] ⇒ 0 Verhaltenswechsel für ALLE Bestands-Aufrufer
    (der eingefrorene ollama.py-Shim + die 7 App-Suiten reichen ihn nie)."""
    gesehen = {}

    def fake(url, daten):
        gesehen["messages"] = daten["messages"]
        return _resp({"antwort": "x"})

    r = rt.OllamaRuntime()
    # Default (kein verlauf): exakt [system, user] wie vor der Erweiterung
    r.strukturiert("SYS", "USER", schema=_Antwort, modell="m", http_post=fake)
    assert [m["role"] for m in gesehen["messages"]] == ["system", "user"]
    assert gesehen["messages"][0]["content"] == "SYS"
    assert gesehen["messages"][-1]["content"] == "USER"

    # Mit verlauf: [system, *verlauf, user] — Reihenfolge + Inhalte erhalten
    verlauf = [{"role": "user", "content": "davor"},
               {"role": "assistant", "content": "antwort davor"}]
    r.strukturiert("SYS", "USER", schema=_Antwort, modell="m",
                   http_post=fake, verlauf=verlauf)
    assert [m["role"] for m in gesehen["messages"]] == \
        ["system", "user", "assistant", "user"]
    assert gesehen["messages"][1:3] == verlauf
    assert gesehen["messages"][-1]["content"] == "USER"


# --- chat_stream: Mapping text/tool_aufrufe/ende -----------------------------

def test_chat_stream_text_chunks_und_ende_nutzung():
    lines = [
        json.dumps({"message": {"content": "Hal"}}),
        "",  # leere Zeile wird übersprungen
        json.dumps({"message": {"content": "lo"}}),
        json.dumps({"message": {"content": ""}, "done": True,
                    "eval_count": 5, "prompt_eval_count": 3, "total_duration": 42}),
    ]
    r = rt.OllamaRuntime(zeilen_stream=_zeilen(lines))
    evs = asyncio.run(_sammle(r.chat_stream([{"role": "user", "content": "?"}], modell="m")))
    assert [e.art for e in evs] == ["text", "text", "ende"]
    assert "".join(e.text for e in evs if e.art == "text") == "Hallo"
    # nutzung = alle rohen Zähler-Felder (ohne die Nachricht selbst)
    assert evs[-1].nutzung == {"done": True, "eval_count": 5,
                               "prompt_eval_count": 3, "total_duration": 42}


def test_chat_stream_tool_aufrufe_komplett_und_normalisiert():
    lines = [
        json.dumps({"message": {"tool_calls": [
            {"function": {"name": "suche", "arguments": {"q": "x"}}},     # dict-Args
            {"function": {"name": "rechne", "arguments": '{"a": 1}'}},    # JSON-String
            {"function": {"name": "kaputt", "arguments": "kein-json"}},   # kaputt ⇒ {}
        ]}}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]
    evs = asyncio.run(_sammle(
        rt.OllamaRuntime(zeilen_stream=_zeilen(lines)).chat_stream([], modell="m")))
    tool_ev = next(e for e in evs if e.art == "tool_aufrufe")
    assert [t.name for t in tool_ev.tool_aufrufe] == ["suche", "rechne", "kaputt"]
    assert [t.argumente for t in tool_ev.tool_aufrufe] == [{"q": "x"}, {"a": 1}, {}]
    # als_ollama-Rückform fürs Konversations-Echo (agent.py, M4)
    assert tool_ev.tool_aufrufe[0].als_ollama() == {
        "function": {"name": "suche", "arguments": {"q": "x"}}}
    assert evs[-1].art == "ende"


def test_chat_stream_payload_traegt_tools_und_optionen():
    gesehen = {}

    def spion(url, payload):
        gesehen["url"], gesehen["payload"] = url, payload

        async def gen():
            yield json.dumps({"message": {"content": "ok"}, "done": True})
        return gen()

    asyncio.run(_sammle(rt.OllamaRuntime(zeilen_stream=spion).chat_stream(
        [{"role": "user", "content": "?"}], modell="m",
        tools=[{"type": "function"}], optionen={"num_ctx": 8192})))
    assert gesehen["url"].endswith("/api/chat")
    assert gesehen["payload"]["stream"] is True
    assert gesehen["payload"]["tools"] == [{"type": "function"}]
    assert gesehen["payload"]["options"] == {"num_ctx": 8192}


def test_chat_stream_wirft_bei_transportfehler():
    def kaputt(url, payload):
        async def gen():
            raise ConnectionError("engine weg")
            yield ""  # unreachable — macht gen() zum async-Generator
        return gen()
    with pytest.raises(ConnectionError):
        asyncio.run(_sammle(
            rt.OllamaRuntime(zeilen_stream=kaputt).chat_stream([], modell="m")))


# --- embed: leer/gültig/Fehler -----------------------------------------------

def test_embed_leer_macht_keinen_call():
    def darf_nicht(u, d):
        raise AssertionError("embed([]) darf keinen Netz-Call machen")
    assert rt.OllamaRuntime(http_post=darf_nicht).embed([], modell="bge-m3") == []


def test_embed_gueltig_form_und_fehler():
    gesehen = {}

    def ok(u, d):
        gesehen["url"], gesehen["daten"] = u, d
        return _roh_resp({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    r = rt.OllamaRuntime()
    assert r.embed(["a", "b"], modell="bge-m3", http_post=ok) == [[0.1, 0.2], [0.3, 0.4]]
    assert gesehen["url"].endswith("/api/embed")
    assert gesehen["daten"] == {"model": "bge-m3", "input": ["a", "b"]}

    # HTTP != 200 ⇒ None
    assert r.embed(["a"], modell="m", http_post=lambda u, d: _roh_resp({}, status=500)) is None

    # Poster wirft ⇒ None (fail-safe)
    def boom(u, d):
        raise OSError("weg")
    assert r.embed(["a"], modell="m", http_post=boom) is None


# --- modelle: Mapping + Fehler ⇒ [] ------------------------------------------

def test_modelle_mapping_name_size_details():
    body = {"models": [
        {"name": "qwen3:14b", "size": 9_000_000_000,
         "details": {"family": "qwen3", "quantization_level": "Q4_K_M"}},
        {"name": "bge-m3", "size": 1_200_000_000},
        {"size": 1},  # ohne name ⇒ übersprungen
    ]}
    ms = rt.OllamaRuntime(http_get=lambda u: _roh_resp(body)).modelle()
    assert [m.name for m in ms] == ["qwen3:14b", "bge-m3"]
    assert ms[0].groesse_bytes == 9_000_000_000
    assert ms[0].details == {"details": {"family": "qwen3", "quantization_level": "Q4_K_M"}}
    assert "size" not in ms[0].details and "name" not in ms[0].details
    assert ms[1].groesse_bytes == 1_200_000_000 and ms[1].details == {}


def test_modelle_fehler_ergibt_leer():
    r = rt.OllamaRuntime()
    assert r.modelle(http_get=lambda u: _roh_resp({}, status=500)) == []

    def boom(u):
        raise OSError("weg")
    assert r.modelle(http_get=boom) == []


# --- health: ok + Fehlerpfad (wirft NIE) -------------------------------------

def test_health_ok():
    h = rt.OllamaRuntime(http_get=lambda u: _roh_resp({"version": "0.5.1"})).health()
    assert h.ok is True and h.version == "0.5.1"
    assert h.laufzeit == "ollama" and h.detail == ""


def test_health_fehlerpfad_wirft_nie():
    r = rt.OllamaRuntime()
    # HTTP != 200 ⇒ ok=False + ehrliches detail
    h1 = r.health(http_get=lambda u: _roh_resp({}, status=503))
    assert h1.ok is False and "503" in h1.detail

    # Verbindungsfehler ⇒ ok=False (kein Crash)
    def boom(u):
        raise ConnectionError("refused")
    h2 = r.health(http_get=boom)
    assert h2.ok is False and "refused" in h2.detail and h2.laufzeit == "ollama"


# --- Registry + Fähigkeiten (M2: beim Import angemeldet) ---------------------

def test_ollama_beim_import_registriert_und_faehigkeiten():
    inst = rt.runtime_holen("ollama")
    assert isinstance(inst, rt.OllamaRuntime)
    assert rt.runtime_holen() is inst        # Default == ollama, eine gecachte Instanz
    f = rt.OllamaRuntime.faehigkeiten
    assert f.cd_dialekt == "json_schema" and f.cd_ref_faehig and f.cd_wurzel_array
    assert f.tool_streaming_quelle == "komplett"
    assert f.tools and f.embed and f.kontext_steuerbar and f.batching == "einzeln"


def test_async_zwillinge_wertgleich_zum_sync_kern():
    """Die geerbten to_thread-Zwillinge liefern denselben Wert wie der Sync-Kern
    (kein Override in M2 — native httpx.AsyncClient-Overrides gehören zu M5/M6)."""
    r = rt.OllamaRuntime(
        http_post=lambda u, d: _roh_resp({"embeddings": [[1.0, 2.0]]}),
        http_get=lambda u: _roh_resp({"version": "9.9"}))
    assert asyncio.run(r.a_embed(["x"], modell="bge-m3")) == [[1.0, 2.0]]
    assert asyncio.run(r.a_health()).version == "9.9"
