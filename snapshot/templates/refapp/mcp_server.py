"""MCP-Server der Referenz-App (read-only, stdio) — Muster für jede App.

Start: <venv-python> templates/refapp/mcp_server.py
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).
"""

from __future__ import annotations

import os

import refapp  # noqa: F401  (Pfad-Shim: macht appkit importierbar)
from refapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS
from appkit.mcp import build_http_mcp

BASE = os.environ.get("DIZZ_REFAPP_URL", "http://127.0.0.1:8290")

# Die Tool-Liste lebt in refapp/mcp_tools.py (EINE Quelle) — dieselbe nutzt das per-App-
# MCP-Gateway in main.py (Standalone, docs/31 §7). build_http_mcp präfixt die Namen
# automatisch in den App-Namensraum (refapp_<tool>, docs/16 §6).
mcp = build_http_mcp("refapp", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
