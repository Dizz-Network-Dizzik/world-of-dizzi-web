"""Dizz Healthy [HE] — Gesundheits-Watching (Vitalwerte · Supplements · Verletzungen
· Training · Termine).

Eigenständige Netzwerk-App (the world of dizzi): einzeln lauffähig + verkaufbar,
im Verbund über Dizzi-ID (SSO), App-Vertrag (appkit) und MCP angebunden.
Entstanden durch Kopieren der Referenz-App (``templates/refapp``) — alles
Vertragliche kommt aus dem vendierten ``appkit`` (READ-ONLY, Vertrag 1.5/appkit 1.6).

HOCHSENSIBEL: Gesundheitsdaten bleiben strikt lokal (Manifest ``sensitivity='hoechst'``
⇒ KI-Routing ``lokal_only``, niemals Cloud-/Boost-Modell). Wearable/Smartwatch ist
über das ``HealthSource``-Interface umfangreich VORBEREITET (Gesetz 5), in v1 aber
nicht gebaut: manuelle Eingabe + lokale KI-Auswertung ist der v1-Kern.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: zuerst die VENDIERTE Kopie neben der App
# (<health>/appkit — Föderation, App bleibt eigenständig), sonst die
# kanonische Quelle im Dizzi-Repo (Entwicklungsbetrieb).
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages", _here.parents[1], _here.parents[3]):  # parents[3]/packages = Monorepo (F1b)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
