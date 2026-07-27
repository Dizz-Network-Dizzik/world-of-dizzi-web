"""Korrektur & Pflege: Buchung stornieren (Soft-Delete der ganzen Buchung) +
Konto umbenennen/löschen (geschützt). Kern-Garantie: nach Storno bleibt die
globale Konsistenz (Summe aller aktiven Postings = 0)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from moneyapp import main as mm

FIX = Path(__file__).resolve().parent / "fixtures"


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _giro(c):
    return c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]


def test_buchung_stornieren_haelt_konsistenz(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        c.post("/api/import", json={"inhalt": (FIX / "sparkasse.csv").read_text(encoding="utf-8"),
                                    "format": "csv", "zielkonto": giro})
        bs = c.get("/api/buchungen").json()
        assert len(bs) == 4
        miete = next(b for b in bs if "Hausverwaltung" in b["gegenpartei"])
        assert c.delete(f"/api/buchungen/{miete['id']}").json()["ok"]
        # verschwindet aus der Liste + Saldo passt sich an
        rest = c.get("/api/buchungen").json()
        assert len(rest) == 3 and all(b["id"] != miete["id"] for b in rest)
        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        assert konten["Giro"]["saldo"] == "3641.27"          # 2815,77 + 825,50 zurück
        # globale Konsistenz: aktive Postings summieren zu 0
        db = c.app.state.db
        s = db.get_conn().execute(
            "SELECT COALESCE(SUM(betrag),0) AS s FROM postings WHERE deleted_at IS NULL").fetchone()["s"]
        assert s == 0


def test_storno_unbekannt_404(tmp_path):
    with _client(tmp_path) as c:
        assert c.delete("/api/buchungen/gibtsnicht").status_code == 404


def test_konto_umbenennen(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        assert c.put(f"/api/konten/{giro}", json={"name": "Hauptkonto"}).json()["ok"]
        konten = {k["id"]: k for k in c.get("/api/konten").json()}
        assert konten[giro]["name"] == "Hauptkonto"
        assert c.put(f"/api/konten/{giro}", json={"name": "  "}).status_code == 400
        assert c.put("/api/konten/weg", json={"name": "X"}).status_code == 404


def test_konto_loeschen_geschuetzt(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        leer = c.post("/api/konten", json={"name": "Leer", "typ": "asset"}).json()["id"]
        # leeres Konto löschbar
        assert c.delete(f"/api/konten/{leer}").json()["ok"]
        assert all(k["id"] != leer for k in c.get("/api/konten").json())
        # bebuchtes Konto NICHT löschbar (Schutz)
        c.post("/api/import", json={"inhalt": (FIX / "sparkasse.csv").read_text(encoding="utf-8"),
                                    "format": "csv", "zielkonto": giro})
        r = c.delete(f"/api/konten/{giro}")
        assert r.status_code == 400 and "stornieren" in r.json()["error"]


def test_konto_loeschen_nach_storno(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/konten", json={"name": "A", "typ": "asset"}).json()["id"]
        b = c.post("/api/konten", json={"name": "B", "typ": "expense"}).json()["id"]
        bid = c.post("/api/buchungen", json={"von_konto": a, "nach_konto": b,
                                             "betrag": "10,00"}).json()["id"]
        assert c.delete(f"/api/konten/{a}").status_code == 400   # bebucht
        c.delete(f"/api/buchungen/{bid}")                        # storniert
        assert c.delete(f"/api/konten/{a}").json()["ok"]         # jetzt löschbar
