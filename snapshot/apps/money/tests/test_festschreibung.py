"""test_festschreibung.py — GoBD-Festschreibungs-Strecke (Vertrag §6.3 / §7).

happy path offen→versiegelt (In-Process-Chronist) · 409 in allen Schreibpfaden · offen-Fenster blockt
(BZ-C-5) · salden_hash = Perioden-Salden · Crash ⇒ idempotente Nachholung · Chronist tot ⇒ Fehler
(nie „ok", C-9) · Replay-Gegenprobe der voll-Festschreibung.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from appkit import chronik
from appkit import chronik_pruef as P
from appkit.db import new_id, now_iso
from moneyapp import chronik_naht
from moneyapp import main as mm


@pytest.fixture(autouse=True)
def _reset():
    chronik.reset_kontext()
    yield
    chronik.reset_kontext()


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _konten(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    aufw = c.post("/api/konten", json={"name": "Aufwand", "typ": "expense"}).json()["id"]
    return giro, aufw


def _buche(c, giro, aufw, betrag, datum):
    return c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                          "betrag": betrag, "datum": datum}).json()["id"]


def _events_art(db, art):
    return db.get_conn().execute(
        "SELECT COUNT(*) FROM chronik_ausgang WHERE art=?", (art,)).fetchone()[0]


def test_happy_path_offen_versiegelt(tmp_path):
    with _client(tmp_path) as c:
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "42,00", "2026-05-04")
        r = c.post("/api/festschreibung", json={"zeitraum": "2026-05"}).json()
        assert r["ok"] and r["beweisgrad"] == "voll" and r["epoche"] >= 1
        assert r["siegel_hash"].startswith("sha256:")
        liste = c.get("/api/festschreibungen").json()
        assert liste[0]["zeitraum"] == "2026-05" and liste[0]["status"] == "versiegelt"
        assert liste[0]["siegel_hash"] == r["siegel_hash"]
        # die Kette selbst verifiziert offline
        P.pruefe(chronik_naht.chronik_dir())


def test_zweite_festschreibung_desselben_monats_409(tmp_path):
    with _client(tmp_path) as c:
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "5,00", "2026-05-06")
        assert c.post("/api/festschreibung", json={"zeitraum": "2026-05"}).json()["ok"]
        assert c.post("/api/festschreibung", json={"zeitraum": "2026-05"}).status_code == 409


def test_laufender_monat_wird_abgelehnt(tmp_path):
    with _client(tmp_path) as c:
        aktuell = now_iso()[:7]
        assert c.post("/api/festschreibung", json={"zeitraum": aktuell}).status_code == 400
        assert c.post("/api/festschreibung", json={"zeitraum": "2026-13"}).status_code == 400


def test_alle_wertbildenden_pfade_409_nach_festschreibung(tmp_path):
    with _client(tmp_path) as c:
        giro, aufw = _konten(c)
        b = _buche(c, giro, aufw, "10,00", "2026-04-03")
        c.post("/api/festschreibung", json={"zeitraum": "2026-04"})
        # neue Buchung / Split / Serie / Storno im versiegelten April ⇒ 409
        assert c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                              "betrag": "1,00", "datum": "2026-04-20"}).status_code == 409
        assert c.post("/api/buchungen/split", json={"konto_id": giro, "datum": "2026-04-21",
               "zeilen": [{"betrag": "1,00", "richtung": "ausgabe"}]}).status_code == 409
        assert c.delete(f"/api/buchungen/{b}").status_code == 409          # Storno im gesperrten Monat


def test_offen_fenster_blockt_schreibpfade(tmp_path):
    """BZ-C-5: schon das kurze ``offen``-Fenster einer laufenden Festschreibung sperrt Schreibpfade."""
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        b = _buche(c, giro, aufw, "3,00", "2026-05-08")
        ts = now_iso()
        db.get_conn().execute(
            "INSERT INTO festschreibungen (id,user_id,zeitraum,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)", (new_id(), "dizzi", "2026-05", "offen", ts, ts))
        db.get_conn().commit()
        assert c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                              "betrag": "1,00", "datum": "2026-05-09"}).status_code == 409
        assert c.delete(f"/api/buchungen/{b}").status_code == 409


def test_salden_hash_ist_perioden_saldo(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "20,00", "2026-05-02")
        _buche(c, giro, aufw, "30,00", "2026-05-03")
        c.post("/api/festschreibung", json={"zeitraum": "2026-05"})
        ev = json.loads(db.get_conn().execute(
            "SELECT nutzlast FROM chronik_ausgang WHERE art='money.festschreibung'").fetchone()[0])
        erwartet, _ = chronik_naht.salden_hash_des_zeitraums(db.get_conn(), "2026-05")
        assert ev["salden_hash"] == erwartet and ev["zeitraum"] == "2026-05"


def test_crash_offen_wird_idempotent_nachgeholt(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "8,00", "2026-05-11")
        # Crash-Zustand simulieren: Zeile 'offen' + Ereignis liegen, Siegel fehlt (zwischen (3) und (5))
        ts = now_iso()
        with db.transaktion() as conn:
            sh, _ = chronik_naht.salden_hash_des_zeitraums(conn, "2026-05")
            bis_i = chronik_naht.outbox_spitze(conn)
            conn.execute("INSERT INTO festschreibungen (id,user_id,zeitraum,status,bis_i,salden_hash,"
                         "beweisgrad,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (new_id(), "dizzi", "2026-05", "offen", bis_i, sh, "voll", ts, ts))
            chronik_naht.schreibe_festschreibung(conn, "dizzi", zeitraum="2026-05",
                                                 bis_i=bis_i, salden_hash=sh, beweisgrad="voll")
        # erneuter Aufruf: KEIN zweites Ereignis, nur die Siegel-Referenz wird nachgeholt
        r = c.post("/api/festschreibung", json={"zeitraum": "2026-05"}).json()
        assert r["ok"]
        assert _events_art(db, "money.festschreibung") == 1          # idempotent (kein Duplikat)
        assert c.get("/api/festschreibungen").json()[0]["status"] == "versiegelt"


def test_chronist_tot_ergibt_fehler_nie_ok(tmp_path, monkeypatch):
    """C-9: ohne Siegel KEIN „ok" — der Endpoint meldet 503, die Zeile bleibt 'offen' (idempotent retrybar)."""
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "6,00", "2026-05-13")

        class _ToterChronist:
            def flush_und_warte(self, *a, **k):
                raise RuntimeError("Chronist nicht erreichbar")

        monkeypatch.setattr(chronik_naht, "baue_chronist", lambda *a, **k: _ToterChronist())
        r = c.post("/api/festschreibung", json={"zeitraum": "2026-05"})
        assert r.status_code == 503 and r.json()["status"] == "offen"
        # das Ereignis liegt (offen), aber nichts wurde versiegelt
        assert _events_art(db, "money.festschreibung") == 1
        assert c.get("/api/festschreibungen").json()[0]["status"] == "offen"


def test_replay_gegenprobe_bestaetigt_voll(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro, aufw = _konten(c)
        _buche(c, giro, aufw, "11,00", "2026-05-01")
        _buche(c, giro, aufw, "22,00", "2026-05-02")
        c.post("/api/festschreibung", json={"zeitraum": "2026-05"})
    rc, zeilen = P.salden_replay(chronik_naht.chronik_dir(), db.db_path)
    assert rc == P.EXIT_GRUEN
    assert any("Festschreibung" in z for z in zeilen)      # voll-Festschreibung gegen die Kette bestätigt
