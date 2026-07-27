"""MCP-Server von Dizz News (read-only, stdio).

Start: <venv-python> mcp_server.py   (im news-Ordner)
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC).
"""

from __future__ import annotations

import os

import newsapp  # noqa: F401  (Pfad-Shim: macht appkit importierbar)
from newsapp.mcp_tools import MCP_INSTRUCTIONS, MCP_TOOLS
from appkit.mcp import build_http_mcp

BASE = os.environ.get("DIZZ_NEWS_URL", "http://127.0.0.1:8216")

mcp = build_http_mcp("news", BASE, tools=MCP_TOOLS, instructions=MCP_INSTRUCTIONS)

if __name__ == "__main__":
    mcp.run()  # stdio
