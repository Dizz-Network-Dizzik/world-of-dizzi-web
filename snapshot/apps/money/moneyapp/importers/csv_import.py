"""CSV-Import mit tolerantem Spalten-Mapping über Profile (reine Funktionen).

Banken exportieren CSV in vielen Dialekten: Trennzeichen ``,`` oder ``;``,
Beträge DE oder EN, getrennte Soll-/Haben-Spalten oder eine vorzeichenbehaftete
Spalte, deutsche oder englische Kopfzeilen. Statt für jede Bank Spezialcode zu
schreiben, beschreibt ein **Profil** nur, WIE die Spalten heißen — der Parser
ist generisch.

- ``ParseProfil`` nennt die Spalten (Aliase, case-insensitiv) je Feld.
- ``AUTO`` (Default) probiert Dialekt + Spalten selbst zu erkennen; deckt
  Revolut, Klarna und gängige DE-Banken (Sparkasse/DKB/ING/Comdirect-CSV) ab.
- Beträge: entweder eine Spalte ``betrag`` (vorzeichenbehaftet) ODER getrennte
  ``soll``/``haben``-Spalten (Lastschrift/Gutschrift).

Kein Geld-Float: Beträge laufen durch ``common.parse_dezimal`` → Minor-Units.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .common import Bewegung, ImportFehler, parse_datum, parse_dezimal


@dataclass(frozen=True)
class ParseProfil:
    """Beschreibt die Spalten eines CSV-Dialekts (Aliase, case-insensitiv)."""

    name: str
    datum: tuple[str, ...]
    betrag: tuple[str, ...] = ()
    soll: tuple[str, ...] = ()                    # Lastschrift-Spalte (Ausgang)
    haben: tuple[str, ...] = ()                   # Gutschrift-Spalte (Eingang)
    gegenpartei: tuple[str, ...] = ()
    verwendungszweck: tuple[str, ...] = ()
    referenz: tuple[str, ...] = ()
    waehrung: tuple[str, ...] = ()
    waehrung_fix: str = ""                        # M-10: leer statt "EUR" — sonst
    # überschattete der EUR-Default die Konto-Währung (standard_waehrung) und ließ jeden
    # Import auf ein USD-/BTC-Konto ohne Währungsspalte zu 100 % als "EUR≠Konto" scheitern.
    decimal: str = "auto"                         # 'auto' | 'de' | 'en'
    tagerst: bool = True                          # Slash-Datum DE (True) vs US
    delimiter: str = ""                           # "" = automatisch erkennen


# Aliase, die der AUTO-Modus für jedes Feld kennt (DE + EN + Revolut/Klarna).
_AUTO = ParseProfil(
    name="auto",
    datum=("buchungstag", "buchung", "datum", "valuta", "wertstellung",
           "date", "started date", "completed date", "transaction date",
           "booking date", "value date", "purchase date"),
    betrag=("betrag", "amount", "umsatz", "value", "betrag (eur)", "betrag eur"),
    soll=("soll", "lastschrift", "debit", "auszahlung", "out", "paid out (eur)",
          "paid out"),
    haben=("haben", "gutschrift", "credit", "einzahlung", "in", "paid in (eur)",
           "paid in"),
    gegenpartei=("auftraggeber/empfänger", "auftraggeber / empfänger",
                 "beguenstigter/zahlungspflichtiger", "begünstigter/zahlungspflichtiger",
                 "empfänger", "empfaenger", "auftraggeber", "name", "payee",
                 "beneficiary", "zahlungspflichtiger", "begünstigter", "beguenstigter",
                 "counterparty", "gegenkonto", "merchant", "description"),
    verwendungszweck=("verwendungszweck", "buchungstext", "vwz", "reference",
                      "zahlungsreferenz", "type", "details", "notes",
                      "verwendungszweck/zahlungsreferenz", "purpose"),
    referenz=("kundenreferenz", "mandatsreferenz", "transaktions-id",
              "transaction id", "id", "end-to-end", "endtoend", "referenz"),
    waehrung=("währung", "waehrung", "currency", "iso-währung", "orig. currency"),
)

# Benannte Profile, falls AUTO mal nicht trifft (explizit wählbar im Endpoint).
PROFILE: dict[str, ParseProfil] = {
    "auto": _AUTO,
    "revolut": ParseProfil(
        name="revolut", datum=("Completed Date", "Started Date"),
        betrag=("Amount",), gegenpartei=("Description",),
        verwendungszweck=("Type",), referenz=("Type",),
        waehrung=("Currency",), decimal="en", delimiter=","),
    "klarna": ParseProfil(
        name="klarna", datum=("Datum", "Date"),
        betrag=("Betrag", "Amount"), gegenpartei=("Empfänger", "Payee"),
        verwendungszweck=("Verwendungszweck", "Reference"), decimal="auto"),
    "sparkasse_camt": ParseProfil(
        name="sparkasse_camt", datum=("Buchungstag",),
        betrag=("Betrag",),
        gegenpartei=("Beguenstigter/Zahlungspflichtiger", "Begünstigter/Zahlungspflichtiger"),
        verwendungszweck=("Verwendungszweck",),
        referenz=("Kundenreferenz", "Mandatsreferenz"),
        waehrung=("Waehrung", "Währung"), decimal="de", delimiter=";"),
    "dkb": ParseProfil(
        name="dkb", datum=("Buchungsdatum", "Wertstellung"),
        betrag=("Betrag (€)", "Betrag"),
        gegenpartei=("Zahlungsempfänger*in", "Zahlungspflichtige*r", "Name"),
        verwendungszweck=("Verwendungszweck",), decimal="de", delimiter=";"),
}


@dataclass
class _Mapping:
    profil: ParseProfil
    spalten: dict[str, str]                       # feld -> echte Spaltenüberschrift
    decimal: str
    extra: list[str] = field(default_factory=list)


def _sniff_delimiter(text: str, vorgabe: str) -> str:
    if vorgabe:
        return vorgabe
    kopf = text.splitlines()[0] if text.splitlines() else ""
    # Häufigstes der gängigen Trennzeichen in der Kopfzeile gewinnt.
    kandidaten = {d: kopf.count(d) for d in (";", ",", "\t", "|")}
    best = max(kandidaten, key=lambda d: kandidaten[d])
    return best if kandidaten[best] > 0 else ","


def _finde_spalte(kopf: list[str], aliase: tuple[str, ...]) -> str:
    norm = {h.strip().lower(): h for h in kopf}
    for a in aliase:
        if a.strip().lower() in norm:
            return norm[a.strip().lower()]
    return ""


def _mapping(kopf: list[str], profil: ParseProfil) -> _Mapping:
    sp: dict[str, str] = {}
    for feld in ("datum", "betrag", "soll", "haben", "gegenpartei",
                 "verwendungszweck", "referenz", "waehrung"):
        treffer = _finde_spalte(kopf, getattr(profil, feld))
        if treffer:
            sp[feld] = treffer
    if "datum" not in sp:
        raise ImportFehler(
            f"CSV-Profil '{profil.name}': keine Datums-Spalte erkannt "
            f"(Kopf: {kopf}).")
    if "betrag" not in sp and not ("soll" in sp or "haben" in sp):
        raise ImportFehler(
            f"CSV-Profil '{profil.name}': weder Betrags- noch Soll/Haben-Spalte "
            f"erkannt (Kopf: {kopf}).")
    return _Mapping(profil=profil, spalten=sp, decimal=profil.decimal)


def _betrag_minor(zeile: dict[str, str], m: _Mapping, waehrung: str) -> int:
    sp = m.spalten
    if "betrag" in sp:
        roh = zeile.get(sp["betrag"], "")
        if str(roh).strip() == "":
            raise ImportFehler("Leerer Betrag in Betrags-Spalte")
        return parse_dezimal(roh, waehrung)
    # Getrennte Soll/Haben: Haben = Eingang (+), Soll = Ausgang (−).
    haben = zeile.get(sp.get("haben", ""), "") or ""
    soll = zeile.get(sp.get("soll", ""), "") or ""
    if haben.strip():
        return abs(parse_dezimal(haben, waehrung))
    if soll.strip():
        return -abs(parse_dezimal(soll, waehrung))
    raise ImportFehler("Zeile ohne Soll- und Haben-Betrag")


def parse_csv(inhalt: str, profil: str | ParseProfil = "auto",
              standard_waehrung: str = "EUR") -> list[Bewegung]:
    """CSV-Text → Liste von ``Bewegung``. Fehlerhafte EINZELzeilen werden
    übersprungen (Auszüge enthalten oft Saldo-/Kopf-Zeilen); ist KEINE Zeile
    lesbar, wirft die Funktion (echtes Format-/Profil-Problem)."""
    p = profil if isinstance(profil, ParseProfil) else PROFILE.get(str(profil).lower())
    if p is None:
        raise ImportFehler(f"Unbekanntes CSV-Profil: {profil!r} "
                           f"(bekannt: {sorted(PROFILE)})")
    text = inhalt.lstrip("﻿")                # BOM entfernen
    if not text.strip():
        raise ImportFehler("Leere CSV-Eingabe")
    delim = _sniff_delimiter(text, p.delimiter)
    leser = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        zeilen = [z for z in leser if any(c.strip() for c in z)]
    except csv.Error as e:                    # AT-2: Feld zu groß / kaputtes Quoting → 400 statt 500
        raise ImportFehler(f"CSV nicht lesbar ({e})")
    if len(zeilen) < 2:
        raise ImportFehler("CSV ohne Datenzeilen")
    kopf = [c.strip() for c in zeilen[0]]
    m = _mapping(kopf, p)

    bewegungen: list[Bewegung] = []
    fehler = 0
    for roh in zeilen[1:]:
        zeile = {kopf[i]: (roh[i] if i < len(roh) else "")
                 for i in range(len(kopf))}
        try:
            waehrung = (zeile.get(m.spalten.get("waehrung", ""), "").strip()
                        or p.waehrung_fix or standard_waehrung).upper()
            betrag = _betrag_minor(zeile, m, waehrung)
            datum = parse_datum(zeile.get(m.spalten["datum"], ""), tagerst=p.tagerst)
            bewegungen.append(Bewegung(
                datum=datum, betrag_minor=betrag, waehrung=waehrung,
                gegenpartei=zeile.get(m.spalten.get("gegenpartei", ""), "").strip(),
                verwendungszweck=zeile.get(m.spalten.get("verwendungszweck", ""), "").strip(),
                referenz=zeile.get(m.spalten.get("referenz", ""), "").strip(),
                roh=zeile))
        except ImportFehler:
            fehler += 1
            continue
    if not bewegungen:
        raise ImportFehler(
            f"CSV-Profil '{p.name}': keine Zeile lesbar ({fehler} Fehler) — "
            "falsches Profil/Trennzeichen?")
    return bewegungen
