"""Teil D end-to-end: Steuer-Flags auf Kategorien, EÜR-artige Jahres-Auswertung
und Export (JSON/CSV) über den HTTP-Pfad. Kein Filing — nur Übersicht/Export."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _setup_jahr(c):
    """Legt Konten/Kategorien an und bucht je eine Einnahme/Ausgabe 2026."""
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    umsatz = c.post("/api/kategorien", json={
        "name": "Umsatz", "richtung": "einnahme",
        "steuer_relevant": True, "steuer_art": "Betriebseinnahme"}).json()["id"]
    buero = c.post("/api/kategorien", json={
        "name": "Büro", "richtung": "ausgabe",
        "steuer_relevant": True, "steuer_art": "Betriebsausgabe"}).json()["id"]
    privat = c.post("/api/kategorien", json={"name": "Privat", "richtung": "ausgabe"}).json()["id"]
    # Import zweier Bewegungen 2026 (Einnahme + Ausgabe) + 1 privat
    csv = ("Datum;Empfänger;Verwendungszweck;Kundenreferenz;Betrag;Währung\n"
           "15.03.2026;Kunde AG;Projekt Alpha;R-1;5.000,00;EUR\n"
           "20.04.2026;Bürohaus;Material;R-2;-1.200,00;EUR\n"
           "01.05.2026;Supermarkt;Privatkauf;R-3;-300,00;EUR\n")
    c.post("/api/import", json={"inhalt": csv, "format": "csv", "zielkonto": giro})
    bs = {b["gegenpartei"]: b for b in c.get("/api/buchungen").json()}
    c.post(f"/api/buchungen/{bs['Kunde AG']['id']}/kategorie", json={"kategorie_id": umsatz})
    c.post(f"/api/buchungen/{bs['Bürohaus']['id']}/kategorie", json={"kategorie_id": buero})
    c.post(f"/api/buchungen/{bs['Supermarkt']['id']}/kategorie", json={"kategorie_id": privat})
    return giro


def test_steuer_jahr_ueberschuss(tmp_path):
    with _client(tmp_path) as c:
        _setup_jahr(c)
        j = c.get("/api/steuer/jahr?jahr=2026").json()
        assert j["einnahmen"] == 500000
        assert j["ausgaben"] == 120000 + 30000
        assert j["ueberschuss"] == 500000 - 150000
        assert j["ueberschuss_text"] == "3500.00"


def test_steuer_jahr_nur_steuer(tmp_path):
    with _client(tmp_path) as c:
        _setup_jahr(c)
        j = c.get("/api/steuer/jahr?jahr=2026&nur_steuer=true").json()
        # Privat (nicht steuerrelevant) fällt raus ⇒ nur Büro als Ausgabe
        assert j["ausgaben"] == 120000
        assert all(k["steuer_relevant"] for k in j["je_kategorie"])


def test_steuer_export_json(tmp_path):
    with _client(tmp_path) as c:
        _setup_jahr(c)
        r = c.get("/api/steuer/export?jahr=2026&format=json")
        assert r.status_code == 200
        assert "application/json" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        assert r.json()["jahr"] == 2026


def test_steuer_export_csv(tmp_path):
    with _client(tmp_path) as c:
        _setup_jahr(c)
        r = c.get("/api/steuer/export?jahr=2026&format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        zeilen = r.text.strip().splitlines()
        assert zeilen[0].startswith("Kategorie;")
        assert any(z.startswith("SUMME 2026;") for z in zeilen)
        assert "Umsatz;ja;Betriebseinnahme;5000.00" in r.text


def test_steuer_export_format_invalid(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/steuer/export?jahr=2026&format=pdf").status_code == 400
