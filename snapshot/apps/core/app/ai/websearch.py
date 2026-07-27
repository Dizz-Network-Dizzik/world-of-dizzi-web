"""Websuche für Dizzi (Tool der KI; NIE im Sensibel-Modus).

Zwei Backends:
- SearXNG (bevorzugt, self-hosted): vorbereiteter Anschluss — aktiv, sobald
  ``DIZZI_SEARXNG_URL`` gesetzt ist (auf Windows sauber erst via Docker/WSL
  oder auf der Server-Stufe; ehrlich dokumentiert in docs/recherche Welle 5).
- DuckDuckGo-HTML (Fallback, 0 €, ohne Key): funktioniert sofort. HTML-Parsing
  ist naturgemäß fragil — Treffer-Struktur wird defensiv geparst.
"""

from __future__ import annotations

import html as html_lib
import os
import re
import urllib.parse
from typing import Any

import httpx

SEARXNG_URL = os.environ.get("DIZZI_SEARXNG_URL", "")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dizzi-core/0.1"

_DDG_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.DOTALL,
)
_TAGS = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html_lib.unescape(_TAGS.sub("", s)).strip()


def _ddg_url(raw_href: str) -> str:
    """DDG verlinkt über einen Redirect (uddg=…) — echte Ziel-URL extrahieren."""
    q = urllib.parse.urlparse(raw_href).query
    target = urllib.parse.parse_qs(q).get("uddg", [""])[0]
    return target or raw_href


def parse_ddg_html(page: str, max_results: int) -> list[dict[str, str]]:
    out = []
    for m in _DDG_RESULT.finditer(page):
        out.append({
            "title": _clean(m.group("title")),
            "url": _ddg_url(m.group("href")),
            "snippet": _clean(m.group("snippet")),
        })
        if len(out) >= max_results:
            break
    return out


async def search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    if SEARXNG_URL:  # bevorzugtes Backend, sobald konfiguriert
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{SEARXNG_URL}/search",
                                 params={"q": query, "format": "json"},
                                 headers={"User-Agent": _UA})
            r.raise_for_status()
            return [
                {"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", "")}
                for x in r.json().get("results", [])[:max_results]
            ]
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get("https://html.duckduckgo.com/html/",
                             params={"q": query}, headers={"User-Agent": _UA})
        r.raise_for_status()
        return parse_ddg_html(r.text, max_results)


def format_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Keine Suchtreffer."
    return "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['url']}\n{r['snippet']}"
        for i, r in enumerate(results)
    )
