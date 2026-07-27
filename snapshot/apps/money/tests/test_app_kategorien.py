"""Teil B end-to-end: Kategorien-CRUD, Regel-Lernen + Auto-Kategorisierung beim
Import, Budgets und die Auswertungs-Endpoints über den HTTP-Pfad."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from moneyapp import main as mm

FIX = Path(__file__).resolve().parent / "fixtures"


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _lies(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _giro(c) -> str:
    return c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]


def test_kategorie_crud(tmp_path):
    with _client(tmp_path) as c:
        kid = c.post("/api/kategorien", json={"name": "Essen", "richtung": "ausgabe"}).json()["id"]
        assert any(k["name"] == "Essen" for k in c.get("/api/kategorien").json())
        c.put(f"/api/kategorien/{kid}", json={"name": "Lebensmittel", "richtung": "ausgabe"})
        assert any(k["name"] == "Lebensmittel" for k in c.get("/api/kategorien").json())
        assert c.delete(f"/api/kategorien/{kid}").json()["ok"]
        assert not c.get("/api/kategorien").json()
        assert c.post("/api/kategorien", json={"name": "X", "richtung": "quatsch"}).status_code == 400


def test_regel_lernen_und_anwenden(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        kid = c.post("/api/kategorien", json={"name": "Lebensmittel"}).json()["id"]
        c.post("/api/import", json={"inhalt": _lies("sparkasse.csv"),
                                    "format": "csv", "zielkonto": giro})
        # REWE-Buchung finden und MIT Lernen kategorisieren
        buchungen = c.get("/api/buchungen").json()
        rewe = next(b for b in buchungen if "REWE" in b["gegenpartei"])
        r = c.post(f"/api/buchungen/{rewe['id']}/kategorie",
                   json={"kategorie_id": kid, "lernen": True}).json()
        assert r["ok"] and r["gelernt"]
        # eine Regel wurde gelernt (Muster aus Gegenpartei)
        regeln = c.get("/api/regeln").json()
        assert any("rewe" in x["muster"] for x in regeln)

        # NEUE REWE-Bewegung (andere Referenz ⇒ kein Duplikat) → Regel greift autom.
        neu = ("Buchungstag;Beguenstigter/Zahlungspflichtiger;Verwendungszweck;"
               "Kundenreferenz;Betrag;Waehrung\n"
               "10.02.2026;REWE Markt City;Wocheneinkauf;E2E-NEU-1;-55,00;EUR\n")
        imp = c.post("/api/import", json={"inhalt": neu, "format": "csv",
                                          "zielkonto": giro}).json()
        assert imp["importiert"] == 1 and imp["auto_kategorisiert"] >= 1
        rewe2 = next(b for b in c.get("/api/buchungen?q=Wocheneinkauf").json())
        assert rewe2["kategorie_id"] == kid          # automatisch zugeordnet


def test_regel_setzt_bereich_beim_treffer(tmp_path):
    """Eine Regel mit Bereich ordnet einen Treffer AUCH diesem Bereich zu (Auto-Zuordnung)."""
    with _client(tmp_path) as c:
        giro = _giro(c)
        kid = c.post("/api/kategorien", json={"name": "Lebensmittel"}).json()["id"]
        bid = c.post("/api/bereiche", json={"name": "Haushalt", "art": "privat"}).json()["id"]
        rid = c.post("/api/regeln", json={"muster": "rewe", "feld": "gegenpartei",
                                          "kategorie_id": kid, "bereich_id": bid}).json()["id"]
        regel = next(x for x in c.get("/api/regeln").json() if x["id"] == rid)
        assert regel["bereich_id"] == bid and regel["bereich_name"] == "Haushalt"
        # Import einer passenden Buchung ⇒ Auto-Kategorie UND Auto-Bereich
        csv = ("Buchungstag;Beguenstigter/Zahlungspflichtiger;Verwendungszweck;"
               "Kundenreferenz;Betrag;Waehrung\n"
               "12.02.2026;REWE Markt;Wocheneinkauf;BER-1;-30,00;EUR\n")
        assert c.post("/api/import", json={"inhalt": csv, "format": "csv",
                                           "zielkonto": giro}).json()["importiert"] == 1
        b = next(x for x in c.get("/api/buchungen?q=Wocheneinkauf").json())
        assert b["kategorie_id"] == kid and b["bereich_id"] == bid
        # PATCH löst den Bereich; ungültiger Bereich wird abgelehnt.
        assert c.patch(f"/api/regeln/{rid}", json={"bereich_id": ""}).json()["ok"]
        assert next(x for x in c.get("/api/regeln").json() if x["id"] == rid)["bereich_id"] == ""
        assert c.patch(f"/api/regeln/{rid}", json={"bereich_id": "gibtsnicht"}).status_code == 404


def test_regel_lernt_bereich_aus_buchung(tmp_path):
    """Kategorisieren MIT Lernen übernimmt den Bereich der Beispiel-Buchung in die Regel."""
    with _client(tmp_path) as c:
        giro = _giro(c)
        kid = c.post("/api/kategorien", json={"name": "Lebensmittel"}).json()["id"]
        bid = c.post("/api/bereiche", json={"name": "Haushalt", "art": "privat"}).json()["id"]
        c.post("/api/import", json={"inhalt": _lies("sparkasse.csv"),
                                    "format": "csv", "zielkonto": giro})
        rewe = next(b for b in c.get("/api/buchungen").json() if "REWE" in b["gegenpartei"])
        c.put("/api/bereiche/zuordnung",
              json={"tabelle": "buchungen", "id": rewe["id"], "bereich_id": bid})
        c.post(f"/api/buchungen/{rewe['id']}/kategorie",
               json={"kategorie_id": kid, "lernen": True})
        regel = next(x for x in c.get("/api/regeln").json() if "rewe" in x["muster"])
        assert regel["bereich_id"] == bid          # Bereich der Buchung wurde mitgelernt


def test_buchungen_filter_und_suche(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        c.post("/api/import", json={"inhalt": _lies("sparkasse.csv"),
                                    "format": "csv", "zielkonto": giro})
        alle = c.get("/api/buchungen").json()
        assert len(alle) == 4
        treffer = c.get("/api/buchungen?q=Miete").json()
        assert len(treffer) == 1 and "Hausverwaltung" in treffer[0]["gegenpartei"]
        offen = c.get("/api/buchungen?kategorie=_nicht").json()
        assert len(offen) == 4                        # noch nichts kategorisiert
        zeitraum = c.get("/api/buchungen?von=2026-01-01&bis=2026-01-31").json()
        assert all(b["datum"].startswith("2026-01") for b in zeitraum)


def test_cashflow_und_vermoegen(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        c.post("/api/import", json={"inhalt": _lies("sparkasse.csv"),
                                    "format": "csv", "zielkonto": giro})
        cf = c.get("/api/auswertung/cashflow").json()
        assert cf["einnahmen"] == 245000 + 123456     # Gehalt + Steuererstattung
        assert cf["ausgaben"] == 82550 + 4329
        v = c.get("/api/auswertung/vermoegen").json()
        assert v["netto_text"] == "2815.77"           # Giro-Saldo (Sammelkonto neutral)


def test_budget_soll_ist(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        kid = c.post("/api/kategorien", json={"name": "Wohnen"}).json()["id"]
        c.post("/api/import", json={"inhalt": _lies("sparkasse.csv"),
                                    "format": "csv", "zielkonto": giro})
        # Miete-Buchung kategorisieren (Januar 2026)
        miete = next(b for b in c.get("/api/buchungen").json()
                     if "Hausverwaltung" in b["gegenpartei"])
        c.post(f"/api/buchungen/{miete['id']}/kategorie", json={"kategorie_id": kid})
        c.post("/api/budgets", json={"kategorie_id": kid, "monat": "2026-01",
                                     "betrag": "800,00"})
        b = c.get("/api/auswertung/budget?monat=2026-01").json()
        eintrag = next(x for x in b["budgets"] if x["kategorie_id"] == kid)
        assert eintrag["ist"] == 82550               # 825,50 ausgegeben
        assert eintrag["ueberzogen"] is True         # über 800 €
        assert eintrag["soll_text"] == "800.00"


def test_budget_negativ_abgelehnt(tmp_path):
    with _client(tmp_path) as c:
        kid = c.post("/api/kategorien", json={"name": "X"}).json()["id"]
        assert c.post("/api/budgets", json={"kategorie_id": kid, "betrag": "-5"}).status_code == 400
