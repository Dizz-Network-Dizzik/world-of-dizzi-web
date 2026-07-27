"""Tests K4: Aktions-Vorschläge mit Human-in-the-Loop-Stufen."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from appkit import auth
import appkit.actions as actions_mod
from appkit.actions import ActionRegistry, decide, propose
from appkit.app import create_app
from appkit.db import Database
from appkit.manifest import AppManifest
from appkit.summary import Kpi


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


def _app(tmp_path):
    reg = ActionRegistry()
    ausgefuehrt: list[dict] = []

    def post_handler(params):
        ausgefuehrt.append(params)
        return {"post_id": "p-1"}

    def kaputt_handler(params):
        raise RuntimeError("Plattform down")

    reg.register("post_veroeffentlichen", post_handler, level="verifiziert",
                 beschreibung="Beitrag auf Kanälen veröffentlichen")
    reg.register("notiz_aufraeumen", lambda p: "ok", level="lokal",
                 beschreibung="Harmlose Hausarbeit")
    reg.register("echtgeld_zuweisen", post_handler, level="hochsicher",
                 beschreibung="Kapital einem Bot zuweisen")
    reg.register("wackelig", kaputt_handler, level="lokal")

    manifest = AppManifest(id="k4app", name="K4-App", brand="Dizz K4",
                           version="0.1.0", port=8298)
    app = create_app(manifest, Database(tmp_path / "k4.sqlite"),
                     summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
                     actions=reg)
    return app, ausgefuehrt


def test_registry_validierung():
    reg = ActionRegistry()
    reg.register("a", lambda p: p, level="lokal")
    with pytest.raises(ValueError):
        reg.register("a", lambda p: p)                    # doppelt
    with pytest.raises(ValueError):
        reg.register("b", lambda p: p, level="gott")      # unbekannte Stufe


def test_propose_approve_fuehrt_aus(tmp_path):
    app, ausgefuehrt = _app(tmp_path)
    with TestClient(app) as c:
        r = c.post("/api/actions/propose",
                   json={"name": "notiz_aufraeumen", "params": {"x": 1},
                         "source": "mcp"})
        assert r.status_code == 200
        aid = r.json()["id"]
        assert r.json()["status"] == "pending"            # NICHTS ausgeführt

        liste = c.get("/api/actions?status=pending").json()["liste"]
        assert [a["id"] for a in liste] == [aid]

        r = c.post(f"/api/actions/{aid}/approve")
        assert r.status_code == 200 and r.json()["status"] == "executed"
        assert r.json()["result"] == "ok"

        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert "aktion_vorgeschlagen" in actions and "aktion_freigegeben" in actions


def test_hitl_stufen_werden_erzwungen(tmp_path):
    app, ausgefuehrt = _app(tmp_path)
    with TestClient(app) as c:
        aid = c.post("/api/actions/propose",
                     json={"name": "echtgeld_zuweisen",
                           "params": {"bot": "b1", "eur": 100}}).json()["id"]
        # Standalone-Stufe 'lokal' ⇒ Freigabe einer hochsicher-Aktion: 403
        r = c.post(f"/api/actions/{aid}/approve")
        assert r.status_code == 403 and ausgefuehrt == []

        # Mit hochsicher-Identität (K1+TOTP) ⇒ Freigabe läuft
        auth.set_identity_provider(
            lambda _r: auth.UserContext("dizzi", level="hochsicher", via="dizzi-id"))
        r = c.post(f"/api/actions/{aid}/approve")
        assert r.status_code == 200 and r.json()["status"] == "executed"
        assert ausgefuehrt == [{"bot": "b1", "eur": 100}]


def test_reject_und_unbekannt_und_fehler(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app) as c:
        aid = c.post("/api/actions/propose",
                     json={"name": "notiz_aufraeumen"}).json()["id"]
        assert c.post(f"/api/actions/{aid}/reject").json()["status"] == "rejected"
        assert c.post(f"/api/actions/{aid}/approve").status_code == 404  # nicht mehr pending

        assert c.post("/api/actions/propose",
                      json={"name": "gibt_es_nicht"}).status_code == 404

        aid2 = c.post("/api/actions/propose", json={"name": "wackelig"}).json()["id"]
        r = c.post(f"/api/actions/{aid2}/approve")
        assert r.json()["status"] == "failed"
        assert "Plattform down" in r.json()["error"]


def test_executing_zwischenstatus_at_most_once(tmp_path):
    """P1.7: vor dem Handler wird auf 'executing' committet; ein zweiter approve
    waehrend der Ausfuehrung darf NICHT erneut laufen (at-most-once gegen Crash)."""
    db = Database(tmp_path / "exact.sqlite")
    db.get_conn()
    reg = ActionRegistry()
    zustand: dict = {}

    def handler(_p):
        row = db.get_conn().execute(
            "SELECT status FROM app_actions WHERE id=?", (zustand["id"],)).fetchone()
        zustand["im_handler"] = row["status"]
        zustand["re_decide"] = decide(db, reg, "dizzi", zustand["id"], approve=True)
        return "fertig"

    reg.register("tu_was", handler=handler, level="lokal")
    p = propose(db, reg, "dizzi", "tu_was", {})
    zustand["id"] = p["id"]
    res = decide(db, reg, "dizzi", p["id"], approve=True)
    assert zustand["im_handler"] == "executing"
    assert zustand["re_decide"] is None
    assert res["status"] == "executed"


def test_parallel_approve_at_most_once(tmp_path, monkeypatch):
    """F-A: zwei GLEICHZEITIGE approves (je Thread eigene Connection) — beide sehen
    'pending', aber nur der CAS-Gewinner darf den Handler feuern (at-most-once).
    Der 2. now_iso-Aufruf je Thread ist das executing-UPDATE (der 1. wird von
    _expire_stale verbraucht) ⇒ Barrier dort erzwingt das Rennen deterministisch.
    NICHT _expire_stale/den Trigger-Index 'vereinfachen' — sonst mis-targetet die
    Barrier lautlos."""
    db = Database(tmp_path / "race.sqlite"); db.get_conn()
    reg = ActionRegistry(); zaehler = {"n": 0}
    reg.register("einmalig", lambda p: zaehler.__setitem__("n", zaehler["n"] + 1) or "ok", level="lokal")
    p = propose(db, reg, "dizzi", "einmalig", {})
    barrier = threading.Barrier(2); echt = actions_mod.now_iso; tl = threading.local()
    def synced_now_iso():
        tl.n = getattr(tl, "n", 0) + 1
        if tl.n == 2:
            barrier.wait(timeout=5)
        return echt()
    monkeypatch.setattr(actions_mod, "now_iso", synced_now_iso)
    results = [None, None]
    def worker(i):
        results[i] = decide(db, reg, "dizzi", p["id"], approve=True)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert zaehler["n"] == 1                       # Handler GENAU einmal
    gewinner = [r for r in results if r is not None]
    assert len(gewinner) == 1 and gewinner[0]["status"] == "executed"
    assert results.count(None) == 1                # Verlierer: None (kein Re-Run)
    row = db.get_conn().execute("SELECT status FROM app_actions WHERE id=?", (p["id"],)).fetchone()
    assert row["status"] == "executed"
