"""Tests RG-2 (docs/83 §1/§4): der netzweite hitl_entschieden-Hook.

Pinnt: (a) ``decide(on_entscheidung=…)`` ist 0-Bruch ohne Hook und ruft ihn bei
FINALER Entscheidung mit den richtigen Feldern; (b) ein kaputter Hook kippt die
gefallene Entscheidung NIE; (c) ``create_app(ereignis_register=…)`` verdrahtet den
Hook zentral ⇒ ein Approve erzeugt EIN hitl_entschieden-Ereignis im Spine — als
reiner Zeiger (kein Inhalt). Runtime-/Ollama-frei.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from appkit import auth, ereignis_spine as es
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


def _reg() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register("mail_senden", lambda p: {"gesendet": True}, level="verifiziert",
                 beschreibung="E-Mail senden")
    return reg


def _pending(db: Database, reg: ActionRegistry) -> str:
    return propose(db, reg, "dizzi", "mail_senden", {"an": "k@example.org"},
                   source="agent", agent_id="triage-1", warum="Kunde wartet",
                   lauf_id="lauf-9")["id"]


# --- standard_register ------------------------------------------------------------

def test_standard_register_hat_hitl():
    reg = es.standard_register("kommunikation")
    assert reg.kennt("hitl_entschieden")
    # Payload-Vertrag: die fünf Standard-Felder validieren, Freitext fliegt.
    reg.pruefe("hitl_entschieden", {"aktion": "mail_senden", "approve": True,
                                    "status": "executed", "agent_id": "a1", "lauf_id": "l1"})


# --- decide-Hook: gerufen / 0-Bruch / robust -------------------------------------

def test_hook_bei_approve_gerufen(tmp_path):
    db, reg = Database(tmp_path / "a.sqlite"), _reg()
    aid = _pending(db, reg)
    gesammelt: list[dict] = []
    decide(db, reg, "dizzi", aid, approve=True, on_entscheidung=gesammelt.append)
    assert len(gesammelt) == 1
    i = gesammelt[0]
    assert (i["name"], i["approve"], i["status"]) == ("mail_senden", True, "executed")
    assert (i["agent_id"], i["lauf_id"], i["level"]) == ("triage-1", "lauf-9", "verifiziert")


def test_hook_bei_reject_gerufen(tmp_path):
    db, reg = Database(tmp_path / "a.sqlite"), _reg()
    aid = _pending(db, reg)
    gesammelt: list[dict] = []
    decide(db, reg, "dizzi", aid, approve=False, on_entscheidung=gesammelt.append)
    assert len(gesammelt) == 1
    assert (gesammelt[0]["approve"], gesammelt[0]["status"]) == (False, "rejected")


def test_hook_nicht_bei_unbekannt(tmp_path):
    db, reg = Database(tmp_path / "a.sqlite"), _reg()
    gesammelt: list[dict] = []
    r = decide(db, reg, "dizzi", "gibts-nicht", approve=True,
               on_entscheidung=gesammelt.append)
    assert r is None and gesammelt == []          # kein Event ohne echte Entscheidung


def test_ohne_hook_0_bruch(tmp_path):
    db, reg = Database(tmp_path / "a.sqlite"), _reg()
    aid = _pending(db, reg)
    r = decide(db, reg, "dizzi", aid, approve=True)     # kein on_entscheidung
    assert r["status"] == "executed"


def test_kaputter_hook_kippt_entscheidung_nicht(tmp_path):
    db, reg = Database(tmp_path / "a.sqlite"), _reg()
    aid = _pending(db, reg)

    def boese(info):
        raise RuntimeError("Hook kaputt")

    r = decide(db, reg, "dizzi", aid, approve=True, on_entscheidung=boese)
    assert r["status"] == "executed"                # Wirkung steht trotz kaputtem Hook


# --- create_app-Integration: netzweit + Zeiger-nie-Inhalt ------------------------

def _app(tmp_path) -> tuple[TestClient, str]:
    reg_akt = ActionRegistry()
    reg_akt.register("notiz", lambda p: {"ok": True}, level="lokal",
                     beschreibung="interne Notiz")
    ev_reg = es.standard_register("kommunikation")
    db = Database(tmp_path / "k.sqlite", extra_schema=es.SCHEMA_EREIGNISSE_SQL)
    manifest = AppManifest(id="kommunikation", name="K", brand="Dizz K",
                           version="1.0", port=8299, icon="mail", sensitivity="normal")
    app = create_app(manifest, db, lambda: [Kpi(label="x", value="1")],
                     actions=reg_akt, ereignis_register=ev_reg,
                     defense=False, mini_dizzi=False, netz=False,
                     fehlerseite=False, sicherheit=False)
    return TestClient(app), "notiz"


def test_create_app_emittiert_hitl_als_zeiger(tmp_path):
    c, _ = _app(tmp_path)
    pr = c.post("/api/actions/propose",
                json={"name": "notiz", "params": {"geheimer_text": "streng-vertraulich"},
                      "source": "agent", "agent_id": "a1", "warum": "weil"})
    assert pr.status_code == 200
    aid = pr.json()["id"]
    ap = c.post(f"/api/actions/{aid}/approve")
    assert ap.status_code == 200 and ap.json()["status"] == "executed"

    ev = c.get("/api/ereignisse").json()["eintraege"]
    assert len(ev) == 1
    e = ev[0]
    assert e["typ"] == "hitl_entschieden"
    assert e["payload"]["aktion"] == "notiz" and e["payload"]["approve"] is True
    assert e["klasse"] == "entwurf"                 # level 'lokal' → klasse 'entwurf'
    assert e["ref"] == f"kommunikation:aktion:{aid}"
    # Zeiger, nie Inhalt: der geheime Notiz-Text taucht NIRGENDS im Ereignis auf.
    assert "streng-vertraulich" not in json.dumps(e)


def test_create_app_ohne_register_kein_spine(tmp_path):
    # 0-Bruch: eine App ohne ereignis_register hat keinen /api/ereignisse-Pfad
    # und emittiert nichts — der Hook ist None.
    reg_akt = ActionRegistry()
    reg_akt.register("notiz", lambda p: {"ok": True}, level="lokal", beschreibung="x")
    db = Database(tmp_path / "n.sqlite")
    manifest = AppManifest(id="news", name="N", brand="Dizz N", version="1.0",
                           port=8298, icon="news", sensitivity="normal")
    app = create_app(manifest, db, lambda: [Kpi(label="x", value="1")],
                     actions=reg_akt, defense=False, mini_dizzi=False, netz=False,
                     fehlerseite=False, sicherheit=False)
    c = TestClient(app)
    assert c.get("/api/ereignisse").status_code == 404      # kein Spine-Router
    pr = c.post("/api/actions/propose",
                json={"name": "notiz", "params": {}, "source": "user"})
    c.post(f"/api/actions/{pr.json()['id']}/approve")       # kein Crash ohne Hook
