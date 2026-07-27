"""FX/Multi-Währung end-to-end: Wechselkurse pflegen, FX-Buchung über Tausch-
Konten, EUR-Aggregation in Vermögen/Cashflow. Globale Konsistenz bleibt gewahrt."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_wechselkurse_pflegen(tmp_path):
    with _client(tmp_path) as c:
        k = c.get("/api/wechselkurse").json()
        assert k["kurse"]["EUR"] == "1" and "USD" in k["kurse"]
        assert c.put("/api/wechselkurse", json={"waehrung": "USD", "kurs": "0,90"}).json()["ok"]
        assert c.get("/api/wechselkurse").json()["kurse"]["USD"] == "0.90"
        assert c.put("/api/wechselkurse", json={"waehrung": "EUR", "kurs": "2"}).status_code == 400
        assert c.put("/api/wechselkurse", json={"waehrung": "XYZ", "kurs": "1"}).status_code == 400


def test_fx_buchung_geschaetzt_aus_kurs(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/wechselkurse", json={"waehrung": "USD", "kurs": "0.90"})  # 1$ = 0,90€
        eur = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        usd = c.post("/api/konten", json={"name": "Dollar", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        # ohne betrag_nach → aus Kurs geschätzt: 90 EUR / 0,90 = 100 USD
        r = c.post("/api/buchungen", json={"von_konto": eur, "nach_konto": usd,
                                           "betrag": "90,00"})
        assert r.json()["ok"]
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "-90.00"
        assert konten["Dollar"]["saldo"] == "100.00"


def test_vermoegen_eur_aggregiert_fremdwaehrung(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/wechselkurse", json={"waehrung": "USD", "kurs": "0.50"})  # 1$ = 0,50€
        eur = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        usd = c.post("/api/konten", json={"name": "Dollar", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        # Startguthaben über Eigenkapital buchen, damit echte Salden entstehen
        ek = c.post("/api/konten", json={"name": "Start", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": eur, "betrag": "200,00"})
        eku = c.post("/api/konten", json={"name": "StartUSD", "typ": "equity",
                                          "waehrung": "USD"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": eku, "nach_konto": usd, "betrag": "100,00"})
        v = c.get("/api/auswertung/vermoegen").json()
        # 200 EUR + 100 USD*0,50 = 200 + 50 = 250 EUR
        assert v["netto_eur_text"] == "250.00"
        assert v["netto_je_waehrung"]["USD"] == 10000          # roh in USD-Cent


def test_buchungsliste_zeigt_fremdwaehrung_nativ(tmp_path):
    """Regression: eine Buchung auf einem Fremdwährungs-Konto erscheint in der
    Liste mit ihrem ECHTEN Betrag + Währung — nicht als 0.00 (alter EUR-Filter)."""
    with _client(tmp_path) as c:
        usd = c.post("/api/konten", json={"name": "Dollar", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        ausg = c.post("/api/konten", json={"name": "Shopping", "typ": "expense",
                                           "waehrung": "USD"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": usd, "nach_konto": ausg,
                                       "betrag": "42,00"})
        b = c.get("/api/buchungen").json()[0]
        assert b["betrag"] == "-42.00" and b["waehrung"] == "USD"   # NICHT 0.00/EUR


def test_fx_globale_konsistenz(tmp_path):
    with _client(tmp_path) as c:
        eur = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        usd = c.post("/api/konten", json={"name": "Dollar", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        for _ in range(3):
            c.post("/api/buchungen", json={"von_konto": eur, "nach_konto": usd,
                                           "betrag": "50,00", "betrag_nach": "54,00"})
        db = c.app.state.db
        s = db.get_conn().execute("SELECT COALESCE(SUM(betrag),0) AS s FROM postings").fetchone()["s"]
        assert s == 0
        # je Währung balanciert: EUR-Postings summieren 0, USD-Postings summieren 0
        eur_s = db.get_conn().execute(
            "SELECT COALESCE(SUM(p.betrag),0) AS s FROM postings p JOIN konten k "
            "ON k.id=p.konto_id WHERE k.waehrung='EUR'").fetchone()["s"]
        usd_s = db.get_conn().execute(
            "SELECT COALESCE(SUM(p.betrag),0) AS s FROM postings p JOIN konten k "
            "ON k.id=p.konto_id WHERE k.waehrung='USD'").fetchone()["s"]
        assert eur_s == 0 and usd_s == 0
