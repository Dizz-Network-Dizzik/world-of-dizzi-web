#!/usr/bin/env python3
"""One-off, 10.09.2026 (WA 173): admit the vocabulary of /dank/ and the README's Thanks section.

Same ritual as the day before (woerter_ergaenzen_2026-09-09.py): the gate names what it does
not know, a person reads every word, and this script appends exactly that list under a dated
header. Read on 10.09.2026: 48 German words of the thanks page (all ordinary words - "Dank",
"Geduld", "Kreis", "Herkunftsangabe"), 42 English words of the README section (plus three
path names, dank / deckel / kinder, that stand in English sentences). None is a misspelling.

Run once, from the repository root. Safe to re-run: known words are not reported again.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = {"de": ROOT / "pruefung" / "woerter_de.txt",
          "en": ROOT / "pruefung" / "woerter_en.txt"}
KOPF = "# 2026-09-10 WA 173 — /dank/ + README „Thanks“ (jedes Wort vor der Aufnahme gelesen)"

roh = subprocess.run([sys.executable, str(ROOT / "pruefung" / "proofread.py"), "--unbekannt"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
neu = {"de": [], "en": []}
for zeile in roh.splitlines():
    m = re.match(r"^(de|en)\t\d+\t(\S+)\s*$", zeile)
    if m and m.group(2) not in neu[m.group(1)]:
        neu[m.group(1)].append(m.group(2))

for sprache, woerter in neu.items():
    if not woerter:
        print(f"{sprache}: nichts Neues")
        continue
    print(f"Schreibe: {LISTEN[sprache]}")
    with LISTEN[sprache].open("a", encoding="utf-8") as f:
        f.write("\n" + KOPF + "\n" + "\n".join(sorted(woerter, key=str.casefold)) + "\n")
    print(f"{sprache}: {len(woerter)} Wörter aufgenommen -> {LISTEN[sprache].name}")
