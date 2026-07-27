"""Dizzis Agent-Loop: natives Tool-Calling über die lokale ``LocalRuntime``.

Warum die Runtime-Naht (docs/62 M4): früher sprach diese Datei Ollamas nativen
``/api/chat`` direkt (nativ statt ``/v1``, weil Ollamas OpenAI-Pfad Tool-Call-
Deltas nicht zuverlässig streamt, Recherche Welle 6). Jetzt liefert die Runtime
``chat_stream`` neutrale ``RuntimeEreignis`` — content-Tokens als ``text`` UND
VOLLSTÄNDIGE Tool-Aufrufe (der Adapter puffert etwaige Deltas). 0-Verhaltens-
wechsel: der Default-Adapter (Ollama) spricht denselben ``/api/chat``-Stream.

Schutzgeländer (Best Practices Welle 6):
- max. ``MAX_ROUNDS`` Werkzeug-Runden, danach erzwungene Antwort ohne Tools
- jedes Tool mit Timeout; Fehler gehen als Text-Ergebnis zurück ans Modell
  (es kann reagieren), nie als Exception in den Stream
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from appkit.runtime import LocalRuntime

from . import providers
from .tools import TOOL_TIMEOUT_S, ToolSpec

MAX_ROUNDS = 4

# Event-Formen: ("t", text) · ("tool", {"name","args"}) — für SSE/UI
AgentEvent = tuple[str, Any]


async def _run_tool(spec: ToolSpec, args: dict) -> str:
    try:
        return await asyncio.wait_for(spec.run(args or {}), timeout=TOOL_TIMEOUT_S)
    except asyncio.TimeoutError:
        return f"Tool {spec.name}: Zeitüberschreitung nach {TOOL_TIMEOUT_S:.0f}s."
    except Exception as e:
        return f"Tool {spec.name} fehlgeschlagen: {e}"


async def stream_agent(messages: list[dict], tools: list[ToolSpec],
                       model: str | None = None,
                       runtime: LocalRuntime | None = None) -> AsyncIterator[AgentEvent]:
    rt = runtime or providers.runtime()
    convo = list(messages)
    by_name = {t.name: t for t in tools}
    tool_payload = [t.payload for t in tools]
    mdl = model or providers.local_model()

    for round_no in range(MAX_ROUNDS + 1):
        with_tools = bool(tools) and round_no < MAX_ROUNDS

        content_parts: list[str] = []
        aufrufe: list[tuple[str, dict]] = []
        echo_calls: list[dict] = []      # assistant.tool_calls fürs Konversations-Echo
        async for ev in rt.chat_stream(convo, modell=mdl,
                                       tools=(tool_payload if with_tools else None)):
            if ev.art == "text":
                if ev.text:
                    content_parts.append(ev.text)
                    yield ("t", ev.text)
            elif ev.art == "tool_aufrufe":
                for ta in ev.tool_aufrufe:      # Aufrufe kommen IMMER komplett (Adapter puffert)
                    aufrufe.append((ta.name, ta.argumente))
                    echo_calls.append(ta.als_ollama())
            elif ev.art == "ende":
                break

        if not aufrufe:
            return  # fertige Antwort

        convo.append({"role": "assistant",
                      "content": "".join(content_parts), "tool_calls": echo_calls})

        # Die Tool-Aufrufe EINER Runde sind voneinander unabhängig ⇒ parallel ausführen
        # (asyncio.gather). Das senkt die Latenz auf das LANGSAMSTE Tool statt der
        # SUMME (mehrere read-only MCP-/Web-Reads). gather erhält die Reihenfolge:
        # ergebnis[i] gehört zu aufruf[i] ⇒ die tool-Messages landen in derselben
        # Folge wie die Aufrufe (das Modell erwartet sie geordnet). Fehler bleiben
        # je Tool isoliert (_run_tool wirft nie ⇒ ein Tool kippt die anderen nicht).
        for name, args in aufrufe:
            yield ("tool", {"name": name, "args": args})

        async def _eines(name: str, args: dict) -> str:
            spec = by_name.get(name)
            if spec is None:
                return f"Unbekanntes Tool: {name}"
            return await _run_tool(spec, args)

        ergebnisse = await asyncio.gather(*(_eines(n, a) for n, a in aufrufe))
        for (name, _args), result in zip(aufrufe, ergebnisse):
            convo.append({"role": "tool", "tool_name": name, "content": result})
