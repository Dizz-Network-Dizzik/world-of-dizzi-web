#!/usr/bin/env python3
"""One-off: replace every inline style attribute in seiten/ with a utility class.

The site ships a strict CSP (`style-src 'self'`, no 'unsafe-inline'), and that
directive also governs style ATTRIBUTES. So the pages carry none. Kept in the
repository as the record of how they were removed, and as a guard: re-running it
must report zero remaining attributes.
"""
import re
import sys
from pathlib import Path

SEITEN = Path(__file__).resolve().parent.parent / "seiten"

PAIRS = [
    # accent custom property -> accent class
    (' class="kachel" href="{h}" style="--akz:var(--{c})"', None),  # handled below
]

ACCENT = {
    "vio": "a-vio", "cy": "a-cy", "mag": "a-mag", "amber": "a-amber",
    "coral": "a-coral", "green": "a-green", "orange": "a-orange",
    "blue": "a-blue", "tx2": "a-steel",
}

SIMPLE = [
    ('<section class="hero" style="padding-block:clamp(40px,7vw,76px)">',
     '<section class="hero klein">'),
    ('<section class="hero" style="padding-block:clamp(36px,6vw,64px)">',
     '<section class="hero klein">'),
    ('<section class="hero" style="padding-block:clamp(56px,11vw,120px)">',
     '<section class="hero gross">'),
    ('<div class="hinweis" style="display:flex;flex-wrap:wrap;gap:14px 24px;'
     'align-items:center;justify-content:space-between">',
     '<div class="hinweis balken">'),
    ('<div class="hinweis" style="margin-top:26px;display:flex;flex-wrap:wrap;'
     'gap:14px 24px;align-items:center;justify-content:space-between">',
     '<div class="hinweis balken mt-l">'),
    ('<div class="hinweis" style="border-color:var(--coral)">',
     '<div class="hinweis warn">'),
    ('<p class="fuss-fein" style="border:0;padding:0;margin-top:10px">',
     '<p class="notiz">'),
    ('<div class="code" style="background:var(--panel)">', '<div class="code hell">'),
    ('<figure class="code" style="align-self:start">', '<figure class="code oben">'),
    ('<p class="dach" style="font-size:14px">', '<p class="dach klein">'),
    ('<p style="margin:0;max-width:60ch">', "<p>"),
    ('<p style="margin:0;max-width:58ch">', "<p>"),
    ('<p style="margin-bottom:18px">', '<p class="mb-m">'),
    ('<p style="margin:0">', '<p class="mb-0">'),
    ('<h2 style="margin-bottom:18px">', '<h2 class="mb-m">'),
    ('<figure class="figur reveal" style="margin-top:26px">',
     '<figure class="figur reveal mt-l">'),
    ('<ul class="bento reveal" style="margin-top:24px">',
     '<ul class="bento reveal mt-l">'),
    ('<ul class="bento" style="margin-top:22px">', '<ul class="bento mt-m">'),
    ('<ol class="strahl reveal" style="margin-top:24px">',
     '<ol class="strahl reveal mt-l">'),
    ('<div class="karten reveal" style="margin-top:26px">',
     '<div class="karten reveal mt-l">'),
    ('<div class="karten reveal" style="margin-top:24px">',
     '<div class="karten reveal mt-l">'),
    ('<div class="karten reveal" style="margin-top:22px">',
     '<div class="karten reveal mt-m">'),
    ('<div class="karten reveal" style="margin-top:20px">',
     '<div class="karten reveal mt-m">'),
    ('<div class="schichten reveal" style="margin-top:28px">',
     '<div class="schichten reveal mt-l">'),
    ('<div class="reveal" style="margin-top:26px">', '<div class="reveal mt-l">'),
    ('<div class="raster" style="margin-top:22px">', '<div class="raster mt-m">'),
    ('<p class="hinweis" style="margin-top:18px">', '<p class="hinweis mt-m">'),
    ('<p class="hinweis" style="margin-top:8px">', '<p class="hinweis mt-s">'),
    ('<p class="hinweis" style="margin-top:22px">', '<p class="hinweis mt-m">'),
    ('<p class="hinweis" style="margin-top:24px">', '<p class="hinweis mt-l">'),
    ('<p class="hinweis" style="margin-top:32px">', '<p class="hinweis mt-xl">'),
    ('<div class="hinweis" style="margin-top:16px">', '<div class="hinweis mt-m">'),
    ('<p class="dach" style="margin-top:18px">', '<p class="dach mt-m">'),
    ('<p class="dach" style="margin-top:20px">', '<p class="dach mt-m">'),
    ('<p class="dach" style="margin-top:22px">', '<p class="dach mt-m">'),
    ('<p class="dach" style="margin-top:28px">', '<p class="dach mt-l">'),
    ('<ul class="liste lang" style="max-width:78ch">', '<ul class="liste lang">'),
    ('<h2 style="margin-top:36px">', '<h2 class="mt-xl">'),
    ('<h2 style="margin-top:34px">', '<h2 class="mt-xl">'),
]


def main() -> int:
    for path in sorted(SEITEN.glob("*.html")):
        text = original = path.read_text(encoding="utf-8")
        for old, new in SIMPLE:
            text = text.replace(old, new)
        # style="--akz:var(--x)"  ->  class token
        def accent(m: re.Match) -> str:
            cls = ACCENT[m.group(2)]
            head = m.group(1)
            if 'class="' in head:
                return head.replace('class="', f'class="{cls} ', 1)
            return f'{head} class="{cls}"'
        text = re.sub(
            r'(<(?:a|li|section|div)\b[^>]*?) style="--akz:var\(--(\w+)\)"',
            accent, text,
        )
        if text != original:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"rewrote {path.name}")

    left = []
    for path in sorted(SEITEN.glob("*.html")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ' style="' in line:
                left.append(f"{path.name}:{n}: {line.strip()[:110]}")
    for row in left:
        print("REMAINS " + row, file=sys.stderr)
    print(f"\n{len(left)} inline style attribute(s) left.")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())
