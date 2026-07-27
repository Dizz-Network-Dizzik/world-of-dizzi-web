"""H2 — Schlüsseldateien ins OS-Schloss (Windows DPAPI, CurrentUser-Scope).

Bisher lagen ``vault.key``, ``idp_key.json`` und RP-Session-Secrets als
Klartext-Dateien im Datenverzeichnis (Bedrohungsmodell docs/18 §4.2). DPAPI
bindet sie jetzt ans Windows-Nutzerkonto: kopierte Dateien sind auf fremden
Konten/Maschinen wertlos. EHRLICH (docs/18 §5): gegen Code, der IM selben
Konto läuft, schützt auch DPAPI nicht — das ist das dokumentierte „hard
limit" jeder Desktop-Software.

Format: ``DPAPI1\\n`` + Schutz-Blob. Dateien OHNE Magic (Bestand) werden beim
ersten Lesen TRANSPARENT migriert — kein manueller Schritt, kein Bruch.
Auf Nicht-Windows (oder wenn crypt32 fehlt) fällt das Modul auf Klartext
zurück und sagt das über ``verfuegbar()`` ehrlich an; die Aufrufer bleiben
plattformneutral.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

MAGIC = b"DPAPI1\n"
_UI_FORBIDDEN = 0x1


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def verfuegbar() -> bool:
    return sys.platform == "win32"


def _crypt(daten: bytes, schuetzen: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    eingabe = _DATA_BLOB(len(daten), ctypes.cast(
        ctypes.create_string_buffer(daten, len(daten)),
        ctypes.POINTER(ctypes.c_char)))
    ausgabe = _DATA_BLOB()
    fn = crypt32.CryptProtectData if schuetzen else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(eingabe), None, None, None, None,
            _UI_FORBIDDEN, ctypes.byref(ausgabe))
    if not ok:
        raise OSError(f"DPAPI fehlgeschlagen (GetLastError="
                      f"{ctypes.get_last_error()})")
    try:
        return ctypes.string_at(ausgabe.pbData, ausgabe.cbData)
    finally:
        kernel32.LocalFree(ausgabe.pbData)


def schreibe_geheim(pfad: Path, daten: bytes) -> None:
    """Schreibt ``daten`` DPAPI-geschützt (bzw. Klartext-Fallback ohne DPAPI).

    CH-3 (28.06.): ATOMAR (temp + fsync + os.replace via io_safe) statt rohem
    write_bytes — sonst lässt ein Crash/Platte-voll MITTEN im Schreiben die
    SCHLÜSSELdatei (z. B. vault.key) korrupt zurück ⇒ der Tresor und damit ALLE
    Secrets werden unrettbar. Schwerer als CH-2 (vault.dat = Nutzdaten), weil dies
    der Wurzel-Schlüssel ist; selten geschrieben (Init/DPAPI-Migration), aber
    katastrophale Folge ⇒ konsistent mit vault.py + io_safe atomar machen."""
    from .io_safe import atomic_write_bytes
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if verfuegbar():
        atomic_write_bytes(pfad, MAGIC + _crypt(daten, schuetzen=True))
    else:
        atomic_write_bytes(pfad, daten)


def lese_geheim(pfad: Path) -> bytes | None:
    """Liest eine Geheim-Datei; Klartext-Bestand wird beim ersten Lesen
    TRANSPARENT auf DPAPI migriert. None = Datei existiert nicht."""
    if not pfad.is_file():
        return None
    roh = pfad.read_bytes()
    if roh.startswith(MAGIC):
        return _crypt(roh[len(MAGIC):], schuetzen=False)
    if verfuegbar():                     # Bestands-Migration (einmalig)
        schreibe_geheim(pfad, roh)
    return roh


def schuetze_wert(daten: bytes) -> bytes:
    """DPAPI-Schutz für In-Memory-Werte (z. B. DB-Spalten) — Pendant zu
    ``schreibe_geheim`` ohne Datei. Ohne DPAPI (Nicht-Windows): Klartext zurück."""
    return _crypt(daten, schuetzen=True) if verfuegbar() else daten


def entschuetze_wert(daten: bytes) -> bytes:
    """Kehrt ``schuetze_wert`` um; Klartext-Fallback spiegelbildlich."""
    return _crypt(daten, schuetzen=False) if verfuegbar() else daten
