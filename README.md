# the world of dizzi — website

The public site for **the world of dizzi**, the personal local-first AI network
whose curated document set lives in [`snapshot/`](snapshot) — in this same
repository, beside the site that explains it. Until 6 August 2026 that folder
held a 966-file code extract; it now holds 38 documents and no code.

The documents show how the system is built. This site explains it.

> The source of this site is part of the showcase. It is written to be read.

---

## What it is

Seventeen pages of static HTML, one stylesheet, three subset web fonts and a
Python baker that counts its own lines and writes the figure into the footer
of every page — so the footer's number cannot drift away from the file it
describes. **No JavaScript, no cookies, no trackers, no external request** —
put the machine in airplane mode after the first load and every page still
works. The one exception is the copied system map at `/karte/`,
which brings its own inline script and is the only page that talks to
anything: it asks `127.0.0.1:8200` whether a local core is running, and shows
the offline view when nothing answers. Total for a first visit to the start
page: **143,296 bytes** uncompressed — 26.0 KB markup, 85.2 KB stylesheet,
28.0 KB fonts, 0.7 KB favicon — and less than that over the wire, where the
server compresses. The latest change is a removal: 104 bytes left on 6 September
2026 when the site moved to its own domain, worldofdizzi.com, and every absolute
address on the start page — canonical link, sitemap, structured data, social
preview — got twelve characters shorter. Before that, 52 bytes were one entry in the menu: a seventeenth
page, `/schwelle/`, in German — the ten laws of the house for people, without a
name, as plain text: it asks nothing, sends nothing and stores nothing. Before
that, 49 bytes were a sixteenth page, `/balance/`, in German, that quotes the
essence of the house word for word from the document the rest of this site
grows out of — and says plainly which of the sections it quotes the published
copy of that document already carries, and which came later. Before that, 588
bytes were a removal wearing
its explanation:
the cross-document view transition is gone, because inside in-app browsers its
snapshot froze the page on every link tap, and a site that reliably navigates
beats one that beautifully transitions. Before that, 5,019 bytes were the
phone polish pass: the
stacked tables drop their desktop width floor instead of hiding a third of
every sentence, anchors land with air above them, the menu arrives instead of
appearing, taps get an answer, the primary button reads as the first step,
and a back-to-top link closes every footer. The 3,082 before them — 2,567 of stylesheet, 515 of markup —
are the small map: a second, hand-written map at `/mini-karte/` that stands in
for the copied one on every screen under 769 pixels, and the CSS pair that
decides which of the two a link points at. The 10,995 before them — 6,339 of
stylesheet, 4,656 of markup — are the grove on the two front pages: three fronds, a singing bowl,
two halves in balance, a band of water and the deep reveals, all of it CSS
and SVG, none of it script. The last 272 bytes are the sentences the 6 August curation
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

Another 7,836 bytes are the design pass, and every one of them is
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
seventeen pages and most of what makes them look like one site. Two things there
are worth more than the ornament: the top of that card gradient is a colour
token like any other, so `kontrast.py` measures text against the *brightest*
surface a card actually paints rather than only against the flat value
underneath it; and the accent colours stay out of text, on bars and borders,
where the 3:1 they are proven against is the threshold that applies. Three
fifths of those bytes are the comments saying so — 4,765 of the 7,836. The last
of them records the one finding the pass produced rather than fixed: measured at
320 pixels, the wordmark was a 39-pixel touch target in a header where every
other free-standing link had already been raised to 44.

The next 6,058 bytes are the visual turn, and they are the first entry on
this list where the markup went *down* while the total went up. The two start
pages were columns of prose with one diagram in the middle. What they say is
unchanged; how much of it has to be read is not. Three blocks of running text
became structure instead: the four headline figures now stand above a table that
says, figure by figure, where each can still be checked; the ten applications are
a table with a port and one sentence each rather than ten tiles; and the law about
human gates is drawn as three nodes with the gate between them instead of being
restated in prose underneath itself. What left the English start page was moved,
not deleted — the three architectural decisions, in full and with the trade-off
each carries, are a section of their own at `/system/#entscheidungen`, and the
start page links there. The German page has no German subpages to move anything
into, so its six-station route was **shortened rather than relocated**: every
station and every rule still stands, the elaboration does not, and the page now
points at `/method/#weg` for it. That is the one place in this pass where text was
cut instead of moved, which is why it is named here rather than left to be noticed.
The German page also gained the network diagram it never had.

The start page's own markup came out 322 bytes lighter — far less than the prose
that left it, because a table row costs about what a sentence costs. The other
6,380 bytes are stylesheet: three components and one animation, of which 3,365
bytes are the comments saying why. The one worth repeating here is why none of
this is a script. An SVG scales its type down with its box, so a drawing that
reads at 1200 pixels arrives on a 360-pixel phone with nine-pixel labels; the
obvious fix is JavaScript, and the privacy statement promises there is none —
a legal text, not a preference. So text that has to stay legible lives in HTML,
where it reflows, and a picture with no text in it lives in an SVG. The nine
straight lines from the core became nine curves, which costs 80 bytes and is the
whole difference between a wiring diagram and something grown; the violet ring
around the core now widens as the diagram is reached, drawn by the reader's
scroll position like the track and the reading bar, because nothing here is
allowed to move on its own.

The next 8,258 bytes are the pass over `/apps/` and `/numbers/`, and
every one of them is stylesheet again — so the start page, which uses none of
it, still pays for it on the first load. That is what one stylesheet for the
whole site costs, and it is the same trade as every byte above. What those two
pages had was prose. The ten applications were ten long blocks of text, and
holding two of them against each other meant reading both; the six figures were
six headings over six blocks that open. They are now one table with a drawn
shape per application, and six tiles that start with the number. Nothing was
dropped: the long text sits under the list it explains, in the same open-on-click
block `/numbers/` already used. The bars beside the figures are drawn from
numbers the pages already state — 966 against 38, and 579 + 46 + 3 + 2,039
against their stated total — and the arithmetic behind every width is written
out next to it in the stylesheet, because bars are a claim about scale and a
claim needs its method here like any other. Two of those are thinner than a
hairline at any width worth using, so the bars carry a floor of three pixels:
one nobody can see would round a real value down to nothing, which is the one
thing a page about honest figures must not do. The ten marks say nothing about
what is inside the machine, and they are hidden from screen readers rather than
labelled: the row already says the name in words, and saying it twice helps
nobody.

The next 7,834 bytes are the mobile pass, and like the two entries above it
they are all stylesheet — the markup did not grow by a byte. Most of the people
who arrive here arrive on a phone, and everything above was drawn at desk width.
Measured at 360 pixels before any of it: the network diagram was held at 520
pixels inside a 328-pixel column, so 192 pixels of it — three of the nine
services — sat behind a sideways swipe that nothing announces; the ten
applications stood in a 168/158 split, and 158 pixels is 21 characters, so every
description of them broke over five lines; the link on an application name was a
19-pixel touch target, on a site whose own rule raises a free-standing link on a
touch screen to 44; and the body text was 15 pixels.

The diagram needed an answer rather than a smaller copy of the old one, because
an SVG scales its type with its box and the labels go illegible first. So below
566 pixels — the width at which the column finally reaches the 520 the drawing
is held at — the nine labels are hidden and the drawing is cropped to the ring
itself, which then fills the screen. The names and the ports are not lost: they
stand in the table directly under the figure, where they reflow, and in the
description a screen reader is given. Two things were given up, and are named
here rather than left to be found. The ring stops breathing on a phone — a
scroll-driven scale inside an SVG re-renders the SVG rather than moving a layer,
and that is a repaint per scroll frame for an ornament, on the mid-range phone
this was written for. And below 480 pixels the two tables become stacks of
cards, which costs them their table role: affordable in these two and nowhere
else here, because both are two columns whose first column is the row header, a
shape that linearises into what it already looked like. Three quarters of the
bytes are the comments saying all of that — 6,083 of the 7,834. The pages are
longer for it, the start page measuring 8,100 pixels at 360 instead of 7,762,
and every line in them is now the full width of the column. At 769 pixels and
above both start pages measure exactly what they measured before.

The most recent 10,313 bytes are the phone a second time — the earlier phone
pass folded the header away, this one carries the seven pages behind the two
that lead. 10,097 of them are stylesheet and 216 are markup, and every figure
in them was read off a browser at 360 and at 412 pixels rather than reasoned
about. The finding that mattered was on `/apps/`: its table of ten is 560
pixels wide inside a frame that is 326 on a phone, so a reader arrived looking
at two of the four columns with nothing on the screen saying the other two
existed. Below 611 pixels — where the wrap padding leaves less than the table
needs, which is arithmetic and not a chosen round number — every row is now a
card. What lets this particular table survive losing its grid is that each cell
says what it is on its own: a port reads as a port and a test count says tests,
so no card has to restate a column head. The contract listing on `/system/`
had the same shape of problem and took the same kind of answer: it needed 452
pixels in a 326 box and could not wrap out of it, so each comment moved under
the line it annotates instead. Measured after: at 360 and at 412 not one of the
seven pages scrolls sideways, and neither does any box inside them. At 320 one
block still does — the diagram on `/method/` — inside its own frame, which is
the rule this site already wrote for wide things. The body text goes from 15 to
16 pixels below 769, still in `rem` so a raised device font keeps its multiple;
the ten links in that table, the six recovery links on the 404 page and the two
contact links on `/about/` became 44-pixel targets. Three things were measured
and then left alone rather than fixed, and they are named in the stylesheet with
the reason: `content-visibility` on `/apps/`, because the ten in-page anchors it
would gamble with are that page's whole navigation; the rail on `/method/` and
`/journey/`, because it already runs through the middle of every station dot and
because a second lane was working the same construct; and the comment colour in
that contract listing, which is about 4.2:1 where 4.5 applies and is older than
this pass. Four fifths of the stylesheet bytes are those explanations. A further
1,028 bytes went into `pruefung/woerter_en.txt`, which nobody downloads. Some of
that is this paragraph paying its own way — a word the site has not used before
has to be checked and entered before the gate will pass it — but four of the
entries are a real fault it had been hiding: `can't`, `doesn't`, `isn't` and
`you're` stood in the list with a straight apostrophe while every page sets the
typographic one, so the gate had been red on four correctly spelled words and
the straight forms it did hold could never be reached.

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
python pruefung/webview_wache.py
                               # the in-app browser rules — and `bake.py` calls
                               # it too, so it runs on every build without
                               # anybody remembering to
powershell -NoProfile -ExecutionPolicy Bypass -File pruefung/sweep.ps1
                               # the disclosure gate — run before every push.
                               # Windows PowerShell 5.1, not pwsh: PowerShell 7
                               # is not installed here, and `pwsh: not found`
                               # looks exactly like a gate that was skipped.
python pruefung/live_gegenprobe.py
                               # the delivery gate — after every push: fetches
                               # every file bake.py wrote and compares it byte
                               # for byte with what is live; the host's own
                               # injection is stripped and reported, anything
                               # else is drift. Until 05.09.2026 this was done
                               # by hand, which looks exactly like not at all.
```

The first three gates were tight from the start and the site still went out
with broken quotation marks in it: none of them reads a sentence.
`proofread.py` is the answer to that, and it judges the baked pages rather
than the fragments, because the titles, meta descriptions, navigation and the
whole footer live in `bake.py` and never in `seiten/`. `sweep.ps1` reads its
term list from outside this repository and stops with exit code `2` when it
cannot find it — a clone can run every other check, but not that one.

`webview_wache.py` is the newest and has the same origin story: every gate above
was green while the site froze inside Instagram's built-in browser. It holds
eight rules for the browsers this site cannot choose — the WebViews inside the
social apps, which draw their own bars over the page. Cross-document view
transitions, unguarded smooth scrolling, `target="_blank"` without
`rel="noopener"`, `javascript:` URLs, any script that is not JSON-LD, anything
pinned to a viewport edge while visible, `100vh` and `100dvh`, and meta refresh.
It reads `seiten/`, `vorlagen/`, the stylesheet and `dist/`, and skips both
copies of the system map, which is a mirror and brings its own script. Comments
are blanked before it matches, because the stylesheet quotes the forbidden
declaration in the note that explains why it went: a watch that fired on its own
explanation would be switched off within a week. `bake.py` calls it on the pages
it has just built, so it runs on every build — a rule that only runs when
somebody remembers it is the rule that was missing the first time. What it
cannot do is open Instagram: a rendering fault in one app on one phone is found
by a thumb, and this one was.

The newest watch is not a script but a refusal, and it lives in `bake.py` as
`check_merge_marker`. On the night of 7 August 2026 two nested conflict blocks
from a merge stood committed and published **in this file**, in the middle of a
paragraph — and all six gates were green, because all six read content and this
file is built into nothing. So the watch is aimed at a class of text rather
than at a place: the seven-character lines git leaves behind when it cannot
merge, in the pages just built *and* in every text file of the working tree.
What it reads on disk is derived rather than listed — the whole repository,
naming only what it skips, since a list of places to look is precisely how the
last one got through. The divider line of a conflict block, seven equals signs,
is also how Markdown underlines a heading, so it counts only where the same
file carries one of the unmistakable markers too: a gate that goes red on a
correct file is switched off within a week. For the same reason this paragraph
names those markers in words instead of quoting them — the watch reads this
file like any other, and a quotation that drifted to the start of a line would
be indistinguishable from the thing it quotes. The one word list a conflict
could hide in longest is `pruefung/woerter_*.txt`: `proofread.py` reads those
as vocabulary, so three marker lines would enrol as three more legal words and
nothing would ever say so.

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
be resolved, and `check_snapshot_links` resolves all **71 source links** against
`snapshot/` on every build: a missing file, a missing folder, a missing heading
all fail it. It asks `git` what the folder holds rather than the disk, because
this disk sees `Docs` and `docs` as one folder and knows files `git` has never
been told about — GitHub does neither. That same check also counts the
links and fails if the figure above no longer matches, so it cannot go stale
unnoticed.

What that still does not cover: whether **this** repository stays public and
keeps its name. Rename it or make it private and every gate stays green while
all 72 links break at once — and the claim on `/numbers/` that exactly one figure
cannot be checked from outside quietly stops being true. It is the one link count
on this page that no gate measures, and it has drifted twice already: it read 83
until a count over the built site produced 72, and 74 from the travel pages until
the start pages were rebuilt. Both times the two figures beside it could not
drift, because something measures them — the same lesson this file already
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
