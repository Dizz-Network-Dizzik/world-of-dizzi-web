"""DzCharta — Policy-Fabric (V-BIZZI-2, B2) — Modell · Validierung · Evaluator.

Die *Verfassung* der Bizzi-Säule als netzweiter appkit-Baustein (docs/84 §B,
CH-1…CH-18): EINE totale, statisch analysierbare Politik über den vier gelebten
Achsen — Assurance · Sensitivität · Autonomie · Wirkungs-Klasse.

- **Artikel** liegen als deklaratives kanon-JSON vor — *kein Text-Parser* (die
  Textform ist Rendering, ``rendere()`` / §B2.2). Ein Artikel = eine Aktion mit
  Gewährungen (Disjunktion von Konjunktionen) und Schranken (Bedingung ⇒ Folge).
- **pruefe()** ist rein, total, wirft nie (CH-4): deny-by-default (CH-1),
  Monotonie (CH-2), fail-closed-Asymmetrie (CH-3), Obliegenheiten-Union +
  verweigere-Dominanz (CH-10), Schatten-Prinzip Agent ⊆ Prinzipal (CH-9).
- **Entscheid** = signierte Einmal-Capability (CH-6). Diese Datei liefert den
  reinen Urteils-Kern; Signatur/TTL/CAS/Chronik-Bindung baut R2 (Tabellen
  ``charta_versionen``/``charta_entscheide``).

Reine Bibliothek: stdlib + ``appkit.chronik`` (Kanon-Wiederverwendung, CH-17) +
``appkit.agenten`` (ruft ``wirksame_stufe`` AUF, ersetzt sie NIE — CH-9). KEIN
Cedar-Import (CH-18: Cedar ist ein dev-seitiges Schatten-Orakel, §B7).

Vertrag: ``docs/84_BIZZI_CONTROLLING_UND_CHARTA_FABLE.md`` §B (build-ready).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable

from . import agenten, chronik


class ChartaFehler(Exception):
    """Fail-loud bei Validierung (CH-3/8/17/18) — VOR Aktivierung einer Version.
    Der Evaluator ``pruefe`` wirft hingegen NIE (CH-4, Totalität)."""


# ─────────────────────────────────────────────────────────────────────────────
# Achsen-Ordnungen + Vokabular (an die gelebten Nähte gepinnt)
# ─────────────────────────────────────────────────────────────────────────────

#: Assurance == ``auth.LEVELS``-Reihenfolge. Bewusst NICHT importiert (charta
#: bleibt HTTP-frei/rein); Naht-Frische-Check §B10: bei auth.LEVELS-Änderung hier
#: nachziehen.
_ASSURANCE = ("lokal", "verifiziert", "hochsicher")
#: Sensitivitäts-Leiter (Manifest, wie ``auth.sensitivity_level``-Böden).
_SENSITIVITAET = ("normal", "hoch", "hoechst")

_AKTION_RE = re.compile(r"^[a-z0-9_.]+$")
#: CH-8: keine user_id-/agent-/system-Literale in Artikeln (nur Rollen/Attribute).
_ID_LITERAL_RE = re.compile(r"^(u:|agent:|system$)")
_ZEIT_FENSTER_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
_DEZIMAL_RE = re.compile(r"^[0-9]+$")   # Geld = Minor-Units als Dezimal-String (CH-17)

#: Geschlossenes Obliegenheiten-Vokabular (B2.2). ``verweigere`` ist die
#: Sonder-Folge (Dominanz, CH-10), keine Obliegenheit.
_OBLIEGENHEITEN = frozenset({
    "step_up", "vier_augen", "siegelpflichtig", "mensch_entscheidet",
    "nur_lokal", "nur_fluechtig", "stapel_pruefsumme",
})
_OBLIEGENHEIT_PARAM = frozenset({"ttl", "protokoll_klasse"})   # Form ``name:arg``
VERWEIGERE = "verweigere"

#: CH-13 — Wiederherstellungs-Artikel = Code-Konstante (NICHT editierbar).
#: v1-Form aus Gate **G-CHARTA-NOTWEG** (David 13.07.2026): lokale Konsole +
#: Stammschlüssel + hochsicher/frisch (ab B7 zusätzlich Zeugen-Quorum). Die
#: Konsolen-/Stamm-Signatur erzwingt die CLI-/HTTP-Schicht (R3) — der Artikel
#: selbst hält den Verfassungsrang: KEINE Charta-Version kann den Notweg
#: entfernen (Lehre aus der defense-P0-Selbstaussperrung, §B9).
WIEDERHERSTELLUNG_AKTION = "charta.wiederherstellen"
WIEDERHERSTELLUNGS_ARTIKEL: dict = {
    "aktion": WIEDERHERSTELLUNG_AKTION,
    "gewaehre": [[
        {"p": "assurance_min", "w": "hochsicher"},
        {"p": "frisch", "w": 300},
        {"p": "rolle", "w": "stammschluessel"},
    ]],
    "schranken": [{"wenn": [{"p": "immer"}], "dann": ["siegelpflichtig"]}],
}

#: CH-16 Bestands-Schutz (D5): Charta-Zwang gilt NUR auf diesen registrierten
#: Kern-Routen-Präfixen — kein bestehender Endpoint ändert Response/Statuscode.
CHARTA_PFLICHT_PRAEFIXE = ("fibu.", "ap.", "verzeichnis.", "charta.", "umzug.")


def ist_charta_pflicht(aktion: str) -> bool:
    """True ⇔ die Aktion liegt auf einer charta-pflichtigen Kern-Route (CH-16).
    Alles andere bleibt unverändert (D5) — die Charta ist rein additiv."""
    return isinstance(aktion, str) and aktion.startswith(CHARTA_PFLICHT_PRAEFIXE)


# ═════════════════════════════════════════════════════════════════════════════
# EVALUATOR-KERN (≤500 Zeilen, CH-4) — pruefe + Prädikate + Helfer
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Entscheid:
    """Reines Urteil des Evaluators (CH-4). Signatur/TTL/CAS = R2."""
    gewaehrt: bool
    obliegenheiten: tuple[str, ...] = ()
    grund: str = ""


def _verweigert(grund: str) -> Entscheid:
    return Entscheid(False, (), grund)


# --- Koordinaten-Zugriff (fail-closed, nie werfend) -------------------------------

def _subj(antrag: dict) -> dict:
    s = antrag.get("subjekt")
    return s if isinstance(s, dict) else {}


def _obj(antrag: dict) -> dict:
    o = antrag.get("objekt")
    return o if isinstance(o, dict) else {}


def _ordnung_idx(ordnung: tuple, wert: Any) -> int | None:
    try:
        return ordnung.index(wert)
    except ValueError:
        return None


def _betrag_quelle(objekt: dict) -> int | None:
    """Betrags-Basis (CH-12): Stapel-Summe schlägt Einzelbetrag — Splitting
    hebelt Schwellen nicht. Nur Dezimal-Strings (CH-17), sonst ``None``."""
    for schluessel in ("stapel_summe_minor", "betrag_minor"):
        v = objekt.get(schluessel)
        if isinstance(v, str) and _DEZIMAL_RE.match(v):
            return int(v)
    return None


# --- Prädikate: True/False oder None (fehlende Koordinate ⇒ Asymmetrie, CH-3) -----

def _p_rolle(w: Any, antrag: dict) -> bool | None:
    r = _subj(antrag).get("rollen")
    return None if not isinstance(r, list) else w in r


def _p_assurance_min(w: Any, antrag: dict) -> bool | None:
    hi = _ordnung_idx(_ASSURANCE, _subj(antrag).get("assurance"))
    wi = _ordnung_idx(_ASSURANCE, w)
    return None if hi is None or wi is None else hi >= wi


def _p_frisch(w: Any, antrag: dict) -> bool | None:
    fs = _subj(antrag).get("frisch_s")
    if isinstance(fs, bool) or isinstance(w, bool):
        return None
    if not isinstance(fs, int) or not isinstance(w, int):
        return None
    return fs <= w


def _p_art(w: Any, antrag: dict) -> bool | None:
    a = _subj(antrag).get("art")
    return None if a is None else a == w


def _p_edition(w: Any, antrag: dict) -> bool | None:
    e = _subj(antrag).get("edition")
    return None if e is None else e == w


def _p_sensitivitaet_min(w: Any, antrag: dict) -> bool | None:
    hi = _ordnung_idx(_SENSITIVITAET, _obj(antrag).get("sensitivitaet"))
    wi = _ordnung_idx(_SENSITIVITAET, w)
    return None if hi is None or wi is None else hi >= wi


def _p_bereich_fremd(_w: Any, antrag: dict) -> bool:
    """Wahr wenn fremd ODER Koordinate fehlt (fail-closed, definiert — nie None)."""
    bid = _obj(antrag).get("bereich_id")
    ber = _subj(antrag).get("bereiche")
    if not bid or not isinstance(ber, list):
        return True
    return bid not in ber


def _p_betrag_ab(w: Any, antrag: dict) -> bool | None:
    b = _betrag_quelle(_obj(antrag))
    if b is None or not (isinstance(w, str) and _DEZIMAL_RE.match(w)):
        return None
    return b >= int(w)


def _p_betrag_bis(w: Any, antrag: dict) -> bool | None:
    b = _betrag_quelle(_obj(antrag))
    if b is None or not (isinstance(w, str) and _DEZIMAL_RE.match(w)):
        return None
    return b <= int(w)


def _p_einzel_max_ab(w: Any, antrag: dict) -> bool | None:
    v = _obj(antrag).get("einzel_max_minor")
    if not (isinstance(v, str) and _DEZIMAL_RE.match(v)):
        return None
    if not (isinstance(w, str) and _DEZIMAL_RE.match(w)):
        return None
    return int(v) >= int(w)


def _hhmm(iso: str) -> str | None:
    m = re.search(r"T([01]\d|2[0-3]):([0-5]\d)", iso)
    return f"{m.group(1)}:{m.group(2)}" if m else None


def _p_zeit_ausserhalb(w: Any, antrag: dict) -> bool | None:
    zeit = antrag.get("zeit")
    if not isinstance(zeit, str) or not (isinstance(w, str) and _ZEIT_FENSTER_RE.match(w)):
        return None
    hhmm = _hhmm(zeit)
    if hhmm is None:
        return None
    von, bis = w.split("-")
    drin = (von <= hhmm <= bis) if von <= bis else (hhmm >= von or hhmm <= bis)
    return not drin


def _p_eigentuemer(_w: Any, antrag: dict) -> bool | None:
    sid, oid = _subj(antrag).get("id"), _obj(antrag).get("eigentuemer_id")
    return None if not sid or not oid else sid == oid


def _p_erfasser_ist_subjekt(_w: Any, antrag: dict) -> bool | None:
    sid, eid = _subj(antrag).get("id"), _obj(antrag).get("erfasser_id")
    return None if not sid or not eid else eid == sid


def _p_immer(_w: Any, _antrag: dict) -> bool:
    return True


#: Geschlossenes Prädikat-Vokabular v1 (B2.3). Neues Prädikat = Vertrags-Änderung.
_PRAEDIKAT_FN: dict[str, Callable[[Any, dict], bool | None]] = {
    "rolle": _p_rolle,
    "assurance_min": _p_assurance_min,
    "frisch": _p_frisch,
    "art": _p_art,
    "edition": _p_edition,
    "sensitivitaet_min": _p_sensitivitaet_min,
    "bereich_fremd": _p_bereich_fremd,
    "betrag_ab": _p_betrag_ab,
    "betrag_bis": _p_betrag_bis,
    "einzel_max_ab": _p_einzel_max_ab,
    "zeit_ausserhalb": _p_zeit_ausserhalb,
    "eigentuemer": _p_eigentuemer,
    "erfasser_ist_subjekt": _p_erfasser_ist_subjekt,
    "immer": _p_immer,
}
PRAEDIKATE = frozenset(_PRAEDIKAT_FN)


def _wahr(praedikat: Any, antrag: dict, *, in_schranke: bool) -> bool:
    """Ein Prädikat auswerten. Unbekanntes Vokabular ODER fehlende Koordinate ⇒
    fail-closed-Asymmetrie (CH-3): in Gewährungen *falsch*, in Schranken *wahr*.
    Jede Ausnahme wird abgefangen (CH-4 Totalität) und fail-closed gedeutet."""
    if not isinstance(praedikat, dict):
        return in_schranke
    fn = _PRAEDIKAT_FN.get(praedikat.get("p"))
    if fn is None:
        return in_schranke
    try:
        ergebnis = fn(praedikat.get("w"), antrag)
    except Exception:
        return in_schranke
    return in_schranke if ergebnis is None else bool(ergebnis)


def _artikel_liste(charta: Any) -> list:
    a = charta.get("artikel") if isinstance(charta, dict) else None
    return a if isinstance(a, list) else []


def _artikel_fuer(charta: Any, aktion: str) -> list:
    if aktion == WIEDERHERSTELLUNG_AKTION:
        return [WIEDERHERSTELLUNGS_ARTIKEL]            # CH-13: immer die Konstante
    return [a for a in _artikel_liste(charta)
            if isinstance(a, dict) and a.get("aktion") == aktion]


def _gewaehre_zeilen(art: dict) -> list:
    z = art.get("gewaehre")
    return z if isinstance(z, list) else []


def _schranken(art: dict) -> list:
    s = art.get("schranken")
    return s if isinstance(s, list) else []


def _aktions_klasse(antrag: dict) -> str:
    """Wirkungs-Klasse für die Autonomie-Böden (CH-9). ``geld``/``gesundheit``
    klemmen ``wirksame_stufe`` unverrückbar auf ``pre_approval`` (agenten.py-
    Naht). Default für schreibende Agent-Aktionen = ``aussenwirkung`` (nie
    ``entwurf``); ein Betrag im Objekt erzwingt ``geld``."""
    aktion = antrag.get("aktion", "")
    for praefix, klasse in (
        ("healthy.", "gesundheit"), ("health.", "gesundheit"),
        ("fibu.", "geld"), ("ap.", "geld"), ("money.", "geld"),
    ):
        if aktion.startswith(praefix):
            return klasse
    if _betrag_quelle(_obj(antrag)) is not None:
        return "geld"
    return "aussenwirkung"


def pruefe(antrag: dict, charta: dict, *, vier_augen_moeglich: bool = True) -> Entscheid:
    """DER Urteils-Kern (CH-4): rein, total, wirft nie.

    ``vier_augen_moeglich`` = existiert eine zweite berechtigte Identität?
    (KEIM-Realität, D2/CH-14) — bei ``False`` sind ``vier_augen``-Artikel *tote
    Artikel*: der Antrag scheitert mit Klartext statt still herabzustufen.
    """
    if not isinstance(antrag, dict):
        return _verweigert("antrag ist kein Objekt")
    aktion = antrag.get("aktion")
    if not isinstance(aktion, str):
        return _verweigert("keine Aktion")

    artikel = _artikel_fuer(charta, aktion)
    if not artikel:
        return _verweigert("keine Gewährung (deny-default)")            # CH-1

    gewaehrt = any(
        all(_wahr(p, antrag, in_schranke=False) for p in zeile)
        for art in artikel for zeile in _gewaehre_zeilen(art)
        if isinstance(zeile, list) and zeile
    )
    if not gewaehrt:
        return _verweigert("keine zutreffende Gewährung")               # CH-1

    folgen: set[str] = set()                                            # CH-10 Union
    for art in artikel:
        for schranke in _schranken(art):
            if not isinstance(schranke, dict):
                continue
            wenn = schranke.get("wenn")
            if not isinstance(wenn, list) or not wenn:
                continue
            if all(_wahr(p, antrag, in_schranke=True) for p in wenn):
                dann = schranke.get("dann")
                if isinstance(dann, list):
                    folgen.update(f for f in dann if isinstance(f, str))

    if VERWEIGERE in folgen:                                            # CH-10 Dominanz
        return _verweigert("schranke: verweigere")

    agent = antrag.get("agent")                                        # CH-9 Schatten
    if isinstance(agent, dict):
        stufe = agenten.wirksame_stufe(
            _aktions_klasse(antrag),
            bereich_stufe=agent.get("bereich_stufe"),
            agent_stufe=agent.get("autonomie"),
            eval_gruen=bool(agent.get("eval_gruen", False)),
        )
        if not agenten.stufe_erlaubt_ausfuehrung(stufe):
            folgen.add("mensch_entscheidet")
        prinzipal = agent.get("prinzipal")
        if not isinstance(prinzipal, dict):
            return _verweigert("agent ohne prinzipal-koordinaten")     # fail-closed
        als_prinzipal = {**antrag, "agent": None, "subjekt": prinzipal}
        if not pruefe(als_prinzipal, charta,
                      vier_augen_moeglich=vier_augen_moeglich).gewaehrt:
            return _verweigert("agent ueberschreitet prinzipal")       # Meet ⊆

    if not vier_augen_moeglich and "vier_augen" in folgen:            # CH-14 / D2
        return _verweigert("vier_augen unerfuellbar (kein zweites Subjekt)")

    return Entscheid(True, tuple(sorted(folgen)), "")


# ═════════════════════════════════════════════════════════════════════════════
# Validierung (CH-3/8/17/18) — VOR Aktivierung; unbekanntes Vokabular = ungültig
# ═════════════════════════════════════════════════════════════════════════════


def validiere(charta: dict) -> str:
    """Prüft eine Charta-Version streng und liefert den ``artikel_hash``
    (``sha256:…`` über ``kanon(artikel)``). Wirft ``ChartaFehler`` bei jedem
    Verstoß — *vor* Aktivierung, damit unbekanntes Vokabular gar nicht erst
    wirksam wird (CH-3, Validierung beim Laden)."""
    if not isinstance(charta, dict):
        raise ChartaFehler("Charta muss ein Objekt sein")
    version = charta.get("charta_version")
    if not isinstance(version, str) or not version:
        raise ChartaFehler("charta_version fehlt oder ist ungültig")
    artikel = charta.get("artikel")
    if not isinstance(artikel, list) or not artikel:
        raise ChartaFehler("artikel-Liste fehlt oder ist leer")

    gesehen: set[str] = set()
    for art in artikel:
        _validiere_artikel(art, gesehen)

    try:                                       # Kanon erzwingt ASCII-Keys (CH-9-BZ)
        roh = chronik.kanon(artikel)           # und verbietet float (CH-17)
    except chronik.ChronikFehler as e:
        raise ChartaFehler(f"Artikel nicht kanon-fähig: {e}") from e
    return "sha256:" + hashlib.sha256(roh.encode("utf-8")).hexdigest()


def _validiere_artikel(art: Any, gesehen: set[str]) -> None:
    if not isinstance(art, dict):
        raise ChartaFehler("Artikel muss ein Objekt sein")
    aktion = art.get("aktion")
    if not isinstance(aktion, str) or not _AKTION_RE.match(aktion):
        raise ChartaFehler(f"aktion ungültig (nur [a-z0-9_.]): {aktion!r}")
    if aktion == WIEDERHERSTELLUNG_AKTION:                              # CH-13
        raise ChartaFehler(
            "charta.wiederherstellen ist Code-Konstante — nicht in Versionen definierbar")
    if aktion in gesehen:
        raise ChartaFehler(f"doppelter Artikel für Aktion {aktion!r}")
    gesehen.add(aktion)

    gewaehre = art.get("gewaehre")
    if not isinstance(gewaehre, list) or not gewaehre:
        raise ChartaFehler(f"{aktion}: gewaehre fehlt oder ist leer")
    for zeile in gewaehre:
        if not isinstance(zeile, list) or not zeile:
            raise ChartaFehler(f"{aktion}: gewähre-Zeile muss nichtleere Konjunktion sein")
        for p in zeile:
            _validiere_praedikat(p, aktion)

    schranken = art.get("schranken", [])
    if not isinstance(schranken, list):
        raise ChartaFehler(f"{aktion}: schranken muss eine Liste sein")
    for schranke in schranken:
        if not isinstance(schranke, dict):
            raise ChartaFehler(f"{aktion}: Schranke muss ein Objekt sein")
        wenn, dann = schranke.get("wenn"), schranke.get("dann")
        if not isinstance(wenn, list) or not wenn:
            raise ChartaFehler(f"{aktion}: Schranke ohne 'wenn'")
        for p in wenn:
            _validiere_praedikat(p, aktion)
        if not isinstance(dann, list) or not dann:
            raise ChartaFehler(f"{aktion}: Schranke ohne 'dann'")
        for folge in dann:
            _validiere_folge(folge, aktion)


def _validiere_praedikat(p: Any, aktion: str) -> None:
    if not isinstance(p, dict) or not isinstance(p.get("p"), str):
        raise ChartaFehler(f"{aktion}: Prädikat muss die Form {{'p': …}} haben")
    name = p["p"]
    if name not in PRAEDIKATE:                                          # CH-3 Vokabular
        raise ChartaFehler(f"{aktion}: unbekanntes Prädikat {name!r}")
    wert = p.get("w")
    if isinstance(wert, str) and _ID_LITERAL_RE.match(wert):           # CH-8
        raise ChartaFehler(f"{aktion}: ID-Literal {wert!r} verboten (nur Rollen/Attribute)")
    if isinstance(wert, float):                                        # CH-17
        raise ChartaFehler(f"{aktion}: {name} — float verboten (Geld = Dezimal-String)")

    if name in ("betrag_ab", "betrag_bis", "einzel_max_ab"):
        if not (isinstance(wert, str) and _DEZIMAL_RE.match(wert)):
            raise ChartaFehler(f"{aktion}: {name} verlangt Minor-Dezimal-String, nicht {wert!r}")
    elif name == "frisch":
        if not isinstance(wert, int) or isinstance(wert, bool) or wert < 0:
            raise ChartaFehler(f"{aktion}: frisch verlangt Sekunden als nicht-negatives int")
    elif name == "assurance_min":
        if wert not in _ASSURANCE:
            raise ChartaFehler(f"{aktion}: assurance_min {wert!r} ∉ {_ASSURANCE}")
    elif name == "sensitivitaet_min":
        if wert not in _SENSITIVITAET:
            raise ChartaFehler(f"{aktion}: sensitivitaet_min {wert!r} ∉ {_SENSITIVITAET}")
    elif name == "zeit_ausserhalb":
        if not (isinstance(wert, str) and _ZEIT_FENSTER_RE.match(wert)):
            raise ChartaFehler(f"{aktion}: zeit_ausserhalb verlangt 'hh:mm-hh:mm'")
    elif name in ("rolle", "art", "edition"):
        if not isinstance(wert, str) or not wert:
            raise ChartaFehler(f"{aktion}: {name} verlangt einen nichtleeren String")
    elif name in ("bereich_fremd", "eigentuemer", "erfasser_ist_subjekt", "immer"):
        if wert is not None:
            raise ChartaFehler(f"{aktion}: {name} nimmt keinen Wert")


def _validiere_folge(folge: Any, aktion: str) -> None:
    if not isinstance(folge, str) or not folge:
        raise ChartaFehler(f"{aktion}: Folge muss ein nichtleerer String sein")
    if folge == VERWEIGERE or folge in _OBLIEGENHEITEN:
        return
    name, _, arg = folge.partition(":")
    if name in _OBLIEGENHEIT_PARAM and arg:
        return
    raise ChartaFehler(f"{aktion}: unbekannte Folge {folge!r}")


# ═════════════════════════════════════════════════════════════════════════════
# Antrags-Konstruktor (CH-5) + Renderer (B2.2) + Charta-Fassade
# ═════════════════════════════════════════════════════════════════════════════

#: Erlaubte Objekt-Fakten (wirkungsfrei) — der Mantel liefert NUR diese. Alles
#: andere (v. a. Subjekt-Attribute) wird strukturell verworfen (CH-5).
_OBJEKT_FELDER = (
    "bereich_id", "betrag_minor", "stapel_summe_minor", "einzel_max_minor",
    "stapel_hash", "erfasser_id", "eigentuemer_id", "sensitivitaet",
)


def _nur_objekt_fakten(objekt: Any) -> dict:
    if not isinstance(objekt, dict):
        return {}
    return {k: objekt[k] for k in _OBJEKT_FELDER if k in objekt}


def antrag_bauen(aktion: str, *, user_id: str, assurance: str, edition: str,
                 rollen, bereiche, objekt: dict, frisch_s: int | None = None,
                 art: str = "mensch", agent: dict | None = None,
                 zeit: str) -> dict:
    """EINZIGER Antrags-Konstruktor (CH-5): die Subjekt-Koordinaten stammen
    AUSSCHLIESSLICH aus vertrauenswürdigem Server-Zustand (``auth.UserContext`` +
    Verzeichnis-KEIM). Der Mantel/Client liefert nur ``aktion`` + ``objekt``
    (wirkungsfreie Fakten, whitelist ``_OBJEKT_FELDER``) — ein ``subjekt`` im
    Client-Payload hat hier keinen Eingang und ist damit strukturell wirkungslos.
    """
    subjekt: dict = {
        "art": art, "id": user_id, "assurance": assurance,
        "rollen": sorted({r for r in (rollen or []) if isinstance(r, str)}),
        "bereiche": sorted({b for b in (bereiche or []) if isinstance(b, str)}),
        "edition": edition,
    }
    if frisch_s is not None:
        subjekt["frisch_s"] = int(frisch_s)
    return {
        "aktion": aktion, "zeit": zeit, "subjekt": subjekt,
        "agent": agent, "objekt": _nur_objekt_fakten(objekt),
    }


def _rendere_praedikat(p: Any) -> str:
    if not isinstance(p, dict):
        return "?"
    wert = p.get("w")
    return f"{p.get('p', '?')}({'' if wert is None else wert})"


def rendere(charta: dict) -> str:
    """Menschenlesbare Textform (B2.2, EBNF) — nur Anzeige/Doku (WP/Betriebsrat/
    Verfahrensdoku), NIE Eingabe. Aus dem kanon-JSON gerendert, kein Parser."""
    zeilen: list[str] = []
    for art in _artikel_liste(charta):
        zeilen.append(f"artikel {art.get('aktion', '?')}:")
        for zeile in _gewaehre_zeilen(art):
            zeilen.append("  gewähre: " + " und ".join(_rendere_praedikat(p) for p in zeile))
        schranken = _schranken(art)
        if schranken:
            zeilen.append("  schranken:")
            for s in schranken:
                bed = " und ".join(_rendere_praedikat(p) for p in s.get("wenn", []))
                dann = s.get("dann") or []
                folge = "verweigere" if VERWEIGERE in dann else ", ".join(dann)
                zeilen.append(f"    - {bed} ⇒ {folge}")
    return "\n".join(zeilen)


@dataclass(frozen=True)
class Charta:
    """Validierte, unveränderliche Charta-Version (Fassade um das kanon-JSON).
    ``aus_json`` validiert einmal; ``pruefe`` bewertet gegen den Kern."""
    version: str
    artikel: tuple
    artikel_hash: str

    @staticmethod
    def aus_json(charta: dict) -> "Charta":
        h = validiere(charta)
        return Charta(charta["charta_version"], tuple(charta["artikel"]), h)

    def als_dict(self) -> dict:
        return {"charta_version": self.version, "artikel": list(self.artikel)}

    def pruefe(self, antrag: dict, *, vier_augen_moeglich: bool = True) -> Entscheid:
        return pruefe(antrag, self.als_dict(), vier_augen_moeglich=vier_augen_moeglich)

    def rendere(self) -> str:
        return rendere(self.als_dict())
