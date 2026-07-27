"""Deklarative MCP-Tool-Liste von Dizz News — EINE Quelle für (a) den stdio-MCP-
Server (``mcp_server.py``, Core-Agent) und (b) das per-App-MCP-Gateway
(``main.py`` → ``appkit.app_gateway``, Standalone-Betrieb). Reine Daten — kein
MCP-Import ⇒ die laufende App liest sie ohne MCP-Abhängigkeit ein.

Jeder Eintrag ``(tool_name, api_pfad, beschreibung)`` = read-only GET auf die
App-API (Namensraum ``news_`` wird automatisch gesetzt, docs/16 §6)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/summary", "Dashboard-Kennzahlen: Quellen, Artikel, letzter Abruf."),
    ("letzte_artikel", "/api/artikel?limit=15", "Die neuesten Artikel (Titel, Link, Quelle, Sektor)."),
    ("quellen", "/api/quellen", "Kuratierte Nachrichten-Quellen mit Sektor."),
]

MCP_INSTRUCTIONS = "Read-only Einblick in Dizz News: kuratierte Quellen, aktuelle Artikel."
