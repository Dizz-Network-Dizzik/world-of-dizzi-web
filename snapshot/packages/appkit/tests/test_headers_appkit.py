"""H-2: Security-Response-Header (nosniff · Referrer-Policy · X-Frame-Options).
Auf JEDER Antwort, auch auf Guard-Abweisungen (äußerste Middleware); ``setdefault``
lässt eine Route ihren bewusst gesetzten Header behalten."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from appkit.app import create_app
from appkit.db import Database
from appkit.headers import SECURITY_HEADERS, install_security_headers
from appkit.manifest import AppManifest
from appkit.summary import Kpi


def _app(tmp_path):
    return create_app(
        AppManifest(id="hdrapp", name="HDR", brand="Dizz HDR",
                    version="0.1.0", port=8297),
        Database(tmp_path / "h.sqlite"),
        summary_fn=lambda: [Kpi(id="n", label="N", value=1)])


def test_header_auf_normaler_antwort(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_header_auch_auf_guard_abweisung(tmp_path):
    # Äußerste Middleware ⇒ stempelt auch die 400 des Local-Guard (DNS-Rebinding).
    with TestClient(_app(tmp_path)) as c:
        r = c.get("/api/health", headers={"host": "angreifer.example"})
        assert r.status_code == 400
        for key, value in SECURITY_HEADERS.items():
            assert r.headers[key.lower()] == value


def test_setdefault_laesst_route_eigenen_wert(tmp_path):
    app = FastAPI()
    install_security_headers(app)

    @app.get("/eigen")
    def eigen():
        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "DENY"})

    @app.get("/standard")
    def standard():
        return {"ok": True}

    with TestClient(app) as c:
        assert c.get("/eigen").headers["x-frame-options"] == "DENY"          # Route gewinnt
        std = c.get("/standard")
        assert std.headers["x-frame-options"] == "SAMEORIGIN"
        assert std.headers["x-content-type-options"] == "nosniff"
        assert std.headers["referrer-policy"] == "no-referrer"
