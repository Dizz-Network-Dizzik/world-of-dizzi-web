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
"""

from __future__ import annotations

import html
import re
import shutil
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
REPO = "https://github.com/Dizz-Network-Dizzik/dizz-network"

OG_ALT = (
    "the world of dizzi — dark title card with the numbers "
    "10 applications, 2,600+ commits, ~100,000 lines of Python, 2,623 tests"
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
             "Source-visible showcase.",
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
             "curated public snapshot on 23 July 2026 — every node dated in "
             "the repository.",
    ),
    dict(
        src="vision.html", out="vision/index.html", path="/vision/", lang="en",
        title="From project to company | the world of dizzi",
        desc="Where the project stands, why the contract architecture scales, "
             "and what we are opening: early conversations with partners and "
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
        desc="Ein persönliches, lokal-first KI-Netzwerk: zehn Anwendungen, ein "
             "gemeinsamer Vertrag, gebaut von einem Menschen mit KI-Assistenz. "
             "Einsehbarer Quellcode.",
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
    ("/journey/", "Journey", "Chronik"),
    ("/vision/", "Vision", "Vision"),
    ("/about/", "About", "Kontakt"),
]

T = {
    "en": dict(
        SKIP="Skip to content",
        NAVLABEL="Main",
        MAP="System map",
        LANGLINK='<a class="nav-lang" href="/de/" lang="de" hreflang="de">Deutsch</a>',
        SOURCE="Source",
        FOOT_CLAIM="Source-visible showcase, not open source. All rights reserved.",
        FOOT_STATUS="Independent project — incorporation ahead.",
        FOOT_LEGALLABEL="Legal",
        IMPRESSUM="Impressum",
        DATENSCHUTZ="Privacy",
        FOOT_BUILT="Built with a 100-line Python baker. No cookies, no trackers, "
                   "no external requests.",
    ),
    "de": dict(
        SKIP="Zum Inhalt springen",
        NAVLABEL="Haupt",
        MAP="System-Karte",
        LANGLINK='<a class="nav-lang" href="/" lang="en" hreflang="en">English</a>',
        SOURCE="Quellcode",
        FOOT_CLAIM="Einsehbarer Quellcode, keine Open-Source-Lizenz. Alle Rechte "
                   "vorbehalten.",
        FOOT_STATUS="Freies Projekt — Gründung in Vorbereitung.",
        FOOT_LEGALLABEL="Rechtliches",
        IMPRESSUM="Impressum",
        DATENSCHUTZ="Datenschutz",
        FOOT_BUILT="Gebacken von einem 100-Zeilen-Python-Skript. Keine Cookies, "
                   "keine Tracker, keine externen Aufrufe.",
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
      "description": "Ten local-first applications around a headless core, joined by one written app contract. Curated public snapshot, source-visible, not open source.",
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
        body = JSONLD[page["jsonld"]] % dict(host=HOST, repo=REPO)
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
            REPO=REPO,
            OGLOCALE="de_DE" if lang == "de" else "en_GB",
            OGALT=html.escape(OG_ALT, quote=True),
            NAV=nav_html(page),
            YEAR="2026",
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
> source-visible personal AI network. Curated public snapshot; not open source.

## Start here
- [The system]({HOST}/system/): architecture, the app contract, shared core library
- [The ten applications]({HOST}/apps/): what each app does, with source links
- [The method]({HOST}/method/): written laws, contracts, AI build-chat orchestration
- [Journey]({HOST}/journey/): dated milestones since June 2026
- [From project to company]({HOST}/vision/): status, why it scales, what we're opening
- [About & contact]({HOST}/about/): who builds this, and how to reach him

## Source
- [Public repository]({REPO}): 966 files, one curated commit
- [Interactive system map]({HOST}/karte/): self-contained, no external calls

## Notes
- Status: independent project, pre-incorporation. No revenue yet; the trading
  fleet runs dry-run only. Snapshot public since 23 July 2026.
- Every number on this site links to the file in the repository that proves it.
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

    faults = check_links(tree) + check_external(tree)
    if check_only:
        faults += compare(tree)

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
