# the world of dizzi — website

The public site for **the world of dizzi**, the personal local-first AI network
whose curated document set lives in [`snapshot/`](snapshot) — in this same
repository, beside the site that explains it. Until 6 August 2026 that folder
held a 966-file code extract; it now holds 38 documents and no code.

The documents show how the system is built. This site explains it.

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
page: **91,205 bytes** uncompressed — 21.2 KB markup, 39.1 KB stylesheet,
28.0 KB fonts, 0.7 KB favicon — and less than that over the wire, where the
server compresses. The last 272 bytes are the sentences the 6 August curation
made necessary: the start page now says on itself that the code behind two of
its figures is no longer published. It was 69,773 bytes before the reveal animations and the
numbers page, which added 5,263 bytes of stylesheet and 55 bytes of markup;
those bytes bought motion that needs no script. Another 140 bytes of markup
followed, and all of it address: the start page carries six source links, and
when the snapshot moved in those six stopped naming a short repository and
started naming a longer one — five of them also gaining the path to the
snapshot's front page. Five links at 25 bytes, one at 15.

Another 2,548 bytes are the phone. On a 360-pixel screen the header used to
take 220 pixels — a quarter of the display before a word of content — because
nine navigation entries wrapped onto three lines. It now collapses behind one
button and takes 69 pixels, on every page and at every width below 769. That
cost 167 bytes of markup, which is the whole mechanism: a checkbox and a label.
The other 2,381 bytes are stylesheet, and about half of them are the comment
explaining why it is a checkbox and not a `<details>` element. A menu that a
browser might refuse to open is a menu; a navigation that a browser might
refuse to *show* is a dead site, and that is the direction the risk runs.

The last 2,959 bytes are the track on `/method/`, and every one of them is
stylesheet — the markup did not grow by a byte. The page that describes how a
work package travels now shows it as a rail with stations beside it: the
stations are an ordered list, the rail is two pseudo-elements on that list, and
the bright half of it is drawn by the reading position rather than by a clock.
No script, which is the constraint that shaped the whole thing — the privacy
statement promises no JavaScript, and that is a legal text, not a preference.
The drawing is a scroll-driven animation over the `contain` range, so the
leading edge stays level with the station being read instead of racing ahead of
it. A browser without scroll timelines shows no rail at all rather than one
frozen at zero; reduced motion and print remove it outright, each in the rule
that already removes the other animations. About half of those bytes are the
comments saying why.

The most recent 7,836 bytes are the design pass, and every one of them is
stylesheet: the markup did not grow by a byte. What the site had was a palette
and a font; what it lacked was a system. A heading sat flush against the text
under it, because headings carried no bottom margin at all and every page
bought its own spacing back with a utility class. Cards were flat fills with a
hairline around them. Only one element on the site — the app tile — did
anything on hover, and the secondary button's hover set its border to the
colour it already had. That is now one recipe rather than nine: cards are lit
from above by a two-stop gradient and cast a shadow downward, code blocks take
the same light from the other side because a code block is a hole in the page
rather than a card on it, and one curve and one duration are shared by
everything that moves. The eyebrow above every section heading carries the
house gradient as a short rule, which is the one ornament that repeats on all
twelve pages and most of what makes them look like one site. Two things there
are worth more than the ornament: the top of that card gradient is a colour
token like any other, so `kontrast.py` measures text against the *brightest*
surface a card actually paints rather than only against the flat value
underneath it; and the accent colours stay out of text, on bars and borders,
where the 3:1 they are proven against is the threshold that applies. Three
fifths of those bytes are the comments saying so — 4,765 of the 7,836. The last
of them records the one finding the pass produced rather than fixed: measured at
320 pixels, the wordmark was a 39-pixel touch target in a header where every
other free-standing link had already been raised to 44.

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
| Design | palette and typography taken from the system map in `statisch/karte/` |
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
it. `AUSZUG` below it names the folder holding the published documents, and the
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
powershell -NoProfile -ExecutionPolicy Bypass -File pruefung/sweep.ps1
                               # the disclosure gate — run before every push.
                               # Windows PowerShell 5.1, not pwsh: PowerShell 7
                               # is not installed here, and `pwsh: not found`
                               # looks exactly like a gate that was skipped.
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
probe, a scroll through the start page and `/method/` with reduced motion
switched on and off, and a print preview of `/numbers/`. The last two are there
because the reveal animations and the track depend on a scroll position and on
a motion preference, and neither
a sheet of paper nor a reader who has switched motion off ever supplies one —
both cases have their own rules at the foot of `stil.css`, and rules nobody has
looked at are not rules yet. The airplane-mode probe is the demonstration this
site was built for.

The source links used to be the one thing no gate here could check. They point
at GitHub, `check_links` skips external targets by design, and they led into a
second repository — so a file renamed over there left every gate green while
the site linked into nothing. Since the snapshot moved in, the same links can
be resolved, and `check_snapshot_links` resolves all **69 source links** against
`snapshot/` on every build: a missing file, a missing folder, a missing heading
all fail it. It asks `git` what the folder holds rather than the disk, because
this disk sees `Docs` and `docs` as one folder and knows files `git` has never
been told about — GitHub does neither. That same check also counts the
links and fails if the figure above no longer matches, so it cannot go stale
unnoticed.

What that still does not cover: whether **this** repository stays public and
keeps its name. Rename it or make it private and every gate stays green while
all 74 links break at once — and the claim on `/numbers/` that exactly one figure
cannot be checked from outside quietly stops being true. That figure read 83
until the travel pages were added, and 83 had not been true for some time:
counted over the built site as it stood before them, there were 72. It is the
one link count on this page that no gate measures, which is precisely why it
drifted while the two beside it could not — the same lesson this file already
tells twice about the first-load number. That risk now has one
source instead of two, but it is not gone. It lives in `bake.py` as `SELBST`.

## Layout

```
bake.py               the build
netlify.toml          publish dist/, run no build command
snapshot/             what the site links into — 38 documents, the curated
                      extract; travels with the repository, not with the site
vorlagen/             head + header, and footer
seiten/               content fragments, no <html> of their own
statisch/             copied 1:1 into dist/
  stil.css            one stylesheet, tokens at the top
  schrift/            three WOFF2 subsets + both OFL licence texts
  bilder/             og.png, favicon.svg
  karte/index.html    the system map; edited only in dizz-network and mirrored
                      here — see "The system map" below
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

### The system map

`statisch/karte/index.html` is the one page here that is not written here. It is
authored in the `dizz-network` repository as `_netzwerk/SYSTEM_KARTE.html` and
mirrored into this one, and it is the only page carrying inline script and style
— the CSP relaxation for that is scoped to `/karte/*` in `statisch/_headers` and
to nowhere else.

The two files are **not** byte-identical, and the difference is deliberate: a
handful of lines name internal working files and one term that does not belong
on a public page, and the mirrored copy carries those lines rewritten. Until
27 July 2026 the README claimed byte-identity and told the reader never to edit
the copy; both were true only because nobody had needed to change the map yet.

What actually has to hold is narrower and checkable: *the copy differs from the
source at exactly the known set of lines, and nowhere else.* The mirror is
therefore never made by hand — a tool reads both files as they stood at the last
commit, derives the rewrite map from that difference, applies it to the new
source, and then proves the resulting difference is the same set as before,
neither larger nor smaller. Editing this copy directly still gets you nothing but
drift; edit the source and re-run the mirror.

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

Documents public, code private, not open source. All rights reserved. The two font
families are SIL OFL 1.1 — their licence texts are in `statisch/schrift/`.
