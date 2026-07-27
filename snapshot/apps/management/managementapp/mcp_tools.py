"""Deklarative MCP-Tool-Liste von Dizz Management — EINE Quelle für den stdio-MCP-
Server (``mcp_server.py``) UND das Per-App-Gateway (``main.py`` →
``appkit.app_gateway``). Reine Daten. ``(tool_name, api_pfad, beschreibung)`` =
read-only GET (Namensraum ``management_``, docs/16 §6)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/stats",
     "Kennzahlen: Kanäle (gesamt/verbunden), aktive Social-Bots, Entwürfe, "
     "geplante Posts, nächster Zeitplan-Slot."),
    ("redaktionsplan", "/api/zeitplan",
     "Redaktionsplan: geplante Posts (zeitlich sortiert) + offene Entwürfe."),
    ("kanal_status", "/api/kanaele",
     "Kanäle mit Plattform, Handle und Verbindungsstatus (getrennt/verbunden/pausiert)."),
    ("social_bots", "/api/bots?aktiv=1",
     "Aktive Social-Media-Bots (Themen-/Marken-Profile): Name, Thema, Ton, Zielgruppe."),
    ("auswertung", "/api/analytics",
     "Redaktionelle Auswertung (lokal): KPIs, Posts je Plattform, Status-Verteilung, "
     "Posting-Zeiten-Heatmap, beste Zeiten. Reichweite/Engagement v1 DORMANT (Gesetz 5)."),
]

MCP_INSTRUCTIONS = ("Read-only Einblick in Dizz Management: Kanäle + Social-Bots + "
                    "Redaktionsplan. Beobachten + vorschlagen; Veröffentlichen NIE "
                    "eigenmächtig (HITL-Freigabe, K4). Inhalte lokal-first (sensibel).")
