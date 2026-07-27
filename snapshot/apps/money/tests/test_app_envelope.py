"""P1(b): Envelope-/Zero-Based-Budget — der /api/auswertung/budget-Endpoint liefert
neben den Umschlägen die Zero-Based-Summen (Einnahmen / zugewiesen / ausgegeben /
zuzuweisen). „Jeder Euro hat einen Job"."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_envelope_summen(tmp_path):
    with _client(tmp_path) as c:
        monat, heute = date.today().isoformat()[:7], date.today().isoformat()
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        lohn = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]
        miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
        wohnen = c.post("/api/kategorien", json={"name": "Wohnen"}).json()["id"]
        # Einnahme 2000 + kategorisierte Ausgabe 500 (heute)
        c.post("/api/buchungen", json={"von_konto": lohn, "nach_konto": giro,
                                       "betrag": "2000,00", "datum": heute})
        bid = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                             "betrag": "500,00", "datum": heute}).json()["id"]
        c.post(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": wohnen})
        c.post("/api/budgets", json={"kategorie_id": wohnen, "monat": monat, "betrag": "800,00"})

        env = c.get(f"/api/auswertung/budget?monat={monat}").json()["envelope"]
        assert env["einnahmen"] == 200000          # 2000,00 €
        assert env["zugewiesen"] == 80000          # 800,00 € einem Umschlag zugewiesen
        assert env["ausgegeben"] == 50000          # 500,00 € ausgegeben
        assert env["zuzuweisen"] == 120000         # 2000 − 800 = 1200 noch zu verteilen
        assert env["zuzuweisen_text"] == "1200.00"


def test_envelope_ueberbudgetiert(tmp_path):
    with _client(tmp_path) as c:
        monat, heute = date.today().isoformat()[:7], date.today().isoformat()
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        lohn = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]
        a = c.post("/api/kategorien", json={"name": "A"}).json()["id"]
        # Einnahme 100, aber 300 zugewiesen ⇒ zuzuweisen negativ (überbudgetiert)
        c.post("/api/buchungen", json={"von_konto": lohn, "nach_konto": giro,
                                       "betrag": "100,00", "datum": heute})
        c.post("/api/budgets", json={"kategorie_id": a, "monat": monat, "betrag": "300,00"})
        env = c.get(f"/api/auswertung/budget?monat={monat}").json()["envelope"]
        assert env["zuzuweisen"] == -20000         # 100 − 300 = −200 €
