"""test_chronik_restore.py — Wiederherstellungs-Verbund (Vertrag §4.6 / BZ-C-3).

App-DB und ``data\\chronik\\`` sind EIN Restore-Verbund. Zwei stille Fehlerbilder werden gefangen:
(a) **DB älter als Kette** (i-Kollision, anderer Inhalt) ⇒ Fork-Abbruch statt Stempel (C-16);
(b) **Chronik älter als DB** ⇒ ``bericht``-Befund über eine fehlende ``festschreibungen.siegel_hash``-Referenz.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from appkit import chronik as C
from appkit import chronik_pruef as P
from appkit.chronist import Chronist, Quelle

UHR_FIX = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

_FESTSCHREIBUNGEN = """
CREATE TABLE IF NOT EXISTS festschreibungen (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, zeitraum TEXT NOT NULL,
  status TEXT NOT NULL, bis_i INTEGER, salden_hash TEXT, beweisgrad TEXT,
  siegel_epoche INTEGER, siegel_hash TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);
"""


@pytest.fixture(autouse=True)
def _kontext_reset():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _setup(tmp_path):
    cdir = tmp_path / "chronik"
    mdb = tmp_path / "money.sqlite"
    conn = sqlite3.connect(mdb)
    conn.executescript(C.AUSGANG_SCHEMA + _FESTSCHREIBUNGEN)
    conn.commit()
    conn.close()
    C.konfiguriere(cdir)
    return cdir, mdb


def _buchung(bid, betrag="1000"):
    return {"buchung_id": bid, "datum": "2026-07-01", "quelle": "manuell",
            "postings": [{"konto_id": "1200", "betrag_minor": betrag},
                         {"konto_id": "8400", "betrag_minor": "-" + betrag}]}


def _schreibe(mdb, nutzlast):
    conn = sqlite3.connect(mdb)
    C.schreibe(conn, art="money.buchung", nutzlast=nutzlast, subjekt="u:" + "a" * 36)
    conn.commit()
    conn.close()


def test_db_aelter_als_kette_forkt_statt_stempeln(tmp_path):
    """(a) Restore einer ÄLTEREN money-DB: Outbox-i kollidiert mit anderem Ketten-Inhalt ⇒ Fork-Stopp."""
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, _buchung("original"))
    Chronist(cdir, [Quelle("money", str(mdb))], uhr=lambda: UHR_FIX).tick(flush=True)

    # „ältere DB": dieselbe i=1 trägt jetzt anderen Inhalt und ist wieder offen (epoche NULL)
    anders = C.kanon(_buchung("aus-alter-DB", betrag="4242"))
    conn = sqlite3.connect(mdb)
    conn.execute("UPDATE chronik_ausgang SET epoche=NULL, nutzlast=?, nutzlast_hash=? WHERE i=1",
                 (anders, C._sha256_hex(anders)))
    conn.commit()
    conn.close()

    ch = Chronist(cdir, [Quelle("money", str(mdb))], uhr=lambda: UHR_FIX)
    ch.tick(flush=True)
    st = ch._lies_status_cache()
    assert st["fork_verdacht"] is not None and st["fork_verdacht"]["i"] == 1
    # ungestempelt geblieben, aber die Kette selbst ist intakt
    offen = sqlite3.connect(mdb).execute(
        "SELECT COUNT(*) FROM chronik_ausgang WHERE epoche IS NULL").fetchone()[0]
    assert offen == 1
    P.pruefe(cdir)


def test_chronik_aelter_als_db_faellt_im_bericht_auf(tmp_path):
    """(b) Restore einer ÄLTEREN Chronik: eine Festschreibung referenziert ein Siegel, das die
    zurückgerollte Chronik nicht (mehr) hat ⇒ ``bericht`` meldet BRUCH (Restore-Wächter §4.6)."""
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, _buchung("b1"))
    Chronist(cdir, [Quelle("money", str(mdb))], uhr=lambda: UHR_FIX).tick(flush=True)

    # DB „weiß" von einer späteren Festschreibung, deren Siegel in der (älteren) Chronik fehlt
    conn = sqlite3.connect(mdb)
    conn.execute(
        "INSERT INTO festschreibungen (id,user_id,zeitraum,status,bis_i,salden_hash,beweisgrad,"
        "siegel_epoche,siegel_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("f1", "u1", "2026-08", "versiegelt", 9, "sha256:00", "voll", 99,
         "sha256:" + "de" * 32, UHR_FIX.isoformat(), UHR_FIX.isoformat()))
    conn.commit()
    conn.close()

    rc_ok, _ = P.bericht(cdir)                    # ohne money-DB: nur Kette/Bestand ⇒ grün
    assert rc_ok == P.EXIT_GRUEN
    rc, zeilen = P.bericht(cdir, mdb)             # mit money-DB: Restore-Wächter schlägt an
    assert rc == P.EXIT_BRUCH
    assert any("2026-08" in z and "BRUCH" in z for z in zeilen)


def test_bericht_gruen_bei_konsistenten_referenzen(tmp_path):
    """Gegenprobe: eine Festschreibung, deren Siegel real existiert ⇒ Restore-Wächter grün."""
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, _buchung("b1"))
    Chronist(cdir, [Quelle("money", str(mdb))], uhr=lambda: UHR_FIX).tick(flush=True)

    s1 = (cdir / "siegel" / "S00000001.json")
    hash1 = C.siegel_hash(json.loads(s1.read_text("utf-8")))
    conn = sqlite3.connect(mdb)
    conn.execute(
        "INSERT INTO festschreibungen (id,user_id,zeitraum,status,bis_i,salden_hash,beweisgrad,"
        "siegel_epoche,siegel_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("f1", "u1", "2026-07", "versiegelt", 1, "sha256:00", "voll", 1, hash1,
         UHR_FIX.isoformat(), UHR_FIX.isoformat()))
    conn.commit()
    conn.close()

    rc, zeilen = P.bericht(cdir, mdb)
    assert rc == P.EXIT_GRUEN
    assert any("Restore-Wächter" in z for z in zeilen)
