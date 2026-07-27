"""MCP-Server von Dizz Admin (read-only, stdio) — Dizzis KI-Fenster in die
vereinte Verwaltung. Start: <venv-python> adminapp/mcp_server.py (im admin-Ordner).
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).

Tools tragen den App-Namensraum ``admin_`` (build_http_mcp präfixt automatisch,
docs/16 §6). Read-only ist Standard; Aktions-Tools (Rechnung stellen …) folgen
mit Human-in-the-Loop über appkit/actions (K4). SENSIBEL (Geschäfts-/Steuerdaten):
die Tools liefern AGGREGATE/Listen, die Dizzi für Erinnerungen + Überblick braucht.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# appkit auffindbar machen, auch als Skript: admin-Wurzel (mit appkit/) auf den Pfad.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adminapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS  # noqa: E402
from appkit.mcp import build_http_mcp  # noqa: E402

BASE = os.environ.get("DIZZ_ADMIN_URL", "http://127.0.0.1:8222")

# Tool-Liste = die geteilte Deklaration (mcp_tools.py) — dieselbe Quelle nutzt das
# per-App-MCP-Gateway in main.py (Standalone-Betrieb, docs/31 §7).
mcp = build_http_mcp("admin", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
