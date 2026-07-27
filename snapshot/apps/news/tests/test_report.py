"""Sektor-Reports: Tiefe-Mechanik, Pflicht-Sektor, Erstellung, Endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from newsapp.main import build_app
from newsapp.report import (SEKTOR_IDS, normalisiere_sektoren,
                            report_erstellen, tiefe_fuer)


class _Antwort:
    def __init__(self, status_code: int, inhalt: str):
        self.status_code = status_code
        self._inhalt = inhalt

    def json(self):
        return {"message": {"content": self._inhalt}}


def _post_mit(inhalt: str, status: int = 200):
    return lambda url, daten: _Antwort(status, inhalt)


def _archiv_capture(store):
    """Mock für den Archiv-POST (archiviere ruft mit keyword ``json=``)."""
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "uebersprungen", "grund": "manuell"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post


def test_tiefe_skaliert_invers():
    assert tiefe_fuer(1)["stufe"] == "tief"
    assert tiefe_fuer(3)["stufe"] == "tief"
    assert tiefe_fuer(5)["stufe"] == "mittel"
    assert tiefe_fuer(12)["stufe"] == "kompakt"
    # weniger Sektoren ⇒ MEHR Artikel je Sektor betrachtet
    assert tiefe_fuer(1)["artikel_je_sektor"] > tiefe_fuer(12)["artikel_je_sektor"]


def test_geopolitik_ist_pflicht_und_zuletzt():
    assert normalisiere_sektoren([]) == SEKTOR_IDS
    assert normalisiere_sektoren(None) == SEKTOR_IDS
    assert normalisiere_sektoren(["ki"]) == ["ki", "geopolitik"]
    assert normalisiere_sektoren(["geopolitik", "finanzen"]) == ["finanzen", "geopolitik"]
    assert normalisiere_sektoren(["quatsch"]) == ["geopolitik"]   # invalide raus


def test_report_erstellen_ehrlich():
    def holen(quell_sektoren, limit):
        return [{"titel": "T", "quelle": "q", "zusammenfassung": "Z"}]

    out = report_erstellen(holen, ["ki"], http_post=_post_mit(
        json.dumps({"punkte": ["Punkt eins", "Punkt zwei"]})))
    assert out["tiefe"] == "tief" and len(out["abschnitte"]) == 2
    assert out["abschnitte"][0]["punkte"] == ["Punkt eins", "Punkt zwei"]
    # leerer Pool ⇒ ehrlicher Hinweis statt KI-Lauf
    leer = report_erstellen(lambda q, l: [], ["ki"], http_post=None)
    assert leer["abschnitte"][0]["hinweis"] == "keine Artikel im Bestand"
    # kaputte KI-Antwort ⇒ Abschnitt als fehlgeschlagen markiert
    kaputt = report_erstellen(holen, ["ki"], http_post=_post_mit("kein json"))
    assert kaputt["abschnitte"][0]["hinweis"] == "KI-Abschnitt fehlgeschlagen"


def test_report_endpoints(tmp_path, monkeypatch):
    import newsapp.main as m
    monkeypatch.setattr(m, "_lade_feed", lambda url: [{
        "titel": "Test", "link": f"https://x.test/{hash(url)}",
        "zusammenfassung": "Inhalt", "published": None}])
    archiv = []
    app = build_app(data_dir=tmp_path, start_timer=False,
                    http_post=_post_mit(json.dumps({"punkte": ["P1"]})),
                    archiv_post=_archiv_capture(archiv))
    with TestClient(app) as client:
        assert len(client.get("/api/sektoren").json()) == 12
        client.post("/api/abrufen")
        r = client.post("/api/reports", json={"sektoren": ["ki", "finanzen"]}).json()
        assert r["tiefe"] == "tief"
        assert [a["sektor"] for a in r["abschnitte"]] == ["finanzen", "ki", "geopolitik"]
        liste = client.get("/api/reports").json()
        assert len(liste) == 1 and liste[0]["ausloeser"] == "manuell"
        detail = client.get(f"/api/reports/{liste[0]['id']}").json()
        assert detail["abschnitte"][0]["punkte"] == ["P1"]
        assert client.get("/api/reports/fehlt").status_code == 404
        assert any(e["action"] == "report_erstellt"
                   for e in client.get("/api/audit").json())
        # V2 (docs/26): Report-Erstellung versucht Auto-Archiv an Memory (Regel gated)
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "news" and u["strom"] == "sektor_report"
        assert u["explizit"] is False and u["ref"].startswith("news:report:")
        # docs/26 §9.1: KEINE Sektor-Tags mehr (Lärm-Reduktion) — Sektoren stehen als
        # ##-Überschriften im Body, Herkunftslabel „News" vergibt Memory zentral.
        assert u["tags"] == []
        assert "## finanzen" in u["inhalt"].lower()
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        # V2: expliziter „in Memory archivieren"-Knopf ⇒ explizit=True (schlägt jede Regel)
        rid = liste[0]["id"]
        assert client.post(f"/api/reports/{rid}/archivieren").status_code == 200
        assert archiv[-1]["umschlag"]["explizit"] is True
        assert client.post("/api/reports/fehlt/archivieren").status_code == 404