"""Charta §B8 — Aktivierungs-Strecke (B3.3/CH-7): charta.version versiegelt in
Test-Kette, genau eine aktive Version, Rollback = NEUES Ereignis (CH-13)."""
from datetime import datetime, timezone

import pytest

from appkit import chronik as C
from appkit import chronik_pruef as P
from appkit import charta_speicher as S
from appkit.chronist import Chronist, Quelle
from appkit.db import Database, now_iso


def _charta(version):
    return {"charta_version": version, "artikel": [{
        "aktion": "fibu.buchen", "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]]}]}


@pytest.fixture(autouse=True)
def _kontext_reset():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _setup(tmp_path):
    cdir = tmp_path / "chronik"
    C.konfiguriere(cdir)
    dbpath = tmp_path / "host.sqlite"
    db = Database(dbpath, extra_schema=S.SCHEMA + C.AUSGANG_SCHEMA)
    db.get_conn()                                      # Schema in die Datei
    chronist = Chronist(cdir, [Quelle("charta", str(dbpath))],
                        uhr=lambda: datetime.now(timezone.utc))
    return cdir, db, chronist


def test_aktivierung_versiegelt_und_genau_eine_aktive(tmp_path):
    cdir, db, chronist = _setup(tmp_path)
    res = S.aktiviere_version(db, charta=_charta("2026-07-13.1"), subjekt="u:" + "a" * 36,
                              jetzt_iso=now_iso(), chronist=chronist)
    assert res["epoche"] >= 1 and res["siegel"].startswith("sha256:")

    conn = db.get_conn()
    aktive = conn.execute("SELECT version FROM charta_versionen WHERE status='aktiv'").fetchall()
    assert len(aktive) == 1 and aktive[0]["version"] == "2026-07-13.1"
    row = conn.execute("SELECT status, chronik_epoche FROM charta_versionen WHERE version=?",
                       ("2026-07-13.1",)).fetchone()
    assert row["status"] == "aktiv" and row["chronik_epoche"] == res["epoche"]
    # charta.version-Ereignis liegt in der Kette; Kette verifiziert grün
    assert conn.execute("SELECT COUNT(*) FROM chronik_ausgang WHERE art='charta.version'"
                        ).fetchone()[0] == 1
    P.pruefe(cdir)


def test_rollback_ist_neues_ereignis_keine_loeschung(tmp_path):
    cdir, db, chronist = _setup(tmp_path)
    S.aktiviere_version(db, charta=_charta("v1"), subjekt="u:" + "a" * 36,
                        jetzt_iso=now_iso(), chronist=chronist)
    S.aktiviere_version(db, charta=_charta("v2"), subjekt="u:" + "a" * 36,
                        jetzt_iso=now_iso(), chronist=chronist)
    # Rollback auf v1 = erneute Aktivierung (NEUES Ereignis, nie Löschung)
    S.aktiviere_version(db, charta=_charta("v1"), subjekt="u:" + "a" * 36,
                        jetzt_iso=now_iso(), chronist=chronist)

    conn = db.get_conn()
    stati = dict(conn.execute("SELECT version, status FROM charta_versionen").fetchall())
    assert stati == {"v1": "aktiv", "v2": "abgeloest"}          # v2-Zeile bleibt (keine Löschung)
    assert conn.execute("SELECT COUNT(*) FROM charta_versionen WHERE status='aktiv'"
                        ).fetchone()[0] == 1
    # drei Aktivierungen ⇒ drei charta.version-Ereignisse in der Kette
    assert conn.execute("SELECT COUNT(*) FROM chronik_ausgang WHERE art='charta.version'"
                        ).fetchone()[0] == 3
    P.pruefe(cdir)
