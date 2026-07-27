"""Deklarative MCP-Tool-Liste von Dizz Money — EINE Quelle für (a) den stdio-MCP-
Server (``mcp_server.py``, Core-Agent) und (b) das per-App-MCP-Gateway
(``main.py`` → ``appkit.app_gateway``, Standalone). Reine Daten — kein MCP-Import.

``(tool_name, api_pfad, beschreibung)`` = read-only GET (Namensraum ``finanzen_``,
docs/16 §6). Schreiben bleibt HITL in der App."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("nettovermoegen", "/api/summary", "Nettovermögen + Konten-Anzahl (Kachel)."),
    ("kontostand", "/api/konten", "Alle Konten mit ihren Salden (read-only)."),
    ("cashflow", "/api/auswertung/cashflow",
     "Cashflow (Einnahmen/Ausgaben/Saldo + je Kategorie) über alle Buchungen."),
    ("vermoegen", "/api/auswertung/vermoegen",
     "Vermögensübersicht je Konto + Nettovermögen je Währung."),
    ("lebenszeichen", "/api/health", "Health-Status von Dizz Money."),
]

MCP_INSTRUCTIONS = "Read-only Einblick in die Finanzen (Dizz Money). Keine Buchungen."
