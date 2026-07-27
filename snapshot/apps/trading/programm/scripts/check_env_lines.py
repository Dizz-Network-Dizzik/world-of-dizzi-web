r"""Zeigt die STRUKTUR der .env (nur Zeilennummer + Schluesselname, KEINE Werte).

Hilft, kaputte Zeilen zu finden (z. B. wenn ein eingefuegter Wert einen
Zeilenumbruch enthielt). Aufruf:
    .\.venv\Scripts\python.exe scripts\check_env_lines.py
"""

from pathlib import Path

env = Path(__file__).resolve().parents[1] / ".env"
if not env.exists():
    print("Keine .env gefunden.")
    raise SystemExit(0)

for i, raw in enumerate(env.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
    line = raw.strip()
    if not line:
        kind = "(leer)"
    elif line.startswith("#"):
        kind = "Kommentar"
    elif "=" in line:
        key = line.split("=", 1)[0].strip()
        val = line.split("=", 1)[1]
        kind = f"OK   Schluessel='{key}'  Wertlaenge={len(val)}"
    else:
        kind = ">>> PROBLEM: kein '=' in dieser Zeile (gehoert evtl. zur vorigen Zeile!)"
    print(f"Zeile {i:2}: {kind}")
