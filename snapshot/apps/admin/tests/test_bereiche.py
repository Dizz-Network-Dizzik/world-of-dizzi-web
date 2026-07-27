"""Tests Dizz Admin — Bereichs-Rückgrat (docs/28 §2, Phase 1B): die typisierte
Kontext-/Kategorie-Achse + idempotente ``bereich_id``-FK-Migration der Domänen-
Tabellen. Lauf: <venv-python> -m pytest tests/ -q
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from adminapp import bereiche as bm
from adminapp import main as lm


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def test_bereich_crud_und_art_coercion(tmp_path):
    with _client(tmp_path) as c:
        # Anlegen (unbekannte Art ⇒ Default 'sonstiges')
        b = c.post("/api/bereiche", json={"name": "Studium Informatik", "art": "studium"}).json()
        assert b["art"] == "studium" and b["status"] == "aktiv" and b["parent_id"] == ""
        bad = c.post("/api/bereiche", json={"name": "X", "art": "quatsch"}).json()
        assert bad["art"] == "sonstiges"
        # Liste + Filter
        assert len(c.get("/api/bereiche").json()) == 2
        assert len(c.get("/api/bereiche?art=studium").json()) == 1
        # Holen
        assert c.get(f"/api/bereiche/{b['id']}").json()["name"] == "Studium Informatik"
        assert c.get("/api/bereiche/gibtsnicht").status_code == 404
        # Ändern (Name/Status/Farbe)
        c.put(f"/api/bereiche/{b['id']}", json={"status": "ruhend", "farbe": "magenta"})
        d = c.get(f"/api/bereiche/{b['id']}").json()
        assert d["status"] == "ruhend" and d["farbe"] == "magenta"
        # Soft-Delete
        assert c.delete(f"/api/bereiche/{b['id']}").json()["ok"] is True
        assert len(c.get("/api/bereiche").json()) == 1
        assert c.delete(f"/api/bereiche/{b['id']}").status_code == 404


# ── BER-2: netzweite Ober-Kategorie (additiv, NEBEN dem admin-kanonischen Typ-Modell) ──
def test_ober_kategorie_additiv_neben_module(tmp_path):
    erwartet = {"geschaeft": "geschaeftlich", "studium": "bildung", "mandant": "geschaeftlich",
                "fortbildung": "bildung", "persoenlich": "persoenlich", "sonstiges": "sonstiges"}
    with _client(tmp_path) as c:
        for art, ok in erwartet.items():
            b = c.post("/api/bereiche", json={"name": art.title(), "art": art}).json()
            assert b["ober_kategorie"] == ok and b["art"] == art
            # Regression: der Admin-``_public``-Override liefert WEITER das typ-gesteuerte
            # ``module`` (docs/49) — die Ober-Kategorie liegt DANEBEN, gated keine Module (I-9).
            assert b["module"] == bm.module_fuer_typ(art)
            d = c.get(f"/api/bereiche/{b['id']}").json()
            assert d["ober_kategorie"] == ok and d["module"] == bm.module_fuer_typ(art)


def test_ober_kategorie_mapping_vollstaendig():
    from appkit.bereich_register import (OBER_KATEGORIEN, mapping_validieren,
                                         ober_kategorie_fuer)
    mapping_validieren(bm.BEREICH_ART)                       # wirft bei Lücke (Bau-Zeit-Assert)
    assert all(ober_kategorie_fuer(a) in OBER_KATEGORIEN for a in bm.BEREICH_ART)


def test_bereich_kontext_slots(tmp_path):
    """A5/V17–V19: die drei Querverbindungs-Kontext-Slots (money/management/memory)
    sind setz- und änderbar und reisen durch die ``_public``-Ausgabe."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={
            "name": "Geschäft X", "art": "geschaeft",
            "money_kontext": "geschaeft-x", "management_kontext": "kanal-x",
            "memory_ref": "Geschäft/X"}).json()
        assert b["money_kontext"] == "geschaeft-x"
        assert b["management_kontext"] == "kanal-x"
        assert b["memory_ref"] == "Geschäft/X"
        # Ändern des Social-Slots
        c.put(f"/api/bereiche/{b['id']}", json={"management_kontext": "kanal-y"})
        assert c.get(f"/api/bereiche/{b['id']}").json()["management_kontext"] == "kanal-y"


def test_bereich_management_kontext_migration(tmp_path):
    """``management_kontext`` ist an der bereiche-Tabelle vorhanden; die Nachtopf-
    Migration (für Bestands-DBs vor A5) ist idempotent — erneuter Lauf crasht nicht
    und legt keine Dublette an."""
    with _client(tmp_path) as c:
        db = c.app.state.bereiche.db
        cols = {r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")}
        assert "management_kontext" in cols
        # idempotent: nochmal migrieren ändert nichts
        bm.migriere_bereich_fk(db)
        cols2 = [r["name"] for r in db.get_conn().execute("PRAGMA table_info(bereiche)")]
        assert cols2.count("management_kontext") == 1


def test_bereich_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/bereiche", json={"name": "  "}).status_code == 400
        assert c.post("/api/bereiche", json={"name": "Y", "parent_id": "fehlt"}).status_code == 400
        bid = c.post("/api/bereiche", json={"name": "G"}).json()["id"]
        # Selbst-Parent + Status-Coercion (unbekannt ⇒ 'aktiv')
        assert c.put(f"/api/bereiche/{bid}", json={"parent_id": bid}).status_code == 400
        c.put(f"/api/bereiche/{bid}", json={"status": "quatsch"})
        assert c.get(f"/api/bereiche/{bid}").json()["status"] == "aktiv"
        assert c.put(f"/api/bereiche/{bid}", json={"name": "  "}).status_code == 400


def test_bereich_hierarchie_und_zyklus(tmp_path):
    """Mandant unter Geschäft (parent_id), Zyklus-Schutz, Re-Parent der Kinder
    zur Wurzel beim Löschen des Übergeordneten."""
    with _client(tmp_path) as c:
        geschaeft = c.post("/api/bereiche", json={"name": "Geschäft X", "art": "geschaeft"}).json()["id"]
        mandant = c.post("/api/bereiche",
                         json={"name": "Mandant Müller", "art": "mandant", "parent_id": geschaeft}).json()["id"]
        # Filter nach parent
        kinder = c.get(f"/api/bereiche?parent_id={geschaeft}").json()
        assert [b["id"] for b in kinder] == [mandant]
        # Zyklus: Geschäft unter seinen eigenen Mandanten hängen ⇒ 400
        assert c.put(f"/api/bereiche/{geschaeft}", json={"parent_id": mandant}).status_code == 400
        # Löschen des Übergeordneten ⇒ Kind wird zur Wurzel hochgezogen
        c.delete(f"/api/bereiche/{geschaeft}")
        assert c.get(f"/api/bereiche/{mandant}").json()["parent_id"] == ""


def test_bereich_id_fk_migration_idempotent(tmp_path):
    """Die bereich_id-Spalte ist an allen Top-Level-Domänen-Tabellen vorhanden;
    erneuter Migrations-Lauf ist idempotent (kein Fehler, keine Dublette)."""
    with _client(tmp_path) as c:
        conn = c.app.state.bereiche.db.get_conn()
        for t in bm._BEREICH_FK_TABELLEN:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
            assert "bereich_id" in cols, f"{t} ohne bereich_id"
        # idempotent: nochmal migrieren ändert nichts (kein Crash)
        bm.migriere_bereich_fk(c.app.state.bereiche.db)
        cols2 = [r["name"] for r in conn.execute("PRAGMA table_info(kunden)")]
        assert cols2.count("bereich_id") == 1


def test_bereich_dsgvo_und_kontrakt_unberuehrt(tmp_path):
    """bereiche trägt user_id+deleted_at ⇒ taucht automatisch im DSGVO-Export auf
    (appkit user_tabellen); der bestehende Vertrag/Aggregator bleibt unberührt."""
    with _client(tmp_path) as c:
        c.post("/api/bereiche", json={"name": "Fortbildung Cloud", "art": "fortbildung"})
        export = c.app.state.bereiche.db.export_user("dizzi")
        assert "bereiche" in export and len(export["bereiche"]) == 1
        # Vertrag/Stats weiterhin erreichbar (kein Regress durch das neue Modul)
        assert "Umsatz" in c.get("/api/summary").text


def test_bereich_zuordnung_und_inhalt(tmp_path):
    """Generische Zuordnung quer über die Module + „Bereich → alles"-Übersicht."""
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Studium", "art": "studium"}).json()["id"]
        pid = c.post("/api/projekte", json={"name": "Bachelorarbeit"}).json()["id"]   # Projekte
        aid = c.post("/api/aufgaben", json={"titel": "Exposé"}).json()["id"]          # Projekte
        did = c.post("/api/dokumente/upload",
                     files={"datei": ("po.pdf", b"%PDF po", "application/pdf")},
                     data={"typ": "Sonstiges"}).json()["id"]                          # Tresor
        for tab, rid in (("projekte", pid), ("aufgaben", aid), ("dokumente", did)):
            assert c.put("/api/bereiche/zuordnung",
                         json={"tabelle": tab, "id": rid, "bereich_id": b}).json()["ok"]
        inh = c.get(f"/api/bereiche/{b}/inhalt").json()
        assert inh["gesamt"] == 3
        assert inh["zaehler"] == {"projekte": 1, "aufgaben": 1, "dokumente": 1}
        # Zuordnung lösen (→ Allgemein)
        c.put("/api/bereiche/zuordnung", json={"tabelle": "projekte", "id": pid, "bereich_id": ""})
        assert "projekte" not in c.get(f"/api/bereiche/{b}/inhalt").json()["zaehler"]


def test_bereich_zuordnung_validierung(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "X"}).json()["id"]
        pid = c.post("/api/projekte", json={"name": "P"}).json()["id"]
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "gibtsnicht", "id": pid, "bereich_id": b}).status_code == 400
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "projekte", "id": "fehlt", "bereich_id": b}).status_code == 404
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "projekte", "id": pid, "bereich_id": "fehlt"}).status_code == 400
        assert c.get("/api/bereiche/fehlt/inhalt").status_code == 404
