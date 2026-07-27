"""Domänen-Tests Dizz Memory: Vault-Spiegel, Ordner, Labels, FTS-Suche,
Import, Reindex, quellen-gestützte KI. KI ist gemockt (kein Ollama nötig)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.vault import MarkdownVault


class _FakeResp:
    status_code = 200

    def __init__(self, antwort: str):
        self._a = antwort

    def json(self):
        import json
        return {"message": {"content": json.dumps({"antwort": self._a})}}


def _client(tmp_path, antwort="Aus deinen Notizen: A."):
    def fake_post(url, json):
        return _FakeResp(antwort)
    app = am.build_app(data_dir=tmp_path, http_post=fake_post, start_import_timer=False)
    c = TestClient(app)
    c._root = tmp_path  # type: ignore[attr-defined]
    return c


def _vault(tmp_path) -> MarkdownVault:
    return MarkdownVault(Path(tmp_path) / "apps" / "memory" / "vault")


def test_notiz_crud_und_vault_spiegel(tmp_path):
    with _client(tmp_path) as c:
        nid = c.post("/api/notizen", json={"titel": "Idee Alpha",
                     "inhalt": "Erste Zeile\nZweite [[Link]]."}).json()["id"]
        d = c.get(f"/api/notizen/{nid}").json()
        assert d["titel"] == "Idee Alpha" and "Zweite" in d["inhalt"]

        # Vault-Datei existiert, mit Frontmatter + Körper
        v = _vault(tmp_path)
        dateien = list(v.iter_dateien("dizzi"))
        assert len(dateien) == 1
        rel, fm, body = dateien[0]
        assert fm["id"] == nid and fm["titel"] == "Idee Alpha"
        assert "[[Link]]" in body and rel.endswith(".md")

        # Bearbeiten ⇒ Spiegel zieht nach
        c.put(f"/api/notizen/{nid}", json={"inhalt": "Geändert XYZ"})
        _, _, body2 = list(v.iter_dateien("dizzi"))[0]
        assert "XYZ" in body2

        # Löschen ⇒ Datei wandert in .trash, Index weich gelöscht
        c.delete(f"/api/notizen/{nid}")
        assert c.get(f"/api/notizen/{nid}").status_code == 404
        assert list(v.iter_dateien("dizzi")) == []
        assert any((Path(v.user_root("dizzi")) / ".trash").glob("*.md"))


def test_ordner_hierarchie_und_loeschen_umhaengt(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/ordner", json={"name": "Projekte"}).json()["id"]
        b = c.post("/api/ordner", json={"name": "2026", "parent_id": a}).json()["id"]
        nid = c.post("/api/notizen", json={"titel": "Plan", "ordner_id": b}).json()["id"]

        # Vault spiegelt die Hierarchie als Verzeichnis
        v = _vault(tmp_path)
        rel = list(v.iter_dateien("dizzi"))[0][0]
        assert rel.startswith("Projekte/2026/")

        # Ordner umbenennen ⇒ Datei-Pfad zieht nach
        c.put(f"/api/ordner/{a}", json={"name": "Vorhaben"})
        rel2 = list(v.iter_dateien("dizzi"))[0][0]
        assert rel2.startswith("Vorhaben/2026/")

        # Schleifen-Schutz: A unter seinen Nachfahren B verschieben ⇒ 400
        assert c.put(f"/api/ordner/{a}",
                     json={"parent_id": b, "parent_setzen": True}).status_code == 400

        # Ordner löschen (ohne Inhalt) ⇒ Notiz an die Wurzel, nicht weg
        c.delete(f"/api/ordner/{b}")
        d = c.get(f"/api/notizen/{nid}").json()
        assert d["ordner_id"] is None
        assert list(v.iter_dateien("dizzi"))[0][0].count("/") == 0


def test_labels_anlegen_zuordnen_filtern(tmp_path):
    with _client(tmp_path) as c:
        lid = c.post("/api/labels", json={"name": "recherche", "farbe": "magenta"}).json()["id"]
        n1 = c.post("/api/notizen", json={"titel": "Mit Label"}).json()["id"]
        n2 = c.post("/api/notizen", json={"titel": "Ohne Label"}).json()["id"]
        c.post(f"/api/notizen/{n1}/labels", json={"label_id": lid})

        # Filter nach Label liefert nur n1
        gefiltert = c.get(f"/api/notizen?label={lid}").json()
        assert [x["id"] for x in gefiltert] == [n1]
        # Label-Liste zählt die Zuordnung
        labels = {l["name"]: l for l in c.get("/api/labels").json()}
        assert labels["recherche"]["anzahl"] == 1
        # Frontmatter der Datei trägt das Label
        rels = {rel: fm for rel, fm, _ in _vault(tmp_path).iter_dateien("dizzi")}
        assert any("recherche" in (fm.get("labels") or []) for fm in rels.values())

        # Label wieder entfernen
        c.delete(f"/api/notizen/{n1}/labels/{lid}")
        assert c.get(f"/api/notizen?label={lid}").json() == []


def test_label_loeschen_loest_zuordnungen(tmp_path):
    """docs/26 §9.2: ein Label ganz löschen (Soft-Delete) — verschwindet aus der
    Liste UND aus allen Notizen (Zuordnungen gelöst, Notiz bleibt erhalten)."""
    with _client(tmp_path) as c:
        lid = c.post("/api/labels", json={"name": "wegdamit"}).json()["id"]
        nid = c.post("/api/notizen", json={"titel": "Hat Label"}).json()["id"]
        c.post(f"/api/notizen/{nid}/labels", json={"label_id": lid})
        assert {l["name"] for l in c.get("/api/labels").json()} == {"wegdamit"}

        assert c.delete(f"/api/labels/{lid}").json()["ok"] is True
        # Aus der Label-Liste raus …
        assert c.get("/api/labels").json() == []
        # … die Notiz lebt weiter, trägt das Label aber nicht mehr.
        det = c.get(f"/api/notizen/{nid}").json()
        assert det["titel"] == "Hat Label" and det["labels"] == []


def test_migration_alt_db_herkunft_boolean_zu_art_enum(tmp_path):
    """docs/26 §9.5: eine ALT-DB (Boolean ``herkunft`` + globales UNIQUE) wird beim
    Start migriert — Spalte ``art``, ``herkunft=1`` → ``art='herkunft'``, UNIQUE per
    Tabellen-Rebuild weg ⇒ Nutzer- und Herkunfts-Label gleichen Namens koexistieren.
    (Genau der Pfad, den die Live-:8212-DB durchläuft.)"""
    import sqlite3
    from appkit.db import default_db_path
    dbp = default_db_path("memory", data_root=Path(tmp_path))
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dbp)
    con.executescript(
        "CREATE TABLE labels (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,"
        " farbe TEXT NOT NULL DEFAULT 'cyan', herkunft INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,"
        " UNIQUE (user_id, name));")
    con.execute("INSERT INTO labels VALUES ('a','dizzi','alt','cyan',0,'t','t',NULL)")
    con.execute("INSERT INTO labels VALUES ('b','dizzi','News','magenta',1,'t','t',NULL)")
    con.commit(); con.close()

    with _client(tmp_path) as c:
        labels = {l["name"]: l for l in c.get("/api/labels").json()}
        assert labels["alt"]["art"] == "normal"
        assert labels["News"]["art"] == "herkunft"       # Boolean korrekt nach art migriert
        # UNIQUE weg ⇒ ein gleichnamiges NUTZER-Label „News" koexistiert jetzt.
        c.post("/api/labels", json={"name": "News"})
        arten = sorted(l["art"] for l in c.get("/api/labels").json() if l["name"] == "News")
        assert arten == ["herkunft", "normal"]

    # Legacy-Spalte ist nach dem Rebuild weg, ``art`` da.
    con = sqlite3.connect(dbp)
    spalten = [r[1] for r in con.execute("PRAGMA table_info(labels)").fetchall()]
    con.close()
    assert "art" in spalten and "herkunft" not in spalten


def test_frische_db_kein_unnoetiger_rebuild(tmp_path):
    """Regression (docs/26 §9.5): die Art-Migration darf auf einer FRISCHEN DB NICHT
    rebuilden. Erkannt wird der Rebuild-Bedarf an der Legacy-Spalte ``herkunft`` —
    NICHT am Wort „unique" im gespeicherten Schema-SQL (SQLite behält Kommentare,
    und der _SCHEMA-Kommentar erwähnt „partielle Unique-Indizes"). Ein Rebuild
    benennt die Tabelle per RENAME um ⇒ gequoteter Name ``"labels"``; bleibt der aus,
    fand kein Rebuild statt."""
    import sqlite3
    from appkit.db import default_db_path
    with _client(tmp_path):
        pass
    con = sqlite3.connect(default_db_path("memory", data_root=Path(tmp_path)))
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='labels'").fetchone()[0]
    cols = [r[1] for r in con.execute("PRAGMA table_info(labels)").fetchall()]
    idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='labels'").fetchall()}
    con.close()
    assert '"labels"' not in sql, "unnötiger Tabellen-Rebuild auf frischer DB"
    assert "art" in cols and "herkunft" not in cols
    assert {"ux_labels_norm", "ux_labels_herk"} <= idx     # partielle Indizes trotzdem da


def test_volltextsuche_fts(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Quantencomputer",
               "inhalt": "Supraleitende Qubits und Fehlerkorrektur."})
        c.post("/api/notizen", json={"titel": "Gartenplan",
               "inhalt": "Tomaten und Basilikum im Mai."})

        treffer = c.get("/api/suche?q=qubit").json()
        assert len(treffer) == 1 and treffer[0]["titel"] == "Quantencomputer"
        assert "«" in treffer[0]["auszug"] or "»" in treffer[0]["auszug"]

        # Prefix-Suche + Sonderzeichen dürfen nie crashen
        assert c.get("/api/suche?q=tomat").json()[0]["titel"] == "Gartenplan"
        assert c.get('/api/suche?q="; DROP').status_code == 200
        assert c.get("/api/suche?q=").json() == []


def test_import_markdown_legt_ordner_und_labels_an(tmp_path):
    with _client(tmp_path) as c:
        roh = ("---\ntitel: Importnotiz\nordner: Import/Alt\n"
               "labels: [alt, wichtig]\n---\n\nInhalt aus Mem.")
        r = c.post("/api/import/markdown", json={"dokumente": [
            roh,
            {"titel": "Direkt", "inhalt": "Direkter Body", "ordner": "Import/Alt"},
        ]}).json()
        assert r["erstellt"] == 2

        # Ordnerkette Import/Alt wurde angelegt (geteilt von beiden)
        namen = {o["name"] for o in c.get("/api/ordner").json()}
        assert {"Import", "Alt"} <= namen
        # Labels angelegt
        labelnamen = {l["name"] for l in c.get("/api/labels").json()}
        assert {"alt", "wichtig"} <= labelnamen
        # Inhalt suchbar
        assert c.get("/api/suche?q=Mem").json()[0]["titel"] == "Importnotiz"


def test_reindex_baut_fts_neu(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Reindex", "inhalt": "Findwort zebra."})
        assert c.get("/api/suche?q=zebra").json()
        r = c.post("/api/reindex").json()
        assert r["ok"] and r["notizen"] == 1
        assert c.get("/api/suche?q=zebra").json()  # nach Reindex weiterhin findbar


def test_ki_frage_quellengestuetzt(tmp_path):
    with _client(tmp_path, antwort="Laut 'Strategie 2026': Fokus Qualität.") as c:
        c.post("/api/notizen", json={"titel": "Strategie 2026",
               "inhalt": "Fokus auf Qualität und Gründlichkeit."})
        out = c.post("/api/frage", json={"frage": "Was ist die Strategie?"}).json()
        assert "Qualität" in out["antwort"]
        assert "Strategie 2026" in out["quellen"]
        # Mini-Dizzi-Brücke nutzt dieselbe App-KI
        a = c.post("/api/ki/frage", json={"frage": "Strategie?"}).json()
        assert a["antwort"] and a["quelle"] == "app_ki"


def test_summary_kpis(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/ordner", json={"name": "X"})
        c.post("/api/labels", json={"name": "y"})
        c.post("/api/notizen", json={"titel": "Z"})
        kpis = {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}
        assert kpis["notizen"] == 1 and kpis["ordner"] == 1 and kpis["labels"] == 1
        assert kpis["letzte"] != "—"
