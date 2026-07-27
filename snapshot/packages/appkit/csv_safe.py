"""CSV-Formel-Injection-Schutz (netzwerkweit, Audit-Runde 3).

Ein CSV-Zellwert, der mit ``=``, ``+``, ``-``, ``@`` (oder Tab/CR) beginnt, wird von
Excel/LibreOffice Calc beim Öffnen als **Formel** ausgeführt. Die Steuer-/Geschäfts-
Exporte des Netzwerks (EÜR, Buchungen, Trading-Steuer, GoBD-Rechnungen) gehen an
**Dritte** (Finanzamt, Steuerberater) ⇒ ein Freitext-Feld (Kategorie/Gegenpartei/Notiz)
darf dort nie als Formel landen. OWASP-Mitigation: ein führender Apostroph entschärft
die Zelle, ohne den sichtbaren Text zu verändern.

Nur auf FREITEXT-Felder anwenden (Beträge/Daten sind kontrolliert).
"""

from __future__ import annotations

from typing import Any

_GEFAEHRLICH = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(val: Any) -> str:
    """Entschärft einen CSV-Zellwert gegen Formel-Injection (führender Apostroph,
    wenn der Wert mit einem Formel-/Steuerzeichen beginnt). ``None`` ⇒ ``""``."""
    s = str(val if val is not None else "")
    return ("'" + s) if s[:1] in _GEFAEHRLICH else s
