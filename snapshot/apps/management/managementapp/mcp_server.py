"""MCP-Server von Dizz Management (read-only, stdio) — Dizzis KI-Fenster in die App.

Start: <venv-python> managementapp/mcp_server.py   (im Ordner apps/management)
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).

Tools tragen den App-Namensraum ``management_`` (build_http_mcp präfixt automatisch,
docs/16 §6) — kollisionsfest, sobald ein Host mehrere App-Server bündelt.
Read-only ist der Standard; das Aktions-Tool (Veröffentlichen) läuft NICHT über MCP,
sondern als HITL-Aktion über appkit/actions (Außenwirkung ⇒ Freigabe-Pflicht, K4).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# managementapp auffindbar machen — auch wenn diese Datei als Skript (statt als
# Paket-Modul) läuft: die App-Wurzel (apps/management) auf den Pfad. appkit kommt
# seit dem Monorepo aus packages/ (PYTHONPATH, s. ops/launch_app.ps1).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from appkit.mcp import build_http_mcp  # noqa: E402
from managementapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS  # noqa: E402

BASE = os.environ.get("DIZZ_MANAGEMENT_URL", "http://127.0.0.1:8213")

mcp = build_http_mcp("management", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
