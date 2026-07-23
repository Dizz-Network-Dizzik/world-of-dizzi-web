# the world of dizzi — website

The public site for **the world of dizzi**, the personal local-first AI network
whose curated snapshot lives at
[Dizz-Network-Dizzik/dizz-network](https://github.com/Dizz-Network-Dizzik/dizz-network).

The repository proves the system. This site explains it.

> The source of this site is part of the showcase. It is written to be read.

---

## What it is

Eleven pages of static HTML, one stylesheet, three subset web fonts and a
100-line Python baker. **No JavaScript, no cookies, no trackers, no external
request** — put the machine in airplane mode after the first load and every
page still works. Total for a first visit to the start page: about **66 KB**.

| | |
|---|---|
| Build | `bake.py` — Python standard library only, no node, no npm |
| Output | `dist/`, committed; Netlify publishes it with **no cloud build** |
| Design | palette and typography taken from `_netzwerk/SYSTEM_KARTE.html` in the public repository |
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
**the one place to change when the custom domain arrives.**

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
pwsh   pruefung/sweep.ps1      # the disclosure gate — run before every push
```

Four checks that need a browser and are therefore manual: Lighthouse on mobile,
axe or pa11y, a keyboard-only walk-through, and the 320-pixel reflow. The
airplane-mode probe is worth doing by hand too — it is the demonstration this
site was built for.

## Layout

```
bake.py               the build
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
subsets them with `fonttools` and writes the three WOFF2 files: **28.7 KB for
all three**. The licence texts ship next to them. The stylesheet declares two
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
