"""Tests RG-5 (docs/83 §4): der Eichungs-Poll (Management misst, eigener Cursor).

Fake-Spine (kein HTTP): eine injizierbare ``fetch_fn`` liefert ``hitl_entschieden``-
Ereignisse ab dem Cursor. Deckt: Cursor rückt vor + idempotenter Re-Poll (kein
Doppel-Zählen) · Präzision-Rechnung ⇒ agent_evals · def_hash-Isolation (Definition
geändert ⇒ Beobachtung frisch) · Offline-Quelle ehrlich · Budget aus Läufen · der
volle Lauf: 20 Approves + Golden grün ⇒ Ampel grün, n<20 ⇒ ungrün.
"""

from __future__ import annotations

from managementapp import agenten_eichung as eich
from managementapp import agenten_eval as ev
from appkit.db import Database, default_db_path


def _db(tmp_path) -> Database:
    return Database(default_db_path("management", data_root=tmp_path),
                    extra_schema=ev.SCHEMA_AGENT_EVALS + eich.SCHEMA_EVAL_POLL)


def _ev(seq: int, agent_id: str, approve: bool, *, klasse="aussenwirkung",
        typ="hitl_entschieden") -> dict:
    """Ein hitl_entschieden-Spine-Ereignis (Zeiger + Skalare, wie ereignis_spine)."""
    return {"seq": seq, "id": f"e{seq}", "typ": typ, "klasse": klasse,
            "payload": {"aktion": "mail_senden", "approve": approve,
                        "status": "executed" if approve else "rejected",
                        "agent_id": agent_id, "lauf_id": f"l{seq}"}}


def _fetch(events_by_quelle: dict[str, list[dict]]) -> eich.EichungFetch:
    """Fake-Spine-Fetcher: liefert je Quelle die Ereignisse mit seq > seit."""
    def fetch(quelle: str, seit: int) -> list[dict]:
        return [e for e in events_by_quelle.get(quelle, []) if int(e["seq"]) > seit]
    return fetch


JETZT = "2026-07-13T00:00:00+00:00"


# --- Poll je Quelle: Cursor + Idempotenz -----------------------------------------

def test_poll_verbucht_und_cursor_rueckt_vor(tmp_path):
    db = _db(tmp_path)
    events = {"kommunikation": [_ev(1, "a1", True), _ev(2, "a1", False),
                               _ev(3, "a1", True)]}
    n = eich.poll_quelle(db, "u1", "kommunikation", _fetch(events), {"a1": "h1"},
                         jetzt_iso=JETZT)
    assert n == 3
    row = db.get_conn().execute(
        "SELECT entschieden, approved FROM eval_beobachtungen WHERE agent_id='a1'").fetchone()
    assert row["entschieden"] == 3 and row["approved"] == 2
    # Re-Poll ohne neue Ereignisse ⇒ Cursor steht, KEIN Doppel-Zählen (idempotent)
    assert eich.poll_quelle(db, "u1", "kommunikation", _fetch(events), {"a1": "h1"},
                            jetzt_iso=JETZT) == 0
    row2 = db.get_conn().execute(
        "SELECT entschieden FROM eval_beobachtungen WHERE agent_id='a1'").fetchone()
    assert row2["entschieden"] == 3


def test_poll_ignoriert_fremde_typen_und_unbekannte_agenten(tmp_path):
    db = _db(tmp_path)
    events = {"kommunikation": [
        _ev(1, "a1", True),
        _ev(2, "a1", True, typ="mail_eingegangen"),   # kein hitl_entschieden ⇒ ignoriert
        _ev(3, "ghost", True),                        # Agent nicht im Wald ⇒ übersprungen
    ]}
    n = eich.poll_quelle(db, "u1", "kommunikation", _fetch(events), {"a1": "h1"},
                         jetzt_iso=JETZT)
    assert n == 1                                     # nur das echte, zugeordnete
    # Cursor rückt trotzdem über ALLE (auch die übersprungenen sind bearbeitet)
    cur = db.get_conn().execute(
        "SELECT seq FROM eval_cursor WHERE quelle_app='kommunikation'").fetchone()
    assert cur["seq"] == 3


def test_def_hash_wechsel_setzt_beobachtung_zurueck(tmp_path):
    db = _db(tmp_path)
    # erste Runde unter def_hash h1
    eich.poll_quelle(db, "u1", "kommunikation",
                     _fetch({"kommunikation": [_ev(1, "a1", False), _ev(2, "a1", False)]}),
                     {"a1": "h1"}, jetzt_iso=JETZT)
    r1 = db.get_conn().execute(
        "SELECT entschieden, def_hash FROM eval_beobachtungen WHERE agent_id='a1'").fetchone()
    assert r1["entschieden"] == 2 and r1["def_hash"] == "h1"
    # Definition geändert (h2) ⇒ die nächste Entscheidung zählt FRISCH (alte Evidenz weg)
    eich.poll_quelle(db, "u1", "kommunikation",
                     _fetch({"kommunikation": [_ev(1, "a1", False), _ev(2, "a1", False),
                                              _ev(3, "a1", True)]}),
                     {"a1": "h2"}, jetzt_iso=JETZT)
    r2 = db.get_conn().execute(
        "SELECT entschieden, approved, def_hash FROM eval_beobachtungen "
        "WHERE agent_id='a1'").fetchone()
    assert r2["def_hash"] == "h2" and r2["entschieden"] == 1 and r2["approved"] == 1


# --- Budget-Aggregation aus Läufen -----------------------------------------------

def test_budget_aus_laeufen():
    laeufe = [
        {"agent_id": "a1", "fehler": ""},                       # im Budget
        {"agent_id": "a1", "fehler": "Tool-Budget erschöpft"},  # nicht
        {"agent_id": "a1", "fehler": ""},                       # im Budget
        {"agent_id": "a2", "fehler": "Laufzeit-Budget erschöpft"},
    ]
    agg = eich.budget_aus_laeufen(laeufe)
    assert agg["a1"] == (3, 2) and agg["a2"] == (1, 0)


# --- Voller Lauf: eichung_lauf ---------------------------------------------------

def _n_approves(quelle: str, agent: str, n_ok: int, n_reject: int, klasse="aussenwirkung"):
    events = []
    seq = 1
    for _ in range(n_ok):
        events.append(_ev(seq, agent, True, klasse=klasse)); seq += 1
    for _ in range(n_reject):
        events.append(_ev(seq, agent, False, klasse=klasse)); seq += 1
    return {quelle: events}


def test_voller_lauf_gruen_bei_genug_approves_und_golden(tmp_path):
    db = _db(tmp_path)
    # 22 approve / 3 reject = 25 Entscheidungen, Präzision 0.88 ≥ 0.80, n ≥ 20
    events = _n_approves("kommunikation", "a1", 22, 3)
    res = eich.eichung_lauf(
        db, "u1", ["kommunikation"], _fetch(events), {"a1": "h1"},
        golden_gruen=True, jetzt_iso=JETZT,
        budget_fuer={"a1": (25, 25)})
    assert res["gepollt"] == 1 and res["verbucht"] == 25 and res["quellen_offline"] == []
    eintraege = ev.eval_holen(db, "u1", "a1", "aussenwirkung")
    assert len(eintraege) == 1 and eintraege[0]["gruen"] is True


def test_voller_lauf_ungruen_unter_20(tmp_path):
    db = _db(tmp_path)
    events = _n_approves("kommunikation", "a1", 10, 0)   # nur 10 < 20
    eich.eichung_lauf(db, "u1", ["kommunikation"], _fetch(events), {"a1": "h1"},
                      golden_gruen=True, jetzt_iso=JETZT, budget_fuer={"a1": (10, 10)})
    eintraege = ev.eval_holen(db, "u1", "a1", "aussenwirkung")
    assert eintraege[0]["gruen"] is False
    assert any("Mindest-Stichprobe" in g for g in eintraege[0]["gruende"])


def test_voller_lauf_ungruen_ohne_golden(tmp_path):
    db = _db(tmp_path)
    events = _n_approves("kommunikation", "a1", 25, 0)   # Präzision top, aber Golden rot
    eich.eichung_lauf(db, "u1", ["kommunikation"], _fetch(events), {"a1": "h1"},
                      golden_gruen=False, jetzt_iso=JETZT, budget_fuer={"a1": (25, 25)})
    eintraege = ev.eval_holen(db, "u1", "a1", "aussenwirkung")
    assert eintraege[0]["gruen"] is False


def test_offline_quelle_ehrlich(tmp_path):
    db = _db(tmp_path)

    def fetch(quelle: str, seit: int):
        raise TimeoutError("spine offline")

    res = eich.eichung_lauf(db, "u1", ["kommunikation"], fetch, {"a1": "h1"},
                            golden_gruen=True, jetzt_iso=JETZT)
    assert res["quellen_offline"] == ["kommunikation"] and res["gepollt"] == 0
