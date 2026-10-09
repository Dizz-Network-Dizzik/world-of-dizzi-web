#!/usr/bin/env python3
"""One-off, 09.10.2026: admit the words the two DizzCube pages (/dizzcube/, /de/dizzcube/), the band on the two start
pages and the new privacy paragraph use. The gate did not know them: ordinary words about a falling-block game on a
cube - pieces, edges, rotate, arrow keys, touchscreen, levels - plus the game's own name, two level names and two
words from the address of the game page.

Same ritual as the scripts before it: the gate names what it does not know, a person reads every word, and this script
appends exactly that list under a dated header. Read on 09.10.2026, 09:1x: sixty-six ordinary German words,
forty-one ordinary English words, no misspelling, no person's name.

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
KOPF = "# 2026-10-09 — DizzCube: Seiten /dizzcube/ + /de/dizzcube/, Band der Startseiten, Datenschutz §2 (jedes Wort vor der Aufnahme gelesen)"
ERWARTET = {
    "de": {"abgeräumt", "ausnahmen", "behalten", "danach", "dimensionen", "dizzcube", "dreht", "eingegebener",
           "erweiterung", "fallen", "fallende", "fallenlassen", "farbe", "flugmodus", "fläche", "gedacht",
           "gekennzeichneten", "gespeichert", "gespielt", "gewählten", "geöffnet", "herunterladen", "html", "hälfte",
           "kanten", "kantenzelle", "konto", "kopiert", "laden", "linke", "nachbarseite", "nachgeladen", "nimmt",
           "pfeiltasten", "platz", "play", "punktestände", "seitlich", "sekunden", "senkrechten", "sofort", "solange",
           "spiel", "spielbar", "spielen", "spielername", "spielfeld", "spiels", "steckt", "stein", "steinen", "stufen",
           "tastatur", "tippen", "touchscreen", "uhrzeigersinn", "verlassen", "volle", "vorschau", "wischen", "wohnt",
           "wählen", "würfel", "würfels", "zugleich", "zurück"},
    "en": {"afterwards", "arrow", "board", "chose", "cleared", "clears", "clockwise", "comes", "cube", "dimensions",
           "dizzcube", "download", "drops", "edges", "extension", "extra", "falling", "falls", "game", "journeyman",
           "levels", "lightning", "loaded", "lock", "locks", "neighbour", "pauses", "piece", "pieces", "play",
           "playable", "played", "release", "rotate", "rotates", "scores", "seconds", "softly", "spins", "thinking",
           "vertical"},
}

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
