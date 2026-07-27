"""Tests Dizz Admin — Bereich-Typ-Modell (docs/49): der Typ (``art``) eines Bereichs
schaltet die für ihn relevanten Module frei (Bereich-first-Navigation). Admin ist die
kanonische Heimat. Lauf: <venv-python> -m pytest tests/ -q
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from adminapp import bereiche as bm
from adminapp import main as lm


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def test_module_fuer_typ_mapping():
    g = set(bm.ALLGEMEINE_MODULE)
    # General immer dabei, in kanonischer Tab-Reihenfolge
    assert bm.module_fuer_typ("persoenlich") == ["uebersicht", "tresor", "projekte", "fristen"]
    assert bm.module_fuer_typ("sonstiges") == ["uebersicht", "tresor", "projekte", "fristen"]
    # Geschäft + Mandant ⇒ Geschäfts-Modul; Studium + Fortbildung ⇒ Studien-Modul
    assert bm.module_fuer_typ("geschaeft") == ["uebersicht", "tresor", "projekte", "geschaeft", "fristen"]
    assert bm.module_fuer_typ("mandant") == bm.module_fuer_typ("geschaeft")
    assert bm.module_fuer_typ("studium") == ["uebersicht", "tresor", "projekte", "studium", "fristen"]
    assert bm.module_fuer_typ("fortbildung") == bm.module_fuer_typ("studium")
    # „geschaeft"/„studium" tauchen NUR im passenden Typ auf
    assert "geschaeft" not in bm.module_fuer_typ("studium")
    assert "studium" not in bm.module_fuer_typ("geschaeft")
    assert "geschaeft" not in bm.module_fuer_typ("persoenlich")
    # Unbekannter Typ ⇒ nur General
    assert bm.module_fuer_typ("quatsch") == list(bm.module_fuer_typ("persoenlich"))
    assert g == {"uebersicht", "tresor", "projekte", "fristen"}


def test_typen_katalog_endpoint(tmp_path):
    with _client(tmp_path) as c:
        d = c.get("/api/bereich-typen").json()
        assert d["default"] == "persoenlich"
        assert d["allgemeine_module"] == ["uebersicht", "tresor", "projekte", "fristen"]
        typen = {t["id"]: t for t in d["typen"]}
        assert set(typen) == {"geschaeft", "studium", "mandant", "fortbildung", "persoenlich", "sonstiges"}
        # Persönlich Allgemein vorhanden + sprechendes Label/Icon
        assert typen["persoenlich"]["label"] == "Persönlich Allgemein"
        assert typen["persoenlich"]["icon"] and typen["persoenlich"]["farbe"]
        # Jeder Typ trägt sein Modul-Set
        assert "geschaeft" in typen["geschaeft"]["module"]
        assert "studium" in typen["studium"]["module"]
        assert typen["persoenlich"]["module"] == ["uebersicht", "tresor", "projekte", "fristen"]


def test_bereich_liefert_module(tmp_path):
    with _client(tmp_path) as c:
        g = c.post("/api/bereiche", json={"name": "Agentur", "art": "geschaeft"}).json()
        assert "geschaeft" in g["module"] and "studium" not in g["module"]
        s = c.post("/api/bereiche", json={"name": "Bachelor", "art": "studium"}).json()
        assert "studium" in s["module"] and "geschaeft" not in s["module"]
        # auch in Liste + Einzelabruf
        liste = {b["name"]: b for b in c.get("/api/bereiche").json()}
        assert "geschaeft" in liste["Agentur"]["module"]
        assert "studium" in c.get(f"/api/bereiche/{s['id']}").json()["module"]


def test_persoenlich_default_und_coercion(tmp_path):
    with _client(tmp_path) as c:
        # ``art`` weggelassen ⇒ Default „Persönlich Allgemein" (Standard-Heimat)
        d = c.post("/api/bereiche", json={"name": "Allerlei"}).json()
        assert d["art"] == "persoenlich"
        # explizit ungültig ⇒ neutral „sonstiges" (unverändert)
        bad = c.post("/api/bereiche", json={"name": "X", "art": "quatsch"}).json()
        assert bad["art"] == "sonstiges"
        # „persoenlich" ist ein gültiger Typ
        ok = c.post("/api/bereiche", json={"name": "Heim", "art": "persoenlich"}).json()
        assert ok["art"] == "persoenlich"


def test_migration_privat_zu_persoenlich(tmp_path):
    """Alt-Bereiche mit Typ ``privat`` werden sanft auf ``persoenlich`` gehoben —
    idempotent, ohne Daten zu verschieben."""
    with _client(tmp_path) as c:
        bid = c.post("/api/bereiche", json={"name": "Alt-Privat", "art": "persoenlich"}).json()["id"]
        db = c.app.state.bereiche.db
        # Legacy-Zustand simulieren: art direkt auf 'privat' setzen (umgeht Coercion)
        conn = db.get_conn()
        conn.execute("UPDATE bereiche SET art='privat' WHERE id=?", (bid,)); conn.commit()
        assert conn.execute("SELECT art FROM bereiche WHERE id=?", (bid,)).fetchone()["art"] == "privat"
        # Migration (wie beim App-Start) — idempotent
        bm.migriere_bereich_fk(db)
        bm.migriere_bereich_fk(db)
        b = c.get(f"/api/bereiche/{bid}").json()
        assert b["art"] == "persoenlich" and b["name"] == "Alt-Privat"  # nichts verloren
