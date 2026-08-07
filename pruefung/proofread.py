#!/usr/bin/env python3
"""proofread.py - the language gate. Run before every push, next to sweep.ps1.

The technical gates were tight and the site still went out with spelling
mistakes in it: bake.py proves the links, pruefen.py proves the structure,
kontrast.py proves the colours, sweep.ps1 proves nothing private leaked - and
not one of them reads a sentence. This one reads the sentences.

It judges the BAKED pages, not the fragments in seiten/. Titles, meta
descriptions, navigation labels and the whole footer are prose that lives in
bake.py, never in seiten/ - a gate pointed at the fragments would be blind to
exactly the text a search engine quotes. Findings are traced back to the file
that has to be edited, so reading dist/ costs nothing in convenience.

Four layers, deliberately independent, because each one covers the others' blind spot:

  1. PATTERNS   a growing list of known misspellings and typographic slips.
                Fires even on words the dictionary accepts - which is the whole
                point: the dictionary is built from this repository's own
                vocabulary, so any mistake already in the text would otherwise
                be enrolled as a legal word. This layer is the antidote to that
                circularity, and it is the layer to extend when a reader finds
                something the gate missed.
  2. DICTIONARY every word of rendered prose must appear in a word list. The
                lists hold the validated vocabulary of this site - validated
                means a fresh reader confirmed each entry, not that it occurred.
                An unknown word is a finding: either a typo or a word to add.
  3. FIGURES    the numbers. Every claim listed in FAKTEN must carry the same
                value everywhere it appears, and where a canonical value is
                declared, that value. Two pages disagreeing is a defect no
                matter which of them is right.
  4. SECURITIES the line Law 12 draws: this site advertises the work, never an
                investment. Participation terms, promised returns, token offers
                and "invest now" mechanics are forbidden on every page, and the
                one sentence the building brief requires verbatim on /vision/
                has to actually be there. A legal rule that lives only in a
                human's memory is the exact failure this whole gate answers.

Limits, stated plainly (see also the closing section of README):
  - Rendered text only. HTML collapses whitespace, so a double space in a
    fragment is invisible to a visitor and is not treated as a defect.
  - <code>, <pre>, <kbd> and <samp> are skipped. Identifiers are not prose.
  - The German pages are checked against German, the English pages against
    English, decided by the lang attribute in effect at that point in the
    document - so the "Deutsch" in the English page's language switch is
    judged as German, not as a broken English word.
  - A dictionary finds typos, not lies. Whether "2,623 tests" is true is a
    question for the reading pass and the repository, not for this script.

    python pruefung/proofread.py                    the gate: exit 0 clean, 1 findings
    python pruefung/proofread.py ../other/README.md  ... plus further files
    python pruefung/proofread.py --woerter          dump the rendered vocabulary
    python pruefung/proofread.py --unbekannt        only the words no list knows
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# A gate that reports „nicht gemessen" as "?nicht gemessen" hides the very
# finding it just made. The Windows console defaults to a code page that cannot
# spell the German pages this script exists to check.
for strom in (sys.stdout, sys.stderr):
    try:
        strom.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Where a finding has to be fixed. dist/ is generated; these are the sources a
# human edits, searched in this order to attribute a word to its origin.
QUELLEN = ["seiten", "vorlagen", "bake.py", "README.md"]


# --------------------------------------------------------------------------
# layer 1: patterns
# --------------------------------------------------------------------------
# Known-wrong spellings and typographic slips. This list grows: every mistake a
# reader reports that the gate did not catch belongs here the same day, so the
# same mistake can never reach the public twice.
#
# Each entry is (language, regex, explanation). The language is "en", "de" or
# "*" and is matched against the lang in force where the text sits, so the
# German rule about E-Mail cannot fire on an English page. The regex is applied
# case-insensitively, so write it in lower case. Anchor whole words with \b -
# without it "adress" fires inside "Adressen" and the finding list fills up
# with noise nobody reads.

MUSTER: list[tuple[str, str, str]] = [
    # -- English, the classic misspellings -------------------------------
    ("en", r"\bteh\b", "teh -> the"),
    ("en", r"\breciev(e|ed|es|er|ing)\b", "recieve -> receive"),
    ("en", r"\bseperate(d|s|ly)?\b", "seperate -> separate"),
    ("en", r"\boccure?d\b", "occured -> occurred"),
    ("en", r"\boccurance(s)?\b", "occurance -> occurrence"),
    ("en", r"\bexistance\b", "existance -> existence"),
    ("en", r"\bindependant(ly)?\b", "independant -> independent"),
    ("en", r"\bconsistant(ly)?\b", "consistant -> consistent"),
    ("en", r"\bpersistant(ly)?\b", "persistant -> persistent"),
    ("en", r"\b(?:dependancy|dependancies)\b", "dependancy -> dependency"),
    ("en", r"\bmaintainance\b", "maintainance -> maintenance"),
    ("en", r"\bcompatability\b", "compatability -> compatibility"),
    ("en", r"\baccomodat(e|ed|es|ing)\b", "accomodate -> accommodate"),
    ("en", r"\b(?:neccessary|necessery|neccesary)\b", "neccessary -> necessary"),
    ("en", r"\bdefinately\b", "definately -> definitely"),
    ("en", r"\bpublically\b", "publically -> publicly"),
    ("en", r"\bwich\b", "wich -> which"),
    ("en", r"\bthier\b", "thier -> their"),
    ("en", r"\balot\b", "alot -> a lot"),
    ("en", r"\bbegining\b", "begining -> beginning"),
    ("en", r"\b(?:writting|runing|geting|seting|planing|comitting|commiting)\b", "wrong consonant doubling"),
    ("en", r"\b(?:refered|prefered|transfered|occuring)\b", "single r: refered -> referred"),
    ("en", r"\baccessable\b", "accessable -> accessible"),
    ("en", r"\bresponsable\b", "responsable -> responsible"),
    ("en", r"\benviroment(s)?\b", "enviroment -> environment"),
    ("en", r"\b(?:lenght|widht|heigth|thruogh)\b", "transposed letters"),
    ("en", r"\bfuntion(s|al)?\b", "funtion -> function"),
    ("en", r"\b(?:strucutre|strucure)\b", "strucutre -> structure"),
    ("en", r"\b(?:architecure|architechture)\b", "architecure -> architecture"),
    ("en", r"\b(?:lanugage|langauge)\b", "langauge -> language"),
    ("en", r"\b(?:avaiable|availabe|avaliable)\b", "avaliable -> available"),
    ("en", r"\b(?:contrat|contarct)\b", "contrat -> contract"),
    ("en", r"\b(?:aplication|applicaton|aplications)\b", "aplication -> application"),
    ("en", r"\b(?:seperat|managment|enviornment|indepenent)\b", "common slip"),
    # contractions written without the apostrophe
    ("en", r"\b(?:dont|doesnt|didnt|wont|cant|isnt|arent|wasnt|werent|hasnt|havent|hadnt|couldnt|wouldnt|shouldnt|youre|theyre|whats)\b",
     "missing apostrophe in a contraction"),

    # -- German ----------------------------------------------------------
    ("de", r"\bdaß\b", "old orthography: daß -> dass"),
    ("de", r"\bmuß\b", "old orthography: muß -> muss"),
    ("de", r"\bmiß(?:ver|brauch|trauen|achtung)", "old orthography: miß- -> miss-"),
    ("de", r"\bstandart\b", "standart -> Standard"),
    ("de", r"\bvorraus\b", "vorraus -> voraus"),
    ("de", r"\bzumindestens\b", "zumindestens -> zumindest / mindestens"),
    ("de", r"\bseperat\b", "seperat -> separat"),
    ("de", r"\brythmus\b", "Rythmus -> Rhythmus"),
    ("de", r"\baddresse(n)?\b", "Addresse -> Adresse"),
    ("de", r"\bintresse(n|nt)?\b", "Intresse -> Interesse"),
    ("de", r"\bnähmlich\b", "nähmlich -> nämlich"),
    ("de", r"\bwiederspiegel(t|n|te)?\b", "wiederspiegeln -> widerspiegeln"),
    ("de", r"\bwiederrufen?\b", "wiederrufen -> widerrufen"),
    ("de", r"\bemail(s)?\b", "email -> E-Mail"),
    ("de", r"\bsinn macht\b", "'Sinn machen' -> 'sinnvoll sein' / 'ergibt Sinn'"),
    # Quotation marks. This is not pedantry: the first reading pass found that
    # every German quotation on de.html opened with „ and closed with a plain
    # ASCII ", which renders as a visibly broken pair - the likeliest source of
    # the spelling report that started all of this. A straight double quote in
    # German prose is always wrong, so the rule can be that blunt.
    ("de", r"\"", "straight double quote in German prose - the pair is „ … “"),
    ("de", r"„[^“„]*(?:\"|'')", "German quotation opened with „ and closed with a straight quote"),
    ("de", r"‚[^‘‚]*'", "German inner quotation opened with ‚ and closed with a straight apostrophe"),

    # -- typography, on the rendered text --------------------------------
    # ':' before a digit is this site's port notation ("the core on :8200"),
    # not a punctuation slip - it is the one exception worth carving out.
    ("*", r"\s+[,;!?]", "space before punctuation"),
    ("*", r"\s+:(?!\d)", "space before a colon"),
    ("*", r"[,;](?=[^\s\d)\]\"'’»«—–…])", "missing space after a comma or semicolon"),
    ("*", r"(?<!\.)\.{2}(?!\.)", "two full stops - an ellipsis is three (…)"),
    ("*", r"[!?]{2,}", "repeated exclamation or question marks"),
    ("en", r"\bi\.e\.[a-z]", "missing space after i.e."),
    ("en", r"\be\.g\.[a-z]", "missing space after e.g."),
]

# Doubled words are handled separately: the pattern has to look at its own
# capture group. It deliberately spans spaces but NOT line breaks - across a
# block boundary "Method" in the navigation and "Method" in the heading below
# it are not a doubling, and treating them as one would bury the real finds.
DOPPELWORT = re.compile(r"\b(\w+)[ \t]+\1\b", re.IGNORECASE | re.UNICODE)
DOPPELWORT_OK = {"had", "that", "is", "long", "very"}


# --------------------------------------------------------------------------
# layer 3: the figures
# --------------------------------------------------------------------------
# A claim that appears twice with two values is a defect whichever value is
# right. Where `kanon` is set, that is the measured truth and every occurrence
# must match it; where it is None the check is only that the site agrees with
# itself. Keep `kanon` empty rather than guessing - a gate that enforces an
# unverified number is worse than no gate, because it makes a wrong number
# permanent.

# A captured number must BEGIN with a digit. Inline elements sit flush against
# each other in the rendered text, so a tile reading "…full-text search." next
# to a chip reading "118 tests" arrives as "search.118 tests" - and a pattern
# starting [\d.,] happily reads that as 0.118. Anchoring on \d costs nothing
# and removes a whole class of phantom figures.
#
# `erlaubt` is the declared-exception mechanism, the same shape sweep.ps1 uses:
# a named set of values that may legitimately coexist, with the reason written
# next to it. It is not an off switch - a value outside the set still fires.

def _bake_zeilen(blank: bool) -> float | None:
    """The builder's own length, measured here rather than trusted. `blank=True`
    counts every physical line, `blank=False` only those with something on them.
    Returns None if bake.py cannot be read, so a missing file disables the
    comparison instead of failing every page against a zero."""
    try:
        zeilen = (ROOT / "bake.py").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return float(len(zeilen) if blank else sum(1 for z in zeilen if z.strip()))


FAKTEN: list[dict] = [
    dict(name="applications",
         muster=[r"(\d+)\s+(?:applications|apps)\b", r"(\d+)\s+Anwendungen\b"],
         woerter={"ten": 10, "zehn": 10, "eleven": 11, "elf": 11, "nine": 9, "neun": 9},
         wortmuster=[r"\b(ten|eleven|nine)\s+(?:applications|apps)\b",
                     r"\b(zehn|elf|neun)\s+Anwendungen\b"],
         erlaubt={9, 10},
         warum="the network is counted both ways on purpose - nine applications around "
               "the Core, ten including it. The numbers panel states the relation, so "
               "both values are correct; anything else is not",
         kanon=None),
    dict(name="tests (network total)",
         muster=[r"(\d[\d.,]*)\s+(?:tests|Tests|test functions|Test-Funktionen)\b"],
         woerter={}, wortmuster=[],
         mindestens=1000,
         warum="only the network total is compared here. The per-application counts on "
               "/apps/ are the same unit word for a different thing, and lumping them in "
               "would report a permanent, meaningless disagreement - the noise that "
               "teaches people to ignore a gate. Their own check is pruefe_app_zahlen()",
         erlaubt=None, kanon=None),
    dict(name="commits",
         muster=[r"(\d[\d.,]*)\+?\s+(?:commits|Commits)\b"],
         woerter={}, wortmuster=[], erlaubt=None, warum="", kanon=None),
    dict(name="pages",
         muster=[r"\b(\d+)\s+(?:pages|Seiten)\b"],
         # "fifteen" joined the list on 07.08.2026, with /mini-karte/. The
         # figure had drifted before that and nothing here could see it: the
         # README still said twelve while dist/ held fourteen pages, because
         # this rule only holds the places that state the number against each
         # other - it cannot count pages, and it never claimed to.
         woerter={"fifteen": 15, "fünfzehn": 15, "twelve": 12, "zwölf": 12,
                  "eleven": 11, "elf": 11, "ten": 10, "zehn": 10},
         wortmuster=[r"\b(fifteen|twelve|eleven|ten)\s+pages\b",
                     r"\b(fünfzehn|zwölf|elf|zehn)\s+Seiten\b"],
         erlaubt=None, warum="", kanon=None),
    dict(name="lines of python",
         muster=[r"(\d[\d.,]*)\s+(?:lines of Python|Zeilen Python)\b"],
         woerter={}, wortmuster=[], erlaubt=None, warum="", kanon=None),
    # The two figures that describe bake.py are the only ones this gate can
    # measure instead of merely compare, because the file is right here. It has
    # drifted twice: the footer said 100 while the file had 530, and then the
    # corrected 530 went stale the moment the file grew. bake.py now writes both
    # figures into the pages itself - this is the independent second opinion, so
    # that a hand-typed number anywhere still fails the gate.
    dict(name="baker size",
         muster=[r"(\d+)-(?:line|Zeilen)[- ](?:Python )?(?:baker|Python-Skript)",
                 r"(\d+)\s+lines in the script that builds this website",
                 r"(\d+)\s+Zeilen im Skript, das diese Website baut"],
         woerter={}, wortmuster=[], erlaubt=None, warum="",
         kanon=_bake_zeilen(blank=True)),
    # Both phrasings, because the sentence was reworded once and the guard was
    # not - and a pattern that matches nothing passes in silence, which is the
    # one failure mode a gate must never have.
    dict(name="baker size, non-blank",
         muster=[r"Of those lines, (\d+) carry a non-whitespace character",
                 r"(\d+) of those lines carry a non-whitespace character"],
         woerter={}, wortmuster=[], erlaubt=None, warum="",
         kanon=_bake_zeilen(blank=False)),
]


# --------------------------------------------------------------------------
# layer 4: the securities line
# --------------------------------------------------------------------------
# Law 12 and section 1.7 of the site's own building brief draw a hard line:
# this site advertises the work, never an investment. Concrete participation
# terms, promised returns, share or token offers and "invest now" mechanics are
# forbidden on every page - German prospectus and investment law, plus unfair
# competition law. Inviting a conversation is allowed and wanted.
#
# The rule was written down once and then lived only in a human's memory. That
# is the failure mode this whole gate exists against, so it gets a layer: the
# forbidden shapes are looked for, and the one sentence the brief requires
# verbatim is checked for presence.

ANLAGE_MUSTER: list[tuple[str, str]] = [
    (r"\binvest\s+now\b", "an 'invest now' call to action"),
    (r"\bjetzt\s+investier", "an 'invest now' call to action"),
    (r"\b(?:minimum|mindest)\s*(?:investment|ticket|einlage|beteiligung)",
     "a minimum ticket - a participation term"),
    (r"\b\d+(?:[.,]\d+)?\s*%\s*(?:equity|stake|shares?|anteil|rendite|return)",
     "a concrete equity or return figure"),
    (r"\b(?:pre-money|post-money|valuation|bewertung)\s*(?:of|von|:)?\s*[€$\d]",
     "a valuation figure"),
    (r"\b(?:guaranteed|garantierte)\s+(?:returns?|rendite|profit)", "a promised return"),
    (r"\b(?:token|coin)\s+(?:sale|offering|presale|angebot)", "a token offering"),
    (r"\b(?:funding|finanzierungs)[- ]?(?:round|runde)\s+(?:open|offen|läuft)",
     "an open funding round - reads as a solicitation"),
    (r"\b(?:buy|kaufe[nt]?)\s+(?:shares|anteile)\b", "a share offer"),
]

# Section 1.7 requires this sentence, word for word, on /vision/.
ANLAGE_PFLICHTSATZ = "invitation to talk, not an offer of securities"
ANLAGE_PFLICHTSEITE = "dist/vision/index.html"


def pruefe_app_zahlen(alle: dict[str, list]) -> list[str]:
    """On /apps/ every application states its test count twice - once on its
    tile in the overview, once on the chip above its section. The two sit two
    hundred lines apart, so correcting one and forgetting the other is the
    obvious way for the page to start contradicting itself. It is not a
    hypothetical: it happened on 26.07.2026, when the Core figure was fixed in
    the section and left standing on the tile. Pair the two lists and say which
    number lost its partner."""
    rel = "dist/apps/index.html"
    if rel not in alle:
        return []
    ganz = re.sub(r"\s+", " ", "".join(t for _, _, t in alle[rel]))

    def hole(rx: str) -> dict[float, int]:
        gefunden: dict[float, int] = defaultdict(int)
        for t in re.finditer(rx, ganz):
            wert = _zahl(t.group(1))
            if wert is not None and wert < 1000:   # the network total is not per-app
                gefunden[wert] += 1
        return gefunden

    kachel = hole(r"(\d[\d.,]*)\s+tests\b")
    schnitt = hole(r"(\d[\d.,]*)\s+test functions\b")
    raus = []
    for wert in sorted(set(kachel) | set(schnitt)):
        if kachel.get(wert, 0) != schnitt.get(wert, 0):
            raus.append(f"{rel}  figures  per-app test count {wert:g} appears "
                        f"{kachel.get(wert, 0)}x as “tests” but "
                        f"{schnitt.get(wert, 0)}x as “test functions” - "
                        f"tile and section have drifted apart")
    return raus


def pruefe_anlage(alle: dict[str, list]) -> list[str]:
    raus: list[str] = []
    for rel, stuecke in sorted(alle.items()):
        ganz = re.sub(r"\s+", " ", "".join(t for _, _, t in stuecke))
        for rx, warum in ANLAGE_MUSTER:
            for t in re.finditer(rx, ganz, re.IGNORECASE):
                raus.append(f"{rel}  securities  {warum}\n"
                            f"        ...{ganz[max(0, t.start() - 45): t.end() + 45].strip()}...")
    if ANLAGE_PFLICHTSEITE in alle:
        ganz = re.sub(r"\s+", " ", "".join(t for _, _, t in alle[ANLAGE_PFLICHTSEITE]))
        if ANLAGE_PFLICHTSATZ not in ganz.lower():
            raus.append(f"{ANLAGE_PFLICHTSEITE}  securities  the sentence required verbatim by "
                        f"the building brief is missing: “…{ANLAGE_PFLICHTSATZ}.”")
    return raus


# --------------------------------------------------------------------------
# what this gate does NOT decide
# --------------------------------------------------------------------------
# Whether a word is allowed to stand in a particular file is sweep.ps1's
# question, and it answers it from a private list. This script only asks
# whether a word is spelled correctly. So the provider name the Impressum is
# legally required to carry simply lives in the German word list like any other
# word - no exception mechanism needed, and no second place where a rule about
# names could rot.


# --------------------------------------------------------------------------
# reading the pages
# --------------------------------------------------------------------------

UEBERSPRINGEN = {"script", "style", "code", "pre", "kbd", "samp"}
BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "section",
         "article", "header", "footer", "nav", "main", "td", "th", "tr",
         "dt", "dd", "figcaption", "blockquote", "br", "hr", "title"}
LEER = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# Attributes a human or a screen reader actually reads out.
PROSA_ATTR = {"alt", "title", "aria-label"}
# meta content is prose only for these; the rest is machine configuration.
PROSA_META = {"description", "og:title", "og:description", "og:image:alt"}
# JSON-LD keys that carry sentences rather than identifiers.
PROSA_JSONLD = {"name", "description", "jobTitle", "headline", "about"}


class Prosa(HTMLParser):
    """Pulls the readable text out of a baked page, remembering the language in
    force and the line each piece sits on."""

    def __init__(self, lang: str = "en") -> None:
        super().__init__(convert_charrefs=True)
        self.stuecke: list[tuple[int, str, str]] = []   # (line, lang, text)
        self._lang = [lang]
        self._skip = 0
        self._jsonld: list[str] = []
        self._in_jsonld = False
        self._offen: list[str] = []

    # -- helpers ---------------------------------------------------------
    def _add(self, text: str, zeile: int | None = None) -> None:
        # Whitespace is kept on purpose. Dropping blank pieces also drops the
        # newline this class writes at every block boundary, and then joining
        # the pieces glues the last word of one block to the first word of the
        # next: the navigation "System" and "Apps" become "SystemApps". Nothing
        # reports an error - the checks downstream simply stop matching, and a
        # gate that silently stops looking is worse than no gate.
        if text:
            self.stuecke.append((zeile or self.getpos()[0], self._lang[-1], text))

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag not in LEER:
            self._offen.append(tag)
            self._lang.append(a.get("lang", self._lang[-1]))
        if tag in UEBERSPRINGEN:
            self._skip += 1
        if tag == "script" and a.get("type", "") == "application/ld+json":
            self._in_jsonld = True
        if tag in BLOCK:
            self._add("\n")

        for schluessel in PROSA_ATTR:
            if a.get(schluessel):
                self._add(" " + a[schluessel] + "\n")
        if tag == "meta":
            kennung = a.get("name") or a.get("property") or ""
            if kennung in PROSA_META and a.get("content"):
                self._add(" " + a["content"] + "\n")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in LEER:
            return
        if tag in UEBERSPRINGEN and self._skip:
            self._skip -= 1
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
        if tag in BLOCK:
            self._add("\n")
        # unwind to the matching open tag; pruefen.py already fails on
        # mismatched markup, so here we only need to stay in step with it
        if tag in self._offen:
            while self._offen:
                offen = self._offen.pop()
                if len(self._lang) > 1:
                    self._lang.pop()
                if offen == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._jsonld.append(data)
            return
        if not self._skip:
            self._add(data)

    # -- what the JSON-LD block contributes ------------------------------
    def jsonld_prosa(self) -> list[str]:
        if not self._jsonld:
            return []
        try:
            daten = json.loads("".join(self._jsonld))
        except json.JSONDecodeError:
            return []
        raus: list[str] = []

        def gehe(knoten) -> None:
            if isinstance(knoten, dict):
                for k, v in knoten.items():
                    if k in PROSA_JSONLD and isinstance(v, str):
                        raus.append(v)
                    else:
                        gehe(v)
            elif isinstance(knoten, list):
                for v in knoten:
                    gehe(v)

        gehe(daten)
        return raus


def seiten_sprache(text: str) -> str:
    treffer = re.search(r"<html[^>]*\blang=[\"']([a-z]{2})", text)
    return treffer.group(1) if treffer else "en"


def html_text(pfad: Path) -> list[tuple[int, str, str]]:
    """(line, language, text) for one baked page."""
    roh = pfad.read_text(encoding="utf-8")
    p = Prosa(seiten_sprache(roh))
    p.feed(roh)
    p.close()
    stuecke = list(p.stuecke)
    for satz in p.jsonld_prosa():
        stuecke.append((0, seiten_sprache(roh), " " + satz + "\n"))
    return stuecke


INLINE = re.compile(r"`[^`]*`")
BILD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
AUTOLINK = re.compile(r"<https?://[^>]*>|https?://\S+")

# Removed markup must not leave a hole where a space appears. Deleting the
# backticks around `dist/` in "`dist/`, committed" outright yields ", committed"
# and the punctuation check reports a space before the comma that no reader can
# see. A code span therefore collapses to one neutral glyph: it holds the place,
# carries no letters for the dictionary, and is no punctuation.
PLATZ = "§"


# The showcase README carries its German half under a heading of its own. Read
# as one language, its words land in the English dictionary - and from then on
# the gate accepts "Abhängigkeit" on an English page without a murmur. A
# bilingual file needs its languages kept apart just like the pages do.
SPRACHWECHSEL = re.compile(r"^\s{0,3}#{1,6}\s*(deutsch|german|english|englisch)\b", re.IGNORECASE)
SPRACHE_VON = {"deutsch": "de", "german": "de", "english": "en", "englisch": "en"}


def md_text(pfad: Path) -> list[tuple[int, str, str]]:
    """Markdown, with the code taken out and the link targets dropped."""
    raus: list[tuple[int, str, str]] = []
    im_block = False
    lang = "en"
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
        if zeile.lstrip().startswith("```"):
            im_block = not im_block
            continue
        if im_block:
            continue
        wechsel = SPRACHWECHSEL.match(zeile)
        if wechsel:
            lang = SPRACHE_VON[wechsel.group(1).lower()]
        z = INLINE.sub(PLATZ, zeile)
        z = BILD.sub(PLATZ, z)
        z = LINK.sub(r"\1", z)
        z = AUTOLINK.sub(PLATZ, z)
        z = re.sub(r"^\s{0,3}#{1,6}\s+", "", z)
        z = re.sub(r"^\s{0,3}>\s?", "", z)
        z = re.sub(r"^\s*[-*+]\s+", "", z)
        z = re.sub(r"^\s*\d+\.\s+", "", z)
        z = z.replace("|", " ")              # table cells are separate phrases
        z = re.sub(r"\*\*|__|~~|\*|(?<=\w)_(?=\w)", "", z)   # emphasis, no gap
        raus.append((nr, lang, z + "\n"))
    return raus


# --------------------------------------------------------------------------
# words
# --------------------------------------------------------------------------

WORT = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)


def worte(text: str):
    """Yields (word, offset). Hyphenated compounds fall apart on their own,
    because the pattern has no hyphen in it: 'local-first' becomes two words,
    each of which has to be a real word.

    A letter run touching a digit is not a word: 'Ed25519' would otherwise
    contribute a phantom 'Ed' that no dictionary knows and no reader can find.
    """
    for treffer in WORT.finditer(text):
        a, b = treffer.start(), treffer.end()
        if (a > 0 and text[a - 1].isdigit()) or (b < len(text) and text[b].isdigit()):
            continue
        w = treffer.group(0)
        for endung in ("'s", "’s"):
            if w.lower().endswith(endung) and len(w) > 3:
                w = w[: -len(endung)]
        if len(w) > 1:
            yield w, treffer.start()


def liste_laden(name: str) -> set[str]:
    pfad = LISTEN / name
    if not pfad.exists():
        return set()
    raus = set()
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.split("#")[0].strip()
        if zeile:
            raus.add(zeile.lower())
    return raus




# --------------------------------------------------------------------------
# where a word has to be fixed
# --------------------------------------------------------------------------

_quelltexte: dict[str, str] | None = None

# dist/apps/index.html was baked from seiten/apps.html. Knowing that saves the
# reader from being sent to the first file that happens to contain the word.
def quelldatei(rel: str) -> str | None:
    if not rel.startswith("dist/"):
        return rel                      # a README is its own source
    rest = rel[len("dist/"):]
    if rest.endswith("/index.html"):
        name = rest[: -len("/index.html")]
    elif rest.endswith(".html"):
        name = rest[: -len(".html")]
    else:
        return None
    if name == "index":
        name = "index"
    kandidat = f"seiten/{name}.html"
    return kandidat if (ROOT / kandidat).exists() else None


def quellen() -> dict[str, str]:
    global _quelltexte
    if _quelltexte is None:
        _quelltexte = {}
        for eintrag in QUELLEN:
            p = ROOT / eintrag
            dateien = sorted(p.rglob("*")) if p.is_dir() else [p]
            for d in dateien:
                if d.is_file() and d.suffix in {".html", ".py", ".md"}:
                    try:
                        _quelltexte[d.relative_to(ROOT).as_posix()] = d.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        pass
    return _quelltexte


def herkunft(wort: str, ziel: str) -> str:
    """The editable file a rendered word came from - dist/ is generated. The
    page's own fragment is searched first, then the chrome that bake.py glues
    around every page."""
    rx = re.compile(r"\b" + re.escape(wort) + r"\b", re.IGNORECASE)
    zuerst = quelldatei(ziel)
    reihe = list(quellen().items())
    if zuerst:
        reihe.sort(key=lambda kv: (kv[0] != zuerst, kv[0] != "bake.py"))
    for rel, text in reihe:
        treffer = rx.search(text)
        if treffer:
            zeile = text[: treffer.start()].count("\n") + 1
            return f"{rel}:{zeile}"
    return "?"


# --------------------------------------------------------------------------
# the three layers
# --------------------------------------------------------------------------

def pruefe_muster(rel: str, stuecke) -> list[str]:
    raus = []
    gesehen: set[tuple] = set()
    for zeile, lang, text in stuecke:
        flach = re.sub(r"[ \t]+", " ", text).strip()
        if not flach:
            continue
        for muster_lang, rx, warum in MUSTER:
            if muster_lang != "*" and muster_lang != lang:
                continue
            for t in re.finditer(rx, flach, re.IGNORECASE | re.UNICODE):
                schnipsel = flach[max(0, t.start() - 35): t.end() + 35].strip()
                schluessel = (warum, schnipsel)
                if schluessel in gesehen:
                    continue    # the same sentence reached us through alt= and prose
                gesehen.add(schluessel)
                raus.append(f"{rel}:{zeile}  pattern  {warum}\n        ...{schnipsel}...")

    # Doubled words need the running text of a block, so the chunks are joined -
    # but line breaks are kept, because the pattern must not reach across them.
    ganz = "".join(t for _, _, t in stuecke)
    ganz = re.sub(r"[ \t]+", " ", ganz)
    for t in DOPPELWORT.finditer(ganz):
        if t.group(1).lower() in DOPPELWORT_OK:
            continue
        raus.append(f"{rel}  pattern  doubled word '{t.group(1)}'\n"
                    f"        ...{ganz[max(0, t.start() - 35): t.end() + 35].strip()}...")
    return raus


# Typographic consistency is a page-level property, not something a single
# regex can see: one page may legitimately use straight marks throughout, and
# another curly ones - what is never right is both in the same document.
#
# An apostrophe stands INSIDE a word ("doesn't", "the app's"); the same glyph at
# a word boundary is a single quotation mark. The first version of this check
# ignored that and reported method.html as mixed, when the only curly mark on
# the page was the nested quotation ‘Quickly, please’ - correct as it stands.
# That false positive nearly caused seventeen correct apostrophes to be
# rewritten, which is the sort of damage an over-eager gate does.
APOSTROPH_GERADE = re.compile(r"(?<=\w)'(?=\w)")
APOSTROPH_TYPO = re.compile(r"(?<=\w)’(?=\w)")
ANFUEHRUNG = {"gerade": '"', "typografisch": "“”„"}


def pruefe_typografie(rel: str, stuecke) -> list[str]:
    ganz = "".join(t for _, _, t in stuecke)
    raus = []
    paare = [
        ("apostrophe", len(APOSTROPH_GERADE.findall(ganz)), len(APOSTROPH_TYPO.findall(ganz))),
        ("quotation mark",
         ganz.count(ANFUEHRUNG["gerade"]),
         sum(ganz.count(z) for z in ANFUEHRUNG["typografisch"])),
    ]
    for name, gerade, typo in paare:
        if gerade and typo:
            raus.append(f"{rel}  typography  mixed {name}s in one document: "
                        f"{gerade} straight, {typo} typographic - pick one")
    return raus


def pruefe_woerter(rel: str, stuecke, listen: dict[str, set[str]]) -> tuple[dict, dict[str, int]]:
    """Unknown words, grouped. A word repeated forty times is one decision, not
    forty findings - a list nobody can read through is a gate nobody uses."""
    unbekannt: dict[tuple[str, str], dict] = {}
    gesehen: dict[str, int] = defaultdict(int)
    for zeile, lang, text in stuecke:
        bekannt = listen.get(lang, set()) | listen["gemeinsam"]
        for wort, _ in worte(text):
            gesehen[f"{lang}\t{wort.lower()}"] += 1
            if wort.lower() in bekannt:
                continue
            schluessel = (lang, wort.lower())
            eintrag = unbekannt.setdefault(
                schluessel, dict(wort=wort, anzahl=0, orte=[], zeile=zeile))
            eintrag["anzahl"] += 1
            if rel not in eintrag["orte"]:
                eintrag["orte"].append(rel)
    return unbekannt, gesehen


ZAHL = re.compile(r"[\d][\d.,]*")


def _zahl(roh: str) -> float | None:
    s = roh.strip().rstrip(".,")
    # 2,600 and 2.600 are both two thousand six hundred; 3.12 is a version.
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def pruefe_fakten(alle: dict[str, list]) -> list[str]:
    raus: list[str] = []
    for fakt in FAKTEN:
        werte: dict[float, list[str]] = defaultdict(list)
        for rel, stuecke in alle.items():
            ganz = re.sub(r"\s+", " ", "".join(t for _, _, t in stuecke))
            for rx in fakt["muster"]:
                for t in re.finditer(rx, ganz, re.IGNORECASE):
                    wert = _zahl(t.group(1))
                    if wert is not None:
                        werte[wert].append(f"{rel}: “{t.group(0).strip()}”")
            for rx in fakt["wortmuster"]:
                for t in re.finditer(rx, ganz, re.IGNORECASE):
                    wert = fakt["woerter"].get(t.group(1).lower())
                    if wert is not None:
                        werte[float(wert)].append(f"{rel}: “{t.group(0).strip()}”")
        grenze = fakt.get("mindestens")
        if grenze:
            werte = {w: o for w, o in werte.items() if w >= grenze}
        erlaubt = fakt.get("erlaubt")
        if erlaubt and set(werte) <= {float(w) for w in erlaubt}:
            continue        # every value found is a declared, argued one
        if len(werte) > 1:
            raus.append(f"figures  '{fakt['name']}' is stated with {len(werte)} different values:")
            for wert, orte in sorted(werte.items()):
                # The rarer value is the interesting one, so show it in full and
                # cut the majority short - a wall of identical places hides it.
                zeigen = orte[:4]
                rest = f"  (+{len(orte) - 4} more)" if len(orte) > 4 else ""
                raus.append(f"           {wert:g}  <-  " + " | ".join(zeigen) + rest)
        elif werte and fakt["kanon"] is not None:
            (wert,) = werte
            if wert != fakt["kanon"]:
                raus.append(f"figures  '{fakt['name']}' says {wert:g}, measured truth is {fakt['kanon']:g}")
    return raus


# --------------------------------------------------------------------------
# assembling the targets
# --------------------------------------------------------------------------

def ziele(extra: list[str]) -> dict[str, list]:
    alle: dict[str, list] = {}
    if not DIST.exists():
        print("dist/ is missing - run python bake.py first.", file=sys.stderr)
        raise SystemExit(2)
    for p in sorted(DIST.rglob("*.html")):
        if "karte" in p.relative_to(DIST).parts:
            continue    # byte-identical copy of the public system map, never edited here
        alle["dist/" + p.relative_to(DIST).as_posix()] = html_text(p)
    llms = DIST / "llms.txt"
    if llms.exists():
        alle["dist/llms.txt"] = [(n, "en", z + "\n") for n, z in
                                 enumerate(llms.read_text(encoding="utf-8").splitlines(), 1)]
    for name in ("README.md",):
        if (ROOT / name).exists():
            alle[name] = md_text(ROOT / name)
    for roh in extra:
        p = Path(roh)
        if not p.exists():
            print(f"extra target not found: {roh}", file=sys.stderr)
            raise SystemExit(2)
        alle[p.name if p.name != "README.md" else f"{p.parent.name}/README.md"] = (
            md_text(p) if p.suffix == ".md" else html_text(p)
        )
    return alle


def main(argv: list[str]) -> int:
    modus = "pruefen"
    extra: list[str] = []
    for arg in argv:
        if arg == "--woerter":
            modus = "woerter"
        elif arg == "--unbekannt":
            modus = "unbekannt"
        elif arg.startswith("--"):
            print(__doc__)
            return 2
        else:
            extra.append(arg)

    listen = {
        "en": liste_laden("woerter_en.txt"),
        "de": liste_laden("woerter_de.txt"),
        "gemeinsam": liste_laden("woerter_gemeinsam.txt"),
    }
    alle = ziele(extra)

    if modus in {"woerter", "unbekannt"}:
        gesehen: dict[str, int] = defaultdict(int)
        for rel, stuecke in alle.items():
            _, teil = pruefe_woerter(rel, stuecke, listen)
            for k, v in teil.items():
                gesehen[k] += v
        for schluessel in sorted(gesehen):
            lang, wort = schluessel.split("\t")
            if modus == "unbekannt" and wort in (listen.get(lang, set()) | listen["gemeinsam"]):
                continue
            print(f"{lang}\t{gesehen[schluessel]}\t{wort}")
        return 0

    muster_f: list[str] = []
    sammel: dict[tuple[str, str], dict] = {}
    for rel, stuecke in sorted(alle.items()):
        muster_f += pruefe_muster(rel, stuecke)
        muster_f += pruefe_typografie(rel, stuecke)
        teil, _ = pruefe_woerter(rel, stuecke, listen)
        for schluessel, eintrag in teil.items():
            treffer = sammel.setdefault(schluessel, dict(eintrag, orte=list(eintrag["orte"])))
            if treffer is not eintrag:
                treffer["anzahl"] += eintrag["anzahl"]
                for ort in eintrag["orte"]:
                    if ort not in treffer["orte"]:
                        treffer["orte"].append(ort)

    wort_f = []
    for (lang, _klein), eintrag in sorted(sammel.items(), key=lambda kv: (-kv[1]["anzahl"], kv[0])):
        ort = eintrag["orte"][0]
        wo = herkunft(eintrag["wort"], ort)
        weitere = f" +{len(eintrag['orte']) - 1} more" if len(eintrag["orte"]) > 1 else ""
        wort_f.append(f"[{lang}] {eintrag['wort']}   {eintrag['anzahl']}x   "
                      f"{ort}{weitere}   (fix in {wo})")
    fakten_f = pruefe_fakten(alle) + pruefe_app_zahlen(alle)
    anlage_f = pruefe_anlage(alle)

    print(f"proofread over {len(alle)} published texts\n")
    for titel, befunde in (("PATTERNS", muster_f), ("DICTIONARY", wort_f),
                           ("FIGURES", fakten_f), ("SECURITIES LINE", anlage_f)):
        print(f"{titel}: {len(befunde)} finding(s)")
        for f in befunde:
            print(f"  {f}")
        print()

    gesamt = len(muster_f) + len(wort_f) + len(fakten_f) + len(anlage_f)
    if not listen["en"] and not listen["de"]:
        print("NOTE: no word lists yet - the dictionary layer is inert.\n"
              "      Build them with --woerter, validate every entry, then re-run.")
    if gesamt:
        print(f"{gesamt} finding(s). Do not push.", file=sys.stderr)
        return 1
    print("proofread clean - 0 findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
