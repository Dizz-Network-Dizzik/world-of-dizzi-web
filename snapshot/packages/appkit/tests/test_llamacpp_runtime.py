"""Adapter-Tests für ``runtime.LlamaCppRuntime`` (Z1.3 / docs/62 §2).

llama.cpp teilt die GESAMTE Transport-/Mapping-/Pufferungs-Logik mit
``VLLMRuntime`` über ``_OpenAIKompatRuntime`` (dort in ``test_vllm_runtime.py``
erschöpfend getestet). Hier NUR der Unterschied: constrained decoding über das
``json_schema``-Feld (statt ``guided_json``), die ehrlichen gbnf-Capability-Flags,
additive Registrierung — plus ein Smoke-Test, dass die geteilte SSE-Delta-
Pufferung auch hier greift.
"""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from appkit import runtime as rt


class _Antwort(BaseModel):
    antwort: str


def _chat_resp(content, status=200):
    class _R:
        status_code = status

        def json(self):
            return {"choices": [{"message": {"content":
                    content if isinstance(content, str) else json.dumps(content)}}]}
    return _R()


async def _sammle(aiter):
    return [ev async for ev in aiter]


def _sse(lines):
    def fabrik(url, payload):
        async def gen():
            for ln in lines:
                yield ln
        return gen()
    return fabrik


def test_strukturiert_nutzt_json_schema_feld_nicht_guided_json():
    """DER Code-Unterschied zu vLLM: llama.cpp erzwingt das Schema über das
    ``json_schema``-Feld (Server konvertiert Schema→GBNF), NICHT ``guided_json``."""
    gesehen = {}

    def fake(url, daten):
        gesehen["url"], gesehen["daten"] = url, daten
        return _chat_resp({"antwort": "ok"})
    res = rt.LlamaCppRuntime().strukturiert("s", "f", schema=_Antwort, modell="m",
                                            http_post=fake)
    assert res is not None and res.antwort == "ok"
    assert gesehen["url"].endswith("/v1/chat/completions")
    assert gesehen["daten"]["json_schema"] == _Antwort.model_json_schema()
    assert "guided_json" not in gesehen["daten"]
    assert gesehen["daten"]["model"] == "m" and gesehen["daten"]["stream"] is False


def test_geteilte_sse_delta_pufferung_greift():
    """Smoke: dieselbe geerbte chat_stream-Pufferung liefert KOMPLETTE Aufrufe
    (Argumente über zwei Fragmente zusammengesetzt)."""
    lines = [
        "data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "c", "function": {"name": "f", "arguments": '{"a":'}}]}}]}),
        "data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '1}'}}]}}]}),
        "data: " + json.dumps({"choices": [{"index": 0, "delta": {},
                                            "finish_reason": "tool_calls"}]}),
        "data: [DONE]",
    ]
    evs = asyncio.run(_sammle(
        rt.LlamaCppRuntime(sse_stream=_sse(lines)).chat_stream([], modell="m")))
    assert [e.art for e in evs] == ["tool_aufrufe", "ende"]
    assert evs[0].tool_aufrufe[0].name == "f"
    assert evs[0].tool_aufrufe[0].argumente == {"a": 1}


def test_llamacpp_registriert_und_faehigkeiten_gbnf():
    inst = rt.runtime_holen("llamacpp")
    assert isinstance(inst, rt.LlamaCppRuntime)
    # teilt die Basis mit vLLM, ist aber eine eigene Klasse
    assert isinstance(inst, rt._OpenAIKompatRuntime)
    assert not isinstance(inst, rt.VLLMRuntime)
    assert rt.DEFAULT_RUNTIME == "ollama"       # weiterhin NICHT Default
    f = rt.LlamaCppRuntime.faehigkeiten
    assert f.cd_dialekt == "gbnf"
    # Konverter löst $ref UND Wurzel-Array (docs/62 §2 ✓/✓) ⇒ True (≠ vLLM guided_json)
    assert f.cd_ref_faehig is True and f.cd_wurzel_array is True
    assert f.tool_streaming_quelle == "deltas"
    assert f.tools is True and f.embed is True
    assert f.batching == "einzeln"              # ≠ vLLM 'kontinuierlich'
    assert f.kontext_steuerbar is False


def test_llamacpp_url_default_und_laufzeit():
    assert rt.LlamaCppRuntime().url == rt.LLAMACPP_STANDARD_URL

    class _Ok:
        status_code = 200
    h = rt.LlamaCppRuntime().health(http_get=lambda u: _Ok())
    assert h.ok is True and h.laufzeit == "llamacpp"
