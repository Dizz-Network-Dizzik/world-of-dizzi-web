"""Tests RG-4 (docs/83 §3): Schatten-Protokoll der Autonomie-Treppe.

Pinnt: eine Beobachtungs-Absicht landet lauf-gebunden im Schatten (nie Inbox) ·
Liste/Zähler als Eichungs-Rohmaterial · Retention (30 Tage) · die gebundene
schatten_fn schreibt und meldet ``status:'schatten'``. DB-isoliert via temp_db.
"""

from __future__ import annotations

import asyncio

from app.ai import schatten


def test_anlegen_und_liste():
    s1 = schatten.schatten_anlegen("u1", "triage", "lauf-1", "email_senden",
                                   {"an": "k@x.org"}, "Kunde wartet")
    schatten.schatten_anlegen("u1", "triage", "lauf-1", "email_markieren", {"flag": "spam"})
    liste = schatten.schatten_liste("u1")
    assert len(liste) == 2 and any(e["id"] == s1 for e in liste)
    e = next(e for e in liste if e["id"] == s1)
    assert e["aktion_name"] == "email_senden" and e["params"] == {"an": "k@x.org"}
    assert e["warum"] == "Kunde wartet" and e["lauf_id"] == "lauf-1"


def test_liste_filter_je_agent_und_lauf():
    schatten.schatten_anlegen("u1", "a", "l1", "x", {})
    schatten.schatten_anlegen("u1", "b", "l2", "y", {})
    assert len(schatten.schatten_liste("u1", agent_id="a")) == 1
    assert len(schatten.schatten_liste("u1", lauf_id="l2")) == 1
    assert schatten.schatten_liste("u2") == []                 # anderer Nutzer ⇒ leer


def test_zaehler_je_agent():
    for _ in range(3):
        schatten.schatten_anlegen("u1", "a", "l", "x", {})
    schatten.schatten_anlegen("u1", "b", "l", "y", {})
    assert schatten.schatten_zaehler("u1") == {"a": 3, "b": 1}


def test_retention_aufraeumen():
    schatten.schatten_anlegen("u1", "a", "l", "alt", {})
    # 40 Tage später räumt (Behalte-Fenster 30) ⇒ der Alt-Eintrag fällt.
    weg = schatten.aufraeumen("u1", behalte_tage=30, jetzt_iso="2099-01-01T00:00:00+00:00")
    assert weg == 1 and schatten.schatten_liste("u1") == []


def test_default_factory_schreibt_und_meldet_schatten():
    fac = schatten.default_schatten_factory("u1")
    fn = fac("triage", "lauf-9")
    res = asyncio.run(fn("email_senden", {"an": "k@x.org"}, "weil"))
    assert res["status"] == "schatten" and res["id"]
    liste = schatten.schatten_liste("u1", agent_id="triage", lauf_id="lauf-9")
    assert len(liste) == 1 and liste[0]["aktion_name"] == "email_senden"
