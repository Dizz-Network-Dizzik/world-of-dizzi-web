"""Token-Tresor (K2) — verschlüsselte Ablage für Dienst-Geheimnisse je App.

Für OAuth-Tokens, API-Keys u. Ä. (Vernetzung & Dienste): NIE in app_settings
(/api/settings würde sie zeigen) und NIE im Repo. Werte liegen Fernet-
verschlüsselt in ``<data>/apps/<id>/vault.dat``; der Schlüssel separat in
``vault.key`` — seit H2 **DPAPI-geschützt** (secrets_os: ans Windows-Konto
gebunden, Bestands-Schlüssel migrieren transparent). Ehrliche Einordnung
(G2 + docs/18 §5): gegen Code im selben Nutzer-Konto schützt auch das nicht —
der Tresor bannt Datei-/Backup-Leaks und erzwingt EINE Secret-API mit Audit.

API bewusst klein: put/get/delete/names. ``names()`` listet nur Namen —
Werte verlassen den Tresor ausschließlich über gezieltes ``get``.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import secrets_os
from .io_safe import atomic_write_bytes


class Vault:
    def __init__(self, app_data_dir: Path) -> None:
        self._dat = app_data_dir / "vault.dat"
        self._keyfile = app_data_dir / "vault.key"
        self._fernet = Fernet(self._load_key())
        # Mutationen sind Read-Modify-Write auf EINER Datei — ohne Lock können
        # sich parallele puts gegenseitig überschreiben (Review 12.06.).
        self._lock = threading.Lock()

    def _load_key(self) -> bytes:
        key = secrets_os.lese_geheim(self._keyfile)  # migriert Klartext-Bestand
        if key is not None:
            return key.strip()
        key = Fernet.generate_key()
        secrets_os.schreibe_geheim(self._keyfile, key)
        return key

    def _read(self) -> dict[str, str]:
        if not self._dat.is_file():
            return {}
        try:
            raw = self._fernet.decrypt(self._dat.read_bytes())
        except InvalidToken as e:  # falscher Schlüssel/korrupte Datei: laut scheitern
            raise RuntimeError("Token-Tresor nicht lesbar (Schlüssel passt nicht)") from e
        return json.loads(raw.decode("utf-8"))

    def _write(self, data: dict[str, str]) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._dat.parent.mkdir(parents=True, exist_ok=True)
        # CH-2 (28.06.): ATOMAR schreiben (temp + fsync + os.replace) statt rohem
        # write_bytes — sonst lässt ein Crash/Platte-voll MITTEN im Schreiben eine
        # teil-geschriebene vault.dat zurück ⇒ _read wirft RuntimeError ⇒ ALLE
        # Connector-Tokens unlesbar. atomic_write_bytes hält die Alt-Datei unversehrt.
        atomic_write_bytes(self._dat, self._fernet.encrypt(raw))

    def put(self, name: str, value: str) -> None:
        with self._lock:
            data = self._read()
            data[name] = value
            self._write(data)

    def get(self, name: str, default: str | None = None) -> str | None:
        return self._read().get(name, default)

    def delete(self, name: str) -> bool:
        with self._lock:
            data = self._read()
            if name not in data:
                return False
            del data[name]
            self._write(data)
            return True

    def names(self) -> list[str]:
        return sorted(self._read().keys())
