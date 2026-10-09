#!/usr/bin/env python3
"""One-off, 09.10.2026: admit the words the use-case block (/apps/ "What you can do with it - five things", /de/ "Was man
damit tun kann - fuenf Dinge") and the five "In short" boxes (journey, numbers, system, method, apps) use. The texts
come word for word from the review proposal of the evening before (D1, E1-E5); the gate did not know some ordinary
words they use.

Same ritual as the scripts before it: the gate names what it does not know, a person reads every word, and this script
appends exactly that list under a dated header. Read on 09.10.2026, 08:3x: ten ordinary English words, twenty-one
ordinary German words, no misspelling, no name.

Run once, from anywhere (paths are resolved from this file). Safe to re-run: known words are not reported again.
Stops without writing if the gate names a word that is not on the list below.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = {"de": ROOT / "pruefung" / "woerter_de.txt",
          "en": ROOT / "pruefung" / "woerter_en.txt"}
KOPF = "# 2026-10-09 — Use-Case-Block (/apps/, /de/) und In-short-Kästen (journey, numbers, system, method, apps) (jedes Wort vor der Aufnahme gelesen)"
ERWARTET = {"de": {"ablegen", "ausgewählten", "bewegt", "Budgets", "Cent", "durchsuchen", "einfache", "Ereignis",
                   "führen", "geordnet", "holen", "Kontodaten", "Lebensbereich", "Messenger", "Neuigkeiten", "Notizen",
                   "Papierkram", "Sektoren", "sortieren", "Termine", "vorbereiten"},
            "en": {"breaking", "case", "filings", "happen", "picked", "plans", "prepare", "sale", "sorted", "yes"}}

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
