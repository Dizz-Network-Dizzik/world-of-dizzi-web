"""Format-Dispatcher: wählt den richtigen Parser für einen Auszug.

Hält die drei Format-Parser hinter EINER Funktion ``parse_inhalt(inhalt,
format, ...)`` zusammen, damit der HTTP-Endpoint (``POST /api/import``) nur ein
Format-Kürzel weiterreicht. ``format='auto'`` rät anhand des Inhalts (XML-
Signatur → camt; ``:20:``/``:61:`` → MT940; sonst CSV)."""

from __future__ import annotations

import re

from .common import Bewegung, ImportFehler
from .camt import parse_camt
from .csv_import import PROFILE, parse_csv
from .mt940 import parse_mt940

FORMATE = ("csv", "camt", "mt940", "auto")


def erkenne_format(inhalt: str) -> str:
    """Heuristische Format-Erkennung (für ``format='auto'``)."""
    kopf = inhalt.lstrip("﻿").lstrip()[:400]
    kopf_l = kopf.lower()
    if kopf.startswith("<?xml") or "<document" in kopf_l or "bktocstmrstmt" in kopf_l:
        return "camt"
    # MT940: ein :tag: am ZEILENANFANG (:20:/:25:/:28C:/:61:). M-11: Zeilenanker statt
    # Substring — sonst matchte eine CSV-Zeitspalte "14:25:10" (enthält ':25:') und die
    # CSV wurde fälschlich als MT940 geparst (→ harter "kein :61:"-Fehler statt CSV).
    erste = inhalt[:2000]
    if re.search(r"(?m)^\s*:(?:20|25|28C|61):", erste):
        return "mt940"
    return "csv"


def parse_inhalt(inhalt: str | bytes, format: str = "auto", *,
                 profil: str = "auto",
                 standard_waehrung: str = "EUR") -> list[Bewegung]:
    """Zentraler Einstieg: Auszug-Inhalt → Liste von ``Bewegung``.

    ``format``: 'csv' | 'camt' | 'mt940' | 'auto'. ``profil`` greift nur bei CSV
    (Spalten-Profil, s. ``csv_import.PROFILE``). Bytes werden als UTF-8 (mit
    Fallback latin-1) dekodiert — Bank-Dateien sind oft ISO-8859-1/15.
    """
    if isinstance(inhalt, bytes):
        try:
            inhalt = inhalt.decode("utf-8-sig")
        except UnicodeDecodeError:
            inhalt = inhalt.decode("latin-1")
    fmt = (format or "auto").lower()
    if fmt not in FORMATE:
        raise ImportFehler(f"Unbekanntes Import-Format: {format!r} "
                           f"(erlaubt: {', '.join(FORMATE)})")
    if fmt == "auto":
        fmt = erkenne_format(inhalt)
    if fmt == "camt":
        return parse_camt(inhalt, standard_waehrung=standard_waehrung)
    if fmt == "mt940":
        return parse_mt940(inhalt, standard_waehrung=standard_waehrung)
    if profil not in PROFILE:
        raise ImportFehler(f"Unbekanntes CSV-Profil: {profil!r} "
                           f"(bekannt: {', '.join(sorted(PROFILE))})")
    return parse_csv(inhalt, profil=profil, standard_waehrung=standard_waehrung)
