"""Dizz Money — Finanzmanagement mit eigenem Double-Entry-Ledger (R2.2+).

Schwester-App auf dem App-Vertrag (Kopie der refapp-Vorlage). Eigenständig +
verkaufbar; im Verbund per Dizzi-ID/SSO + MCP + Dashboard-Kachel + Dizz Defense.

Der Buchhaltungs-Kern (``ledger.py``) ist die EINE Stelle mit erhöhter
Sorgfaltspflicht (Fragerunde 3, F-Q1): Beträge als ganzzahlige Minor-Units
(nie Float), doppelte Buchführung mit harter Invariante Summe = 0, Property-
getestet. Bank-Anbindung (AISP/FinTS), Import, Budgets = späterer Bau-KI-Fill.
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
