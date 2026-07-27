"""Atomare Datei-Schreibvorgänge (Chaos-Härtung, docs/50 P1.2).

Schreibt erst in eine **temporäre Datei im SELBEN Verzeichnis**, ruft ``fsync``
(Daten wirklich auf die Platte) und dann ``os.replace`` (atomar auf demselben
Dateisystem). Ein Crash / eine volle Platte MITTEN im Schreiben hinterlässt damit
nie eine halb-geschriebene Ziel-Datei: entweder die alte Version bleibt unberührt,
oder die neue ist vollständig da. Same-Filesystem ist garantiert, weil die Temp-
Datei im Zielordner liegt. Das ist das Muster, das Memory-Trash (``Path.replace``
für Moves) schon nutzt — hier für Content-Writes (Vault / Tresor / DAM).

Reine Funktionen, keine App-Kopplung; testbar mit einem Tmp-Verzeichnis.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(pfad: Path | str, daten: bytes) -> None:
    """Schreibt ``daten`` atomar nach ``pfad`` (temp + fsync + os.replace).
    Bei Fehler (z. B. Platte voll) wird die Temp-Datei aufgeräumt und der Fehler
    weitergereicht — die bestehende Ziel-Datei bleibt dabei UNBERÜHRT."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(pfad.parent), prefix=f".{pfad.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(pfad: Path | str, text: str, encoding: str = "utf-8") -> None:
    """``atomic_write_bytes`` für Text (Default UTF-8)."""
    atomic_write_bytes(pfad, text.encode(encoding))
