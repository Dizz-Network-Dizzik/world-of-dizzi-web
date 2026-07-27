"""Vertrags-Tests für appkit/ereignis_spine.py (Agenten-Regie W2, RG-1 — docs/83 §1).

Pinnt den VERTRAG des Event-Spine, nicht eine Implementierung:
- Outbox-Garantie: Rollback der Domain-Tx nimmt das Ereignis mit.
- Reihenfolge + Replay ab Cursor (at-least-once, Konsument dedupt über id).
- „Zeiger, nie Inhalt": Freitext-Felder / unbekannte Felder / Nicht-Skalare fliegen.
- Sichtbarkeit fail-closed: hoch/höchst-Quellen erreichen keine schwächeren Agenten.
- Router ist read-only und respektiert den seit-Cursor.
Komplett Runtime-/Ollama-frei; SQLite in tmp_path.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from appkit import ereignis_spine as es
from appkit.db import Database


def _reg() -> es.EreignisTypRegister:
    r = es.EreignisTypRegister("kommunikation")
    r.register("mail_eingegangen", ("konto_id", "nachricht_ref", "thread_ref"))
    r.register("mail_gesendet", ("konto_id",))
    return r


def _db(tmp_path) -> Database:
    return Database(tmp_path / "e.sqlite", extra_schema=es.SCHEMA_EREIGNISSE_SQL)


# --- Schema + Grundpfad anlegen/lesen --------------------------------------------

def test_schema_parst():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(es.SCHEMA_EREIGNISSE_SQL)
    finally:
        conn.close()


def test_anlegen_und_lesen_in_reihenfolge(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        es.ereignis_anlegen(conn, "dizzi", "mail_eingegangen", register=reg,
                            ref="kommunikation:nachricht:1",
                            payload={"konto_id": "k1", "nachricht_ref": "n1"})
        es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                            payload={"konto_id": "k1"})
    rows = es.ereignisse_seit(db.get_conn(), "dizzi", 0)
    assert [r["typ"] for r in rows] == ["mail_eingegangen", "mail_gesendet"]
    assert rows[0]["seq"] < rows[1]["seq"]                 # seq monoton
    assert rows[0]["payload"] == {"konto_id": "k1", "nachricht_ref": "n1"}
    assert rows[0]["ref"] == "kommunikation:nachricht:1"


def test_replay_ab_cursor(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        for i in range(5):
            es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                                payload={"konto_id": f"k{i}"})
    alle = es.ereignisse_seit(db.get_conn(), "dizzi", 0)
    cursor = alle[1]["seq"]
    rest = es.ereignisse_seit(db.get_conn(), "dizzi", cursor)
    assert [r["seq"] for r in rest] == [r["seq"] for r in alle[2:]]   # > cursor
    assert es.ereignisse_seit(db.get_conn(), "dizzi", alle[-1]["seq"]) == []


def test_limit_geklemmt(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        for i in range(3):
            es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                                payload={"konto_id": f"k{i}"})
    assert len(es.ereignisse_seit(db.get_conn(), "dizzi", 0, limit=2)) == 2
    assert len(es.ereignisse_seit(db.get_conn(), "dizzi", 0, limit=99999)) == 3  # <=1000


def test_nutzer_isolation(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        es.ereignis_anlegen(conn, "a", "mail_gesendet", register=reg,
                            payload={"konto_id": "k"})
        es.ereignis_anlegen(conn, "b", "mail_gesendet", register=reg,
                            payload={"konto_id": "k"})
    assert len(es.ereignisse_seit(db.get_conn(), "a", 0)) == 1
    assert len(es.ereignisse_seit(db.get_conn(), "b", 0)) == 1


def test_soft_delete_kaskade_deckt_ereignisse(tmp_path):
    # KA-H1-Lösch-Invariante: ereignisse trägt deleted_at ⇒ die netzweite
    # Soft-Delete-Kaskade (Konto-Löschung) erfasst sie, ereignisse_seit überspringt.
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                            payload={"konto_id": "k1"})
    assert len(es.ereignisse_seit(db.get_conn(), "dizzi", 0)) == 1
    db.soft_delete_user("dizzi")                       # Konto-Lösch-Kaskade
    assert es.ereignisse_seit(db.get_conn(), "dizzi", 0) == []


# --- Outbox-Garantie: Rollback nimmt das Ereignis mit ----------------------------

def test_rollback_nimmt_ereignis_mit(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with pytest.raises(RuntimeError, match="absicht"):
        with db.transaktion() as conn:
            es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                                payload={"konto_id": "k1"})
            raise RuntimeError("absicht: Domain-Write scheitert")
    # Das Ereignis darf NICHT persistiert sein — es teilt das Schicksal der Tx.
    assert es.ereignisse_seit(db.get_conn(), "dizzi", 0) == []


# --- „Zeiger, nie Inhalt": Register-Vertrag fail-closed --------------------------

def test_freitext_feld_beim_registrieren_verboten():
    r = es.EreignisTypRegister("kommunikation")
    for feld in ("betreff", "body", "absender", "betrag", "token"):
        with pytest.raises(es.EreignisRegisterFehler, match="verboten"):
            r.register("x", ("konto_id", feld))


def test_unbekannter_typ_wirft():
    with pytest.raises(es.EreignisRegisterFehler, match="unbekannter Ereignis-Typ"):
        _reg().pruefe("gibt_es_nicht", {})


def test_unbekanntes_feld_wirft():
    with pytest.raises(es.EreignisRegisterFehler, match="unbekannte Payload-Felder"):
        _reg().pruefe("mail_gesendet", {"konto_id": "k", "schmuggel": "x"})


def test_nicht_skalar_wirft():
    with pytest.raises(es.EreignisRegisterFehler, match="nur Skalare"):
        _reg().pruefe("mail_gesendet", {"konto_id": ["verkappte", "liste"]})


def test_zu_langer_wert_wirft():
    with pytest.raises(es.EreignisRegisterFehler, match="Zeichen"):
        _reg().pruefe("mail_gesendet", {"konto_id": "x" * (es.MAX_WERT_LEN + 1)})


def test_anlegen_validiert_fail_closed(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with pytest.raises(es.EreignisRegisterFehler):
        with db.transaktion() as conn:
            es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                                payload={"konto_id": "k", "betreff": "geheim"})
    assert es.ereignisse_seit(db.get_conn(), "dizzi", 0) == []


# --- Sichtbarkeit fail-closed (docs/83 §1.2) -------------------------------------

def test_zustellbar_kernschutz_hoch_nie_an_normal():
    # Der Kernpunkt: ein hoch-Ereignis erreicht nie einen normal-/Boost-Agenten.
    assert not es.ereignis_zustellbar("hoch", "normal")
    assert not es.ereignis_zustellbar("hoechst", "normal")
    assert not es.ereignis_zustellbar("höchst", "hoch")     # höchst nur an höchst


def test_zustellbar_gleich_oder_strenger_ok():
    assert es.ereignis_zustellbar("normal", "normal")
    assert es.ereignis_zustellbar("normal", "hoch")         # strengerer Agent ok
    assert es.ereignis_zustellbar("hoch", "hoch")
    assert es.ereignis_zustellbar("hoch", "hoechst")
    assert es.ereignis_zustellbar("hoechst", "höchst")      # Schreibvarianten = gleich


def test_zustellbar_unbekannt_fail_closed():
    assert not es.ereignis_zustellbar("quatsch", "hoch")    # unbek. Quelle = höchst-streng
    assert es.ereignis_zustellbar("quatsch", "hoechst")
    assert not es.ereignis_zustellbar("hoch", "quatsch")    # unbek. Agent = normal-schwach


# --- Read-only-Router -------------------------------------------------------------

class _FakeUser:
    user_id = "dizzi"


def _app_mit_router(db, reg) -> TestClient:
    app = FastAPI()
    app.include_router(es.router_factory(db, reg, user_dep=lambda: _FakeUser()))
    return TestClient(app)


def test_router_liefert_und_respektiert_cursor(tmp_path):
    db, reg = _db(tmp_path), _reg()
    with db.transaktion() as conn:
        for i in range(3):
            es.ereignis_anlegen(conn, "dizzi", "mail_gesendet", register=reg,
                                payload={"konto_id": f"k{i}"})
    c = _app_mit_router(db, reg)
    r = c.get("/api/ereignisse")
    assert r.status_code == 200
    body = r.json()
    assert len(body["eintraege"]) == 3
    assert body["cursor"] == body["eintraege"][-1]["seq"]
    assert set(body["typen"]) == {"mail_eingegangen", "mail_gesendet"}
    # Cursor respektiert: ab der 1. seq bleiben 2 Einträge.
    r2 = c.get(f"/api/ereignisse?seit={body['eintraege'][0]['seq']}")
    assert len(r2.json()["eintraege"]) == 2


def test_router_ist_read_only(tmp_path):
    db, reg = _db(tmp_path), _reg()
    c = _app_mit_router(db, reg)
    # Es gibt keinen Schreibpfad — POST/PUT existieren nicht.
    assert c.post("/api/ereignisse", json={"typ": "x"}).status_code == 405
    assert c.put("/api/ereignisse", json={"typ": "x"}).status_code == 405
