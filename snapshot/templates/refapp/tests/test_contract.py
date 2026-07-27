"""Konformitäts-Tests der Referenz-App — DIESE Datei kopiert jede neue App
(nur APP_ID/Import anpassen). Der Vertrag bleibt damit maschinell erzwungen."""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit import conformance
from refapp.main import APP_ID, build_app


def test_vertrag_konform(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as client:
        conformance.check_contract(client, APP_ID)
        # Dizzi-ID-Anschluss installiert; ohne Login = Standalone-Stufe 'lokal'
        me = client.get("/auth/me").json()
        assert me == {"angemeldet": False, "level": "lokal"}


def test_domaene_speist_kachel(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as client:
        s0 = client.get("/api/summary").json()
        notizen0 = next(k for k in s0["kpis"] if k["id"] == "notizen")
        assert notizen0["value"] == 0

        assert client.post("/api/notizen", json={"text": "Hallo Vertrag"}).status_code == 200

        s1 = client.get("/api/summary").json()
        notizen1 = next(k for k in s1["kpis"] if k["id"] == "notizen")
        assert notizen1["value"] == 1 and s1["status"] == "ok"

        # Domänen-Aktion ist auditiert (Vertrags-Pflicht: Wirkung ⇒ Protokoll)
        actions = [e["action"] for e in client.get("/api/audit").json()]
        assert "notiz_angelegt" in actions


def test_mcp_server_definiert_tools(tmp_path):
    import asyncio

    import pytest
    pytest.importorskip("fastmcp")
    import mcp_server  # noqa: F401  (Import beweist: kein stdout-Schreiben, Tools bauen)
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    # Tools tragen den App-Namensraum "refapp_" (docs/16 §6), nicht den nackten Namen.
    assert {"refapp_kachel_stats", "refapp_lebenszeichen"} <= names
    assert "kachel_stats" not in names
