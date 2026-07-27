"""K2.1b (Vertrag 1.3): Datenrechte — Export + Lösch-Kaskade, Re-Auth-Gate."""

from __future__ import annotations

import time

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from appkit import auth
from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.summary import Kpi

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notizen (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, text TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
);
"""


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


def _app(tmp_path):
    db = Database(tmp_path / "dr.sqlite", extra_schema=_SCHEMA)
    app = create_app(
        AppManifest(id="drtest", name="DR", brand="Dizz DR",
                    version="0.1.0", port=8297),
        db, summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
        routers=[APIRouter()])
    return app, db


def _frisch_verifiziert():
    auth.set_identity_provider(lambda _r: auth.UserContext(
        "dizzi", level="verifiziert", via="dizzi-id",
        auth_time=time.time() - 5))


def test_fail_closed_ohne_reauth(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app) as c:
        assert c.post("/api/account/export").status_code == 403
        assert c.post("/api/account/loeschen").status_code == 403


def test_export_liefert_alles_und_auditiert(tmp_path):
    app, db = _app(tmp_path)
    with TestClient(app) as c:
        c.put("/api/settings", json={"key": "x_marker", "value": 7})
        conn = db.get_conn()
        from appkit.db import new_id, now_iso
        ts = now_iso()
        conn.execute("INSERT INTO notizen VALUES (?,?,?,?,?,NULL)",
                     (new_id(), "dizzi", "geheim", ts, ts))
        conn.commit()
        app.state.vault.put("dienst_x", "token-abc")

        _frisch_verifiziert()
        r = c.post("/api/account/export")
        assert r.status_code == 200
        export = r.json()
        assert export["app"] == "drtest" and export["format"] == "json"
        assert export["tresor_namen"] == ["dienst_x"]
        # Tresor-WERT ist NIRGENDS im Export
        assert "token-abc" not in r.text
        assert export["daten"]["notizen"][0]["text"] == "geheim"
        assert any(s["key"] == "x_marker"
                   for s in export["daten"]["app_settings"])
        audit = [e["action"] for e in c.get("/api/audit").json()]
        assert "daten_exportiert" in audit


def test_loesch_kaskade_und_tresor_wipe(tmp_path):
    app, db = _app(tmp_path)
    with TestClient(app) as c:
        from appkit.db import new_id, now_iso
        ts = now_iso()
        db.get_conn().execute("INSERT INTO notizen VALUES (?,?,?,?,?,NULL)",
                              (new_id(), "dizzi", "weg damit", ts, ts))
        db.get_conn().commit()
        c.put("/api/settings", json={"key": "x_marker", "value": 1})
        app.state.vault.put("dienst_x", "token")

        _frisch_verifiziert()
        r = c.post("/api/account/loeschen").json()
        assert r["ok"] is True and r["tresor_geleert"] is True
        assert r["geloescht"]["notizen"] == 1
        assert app.state.vault.names() == []
        # Soft-Delete: Zeile existiert, ist aber als gelöscht markiert …
        row = db.get_conn().execute("SELECT deleted_at FROM notizen").fetchone()
        assert row["deleted_at"] is not None
        # … und das Audit-Log bleibt (Beleg der Löschung selbst)
        audit = [e["action"] for e in c.get("/api/audit").json()]
        assert "daten_geloescht" in audit


# ===================== H-7: on_delete-Hook (app-eigene Artefakte) =================
def _app_mit_hook(tmp_path, hook):
    db = Database(tmp_path / "hk.sqlite", extra_schema=_SCHEMA)
    app = create_app(
        AppManifest(id="hktest", name="HK", brand="Dizz HK",
                    version="0.1.0", port=8296),
        db, summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
        routers=[APIRouter()], on_delete=hook)
    return app, db


def test_on_delete_hook_wird_mit_user_gerufen(tmp_path):
    gerufen = {}
    app, _ = _app_mit_hook(tmp_path, lambda uid: gerufen.update(uid=uid))
    with TestClient(app) as c:
        _frisch_verifiziert()
        r = c.post("/api/account/loeschen").json()
    assert r["ok"] is True and r["artefakte_geraeumt"] is True
    assert gerufen["uid"] == "dizzi"  # der Single-User


def test_on_delete_fehler_bricht_loeschung_nicht(tmp_path):
    def boom(_uid):
        raise RuntimeError("io kaputt")
    app, db = _app_mit_hook(tmp_path, boom)
    with TestClient(app) as c:
        _frisch_verifiziert()
        r = c.post("/api/account/loeschen").json()
        # Konto-Löschung selbst erfolgt; Artefakt-Räumung ehrlich als False gemeldet
        assert r["ok"] is True and r["tresor_geleert"] is True
        assert r["artefakte_geraeumt"] is False
        audit = [e["action"] for e in c.get("/api/audit").json()]
        assert "on_delete_fehler" in audit and "daten_geloescht" in audit
