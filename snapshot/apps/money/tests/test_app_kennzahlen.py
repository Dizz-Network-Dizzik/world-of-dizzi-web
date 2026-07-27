"""Dashboard-Tiefe: Sparquote + Fixkosten/Monat in der summary-Kachel und das
kompakte Kennzahlen-Bündel (/api/auswertung/kennzahlen)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _heutige_buchungen(c, giro):
    """Eine Einnahme + eine Ausgabe MIT heutigem Datum (für den 30T-Cashflow)."""
    heute = date.today().isoformat()
    lohn = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]
    miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
    c.post("/api/buchungen", json={"von_konto": lohn, "nach_konto": giro,
                                   "betrag": "2000,00", "datum": heute})
    c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                   "betrag": "500,00", "datum": heute})


def test_summary_sparquote_und_fixkosten(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        _heutige_buchungen(c, giro)
        c.post("/api/wiederkehr", json={"name": "Strom", "betrag": "80,00",
                                        "richtung": "ausgabe", "intervall_tage": 30})
        kpis = {k["id"]: k for k in c.get("/api/summary").json()["kpis"]}
        # Sparquote = (2000-500)/2000 = 75 %
        assert kpis["sparquote_30t"]["value"] == 75
        assert kpis["fixkosten_monat"]["value"] == "80.00"


def test_kennzahlen_buendel(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        _heutige_buchungen(c, giro)
        k = c.get("/api/auswertung/kennzahlen").json()
        assert k["netto_eur_text"] == "1500.00"          # 2000 − 500
        assert k["liquide_mittel_text"] == "1500.00"     # Asset-Konto (Giro)
        assert k["einnahmen_30t_text"] == "2000.00" and k["ausgaben_30t_text"] == "500.00"
        assert k["cashflow_30t_text"] == "1500.00"
        assert k["sparquote_30t"] == 75
        assert k["budget_warnungen"] == 0


def test_kennzahlen_leer(tmp_path):
    with _client(tmp_path) as c:
        k = c.get("/api/auswertung/kennzahlen").json()
        assert k["sparquote_30t"] is None and k["netto_eur"] == 0
