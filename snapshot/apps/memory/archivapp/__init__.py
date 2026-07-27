"""Dizz Memory — Wissensspeicher (Notizen · Archiv · Langzeitgedächtnis).

Schwester-App im Netzwerk „the world of dizzi", aufgesetzt aus der refapp-Vorlage
des App-Vertrags (docs/16). Eigenständig + einzeln verkaufbar; im Verbund per
Dizzi-ID/SSO, MCP-Server (Namensraum ``memory_``) und Dashboard-Kachel verbunden.

Kern (REV-5, docs/11 §5b): **Markdown-Vault** als kanonisches, portables
Speicherformat (Obsidian-kompatibel, kein DB-Lock-in) + abgeleiteter SQLite-/
FTS-Index für Suche und die Vertrags-Konventionen. Ordner (hierarchisch) +
Labels (Cross-Verweise) + KI-gestützte Suche; die App-KI antwortet quellen-
gestützt aus den eigenen Notizen (Mini-Dizzi-Slot).

Hinweis Namensgebung: der **Projekt-/Ordnername bleibt ``archiv``** (REV-5: harte
Umbenennung = R-STRUKTUR-Migration), die **Netzwerk-/Manifest-id ist ``memory``**
(damit MCP-Tools im Namensraum ``memory_<tool>`` liegen, docs/16 §6).
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: vendierte Kopie neben der App (Föderation). Wie im
# News-/refapp-Muster — parents[1] = der App-Ordner (enthält appkit/), parents[3]
# = die kanonische Quelle im Dizzi-Repo (Entwicklung ohne Vendoring).
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages", _here.parents[1], _here.parents[3]):  # parents[3]/packages = Monorepo (F1b)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
