# the world of dizzi — website

The public site for **the world of dizzi**, the personal local-first AI network
whose curated code snapshot lives in [`snapshot/`](snapshot) — in this same
repository, beside the site that explains it.

The code proves the system. This site explains it.

> The source of this site is part of the showcase. It is written to be read.

---

## What it is

Twelve pages of static HTML, one stylesheet, three subset web fonts and a
Python baker that counts its own lines and writes the figure into the footer
of every page — so the footer's number cannot drift away from the file it
describes. **No JavaScript, no cookies, no trackers, no external request** —
put the machine in airplane mode after the first load and every page still
works. The one exception is the copied system map at `/karte/`,
which brings its own inline script and is the only page that talks to
anything: it asks `127.0.0.1:8200` whether a local core is running, and shows
the offline view when nothing answers. Total for a first visit to the start
page: **75,231 bytes** uncompressed — 20.8 KB markup, 23.9 KB stylesheet,
28.0 KB fonts, 0.7 KB favicon — and less than that over the wire, where the
server compresses. It was 69,773 bytes before the reveal animations and the
numbers page, which added 5,263 bytes of stylesheet and 55 bytes of markup;
those bytes bought motion that needs no script. The 140 bytes since are markup
as well, and all of it address: the start page carries six source links, and
when the snapshot moved in those six stopped naming a short repository and
started naming a longer one — five of them also gaining the path to the
snapshot's front page. Five links at 25 bytes, one at 15.

That figure is exact rather than rounded, and `bake.py --check` measures it
against the built files. It went stale twice while `/numbers/` was being
written — once when the stylesheet grew, once when a single link was added to
the footer — and nothing noticed either time. A first-load number nobody
re-measures is a claim, not a measurement.

The six figures the site leads with have a page of their own at `/numbers/`,
which carries the method that produced each one and the date it was measured,
and names the one figure that cannot be checked from outside. That page is why
the numbers tiles no longer borrow their evidence from a README: they used to
link to one, and a README that repeats a number does not prove it. It is also
why this repository is linked from the site — the build figure in every footer
is measured here, so the file behind it has to be reachable.

| | |
|---|---|
| Build | `bake.py` — Python standard library only, no node, no npm |
| Output | `dist/`, committed; Netlify publishes it with **no cloud build** |
| Design | palette and typography taken from `snapshot/_netzwerk/SYSTEM_KARTE.html` |
| Languages | English throughout, plus a German entry page at `/de/` and German legal pages |
| Hosting | Netlify free tier; `_headers` carries the CSP and the security headers |

## Build it

```
python bake.py            # writes dist/
python bake.py --check    # verifies without writing (part of the gate)
```

`bake.py` glues `vorlagen/kopf.html` + a fragment from `seiten/` +
`vorlagen/fuss.html`, copies `statisch/` verbatim, and generates `sitemap.xml`,
`robots.txt` and `llms.txt` from the `HOST` constant at the top of the file —
**the one place to change when the custom domain arrives.** `SELBST` sits
beside it and names this repository, so that the file behind the build figure
in every footer — `bake.py` itself — stays reachable from the page that quotes
it. `AUSZUG` below it names the folder holding the code snapshot, and the
two link bases built from those two, `DATEI` and `ORDNER`, carry every source
link on the site. Moving or renaming the snapshot is one line here, then build
again.

It refuses to finish quietly. It fails on a dead internal link, a dead anchor,
an unknown `{{PLACEHOLDER}}` or a subresource pointing at another host, and it
exits with code `2` — "build fine, do not publish" — while the Impressum still
carries its placeholder.

### Look at it locally

```
python -m http.server 8791 --directory dist --bind 127.0.0.1
```

Then open `http://127.0.0.1:8791/`. Absolute paths need a server; opening
`dist/index.html` from the file system will not load the stylesheet.

## Check it

```
python bake.py --check         # links, anchors, external subresources, dist freshness
python pruefung/pruefen.py     # structure, landmarks, heading order, names, metadata
python pruefung/kontrast.py    # every colour pair against WCAG 2.1 AA
python pruefung/proofread.py   # spelling, typography, figures, the securities line
pwsh   pruefung/sweep.ps1      # the disclosure gate — run before every push
```

The first three gates were tight from the start and the site still went out
with broken quotation marks in it: none of them reads a sentence.
`proofread.py` is the answer to that, and it judges the baked pages rather
than the fragments, because the titles, meta descriptions, navigation and the
whole footer live in `bake.py` and never in `seiten/`. `sweep.ps1` reads its
term list from outside this repository and stops with exit code `2` when it
cannot find it — a clone can run every other check, but not that one.

Seven checks need a browser and are therefore manual: Lighthouse on mobile, axe
or pa11y, a keyboard-only walk-through, the 320-pixel reflow, the airplane-mode
probe, a scroll through the start page with reduced motion switched on and off,
and a print preview of `/numbers/`. The last two are there because the reveal
animations depend on a scroll position and on a motion preference, and neither
a sheet of paper nor a reader who has switched motion off ever supplies one —
both cases have their own rules at the foot of `stil.css`, and rules nobody has
looked at are not rules yet. The airplane-mode probe is the demonstration this
site was built for.

The source links used to be the one thing no gate here could check. They point
at GitHub, `check_links` skips external targets by design, and they led into a
second repository — so a file renamed over there left every gate green while
the site linked into nothing. Since the snapshot moved in, the same links can
be resolved, and `check_snapshot_links` resolves all **76 source links** against
`snapshot/` on every build: a missing file, a missing folder, a missing heading
all fail it. It asks `git` what the folder holds rather than the disk, because
this disk sees `Docs` and `docs` as one folder and knows files `git` has never
been told about — GitHub does neither. That same check also counts the
links and fails if the figure above no longer matches, so it cannot go stale
unnoticed.

What that still does not cover: whether **this** repository stays public and
keeps its name. Rename it or make it private and every gate stays green while
all 76 links break at once — and the claim on `/numbers/` that exactly one figure
cannot be checked from outside quietly stops being true. That risk now has one
source instead of two, but it is not gone. It lives in `bake.py` as `SELBST`.

## Layout

```
bake.py               the build
netlify.toml          publish dist/, run no build command
snapshot/             the code this site is about — 966 files, the curated
                      extract; travels with the repository, not with the site
vorlagen/             head + header, and footer
seiten/               content fragments, no <html> of their own
statisch/             copied 1:1 into dist/
  stil.css            one stylesheet, tokens at the top
  schrift/            three WOFF2 subsets + both OFL licence texts
  bilder/             og.png, favicon.svg
  karte/index.html    byte-identical copy of the system map — never edit
  _headers            CSP and security headers for Netlify
pruefung/             the quality gate
werkzeug/             one-off build tools (fonts, OG image) — not site dependencies
dist/                 the baked site, committed, published by Netlify
```

### Fonts

Orbitron for display, Chakra Petch for text — both SIL OFL, both self-hosted.
`werkzeug/schriften.ps1` fetches the sources from `github.com/google/fonts`,
subsets them with `fonttools` and writes the three WOFF2 files: **28,720 bytes
for all three**. The licence texts ship next to them. The stylesheet declares two
metric-matched fallback faces whose `size-adjust`, `ascent-override` and
`descent-override` were measured from the real fonts, so the font swap costs no
layout shift.

Rebuilding the fonts or the share image needs `pip install fonttools brotli`;
neither is a dependency of the site.

### No inline styles, on purpose

The CSP sets `style-src 'self'` with no `'unsafe-inline'`, and that directive
also governs `style="…"` attributes — so the pages carry none. Accents and
spacing come from a small closed set of utility classes at the bottom of
`stil.css`. `werkzeug/entstyle.py` is the record of how they were removed and
re-runs as a guard.

## Deploy

Netlify, publish directory `dist`, build command empty. Nothing is installed,
so nothing can break on a dependency update.

**The gate:** do not publish until the quality checks are green *and* the
Impressum carries a real, servable address. `bake.py` exits `2` until it does.

## Licence

Source-visible showcase, not open source. All rights reserved. The two font
families are SIL OFL 1.1 — their licence texts are in `statisch/schrift/`.
