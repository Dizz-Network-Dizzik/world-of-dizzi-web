"""Deklarative MCP-Tool-Liste der Referenz-App — EINE Quelle für (a) den stdio-MCP-
Server (``mcp_server.py``, Core-Agent/Connector) und (b) das per-App-MCP-Gateway
(``main.py`` → ``appkit.app_gateway``, Standalone-Betrieb). Reine Daten — kein
MCP-Import. **Muster für jede neue App** (Kopiervorlage).

``(tool_name, api_pfad, beschreibung)`` = read-only GET; build_http_mcp/app_gateway
präfixen den Namen automatisch in den App-Namensraum ``refapp_`` (docs/16 §6)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/summary", "Dashboard-Kennzahlen der Referenz-App."),
    ("lebenszeichen", "/api/health", "Health-Status der Referenz-App."),
]

MCP_INSTRUCTIONS = "Read-only Einblick in die Referenz-App des Dizzi-App-Vertrags."
