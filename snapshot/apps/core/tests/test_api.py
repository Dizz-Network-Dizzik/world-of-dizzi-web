from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_panels_endpoint():
    r = client.get("/api/panels")
    assert r.status_code == 200
    assert len(r.json()) == 10  # 8 Apps + systeminfo + tradingbot (plans/leading→admin verschmolzen, musik eingeschmolzen)


def test_sicherheit_lage_endpoint():
    """SF-1 (docs/82 §3): Ampel des Hubs — localhost, Stufe lokal, 5 Checks, wirft nie."""
    r = client.get("/api/sicherheit/lage")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "core"
    assert body["gesamt"] in ("gruen", "gelb", "rot", "unbekannt")
    assert {c["id"] for c in body["checks"]} == {
        "fde", "db_at_rest", "vault_schluessel", "backup_crypto", "auto_lock"}


def test_panel_stats_endpoint():
    r = client.get("/api/panels/systeminfo/stats")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_panel_stats_404():
    assert client.get("/api/panels/nix/stats").status_code == 404


def test_settings_roundtrip():
    r = client.put("/api/settings", json={"key": "lang", "value": "de"})
    assert r.status_code == 200
    assert client.get("/api/settings").json()["lang"] == "de"


def test_audit_endpoint():
    client.put("/api/settings", json={"key": "x", "value": 1})
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "setting_changed" in actions
