"""Charta §B8 — Erreichbarkeits-Enumerator (CH-14): CFO · Betriebsrat · SoD · tote Artikel."""
from appkit import charta_erreichbar as E

CHARTA = {"charta_version": "t", "artikel": [
    {"aktion": "fibu.buchen", "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]],
     "schranken": [{"wenn": [{"p": "betrag_ab", "w": "1000000"}], "dann": ["vier_augen"]}]},
    {"aktion": "fibu.festschreiben",
     "gewaehre": [[{"p": "rolle", "w": "fibu_leitung"}, {"p": "assurance_min", "w": "hochsicher"}]],
     "schranken": [{"wenn": [{"p": "immer"}], "dann": ["vier_augen", "siegelpflichtig"]},
                   {"wenn": [{"p": "erfasser_ist_subjekt"}], "dann": ["verweigere"]}]},
    {"aktion": "verzeichnis.zuweisen", "gewaehre": [[{"p": "rolle", "w": "personal"}]]}]}

A, B, D = "u:" + "a" * 10, "u:" + "b" * 10, "u:" + "d" * 10


def _s(uid, rollen, bereiche=("b:eigen",)):
    return {"art": "mensch", "id": uid, "assurance": "hochsicher", "frisch_s": 0,
            "edition": "bizzi", "rollen": list(rollen), "bereiche": list(bereiche)}


def test_wer_kann_cfo():
    beleg = [_s(A, ["buchhaltung"]), _s(B, ["fibu_leitung"]), _s(D, ["leser"])]
    assert E.wer_kann(CHARTA, beleg, "fibu.buchen") == [A]
    assert E.wer_kann(CHARTA, beleg, "fibu.festschreiben") == [B]


def test_niemand_ausser_betriebsrat():
    beleg = [_s(A, ["buchhaltung"]), _s(B, ["leser"])]
    r = E.niemand_ausser(CHARTA, beleg, "fibu.buchen")
    assert r["kann"] == [A] and r["kann_nicht"] == [B]


def test_tote_artikel_solo_vieraugen_und_fehlende_rolle():
    beleg = [_s(A, ["fibu_leitung", "buchhaltung"])]
    tot = E.tote_artikel(CHARTA, beleg)
    assert "fibu.festschreiben" in tot          # nur EINE Identität ⇒ vier_augen unerfüllbar
    assert "verzeichnis.zuweisen" in tot         # Rolle 'personal' hat niemand
    assert "fibu.buchen" not in tot              # buchhaltung vorhanden


def test_zwei_berechtigte_beleben_vieraugen_artikel():
    beleg = [_s(A, ["fibu_leitung"]), _s(B, ["fibu_leitung"])]
    assert "fibu.festschreiben" not in E.tote_artikel(CHARTA, beleg)


def test_sod_matrix_findet_konflikt():
    beleg = [_s(A, ["buchhaltung", "fibu_leitung"]), _s(B, ["fibu_leitung"])]
    m = E.sod_matrix(CHARTA, beleg, [("fibu.buchen", "fibu.festschreiben")])
    assert m and m[0]["beide"] == [A]            # A erreicht beide ⇒ Trennungs-Konflikt


def test_ehrlichkeitskasten_vorhanden():
    assert "tote Artikel" in E.EHRLICHKEIT and "Rubber-Stamping" in E.EHRLICHKEIT
