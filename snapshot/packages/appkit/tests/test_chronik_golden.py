"""test_chronik_golden.py — der eingecheckte Golden-Harness (Vertrag §7 / C-13).

Läuft ``chronik_pruef`` gegen **eingecheckte** Fixtures (``tests/golden/chronik/``, erzeugt von
``chronik_golden_gen.py`` mit festen Test-Schlüsseln + fester Uhr). Damit ist der Prüfer offline,
deterministisch und reproduzierbar — UND ein Drift-Wächter: ändert sich ``chronik.py`` am Format/Hash,
verifiziert die ``ok``-Fixture nicht mehr. Je Fehlerklasse eine manipulierte Variante ⇒ erwarteter Exit.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from appkit import chronik_pruef as P

GOLDEN = Path(__file__).resolve().parent / "golden" / "chronik"


def test_ok_fixture_ist_gruen():
    P.pruefe(GOLDEN / "ok")                          # wirft bei Bruch


def test_ok_beweis_verifiziert():
    b = P.beweis(GOLDEN / "ok", n=3)                 # letzte Zeile der ersten Epoche
    assert b["epoche"] == 1 and b["n"] == 3 and b["pfad"]


def test_ok_bericht_gruen():
    rc, zeilen = P.bericht(GOLDEN / "ok")
    assert rc == P.EXIT_GRUEN
    assert any("grün" in z for z in zeilen)


def test_ok_salden_replay_gegen_erwartete_db(tmp_path):
    """Die eingecheckte ok-Fixtur (uebernahme + 4 Buchungen + 1 Storno) repliziert deterministisch
    auf 1200=+5950 / 8400=−5950 — eine money-DB mit genau diesen aktiven Salden ⇒ Replay grün."""
    mdb = tmp_path / "money.sqlite"
    conn = sqlite3.connect(mdb)
    conn.executescript("CREATE TABLE postings (konto_id TEXT, betrag INTEGER, deleted_at TEXT);")
    conn.execute("INSERT INTO postings VALUES ('1200', 5950, NULL)")
    conn.execute("INSERT INTO postings VALUES ('8400', -5950, NULL)")
    conn.commit()
    conn.close()
    rc, zeilen = P.salden_replay(GOLDEN / "ok", mdb)
    assert rc == P.EXIT_GRUEN, zeilen


@pytest.mark.parametrize("variante", ["kette_bruch", "merkle_wurzel_falsch", "siegel_kette_bruch"])
def test_manipulierte_variante_bricht(variante):
    """Jede manipulierte Variante ⇒ Exit 2 über die CLI (ein anderer Prüf-Pfad je Variante)."""
    assert P._cli(["--dir", str(GOLDEN / variante), "pruefe"]) == P.EXIT_BRUCH


def test_golden_generator_ist_beigelegt():
    """C-13/§7: der Generator liegt reproduzierbar bei den Fixtures."""
    assert (GOLDEN.parent / "chronik_golden_gen.py").is_file()
