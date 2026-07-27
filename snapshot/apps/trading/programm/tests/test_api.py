"""API-Tests: Versionierungs-Alias (/api/v1 == /api) + Health (Produkt-Vorbereitung)."""
from fastapi.testclient import TestClient

import backend.app.main as M
from backend.app.main import app

client = TestClient(app)


def test_owner_token_off_by_default(monkeypatch):
    monkeypatch.setattr(M, "_API_TOKEN", "")
    assert client.post("/api/__nonexistent__").status_code == 404   # kein Gate -> normales Routing


def test_owner_token_gate_when_set(monkeypatch):
    monkeypatch.setattr(M, "_API_TOKEN", "secret123")
    assert client.post("/api/__nonexistent__").status_code == 401              # ohne Token
    assert client.post("/api/__nonexistent__",
                       headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/__nonexistent__",
                       headers={"Authorization": "Bearer secret123"}).status_code == 404  # passiert Gate
    assert client.get("/api/strategies").status_code == 200                    # GET ungeschützt


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_v1_alias_matches_legacy():
    legacy = client.get("/api/strategies")
    v1 = client.get("/api/v1/strategies")
    assert legacy.status_code == 200 and v1.status_code == 200
    assert v1.json() == legacy.json()


def test_mn_config_triggers_auto_train():
    # Setzt man eine MN-Engine-Config (Lern-Loop), löst der Master automatisch einen Trainingsschritt
    # aus, damit die Ensemble-Politik mitwächst. Leerer Patch = keine Änderung, prüft nur die Verdrahtung.
    r = client.post("/api/csm/config", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and "config" in body
    assert isinstance(body.get("master"), dict)   # Auto-Train-Resultat (improved/version oder error)


def test_meta_insights_present():
    r = client.get("/api/meta")
    assert r.status_code == 200
    ins = r.json().get("insights")
    assert ins and "headline" in ins and "per_strategy" in ins
    assert isinstance(ins["lessons"], list) and ins["lessons"]
    assert "echtgeldreif_count" in ins
