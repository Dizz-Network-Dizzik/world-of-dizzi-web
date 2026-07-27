"""Tests Dizz Admin — Live-Daten-Migration (docs/28 §15, Phase 4): TROCKEN-Test des
Merge-Schreibpfads gegen synthetische Quell-DBs (inkl. Admins SCHLANKEM ``aufgaben``,
um den Spalten-Mismatch zu beweisen). Schreibt NIE echte Daten. Lauf: pytest tests/ -q
"""

from __future__ import annotations

import sqlite3

from appkit.db import Database, new_id, now_iso

from adminapp import migration, projekte, tresor


def _plans_quelle(pfad):
    """Plans-Quelle mit REICHEM aufgaben-Schema (wie die echte plans.sqlite)."""
    db = Database(pfad, extra_schema=projekte.SCHEMA_PROJEKTE)
    c = db.get_conn(); ts = now_iso(); pid = new_id()
    c.execute("INSERT INTO projekte (id,user_id,name,beschreibung,status,farbe,app_id,"
              "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (pid, "dizzi", "Projekt A", "", "aktiv", "cyan", "", ts, ts))
    c.execute("INSERT INTO aufgaben (id,user_id,projekt_id,titel,notiz,status,prioritaet,"
              "faellig,meilenstein,abhaengig_von,rrule,created_at,updated_at) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (new_id(), "dizzi", pid, "Plans-Aufgabe", "", "offen", "mittel", "",
               0, "[]", "", ts, ts))
    c.execute("INSERT INTO termine (id,user_id,titel,beginn,created_at,updated_at) "
              "VALUES (?,?,?,?,?,?)", (new_id(), "dizzi", "Termin", "2026-07-01", ts, ts))
    c.commit()
    return db


def _admin_quelle(pfad):
    """Admin-Quelle mit SCHLANKEM aufgaben (ohne projekt_id/rrule) + Dokument + V15."""
    c = sqlite3.connect(pfad)
    c.executescript(tresor.SCHEMA_TRESOR)                 # dokumente + fts + verknuepfungen
    c.execute("CREATE TABLE aufgaben (id TEXT PRIMARY KEY, user_id TEXT, titel TEXT, "
              "faellig TEXT DEFAULT '', status TEXT DEFAULT 'offen', "
              "prioritaet TEXT DEFAULT 'mittel', notiz TEXT DEFAULT '', "
              "created_at TEXT, updated_at TEXT, deleted_at TEXT)")
    ts = now_iso(); did = new_id()
    c.execute("INSERT INTO dokumente (id,user_id,titel,typ,datei_pfad,datei_name,groesse,"
              "erstellt_am,tags,notiz,sha256,volltext,volltext_methode,quelle,korrespondent,"
              "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (did, "dizzi", "Rechnung Mai", "Rechnung", "dizzi/x.pdf", "x.pdf", 100, ts,
               "[]", "", "sha1", "Stromkosten Mai 2026", "txt", "upload", "Stadtwerke", ts, ts))
    c.execute("INSERT INTO dokument_verknuepfungen (id,user_id,dok_id,von_app,von_ref,"
              "von_titel,created_at) VALUES (?,?,?,?,?,?,?)",
              (new_id(), "dizzi", did, "finanzen", "finanzen:buchung:1", "Buchung", ts))
    c.execute("INSERT INTO aufgaben (id,user_id,titel,created_at,updated_at) "
              "VALUES (?,?,?,?,?)", (new_id(), "dizzi", "Admin-Buero-Aufgabe", ts, ts))
    c.commit(); c.close()


def test_merge_quellen_dry(tmp_path):
    _plans_quelle(tmp_path / "plans.sqlite")
    _admin_quelle(tmp_path / "admin.sqlite")
    ziel_p = tmp_path / "ziel" / "admin.sqlite"
    ziel_p.parent.mkdir(parents=True)
    zdb = migration.ziel_db(ziel_p)
    bericht = migration.merge_quellen(zdb, {
        "plans": tmp_path / "plans.sqlite",
        "admin": tmp_path / "admin.sqlite",
        "leading": tmp_path / "fehlt.sqlite",            # nicht vorhanden ⇒ übersprungen
    })
    z = bericht["ziel"]
    assert z["projekte"] == 1 and z["termine"] == 1
    assert z["aufgaben"] == 2                              # Plans-reich + Admin-schlank gemerged
    assert z["dokumente"] == 1 and z["dokument_verknuepfungen"] == 1
    assert bericht["fts_indexiert"] == 1
    # Admins schlanke Aufgabe bekam die Ziel-Defaults (Spalten-Mismatch gelöst)
    conn = zdb.get_conn()
    a = conn.execute("SELECT * FROM aufgaben WHERE titel='Admin-Buero-Aufgabe'").fetchone()
    assert a["projekt_id"] == "" and a["abhaengig_von"] == "[]" and a["bereich_id"] == ""
    # FTS-Suche findet das importierte Dokument
    hits = conn.execute("SELECT dok_id FROM dokumente_fts WHERE dokumente_fts MATCH 'Stromkosten*'").fetchall()
    assert len(hits) == 1
    # bereich_id-Spalte überall (Ziel-Schema komplett)
    assert "bereich_id" in {r["name"] for r in conn.execute("PRAGMA table_info(dokumente)")}


def test_merge_idempotent(tmp_path):
    _plans_quelle(tmp_path / "plans.sqlite")
    ziel_p = tmp_path / "ziel" / "admin.sqlite"
    ziel_p.parent.mkdir(parents=True)
    zdb = migration.ziel_db(ziel_p)
    sources = {"plans": tmp_path / "plans.sqlite"}
    migration.merge_quellen(zdb, sources)
    b2 = migration.merge_quellen(zdb, sources)            # zweiter Lauf
    assert b2["ziel"]["projekte"] == 1 and b2["ziel"]["aufgaben"] == 1   # keine Dubletten
    assert b2["quellen"]["plans.projekte"]["importiert"] == 0           # alles OR IGNORE
