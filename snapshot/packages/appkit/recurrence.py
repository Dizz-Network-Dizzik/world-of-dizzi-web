"""RRULE-light — deterministische Wiederholungs-Regeln (netzweit geteilt, appkit).

Bewusst eine KLEINE, vollständig deterministische Teilmenge von RFC 5545 (RRULE):
``FREQ`` ∈ {DAILY, WEEKLY, MONTHLY} · ``INTERVAL`` (≥1) · genau eine Grenze
``COUNT`` ODER ``UNTIL`` (sonst über ``limit`` gedeckelt) · optional ``BYDAY``
(Wochentage, für MONTHLY auch n-ter/​letzter Wochentag, optional ``BYSETPOS``).
Das deckt den Alltag („jeden Tag / jede Woche / jeden Monat / jeden Mo+Mi /
2. Montag im Monat") ab und ist trivial testbar — kein Datums-Bibliotheks-Zauber,
keine Zeitzonen-Mathematik.

Warum eigenständig (statt ``dateutil.rrule``): 0 Zusatz-Abhängigkeit, und das
Format ist 1:1 das ``rrule``-Feld, das der iCal-Import (admin/sources.parse_ical)
ohnehin ROH speichert — eine importierte ``FREQ=WEEKLY;BYDAY=MO,WE`` wird damit
direkt expandierbar (Import-Treue, docs/50 P2.2).

**Single-Source (docs/50 P2.2):** liegt EINMAL hier in ``packages/appkit`` und wird
von Dizz Admin (Aufgaben/Termine/Abos) UND Dizz Money (wiederkehrende Posten,
kalender-bewusste Fälligkeits-Vorhersage) geteilt — kein Vendoring.

Reine Funktionen, KEIN ``now()`` — die Expansion hängt nur von (Regel, Start) ab.
Zeit-/Zonen-Suffix des Starts (``T13:00:00+00:00``) wird unverändert an jede
Instanz gehängt (v1-Grenze: keine TZ-Verschiebung — wie der iCal-Import, docs).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

FREQS = ("DAILY", "WEEKLY", "MONTHLY")
_MAX = 366  # harte Obergrenze gegen Endlos-Expansion (auch ohne COUNT/UNTIL)

# RFC 5545 §3.3.10: MO…SU. Index = Python ``date.weekday()`` (Montag=0).
_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_byday(roh: str) -> list[tuple[int | None, int]]:
    """Zerlegt ``BYDAY`` (z. B. ``MO,WE`` oder ``2MO,-1FR``) in eine Liste von
    ``(ordinal|None, weekday)``. Unbekannte Tokens werden tolerant übersprungen
    (leere Liste ⇒ BYDAY wirkt nicht, wie bisher die Roh-Toleranz)."""
    out: list[tuple[int | None, int]] = []
    for tok in roh.split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        tag = tok[-2:]
        if tag not in _WEEKDAYS:
            continue
        praefix = tok[:-2]
        ordinal: int | None = None
        if praefix:
            try:
                ordinal = int(praefix)
            except ValueError:
                continue
            if ordinal == 0:
                continue
        out.append((ordinal, _WEEKDAYS[tag]))
    return out


def parse_rule(rrule: str) -> dict:
    """Zerlegt eine RRULE-light in ein normiertes dict — oder ``{}`` (leer/ungültig).

    Erkennt ``FREQ`` (Pflicht, einer aus FREQS), ``INTERVAL`` (≥1, Default 1),
    ``COUNT`` (≥1), ``UNTIL`` (Datum: ``YYYYMMDD`` oder ISO ``YYYY-MM-DD…``),
    ``BYDAY`` (Wochentage, optional mit Ordinal-Präfix) und ``BYSETPOS`` (Auswahl
    aus den BYDAY-Treffern eines Monats, 1-basiert, negativ = von hinten).
    Unbekannte/kaputte BYDAY-Tokens werden tolerant ignoriert.
    """
    if not rrule or not rrule.strip():
        return {}
    teile: dict[str, str] = {}
    for stueck in rrule.strip().split(";"):
        if "=" in stueck:
            k, v = stueck.split("=", 1)
            teile[k.strip().upper()] = v.strip()
    freq = teile.get("FREQ", "").upper()
    if freq not in FREQS:
        return {}
    out: dict = {"freq": freq, "interval": 1}
    try:
        if "INTERVAL" in teile:
            out["interval"] = max(1, int(teile["INTERVAL"]))
        if "COUNT" in teile:
            out["count"] = max(1, int(teile["COUNT"]))
        if "UNTIL" in teile:
            roh = teile["UNTIL"]
            datum = roh[:10] if "-" in roh else f"{roh[0:4]}-{roh[4:6]}-{roh[6:8]}"
            out["until"] = date.fromisoformat(datum)
        if "BYSETPOS" in teile:
            out["bysetpos"] = int(teile["BYSETPOS"])
    except (ValueError, IndexError):
        return {}
    if "BYDAY" in teile:
        byday = _parse_byday(teile["BYDAY"])
        if byday:
            out["byday"] = byday
    return out


def ist_gueltig(rrule: str) -> bool:
    """True, wenn ``rrule`` leer ODER eine wohlgeformte RRULE-light ist.
    (Leer = „einmalig" ist gültig; nur Müll-Regeln werden abgelehnt.)"""
    return not rrule.strip() or bool(parse_rule(rrule))


def _split_start(start: str) -> tuple[date, str]:
    """Trennt einen ISO-Start in (Datum, Suffix). Suffix = alles ab Zeichen 10
    (``T13:00…`` oder ``""`` bei reinem Datum)."""
    datum = date.fromisoformat(start[:10])
    return datum, start[10:]


def _add(d: date, freq: str, interval: int) -> date:
    """Ein Wiederholungs-Schritt. MONTHLY klemmt den Tag auf die Monatslänge
    (31. Jan + 1 Monat ⇒ 28./29. Feb) — deterministisch und überraschungsfrei."""
    if freq == "DAILY":
        return date.fromordinal(d.toordinal() + interval)
    if freq == "WEEKLY":
        return date.fromordinal(d.toordinal() + 7 * interval)
    # MONTHLY
    return _add_months(d, interval)


def _add_months(d: date, monate: int) -> date:
    """Kalender-bewusster Monats-Schritt mit Tag-Klemmung (für MONTHLY und für
    Dizz Moneys kalender-bewusste Vorhersage: 31. Jan +1 ⇒ 28./29. Feb)."""
    m0 = d.month - 1 + monate
    jahr = d.year + m0 // 12
    monat = m0 % 12 + 1
    tag = min(d.day, calendar.monthrange(jahr, monat)[1])
    return date(jahr, monat, tag)


def schritt_kalender(d: date, einheit: str, anzahl: int = 1) -> date:
    """Öffentlicher Kalender-Schritt für Konsumenten ohne RRULE-String (Dizz Money):
    ``'monat'``/``'jahr'`` rechnen ECHTE Kalenderschritte (gleicher Tag-im-Monat,
    geklemmt) statt fixer +30/+365-Tage; ``'tag'``/``'woche'`` sind exakt."""
    if einheit == "tag":
        return date.fromordinal(d.toordinal() + anzahl)
    if einheit == "woche":
        return date.fromordinal(d.toordinal() + 7 * anzahl)
    if einheit == "monat":
        return _add_months(d, anzahl)
    if einheit == "jahr":
        return _add_months(d, 12 * anzahl)
    raise ValueError(f"unbekannte Einheit: {einheit!r}")


def _nth_weekday(jahr: int, monat: int, wd: int, ordinal: int) -> date | None:
    """Das ``ordinal``-te Vorkommen von Wochentag ``wd`` im Monat (1…5, -1…-5);
    ``None`` wenn es das im Monat nicht gibt (z. B. 5. Freitag fehlt)."""
    tage_im_monat = calendar.monthrange(jahr, monat)[1]
    treffer = [t for t in range(1, tage_im_monat + 1)
               if date(jahr, monat, t).weekday() == wd]
    idx = ordinal - 1 if ordinal > 0 else ordinal  # -1 ⇒ letzter
    if -len(treffer) <= idx < len(treffer):
        return date(jahr, monat, treffer[idx])
    return None


def _monat_byday_termine(jahr: int, monat: int, regel: dict) -> list[date]:
    """Alle BYDAY-Termine eines Monats (sortiert), gefiltert via ``BYSETPOS``.

    - BYDAY mit Ordinal (``2MO``) ⇒ genau dieses Vorkommen.
    - BYDAY ohne Ordinal (``MO,WE``) ⇒ alle Vorkommen dieser Wochentage; mit
      ``BYSETPOS`` wird daraus die n-te Auswahl gegriffen (RFC 5545: „letzter
      Werktag" = ``BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1``).
    """
    byday = regel["byday"]
    termine: list[date] = []
    for ordinal, wd in byday:
        if ordinal is not None:
            d = _nth_weekday(jahr, monat, wd, ordinal)
            if d:
                termine.append(d)
        else:
            tage_im_monat = calendar.monthrange(jahr, monat)[1]
            termine += [date(jahr, monat, t) for t in range(1, tage_im_monat + 1)
                        if date(jahr, monat, t).weekday() == wd]
    termine = sorted(set(termine))
    setpos = regel.get("bysetpos")
    if setpos and termine:
        idx = setpos - 1 if setpos > 0 else setpos
        termine = [termine[idx]] if -len(termine) <= idx < len(termine) else []
    return termine


def _expandiere_byday(regel: dict, d0: date, suffix: str, *, grenze: int,
                      until: date | None, fenster: date | None) -> list[str]:
    """Expansion für Regeln mit ``BYDAY`` — WEEKLY (mehrere Wochentage je Woche)
    und MONTHLY (n-ter/letzter Wochentag). Block-verankert ⇒ driftfrei."""
    interval = regel["interval"]
    out: list[str] = []

    def schliesst_ab(cur: date) -> bool:
        """True ⇒ Expansion beenden (Grenze überschritten)."""
        return (until is not None and cur > until) or (fenster is not None and cur > fenster)

    if regel["freq"] == "WEEKLY":
        wdays = sorted({wd for _, wd in regel["byday"]})
        woche0 = d0 - timedelta(days=d0.weekday())  # Montag der Start-Woche (WKST=MO)
        block = 0
        while len(out) < grenze and block < _MAX:
            basis = woche0 + timedelta(weeks=interval * block)
            for wd in wdays:
                cur = basis + timedelta(days=wd)
                if cur < d0:
                    continue  # angebrochene erste Woche: vor DTSTART nichts
                if schliesst_ab(cur):
                    return out
                out.append(cur.isoformat() + suffix)
                if len(out) >= grenze:
                    return out
            block += 1
        return out

    # MONTHLY + BYDAY (n-ter Wochentag / BYSETPOS)
    block = 0
    while len(out) < grenze and block < _MAX:
        anker = _add_months(date(d0.year, d0.month, 1), interval * block)
        for cur in _monat_byday_termine(anker.year, anker.month, regel):
            if cur < d0:
                continue
            if schliesst_ab(cur):
                return out
            out.append(cur.isoformat() + suffix)
            if len(out) >= grenze:
                return out
        block += 1
    return out


def expandiere(rrule: str, start: str, *, limit: int = 50, bis: str = "") -> list[str]:
    """Expandiert ``rrule`` ab ``start`` in eine Liste von ISO-Start-Strings.

    - Leere/ungültige Regel ⇒ ``[start]`` (eine einzelne Instanz).
    - ``COUNT`` zählt INKLUSIVE der ersten Instanz (RFC 5545).
    - ``UNTIL`` ist inklusiv; ``bis`` (Aufrufer-Fenster, ``YYYY-MM-DD``) deckelt
      zusätzlich. ``limit`` (1…366) ist die harte Obergrenze.
    - ``BYDAY`` (falls vorhanden) steuert die Wochentage (WEEKLY) bzw. den n-ten
      Wochentag im Monat (MONTHLY).
    - Suffix (Uhrzeit/Zone) des Starts bleibt an jeder Instanz erhalten.
    """
    try:
        d0, suffix = _split_start(start)
    except (ValueError, IndexError):
        return [start]
    regel = parse_rule(rrule)
    if not regel:
        return [start]

    limit = max(1, min(limit, _MAX))
    grenze = min(regel.get("count", limit), limit)
    until = regel.get("until")
    fenster = None
    if bis:
        try:
            fenster = date.fromisoformat(bis[:10])
        except ValueError:
            fenster = None

    if "byday" in regel:
        return _expandiere_byday(regel, d0, suffix, grenze=grenze,
                                 until=until, fenster=fenster)

    # Jede Instanz wird vom ORIGINAL-Start aus berechnet (interval × Schritt),
    # nicht aus der jeweils vorigen — sonst driftet MONTHLY nach einer Klemmung
    # (31. Jan ⇒ Feb 28 ⇒ würde sonst Mär 28 statt Mär 31 ergeben; RFC 5545
    # verankert MONTHLY am DTSTART-Tag).
    out = [d0.isoformat() + suffix]
    schritt = 1
    while len(out) < grenze:
        cur = _add(d0, regel["freq"], regel["interval"] * schritt)
        if until and cur > until:
            break
        if fenster and cur > fenster:
            break
        out.append(cur.isoformat() + suffix)
        schritt += 1
    return out


def naechste_faellig(rrule: str, faellig: str) -> str:
    """Nächster Fälligkeits-Termin NACH ``faellig`` (für wiederkehrende Aufgaben:
    beim Abhaken wird die Folge-Aufgabe um einen Schritt vorgerückt).

    Liefert ``""`` wenn keine/ungültige Regel, kein ``faellig``, oder die Serie
    durch ``UNTIL`` erschöpft ist. ``COUNT`` wird hier bewusst ignoriert (eine
    Aufgabe trägt keinen Lauf-Zähler — die Serie endet via ``UNTIL`` oder manuell).
    """
    regel = parse_rule(rrule)
    if not regel or not faellig.strip():
        return ""
    try:
        d = date.fromisoformat(faellig[:10])
    except ValueError:
        return ""
    until = regel.get("until")

    if "byday" in regel:
        # Vorwärts suchen: erste BYDAY-Instanz ECHT nach ``faellig``. COUNT/​Fenster
        # bewusst ohne Grenze (limit deckelt), UNTIL respektiert.
        ohne_count = {k: v for k, v in regel.items() if k != "count"}
        starts = _expandiere_byday(ohne_count, d, "", grenze=_MAX,
                                   until=until, fenster=None)
        for s in starts:
            if s > faellig[:10]:
                return s
        return ""

    nxt = _add(d, regel["freq"], regel["interval"])
    if until and nxt > until:
        return ""
    return nxt.isoformat()
