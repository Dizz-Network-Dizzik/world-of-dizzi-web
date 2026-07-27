"""Pro-Quelle-Gesundheit (Backlog docs/33): fetch_all hält je Quelle fest, ob der
letzte Abruf erfolgreich war (``letzter_ok``, Zähler 0) oder fehlerhaft
(``letzter_fehler``, Zähler hoch); ``/api/quellen`` liefert das mit. Abruf gemockt."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsapp import main as nm

OK_URL = "https://ok.test/feed"
KAPUTT_URL = "https://kaputt.test/feed"


def _feed(url):
    if url == KAPUTT_URL:
        raise RuntimeError("offline")
    if url == OK_URL:
        return [{"titel": "A", "link": "https://ok.test/a", "zusammenfassung": "", "published": None}]
    return []                                    # Seed-Quellen: leer, aber „ok"


def test_quelle_gesundheit_ok_fehler_und_erholung(tmp_path, monkeypatch):
    monkeypatch.setattr(nm, "_lade_feed", _feed)
    with TestClient(nm.build_app(data_dir=tmp_path, start_timer=False)) as c:
        c.post("/api/quellen", json={"name": "Heile", "url": OK_URL, "sektor": "tech"})
        c.post("/api/quellen", json={"name": "Kaputt", "url": KAPUTT_URL, "sektor": "tech"})

        assert c.post("/api/abrufen").json()["fehler"] == 1     # genau die kaputte Quelle
        q = {x["url"]: x for x in c.get("/api/quellen").json()}
        assert q[OK_URL]["letzter_ok"] and q[OK_URL]["fehler_zaehler"] == 0
        assert q[OK_URL]["letzter_fehler"] is None
        assert q[KAPUTT_URL]["letzter_fehler"] and q[KAPUTT_URL]["fehler_zaehler"] == 1
        assert q[KAPUTT_URL]["letzter_ok"] is None

        # Zweiter Lauf: kaputte Quelle bleibt kaputt ⇒ Zähler steigt.
        c.post("/api/abrufen")
        assert {x["url"]: x for x in c.get("/api/quellen").json()}[KAPUTT_URL]["fehler_zaehler"] == 2

        # Erholung: liefert wieder ⇒ Zähler zurück auf 0 + letzter_ok gesetzt.
        monkeypatch.setattr(nm, "_lade_feed", lambda url: (
            [{"titel": "Z", "link": "https://kaputt.test/z", "zusammenfassung": "", "published": None}]
            if url == KAPUTT_URL else []))
        c.post("/api/abrufen")
        geheilt = {x["url"]: x for x in c.get("/api/quellen").json()}[KAPUTT_URL]
        assert geheilt["fehler_zaehler"] == 0 and geheilt["letzter_ok"]
