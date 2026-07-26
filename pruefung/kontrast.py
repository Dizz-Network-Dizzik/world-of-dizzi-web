#!/usr/bin/env python3
"""Measures every text/surface combination the site actually uses.

Reads the tokens straight out of statisch/stil.css, so the numbers can never
drift from the stylesheet. WCAG 2.1 contrast: 4.5:1 for body text, 3:1 for
large text (>=24px, or >=18.7px bold) and for non-text indicators.

    python pruefung/kontrast.py      exit != 0 if any pair misses its target
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "statisch" / "stil.css"


def tokens() -> dict[str, str]:
    text = CSS.read_text(encoding="utf-8")
    root = text.split(":root{", 1)[1].split("}", 1)[0]
    return {m[0]: m[1] for m in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root)}


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# (foreground token, background token, required ratio, where it is used)
PAIRS = [
    ("tx",     "bg",     4.5, "body text on the page background"),
    ("tx",     "panel",  4.5, "body text inside a card"),
    ("tx",     "panel2", 4.5, "body text inside a notice"),
    ("tx",     "panelh", 4.5, "card text in the hover state"),
    ("tx",     "bg2",    4.5, "header, footer and code block text"),
    ("tx2",    "bg",     4.5, "muted body text, lists, captions"),
    ("tx2",    "panel",  4.5, "muted text inside a card"),
    ("tx2",    "panel2", 4.5, "muted text inside a notice"),
    ("tx2",    "panelh", 4.5, "muted text in the hover state"),
    ("tx2",    "bg2",    4.5, "footer text, status strip, chips"),
    ("cy",     "bg",     4.5, "links and the kicker line"),
    ("cy",     "panel",  4.5, "links inside a card, law-quote kicker"),
    ("cy",     "bg2",    4.5, "map link in the navigation"),
    ("cy",     "panelh", 4.5, "focus ring and button hover"),
    ("green",  "bg",     3.0, "status LED, done marker"),
    ("green",  "panel",  3.0, "done marker inside a card"),
    ("amber",  "bg",     3.0, "status LED for the dry-run flag"),
    ("vio",    "bg",     3.0, "diagram accent, core ring"),
    ("mag",    "bg",     3.0, "gradient start, tile edges"),
    ("coral",  "bg",     3.0, "trading accent, tile edges"),
    ("orange", "bg",     3.0, "news accent, tile edges"),
    ("blue",   "bg",     3.0, "communication accent, tile edges"),
    ("tx2",    "bg",     3.0, "steel accent for the admin tile"),
    # deliberately listed: tx3 is decoration only, never carries information
    ("tx3",    "bg",     3.0, "decorative separator dots only - no information"),
]


def main() -> int:
    tk = tokens()
    print(f"{len(tk)} colour tokens read from statisch/stil.css\n")
    print(f"{'pair':<22}{'ratio':>8}{'need':>7}  {'':<4}where")
    print("-" * 96)
    bad = 0
    for fg, bg, need, where in PAIRS:
        got = ratio(tk[fg], tk[bg])
        ok = got >= need
        bad += 0 if ok else 1
        print(f"--{fg} on --{bg}".ljust(22)
              + f"{got:>7.2f}:1{need:>6}:1  {'PASS' if ok else 'FAIL':<4}{where}")
    print("-" * 96)
    if bad:
        print(f"\n{bad} combination(s) below target.", file=sys.stderr)
        return 1
    print(f"\nall {len(PAIRS)} combinations meet WCAG 2.1 AA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
