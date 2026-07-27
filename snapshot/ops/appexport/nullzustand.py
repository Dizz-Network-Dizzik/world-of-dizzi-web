"""Daten-/Secret-Nullzustand — Verbots- und Ausschluss-Regeln (docs/66 §7; I-2/I-3/I-6).

Die MUSTER sind normativ und pur testbar; der Baum-Scanner (läuft über ein
erzeugtes Bündel und bricht bei jedem Fund hart ab) ist Bau C1-3.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import NichtGebaut

# I-3: Secret-Muster — Fund in irgendeiner Text-Datei des Bündels ⇒ Abbruch ohne Override.
SECRET_MUSTER: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("zuweisungs-secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwort|password|client[_-]?secret)\s*[:=]\s*['\"][^'\"\s]{8,}")),
    ("pin", re.compile(r"(?i)\bpin\s*[:=]\s*['\"]?\d{4,}")),
)

# I-6: Monorepo-Rest-Muster — absolute Entwickler-Pfade/Daten-Wurzeln haben im Bündel nichts verloren.
PFAD_MUSTER: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absoluter-dizzik-pfad", re.compile(r"(?i)C:[\\/]+Dizzik")),
    ("daten-wurzel", re.compile(r"(?i)\bdata[\\/]+apps[\\/]")),
    ("backup-pfad", re.compile(r"(?i)_backups[\\/]")),
)

# I-2 (+ Schlüsselmaterial): Datei-Typen, die NIE ins Bündel dürfen (Match auf Dateinamen).
VERBOTENE_DATEIEN: tuple[str, ...] = (
    "*.db", "*.sqlite", "*.sqlite3", "*.db-wal", "*.db-shm",
    ".env", "*.env", "*.pem", "*.key", "*.pfx", "*.p12",
)

# §2: Entwicklungs-Artefakte, die der Builder beim Kopieren auslässt (kein Fehler, nur Filter).
AUSSCHLUSS_ORDNER: frozenset[str] = frozenset({"tests", "_workfiles", "docs", "__pycache__", ".git"})
AUSSCHLUSS_DATEIEN: tuple[str, ...] = ("CLAUDE.md", "conftest.py", "*.pyc")


def verstoesse_in_text(text: str) -> list[str]:
    """Namen aller Secret-/Pfad-Muster, die im Text anschlagen (leer = sauber)."""
    return [name for name, muster in SECRET_MUSTER + PFAD_MUSTER if muster.search(text)]


def ist_verbotene_datei(dateiname: str) -> bool:
    """I-2/I-3 auf Datei-Ebene: DB-/Secret-Dateitypen (Match auf den Basisnamen)."""
    return any(fnmatch.fnmatch(dateiname, muster) for muster in VERBOTENE_DATEIEN)


def ist_ausgeschlossen(rel_pfad: str) -> bool:
    """§2-Ausschluss beim Kopieren: Entwicklungs-Artefakte (Pfad relativ zur Bündel-Quelle)."""
    teile = Path(rel_pfad).parts
    if any(teil in AUSSCHLUSS_ORDNER for teil in teile[:-1]):
        return True
    basis = teile[-1] if teile else ""
    return any(fnmatch.fnmatch(basis, muster) for muster in AUSSCHLUSS_DATEIEN)


def scanne_baum(bundle_wurzel: Path) -> list[str]:
    """Voll-Scan eines erzeugten Bündels (Dateinamen + Textinhalte) — Bau C1-3."""
    raise NichtGebaut("C1-3 (docs/66 §10): Bündel-Baum-Scanner")
