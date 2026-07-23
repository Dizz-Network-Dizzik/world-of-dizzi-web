#!/usr/bin/env python3
"""Structural and accessibility checks over dist/ - the part of the quality gate
that can be proven without a browser.

Covers: well-formedness, landmarks, heading order, accessible names, unique ids,
language attributes, the no-JavaScript / no-inline-style promise, SVG labelling,
metadata lengths and the skip link. Browser-only checks (Lighthouse, axe, WAVE,
keyboard walk-through, 320px reflow) stay manual - see README.

    python pruefung/pruefen.py       exit != 0 on any finding
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.findings: list[str] = []
        self.ids: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.landmarks: set[str] = set()
        self.links: list[tuple[str, str]] = []      # (href, accessible name)
        self.scripts: list[str] = []
        self.inline_style = 0
        self.forms = 0
        self.imgs_without_alt = 0
        self.svgs: list[tuple[str, str]] = []       # (role, aria-labelledby)
        self.first_focusable: str | None = None
        self.lang: str | None = None
        self.title = ""
        self.description = ""
        self.viewport = False
        self._collect: list[str] | None = None
        self._href = ""
        self._hidden = 0
        self._in_title = False

    # -- helpers ----------------------------------------------------------
    def _fail(self, msg: str) -> None:
        self.findings.append(f"line {self.getpos()[0]}: {msg}")

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

        if "style" in a:
            self.inline_style += 1
            self._fail(f"<{tag}> carries an inline style attribute")
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        if tag in HEADINGS:
            self.headings.append((int(tag[1]), ""))
            self._collect = []
        if tag in {"header", "nav", "main", "footer"}:
            self.landmarks.add(tag)
        if tag == "script":
            self.scripts.append(a.get("type", "text/javascript"))
        if tag == "form":
            self.forms += 1
        if tag == "img" and not a.get("alt") and a.get("alt") != "":
            self.imgs_without_alt += 1
        if tag == "svg":
            self.svgs.append((a.get("role", ""), a.get("aria-labelledby", "")))
        if tag == "title" and any(t == "head" for t, _ in self.stack):
            self._in_title = True   # the <title> inside an <svg> is not the page title
        if tag == "meta" and a.get("name") == "description":
            self.description = a.get("content", "")
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = True
        if a.get("aria-hidden") == "true":
            self._hidden += 1
        if tag == "a" and "href" in a:
            if self.first_focusable is None:
                self.first_focusable = a["href"]
            self._href = a["href"]
            self._collect = [a["aria-label"]] if a.get("aria-label") else []

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if not self.stack:
            self._fail(f"</{tag}> with nothing open")
            return
        open_tag, line = self.stack.pop()
        if open_tag != tag:
            self._fail(f"</{tag}> closes <{open_tag}> opened on line {line}")
        if tag == "title":
            self._in_title = False
        if tag in HEADINGS and self._collect is not None:
            level = self.headings[-1][0]
            self.headings[-1] = (level, " ".join(self._collect).strip())
            self._collect = None
        if tag == "a" and self._collect is not None:
            name = " ".join(self._collect).strip()
            self.links.append((self._href, name))
            self._collect = None
        if self._hidden:
            self._hidden = max(0, self._hidden - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._collect is not None and not self._hidden and data.strip():
            self._collect.append(data.strip())


def check(path: Path, rel: str) -> list[str]:
    out: list[str] = []
    text = path.read_text(encoding="utf-8")
    p = Page()
    p.feed(text)
    p.close()
    out += p.findings
    if p.stack:
        out += [f"unclosed <{t}> from line {n}" for t, n in p.stack]

    # language
    if not p.lang:
        out.append("<html> has no lang attribute")
    expected = "de" if rel.startswith(("de/", "impressum/", "datenschutz/")) else "en"
    if p.lang != expected:
        out.append(f"lang is {p.lang!r}, expected {expected!r}")

    # landmarks
    for lm in ("header", "nav", "main", "footer"):
        if lm not in p.landmarks:
            out.append(f"missing <{lm}> landmark")

    # headings
    levels = [lv for lv, _ in p.headings]
    if levels.count(1) != 1:
        out.append(f"expected exactly one <h1>, found {levels.count(1)}")
    for prev, cur in zip(levels, levels[1:]):
        if cur > prev + 1:
            out.append(f"heading order jumps from h{prev} to h{cur}")
    for lv, txt in p.headings:
        if not txt:
            out.append(f"empty <h{lv}>")

    # accessible names
    for href, name in p.links:
        if not name:
            out.append(f"link to {href} has no accessible name")

    # ids
    dupes = {i for i in p.ids if p.ids.count(i) > 1}
    if dupes:
        out.append(f"duplicate id(s): {sorted(dupes)}")

    # the promises
    for kind in p.scripts:
        if kind.lower() != "application/ld+json":
            out.append(f"executable <script type={kind!r}> - this site ships no JS")
    if p.inline_style:
        out.append(f"{p.inline_style} inline style attribute(s) - CSP forbids them")
    if p.forms:
        out.append(f"{p.forms} <form> element(s) - form-action is 'none'")
    if p.imgs_without_alt:
        out.append(f"{p.imgs_without_alt} <img> without alt")

    # svg labelling
    for role, labelled in p.svgs:
        if role != "img":
            out.append("<svg> without role=\"img\"")
        for ref in labelled.split():
            if ref not in p.ids:
                out.append(f"<svg aria-labelledby> points at missing id {ref!r}")

    # skip link first
    if p.first_focusable != "#inhalt":
        out.append(f"first focusable element is {p.first_focusable!r}, "
                   "expected the skip link '#inhalt'")
    if 'id="inhalt"' not in text:
        out.append("skip link target #inhalt does not exist")

    # metadata
    title = p.title.strip()
    if not title:
        out.append("no <title>")
    elif len(title) > 60:
        out.append(f"<title> is {len(title)} characters (limit 60): {title!r}")
    if not p.description:
        out.append("no meta description")
    elif len(p.description) > 155:
        out.append(f"meta description is {len(p.description)} characters (limit 155)")
    if not p.viewport:
        out.append("no viewport meta")

    return out


def main() -> int:
    pages = sorted(
        p for p in DIST.rglob("*.html") if "karte" not in p.relative_to(DIST).parts
    )
    total = 0
    for path in pages:
        rel = path.relative_to(DIST).as_posix()
        findings = check(path, rel)
        total += len(findings)
        mark = "ok  " if not findings else "FAIL"
        print(f"{mark} {rel}")
        for f in findings:
            print(f"       - {f}")
    print()
    if total:
        print(f"{total} finding(s) across {len(pages)} pages.", file=sys.stderr)
        return 1
    print(f"{len(pages)} pages, 0 findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
