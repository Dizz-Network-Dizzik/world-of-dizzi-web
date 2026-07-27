"""Bereich-Achse von Dizz Management (Umbau): lokale ``bereiche``-CRUD (Muster Admin/Money),
``bereich_id``-Migration an Kanäle/Bots/Posts, optionaler Ziel-Plattform-Slot der Bots,
Zuordnung + Bereichs-Inhalt, per-Bereich-Filter. Bestand wandert nach „Allgemein"
(``bereich_id=''``). lokal_only + Publish-HITL bleiben unangetastet."""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm


def _client(tmp_path) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path))


# ── Typ-Katalog + CRUD ─────────────────────────────────────────────────────────
def test_bereich_typen_katalog(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/api/bereich-typen").json()
        ids = {t["id"] for t in r["typen"]}
        assert ids == {"kunde", "marke", "kampagne", "projekt", "persoenlich", "sonstiges"}
        assert r["default"] == "marke"
        # jeder Typ trägt Anzeige-Metadaten
        assert all({"label", "icon", "farbe"} <= set(t) for t in r["typen"])


# ── BER-2: netzweite Ober-Kategorie (additiv über dem art-Katalog, docs/67 §4) ───
def test_ober_kategorie_additiv_in_api(tmp_path):
    erwartet = {"kunde": "geschaeftlich", "marke": "geschaeftlich", "kampagne": "projekt",
                "projekt": "projekt", "persoenlich": "persoenlich", "sonstiges": "sonstiges"}
    with _client(tmp_path) as c:
        for art, ok in erwartet.items():
            b = c.post("/api/bereiche", json={"name": art.title(), "art": art}).json()
            assert b["ober_kategorie"] == ok and b["art"] == art          # additiv, art unberührt
            assert c.get(f"/api/bereiche/{b['id']}").json()["ober_kategorie"] == ok


def test_ober_kategorie_mapping_vollstaendig():
    from appkit.bereich_register import (OBER_KATEGORIEN, mapping_validieren,
                                         ober_kategorie_fuer)
    from managementapp import bereiche as mb
    mapping_validieren(mb.BEREICH_ART)                       # wirft bei Lücke (Bau-Zeit-Assert)
    assert all(ober_kategorie_fuer(a) in OBER_KATEGORIEN for a in mb.BEREICH_ART)


def test_bereich_crud_und_art_coerce(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={
            "name": "Social Media Manager für Ludwig Hülsen Nagelfabrik",
            "art": "kunde", "kontext": "lhn"}).json()
        assert b["art"] == "kunde" and b["kontext"] == "lhn"
        assert b["status"] == "aktiv"
        # ungültiger Typ ⇒ auf 'sonstiges' geklemmt
        b2 = c.post("/api/bereiche", json={"name": "X", "art": "quatsch"}).json()
        assert b2["art"] == "sonstiges"
        # leerer Name ⇒ 400
        assert c.post("/api/bereiche", json={"name": "  "}).status_code == 400
        # Liste + Filter nach art
        assert len(c.get("/api/bereiche").json()) == 2
        assert len(c.get("/api/bereiche?art=kunde").json()) == 1
        # Ändern (Name/kontext) + Holen
        c.put(f"/api/bereiche/{b['id']}", json={"name": "LHN", "kontext": "lhn-neu"})
        assert c.get(f"/api/bereiche/{b['id']}").json()["name"] == "LHN"
        assert c.get(f"/api/bereiche/{b['id']}").json()["kontext"] == "lhn-neu"


def test_bereich_zyklus_schutz(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/bereiche", json={"name": "A"}).json()["id"]
        b = c.post("/api/bereiche", json={"name": "B", "parent_id": a}).json()["id"]
        # A unter B hängen würde einen Zyklus erzeugen ⇒ 400
        assert c.put(f"/api/bereiche/{a}", json={"parent_id": b}).status_code == 400
        # Selbst-Parent ⇒ 400
        assert c.put(f"/api/bereiche/{a}", json={"parent_id": a}).status_code == 400


def test_bereich_loeschen_zieht_kinder_hoch(tmp_path):
    with _client(tmp_path) as c:
        p = c.post("/api/bereiche", json={"name": "Parent"}).json()["id"]
        kind = c.post("/api/bereiche", json={"name": "Kind", "parent_id": p}).json()["id"]
        assert c.delete(f"/api/bereiche/{p}").json()["ok"] is True
        assert c.get(f"/api/bereiche/{p}").status_code == 404
        # Kind überlebt, parent_id ist auf '' (Wurzel) hochgezogen — kein Waisen-Teilbaum
        assert c.get(f"/api/bereiche/{kind}").json()["parent_id"] == ""


# ── bereich_id an den Domänen-Entitäten + Filter ────────────────────────────────
def test_bereich_id_auf_kanal_bot_post(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Marke A", "art": "marke"}).json()["id"]
        k = c.post("/api/kanaele", json={"plattform": "instagram", "handle": "@a",
                                         "bereich_id": b}).json()["id"]
        bot = c.post("/api/bots", json={"name": "Bot A", "bereich_id": b}).json()["id"]
        p = c.post("/api/posts", json={"titel": "P", "plattform": "x", "bereich_id": b}).json()["id"]
        # Serializer geben bereich_id zurück
        assert c.get("/api/kanaele", params={"bereich_id": b}).json()[0]["bereich_id"] == b
        assert c.get("/api/bots", params={"bereich_id": b}).json()[0]["bereich_id"] == b
        assert c.get("/api/posts", params={"bereich_id": b}).json()[0]["bereich_id"] == b
        # Filter grenzt sauber ab (anderer/leerer Bereich ⇒ nichts)
        assert c.get("/api/kanaele", params={"bereich_id": "anderswo"}).json() == []
        # Inhalt-Zähler des Bereichs
        inh = c.get(f"/api/bereiche/{b}/inhalt").json()
        assert inh["zaehler"] == {"kanaele": 1, "social_bots": 1, "posts": 1}
        assert inh["gesamt"] == 3
        _ = (k, bot, p)


def test_bestand_landet_in_allgemein(tmp_path):
    """Ohne bereich_id angelegte Entitäten sind voll sichtbar (Allgemein = '')."""
    with _client(tmp_path) as c:
        c.post("/api/kanaele", json={"plattform": "tiktok", "handle": "@alt"})
        alle = c.get("/api/kanaele").json()
        assert len(alle) == 1 and alle[0]["bereich_id"] == ""


def test_zuordnung_verschiebt_entitaet(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Ziel"}).json()["id"]
        k = c.post("/api/kanaele", json={"plattform": "x", "handle": "@k"}).json()["id"]
        r = c.put("/api/bereiche/zuordnung",
                  json={"tabelle": "kanaele", "id": k, "bereich_id": b})
        assert r.json()["ok"] is True
        assert c.get("/api/kanaele", params={"bereich_id": b}).json()[0]["id"] == k
        # Lösen (→ Allgemein)
        c.put("/api/bereiche/zuordnung", json={"tabelle": "kanaele", "id": k, "bereich_id": ""})
        assert c.get("/api/kanaele", params={"bereich_id": b}).json() == []
        # unbekannte Tabelle ⇒ 400
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "secrets", "id": k, "bereich_id": b}).status_code == 400


# ── Bot-Plattform-Slot ──────────────────────────────────────────────────────────
def test_bot_plattform_slot(tmp_path):
    with _client(tmp_path) as c:
        # leer = plattform-übergreifend (Default, kein Fehler)
        b0 = c.post("/api/bots", json={"name": "Übergreifend"}).json()["id"]
        assert c.get("/api/bots").json()[0]["plattform"] == ""
        # gültige Plattform
        c.post("/api/bots", json={"name": "IG-Bot", "plattform": "instagram"})
        ig = [b for b in c.get("/api/bots").json() if b["name"] == "IG-Bot"][0]
        assert ig["plattform"] == "instagram"
        # ungültige Plattform ⇒ 400
        assert c.post("/api/bots", json={"name": "Mist", "plattform": "quatsch"}).status_code == 400
        # Patch auf ungültige Plattform ⇒ 400; auf gültige ⇒ ok
        assert c.patch(f"/api/bots/{b0}", json={"plattform": "quatsch"}).status_code == 400
        c.patch(f"/api/bots/{b0}", json={"plattform": "linkedin"})
        assert [b for b in c.get("/api/bots").json()
                if b["id"] == b0][0]["plattform"] == "linkedin"


# ── Creating-Empfang + Bulk je Bereich ──────────────────────────────────────────
def test_creating_empfang_je_bereich(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Kampagne Q3", "art": "kampagne"}).json()["id"]
        # Kanal im Bereich → soll bevorzugt zugeordnet werden
        kib = c.post("/api/kanaele", json={"plattform": "instagram", "handle": "@inber",
                                           "bereich_id": b}).json()["id"]
        r = c.post("/api/creating/empfang", json={
            "asset_id": "asset-1", "titel": "Reel", "bereich_id": b,
            "derivate": [{"plattform": "instagram", "format": "9:16", "pfad": "/dam/x.mp4"}]}).json()
        pid = r["angelegt"][0]
        post = [p for p in c.get("/api/posts", params={"bereich_id": b}).json() if p["id"] == pid][0]
        assert post["bereich_id"] == b
        assert post["kanal_id"] == kib          # Kanal desselben Bereichs bevorzugt
        # Idempotenz bleibt erhalten (gleicher Asset+Plattform ⇒ nichts Neues)
        r2 = c.post("/api/creating/empfang", json={
            "asset_id": "asset-1", "bereich_id": b,
            "derivate": [{"plattform": "instagram"}]}).json()
        assert r2["angelegt"] == [] and r2["uebersprungen"] == [pid]


def test_bulk_import_je_bereich(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Bulk-Bereich"}).json()["id"]
        csv = "titel,text,plattform\nReel A,Hallo,instagram\nTweet B,Kurz,x\n"
        r = c.post("/api/posts/bulk", json={"csv": csv, "bereich_id": b}).json()
        assert len(r["angelegt"]) == 2 and r["fehler"] == []
        posts = c.get("/api/posts", params={"bereich_id": b}).json()
        assert len(posts) == 2 and all(p["bereich_id"] == b for p in posts)


# ── Migration: Bestands-DB nachrüsten (idempotent) ──────────────────────────────
def test_migration_auf_bestands_db(tmp_path):
    """Simuliert eine Bestands-DB OHNE die neuen Spalten (nur domain.SCHEMA) und prüft,
    dass ``migriere_bereich`` ``bereich_id`` + Bot-``plattform`` idempotent nachrüstet."""
    from appkit.db import Database
    from managementapp.domain import SCHEMA
    from managementapp import bereiche as bm

    db = Database(str(tmp_path / "legacy.db"), extra_schema=SCHEMA)  # OHNE bereich_id/plattform
    conn = db.get_conn()
    for t in ("kanaele", "social_bots", "posts"):
        assert "bereich_id" not in {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}

    bm.migriere_bereich(db)
    for t in ("kanaele", "social_bots", "posts"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        assert "bereich_id" in cols
    assert "plattform" in {r["name"] for r in conn.execute("PRAGMA table_info(social_bots)")}

    bm.migriere_bereich(db)   # zweiter Lauf = No-op (idempotent, kein Fehler)


# ── BER-1: Bereichs-Kanon (kanon_id + Feed + Bindung, docs/67) ──────────────────
def test_migriere_bereich_ruestet_kanon_nach(tmp_path):
    """MIG-KANON-1 hängt an ``migriere_bereich`` an: additive kanon_id-Spalte, idempotent."""
    from appkit.db import Database
    from managementapp import bereiche as bm

    db = Database(str(tmp_path / "b.db"), extra_schema=bm.SCHEMA_BEREICHE)
    bm.migriere_bereich(db)
    bm.migriere_bereich(db)                         # idempotent
    cols = [r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")]
    assert cols.count("kanon_id") == 1
    assert "idx_bereiche_kanon" in {r["name"] for r in db.get_conn().execute(
        "PRAGMA index_list(bereiche)")}


def test_kanon_status_feed_und_bindung(tmp_path):
    with _client(tmp_path) as c:
        b1 = c.post("/api/bereiche", json={"name": "LHN", "art": "kunde",
                                           "kontext": "lhn"}).json()["id"]
        b2 = c.post("/api/bereiche", json={"name": "Marke", "art": "marke"}).json()["id"]
        c.post("/api/bots", json={"name": "Uni-Bot", "bereich_id": b1})
        feed = c.get("/api/bereiche/kanon-status").json()
        assert feed["ok"] is True
        assert feed["anker_extra"]["bots"] == ["Uni-Bot"]     # V18-Alt-Kante (docs/34)
        by_id = {b["id"]: b for b in feed["bereiche"]}
        assert by_id[b1]["kanon_id"] == "" and by_id[b1]["kontext"] == "lhn"
        # Binden an die kanonische Admin-ID + Eindeutigkeit (I-4) + Lösen
        assert c.put(f"/api/bereiche/{b1}/kanon", json={"kanon_id": "A-9"}).json()["ok"]
        assert c.put(f"/api/bereiche/{b2}/kanon", json={"kanon_id": "A-9"}).status_code == 409
        assert {b["id"]: b for b in c.get("/api/bereiche/kanon-status").json()["bereiche"]
                }[b1]["kanon_id"] == "A-9"
        assert c.delete(f"/api/bereiche/{b1}/kanon").json()["kanon_id"] == ""
