"""Bereichs-Achse (Über-Kategorisierung) — CRUD, Zuordnung, Vererbung & Filter.
Vorbild + Kanon: adminapp.bereiche. Ollama-frei (RAG aus ohne embed_fn)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp import bereiche as B


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _neu_bereich(c, name="Praktikum", art="projekt"):
    return c.post("/api/bereiche", json={"name": name, "art": art}).json()


def test_crud_und_coercion(tmp_path):
    with _client(tmp_path) as c:
        b = _neu_bereich(c)
        assert b["name"] == "Praktikum" and b["art"] == "projekt" and b["status"] == "aktiv"
        # unbekannte art ⇒ auf 'sonstiges' normalisiert
        b2 = c.post("/api/bereiche", json={"name": "X", "art": "quatsch"}).json()
        assert b2["art"] == "sonstiges"
        # Liste
        assert {x["name"] for x in c.get("/api/bereiche").json()} == {"Praktikum", "X"}
        # Ändern (Name + status)
        c.put(f"/api/bereiche/{b['id']}", json={"name": "Praktikum NF", "status": "ruhend"})
        d = c.get(f"/api/bereiche/{b['id']}").json()
        assert d["name"] == "Praktikum NF" and d["status"] == "ruhend"
        # leerer Name verboten
        assert c.put(f"/api/bereiche/{b['id']}", json={"name": "  "}).status_code == 400
        # Löschen (soft) ⇒ raus aus Liste, Detail 404
        c.delete(f"/api/bereiche/{b['id']}")
        assert {x["name"] for x in c.get("/api/bereiche").json()} == {"X"}
        assert c.get(f"/api/bereiche/{b['id']}").status_code == 404


# ── BER-2: netzweite Ober-Kategorie (additiv über dem art-Katalog, docs/67 §4) ───
def test_ober_kategorie_additiv_in_api(tmp_path):
    erwartet = {"projekt": "projekt", "lebensbereich": "persoenlich", "wissen": "bildung",
                "referenz": "bildung", "sonstiges": "sonstiges"}
    with _client(tmp_path) as c:
        for art, ok in erwartet.items():
            b = _neu_bereich(c, art.title(), art)
            assert b["ober_kategorie"] == ok and b["art"] == art          # additiv, art unberührt
            assert c.get(f"/api/bereiche/{b['id']}").json()["ober_kategorie"] == ok


def test_ober_kategorie_mapping_vollstaendig():
    from appkit.bereich_register import (OBER_KATEGORIEN, mapping_validieren,
                                         ober_kategorie_fuer)
    mapping_validieren(B.BEREICH_ART)                        # wirft bei Lücke (Bau-Zeit-Assert)
    assert all(ober_kategorie_fuer(a) in OBER_KATEGORIEN for a in B.BEREICH_ART)


def test_hierarchie_zyklus_und_loeschen_hochziehen(tmp_path):
    with _client(tmp_path) as c:
        a = _neu_bereich(c, "Geschäft")["id"]
        kind = c.post("/api/bereiche", json={"name": "Mandant", "parent_id": a}).json()["id"]
        # Zyklus: a unter sein eigenes Kind hängen ⇒ 400
        assert c.put(f"/api/bereiche/{a}", json={"parent_id": kind}).status_code == 400
        # sich selbst als parent ⇒ 400
        assert c.put(f"/api/bereiche/{a}", json={"parent_id": a}).status_code == 400
        # Eltern löschen ⇒ Kind wird zur Wurzel hochgezogen (parent_id '')
        c.delete(f"/api/bereiche/{a}")
        assert c.get(f"/api/bereiche/{kind}").json()["parent_id"] == ""


def test_zuordnung_vererbung_und_filter(tmp_path):
    with _client(tmp_path) as c:
        b = _neu_bereich(c)["id"]
        # Ordner → Bereich; Notiz im Ordner erbt
        o = c.post("/api/ordner", json={"name": "Logs"}).json()["id"]
        c.put("/api/bereiche/zuordnung", json={"tabelle": "ordner", "id": o, "bereich_id": b})
        n_erbt = c.post("/api/notizen", json={"titel": "Tag 1", "ordner_id": o}).json()["id"]
        # Lose Notiz direkt zugeordnet
        n_lose = c.post("/api/notizen", json={"titel": "Lose"}).json()["id"]
        c.put("/api/bereiche/zuordnung", json={"tabelle": "notizen", "id": n_lose, "bereich_id": b})
        # Notiz ganz ohne Bereich
        c.post("/api/notizen", json={"titel": "Neutral"})

        of = [x["name"] for x in c.get("/api/ordner", params={"bereich": b}).json()]
        nf = sorted(x["titel"] for x in c.get("/api/notizen", params={"bereich": b}).json())
        assert of == ["Logs"]
        assert nf == ["Lose", "Tag 1"]           # erbt + direkt, NICHT „Neutral"
        # Detail liefert bereich_id der losen Notiz
        assert c.get(f"/api/notizen/{n_lose}").json()["bereich_id"] == b
        # inhalt-Zähler
        inh = c.get(f"/api/bereiche/{b}/inhalt").json()
        assert inh["zaehler"] == {"ordner": 1, "notizen": 2} and inh["gesamt"] == 3
        # Zuordnung lösen (bereich_id='') ⇒ Notiz fällt aus dem Filter
        c.put("/api/bereiche/zuordnung", json={"tabelle": "notizen", "id": n_lose, "bereich_id": ""})
        assert [x["titel"] for x in c.get("/api/notizen", params={"bereich": b}).json()] == ["Tag 1"]


def test_zuordnung_fehler(tmp_path):
    with _client(tmp_path) as c:
        b = _neu_bereich(c)["id"]
        # unbekannte Tabelle (nicht in Whitelist) ⇒ 400
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "labels", "id": "x", "bereich_id": b}).status_code == 400
        # unbekannter Bereich ⇒ 400
        o = c.post("/api/ordner", json={"name": "O"}).json()["id"]
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "ordner", "id": o, "bereich_id": "gibtsnicht"}).status_code == 400
        # unbekannte Zeile ⇒ 404
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "ordner", "id": "gibtsnicht", "bereich_id": b}).status_code == 404


def test_fk_migration_idempotent(tmp_path):
    # Zweimal bauen auf demselben Daten-Dir ⇒ ALTER-Migration darf nicht crashen.
    with _client(tmp_path) as c:
        c.post("/api/ordner", json={"name": "A"})
    with _client(tmp_path) as c:
        cols_ordner = {r["name"] for r in
                       c.app.state.db.get_conn().execute("PRAGMA table_info(ordner)")}
        cols_notizen = {r["name"] for r in
                        c.app.state.db.get_conn().execute("PRAGMA table_info(notizen)")}
        assert "bereich_id" in cols_ordner and "bereich_id" in cols_notizen
        # app.state.bereiche exponiert
        assert c.app.state.bereiche.anzahl("dizzi") == 0


def test_effektiv_bereich_where_helper():
    # Der SQL-Helfer nennt :bereich + :user (für das Test-/Wartungs-Bewusstsein).
    w = B.effektiv_bereich_where("n")
    assert ":bereich" in w and ":user" in w and "n.bereich_id" in w


# ── BER-1: Bereichs-Kanon (kanon-only, Ordner-Namen = V19-Alt-Kante, docs/67) ────
def test_migriere_ruestet_kanon_nach(tmp_path):
    """MIG-KANON-1 hängt an ``migriere_bereich_fk`` an: additive kanon_id-Spalte, idempotent."""
    from appkit.db import Database

    db = Database(tmp_path / "b.sqlite", extra_schema=B.SCHEMA_BEREICHE)
    B.migriere_bereich_fk(db)
    B.migriere_bereich_fk(db)                       # idempotent
    cols = [r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")]
    assert cols.count("kanon_id") == 1


def test_kanon_status_feed_und_bindung(tmp_path):
    with _client(tmp_path) as c:
        b1 = _neu_bereich(c, "Studium", "wissen")["id"]
        b2 = _neu_bereich(c, "Privat", "lebensbereich")["id"]
        c.post("/api/ordner", json={"name": "Studium Informatik"})
        feed = c.get("/api/bereiche/kanon-status").json()
        assert feed["ok"] is True
        assert feed["anker_extra"]["ordner"] == ["Studium Informatik"]   # V19-Alt-Kante
        by_id = {b["id"]: b for b in feed["bereiche"]}
        # Memory hat KEINE kontext-Spalte ⇒ kontext leer, Auflösung kanon-only
        assert by_id[b1]["kanon_id"] == "" and by_id[b1]["kontext"] == ""
        # Binden (kanon-only) + Eindeutigkeit (I-4) + Lösen
        assert c.put(f"/api/bereiche/{b1}/kanon", json={"kanon_id": "A-7"}).json()["ok"]
        assert c.put(f"/api/bereiche/{b2}/kanon", json={"kanon_id": "A-7"}).status_code == 409
        assert {b["id"]: b for b in c.get("/api/bereiche/kanon-status").json()["bereiche"]
                }[b1]["kanon_id"] == "A-7"
        assert c.delete(f"/api/bereiche/{b1}/kanon").json()["kanon_id"] == ""
