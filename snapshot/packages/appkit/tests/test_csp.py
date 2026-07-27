"""Tests der Nonce-CSP (appkit/csp.py, docs/36 W2)."""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from appkit.csp import build_csp, inject_nonce, install_csp, serve_html_mit_csp


def _nonce_aus_header(h: str) -> str:
    m = re.search(r"'nonce-([^']+)'", h)
    return m.group(1) if m else ""


def test_build_csp_streng_und_mit_nonce():
    csp = build_csp("ABC123", connect_extra=["http://127.0.0.1:8200"])
    assert "script-src 'self' 'nonce-ABC123'" in csp
    # style-src bleibt AUCH strikt lenient ('unsafe-inline') — inline style="…"-Attribute
    # sind kein Skript-Vektor + Nonce gilt nicht für Style-Attribute (sonst Layout-Bruch).
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "'nonce-ABC123'" not in csp.split("style-src")[1].split(";")[0]  # KEIN Nonce in style-src
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "default-src 'self'" in csp
    assert "http://127.0.0.1:8200" in csp          # connect-src-Erweiterung


def test_build_csp_baseline_unsafe_inline_aber_extern_dicht():
    """Baseline (strikt=False): erlaubt Inline (für Bestands-onclick-Handler), blockt
    aber weiter extern/object/frame/base."""
    csp = build_csp(strikt=False)
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "'nonce-" not in csp                       # kein Nonce im Baseline-Modus
    assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    assert "base-uri 'self'" in csp and "default-src 'self'" in csp


def test_inject_nonce_setzt_und_dedupliziert():
    html = ('<style>a{}</style><script>x()</script>'
            '<script nonce="schon">y()</script><!--{{csp_nonce}}-->')
    out = inject_nonce(html, "NX")
    assert '<style nonce="NX">' in out
    assert '<script nonce="NX">x()' in out
    assert '<script nonce="schon">y()' in out      # vorhandenen Nonce NICHT überschreiben
    assert "<!--NX-->" in out                       # {{csp_nonce}}-Platzhalter ersetzt


def _app(mode: str) -> FastAPI:
    app = FastAPI()
    install_csp(app, mode=mode)

    @app.get("/")
    def index(request: Request):
        return serve_html_mit_csp(request, _TMP_HTML)

    @app.get("/api/x")
    def api():
        return JSONResponse({"ok": True})
    return app


_TMP_HTML = None


def test_modus_aus_kein_header(tmp_path):
    global _TMP_HTML
    _TMP_HTML = tmp_path / "i.html"
    _TMP_HTML.write_text("<html><script>1</script></html>", encoding="utf-8")
    c = TestClient(_app("aus"))
    r = c.get("/")
    assert "content-security-policy" not in {k.lower() for k in r.headers}
    assert "content-security-policy-report-only" not in {k.lower() for k in r.headers}


def test_modus_report_only_und_json_unberuehrt(tmp_path):
    global _TMP_HTML
    _TMP_HTML = tmp_path / "i.html"
    _TMP_HTML.write_text("<html><script>1</script></html>", encoding="utf-8")
    c = TestClient(_app("report-only"))
    r = c.get("/")
    assert "Content-Security-Policy-Report-Only" in r.headers
    assert "Content-Security-Policy" not in r.headers
    # JSON-Antworten (kein text/html) bekommen KEINE CSP.
    rj = c.get("/api/x")
    assert "Content-Security-Policy-Report-Only" not in rj.headers


def test_modus_enforce_nonce_im_header_und_body_gleich_und_pro_request_neu(tmp_path):
    global _TMP_HTML
    _TMP_HTML = tmp_path / "i.html"
    _TMP_HTML.write_text("<html><script>app()</script></html>", encoding="utf-8")
    c = TestClient(_app("enforce"))
    r1 = c.get("/")
    assert "Content-Security-Policy" in r1.headers
    n1 = _nonce_aus_header(r1.headers["Content-Security-Policy"])
    assert n1 and f'<script nonce="{n1}">app()' in r1.text   # Header- = Body-Nonce
    r2 = c.get("/")
    n2 = _nonce_aus_header(r2.headers["Content-Security-Policy"])
    assert n2 and n2 != n1                                    # Nonce wechselt je Request


def test_unbekannter_modus_faellt_auf_aus(tmp_path):
    global _TMP_HTML
    _TMP_HTML = tmp_path / "i.html"
    _TMP_HTML.write_text("<html></html>", encoding="utf-8")
    c = TestClient(_app("kaputt"))
    r = c.get("/")
    assert "content-security-policy" not in {k.lower() for k in r.headers}
