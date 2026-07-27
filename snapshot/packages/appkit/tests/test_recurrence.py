"""Tests der RRULE-light-Engine ``appkit/recurrence.py`` (netzweit geteilt,
docs/50 P2.2) — rein/deterministisch. Deckt die bestehende Semantik (von admin
übernommen) UND die neue BYDAY-Erweiterung (RFC 5545 §3.3.10).

Lauf: PYTHONPATH=packages  venv-python -m pytest packages/appkit/tests/test_recurrence.py -q
"""

from __future__ import annotations

from datetime import date

from appkit.recurrence import (expandiere, ist_gueltig, naechste_faellig,
                               parse_rule, schritt_kalender)


# ===================== parse_rule =====================
def test_parse_rule_grundformen():
    assert parse_rule("FREQ=DAILY") == {"freq": "DAILY", "interval": 1}
    assert parse_rule("FREQ=WEEKLY;INTERVAL=2")["interval"] == 2
    assert parse_rule("FREQ=MONTHLY;COUNT=6")["count"] == 6
    r = parse_rule("freq=weekly;until=20261231")     # case-insensitiv + UNTIL
    assert r["freq"] == "WEEKLY" and r["until"].isoformat() == "2026-12-31"


def test_parse_rule_byday():
    # BYDAY wird jetzt erkannt (nicht mehr nur tolerant ignoriert)
    assert parse_rule("FREQ=WEEKLY;BYDAY=MO,WE")["byday"] == [(None, 0), (None, 2)]
    assert parse_rule("FREQ=MONTHLY;BYDAY=2MO")["byday"] == [(2, 0)]
    assert parse_rule("FREQ=MONTHLY;BYDAY=-1FR")["byday"] == [(-1, 4)]
    assert parse_rule("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1")["bysetpos"] == -1
    # kaputte/leere BYDAY-Tokens tolerant ⇒ kein byday-Key, Regel bleibt gültig
    assert "byday" not in parse_rule("FREQ=WEEKLY;BYDAY=XX,0MO")
    assert parse_rule("FREQ=WEEKLY;BYDAY=XX")["freq"] == "WEEKLY"


def test_parse_rule_ungueltig():
    assert parse_rule("") == {}
    assert parse_rule("   ") == {}
    assert parse_rule("FREQ=HOURLY") == {}          # nicht unterstützte Frequenz
    assert parse_rule("INTERVAL=2") == {}           # FREQ fehlt
    assert parse_rule("FREQ=DAILY;COUNT=abc") == {}  # kaputter Wert ⇒ ganz verworfen


def test_ist_gueltig():
    assert ist_gueltig("") is True                  # leer = einmalig = ok
    assert ist_gueltig("FREQ=DAILY;INTERVAL=3") is True
    assert ist_gueltig("FREQ=WEEKLY;BYDAY=MO,WE") is True
    assert ist_gueltig("FREQ=NONSENSE") is False


# ===================== expandiere (Basis, von admin übernommen) ===============
def test_expandiere_leer_ist_einzeln():
    assert expandiere("", "2026-06-20") == ["2026-06-20"]
    assert expandiere("FREQ=BLAH", "2026-06-20") == ["2026-06-20"]


def test_expandiere_taeglich_count_inklusiv():
    assert expandiere("FREQ=DAILY;COUNT=3", "2026-06-20") == [
        "2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_woechentlich_interval_und_suffix():
    out = expandiere("FREQ=WEEKLY;INTERVAL=2;COUNT=3", "2026-06-01T09:30:00+00:00")
    assert out == ["2026-06-01T09:30:00+00:00", "2026-06-15T09:30:00+00:00",
                   "2026-06-29T09:30:00+00:00"]


def test_expandiere_monatlich_klemmt_tag():
    out = expandiere("FREQ=MONTHLY;COUNT=4", "2026-01-31")
    assert out == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_expandiere_until_inklusiv():
    out = expandiere("FREQ=DAILY;UNTIL=2026-06-22", "2026-06-20")
    assert out == ["2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_fenster_bis_deckelt():
    out = expandiere("FREQ=DAILY;COUNT=30", "2026-06-20", bis="2026-06-22")
    assert out == ["2026-06-20", "2026-06-21", "2026-06-22"]


def test_expandiere_limit_obergrenze():
    assert len(expandiere("FREQ=DAILY", "2026-01-01", limit=5)) == 5


# ===================== expandiere (BYDAY, neu) ================================
def test_expandiere_weekly_byday_mehrere_wochentage():
    # 2026-06-01 ist Montag; Mo+Mi je Woche, COUNT zählt Instanzen
    assert expandiere("FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4", "2026-06-01") == [
        "2026-06-01", "2026-06-03", "2026-06-08", "2026-06-10"]


def test_expandiere_weekly_byday_start_mittendrin():
    # Start an einem Mittwoch ⇒ der Montag DAVOR (gleiche Woche) entfällt
    assert expandiere("FREQ=WEEKLY;BYDAY=MO,WE;COUNT=3", "2026-06-03") == [
        "2026-06-03", "2026-06-08", "2026-06-10"]


def test_expandiere_weekly_byday_interval_und_suffix():
    out = expandiere("FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;COUNT=3", "2026-06-05T08:00:00+00:00")
    assert out == ["2026-06-05T08:00:00+00:00", "2026-06-19T08:00:00+00:00",
                   "2026-07-03T08:00:00+00:00"]


def test_expandiere_monthly_byday_nter_wochentag():
    # 2. Montag im Monat
    assert expandiere("FREQ=MONTHLY;BYDAY=2MO;COUNT=3", "2026-06-01") == [
        "2026-06-08", "2026-07-13", "2026-08-10"]


def test_expandiere_monthly_byday_letzter():
    # Letzter Freitag im Monat
    assert expandiere("FREQ=MONTHLY;BYDAY=-1FR;COUNT=3", "2026-06-01") == [
        "2026-06-26", "2026-07-31", "2026-08-28"]


def test_expandiere_monthly_bysetpos_letzter_werktag():
    # „Letzter Werktag" = BYDAY=MO..FR;BYSETPOS=-1
    assert expandiere("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=3",
                      "2026-06-01") == ["2026-06-30", "2026-07-31", "2026-08-31"]


def test_expandiere_byday_until_deckelt():
    out = expandiere("FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=2026-06-08", "2026-06-01")
    assert out == ["2026-06-01", "2026-06-03", "2026-06-08"]


# ===================== naechste_faellig =====================
def test_naechste_faellig():
    assert naechste_faellig("FREQ=WEEKLY", "2026-06-20") == "2026-06-27"
    assert naechste_faellig("FREQ=MONTHLY;INTERVAL=2", "2026-01-31") == "2026-03-31"
    assert naechste_faellig("", "2026-06-20") == ""           # keine Regel
    assert naechste_faellig("FREQ=DAILY", "") == ""           # kein faellig
    assert naechste_faellig("FREQ=DAILY;UNTIL=2026-06-20", "2026-06-20") == ""


def test_naechste_faellig_byday():
    # nach Mo 2026-06-01 ist die nächste Mo/Mi-Instanz der Mi 2026-06-03
    assert naechste_faellig("FREQ=WEEKLY;BYDAY=MO,WE", "2026-06-01") == "2026-06-03"
    # 2. Montag: nach dem 2026-06-08 folgt der 2026-07-13
    assert naechste_faellig("FREQ=MONTHLY;BYDAY=2MO", "2026-06-08") == "2026-07-13"
    # durch UNTIL erschöpft ⇒ keine Folge
    assert naechste_faellig("FREQ=WEEKLY;BYDAY=MO;UNTIL=2026-06-01", "2026-06-01") == ""


# ===================== schritt_kalender (Money-Hebel) =========================
def test_schritt_kalender_kalender_bewusst():
    # Monat = ECHTER Kalenderschritt (gleicher Tag, geklemmt) — nicht +30 Tage
    assert schritt_kalender(date(2026, 1, 1), "monat") == date(2026, 2, 1)
    assert schritt_kalender(date(2026, 1, 31), "monat") == date(2026, 2, 28)
    assert schritt_kalender(date(2026, 1, 15), "jahr") == date(2027, 1, 15)
    assert schritt_kalender(date(2026, 6, 1), "tag", 5) == date(2026, 6, 6)
    assert schritt_kalender(date(2026, 6, 1), "woche", 2) == date(2026, 6, 15)
