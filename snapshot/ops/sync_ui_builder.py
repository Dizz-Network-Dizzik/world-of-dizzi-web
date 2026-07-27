"""Vendort das »UI Builder Tool« (vormals Panel-Bautool) aus der kanonischen
Quelle in alle App-`ui-kit`-Ordner, Core, den Trading Bot UND den dedizierten
Standalone-Ordner `C:\\Dizzik\\code\\ui-builder-tool`.

Kanonische Quelle der Wahrheit: `the world of dizzi/tools/ui-builder-tool.{html,js}`.
Das Tool besteht aus ZWEI Dateien (html + js, seit dem CSP-Fix v14) und wird
IMMER ZUSAMMEN vendort. Dieses Skript kopiert sie, entfernt stale Alt-Namen
(`panel-builder.{html,js}`) und erkennt Drift (md5/sha256) — analog
`ops/sync_appkit.py`.

WICHTIG — Serving-Modell (für die Live-Wirkung):
- Die 8 Apps (admin/creator/finanzen/health/kommunikation/news/social-media) +
  buerokratie/projekte servieren `/ui-kit` als generischen StaticFiles-Mount ⇒
  ein Datei-Rename greift **disk-served ohne Neustart**.
- ARCHIV (Memory), CORE und der TRADING BOT servieren `/ui-kit` über eine
  Allowlist-Route mit HARTKODIERTEN Dateinamen (`archivapp/main.py`,
  `core/app/main.py`, TB `backend/app/main.py`). Dort muss der Allowlist-Eintrag
  die neuen Namen führen UND der Dienst gegated neu gestartet werden, sonst 404.

Abgewickelte Repos `buerokratie`/`projekte` werden NICHT bespielt (Bestand).

Aufrufe (venv-Python, aus dem Repo-Ordner `the world of dizzi`):
    python ops/sync_ui_builder.py --all      # alle Ziele vendoren
    python ops/sync_ui_builder.py --to ../news/ui-kit
    python ops/sync_ui_builder.py --check     # Drift-Prüfung ALLER Ziele (CI-tauglich)
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # the world of dizzi
ROOT = REPO.parent                                  # C:\Dizzik\code
SRC = REPO / "tools"
TOOL_FILES = ("ui-builder-tool.html", "ui-builder-tool.js")
STALE = ("panel-builder.html", "panel-builder.js")  # Alt-Namen, beim Sync entfernen
STAMP = "_UI_BUILDER_VENDORED.txt"

# Vendor-Ziele = alle ui-kit-Ordner, die das Tool tragen, + der Standalone-Ordner.
TARGETS = [
    REPO / "core" / "ui-kit",
    ROOT / "admin" / "ui-kit",
    ROOT / "archiv" / "ui-kit",
    ROOT / "creator" / "ui-kit",
    ROOT / "finanzen" / "ui-kit",
    ROOT / "health" / "ui-kit",
    ROOT / "kommunikation" / "ui-kit",
    ROOT / "news" / "ui-kit",
    ROOT / "social-media" / "ui-kit",
    ROOT / "Trading Bot eins" / "programm" / "backend" / "app" / "static" / "ui-kit",
    ROOT / "ui-builder-tool",                       # dedizierte Standalone-Form
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _src_digest() -> str:
    h = hashlib.sha256()
    for name in TOOL_FILES:
        h.update(name.encode())
        h.update((SRC / name).read_bytes())
    return h.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unbekannt"


def sync(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in TOOL_FILES:
        (target / name).write_bytes((SRC / name).read_bytes())
    entfernt = []
    for name in STALE:
        alt = target / name
        if alt.is_file():
            alt.unlink()
            entfernt.append(name)
    (target / STAMP).write_text(
        f"UI Builder Tool · Quelle {_git_head()} · sha256 {_src_digest()}\n"
        "Kanonische Quelle: the world of dizzi/tools/ui-builder-tool.{html,js}\n"
        "NICHT hier editieren — dort aendern und mit ops/sync_ui_builder.py neu vendoren.\n",
        encoding="utf-8")
    extra = f"  (stale entfernt: {', '.join(entfernt)})" if entfernt else ""
    print(f"OK  {target}{extra}")


def check(target: Path) -> bool:
    ok = True
    for name in TOOL_FILES:
        f = target / name
        if not f.is_file():
            print(f"FEHLT  {f}")
            ok = False
        elif _sha(f) != _sha(SRC / name):
            print(f"DRIFT  {f} (Inhalt != Master)")
            ok = False
    for name in STALE:
        if (target / name).is_file():
            print(f"STALE  {target / name} (Alt-Name noch vorhanden)")
            ok = False
    if ok:
        print(f"OK  {target}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="alle Ziele vendoren")
    ap.add_argument("--to", type=Path, help="ein einzelnes ui-kit-Ziel vendoren")
    ap.add_argument("--check", action="store_true", help="Drift-Pruefung ALLER Ziele")
    args = ap.parse_args()

    for name in TOOL_FILES:
        if not (SRC / name).is_file():
            print(f"FEHLER: Master fehlt: {SRC / name}")
            return 2

    if args.check:
        return 0 if all(check(t) for t in TARGETS) else 1
    if args.to:
        sync(args.to)
        return 0
    if args.all:
        for t in TARGETS:
            sync(t)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
