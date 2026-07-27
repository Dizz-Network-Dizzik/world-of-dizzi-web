"""Pytest-Bootstrap für Dizz News.

``appkit``/``ui-kit`` liegen seit dem De-Vendoring geteilt in ``../../packages``
(Single-Source). pytest importiert ``conftest.py`` VOR den Test-Modulen — daher
legen wir ``packages/`` hier auf ``sys.path``, sodass ``from appkit import …`` am
Modulkopf der Tests greift, OHNE dass man ``PYTHONPATH`` von Hand setzen muss.
``python -m pytest -q`` läuft damit direkt aus ``apps/news`` (oder dem Repo-Root).
"""

import sys
from pathlib import Path

_packages = Path(__file__).resolve().parents[2] / "packages"
if _packages.is_dir() and str(_packages) not in sys.path:
    sys.path.insert(0, str(_packages))
