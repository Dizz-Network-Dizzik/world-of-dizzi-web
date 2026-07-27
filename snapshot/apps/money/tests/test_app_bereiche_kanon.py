"""BER-1 (docs/67) — Money-Verdrahtung des Bereichs-Kanons: MIG-KANON-1 idempotent ·
Dual-Read-Register (① kanon → ② kontext) · kanon-status-Feed + Bindungs-Endpunkte
(``PUT/DELETE /api/bereiche/{bid}/kanon``, fail-closed I-4). Additiv/rückwärtskompatibel
— die bestehende Bereichs-CRUD/Finanzspur bleibt unberührt (test_app_bereiche.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit.db import Database
from moneyapp import bereiche as bmod
from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _db(tmp_path):
    return Database(tmp_path / "m.sqlite", extra_schema=bmod.SCHEMA_BEREICHE)


# ── Datenschicht: MIG-KANON-1 + Register-Auflösung (Modul-Ebene) ────────────────
def test_migriere_bereich_idempotent(tmp_path):
    db = _db(tmp_path)
    bmod.migriere_bereich(db)
    bmod.migriere_bereich(db)                       # rerun ⇒ kein Fehler
    cols = [r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")]
    assert cols.count("kanon_id") == 1
    idx = {r["name"] for r in db.get_conn().execute("PRAGMA index_list(bereiche)")}
    assert "idx_bereiche_kanon" in idx


def test_bereiche_init_ruestet_kanon_spalte_nach(tmp_path):
    """Money hat keinen startup-Migrations-Hook in bereiche.py ⇒ ``Bereiche.__init__``
    stellt die additive kanon_id-Spalte sicher (einmal beim Aufbau der Achse)."""
    db = _db(tmp_path)
    assert "kanon_id" not in {r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")}
    bmod.Bereiche(db)
    assert "kanon_id" in {r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")}


def test_register_dual_read_kanon_vor_kontext(tmp_path):
    db = _db(tmp_path)
    ber = bmod.Bereiche(db)                          # __init__ migriert kanon_id
    b = ber.anlegen("u1", bmod.BereichIn(name="Nagelfabrik", kontext="nagelfabrik"))
    # ungebunden ⇒ Stufe-② (kontext), Stufe-0-wertgleich zu heute
    assert ber.register.aufloesen("u1", kontext="nagelfabrik").quelle == "kontext"
    # gebunden ⇒ Stufe-① (kanon) gewinnt
    ber.register.verknuepfen("u1", b["id"], "A-1")
    a = ber.register.aufloesen("u1", kanon="A-1", kontext="ignoriert")
    assert a.bereich_id == b["id"] and a.quelle == "kanon"


# ── HTTP: Feed + Bindungs-Endpunkte (End-to-End über build_app) ─────────────────
def test_kanon_status_und_bindung_http(tmp_path):
    with _client(tmp_path) as c:
        b1 = c.post("/api/bereiche", json={"name": "Nagelfabrik", "art": "geschaeft",
                                           "kontext": "nagelfabrik"}).json()["id"]
        b2 = c.post("/api/bereiche", json={"name": "Privat", "art": "privat"}).json()["id"]
        # Feed (Literal-Route vor /{bid}): kanon_id leer, kontext gesetzt, anker_extra={}
        feed = c.get("/api/bereiche/kanon-status").json()
        assert feed["ok"] is True and feed["anker_extra"] == {}
        by_id = {b["id"]: b for b in feed["bereiche"]}
        assert by_id[b1]["kanon_id"] == "" and by_id[b1]["kontext"] == "nagelfabrik"
        # Binden an die kanonische Admin-ID
        assert c.put(f"/api/bereiche/{b1}/kanon", json={"kanon_id": "A-1"}).json()["ok"]
        assert {b["id"]: b for b in c.get("/api/bereiche/kanon-status").json()["bereiche"]
                }[b1]["kanon_id"] == "A-1"
        # Eindeutigkeit (I-4): dieselbe kanon_id an b2 ⇒ 409; leer ⇒ 400; unbekannt ⇒ 404
        assert c.put(f"/api/bereiche/{b2}/kanon", json={"kanon_id": "A-1"}).status_code == 409
        assert c.put(f"/api/bereiche/{b2}/kanon", json={"kanon_id": "  "}).status_code == 400
        assert c.put("/api/bereiche/weg/kanon", json={"kanon_id": "X"}).status_code == 404
        # Lösen
        assert c.delete(f"/api/bereiche/{b1}/kanon").json()["kanon_id"] == ""
        assert {b["id"]: b for b in c.get("/api/bereiche/kanon-status").json()["bereiche"]
                }[b1]["kanon_id"] == ""


# ── V17-Kantenvertrag: kanon-Param → Finanzspur-quelle (docs/67 §10) ────────────
def test_finanzspur_kanon_liefert_quelle_kanon(tmp_path):
    """kanon schlägt einen falschen kontext (quelle='kanon'); ein dangling kanon
    fällt auf die Not-Leiter ② kontext durch (§3.2)."""
    with _client(tmp_path) as c:
        b1 = c.post("/api/bereiche", json={"name": "Nagelfabrik", "art": "geschaeft",
                                           "kontext": "nagelfabrik"}).json()["id"]
        assert c.put(f"/api/bereiche/{b1}/kanon", json={"kanon_id": "A-1"}).json()["ok"]
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset",
                                           "bereich_id": b1}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                       "betrag": "300,00", "datum": "2026-06-10"})
        # kanon gewinnt gegen einen völlig falschen kontext:
        r = c.get("/api/bereich/finanzspur?kanon=A-1&kontext=voelligfalsch").json()
        assert r["quelle"] == "kanon" and r["bereich_id"] == b1
        # dangling kanon fällt auf die Not-Leiter (② kontext) durch:
        r2 = c.get("/api/bereich/finanzspur?kanon=GIBTSNICHT&kontext=nagelfabrik").json()
        assert r2["quelle"] == "kontext" and r2["bereich_id"] == b1
