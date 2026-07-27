"""Tests der reinen Auswertungsfunktionen (Teil B + D): deterministisch, ohne
DB. Beträge sind Minor-Units (Cent)."""

from __future__ import annotations

from moneyapp.auswertung import (budget_status, cashflow, eur_jahr, finanzspur,
                                 spending_insights, vermoegen)


def test_finanzspur_je_waehrung_getrennt_und_transfer_ignoriert():
    bew = [
        {"waehrung": "EUR", "netto_w": 20000},     # Einnahme
        {"waehrung": "EUR", "netto_w": -10000},    # Ausgabe
        {"waehrung": "USD", "netto_w": -5000},     # Ausgabe (eigene Währung!)
        {"waehrung": "EUR", "netto_w": 0},         # interner Transfer → ignoriert
    ]
    je = {e["waehrung"]: e for e in finanzspur(bew)}
    assert set(je) == {"EUR", "USD"}                # nie gemischt
    assert je["EUR"] == {"waehrung": "EUR", "einnahmen": 20000, "ausgaben": 10000,
                         "saldo": 10000, "anzahl": 2}
    assert je["USD"]["ausgaben"] == 5000 and je["USD"]["saldo"] == -5000
    # deterministische Sortierung: größtes Volumen zuerst (EUR 30000 > USD 5000)
    assert [e["waehrung"] for e in finanzspur(bew)] == ["EUR", "USD"]
    assert finanzspur([]) == []


def _bew(datum, netto, kid=None, name=None, steuer=False, art=""):
    return {"datum": datum, "netto": netto, "kategorie_id": kid,
            "kategorie_name": name, "steuer_relevant": steuer, "steuer_art": art}


def test_cashflow_summen_und_transfer_ignoriert():
    bs = [
        _bew("2026-01-05", 245000, "lohn", "Gehalt"),
        _bew("2026-01-06", -82550, "miete", "Miete"),
        _bew("2026-01-07", -4329, "essen", "Essen"),
        _bew("2026-01-08", 0, None, None),           # interner Transfer → ignoriert
    ]
    cf = cashflow(bs)
    assert cf["einnahmen"] == 245000
    assert cf["ausgaben"] == 82550 + 4329
    assert cf["saldo"] == 245000 - 82550 - 4329
    # je Kategorie nach Volumen sortiert (Gehalt am größten)
    assert cf["je_kategorie"][0]["kategorie_name"] == "Gehalt"
    assert all(e["kategorie_name"] != "" for e in cf["je_kategorie"])


def test_cashflow_zeitraum_filtert():
    bs = [_bew("2025-12-31", 100000), _bew("2026-01-15", -5000),
          _bew("2026-02-01", -3000)]
    cf = cashflow(bs, von="2026-01-01", bis="2026-01-31")
    assert cf["ausgaben"] == 5000 and cf["einnahmen"] == 0


def test_cashflow_nicht_zugeordnet():
    cf = cashflow([_bew("2026-01-01", -1000)])
    assert cf["je_kategorie"][0]["kategorie_name"] == "Nicht zugeordnet"
    assert cf["je_kategorie"][0]["kategorie_id"] is None


def test_vermoegen_netto_und_anzeige():
    konten = [
        {"id": "g", "name": "Giro", "typ": "asset", "waehrung": "EUR", "roh_saldo": 175000},
        {"id": "k", "name": "Kredit", "typ": "liability", "waehrung": "EUR", "roh_saldo": -50000},
        {"id": "e", "name": "Essen", "typ": "expense", "waehrung": "EUR", "roh_saldo": 30000},
    ]
    v = vermoegen(konten)
    # Netto = Asset + Liability roh = 175000 + (−50000) = 125000 (Schuld mindert)
    assert v["netto_je_waehrung"]["EUR"] == 125000
    # Anzeige-Saldo: Liability als positive Schuld, Expense positiv
    zeilen = {z["name"]: z for z in v["konten"]}
    assert zeilen["Kredit"]["saldo_minor"] == 50000
    assert zeilen["Essen"]["saldo_minor"] == 30000


def test_budget_status_ueberzogen():
    budgets = [{"kategorie_id": "essen", "kategorie_name": "Essen", "monat": "2026-01",
                "betrag": 40000},
               {"kategorie_id": "frei", "kategorie_name": "Freizeit", "monat": "2026-01",
                "betrag": 10000}]
    ist = {"essen": 45000, "frei": 2000}
    status = budget_status(budgets, ist)
    essen = next(s for s in status if s["kategorie_id"] == "essen")
    assert essen["rest"] == -5000 and essen["ueberzogen"] is True
    assert essen["prozent"] == 113
    # nach Prozent absteigend sortiert ⇒ Essen (113 %) vor Freizeit (20 %)
    assert status[0]["kategorie_id"] == "essen"


def test_budget_soll_null():
    status = budget_status([{"kategorie_id": "x", "kategorie_name": "X",
                             "monat": "*", "betrag": 0}], {"x": 500})
    assert status[0]["prozent"] == 0 and status[0]["ueberzogen"] is True


def test_eur_jahr_ueberschuss_und_steuerfilter():
    bs = [
        _bew("2026-03-01", 500000, "umsatz", "Umsatz", steuer=True, art="Betriebseinnahme"),
        _bew("2026-04-01", -120000, "buero", "Büro", steuer=True, art="Betriebsausgabe"),
        _bew("2026-05-01", -30000, "privat", "Privat", steuer=False),
        _bew("2025-12-31", 99999, "alt", "Alt", steuer=True),   # anderes Jahr
    ]
    voll = eur_jahr(bs, 2026)
    assert voll["einnahmen"] == 500000
    assert voll["ausgaben"] == 150000
    assert voll["ueberschuss"] == 350000
    nur = eur_jahr(bs, 2026, nur_steuer=True)
    assert nur["ausgaben"] == 120000          # Privat (nicht steuer) fällt raus
    # steuerrelevante zuerst sortiert
    assert nur["je_kategorie"][0]["steuer_relevant"] is True


def test_spending_insights_anomalie_und_sortierung():
    bs = [
        _bew("2026-03-10", -10000, "essen", "Essen"),    # Vormonate je 100 €
        _bew("2026-04-10", -10000, "essen", "Essen"),
        _bew("2026-05-10", -10000, "essen", "Essen"),
        _bew("2026-06-05", -30000, "essen", "Essen"),     # laufender Monat 300 € (Anomalie)
        _bew("2026-06-01", 100000, "lohn", "Lohn"),
    ]
    ins = spending_insights(bs, "2026-06-15",
                            budget_ueberzogen=[{"kategorie_name": "Wohnen", "prozent": 130}],
                            projektion_marken=[{"tage": 60, "saldo": -5000, "negativ": True}])
    txt = " | ".join(i["text"] for i in ins)
    assert "Wohnen" in txt and "Essen" in txt and "ungewöhnlich hoch" in txt
    assert "Liquidität in 60 Tagen negativ" in txt
    # Schweregrad-Sortierung: bad zuerst, dann warn, dann info
    rang = [i["schwere"] for i in ins]
    assert rang == sorted(rang, key=lambda s: {"bad": 0, "warn": 1, "info": 2}[s])


def test_spending_insights_leer_ist_gruen():
    ins = spending_insights([], "2026-06-15")
    assert len(ins) == 1 and ins[0]["art"] == "ok"
