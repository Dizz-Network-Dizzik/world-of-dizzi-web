"""P3: 30/60/90-Liquiditäts-Projektion — heutige liquide Mittel mit den
gespeicherten wiederkehrenden Posten fortgeschrieben."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_projektion_marken(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        ek = c.post("/api/konten", json={"name": "Start", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro, "betrag": "1000,00"})
        # monatliches Abo −100, erste Fälligkeit in 5 Tagen
        faellig = (date.today() + timedelta(days=5)).isoformat()
        c.post("/api/wiederkehr", json={"name": "Netflix", "betrag": "100,00",
                                        "richtung": "ausgabe", "intervall_tage": 30,
                                        "naechste_faelligkeit": faellig})
        p = c.get("/api/auswertung/projektion?tage=90").json()
        assert p["start_text"] == "1000.00"
        m = {x["tage"]: x for x in p["marken"]}
        assert m[30]["saldo_text"] == "900.00"        # 1 Fälligkeit (Tag 5)
        assert m[60]["saldo_text"] == "800.00"        # + Tag 35
        assert m[90]["saldo_text"] == "700.00"        # + Tag 65


def test_projektion_ohne_serien(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        ek = c.post("/api/konten", json={"name": "S", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro, "betrag": "500,00"})
        p = c.get("/api/auswertung/projektion").json()
        assert p["start_text"] == "500.00"
        assert all(x["saldo_text"] == "500.00" for x in p["marken"])   # konstant ohne Fixposten
