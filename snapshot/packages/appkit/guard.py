"""Local-Guard (Härtung H1, docs/18 §4.1) — Schutz der localhost-APIs vor
Browser-Angriffen: **DNS-Rebinding** (fremde Domain wird per DNS auf 127.0.0.1
gebunden und damit „same-origin") und **CSRF** (fremde Seite feuert blinde
schreibende Requests auf 127.0.0.1).

Zwei billige, entscheidende Prüfungen (Recherche 12.06., GitHub Security Lab):
1. **Host-Allowlist** für ALLE Requests: nur 127.0.0.1/localhost (+ Test-Host).
   Rebinding-Requests tragen die Angreifer-Domain im Host-Header ⇒ 400.
2. **Origin-Prüfung** für schreibende Methoden: schickt ein Browser einen
   Origin-Header, muss er lokal sein ⇒ sonst 403. Nicht-Browser-Clients
   (curl/Skripte/Monitor) senden keinen Origin und bleiben unberührt.

Bewusst KEIN Token-Zwang auf Lese-Endpoints — die Vertrauensgrenze localhost
bleibt; der Guard schließt die Browser-Lücke in dieser Grenze.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# "testserver" = Host des Starlette-TestClients (kein öffentlich bindbarer
# Name); "0.0.0.0" fehlt bewusst (0.0.0.0-Day-Angriffsmuster).
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "testserver"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _hostname(value: str) -> str:
    """Hostname ohne Port aus Host-Header oder Origin-URL (robust, lowercase)."""
    value = value.strip().lower()
    # RD-1b (28.06., Defense-in-Depth, analog RD-1/_safe_next): Backslash/Control-Char
    # hart abweisen ⇒ "" (fällt aus der Allowlist = fail-closed). Browser normalisieren
    # '\' -> '/' (WHATWG) vor dem Senden, Pythons urlsplit nicht ⇒ ``evil.com\@127.0.0.1``
    # parst sonst host=127.0.0.1. Legitime Host/Origin tragen weder '\' noch Control-Chars.
    if "\\" in value or any(ord(c) < 0x20 for c in value):
        return ""
    if "://" in value:
        return urlsplit(value).hostname or ""
    return urlsplit(f"//{value}").hostname or ""


def install_local_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def _local_guard(request: Request, call_next):
        host = _hostname(request.headers.get("host", ""))
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                {"error": "Host nicht erlaubt (Local-Guard: DNS-Rebinding-Schutz)"},
                status_code=400)
        if request.method in WRITE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin != "null":
                if _hostname(origin) not in ALLOWED_HOSTS:
                    return JSONResponse(
                        {"error": "Fremder Origin abgelehnt (Local-Guard: CSRF-Schutz)"},
                        status_code=403)
            elif origin == "null":  # sandboxed/Daten-URLs: kein legitimer Fall
                return JSONResponse(
                    {"error": "Origin 'null' abgelehnt (Local-Guard)"},
                    status_code=403)
        return await call_next(request)
