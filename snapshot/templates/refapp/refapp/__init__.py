"""Referenz-App des App-Vertrags (K3) — Kopier-Quelle für jede neue Netzwerk-App.

Beim Kopieren in einen App-Ordner: Paket umbenennen (z. B. ``money``),
Manifest anpassen, Domänen-Schema/-Routen ersetzen. Anleitung: ../README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: zuerst die VENDIERTE Kopie neben der App
# (<app>/appkit, Föderation — App bleibt eigenständig), sonst die kanonische
# Quelle im Dizzi-Repo (Template-Betrieb/Entwicklung).
_here = Path(__file__).resolve()
for _cand in (_here.parents[1], _here.parents[3]):
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
