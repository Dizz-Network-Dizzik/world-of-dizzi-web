"""Tests der Import-Grundlagen: Betrag-/Datum-Parser + Dedupe-Hash.

PROPERTY-Tests, weil die Parser an der RÄNDER zwischen unsicherer Eingabe und
dem exakten Ledger stehen — hier darf kein Cent verloren gehen und kein Float
durchrutschen."""

from __future__ import annotations

import random

import pytest

from moneyapp.importers.common import (Bewegung, ImportFehler, bewegung_hash,
                                       parse_datum, parse_dezimal)
from moneyapp.ledger import format_betrag


# ------------------------------------------------------------- Betrag (DE/EN)

@pytest.mark.parametrize("text,erwartet", [
    ("1.234,56", 123456), ("1,234.56", 123456),     # DE vs EN, gleiche Zahl
    ("-825,50", -82550), ("825.50", 82550),
    ("1.000,00", 100000), ("1,000.00", 100000),
    ("12,34", 1234), ("12.34", 1234),
    ("1,5", 150), ("1.5", 150),
    ("1,234", 123400), ("1.234", 123400),            # reine Tausender (kein Dezimal)
    ("0,00", 0), ("(1,23)", -123),                   # Klammer = negativ
    ("+99,00", 9900), ("99 €", 9900), ("1.234,56 EUR", 123456),
    ("9.999.999,99", 999999999),
])
def test_parse_dezimal_de_en(text, erwartet):
    assert parse_dezimal(text, "EUR") == erwartet


def test_parse_dezimal_typen_und_unfug():
    assert parse_dezimal(12.5, "EUR") == 1250
    assert parse_dezimal(100, "EUR") == 10000
    for schlecht in ("", "abc", True, float("inf")):
        with pytest.raises(ImportFehler):
            parse_dezimal(schlecht)


def test_parse_dezimal_property_round_trip():
    """Property: format_betrag(parse_dezimal(x)) == x für viele DE-Strings."""
    rng = random.Random(2026)
    for _ in range(2000):
        cent = rng.randint(0, 9_999_999)
        euro, rest = divmod(cent, 100)
        de = f"{euro:,}".replace(",", ".") + f",{rest:02d}"   # 1.234.567,89
        assert parse_dezimal(de, "EUR") == cent
        # und das Ergebnis ist exakt wie der Ledger formatiert (Punkt-Notation)
        assert format_betrag(parse_dezimal(de, "EUR"), "EUR") == f"{euro}.{rest:02d}"


# --------------------------------------------------------------------- Datum

@pytest.mark.parametrize("text,iso", [
    ("2025-12-31", "2025-12-31"), ("31.12.2025", "2025-12-31"),
    ("31.12.25", "2025-12-31"), ("2025-12-31T09:00:00", "2025-12-31"),
    ("251231", "2025-12-31"), ("01/02/2026", "2026-02-01"),    # tagerst (DE)
])
def test_parse_datum(text, iso):
    assert parse_datum(text) == iso


def test_parse_datum_us_reihenfolge():
    assert parse_datum("12/31/2025", tagerst=False) == "2025-12-31"
    # eindeutig vertauscht (Monat>12) wird auch bei tagerst korrigiert
    assert parse_datum("12/31/2025", tagerst=True) == "2025-12-31"


def test_parse_datum_fehler():
    for schlecht in ("", "kein-datum", "31.13.2025", "2025-02-30"):
        with pytest.raises(ImportFehler):
            parse_datum(schlecht)


# ---------------------------------------------------------------- Dedupe-Hash

def test_hash_stabil_und_referenz_eindeutig():
    a = Bewegung("2026-01-02", -82550, "EUR", "Hausverwaltung", "Miete", "REF1")
    b = Bewegung("2026-01-02", -82550, "EUR", "Hausverwaltung", "Miete", "REF1")
    c = Bewegung("2026-01-02", -82550, "EUR", "Hausverwaltung", "Miete", "REF2")
    assert a.hash == b.hash                       # identisch ⇒ gleicher Hash
    assert a.hash != c.hash                       # andere Referenz ⇒ anderer Hash


def test_hash_ignoriert_whitespace_und_case():
    a = Bewegung("2026-01-02", 100, "EUR", "REWE  Markt", "Lebensmittel")
    b = Bewegung("2026-01-02", 100, "EUR", "rewe markt", "  lebensmittel ")
    assert bewegung_hash(a) == bewegung_hash(b)


def test_bewegung_validiert():
    with pytest.raises(ImportFehler):
        Bewegung("2026-1-2", 100)                 # Datum nicht ISO
    with pytest.raises(ImportFehler):
        Bewegung("2026-01-02", 1.5)               # kein int
    with pytest.raises(ImportFehler):
        Bewegung("2026-01-02", True)              # bool verboten
