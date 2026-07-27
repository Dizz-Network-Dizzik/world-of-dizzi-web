"""Wiederkehrende Posten — Abos/Daueraufträge erkennen + planen (reine Logik).

Idee: Aus der Buchungshistorie tauchen regelmäßige Posten als Muster auf — gleiche
Gegenpartei, ähnlicher Betrag, regelmäßiger Abstand (Netflix monatlich, Miete
monatlich, Versicherung jährlich …). Dieses Modul **erkennt** solche Serien und
**plant** ihre nächsten Fälligkeiten voraus.

Reine Funktionen, kein DB/HTTP — voll testbar und deterministisch:
- ``erkenne_serien(buchungen, heute)`` → Kandidaten mit Intervall + Konfidenz.
- ``plane(serien, von, bis)`` → erwartete Fälligkeiten im Zeitfenster.
- ``monatsbelastung(serien)`` → auf den Monat normierte Fixkosten/-einnahmen.

Gegen Fehlalarm (z. B. „REWE" = unregelmäßige Einkäufe, KEIN Abo): die Konfidenz
verlangt SOWOHL einen regelmäßigen Abstand ALS AUCH einen stabilen Betrag; nur
Kandidaten über einer Schwelle gelten als Serie. Geld bleibt Minor-Units."""

from __future__ import annotations

import re
import statistics
from datetime import date, timedelta
from typing import Iterable, Optional

from appkit.recurrence import expandiere, schritt_kalender

# Nominal-Abstände der benannten Intervalle (Tage) — für die Etikettierung.
INTERVALLE: dict[str, int] = {
    "woechentlich": 7, "zweiwoechentlich": 14, "monatlich": 30,
    "vierteljaehrlich": 91, "halbjaehrlich": 182, "jaehrlich": 365,
}
# Kalender-benannte Intervalle → ECHTER Kalenderschritt (Einheit, Anzahl) für die
# Fälligkeits-VORHERSAGE (docs/50 P2.2b): monatlich/quartal/halbjahr/jährlich
# schreiten gleichen Tag-im-Monat (geklemmt) statt fixer +30/+91/+182/+365 Tage —
# so driftet eine Monatsserie nicht (1. Jan → 1. Feb, nicht 31. Jan; 31. Jan →
# 28. Feb). Tages-Serien (wöchentlich/14-tägig/unbenannt) bleiben tagesgenau.
_KALENDER_SCHRITT: dict[str, tuple[str, int]] = {
    "monatlich": ("monat", 1), "vierteljaehrlich": ("monat", 3),
    "halbjaehrlich": ("monat", 6), "jaehrlich": ("jahr", 1),
}
# … und als RRULE für die MEHRSCHRITT-Vorhersage (plane): der geteilte recurrence-
# Kern expandiert DTSTART-verankert ⇒ driftfrei AUCH nach einer Tag-Klemmung
# (31. Jan monatlich ⇒ 28. Feb, dann wieder 31. Mär — nicht 28. Mär). „jährlich"
# = MONTHLY;INTERVAL=12 (recurrence kennt kein YEARLY, mathematisch identisch).
_RRULE_FUER_LABEL: dict[str, str] = {
    "monatlich": "FREQ=MONTHLY", "vierteljaehrlich": "FREQ=MONTHLY;INTERVAL=3",
    "halbjaehrlich": "FREQ=MONTHLY;INTERVAL=6", "jaehrlich": "FREQ=MONTHLY;INTERVAL=12",
}
MIN_TREFFER = 3
KONFIDENZ_SCHWELLE = 0.55


def _serie_faelligkeiten(s: dict, von_d: date, bis_d: date, max_pro_serie: int) -> list[date]:
    """Erwartete Fälligkeiten EINER Serie im Fenster [von_d, bis_d] (sortiert).

    Kalender-benanntes Intervall ⇒ DTSTART-verankerte Monats-/Jahres-Expansion
    über den geteilten ``recurrence``-Kern (driftfrei). Sonst (wöchentlich/
    14-tägig/unbenannt) der gemessene Tages-Schritt — Verhalten 1:1."""
    start = s.get("naechste_faelligkeit") or s.get("naechste_faellig")
    if not start:
        return []
    rrule = _RRULE_FUER_LABEL.get(s.get("intervall") or "")
    if rrule:
        roh = expandiere(rrule, str(start)[:10], limit=max_pro_serie, bis=bis_d.isoformat())
        kandidaten = [date.fromisoformat(x) for x in roh]
    else:
        schritt = int(s.get("intervall_tage", 30)) or 30
        kandidaten, d = [], _d(start)
        while d <= bis_d and len(kandidaten) < max_pro_serie:
            kandidaten.append(d)
            d += timedelta(days=schritt)
    return [d for d in kandidaten if von_d <= d <= bis_d]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _schluessel(b: dict) -> str:
    """Gruppierungs-Schlüssel einer Buchung: Gegenpartei bevorzugt, sonst die
    ersten markanten Wörter des Verwendungszwecks (stabiles Merkmal eines Abos)."""
    gp = _norm(b.get("gegenpartei", ""))
    if gp:
        return gp
    vz = _norm(b.get("verwendungszweck", ""))
    return " ".join(vz.split()[:3])


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _label(median_gap: float) -> str:
    """Nächstgelegenes benanntes Intervall zum gemessenen Median-Abstand."""
    return min(INTERVALLE, key=lambda name: abs(INTERVALLE[name] - median_gap))


def erkenne_serien(buchungen: Iterable[dict], heute: Optional[str] = None,
                   min_treffer: int = MIN_TREFFER) -> list[dict]:
    """Erkennt wiederkehrende Serien aus ``buchungen`` (je: ``datum`` YYYY-MM-DD,
    ``betrag`` netto-Minor-Units signiert, ``gegenpartei``, ``verwendungszweck``,
    optional ``kategorie_id``/``kategorie_name``).

    Liefert Kandidaten (deterministisch nach Konfidenz, dann Betrag sortiert):
    ``schluessel``, ``name``, ``betrag`` (Median, signiert), ``richtung``,
    ``intervall`` (Label), ``intervall_tage`` (gemessen), ``anzahl``, ``erste``,
    ``letzte``, ``naechste_faellig``, ``konfidenz`` (0..1)."""
    heute_d = _d(heute) if heute else date.today()
    gruppen: dict[tuple[str, int], list[dict]] = {}
    for b in buchungen:
        netto = int(b.get("betrag", 0))
        if netto == 0:
            continue
        key = _schluessel(b)
        if not key:
            continue
        gruppen.setdefault((key, 1 if netto > 0 else -1), []).append(b)

    serien: list[dict] = []
    for (key, vz), gruppe in gruppen.items():
        if len(gruppe) < min_treffer:
            continue
        gruppe = sorted(gruppe, key=lambda b: b["datum"][:10])
        tage = [_d(b["datum"]) for b in gruppe]
        gaps = [(tage[i] - tage[i - 1]).days for i in range(1, len(tage))]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        median_gap = statistics.median(gaps)
        if median_gap <= 0:
            continue
        betraege = [int(b["betrag"]) for b in gruppe]
        median_betrag = int(round(statistics.median(betraege)))

        # Konfidenz: Abstands-Regelmäßigkeit + Betrags-Stabilität + Häufigkeit.
        gap_streu = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
        regel = max(0.0, 1.0 - gap_streu / median_gap)
        betr_streu = statistics.pstdev(betraege) if len(betraege) > 1 else 0.0
        mittel = statistics.mean(abs(x) for x in betraege) or 1
        stabil = max(0.0, 1.0 - betr_streu / mittel)
        haeufig = min(1.0, len(gruppe) / 6.0)
        konfidenz = round(0.45 * regel + 0.35 * stabil + 0.20 * haeufig, 2)
        if konfidenz < KONFIDENZ_SCHWELLE:
            continue

        intervall_tage = int(round(median_gap))
        label = _label(median_gap)
        letzte = tage[-1]
        # Kalender-bewusste nächste Fälligkeit — ANKER-verankert an ``letzte`` (MR-1,
        # 28.06.): der n-te Schritt wird stets VOM ANKER gerechnet, nicht iterativ vom
        # Vorgänger. Sonst driftet eine Monatsserie nach einer Februar-Klemmung dauerhaft
        # (31. Jan ⇒ 29. Feb ⇒ iterativ fälschlich 29. Mär statt 31. Mär). Damit konsistent
        # mit _serie_faelligkeiten/recurrence.expandiere (driftfrei). Tages-Serien exakt.
        kal = _KALENDER_SCHRITT.get(label or "")
        _tage = int(intervall_tage) or 30

        def _nth_faellig(n: int) -> date:
            if kal:
                return schritt_kalender(letzte, kal[0], kal[1] * n)
            return letzte + timedelta(days=_tage * n)

        n = 1
        naechste = _nth_faellig(n)
        while naechste < heute_d:          # auf das nächste zukünftige Vielfache schieben
            n += 1
            naechste = _nth_faellig(n)
        muster = next((b for b in gruppe if b.get("gegenpartei")), gruppe[-1])
        serien.append({
            "schluessel": key, "name": muster.get("gegenpartei") or key.title(),
            "betrag": median_betrag, "richtung": "einnahme" if vz > 0 else "ausgabe",
            "intervall": label, "intervall_tage": intervall_tage,
            "anzahl": len(gruppe), "erste": tage[0].isoformat(),
            "letzte": letzte.isoformat(), "naechste_faellig": naechste.isoformat(),
            "kategorie_id": muster.get("kategorie_id"),
            "kategorie_name": muster.get("kategorie_name"),
            "konfidenz": konfidenz})
    serien.sort(key=lambda s: (-s["konfidenz"], -abs(s["betrag"])))
    return serien


def plane(serien: Iterable[dict], von: str, bis: str,
          max_pro_serie: int = 60) -> dict:
    """Vorausschau: erwartete Fälligkeiten aller ``serien`` im Fenster [von, bis].

    Jede Serie (``betrag``, ``intervall_tage``, ``naechste_faelligkeit``/
    ``naechste_faellig``, ``name``) wird ab ihrer nächsten Fälligkeit in
    Intervall-Schritten expandiert. Liefert die Termine (nach Datum sortiert) +
    Summen (Einnahmen/Ausgaben/Saldo) über das Fenster."""
    von_d, bis_d = _d(von), _d(bis)
    termine: list[dict] = []
    einnahmen = ausgaben = 0
    for s in serien:
        betrag = int(s.get("betrag", 0))
        for d in _serie_faelligkeiten(s, von_d, bis_d, max_pro_serie):
            termine.append({"datum": d.isoformat(), "name": s.get("name", "?"),
                            "betrag": betrag, "schluessel": s.get("schluessel", ""),
                            "richtung": s.get("richtung",
                                              "einnahme" if betrag > 0 else "ausgabe")})
            if betrag > 0:
                einnahmen += betrag
            else:
                ausgaben += -betrag
    termine.sort(key=lambda t: (t["datum"], t["name"]))
    return {"von": von, "bis": bis, "termine": termine,
            "einnahmen": einnahmen, "ausgaben": ausgaben,
            "saldo": einnahmen - ausgaben}


def monatsbelastung(serien: Iterable[dict]) -> dict:
    """Auf EINEN Monat normierte Fixposten: jede Serie wird mit 30/Intervall-Tage
    auf eine Monatsrate umgerechnet (ganzzahlig). Liefert Einnahmen/Ausgaben/
    Saldo je Monat — die „Fixkosten-Grundlast" für Budget/Cashflow-Planung."""
    einnahmen = ausgaben = 0
    for s in serien:
        schritt = int(s.get("intervall_tage", 30)) or 30
        rate = int(round(int(s.get("betrag", 0)) * 30 / schritt))
        if rate > 0:
            einnahmen += rate
        else:
            ausgaben += -rate
    return {"einnahmen": einnahmen, "ausgaben": ausgaben,
            "saldo": einnahmen - ausgaben}
