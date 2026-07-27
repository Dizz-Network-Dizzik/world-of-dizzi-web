"""Tests des Double-Entry-Kerns — inklusive PROPERTY-Tests (deterministisch,
seed-basiert, keine externe Abhängigkeit). Der Kern trägt erhöhte Sorgfalt
(F-Q1), darum prüfen wir die Invarianten über viele zufällige Eingaben, nicht
nur an Beispielen."""

from __future__ import annotations

import random

import pytest

from moneyapp import ledger
from moneyapp.ledger import (Buchung, LedgerError, Posting, anzeige_saldo,
                             einfache_buchung, format_betrag, fx_buchung,
                             gesamt_konsistent, parse_betrag, saldo, umrechnen)


# ------------------------------------------------------- Beträge / Minor-Units

@pytest.mark.parametrize("text,waehrung,erwartet", [
    ("12,50", "EUR", 1250), ("12.50", "EUR", 1250), ("0", "EUR", 0),
    ("-3,33", "EUR", -333), ("1000", "EUR", 100000), (12.5, "EUR", 1250),
    ("0,005", "EUR", 1),         # kaufmännisch auf (ROUND_HALF_UP)
    ("0,004", "EUR", 0),         # ab
    ("1", "JPY", 1), ("1,23456789", "BTC", 123456789),
])
def test_parse_betrag(text, waehrung, erwartet):
    assert parse_betrag(text, waehrung) == erwartet


@pytest.mark.parametrize("minor,waehrung,erwartet", [
    (1250, "EUR", "12.50"), (-333, "EUR", "-3.33"), (5, "EUR", "0.05"),
    (100000, "EUR", "1000.00"), (1, "JPY", "1"), (123456789, "BTC", "1.23456789"),
])
def test_format_betrag(minor, waehrung, erwartet):
    assert format_betrag(minor, waehrung) == erwartet


def test_parse_lehnt_unfug_ab():
    for schlecht in ("abc", "", "1,2,3", float("inf"), float("nan"), True):
        with pytest.raises(LedgerError):
            parse_betrag(schlecht)
    with pytest.raises(LedgerError):
        parse_betrag("1", "XYZ")


def test_parse_betrag_obergrenze_sqlite_integer():
    # Grenzwert selbst geht noch durch (2^63−1 Minor) …
    assert parse_betrag("92233720368547758.07", "EUR") == 2**63 - 1
    assert parse_betrag("-92233720368547758.07", "EUR") == -(2**63 - 1)
    # … alles darüber ⇒ LedgerError (kein OverflowError beim INSERT, F2)
    for riese in ("92233720368547758.08", "1e19", "9" * 20, 10**19):
        with pytest.raises(LedgerError):
            parse_betrag(riese, "EUR")
    assert ledger.pruefe_minor(2**63 - 1) == 2**63 - 1
    with pytest.raises(LedgerError):
        ledger.pruefe_minor(2**63)


def test_parse_format_roundtrip_property():
    """Property: format(parse(x)) ist stabil und parse ist sein eigenes Inverses
    auf Minor-Ebene — über viele Zufallsbeträge und Währungen."""
    rng = random.Random(20260612)
    for _ in range(2000):
        waehrung = rng.choice(list(ledger.WAEHRUNG_DEZIMAL))
        minor = rng.randint(-10**12, 10**12)
        s = format_betrag(minor, waehrung)
        assert parse_betrag(s, waehrung) == minor          # exaktes Inverses
        assert format_betrag(parse_betrag(s, waehrung), waehrung) == s


# ------------------------------------------------------------- Postings/Buchung

def test_posting_validierung():
    with pytest.raises(LedgerError):
        Posting("k1", 0)                       # 0 verboten
    with pytest.raises(LedgerError):
        Posting("", 100)                       # kein Konto
    with pytest.raises(LedgerError):
        Posting("k1", 1.5)                     # kein int
    with pytest.raises(LedgerError):
        Posting("k1", True)                    # bool ist kein gültiger Betrag


def test_buchung_muss_balanciert_sein():
    with pytest.raises(LedgerError):           # Summe 30, nicht 0
        Buchung((Posting("a", 100), Posting("b", -70)))
    with pytest.raises(LedgerError):           # nur ein Konto
        Buchung((Posting("a", 100), Posting("a", -100)))
    with pytest.raises(LedgerError):           # < 2 Postings
        Buchung((Posting("a", 100),))
    gut = Buchung((Posting("a", 100), Posting("b", -100)))
    assert gut.volumen == 100


def test_einfache_buchung():
    b = einfache_buchung("giro", "miete", 75000, notiz="Miete")
    assert sum(p.betrag for p in b.postings) == 0
    assert saldo(b.postings, "miete") == 75000
    assert saldo(b.postings, "giro") == -75000
    with pytest.raises(LedgerError):
        einfache_buchung("giro", "miete", 0)
    with pytest.raises(LedgerError):
        einfache_buchung("giro", "miete", -5)


def test_anzeige_saldo_typ_orientiert():
    # Einnahme: Income-Konto steht roh negativ, soll positiv erscheinen.
    assert anzeige_saldo(-5000, "income") == 5000
    assert anzeige_saldo(12000, "asset") == 12000
    assert anzeige_saldo(-20000, "liability") == 20000   # Schuld als positive Zahl
    with pytest.raises(LedgerError):
        anzeige_saldo(1, "quatsch")


# --------------------------------------------------------------- Property-Tests

def _zufalls_buchung(rng, konten):
    """Erzeugt eine zufällige, GARANTIERT balancierte Mehr-Zeilen-Buchung."""
    k = rng.sample(konten, rng.randint(2, min(4, len(konten))))
    betraege = [rng.randint(-50000, 50000) or 1 for _ in k[:-1]]
    betraege.append(-sum(betraege))            # letzte Zeile gleicht aus
    if betraege[-1] == 0:                       # 0 ist als Posting verboten
        betraege[0] += 1
        betraege[-1] -= 1
    return Buchung(tuple(Posting(kk, b) for kk, b in zip(k, betraege)))


def test_property_balanciert_und_global_konsistent():
    """Property: ein System aus beliebig vielen balancierten Buchungen ist
    IMMER global konsistent (Summe aller Postings 0) — und die Summe aller
    Konten-Salden ist 0. Das ist die fundamentale Buchhaltungs-Garantie."""
    rng = random.Random(42)
    konten = [f"k{i}" for i in range(8)]
    for _ in range(500):
        alle: list[Posting] = []
        for _ in range(rng.randint(1, 40)):
            alle.extend(_zufalls_buchung(rng, konten).postings)
        assert gesamt_konsistent(alle)
        assert sum(saldo(alle, k) for k in konten) == 0


# --------------------------------------------------------------- FX / Multi-Whg

def test_fx_buchung_balanciert_pro_waehrung():
    # 100,00 EUR → 108,00 USD über Tausch-Konten
    b = fx_buchung("giro_eur", 10000, "EUR", "konto_usd", 10800, "USD",
                   "tausch_eur", "tausch_usd", notiz="Reise")
    assert sum(p.betrag for p in b.postings) == 0          # strukturell
    # reale Konten bewegen sich korrekt
    assert saldo(b.postings, "giro_eur") == -10000
    assert saldo(b.postings, "konto_usd") == 10800
    # jede Währung balanciert für sich
    eur = sum(p.betrag for p in b.postings if p.waehrung == "EUR")
    usd = sum(p.betrag for p in b.postings if p.waehrung == "USD")
    assert eur == 0 and usd == 0


def test_fx_zwei_zeilen_quer_wird_abgelehnt():
    # EUR −100 / USD +100 summiert zwar zu 0 (währungsblind), ist aber pro
    # Währung unbalanciert ⇒ muss scheitern (kein Geld aus Kurs-Magie).
    with pytest.raises(LedgerError):
        Buchung((Posting("eur", -10000, "EUR"), Posting("usd", 10000, "USD")))


def test_misch_buchung_teilweise_waehrung_abgelehnt():
    with pytest.raises(LedgerError):
        Buchung((Posting("a", 100, "EUR"), Posting("b", -100)))   # eine ohne Whg


def test_fx_buchung_gleiche_waehrung_verboten():
    with pytest.raises(LedgerError):
        fx_buchung("a", 100, "EUR", "b", 100, "EUR", "c", "d")


@pytest.mark.parametrize("betrag,von,nach,kurse,erwartet", [
    (10000, "EUR", "USD", {"EUR": 1, "USD": "0.9259259259"}, 10800),  # 100€ → 108$
    (10800, "USD", "EUR", {"EUR": 1, "USD": "0.9259259259"}, 10000),  # zurück
    (10000, "EUR", "JPY", {"EUR": 1, "JPY": "0.00625"}, 16000),       # 100€ → 16000¥ (0 Nachk.)
    (100000000, "BTC", "EUR", {"EUR": 1, "BTC": "60000"}, 6000000),   # 1 BTC → 60.000€
    (5000, "EUR", "EUR", {"EUR": 1}, 5000),                            # gleich = identisch
])
def test_umrechnen_exakt(betrag, von, nach, kurse, erwartet):
    assert umrechnen(betrag, von, nach, kurse) == erwartet


def test_umrechnen_fehlender_kurs():
    with pytest.raises(LedgerError):
        umrechnen(100, "EUR", "NOK", {"EUR": 1})


def test_property_unbalanciert_wird_immer_abgelehnt():
    """Property: jede unbalancierte Posting-Menge wird vom Konstruktor
    zurückgewiesen — es gibt keinen Zufalls-Pfad zu einer gültigen
    unbalancierten Buchung."""
    rng = random.Random(7)
    for _ in range(2000):
        n = rng.randint(2, 5)
        betraege = [rng.randint(-1000, 1000) or 1 for _ in range(n)]
        konten = [f"k{i}" for i in range(n)]
        postings = tuple(Posting(k, b) for k, b in zip(konten, betraege))
        if sum(betraege) == 0:
            assert Buchung(postings).volumen >= 0          # gültig
        else:
            with pytest.raises(LedgerError):
                Buchung(postings)
