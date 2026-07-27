"""Deklarative MCP-Tool-Liste von Dizz Healthy — EINE Quelle für den stdio-MCP-
Server (``mcp_server.py``) UND das Per-App-Gateway (``main.py`` →
``appkit.app_gateway``). Reine Daten. ``(tool_name, api_pfad, beschreibung)`` =
read-only GET (Namensraum ``health_``, docs/16 §6). HOCHSENSIBEL: nur Aggregate/
Trends + anstehende Termine + aktive Supplement-Namen, keine Rohwerte."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/stats",
     "Kennzahlen: Messwerte (30 T), aktive Supplements, offene Verletzungen, "
     "Training (7 T), nächster Termin, jüngstes Gewicht."),
    ("gesundheits_trend", "/api/trends?tage=30",
     "Deterministische Messwert-Trends: jüngster Wert, Richtung (steigend/"
     "fallend/stabil), Schnitt, orientierende Referenz-Einordnung — KEINE Diagnose."),
    ("naechste_termine", "/api/termine?kommend=1",
     "Kommende Gesundheits-Termine (Arzt/Vorsorge/Impfung/…) mit Beginn/Ort."),
    ("aktive_supplements", "/api/supplements?aktiv=1",
     "Aktuell eingenommene Supplements (Name, Dosis, Frequenz)."),
]

MCP_INSTRUCTIONS = ("Read-only Einblick in Dizz Healthy: Gesundheits-Trends + Termine + "
                    "Supplements. Beobachten + sanfte Hinweise, NIE Diagnose; Inhalte "
                    "strikt lokal (hochsensibel).")
