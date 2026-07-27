"""Tests Z4.1-B (docs/63 §2): additive Inbox-Erweiterung von app_actions.

Kernversprechen: **0-Bruch**. Bestands-Aufrufer (``source='ki'/'mcp'``) verhalten
sich byte-nah wie vorher; Agenten-Vorschläge tragen agent_id/warum/lauf_id; ein
Agent OHNE Warum wird abgelehnt; und eine BESTANDS-DB mit alten pending-Zeilen ohne
die neuen Spalten überlebt den Migrations-Übergang ohne Crash.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from appkit import auth
from appkit.actions import (ActionRegistry, decide, listing,
                            migriere_actions_inbox, propose)
from appkit.agenten import INBOX_ZUSATZSPALTEN, inbox_eintrag
from appkit.app import create_app
from appkit.db import Database, new_id, now_iso
from appkit.manifest import AppManifest
from appkit.summary import Kpi


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


def _reg() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register("email_senden", lambda p: {"gesendet": True}, level="verifiziert",
                 beschreibung="E-Mail senden (Außenwirkung)")
    return reg


def _spalten(db: Database) -> list[str]:
    return [r["name"] for r in db.get_conn().execute("PRAGMA table_info(app_actions)")]


# --- Migration ---------------------------------------------------------------

def test_migration_idempotent(tmp_path):
    db = Database(tmp_path / "m.sqlite")
    db.get_conn()
    migriere_actions_inbox(db)
    migriere_actions_inbox(db)                      # zweiter Lauf ⇒ kein Fehler
    cols = _spalten(db)
    for name, _ddl in INBOX_ZUSATZSPALTEN:
        assert cols.count(name) == 1                # genau einmal, kein Doppel-ALTER


# --- Agenten-Herkunft durchgereicht -----------------------------------------

def test_propose_agent_felder_in_listing_und_projektion(tmp_path):
    db = Database(tmp_path / "a.sqlite")
    reg = _reg()
    p = propose(db, reg, "dizzi", "email_senden", {"an": "k@example.org"},
                source="agent", agent_id="triage-1", warum="Kunde wartet seit 3 Tagen",
                lauf_id="lauf-9")
    assert p["status"] == "pending"
    zeile = listing(db, "dizzi", reg)[0]
    assert zeile["agent_id"] == "triage-1"
    assert zeile["warum"] == "Kunde wartet seit 3 Tagen"
    assert zeile["lauf_id"] == "lauf-9" and zeile["source"] == "agent"
    # Netz-Inbox-Projektion (P3): WAS+WARUM+Argumente + Herkunft + Klasse aus Level
    e = inbox_eintrag("kommunikation", zeile, "verifiziert")
    assert (e["was"], e["warum"]) == ("email_senden", "Kunde wartet seit 3 Tagen")
    assert e["argumente"] == {"an": "k@example.org"}
    assert e["agent_id"] == "triage-1" and e["lauf_id"] == "lauf-9"
    assert e["klasse"] == "aussenwirkung"


def test_agent_ohne_warum_wird_abgelehnt(tmp_path):
    db = Database(tmp_path / "b.sqlite")
    reg = _reg()
    with pytest.raises(ValueError, match="ohne WARUM"):
        propose(db, reg, "dizzi", "email_senden", {}, source="agent", warum="   ")
    # nichts wurde angelegt (Inbox bleibt sauber)
    assert listing(db, "dizzi", reg) == []


def test_bestand_ki_vorschlag_unveraendert(tmp_path):
    """Bestands-Aufrufer ohne die neuen Keyword-Args: neue Felder leer, Fluss intakt."""
    db = Database(tmp_path / "c.sqlite")
    reg = _reg()
    propose(db, reg, "dizzi", "email_senden", {"an": "x"}, source="mcp")
    zeile = listing(db, "dizzi", reg)[0]
    assert zeile["source"] == "mcp"
    assert zeile["agent_id"] == "" and zeile["warum"] == "" and zeile["lauf_id"] == ""


def test_bestands_db_ohne_spalten_kein_crash(tmp_path):
    """Bestands-DB mit einer ALTEN pending-Zeile OHNE die neuen Spalten (wie auf den
    10 Live-Apps vor dem Upgrade): listing() darf NICHT crashen, sondern liefert die
    Zeile mit leeren Herkunftsfeldern (spalten-tolerantes _row_get)."""
    db = Database(tmp_path / "old.sqlite")
    conn = db.get_conn()                             # _BASE_SCHEMA: app_actions OHNE Zusatzspalten
    assert "warum" not in _spalten(db)               # Vorbedingung: Spalten fehlen noch
    ts = now_iso()
    conn.execute(
        "INSERT INTO app_actions (id, user_id, name, params, source, status, "
        "expires_at, created_at, updated_at) VALUES (?,?,?,?,?,'pending',?,?,?)",
        (new_id(), "dizzi", "email_senden", "{}", "ki",
         time.time() + 3600, ts, ts))
    conn.commit()
    zeile = listing(db, "dizzi", _reg())[0]           # kein KeyError trotz fehlender Spalten
    assert zeile["warum"] == "" and zeile["agent_id"] == "" and zeile["lauf_id"] == ""


# --- idem-Dedup (RG-4, docs/83 §2): Wiederanlauf erzeugt keine Dublette -------

def test_idem_dedup_gleiche_pending_zurueck(tmp_path):
    """Zweiter propose mit gleicher idem ⇒ die BESTEHENDE pending-Aktion zurück
    (idem_treffer), KEINE Dublette — at-least-once × Wiederanlauf bleibt sauber."""
    db = Database(tmp_path / "idem.sqlite")
    reg = _reg()
    p1 = propose(db, reg, "dizzi", "email_senden", {"an": "k@x.org"}, source="agent",
                 warum="Kunde wartet", idem="msg-42:email_senden")
    p2 = propose(db, reg, "dizzi", "email_senden", {"an": "k@x.org"}, source="agent",
                 warum="Kunde wartet", idem="msg-42:email_senden")
    assert p2["id"] == p1["id"] and p2.get("idem_treffer") is True
    pend = [z for z in listing(db, "dizzi", reg) if z["status"] == "pending"]
    assert len(pend) == 1 and pend[0]["idem"] == "msg-42:email_senden"


def test_idem_verschieden_legt_neu_an(tmp_path):
    db = Database(tmp_path / "idem2.sqlite")
    reg = _reg()
    propose(db, reg, "dizzi", "email_senden", {"an": "a"}, source="agent",
            warum="w", idem="msg-1:email_senden")
    propose(db, reg, "dizzi", "email_senden", {"an": "b"}, source="agent",
            warum="w", idem="msg-2:email_senden")
    assert len({z["id"] for z in listing(db, "dizzi", reg)}) == 2


def test_idem_leer_kein_dedup(tmp_path):
    """0-Bruch: ohne idem (Default '') dedupt nichts — zwei Vorschläge, zwei Einträge."""
    db = Database(tmp_path / "idem3.sqlite")
    reg = _reg()
    propose(db, reg, "dizzi", "email_senden", {"an": "a"}, source="mcp")
    propose(db, reg, "dizzi", "email_senden", {"an": "a"}, source="mcp")
    assert len(listing(db, "dizzi", reg)) == 2


def test_idem_dedup_nur_gegen_pending(tmp_path):
    """Nach einer Entscheidung (executed) darf dieselbe idem wieder anlegen — der
    Dedup schützt nur den offenen Vorschlag, nicht die abgeschlossene Wirkung."""
    db = Database(tmp_path / "idem4.sqlite")
    reg = _reg()
    p1 = propose(db, reg, "dizzi", "email_senden", {"an": "k@x.org"}, source="agent",
                 warum="w", idem="msg-7:email_senden")
    decide(db, reg, "dizzi", p1["id"], True)          # executed ⇒ nicht mehr pending
    p2 = propose(db, reg, "dizzi", "email_senden", {"an": "k@x.org"}, source="agent",
                 warum="w", idem="msg-7:email_senden")
    assert p2["id"] != p1["id"] and not p2.get("idem_treffer")


# --- HTTP-Schicht ------------------------------------------------------------

def _app(tmp_path):
    manifest = AppManifest(id="k4app", name="K4", brand="Dizz K4",
                           version="0.1.0", port=8299)
    return create_app(manifest, Database(tmp_path / "http.sqlite"),
                      summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
                      actions=_reg())


def test_http_agent_propose_mit_und_ohne_warum(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        # Agent-Vorschlag mit WARUM ⇒ pending + Felder in der Liste
        r = c.post("/api/actions/propose", json={
            "name": "email_senden", "params": {"an": "k@x.org"},
            "source": "agent", "agent_id": "a1", "warum": "Rechnung überfällig",
            "lauf_id": "l1"})
        assert r.status_code == 200 and r.json()["status"] == "pending"
        pend = c.get("/api/actions?status=pending").json()["liste"][0]
        assert pend["warum"] == "Rechnung überfällig" and pend["agent_id"] == "a1"
        # Agent-Vorschlag OHNE WARUM ⇒ 422 (abgelehnt), nichts Neues angelegt
        r2 = c.post("/api/actions/propose", json={
            "name": "email_senden", "params": {}, "source": "agent"})
        assert r2.status_code == 422 and "WARUM" in r2.json()["error"]
        assert len(c.get("/api/actions?status=pending").json()["liste"]) == 1
