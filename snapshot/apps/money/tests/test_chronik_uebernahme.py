"""test_chronik_uebernahme.py — Bestands-Anschluss (Vertrag §6.0 / §7, BZ-C-1).

Eine echte money-DB trägt Jahre an Buchungen VOR dem Chronik-Genesis. Der ``money.uebernahme``-Anker
fängt deren Ist-Salden, sodass ``salden-replay`` ab Tag 1 grün ist; der Beweisgrad weist ehrlich aus,
ob ein Zeitraum lückenlos ketten-gedeckt (``voll``) oder nur DB-gesiegelt (``db-stand``) ist.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit import chronik
from appkit import chronik_pruef as P
from appkit.db import new_id, now_iso
from moneyapp import chronik_naht
from moneyapp import main as mm


@pytest.fixture(autouse=True)
def _reset():
    chronik.reset_kontext()
    yield
    chronik.reset_kontext()


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _konten(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    aufw = c.post("/api/konten", json={"name": "Aufwand", "typ": "expense"}).json()["id"]
    return giro, aufw


def _direkt_buchung(db, konto_soll, konto_haben, betrag, datum):
    """Bestands-Buchung DIREKT in die DB (wie vor dem Chronik-Anschluss) — kein Ereignis."""
    conn = db.get_conn()
    bid, ts = new_id(), now_iso()
    conn.execute("INSERT INTO buchungen (id,user_id,notiz,datum,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                 (bid, "dizzi", "", datum, ts, ts))
    conn.execute("INSERT INTO postings (id,user_id,buchung_id,konto_id,betrag,created_at) VALUES (?,?,?,?,?,?)",
                 (new_id(), "dizzi", bid, konto_soll, betrag, ts))
    conn.execute("INSERT INTO postings (id,user_id,buchung_id,konto_id,betrag,created_at) VALUES (?,?,?,?,?,?)",
                 (new_id(), "dizzi", bid, konto_haben, -betrag, ts))
    conn.commit()
    return bid


def _uebernahme(db, stichtag):
    with db.transaktion() as conn:
        chronik_naht.schreibe_uebernahme(conn, stichtag=stichtag)


def test_bestands_db_replay_gruen_nach_uebernahme(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        # Vor-Genesis-Bestand (kein Ereignis)
        _direkt_buchung(db, aufw, giro, 12000, "2026-03-10")
        _direkt_buchung(db, aufw, giro, 5000, "2026-03-20")
        _uebernahme(db, "2026-03-31")
        # neue, ketten-gedeckte Buchung nach dem Stichtag
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                       "betrag": "40,00", "datum": "2026-05-02"})
        chronik_naht.baue_chronist(db.db_path).tick(flush=True)   # Segmente materialisieren
    rc, zeilen = P.salden_replay(chronik_naht.chronik_dir(), db.db_path)
    assert rc == P.EXIT_GRUEN, zeilen


def test_beweisgrad_vor_und_nach_stichtag(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        _direkt_buchung(db, aufw, giro, 3000, "2026-02-10")
        _uebernahme(db, "2026-03-31")
        # Buchungen in einem Vor- und einem Nach-Stichtag-Monat (beide vergangen)
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw, "betrag": "1,00", "datum": "2026-02-15"})
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw, "betrag": "2,00", "datum": "2026-05-15"})
        vor = c.post("/api/festschreibung", json={"zeitraum": "2026-02"}).json()
        nach = c.post("/api/festschreibung", json={"zeitraum": "2026-05"}).json()
        assert vor["beweisgrad"] == "db-stand"     # Zeitraum liegt vor dem Anker
        assert nach["beweisgrad"] == "voll"        # vollständig nach dem Anker


def test_vor_genesis_storno_repliziert(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        alt = _direkt_buchung(db, aufw, giro, 9000, "2026-05-10")   # Bestands-Buchung
        _uebernahme(db, "2026-04-30")
        # Storno der Bestands-Buchung nach Genesis (self-contained postings, BZ-C-1)
        assert c.delete(f"/api/buchungen/{alt}").status_code == 200
        assert "money.storno" in [r["art"] for r in db.get_conn().execute(
            "SELECT art FROM chronik_ausgang").fetchall()]
        chronik_naht.baue_chronist(db.db_path).tick(flush=True)
    rc, zeilen = P.salden_replay(chronik_naht.chronik_dir(), db.db_path)
    assert rc == P.EXIT_GRUEN, zeilen             # Anker(+X) + Storno(−X) = 0 = DB (gelöscht)
