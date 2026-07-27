"""V14 (docs/26 §13): Trading-Steuer-Endpoints in Money — Config, Kapital-Verlauf,
Realisierungen, Jahres-Steuer-Übersicht (gegen die geprüfte Engine) + die read-only
Trading-Bot-Performance-Brücke."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from appkit import auth
from appkit.auth import DEFAULT_USER_ID
from moneyapp import main as mm


def _client(tmp_path, *, tb_get=None):
    kw = {}
    if tb_get is not None:
        kw["tb_get"] = tb_get
    return TestClient(mm.build_app(data_dir=tmp_path, **kw))


def test_config_default_und_update(tmp_path):
    with _client(tmp_path) as c:
        cfg = c.get("/api/trading/config").json()
        assert cfg["kirchensteuer_satz"] == 0.09          # Nutzer-Default (17.06.)
        assert cfg["pauschbetrag_rest_cent"] == 100_000
        r = c.put("/api/trading/config",
                  json={"persoenlicher_satz": 0.30, "pauschbetrag_rest": "500,00",
                        "kirchensteuer_satz": 0.0})
        assert r.json()["ok"] is True
        cfg2 = c.get("/api/trading/config").json()
        assert cfg2["persoenlicher_satz"] == 0.30
        assert cfg2["pauschbetrag_rest_cent"] == 50_000
        assert cfg2["kirchensteuer_satz"] == 0.0


def test_kapital_crud_und_stand(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/trading/kapital",
               json={"datum": "2026-01-01", "art": "einlage", "betrag": "5000,00"})
        c.post("/api/trading/kapital",
               json={"datum": "2026-03-01", "art": "bewertung", "betrag": "6000,00"})
        liste = c.get("/api/trading/kapital").json()
        assert len(liste) == 2 and liste[0]["betrag"] == "6000.00"
        stand = c.get("/api/trading/kapital/stand").json()
        assert stand["investiert"] == 500_000 and stand["aktueller_wert"] == 600_000
        assert stand["unrealisiert"] == 100_000 and stand["bewertet"] is True
        # ungültige art ⇒ 400 · negativer Betrag ⇒ 400
        assert c.post("/api/trading/kapital",
                      json={"datum": "2026-01-01", "art": "quatsch", "betrag": "1"}).status_code == 400
        # löschen
        kid = liste[0]["id"]
        assert c.delete(f"/api/trading/kapital/{kid}").json()["ok"] is True
        assert c.delete(f"/api/trading/kapital/{kid}").status_code == 404


def test_realisierung_und_steuer_uebersicht(tmp_path):
    with _client(tmp_path) as c:
        # Futures-Gewinn 1.500 € ⇒ über Sparer-Pauschbetrag
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-02-01", "regime": "futures", "betrag": "1500,00",
                     "richtung": "gewinn"})
        # Spot-Gewinn 1.200 € innerhalb der Haltefrist
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-04-01", "regime": "spot", "betrag": "1200,00",
                     "richtung": "gewinn", "kauf_datum": "2026-01-01"})
        # Verlust mindert Futures-Netto
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-05-01", "regime": "futures", "betrag": "200,00",
                     "richtung": "verlust"})
        st = c.get("/api/trading/steuer", params={"jahr": 2026}).json()
        assert st["jahr"] == 2026
        assert st["futures"]["netto"] == 130_000           # 1.500 − 200
        assert st["futures"]["steuerpflichtig"] == 30_000  # − 1.000 Pauschbetrag
        assert st["spot"]["unter_freigrenze"] is False     # 1.200 > 1.000
        assert st["spot"]["steuerpflichtig"] == 120_000
        assert len(st["warnungen"]) >= 2
        assert st["steuer_gesamt"] > 0
        # Jahres-Filter
        assert len(c.get("/api/trading/realisierungen", params={"jahr": 2026}).json()) == 3
        assert c.get("/api/trading/realisierungen", params={"jahr": 2025}).json() == []
        # ungültiges regime/richtung ⇒ 400
        assert c.post("/api/trading/realisierungen",
                      json={"datum": "2026-01-01", "regime": "x", "betrag": "1"}).status_code == 400


def test_tb_performance_brucke_readonly(tmp_path):
    erfasst = {}

    class _R:
        status_code = 200

        def json(self):
            return {"running": 51, "profit_abs": -830.46}

    def fake_get(url):
        erfasst["url"] = url
        return _R()

    with _client(tmp_path, tb_get=fake_get) as c:
        r = c.get("/api/trading/tb-performance").json()
        assert r["ok"] is True and r["paper"] is True
        assert r["stats"]["running"] == 51
        assert erfasst["url"].endswith("/api/panels/tradingbot/stats")


def test_tb_performance_offline_ehrlich(tmp_path):
    def boom(url):
        raise RuntimeError("down")

    with _client(tmp_path, tb_get=boom) as c:
        r = c.get("/api/trading/tb-performance").json()
        assert r["ok"] is False and "fehler" in r and r["stats"] == {}


def test_steuer_export_formate(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-02-01", "regime": "futures", "betrag": "1500,00",
                     "richtung": "gewinn", "beschreibung": "Future X"})
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-04-01", "regime": "spot", "betrag": "1200,00",
                     "richtung": "gewinn", "kauf_datum": "2026-01-01", "beschreibung": "Spot A"})
        md = c.get("/api/trading/steuer/export", params={"jahr": 2026, "format": "md"})
        assert md.status_code == 200
        assert "Anlage KAP" in md.text and "Future X" in md.text
        assert "attachment" in md.headers["content-disposition"]
        csv = c.get("/api/trading/steuer/export", params={"jahr": 2026, "format": "csv"})
        assert csv.status_code == 200 and "Regime" in csv.text and "futures" in csv.text
        js = c.get("/api/trading/steuer/export", params={"jahr": 2026, "format": "json"}).json()
        assert "auswertung" in js and "posten" in js and len(js["posten"]) == 2
        # ungültiges Format ⇒ 400
        assert c.get("/api/trading/steuer/export", params={"format": "pdf"}).status_code == 400


def test_csv_export_entschaerft_formel_injection(tmp_path):
    """Audit-2-Fund: ein Beschreibungstext, der mit =,+,-,@ beginnt, würde in Excel/Calc
    als Formel ausgeführt — der CSV-Export (geht an Steuerberater/Finanzamt) entschärft ihn."""
    with _client(tmp_path) as c:
        c.post("/api/trading/realisierungen",
               json={"datum": "2026-01-01", "regime": "futures", "betrag": "100",
                     "richtung": "gewinn", "beschreibung": "=SUM(A1:A9)"})
        csv = c.get("/api/trading/steuer/export", params={"jahr": 2026, "format": "csv"}).text
        assert "'=SUM" in csv                 # mit führendem Apostroph entschärft
        assert ";=SUM" not in csv             # nicht roh als Zell-Start
        assert "\n=SUM" not in csv            # auch nicht am Zeilenanfang


def test_datum_validierung(tmp_path):
    """Audit-Fund (d): ungültige/leere Datumsfelder werden mit 400 abgelehnt statt
    still nicht erfasst."""
    with _client(tmp_path) as c:
        assert c.post("/api/trading/kapital",
                      json={"datum": "31.02.2026", "art": "einlage", "betrag": "100"}).status_code == 400
        assert c.post("/api/trading/kapital",
                      json={"datum": "", "art": "einlage", "betrag": "100"}).status_code == 400
        assert c.post("/api/trading/realisierungen",
                      json={"datum": "quatsch", "regime": "futures", "betrag": "100",
                            "richtung": "gewinn"}).status_code == 400
        # ungültiges kauf_datum (Spot) ⇒ 400
        assert c.post("/api/trading/realisierungen",
                      json={"datum": "2026-01-01", "regime": "spot", "betrag": "100",
                            "richtung": "gewinn", "kauf_datum": "2026-13-01"}).status_code == 400
        # gültige Daten ⇒ 200
        assert c.post("/api/trading/kapital",
                      json={"datum": "2026-01-01", "art": "einlage", "betrag": "100"}).json()["ok"]
        assert c.post("/api/trading/realisierungen",
                      json={"datum": "2026-01-01", "regime": "futures", "betrag": "100",
                            "richtung": "gewinn"}).json()["ok"]


def test_konto_loeschen_raeumt_config_und_kurse_hart(tmp_path):
    """DSGVO-Audit-Fund: trading_config + wechselkurse haben KEIN deleted_at ⇒
    soft_delete_user überspringt sie. Der on_delete-Hook muss sie bei der Konto-
    Löschung HART entfernen (sonst bleiben Nutzer-Daten liegen)."""
    auth.reset_identity_provider()
    app = mm.build_app(data_dir=tmp_path)
    db = app.state.db
    try:
        with TestClient(app) as c:
            c.get("/api/trading/config")                 # legt die Config-Zeile an
            n = db.get_conn().execute("SELECT COUNT(*) AS n FROM trading_config").fetchone()["n"]
            assert n == 1
            # fail-closed: verifizierte, frische Identität setzen
            auth.set_identity_provider(lambda _r: auth.UserContext(
                DEFAULT_USER_ID, level="verifiziert", via="dizzi-id", auth_time=time.time() - 5))
            r = c.post("/api/account/loeschen").json()
            assert r["ok"] is True and r["artefakte_geraeumt"] is True
            # HART gelöscht (keine deleted_at-Spalte ⇒ Zeile ganz weg)
            n2 = db.get_conn().execute("SELECT COUNT(*) AS n FROM trading_config").fetchone()["n"]
            assert n2 == 0
            n3 = db.get_conn().execute("SELECT COUNT(*) AS n FROM wechselkurse").fetchone()["n"]
            assert n3 == 0
    finally:
        auth.reset_identity_provider()
