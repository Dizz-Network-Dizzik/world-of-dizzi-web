"""RRULE-light — **verschoben nach ``packages/appkit/recurrence.py``** (netzweit
geteilt, docs/50 P2.2): Dizz Admin UND Dizz Money teilen jetzt EINEN Kalender-
Kern (Single-Source, kein Vendoring). Dieses Modul ist nur noch ein Re-Export,
damit ``from . import recurrence`` / ``adminapp.recurrence`` unverändert tragen.
"""

from __future__ import annotations

from appkit.recurrence import (  # noqa: F401  (Re-Export)
    FREQS,
    expandiere,
    ist_gueltig,
    naechste_faellig,
    parse_rule,
    schritt_kalender,
)
