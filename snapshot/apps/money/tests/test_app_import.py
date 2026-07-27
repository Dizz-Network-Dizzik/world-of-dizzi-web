"""Import-Endpoint end-to-end (Teil A): POST /api/import über alle drei Formate,
DEDUPE, Sammelkonto-Gegenbuchung und die globale Konsistenz-Probe.

Kern-Garantie: Egal über welches Format importiert wird — die Postings-Tabelle
bleibt global balanciert (Summe aller Beträge 0), und ein zweiter Import
desselben Auszugs erzeugt KEINE Dubletten."""

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


def test_import_csv_bucht_und_balanciert(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        r = c.post("/api/import", json={
            "inhalt": _lies("sparkasse.csv"), "format": "csv", "zielkonto": giro})
        assert r.status_code == 200
        j = r.json()
        assert j["importiert"] == 4 and j["dupliziert"] == 0

        konten = {k["name"]: k for k in c.get("/api/konten").json()}
        # 2450 − 825,50 − 43,29 + 1234,56 = 2815,77
        assert konten["Giro"]["saldo"] == "2815.77"
        assert "Nicht zugeordnet" in konten          # Sammelkonto automatisch angelegt

        db = c.app.state.db
        s = db.get_conn().execute(
            "SELECT COALESCE(SUM(betrag),0) AS s FROM postings").fetchone()["s"]
        assert s == 0                                 # global balanciert


def test_import_dedupe_zweiter_lauf(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        a = c.post("/api/import", json={
            "inhalt": _lies("sparkasse.csv"), "format": "auto", "zielkonto": giro}).json()
        assert a["importiert"] == 4
        b = c.post("/api/import", json={
            "inhalt": _lies("sparkasse.csv"), "format": "auto", "zielkonto": giro}).json()
        assert b["importiert"] == 0 and b["dupliziert"] == 4   # idempotent


def test_import_camt_und_mt940(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        camt = c.post("/api/import", json={
            "inhalt": _lies("statement.camt053.xml"), "format": "camt",
            "zielkonto": giro}).json()
        assert camt["importiert"] == 3
        # MT940 desselben Auszugs: gleiche Referenzen ⇒ als Dubletten erkannt.
        mt = c.post("/api/import", json={
            "inhalt": _lies("auszug.mt940.sta"), "format": "mt940",
            "zielkonto": giro}).json()
        assert mt["dupliziert"] >= 1                  # E2E-Referenzen matchen camt


def test_import_zielkonto_pflicht(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/import", json={
            "inhalt": _lies("sparkasse.csv"), "format": "csv",
            "zielkonto": "gibtsnicht"})
        assert r.status_code == 404


def test_import_falsches_zielkonto_typ(tmp_path):
    with _client(tmp_path) as c:
        ausg = c.post("/api/konten", json={"name": "Essen", "typ": "expense"}).json()["id"]
        r = c.post("/api/import", json={
            "inhalt": _lies("sparkasse.csv"), "format": "csv", "zielkonto": ausg})
        assert r.status_code == 400


def test_import_muell_400(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        r = c.post("/api/import", json={
            "inhalt": "weder csv noch xml noch mt940", "format": "auto",
            "zielkonto": giro})
        assert r.status_code == 400


def test_import_riesen_betrag_kein_crash(tmp_path):
    """AT-1 (Angreifer-5, 28.06.): ein absurd großer Betrag (kaputte/böswillige Datei)
    führt NICHT zu OverflowError/500 beim INSERT — die Zeile wird beim Parsen
    abgewiesen (Minor-Units überschreiten SQLites 64-bit-INTEGER). Eine danebenstehende
    GÜLTIGE Zeile importiert normal; das Ledger bleibt balanciert."""
    with _client(tmp_path) as c:
        giro = _giro(c)
        csv = ("Datum;Empfänger;Verwendungszweck;Betrag;Währung\n"
               "01.01.2026;Gut;OK;-12,50;EUR\n"
               "02.01.2026;Boese;Overflow;99999999999999999999999999;EUR")
        r = c.post("/api/import", json={"inhalt": csv, "format": "csv", "zielkonto": giro})
        assert r.status_code == 200                 # KEIN 500/OverflowError
        assert r.json()["importiert"] == 1          # nur die gültige Zeile, böse übersprungen
        s = c.app.state.db.get_conn().execute(
            "SELECT COALESCE(SUM(betrag),0) AS s FROM postings").fetchone()["s"]
        assert s == 0                               # Ledger balanciert (keine Fehlbuchung)


def test_import_riesen_feld_400(tmp_path):
    """AT-2: ein Feld über dem csv-Modul-Limit (>128 KB) ⇒ 400 (csv.Error gefangen),
    kein 500/Crash."""
    with _client(tmp_path) as c:
        giro = _giro(c)
        r = c.post("/api/import", json={"inhalt": "A" * 2_000_000, "format": "csv",
                                        "zielkonto": giro})
        assert r.status_code == 400
