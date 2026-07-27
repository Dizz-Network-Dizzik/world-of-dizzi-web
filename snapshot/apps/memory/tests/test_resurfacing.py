"""Resurfacing (P3.2): „An diesem Tag" (gleicher Monat-Tag aus früheren Jahren)
+ „Zufallsfund" (zufällige Notiz älter als 30 Tage). Readwise-Muster.

created_at wird direkt gesetzt (app.state.db) — die API stempelt sonst „jetzt"."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from archivapp import main as am


def _app(tmp_path):
    return am.build_app(data_dir=tmp_path, start_import_timer=False)


def _neu(c, titel, inhalt=""):
    return c.post("/api/notizen", json={"titel": titel, "inhalt": inhalt}).json()["id"]


def _setze_datum(app, nid, iso):
    conn = app.state.db.get_conn()
    conn.execute("UPDATE notizen SET created_at=? WHERE id=?", (iso, nid))
    conn.commit()


def test_an_diesem_tag_nur_fruehere_jahre(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        heute = date.today()
        mmdd = heute.strftime("%m-%d")
        jubilaeum = _neu(c, "Vor einem Jahr")
        _setze_datum(app, jubilaeum, f"{heute.year - 1}-{mmdd}T10:00:00+00:00")
        # Notiz im AKTUELLEN Jahr mit gleichem Monat-Tag ⇒ KEIN Rückblick.
        heutiges = _neu(c, "Heute angelegt")
        _setze_datum(app, heutiges, f"{heute.year}-{mmdd}T11:00:00+00:00")

        r = c.get("/api/resurfacing").json()
        ids = [n["id"] for n in r["an_diesem_tag"]]
        assert jubilaeum in ids
        assert heutiges not in ids
        eintrag = next(n for n in r["an_diesem_tag"] if n["id"] == jubilaeum)
        assert eintrag["jahre_her"] == 1 and eintrag["titel"] == "Vor einem Jahr"


def test_zufall_nur_aelter_als_30_tage(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        heute = date.today()
        alt = _neu(c, "Alte Notiz")
        _setze_datum(app, alt, f"{heute.year - 1}-01-15T08:00:00+00:00")
        frisch = _neu(c, "Frische Notiz")   # bleibt „jetzt" (< 30 Tage)

        r = c.get("/api/resurfacing").json()
        # Nur die alte Notiz ist älter als 30 Tage ⇒ der Zufallsfund ist eindeutig.
        assert r["zufall"] is not None
        assert r["zufall"]["id"] == alt
        assert r["zufall"]["id"] != frisch


def test_leerer_vault(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        r = c.get("/api/resurfacing").json()
        assert r["an_diesem_tag"] == [] and r["zufall"] is None
