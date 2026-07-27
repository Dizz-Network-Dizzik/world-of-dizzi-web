"""MCP-Helfer des App-Vertrags — read-only Tools aus der eigenen HTTP-API.

Muster wie der Trading-Bot-Connector (connectors/tradingbot/mcp_server.py):
der MCP-Server läuft als eigener stdio-Prozess und liest die HTTP-API der
laufenden App. Vorteil: ein Absturz des MCP-Prozesses berührt die App nie,
und die Tools sind automatisch so aktuell wie die API.

K4 (KI-Interaktions-Protokoll) erweitert dieses Modul später um Aktions-Tools
mit Human-in-the-Loop-Stufen und Event-Push — read-only bleibt der Standard.

Namensraum (docs/16 §6): jedes Tool trägt den App-Präfix ``<app_id>_<tool>``,
damit generische Namen (``summary``/``status``/``alerts``) nicht kollidieren,
sobald EIN Host (Leading-Aggregator, Core-Agent) mehrere App-Server bündelt.
``build_http_mcp`` setzt den Präfix automatisch; direkte FastMCP-Server nutzen
``namespaced()`` bzw. benennen ihre Tool-Funktionen bereits präfixiert.

WICHTIG für jeden MCP-Server: niemals auf stdout schreiben (zerstört JSON-RPC).
"""

from __future__ import annotations

from typing import Any


def namespaced(app_id: str, tool: str) -> str:
    """MCP-Tool-Name im App-Namensraum: ``<app_id>_<tool>`` (docs/16 §6).

    Verhindert Namenskollisionen, sobald ein Host mehrere App-MCP-Server
    gleichzeitig lädt — ohne Präfix wären ``summary``/``status`` doppeldeutig.
    Der Präfix ist die kanonische Manifest-``id`` (garantiert eindeutig,
    mappingsfrei). Idempotent: ein bereits korrekt präfixierter Name bleibt
    unverändert (kein ``news_news_briefing``).
    """
    tool = tool.strip().lstrip("_")
    prefix = f"{app_id}_"
    return tool if tool.startswith(prefix) else prefix + tool


def build_http_mcp(name: str, base_url: str,
                   tools: list[tuple[str, str, str]],
                   instructions: str = "",
                   query_tools: list[tuple[str, str, str, str]] | None = None) -> Any:
    """Baut einen read-only MCP-Server über der HTTP-API der App.

    ``tools`` = Liste aus (tool_name, api_pfad, beschreibung); jedes Tool macht
    GET <base_url><api_pfad> und liefert das JSON (bzw. eine Fehler-Struktur,
    wenn die App offline ist — der Host soll das erklärt bekommen, nicht crashen).

    ``query_tools`` = PARAMETRISCHE Tools aus (tool_name, api_pfad, query_param,
    beschreibung): das Tool nimmt einen Suchtext ``q`` (+ optional ``anzahl``)
    und macht GET <base_url><api_pfad>?q=…&<query_param>=<anzahl>. So fragt z. B.
    der Core-Agent das zentrale Memory-Archiv parametrisch ab (docs/26 §10.1
    Rück-Lese: ``memory_suche``/``memory_semantisch``). ``query_param`` ist der
    seitige Mengen-Parameter (Memory: ``limit`` für FTS, ``k`` für semantisch).

    ``name`` ist die App-``id`` und zugleich der Tool-Namensraum: jeder
    ``tool_name`` wird automatisch zu ``<name>_<tool_name>`` präfixiert
    (``namespaced``), damit Apps kurze Namen deklarieren können und der
    Kollisionsschutz trotzdem garantiert ist (docs/16 §6).
    """
    import httpx
    from fastmcp import FastMCP  # lazy: nur MCP-Prozesse brauchen fastmcp

    mcp = FastMCP(name, instructions=instructions)

    # Tool-Annotationen (MCP 2025-06-18, docs/50 P3.2): JEDES hier gebaute Tool ist
    # ein reiner GET-Leser der lokalen App-API ⇒ read-only, nicht destruktiv,
    # idempotent, kein „open world" (kein Internet). Exakt, kein Raten — Hosts/
    # externe Agenten dürfen sie ohne Rückfrage aufrufen.
    _READONLY_ANN = {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False}

    def _get(path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = httpx.get(f"{base_url}{path}", params=params, timeout=5.0)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": f"App '{name}' nicht erreichbar ({path}): {e}"}

    def _register(tool_name: str, path: str, description: str) -> None:
        # Closure-Fabrik: bindet path je Tool (keine späte Bindung in der Schleife).
        def _tool() -> Any:
            return _get(path)
        _tool.__name__ = tool_name
        _tool.__doc__ = description
        mcp.tool(_tool, annotations=dict(_READONLY_ANN))

    def _register_query(tool_name: str, path: str, query_param: str,
                        description: str) -> None:
        def _tool(q: str, anzahl: int = 8) -> Any:
            return _get(path, params={"q": q, query_param: anzahl})
        _tool.__name__ = tool_name
        _tool.__doc__ = description
        mcp.tool(_tool, annotations=dict(_READONLY_ANN))

    for tool_name, path, description in tools:
        _register(namespaced(name, tool_name), path, description)
    for tool_name, path, query_param, description in (query_tools or []):
        _register_query(namespaced(name, tool_name), path, query_param, description)
    return mcp
