"""Dizz Communication — kompletter Nachrichtenverkehr (R2.2-Fundament, Architektur-KI).

HOCHSENSIBLE App (sensitivity hoechst): private Kommunikation bleibt lokal,
Inhalte gehen NIE an Cloud-Modelle, Senden ist IMMER eine HITL-Aktion.
Zwei-Schienen-Architektur (docs/RECHERCHE.md): E-Mail = risikofreier Kern
(IMAP/XOAUTH2, Microsoft killt Basic Auth 30.04.2026); Messenger folgen als
Webview (Schiene A) + Matrix/Bridges (Schiene B) auf demselben kanal-
agnostischen Schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: vendierte Kopie neben der App (Föderation).
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages", _here.parents[1], _here.parents[3]):  # parents[3]/packages = Monorepo (F1b)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
