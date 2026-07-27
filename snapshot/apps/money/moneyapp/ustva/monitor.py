"""§19-Kleinunternehmer-Monitor — Gesamtumsatz + Schwellen-Wächter + Regime-Schnitt
(M4-2, docs/68 §6/§11). KEINE echte UStVA, KEINE Steuer-BERATUNG.

Die Mess-/Warn-Schicht UNTER dem Vertrag (``vertrag.py`` bleibt normativ +
UNANGETASTET — genau wie ``persistenz.py`` unter M4-1). Der Vertrag liefert die
§19-WEICHE (``pruefe_kleinunternehmer``, ``schwellen_fuer``, ``StatusBefund``) und
die Kategorien; dieses Modul liefert das, was der Vertrag der Bau-Stufe M4-2
ausdrücklich überlässt (Docstring ``pruefe_kleinunternehmer``: „den präzisen
Schnitt am Ledger-Datum baut M4-2"):

  * ``gesamtumsatz_cent`` — die vereinnahmten Entgelte (§19 Abs. 2) aus
    KLASSIFIZIERTEN Summen (reine Funktion; Kapitalerträge/Trading = KEIN_UMSATZ
    zählen NIE — docs/68 §6),
  * ``GESAMTUMSATZ_KATEGORIEN`` — die **Abgrenzungsliste** (VERIFY erledigt, s. u.),
  * ``warnstufe`` — die 80 %/100 %-Ampel (Warnung VOR Überschreiten),
  * ``regime_schnitt`` — der unterjährige 100k-Zwangswechsel (Jahr in zwei
    Regime-Fenster; der überschreitende Umsatz selbst ist bereits steuerpflichtig).

REINE LOGIK: kein DB-Zugriff, kein FastAPI, keine Ledger-Berührung (U-4). Die
Orchestrierung (Bewegungen über die injizierte Naht lesen, Status persistieren,
HTTP) liegt in ``persistenz.py``. Schwellen kommen IMMER aus der Jahres-Tabelle
``schwellen_fuer`` (U-2) — nie eine Code-Konstante hier.
"""

from __future__ import annotations

import enum
from datetime import date, timedelta
from typing import Iterable, Mapping

from .vertrag import (
    Klassifikation,
    KlassifikationsRegel,
    KlassifikationUnklar,
    KonfigFehler,
    UStKategorie,
    klassifiziere,
)

# ---------------------------------------------------------- Abgrenzung Gesamtumsatz

#: ★ ABGRENZUNGSLISTE Gesamtumsatz (§19 Abs. 2 UStG; die „VERIFY erledigt"-Aufgabe
#: aus docs/68 §11 M4-2). Der Gesamtumsatz misst die im Inland STEUERBAREN Umsätze
#: (§1 Abs. 1 Nr. 1) nach VEREINNAHMTEN Entgelten. Aufgenommen sind die
#: Ausgangs-Umsätze, die steuerbar sind (steuerpflichtig ODER steuerfrei, mit oder
#: ohne Vorsteuerabzug). BEWUSST NICHT aufgenommen:
#:
#:   * ``KEIN_UMSATZ`` — kein Leistungsaustausch (Privateinlage/-entnahme,
#:     Trading/Kapitalertrag §20/§23, Steuerzahlungen ans FA, durchlaufende
#:     Posten); docs/68 §6 nennt das ausdrücklich („zählen NIE"),
#:   * die gesamte EINGANGS-/ERWERBS-Seite (``ERWERB_IG_*``, ``BEZUG_13B``,
#:     ``EINGANG_*``) — das sind BEZOGENE Leistungen, kein eigener Umsatz,
#:   * ``UMSATZ_EU_B2B`` / ``UMSATZ_NICHT_STEUERBAR`` — NICHT steuerbare Umsätze
#:     (Leistungsort Ausland u. a.) gehören definitionsgemäß nicht zum
#:     Gesamtumsatz nach §1 Abs. 1 Nr. 1 — das ist Systematik, kein „Zweifel".
#:
#: KONSERVATIV (docs/68 §6 „im Zweifel MITZÄHLEN", der zulässige Fehler zeigt
#: Richtung Regelbesteuerung/UStVA, nie Richtung „fälschlich keine Erklärung"):
#: ``UMSATZ_STFREI_OHNE_VST`` wird VOLL mitgezählt, obwohl §19 Abs. 2 einzelne
#: steuerfreie Umsätze wieder herausnimmt (§4 Nr. 8i, 9b, 11–29) und Verkäufe von
#: Anlagevermögen kürzt — beides würde den Gesamtumsatz nur SENKEN. Diese
#: Feinabgrenzung (die die geschlossene Kategorie ohnehin nicht auflösen kann)
#: bleibt eine bewusste VERIFY-Verfeinerung; die konservative Richtung (eher
#: Regelbesteuerung warnen) ist gewahrt.
GESAMTUMSATZ_KATEGORIEN: frozenset[UStKategorie] = frozenset({
    UStKategorie.UMSATZ_19,
    UStKategorie.UMSATZ_7,
    UStKategorie.UMSATZ_STFREI_MIT_VST,
    UStKategorie.UMSATZ_IG_LIEFERUNG,
    UStKategorie.UMSATZ_STFREI_OHNE_VST,
    UStKategorie.UMSATZ_13B_LEISTENDER,
})


def entgelt_cent(klass: Klassifikation, buchung_netto_cent: int) -> int:
    """Das VEREINNAHMTE Entgelt einer klassifizierten Buchung fürs Gesamtumsatz-Maß
    (§19 Abs. 2), vorzeichenrichtig. Betrag = Split-Netto (bei MIT_SPLIT-Umsätzen
    das Entgelt OHNE USt — für einen Regelbesteuerer die richtige Vergleichszahl
    zum §19-Maß) sonst der volle Zufluss (kein USt-Ausweis ⇒ Brutto = Entgelt);
    das Vorzeichen trägt der Ledger-Netto, damit Entgeltminderungen/Stornos den
    Gesamtumsatz mindern. Kategorien außerhalb der Abgrenzungsliste liefern 0
    (Eingangsseite/KEIN_UMSATZ zählen nie)."""
    if klass.ust_kategorie not in GESAMTUMSATZ_KATEGORIEN:
        return 0
    betrag = klass.split.netto_cent if klass.split is not None else abs(int(buchung_netto_cent))
    return betrag if int(buchung_netto_cent) >= 0 else -betrag


def gesamtumsatz_cent(posten: Iterable[tuple[UStKategorie, int]]) -> int:
    """Der Gesamtumsatz (§19 Abs. 2) aus KLASSIFIZIERTEN Summen — die reine
    Funktion aus docs/68 §6. ``posten`` = Iterable von (UStKategorie,
    entgelt_cent); summiert wird NUR über die Abgrenzungsliste (alles andere
    zählt nicht mit, insbesondere KEIN_UMSATZ/Trading und die Eingangsseite)."""
    return sum(e for kat, e in posten if kat in GESAMTUMSATZ_KATEGORIEN)


def umsatz_posten(bewegungen: Iterable[Mapping],
                  regeln: Mapping[str, KlassifikationsRegel],
                  overrides: Mapping[str, Klassifikation] | None = None
                  ) -> tuple[list[tuple[str, UStKategorie, int]], int]:
    """Brücke Bewegungen → Gesamtumsatz-Posten: klassifiziert jede Bewegung über
    den Vertrags-Lookup ``klassifiziere`` (Override → Regel → sonst offen) und
    liefert (Posten, offen_anzahl). Posten = (datum, UStKategorie, entgelt_cent)
    NUR für Abgrenzungs-Kategorien; ``offen_anzahl`` = Buchungen ohne eindeutige
    Klassifikation (Ehrlichkeit: der gemessene Gesamtumsatz ist „mindestens X,
    solange Y Buchungen offen sind" — kein stilles Weglassen).

    Reine Funktion über die (bereits vom Ledger gelesenen) Bewegungen — kein
    Ledger-Zugriff, keine Kurs-Kopie, keine Mutation (U-4)."""
    posten: list[tuple[str, UStKategorie, int]] = []
    offen = 0
    for b in bewegungen:
        try:
            k = klassifiziere(b, regeln, overrides)
        except KlassifikationUnklar:
            offen += 1
            continue
        if k.ust_kategorie in GESAMTUMSATZ_KATEGORIEN:
            e = entgelt_cent(k, int(b.get("netto", 0) or 0))
            posten.append((str(b.get("datum", "") or "")[:10], k.ust_kategorie, e))
    return posten, offen


# ------------------------------------------------------------------ Warn-Stufen

#: Warnung ab 80 % der Grenze — VOR dem Überschreiten (docs/68 §11 M4-2).
WARN_ANTEIL = 0.8


class Ampel(str, enum.Enum):
    """Warn-Ampel einer Schwelle."""
    GRUEN = "gruen"     # < 80 % der Grenze
    GELB = "gelb"       # 80 % … < 100 % — die Warnung VOR dem Überschreiten
    ROT = "rot"         # >= 100 % — überschritten (100k wirkt dann HART unterjährig)


def warnstufe(wert_cent: int, grenze_cent: int) -> dict:
    """Die 80 %/100 %-Ampel einer §19-Schwelle (Warnung VOR Überschreiten,
    docs/68 §11). ``grenze_cent`` kommt IMMER aus ``schwellen_fuer`` (U-2) — nie
    eine Code-Konstante. ``wert >= grenze`` ⇒ ROT (überschritten); ab 80 % ⇒ GELB
    (die eigentliche Warnung); darunter GRÜN. ``grenze <= 0`` ⇒ ``KonfigFehler``
    (keine sinnvolle Quote — schützt vor einer leeren/kaputten Schwellen-Zeile)."""
    if grenze_cent <= 0:
        raise KonfigFehler("warnstufe: Grenze muss > 0 sein (Schwellen-Tabelle, U-2)")
    anteil = wert_cent / grenze_cent
    if wert_cent >= grenze_cent:
        ampel = Ampel.ROT
    elif anteil >= WARN_ANTEIL:
        ampel = Ampel.GELB
    else:
        ampel = Ampel.GRUEN
    return {
        "wert_cent": int(wert_cent),
        "grenze_cent": int(grenze_cent),
        "anteil_prozent": round(anteil * 100, 1),
        "ampel": ampel.value,
        "warnung": ampel is not Ampel.GRUEN,
        "ueberschritten": ampel is Ampel.ROT,
    }


_AMPEL_RANG = {Ampel.GRUEN.value: 0, Ampel.GELB.value: 1, Ampel.ROT.value: 2}


def schlimmste_ampel(*stufen: dict) -> str:
    """Die dringlichste Ampel über mehrere ``warnstufe``-Ergebnisse (die
    Gesamt-Ampel der §19-Karte). Leere Eingabe ⇒ GRÜN."""
    schlimm = Ampel.GRUEN.value
    for s in stufen:
        if _AMPEL_RANG.get(s.get("ampel", ""), 0) > _AMPEL_RANG[schlimm]:
            schlimm = s["ampel"]
    return schlimm


# --------------------------------------------------------------- Regime-Schnitt

def _vortag(datum_iso: str) -> str:
    """ISO-Vortag (rein rechnerisch, kein §108-AO-Werktags-Bezug)."""
    return (date.fromisoformat(datum_iso[:10]) - timedelta(days=1)).isoformat()


def regime_schnitt(jahr: int, posten: Iterable[tuple[str, UStKategorie, int]],
                   laufend_max_cent: int) -> dict:
    """Der unterjährige 100k-Zwangswechsel (docs/68 §6, JStG-2024-Recht): sobald
    der KUMULIERTE Gesamtumsatz des Jahres die laufende Grenze ÜBERSCHREITET,
    teilt sich das Jahr in zwei Regime-Fenster —

      * ``kleinunternehmer_fenster`` = 01.01. bis zum VORTAG des überschreitenden
        Umsatzes (§19, steuerfrei),
      * ``regelbesteuerung_fenster`` = AB dem überschreitenden Umsatz
        (EINSCHLIESSLICH!) bis 31.12. — „bereits der überschreitende Umsatz ist
        steuerpflichtig" (kein Prognose-Modell mehr).

    ``posten`` = (datum_iso, UStKategorie, entgelt_cent); nur Abgrenzungs-
    Kategorien zählen, sortiert nach Datum. **TAGES-Granularität:** der Ledger
    führt kein Intraday-Ordering ⇒ ALLE Umsätze des Schnitt-Tages fallen ins
    Regel-Fenster (die konservative Richtung — im Zweifel steuerpflichtig).
    ``laufend_max_cent`` kommt aus ``schwellen_fuer`` (U-2). Kein Schnitt ⇒ das
    ganze Jahr ist EIN Regime-Fenster (Kleinunternehmer)."""
    relevante = sorted(((d, e) for d, kat, e in posten
                        if kat in GESAMTUMSATZ_KATEGORIEN and d),
                       key=lambda t: t[0])
    kum = 0
    schnitt = ""
    for d, e in relevante:
        kum += e
        if kum > laufend_max_cent:
            schnitt = d
            break
    jahr_von, jahr_bis = f"{int(jahr):04d}-01-01", f"{int(jahr):04d}-12-31"
    if not schnitt:
        return {
            "ueberschritten": False,
            "schnitt_datum": "",
            "kleinunternehmer_fenster": [jahr_von, jahr_bis],
            "regelbesteuerung_fenster": None,
            "kumuliert_cent": kum,
        }
    vortag = _vortag(schnitt)
    ku_fenster = [jahr_von, vortag] if vortag >= jahr_von else None
    return {
        "ueberschritten": True,
        "schnitt_datum": schnitt,
        "kleinunternehmer_fenster": ku_fenster,
        "regelbesteuerung_fenster": [schnitt, jahr_bis],
        "kumuliert_cent": kum,
    }
