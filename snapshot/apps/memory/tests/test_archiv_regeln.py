"""Archiv-Regeln (docs/26 §8): Steuerung automatisch / auf Zuruf je (app, strom).
Default manuell (nichts flutet), explizit schlägt jede Regel, auto/gefiltert, Selbst-Registrierung."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def test_default_manuell_ueberspringt_und_selbstregistriert(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Artikel", "inhalt": "x", "app": "news", "strom": "artikel"}).json()
        assert r["status"] == "uebersprungen" and r["modus"] == "manuell"
        assert c.get("/api/notizen").json() == []          # keine Notiz angelegt
        regeln = c.get("/api/archiv-regeln").json()          # aber Regel sichtbar
        assert any(g["app"] == "news" and g["strom"] == "artikel"
                   and g["modus"] == "manuell" for g in regeln)


def test_explizit_schlaegt_jede_regel(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Artikel", "inhalt": "x", "app": "news", "strom": "artikel",
            "explizit": True}).json()
        assert r["status"] == "archiviert" and r["id"]
        assert len(c.get("/api/notizen").json()) == 1


def test_auto_archiviert(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/archiv-regeln", json={"app": "news", "strom": "wochenbericht",
                                          "modus": "auto"})
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Wochenbericht", "inhalt": "…", "app": "news",
            "strom": "wochenbericht"}).json()
        assert r["status"] == "archiviert"


def test_auto_gefiltert_tag_und_schluessel(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/archiv-regeln", json={
            "app": "news", "strom": "artikel", "modus": "auto_gefiltert",
            "filter": {"tags": ["wichtig"], "schluessel": "ezb"}})
        ja = c.post("/api/querverbindung/archivieren", json={
            "titel": "EZB-Entscheid", "inhalt": "Leitzins", "app": "news",
            "strom": "artikel", "tags": ["wichtig"], "ref": "n:1"}).json()
        assert ja["status"] == "archiviert"
        nein = c.post("/api/querverbindung/archivieren", json={
            "titel": "EZB-Entscheid", "inhalt": "Leitzins", "app": "news",
            "strom": "artikel", "tags": ["egal"], "ref": "n:2"}).json()
        assert nein["status"] == "uebersprungen" and nein["grund"] == "filter-kein-treffer"


def test_regel_ziel_ordner_und_sensibel_override(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/archiv-regeln", json={
            "app": "trading", "strom": "report", "modus": "auto",
            "ziel_ordner": "Trading/Reports", "sensibel": True})
        r = c.post("/api/querverbindung/archivieren", json={
            "titel": "Tagesreport", "inhalt": "…", "app": "trading",
            "strom": "report"}).json()
        assert r["status"] == "archiviert"
        det = c.get("/api/notizen/" + r["id"]).json()
        assert det["sensibel"] is True
        assert {"Trading", "Reports"} <= {o["name"] for o in c.get("/api/ordner").json()}


def test_regel_loeschen(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/archiv-regeln", json={"app": "news", "strom": "x", "modus": "auto"})
        assert any(g["app"] == "news" and g["strom"] == "x"
                   for g in c.get("/api/archiv-regeln").json())
        assert c.delete("/api/archiv-regeln?app=news&strom=x").status_code == 200
        assert not any(g["app"] == "news" and g["strom"] == "x"
                       for g in c.get("/api/archiv-regeln").json())


def test_put_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.put("/api/archiv-regeln",
                     json={"app": "news", "modus": "quatsch"}).status_code == 400
        assert c.put("/api/archiv-regeln",
                     json={"app": "", "modus": "auto"}).status_code == 400
