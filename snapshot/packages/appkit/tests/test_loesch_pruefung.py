"""Units für das Lösch-Invariante-Prüfkit (KA-H1, appkit/loesch_pruefung.py)."""

from __future__ import annotations

import sqlite3

from appkit import loesch_pruefung as lp


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE gedeckt_soft (          -- user_id + deleted_at ⇒ Kaskade deckt
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, deleted_at TEXT);
        CREATE TABLE gedeckt_hook (          -- user_id, KEIN deleted_at ⇒ nur via Hook
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
        CREATE TABLE offen (                 -- user_id, KEIN deleted_at, kein Hook ⇒ LOCH
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
        CREATE TABLE audit_log (             -- Ausnahme (Löschbeleg, muss überleben)
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
        CREATE TABLE global_ohne_user (      -- keine user_id ⇒ für die Invariante irrelevant
            id TEXT PRIMARY KEY, wert TEXT);
        """
    )
    return c


def test_offene_tabelle_wird_gemeldet():
    c = _conn()
    # gedeckt_hook als Hook-Tabelle deklariert; 'offen' NICHT ⇒ nur 'offen' bleibt.
    off = lp.user_tabellen_ohne_deckung(
        c, hook_tabellen=frozenset({"gedeckt_hook"}))
    assert off == ["offen"]


def test_alles_gedeckt_ist_leer():
    c = _conn()
    off = lp.user_tabellen_ohne_deckung(
        c, hook_tabellen=frozenset({"gedeckt_hook", "offen"}))
    assert off == []


def test_audit_log_ist_default_ausnahme():
    c = _conn()
    # audit_log trägt user_id + kein deleted_at, darf aber NIE als Loch erscheinen.
    off = lp.user_tabellen_ohne_deckung(
        c, hook_tabellen=frozenset({"gedeckt_hook", "offen"}))
    assert "audit_log" not in off


def test_pruefe_hook_loescht_zaehlt_reste():
    c = _conn()
    c.execute("INSERT INTO gedeckt_hook VALUES ('1','u1')")
    c.execute("INSERT INTO gedeckt_hook VALUES ('2','u2')")
    c.execute("INSERT INTO offen VALUES ('3','u1')")
    c.commit()
    rest = lp.pruefe_hook_loescht(
        c, "u1", frozenset({"gedeckt_hook", "offen"}))
    assert rest == {"gedeckt_hook": 1, "offen": 1}      # je 1 Zeile für u1

    c.execute("DELETE FROM gedeckt_hook WHERE user_id='u1'")
    c.execute("DELETE FROM offen WHERE user_id='u1'")
    c.commit()
    rest2 = lp.pruefe_hook_loescht(
        c, "u1", frozenset({"gedeckt_hook", "offen"}))
    assert rest2 == {"gedeckt_hook": 0, "offen": 0}     # u1 geräumt
    assert lp.pruefe_hook_loescht(
        c, "u2", frozenset({"gedeckt_hook"})) == {"gedeckt_hook": 1}  # u2 unberührt


def test_row_factory_agnostisch():
    """Ohne sqlite3.Row (Default-Tuple) müssen die positionalen Zugriffe halten —
    der Core (A2) nutzt das Kit mit seiner eigenen, nicht-Row conn."""
    c = sqlite3.connect(":memory:")                      # bewusst KEIN row_factory
    c.executescript(
        "CREATE TABLE t (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);")
    assert lp.user_tabellen_ohne_deckung(c, hook_tabellen=frozenset()) == ["t"]
