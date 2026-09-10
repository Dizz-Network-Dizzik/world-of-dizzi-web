#!/usr/bin/env python3
"""One-off, 09.09.2026 (WA 172): admit the vocabulary of /deckel/ and /deckel/kinder/.

The language gate is a whitelist. Two new German pages bring roughly 330 ordinary
German words the site had never used before - "Antwort", "Kinder", "Mama", "Rad",
"Topf" - plus the names of the thinkers and three transliterations (śūnya, ṣifr,
zephirum). Every word in the gate's own --unbekannt list was read by a person
before this ran; none is a misspelling. This script asks the gate, not a memory of
it, and appends what it names under a dated header - the same ritual as every
page before, only in one motion instead of by hand.

Run once, from the repository root. Safe to re-run: words already known are not
reported by the gate and therefore not appended twice.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = {"de": ROOT / "pruefung" / "woerter_de.txt",
          "en": ROOT / "pruefung" / "woerter_en.txt"}
KOPF = "# 2026-09-09 WA 172 — /deckel/ + /deckel/kinder/ (Vokabular der zwei Seiten; jedes Wort vor der Aufnahme gelesen)"

roh = subprocess.run([sys.executable, str(ROOT / "pruefung" / "proofread.py"), "--unbekannt"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
neu = {"de": [], "en": []}
for zeile in roh.splitlines():
    # --unbekannt prints one word per line, tab-separated and lower-cased:
    # "de<TAB>1<TAB>achse". The lists hold words lower-cased too.
    m = re.match(r"^(de|en)\t\d+\t(\S+)\s*$", zeile)
    if m and m.group(2) not in neu[m.group(1)]:
        neu[m.group(1)].append(m.group(2))

for sprache, woerter in neu.items():
    if not woerter:
        print(f"{sprache}: nichts Neues")
        continue
    with LISTEN[sprache].open("a", encoding="utf-8") as f:
        f.write("\n" + KOPF + "\n" + "\n".join(sorted(woerter, key=str.casefold)) + "\n")
    print(f"{sprache}: {len(woerter)} Wörter aufgenommen -> {LISTEN[sprache].name}")
