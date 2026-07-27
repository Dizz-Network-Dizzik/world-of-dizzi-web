"""A5/V17 (docs/34) — per-Bereich-Finanzspur-Endpoint für Dizz Admins Bereichs-
Cockpit. Aggregiert JE WÄHRUNG getrennt (Ledger-Invariante, keine EUR-Mischung),
gefiltert auf den Kategorie-Namen (= ``bereich.money_kontext``). Read-only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _kat(c, name):
    return c.post("/api/kategorien", json={"name": name}).json()["id"]


def _konto(c, name, typ, waehrung="EUR"):
    return c.post("/api/konten", json={"name": name, "typ": typ,
                                       "waehrung": waehrung}).json()["id"]


def _buchung(c, von, nach, betrag, kat=None, datum=""):
    bid = c.post("/api/buchungen", json={"von_konto": von, "nach_konto": nach,
                                         "betrag": betrag, "datum": datum}).json()["id"]
    if kat:
        c.post(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": kat})
    return bid


def test_finanzspur_je_waehrung_getrennt(tmp_path):
    with _client(tmp_path) as c:
        studium = _kat(c, "Studium")
        freizeit = _kat(c, "Freizeit")
        giro = _konto(c, "Giro", "asset")
        uni = _konto(c, "Uni", "expense")
        stip = _konto(c, "Stipendium", "income")
        usd = _konto(c, "DollarKonto", "asset", "USD")
        books = _konto(c, "Books", "expense", "USD")
        # EUR: Einnahme 200 + Ausgabe 100 (Studium, 2026)
        _buchung(c, stip, giro, "200,00", studium, "2026-03-01")
        _buchung(c, giro, uni, "100,00", studium, "2026-03-02")
        # USD: Ausgabe 50 (Studium, 2026)
        _buchung(c, usd, books, "50,00", studium, "2026-03-03")
        # andere Kategorie (darf NICHT auftauchen)
        _buchung(c, giro, uni, "999,00", freizeit, "2026-03-04")
        # Studium in 2025 (Jahresfilter darf es ausschließen)
        _buchung(c, giro, uni, "77,00", studium, "2025-03-01")

        r = c.get("/api/bereich/finanzspur?kontext=studium&jahr=2026").json()
        assert r["kontext"] == "studium" and r["jahr"] == 2026
        je = {e["waehrung"]: e for e in r["je_waehrung"]}
        assert set(je) == {"EUR", "USD"}                       # getrennt, nie gemischt
        assert je["EUR"]["einnahmen"] == 20000
        assert je["EUR"]["ausgaben"] == 10000
        assert je["EUR"]["saldo"] == 10000 and je["EUR"]["anzahl"] == 2
        assert je["USD"]["ausgaben"] == 5000 and je["USD"]["einnahmen"] == 0
        assert je["USD"]["saldo"] == -5000 and je["USD"]["anzahl"] == 1
        assert je["EUR"]["saldo_text"] == "100.00"
        assert je["USD"]["ausgaben_text"] == "50.00"
        assert "Studium" in r["kategorien"]
        assert r["anzahl_buchungen"] == 3                      # 999€-Freizeit + 2025 raus

        # case-insensitiv + ohne Jahr zieht 2025 mit ein (10000 + 7700)
        alle = c.get("/api/bereich/finanzspur?kontext=Studium").json()
        je_alle = {e["waehrung"]: e for e in alle["je_waehrung"]}
        assert je_alle["EUR"]["ausgaben"] == 10000 + 7700


def test_finanzspur_unbekannter_und_leerer_kontext(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/bereich/finanzspur?kontext=gibtsnicht").json()["je_waehrung"] == []
        assert c.get("/api/bereich/finanzspur").json() == {
            "kontext": "", "jahr": 0, "je_waehrung": [],
            "kategorien": [], "anzahl_buchungen": 0}
