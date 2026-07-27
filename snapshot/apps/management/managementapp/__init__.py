"""Dizz Management [MG] — die KI-Agenten-Verwaltung des Netzes (App-Vertrag-Paket).

★ Umdeklaration 03.07.2026 (Nutzer-Directive D13): Management ist nicht mehr als
Social-Media-App deklariert, sondern als **KI-Agenten-Verwaltung** — die Heimat der
Agenten-Regie (docs/58 VO-3/D5). Die heutige Social-Media-Funktion (Kanäle/Bots/
Posts/Zeitplan) ist die ERSTE Agenten-Domäne darunter; der Agenten-Ausbau (MG-1)
setzt hier auf. Marke bleibt „Dizz Management".

Kopier-Quelle: ``templates/refapp`` (K3). Diese App folgt dem modularen Muster von
Dizz Healthy: ``manifest.py`` (Identität), ``domain.py`` (Kanäle/Social-Bots/Posts/
Zeitplan), ``channels.py`` (ChannelSource-Adapter, Gesetz 5 dormant), ``ki.py``
(lokale KI) und ``main.py`` (Verdrahtung). Alles Vertragliche kommt aus dem
geteilten ``appkit`` (`packages/`, Single-Source).
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: zuerst die VENDIERTE Kopie neben der App
# (<app>/appkit, Föderation — App bleibt eigenständig), sonst die kanonische
# Quelle im Dizzi-Repo (Template-Betrieb/Entwicklung).
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages", _here.parents[1], _here.parents[3]):  # parents[3]/packages = Monorepo (F1b)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
