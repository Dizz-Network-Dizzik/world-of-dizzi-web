"""Charta §B8 — Golden: Beispiel-Charta (B2.1), Antrag→Entscheid-Fixtures,
``validiere()``-Ablehnungen (CH-3/8/13/17 + Nicht-ASCII), Renderer, Notweg (CH-13)."""
import pytest

from appkit import charta as CH

# Die Beispiel-Charta aus docs/84 §B2.1 (wortlaut-treu).
BEISPIEL = {"charta_version": "2026-07-12.1", "artikel": [
    {"aktion": "fibu.buchen",
     "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}, {"p": "assurance_min", "w": "verifiziert"}],
                  [{"p": "rolle", "w": "fibu_leitung"}, {"p": "assurance_min", "w": "verifiziert"}]],
     "schranken": [
         {"wenn": [{"p": "betrag_ab", "w": "1000000"}], "dann": ["vier_augen"]},
         {"wenn": [{"p": "art", "w": "agent"}], "dann": ["mensch_entscheidet"]},
         {"wenn": [{"p": "zeit_ausserhalb", "w": "06:00-22:00"}], "dann": ["step_up"]},
         {"wenn": [{"p": "bereich_fremd"}], "dann": ["verweigere"]}]},
    {"aktion": "fibu.festschreiben",
     "gewaehre": [[{"p": "rolle", "w": "fibu_leitung"}, {"p": "assurance_min", "w": "hochsicher"},
                   {"p": "frisch", "w": 300}]],
     "schranken": [
         {"wenn": [{"p": "immer"}], "dann": ["vier_augen", "siegelpflichtig"]},
         {"wenn": [{"p": "erfasser_ist_subjekt"}], "dann": ["verweigere"]}]},
    {"aktion": "privatgedaechtnis.lesen",
     "gewaehre": [[{"p": "eigentuemer"}]],
     "schranken": [{"wenn": [{"p": "sensitivitaet_min", "w": "hoch"}], "dann": ["nur_fluechtig"]}]}]}

_ZEIT_TAG = "2026-07-13T09:30:00+00:00"
_ZEIT_NACHT = "2026-07-13T23:15:00+00:00"


def _bau(aktion, **kw):
    kw.setdefault("user_id", "u:" + "a" * 10)
    kw.setdefault("assurance", "verifiziert")
    kw.setdefault("edition", "bizzi")
    kw.setdefault("rollen", [])
    kw.setdefault("bereiche", ["b:eigen"])
    kw.setdefault("objekt", {})
    kw.setdefault("zeit", _ZEIT_TAG)
    return CH.antrag_bauen(aktion, **kw)


# ── validiere + Determinismus ────────────────────────────────────────────────

def test_beispiel_validiert_und_hash_stabil():
    h1 = CH.validiere(BEISPIEL)
    h2 = CH.validiere(BEISPIEL)
    assert h1.startswith("sha256:") and h1 == h2
    assert CH.Charta.aus_json(BEISPIEL).artikel_hash == h1


# ── fibu.buchen ──────────────────────────────────────────────────────────────

def test_buchen_grossbetrag_loest_vier_augen():
    an = _bau("fibu.buchen", rollen=["buchhaltung"],
              objekt={"betrag_minor": "1250000", "bereich_id": "b:eigen"})
    e = CH.pruefe(an, BEISPIEL)
    assert e.gewaehrt and e.obliegenheiten == ("vier_augen",)


def test_buchen_nachts_loest_step_up():
    an = _bau("fibu.buchen", rollen=["fibu_leitung"], zeit=_ZEIT_NACHT,
              objekt={"betrag_minor": "50000", "bereich_id": "b:eigen"})
    e = CH.pruefe(an, BEISPIEL)
    assert e.gewaehrt and e.obliegenheiten == ("step_up",)


def test_buchen_fremder_bereich_verweigert():
    an = _bau("fibu.buchen", rollen=["buchhaltung"], bereiche=["b:eigen"],
              objekt={"betrag_minor": "50000", "bereich_id": "b:fremd"})
    assert CH.pruefe(an, BEISPIEL).gewaehrt is False        # verweigere-Dominanz


def test_buchen_ohne_rolle_deny_default():
    an = _bau("fibu.buchen", rollen=["leser"],
              objekt={"betrag_minor": "50000", "bereich_id": "b:eigen"})
    assert CH.pruefe(an, BEISPIEL).gewaehrt is False


# ── fibu.festschreiben (Vier-Augen + SoD + toter Artikel) ────────────────────

def test_festschreiben_gewaehrt_mit_siegel_und_vieraugen():
    an = _bau("fibu.festschreiben", assurance="hochsicher", rollen=["fibu_leitung"],
              frisch_s=100, objekt={"bereich_id": "b:eigen", "erfasser_id": "u:" + "b" * 10})
    e = CH.pruefe(an, BEISPIEL)
    assert e.gewaehrt and e.obliegenheiten == ("siegelpflichtig", "vier_augen")


def test_festschreiben_ohne_zweites_subjekt_ist_toter_artikel():
    an = _bau("fibu.festschreiben", assurance="hochsicher", rollen=["fibu_leitung"],
              frisch_s=100, objekt={"bereich_id": "b:eigen"})
    assert CH.pruefe(an, BEISPIEL, vier_augen_moeglich=False).gewaehrt is False


def test_festschreiben_erfasser_ist_subjekt_verweigert():
    an = _bau("fibu.festschreiben", user_id="u:" + "a" * 10, assurance="hochsicher",
              rollen=["fibu_leitung"], frisch_s=100,
              objekt={"bereich_id": "b:eigen", "erfasser_id": "u:" + "a" * 10})
    assert CH.pruefe(an, BEISPIEL).gewaehrt is False        # SoD (Maker≠Checker)


def test_festschreiben_zu_alt_deny():
    an = _bau("fibu.festschreiben", assurance="hochsicher", rollen=["fibu_leitung"],
              frisch_s=100000, objekt={"bereich_id": "b:eigen", "erfasser_id": "u:" + "b" * 10})
    assert CH.pruefe(an, BEISPIEL).gewaehrt is False        # frisch(300) verletzt


# ── privatgedaechtnis.lesen (Eigentümer + Sensitivität) ──────────────────────

def test_privat_eigentuemer_liest_fluechtig():
    an = _bau("privatgedaechtnis.lesen", user_id="u:" + "a" * 10,
              objekt={"eigentuemer_id": "u:" + "a" * 10, "sensitivitaet": "hoch"})
    e = CH.pruefe(an, BEISPIEL)
    assert e.gewaehrt and e.obliegenheiten == ("nur_fluechtig",)


def test_privat_fremder_deny():
    an = _bau("privatgedaechtnis.lesen", user_id="u:" + "a" * 10,
              objekt={"eigentuemer_id": "u:" + "z" * 10})
    assert CH.pruefe(an, BEISPIEL).gewaehrt is False


# ── validiere-Ablehnungen ────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"charta_version": "t", "artikel": [{"aktion": "x.y", "gewaehre": [[{"p": "zauberei"}]]}]},
    {"charta_version": "t", "artikel": [{"aktion": "x.y",
        "gewaehre": [[{"p": "rolle", "w": "u:anna"}]]}]},                 # CH-8 ID-Literal
    {"charta_version": "t", "artikel": [{"aktion": "x.y",
        "gewaehre": [[{"p": "betrag_ab", "w": 1.5}]]}]},                  # CH-17 float
    {"charta_version": "t", "artikel": [{"aktion": "x.y",
        "gewaehre": [[{"p": "betrag_ab", "w": 10000}]]}]},               # kein Dezimal-String
    {"charta_version": "t", "artikel": [{"aktion": "x.y",
        "gewaehre": [[{"p": "immer"}]], "Ünlaut": 1}]},                  # Nicht-ASCII-Schlüssel
    {"charta_version": "t", "artikel": [{"aktion": "Fibu.Buchen",
        "gewaehre": [[{"p": "immer"}]]}]},                               # Aktion nicht [a-z0-9_.]
    {"charta_version": "t", "artikel": [{"aktion": "x.y", "gewaehre": []}]},  # leere Gewährung
    {"charta_version": "t", "artikel": []},                              # leere Charta
])
def test_validiere_lehnt_ab(bad):
    with pytest.raises(CH.ChartaFehler):
        CH.validiere(bad)


# ── CH-13 Wiederherstellungs-Artikel (Notweg) ────────────────────────────────

def test_notweg_nicht_in_version_definierbar():
    bad = {"charta_version": "t", "artikel": [{
        "aktion": "charta.wiederherstellen", "gewaehre": [[{"p": "immer"}]]}]}
    with pytest.raises(CH.ChartaFehler):
        CH.validiere(bad)


def test_notweg_konstante_greift_auch_ohne_charta():
    leer = {"charta_version": "t", "artikel": [
        {"aktion": "memo.schreiben", "gewaehre": [[{"p": "immer"}]]}]}
    # Stammschlüssel-Inhaber, hochsicher + frisch ⇒ gewährt + siegelpflichtig.
    ja = _bau("charta.wiederherstellen", assurance="hochsicher",
              rollen=["stammschluessel"], frisch_s=100)
    e = CH.pruefe(ja, leer)
    assert e.gewaehrt and e.obliegenheiten == ("siegelpflichtig",)
    # Ohne Stammschlüssel / zu niedrige Stufe ⇒ verweigert (Verfassungsrang).
    nein = _bau("charta.wiederherstellen", assurance="lokal", rollen=["buchhaltung"], frisch_s=100)
    assert CH.pruefe(nein, leer).gewaehrt is False


# ── CH-5 · Kern befüllt Subjekt; Client-Attribute werden verworfen ───────────

def test_antrag_bauen_verwirft_client_subjekt_attribute():
    # Ein Client, der über das Objekt Subjekt-Attribute schmuggeln will:
    an = CH.antrag_bauen("fibu.buchen", user_id="u:" + "a" * 10, assurance="lokal",
                         edition="bizzi", rollen=["buchhaltung"], bereiche=["b:eigen"],
                         objekt={"betrag_minor": "50000", "assurance": "hochsicher",
                                 "rollen": ["fibu_leitung"], "id": "u:boss"},
                         zeit=_ZEIT_TAG)
    assert "assurance" not in an["objekt"] and "rollen" not in an["objekt"]
    assert an["subjekt"]["assurance"] == "lokal"            # Server-Wahrheit gewinnt
    assert an["subjekt"]["rollen"] == ["buchhaltung"]


# ── Renderer (B2.2) ──────────────────────────────────────────────────────────

def test_rendere_textform():
    text = CH.rendere(BEISPIEL)
    assert "artikel fibu.buchen:" in text
    assert "gewähre: rolle(buchhaltung) und assurance_min(verifiziert)" in text
    assert "⇒ verweigere" in text


# ── CH-16 · Bestands-Schutz: Charta-Pflicht nur auf Kern-Routen (D5) ─────────

@pytest.mark.parametrize("aktion", ["fibu.buchen", "ap.zahlung", "verzeichnis.zuweisen",
                                    "charta.wiederherstellen", "umzug.cutover"])
def test_charta_pflicht_kern_routen(aktion):
    assert CH.ist_charta_pflicht(aktion) is True


@pytest.mark.parametrize("aktion", ["news.lesen", "creator.rendern", "memo.schreiben", "", 123])
def test_keine_charta_pflicht_ausserhalb(aktion):
    assert CH.ist_charta_pflicht(aktion) is False
