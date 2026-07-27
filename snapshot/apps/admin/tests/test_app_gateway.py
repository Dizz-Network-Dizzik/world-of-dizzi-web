"""Tests per-App-MCP-Gateway (appkit.app_gateway, docs/31 §7) — die Föderations-
Variante: eine App bietet im STANDALONE-Betrieb ihr eigenes MCP-Gate an und schaltet
es im Modus 'auto' ab, sobald der Core sein zentrales Gateway führt. Geprüft am
appkit-Modul direkt (Fake-DB + injizierte api_get/central_probe — kein echter Server)."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from appkit.app_gateway import build_app_gateway


class _FakeDB:
    def __init__(self):
        self._s = {}

    def setting_get(self, uid, key, default=None):
        return self._s.get(key, default)

    def setting_put(self, uid, key, value):
        self._s[key] = value

    def audit(self, *a, **k):
        pass


def _build(central=False):
    db = _FakeDB()
    man = SimpleNamespace(id="admin", sensitivity="hoch", port=8222)

    def _api(path, params):
        return {"path": path, "params": params}

    router = build_app_gateway(
        man, db,
        tools=[("kpis", "/api/stats", "KPIs"),
               ("dokument_datei", "/api/dokumente/x/datei", "Dateiinhalt")],  # *_datei* ⇒ hochsicher
        base_url="http://127.0.0.1:8222", api_get=_api, central_probe=lambda: central)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _rpc(c, method, params=None, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    return c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method,
                                "params": params or {}}, headers=h)


def test_standalone_serving_und_protokoll():
    c = _build(central=False)                       # Core-Gate aus ⇒ auto ⇒ serving
    info = c.get("/mcp/info").json()
    assert info["serving"] is True and info["mode"] == "auto"
    tok = info["token"]
    assert _rpc(c, "initialize").status_code == 401  # Token nötig
    init = _rpc(c, "initialize", token=tok).json()
    assert init["result"]["serverInfo"]["name"].startswith("Dizz admin")
    namen = [t["name"] for t in _rpc(c, "tools/list", token=tok).json()["result"]["tools"]]
    assert "admin_kpis" in namen
    assert "admin_dokument_datei" not in namen      # hochsicher (Muster *_datei*) gesperrt
    tc = _rpc(c, "tools/call", {"name": "admin_kpis"}, token=tok).json()
    assert tc["result"]["isError"] is False and "/api/stats" in tc["result"]["content"][0]["text"]
    blk = _rpc(c, "tools/call", {"name": "admin_dokument_datei"}, token=tok).json()
    assert blk["result"]["isError"] is True


def test_auto_deaktiviert_wenn_core_gateway_aktiv():
    c = _build(central=True)                         # Core-Gate AN ⇒ auto ⇒ NICHT serving
    assert c.get("/mcp/info").json()["serving"] is False
    assert _rpc(c, "initialize").status_code == 403  # inaktiv
    # Modus 'an' erzwingt das App-Gate trotz aktivem Core-Gateway
    c.post("/mcp/mode", params={"wert": "an"})
    info = c.get("/mcp/info").json()
    assert info["serving"] is True
    assert _rpc(c, "initialize", token=info["token"]).status_code == 200
    # Modus 'aus' ⇒ nie
    c.post("/mcp/mode", params={"wert": "aus"})
    assert c.get("/mcp/info").json()["serving"] is False


def test_hochsicher_freigabe():
    c = _build(central=False)
    tok = c.get("/mcp/info").json()["token"]
    sichtbar = lambda: [t["name"] for t in _rpc(c, "tools/list", token=tok).json()["result"]["tools"]]
    assert "admin_dokument_datei" not in sichtbar()
    c.post("/mcp/freigabe-hochsicher", params={"minuten": 5})
    assert "admin_dokument_datei" in sichtbar()
    c.post("/mcp/freigabe-sperren")
    assert "admin_dokument_datei" not in sichtbar()
