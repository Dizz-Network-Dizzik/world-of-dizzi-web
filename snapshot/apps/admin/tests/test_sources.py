"""Tests Dizz Admin — Kalender-/Task-Quellen (Projekte-Modul, aus Plans portiert):
iCal-Parser + dormante Konnektor-Slots (Google/CalDAV/GitHub/GitLab, Gesetz 5).
App-freie Einheiten; die Endpoint-Tests (/api/termine/import_ical, /api/quellen)
folgen mit dem Projekte-Domänen-Port. Lauf: <venv-python> -m pytest tests/ -q
"""

from __future__ import annotations

import pytest

from adminapp.sources import (CalDAVAdapter, GitHubAdapter, GitLabAdapter,
                              GoogleCalendarAdapter, ICalImport,
                              QuelleNichtVerbunden, parse_ical)

SAMPLE_ICS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:evt-1@dizz\r\n"
    "SUMMARY:Kickoff Dizz Plans\r\n"
    "DTSTART:20260620T130000Z\r\n"
    "DTEND:20260620T140000Z\r\n"
    "LOCATION:Online\r\n"
    "DESCRIPTION:Erstes Treffen\\, Agenda folgt\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:evt-2@dizz\r\n"
    "SUMMARY:Ganztag Workshop\r\n"
    "DTSTART;VALUE=DATE:20260622\r\n"
    "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_ical_parser_units():
    events = parse_ical(SAMPLE_ICS)
    assert len(events) == 2
    e1, e2 = events
    assert e1.extern_id == "evt-1@dizz" and e1.titel == "Kickoff Dizz Plans"
    assert e1.beginn == "2026-06-20T13:00:00+00:00" and e1.ende == "2026-06-20T14:00:00+00:00"
    assert e1.ganztags is False and e1.ort == "Online"
    assert e1.notiz == "Erstes Treffen, Agenda folgt"      # Komma-Unescaping
    # Ganztag (VALUE=DATE) + RRULE roh durchgereicht
    assert e2.beginn == "2026-06-22" and e2.ganztags is True
    assert e2.rrule == "FREQ=WEEKLY;COUNT=3"


def test_google_adapter_dormant():
    # ohne Tresor-Token: nicht verfügbar, list_events meldet ehrlich „nicht verbunden"
    leer = GoogleCalendarAdapter(vault_get=lambda _n: None)
    assert leer.verfuegbar() is False
    assert leer.status()["verbunden"] is False
    with pytest.raises(QuelleNichtVerbunden):
        leer.list_events()
    # mit Token: verfügbar — der Live-Abruf ist v1 bewusst noch nicht freigeschaltet
    mit = GoogleCalendarAdapter(vault_get=lambda _n: "refresh-token-xyz")
    assert mit.verfuegbar() is True and mit.status()["verbunden"] is True
    with pytest.raises(QuelleNichtVerbunden):
        mit.list_events()


def test_konnektor_slots_dormant():
    """Gesetz 5: CalDAV + GitHub/GitLab als vorbereitete, dormante Stecker —
    nicht verbunden ohne Tresor-Daten; Issue→Aufgabe-Mapping rein/testbar."""
    cal = CalDAVAdapter(vault_get=lambda n: None)
    assert cal.verfuegbar() is False
    with pytest.raises(QuelleNichtVerbunden):
        cal.list_events()
    cal2 = CalDAVAdapter(vault_get=lambda n: "pw", base_url="https://dav.example/cal/")
    assert cal2.verfuegbar() is True
    with pytest.raises(QuelleNichtVerbunden):    # Live in v1 bewusst nicht freigeschaltet
        cal2.list_events()
    gh = GitHubAdapter(vault_get=lambda n: None, repo="me/repo")
    assert gh.verfuegbar() is False
    with pytest.raises(QuelleNichtVerbunden):
        gh.list_tasks()
    t = GitHubAdapter.issue_to_task({"id": 7, "title": "Bug", "state": "open", "body": "x"})
    assert t.extern_id == "github:7" and t.titel == "Bug" and t.status == "offen" and t.quelle == "github"
    assert GitHubAdapter.issue_to_task({"number": 9, "title": "Z", "state": "closed"}).status == "erledigt"
    g = GitLabAdapter.issue_to_task({"id": 3, "title": "Feat", "state": "opened",
                                     "due_date": "2026-09-01", "description": "d"})
    assert g.extern_id == "gitlab:3" and g.faellig == "2026-09-01" and g.status == "offen"


def test_ical_import_source_interface():
    src = ICalImport(SAMPLE_ICS)
    assert src.verfuegbar() is True
    assert len(src.list_events()) == 2
    # Zeitfenster-Filter (since/until über das Interface)
    assert len(src.list_events(since="2026-06-21")) == 1     # nur der Ganztag-Event danach
    assert ICalImport("").verfuegbar() is False
