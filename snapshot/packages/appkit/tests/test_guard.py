"""Tests H1 Local-Guard: DNS-Rebinding- und CSRF-Muster werden abgewiesen,
legitime lokale/skriptgesteuerte Nutzung bleibt unberührt (docs/18 §4.1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.summary import Kpi


def _app(tmp_path):
    return create_app(
        AppManifest(id="guardapp", name="Guard", brand="Dizz Guard",
                    version="0.1.0", port=8297),
        Database(tmp_path / "g.sqlite"),
        summary_fn=lambda: [Kpi(id="n", label="N", value=1)])


def test_rebinding_host_wird_abgelehnt(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        # DNS-Rebinding: Browser glaubt angreifer.example, trifft 127.0.0.1 —
        # der Host-Header trägt die fremde Domain.
        r = c.get("/api/health", headers={"host": "angreifer.example"})
        assert r.status_code == 400
        assert "Rebinding" in r.json()["error"]
        # Normale Hosts bleiben offen
        assert c.get("/api/health").status_code == 200                  # testserver
        assert c.get("/api/health",
                     headers={"host": "127.0.0.1:8297"}).status_code == 200
        assert c.get("/api/health",
                     headers={"host": "localhost"}).status_code == 200
        # RD-1b: Backslash-Confusion — urlsplit saehe host=127.0.0.1 (erlaubt), aber
        # MUSS abgelehnt werden (Backslash/Control-Char hart verworfen = fail-closed).
        assert c.get("/api/health",
                     headers={"host": "evil.com\\@127.0.0.1"}).status_code == 400


def test_csrf_fremder_origin_auf_schreibend(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        # Fremde Webseite feuert POST auf localhost ⇒ 403
        r = c.put("/api/settings", json={"key": "x_a", "value": 1},
                  headers={"origin": "https://boese-seite.example"})
        assert r.status_code == 403 and "CSRF" in r.json()["error"]
        r = c.put("/api/settings", json={"key": "x_a", "value": 1},
                  headers={"origin": "null"})
        assert r.status_code == 403
        # Eigenes Frontend (lokaler Origin) und Skripte (kein Origin) ⇒ ok
        assert c.put("/api/settings", json={"key": "x_a", "value": 1},
                     headers={"origin": "http://127.0.0.1:8297"}).status_code == 200
        assert c.put("/api/settings", json={"key": "x_a", "value": 2}).status_code == 200
        # Lesen mit fremdem Origin bleibt erlaubt (kein Schreib-Effekt;
        # Antwort schützt die Browser-Same-Origin-Policy)
        assert c.get("/api/health",
                     headers={"origin": "https://boese-seite.example"}).status_code == 200
