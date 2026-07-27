"""Tests der drei Format-Parser an echten Musterdateien (Fixtures) + Dispatch.

Die drei Wege CSV / camt.053 / MT940 bilden DENSELBEN Auszug ab (Gehalt, Miete,
REWE) — am Ende muss jeder dieselben Bewegungen mit gleichen Beträgen und
gleichem Vorzeichen liefern. Das prüft die Vorzeichen-/Richtungs-Logik aller
drei Parser gegeneinander."""

from __future__ import annotations

from pathlib import Path

import pytest

from moneyapp.importers import parse_inhalt
from moneyapp.importers.csv_import import parse_csv
from moneyapp.importers.camt import parse_camt
from moneyapp.importers.mt940 import parse_mt940
from moneyapp.importers.dispatch import erkenne_format

FIX = Path(__file__).resolve().parent / "fixtures"


def _lies(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# ------------------------------------------------------------------------ CSV

def test_csv_sparkasse_einzelbetrag():
    bs = parse_csv(_lies("sparkasse.csv"), profil="auto")
    assert len(bs) == 4
    lohn = bs[0]
    assert lohn.datum == "2025-12-31" and lohn.betrag_minor == 245000
    assert lohn.gegenpartei == "Muster GmbH" and "Gehalt" in lohn.verwendungszweck
    assert lohn.referenz == "E2E-2025-0001"
    miete = bs[1]
    assert miete.betrag_minor == -82550               # Ausgang negativ
    assert bs[3].betrag_minor == 123456               # Steuererstattung +


def test_csv_revolut_en_dezimal():
    bs = parse_csv(_lies("revolut.csv"), profil="auto")
    assert len(bs) == 4
    spotify = bs[0]
    assert spotify.betrag_minor == -999 and spotify.waehrung == "EUR"
    assert bs[1].betrag_minor == 25000                # Top-Up +
    assert bs[2].betrag_minor == -123450              # 1,234.50 EN-Notation


def test_csv_soll_haben_spalten():
    bs = parse_csv(_lies("giro_sollhaben.csv"), profil="auto")
    assert [b.betrag_minor for b in bs] == [-7500, 100000, -1234]
    assert bs[1].gegenpartei == "Arbeitgeber AG"


def test_csv_fehlende_spalte_wirft():
    with pytest.raises(Exception):
        parse_csv("a;b;c\n1;2;3", profil="auto")       # keine Datums-/Betragsspalte


# -------------------------------------------------------------------- camt.053

def test_camt_richtung_und_referenz():
    bs = parse_camt(_lies("statement.camt053.xml"))
    assert len(bs) == 3
    assert bs[0].betrag_minor == 245000 and bs[0].gegenpartei == "Muster GmbH"
    assert bs[0].referenz == "E2E-2025-0001"
    assert bs[1].betrag_minor == -82550               # DBIT
    assert bs[1].verwendungszweck == "Miete Januar Wohnung 4"
    # NOTPROVIDED-EndToEnd wird übersprungen → AcctSvcrRef greift
    assert bs[2].referenz == "ASR-1042"


def test_camt_entity_bombe_abgewehrt():
    """P4.1 (geld-kritisch): eine camt-XML mit DTD/Entity (Billion-Laughs/XXE)
    wird als ImportFehler abgewiesen — NICHT expandiert. Gültige camt parst weiter
    (Regression: der Fixture-Auszug bleibt korrekt lesbar)."""
    from moneyapp.importers.common import ImportFehler
    bombe = ('<?xml version="1.0"?>'
             '<!DOCTYPE x [<!ENTITY a "AAAAAAAAAA">'
             '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
             '<Document><Ntry><Amt Ccy="EUR">&b;</Amt>'
             '<CdtDbtInd>CRDT</CdtDbtInd></Ntry></Document>')
    with pytest.raises(ImportFehler):
        parse_camt(bombe)
    # externe Entität (XXE) ebenso
    xxe = ('<?xml version="1.0"?>'
           '<!DOCTYPE d [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
           '<Document><Ntry><Amt Ccy="EUR">1.00</Amt>'
           '<CdtDbtInd>CRDT</CdtDbtInd></Ntry></Document>')
    with pytest.raises(ImportFehler):
        parse_camt(xxe)
    # Regression: gültige camt.053 weiterhin korrekt
    assert len(parse_camt(_lies("statement.camt053.xml"))) == 3


# ---------------------------------------------------------------------- MT940

def test_mt940_felder_und_vorzeichen():
    bs = parse_mt940(_lies("auszug.mt940.sta"))
    assert len(bs) == 3
    assert bs[0].betrag_minor == 245000 and bs[0].datum == "2025-12-31"
    assert bs[0].gegenpartei == "Muster GmbH"
    assert "Gehalt" in bs[0].verwendungszweck
    assert bs[1].betrag_minor == -82550               # D = Lastschrift
    assert bs[2].gegenpartei == "REWE Markt"


def test_mt940_buchungsdatum_jahreswechsel():
    """F3: Buchungs-MMTT über den Jahreswechsel gehört ins Nachbar-Jahr, nicht
    stur ins Valuta-Jahr — sonst rutscht der Betrag still ins falsche Steuerjahr.
    Beide Wrap-Richtungen + Kein-Wrap + stiller Fallback bei kaputter MMTT."""
    mt = (":20:JW\n:25:DE02120300000000202051\n:28C:00002/001\n"
          ":60F:C251231EUR0,00\n"
          ":61:2512310102DR10,00NTRFNONREF//A1\n"    # Valuta 31.12.25, Buchung 02.01. → 2026
          ":86:105?20Wrap vor\n"
          ":61:2601021230CR20,00NTRFNONREF//A2\n"    # Valuta 02.01.26, Buchung 30.12. → 2025
          ":86:166?20Wrap zurueck\n"
          ":61:2601150115DR5,00NTRFNONREF//A3\n"      # gleicher Monat → unverändert
          ":86:105?20Kein Wrap\n"
          ":61:2512311332DR1,00NTRFNONREF//A4\n"      # MMTT 13/32 unplausibel → Valuta-Datum
          ":86:105?20Kaputte MMTT\n"
          ":62F:C260115EUR4,00\n-\n")
    bs = parse_mt940(mt)
    assert [b.datum for b in bs] == [
        "2026-01-02", "2025-12-30", "2026-01-15", "2025-12-31"]
    assert [b.betrag_minor for b in bs] == [-1000, 2000, -500, -100]


# ------------------------------------------------------ Drei Wege, ein Auszug

def test_drei_formate_gleiche_betraege():
    csv_b = parse_csv(_lies("sparkasse.csv"), profil="auto")[:3]
    camt_b = parse_camt(_lies("statement.camt053.xml"))
    mt_b = parse_mt940(_lies("auszug.mt940.sta"))
    soll = [245000, -82550, -4329]
    assert [b.betrag_minor for b in csv_b] == soll
    assert [b.betrag_minor for b in camt_b] == soll
    assert [b.betrag_minor for b in mt_b] == soll


# ------------------------------------------------------------------- Dispatch

@pytest.mark.parametrize("name,fmt", [
    ("statement.camt053.xml", "camt"),
    ("auszug.mt940.sta", "mt940"),
    ("sparkasse.csv", "csv"),
    ("revolut.csv", "csv"),
])
def test_auto_erkennung(name, fmt):
    assert erkenne_format(_lies(name)) == fmt


def test_dispatch_auto_liefert_bewegungen():
    for name in ("statement.camt053.xml", "auszug.mt940.sta", "sparkasse.csv"):
        bs = parse_inhalt(_lies(name), format="auto")
        assert bs and all(b.datum.startswith("202") for b in bs)


def test_dispatch_bytes_latin1():
    roh = "Datum;Betrag;Empfänger\n01.02.2026;-9,99;Café Münster".encode("latin-1")
    bs = parse_inhalt(roh, format="csv")
    assert bs[0].betrag_minor == -999 and "Café" in bs[0].gegenpartei
