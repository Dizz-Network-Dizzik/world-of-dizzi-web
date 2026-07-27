"""P2: Reconciliation-Flow — Kontoauszug-Saldo ↔ Ledger zum Stichtag abgleichen,
„abgeglichen bis"-Marke (Vertrauensanker für den Double-Entry-Kern)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _setup(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    ek = c.post("/api/konten", json={"name": "Start", "typ": "equity"}).json()["id"]
    c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                   "betrag": "1000,00", "datum": "2026-06-10"})
    c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": ek,
                                   "betrag": "200,00", "datum": "2026-06-20"})
    return giro


def test_abgleich_pruefen_stichtag(tmp_path):
    with _client(tmp_path) as c:
        giro = _setup(c)
        # bis 15.06.: nur die 1000er-Buchung zählt (200er ist am 20.06.)
        chk = c.get(f"/api/konten/{giro}/abgleich?bis=2026-06-15&saldo=1000,00").json()
        assert chk["ledger_saldo_text"] == "1000.00"
        assert chk["differenz"] == 0 and chk["abgeglichen"] is True
        # bis heute: 1000 − 200 = 800
        chk2 = c.get(f"/api/konten/{giro}/abgleich?bis=2026-12-31&saldo=800,00").json()
        assert chk2["ledger_saldo_text"] == "800.00" and chk2["abgeglichen"] is True


def test_abgleich_differenz_und_markieren(tmp_path):
    with _client(tmp_path) as c:
        giro = _setup(c)
        chk = c.get(f"/api/konten/{giro}/abgleich?bis=2026-06-15&saldo=900,00").json()
        assert chk["differenz"] == -10000 and chk["abgeglichen"] is False   # 900 − 1000
        # Markieren bei Differenz ⇒ NICHT abgeglichen
        m = c.post(f"/api/konten/{giro}/abgleich", json={"bis": "2026-06-15", "saldo": "900,00"}).json()
        assert m["ok"] is False
        # Markieren bei Übereinstimmung ⇒ Marke gesetzt
        m2 = c.post(f"/api/konten/{giro}/abgleich", json={"bis": "2026-06-15", "saldo": "1000,00"}).json()
        assert m2["ok"] is True and m2["abgeglichen_bis"] == "2026-06-15"
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["abgeglichen_bis"] == "2026-06-15"


def test_abgleich_konto_unbekannt(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/konten/weg/abgleich?bis=2026-06-15").status_code == 404
