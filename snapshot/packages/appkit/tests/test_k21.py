"""Tests K2.1a: erweitertes Basis-Schema (docs/19 §2) + Re-Auth-Frische
(require_fresh_stepup) für sensible Aktionen."""

from __future__ import annotations

import time

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from appkit import auth
from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.settings_core import make_schema
from appkit.summary import Kpi


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


def test_basis_schema_k21_ergaenzungen():
    keys = {d.key for d in make_schema().defs}
    assert {"avatar_farbe", "reauth_sensibel", "login_benachrichtigung",
            "ki_vorschlaege_aktiv", "mcp_freigegeben", "cross_app_zugriff",
            "dichte", "reduzierte_bewegung", "backup_verschluesselt",
            "export_format"} <= keys
    by = make_schema().by_key()
    assert by["reauth_sensibel"].default is True            # Sicherheit per Default AN
    assert by["cross_app_zugriff"].default == "fragen"


def _app(tmp_path):
    router = APIRouter()

    @router.post("/api/export",
                 dependencies=[Depends(auth.require_fresh_stepup("hochsicher", 300))])
    def export():
        return {"export": True}

    return create_app(
        AppManifest(id="k21app", name="K21", brand="Dizz K21",
                    version="0.1.0", port=8296),
        Database(tmp_path / "k21.sqlite"),
        summary_fn=lambda: [Kpi(id="n", label="N", value=1)], routers=[router])


def test_fresh_stepup_fail_closed_und_frisch(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        # standalone (auth_time None) ⇒ fail-closed
        assert c.post("/api/export").status_code == 403

        # hochsicher, aber Step-up 10 Minuten alt ⇒ 403 (Frische verlangt)
        auth.set_identity_provider(lambda _r: auth.UserContext(
            "dizzi", level="hochsicher", via="dizzi-id",
            auth_time=time.time() - 600))
        r = c.post("/api/export")
        assert r.status_code == 403 and "Frische" in r.json()["detail"]

        # hochsicher + frisch ⇒ erlaubt
        auth.set_identity_provider(lambda _r: auth.UserContext(
            "dizzi", level="hochsicher", via="dizzi-id", auth_time=time.time() - 5))
        assert c.post("/api/export").status_code == 200

        # frisch, aber nur 'verifiziert' ⇒ Stufe fehlt ⇒ 403
        auth.set_identity_provider(lambda _r: auth.UserContext(
            "dizzi", level="verifiziert", via="dizzi-id", auth_time=time.time()))
        assert c.post("/api/export").status_code == 403

    with pytest.raises(ValueError):
        auth.require_fresh_stepup("gott")
