"""Tests für den generischen Bereichs-Scaffold ``appkit.bereiche.BereicheBasis``
(De-Fork docs/49 §6): exerziert CRUD · Hierarchie/Zyklus-Schutz · Soft-Delete mit
Kind-Reparenting · generische Zuordnung/Inhalt · kontext-Spalten · user-Isolation —
die Logik, die bisher in Admin/Money/Memory/Management 4× dupliziert war."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from appkit.bereiche import BereicheBasis, BereichInBasis, BereichPatchBasis
from appkit.db import Database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bereiche (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
    art TEXT NOT NULL DEFAULT 'sonstiges', parent_id TEXT NOT NULL DEFAULT '',
    farbe TEXT, icon TEXT, status TEXT NOT NULL DEFAULT 'aktiv',
    beschreibung TEXT, kontext TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS dinge (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    bereich_id TEXT NOT NULL DEFAULT '', deleted_at TEXT
);
"""

U = "u1"


class _BereichIn(BereichInBasis):
    kontext: str = ""


class _BereichPatch(BereichPatchBasis):
    kontext: str | None = None


class _Bereiche(BereicheBasis):
    arten = ("projekt", "kunde", "sonstiges")
    fk_tabellen = ("dinge",)
    kontext_spalten = ("kontext",)


@pytest.fixture
def b(tmp_path):
    db = Database(tmp_path / "b.sqlite", extra_schema=_SCHEMA)
    return _Bereiche(db), db


def test_anlegen_holen_kontext(b):
    api, _ = b
    r = api.anlegen(U, _BereichIn(name=" Agentur ", art="kunde", kontext="k:nord"))
    assert r["name"] == "Agentur" and r["art"] == "kunde" and r["kontext"] == "k:nord"
    assert api.holen(U, r["id"])["id"] == r["id"]
    r2 = api.anlegen(U, _BereichIn(name="X", art="quatsch"))      # unbekannte art ⇒ sonstiges
    assert r2["art"] == "sonstiges"


def test_aendern_status_und_kontext(b):
    api, _ = b
    r = api.anlegen(U, _BereichIn(name="A"))
    upd = api.aendern(U, r["id"], _BereichPatch(status="ruhend", kontext="neu", name="A2"))
    assert upd["status"] == "ruhend" and upd["kontext"] == "neu" and upd["name"] == "A2"
    with pytest.raises(HTTPException):                            # leerer Name ⇒ 400
        api.aendern(U, r["id"], _BereichPatch(name="  "))


def test_hierarchie_und_zyklus(b):
    api, _ = b
    a = api.anlegen(U, _BereichIn(name="A"))
    c = api.anlegen(U, _BereichIn(name="C"))
    api.aendern(U, c["id"], _BereichPatch(parent_id=a["id"]))     # C unter A
    with pytest.raises(HTTPException):                            # A unter C = Zyklus
        api.aendern(U, a["id"], _BereichPatch(parent_id=c["id"]))
    with pytest.raises(HTTPException):                            # self-parent
        api.aendern(U, a["id"], _BereichPatch(parent_id=a["id"]))


def test_loeschen_zieht_kinder_zur_wurzel(b):
    api, _ = b
    a = api.anlegen(U, _BereichIn(name="A"))
    c = api.anlegen(U, _BereichIn(name="C"))
    api.aendern(U, c["id"], _BereichPatch(parent_id=a["id"]))
    assert api.loeschen(U, a["id"]) is True
    assert api.holen(U, a["id"]) is None                         # soft-deleted
    assert api.holen(U, c["id"])["parent_id"] == ""             # Kind zur Wurzel
    assert api.loeschen(U, "gibtsnicht") is False


def test_zuordnen_und_inhalt(b):
    api, db = b
    a = api.anlegen(U, _BereichIn(name="A"))
    db.get_conn().execute("INSERT INTO dinge (id,user_id,bereich_id) VALUES ('d1',?, '')", (U,))
    db.get_conn().commit()
    api.zuordnen(U, "dinge", "d1", a["id"])
    assert api.inhalt(U, a["id"])["zaehler"] == {"dinge": 1}
    with pytest.raises(HTTPException):                            # unbekannte Tabelle ⇒ 400 (kein Injection)
        api.zuordnen(U, "evil; DROP", "d1", a["id"])
    assert api.anzahl(U) == 1


def test_user_isolation(b):
    api, _ = b
    r = api.anlegen(U, _BereichIn(name="A"))
    assert api.holen("anderer", r["id"]) is None
