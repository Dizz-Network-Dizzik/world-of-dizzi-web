"""Per-App-Spiegel / Export — aus dem Monorepo je App ein EIGENSTÄNDIGES, weitergebbares
Bundle erzeugen (Backup-Eigenständigkeit + Einzel-App-Distribution, docs/44).

Pro App entsteht unter ``C:\\Dizzik\\data\\_backups\\mirrors\\<id>``:
  - der App-Code MIT eigener git-Historie (``git subtree split --prefix=apps/<id>``),
  - dazu gebündelt ``appkit/`` + ``ui-kit/`` (aus ``packages/``) ⇒ self-contained lauffähig,
  - ``_STANDALONE.md`` (Start-Hinweis).
Das Bundle ist ein eigenständiges git-Repo (App-Historie + Bundle-Commit) ⇒ direkt
weitergebbar (Dizzi-ID-fähig, da das appkit-Connector-/Vertrags-Gerüst mitkommt).

Läuft in den großen Check-/Backup-Runden. Idempotent (re-run frischt auf).
Aufruf:  python ops/mirror_export.py [--only <id>]

Core (Shell-Frontend an der Monorepo-Wurzel) + Trading (eigener Stack) = Sonderfälle,
bewusst NICHT in diesem v1 (eigene Behandlung).
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys, datetime
from pathlib import Path

MONO = Path(__file__).resolve().parents[1]                 # ...\dizz-network
OUT  = Path(r"C:\Dizzik\data\_backups\mirrors")
APPS = ["news", "money", "communication", "creating", "memory", "management", "healthy", "admin"]


def git(*args, cwd=MONO, check=True) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], text=True, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (cwd={cwd}):\n{r.stderr.strip()}")
    return (r.stdout or "").strip()


def export_app(app_id: str) -> str:
    prefix = f"apps/{app_id}"
    if not (MONO / prefix).is_dir():
        return f"SKIP (kein {prefix})"
    # 1) eigenständige Historie der App herauslösen (rewrite, als läge sie immer an der Wurzel)
    sha = git("subtree", "split", f"--prefix={prefix}")
    mirror = OUT / app_id
    mirror.mkdir(parents=True, exist_ok=True)
    if not (mirror / ".git").exists():
        git("init", "-q", cwd=mirror)
        git("config", "user.email", "308303970+Dizz-Network-Dizzik@users.noreply.github.com", cwd=mirror)
        git("config", "user.name", "world of dizzi", cwd=mirror)
    # 2) den Split-Stand in den Spiegel holen (volle App-Historie)
    git("fetch", "-q", str(MONO), sha, cwd=mirror)
    git("reset", "--hard", "-q", "FETCH_HEAD", cwd=mirror)
    # 3) geteilte Deps bündeln -> self-contained
    for pkg in ("appkit", "ui-kit"):
        dst = mirror / pkg
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(MONO / "packages" / pkg, dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # 4) Start-Hinweis + Bundle-Commit
    (mirror / "_STANDALONE.md").write_text(
        f"# {app_id} — eigenständiges Bundle (aus dizz-network, {datetime.date.today()})\n\n"
        "Self-contained: App-Code (mit eigener Historie) + gebündeltes `appkit/` + `ui-kit/`.\n"
        "Start (Beispiel): `set PYTHONPATH=%CD%` dann uvicorn der App; appkit/ui-kit liegen als\n"
        "Schwestern ⇒ `appkit.ui_kit_path()` findet `ui-kit/` automatisch. Dizzi-ID-Anbindung via\n"
        "appkit-Connector-Gerüst. Erzeugt von `ops/mirror_export.py`.\n", encoding="utf-8")
    git("add", "-A", cwd=mirror)
    if git("status", "--porcelain", cwd=mirror):
        git("commit", "-q", "-m",
            f"mirror/export {datetime.date.today()}: {app_id} standalone (+ appkit + ui-kit) aus dizz-network {sha[:8]}",
            cwd=mirror)
    n = git("rev-list", "--count", "HEAD", cwd=mirror)
    return f"OK  {mirror}  (split {sha[:8]}, {n} commits)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="nur diese App-id")
    args = ap.parse_args()
    targets = [args.only] if args.only else APPS
    OUT.mkdir(parents=True, exist_ok=True)
    for a in targets:
        print(f"  {a:13} -> {export_app(a)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
