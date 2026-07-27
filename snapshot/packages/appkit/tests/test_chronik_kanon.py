"""B1 §7 — Kanon + Datenklassen + Feld-Hash-Pfeffer (C-2/C-3/C-15/C-17)."""
import sqlite3

import pytest

from appkit import chronik as C


@pytest.fixture(autouse=True)
def _kontext(tmp_path):
    C.konfiguriere(tmp_path / "chronik")
    yield
    C.reset_kontext()


# ── Kanon (RFC-8785-Subset) ──────────────────────────────────────────────────

def test_kanon_sortiert_und_kompakt():
    assert C.kanon({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert C.kanon({"x": [3, 2, 1]}) == '{"x":[3,2,1]}'   # Listen behalten Reihenfolge
    assert C.kanon({"u": "über"}) == '{"u":"über"}'        # Unicode-Werte erlaubt


def test_kanon_bool_und_int_grenze():
    assert C.kanon({"k": True}) == '{"k":true}'
    assert C.kanon({"k": C.MAX_SAFE_INT}) == '{"k":9007199254740991}'


@pytest.mark.parametrize("bad", [
    {"k": 1.5},                 # float verboten (C-2)
    {"k": float("nan")},        # NaN verboten
    {"k": 2**53},               # int > 2^53-1 (C-2)
    {"Groß": 1},                # Nicht-ASCII-Objekt-Schlüssel (C-17)
    {"a b": 1},                 # Leerzeichen im Schlüssel (C-17)
    {"UPPER": 1},               # Großbuchstaben im Schlüssel (C-17)
    {"k": {1, 2}},              # unerlaubter Typ (set)
    {"k": b"bytes"},            # unerlaubter Typ (bytes)
])
def test_kanon_lehnt_ungueltiges_ab(bad):
    with pytest.raises(C.ChronikFehler):
        C.kanon(bad)


def test_kanon_geld_als_dezimalstring():
    # Geld gehört als Dezimal-String — als int > 2^53 würde es fail-loud brechen.
    assert C.kanon({"betrag_minor": "9223372036854775807"}) == '{"betrag_minor":"9223372036854775807"}'


# ── Feld-Hash-Pfeffer (C-15) ─────────────────────────────────────────────────

def test_feld_hash_leer_ist_none():
    assert C.feld_hash("") is None
    assert C.feld_hash(None) is None


def test_feld_hash_format_und_determinismus():
    h = C.feld_hash("REWE Markt GmbH")
    assert h.startswith("hmac256:") and len(h) == len("hmac256:") + 64
    assert h == C.feld_hash("REWE Markt GmbH")          # je Instanz stabil


def test_feld_hash_ueber_instanzen_verschieden(tmp_path):
    h1 = C.feld_hash("Anna Schmidt")
    C.reset_kontext()
    C.konfiguriere(tmp_path / "chronik2")               # frischer Pfeffer
    assert C.feld_hash("Anna Schmidt") != h1            # kein Wörterbuch-Rückschluss


# ── Datenklassen + Outbox-Schreiber (C-3) ────────────────────────────────────

def _conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(C.AUSGANG_SCHEMA)
    return conn


def test_schreibe_klar_traegt_nutzlast_und_sha256():
    conn = _conn()
    C.schreibe(conn, art="money.festschreibung", subjekt="u:" + "a" * 36,
               nutzlast={"zeitraum": "2026-06", "bis_i": 42, "salden_hash": "sha256:x", "beweisgrad": "voll"})
    art, last, h = conn.execute("SELECT art, nutzlast, nutzlast_hash FROM chronik_ausgang").fetchone()
    assert last.startswith("{") and h.startswith("sha256:")


def test_schreibe_hash_only_leert_nutzlast_und_pfeffert():
    conn = _conn()
    C.schreibe(conn, art="verzeichnis.austritt", subjekt="system", nutzlast={"user": "x"})
    last, h = conn.execute("SELECT nutzlast, nutzlast_hash FROM chronik_ausgang").fetchone()
    assert last == "" and h.startswith("hmac256:")


def test_schreibe_lehnt_unbekannte_art_ab():
    with pytest.raises(C.ChronikFehler):
        C.schreibe(_conn(), art="quatsch.unbekannt", subjekt="system", nutzlast={})


@pytest.mark.parametrize("subjekt", ["Anna Schmidt", "anna@example.com", "", "u:kurz"])
def test_schreibe_lehnt_klartext_subjekt_ab(subjekt):
    # BZ-C-10: nur opake Kennung (u:<uuid>|system|agent:<id>)
    with pytest.raises(C.ChronikFehler):
        C.schreibe(_conn(), art="money.buchung", subjekt=subjekt, nutzlast={"buchung_id": "b"})


def test_schreibe_ohne_commit_rollback_laesst_nichts(tmp_path):
    # C-1: schreibe committet nie selbst — Rollback ⇒ keine Outbox-Zeile.
    conn = _conn()
    conn.execute("BEGIN")
    C.schreibe(conn, art="money.storno", subjekt="system", nutzlast={"buchung_id": "b", "datum_storno": "2026-06-30"})
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM chronik_ausgang").fetchone()[0] == 0
