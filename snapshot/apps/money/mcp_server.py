"""MCP-Server von Dizz Money (read-only, stdio) — Dizzi befragt die Finanzen.

Start: <venv-python> finanzen/mcp_server.py
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC). Read-only: Dizzi
sieht Salden/Kennzahlen, bucht aber NICHTS (Schreiben bleibt HITL in der App).
"""

from __future__ import annotations

import os

import moneyapp  # noqa: F401  (Pfad-Shim: macht appkit importierbar)
from moneyapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS
from appkit.mcp import build_http_mcp

BASE = os.environ.get("DIZZ_FINANZEN_URL", "http://127.0.0.1:8210")

mcp = build_http_mcp("finanzen", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
