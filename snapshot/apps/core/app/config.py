"""Zentrale Konfiguration.

Alle Werte sind per Umgebungsvariable mit Präfix ``DIZZI_`` übersteuerbar
(z. B. ``DIZZI_DATA_DIR``). Laufzeitdaten liegen bewusst außerhalb von
OneDrive-synchronisierten Pfaden (Datei-Sperren-Lehre aus dem Trading Bot).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_env_file(path: Path) -> None:
    """Lädt Secrets (API-Keys) aus der geschützten .env AUSSERHALB von Repo
    und OneDrive in die Prozess-Umgebung. Bereits gesetzte Variablen gewinnen."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(Path(r"C:\Dizzik\data\.env"))

# Single-User-Betrieb der Stufe 1; alle Tabellen sind trotzdem user-scoped,
# damit Multi-User (Stufe 3) ein Aufsatz wird und kein Umbau.
DEFAULT_USER_ID = "dizzi"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIZZI_")

    data_dir: Path = Path(r"C:\Dizzik\data")
    host: str = "127.0.0.1"  # nur localhost, bis Auth-Vollausbau (Stufe 3)
    port: int = 8200
    app_name: str = "the world of dizzi"

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def db_path(self) -> Path:
        return self.db_dir / "dizzi.sqlite"


settings = Settings()
