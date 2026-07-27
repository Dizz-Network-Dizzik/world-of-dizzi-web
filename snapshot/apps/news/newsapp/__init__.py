"""Dizz News — kompakter, quellen-kuratierter Nachrichten-Überblick (R2.1).

Erste echte Schwester-App auf dem App-Vertrag (Kopie der refapp-Vorlage).
Eigenständig + verkaufbar; im Verbund per Dizzi-ID/SSO + MCP + Dashboard-Kachel.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen, ohne externes PYTHONPATH: heute liegt es geteilt in
# ``<monorepo>/packages`` (Single-Source, De-Vendoring); historisch auch neben der
# App / im Repo-Wurzel (vendiert). Erst-Treffer gewinnt.
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages",   # dizz-network/packages (Monorepo)
              _here.parents[1],                # apps/news (alte Vendier-Lage)
              _here.parents[3]):               # dizz-network (alte Vendier-Lage)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
