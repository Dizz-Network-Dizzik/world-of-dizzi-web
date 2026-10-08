#!/usr/bin/env python3
"""One-off, 08.10.2026 (late evening): admit the words the extended Journey timeline uses.
Eight dated nodes joined /journey/ (27 July to 8 October 2026), each hanging on a commit of
this repository or on one of the house's other public repositories. The gate did not know
some ordinary English words those nodes use.

Same ritual as the scripts before it: the gate names what it does not know, a person reads
every word, and this script appends exactly that list under a dated header. Read on
08.10.2026, 23:1x: ordinary English words and one month name, no misspelling, no name.

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
KOPF = "# 2026-10-08 — Journey-Timeline bis Oktober (acht Knoten; jedes Wort vor der Aufnahme gelesen)"
ERWARTET = {"de": set(),
            "en": {"blocklist", "comparing", "covers", "decimal", "delivery", "discovered", "evening", "faults",
                   "forwards", "governance", "hit", "October", "repositories", "reworded", "screens", "switch",
                   "toolkit", "turned", "twin", "watches", "Wording", "commit", "libraries", "licence", "nodes"}}

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
    fremd = {w for w in woerter if w.casefold() not in {e.casefold() for e in ERWARTET[sprache]}}
    if fremd:
        print(f"{sprache}: STOPP - unerwartete Wörter, nichts geschrieben: {sorted(fremd)}")
        sys.exit(2)
    print(f"Schreibe: {LISTEN[sprache]}  ->  {woerter}")
    with LISTEN[sprache].open("a", encoding="utf-8") as f:
        f.write("\n" + KOPF + "\n" + "\n".join(sorted(woerter, key=str.casefold)) + "\n")
    print(f"{sprache}: {len(woerter)} Wörter aufgenommen -> {LISTEN[sprache].name}")
