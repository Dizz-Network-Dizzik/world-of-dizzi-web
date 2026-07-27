"""P1(a): Split-Buchung — ein Beleg in mehrere kategorisierte Zeilen geteilt.
Jede Zeile wird eine eigene balancierte Buchung; globale Konsistenz bleibt."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_split_bucht_mehrere_kategorien(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        food = c.post("/api/kategorien", json={"name": "Lebensmittel"}).json()["id"]
        haus = c.post("/api/kategorien", json={"name": "Haushalt"}).json()["id"]
        r = c.post("/api/buchungen/split", json={
            "konto_id": giro, "gegenpartei": "REWE", "datum": "2026-06-13",
            "zeilen": [{"betrag": "70,00", "richtung": "ausgabe", "kategorie_id": food},
                       {"betrag": "30,00", "richtung": "ausgabe", "kategorie_id": haus}]})
        assert r.status_code == 200 and r.json()["anzahl"] == 2
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "-100.00"          # 70 + 30 abgeflossen
        bs = c.get("/api/buchungen").json()
        assert len(bs) == 2
        assert {b["kategorie_name"] for b in bs} == {"Lebensmittel", "Haushalt"}
        assert all(b["gegenpartei"] == "REWE" for b in bs)
        db = c.app.state.db
        s = db.get_conn().execute(
            "SELECT COALESCE(SUM(betrag),0) AS s FROM postings WHERE deleted_at IS NULL").fetchone()["s"]
        assert s == 0                                         # global balanciert


def test_split_validierung(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        # keine Zeilen
        assert c.post("/api/buchungen/split", json={"konto_id": giro, "zeilen": []}).status_code == 400
        # negativer Betrag
        assert c.post("/api/buchungen/split", json={"konto_id": giro,
            "zeilen": [{"betrag": "-5", "richtung": "ausgabe"}]}).status_code == 400
        # falsches Konto
        assert c.post("/api/buchungen/split", json={"konto_id": "weg",
            "zeilen": [{"betrag": "5", "richtung": "ausgabe"}]}).status_code == 404
        # Ausgabe-Konto als Split-Konto ⇒ 400
        ausg = c.post("/api/konten", json={"name": "X", "typ": "expense"}).json()["id"]
        assert c.post("/api/buchungen/split", json={"konto_id": ausg,
            "zeilen": [{"betrag": "5", "richtung": "ausgabe"}]}).status_code == 400


def test_split_einnahme(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        r = c.post("/api/buchungen/split", json={"konto_id": giro, "gegenpartei": "Arbeitgeber",
            "zeilen": [{"betrag": "2500,00", "richtung": "einnahme"}]})
        assert r.json()["anzahl"] == 1
        assert {k["name"]: k for k in c.get("/api/konten").json()}["Giro"]["saldo"] == "2500.00"
