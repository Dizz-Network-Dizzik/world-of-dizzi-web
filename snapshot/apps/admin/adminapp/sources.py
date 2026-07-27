"""Kalender-/Aufgaben-Quellen des Projekte-Moduls von Dizz Admin (aus Dizz Plans
portiert) — der austauschbare Sync-Stecker.

Kernidee (docs/RECHERCHE §3, Gesetz 5 = Anschlüsse JETZT vorsehen): die App
spricht nie direkt mit einem konkreten Anbieter, sondern gegen ZWEI Interfaces
— ``CalendarSource`` und ``TaskSource``. v1 ist **lokal-first**: die lokale DB
ist die Wahrheit; externe Quellen werden eingezogen (Import), nicht live
gespiegelt. Spätere Stufe = Zwei-Wege-Sync (ETags/Last-Modified, Konfliktlösung)
— das Datenmodell (extern_id/etag/quelle, s. domain.py) ist dafür schon bereit.

Vorbereitete Adapter (bewusst dokumentierte Slots — Bewusstsein über ihr
Vorhandensein, auch wo v1 sie noch nicht nutzt, Gesetz 5):

- ``GoogleCalendarAdapter`` — ERSTER Adapter (Nutzer-Entscheid, docs/02). v1
  DORMANT: ``verfuegbar()`` ist erst True, sobald ein OAuth-Token im Token-Tresor
  liegt (appkit/vault.py). Ohne Token liefert der Adapter ehrlich „nicht
  verbunden" statt zu raten. Der echte OAuth-Flow + die Calendar-v3-Abfrage sind
  als Methoden-Gerüst + Doku angelegt; Aktivierung = K2-Tresor-Token + Freigabe.
- ``ICalImport`` — iCal/.ics-Import (RFC 5545). v1 ECHT nutzbar: ``parse_ical``
  ist ein abhängigkeitsfreier Parser (Zeilen-Entfaltung, VEVENT, DATE vs
  DATE-TIME, TEXT-Unescaping, RRULE roh durchgereicht). „Kleinster gemeinsamer
  Nenner" für Termin-Austausch — funktioniert mit Google/Nextcloud/Outlook-Export.

Künftige Slots (gleiche Interfaces, kein Domänen-Umbau): ``CalDAVAdapter`` (offener
Standard, Nextcloud/Fastmail/…), ``GitHubAdapter``/``GitLabAdapter`` als
``TaskSource`` (Issues als Projektquelle — der Nutzer baut selbst Software).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Normierte Austauschformate (was JEDER Adapter liefert) ────────────────────
@dataclass
class ExternalEvent:
    """Ein Termin aus einer externen Quelle, normiert auf das Domänen-Modell.

    ``extern_id`` ist der stabile Schlüssel der Quelle (iCal-UID / Google-Event-ID)
    — er trägt die Idempotenz des Imports (Dedupe) und später den Zwei-Wege-Sync.
    Zeiten als ISO-8601-Strings: ``beginn``/``ende``; ``ganztags`` markiert reine
    DATE-Werte. ``rrule`` wird ROH durchgereicht (Expansion = späterer Slot).
    """

    extern_id: str
    titel: str
    beginn: str                       # ISO-8601 (Date oder DateTime)
    ende: str = ""                    # ISO-8601 oder leer
    ganztags: bool = False
    ort: str = ""
    notiz: str = ""
    rrule: str = ""                   # roh (RFC 5545), Expansion folgt
    quelle: str = "ical"
    etag: str = ""                    # für späteren Zwei-Wege-Sync (Last-Modified)


@dataclass
class ExternalTask:
    """Eine Aufgabe aus einer externen Quelle (Todoist/GitHub-Issue/…)."""

    extern_id: str
    titel: str
    faellig: str = ""                 # ISO-Date oder leer
    notiz: str = ""
    status: str = "offen"
    quelle: str = ""


# ── Interfaces (der Vertrag, gegen den die Domäne arbeitet) ───────────────────
class CalendarSource(ABC):
    """Quelle von Terminen. v1 read-only (Einzug); Schreiben = späterer Slot."""

    name: str = "kalender"

    @abstractmethod
    def verfuegbar(self) -> bool:
        """True, wenn die Quelle nutzbar ist (Token vorhanden / Datei geladen)."""

    @abstractmethod
    def list_events(self, since: str = "", until: str = "") -> list[ExternalEvent]:
        """Termine im Zeitfenster ``[since, until]`` (ISO-Daten; leer = alle)."""


class TaskSource(ABC):
    """Quelle von Aufgaben (Todoist/GitHub-Issues/…) — v1 nur Slot."""

    name: str = "aufgaben"

    @abstractmethod
    def verfuegbar(self) -> bool: ...

    @abstractmethod
    def list_tasks(self) -> list[ExternalTask]: ...


class QuelleNichtVerbunden(RuntimeError):
    """Adapter ist deklariert, aber (noch) nicht verbunden — ehrlich statt raten."""


# ── iCal-Import (RFC 5545) — v1 ECHT ──────────────────────────────────────────
def _entfalte(text: str) -> list[str]:
    """RFC-5545-Zeilen-Entfaltung: Folgezeilen beginnen mit Space/Tab und gehören
    an die vorige Zeile (lange Werte werden im Format umgebrochen)."""
    roh = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    zeilen: list[str] = []
    for z in roh:
        if z[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += z[1:]
        else:
            zeilen.append(z)
    return zeilen


def _split_prop(zeile: str) -> tuple[str, dict[str, str], str]:
    """Zerlegt ``NAME;PARAM=val;…:WERT`` in (Name, Parameter, Wert).
    Der Wert beginnt am ersten ':' außerhalb von Anführungszeichen."""
    in_quote = False
    for i, ch in enumerate(zeile):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            kopf, wert = zeile[:i], zeile[i + 1:]
            break
    else:
        return zeile.strip().upper(), {}, ""
    teile = kopf.split(";")
    name = teile[0].strip().upper()
    params: dict[str, str] = {}
    for p in teile[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return name, params, wert


def _unescape(text: str) -> str:
    """TEXT-Werte entschärfen (RFC 5545 §3.3.11)."""
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append({"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _iso_zeit(wert: str, params: dict[str, str]) -> tuple[str, bool]:
    """Wandelt einen DTSTART/DTEND-Wert in (ISO-8601, ganztags).

    - ``VALUE=DATE`` oder 8-stellig ⇒ reines Datum ``YYYY-MM-DD`` (ganztags).
    - ``…T…Z`` ⇒ UTC, als ``…+00:00`` ausgewiesen.
    - ``…T…`` ohne Z (floating/TZID) ⇒ naive ISO-Zeit; TZID wird NICHT
      umgerechnet (v1-Grenze, dokumentiert) — der Sync trägt extern_id/etag.
    """
    wert = wert.strip()
    if params.get("VALUE") == "DATE" or (len(wert) == 8 and wert.isdigit()):
        d = wert[:8]
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}", True
    if "T" in wert:
        datum, _, zeit = wert.partition("T")
        utc = zeit.endswith("Z")
        zeit = zeit[:-1] if utc else zeit
        d, t = datum, (zeit + "000000")[:6]
        iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}T{t[0:2]}:{t[2:4]}:{t[4:6]}"
        return (iso + "+00:00") if utc else iso, False
    return wert, False


def parse_ical(text: str) -> list[ExternalEvent]:
    """Parst iCal/.ics-Text zu normierten ``ExternalEvent`` (nur VEVENT).

    Abhängigkeitsfrei und tolerant: unbekannte Properties werden ignoriert,
    fehlende UID per Inhalts-Hash synthetisiert (stabiler Dedupe-Schlüssel),
    VEVENT ohne SUMMARY/DTSTART übersprungen.
    """
    events: list[ExternalEvent] = []
    cur: dict[str, Any] | None = None
    for zeile in _entfalte(text):
        name, params, wert = _split_prop(zeile)
        if name == "BEGIN" and wert.upper() == "VEVENT":
            cur = {}
            continue
        if name == "END" and wert.upper() == "VEVENT":
            if cur is not None and cur.get("titel") and cur.get("beginn"):
                uid = cur.get("uid") or "ical-" + hashlib.sha1(
                    f"{cur['titel']}|{cur['beginn']}".encode("utf-8")).hexdigest()[:16]
                events.append(ExternalEvent(
                    extern_id=uid, titel=cur["titel"], beginn=cur["beginn"],
                    ende=cur.get("ende", ""), ganztags=cur.get("ganztags", False),
                    ort=cur.get("ort", ""), notiz=cur.get("notiz", ""),
                    rrule=cur.get("rrule", ""), quelle="ical"))
            cur = None
            continue
        if cur is None:
            continue
        if name == "UID":
            cur["uid"] = wert.strip()
        elif name == "SUMMARY":
            cur["titel"] = _unescape(wert).strip()
        elif name == "DTSTART":
            cur["beginn"], cur["ganztags"] = _iso_zeit(wert, params)
        elif name == "DTEND":
            cur["ende"], _ = _iso_zeit(wert, params)
        elif name == "LOCATION":
            cur["ort"] = _unescape(wert).strip()
        elif name == "DESCRIPTION":
            cur["notiz"] = _unescape(wert).strip()
        elif name == "RRULE":
            cur["rrule"] = wert.strip()
    return events


class ICalImport(CalendarSource):
    """``CalendarSource`` über einem iCal-Text (Datei-Upload / .ics-Inhalt).

    Erfüllt das Interface, damit der Import-Pfad identisch zu künftigen
    Live-Quellen (Google/CalDAV) bleibt — die Domäne ruft immer ``list_events``.
    """

    name = "ical"

    def __init__(self, ics_text: str) -> None:
        self._text = ics_text or ""
        self._events = parse_ical(self._text)

    def verfuegbar(self) -> bool:
        return bool(self._text.strip())

    def list_events(self, since: str = "", until: str = "") -> list[ExternalEvent]:
        ev = self._events
        if since:
            ev = [e for e in ev if (e.ende or e.beginn) >= since]
        if until:
            ev = [e for e in ev if e.beginn <= until]
        return ev


# ── Google Calendar (ERSTER Adapter) — v1 DORMANT, Token-Tresor-gated ─────────
class GoogleCalendarAdapter(CalendarSource):
    """Google-Calendar-Adapter (Nutzer-Entscheid: erster Adapter, docs/02).

    ── Aktivierung (Gesetz 5: vorbereitet, nicht aktiv) ──────────────────────
    1. OAuth-2.0-Consent (Scope ``calendar.readonly``) → Refresh-Token.
    2. Refresh-Token verschlüsselt in den App-Token-Tresor legen
       (``appkit/vault.py``, Name = ``token_name``) — NIE in app_settings.
    3. ``verfuegbar()`` wird dann True; ``list_events`` ruft die Calendar-v3-API
       (``/calendar/v3/calendars/primary/events``) und normiert auf
       ``ExternalEvent`` (Felder identisch zum iCal-Pfad).

    v1 absichtlich passiv: ohne Tresor-Token meldet der Adapter „nicht verbunden"
    (``QuelleNichtVerbunden``) statt zu raten. So steht der Stecker bereit, ohne
    dass v1 ein Google-Konto braucht oder Außenwirkung erzeugt (lokal-first).
    """

    name = "google"
    # Calendar-v3-Basis (für die spätere Aktivierung dokumentiert):
    API_BASE = "https://www.googleapis.com/calendar/v3"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str = "google_calendar_refresh_token",
                 kalender_id: str = "primary",
                 http_get: Callable[..., Any] | None = None) -> None:
        # ``vault_get(name)`` liefert das (entschlüsselte) Token oder None.
        self._vault_get = vault_get or (lambda _name: None)
        self.token_name = token_name
        self.kalender_id = kalender_id
        self._http_get = http_get        # injizierbar (Tests/spätere Aktivierung)

    def verfuegbar(self) -> bool:
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        """Für die UI/MCP: verbunden? welcher Tresor-Schlüssel wird erwartet?"""
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "token_name": self.token_name, "kalender": self.kalender_id,
                "hinweis": "OAuth-Refresh-Token im Token-Tresor hinterlegen, "
                           "dann ist die Quelle aktiv (read-only)."}

    def list_events(self, since: str = "", until: str = "") -> list[ExternalEvent]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                "Google Calendar nicht verbunden — Refresh-Token fehlt im "
                f"Token-Tresor (erwarteter Name: {self.token_name!r}).")
        # Aktivierungs-Slot: Access-Token aus Refresh-Token holen, Events laden
        # und auf ExternalEvent normieren. v1 noch nicht freigeschaltet.
        raise QuelleNichtVerbunden(
            "Google-Live-Abruf ist in v1 noch nicht freigeschaltet "
            "(Adapter-Gerüst steht; Aktivierung = K2-Token + Freigabe).")


# ── CalDAV (offener Standard, „kleinster gemeinsamer Nenner") — DORMANT ───────
class CalDAVAdapter(CalendarSource):
    """CalDAV-Adapter (RFC 4791) — der offene Standard hinter Nextcloud/Fastmail/
    fruux/Zoho/Yahoo (docs/RECHERCHE §2). v1 DORMANT (Gesetz 5: vorbereitet).

    ── Aktivierung ──────────────────────────────────────────────────────────
    1. Server-URL (Kalender-Collection) + Benutzer + App-Passwort; das Passwort
       verschlüsselt in den Token-Tresor (Name = ``token_name``) — NIE app_settings.
    2. ``verfuegbar()`` wird True (URL gesetzt + Passwort im Tresor).
    3. ``list_events`` macht einen ``REPORT`` (``calendar-query``) gegen die
       Collection; die Antwort liefert ``VCALENDAR``-Blöcke ⇒ direkt über
       ``parse_ical`` auf ``ExternalEvent`` normierbar (derselbe Pfad wie iCal).
       (``PROPFIND`` listet die Kalender; ETags tragen später den Zwei-Wege-Sync.)

    v1 absichtlich passiv: ohne URL+Passwort „nicht verbunden". Read-only zuerst.
    """

    name = "caldav"

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 base_url: str = "", benutzer: str = "",
                 token_name: str = "caldav_passwort",
                 http_request: Callable[..., Any] | None = None) -> None:
        self._vault_get = vault_get or (lambda _name: None)
        self.base_url = base_url.rstrip("/")
        self.benutzer = benutzer
        self.token_name = token_name
        self._http_request = http_request    # injizierbar (Tests/spätere Aktivierung)

    def verfuegbar(self) -> bool:
        try:
            return bool(self.base_url) and bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "token_name": self.token_name, "url_gesetzt": bool(self.base_url),
                "hinweis": "Server-URL setzen + App-Passwort im Tresor hinterlegen "
                           "(read-only REPORT/calendar-query, Antwort via parse_ical)."}

    def list_events(self, since: str = "", until: str = "") -> list[ExternalEvent]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                "CalDAV nicht verbunden — Server-URL und/oder App-Passwort "
                f"(Tresor {self.token_name!r}) fehlen.")
        # Aktivierungs-Slot: REPORT calendar-query → VCALENDAR-Blöcke → parse_ical.
        raise QuelleNichtVerbunden(
            "CalDAV-Live-Abruf ist in v1 noch nicht freigeschaltet "
            "(Adapter-Gerüst + parse_ical-Pfad stehen; Aktivierung = K2-Token + Freigabe).")


# ── Issue-Tracker als TaskSource (GitHub/GitLab) — DORMANT ────────────────────
def _github_issue_to_task(issue: dict[str, Any]) -> ExternalTask:
    """GitHub-Issue-JSON → ``ExternalTask`` (reine Abbildung, testbar)."""
    return ExternalTask(
        extern_id="github:" + str(issue.get("id") or issue.get("number") or ""),
        titel=str(issue.get("title") or "").strip() or "(ohne Titel)",
        faellig="",  # GitHub-Issues haben kein Fälligkeitsdatum (Milestone optional)
        notiz=(str(issue.get("body") or "")[:500]),
        status="erledigt" if str(issue.get("state")) == "closed" else "offen",
        quelle="github")


def _gitlab_issue_to_task(issue: dict[str, Any]) -> ExternalTask:
    """GitLab-Issue-JSON → ``ExternalTask`` (reine Abbildung, testbar)."""
    return ExternalTask(
        extern_id="gitlab:" + str(issue.get("id") or issue.get("iid") or ""),
        titel=str(issue.get("title") or "").strip() or "(ohne Titel)",
        faellig=str(issue.get("due_date") or "")[:10],   # GitLab kennt due_date
        notiz=(str(issue.get("description") or "")[:500]),
        status="erledigt" if str(issue.get("state")) == "closed" else "offen",
        quelle="gitlab")


class _IssueTrackerAdapter(TaskSource):
    """Gemeinsame Basis für GitHub/GitLab-Issue-Quellen — v1 DORMANT (Gesetz 5).
    Der Nutzer baut selbst Software (Trading Bot, Dizzi) ⇒ Code-Repos als
    Projektquelle vorgesehen (docs/RECHERCHE §2). Token im Tresor, read-only.
    Aktivierung: Issues der API holen → ``_*_issue_to_task`` mappen."""

    name = "issues"
    API_BASE = ""
    _MAP: Callable[[dict[str, Any]], ExternalTask]

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str = "", repo: str = "",
                 http_get: Callable[..., Any] | None = None) -> None:
        self._vault_get = vault_get or (lambda _name: None)
        self.token_name = token_name
        self.repo = repo
        self._http_get = http_get

    def verfuegbar(self) -> bool:
        try:
            return bool(self.repo) and bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "verbunden": self.verfuegbar(),
                "token_name": self.token_name, "repo_gesetzt": bool(self.repo),
                "hinweis": "Repo setzen + Personal-Access-Token im Tresor; read-only "
                           "Issue-Import (Issue→Aufgabe)."}

    def list_tasks(self) -> list[ExternalTask]:
        if not self.verfuegbar():
            raise QuelleNichtVerbunden(
                f"{self.name} nicht verbunden — Repo und/oder Token "
                f"(Tresor {self.token_name!r}) fehlen.")
        raise QuelleNichtVerbunden(
            f"{self.name}-Live-Abruf ist in v1 noch nicht freigeschaltet "
            "(Adapter-Gerüst + Issue-Mapping stehen; Aktivierung = K2-Token + Freigabe).")


class GitHubAdapter(_IssueTrackerAdapter):
    name = "github"
    API_BASE = "https://api.github.com"

    def __init__(self, vault_get=None, repo="", token_name="github_token", http_get=None):
        super().__init__(vault_get, token_name=token_name, repo=repo, http_get=http_get)

    @staticmethod
    def issue_to_task(issue: dict[str, Any]) -> ExternalTask:
        return _github_issue_to_task(issue)


class GitLabAdapter(_IssueTrackerAdapter):
    name = "gitlab"
    API_BASE = "https://gitlab.com/api/v4"

    def __init__(self, vault_get=None, repo="", token_name="gitlab_token", http_get=None):
        super().__init__(vault_get, token_name=token_name, repo=repo, http_get=http_get)

    @staticmethod
    def issue_to_task(issue: dict[str, Any]) -> ExternalTask:
        return _gitlab_issue_to_task(issue)


# ── Quellen-Register: alle vorbereiteten Stecker auf einen Blick (Gesetz 5) ───
# Macht die vorhandenen (aktiven + dormanten) Anschlüsse sichtbar — Bewusstsein
# über Vorbereitungen (Grundgesetz 5). ``/api/quellen`` rendert das + Tresor-Status.
SOURCE_SLOTS: tuple[dict[str, str], ...] = (
    {"name": "ical", "art": "kalender", "status": "aktiv", "token_name": "",
     "hinweis": "iCal/.ics-Import (echt) über POST /api/termine/import_ical."},
    {"name": "google", "art": "kalender", "status": "vorbereitet",
     "token_name": "google_calendar_refresh_token",
     "hinweis": "Google Calendar (read-only) — OAuth-Refresh-Token in den Tresor."},
    {"name": "caldav", "art": "kalender", "status": "vorbereitet",
     "token_name": "caldav_passwort",
     "hinweis": "CalDAV (offener Standard) — Server-URL + App-Passwort im Tresor."},
    {"name": "github", "art": "aufgaben", "status": "vorbereitet",
     "token_name": "github_token",
     "hinweis": "GitHub-Issues → Aufgaben (read-only) — Repo + PAT im Tresor."},
    {"name": "gitlab", "art": "aufgaben", "status": "vorbereitet",
     "token_name": "gitlab_token",
     "hinweis": "GitLab-Issues → Aufgaben (read-only) — Repo + PAT im Tresor."},
)
