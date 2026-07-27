"""Dizz Admin [AD] — vereinte Verwaltungs-App des Netzwerks (Bereiche · Tresor ·
Projekte · Geschäft · Studium · Fristen; Plans+Admin+Leading verschmolzen, docs/28).

Eigenständige Netzwerk-App (the world of dizzi). Bereichs-zentriert: eine typisierte
Kontext-Achse (Studium/Geschäft/Mandant …), an der alle Module kategorisiert hängen.
Enthält die GoBD-Geschäftsführung (Kunden/Produkte/Rechnungen append-only/Fristen/
Support/KPIs) + Aggregator (konsumiert die Schwester-Apps read-only über den Core,
statt zu doppeln). Basis-Repo `leading` (Paket hier ``adminapp``), id `admin`, :8222.

Vertragliches (Summary/Settings/Account/Datenrechte/Defense/Mini-Dizzi) kommt aus
dem vendierten ``appkit`` (READ-ONLY, Vertrag 1.5). SENSIBEL (``sensitivity='hoch'``):
Geschäfts-/Steuer-/Studien-Daten lokal, KI lokal-first; Tresor-Fächer zusätzlich
verschlüsselbar (docs/28 §6).
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

# appkit auffindbar machen: zuerst die VENDIERTE Kopie neben der App
# (<leading>/appkit — Föderation), sonst die kanonische Quelle im Dizzi-Repo.
_here = Path(__file__).resolve()
for _cand in (_here.parents[3] / "packages", _here.parents[1], _here.parents[3]):  # parents[3]/packages = Monorepo (F1b)
    if (_cand / "appkit" / "__init__.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break
