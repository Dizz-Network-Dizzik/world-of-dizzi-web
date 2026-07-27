"""Tests Dizz Money (App-Ebene): Vertrags-Konformität + Buchungs-Domäne
end-to-end. Die DB darf eine unbalancierte Buchung nie sehen — geprüft über
den HTTP-Pfad UND die globale Konsistenz-Probe auf der Postings-Tabelle."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit import conformance
from moneyapp import main as mm


def _client(tmp_path, *, archiv_post=None):
    kw = {}
    if archiv_post is not None:
        kw["archiv_post"] = archiv_post
    return TestClient(mm.build_app(data_dir=tmp_path, **kw))


def _archiv_capture(store):
    """Mock für den Querverbindungs-POST (archiviere ruft mit keyword ``json=``)."""
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "uebersprungen", "grund": "manuell"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post


def test_beleg_archivieren_an_memory(tmp_path):
    """V9 (docs/26): der „⇲ Memory"-Knopf schickt einen Beleg explizit über den
    Core-Relay an Dizz Memory — Finanzdaten ⇒ IMMER ``sensibel=True`` (Memory-KI
    nur lokal); Umschlag korrekt (app/strom/ref/explizit), Betrag + Notiz im Body."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
        bid = c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": miete, "betrag": "750,00",
            "datum": "2026-06-15", "notiz": "Miete Juni 2026"}).json()["id"]

        r = c.post(f"/api/buchungen/{bid}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "finanzen" and u["strom"] == "beleg"
        assert u["explizit"] is True and u["ref"] == "finanzen:beleg:" + bid
        assert u["sensibel"] is True                  # Finanzdaten IMMER sensibel (docs/26 §5)
        assert "Miete Juni 2026" in u["inhalt"] and "750" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        assert "beleg_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/buchungen/fehlt/archivieren").status_code == 404


def test_vertrag_konform(tmp_path):
    with _client(tmp_path) as c:
        conformance.check_contract(c, "finanzen")
        # sensible App (hoch) ⇒ KI-Routing startet lokal_only
        schema = c.get("/api/settings/schema").json()["kategorien"]
        ki = {d["key"]: d for d in schema["ki"]}
        assert ki["ki_routing"]["default"] == "lokal_only"


def test_konto_und_buchung_end_to_end(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
        lohn = c.post("/api/konten", json={"name": "Lohn", "typ": "income"}).json()["id"]

        # Lohn 2500,00 aufs Giro; Miete 750,00 vom Giro
        assert c.post("/api/buchungen", json={
            "von_konto": lohn, "nach_konto": giro, "betrag": "2500,00"}).json()["ok"]
        assert c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": miete, "betrag": "750,00"}).json()["ok"]

        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "1750.00"     # 2500 − 750
        assert konten["Miete"]["saldo"] == "750.00"      # Ausgabe positiv
        assert konten["Lohn"]["saldo"] == "2500.00"      # Einnahme positiv (Anzeige)

        netto = next(k for k in c.get("/api/summary").json()["kpis"]
                     if k["id"] == "netto")
        assert netto["value"] == "1750.00"               # nur Asset/Liability


def test_unbalanciert_erreicht_die_db_nie(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        spar = c.post("/api/konten", json={"name": "Spar", "typ": "asset"}).json()["id"]
        # Ungültige Beträge werden mit 400 abgelehnt, NICHTS wird gebucht.
        assert c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": spar, "betrag": "0"}).status_code == 400
        assert c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": spar, "betrag": "-50"}).status_code == 400
        assert c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": "gibtsnicht", "betrag": "10"}).status_code == 404
        # Globale Konsistenz-Probe auf der echten Postings-Tabelle:
        db = mm.build_app(data_dir=tmp_path).state.db
        s = db.get_conn().execute("SELECT COALESCE(SUM(betrag),0) AS s FROM postings").fetchone()["s"]
        assert s == 0


def test_buchung_setzt_balancierte_postings(tmp_path):
    """Jede gebuchte Transaktion hinterlässt exakt balancierte Postings —
    die Summe je Buchung ist 0 (doppelte Buchführung in der DB)."""
    with _client(tmp_path) as c:
        a = c.post("/api/konten", json={"name": "A", "typ": "asset"}).json()["id"]
        b = c.post("/api/konten", json={"name": "B", "typ": "expense"}).json()["id"]
        for betrag in ("1,11", "999,99", "0,01"):
            c.post("/api/buchungen", json={"von_konto": a, "nach_konto": b,
                                           "betrag": betrag})
        db = c.app.state.db
        rows = db.get_conn().execute(
            "SELECT buchung_id, SUM(betrag) AS s FROM postings GROUP BY buchung_id").fetchall()
        assert rows and all(r["s"] == 0 for r in rows)


def test_buchung_riesenbetrag_400_statt_500(tmp_path):
    """F2: absurd großer Betrag ⇒ 400 am Rand (nicht OverflowError → 500), 0 Zeilen."""
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        spar = c.post("/api/konten", json={"name": "Spar", "typ": "asset"}).json()["id"]
        r = c.post("/api/buchungen",
                   json={"von_konto": giro, "nach_konto": spar, "betrag": "99999999999999999999"})
        assert r.status_code == 400          # vorher: OverflowError → 500
        db = c.app.state.db
        assert db.get_conn().execute("SELECT COUNT(*) AS n FROM buchungen").fetchone()["n"] == 0


def test_buchung_write_crash_laesst_keine_waisen(tmp_path, monkeypatch):
    """F1: Crash MITTEN im Multi-Statement-Write ⇒ Rollback (0 Waisen), Folge-Write frei."""
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        spar = c.post("/api/konten", json={"name": "Spar", "typ": "asset"}).json()["id"]
        echt, zaehler = mm.new_id, {"n": 0}
        def kaputt():
            zaehler["n"] += 1
            if zaehler["n"] == 3:            # bid + 1. Posting ok, 2. Posting crasht mitten im Write
                raise RuntimeError("boom mitten im Write")
            return echt()
        monkeypatch.setattr(mm, "new_id", kaputt)   # main.py bindet new_id per from-Import ⇒ mm.new_id greift
        with pytest.raises(RuntimeError):
            c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": spar, "betrag": "10,00"})
        monkeypatch.setattr(mm, "new_id", echt)
        db = c.app.state.db
        assert db.get_conn().execute("SELECT COUNT(*) AS n FROM buchungen").fetchone()["n"] == 0   # 0 Waisen-Köpfe
        assert db.get_conn().execute("SELECT COUNT(*) AS n FROM postings").fetchone()["n"] == 0    # 0 Waisen-Postings
        # Folge-Write geht sofort (Txn geschlossen, WAL-Write-Lock frei):
        assert c.post("/api/buchungen",
                      json={"von_konto": giro, "nach_konto": spar, "betrag": "10,00"}).json()["ok"]


def test_fx_buchung_ueber_tauschkonten(tmp_path):
    """FX wird jetzt unterstützt: balanciert pro Währung über Tausch-Konten;
    die globale Postings-Summe bleibt 0 und die Konten bewegen sich korrekt."""
    with _client(tmp_path) as c:
        eur = c.post("/api/konten", json={"name": "Giro", "typ": "asset",
                                          "waehrung": "EUR"}).json()["id"]
        usd = c.post("/api/konten", json={"name": "USD", "typ": "asset",
                                          "waehrung": "USD"}).json()["id"]
        # 100,00 EUR → 108,00 USD (expliziter Empfangsbetrag)
        r = c.post("/api/buchungen", json={"von_konto": eur, "nach_konto": usd,
                                           "betrag": "100,00", "betrag_nach": "108,00"})
        assert r.json()["ok"]
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "-100.00"
        assert konten["USD"]["saldo"] == "108.00"
        # globale Konsistenz bleibt (jede Währung für sich 0 ⇒ Gesamtsumme 0)
        db = c.app.state.db
        s = db.get_conn().execute("SELECT COALESCE(SUM(betrag),0) AS s FROM postings").fetchone()["s"]
        assert s == 0


def test_ungueltiger_kontotyp(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/konten", json={"name": "X", "typ": "quatsch"}).status_code == 400
        assert c.post("/api/konten", json={"name": "X", "typ": "asset",
                                           "waehrung": "XYZ"}).status_code == 400


def test_dizz_defense_aktiv(tmp_path):
    """Vertrag 1.4: Dizz Money bringt sein Immunsystem mit."""
    with _client(tmp_path) as c:
        d = c.get("/api/defense").json()
        assert d["name"] == "Dizz Defense" and d["app"] == "finanzen"
