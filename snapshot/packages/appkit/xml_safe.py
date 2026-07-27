"""Sicheres XML-Parsen ohne DTD/Entities — EIN Schutz für ALLE XML-Importe im
Netz (Dizz News OPML, Dizz Money camt.053 …), docs/50 P4.1.

Bedrohung: **Billion-Laughs** (interne Entity-Expansion sprengt RAM/CPU) UND
**XXE** (externe Entity liest Dateien / macht Netz-Requests). BEIDE brauchen
ZWINGEND eine ``<!DOCTYPE …>`` mit ``<!ENTITY …>``. Wir weisen deshalb jede
DTD/Entity-Deklaration KOMPLETT ab (ASCII-Marker, NUL-Strip ⇒ greift auch bei
UTF-16) — **dependency-frei** (``defusedxml`` ist im Netzwerk-venv NICHT
vorhanden; der stdlib-``ElementTree`` expandiert sonst interne Entities). Ohne
DTD löst der Parser danach keinerlei Entities mehr auf.

Single-Source (kein Vendoring): liegt EINMAL hier; News/Money/künftige Importer
rufen denselben Schutz — ein Fix wirkt netzweit, kein Drift zwischen Kopien.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


class UnsicheresXml(ValueError):
    """XML mit DTD/Entity-Deklaration — abgewiesen (XXE/Billion-Laughs-Schutz)."""


def pruefe_keine_dtd(raw: bytes | str) -> bytes:
    """Weist DTD/``<!ENTITY>``-Deklarationen ab und gibt die Bytes zurück (bytes ⇒
    der Parser respektiert die XML-Encoding-Deklaration). Wirft ``UnsicheresXml``."""
    roh = raw.encode("utf-8") if isinstance(raw, str) else raw
    # NUL-Strip ⇒ auch UTF-16/UTF-32-kodierte Marker werden ASCII-sichtbar.
    probe = roh.replace(b"\x00", b"").decode("ascii", "ignore").lower()
    if "<!doctype" in probe or "<!entity" in probe:
        raise UnsicheresXml("DTD/Entity-Deklarationen sind nicht erlaubt "
                            "(Schutz gegen XXE / Billion-Laughs)")
    return roh


def sichere_wurzel(raw: bytes | str) -> ET.Element:
    """Geprüfte XML-Wurzel: erst DTD/Entities abweisen, dann stdlib-Parse.
    ``ET.ParseError`` (kaputtes XML) reicht der Aufrufer wie gewohnt durch."""
    return ET.fromstring(pruefe_keine_dtd(raw))
