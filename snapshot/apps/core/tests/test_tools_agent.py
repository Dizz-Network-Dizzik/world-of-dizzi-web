"""Tests für Tool-Registry, Agent-Loop und L4-Beobachtungen (alles gemockt —
kein Ollama, kein MCP-Subprozess, kein Trading Bot nötig)."""

import json

import pytest

from appkit.runtime import OllamaRuntime

from app.ai import agent, observe, tools
from app.ai.tools import ToolSpec, _schema


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def no_mcp(monkeypatch):
    async def empty():
        return []
    monkeypatch.setattr(tools, "_mcp_toolspecs", empty)


@pytest.fixture
def no_keys(monkeypatch):
    for var in ("DIZZI_NIM_KEY", "DIZZI_GROQ_KEY", "DIZZI_CEREBRAS_KEY"):
        monkeypatch.delenv(var, raising=False)


# --- Registry ----------------------------------------------------------------

@pytest.mark.anyio
async def test_registry_sensitive_keeps_data_local(no_keys, monkeypatch):
    monkeypatch.setenv("DIZZI_NIM_KEY", "x")  # Boost wäre verfügbar …
    names = [t.name for t in await tools.registry(sensitive=True)]
    assert names == ["trading_beobachtungen"]  # … aber sensibel ⇒ nichts geht raus


@pytest.mark.anyio
async def test_registry_normal_without_keys(no_keys):
    names = [t.name for t in await tools.registry(sensitive=False)]
    assert "web_suche" in names
    assert "boost_frage" not in names  # kein Key ⇒ kein Boost-Tool


@pytest.mark.anyio
async def test_registry_boost_with_key(no_keys, monkeypatch):
    monkeypatch.setenv("DIZZI_NIM_KEY", "x")
    names = [t.name for t in await tools.registry(sensitive=False)]
    assert "boost_frage" in names


def test_toolspec_payload_shape():
    spec = ToolSpec("x", "desc", _schema({"a": {"type": "string"}}, ["a"]), None)
    p = spec.payload
    assert p["type"] == "function"
    assert p["function"]["name"] == "x"
    assert p["function"]["parameters"]["required"] == ["a"]


def test_clip():
    assert tools._clip("kurz") == "kurz"
    assert tools._clip("x" * 5000).endswith("…[gekürzt]")


# --- Agent-Loop ----------------------------------------------------------------

def _fake_streams(streams: list[list[dict]]):
    """M4-Naht: statt ``agent._ollama_chat_stream`` wird eine ``LocalRuntime`` in
    ``stream_agent`` injiziert. Dieselben Ollama-NDJSON-Konserven (``streams``) —
    nur als JSON-Zeilen durch die ECHTE ``OllamaRuntime`` (deren NDJSON→Ereignis-
    Abbildung die appkit-Suite ``test_runtime`` prüft). Rückgabe ``(runtime, calls)``;
    ``calls[i]`` = der Payload der i-ten ``chat_stream``-Runde (model/messages/tools —
    ``tools`` nur, wenn gesetzt), byte-gleich zur früheren ``_ollama_chat_stream``-Konserve."""
    calls: list[dict] = []

    def fake_zeilen_stream(url, payload):
        calls.append(payload)

        async def gen():
            for obj in streams[len(calls) - 1]:
                yield json.dumps(obj)
        return gen()

    return OllamaRuntime(zeilen_stream=fake_zeilen_stream), calls


@pytest.mark.anyio
async def test_agent_plain_answer():
    rt, _ = _fake_streams([[
        {"message": {"content": "Hal"}}, {"message": {"content": "lo"}, "done": True},
    ]])
    events = [e async for e in agent.stream_agent(
        [{"role": "user", "content": "hi"}], [], runtime=rt)]
    assert events == [("t", "Hal"), ("t", "lo")]


@pytest.mark.anyio
async def test_agent_tool_round():
    ran: list[dict] = []

    async def runner(args):
        ran.append(args)
        return json.dumps({"roi": -0.4})
    spec = ToolSpec("fleet", "Flotte", _schema({}), runner)
    rt, calls = _fake_streams([
        [{"message": {"tool_calls": [
            {"function": {"name": "fleet", "arguments": {}}}]}, "done": True}],
        [{"message": {"content": "ROI ist -0.4 %"}, "done": True}],
    ])
    events = [e async for e in agent.stream_agent(
        [{"role": "user", "content": "?"}], [spec], runtime=rt)]
    assert ("tool", {"name": "fleet", "args": {}}) in events
    assert ("t", "ROI ist -0.4 %") in events
    assert ran == [{}]
    # 2. Aufruf enthält das Tool-Ergebnis als role=tool
    roles = [m["role"] for m in calls[1]["messages"]]
    assert roles[-1] == "tool"


@pytest.mark.anyio
async def test_agent_tool_error_fed_back():
    async def broken(args):
        raise RuntimeError("kaputt")
    spec = ToolSpec("boom", "explodiert", _schema({}), broken)
    rt, calls = _fake_streams([
        [{"message": {"tool_calls": [
            {"function": {"name": "boom", "arguments": "{}"}}]}, "done": True}],
        [{"message": {"content": "Tool ging nicht."}, "done": True}],
    ])
    events = [e async for e in agent.stream_agent(
        [{"role": "user", "content": "?"}], [spec], runtime=rt)]
    assert ("t", "Tool ging nicht.") in events
    tool_msg = calls[1]["messages"][-1]
    assert "fehlgeschlagen" in tool_msg["content"]


@pytest.mark.anyio
async def test_agent_parallele_tools_einer_runde(monkeypatch):
    """P3.3a: mehrere tool_calls EINER Runde laufen PARALLEL (asyncio.gather) — die
    Ergebnisse werden korrekt zugeordnet (Reihenfolge = tool_calls), ein Fehler in
    einem Tool kippt das andere nicht, und die Gesamtdauer ist ~max statt Summe."""
    import asyncio as _aio

    laufend = {"n": 0, "max": 0}

    async def langsam_a(args):
        laufend["n"] += 1
        laufend["max"] = max(laufend["max"], laufend["n"])
        await _aio.sleep(0.05)          # beide gleichzeitig „in flight" ⇒ max==2
        laufend["n"] -= 1
        return "ERG_A"

    async def kaputt_b(args):
        laufend["n"] += 1               # auch B zählt mit ⇒ erkennt Gleichzeitigkeit
        laufend["max"] = max(laufend["max"], laufend["n"])
        await _aio.sleep(0.05)
        laufend["n"] -= 1
        raise RuntimeError("B kaputt")

    spec_a = ToolSpec("a_tool", "A", _schema({}), langsam_a)
    spec_b = ToolSpec("b_tool", "B", _schema({}), kaputt_b)
    rt, calls = _fake_streams([
        [{"message": {"tool_calls": [
            {"function": {"name": "a_tool", "arguments": {}}},
            {"function": {"name": "b_tool", "arguments": {}}}]}, "done": True}],
        [{"message": {"content": "fertig"}, "done": True}],
    ])
    events = [e async for e in agent.stream_agent(
        [{"role": "user", "content": "?"}], [spec_a, spec_b], runtime=rt)]
    # beide tool-Events emittiert (Reihenfolge der tool_calls)
    tool_events = [e for e in events if e[0] == "tool"]
    assert [e[1]["name"] for e in tool_events] == ["a_tool", "b_tool"]
    # PARALLEL: beide waren gleichzeitig in flight
    assert laufend["max"] == 2
    # zweiter Modell-Aufruf trägt beide Ergebnisse als role=tool, korrekt zugeordnet
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert tool_msgs[0]["tool_name"] == "a_tool" and tool_msgs[0]["content"] == "ERG_A"
    assert tool_msgs[1]["tool_name"] == "b_tool" and "fehlgeschlagen" in tool_msgs[1]["content"]


@pytest.mark.anyio
async def test_agent_max_rounds_forces_answer():
    async def runner(args):
        return "ok"
    spec = ToolSpec("loopy", "ruft immer", _schema({}), runner)
    tool_stream = [{"message": {"tool_calls": [
        {"function": {"name": "loopy", "arguments": {}}}]}, "done": True}]
    final_stream = [{"message": {"content": "Schluss."}, "done": True}]
    rt, calls = _fake_streams([tool_stream] * agent.MAX_ROUNDS + [final_stream])
    events = [e async for e in agent.stream_agent(
        [{"role": "user", "content": "?"}], [spec], runtime=rt)]
    assert events[-1] == ("t", "Schluss.")
    assert "tools" not in calls[-1]  # letzte Runde erzwingt Antwort ohne Tools


# --- L4-Beobachtungen ------------------------------------------------------------

def test_observe_record_and_recent():
    observe.record("dizzi", "tradingbot", {"regime": "trend_up"})
    rows = observe.recent("dizzi", hours=1)
    assert len(rows) == 1
    assert rows[0]["quelle"] == "tradingbot"
    assert rows[0]["daten"]["regime"] == "trend_up"


def test_observe_user_scoped():
    observe.record("dizzi", "tradingbot", {"x": 1})
    assert observe.recent("gast", hours=1) == []
