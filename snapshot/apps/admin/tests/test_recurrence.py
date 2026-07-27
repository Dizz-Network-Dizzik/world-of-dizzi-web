"""Tests der RRULE-light-Engine (plansapp/recurrence.py) — rein/deterministisch.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

from adminapp.recurrence import (expandiere, ist_gueltig, naechste_faellig,
                                 parse_rule)


# ===================== parse_rule =====================
def test_parse_rule_grundformen():
    assert parse_rule("FREQ=DAILY") == {"freq": "DAILY", "interval": 1}
    assert parse_rule("FREQ=WEEKLY;INTERVAL=2")["interval"] == 2
    assert parse_rule("FREQ=MONTHLY;COUNT=6")["count"] == 6
    r = parse_rule("freq=weekly;until=20261231")     # case-insensitiv + UNTIL
    assert r["freq"] == "WEEKLY" and r["until"].isoformat() == "2026-12-31"
    # tolerant gegen iCal-Zusätze (BYDAY ignoriert, nicht fatal)
    assert parse_rule("FREQ=WEEKLY;BYDAY=MO,WE")["freq"] == "WEEKLY"


def test_parse_rule_ungueltig():
    assert parse_rule("") == {}
    assert parse_rule("   ") == {}
    assert parse_rule("FREQ=HOURLY") == {}          # nicht unterstützte Frequenz
    assert parse_rule("INTERVAL=2") == {}           # FREQ fehlt
    assert parse_rule("FREQ=DAILY;COUNT=abc") == {} # kaputter Wert ⇒ ganz verworfen


def test_ist_gueltig():
    assert ist_gueltig("") is True                  # leer = einmalig = ok
    assert ist_gueltig("FREQ=DAILY;INTERVAL=3") is True
    assert ist_gueltig("FREQ=NONSENSE") is False


# ===================== expandiere =====================
def test_expandiere_leer_ist_einzeln():
    assert expandiere("", "2026-06-20") == ["2026-06-20"]
    assert expandiere("FREQ=BLAH", "2026-06-20") == ["2026-06-20"]


def test_expandiere_taeglich_count_inklusiv():
    # COUNT zählt die erste Instanz mit (RFC 5545)
    assert expandiere("FREQ=DAILY;COUNT=3", "2026-06-20") == [
        "2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_woechentlich_interval_und_suffix():
    # Suffix (Uhrzeit/Zone) bleibt an jeder Instanz erhalten
    out = expandiere("FREQ=WEEKLY;INTERVAL=2;COUNT=3", "2026-06-01T09:30:00+00:00")
    assert out == ["2026-06-01T09:30:00+00:00", "2026-06-15T09:30:00+00:00",
                   "2026-06-29T09:30:00+00:00"]


def test_expandiere_monatlich_klemmt_tag():
    # 31. Jan monatlich ⇒ Feb auf 28 geklemmt, März wieder 31 (deterministisch)
    out = expandiere("FREQ=MONTHLY;COUNT=4", "2026-01-31")
    assert out == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_expandiere_until_inklusiv():
    out = expandiere("FREQ=DAILY;UNTIL=2026-06-22", "2026-06-20")
    assert out == ["2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_fenster_bis_deckelt():
    out = expandiere("FREQ=DAILY;COUNT=30", "2026-06-20", bis="2026-06-22")
    assert out == ["2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_limit_obergrenze():
    # ohne COUNT/UNTIL greift die limit-Deckelung
    assert len(expandiere("FREQ=DAILY", "2026-01-01", limit=5)) == 5


# ===================== naechste_faellig =====================
def test_naechste_faellig():
    assert naechste_faellig("FREQ=WEEKLY", "2026-06-20") == "2026-06-27"
    assert naechste_faellig("FREQ=MONTHLY;INTERVAL=2", "2026-01-31") == "2026-03-31"
    assert naechste_faellig("", "2026-06-20") == ""           # keine Regel
    assert naechste_faellig("FREQ=DAILY", "") == ""           # kein faellig
    # durch UNTIL erschöpft ⇒ keine Folge mehr
    assert naechste_faellig("FREQ=DAILY;UNTIL=2026-06-20", "2026-06-20") == ""
