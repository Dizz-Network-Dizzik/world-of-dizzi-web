"""Charta §B8 — Verzeichnis-KEIM (§B4/D2): Zuweisung/Entzug + rollen_von + Belegschaft;
verzeichnis.rolle ist hash_only (Personendaten löschbar, Gate #3)."""
import pytest

from appkit import chronik as C
from appkit import charta_verzeichnis as V
from appkit.db import Database

UA, UB = "u:" + "a" * 36, "u:" + "b" * 36


@pytest.fixture(autouse=True)
def _kontext(tmp_path):
    C.konfiguriere(tmp_path / "chronik")               # Pfeffer für hash_only-Ereignisse
    yield
    C.reset_kontext()


def _db(tmp_path):
    db = Database(tmp_path / "h.sqlite", extra_schema=V.SCHEMA + C.AUSGANG_SCHEMA)
    db.get_conn()
    return db


def test_zuweisen_und_rollen_von(tmp_path):
    db = _db(tmp_path)
    with db.transaktion() as conn:
        V.zuweisen(conn, user_id=UA, rolle="buchhaltung", bereich_id="b:eigen")
    conn = db.get_conn()
    r = V.rollen_von(conn, UA)
    assert r["rollen"] == {"buchhaltung"} and r["bereiche"] == {"b:eigen"}
    art, last = conn.execute("SELECT art, nutzlast FROM chronik_ausgang").fetchone()
    assert art == "verzeichnis.rolle" and last == ""    # hash_only ⇒ leere Klartext-Nutzlast


def test_entziehen_macht_rolle_ungueltig(tmp_path):
    db = _db(tmp_path)
    with db.transaktion() as conn:
        V.zuweisen(conn, user_id=UA, rolle="leser")
    with db.transaktion() as conn:
        V.entziehen(conn, user_id=UA, rolle="leser")
    assert V.rollen_von(db.get_conn(), UA)["rollen"] == set()


def test_belegschaft_aggregiert(tmp_path):
    db = _db(tmp_path)
    with db.transaktion() as conn:
        V.zuweisen(conn, user_id=UA, rolle="buchhaltung", bereich_id="b:eigen")
        V.zuweisen(conn, user_id=UA, rolle="fibu_leitung", bereich_id="b:eigen")
        V.zuweisen(conn, user_id=UB, rolle="leser")
    beleg = V.belegschaft(db.get_conn())
    assert len(beleg) == 2
    a = next(s for s in beleg if s["id"] == UA)
    assert set(a["rollen"]) == {"buchhaltung", "fibu_leitung"} and a["assurance"] == "hochsicher"
