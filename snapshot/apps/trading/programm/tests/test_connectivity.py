"""Tests: Per-App-MCP-Gateway (docs/31 §7) + Mini-Dizzi (Vertrag 1.5).
Strikt read-only; Echtgeld-Gate unberührt."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import main


# ------------------------------------------------------------------ Gateway
def test_mcp_info_erreichbar():
    """GET /mcp/info antwortet 200 (lokal, kein Token nötig)."""
    with TestClient(main.app) as c:
        r = c.get("/mcp/info")
        assert r.status_code == 200
        d = r.json()
        assert d.get("app") == "tradingbot"
        assert "mode" in d
        assert "serving" in d


def test_mcp_ohne_token_liefert_401():
    """POST /mcp ohne Authorization-Header → 401."""
    with TestClient(main.app) as c:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        r = c.post("/mcp", json=payload)
        assert r.status_code == 401


def test_mcp_mit_token_initialize():
    """POST /mcp → initialize antwortet mit Protokoll-Version."""
    with TestClient(main.app) as c:
        info = c.get("/mcp/info").json()
        token = info.get("token")
        assert token and token.startswith("dzmcp_"), \
            f"Kein Token in /mcp/info (serving={info.get('serving')})"
        r = c.post("/mcp",
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26",
                                    "clientInfo": {"name": "test", "version": "0"}}},
                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("result", {}).get("protocolVersion") is not None


def test_mcp_tool_liste_enthaelt_tb_tools():
    """tools/list enthält die TB-spezifischen Monitoring-Tools (Ceiling=hoechst)."""
    with TestClient(main.app) as c:
        info = c.get("/mcp/info").json()
        token = info.get("token")
        assert token, f"Kein Token (info={info})"
        r = c.post("/mcp",
                   json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        tools = r.json().get("result", {}).get("tools", [])
        names = [t["name"] for t in tools]
        assert any("flotte" in n for n in names), f"tradingbot_flotte fehlt: {names}"
        assert any("alerts" in n for n in names), f"tradingbot_alerts fehlt: {names}"
        assert any("master" in n for n in names), f"tradingbot_master fehlt: {names}"


def test_mcp_mode_umschalten():
    """POST /mcp/mode lokal → schaltet Modus um und zurück (idempotent)."""
    with TestClient(main.app) as c:
        r = c.post("/mcp/mode?wert=an")
        assert r.status_code == 200
        assert r.json().get("mode") == "an"
        # zurück auf auto
        r2 = c.post("/mcp/mode?wert=auto")
        assert r2.status_code == 200
        assert r2.json().get("mode") == "auto"


# ------------------------------------------------------------------ Mini-Dizzi
def test_mini_dizzi_status_erreichbar():
    """GET /api/ki/status → 200 mit app='tradingbot'."""
    with TestClient(main.app) as c:
        r = c.get("/api/ki/status")
        assert r.status_code == 200
        d = r.json()
        assert d.get("app") == "tradingbot"
        assert "app_ki_registriert" in d


def test_mini_dizzi_frage_antwortet():
    """POST /api/ki/frage → 200 + antwort-Schlüssel (Ollama-Fallback ohne API-Key)."""
    with TestClient(main.app) as c:
        r = c.post("/api/ki/frage", json={"frage": "Wie viele Bots laufen?"})
        assert r.status_code == 200
        assert "antwort" in r.json()


def test_mini_dizzi_leere_frage_kein_500():
    """POST /api/ki/frage mit leerem Text → saubere Antwort, kein 500."""
    with TestClient(main.app) as c:
        r = c.post("/api/ki/frage", json={"frage": ""})
        assert r.status_code == 200
        assert "antwort" in r.json()


def test_mini_dizzi_settings_im_schema():
    """Settings-Schema enthält Mini-Dizzi-Schlüssel (mini_dizzi_aktiv, voice_modus)."""
    with TestClient(main.app) as c:
        schema = c.get("/api/settings/schema").json()
        ki_keys = [d["key"] for d in schema["kategorien"].get("ki", [])]
        assert "mini_dizzi_aktiv" in ki_keys, f"mini_dizzi_aktiv fehlt in ki: {ki_keys}"
        vern_keys = [d["key"] for d in schema["kategorien"].get("vernetzung", [])]
        assert "voice_modus" in vern_keys, f"voice_modus fehlt in vernetzung: {vern_keys}"
