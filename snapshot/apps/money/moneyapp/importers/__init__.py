"""Universeller Import — Bank-/Konto-Bewegungen → Ledger-Buchungen (Bau-KI-Fill A).

Jedes Format ist ein EIGENES, reines Modul (keine DB, keine HTTP-Abhängigkeit):

- ``csv_import``  — tolerantes CSV mit Spalten-Profilen (DE/EN Dezimal + Datum).
- ``camt``       — camt.053 (ISO-20022-XML, nur stdlib ``xml.etree``).
- ``mt940``      — SWIFT MT940 (:20:/:25:/:61:/:86:).

Alle liefern dieselbe Zwischenform ``Bewegung`` (siehe ``common``). Die App
(``moneyapp.main``) macht aus jeder Bewegung GENAU EINE doppelte Buchung
(Bankkonto ↔ Sammelkonto „Nicht zugeordnet") und entdoppelt über den stabilen
``bewegung_hash`` — so erzeugt ein erneuter Import desselben Auszugs keine
Dubletten. Der Buchungs-Kern (``ledger``) bleibt die einzige Stelle mit
Geld-Mathematik; die Parser reichen nur ganzzahlige Minor-Units weiter.
"""

from __future__ import annotations

from .common import (Bewegung, ImportFehler, als_buchung, bewegung_hash,
                     parse_dezimal, parse_datum)
from .dispatch import FORMATE, parse_inhalt

__all__ = [
    "Bewegung", "ImportFehler", "als_buchung", "bewegung_hash", "parse_dezimal",
    "parse_datum", "FORMATE", "parse_inhalt",
]
