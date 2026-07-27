"""Tests Dizz Admin — Integrations-Reste der vereinten App (docs/28): die mini-dizzi
antwortet über ALLE Module + der MCP-Namensraum deckt alle Module ab. Lauf: pytest -q
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from adminapp import main as lm
from adminapp.manifest import MANIFEST


def test_mcp_tools_decken_alle_module(tmp_path):
    tools = MANIFEST.mcp.tools
    for t in ("admin_geschaefts_kpis", "admin_studien_uebersicht", "admin_bereiche",
              "admin_fristen_cockpit", "admin_dokumente", "admin_projekte", "admin_erinnerungen"):
        assert t in tools, f"MCP-Tool fehlt: {t}"


def test_ki_kontext_ueber_alle_module(tmp_path):
    """Der an die lokale KI gesendete Kontext umfasst Projekte UND Tresor-Dokumente
    (nicht nur Geschäft) — Beleg der KI-Vereinheitlichung."""
    erfasst: dict = {}

    class _R:
        status_code = 200

        def json(self):
            return {"message": {"content": json.dumps({"antwort": "ok"})}}

    def _post(url, json):
        erfasst["payload"] = json
        return _R()

    with TestClient(lm.build_app(data_dir=tmp_path, http_post=_post)) as c:
        c.post("/api/projekte", json={"name": "Bachelorarbeit"})
        c.post("/api/dokumente/upload",
               files={"datei": ("po.pdf", b"%PDF po", "application/pdf")},
               data={"titel": "Modulhandbuch"})
        out = c.post("/api/ki/frage", json={"frage": "Was läuft gerade?"}).json()
        assert "antwort" in out

    text = json.dumps(erfasst["payload"], ensure_ascii=False)
    assert "Bachelorarbeit" in text          # Projekte-Kontext gespeist
    assert "Modulhandbuch" in text           # Tresor-Kontext gespeist
