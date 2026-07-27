"""Vertrags-Konformität von Dizz Memory — maschinell erzwungen (appkit.conformance).

Kopie des refapp-Musters: prüft alle Pflicht-Endpoints des App-Vertrags
(docs/16 §2) inkl. Settings-Roundtrip, Audit, Datenrechte-fail-closed,
Defense- und Mini-Dizzi-Slot.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit import conformance
from archivapp import main as am


def test_vertrag_konform(tmp_path):
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        conformance.check_contract(c, "memory")
        assert c.get("/auth/me").json()["level"] == "lokal"


def test_manifest_marke_und_namensraum(tmp_path):
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        m = c.get("/api/manifest").json()
        assert m["brand"] == "Dizz Memory" and m["name"] == "Wissensspeicher"
        assert m["port"] == 8212 and m["sensitivity"] == "hoch"
        # MCP-Tools tragen den memory_-Namensraum (docs/16 §6)
        assert all(t.startswith("memory_") for t in m["mcp"]["tools"])
        assert "memory_kachel_stats" in m["mcp"]["tools"]


def test_frontend_und_ui_kit_assets(tmp_path):
    """Startseite + tokenbasiertes UI-Kit (Whitelist) werden ausgeliefert;
    Unbekanntes ⇒ 404 (kein Pfad-Durchgriff)."""
    app = am.build_app(data_dir=tmp_path, start_import_timer=False)
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        for datei, typ in [("tokens.css", "css"), ("controls.css", "css"),
                           ("collapse.js", "javascript"), ("spinfling.js", "javascript"),
                           ("floats.js", "javascript"),
                           ("float_dock.css", "css"), ("float_dock.js", "javascript")]:
            r = c.get(f"/ui-kit/{datei}")
            assert r.status_code == 200 and typ in r.headers["content-type"]
            assert len(r.content) > 0
        assert c.get("/ui-kit/geheim.txt").status_code == 404
