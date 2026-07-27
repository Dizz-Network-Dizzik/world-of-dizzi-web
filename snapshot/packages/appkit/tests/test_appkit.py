"""Tests der Vertrags-Bibliothek (K3): DB-Konventionen, Auth-Slot (fail-closed),
App-Fabrik inkl. Konformitäts-Suite, Summary-Robustheit, MCP-Helfer."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from appkit import CONTRACT_VERSION, auth, conformance
from appkit.app import create_app
from appkit.db import Database, default_db_path
from appkit.manifest import AppManifest
from appkit.summary import Kpi, Summary, normalize


# --- Bausteine ---------------------------------------------------------------

def _manifest(**over) -> AppManifest:
    base = dict(id="testapp", name="Test-App", brand="Dizz Test",
                version="0.1.0", port=8299, sensitivity="normal")
    base.update(over)
    return AppManifest(**base)


def _db(tmp_path, extra: str = "") -> Database:
    return Database(tmp_path / "test.sqlite", extra_schema=extra)


@pytest.fixture(autouse=True)
def _clean_auth():
    """Jeder Test startet und endet mit dem Standalone-Provider."""
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


# --- Datenbank: Konventionen -------------------------------------------------

def test_db_settings_roundtrip_und_audit(tmp_path):
    db = _db(tmp_path)
    db.setting_put("u1", "farbe", {"ton": "cyan"})
    assert db.setting_get("u1", "farbe") == {"ton": "cyan"}
    assert db.setting_get("u2", "farbe") is None          # user-scoped
    db.setting_put("u1", "farbe", "magenta")              # upsert
    assert db.settings_all("u1") == {"farbe": "magenta"}

    db.audit("u1", "system", "test_aktion", {"x": 1})
    recent = db.audit_recent("u1")
    assert recent and recent[0]["action"] == "test_aktion"
    assert recent[0]["detail"] == {"x": 1}


def test_db_pragmas_wal_fk_busy_timeout(tmp_path):
    """Robustheits-Pragmas: WAL (Leser blocken Schreiber nicht), foreign_keys=ON
    (Kaskaden greifen) und busy_timeout>0 (parallele Writer warten statt sofortigem
    SQLITE_BUSY/„database is locked"). Kern-Dauerschleife R3 (appkit 1.21.2)."""
    conn = _db(tmp_path).get_conn()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000


def test_db_extra_schema_und_default_pfad(tmp_path):
    db = _db(tmp_path, extra="""
        CREATE TABLE IF NOT EXISTS dinge (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
        );""")
    conn = db.get_conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(dinge)")}
    assert {"id", "user_id", "created_at", "updated_at", "deleted_at"} <= cols

    p = default_db_path("finanzen", data_root=tmp_path)
    assert p == tmp_path / "apps" / "finanzen" / "finanzen.sqlite"


def test_db_schema_tolerant_gegen_index_auf_migrationsspalte(tmp_path):
    """docs/25 H-8 (Wurzel-Härtung): ein Schema-Index auf einer Spalte, die es auf
    einer ALT-DB noch nicht gibt (erst per App-Migration ``ALTER … ADD COLUMN``
    nachgerüstet), darf den App-Start NICHT blockieren. ``get_conn`` überspringt die
    scheiternde Einzel-Anweisung statt den ganzen Schema-Lauf abzubrechen —
    ``CREATE TABLE IF NOT EXISTS`` (auch nach dem Index!) bleibt voll erhalten."""
    import sqlite3
    dbp = tmp_path / "apps" / "x" / "x.sqlite"
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dbp)              # v1-Bestands-DB: Tabelle OHNE Spalte 'neu'
    con.executescript("CREATE TABLE dinge (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
                      "created_at TEXT NOT NULL);")
    con.execute("INSERT INTO dinge VALUES ('a','dizzi','t')")
    con.commit(); con.close()
    # v2-Schema: Tabelle MIT 'neu' + Index auf 'neu' (scheitert auf der v1-DB) +
    # eine ganz NEUE Tabelle NACH dem Index (würde ohne Härtung nicht angelegt).
    v2 = ("CREATE TABLE IF NOT EXISTS dinge (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
          "neu TEXT, created_at TEXT NOT NULL);"
          "CREATE INDEX IF NOT EXISTS idx_dinge_neu ON dinge (user_id, neu);"
          "CREATE TABLE IF NOT EXISTS frisch (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);")
    db = Database(dbp, extra_schema=v2)
    conn = db.get_conn()                   # darf NICHT crashen
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='frisch'"
                        ).fetchone() is not None          # neue Tabelle trotz Index-Fehler da
    # App-Migration rüstet die Spalte nach ⇒ der nächste Verbindungs-Lauf legt den Index an.
    conn.execute("ALTER TABLE dinge ADD COLUMN neu TEXT"); conn.commit()
    db.reset_thread_conn()
    conn2 = db.get_conn()
    assert conn2.execute("SELECT name FROM sqlite_master WHERE type='index' "
                         "AND name='idx_dinge_neu'").fetchone() is not None


# --- Auth-Slot: fail-closed + K1-Austauschpunkt -------------------------------

def _mini_app(tmp_path, level: str):
    router = APIRouter()

    @router.get("/api/geschuetzt",
                dependencies=[Depends(auth.require_level(level))])
    def geschuetzt():
        return {"zugang": True}

    return create_app(_manifest(), _db(tmp_path),
                      summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
                      routers=[router])


def test_auth_lokal_erlaubt_hoehere_stufen_fail_closed(tmp_path):
    app = _mini_app(tmp_path, "lokal")
    with TestClient(app) as c:
        assert c.get("/api/geschuetzt").status_code == 200

    app2 = _mini_app(tmp_path, "hochsicher")
    with TestClient(app2) as c:
        r = c.get("/api/geschuetzt")
        assert r.status_code == 403                       # fail-closed vor K1
        assert "hochsicher" in r.json()["detail"]


def test_auth_provider_austauschbar_k1_slot(tmp_path):
    app = _mini_app(tmp_path, "verifiziert")
    auth.set_identity_provider(
        lambda _req: auth.UserContext("dizzi", level="verifiziert", via="dizzi-id"))
    with TestClient(app) as c:
        assert c.get("/api/geschuetzt").status_code == 200


def test_require_level_unbekannte_stufe():
    with pytest.raises(ValueError):
        auth.require_level("gott")


# --- Summary: Normalisierung + Robustheit -------------------------------------

def test_summary_normalize_liste_und_leer():
    s = normalize("a", "A", "2026-06-11T00:00:00+00:00",
                  [Kpi(id="x", label="X", value=3, unit="Stk")])
    assert s.status == "ok" and s.kpis[0].unit == "Stk"
    s2 = normalize("a", "A", "2026-06-11T00:00:00+00:00", [])
    assert s2.status == "leer"
    with pytest.raises(TypeError):
        normalize("a", "A", "ts", "quatsch")


def test_summary_endpoint_faengt_fehler_als_status(tmp_path):
    def kaputt():
        raise RuntimeError("Domäne explodiert")
    app = create_app(_manifest(), _db(tmp_path), summary_fn=kaputt)
    with TestClient(app) as c:
        r = c.get("/api/summary")
        assert r.status_code == 200                       # nie 500 fürs Dashboard
        s = Summary(**r.json())
        assert s.status == "fehler" and s.ok is False
        assert "Domäne explodiert" in (s.note or "")


# --- App-Fabrik: volle Vertrags-Konformität ------------------------------------

def test_create_app_erfuellt_vertrag(tmp_path):
    app = create_app(_manifest(), _db(tmp_path),
                     summary_fn=lambda: [Kpi(id="n", label="Anzahl", value=7)])
    with TestClient(app) as c:
        conformance.check_contract(c, "testapp")
        # Start-Audit aus der Lifespan ist protokolliert
        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "app_started" in actions


def test_manifest_deep_link_und_vertragsversion():
    m = _manifest(port=8210)
    assert m.url == "http://127.0.0.1:8210"
    assert m.contract == CONTRACT_VERSION
    assert m.model_dump()["url"] == "http://127.0.0.1:8210"  # serialisiert


# --- MCP-Helfer ----------------------------------------------------------------

def test_build_http_mcp_namespaced_tools():
    """build_http_mcp präfixt jeden Tool-Namen mit der app_id (Namensraum, docs/16 §6)."""
    pytest.importorskip("fastmcp")
    from appkit.mcp import build_http_mcp
    mcp = build_http_mcp("testapp", "http://127.0.0.1:1",
                         [("status", "/api/summary", "Kachel-Stats."),
                          ("gesund", "/api/health", "Lebenszeichen.")])
    import asyncio
    werkzeuge = asyncio.run(mcp.list_tools())
    names = {t.name for t in werkzeuge}
    assert {"testapp_status", "testapp_gesund"} <= names
    assert "status" not in names and "gesund" not in names  # kein nackter Name
    # MCP 2025-06-18 (P3.2): read-only-Annotationen (reine GET-Leser) sind exakt gesetzt
    t0 = werkzeuge[0]
    assert t0.annotations is not None
    assert t0.annotations.readOnlyHint is True and t0.annotations.openWorldHint is False


def test_namespaced_praefix_und_idempotenz():
    """namespaced() = <app_id>_<tool>, idempotent + robust (docs/16 §6)."""
    from appkit.mcp import namespaced
    assert namespaced("news", "briefing") == "news_briefing"
    assert namespaced("news", "news_briefing") == "news_briefing"   # nicht doppelt
    assert namespaced("finanzen", "_kontostand") == "finanzen_kontostand"  # führende _ weg
    assert namespaced("komm", "  suche  ") == "komm_suche"          # getrimmt
