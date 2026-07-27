"""Deklarative MCP-Tool-Liste von Dizz Memory — EINE Quelle für den stdio-MCP-
Server (``mcp_server.py``) UND das Per-App-Gateway (``main.py`` →
``appkit.app_gateway``). Reine Daten. ``MCP_TOOLS`` = read-only GET (Namensraum
``memory_``, docs/16 §6); ``MCP_QUERY_TOOLS`` = parametrische GET-Suche (q=…)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/summary", "Dashboard-Kennzahlen: Notizen, Ordner, Labels, letzte Änderung."),
    ("letzte_notizen", "/api/notizen?limit=15", "Die zuletzt bearbeiteten Notizen (Titel, Auszug, Ordner, Labels)."),
    ("ordner", "/api/ordner", "Ordnerbaum des Wissensspeichers (Name, Eltern, Anzahl Notizen)."),
    ("labels", "/api/labels", "Labels für Cross-Verweise (Name, Farbe, Anzahl)."),
]

MCP_QUERY_TOOLS: list[tuple[str, str, str, str]] = [
    # Rück-Lese (docs/26 §10.1): das zentrale Archiv parametrisch durchsuchen.
    ("suche", "/api/suche", "limit",
     "Wortsuche (FTS5) im Archiv. q=Suchtext, anzahl=max. Treffer; je Treffer Titel/Auszug/Ordner/Labels."),
    ("semantisch", "/api/suche/semantisch", "k",
     "Bedeutungssuche (RAG/Vektor) im Archiv — findet Sinnverwandtes, nicht nur Wörter. q=Suchtext, anzahl=max. Treffer."),
]

MCP_INSTRUCTIONS = ("Read-only Einblick in Dizz Memory: Notizen, Ordner, Labels + Volltext-/Bedeutungssuche "
                    "im zentralen Archiv. Sensible App — private Inhalte bleiben lokal.")
