"""Transaktions-Export (Alltags-Export der gefilterten Liste als CSV/JSON).
Ergänzt DSGVO-Voll-Export (/api/account/export) und Steuer-EÜR (/api/steuer/export)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from moneyapp import main as mm

FIX = Path(__file__).resolve().parent / "fixtures"


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _setup(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    c.post("/api/import", json={"inhalt": (FIX / "sparkasse.csv").read_text(encoding="utf-8"),
                                "format": "csv", "zielkonto": giro})
    return giro


def test_export_csv(tmp_path):
    with _client(tmp_path) as c:
        _setup(c)
        r = c.get("/api/buchungen/export?format=csv")
        assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        zeilen = r.text.strip().splitlines()
        assert zeilen[0].startswith("Datum;Gegenpartei;")
        assert len(zeilen) == 1 + 4                       # Kopf + 4 Buchungen
        assert any("Hausverwaltung Stadt" in z for z in zeilen)


def test_export_json_und_filter(tmp_path):
    with _client(tmp_path) as c:
        _setup(c)
        r = c.get("/api/buchungen/export?format=json&q=Miete")
        assert r.status_code == 200 and "application/json" in r.headers["content-type"]
        daten = r.json()
        assert len(daten) == 1 and "Hausverwaltung" in daten[0]["gegenpartei"]


def test_export_format_invalid(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/buchungen/export?format=xml").status_code == 400


def test_liste_unveraendert(tmp_path):
    """Refactor-Sicherung: die normale Liste liefert weiter wie zuvor."""
    with _client(tmp_path) as c:
        _setup(c)
        assert len(c.get("/api/buchungen").json()) == 4
        assert len(c.get("/api/buchungen?q=Miete").json()) == 1


def test_export_nicht_vom_listen_limit_beschnitten(tmp_path):
    """Z-3 (28.06.): der Export liefert ALLE gefilterten Buchungen — auch wenn ein
    kleiner Listen-``limit`` gesetzt ist. Vorher cappte ``_buchungen_laden`` hart bei
    5000 ⇒ ein Nutzer mit >5000 Transaktionen bekam einen STILL trunkierten Steuer-/
    Archiv-Export (Datenverlust). Export ruft jetzt ``limit=0`` (= alles); die Liste
    bleibt durch ihren eigenen limit geschützt."""
    with _client(tmp_path) as c:
        _setup(c)                                          # 4 Buchungen
        # Liste respektiert einen kleinen limit ...
        assert len(c.get("/api/buchungen?limit=2").json()) == 2
        # ... der Export NICHT (liefert alle 4, nicht vom Listen-limit beschnitten).
        assert len(c.get("/api/buchungen/export?format=json").json()) == 4
        assert len(c.get("/api/buchungen/export?format=csv").text.strip().splitlines()) == 1 + 4
        # limit<=0 ist allein dem Export vorbehalten: die Liste kann nicht unbegrenzt
        # werden (max(1,limit) ⇒ limit=0 an der Liste verhält sich wie limit=1).
        assert len(c.get("/api/buchungen?limit=0").json()) == 1
