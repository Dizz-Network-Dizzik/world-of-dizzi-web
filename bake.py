#!/usr/bin/env python3
"""bake.py - the whole build system for "the world of dizzi".

Standard library only. No node, no npm, no cloud build. It takes the two
templates in vorlagen/ plus the content fragments in seiten/, glues them
together, copies statisch/ verbatim and writes everything into dist/.
dist/ is committed; Netlify publishes it as-is.

    python bake.py            build dist/
    python bake.py --check    verify only: dist/ matches a fresh bake,
                              no dead internal links, no dead anchors,
                              no external subresource. Exit != 0 on any fault.

Every run, in both modes, also resolves each source link against the code
snapshot in snapshot/ and checks the two figures the README states about the
built site - its first load in bytes and how many source links there are -
against the files actually produced. A number nobody measures goes stale
without anybody noticing; both of these already did once.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VORLAGEN = ROOT / "vorlagen"
SEITEN_DIR = ROOT / "seiten"
STATISCH = ROOT / "statisch"
DIST = ROOT / "dist"

# The public origin. One place to change when the custom domain arrives:
# canonical URLs, og:url, sitemap.xml, robots.txt and llms.txt all read it.
HOST = "https://worldofdizzi.netlify.app"
# This site's own repository. The footer of every page quotes the length of the
# file below, and /numbers/ states that exactly one figure on this site cannot
# be checked from outside. That sentence is only true while the file behind the
# build figure is reachable - so the site links itself, and this is where.
SELBST = "https://github.com/Dizz-Network-Dizzik/world-of-dizzi-web"

# The code the site talks about used to sit in a second, separate repository.
# It now sits in THIS one, under the folder below: one public repository, not
# two. Every source link is built from the two values below and nothing else,
# so moving or renaming the folder is one line here plus a rebake, never a hunt
# through the pages. Two counts, because they measure different things and the
# difference is not a discrepancy: 54 link sites in seiten/ and vorlagen/ - what
# an author edits - render as 67 links in dist/, since the footer link repeats
# on all twelve pages and llms.txt and the JSON-LD block carry one each.
# check_snapshot_links() resolves all 67 against the folder on every bake.
AUSZUG = "snapshot"
DATEI = f"{SELBST}/blob/main/{AUSZUG}"   # a file inside the extract
ORDNER = f"{SELBST}/tree/main/{AUSZUG}"  # a directory inside the extract

# The footer of every page quotes the length of this file, and /numbers/ quotes
# it twice. That figure was wrong once already - the footer said "100-line"
# while the file had 530 - and it went wrong again the moment this file grew by
# nine lines. A number that describes the builder is therefore measured BY the
# builder, at build time, and never typed anywhere. Editing this file now
# changes the pages, which makes `bake.py --check` fail until they are rebaked.
_EIGENE_ZEILEN = Path(__file__).read_text(encoding="utf-8").splitlines()
BAKER_ZEILEN = len(_EIGENE_ZEILEN)
BAKER_CODE = sum(1 for z in _EIGENE_ZEILEN if z.strip())

OG_ALT = (
    "the world of dizzi — dark title card with the numbers "
    "10 applications, 2,600+ commits, ~100,000 lines of Python, 2,667 tests"
)

# --------------------------------------------------------------------------
# pages: source fragment -> output path
# --------------------------------------------------------------------------
# flags:  noindex  - <meta name="robots" content="noindex">, keeps a page out
#                    of search results while staying reachable (legal pages)
#         nomap    - not listed in sitemap.xml
#         alt      - path of the other-language twin (emits the hreflang pair)
#         jsonld   - key into JSONLD below

PAGES: list[dict] = [
    dict(
        src="index.html", out="index.html", path="/", lang="en",
        title="the world of dizzi — one person, ten applications",
        desc="A personal, local-first AI network: ten applications, one shared "
             "contract, built by one person with AI coding assistants. "
             "Documents public, code private.",
        alt="/de/", jsonld="start",
    ),
    dict(
        src="system.html", out="system/index.html", path="/system/", lang="en",
        title="Architecture & the app contract | the world of dizzi",
        desc="How ten applications behave like one: a headless core on :8200, "
             "the App Contract, the shared appkit library and read-only "
             "cross-connections.",
    ),
    dict(
        src="apps.html", out="apps/index.html", path="/apps/", lang="en",
        title="The ten applications | the world of dizzi",
        desc="Core, money, communication, creating, memory, management, news, "
             "health, admin and a trading fleet — each on its own port, each "
             "with a source link.",
    ),
    dict(
        src="numbers.html", out="numbers/index.html", path="/numbers/", lang="en",
        title="How the numbers were counted | the world of dizzi",
        desc="The six figures this site leads with — how each was counted, when it was "
             "measured, and which one cannot be checked from outside.",
    ),
    dict(
        src="method.html", out="method/index.html", path="/method/", lang="en",
        title="The method — how this gets built | the world of dizzi",
        desc="Written law before code, contracts before features, research "
             "before decisions, an orchestra of AI build chats and human gates "
             "on everything irreversible.",
    ),
    dict(
        src="journey.html", out="journey/index.html", path="/journey/", lang="en",
        title="Journey — dated milestones | the world of dizzi",
        desc="From the first trading validation nights in June 2026 to the "
             "public extract of 23 July and its curation down to documents on "
             "6 August — every node dated.",
    ),
    dict(
        src="vision.html", out="vision/index.html", path="/vision/", lang="en",
        title="From project to company | the world of dizzi",
        desc="Where the project stands, why the contract architecture scales, "
             "and what I am opening: early conversations with partners and "
             "investors.",
    ),
    dict(
        src="about.html", out="about/index.html", path="/about/", lang="en",
        title="About & contact | the world of dizzi",
        desc="Who builds the world of dizzi, and how to get in touch.",
    ),
    dict(
        src="de.html", out="de/index.html", path="/de/", lang="de",
        title="the world of dizzi — ein Mensch, zehn Anwendungen",
        # 155 characters is the limit pruefen.py enforces; the version pushed on
        # 27.07. ran to 209 and the gate was red on main until this shortening.
        # Same claim, nothing dropped that "neun ... der Kern" does not imply.
        desc="Ein persönliches, lokal-first KI-Netzwerk: neun Anwendungen sprechen "
             "einen gemeinsamen Vertrag, der Kern sammelt ihn ein. Die Dokumente "
             "sind öffentlich.",
        alt="/",
    ),
    dict(
        src="impressum.html", out="impressum/index.html", path="/impressum/",
        lang="de", title="Impressum | the world of dizzi",
        desc="Anbieterkennzeichnung nach § 5 DDG.",
        noindex=True, nomap=True,
    ),
    dict(
        src="datenschutz.html", out="datenschutz/index.html", path="/datenschutz/",
        lang="de", title="Datenschutzerklärung | the world of dizzi",
        desc="Welche Daten beim Besuch dieser Website anfallen – und welche nicht.",
        noindex=True, nomap=True,
    ),
    dict(
        src="404.html", out="404.html", path="/404.html", lang="en",
        title="404 — not in the registry | the world of dizzi",
        desc="This panel is not in the registry.",
        noindex=True, nomap=True,
    ),
]

# --------------------------------------------------------------------------
# chrome: everything the two templates need, per language
# --------------------------------------------------------------------------

NAV = [
    ("/system/", "System", "System"),
    ("/apps/", "Apps", "Apps"),
    ("/method/", "Method", "Methode"),
    ("/numbers/", "Numbers", "Zahlen"),
    ("/journey/", "Journey", "Chronik"),
    ("/vision/", "Vision", "Vision"),
    ("/about/", "About", "Kontakt"),
]

T = {
    "en": dict(
        SKIP="Skip to content",
        NAVLABEL="Main",
        MENU="Menu",
        MAP="System map",
        LANGLINK='<a class="nav-lang" href="/de/" lang="de" hreflang="de">Deutsch</a>',
        SOURCE="Documents",
        FOOT_CLAIM="Documents public, code private. All rights reserved.",
        FOOT_STATUS="Independent project — incorporation ahead.",
        FOOT_LEGALLABEL="Legal",
        IMPRESSUM="Impressum",
        DATENSCHUTZ="Privacy",
        FOOT_BUILT=f'Built with a <a href="/numbers/#baecker">{BAKER_ZEILEN}-line '
                   "Python baker</a>. No cookies, no trackers, no external requests.",
    ),
    "de": dict(
        SKIP="Zum Inhalt springen",
        NAVLABEL="Haupt",
        MENU="Menü",
        MAP="System-Karte",
        LANGLINK='<a class="nav-lang" href="/" lang="en" hreflang="en">English</a>',
        SOURCE="Dokumente",
        FOOT_CLAIM="Dokumente öffentlich, Code privat. Alle Rechte "
                   "vorbehalten.",
        FOOT_STATUS="Unabhängiges Projekt — Gründung in Vorbereitung.",
        FOOT_LEGALLABEL="Rechtliches",
        IMPRESSUM="Impressum",
        DATENSCHUTZ="Datenschutz",
        FOOT_BUILT=f'Gebacken von einem <a href="/numbers/#baecker">{BAKER_ZEILEN}-'
                   "Zeilen-Python-Skript</a>. Keine Cookies, keine Tracker, keine "
                   "externen Aufrufe.",
    ),
}

JSONLD = {
    "start": """{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": "%(host)s/#website",
      "url": "%(host)s/",
      "name": "the world of dizzi",
      "inLanguage": "en",
      "description": "A personal, local-first AI network: ten applications, one shared architecture.",
      "publisher": { "@id": "%(host)s/#person" }
    },
    {
      "@type": "Person",
      "@id": "%(host)s/#person",
      "name": "David",
      "url": "%(host)s/about/",
      "jobTitle": "Builder",
      "sameAs": [ "https://github.com/Dizz-Network-Dizzik" ]
    },
    {
      "@type": "SoftwareSourceCode",
      "name": "the world of dizzi",
      "description": "Ten local-first applications around a headless core, joined by one written app contract. A curated set of documents is published; the code is not.",
      "codeRepository": "%(repo)s",
      "programmingLanguage": "Python",
      "runtimePlatform": "Python 3.12",
      "author": { "@id": "%(host)s/#person" },
      "url": "%(host)s/system/"
    }
  ]
}""",
}


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def fill(tpl: str, values: dict) -> str:
    out = tpl
    for key, val in values.items():
        out = out.replace("{{%s}}" % key, val)
    return out


def nav_html(page: dict) -> str:
    lang = page["lang"]
    idx = 2 if lang == "de" else 1
    items = []
    for path, en, de in NAV:
        label = de if lang == "de" else en
        cur = ' aria-current="page"' if path == page["path"] else ""
        items.append(f'<li><a href="{path}"{cur}>{label}</a></li>')
    items.append(
        f'<li><a class="nav-karte" href="/karte/">{T[lang]["MAP"]}</a></li>'
    )
    _ = idx, en, de
    return "\n        ".join(items)


def head_extras(page: dict) -> dict:
    robots = ""
    if page.get("noindex"):
        robots = '<meta name="robots" content="noindex, follow">\n  '

    hreflang = ""
    if page.get("alt"):
        pairs = [(page["path"], page["lang"]), (page["alt"],
                 "de" if page["lang"] == "en" else "en")]
        lines = [
            f'<link rel="alternate" hreflang="{lg}" href="{HOST}{pt}">'
            for pt, lg in pairs
        ]
        lines.append(f'<link rel="alternate" hreflang="x-default" href="{HOST}/">')
        hreflang = "\n  ".join(lines) + "\n  "

    ld = ""
    if page.get("jsonld"):
        body = JSONLD[page["jsonld"]] % dict(host=HOST, repo=ORDNER)
        ld = '<script type="application/ld+json">%s</script>\n  ' % body

    return dict(ROBOTS=robots, HREFLANG=hreflang, JSONLD=ld)


def build() -> dict[str, bytes]:
    kopf = read(VORLAGEN / "kopf.html")
    fuss = read(VORLAGEN / "fuss.html")
    tree: dict[str, bytes] = {}

    for page in PAGES:
        lang = page["lang"]
        values = dict(T[lang])
        values.update(
            LANG=lang,
            TITLE=html.escape(page["title"], quote=True),
            DESC=html.escape(page["desc"], quote=True),
            PATH=page["path"],
            HOST=HOST,
            DATEI=DATEI,
            ORDNER=ORDNER,
            OGLOCALE="de_DE" if lang == "de" else "en_GB",
            OGALT=html.escape(OG_ALT, quote=True),
            NAV=nav_html(page),
            YEAR="2026",
            BAKERZEILEN=str(BAKER_ZEILEN),
            BAKERCODE=str(BAKER_CODE),
            SELBST=SELBST,
        )
        values.update(head_extras(page))
        body = read(SEITEN_DIR / page["src"])
        doc = fill(kopf + body + fuss, values)
        # collapse the blank lines the optional head blocks leave behind
        doc = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", doc)
        left = re.findall(r"\{\{[A-Z_]+\}\}", doc)
        if left:
            raise SystemExit(
                f"{page['src']}: unknown placeholder(s) {sorted(set(left))}"
            )
        tree[page["out"]] = doc.encode("utf-8")

    for src in sorted(STATISCH.rglob("*")):
        if src.is_file():
            tree[src.relative_to(STATISCH).as_posix()] = src.read_bytes()

    tree["sitemap.xml"] = sitemap().encode("utf-8")
    tree["robots.txt"] = robots().encode("utf-8")
    tree["llms.txt"] = llms().encode("utf-8")
    return tree


def sitemap() -> str:
    rows = []
    for page in PAGES:
        if page.get("nomap"):
            continue
        alt = ""
        if page.get("alt"):
            other = "de" if page["lang"] == "en" else "en"
            alt = (
                f'\n    <xhtml:link rel="alternate" hreflang="{page["lang"]}" '
                f'href="{HOST}{page["path"]}"/>'
                f'\n    <xhtml:link rel="alternate" hreflang="{other}" '
                f'href="{HOST}{page["alt"]}"/>'
            )
        prio = "1.0" if page["path"] == "/" else "0.8"
        rows.append(
            f'  <url>\n    <loc>{HOST}{page["path"]}</loc>{alt}\n'
            f"    <priority>{prio}</priority>\n  </url>"
        )
    rows.append(
        f'  <url>\n    <loc>{HOST}/karte/</loc>\n'
        f"    <priority>0.8</priority>\n  </url>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )


def robots() -> str:
    # Everything is allowed. The two legal pages carry a noindex meta tag
    # instead of a robots rule - a blocked crawler would never see the tag.
    return f"User-agent: *\nAllow: /\n\nSitemap: {HOST}/sitemap.xml\n"


def llms() -> str:
    return f"""# the world of dizzi

> One person, ten local-first applications, one shared architecture - a
> personal AI network. A curated set of documents is public; the code is not.

## Start here
- [The system]({HOST}/system/): architecture, the app contract, shared core library
- [The ten applications]({HOST}/apps/): what each app does, and what is published
- [The method]({HOST}/method/): written laws, contracts, AI build-chat orchestration
- [The numbers]({HOST}/numbers/): the six headline figures, each with its method
- [Journey]({HOST}/journey/): dated milestones since June 2026
- [From project to company]({HOST}/vision/): status, why it scales, what I am opening
- [About & contact]({HOST}/about/): who builds this, and how to reach me

## Source
- [The published documents]({ORDNER}): 38 documents - the network laws and
  contracts plus one README per application. The code extract that stood here
  until 6 August 2026 is no longer published
- [This site's own source]({SELBST}): the build script behind the figure in every footer
- [Interactive system map]({HOST}/karte/): self-contained, no external calls

## Notes
- Status: independent project, pre-incorporation. No revenue yet. Since 4 August
  2026 a small part of the fleet trades with my own money, on my own account; no
  outside capital, no offer to anyone. Public since 23 July 2026; cut back to a
  document set on 6 August 2026.
- The six figures this site leads with are listed at {HOST}/numbers/ with the
  method that produced each one and the date it was measured. Three of them can
  no longer be checked from outside: the commit count is private and stated as a
  floor for that reason, and the two code figures were measured against the
  extract that was withdrawn on 6 August 2026. Each says so in its own entry.
- German entry page: {HOST}/de/
"""


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

HREF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"', re.I)
ID_RE = re.compile(r'\sid\s*=\s*"([^"]+)"')
EXTERNAL_RE = re.compile(r"^(?:https?:)?//", re.I)
SRC_RE = re.compile(
    r'<(?:script|img|source|iframe|embed|video|audio)\b[^>]*?\bsrc\s*=\s*"([^"]*)"',
    re.I,
)
LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
ATTR_RE = re.compile(r'\b(rel|href)\s*=\s*"([^"]*)"', re.I)
# rel values that make the browser fetch something; canonical/alternate do not
FETCHING_REL = {
    "stylesheet", "preload", "prefetch", "modulepreload", "preconnect",
    "dns-prefetch", "icon", "shortcut", "apple-touch-icon", "manifest",
}


def targets(tree: dict[str, bytes]) -> tuple[set[str], dict[str, set[str]]]:
    urls: set[str] = set()
    ids: dict[str, set[str]] = {}
    for rel, data in tree.items():
        url = "/" + rel
        urls.add(url)
        if rel.endswith("index.html"):
            urls.add(url[: -len("index.html")])
        if rel.endswith(".html"):
            ids["/" + rel] = set(ID_RE.findall(data.decode("utf-8")))
    for rel in list(urls):
        if rel.endswith("/index.html"):
            ids.setdefault(rel[: -len("index.html")], ids.get(rel, set()))
    return urls, ids


def check_links(tree: dict[str, bytes]) -> list[str]:
    urls, ids = targets(tree)
    faults: list[str] = []
    for rel, data in sorted(tree.items()):
        if not rel.endswith(".html") or rel.startswith("karte/"):
            continue  # the map is a verbatim copy from the public repo
        text = data.decode("utf-8")
        page_ids = set(ID_RE.findall(text))
        for raw in HREF_RE.findall(text):
            ref = html.unescape(raw)
            if ref.startswith(("mailto:", "tel:", "data:")) or EXTERNAL_RE.match(ref):
                continue
            if ref.startswith("#"):
                if ref[1:] and ref[1:] not in page_ids:
                    faults.append(f"{rel}: dead anchor {ref}")
                continue
            if not ref.startswith("/"):
                faults.append(f"{rel}: relative link {ref!r} (use absolute paths)")
                continue
            path, _, frag = ref.partition("#")
            if path not in urls:
                faults.append(f"{rel}: dead link {path}")
                continue
            if frag:
                known = ids.get(path) or ids.get(path + "index.html") or set()
                if frag not in known:
                    faults.append(f"{rel}: dead anchor {ref}")
    return faults


def check_external(tree: dict[str, bytes]) -> list[str]:
    """No page may pull a subresource from another host. Airplane-mode proof."""
    faults = []
    for rel, data in sorted(tree.items()):
        if not rel.endswith(".html") or rel.startswith("karte/"):
            continue
        text = data.decode("utf-8")
        refs = list(SRC_RE.findall(text))
        for tag in LINK_RE.findall(text):
            attrs = {k.lower(): v for k, v in ATTR_RE.findall(tag)}
            rels = set(attrs.get("rel", "").lower().split())
            if rels & FETCHING_REL:
                refs.append(attrs.get("href", ""))
        for ref in refs:
            if EXTERNAL_RE.match(ref):
                faults.append(f"{rel}: external subresource {ref}")
    return faults


DEPLOY_BLOCKERS = {
    "[IMPRESSUM-DATEN]": "the Impressum still carries the placeholder instead of a "
                         "real, servable address (required by section 5 DDG)",
}


def check_deploy(tree: dict[str, bytes]) -> list[str]:
    """Things that must not be live. They do not block a build or a push."""
    blockers = []
    for rel, data in sorted(tree.items()):
        if not rel.endswith((".html", ".txt", ".xml")):
            continue
        text = data.decode("utf-8", "replace")
        for needle, why in DEPLOY_BLOCKERS.items():
            if needle in text:
                blockers.append(f"{rel}: {why}")
    return blockers


# What a browser fetches for a first visit to the start page: the document, the
# stylesheet, the three fonts it preloads or uses, and the favicon.
ERSTANSICHT = (
    "index.html", "stil.css", "schrift/chakra-400.woff2",
    "schrift/orbitron-var.woff2", "schrift/chakra-600.woff2",
    "bilder/favicon.svg",
)


def md_anker(text: str) -> set[str]:
    """GitHub's heading anchors, reproduced closely enough to be worth trusting:
    lower case, punctuation dropped, EVERY space its own hyphen (two spaces make
    two), repeated headings numbered -1, -2. Fenced blocks are skipped, because
    a '# ' inside a code sample is a comment, not a heading."""
    anker: set[str] = set()
    gezaehlt: dict[str, int] = {}
    fence = False
    for zeile in text.splitlines():
        if zeile.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence or not re.match(r"#{1,6}\s", zeile.lstrip()):
            continue
        slug = re.sub(r"[^\w\s-]", "", zeile.lstrip().lstrip("#").strip().lower())
        slug = re.sub(r"\s", "-", slug)
        n = gezaehlt.get(slug, 0)
        gezaehlt[slug] = n + 1
        anker.add(slug if not n else f"{slug}-{n}")
    return anker


def check_snapshot_links(tree: dict[str, bytes]) -> list[str]:
    """The source links used to point into a second repository, where nothing
    here could follow them: check_links skips external targets by design, so a
    file renamed on the other side left every gate green while the site linked
    into nothing. The extract now sits in AUSZUG/, in this repository, so the
    same links can be resolved - and are, on every build.

    git decides what exists here, not the disk. The disk on a Windows machine
    answers yes to the wrong capitalisation, holds untracked files and knows
    empty folders; GitHub does none of the three. Asking the index instead of
    the filesystem is the difference between checking what will be published
    and checking what happens to lie around."""
    try:
        roh = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, text=True, check=True, encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        # Fail closed. Falling back to the filesystem would restore exactly the
        # blind spot this function exists to remove.
        return [f"cannot ask git what {AUSZUG}/ holds, so the source links "
                f"cannot be checked: {e}"]

    versioniert = {p for p in roh.split("\0") if p}
    dateien = {p[len(AUSZUG) + 1:] for p in versioniert
               if p.startswith(AUSZUG + "/")}
    if not dateien:
        return [f"git tracks nothing under {AUSZUG}/ - every source link would "
                "be a 404 on the remote, however complete the folder looks here"]
    ordner = {""}
    for d in dateien:
        teile = d.split("/")
        for i in range(1, len(teile)):
            ordner.add("/".join(teile[:i]))

    # Every github.com address in the output has to be one we meant to write.
    # Matching only the correct shape would let the likely typos - wrong branch,
    # wrong repository, /raw/ instead of /blob/ - pass by unseen.
    ERLAUBT = {SELBST, "https://github.com/Dizz-Network-Dizzik"}
    ALLE = re.compile(r"https://github\.com/[^\s\"'<>)]+")
    GUT = re.compile(
        re.escape(SELBST) + r"/(blob|tree)/main/" + re.escape(AUSZUG)
        + r"((?:[/#][^\s\"'<>)]*)?)$"
    )
    # The site also links one file of its own - bake.py, behind the footer
    # figure. It costs nothing to hold that to the same standard.
    EIGEN = re.compile(re.escape(SELBST) + r"/blob/main/([^\s\"'<>)#?]+)$")

    faults: list[str] = []
    gesehen = 0
    for rel, data in sorted(tree.items()):
        if not rel.endswith((".html", ".txt")):
            continue
        if rel.startswith("schrift/"):
            continue  # upstream licence texts, copied verbatim, not ours to edit
        for url in ALLE.findall(html.unescape(data.decode("utf-8"))):
            url = url.rstrip(".,;")
            if url in ERLAUBT:
                continue
            treffer = GUT.fullmatch(url)
            if not treffer:
                eigen = EIGEN.fullmatch(url)
                if eigen and not eigen.group(1).startswith(AUSZUG + "/"):
                    if eigen.group(1) not in versioniert:
                        faults.append(f"{rel}: {url} - git tracks no such file "
                                      "in this repository")
                    continue
                faults.append(f"{rel}: {url} - not a link into {AUSZUG}/ and not "
                              "one of this site's own addresses")
                continue
            gesehen += 1
            art, rest = treffer.group(1), treffer.group(2)
            pfad, _, frag = rest.partition("#")
            pfad = pfad.split("?")[0].strip("/")
            if ".." in pfad.split("/"):
                faults.append(f"{rel}: {url} - climbs out of {AUSZUG}/")
                continue
            if art == "blob" and pfad not in dateien:
                faults.append(f"{rel}: {url} - git tracks no such file")
                continue
            if art == "tree" and pfad not in ordner:
                faults.append(f"{rel}: {url} - git tracks no such folder")
                continue
            if not frag:
                continue
            # An anchor is only checkable where a Markdown file backs it.
            quelle = pfad if pfad.endswith(".md") else f"{pfad}/README.md".lstrip("/")
            if quelle not in dateien:
                continue
            anker = md_anker((ROOT / AUSZUG / quelle).read_text(encoding="utf-8"))
            if frag not in anker:
                faults.append(f"{rel}: {url} - {quelle} has no heading #{frag}")

    if not gesehen:
        # A checker that silently matches nothing reads exactly like a clean run.
        faults.append("no source link into the snapshot found - this check would "
                      "have passed on a site with none")
    else:
        faults += check_linkzahl(gesehen)
    return faults


def check_linkzahl(gemessen: int) -> list[str]:
    """The README quotes how many source links the site carries. A quoted figure
    that nothing measures is precisely what /numbers/ spends a page arguing
    against, so it gets the same treatment as the first-load figure: measured
    here, at build time, and never trusted."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return []
    genannt = re.findall(r"\*\*(\d+) source links\*\*",
                         readme.read_text(encoding="utf-8"))
    if len(genannt) != 1:
        return [f"README states {len(genannt)} source-link figures in the form "
                "**N source links**; the check needs exactly one"]
    if int(genannt[0]) != gemessen:
        return [f"README says the site carries {genannt[0]} source links; "
                f"measured {gemessen}"]
    return []


def check_readme(tree: dict[str, bytes]) -> list[str]:
    """The README states that first load in bytes. The figure went stale twice
    while /numbers/ was being written - once when the stylesheet grew, once when
    a single link was added to the footer - and nothing noticed either time. It
    is a measurement, so it is measured here rather than trusted."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return []
    text = readme.read_text(encoding="utf-8")
    genannt = re.findall(r"\*\*([\d,]+) bytes\*\*", text)
    if len(genannt) != 1:
        return [f"README states {len(genannt)} first-load figures in the form "
                "**N bytes**; the check needs exactly one"]
    ist = sum(len(tree[rel]) for rel in ERSTANSICHT if rel in tree)
    if int(genannt[0].replace(",", "")) != ist:
        return [f"README says the start page costs {genannt[0]} bytes on a first "
                f"visit; measured {ist:,}"]
    return []


def compare(tree: dict[str, bytes]) -> list[str]:
    faults = []
    on_disk = {
        p.relative_to(DIST).as_posix(): p.read_bytes()
        for p in DIST.rglob("*") if p.is_file()
    }
    for rel in sorted(set(tree) | set(on_disk)):
        if rel not in on_disk:
            faults.append(f"dist/ is missing {rel}")
        elif rel not in tree:
            faults.append(f"dist/ has a stray {rel}")
        elif on_disk[rel] != tree[rel]:
            faults.append(f"dist/{rel} is stale")
    return faults


def write(tree: dict[str, bytes]) -> None:
    if (DIST / ".git").exists():
        raise SystemExit("refusing to wipe dist/: it contains a .git directory")
    if DIST.exists():
        shutil.rmtree(DIST)
    for rel, data in tree.items():
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    tree = build()

    faults = check_links(tree) + check_external(tree) + check_snapshot_links(tree)
    if check_only:
        faults += compare(tree) + check_readme(tree)

    for fault in faults:
        print("FAULT  " + fault, file=sys.stderr)
    if faults:
        print(f"\n{len(faults)} fault(s).", file=sys.stderr)
        return 1

    if check_only:
        print(f"check ok - {len(tree)} files, links and anchors resolve, "
              "no external subresource, dist/ is current.")
    else:
        write(tree)
        total = sum(len(v) for v in tree.values())
        print(f"baked {len(tree)} files into dist/ ({total/1024:.0f} KB total)")

    blockers = check_deploy(tree)
    for blocker in blockers:
        print("DEPLOY BLOCKER  " + blocker, file=sys.stderr)
    if blockers:
        print("\nBuild is fine. Do NOT publish until the above is resolved.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
