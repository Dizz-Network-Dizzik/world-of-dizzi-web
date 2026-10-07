#!/usr/bin/env python3
"""One-off, 08.10.2026: admit the vocabulary of the new section 6 of the privacy page
(seiten/datenschutz.html - the Instagram profile, worded on the house's legal review of the
same night).

Same ritual as the four scripts before it (woerter_ergaenzen_2026-09-09.py, _2026-09-10.py,
_2026-09-10b.py, _2026-09-10c.py): the gate names what it does not know, a person reads every
word, and this script appends exactly that list under a dated header. Read on 08.10.2026,
01:3x: twenty-two German words and names - Anlehnung, antworten, Avenue, beruhen, betreiben,
Block, Europäischen, Facebook, Fanpages, gehe, Gerichtshofs, Ihnen, Insoweit, Kommentare,
Metas, Profilnamen, Rechtsprechung, Serpentine, Soweit, Verantwortlichkeit, welchen, Zwecken -
all ordinary words or the address and name of the network operator, no misspelling.

Run once, from anywhere (paths are resolved from this file). Safe to re-run: known words
are not reported again.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = {"de": ROOT / "pruefung" / "woerter_de.txt",
          "en": ROOT / "pruefung" / "woerter_en.txt"}
KOPF = "# 2026-10-08 — /datenschutz/, Abschnitt 6 Instagram-Profil (Rechtswache derselben Nacht; jedes Wort vor der Aufnahme gelesen)"

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
    print(f"Schreibe: {LISTEN[sprache]}  ->  {woerter}")
    with LISTEN[sprache].open("a", encoding="utf-8") as f:
        f.write("\n" + KOPF + "\n" + "\n".join(sorted(woerter, key=str.casefold)) + "\n")
    print(f"{sprache}: {len(woerter)} Wörter aufgenommen -> {LISTEN[sprache].name}")
