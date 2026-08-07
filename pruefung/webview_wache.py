#!/usr/bin/env python3
"""webview_wache.py - the in-app browser watch. Runs on every bake.

On 08.08.2026 this site was opened from Instagram and it froze on the first
link tap. Nothing was broken in it: `@view-transition{navigation:auto}` asked
the browser to snapshot the old page and blend it into the new one, and inside
an in-app WebView that snapshot path is where the engine stops. The old frame
stayed up, the new page never painted, and the reader saw a dead site. One
declaration, removed in 05f3ce6, and it took a human thumb on a phone to find
it - because every other gate here was green the whole time.

This is the machine that notices the next one. It is aimed at the browsers
this site cannot choose and cannot test: the WebViews inside Instagram,
Facebook, TikTok, LinkedIn and every messenger that opens a link in-app. They
are Chromium and Safari engines with pieces missing, embedded in an app that
draws its own bars over the page, and they are how most people arriving from a
post will ever see this site.

Eight classes, each one a way a page can hang, hide itself or go dead under a
tap - and each one invisible to a desktop browser, which is what makes a watch
necessary rather than a habit:

  W1  @view-transition        the freeze that started this. Cross-document
                              transitions snapshot the outgoing page; the
                              WebView never paints the incoming one.
  W2  scroll-behavior:smooth  a smooth scroll is an animation the page owes
                              the reader. Older WebViews run it on the main
                              thread, and a long anchor jump crawls or stalls.
                              Behind prefers-reduced-motion:no-preference it is
                              allowed, because there the reader has asked.
  W3  target=_blank           a new WebView window with an opener handle. The
                              in-app browser has no tab strip and often no way
                              back, so the reader is stranded in a window that
                              still holds a reference to the page it came from.
                              rel="noopener" cuts the handle.
  W4  javascript: URLs        this site ships no script and its CSP says
                              script-src 'none'. Such a link is silently
                              refused - a tap that answers with nothing, which
                              a reader reads as "the site hangs".
  W5  <script>                the no-JavaScript promise, in machine form.
                              application/ld+json is data, not code, and is the
                              only type allowed. pruefen.py holds this line over
                              dist/; this holds it over seiten/ and vorlagen/
                              too, so a script is caught before it is baked.
  W6  position:fixed          Instagram draws its own header and footer over
                              the page and moves them while scrolling. Anything
                              the page pins to a viewport edge lands under them:
                              covered content, or a tap target that cannot be
                              reached. Accepted only where the same rule sets
                              display:none, i.e. is off until switched on.
  W7  100vh / 100dvh          the same bars, measured wrong. In-app browsers
                              report a viewport height that excludes their own
                              chrome, or fail to update it when the chrome
                              moves; a 100vh block is then taller than the space
                              the reader has, and whatever sits at its bottom
                              edge is unreachable. 100svh or a percentage is the
                              form that survives.
  W8  meta refresh            WebViews disagree about http-equiv="refresh":
                              some honour it, some ignore it, some ignore it
                              only when the page is not in the foreground. A
                              page that waits for a redirect that never fires
                              looks exactly like a page that hung.

statisch/karte/ and dist/karte/ are NOT checked. The system map is a mirror of
another repository, it is never edited here, and it brings its own JavaScript -
judging it by these rules would report faults nobody in this repository may
fix. Every narrow screen is sent to seiten/mini-karte.html instead, and that
one is checked like any other page.

    python pruefung/webview_wache.py          exit 0 clean, 1 findings, 2 nothing checked
    python pruefung/webview_wache.py <root>   check a copy of the tree instead -
                                              this is how the red proof is run:
                                              plant the bait in a copy, watch it
                                              fire, throw the copy away.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent


class Quelle(NamedTuple):
    name: str          # repo-relative, posix, e.g. "statisch/stil.css"
    text: str
    art: str           # "css" or "html"


class Fund(NamedTuple):
    wo: str            # "statisch/stil.css:430"
    was: str


class Punkt(NamedTuple):
    kuerzel: str       # "W1"
    titel: str
    funde: list[Fund]
    zaehler: str       # what was counted, printed green or red alike


# --------------------------------------------------------------------------
# reading text without reading its comments
# --------------------------------------------------------------------------
# A comment is where a fault is explained, and stil.css explains this exact
# fault by quoting it: the note at the foot of the stylesheet spells out
# `@view-transition{navigation:auto}` so the next reader knows what was removed
# and why. A watch that matched raw text would fire on that note forever, and a
# gate that is red while the tree is correct gets switched off within a week.
#
# So comments are blanked before matching - every character replaced by a
# space, newlines kept - which keeps every line number true while making the
# commented text invisible to every pattern below. The mentions inside comments
# are counted separately and printed on the W1 line, so the exclusion is
# visible in the output rather than assumed: if that counter ever drops to
# zero, the note was deleted, and the reason the declaration is forbidden went
# with it.

def ohne_kommentare(text: str, art: str) -> str:
    muster = r"/\*.*?\*/" if art == "css" else r"<!--.*?-->"
    return re.sub(muster, lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=re.S)


def zeile(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def bloecke(text: str) -> list[tuple[int, int, str]]:
    """Every brace block in a stylesheet as (content start, content end, prelude).

    Enough of a parser for what the rules below need: which @media conditions a
    declaration stands under, and what else its own rule declares. Deliberately
    not a CSS parser - it is fed comment-free text and asked two narrow
    questions."""
    offen: list[tuple[str, int]] = []
    fertig: list[tuple[int, int, str]] = []
    zuletzt = 0
    for m in re.finditer(r"[{};]", text):
        if m.group() == "{":
            offen.append((text[zuletzt:m.start()].strip(), m.end()))
        elif m.group() == "}" and offen:
            prelude, start = offen.pop()
            fertig.append((start, m.start(), prelude))
        zuletzt = m.end()
    return fertig


def umgebung(text: str, offset: int) -> tuple[list[str], str]:
    """(the preludes enclosing that offset, the innermost block's own text)"""
    treffer = [b for b in bloecke(text) if b[0] <= offset < b[1]]
    if not treffer:
        return [], ""
    innen = max(treffer, key=lambda b: b[0])
    return [b[2] for b in treffer], text[innen[0]:innen[1]]


# --------------------------------------------------------------------------
# the markup side
# --------------------------------------------------------------------------
# HTMLParser rather than a regex over "<a ...>", for one reason that matters
# here: it does not see inside comments. Markup that has been commented out is
# not markup, and a watch that fired on it would push the next author into
# deleting the commented example instead of the live tag.
#
# The fragments in seiten/ have no <html> of their own; the parser handles a
# fragment exactly as well as a document, so sources and baked pages go through
# the same reading.

URL_ATTRS = ("href", "src", "action", "formaction", "data", "poster")


class Seite(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anker: list[tuple[int, dict]] = []
        self.skripte: list[tuple[int, str]] = []
        self.refresh: list[tuple[int, str]] = []
        self.js_urls: list[tuple[int, str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}
        n = self.getpos()[0]
        if tag == "a":
            self.anker.append((n, a))
        if tag == "script":
            self.skripte.append((n, a.get("type", "text/javascript")))
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.refresh.append((n, a.get("content", "")))
        for attr in URL_ATTRS:
            wert = a.get(attr, "")
            # control characters and whitespace are stripped by the URL parser
            # before the scheme is read, so "java\tscript:" is the same link
            if re.sub(r"[\s\x00-\x1f]", "", wert).lower().startswith("javascript:"):
                self.js_urls.append((n, tag, attr, wert.strip()))


def markup(quellen: list[Quelle]) -> list[tuple[Quelle, Seite]]:
    out = []
    for q in quellen:
        if q.art != "html":
            continue
        p = Seite()
        p.feed(q.text)
        p.close()
        out.append((q, p))
    return out


# --------------------------------------------------------------------------
# the eight checks
# --------------------------------------------------------------------------

def w1_view_transition(quellen: list[Quelle]) -> Punkt:
    funde, im_kommentar = [], []
    for q in quellen:
        sauber = ohne_kommentare(q.text, q.art)
        for m in re.finditer(r"@view-transition\b", sauber, re.I):
            funde.append(Fund(f"{q.name}:{zeile(q.text, m.start())}",
                              "@view-transition is a real rule here - a link tap "
                              "inside an in-app WebView freezes on it"))
        # the same word in the raw text, at a span the blanking emptied: that
        # is a mention inside a comment, and this is where it is accounted for
        for m in re.finditer(r"@view-transition\b", q.text, re.I):
            if not sauber[m.start():m.end()].strip():
                im_kommentar.append(f"{q.name}:{zeile(q.text, m.start())}")
    zaehler = f"{len(funde)} rule(s)"
    if im_kommentar:
        zaehler += (f"; {len(im_kommentar)} mention(s) inside a comment, "
                    f"not counted ({', '.join(im_kommentar)})")
    return Punkt("W1", "cross-document view transitions", funde, zaehler)


def w2_smooth(quellen: list[Quelle]) -> Punkt:
    funde, geschuetzt = [], 0
    for q in quellen:
        if q.art != "css":
            continue
        sauber = ohne_kommentare(q.text, q.art)
        for m in re.finditer(r"scroll-behavior\s*:\s*smooth", sauber, re.I):
            preludes, _ = umgebung(sauber, m.start())
            if any("prefers-reduced-motion" in p for p in preludes):
                geschuetzt += 1
                continue
            funde.append(Fund(f"{q.name}:{zeile(q.text, m.start())}",
                              "scroll-behavior:smooth with no motion guard - put it "
                              "inside @media (prefers-reduced-motion:no-preference)"))
    return Punkt("W2", "smooth scrolling with no motion guard", funde,
                 f"{len(funde) + geschuetzt} declaration(s), {geschuetzt} guarded")


def w3_blank(seiten: list[tuple[Quelle, Seite]]) -> Punkt:
    funde, gesamt = [], 0
    for q, p in seiten:
        for n, a in p.anker:
            if "target" not in a:
                continue
            gesamt += 1
            if a["target"].strip().lower() != "_blank":
                continue
            if "noopener" not in a.get("rel", "").lower():
                funde.append(Fund(f"{q.name}:{n}",
                                  f'target="_blank" to {a.get("href", "?")} without '
                                  'rel="noopener"'))
    return Punkt("W3", 'target="_blank" without rel="noopener"', funde,
                 f"{gesamt} target attribute(s) on the whole site")


def w4_js_url(seiten: list[tuple[Quelle, Seite]]) -> Punkt:
    funde = []
    for q, p in seiten:
        for n, tag, attr, wert in p.js_urls:
            funde.append(Fund(f"{q.name}:{n}",
                              f"<{tag} {attr}=\"{wert[:40]}\"> - the CSP refuses it "
                              "silently, so the tap answers with nothing"))
    return Punkt("W4", "javascript: URLs", funde, f"{len(funde)} such URL(s)")


def w5_script(seiten: list[tuple[Quelle, Seite]]) -> Punkt:
    funde, ld_json = [], 0
    for q, p in seiten:
        for n, typ in p.skripte:
            if typ.strip().lower() == "application/ld+json":
                ld_json += 1
                continue
            funde.append(Fund(f"{q.name}:{n}",
                              f"<script type={typ!r}> - this site ships no code; "
                              "application/ld+json is the only type allowed"))
    return Punkt("W5", "script elements outside JSON-LD", funde,
                 f"{len(funde)} executable, {ld_json} JSON-LD data block(s)")


def w6_fixed(quellen: list[Quelle]) -> Punkt:
    funde, aus = [], []
    for q in quellen:
        if q.art != "css":
            continue
        sauber = ohne_kommentare(q.text, q.art)
        for m in re.finditer(r"position\s*:\s*fixed", sauber, re.I):
            _, block = umgebung(sauber, m.start())
            ort = f"{q.name}:{zeile(q.text, m.start())}"
            if re.search(r"display\s*:\s*none", block, re.I):
                # off until something switches it on: it cannot cover anything
                # in the state a page loads in. Listed, never silent - see the
                # limits section of the README.
                aus.append(ort)
                continue
            funde.append(Fund(ort, "position:fixed and visible by default - the "
                               "in-app browser draws its own bars over exactly "
                               "that strip"))
    zaehler = f"{len(funde)} visible by default"
    if aus:
        zaehler += f", {len(aus)} hidden by default ({', '.join(aus)})"
    return Punkt("W6", "viewport-fixed elements", funde, zaehler)


def w7_vh(quellen: list[Quelle]) -> Punkt:
    funde = []
    for q in quellen:
        sauber = ohne_kommentare(q.text, q.art)
        for m in re.finditer(r"\b100(vh|dvh)\b", sauber, re.I):
            funde.append(Fund(f"{q.name}:{zeile(q.text, m.start())}",
                              f"100{m.group(1)} - the in-app browser's own bars are "
                              "not in that number; use 100svh or a percentage"))
    return Punkt("W7", "the 100vh / 100dvh viewport trap", funde,
                 f"{len(funde)} viewport-height unit(s)")


def w8_refresh(seiten: list[tuple[Quelle, Seite]]) -> Punkt:
    funde = []
    for q, p in seiten:
        for n, inhalt in p.refresh:
            funde.append(Fund(f"{q.name}:{n}",
                              f'<meta http-equiv="refresh" content="{inhalt}"> - '
                              "WebViews disagree about it; a redirect that never "
                              "fires reads as a hang"))
    return Punkt("W8", "meta refresh redirects", funde, f"{len(funde)} redirect(s)")


def pruefe(quellen: list[Quelle]) -> list[Punkt]:
    seiten = markup(quellen)
    return [w1_view_transition(quellen), w2_smooth(quellen), w3_blank(seiten),
            w4_js_url(seiten), w5_script(seiten), w6_fixed(quellen),
            w7_vh(quellen), w8_refresh(seiten)]


# --------------------------------------------------------------------------
# what is read
# --------------------------------------------------------------------------

def art(rel: str) -> str:
    return {".html": "html", ".css": "css"}.get(Path(rel).suffix.lower(), "")


def ohne_karte(rel: str) -> bool:
    return "karte" not in Path(rel).parts


def sammeln(wurzel: Path, mit_dist: bool = True) -> list[Quelle]:
    quellen: list[Quelle] = []
    for pfad in sorted((wurzel / "seiten").glob("*.html")):
        quellen.append(Quelle(f"seiten/{pfad.name}",
                              pfad.read_text(encoding="utf-8"), "html"))
    for pfad in sorted((wurzel / "vorlagen").glob("*.html")):
        quellen.append(Quelle(f"vorlagen/{pfad.name}",
                              pfad.read_text(encoding="utf-8"), "html"))
    css = wurzel / "statisch" / "stil.css"
    if css.exists():
        quellen.append(Quelle("statisch/stil.css",
                              css.read_text(encoding="utf-8"), "css"))
    if mit_dist and (wurzel / "dist").is_dir():
        for pfad in sorted((wurzel / "dist").rglob("*")):
            rel = pfad.relative_to(wurzel / "dist").as_posix()
            if pfad.is_file() and art(rel) and ohne_karte(rel):
                quellen.append(Quelle(f"dist/{rel}",
                                      pfad.read_text(encoding="utf-8"), art(rel)))
    return quellen


def faults_fuer_bake(wurzel: Path, tree: dict[str, bytes]) -> list[str]:
    """What bake.py calls on every run: the sources on disk plus the pages it
    has just built in memory, judged before a single byte reaches dist/. The
    baked pages are the ones a reader gets, and the fragments are where the
    author works - both, because a fault caught in dist/ has already been
    written, and a fault that only exists in bake.py's own templates would
    never show up in seiten/."""
    quellen = sammeln(wurzel, mit_dist=False)
    for rel in sorted(tree):
        if art(rel) and ohne_karte(rel):
            quellen.append(Quelle(f"dist/{rel}",
                                  tree[rel].decode("utf-8"), art(rel)))
    return [f"{p.kuerzel} {f.wo}: {f.was}" for p in pruefe(quellen) for f in p.funde]


# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    wurzel = Path(argv[0]).resolve() if argv else ROOT
    if not (wurzel / "seiten").is_dir() or not (wurzel / "statisch" / "stil.css").exists():
        print(f"ABORT: {wurzel} is not a copy of this site - nothing was checked.",
              file=sys.stderr)
        return 2

    quellen = sammeln(wurzel)
    # A watch that reads no files reports exactly what a clean tree reports.
    if len(quellen) < 10:
        print(f"ABORT: only {len(quellen)} file(s) found under {wurzel} - "
              "nothing was checked.", file=sys.stderr)
        return 2

    q_src = sum(1 for q in quellen if not q.name.startswith("dist/"))
    print(f"webview watch - {len(quellen)} files ({q_src} sources, "
          f"{len(quellen) - q_src} baked), statisch/karte/ and dist/karte/ excluded\n")

    punkte = pruefe(quellen)
    schlecht = 0
    for p in punkte:
        mark = "ok  " if not p.funde else "FAIL"
        print(f"{p.kuerzel}  {mark}  {p.titel:<42}{p.zaehler}")
        for f in p.funde:
            print(f"          - {f.wo}: {f.was}")
        schlecht += 1 if p.funde else 0
    print()
    if schlecht:
        gesamt = sum(len(p.funde) for p in punkte)
        print(f"{gesamt} finding(s) across {schlecht} of {len(punkte)} checks.",
              file=sys.stderr)
        return 1
    print(f"all {len(punkte)} checks green over {len(quellen)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
