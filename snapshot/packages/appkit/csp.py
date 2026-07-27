"""Nonce-basierte Content-Security-Policy (Härtung H-CSP, docs/25 / docs/36 W2).

CSP ist der Browser-Schutz gegen eingeschleusten Code (XSS): der Browser führt nur
Skripte/Styles aus, die die Policy erlaubt. Weil die Dizz-Apps **inline-lastige**
``index.html`` ausliefern (inline ``<script>``/``<style>``), braucht eine STRIKTE CSP
einen **Per-Request-Nonce**, der (a) im CSP-Header steht UND (b) in JEDEN Inline-Tag
der ausgelieferten HTML injiziert wird. Ohne Nonce müsste man ``'unsafe-inline'``
erlauben — das hebelt den Schutz aus.

Ablauf:
  install_csp(app, mode)          -> Middleware: setzt pro Request einen Nonce auf
                                     ``request.state.csp_nonce`` + den CSP-Header (je Modus).
  serve_html_mit_csp(request,pfad)-> liest die HTML, injiziert den Nonce in alle
                                     ``<script>``/``<style>`` (+ ``{{csp_nonce}}``-Platzhalter),
                                     liefert HTMLResponse. ERSETZT das nackte FileResponse
                                     der ``GET /``-Route, sobald die App CSP einschaltet.

Drei Modi (Default 'aus' — nichts ändert sich, bis eine App den Nonce ausliefert):
  - 'aus'         : kein CSP-Header (Verhalten wie bisher).
  - 'report-only' : ``Content-Security-Policy-Report-Only`` — der Browser MELDET Verstöße
                    (Konsole), blockt aber nichts ⇒ gefahrloses Einfahren je App.
  - 'enforce'     : ``Content-Security-Policy`` — blockt. Erst NACHDEM ``index.html`` über
                    ``serve_html_mit_csp`` mit Nonce ausgeliefert wird.

Lokale 127.0.0.1-Apps: ``connect-src`` = self + (optional) Core-Relay; keine externen CDNs
(alles lokal über ``/ui-kit``). Standalone-fähig — jede App trägt es selbst (wie ``defense``).
"""
from __future__ import annotations

import re
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# Inline-<script>/<style> OHNE bereits vorhandenes nonce= bekommen eins eingesetzt.
_INLINE_TAG = re.compile(r"<(script|style)(?![^>]*\bnonce=)([^>]*)>", re.IGNORECASE)
_MODI = ("aus", "report-only", "enforce")


def csp_nonce(request: Request) -> str:
    """Holt/erzeugt den Per-Request-Nonce (idempotent je Request)."""
    n = getattr(request.state, "csp_nonce", None)
    if not n:
        n = secrets.token_urlsafe(16)
        request.state.csp_nonce = n
    return n


def build_csp(nonce: str | None = None, *, strikt: bool = True,
              connect_extra: list[str] | None = None,
              img_extra: list[str] | None = None,
              style_extra: list[str] | None = None,
              font_extra: list[str] | None = None) -> str:
    """Baut den CSP-String mit lokal-tauglichen Defaults.

    Stufen NUR für script-src (style-src bleibt IMMER lenient — s. u.):
    - ``strikt=True`` (Nonce): ``script-src 'self' 'nonce-…'`` — blockiert Inline-Skripte
      UND Inline-Event-Handler (onclick=…). Nur für Apps, die ihre Inline-Handler auf
      data-dz-act/addEventListener umgebaut haben (sonst bricht die UI).
    - ``strikt=False`` (BASELINE, nicht-brechend): ``script-src 'self' 'unsafe-inline'``.
    **``style-src`` behält IMMER ``'self' 'unsafe-inline'``** (in BEIDEN Stufen): inline
    ``style="…"``-ATTRIBUTE nutzen alle Frontends massiv, sind aber KEIN Skript-XSS-Vektor —
    und ein Nonce gilt nicht für Style-Attribute (nur für ``<style>``-Elemente), würde sie
    also blockieren ⇒ Layout-Bruch. „Voll-strikt" meint script-src (Google-strict-csp-Muster).
    Beide Stufen setzen immer: default-src 'self', object-src 'none', base-uri 'self',
    frame-ancestors 'self', form-action 'self', img/font/connect lokal."""
    connect = " ".join(["'self'", *(connect_extra or [])])
    img = " ".join(["'self'", "data:", *(img_extra or [])])
    if strikt and nonce:
        script_src = f"script-src 'self' 'nonce-{nonce}'"
    else:
        script_src = "script-src 'self' 'unsafe-inline'"
    # style/font_extra (wie connect/img_extra): gezielte Zusatz-Origins statt Policy-
    # Aufweichung — z. B. Core-Shell-Webfonts, bis sie self-hosted sind. Skripte
    # bekommen BEWUSST keine Extra-Origins (XSS-Kern bleibt zu).
    style_src = " ".join(["style-src 'self' 'unsafe-inline'",   # immer lenient (s. Docstring)
                          *(style_extra or [])])
    font_src = " ".join(["font-src 'self' data:", *(font_extra or [])])
    return "; ".join([
        "default-src 'self'",
        script_src,
        style_src,
        f"img-src {img}",
        font_src,
        f"connect-src {connect}",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


def inject_nonce(html: str, nonce: str) -> str:
    """Setzt den Nonce in alle Inline-``<script>``/``<style>`` + ersetzt den
    optionalen ``{{csp_nonce}}``-Platzhalter (z. B. für ``<link>``/Import-Maps)."""
    html = html.replace("{{csp_nonce}}", nonce)
    return _INLINE_TAG.sub(lambda m: f'<{m.group(1)} nonce="{nonce}"{m.group(2)}>', html)


def serve_html_mit_csp(request: Request, pfad: str | Path) -> HTMLResponse:
    """Liest die HTML-Datei + injiziert den Per-Request-Nonce. Ersatz für
    ``FileResponse(index.html)`` in der ``GET /``-Route, sobald CSP greift."""
    nonce = csp_nonce(request)
    html = Path(pfad).read_text(encoding="utf-8")
    resp = HTMLResponse(inject_nonce(html, nonce))
    resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def install_csp(app: FastAPI, *, mode: str = "aus", strikt: bool = True,
                connect_extra: list[str] | None = None,
                img_extra: list[str] | None = None,
                style_extra: list[str] | None = None,
                font_extra: list[str] | None = None) -> None:
    """Hängt die CSP-Middleware ein: stempelt den CSP-Header auf HTML-Antworten gemäß
    ``mode`` (aus|report-only|enforce). Bei ``strikt=True`` wird zusätzlich pro Request
    ein Nonce gesetzt (Route: ``csp_nonce(request)`` + ``serve_html_mit_csp``); bei
    ``strikt=False`` (Baseline) braucht es keinen Nonce (Inline via 'unsafe-inline').
    Unbekannter Modus ⇒ 'aus' (fail-safe)."""
    if mode not in _MODI:
        mode = "aus"

    @app.middleware("http")
    async def _csp(request: Request, call_next):
        if strikt:
            csp_nonce(request)                  # Nonce VOR der Route bereitstellen
        resp = await call_next(request)
        if mode in ("report-only", "enforce") and \
                resp.headers.get("content-type", "").startswith("text/html"):
            header = ("Content-Security-Policy-Report-Only"
                      if mode == "report-only" else "Content-Security-Policy")
            resp.headers.setdefault(header, build_csp(
                getattr(request.state, "csp_nonce", None), strikt=strikt,
                connect_extra=connect_extra, img_extra=img_extra,
                style_extra=style_extra, font_extra=font_extra))
        return resp
