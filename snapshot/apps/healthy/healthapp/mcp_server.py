"""MCP-Server von Dizz Healthy (read-only, stdio) — Dizzis KI-Fenster in die App.

Start: <venv-python> healthapp/mcp_server.py   (im health-Ordner)
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).

Tools tragen den App-Namensraum ``health_`` (build_http_mcp präfixt automatisch,
docs/16 §6) — kollisionsfest, sobald ein Host mehrere App-Server bündelt.
Read-only ist der Standard; Aktions-Tools (Termin/Wert anlegen) folgen mit
Human-in-the-Loop über appkit/actions (K4).

HOCHSENSIBEL: die Tools liefern bewusst AGGREGATE/Trends + anstehende Termine +
aktive Supplement-Namen — die Gesundheits-Beobachtung, die Dizzi für sanfte
Hinweise braucht, ohne dass jeder Rohwert über den Bus geht.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# appkit auffindbar machen — auch wenn diese Datei als Skript (statt als
# Paket-Modul) läuft: die health-Wurzel (mit ``appkit/``) auf den Pfad.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from appkit.mcp import build_http_mcp  # noqa: E402
from healthapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS  # noqa: E402

BASE = os.environ.get("DIZZ_HEALTH_URL", "http://127.0.0.1:8217")

mcp = build_http_mcp("health", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
