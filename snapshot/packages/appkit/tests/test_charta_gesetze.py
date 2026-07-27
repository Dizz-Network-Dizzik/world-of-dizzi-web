"""Charta §B8 — Gesetze P1…P8 (seeded ``random.Random(0xB1221)``, ≥300 Paare).

Die Property-Tests sind der Beweis, dass der ≤500-Zeilen-Evaluator die
Invarianten CH-1…CH-10 trägt: deny-default, Monotonie, fail-closed-Asymmetrie,
Obliegenheiten-Union, verweigere-Dominanz, Agent ⊆ Prinzipal, Totalität.
"""
import copy
import json
import random

from appkit import charta as CH

# ── Endliche Domänen ─────────────────────────────────────────────────────────
ROLLEN = ["buchhaltung", "fibu_leitung", "ap_erfasser", "leser", "stammschluessel"]
BEREICHE = ["b:kanon1", "b:kanon2", "b:kanon3"]
AKTIONEN = ["fibu.buchen", "ap.zahlung", "privatgedaechtnis.lesen", "memo.schreiben"]
ASSURANCE = ["lokal", "verifiziert", "hochsicher"]
EDITIONEN = ["bizzi", "dizzi"]
ZEITEN = ["2026-07-13T09:30:00+00:00", "2026-07-13T23:15:00+00:00",
          "2026-07-13T05:00:00+00:00"]
BETRAEGE = ["0", "50000", "990000", "1000000", "1250000"]
SENS = ["normal", "hoch", "hoechst"]

_GEWAEHRE_P = ["rolle", "assurance_min", "edition", "art", "frisch", "eigentuemer"]
_SCHRANKE_P = ["betrag_ab", "zeit_ausserhalb", "art", "bereich_fremd",
               "sensitivitaet_min", "immer", "erfasser_ist_subjekt"]
_OBLIEG = ["step_up", "vier_augen", "siegelpflichtig", "mensch_entscheidet", "nur_lokal"]


def _pred(rng, name):
    if name in ("bereich_fremd", "eigentuemer", "erfasser_ist_subjekt", "immer"):
        return {"p": name}
    if name in ("betrag_ab", "betrag_bis", "einzel_max_ab"):
        return {"p": name, "w": rng.choice(["10000", "500000", "1000000"])}
    if name == "frisch":
        return {"p": name, "w": rng.choice([60, 300, 86400])}
    if name == "assurance_min":
        return {"p": name, "w": rng.choice(ASSURANCE)}
    if name == "sensitivitaet_min":
        return {"p": name, "w": rng.choice(SENS)}
    if name == "zeit_ausserhalb":
        return {"p": name, "w": "06:00-22:00"}
    if name == "rolle":
        return {"p": name, "w": rng.choice(ROLLEN)}
    if name == "art":
        return {"p": name, "w": rng.choice(["mensch", "agent", "modul"])}
    if name == "edition":
        return {"p": name, "w": rng.choice(EDITIONEN)}
    raise AssertionError(name)


def _artikel(rng, aktion):
    gewaehre = [[_pred(rng, rng.choice(_GEWAEHRE_P)) for _ in range(rng.randint(1, 2))]
                for _ in range(rng.randint(1, 2))]
    art = {"aktion": aktion, "gewaehre": gewaehre}
    schranken = []
    for _ in range(rng.randint(0, 3)):
        wenn = [_pred(rng, rng.choice(_SCHRANKE_P)) for _ in range(rng.randint(1, 2))]
        dann = ["verweigere"] if rng.random() < 0.25 else \
            rng.sample(_OBLIEG, rng.randint(1, 2))
        schranken.append({"wenn": wenn, "dann": dann})
    if schranken:
        art["schranken"] = schranken
    return art


def _charta(rng):
    aktionen = rng.sample(AKTIONEN, rng.randint(1, len(AKTIONEN)))
    return {"charta_version": "2026-07-13.%d" % rng.randint(1, 9),
            "artikel": [_artikel(rng, a) for a in aktionen]}


def _subjekt(rng, art=None):
    return {"art": art or rng.choice(["mensch", "agent", "modul"]),
            "id": "u:" + rng.choice("abcdef") * 10,
            "assurance": rng.choice(ASSURANCE),
            "rollen": rng.sample(ROLLEN, rng.randint(0, 3)),
            "bereiche": rng.sample(BEREICHE, rng.randint(0, 3)),
            "edition": rng.choice(EDITIONEN),
            "frisch_s": rng.choice([10, 200, 400, 100000])}


def _objekt(rng):
    o = {}
    if rng.random() < 0.85:
        o["betrag_minor"] = rng.choice(BETRAEGE)
        if rng.random() < 0.5:
            o["stapel_summe_minor"] = rng.choice(BETRAEGE)
        if rng.random() < 0.5:
            o["einzel_max_minor"] = rng.choice(BETRAEGE)
    if rng.random() < 0.6:
        o["bereich_id"] = rng.choice(BEREICHE)
    if rng.random() < 0.5:
        o["sensitivitaet"] = rng.choice(SENS)
    if rng.random() < 0.4:
        o["eigentuemer_id"] = "u:" + rng.choice("abcdef") * 10
    if rng.random() < 0.4:
        o["erfasser_id"] = "u:" + rng.choice("abcdef") * 10
    return o


def _antrag(rng, aktion=None, art=None):
    return {"aktion": aktion or rng.choice(AKTIONEN), "zeit": rng.choice(ZEITEN),
            "subjekt": _subjekt(rng, art), "agent": None, "objekt": _objekt(rng)}


# ── P1 · deny-by-default (CH-1) ──────────────────────────────────────────────

def test_p1_deny_default():
    rng = random.Random(0xB1221)
    n = 0
    for _ in range(120):
        ch = _charta(rng)
        CH.validiere(ch)                       # Generator liefert nur gültige Charten
        vorhanden = {a["aktion"] for a in ch["artikel"]}
        fehlend = [a for a in AKTIONEN if a not in vorhanden] + ["gibts.nicht"]
        an = _antrag(rng, aktion=rng.choice(fehlend))
        assert CH.pruefe(an, ch).gewaehrt is False
        n += 1
    assert n >= 100


# ── P2 · Monotonie: Schranke dazu ⇒ nie mehr erlaubt, Obliegenheiten wachsen ──

def test_p2_monotonie_schranke_dazu():
    rng = random.Random(0xB1221 + 2)
    for _ in range(150):
        ch = _charta(rng)
        CH.validiere(ch)
        an = _antrag(rng)
        e1 = CH.pruefe(an, ch)
        ch2 = copy.deepcopy(ch)
        for art in ch2["artikel"]:
            if art["aktion"] == an["aktion"]:
                art.setdefault("schranken", []).append(
                    {"wenn": [{"p": "immer"}], "dann": ["step_up"]})
        CH.validiere(ch2)
        e2 = CH.pruefe(an, ch2)
        assert not (not e1.gewaehrt and e2.gewaehrt)     # nie deny → grant
        if e1.gewaehrt:
            assert e2.gewaehrt                           # step_up verweigert nicht
            assert "step_up" in e2.obliegenheiten
            assert set(e1.obliegenheiten) <= set(e2.obliegenheiten)


# ── P3 · Monotonie: entfernte Gewährung erlaubt nie mehr (CH-2) ──────────────

def test_p3_monotonie_gewaehrung_weg():
    rng = random.Random(0xB1221 + 3)
    geprueft = 0
    for _ in range(180):
        ch = _charta(rng)
        CH.validiere(ch)
        an = _antrag(rng)
        e1 = CH.pruefe(an, ch)
        ch2 = copy.deepcopy(ch)
        geaendert = False
        for art in ch2["artikel"]:
            if art["aktion"] == an["aktion"] and len(art["gewaehre"]) > 1:
                art["gewaehre"].pop(rng.randrange(len(art["gewaehre"])))
                geaendert = True
        if not geaendert:
            continue
        CH.validiere(ch2)
        e2 = CH.pruefe(an, ch2)
        assert not (not e1.gewaehrt and e2.gewaehrt)
        geprueft += 1
    assert geprueft >= 20


# ── P4 · fail-closed-Asymmetrie (CH-3): fehlendes Attribut senkt nie Schutz ──

def test_p4_failclosed_asymmetrie():
    rng = random.Random(0xB1221 + 4)
    for _ in range(160):
        ch = _charta(rng)
        CH.validiere(ch)
        an = _antrag(rng)
        e1 = CH.pruefe(an, ch)
        if not an["subjekt"]:
            continue
        an2 = copy.deepcopy(an)
        del an2["subjekt"][rng.choice(list(an2["subjekt"].keys()))]
        e2 = CH.pruefe(an2, ch)
        assert not (not e1.gewaehrt and e2.gewaehrt)      # Gewährung: fehlend ⇒ falsch
        if e1.gewaehrt and e2.gewaehrt:                   # Schranke: fehlend ⇒ wahr
            assert set(e1.obliegenheiten) <= set(e2.obliegenheiten)


# ── P5 · Obliegenheiten-Union (CH-10) ────────────────────────────────────────

def test_p5_obliegenheiten_union():
    ch = {"charta_version": "t", "artikel": [{
        "aktion": "fibu.buchen",
        "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]],
        "schranken": [
            {"wenn": [{"p": "immer"}], "dann": ["step_up"]},
            {"wenn": [{"p": "betrag_ab", "w": "10000"}], "dann": ["vier_augen"]}]}]}
    CH.validiere(ch)
    an = CH.antrag_bauen("fibu.buchen", user_id="u:" + "a" * 10, assurance="verifiziert",
                         edition="bizzi", rollen=["buchhaltung"], bereiche=[],
                         objekt={"betrag_minor": "50000"}, zeit="2026-07-13T09:00:00+00:00")
    e = CH.pruefe(an, ch)
    assert e.gewaehrt and set(e.obliegenheiten) == {"step_up", "vier_augen"}


# ── P6 · verweigere-Dominanz (CH-10) ─────────────────────────────────────────

def test_p6_verweigere_dominanz():
    ch = {"charta_version": "t", "artikel": [{
        "aktion": "fibu.buchen",
        "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]],
        "schranken": [
            {"wenn": [{"p": "immer"}], "dann": ["step_up"]},
            {"wenn": [{"p": "immer"}], "dann": ["verweigere"]}]}]}
    CH.validiere(ch)
    an = CH.antrag_bauen("fibu.buchen", user_id="u:" + "a" * 10, assurance="hochsicher",
                         edition="bizzi", rollen=["buchhaltung"], bereiche=[],
                         objekt={}, zeit="2026-07-13T09:00:00+00:00")
    assert CH.pruefe(an, ch).gewaehrt is False


# ── P7 · Agent ⊆ Prinzipal (CH-9) ────────────────────────────────────────────

def test_p7_agent_subset_prinzipal():
    rng = random.Random(0xB1221 + 7)
    n = 0
    for _ in range(140):
        ch = _charta(rng)
        CH.validiere(ch)
        prinzipal = _subjekt(rng, art="mensch")
        an = {"aktion": rng.choice(AKTIONEN), "zeit": rng.choice(ZEITEN),
              "subjekt": _subjekt(rng, art="agent"), "objekt": _objekt(rng),
              "agent": {"id": "agent:x", "prinzipal": prinzipal,
                        "autonomie": rng.choice(["pre_approval", "monitored", "autonom_audit"]),
                        "eval_gruen": rng.random() < 0.5}}
        e_agent = CH.pruefe(an, ch)
        e_prinz = CH.pruefe({**an, "agent": None, "subjekt": prinzipal}, ch)
        if e_agent.gewaehrt:
            assert e_prinz.gewaehrt                        # wirksam(Agent) ⊆ wirksam(Prinzipal)
            if an["aktion"].startswith(("fibu.", "ap.")):  # geld-Boden ⇒ Mensch entscheidet
                assert "mensch_entscheidet" in e_agent.obliegenheiten
        n += 1
    assert n >= 100


def test_p7_agent_ohne_prinzipal_verweigert():
    ch = {"charta_version": "t", "artikel": [{
        "aktion": "memo.schreiben", "gewaehre": [[{"p": "immer"}]]}]}
    an = {"aktion": "memo.schreiben", "zeit": ZEITEN[0],
          "subjekt": {"art": "agent", "id": "agent:x"},
          "agent": {"id": "agent:x", "autonomie": "monitored"}, "objekt": {}}
    assert CH.pruefe(an, ch).gewaehrt is False             # fail-closed ohne Prinzipal


# ── P8 · Totalität + Determinismus (CH-4) ────────────────────────────────────

def test_p8_totalitaet_und_determinismus():
    rng = random.Random(0xB1221 + 8)
    muell_antrag = [None, 1, "x", [], {}, {"aktion": 123},
                    {"aktion": "fibu.buchen", "subjekt": 42},
                    {"aktion": "fibu.buchen", "subjekt": {"rollen": "keine_liste"},
                     "objekt": {"betrag_minor": 1.5}},
                    {"aktion": "fibu.buchen", "agent": {"autonomie": "monitored"}}]
    muell_charta = [{"charta_version": "t", "artikel": [
        {"aktion": "fibu.buchen", "gewaehre": [[{"p": "immer"}]]}]},
        {"artikel": "kaputt"}, {}, None, {"artikel": [1, "x", None]}]
    for _ in range(160):
        an = rng.choice(muell_antrag) if rng.random() < 0.4 else _antrag(rng)
        ch = rng.choice(muell_charta) if rng.random() < 0.4 else _charta(rng)
        e1 = CH.pruefe(an, ch)                              # darf NIE werfen (CH-4)
        assert isinstance(e1, CH.Entscheid)
        an_kopie = json.loads(json.dumps(an)) if isinstance(an, (dict, list)) else an
        ch_kopie = json.loads(json.dumps(ch)) if isinstance(ch, (dict, list)) else ch
        assert CH.pruefe(an_kopie, ch_kopie) == e1          # deterministisch
