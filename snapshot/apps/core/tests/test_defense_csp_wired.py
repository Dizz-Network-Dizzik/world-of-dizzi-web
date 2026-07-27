"""M-4 Regressionsschutz: Der Core-Hub bekommt jetzt — wie jede create_app-App —
die Defense-Immunschicht UND eine Baseline-CSP. Vor M-4 fehlten beide am wichtigsten
Origin (Core hält den SSO-/Dizzi-ID-Cookie + trägt das MCP-Gateway). Diese Tests
fixieren die Verdrahtung, damit sie nicht still wieder herausfällt.

TestClient-Requests kommen vom Host ``testclient`` ∈ ``defense.LOOPBACK`` ⇒ die
Sensorik lässt sie durch (kein Blocken im Test)."""

from __future__ import annotations

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from app.main import app


# CSP wird NUR auf text/html-Antworten gestempelt. Die echte GET /-Route liefert die
# Shell-SPA nur, wenn shell/dist on-disk liegt (gitignoriertes Build-Artefakt, im
# frischen Checkout/CI abwesend) ⇒ hier eine deterministische HTML-Antwort durch
# denselben Middleware-Stack schicken, damit der Test portabel ist.
@app.get("/__csp_probe__", include_in_schema=False)
def _csp_probe() -> HTMLResponse:
    return HTMLResponse("<!doctype html><title>probe</title>")


client = TestClient(app)


def test_defense_am_hub_verdrahtet() -> None:
    # install_defense setzt app.state.defense (mit korrekter app_id)
    assert getattr(app.state, "defense", None) is not None
    assert app.state.defense.app_id == "core"
    # Cockpit-Router ist eingehängt und antwortet dem Loopback (TestClient ∈ LOOPBACK):
    # status() + vorfaelle() zusammengeführt.
    r = client.get("/api/defense")
    assert r.status_code == 200
    assert "vorfaelle" in r.json()


def test_csp_baseline_auf_html() -> None:
    r = client.get("/__csp_probe__")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy")
    assert csp, "CSP-Header fehlt auf HTML-Antwort — install_csp nicht verdrahtet"
    # Baseline (strikt=False): 'unsafe-inline' statt Nonce, damit die Shell-SPA lebt.
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "'nonce-" not in csp
    # Kern-Härtung: externe Objekte/Frames/Base gesperrt, connect-src nur self.
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "connect-src 'self'" in csp
    # Shell-Webfonts (Chakra Petch/Orbitron via Google Fonts) bleiben unter enforce
    # erlaubt — sonst fiele die Optik auf System-Fonts zurück (Feel-Änderung ohne Go).
    # Skript-Quellen tragen KEINE Extra-Origins.
    assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp
    assert "font-src 'self' data: https://fonts.gstatic.com" in csp
    assert "script-src 'self' 'unsafe-inline';" in csp  # exakt, ohne Zusatz-Origin


def test_guard_abweisung_traegt_security_header() -> None:
    """Reihenfolge-Beweis (Guard → Defense → Header → CSP): auch eine vom Local-Guard
    abgewiesene Anfrage (DNS-Rebinding-Host) wird von den äußeren Schichten gestempelt."""
    r = client.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code in (400, 403)
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_json_api_traegt_keine_csp() -> None:
    # CSP gilt gezielt nur für HTML — die JSON-APIs bleiben unverändert.
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "content-security-policy" not in {k.lower() for k in r.headers}
