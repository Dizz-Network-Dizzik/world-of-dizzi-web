"""appkit/mcp.py — Namensraum + parametrische read-only Tools (docs/16 §6, docs/26 §10.1)."""

from __future__ import annotations

import asyncio

import pytest

from appkit.mcp import build_http_mcp, namespaced


def test_namespaced_praefixt_und_ist_idempotent():
    assert namespaced("news", "briefing") == "news_briefing"
    assert namespaced("news", "news_briefing") == "news_briefing"  # kein Doppel-Präfix
    assert namespaced("memory", "_suche") == "memory_suche"


def test_query_tools_registriert_und_ruft_parametrisch(monkeypatch):
    """``query_tools`` baut PARAMETRISCHE Tools (q + anzahl) im App-Namensraum,
    die GET <base><pfad>?q=…&<param>=<anzahl> machen (Memory-Rück-Lese)."""
    pytest.importorskip("fastmcp")  # nur MCP-Prozesse brauchen fastmcp
    import httpx

    erfasst: dict = {}

    class _R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [{"titel": "T", "auszug": "…"}]

    def fake_get(url, params=None, timeout=None):
        erfasst["url"] = url
        erfasst["params"] = params
        return _R()

    monkeypatch.setattr(httpx, "get", fake_get)

    mcp = build_http_mcp(
        "memory", "http://mem",
        tools=[("kachel_stats", "/api/summary", "Kennzahlen")],
        query_tools=[("suche", "/api/suche", "limit", "Wortsuche"),
                     ("semantisch", "/api/suche/semantisch", "k", "Bedeutungssuche")],
    )

    # Registrierung + Namensraum (kurze Namen werden präfixiert)
    for name in ("memory_kachel_stats", "memory_suche", "memory_semantisch"):
        assert asyncio.run(mcp.get_tool(name)) is not None

    # FTS-Suche: q + limit
    suche = asyncio.run(mcp.get_tool("memory_suche"))
    out = suche.fn(q="ezb zinsen", anzahl=5)
    assert out == [{"titel": "T", "auszug": "…"}]
    assert erfasst["url"] == "http://mem/api/suche"
    assert erfasst["params"] == {"q": "ezb zinsen", "limit": 5}

    # semantische Suche: q + k (anderer Mengen-Parameter)
    sem = asyncio.run(mcp.get_tool("memory_semantisch"))
    sem.fn(q="geldanlage", anzahl=3)
    assert erfasst["url"] == "http://mem/api/suche/semantisch"
    assert erfasst["params"] == {"q": "geldanlage", "k": 3}


def test_query_tools_offline_struktur(monkeypatch):
    """Offline ⇒ erklärende Fehlerstruktur statt Crash (Host-freundlich)."""
    pytest.importorskip("fastmcp")
    import httpx

    def boom(url, params=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    mcp = build_http_mcp("memory", "http://mem", tools=[],
                         query_tools=[("suche", "/api/suche", "limit", "Wortsuche")])
    suche = asyncio.run(mcp.get_tool("memory_suche"))
    out = suche.fn(q="x")
    assert isinstance(out, dict) and "error" in out
