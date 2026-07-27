"""SF-1 — Sicherheits-Ampel (docs/82 §3, Schicht A3/C).

Reine **Lese**-Checks: prüft den Sicherheits-Zustand einer Installation und
zeigt ihn als Ampel an — **ändert nie** System-Zustand (kein Aktivieren von
BitLocker, kein Schlüssel-Umzug; das tut der Nutzer geführt). Die Ampel-Semantik
folgt dem fail-closed Muster der Lizenz-Ampel (``ops/appexport/lizenz.py``):

- ``gruen``     — nachweislich geschützt.
- ``gelb``      — Schwäche/Defense-in-depth fehlt (kein Hard-Fail).
- ``rot``       — **positiv festgestellte** Schwäche (unverschlüsselt, wo es weh tut).
- ``unbekannt`` — nicht ermittelbar (keine Rechte, Werkzeug fehlt, Baustein folgt).
                  Wiegt fürs Gesamt-Urteil wie ``gelb`` (Vorsicht), ist aber
                  ehrlich als „nicht ermittelbar" gekennzeichnet.

**fail-closed:** jeder Check fängt seine eigenen Fehler und liefert dann
``unbekannt`` mit Befund — die Ampel wirft nie und wird nie fälschlich grün.

Der einzige Zugriff nach außen ist ``GET /api/sicherheit/lage`` (localhost-
guarded, Stufe ``lokal``): reine Statusanzeige, die dem Nutzer beim Härten hilft
und keine sensiblen Daten preisgibt (Schlüssel-WERTE verlassen nichts — geprüft
werden nur Datei-Kopf-Magie-Bytes).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends

from .auth import DEFAULT_USER_ID, UserContext, current_user
from .db import now_iso

# --- Ampel-Zustände + Rang (gesamt = schlechtester Einzel-Zustand) -------------------
GRUEN = "gruen"
GELB = "gelb"
ROT = "rot"
UNBEKANNT = "unbekannt"
# unbekannt wiegt wie gelb (Vorsicht, aber kein Hard-Fail); rot ist das schlechteste.
_RANG: dict[str, int] = {GRUEN: 0, GELB: 1, UNBEKANNT: 1, ROT: 2}


def _schlechtester(zustaende: list[str]) -> str:
    """Aggregation: der Zustand mit dem höchsten Rang gewinnt (unbekannt≈gelb).
    Bei Gleichstand gewinnt der EXPLIZITE (unbekannt tritt hinter gelb zurück,
    damit ``gesamt`` ehrlich ‚gelb' statt ‚unbekannt' zeigt, wenn beides auftritt)."""
    if not zustaende:
        return UNBEKANNT
    hoechster = max(_RANG.get(z, 1) for z in zustaende)
    if hoechster == 2:
        return ROT
    if hoechster == 0:
        return GRUEN
    # Rang 1: gelb ODER unbekannt vorhanden — gelb ist die aussagekräftigere Farbe.
    return GELB if GELB in zustaende else UNBEKANNT


# --- Magie-Bytes (Datei-Köpfe — es werden NIE Schlüssel-/DB-Inhalte gelesen) ---------
_SQLITE_MAGIC = b"SQLite format 3\x00"     # unverschlüsselte SQLite-DB; SQLCipher hat KEINEN
_DPAPI_MAGIC = b"DPAPI1\n"                  # secrets_os DPAPI-Header (Windows-OS-Schloss)
_OSKEY_MAGIC = b"OSKEY1\n"                  # secrets_os OS-neutraler Wickel (SF-3)

# Kanonischer Setting-Schlüssel des Auto-Locks — SF-6 DEFINIERT + schreibt ihn, SF-1
# liest nur (fehlt er ⇒ „Baustein folgt"). Als Konstante, damit SF-6 denselben Namen nutzt.
AUTOLOCK_SETTING = "sicherheit_autolock_minuten"

# Backup-Passphrasen-Slot (DPAPI-gewickelt, ops/backup_apps.py::PASS_SLOT). appkit
# importiert ops NICHT (Schicht-Trennung) ⇒ Pfad als überschreibbare Konvention.
_BACKUP_SLOT_DEFAULT = Path(r"C:\Dizzik\data\tools\backup_zip_pass.bin")


def _kopf(pfad: Path, n: int) -> bytes | None:
    """Erste ``n`` Bytes einer Datei; ``None`` wenn nicht vorhanden. Wirft nicht."""
    try:
        if not pfad.is_file():
            return None
        with open(pfad, "rb") as f:
            return f.read(n)
    except OSError:
        return None


# === Die fünf Checks (jeder liefert (zustand, befund, empfehlung)) ====================
# Jeder Check ist rein lesend + kapselt Fehler NICHT selbst — das tut der Runner
# (``_lauf``) einheitlich zu ``unbekannt``, sodass fail-closed an EINER Stelle gilt.

def _check_fde(data_dir: Path) -> tuple[str, str, str]:
    """Voll-Datenträger-Verschlüsselung des Daten-Laufwerks (T1: „PC aus/Platte
    ausgebaut"). Windows: BitLocker via ``Get-BitLockerVolume`` (Timeout 3 s).
    Ohne Admin-Rechte/leer ⇒ unbekannt + Anleitung (das ist das RICHTIGE, ehrliche
    Ergebnis — nicht wegmogeln). Nicht-Windows ⇒ unbekannt + OS-Hinweis."""
    if sys.platform != "win32":
        return (UNBEKANNT,
                "Nicht-Windows — FDE-Status hier nicht automatisch prüfbar.",
                "Laufwerks-Verschlüsselung sicherstellen (macOS: FileVault · "
                "Linux: LUKS · portabel: VeraCrypt).")
    laufwerk = str(data_dir.anchor or "C:\\").rstrip("\\")   # z. B. 'C:'
    try:
        fertig = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-BitLockerVolume -MountPoint '{laufwerk}').ProtectionStatus"],
            capture_output=True, text=True, timeout=3.0)
    except (subprocess.TimeoutExpired, OSError):
        return (UNBEKANNT,
                "BitLocker-Status nicht ermittelbar (Zeitüberschreitung/kein PowerShell).",
                "Als Admin prüfen: manage-bde -status. Empfohlen: BitLocker mit "
                "TPM+PIN (Pre-Boot-PIN) oder VeraCrypt.")
    roh = (fertig.stdout or "").strip()
    if fertig.returncode != 0 or not roh:
        return (UNBEKANNT,
                "BitLocker-Status nicht ermittelbar (fehlende Rechte oder kein BitLocker).",
                "Als Admin prüfen: manage-bde -status. Ohne TPM/BitLocker (z. B. Windows "
                "Home): VeraCrypt. Empfohlen: Pre-Boot-PIN.")
    wert = roh.splitlines()[0].strip().lower()
    if wert in ("on", "1"):
        return (GRUEN, f"BitLocker aktiv auf {laufwerk}.",
                "Ideal zusätzlich: Pre-Boot-PIN (TPM+PIN), damit der Schlüssel erst "
                "nach deiner Eingabe in den Speicher kommt.")
    if wert in ("off", "0"):
        return (ROT, f"Laufwerk {laufwerk} ist NICHT verschlüsselt (BitLocker aus).",
                "BitLocker mit TPM+PIN aktivieren (oder VeraCrypt) — sonst sind die "
                "Datei-Bytes bei ausgebauter Platte lesbar.")
    return (UNBEKANNT, f"BitLocker-Status unklar ({roh[:40]!r}).",
            "Als Admin prüfen: manage-bde -status.")


def _check_db_at_rest(db_pfad: Path, sensitivitaet: str) -> tuple[str, str, str]:
    """App-Datenbank verschlüsselt? Unverschlüsselte SQLite beginnt mit
    ``SQLite format 3\\0``; SQLCipher/SEE verschlüsseln den GANZEN Kopf ⇒ Magie
    fehlt. Bewertung skaliert mit der Sensibilität (höchst-Apps: Klartext = rot)."""
    kopf = _kopf(db_pfad, len(_SQLITE_MAGIC))
    if kopf is None:
        return (GRUEN, "Noch keine Datenbank angelegt (keine ruhenden Klartext-Daten).",
                "")
    if kopf != _SQLITE_MAGIC:
        return (GRUEN, "Datenbank verschlüsselt (kein Klartext-SQLite-Kopf).", "")
    # Klartext-DB — Schwere nach Sensibilität.
    if sensitivitaet == "hoechst":
        return (ROT, "Höchst-sensible Daten liegen UNVERSCHLÜSSELT in der DB.",
                "App-eigene DB-Verschlüsselung aktivieren (SF-2, Passphrase-abgeleitet) "
                "— zusätzlich zur Laufwerks-Verschlüsselung.")
    if sensitivitaet == "hoch":
        return (GELB, "Sensible Daten liegen unverschlüsselt in der DB.",
                "DB-Verschlüsselung (SF-2) empfohlen; mindestens Laufwerks-FDE aktiv halten.")
    return (GELB, "Datenbank unverschlüsselt (bei normaler Sensibilität meist okay).",
            "Laufwerks-FDE genügt für diese Daten-Klasse; DB-Crypto (SF-2) optional.")


def _check_vault_schluessel(data_dir: Path) -> tuple[str, str, str]:
    """Liegt der Tresor-Schlüssel (``vault.key``) im OS-Schloss (DPAPI/OSKEY)
    statt als Klartext? Es werden nur die Kopf-Magie-Bytes gelesen, NIE der Wert."""
    pfad = data_dir / "vault.key"
    kopf = _kopf(pfad, max(len(_DPAPI_MAGIC), len(_OSKEY_MAGIC)))
    if kopf is None:
        return (GRUEN, "Kein Tresor-Schlüssel vorhanden (noch keine Secrets abgelegt).", "")
    if kopf.startswith(_DPAPI_MAGIC) or kopf.startswith(_OSKEY_MAGIC):
        return (GRUEN, "Tresor-Schlüssel im OS-Schloss (an dieses Konto gebunden).", "")
    if sys.platform == "win32":
        return (ROT, "Tresor-Schlüssel liegt als KLARTEXT-Datei (nicht DPAPI-geschützt).",
                "App einmal starten — secrets_os migriert den Schlüssel transparent ins "
                "OS-Schloss; Klartext-Kopie danach entfernen.")
    return (GELB, "Tresor-Schlüssel im Klartext (auf diesem OS kein DPAPI-Äquivalent aktiv).",
            "Keyring-Backend einrichten (SF-3) oder Laufwerks-FDE als Schutz sicherstellen.")


def _check_backup_crypto(backup_slot: Path) -> tuple[str, str, str]:
    """Ist die Backup-Passphrase gesetzt (⇒ Nightly-Archive AES-verschlüsselt)?
    Geprüft wird nur die PRÄSENZ des DPAPI-Slots, nie sein Inhalt."""
    roh = _kopf(backup_slot, 1)
    if roh:
        return (GRUEN, "Backup-Passphrase gesetzt — Nightly-Archive verschlüsselt.", "")
    return (GELB, "Keine Backup-Passphrase gesetzt — Backups evtl. unverschlüsselt.",
            "Einmalig setzen: ops/backup_apps.py --set-passphrase (liegt DPAPI-gewickelt).")


def _check_auto_lock(autolock_minuten: Any, sensitivitaet: str) -> tuple[str, str, str]:
    """Auto-Lock aktiv? Der Baustein (SF-6) folgt noch — bis dahin ehrlich
    ``unbekannt``. ``autolock_minuten`` = gelesener Setting-Wert (None = nicht gesetzt)."""
    if autolock_minuten is None:
        return (UNBEKANNT, "Auto-Lock-Baustein folgt (SF-6) — Setting noch nicht vorhanden.",
                "Kommt mit SF-6: Inaktivitäts-Sperre + Schlüssel-Zeroization.")
    try:
        minuten = int(autolock_minuten)
    except (TypeError, ValueError):
        return (UNBEKANNT, f"Auto-Lock-Wert unlesbar ({autolock_minuten!r}).", "")
    if minuten > 0:
        return (GRUEN, f"Auto-Lock nach {minuten} min Inaktivität aktiv.", "")
    if sensitivitaet in ("hoch", "hoechst"):
        return (GELB, "Auto-Lock aus (bei sensibler App empfohlen).",
                "Inaktivitäts-Sperre einschalten (Setting sicherheit_autolock_minuten > 0).")
    return (GRUEN, "Auto-Lock aus (für diese Daten-Klasse vertretbar).", "")


# === Runner (fail-closed an EINER Stelle) + öffentliche API ===========================

_CHECK_TITEL: dict[str, str] = {
    "fde": "Laufwerks-Verschlüsselung",
    "db_at_rest": "Datenbank-Verschlüsselung",
    "vault_schluessel": "Tresor-Schlüssel im OS-Schloss",
    "backup_crypto": "Backup-Verschlüsselung",
    "auto_lock": "Automatische Sperre",
}


def _lauf(check_id: str, fn: Callable[[], tuple[str, str, str]]) -> dict[str, Any]:
    """Führt einen Check aus; JEDE Ausnahme ⇒ ``unbekannt`` (fail-closed, nie werfen)."""
    try:
        zustand, befund, empfehlung = fn()
    except Exception as e:  # noqa: BLE001 — fail-closed: kein Check darf die Ampel kippen
        zustand = UNBEKANNT
        befund = f"Check nicht ausführbar ({type(e).__name__})."
        empfehlung = ""
    return {"id": check_id, "titel": _CHECK_TITEL.get(check_id, check_id),
            "zustand": zustand, "befund": befund, "empfehlung": empfehlung}


def pruefe_lage(app_id: str, db_pfad: str | Path, data_dir: str | Path,
                sensitivitaet: str, *, autolock_minuten: Any = None,
                backup_slot: str | Path | None = None) -> dict[str, Any]:
    """Sicherheits-Lage einer Installation (docs/82 §3). Rein lesend, wirft nie.

    Rückgabe: ``{app, gesamt, geprueft_am, checks: [{id, titel, zustand, befund,
    empfehlung}]}`` mit ``gesamt`` = schlechtester Einzel-Zustand (unbekannt≈gelb).
    ``autolock_minuten`` reicht der Aufrufer aus seinem Settings-Store durch
    (None = Setting fehlt ⇒ SF-6 folgt). ``backup_slot`` überschreibt den DPAPI-
    Slot-Pfad (Default = ops/backup_apps.py-Konvention)."""
    db_p = Path(db_pfad)
    dd = Path(data_dir)
    slot = Path(backup_slot) if backup_slot is not None else _BACKUP_SLOT_DEFAULT
    checks = [
        _lauf("fde", lambda: _check_fde(dd)),
        _lauf("db_at_rest", lambda: _check_db_at_rest(db_p, sensitivitaet)),
        _lauf("vault_schluessel", lambda: _check_vault_schluessel(dd)),
        _lauf("backup_crypto", lambda: _check_backup_crypto(slot)),
        _lauf("auto_lock", lambda: _check_auto_lock(autolock_minuten, sensitivitaet)),
    ]
    gesamt = _schlechtester([c["zustand"] for c in checks])
    return {"app": app_id, "gesamt": gesamt, "geprueft_am": now_iso(),
            "checks": checks}


def posture_router(manifest: Any, db: Any) -> APIRouter:
    """``GET /api/sicherheit/lage`` für create_app-Apps (docs/82 §3).

    **Stufe ``lokal``** (localhost-guarded), NICHT ``verifiziert``: reine
    read-only Statusanzeige, die dem Nutzer beim Härten hilft und keine sensiblen
    Daten preisgibt — im Standalone-Single-User (Provider-Stufe ‚lokal') muss sie
    erreichbar sein, sonst wäre die Ampel im Normalbetrieb tot. (Bewusste
    Korrektur der docs/82-§3-Erstformulierung ‚verifiziert', die den Single-User-
    Betrieb ausgesperrt hätte — Gesetz 2.)"""
    r = APIRouter(tags=["sicherheit"])

    @r.get("/api/sicherheit/lage")
    def lage(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        try:
            autolock = db.setting_get(user.user_id, AUTOLOCK_SETTING, None)
        except Exception:  # noqa: BLE001 — Setting-Fehler darf die Lage nie kippen
            autolock = None
        return pruefe_lage(manifest.id, db.db_path, db.db_path.parent,
                           manifest.sensitivity, autolock_minuten=autolock)

    return r
