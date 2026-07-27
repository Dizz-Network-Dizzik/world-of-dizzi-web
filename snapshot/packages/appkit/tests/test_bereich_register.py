"""Vertrags-Tests zum Bereichs-Kanon ``appkit.bereich_register`` (docs/67, VO-2 —
Design-Stufe 0): Schema-Single-Source wertgleich zu den vier Bestands-DDLs ·
MIG-KANON-1 idempotent · Dual-Read-Auflösekette (kanon→kontext, Stufe-0-wertgleich
ohne Spalte) · fail-closed-Bindung · Broken-Link-Wächter · Backfill-Dry-Run ·
Ober-Kategorien-Mapping · Baum/Roll-up (ME-1-Muster)."""

from __future__ import annotations

import re

import pytest
from fastapi import HTTPException

from appkit.bereich_register import (AnkerIndex, Aufloesung, DzBereichRegister,
                                     MIG_PHASEN, OBER_KATEGORIEN, WAECHTER_BEFUNDE,
                                     WAECHTER_KANTEN, anker_index,
                                     backfill_vorschlaege, baum_bauen,
                                     mapping_validieren, migriere_bereich_fk,
                                     migriere_kanon_id,
                                     mit_ober_kategorie, ober_kategorie_fuer,
                                     rollup_zaehler, schema_bereiche, waechter_report)
from appkit.db import Database

U = "u1"

# ── Golden-DDLs: wörtliche Kopien der vier App-Schemata (Stand 04.07.2026) ──────
# Quelle: moneyapp/managementapp/archivapp/adminapp ``bereiche.py``. BER-3.1 ersetzt
# die App-Literale durch ``schema_bereiche(…)`` — bis dahin pinnen diese Goldens die
# Wertgleichheit (Vergleich kommentar-/whitespace-normalisiert).
_GOLD_MONEY = """
CREATE TABLE IF NOT EXISTS bereiche (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    art           TEXT NOT NULL DEFAULT 'sonstiges',   -- geschaeft|privat|projekt|mandant|investment|sonstiges
    parent_id     TEXT NOT NULL DEFAULT '',            -- Selbst-FK ('' = Wurzel); Mandant unter Geschäft
    farbe         TEXT NOT NULL DEFAULT 'cyan',
    icon          TEXT NOT NULL DEFAULT 'folder',
    status        TEXT NOT NULL DEFAULT 'aktiv',        -- aktiv|ruhend|abgeschlossen|archiviert
    beschreibung  TEXT NOT NULL DEFAULT '',
    kontext       TEXT NOT NULL DEFAULT '',             -- stabiler Schlüssel = Admins bereich.money_kontext (V17)
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bereiche ON bereiche (user_id, status, sort_order);
CREATE INDEX IF NOT EXISTS idx_bereiche_parent ON bereiche (user_id, parent_id);
"""

_GOLD_MANAGEMENT = """
CREATE TABLE IF NOT EXISTS bereiche (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    art           TEXT NOT NULL DEFAULT 'sonstiges',   -- kunde|marke|kampagne|projekt|persoenlich|sonstiges
    parent_id     TEXT NOT NULL DEFAULT '',            -- Selbst-FK ('' = Wurzel)
    farbe         TEXT NOT NULL DEFAULT 'cyan',
    icon          TEXT NOT NULL DEFAULT 'folder',
    status        TEXT NOT NULL DEFAULT 'aktiv',        -- aktiv|ruhend|abgeschlossen|archiviert
    beschreibung  TEXT NOT NULL DEFAULT '',
    kontext       TEXT NOT NULL DEFAULT '',             -- stabiler Schlüssel = Admins bereich.management_kontext (V18)
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bereiche ON bereiche (user_id, status, sort_order);
CREATE INDEX IF NOT EXISTS idx_bereiche_parent ON bereiche (user_id, parent_id);
"""

_GOLD_MEMORY = """
CREATE TABLE IF NOT EXISTS bereiche (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    art           TEXT NOT NULL DEFAULT 'sonstiges',   -- projekt|lebensbereich|wissen|referenz|sonstiges
    parent_id     TEXT NOT NULL DEFAULT '',            -- Selbst-FK ('' = Wurzel)
    farbe         TEXT NOT NULL DEFAULT 'cyan',
    icon          TEXT NOT NULL DEFAULT 'folder',
    status        TEXT NOT NULL DEFAULT 'aktiv',        -- aktiv|ruhend|abgeschlossen|archiviert
    beschreibung  TEXT NOT NULL DEFAULT '',
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bereiche ON bereiche (user_id, status, sort_order);
CREATE INDEX IF NOT EXISTS idx_bereiche_parent ON bereiche (user_id, parent_id);
"""

_GOLD_ADMIN = """
CREATE TABLE IF NOT EXISTS bereiche (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    art           TEXT NOT NULL DEFAULT 'sonstiges',   -- studium|geschaeft|mandant|fortbildung|privat|sonstiges
    parent_id     TEXT NOT NULL DEFAULT '',            -- Selbst-FK ('' = Wurzel); Mandant unter Geschäft
    farbe         TEXT NOT NULL DEFAULT 'cyan',
    icon          TEXT NOT NULL DEFAULT 'folder',
    status        TEXT NOT NULL DEFAULT 'aktiv',        -- aktiv|ruhend|abgeschlossen|archiviert
    beschreibung  TEXT NOT NULL DEFAULT '',
    memory_ref    TEXT NOT NULL DEFAULT '',             -- gespiegelte Memory-Kategorie (V19)
    money_kontext TEXT NOT NULL DEFAULT '',             -- Schlüssel der per-Bereich-Finanzspur (V17)
    management_kontext TEXT NOT NULL DEFAULT '',        -- Schlüssel der per-Bereich-Social-Spur (V18, A5)
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bereiche ON bereiche (user_id, status, sort_order);
CREATE INDEX IF NOT EXISTS idx_bereiche_parent ON bereiche (user_id, parent_id);
"""

# Golden-``art``-Kataloge der vier Apps (Stand 04.07.) für den Mapping-Vollständigkeits-Vertrag.
_ARTEN = {
    "admin": ("geschaeft", "studium", "mandant", "fortbildung", "persoenlich", "sonstiges"),
    "money": ("geschaeft", "privat", "projekt", "mandant", "investment", "sonstiges"),
    "memory": ("projekt", "lebensbereich", "wissen", "referenz", "sonstiges"),
    "management": ("kunde", "marke", "kampagne", "projekt", "persoenlich", "sonstiges"),
}


def _norm(sql: str) -> str:
    """Kommentare raus, Whitespace kollabiert — vergleicht die DDL-Substanz."""
    return " ".join(re.sub(r"--[^\n]*", "", sql).split())


def _db(tmp_path, name="b.sqlite", *, kontext=True, kanon=False) -> Database:
    schema = schema_bereiche(("kontext",) if kontext else (), mit_kanon=kanon)
    return Database(tmp_path / name, extra_schema=schema)


def _bereich(db: Database, bid: str, name: str, *, user=U, kontext="", kanon="",
             parent="", sort=0) -> None:
    conn = db.get_conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(bereiche)")}
    felder = {"id": bid, "user_id": user, "name": name, "art": "sonstiges",
              "parent_id": parent, "farbe": "cyan", "icon": "folder", "status": "aktiv",
              "beschreibung": "", "sort_order": sort,
              "created_at": "2026-07-04T00:00:00+00:00",
              "updated_at": "2026-07-04T00:00:00+00:00"}
    if "kontext" in cols:
        felder["kontext"] = kontext
    if "kanon_id" in cols:
        felder["kanon_id"] = kanon
    conn.execute(f"INSERT INTO bereiche ({','.join(felder)}) "
                 f"VALUES ({','.join('?' * len(felder))})", list(felder.values()))
    conn.commit()


# ── Schema-Single-Source (docs/67 §5.2) ─────────────────────────────────────────
def test_schema_wertgleich_money_und_management():
    erzeugt = _norm(schema_bereiche(("kontext",)))
    assert erzeugt == _norm(_GOLD_MONEY)
    assert erzeugt == _norm(_GOLD_MANAGEMENT)


def test_schema_wertgleich_memory():
    assert _norm(schema_bereiche(())) == _norm(_GOLD_MEMORY)


def test_schema_wertgleich_admin():
    assert _norm(schema_bereiche(("memory_ref", "money_kontext",
                                  "management_kontext"))) == _norm(_GOLD_ADMIN)


def test_schema_mit_kanon_ergaenzt_spalte_und_index():
    ohne = schema_bereiche(("kontext",))
    mit = schema_bereiche(("kontext",), mit_kanon=True)
    assert "kanon_id" not in ohne and "idx_bereiche_kanon" not in ohne
    assert "kanon_id" in mit and "idx_bereiche_kanon" in mit
    # kanon_id sitzt VOR sort_order (stabile Spalten-Ordnung des Vertrags)
    assert mit.index("kanon_id") < mit.index("sort_order")


def test_schema_bereiche_verweigert_boesen_kontext_spaltennamen():
    """docs/71 R-17: der Generator interpoliert kontext-Spalten ROH in die DDL ⇒
    Whitelist-Pflicht (dieselbe Strenge wie ``DzBereichRegister.kontext_spalte``)."""
    with pytest.raises(ValueError):
        schema_bereiche(("kontext; DROP TABLE bereiche",))
    with pytest.raises(ValueError):
        schema_bereiche(("memory_ref", "Boese Spalte"))
    # die vier realen Konfigurationen bleiben gültig (kein False-Positive)
    for kfg in ((), ("kontext",), ("memory_ref", "money_kontext", "management_kontext")):
        schema_bereiche(kfg)


# ── MIG-KANON-1 (docs/67 §7 P1) ─────────────────────────────────────────────────
def test_migriere_kanon_id_idempotent_daten_intakt(tmp_path):
    db = _db(tmp_path)
    _bereich(db, "b1", "Alt", kontext="k1")
    migriere_kanon_id(db)
    migriere_kanon_id(db)                                     # rerun ⇒ kein Fehler
    conn = db.get_conn()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(bereiche)")]
    assert cols.count("kanon_id") == 1
    row = conn.execute("SELECT * FROM bereiche WHERE id='b1'").fetchone()
    assert row["name"] == "Alt" and row["kontext"] == "k1" and row["kanon_id"] == ""
    idx = {r["name"] for r in conn.execute("PRAGMA index_list(bereiche)")}
    assert "idx_bereiche_kanon" in idx


def test_migriere_ohne_bereiche_tabelle_noop(tmp_path):
    db = Database(tmp_path / "leer.sqlite", extra_schema="")
    migriere_kanon_id(db)                                     # darf nicht werfen


def test_migriere_bereich_fk_ruestet_spalte_und_index_nach(tmp_path):
    """Geteilte ``bereich_id``-FK-Nachrüstung (B-4, docs/67 §5): additive Spalte +
    ``idx_<t>_bereich``, idempotent; fehlende Tabellen werden übersprungen; Bezeichner
    Whitelist-geprüft (kein Injection). Verhält sich wortgleich zur zuvor in Admin/Memory
    duplizierten Schleife."""
    db = Database(tmp_path / "fk.sqlite",
                  extra_schema="CREATE TABLE konten (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);")
    migriere_bereich_fk(db, ("konten", "fehlt_noch"))         # 'fehlt_noch' existiert nicht ⇒ skip
    migriere_bereich_fk(db, ("konten", "fehlt_noch"))         # rerun ⇒ idempotent
    conn = db.get_conn()
    assert [r["name"] for r in conn.execute("PRAGMA table_info(konten)")].count("bereich_id") == 1
    assert "idx_konten_bereich" in {r["name"] for r in conn.execute("PRAGMA index_list(konten)")}
    assert "fehlt_noch" not in {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}   # nichts angelegt
    with pytest.raises(ValueError):                            # Injection-Bezeichner ⇒ fail-closed
        migriere_bereich_fk(db, ("konten; DROP TABLE konten",))


# ── Auflösekette (docs/67 §3.2) ─────────────────────────────────────────────────
@pytest.fixture
def reg(tmp_path):
    db = _db(tmp_path, kanon=True)
    return DzBereichRegister(db), db


def test_aufloesen_kanon_gewinnt(reg):
    r, db = reg
    _bereich(db, "b1", "A", kontext="nagelfabrik", kanon="K-1")
    _bereich(db, "b2", "B", kontext="anders")
    assert r.aufloesen(U, kanon="K-1", kontext="anders") == Aufloesung("b1", "kanon", False)


def test_aufloesen_dangling_kanon_faellt_auf_kontext(reg):
    r, db = reg
    _bereich(db, "b1", "A", kontext="nagelfabrik")
    assert r.aufloesen(U, kanon="GIBTS-NICHT", kontext="nagelfabrik") == \
        Aufloesung("b1", "kontext", False)


def test_aufloesen_kontext_case_insensitiv_und_trim(reg):
    r, db = reg
    _bereich(db, "b1", "A", kontext="NagelFabrik")
    assert r.aufloesen(U, kontext="  nagelfabrik ").bereich_id == "b1"


def test_aufloesen_kontext_mehrdeutig_deterministisch(reg):
    r, db = reg
    _bereich(db, "b2", "Zwei", kontext="doppelt", sort=1)
    _bereich(db, "b1", "Eins", kontext="Doppelt", sort=0)
    a = r.aufloesen(U, kontext="doppelt")
    assert a == Aufloesung("b1", "kontext", True)             # sort_order, name + Flag


def test_aufloesen_kanon_mehrdeutig_ist_datenfehler_flag(reg):
    r, db = reg
    _bereich(db, "b1", "A", kanon="K-1", sort=0)
    _bereich(db, "b2", "B", kanon="K-1", sort=1)              # direkter Insert umgeht I-4
    a = r.aufloesen(U, kanon="K-1")
    assert a.bereich_id == "b1" and a.quelle == "kanon" and a.mehrdeutig


def test_aufloesen_ohne_kanon_spalte_stufe0_wertgleich(tmp_path):
    db = _db(tmp_path, kanon=False)                           # MIG-KANON-1 nicht gelaufen
    r = DzBereichRegister(db)
    _bereich(db, "b1", "A", kontext="k")
    assert r.aufloesen(U, kanon="egal", kontext="k") == Aufloesung("b1", "kontext", False)


def test_aufloesen_kein_treffer_und_leere_parameter(reg):
    r, db = reg
    _bereich(db, "b1", "A", kontext="k")
    assert r.aufloesen(U, kontext="fremd") == Aufloesung(None, "", False)
    assert r.aufloesen(U) == Aufloesung(None, "", False)
    assert r.aufloesen(U, kontext="   ") == Aufloesung(None, "", False)


def test_aufloesen_user_isolation_und_soft_delete(reg):
    r, db = reg
    _bereich(db, "b1", "A", kontext="k", kanon="K-1", user="ANDERER")
    assert r.aufloesen(U, kanon="K-1", kontext="k").bereich_id is None
    _bereich(db, "b2", "B", kontext="weg", kanon="K-2")
    db.get_conn().execute("UPDATE bereiche SET deleted_at='x' WHERE id='b2'")
    assert r.aufloesen(U, kanon="K-2", kontext="weg").bereich_id is None


def test_memory_konfig_ohne_kontext_spalte(tmp_path):
    db = _db(tmp_path, kontext=False, kanon=True)             # Memory: kontext_spalten=()
    r = DzBereichRegister(db, kontext_spalte="")
    _bereich(db, "b1", "Wissen", kanon="K-1")
    assert r.aufloesen(U, kanon="K-1").quelle == "kanon"
    assert r.aufloesen(U, kontext="Wissen").bereich_id is None  # Stufe ② strukturell aus


def test_konstruktor_verweigert_boesen_spaltennamen(tmp_path):
    with pytest.raises(ValueError):
        DzBereichRegister(_db(tmp_path), kontext_spalte="kontext; DROP TABLE x")


# ── Bindung verknuepfen/loesen (docs/67 §3.1, I-4/I-10) ─────────────────────────
def test_verknuepfen_setzt_rebind_und_korrektur(reg):
    r, db = reg
    _bereich(db, "b1", "A")
    assert r.verknuepfen(U, "b1", "K-1")["ok"] is True
    assert r.kanon_status(U)[0]["kanon_id"] == "K-1"
    r.verknuepfen(U, "b1", "K-1")                             # idempotentes Re-Bind
    r.verknuepfen(U, "b1", "K-NEU")                           # Korrektur erlaubt
    assert r.kanon_status(U)[0]["kanon_id"] == "K-NEU"


def test_verknuepfen_fail_closed(reg):
    r, db = reg
    _bereich(db, "b1", "A", kanon="K-1")
    _bereich(db, "b2", "B")
    with pytest.raises(HTTPException) as e:                   # Doppelbindung (I-4)
        r.verknuepfen(U, "b2", "K-1")
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:                   # unbekannter Bereich
        r.verknuepfen(U, "fehlt", "K-9")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:                   # leere kanon_id
        r.verknuepfen(U, "b2", "  ")
    assert e.value.status_code == 400


def test_verknuepfen_ohne_spalte_klarer_fehler(tmp_path):
    db = _db(tmp_path, kanon=False)
    r = DzBereichRegister(db)
    _bereich(db, "b1", "A")
    with pytest.raises(HTTPException) as e:
        r.verknuepfen(U, "b1", "K-1")
    assert e.value.status_code == 409 and "MIG-KANON-1" in e.value.detail


def test_eindeutigkeit_ist_pro_user(reg):
    r, db = reg
    _bereich(db, "b1", "A")
    _bereich(db, "x1", "X", user="ANDERER")
    r.verknuepfen(U, "b1", "K-1")
    r2 = DzBereichRegister(db)
    assert r2.verknuepfen("ANDERER", "x1", "K-1")["ok"] is True   # I-4: pro User


def test_loesen(reg):
    r, db = reg
    _bereich(db, "b1", "A", kanon="K-1")
    assert r.loesen(U, "b1")["kanon_id"] == ""
    assert r.kanon_status(U)[0]["kanon_id"] == ""
    with pytest.raises(HTTPException):
        r.loesen(U, "fehlt")


def test_kanon_status_feed_in_jeder_phase(tmp_path):
    db0 = _db(tmp_path, "vorher.sqlite", kanon=False)         # vor MIG-KANON-1
    _bereich(db0, "b1", "A", kontext="k1")
    feed0 = DzBereichRegister(db0).kanon_status(U)
    assert feed0 == [{"id": "b1", "name": "A", "kanon_id": "", "kontext": "k1"}]
    db1 = _db(tmp_path, "nachher.sqlite", kanon=True)
    _bereich(db1, "b2", "Zwei", kontext="k2", kanon="K-2", sort=1)
    _bereich(db1, "b1", "Eins", sort=0)
    feed1 = DzBereichRegister(db1).kanon_status(U)
    assert [f["id"] for f in feed1] == ["b1", "b2"]           # sort_order, name
    assert feed1[1]["kanon_id"] == "K-2"


# ── Broken-Link-Wächter (docs/67 §3.4 — pure) ───────────────────────────────────
def _admin(bid, name, **slots):
    return {"id": bid, "name": name, "money_kontext": "", "management_kontext": "",
            "memory_ref": "", **slots}


def test_waechter_klassifiziert_alle_befunde():
    admin = [
        _admin("A1", "Gebunden", money_kontext="egal"),       # kanon-Bindung ⇒ ok
        _admin("A2", "Fragil", money_kontext="nagelfabrik"),  # kontext-Treffer ⇒ alt
        _admin("A3", "Doppel", money_kontext="doppelt"),      # 2 Treffer ⇒ mehrdeutig
        _admin("A4", "Tot", money_kontext="gibtsnicht"),      # kein Treffer ⇒ dangling
        _admin("A5", "Leer"),                                 # Slot leer ⇒ ungenutzt
    ]
    money = anker_index([
        {"id": "m1", "name": "M1", "kanon_id": "A1", "kontext": ""},
        {"id": "m2", "name": "M2", "kanon_id": "", "kontext": "Nagelfabrik"},
        {"id": "m3", "name": "M3", "kanon_id": "", "kontext": "doppelt"},
        {"id": "m4", "name": "M4", "kanon_id": "", "kontext": "DOPPELT"},
    ])
    report = waechter_report(admin, {"V17": money})           # V18/V19 fehlen ⇒ unbekannt
    v17 = {e["bereich_id"]: e for e in report["kanten"] if e["kante"] == "V17"}
    assert v17["A1"]["befund"] == "ok" and v17["A1"]["quelle"] == "kanon"
    assert v17["A2"]["befund"] == "alt" and v17["A2"]["quelle"] == "kontext"
    assert v17["A3"]["befund"] == "mehrdeutig"
    assert v17["A4"]["befund"] == "dangling"
    assert v17["A5"]["befund"] == "ungenutzt"
    z = report["zusammenfassung"]
    assert z["unbekannt"] == 10                               # 5 Bereiche × (V18+V19)
    assert set(z) == set(WAECHTER_BEFUNDE)
    assert z["ok"] == 1 and z["alt"] == 1 and z["dangling"] == 1 and z["mehrdeutig"] == 1


def test_waechter_v19_ordner_namen_als_fallback():
    admin = [_admin("A1", "Wissen", memory_ref="Studium Info")]
    memory = anker_index([{"id": "b1", "name": "Anders", "kanon_id": "", "kontext": ""}],
                         extra_namen=("studium info",))
    e = [k for k in waechter_report(admin, {"V19": memory})["kanten"]
         if k["kante"] == "V19"][0]
    assert e["befund"] == "alt" and e["quelle"] == "name"


def test_waechter_reverse_verwaist_app():
    admin = [_admin("A1", "Lebt", money_kontext="egal")]
    money = anker_index([
        {"id": "m1", "kanon_id": "A1", "kontext": ""},
        {"id": "m2", "kanon_id": "A-GELOESCHT", "kontext": ""}])
    rep = waechter_report(admin, {"V17": money})       # V18/V19 ohne Feed ⇒ kein Reverse
    verw = [e for e in rep["kanten"] if e["befund"] == "verwaist_app"]
    assert verw == [{"kante": "V17", "bereich_id": "", "bereich_name": "",
                     "schluessel": "A-GELOESCHT", "befund": "verwaist_app", "quelle": "kanon"}]
    assert rep["zusammenfassung"]["verwaist_app"] == 1


# ── Backfill-Dry-Run (docs/67 §7 P2 — NUR eindeutige, schreibt nichts) ──────────
def test_backfill_nur_eindeutige_vorschlaege():
    admin = [
        _admin("A1", "Sauber", money_kontext="nagelfabrik"),  # 1:1 ⇒ Vorschlag
        _admin("A2", "Mehrdeutig", money_kontext="doppelt"),  # 2 App-Treffer ⇒ nein
        _admin("A3", "ZielGebunden", money_kontext="belegt"), # Ziel hat kanon_id ⇒ nein
        _admin("A4", "SchonOk", money_kontext="fertig"),      # A4 bereits gebunden ⇒ nein
        _admin("A5", "Streit", money_kontext="umkaempft"),    # Slot 2× beansprucht ⇒ nein
        _admin("A6", "Streit2", money_kontext="Umkaempft"),
    ]
    app = [
        {"id": "m1", "name": "M1", "kanon_id": "", "kontext": "Nagelfabrik"},
        {"id": "m2", "name": "M2", "kanon_id": "", "kontext": "doppelt"},
        {"id": "m3", "name": "M3", "kanon_id": "", "kontext": "DOPPELT"},
        {"id": "m4", "name": "M4", "kanon_id": "K-FREMD", "kontext": "belegt"},
        {"id": "m5", "name": "M5", "kanon_id": "A4", "kontext": "fertig"},
        {"id": "m6", "name": "M6", "kanon_id": "", "kontext": "umkaempft"},
    ]
    v = backfill_vorschlaege(admin, "V17", app)
    assert v == [{"kante": "V17", "app_bereich_id": "m1", "app_name": "M1",
                  "kanon_id": "A1", "admin_name": "Sauber", "kontext": "nagelfabrik"}]


def test_backfill_unbekannte_kante():
    with pytest.raises(ValueError):
        backfill_vorschlaege([], "V99", [])


# ── Ober-Kategorien (docs/67 §4) ────────────────────────────────────────────────
def test_mapping_vollstaendig_fuer_alle_vier_kataloge():
    for app, arten in _ARTEN.items():
        mapping_validieren(arten)                             # wirft bei Lücke
        for art in arten:
            assert ober_kategorie_fuer(art) in OBER_KATEGORIEN, (app, art)
    # die Angleich-Paare landen deckungsgleich (privat ≡ persoenlich bis MIG-ART-1)
    assert ober_kategorie_fuer("privat") == ober_kategorie_fuer("persoenlich")


def test_ober_kategorie_fail_closed_und_override():
    assert ober_kategorie_fuer("voellig_neu") == "sonstiges"
    assert ober_kategorie_fuer("voellig_neu", {"voellig_neu": "projekt"}) == "projekt"


def test_mapping_validieren_fail_closed():
    with pytest.raises(ValueError):
        mapping_validieren(("brandneu",))                     # ungemappte art
    with pytest.raises(ValueError):
        mapping_validieren(("brandneu",), {"brandneu": "kein_set_mitglied"})


def test_mit_ober_kategorie_haengt_feld_additiv_an():
    """Der geteilte ``_public``-Baustein (BER-2): Bestandsfelder unverändert, ``ober_kategorie``
    additiv ergänzt; fehlende/unbekannte art fail-closed; Eingabe nicht mutiert (dict-Kopie)."""
    d = mit_ober_kategorie({"id": "b1", "name": "A", "art": "geschaeft"})
    assert d["ober_kategorie"] == "geschaeftlich"
    assert d["id"] == "b1" and d["name"] == "A" and d["art"] == "geschaeft"   # additiv
    assert mit_ober_kategorie({"art": "voellig_neu"})["ober_kategorie"] == "sonstiges"
    assert mit_ober_kategorie({"name": "ohne art"})["ober_kategorie"] == "sonstiges"
    assert mit_ober_kategorie({"art": "voellig_neu"},
                              {"voellig_neu": "projekt"})["ober_kategorie"] == "projekt"
    row = {"art": "wissen"}                                   # _public bekommt eine LIVE-Row
    mit_ober_kategorie(row)
    assert "ober_kategorie" not in row                        # Kopie, keine Mutation


# ── Baum + Roll-up (docs/67 §6, ME-1-Muster) ────────────────────────────────────
def _kn(bid, parent=""):
    return {"id": bid, "name": bid, "parent_id": parent}


def test_baum_verschachtelung_und_reihenfolge():
    baum = baum_bauen([_kn("w1"), _kn("k1", "w1"), _kn("k2", "w1"),
                       _kn("e1", "k1"), _kn("w2")])
    assert [w["id"] for w in baum] == ["w1", "w2"]
    assert [k["id"] for k in baum[0]["kinder"]] == ["k1", "k2"]
    assert baum[0]["kinder"][0]["kinder"][0]["id"] == "e1"
    assert "verwaist" not in baum[0]


def test_baum_rettet_verwaiste_und_zyklen():
    baum = baum_bauen([_kn("solo", "FEHLT"),                  # Parent existiert nicht
                       _kn("a", "b"), _kn("b", "a")])         # Zyklus (nur Alt-Daten möglich)
    assert {w["id"] for w in baum} == {"solo", "a", "b"}
    assert all(w.get("verwaist") for w in baum)
    assert all(w["kinder"] == [] for w in baum)


def test_rollup_summiert_ueber_enkel():
    baum = baum_bauen([_kn("w"), _kn("k", "w"), _kn("e", "k")])
    rollup_zaehler(baum, {"w": {"notizen": 1}, "k": {"notizen": 2, "ordner": 1},
                          "e": {"notizen": 4}})
    w = baum[0]
    assert w["zaehler"] == {"notizen": 1}
    assert w["rollup"] == {"notizen": 7, "ordner": 1} and w["rollup_gesamt"] == 8
    k = w["kinder"][0]
    assert k["rollup"] == {"notizen": 6, "ordner": 1} and k["kinder"][0]["rollup_gesamt"] == 4


# ── Konstanten-Verträge ─────────────────────────────────────────────────────────
def test_konstanten():
    assert MIG_PHASEN == ("bestand", "spalte", "backfill", "dual_read", "cutover")
    assert dict(WAECHTER_KANTEN) == {"V17": "money_kontext", "V18": "management_kontext",
                                     "V19": "memory_ref"}
    assert isinstance(anker_index([]), AnkerIndex)
