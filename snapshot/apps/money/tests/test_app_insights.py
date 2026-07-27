"""P3: Spending-Insights-Endpoint — die App-Wächter-KI sichtbar gemacht
(deterministisch, beobachten + hinweisen)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_insights_budget_ueberzug(tmp_path):
    with _client(tmp_path) as c:
        monat, heute = date.today().isoformat()[:7], date.today().isoformat()
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        lohn = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]
        miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
        wohnen = c.post("/api/kategorien", json={"name": "Wohnen"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": lohn, "nach_konto": giro,
                                       "betrag": "1000,00", "datum": heute})
        bid = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                             "betrag": "500,00", "datum": heute}).json()["id"]
        c.post(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": wohnen})
        c.post("/api/budgets", json={"kategorie_id": wohnen, "monat": monat, "betrag": "100,00"})
        ins = c.get("/api/auswertung/insights").json()["insights"]
        assert any(i["art"] == "budget" for i in ins)
        assert any("Wohnen" in i["text"] for i in ins)


def test_insights_leer_gruen(tmp_path):
    with _client(tmp_path) as c:
        ins = c.get("/api/auswertung/insights").json()["insights"]
        assert ins and ins[0]["art"] == "ok"
