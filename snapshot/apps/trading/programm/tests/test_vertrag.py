"""Tests K6: Dizzi-App-Vertrag auf Dizz Trading (RP-Anschluss, Manifest,
Vertrags-Settings, Echtgeld-Gate). Bestands-Routen bleiben unberührt."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app import main


def test_manifest_und_vertrags_endpoints():
    with TestClient(main.app) as c:
        m = c.get("/api/manifest").json()
        assert m["id"] == "tradingbot" and m["brand"] == "Dizz Trading"
        assert m["sensitivity"] == "hoechst"
        assert m["url"] == "http://127.0.0.1:8137"
        assert m["auth"]["status"] == "aktiv"              # RP installiert

        schema = c.get("/api/settings/schema").json()
        assert set(schema["kategorien"]) == {"konto", "sicherheit", "ki",
                                             "vernetzung", "darstellung", "daten"}
        # Sensible App ⇒ KI-Routing default lokal_only
        assert c.get("/api/settings").json()["ki_routing"] == "lokal_only"

        # SSO-Anschluss da; ohne Login Standalone-Stufe 'lokal'
        me = c.get("/auth/me").json()
        assert me == {"angemeldet": False, "level": "lokal"}

        # Bestands-Routen unberührt (Legacy-Kachel + TB-eigenes Konto/Audit)
        assert c.get("/api/summary").status_code == 200
        assert "bots" in c.get("/api/summary").json()


def test_paper_transfer_bleibt_frei():
    with TestClient(main.app) as c:
        r = c.post("/api/transfer", json={"to": "bot-1", "amount": 5,
                                          "confirm": False})
        assert r.status_code == 200                        # Paper: kein Gate
        assert r.json().get("needs_confirmation") is True


def test_echtgeld_transfer_verlangt_hochsicher(monkeypatch):
    echt = SimpleNamespace(bitget_configured=True, dry_run=False)
    monkeypatch.setattr(main, "get_settings", lambda: echt)
    with TestClient(main.app) as c:
        r = c.post("/api/transfer", json={"to": "bot-1", "amount": 5,
                                          "confirm": True})
        assert r.status_code == 403                        # fail-closed ohne Login
        assert "hochsicher" in r.json()["detail"]

    # Mit hochsicher-Identität (Dizzi-ID + TOTP) ist das Gate offen
    import appkit.auth as appkit_auth
    appkit_auth.set_identity_provider(
        lambda _r: appkit_auth.UserContext("dizzi", level="hochsicher",
                                           via="dizzi-id"))
    try:
        with TestClient(main.app) as c:
            r = c.post("/api/transfer", json={"to": "bot-1", "amount": 5,
                                              "confirm": True})
            assert r.status_code == 200                    # Gate offen …
            assert r.json()["ok"] is False                 # … transfer.py blockt
            assert "Transfer-Recht" in r.json()["error"]   # (kein Transfer-Key)
    finally:
        appkit_auth.reset_identity_provider()
