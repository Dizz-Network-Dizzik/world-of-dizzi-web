"""Per-App-MCP-Gateway (Föderations-Variante des Core-Gateways · docs/31 §7).

Jede App kann **im Standalone-Betrieb** ihr EIGENES MCP-Gate über HTTP anbieten —
eine externe KI (Claude) verbindet sich dann direkt mit DIESER einen App. Sobald
die App am Netzwerk hängt UND der Core sein zentrales Gateway aktiv hat, schaltet
sich das App-Gate im Modus ``auto`` **automatisch ab** (dann ist der Core die EINE
Verbindung, docs/30 §H1). Genau die Föderations-Konsistenz: einzeln verkauf-/nutzbar,
im Verbund über den Core gebündelt.

Gleiches Protokoll + dieselbe Sicherheit wie das Core-Gateway: opt-in (Modus),
Bearer-Token, **read-only**, **HOCHSICHER-Gate** (verschlüsselte Dokumente/Echtgeld
nur nach expliziter Freigabe). Tool-Quelle = die deklarativen ``(name, pfad,
beschreibung)``-Tupel der App (dieselben wie ``build_http_mcp``); Tool-Aufruf = GET
der App-eigenen HTTP-API. Verwaltung (mode/info/freigabe) nur von localhost.

Mounten (in der App-``main.py`` nach ``create_app``):
    app.include_router(build_app_gateway(MANIFEST, db, tools=MCP_TOOLS,
        query_tools=MCP_QUERY_TOOLS, base_url="http://127.0.0.1:<port>"))
"""

from __future__ import annotations

import fnmatch
import secrets
import time
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .auth import DEFAULT_USER_ID

_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
_STUFE = {"normal": 0, "hoch": 1, "hoechst": 2, "hochsicher": 3}
_HOCHSICHER_MUSTER = ("*hochsicher*", "*verschluessel*", "*verschluesselt*", "*_datei*",
                      "*echtgeld*", "*_secret*", "*passwort*", "*token_lesen*")
_PROBE_TTL = 60.0   # s: Core-Status wird gecacht, kein Probe je Request


def build_app_gateway(manifest: Any, db: Any, *,
                      tools: list[tuple[str, str, str]],
                      query_tools: list[tuple[str, str, str, str]] | None = None,
                      base_url: str,
                      core_url: str = "http://127.0.0.1:8200",
                      api_get: Callable[[str, dict | None], Any] | None = None,
                      central_probe: Callable[[], bool] | None = None) -> APIRouter:
    """Baut den per-App-MCP-Gateway-Router. ``api_get`` (Tool-Aufruf) + ``central_probe``
    (zentrales Core-Gateway aktiv?) sind Test-Injektionspunkte; Defaults nutzen httpx
    (``base_url``+pfad für Tools · ``core_url``/mcp/info für die Standalone-Erkennung)."""
    app_id = manifest.id
    app_sens = _STUFE.get(getattr(manifest, "sensitivity", "hoch"), 1)
    query_tools = list(query_tools or [])
    router = APIRouter(tags=["app-mcp-gateway"])
    _probe: dict[str, float] = {"ts": 0.0, "central": 0.0}

    def _get(path: str, params: dict | None = None) -> Any:
        if api_get is not None:
            return api_get(path, params)
        import httpx
        try:
            r = httpx.get(f"{base_url}{path}", params=params, timeout=5.0)
            r.raise_for_status()
            return r.json()
        except Exception as e:   # noqa: BLE001
            return {"error": f"App '{app_id}' nicht erreichbar ({path}): {e}"}

    # --- Standalone-Erkennung: zentrales Core-Gateway aktiv? (gecacht) ----------
    def _central_active() -> bool:
        now = time.time()
        if now - _probe["ts"] < _PROBE_TTL:
            return bool(_probe["central"])
        if central_probe is not None:
            aktiv = bool(central_probe())
        else:
            try:
                import httpx
                r = httpx.get(f"{core_url}/mcp/info", timeout=1.2)
                aktiv = r.status_code == 200 and bool(r.json().get("enabled"))
            except Exception:   # noqa: BLE001 — Core nicht erreichbar ⇒ Standalone
                aktiv = False
        _probe["ts"], _probe["central"] = now, 1.0 if aktiv else 0.0
        return aktiv

    def _mode() -> str:
        return str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_mode", "auto"))

    def _serving() -> bool:
        """App-Gate aktiv? an=immer · aus=nie · auto=nur wenn der Core das zentrale
        Gateway NICHT führt (Standalone bzw. Core-Gate aus)."""
        m = _mode()
        if m == "an":
            return True
        if m == "aus":
            return False
        return not _central_active()        # auto

    def _token() -> str:
        t = db.setting_get(DEFAULT_USER_ID, "mcp_gateway_token", "")
        if not t:
            t = "dzmcp_" + secrets.token_urlsafe(24)
            db.setting_put(DEFAULT_USER_ID, "mcp_gateway_token", t)
        return t

    def _is_local(request: Request) -> bool:
        host = request.client.host if request.client else ""
        return host in ("127.0.0.1", "::1", "localhost", "testclient")

    def _authed(request: Request) -> bool:
        auth = request.headers.get("authorization", "")
        return auth[:7].lower() == "bearer " and secrets.compare_digest(auth[7:].strip(), _token())

    # --- Hochsicher-Gate (wie Core) -------------------------------------------
    def _ceiling() -> int:
        return _STUFE.get(str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_ceiling", "hoch")), 1)

    def _freigabe() -> bool:
        if not bool(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", False)):
            return False
        try:
            bis = float(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_freigabe_bis", 0) or 0)
        except (TypeError, ValueError):
            bis = 0.0
        return bis == 0 or time.time() < bis

    def _muster() -> tuple[str, ...]:
        extra = str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_hochsicher_muster", "") or "")
        return _HOCHSICHER_MUSTER + tuple(m.strip().lower() for m in extra.split(",") if m.strip())

    def _stufe(name: str) -> int:
        s = app_sens
        if any(fnmatch.fnmatch(name.lower(), m) for m in _muster()):
            s = max(s, _STUFE["hochsicher"])
        return s

    def _erlaubt(name: str) -> bool:
        return _stufe(name) <= (_STUFE["hochsicher"] if _freigabe() else _ceiling())

    # --- Tool-Katalog (deklarativ, namespaced wie build_http_mcp) ---------------
    _NOARG = {"type": "object", "properties": {}}
    _QARG = {"type": "object",
             "properties": {"q": {"type": "string", "description": "Suchtext"},
                            "anzahl": {"type": "integer", "description": "max. Treffer"}},
             "required": ["q"]}

    def _katalog() -> list[dict[str, Any]]:
        out = []
        for tname, path, beschr in tools:
            out.append({"name": f"{app_id}_{tname}".replace(f"{app_id}_{app_id}_", f"{app_id}_"),
                        "description": beschr, "_path": path, "_schema": _NOARG, "_q": None})
        for tname, path, qp, beschr in query_tools:
            out.append({"name": f"{app_id}_{tname}", "description": beschr,
                        "_path": path, "_schema": _QARG, "_q": qp})
        return out

    def _err(rid, code, msg):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}

    def _okr(rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    async def _handle(method, params, rid):
        params = params or {}
        if method == "initialize":
            want = params.get("protocolVersion")
            ver = want if want in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
            return _okr(rid, {"protocolVersion": ver,
                              "capabilities": {"tools": {"listChanged": False}},
                              "serverInfo": {"name": f"Dizz {app_id} (standalone)", "version": "1.0.0"},
                              "instructions": "App-eigenes MCP-Gate (read-only). Hochsicher-Inhalte "
                                              "nur nach expliziter Freigabe; Schreibaktionen via App-HITL."})
        if method == "tools/list":
            return _okr(rid, {"tools": [{"name": t["name"], "description": t["description"],
                                         "inputSchema": t["_schema"]}
                                        for t in _katalog() if _erlaubt(t["name"])]})
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            t = next((x for x in _katalog() if x["name"] == name), None)
            if t is None:
                return _err(rid, -32602, f"Unbekanntes Tool: {name!r}")
            if not _erlaubt(name):
                db.audit(DEFAULT_USER_ID, "mcp_gateway", "tool_gesperrt", {"tool": name})
                return _okr(rid, {"content": [{"type": "text", "text":
                    "Zugriff verweigert: hochsicher-eingestuft. Erst nach expliziter Freigabe "
                    "(lokal POST /mcp/freigabe-hochsicher)."}], "isError": True})
            qp = t["_q"]
            data = _get(t["_path"], {"q": args.get("q", ""), qp: args.get("anzahl", 8)} if qp else None)
            db.audit(DEFAULT_USER_ID, "mcp_gateway", "tool_call", {"tool": name})
            import json as _json
            return _okr(rid, {"content": [{"type": "text",
                              "text": _json.dumps(data, ensure_ascii=False, default=str)}], "isError": False})
        if method == "ping":
            return _okr(rid, {})
        return _err(rid, -32601, f"Methode nicht unterstützt: {method!r}")

    async def _one(req):
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return _err(req.get("id") if isinstance(req, dict) else None, -32600, "Ungültige Anfrage")
        method, rid = str(req.get("method", "")), req.get("id")
        if rid is None and method.startswith("notifications/"):
            return None
        return await _handle(method, req.get("params"), rid)

    @router.post("/mcp")
    async def app_mcp(request: Request):
        if not _serving():
            return JSONResponse(_err(None, -32000, "App-MCP-Gate inaktiv "
                                "(Modus 'auto': der Core führt das zentrale Gateway)."), status_code=403)
        if not _authed(request):
            return JSONResponse(_err(None, -32001, "Nicht autorisiert — Bearer-Token nötig."),
                                status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(_err(None, -32700, "Parse-Fehler"), status_code=400)
        if isinstance(body, list):
            ant = [a for a in [await _one(r) for r in body] if a is not None]
            return JSONResponse(ant) if ant else Response(status_code=202)
        ant = await _one(body)
        return JSONResponse(ant) if ant is not None else Response(status_code=202)

    def _claude_cfg(tok: str) -> dict[str, Any]:
        return {"mcpServers": {f"dizz-{app_id}": {
            "url": f"{base_url}/mcp", "headers": {"Authorization": f"Bearer {tok}"}}}}

    @router.get("/mcp/info")
    def app_mcp_info(request: Request):
        if not _is_local(request):
            return JSONResponse({"error": "nur lokal"}, status_code=403)
        m, serving = _mode(), _serving()
        return {"app": app_id, "mode": m, "serving": serving,
                "central_gateway_active": _central_active(),
                "endpoint": f"{base_url}/mcp", "modus": "read-only",
                "token": _token() if serving else None,
                "claude_config": _claude_cfg(_token()) if serving else None,
                "sicherheit": {"standard_hoechststufe":
                               str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_ceiling", "hoch")),
                               "hochsicher_freigegeben": _freigabe()},
                "hinweis": ("Standalone-Gate; im Modus 'auto' deaktiviert, sobald der Core sein "
                            "zentrales Gateway aktiv hat. Hochsicher-Inhalte nur mit Freigabe.")}

    @router.post("/mcp/mode")
    def app_mcp_mode(request: Request, wert: str = "auto"):
        if not _is_local(request):
            return JSONResponse({"error": "nur lokal"}, status_code=403)
        if wert not in ("auto", "an", "aus"):
            return JSONResponse({"error": "wert ∈ {auto,an,aus}"}, status_code=400)
        db.setting_put(DEFAULT_USER_ID, "mcp_gateway_mode", wert)
        db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_mode", {"app": app_id, "mode": wert})
        tok = _token()
        return {"mode": wert, "serving": _serving(),
                "token": tok if _serving() else None,
                "claude_config": _claude_cfg(tok) if _serving() else None}

    @router.post("/mcp/freigabe-hochsicher")
    def app_mcp_freigabe(request: Request, minuten: int = 30):
        if not _is_local(request):
            return JSONResponse({"error": "nur lokal"}, status_code=403)
        minuten = max(0, int(minuten))
        db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", True)
        db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_bis",
                       0.0 if minuten == 0 else time.time() + minuten * 60)
        db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_hochsicher_freigegeben",
                 {"app": app_id, "minuten": minuten})
        return {"hochsicher_freigegeben": True, "befristet_minuten": minuten or None}

    @router.post("/mcp/freigabe-sperren")
    def app_mcp_sperren(request: Request):
        if not _is_local(request):
            return JSONResponse({"error": "nur lokal"}, status_code=403)
        db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", False)
        db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_hochsicher_gesperrt", {"app": app_id})
        return {"hochsicher_freigegeben": False}

    return router
