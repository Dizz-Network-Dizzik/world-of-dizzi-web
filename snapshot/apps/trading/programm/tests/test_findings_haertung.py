"""Tests fuer den Findings-Haertungs-Pass (16.06.2026):

F2 — destruktive Flotten-Befehle (component/command pause_all/resume_all) verlangen
     zusaetzlich die Schutzstufe 'verifiziert' (fail-closed; Einzel-Bot-Steuerung unberuehrt).
F5 — Rueck-Lese-Endpunkt /api/wissen/suche liest best-effort aus dem zentralen Archiv
     (appkit.querverbindung.memory_suche), wirft nie, READ-ONLY.
"""
from fastapi.testclient import TestClient

from appkit import auth as appkit_auth
from backend.app import vertrag
from backend.app.main import app


# --- F2: Steuerstufe -----------------------------------------------------------------------------
def test_require_steuerstufe_blockt_lokal():
    """Ohne Anmeldung (Standalone-Stufe 'lokal') ist ein destruktiver Befehl verboten."""
    appkit_auth.reset_identity_provider()
    fehler = vertrag.require_steuerstufe(None)
    assert fehler is not None and "verifiziert" in fehler


def test_require_steuerstufe_erlaubt_verifiziert():
    """Eine verifizierte Verbindung darf den destruktiven Befehl ausloesen."""
    appkit_auth.set_identity_provider(
        lambda req: appkit_auth.UserContext(user_id="t", level="verifiziert", via="test"))
    try:
        assert vertrag.require_steuerstufe(None) is None
    finally:
        appkit_auth.reset_identity_provider()


def test_component_command_pause_all_braucht_verifiziert():
    """Endpunkt-Gate: pause_all (mit confirm) wird ohne 'verifiziert' mit 403 abgewiesen —
    BEVOR irgendein Bot angefasst wird."""
    appkit_auth.reset_identity_provider()
    client = TestClient(app)
    r = client.post("/api/component/command",
                    json={"action": "pause_all", "params": {"confirm": True}})
    assert r.status_code == 403
    assert "verifiziert" in r.json().get("detail", "")


def test_component_command_safe_aktion_ohne_login():
    """Nicht-destruktive Befehle (z. B. report) bleiben ohne Login erreichbar."""
    appkit_auth.reset_identity_provider()
    client = TestClient(app)
    r = client.post("/api/component/command", json={"action": "report"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


# --- F5: Rueck-Lese ------------------------------------------------------------------------------
def test_wissen_suche_leerer_begriff():
    client = TestClient(app)
    r = client.get("/api/wissen/suche", params={"q": "   "})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_wissen_suche_reicht_treffer_durch(monkeypatch):
    """Der Endpunkt delegiert an appkit.querverbindung.memory_suche und reicht das Ergebnis durch."""
    from appkit import querverbindung
    calls = {}

    def fake(begriff, **kw):
        calls["q"] = begriff
        calls["kw"] = kw
        return {"ok": True, "treffer": [{"titel": "x", "auszug": "y"}], "anzahl": 1}

    monkeypatch.setattr(querverbindung, "memory_suche", fake)
    client = TestClient(app)
    r = client.get("/api/wissen/suche", params={"q": "BTC", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["anzahl"] == 1
    assert calls["q"] == "BTC" and calls["kw"]["limit"] == 5
