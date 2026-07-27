"""Tests der reinen Regel-Engine (Teil B): Matching ist deterministisch und
ohne DB testbar."""

from __future__ import annotations

from moneyapp.regeln import finde_regel, lern_muster, passt


def _f(gp="", vz="", notiz=""):
    return {"gegenpartei": gp, "verwendungszweck": vz, "notiz": notiz}


def test_passt_feld_und_beliebig():
    assert passt("rewe", "gegenpartei", _f(gp="REWE Markt GmbH"))
    assert not passt("rewe", "verwendungszweck", _f(gp="REWE Markt"))
    assert passt("rewe", "beliebig", _f(gp="REWE Markt"))
    assert passt("miete", "beliebig", _f(vz="Miete Januar"))
    assert not passt("", "beliebig", _f(gp="egal"))     # leeres Muster trifft nie


def test_finde_regel_prioritaet_dann_treffer():
    regeln = [
        {"id": "a", "muster": "rewe", "feld": "gegenpartei", "kategorie_id": "k1",
         "prioritaet": 100, "treffer": 3, "created_at": "2026-01-01"},
        {"id": "b", "muster": "rewe", "feld": "gegenpartei", "kategorie_id": "k2",
         "prioritaet": 200, "treffer": 0, "created_at": "2026-01-02"},
    ]
    # höhere Priorität gewinnt, egal wie viele Treffer die andere hat
    assert finde_regel(regeln, _f(gp="REWE"))["id"] == "b"


def test_finde_regel_treffer_bricht_gleichstand():
    regeln = [
        {"id": "a", "muster": "edeka", "feld": "beliebig", "kategorie_id": "k1",
         "prioritaet": 100, "treffer": 1, "created_at": "2026-01-01"},
        {"id": "b", "muster": "edeka", "feld": "beliebig", "kategorie_id": "k2",
         "prioritaet": 100, "treffer": 9, "created_at": "2026-01-01"},
    ]
    assert finde_regel(regeln, _f(gp="EDEKA"))["id"] == "b"


def test_finde_regel_keine():
    assert finde_regel([], _f(gp="x")) is None
    regeln = [{"id": "a", "muster": "rewe", "feld": "gegenpartei",
               "kategorie_id": "k1"}]
    assert finde_regel(regeln, _f(gp="ALDI")) is None


def test_lern_muster_bevorzugt_gegenpartei():
    assert lern_muster(_f(gp="REWE Markt")) == ("rewe markt", "gegenpartei")
    assert lern_muster(_f(vz="Netflix Abo Monat")) == ("netflix abo monat", "verwendungszweck")
    assert lern_muster(_f()) == ("", "beliebig")
