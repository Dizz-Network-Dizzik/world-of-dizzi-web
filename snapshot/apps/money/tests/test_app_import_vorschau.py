"""P2: Import-Assistent (Dry-Run-Vorschau) — zeigt VOR dem Schreiben neu vs.
Dublette + Regel-Kategorie-Vorschlag; schreibt nichts."""

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


def test_vorschau_neu_dann_dublette(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        csv = _lies("sparkasse.csv")
        v = c.post("/api/import/vorschau", json={"inhalt": csv, "format": "csv",
                                                 "zielkonto": giro}).json()
        assert v["gefunden"] == 4 and v["neu"] == 4 and v["dupliziert"] == 0
        assert len(v["zeilen"]) == 4 and not any(z["dupliziert"] for z in v["zeilen"])
        # Vorschau schreibt NICHTS:
        assert c.get("/api/buchungen").json() == []
        # echter Import, dann erneute Vorschau ⇒ alles Dublette
        c.post("/api/import", json={"inhalt": csv, "format": "csv", "zielkonto": giro})
        v2 = c.post("/api/import/vorschau", json={"inhalt": csv, "format": "csv",
                                                  "zielkonto": giro}).json()
        assert v2["neu"] == 0 and v2["dupliziert"] == 4
        assert all(z["dupliziert"] for z in v2["zeilen"])


def test_vorschau_regel_vorschlag(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        kid = c.post("/api/kategorien", json={"name": "Lebensmittel"}).json()["id"]
        c.post("/api/regeln", json={"muster": "rewe", "feld": "gegenpartei", "kategorie_id": kid})
        v = c.post("/api/import/vorschau", json={"inhalt": _lies("sparkasse.csv"),
                                                 "format": "csv", "zielkonto": giro}).json()
        rewe = next(z for z in v["zeilen"] if "REWE" in z["gegenpartei"])
        assert rewe["kategorie_vorschlag"] == "Lebensmittel"


def test_vorschau_konto_pflicht(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/import/vorschau", json={"inhalt": "x", "format": "csv",
                                                    "zielkonto": "weg"}).status_code == 404
