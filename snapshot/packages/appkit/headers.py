"""Security-Response-Header (Härtung H-2, docs/25 / docs/18) — Defense-in-Depth
für die lokalen App-APIs. Drei billige, breit empfohlene Header auf JEDER Antwort:

- ``X-Content-Type-Options: nosniff`` — verbietet MIME-Sniffing (der ``.js``-MIME-
  Vorfall wäre damit geblockt worden).
- ``Referrer-Policy: no-referrer`` — keine Referrer-Lecks an Dritte.
- ``X-Frame-Options: SAMEORIGIN`` — kein Clickjacking via fremdes ``<iframe>``.
  Bricht Passkey/IdP-Flows NICHT (das sind Top-Level-Navigationen + die
  ``navigator.credentials``-API, keine Cross-Origin-Frames).

Lokale Apps (127.0.0.1) tragen geringes Risiko; sensible Apps (Money/Admin/
Health) + Defense-in-Depth rechtfertigen die Härtung. **CSP bewusst später**
(braucht App-spezifisches Allowlisting der Inline-Styles/Skripte).

``setdefault``: eine Route, die einen Header bewusst anders setzt, behält ihn.
Als ÄUSSERSTE Middleware installiert ⇒ stempelt auch Guard-/Defense-Abweisungen.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "SAMEORIGIN",
}


def install_security_headers(app: FastAPI) -> None:
    """Hängt die Security-Header-Middleware ein. ZULETZT aufrufen (nach Guard +
    Defense), damit sie äußerste Schicht ist und jede Antwort stempelt."""
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            resp.headers.setdefault(key, value)
        # HTML-Seiten (index.html) NICHT heuristisch cachen: ohne Cache-Control cached der
        # Browser sie ohne Revalidierung -> Frontend-Edits (Kit/Settings/Header) erscheinen
        # mal frisch, mal alt (Vorfall 18.06.: "Greif-Glow geht nur bei manchen Apps").
        # no-cache = via ETag revalidieren -> Edits schlagen sofort + netzwerkweit durch.
        # (Die statischen ui-kit-Dateien tragen ihre eigene no-cache-Auslieferung.)
        if resp.headers.get("content-type", "").startswith("text/html"):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp
