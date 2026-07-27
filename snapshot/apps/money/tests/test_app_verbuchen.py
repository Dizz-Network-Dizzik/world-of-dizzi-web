"""Wiederkehrende Serie verbuchen (Plan → Ist): aus einer gespeicherten Serie
eine echte Buchung erzeugen; Fälligkeit rückt weiter; Cashflow/Kategorie greifen."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _serie(c, kategorie_id=None, richtung="ausgabe", betrag="12,99"):
    return c.post("/api/wiederkehr", json={
        "name": "Netflix", "betrag": betrag, "richtung": richtung,
        "intervall_tage": 30, "intervall": "monatlich",
        "naechste_faelligkeit": "2026-07-05",
        "kategorie_id": kategorie_id}).json()["id"]


def test_verbuchen_erzeugt_buchung_und_rueckt_faelligkeit(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        kat = c.post("/api/kategorien", json={"name": "Abos"}).json()["id"]
        sid = _serie(c, kategorie_id=kat)
        r = c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": giro}).json()
        assert r["ok"] and r["naechste_faelligkeit"] == "2026-08-04"   # +30 Tage
        # Buchung existiert, ist der Kategorie zugeordnet, mindert den Saldo
        bs = c.get("/api/buchungen").json()
        b = next(b for b in bs if b["id"] == r["buchung_id"])
        assert b["betrag"] == "-12.99" and b["kategorie_id"] == kat
        assert b["quelle"] == "serie" and b["datum"] == "2026-07-05"
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "-12.99"


def test_verbuchen_einnahme_positiv(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        sid = _serie(c, richtung="einnahme", betrag="2500,00")
        r = c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": giro}).json()
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "2500.00"


def test_verbuchen_fremdwaehrung_umgerechnet(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/wechselkurse", json={"waehrung": "USD", "kurs": "0.50"})  # 1$=0,50€
        usd = c.post("/api/konten", json={"name": "Dollar", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        sid = _serie(c, richtung="ausgabe", betrag="10,00")   # 10 € → 20 USD
        c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": usd})
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Dollar"]["saldo"] == "-20.00"


def test_verbuchen_validierung(tmp_path):
    with _client(tmp_path) as c:
        sid = _serie(c)
        ausg = c.post("/api/konten", json={"name": "X", "typ": "expense"}).json()["id"]
        assert c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": ausg}).status_code == 400
        assert c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": "weg"}).status_code == 404
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        assert c.post("/api/wiederkehr/weg/verbuchen", json={"konto_id": giro}).status_code == 404
