"""Zentrale Konfiguration — lädt Werte aus Umgebung / .env.

Secrets stehen ausschließlich in ``.env`` (nicht versioniert). Diese Datei
liest sie typsicher ein und stellt globale Sicherheits-Defaults bereit.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Projektwurzel (…/dizz-network/apps/trading/programm — Live seit C1-Cutover 2026-06-24; relativ via parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Anwendungseinstellungen, gespeist aus Umgebungsvariablen / .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Betriebsmodus ---
    dry_run: bool = Field(default=True, alias="TBT_DRY_RUN")

    # --- Bitget API ---
    bitget_api_key: str = Field(default="", alias="BITGET_API_KEY")
    bitget_api_secret: str = Field(default="", alias="BITGET_API_SECRET")
    bitget_api_password: str = Field(default="", alias="BITGET_API_PASSWORD")

    # --- Orchestrator-Backend ---
    api_host: str = Field(default="127.0.0.1", alias="TBT_API_HOST")
    api_port: int = Field(default=8137, alias="TBT_API_PORT")
    api_token: str = Field(default="", alias="TBT_API_TOKEN")
    # CORS: kommaseparierte erlaubte Origins (leer = aus, nur lokal). Für spätere App/Server-Clients.
    cors_origins: str = Field(default="", alias="TBT_CORS_ORIGINS")

    # --- KI-Modul (optional) ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    ai_model: str = Field(default="claude-sonnet-4-5", alias="TBT_AI_MODEL")

    # --- Fundamental-Daten (optional) ---
    # St. Louis Fed (FRED) — echte Makro-Werte (CPI/Zinsen/Financial Conditions). Ohne Key: Proxy.
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")

    # --- Globale Sicherheitslimits ---
    global_max_drawdown_pct: float = Field(
        default=20.0, alias="TBT_GLOBAL_MAX_DRAWDOWN_PCT"
    )
    global_capital_cap_eur: float = Field(
        default=200.0, alias="TBT_GLOBAL_CAPITAL_CAP_EUR"
    )

    @property
    def bitget_configured(self) -> bool:
        """True, wenn ein Bitget-API-Schlüssel hinterlegt ist."""
        return bool(self.bitget_api_key and self.bitget_api_secret)


def get_settings() -> Settings:
    """Einstellungen laden (eigene Instanz; einfache, testbare Funktion)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
