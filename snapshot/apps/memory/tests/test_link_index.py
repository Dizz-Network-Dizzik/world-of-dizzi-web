"""Wikilink-Index (P2.4): der `notiz_links`-Index hält graph/verknuepfungen
indiziert (statt Roh-Text-Scan über ALLE Notizen). Geprüft: Save-Hook hält den
Index live (Edit fügt/entfernt Kanten), Löschen räumt ausgehende Kanten, und der
einmalige Backfill baut den Index aus dem Bestand neu (Alt-DB-Pfad). Rename-Semantik
(titel-basiert, wie Obsidian) ist dokumentiert + getestet.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.main import APP_ID, default_db_path


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _neu(c, titel, inhalt=""):
    return c.post("/api/notizen", json={"titel": titel, "inhalt": inhalt}).json()["id"]


def test_save_hook_haelt_index_live(tmp_path):
    """Edit der Notiz ⇒ Backlinks ziehen sofort nach (Index über _sync_notiz)."""
    with _client(tmp_path) as c:
        a = _neu(c, "Alpha", "Hauptnotiz.")
        b = _neu(c, "Beta", "noch ohne Link")
        # anfangs kein Backlink auf Alpha
        assert c.get(f"/api/notizen/{a}/verknuepfungen").json()["erwaehnt_in"] == []
        # Beta editieren ⇒ Link auf Alpha ⇒ Backlink erscheint
        c.put(f"/api/notizen/{b}", json={"inhalt": "siehe [[Alpha]]"})
        va = c.get(f"/api/notizen/{a}/verknuepfungen").json()
        assert {"id": b, "titel": "Beta"} in va["erwaehnt_in"]
        assert {"von": b, "nach": a} in c.get("/api/graph").json()["edges"]
        # Link wieder entfernen ⇒ Backlink/Kante verschwinden (Index neu gesetzt)
        c.put(f"/api/notizen/{b}", json={"inhalt": "doch nicht"})
        assert c.get(f"/api/notizen/{a}/verknuepfungen").json()["erwaehnt_in"] == []
        assert c.get("/api/graph").json()["edges"] == []


def test_loeschen_raeumt_ausgehende_kanten(tmp_path):
    """Notiz löschen ⇒ ihre [[Links]] verschwinden aus Graph + Backlinks."""
    with _client(tmp_path) as c:
        a = _neu(c, "Ziel", "x")
        b = _neu(c, "Quelle", "[[Ziel]]")
        assert len(c.get("/api/graph").json()["edges"]) == 1
        c.delete(f"/api/notizen/{b}")
        assert c.get("/api/graph").json()["edges"] == []
        assert c.get(f"/api/notizen/{a}/verknuepfungen").json()["erwaehnt_in"] == []


def test_rename_semantik_titelbasiert(tmp_path):
    """Wikilinks sind TITEL-basiert (Obsidian/Logseq): wird die Ziel-Notiz
    umbenannt, zeigt der alte [[Titel]]-Verweis ins Leere (id=None), bis die
    Quell-Notiz nachgezogen wird — dokumentiertes, erwartetes Verhalten."""
    with _client(tmp_path) as c:
        a = _neu(c, "Alt", "Zielnotiz.")
        b = _neu(c, "Quelle", "siehe [[Alt]]")
        assert c.get(f"/api/notizen/{b}/verknuepfungen").json()["ausgehend"][0]["id"] == a
        # Ziel umbenennen ⇒ [[Alt]] löst nicht mehr auf
        c.put(f"/api/notizen/{a}", json={"titel": "Neu"})
        va = c.get(f"/api/notizen/{b}/verknuepfungen").json()
        assert va["ausgehend"] == [{"titel": "Alt", "id": None}]
        # Quelle auf den neuen Titel nachziehen ⇒ wieder aufgelöst
        c.put(f"/api/notizen/{b}", json={"inhalt": "siehe [[Neu]]"})
        assert c.get(f"/api/notizen/{b}/verknuepfungen").json()["ausgehend"][0]["id"] == a


def test_backfill_baut_index_aus_bestand(tmp_path):
    """Alt-DB-Pfad: Index + Flag entfernt ⇒ beim nächsten Start baut der Backfill
    den Wikilink-Index aus dem Vault/Bestand neu (idempotent, einmalig)."""
    with _client(tmp_path) as c:
        a = _neu(c, "Alpha", "x")
        b = _neu(c, "Beta", "siehe [[Alpha]]")
    # „Alt-DB ohne Index" simulieren: Index leeren + Backfill-Flag zurücksetzen
    raw = sqlite3.connect(str(default_db_path(APP_ID, data_root=tmp_path)))
    raw.execute("DELETE FROM notiz_links")
    raw.execute("DELETE FROM app_settings WHERE key='links_index_gebaut'")
    raw.commit()
    raw.close()
    # Neu öffnen ⇒ Backfill repopuliert den Index
    with _client(tmp_path) as c:
        g = c.get("/api/graph").json()
        assert {"von": b, "nach": a} in g["edges"]
        va = c.get(f"/api/notizen/{a}/verknuepfungen").json()
        assert {"id": b, "titel": "Beta"} in va["erwaehnt_in"]
