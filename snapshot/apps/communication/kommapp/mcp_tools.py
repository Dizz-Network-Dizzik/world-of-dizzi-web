"""Deklarative read-only MCP-Tool-Liste von Dizz Communication — EINE Quelle für den
stdio-MCP-Server (``mcp_server.py``) UND das Per-App-Gateway (``main.py`` →
``appkit.app_gateway``). Reine Daten. HOECHST-App: NUR Metadaten/Zähler/Kopfzeilen,
NIE Nachrichten-Volltexte. Das HITL-Aktions-Tool (mail_senden_vorschlagen) lebt
weiter in ``mcp_server.py`` — das read-only Gateway trägt es bewusst NICHT.

``(tool_name, api_pfad, beschreibung)`` = read-only GET (Namensraum ``kommunikation_``)."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("kachel_stats", "/api/summary",
     "Dashboard-Kennzahlen: Konten, Konversationen, Nachrichten, Ungelesen."),
    ("posteingang_uebersicht", "/api/konversationen?limit=20",
     "Konversations-Übersicht: Titel, Zähler (gesamt/ungelesen), letzter "
     "Absender, Zeit — KEINE Nachrichten-Volltexte."),
    ("ungelesen", "/api/mcp/ungelesen",
     "Ungelesen-Zähler gesamt und je Konto (Kanal)."),
    ("letzte_nachrichten", "/api/mcp/letzte_nachrichten?limit=15",
     "Neueste Nachrichten als Metadaten (Betreff/Absender/Datum/Ordner/"
     "gelesen) — OHNE Inhalte."),
    ("konten", "/api/konten",
     "Eingerichtete Kommunikations-Konten (ohne Geheimnisse)."),
]

MCP_INSTRUCTIONS = ("Read-only Einblick in Dizz Communication (hoechst-sensibel): "
                    "NUR Metadaten/Zähler/Kopfzeilen, nie Nachrichten-Inhalte. "
                    "Ein einziges Aktions-Tool (mail_senden_vorschlagen) SCHLÄGT "
                    "VOR — die Wirkung verlangt immer eine menschliche Freigabe.")
