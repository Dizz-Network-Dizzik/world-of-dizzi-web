import sys
from pathlib import Path

# App-Wurzel (Paket ``healthapp``) in den Pfad.
_app_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_app_dir))

# Monorepo (dizz-network): ``appkit``/``ui-kit`` liegen geteilt in ``packages/``
# (Single-Source, kein Vendoring) — diese auffindbar machen, damit der dokumentierte
# Test-Befehl ``pytest -q`` ohne extra PYTHONPATH läuft. Alt-Layout (vendiert neben
# der App) bleibt unterstützt; Einfügen ist idempotent.
for _cand in (_app_dir, *_app_dir.parents):
    _pkgs = _cand / "packages"
    if (_pkgs / "appkit" / "__init__.py").is_file():
        if str(_pkgs) not in sys.path:
            sys.path.insert(0, str(_pkgs))
        break
