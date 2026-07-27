"""LOC-Zählung für das Faktenblatt (read-only, reproduzierbar).

Quelle der Zahlen in ``_netzwerk/businessplan/FAKTEN_ANKER.md`` — jede dort
genannte LOC-Zahl muss sich mit diesem Skript reproduzieren lassen.

Methode:
  * Dateimenge = ``git ls-files`` (nur versionierte Dateien; venvs/Build-Müll
    sind damit automatisch draußen).
  * LOC = physische Zeilen je Datei (wie ``wc -l``).
  * CODE = .py .js .mjs .ts .tsx .html .css .ps1 .sh .sql außerhalb von
    Test-Pfaden · TEST = gleiche Endungen in Test-Pfaden (``tests/``-Ordner,
    ``test_*``-Dateien, ``conftest.py``) · MD = .md (Doku, nachrichtlich).

Aufruf:  cd C:\\Dizzik\\code\\dizz-network && python ops\\loc_zaehlung.py
"""
from __future__ import annotations

import collections
import os
import subprocess

CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".html", ".css", ".ps1", ".sh", ".sql"}


def ist_test(pfad: str) -> bool:
    teile = pfad.split("/")
    name = teile[-1]
    return ("tests" in teile or "test" in teile
            or name.startswith("test_") or name.endswith("_test.py")
            or name == "conftest.py")


def bereich(pfad: str) -> str:
    p = pfad.split("/")
    if p[0] in ("apps", "packages") and len(p) > 1:
        return f"{p[0]}/{p[1]}"
    return p[0] if len(p) > 1 else "(root)"


def main() -> None:
    dateien = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                             encoding="utf-8").stdout.splitlines()
    # je Bereich: [code_loc, code_n, test_loc, test_n, md_loc, md_n]
    statistik = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0])

    for f in dateien:
        ext = os.path.splitext(f)[1].lower()
        if ext not in CODE_EXT and ext != ".md":
            continue
        try:
            with open(f, "rb") as fh:
                n = sum(1 for _ in fh)
        except OSError:
            continue
        b = statistik[bereich(f)]
        if ext == ".md":
            b[4] += n; b[5] += 1
        elif ist_test(f):
            b[2] += n; b[3] += 1
        else:
            b[0] += n; b[1] += 1

    summe = [0, 0, 0, 0, 0, 0]
    print(f"{'Bereich':<24}{'Code-LOC':>10}{'Dateien':>8}{'Test-LOC':>10}{'Dateien':>8}{'MD-LOC':>10}{'Dateien':>8}")
    for k in sorted(statistik):
        s = statistik[k]
        for i in range(6):
            summe[i] += s[i]
        print(f"{k:<24}{s[0]:>10,}{s[1]:>8}{s[2]:>10,}{s[3]:>8}{s[4]:>10,}{s[5]:>8}")
    print(f"{'GESAMT':<24}{summe[0]:>10,}{summe[1]:>8}{summe[2]:>10,}{summe[3]:>8}{summe[4]:>10,}{summe[5]:>8}")
    print(f"\nCode+Test = {summe[0] + summe[2]:,} LOC | Code ohne Tests = {summe[0]:,} LOC")


if __name__ == "__main__":
    main()
