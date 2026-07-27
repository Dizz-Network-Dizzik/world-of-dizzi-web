"""Remote-MCP-Gateway (docs/30 §H1 · docs/11 ★★★ 19.06.2026) — „die EINE Verbindung
zu allem".

Exponiert die im Core aggregierten App-Werkzeuge (``tools.registry``) als AUSGEHENDEN
MCP-Server über HTTP (Streamable-HTTP, JSON-RPC 2.0). Eine externe KI (Claude Desktop/
Code, IDE-Agent, künftige Agenten) verbindet sich EINMAL mit Dizzi/Core und erreicht
darüber das ganze Netzwerk — statt jede App einzeln einzubinden.

SICHERHEIT (opt-in/HITL-Disziplin des Netzwerks):
- **Standardmäßig AUS** (Setting ``mcp_gateway_enabled``); Einschalten lokal über
  ``POST /mcp/enable`` (vergibt + zeigt ein Bearer-Token).
- **Bearer-Token-Pflicht**, sobald aktiv (auch lokal — kein anderer Prozess soll frei
  zugreifen). Verwaltung (info/enable/disable/rotate) nur von **localhost**.
- **v1 = READ-ONLY**: nur die nicht-sensiblen App-/Daten-Tools (``registry(sensitive=
  True)`` lässt Web-Suche/Boost & PC-verlassende Tools weg). Schreib-/Aktions-Tools
  bleiben außen vor — sie laufen weiter über die App-eigene **K4-HITL**-Freigabe.
- **OAuth 2.1 / Dynamic Client Registration über Dizzi-ID** (für echtes Remote off-host)
  = dokumentierter v2-Slot; v1 zielt auf same-host-Clients (Claude Desktop/Code).
"""

from __future__ import annotations

import fnmatch
import secrets
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .. import db
from ..config import DEFAULT_USER_ID
from . import tools

router = APIRouter(tags=["mcp-gateway"])

# Unterstützte MCP-Protokoll-Versionen (neueste zuerst). Wir echoen die vom Client
# gewünschte, wenn bekannt — sonst die neueste, die wir sprechen.
_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "Dizz Network (the world of dizzi)", "version": "1.0.0"}
_INSTRUCTIONS = ("Dizz-Netzwerk-Gateway: Werkzeuge der angebundenen Apps (read-only). "
                 "Schreibende/auslösende Aktionen laufen NICHT hierüber, sondern über die "
                 "App-eigene Freigabe (Human-in-the-Loop). Sensible Daten bleiben lokal. "
                 "HOCHSICHER-eingestufte Inhalte (z. B. verschlüsselte Tresor-Dokumente) "
                 "sind extern gesperrt — sie brauchen eine explizite Nutzer-Freigabe.")

# ── Sensitivitäts-Gate (Nutzer-Wunsch 19.06.) ─────────────────────────────────
# Stufen aufsteigend. ``hochsicher`` = Dizzi-ID-Step-up-Tier (verschlüsselte Tresor-
# Dokumente, Echtgeld) — für externe Agenten (Claude) NUR nach expliziter Freigabe.
_STUFE = {"normal": 0, "hoch": 1, "hoechst": 2, "hochsicher": 3}
# App-Sensitivität (= Manifest-Werte). Tool-Namen sind ``<app>_<tool>`` ⇒ Präfix.
# Unbekannt ⇒ vorsichtig „hoch". (Beim Connector-Ausbau hier ergänzen.)
_APP_SENS = {"tradingbot": "hoch", "admin": "hoch", "finanzen": "hoch",
             "health": "hoechst", "memory": "hoch", "kommunikation": "hoch",
             "management": "hoch", "creator": "normal", "news": "normal"}
# (plans/leading entfernt 22.06. — abgewickelt/in admin verschmolzen; unbekannte Apps ⇒ Default „hoch".)
# Tool-Namensmuster, die hochsicher-eingestuften Inhalt berühren (Datei-/Krypto-/
# Echtgeld-Zugriffe). Werden auf Stufe ``hochsicher`` angehoben ⇒ ohne Freigabe gesperrt.
# Erweiterbar per Setting ``mcp_gateway_hochsicher_muster`` (Komma-Liste von Globs).
_HOCHSICHER_MUSTER = ("*hochsicher*", "*verschluessel*", "*verschluesselt*", "*_datei*",
                      "*echtgeld*", "*_secret*", "*passwort*", "*token_lesen*")
# Schreib-/Aktions-Tools (kein reines GET-Lesen, z. B. Communications Sende-VORSCHLAG):
# das Gateway ist v1 READ-ONLY ⇒ sie bleiben extern außen vor (laufen weiter über die
# App-eigene K4-HITL-Freigabe). Dizzis INTERNER Agent (tools.registry) nutzt sie weiter
# — NUR dieser ausgehende Kanal filtert. Namens-Konvention <id>_<verb…> (docs/16 §6).
_AKTIONS_MUSTER = ("*_vorschlagen", "*_senden", "*_anlegen", "*_erstellen",
                   "*_aktualisieren", "*_loeschen", "*_starten", "*_stoppen",
                   "*_buchen", "*_freigeben", "*_veroeffentlichen",
                   # E-Mail-Pilot (RG-6, docs/83 §5.7): die drei neuen Schreib-Verben,
                   # damit die Regie sie als Aktion erkennt (sonst kein propose-Wrap ⇒
                   # der Agent-Grant verpufft als 'verweigert'). **VERENGT (RG-8-Feinschliff,
                   # WA 19.07.):** exakt die email_*-Aktionen — die generischen `*_ablegen`/
                   # `*_markieren`/`*_verschieben` fingen sonst Bestands-Verben mit
                   # (notiz_verschieben · konto_abgleich_markieren · …_als_gelesen_markieren);
                   # das war safe-direction, aber unsauber überbreit.
                   "*_email_entwurf_ablegen", "*_email_markieren", "*_email_verschieben")


def _ceiling() -> int:
    """Standard-Höchststufe ohne Freigabe (Setting; Default ``hoch``)."""
    return _STUFE.get(str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_ceiling", "hoch")), 1)


def _freigabe_aktiv() -> bool:
    """Explizite Hochsicher-Freigabe aktiv (optional zeitlich befristet)."""
    if not bool(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", False)):
        return False
    try:
        bis = float(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_freigabe_bis", 0) or 0)
    except (TypeError, ValueError):
        bis = 0.0
    return bis == 0 or time.time() < bis        # 0 = unbefristet


def _muster() -> tuple[str, ...]:
    extra = str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_hochsicher_muster", "") or "")
    return _HOCHSICHER_MUSTER + tuple(m.strip().lower() for m in extra.split(",") if m.strip())


def _spec_name(spec: Any) -> str:
    """Akzeptiert einen ToolSpec ODER einen blanken Namen (rückwärts-kompatibel)."""
    return spec.name if hasattr(spec, "name") else str(spec)


def _tool_stufe(spec: Any) -> int:
    """Sensitivitäts-Stufe eines Tools = MAXIMUM aus App-Sensitivität, explizitem
    ``spec.sensitivity`` (falls gesetzt) und Krypto-/Datei-/Echtgeld-Namensmuster
    (⇒ ``hochsicher``). FAIL-SAFE: das explizite Attribut kann die Stufe nur ANHEBEN,
    nie unter die App-/Muster-Stufe senken — ein Tool mogelt sich nie aus dem Gate."""
    name = _spec_name(spec)
    app = name.split("_", 1)[0]
    stufe = _STUFE.get(_APP_SENS.get(app, "hoch"), 1)
    explizit = (getattr(spec, "sensitivity", "") or "").strip().lower()
    if explizit in _STUFE:
        stufe = max(stufe, _STUFE[explizit])
    if any(fnmatch.fnmatch(name.lower(), m) for m in _muster()):
        stufe = max(stufe, _STUFE["hochsicher"])
    return stufe


def _erlaubt(spec: Any) -> bool:
    """Tool extern erlaubt? Standard bis ``_ceiling``; mit aktiver Freigabe bis
    ``hochsicher``. ⇒ Hochsicher-Inhalte sind ohne explizite Freigabe gesperrt."""
    allow = _STUFE["hochsicher"] if _freigabe_aktiv() else _ceiling()
    return _tool_stufe(spec) <= allow


def _ist_aktion(spec: Any) -> bool:
    """Schreib-/Aktions-Tool? Explizites ``spec.is_action=True`` ODER Namensmuster
    (read-only-v1: extern gesperrt, intern erlaubt). FAIL-SAFE: das Attribut kann nur
    ZUSÄTZLICH als Aktion markieren, nie ein Muster aushebeln."""
    if getattr(spec, "is_action", None) is True:
        return True
    low = _spec_name(spec).lower()
    return any(fnmatch.fnmatch(low, m) for m in _AKTIONS_MUSTER)


def ist_schreib_tool(spec: Any) -> bool:
    """Öffentlicher Alias der Schreib-/Aktions-Klassifikation (docs/63 §3/§4). Die
    Agenten-Regie (agenten_katalog) nutzt DIESELBE Wahrheit wie das Gateway
    („Schreib-Tools extern nur propose") — es gibt EINE Klassifikation, nicht zwei:
    ein Tool, das extern gesperrt/propose-only ist, wird für einen Agenten NIE roh
    ausführbar, sondern IMMER über die K4-Inbox vorgeschlagen (fail-closed)."""
    return _ist_aktion(spec)


def ist_aktions_name(name: str) -> bool:
    """Wie ``ist_schreib_tool``, aber für einen blanken Werkzeug-NAMEN (Grant): matcht
    die Schreib-/Aktions-Namensmuster (``*_senden``/``*_anlegen``/…). Nötig, weil ein
    Agent Schreib-Aktionen als ``werkzeuge``-Grant referenziert — die App-MCP-Server
    listen v1 nur read-only GET-Tools (mcp_tools), Schreib-Aktionen tauchen also nicht
    im ``tools.registry``-Katalog auf und müssen aus dem Grant-Namen erkannt werden."""
    low = name.strip().lower()
    return any(fnmatch.fnmatch(low, m) for m in _AKTIONS_MUSTER)


def _enabled() -> bool:
    return bool(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_enabled", False))


def _token() -> str:
    """Lazy-Token: erzeugt einmalig ein Geheimnis und persistiert es."""
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
    if auth[:7].lower() == "bearer ":
        return secrets.compare_digest(auth[7:].strip(), _token())
    return False


def _err(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _ok(rid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _strukturiert(text: str) -> dict[str, Any] | None:
    """``structuredContent`` (MCP 2025-06-18) aus einem Tool-Ergebnis — NUR wenn es
    ein JSON-OBJEKT ist (die Spec definiert structuredContent als Objekt). Arrays/
    Skalare/Prosa bleiben reiner ``content``-Text (gültig, abwärtskompatibel). Der
    Text wird ZUSÄTZLICH immer geliefert (Spec: funktional äquivalenter Klartext)."""
    import json
    try:
        daten = json.loads(text)
    except (ValueError, TypeError):
        return None
    return daten if isinstance(daten, dict) else None


async def _handle(method: str, params: dict[str, Any] | None, rid: Any) -> dict[str, Any]:
    params = params or {}
    if method == "initialize":
        want = params.get("protocolVersion")
        ver = want if want in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
        return _ok(rid, {
            "protocolVersion": ver,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": _INSTRUCTIONS,
        })
    if method == "tools/list":
        specs = await tools.registry(sensitive=True)   # nur nicht-sensible App-/Daten-Tools
        # Tool-Annotationen (MCP 2025-06-18, eingeführt 2025-03-26): das Gateway listet
        # NUR read-only-, nicht-Aktions-, lokale Netzwerk-Tools ⇒ die Hints sind exakt
        # (kein Raten): readOnly + nicht-destruktiv + nicht „open world" (kein Internet).
        # Ältere Clients ignorieren das Feld (additiv, abwärtskompatibel).
        return _ok(rid, {"tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.parameters,
             "annotations": {"title": t.name, "readOnlyHint": True,
                             "destructiveHint": False, "idempotentHint": True,
                             "openWorldHint": False}}
            for t in specs if _erlaubt(t) and not _ist_aktion(t)]})  # Hochsicher- + read-only-Gate
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        specs = await tools.registry(sensitive=True)
        spec = next((t for t in specs if t.name == name), None)
        if spec is None:
            return _err(rid, -32602, f"Unbekanntes Tool: {name!r}")
        if _ist_aktion(spec):                           # read-only-v1: Schreib-/Aktions-Tools extern gesperrt
            db.audit(DEFAULT_USER_ID, "mcp_gateway", "aktion_gesperrt", {"tool": name})
            return _ok(rid, {"content": [{"type": "text", "text":
                "Schreib-/Aktions-Tool ist über das Netzwerk-Gateway gesperrt (read-only v1). "
                "Solche Aktionen laufen über die App-eigene Freigabe (Human-in-the-Loop)."}],
                "isError": True})
        if not _erlaubt(spec):                          # Hochsicher-Gate: ohne Freigabe verweigern
            db.audit(DEFAULT_USER_ID, "mcp_gateway", "tool_gesperrt", {"tool": name})
            return _ok(rid, {"content": [{"type": "text", "text":
                "Zugriff verweigert: hochsicher-eingestufter Inhalt (z. B. verschlüsselte "
                "Dokumente / Echtgeld). Erst nach EXPLIZITER Nutzer-Freigabe am Core "
                "(lokal: POST /mcp/freigabe-hochsicher) extern zugänglich."}], "isError": True})
        try:
            text = await spec.run(args)
        except Exception as e:   # noqa: BLE001 — Tool-Fehler als MCP-isError zurück, nie 500
            db.audit(DEFAULT_USER_ID, "mcp_gateway", "tool_error", {"tool": name, "fehler": str(e)})
            return _ok(rid, {"content": [{"type": "text", "text": f"Fehler: {e}"}], "isError": True})
        db.audit(DEFAULT_USER_ID, "mcp_gateway", "tool_call", {"tool": name})
        ergebnis: dict[str, Any] = {
            "content": [{"type": "text", "text": str(text)}], "isError": False}
        strukturiert = _strukturiert(str(text))   # MCP 2025-06-18: structuredContent (Objekt)
        if strukturiert is not None:
            ergebnis["structuredContent"] = strukturiert
        return _ok(rid, ergebnis)
    if method == "ping":
        return _ok(rid, {})
    return _err(rid, -32601, f"Methode nicht unterstützt: {method!r}")


async def _one(req: Any) -> dict[str, Any] | None:
    """Verarbeitet eine JSON-RPC-Nachricht. ``None`` = Notification (keine Antwort)."""
    if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
        rid = req.get("id") if isinstance(req, dict) else None
        return _err(rid, -32600, "Ungültige JSON-RPC-2.0-Anfrage")
    method = str(req.get("method", ""))
    rid = req.get("id")
    if rid is None and method.startswith("notifications/"):
        return None
    return await _handle(method, req.get("params"), rid)


@router.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP-Streamable-HTTP-Endpunkt (JSON-RPC 2.0). Einzel- oder Batch-Anfrage."""
    if not _enabled():
        return JSONResponse(_err(None, -32000, "MCP-Gateway ist deaktiviert "
                                 "(lokal über POST /mcp/enable einschalten)."), status_code=403)
    if not _authed(request):
        return JSONResponse(_err(None, -32001, "Nicht autorisiert — Bearer-Token nötig."),
                            status_code=401, headers={"WWW-Authenticate": "Bearer"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_err(None, -32700, "Parse-Fehler"), status_code=400)
    if isinstance(body, list):                       # JSON-RPC-Batch
        antworten = [a for a in [await _one(r) for r in body] if a is not None]
        return JSONResponse(antworten) if antworten else Response(status_code=202)
    antwort = await _one(body)
    return JSONResponse(antwort) if antwort is not None else Response(status_code=202)


# ── Verwaltung (NUR localhost) ────────────────────────────────────────────────
def _claude_config(token: str) -> dict[str, Any]:
    """Fertiger Eintrag für die MCP-Client-Konfiguration (Claude Desktop/Code)."""
    return {"mcpServers": {"dizz-network": {
        "url": "http://127.0.0.1:8200/mcp",
        "headers": {"Authorization": f"Bearer {token}"}}}}


@router.get("/mcp/info")
def mcp_info(request: Request):
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal abrufbar"}, status_code=403)
    aktiv = _enabled()
    return {
        "enabled": aktiv,
        "endpoint": "http://127.0.0.1:8200/mcp",
        "transport": "streamable-http (JSON-RPC 2.0)",
        "modus": "read-only (v1)",
        "token": _token() if aktiv else None,
        "claude_config": _claude_config(_token()) if aktiv else None,
        "sicherheit": {
            "standard_hoechststufe": str(db.setting_get(DEFAULT_USER_ID, "mcp_gateway_ceiling", "hoch")),
            "hochsicher_freigegeben": _freigabe_aktiv(),
            "hinweis": ("Hochsicher-eingestufte Inhalte (verschlüsselte Tresor-Dokumente, "
                        "Echtgeld) sind extern GESPERRT — erst nach expliziter Freigabe."),
        },
        "hinweis": ("Read-only-v1: nur nicht-sensible App-Tools. Schreibaktionen über "
                    "App-HITL. OAuth/Dizzi-ID-DCR (echtes Remote) = v2."),
    }


@router.post("/mcp/freigabe-hochsicher")
def mcp_freigabe(request: Request, minuten: int = 30):
    """EXPLIZITE Freigabe: erlaubt externen Agenten zeitlich befristet auch hochsicher-
    eingestufte Inhalte. Default 30 Min; ``minuten=0`` = unbefristet (bis ``/freigabe-
    sperren``). Nur lokal — die Freigabe ist eine bewusste Nutzer-Handlung."""
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal"}, status_code=403)
    minuten = max(0, int(minuten))
    bis = 0.0 if minuten == 0 else time.time() + minuten * 60
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", True)
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_bis", bis)
    db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_hochsicher_freigegeben", {"minuten": minuten})
    return {"hochsicher_freigegeben": True, "befristet_minuten": minuten or None}


@router.post("/mcp/freigabe-sperren")
def mcp_freigabe_sperren(request: Request):
    """Hochsicher-Freigabe sofort widerrufen (Standard-Zustand)."""
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal"}, status_code=403)
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_freigabe_hochsicher", False)
    db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_hochsicher_gesperrt", {})
    return {"hochsicher_freigegeben": False}


@router.post("/mcp/enable")
def mcp_enable(request: Request):
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal"}, status_code=403)
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_enabled", True)
    db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_enabled", {})
    tok = _token()
    return {"enabled": True, "endpoint": "http://127.0.0.1:8200/mcp",
            "token": tok, "claude_config": _claude_config(tok)}


@router.post("/mcp/disable")
def mcp_disable(request: Request):
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal"}, status_code=403)
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_enabled", False)
    db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_disabled", {})
    return {"enabled": False}


@router.post("/mcp/rotate-token")
def mcp_rotate(request: Request):
    if not _is_local(request):
        return JSONResponse({"error": "nur lokal"}, status_code=403)
    tok = "dzmcp_" + secrets.token_urlsafe(24)
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_token", tok)
    db.audit(DEFAULT_USER_ID, "user", "mcp_gateway_token_rotiert", {})
    return {"token": tok, "claude_config": _claude_config(tok)}
