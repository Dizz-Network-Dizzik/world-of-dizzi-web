"""test_chronik_anbindung.py — Money-Schreibpfade → Chronik-Outbox (Vertrag §6.2 / §7).

Jeder der fünf wertbildenden + vier UPDATE-Pfade erzeugt exakt seine Ereignisse in DERSELBEN Txn
(C-1, Rollback-Test) · 409/Erlaubnis-Matrix der UPDATE-Pfade (BZ-C-2) · Umklassung/Beleg-Formate (§3) ·
Freitexte + Anzeigenamen erscheinen NIE im Klartext in den erzeugten Segmenten (BZ-C-10).
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from appkit import chronik
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
    miete = c.post("/api/konten", json={"name": "Miete", "typ": "expense"}).json()["id"]
    return giro, miete


def _events(app):
    return [dict(r) for r in app.state.db.get_conn().execute(
        "SELECT art, nutzlast, subjekt FROM chronik_ausgang ORDER BY i").fetchall()]


def _arten(app):
    return [e["art"] for e in _events(app)]


# ── wertbildende Pfade ───────────────────────────────────────────────────────

def test_buchung_erzeugt_ein_ereignis_mit_formaten(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        r = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                           "betrag": "750,00", "datum": "2026-05-15", "notiz": "Miete Mai"})
        bid = r.json()["id"]
        ev = _events(c.app)
        assert [e["art"] for e in ev] == ["money.buchung"]
        nutz = json.loads(ev[0]["nutzlast"])
        assert nutz["buchung_id"] == bid and nutz["datum"] == "2026-05-15" and nutz["quelle"] == "manuell"
        assert sum(int(p["betrag_minor"]) for p in nutz["postings"]) == 0        # balanciert, Dezimal-String
        assert all(isinstance(p["betrag_minor"], str) for p in nutz["postings"])  # C-2
        assert nutz["notiz_hash"].startswith("hmac256:") and "notiz" not in nutz  # C-15 (kein Klartext)
        assert ev[0]["subjekt"].startswith("u:") and "dizzi" not in ev[0]["subjekt"]  # BZ-C-10


def test_split_erzeugt_je_zeile_ein_ereignis(tmp_path):
    with _client(tmp_path) as c:
        giro, _ = _konten(c)
        kat = c.post("/api/kategorien", json={"name": "Haushalt"}).json()["id"]
        c.post("/api/buchungen/split", json={"konto_id": giro, "datum": "2026-05-02", "gegenpartei": "REWE",
               "zeilen": [{"betrag": "70,00", "richtung": "ausgabe", "kategorie_id": kat},
                          {"betrag": "30,00", "richtung": "ausgabe"}]})
        assert _arten(c.app) == ["money.buchung", "money.buchung"]
        n0 = json.loads(_events(c.app)[0]["nutzlast"])
        assert n0["kategorie_id"] == kat and n0["gegenpartei_hash"].startswith("hmac256:")


def test_import_erzeugt_je_bewegung_ein_ereignis(tmp_path):
    with _client(tmp_path) as c:
        giro, _ = _konten(c)
        csv = "Datum;Betrag;Empfaenger\n2026-05-03;-12,50;Baecker\n2026-05-04;-8,00;Kiosk\n"
        r = c.post("/api/import", json={"zielkonto": giro, "inhalt": csv, "format": "csv"})
        assert r.json()["importiert"] == 2
        arten = _arten(c.app)
        assert arten.count("money.buchung") == 2
        assert all(json.loads(e["nutzlast"])["quelle"].startswith("import:")
                   for e in _events(c.app) if e["art"] == "money.buchung")


def test_serie_verbuchen_erzeugt_ereignis(tmp_path):
    with _client(tmp_path) as c:
        giro, _ = _konten(c)
        sid = c.post("/api/wiederkehr", json={"name": "Netflix", "betrag": "12,99", "richtung": "ausgabe",
                                              "intervall_tage": 30, "intervall": "monatlich",
                                              "naechste_faelligkeit": "2026-05-01"}).json()["id"]
        c.post(f"/api/wiederkehr/{sid}/verbuchen", json={"konto_id": giro, "datum": "2026-05-01"})
        buch = [json.loads(e["nutzlast"]) for e in _events(c.app) if e["art"] == "money.buchung"]
        assert len(buch) == 1 and buch[0]["quelle"] == "serie"


def test_storno_erzeugt_invertierte_postings(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        bid = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                             "betrag": "100,00", "datum": "2026-05-10"}).json()["id"]
        buchung_ev = json.loads([e for e in _events(c.app) if e["art"] == "money.buchung"][0]["nutzlast"])
        c.delete(f"/api/buchungen/{bid}")
        storno = [e for e in _events(c.app) if e["art"] == "money.storno"]
        assert len(storno) == 1
        sn = json.loads(storno[0]["nutzlast"])
        # invertierte Gegenwerte: Buchung + Storno je Konto = 0 (self-contained, BZ-C-1)
        summe: dict[str, int] = {}
        for p in buchung_ev["postings"] + sn["postings"]:
            summe[p["konto_id"]] = summe.get(p["konto_id"], 0) + int(p["betrag_minor"])
        assert set(summe.values()) == {0}


# ── C-1: Atomarität (Rollback ⇒ keine Outbox-Zeile) ─────────────────────────

def test_rollback_laesst_keine_outbox_zeile(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        vorher = db.get_conn().execute("SELECT COUNT(*) FROM chronik_ausgang").fetchone()[0]
        with pytest.raises(RuntimeError):
            with db.transaktion() as conn:
                chronik_naht.schreibe_buchung(conn, "dizzi", buchung_id="x", datum="2026-05-01",
                                              quelle="manuell", postings=[("1200", 100), ("8400", -100)])
                raise RuntimeError("Abbruch nach Outbox-INSERT")
        nachher = db.get_conn().execute("SELECT COUNT(*) FROM chronik_ausgang").fetchone()[0]
        assert nachher == vorher            # C-1: beide Wahrheiten oder keine


# ── UPDATE-Pfade: 409/Erlaubnis-Matrix (BZ-C-2) + Umklassung/Beleg ──────────

def _festschreibe(c, zeitraum):
    return c.post("/api/festschreibung", json={"zeitraum": zeitraum})


def test_umklassung_offen_und_409_versiegelt(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        kat = c.post("/api/kategorien", json={"name": "Wohnen"}).json()["id"]
        # offener Monat ⇒ Umklassung erlaubt + Ereignis
        bid = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                             "betrag": "50,00", "datum": "2026-05-20"}).json()["id"]
        assert c.post(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": kat}).status_code == 200
        assert "money.umklassung" in _arten(c.app)
        # Buchung im April, April festschreiben ⇒ Umklassung dort 409
        b2 = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                            "betrag": "9,00", "datum": "2026-04-11"}).json()["id"]
        assert _festschreibe(c, "2026-04").json()["ok"] is True
        assert c.post(f"/api/buchungen/{b2}/kategorie", json={"kategorie_id": kat}).status_code == 409


def test_beleg_anhaengen_auch_versiegelt_erlaubt(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        bid = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                             "betrag": "5,00", "datum": "2026-04-08"}).json()["id"]
        _festschreibe(c, "2026-04")
        # Anhängen erlaubt (verbessert Nachvollziehbarkeit, ändert keine Werte) + money.beleg
        r = c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:d1", "titel": "Rechnung"})
        assert r.status_code == 200
        beleg = [json.loads(e["nutzlast"]) for e in _events(c.app) if e["art"] == "money.beleg"]
        assert beleg and beleg[-1]["beleg_titel_hash"].startswith("hmac256:")
        # Entfernen im versiegelten Monat ⇒ 409
        assert c.delete(f"/api/buchungen/{bid}/beleg").status_code == 409


def test_bulk_kategorie_loeschung_spart_versiegelte_aus(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        kat = c.post("/api/kategorien", json={"name": "Alt"}).json()["id"]
        offen = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                               "betrag": "7,00", "datum": "2026-05-05"}).json()["id"]
        sealed = c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                                "betrag": "8,00", "datum": "2026-04-05"}).json()["id"]
        c.post(f"/api/buchungen/{offen}/kategorie", json={"kategorie_id": kat})
        c.post(f"/api/buchungen/{sealed}/kategorie", json={"kategorie_id": kat})
        _festschreibe(c, "2026-04")     # sealed-Buchung liegt jetzt in einem versiegelten Monat
        vor = _arten(c.app).count("money.umklassung")
        r = c.delete(f"/api/kategorien/{kat}")
        assert r.json().get("ausgespart") == 1               # die versiegelte behielt ihre Kategorie
        # die offene Buchung wurde umklassiert (kategorie_id="") ⇒ genau ein neues Ereignis
        assert _arten(c.app).count("money.umklassung") == vor + 1
        # die versiegelte Buchung trägt weiterhin ihre (archivierte) Kategorie
        row = c.app.state.db.get_conn().execute(
            "SELECT kategorie_id FROM buchungen WHERE id=?", (sealed,)).fetchone()
        assert row["kategorie_id"] == kat


def test_wertbildende_pfade_409_im_versiegelten_monat(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        # April mit einer Buchung anlegen, dann festschreiben
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                       "betrag": "1,00", "datum": "2026-04-01"})
        _festschreibe(c, "2026-04")
        # neue Buchung in den versiegelten April ⇒ 409
        assert c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete,
                                              "betrag": "2,00", "datum": "2026-04-15"}).status_code == 409


# ── BZ-C-10: keine Freitexte/Namen im Klartext in den Segmenten ─────────────

def test_keine_klartext_freitexte_in_segmenten(tmp_path):
    with _client(tmp_path) as c:
        giro, miete = _konten(c)
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": miete, "betrag": "3,00",
                                       "datum": "2026-04-09", "notiz": "GEHEIMNIS Kontakt Mueller"})
        _festschreibe(c, "2026-04")           # materialisiert Segmente über den In-Process-Chronisten
    seg = chronik_naht.chronik_dir() / "segmente"
    text = "\n".join(p.read_text("utf-8") for p in seg.iterdir())
    assert "GEHEIMNIS" not in text and "Mueller" not in text and "dizzi" not in text
    assert "hmac256:" in text                 # die Freitexte liegen NUR als gepfefferte Hashes vor
