"""MCP-Server von Dizz Memory (read-only, stdio) — Muster wie refapp/news.

Start: <venv-python> mcp_server.py   (im archiv-Ordner)
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).

Tool-Namen kurz angeben — build_http_mcp präfixt sie automatisch in den
App-Namensraum ``memory_<tool>`` (docs/16 §6), kollisionsfrei beim Bündeln
mehrerer App-Server. Schreib-/Aktions-Tools bleiben read-only ausgespart
(Least-Privilege, K4/HITL = Folgepaket).
"""

from __future__ import annotations

import os

import archivapp  # noqa: F401  (Pfad-Shim: macht appkit importierbar)
from archivapp.mcp_tools import MCP_INSTRUCTIONS, MCP_QUERY_TOOLS, MCP_TOOLS
from appkit.mcp import build_http_mcp

BASE = os.environ.get("DIZZ_MEMORY_URL", "http://127.0.0.1:8212")

mcp = build_http_mcp("memory", BASE, tools=MCP_TOOLS,
                     query_tools=MCP_QUERY_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
