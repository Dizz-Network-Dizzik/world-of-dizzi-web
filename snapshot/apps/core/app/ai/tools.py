"""Tool-Registry für Dizzis Agent-Loop (Phase 4).

Zwei Tool-Quellen:
- INTERN: Websuche, Boost-Eskalation, L4-Beobachtungen (laufen im Core).
- MCP: Tools angebundener Panel-Server (z. B. Trading Bot) via FastMCP-Client
  (stdio-Subprozess, persistent gehalten, Reconnect bei Fehlern).

Routing-Regeln:
- ``sensitive=True`` ⇒ KEINE Tools, die den PC verlassen (Websuche, Boost).
  MCP-Panel-Tools bleiben erlaubt — sie lesen lokale Projekte.
- Boost ist hier ein TOOL (``boost_frage``): das lokale Modell delegiert
  besonders schwere Teilfragen ans große Gratis-Modell, statt dass der ganze
  Chat dorthin wandert. Eine Schleife, klare Verantwortung.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from .. import db
from ..config import DEFAULT_USER_ID
from . import observe, providers, websearch

# Monorepo-Pfade (W2.0-Fix 27.06.2026, docs/54 §6): apps/ = parents[3], connectors/ an der
# Repo-Wurzel = parents[4]. VOR dem Fix zeigten alle Pfade auf das Vor-Monorepo-Geschwister-
# Layout ⇒ _mcp_toolspecs übersprang ALLE ⇒ Agent + Gateway hatten KEINE App-Tools.
_APPS = Path(__file__).resolve().parents[3]            # …/dizz-network/apps
_CONNECTORS = _APPS.parent / "connectors"              # …/dizz-network/connectors
_PACKAGES = _APPS.parent / "packages"                  # …/dizz-network/packages (appkit/ui-kit Single-Source)
# Core-Connectoren = die stdio-MCP-Server JEDER Netzwerk-App (A4, docs/31 §6): der Core spawnt
# sie persistent und bündelt ihre read-only Tools (für Dizzis Agent UND das zentrale Gateway).
# Ein fehlender/nicht startbarer Server wird übersprungen (graceful, s. _mcp_toolspecs). Tool-
# Namensraum = <id>_<tool> (build_http_mcp); _wrap_mcp_tool dedupliziert das Server-Präfix.
# WICHTIG: die server_id (1. Tupel-Element) ist Tool-Namensraum UND Sensitivitäts-Schlüssel
# (mcp_gateway._APP_SENS) — sie bleibt die DATEN-id (finanzen/creator/kommunikation/health…),
# unabhängig vom Monorepo-Ordnernamen. NUR die Pfade folgen den heutigen apps/<ordner>.
MCP_SERVERS: list[tuple[str, Path]] = [
    ("tradingbot",    _CONNECTORS / "tradingbot" / "mcp_server.py"),
    ("news",          _APPS / "news"          / "mcp_server.py"),
    ("finanzen",      _APPS / "money"         / "mcp_server.py"),   # Ordner money, id bleibt finanzen
    ("creator",       _APPS / "creating"      / "mcp_server.py"),   # Ordner creating, id bleibt creator
    ("memory",        _APPS / "memory"        / "mcp_server.py"),
    ("kommunikation", _APPS / "communication" / "mcp_server.py"),
    ("admin",         _APPS / "admin"   / "adminapp"       / "mcp_server.py"),
    ("health",        _APPS / "healthy" / "healthapp"      / "mcp_server.py"),
    ("management",    _APPS / "management" / "managementapp" / "mcp_server.py"),
]
TOOL_RESULT_MAX_CHARS = 4000
TOOL_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], Awaitable[str]]
    # Explizite Klassifikation fürs MCP-Gateway (statt reiner Namensmuster-Inferenz,
    # docs/33 R6). RÜCKWÄRTS-KOMPATIBEL + FAIL-SAFE: leer/None ⇒ wie bisher aus Name/App
    # abgeleitet; gesetzt ⇒ kann die Gate-Stufe nur ANHEBEN (nie unter Muster/App senken).
    sensitivity: str = ""          # "" | normal | hoch | hoechst | hochsicher
    is_action: bool | None = None  # True = Schreib-/Aktions-Tool (extern gesperrt)

    @property
    def payload(self) -> dict[str, Any]:
        """Form für Ollamas natives tools-Feld (OpenAI-Schema)."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters,
        }}


def _schema(props: dict[str, dict], required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


def _clip(s: str) -> str:
    return s if len(s) <= TOOL_RESULT_MAX_CHARS else s[:TOOL_RESULT_MAX_CHARS] + " …[gekürzt]"


# --- interne Tools -----------------------------------------------------------

async def _run_websearch(args: dict) -> str:
    results = await websearch.search(str(args.get("suchbegriffe", "")).strip())
    db.audit(DEFAULT_USER_ID, "ki", "web_search", {"query": args.get("suchbegriffe")})
    return _clip(websearch.format_results(results))


async def _run_boost(args: dict) -> str:
    frage = str(args.get("frage", "")).strip()
    spec = next((p for p in providers.PROVIDERS if p.kind == "boost" and p.available), None)
    if spec is None:
        return "Kein Boost-Provider verfügbar."
    model = db.setting_get(DEFAULT_USER_ID, f"boost_model_{spec.id}", spec.default_model)
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{spec.base_url}/chat/completions",
            json={"model": model, "stream": False,
                  "messages": [{"role": "user", "content": frage}]},
            headers={"Authorization": f"Bearer {__import__('os').environ[spec.api_key_env]}",
                     "Content-Type": "application/json"},
        )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
    db.audit(DEFAULT_USER_ID, "ki", "boost_consult", {"provider": spec.id, "chars": len(answer)})
    return _clip(answer)


async def _run_observations(args: dict) -> str:
    hours = int(args.get("stunden", 24) or 24)
    rows = observe.recent(DEFAULT_USER_ID, hours=min(hours, 24 * 7))
    if not rows:
        return "Noch keine Beobachtungen aufgezeichnet."
    return _clip(json.dumps(rows, ensure_ascii=False))


def _internal_tools(sensitive: bool) -> list[ToolSpec]:
    out = [ToolSpec(
        "trading_beobachtungen",
        "Verlaufs-Beobachtungen des Trading-Bot-Systems (periodische Schnappschüsse "
        "von Regime, Governor, Flotte) — für Trend-Fragen wie 'wie hat sich X entwickelt?'.",
        _schema({"stunden": {"type": "integer", "description": "Zeitraum rückwärts in Stunden (Standard 24)"}}),
        _run_observations,
    )]
    if not sensitive:
        out.append(ToolSpec(
            "web_suche",
            "Sucht im Internet nach AKTUELLEN Informationen (News, Preise, Ereignisse). "
            "Nutze dies, wenn dein Wissen nicht aktuell genug ist.",
            _schema({"suchbegriffe": {"type": "string", "description": "Suchanfrage"}}, ["suchbegriffe"]),
            _run_websearch,
        ))
        if any(p.kind == "boost" and p.available for p in providers.PROVIDERS):
            out.append(ToolSpec(
                "boost_frage",
                "Stellt eine besonders schwere Denk-/Analysefrage an ein großes Boost-Modell "
                "und liefert dessen Antwort. Nur für komplexe Teilprobleme nutzen.",
                _schema({"frage": {"type": "string", "description": "Die vollständige, in sich geschlossene Frage"}}, ["frage"]),
                _run_boost,
            ))
    return out


# --- MCP-Brücke (persistente stdio-Clients) -----------------------------------

_mcp_clients: dict[str, Any] = {}
_mcp_lock = asyncio.Lock()

# Toolspec-Cache (docs/50 P1.4): die Tool-LISTE der stdio-Server ist quasi statisch;
# ein kurzer TTL spart das `list_tools()`-Round-Trip über ALLE Server bei jedem
# `registry()`-Aufruf (das Gateway baut die Registry 2× je Tool-Call). Invalidiert
# bei `_drop_client` (Reconnect ⇒ Toolset evtl. geändert). Die gecachten ToolSpecs
# bleiben gültig: ihr `run` löst den Client zur Laufzeit neu auf (call_mcp).
_TOOLSPEC_TTL_S = 45.0
_toolspec_cache: dict[str, Any] = {"specs": None, "bis": 0.0}


def _connector_env() -> dict[str, str]:
    """Umgebung für die stdio-Connector-Subprozesse.

    W2.0-RESTLOCH (27.06.2026): der MCP-stdio-Default (``env=None``) nutzt das
    SDK-``get_default_environment()`` und STRIPT u. a. ``PYTHONPATH``. Damit finden
    Connector-Apps mit Vor-Monorepo-Shim (alle außer news/tradingbot, die ``packages``
    selbst auf ``sys.path`` legen) das geteilte ``appkit`` nicht mehr ⇒ ihr ``import
    appkit`` crasht beim Start ⇒ ihre read-only Tools fehlen LAUTLOS in Dizzis Agent
    UND im MCP-Gateway (``_mcp_toolspecs`` überspringt den toten Server graceful).
    Wir reichen daher die volle Umgebung + ``packages`` auf ``PYTHONPATH`` weiter —
    genau wie ``ops/launch_app.ps1`` die App-Server selbst startet."""
    env = dict(os.environ)
    vorhanden = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (str(_PACKAGES) + os.pathsep + vorhanden) if vorhanden else str(_PACKAGES)
    return env


async def _client_for(server_id: str, path: Path):
    from fastmcp import Client
    from fastmcp.client.transports import PythonStdioTransport
    cached = _mcp_clients.get(server_id)
    if cached is not None:
        return cached
    async with _mcp_lock:
        cached = _mcp_clients.get(server_id)
        if cached is not None:
            return cached
        # Explizites Transport mit PYTHONPATH=packages (s. _connector_env): ohne das
        # liefe der Subprozess mit gestripptem PYTHONPATH ⇒ appkit-Import-Crash.
        client = Client(PythonStdioTransport(str(path), env=_connector_env()))
        await client.__aenter__()  # persistent halten; Reconnect via _drop_client
        _mcp_clients[server_id] = client
        return client


async def _drop_client(server_id: str) -> None:
    _toolspec_cache["bis"] = 0.0          # Reconnect ⇒ Toolspec-Cache invalidieren
    client = _mcp_clients.pop(server_id, None)
    if client is not None:
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass


def _extract_result(res: Any) -> Any:
    """Pythonisches Ergebnis aus einem FastMCP-``CallToolResult`` ziehen — robust
    über ALLE Rückgabe-Formen.

    FALLE (27.06.2026, Funktions-Forscher): ``res.data`` ist nur gesetzt, wenn das
    Tool ein JSON-OBJEKT liefert (MCP ``structuredContent`` ist per Spec objekt-only).
    Tools, die ein top-level **Array** zurückgeben (``*_quellen``/``*_ordner``/
    ``*_konten``/``*_letzte_*``/viele ``admin_*``-Listen), haben ``data=None`` UND
    ``structured_content=None`` — die Nutzlast steckt dann ausschließlich im Text-
    ``content``. ``getattr(res, "data", None)`` ließ diese Tools lautlos als ``null``
    erscheinen (Agent + Gateway bekamen "null" statt der Liste). Reihenfolge:
    strukturiert (Objekt) → sonst Text-content als JSON parsen → sonst roher Text."""
    data = getattr(res, "data", None)
    if data is not None:
        return data
    sc = getattr(res, "structured_content", None)
    if sc is not None:
        return sc
    texte = [t for t in (getattr(b, "text", None) for b in (getattr(res, "content", None) or []))
             if t is not None]
    if not texte:
        return None
    roh = texte[0] if len(texte) == 1 else "".join(texte)
    try:
        return json.loads(roh)        # Array/Skalar aus dem Text-content
    except (ValueError, TypeError):
        return roh                    # reiner Prosa-Text (kein JSON)


async def call_mcp(server_id: str, name: str, args: dict | None = None) -> Any:
    """Roher MCP-Tool-Aufruf (ungekappt) — für interne Nutzer wie den
    L4-Beobachter. 1 Reconnect-Versuch bei totem Subprozess."""
    path = dict(MCP_SERVERS).get(server_id)
    if path is None:
        raise KeyError(f"Unbekannter MCP-Server: {server_id}")
    last: Exception | None = None
    for _ in range(2):
        try:
            client = await _client_for(server_id, path)
            res = await client.call_tool(name, args or {})
            return _extract_result(res)
        except Exception as e:
            last = e
            await _drop_client(server_id)
    raise RuntimeError(f"MCP-Tool {server_id}/{name} fehlgeschlagen: {last}")


def _wrap_mcp_tool(server_id: str, name: str, description: str,
                   parameters: dict) -> ToolSpec:
    async def run(args: dict) -> str:
        try:
            data = await call_mcp(server_id, name, args)
        except Exception as e:
            return str(e)
        return _clip(json.dumps(data, ensure_ascii=False, default=str))
    # Das Tool ist beim App-Server bereits namespaced (build_http_mcp ⇒ <id>_<tool>) —
    # das Server-Präfix nicht doppeln (news_news_… ⇒ news_…). Der echte MCP-Aufruf nutzt
    # weiter den Original-Namen (Closure ``name``), nur der sichtbare Name wird dedupliziert.
    sichtbar = f"{server_id}_{name}".replace(f"{server_id}_{server_id}_", f"{server_id}_", 1)
    return ToolSpec(sichtbar, description, parameters or _schema({}), run)


async def _mcp_toolspecs() -> list[ToolSpec]:
    if _toolspec_cache["specs"] is not None and time.monotonic() < _toolspec_cache["bis"]:
        return _toolspec_cache["specs"]
    specs: list[ToolSpec] = []
    for server_id, path in MCP_SERVERS:
        if not path.is_file():
            continue
        try:
            client = await _client_for(server_id, path)
            for t in await client.list_tools():
                specs.append(_wrap_mcp_tool(
                    server_id, t.name, t.description or t.name,
                    t.inputSchema or _schema({}),
                ))
        except Exception as e:  # Server nicht startbar → Chat läuft ohne ihn weiter
            print(f"MCP-Server {server_id} nicht verfügbar: {e}", file=sys.stderr)
            await _drop_client(server_id)
    _toolspec_cache["specs"] = specs
    _toolspec_cache["bis"] = time.monotonic() + _TOOLSPEC_TTL_S
    return specs


async def registry(sensitive: bool) -> list[ToolSpec]:
    return _internal_tools(sensitive) + await _mcp_toolspecs()
