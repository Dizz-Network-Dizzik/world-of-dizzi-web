"""HTML-Fehlerseiten statt rohem JSON im Browser (docs/70 §3.4, Baustein B-404/F-4).

FP-6-Befund (docs/60 F-4): 404 = ``{"detail":"Not Found"}`` in 8/8 Stacks —
Sackgasse ohne Rückweg. Dieses Modul rendert für BROWSER-Navigationen eine
token-basierte Fehlerseite (Marken-Lockup + „Zur App-Startseite" + „Zur
Zentrale"); für alles andere bleibt die Antwort **byte-gleich JSON**.

Wertgleichheits-Garantie (Stufe-0, docs/70 §2.2): HTML kommt NUR, wenn
1. der ``Accept``-Header ausdrücklich ``text/html`` nennt (Browser-Navigation;
   ``fetch``/API-Clients/Tests senden ``*/*`` bzw. ``application/json``) UND
2. der Pfad NICHT unter ``/api/`` liegt (der API-Vertrag docs/16 bleibt stabil).

Die Seite lädt nur ``/ui-kit/tokens.css|controls.css|ux-kit.css`` — jede App
serviert die selbst (offline-fest) — und enthält KEIN Inline-CSS/JS
(CSP-strikt-tauglich, docs/37; Layout-Klassen ``.dz-fehler*`` in ux-kit.css).
"""

from __future__ import annotations

import html as _html
from typing import Any

from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from .netz import CORE_URL

#: Kunden-Sätze je Status (docs/70 §3.4: ein Satz, zwei Ausgänge — keine Spielerei).
_SAETZE = {
    404: "Diese Seite gibt es hier nicht.",
    405: "Diese Aktion ist hier so nicht möglich.",
    410: "Diese Seite gibt es nicht mehr.",
}
_SATZ_SONST = "Hier ist etwas schiefgegangen."

_SEITE = """<!doctype html>
<html lang="de" data-design="metall" data-farbe="cyan-magenta">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{code} — {brand}</title>
<link rel="stylesheet" href="/ui-kit/tokens.css">
<link rel="stylesheet" href="/ui-kit/controls.css">
<link rel="stylesheet" href="/ui-kit/ux-kit.css">
</head>
<body class="dz-fehlerseite">
<main class="dz-fehler">
  <header class="dz-appkopf">
    <h1 class="dz-kopf-brand">{brand}</h1>
    <span class="dz-kopf-sub">{name}</span>
    <span class="dz-kopf-spacer"></span>
  </header>
  <div class="dz-fehler-code" aria-hidden="true">{code}</div>
  <p class="dz-fehler-text">{satz}</p>
  <nav class="dz-fehler-wege" aria-label="Weiter geht es hier">
    <a class="dz-btn" href="/">Zur App-Startseite</a>
    <a class="dz-btn" href="{core_url}">Zur Zentrale</a>
  </nav>
</main>
</body>
</html>
"""


def fehlerseite_html(manifest: Any, status_code: int) -> str:
    """Die display-fertige Fehlerseite (Marke/Funktion aus dem Manifest, K2.3)."""
    return _SEITE.format(
        code=int(status_code),
        brand=_html.escape(getattr(manifest, "brand", "") or "Dizz App"),
        name=_html.escape(getattr(manifest, "name", "") or ""),
        satz=_html.escape(_SAETZE.get(status_code, _SATZ_SONST)),
        core_url=_html.escape(CORE_URL),
    )


def _will_html(request: Request) -> bool:
    """Strikte Content-Negotiation: HTML nur für echte Browser-Seitenaufrufe."""
    if request.url.path.startswith("/api/"):
        return False                      # API-Pfade antworten IMMER JSON
    return "text/html" in request.headers.get("accept", "").lower()


def install_fehlerseiten(app: Any, manifest: Any) -> None:
    """Registriert den HTML-Fehler-Handler (404/405/410 + übrige HTTPException).

    Alles Nicht-Browser-artige läuft unverändert durch FastAPIs
    Standard-Handler (exakt die bisherige JSON-Antwort inkl. Header).
    """

    @app.exception_handler(StarletteHTTPException)
    async def _fehler(request: Request, exc: StarletteHTTPException):
        if _will_html(request):
            return HTMLResponse(fehlerseite_html(manifest, exc.status_code),
                                status_code=exc.status_code)
        return await http_exception_handler(request, exc)
