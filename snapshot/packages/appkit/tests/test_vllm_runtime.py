"""Adapter-Tests für ``runtime.VLLMRuntime`` (Z1.3 / docs/62 §2).

Server-frei: ALLE I/O-Nähte (``http_post``/``http_get`` sync, ``sse_stream``
async) sind gefakt — wie der Ollama-Adapter (M2), den anfangs auch niemand rief.
Beweist die OpenAI-``/v1``-Wire-Form + die Fehler-Verträge, und — das Kernstück —
dass die SSE-Tool-DELTAS adapter-intern zu KOMPLETTEN ``ToolAufruf`` gepuffert
werden (nie Deltas nach außen) und das Ollama-nativ→OpenAI-Nachrichten-Mapping
stimmt (``tool_name`` → ``tool_call_id``). async über ``asyncio.run`` (keine
pytest-asyncio-Annahme, wie ``test_ollama_runtime.py``).
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


def _chat_resp(content, status=200):
    """Nicht-streamende /v1/chat/completions-Antwort (strukturiert): OpenAI-Form
    ``choices[0].message.content`` = JSON-Dump (bzw. roher String)."""
    class _R:
        status_code = status

        def json(self):
            return {"choices": [{"message": {"content":
                    content if isinstance(content, str) else json.dumps(content)}}]}
    return _R()


def _roh_resp(payload, status=200):
    """Roher-Body-Antwort-Fake für embed/modelle/health."""
    class _R:
        status_code = status

        def json(self):
            return payload
    return _R()


async def _sammle(aiter):
    return [ev async for ev in aiter]


def _sse(lines):
    """``sse_stream``-Fake: AsyncIterator über feste SSE-``data:``-Zeilen."""
    def fabrik(url, payload):
        async def gen():
            for ln in lines:
                yield ln
        return gen()
    return fabrik


def _frame(obj):
    """Ein SSE-``data:``-Frame aus einem Chat-Completion-Chunk."""
    return "data: " + json.dumps(obj)


# --- strukturiert: guided_json + Validierung + Fehler-Verträge ---------------

def test_strukturiert_guided_json_und_validierung():
    gesehen = {}

    def fake(url, daten):
        gesehen["url"], gesehen["daten"] = url, daten
        return _chat_resp({"antwort": "Hallo", "belege": ["A"]})

    res = rt.VLLMRuntime().strukturiert(
        "sys", "frage", schema=_Antwort, modell="m", http_post=fake)
    assert res is not None and res.antwort == "Hallo" and res.belege == ["A"]
    assert gesehen["url"].endswith("/v1/chat/completions")
    # vLLM: guided_json (NICHT die strikte response_format-Schiene) trägt das Schema
    assert gesehen["daten"]["guided_json"] == _Antwort.model_json_schema()
    assert "response_format" not in gesehen["daten"]
    assert gesehen["daten"]["model"] == "m"
    assert gesehen["daten"]["stream"] is False
    assert [msg["role"] for msg in gesehen["daten"]["messages"]] == ["system", "user"]


def test_strukturiert_fehlerpfade_ergeben_none():
    r = rt.VLLMRuntime()
    # HTTP != 200 ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _chat_resp({}, status=500)) is None

    # Poster wirft ⇒ None (fail-safe)
    def boom(u, d):
        raise OSError("vllm weg")
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m", http_post=boom) is None

    # schema-ungültig (Pflichtfeld fehlt) ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _chat_resp({"falsch": 1})) is None
    # gar kein JSON ⇒ None
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m",
                          http_post=lambda u, d: _chat_resp("kein json")) is None


def test_strukturiert_temperature_positional_und_strikt():
    gesehen = {}

    def fake(url, daten):
        gesehen["t"] = daten["temperature"]
        return _chat_resp({"antwort": "x"})
    rt.VLLMRuntime().strukturiert("s", "f", schema=_Antwort, modell="m",
                                  http_post=fake, temperature=0.3)
    assert gesehen["t"] == 0.3

    # positional-Kompatibilität zur App-Fake-Konvention (def fake(url, json))
    def fake_json(url, json):
        return _chat_resp({"antwort": json["model"]})
    res = rt.VLLMRuntime().strukturiert("s", "f", schema=_Antwort, modell="qwen",
                                        http_post=fake_json)
    assert res is not None and res.antwort == "qwen"

    # strikt=True reicht die Original-Exception durch (quick_chat-Parität)
    def boom(u, d):
        raise OSError("weg")
    with pytest.raises(OSError):
        rt.VLLMRuntime().strukturiert("s", "f", schema=_Antwort, modell="m",
                                      http_post=boom, strikt=True)


def test_strukturiert_instanz_naht_und_verlauf():
    # Instanz-Naht (http_post via __init__)
    r = rt.VLLMRuntime(http_post=lambda u, d: _chat_resp({"antwort": "inst"}))
    assert r.strukturiert("s", "f", schema=_Antwort, modell="m").antwort == "inst"

    # verlauf wird ZWISCHEN system und user gespleißt (memory-Vault-Chat-Parität)
    gesehen = {}

    def fake(url, daten):
        gesehen["messages"] = daten["messages"]
        return _chat_resp({"antwort": "x"})
    verlauf = [{"role": "user", "content": "davor"},
               {"role": "assistant", "content": "antwort davor"}]
    rt.VLLMRuntime().strukturiert("SYS", "USER", schema=_Antwort, modell="m",
                                  http_post=fake, verlauf=verlauf)
    assert [m["role"] for m in gesehen["messages"]] == \
        ["system", "user", "assistant", "user"]
    assert gesehen["messages"][1:3] == verlauf
    assert gesehen["messages"][0]["content"] == "SYS"
    assert gesehen["messages"][-1]["content"] == "USER"


# --- chat_stream: text/ende + SSE-Delta-Pufferung (Kernstück) ----------------

def test_chat_stream_text_chunks_und_ende_nutzung():
    lines = [
        _frame({"choices": [{"index": 0, "delta": {"content": "Hal"},
                             "finish_reason": None}]}),
        "",                       # Blank-Zeile übersprungen
        ": keepalive",            # SSE-Kommentar ignoriert
        _frame({"choices": [{"index": 0, "delta": {"content": "lo"},
                             "finish_reason": None}]}),
        _frame({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
        _frame({"choices": [], "usage": {"prompt_tokens": 3,
                                         "completion_tokens": 2, "total_tokens": 5}}),
        "data: [DONE]",
    ]
    r = rt.VLLMRuntime(sse_stream=_sse(lines))
    evs = asyncio.run(_sammle(r.chat_stream([{"role": "user", "content": "?"}], modell="m")))
    assert [e.art for e in evs] == ["text", "text", "ende"]
    assert "".join(e.text for e in evs if e.art == "text") == "Hallo"
    # ende.nutzung = rohe usage-Zähler (aus dem include_usage-Chunk)
    assert evs[-1].nutzung == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


def test_chat_stream_tool_deltas_werden_zu_kompletten_aufrufen_gepuffert():
    """DAS Kernstück: vLLM streamt Tool-Argumente index-fragmentiert (OpenAI-Delta-
    Stil); der Adapter PUFFERT bis komplett und liefert nach außen NIE Deltas,
    sondern EIN ``tool_aufrufe``-Ereignis mit KOMPLETTEN ``ToolAufruf``."""
    lines = [
        # Aufruf 0: Name zuerst, Argumente über 3 Fragmente verteilt
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_a", "type": "function",
             "function": {"name": "suche", "arguments": ""}}]}}]}),
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '{"q": '}}]}}]}),
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '"x"}'}}]}}]}),
        # Aufruf 1 (parallel, anderer Index): komplett in einem Fragment
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 1, "id": "call_b", "type": "function",
             "function": {"name": "rechne", "arguments": '{"a": 1}'}}]}}]}),
        _frame({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
        _frame({"choices": [], "usage": {"total_tokens": 18}}),
        "data: [DONE]",
    ]
    evs = asyncio.run(_sammle(
        rt.VLLMRuntime(sse_stream=_sse(lines)).chat_stream([], modell="m")))
    assert [e.art for e in evs] == ["tool_aufrufe", "ende"]
    tool_ev = evs[0]
    # KOMPLETT + normalisiert (String-Fragmente → geparste dicts), Reihenfolge erhalten
    assert [t.name for t in tool_ev.tool_aufrufe] == ["suche", "rechne"]
    assert [t.argumente for t in tool_ev.tool_aufrufe] == [{"q": "x"}, {"a": 1}]
    assert [t.id for t in tool_ev.tool_aufrufe] == ["call_a", "call_b"]
    # als_ollama-Rückform fürs Konversations-Echo (agent.py)
    assert tool_ev.tool_aufrufe[0].als_ollama() == {
        "function": {"name": "suche", "arguments": {"q": "x"}}}
    assert evs[-1].nutzung == {"total_tokens": 18}


def test_chat_stream_kaputte_tool_argumente_werden_leeres_dict():
    lines = [
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "c", "function": {"name": "kaputt",
             "arguments": "kein-json"}}]}}]}),
        _frame({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
        "data: [DONE]",
    ]
    evs = asyncio.run(_sammle(
        rt.VLLMRuntime(sse_stream=_sse(lines)).chat_stream([], modell="m")))
    tool_ev = next(e for e in evs if e.art == "tool_aufrufe")
    assert tool_ev.tool_aufrufe[0].name == "kaputt"
    assert tool_ev.tool_aufrufe[0].argumente == {}      # kaputtes JSON ⇒ {}


def test_chat_stream_tools_ohne_finish_reason_defensiv_geflusht():
    """Endet der Stream ohne finish_reason (nur [DONE]/Abriss), werden gepufferte
    Tools trotzdem VOR dem ``ende`` geflusht (defensiv, docs/62 §2 'puffert defensiv')."""
    lines = [
        _frame({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "c1", "function": {"name": "t", "arguments": "{}"}}]}}]}),
        "data: [DONE]",
    ]
    evs = asyncio.run(_sammle(
        rt.VLLMRuntime(sse_stream=_sse(lines)).chat_stream([], modell="m")))
    assert [e.art for e in evs] == ["tool_aufrufe", "ende"]
    assert evs[0].tool_aufrufe[0].name == "t" and evs[0].tool_aufrufe[0].argumente == {}


def test_chat_stream_payload_traegt_tools_optionen_stream_options_und_mapping():
    gesehen = {}

    def spion(url, payload):
        gesehen["url"], gesehen["payload"] = url, payload

        async def gen():
            yield _frame({"choices": [{"index": 0, "delta": {},
                                       "finish_reason": "stop"}]})
            yield "data: [DONE]"
        return gen()

    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "frage"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "suche", "arguments": {"q": "x"}}}]},
        {"role": "tool", "tool_name": "suche", "content": "ergebnis"},
    ]
    asyncio.run(_sammle(rt.VLLMRuntime(sse_stream=spion).chat_stream(
        messages, modell="m", tools=[{"type": "function"}],
        optionen={"temperature": 0.2, "max_tokens": 128})))
    pl = gesehen["payload"]
    assert gesehen["url"].endswith("/v1/chat/completions")
    assert pl["model"] == "m" and pl["stream"] is True
    assert pl["stream_options"] == {"include_usage": True}      # ende.nutzung-Anker
    assert pl["tools"] == [{"type": "function"}]
    assert pl["temperature"] == 0.2 and pl["max_tokens"] == 128  # optionen durchgereicht
    mapped = pl["messages"]
    # system/user unverändert durchgereicht
    assert mapped[0] == {"role": "system", "content": "S"}
    assert mapped[1] == {"role": "user", "content": "frage"}
    # assistant.tool_calls: Ollama-Form → OpenAI-Form (id synthetisiert, args STRING)
    asst = mapped[2]
    assert asst["role"] == "assistant"
    tc = asst["tool_calls"][0]
    assert tc["type"] == "function" and tc["function"]["name"] == "suche"
    assert tc["function"]["arguments"] == json.dumps({"q": "x"})   # dict → JSON-String
    cid = tc["id"]
    assert cid                                # nicht-leere synthetische id
    # tool-Ergebnis: tool_name → tool_call_id (über denselben Namen korreliert)
    assert mapped[3] == {"role": "tool", "content": "ergebnis", "tool_call_id": cid}


def test_chat_stream_wirft_bei_transportfehler():
    def kaputt(url, payload):
        async def gen():
            raise ConnectionError("engine weg")
            yield ""      # unreachable — macht gen() zum async-Generator
        return gen()
    with pytest.raises(ConnectionError):
        asyncio.run(_sammle(
            rt.VLLMRuntime(sse_stream=kaputt).chat_stream([], modell="m")))


def test_chat_stream_wirft_bei_kaputtem_frame():
    """Ein kaputter ``data:``-Frame = Engine-Fehler ⇒ WIRFT (Vertrag: ein Stream
    degradiert nicht ehrlich zu None; die Failover-Politik liegt beim Aufrufer)."""
    with pytest.raises(json.JSONDecodeError):
        asyncio.run(_sammle(
            rt.VLLMRuntime(sse_stream=_sse(["data: {kaputt"])).chat_stream([], modell="m")))


# --- Nachrichten-Mapping (Ollama-nativ → OpenAI), inkl. FIFO-Korrelation ------

def test_nachrichten_mapping_formen_und_fifo_korrelation():
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "u", "name": "beispiel"},   # optionaler name bleibt
        {"role": "assistant", "content": "denk",
         "tool_calls": [
             {"function": {"name": "suche", "arguments": {"q": "a"}}},
             {"function": {"name": "suche", "arguments": {"q": "b"}}}]},   # 2× gleicher Name
        {"role": "tool", "tool_name": "suche", "content": "r-a"},
        {"role": "tool", "tool_name": "suche", "content": "r-b"},
    ]
    out = rt._zu_openai_nachrichten(msgs)
    assert out[0] == {"role": "system", "content": "S"}
    assert out[1] == {"role": "user", "content": "u", "name": "beispiel"}
    assert out[2]["content"] == "denk"
    calls = out[2]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["suche", "suche"]
    # Argumente dict → JSON-STRING; type + nicht-leere id je Aufruf
    assert calls[0]["function"]["arguments"] == json.dumps({"q": "a"})
    assert all(c["type"] == "function" and c["id"] for c in calls)
    assert calls[0]["id"] != calls[1]["id"]
    # FIFO-Korrelation je Name: erstes Ergebnis → erster Aufruf, zweites → zweiter
    assert out[3] == {"role": "tool", "content": "r-a", "tool_call_id": calls[0]["id"]}
    assert out[4] == {"role": "tool", "content": "r-b", "tool_call_id": calls[1]["id"]}


def test_nachrichten_mapping_respektiert_vorhandene_openai_form():
    """Trägt eine Nachricht bereits OpenAI-Form (explizite id / tool_call_id),
    bleibt sie erhalten (String-Args unverändert, explizite tool_call_id gewinnt)."""
    msgs = [
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call_X", "type": "function",
                         "function": {"name": "f", "arguments": '{"a": 1}'}}]},
        {"role": "tool", "tool_call_id": "call_X", "content": "ok"},
    ]
    out = rt._zu_openai_nachrichten(msgs)
    assert out[0]["tool_calls"][0]["id"] == "call_X"
    assert out[0]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'   # String bleibt
    assert out[1]["tool_call_id"] == "call_X"


# --- embed: leer/gültig(Reihenfolge über index)/Fehler ------------------------

def test_embed_leer_macht_keinen_call():
    def darf_nicht(u, d):
        raise AssertionError("embed([]) darf keinen Netz-Call machen")
    assert rt.VLLMRuntime(http_post=darf_nicht).embed([], modell="bge-m3") == []


def test_embed_gueltig_index_reihenfolge_und_fehler():
    gesehen = {}

    def ok(u, d):
        gesehen["url"], gesehen["daten"] = u, d
        # bewusst verdreht (index 1 vor 0) — der Adapter ordnet nach index
        return _roh_resp({"object": "list", "data": [
            {"embedding": [0.3, 0.4], "index": 1},
            {"embedding": [0.1, 0.2], "index": 0}]})
    r = rt.VLLMRuntime()
    assert r.embed(["a", "b"], modell="bge-m3", http_post=ok) == [[0.1, 0.2], [0.3, 0.4]]
    assert gesehen["url"].endswith("/v1/embeddings")
    assert gesehen["daten"] == {"model": "bge-m3", "input": ["a", "b"]}

    # HTTP != 200 ⇒ None
    assert r.embed(["a"], modell="m",
                   http_post=lambda u, d: _roh_resp({}, status=500)) is None

    # Poster wirft ⇒ None (fail-safe)
    def boom(u, d):
        raise OSError("weg")
    assert r.embed(["a"], modell="m", http_post=boom) is None


# --- modelle: /v1/models-Mapping + Fehler ⇒ [] --------------------------------

def test_modelle_mapping_v1_models():
    body = {"object": "list", "data": [
        {"id": "meta-llama/Llama-3-8B-Instruct", "object": "model",
         "owned_by": "vllm", "created": 123},
        {"id": "bge-m3"},
        {"object": "model"},          # ohne id ⇒ übersprungen
    ]}
    ms = rt.VLLMRuntime(http_get=lambda u: _roh_resp(body)).modelle()
    assert [m.name for m in ms] == ["meta-llama/Llama-3-8B-Instruct", "bge-m3"]
    # /v1/models trägt keine Größe ⇒ None (ehrlich, docs/62 §2 „nur IDs")
    assert ms[0].groesse_bytes is None
    assert ms[0].details == {"object": "model", "owned_by": "vllm", "created": 123}
    assert ms[1].details == {}


def test_modelle_fehler_ergibt_leer():
    r = rt.VLLMRuntime()
    assert r.modelle(http_get=lambda u: _roh_resp({}, status=503)) == []

    def boom(u):
        raise OSError("weg")
    assert r.modelle(http_get=boom) == []


# --- health: ok(200, leerer Body) + Fehlerpfad (wirft NIE) --------------------

def test_health_ok_ohne_version():
    # vLLM /health = leerer 200 ⇒ ok=True, version=None (kein Body gelesen)
    h = rt.VLLMRuntime(http_get=lambda u: _roh_resp({}, status=200)).health()
    assert h.ok is True and h.version is None
    assert h.laufzeit == "vllm" and h.detail == ""


def test_health_fehlerpfad_wirft_nie():
    r = rt.VLLMRuntime()
    # HTTP != 200 ⇒ ok=False + ehrliches detail
    h1 = r.health(http_get=lambda u: _roh_resp({}, status=503))
    assert h1.ok is False and "503" in h1.detail and h1.laufzeit == "vllm"

    # Verbindungsfehler ⇒ ok=False (kein Crash)
    def boom(u):
        raise ConnectionError("refused")
    h2 = r.health(http_get=boom)
    assert h2.ok is False and "refused" in h2.detail


# --- Registry + Fähigkeiten (additiv angemeldet, NICHT Default) ---------------

def test_vllm_registriert_aber_nicht_default():
    inst = rt.runtime_holen("vllm")
    assert isinstance(inst, rt.VLLMRuntime)
    assert rt.runtime_holen("vllm") is inst              # eine gecachte Instanz je Name
    # Default bleibt ollama — vllm ist NICHT Default ⇒ 0 Verhaltenswechsel
    assert rt.DEFAULT_RUNTIME == "ollama"
    assert not isinstance(rt.runtime_holen(), rt.VLLMRuntime)


def test_vllm_faehigkeiten_ehrlich():
    f = rt.VLLMRuntime.faehigkeiten
    assert f.cd_dialekt == "guided_json" and f.cd_ref_faehig is True
    # bewusst konservativ False (docs/62 §2 führt guided_json als ✓ — hier under-
    # claimed; Unterschied zu Ollama, das True deklariert). Siehe Klassen-Docstring.
    assert f.cd_wurzel_array is False
    assert f.tool_streaming_quelle == "deltas"        # ≠ Ollama 'komplett'
    assert f.tools is True and f.embed is True
    assert f.kontext_steuerbar is False               # server-fix (max_model_len)
    assert f.batching == "kontinuierlich"             # continuous batching


def test_vllm_url_default_und_explizit():
    assert rt.VLLMRuntime().url == rt.VLLM_STANDARD_URL
    assert rt.VLLMRuntime("http://gpu-box:8000").url == "http://gpu-box:8000"


def test_async_zwillinge_wertgleich_zum_sync_kern():
    """Die geerbten to_thread-Zwillinge liefern denselben Wert wie der Sync-Kern
    (kein Override — native httpx.AsyncClient-Overrides erst bei echtem async-Konsum)."""
    r = rt.VLLMRuntime(
        http_post=lambda u, d: _roh_resp({"data": [{"embedding": [1.0, 2.0], "index": 0}]}),
        http_get=lambda u: _roh_resp({}, status=200))
    assert asyncio.run(r.a_embed(["x"], modell="bge-m3")) == [[1.0, 2.0]]
    assert asyncio.run(r.a_health()).ok is True
    assert asyncio.run(r.a_health()).laufzeit == "vllm"
