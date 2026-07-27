"""Pydantic-Datenmodelle für Bots und Risiko-Parameter.

Diese Modelle sind die zentrale Definition eines „Bots" im System: Identität,
Handels-Setup, Strategie-Auswahl und die im Plan (§4) definierten harten
Risiko-/Trading-Parameter.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tf_minutes(timeframe: str) -> int | None:
    """Timeframe-String → Minuten ('1m'→1, '15m'→15, '1h'→60, '4h'→240, '1d'→1440)."""
    tf = (timeframe or "").strip().lower().replace("min", "m")
    if not tf or not tf[0].isdigit():
        return None
    num = ""
    for ch in tf:
        if ch.isdigit():
            num += ch
        else:
            break
    if not num:
        return None
    n = int(num)
    unit = tf[len(num):] or "m"
    return n * {"m": 1, "h": 60, "d": 1440, "w": 10080}.get(unit[0], 1)


# Zeit-Horizont je Bot (recherchierte Krypto-Grenzen): Scalping Sek–Min (≤5m),
# Intraday Min–Std innerhalb des Tages (15m–1h), Swing Tage (≥4h). Dies ist seit dem
# Horizont-Umbau (2026-06-10) die PRIMÄRE Gruppierungs-Dimension (statt spot/futures).
HORIZONS = ("scalping", "intraday", "swing")


def derive_horizon(timeframe: str) -> str:
    """Leitet den Zeit-Horizont aus dem Timeframe ab (Default intraday, wenn unbekannt)."""
    m = tf_minutes(timeframe)
    if m is None:
        return "intraday"
    if m <= 5:
        return "scalping"
    if m <= 60:
        return "intraday"
    return "swing"


class RiskParams(BaseModel):
    """Harte, durchgesetzte Limits pro Bot (entspricht Plan §4)."""

    crv_min: float = Field(default=1.5, description="Mindest-Risk-Reward (CRV).")
    max_loss_per_trade_pct: float = Field(default=8.0, description="Stop-Loss je Trade in %.")
    max_daily_loss_pct: float = Field(default=10.0, description="Max. Tagesverlust in %.")
    max_drawdown_pct: float = Field(default=20.0, description="Max. Gesamt-Drawdown in %.")
    max_trades_per_day: int = Field(default=20, description="Begrenzt Handelsfrequenz (Steuer/Gewerbe).")
    capital_cap_eur: float = Field(default=200.0, description="Sicherheitsdeckel je Bot in EUR.")
    position_size_pct: float = Field(default=10.0, description="Anteil des Bot-Kapitals je Trade in %.")


class BotConfig(BaseModel):
    """Vollständige Konfiguration eines Bots."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    # Stabiler, eindeutiger Nummern-Tag (#NN) — vom Menschen lesbar, aenderungssicher (anders als die
    # Hash-id), automatisch vergeben (registry). 0 = noch nicht zugewiesen (Migration vergibt einen).
    tag: int = 0
    name: str
    strategy: str = "TrendFollowEma"
    pairs: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    # „Pairs streuen" (2026-06-10): bei ``dynamic`` ist ``pairs`` das kuratierte Kandidaten-Universum
    # (siehe universe.py), aus dem Freqtrade per VolumePairList die volumenstärksten Coins horizont-
    # gedeckelt dynamisch auswählt. ``static`` = klassische feste Whitelist (genau ``pairs``).
    pair_mode: Literal["static", "dynamic"] = "static"
    timeframe: str = "1h"
    # Zusaetzliche hoehere Timeframes fuer Multi-TF-Bestaetigung (z. B. ["1h"]).
    # Leer = klassisch single-TF. Wird der Engine per Env TBT_INFORMATIVE_TFS uebergeben.
    timeframes: list[str] = Field(default_factory=list)
    stake_amount: float = 100.0
    max_open_trades: int = 3
    dry_run: bool = True
    dry_run_wallet: float = 1000.0  # theoretisches Paper-Kapital (kein echtes Geld)
    trading_mode: Literal["spot", "futures"] = "spot"
    # PRIMÄRE Gruppierungs-Dimension (seit Horizont-Umbau 2026-06-10): Zeit-Horizont des Bots.
    # `trading_mode` (spot/futures) bleibt nur noch technisches Exchange-Attribut (Engine/Hebel-Icon).
    # Default aus dem Timeframe abgeleitet (registry/Migration setzen ihn konkret).
    horizon: Literal["scalping", "intraday", "swing"] = "intraday"
    # Reaktivität = wie oft der Bot seine Logik prüft (mappt auf Freqtrade
    # internals.process_throttle_secs): 'hoch'=1s (Scalping), 'standard'=5s, 'ruhig'=15s.
    # Wird beim Anlegen aus dem System/Timeframe abgeleitet (Scalping = reaktiver).
    reactivity: Literal["hoch", "standard", "ruhig"] = "standard"
    # Platzhalter für M4: Name/Label des Bitget-Subaccounts (eigener API-Key).
    subaccount: str | None = None
    # Vom Lern-Loop angewandte (optimierte) Strategie-Parameter (proposal-only,
    # nur per ausdrücklicher Anwendung gesetzt). Wird der Engine zur Laufzeit per
    # Env TBT_OPT_PARAMS übergeben (nur bei parametrisierbaren Strategien wirksam).
    opt_params: dict | None = None
    # C2: Versionszähler der angewandten Verbesserungen (0 = Basis; +1 je Upgrade).
    opt_version: int = 0
    # Auto-Upgrade (2026-06-10): sobald EINMAL manuell ein Upgrade angewandt wurde, werden weitere
    # validierte Verbesserungen für diesen Bot automatisch übernommen (immer mit Version + Changelog).
    auto_upgrade: bool = False
    # Manuelle Override-Parameter (Nutzer-Tuning im Bot-Management): liegen IMMER ueber den
    # gelernten ``opt_params`` (im runner gemergt) -> Auto-Upgrade ueberschreibt sie NICHT.
    # None/{} = kein manueller Override.
    manual_params: dict | None = None
    # Per-Bot-Hebel (Futures): None = Engine-Default. Wird der Engine via Env ``TBT_LEVERAGE``
    # uebergeben und dort hart auf <=5x gedeckelt (Echtgeld-Verstaerker). Spot-Engines ignorieren ihn.
    leverage: int | None = None
    risk: RiskParams = Field(default_factory=RiskParams)
    status: Literal["created", "paper_running", "live_running", "stopped"] = "created"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class BotCreate(BaseModel):
    """Eingabe zum Anlegen eines Bots (nur die nötigen Felder)."""

    name: str
    tag: int | None = None  # optional vorgeben; sonst vergibt registry den naechsten freien
    strategy: str = "TrendFollowEma"
    pairs: list[str] | None = None
    # None → create_bot wählt: ohne explizite pairs „dynamic" (gestreutes Universum), sonst „static".
    pair_mode: Literal["static", "dynamic"] | None = None
    timeframe: str = "1h"
    timeframes: list[str] | None = None
    stake_amount: float = 100.0
    max_open_trades: int = 3
    dry_run: bool = True
    dry_run_wallet: float = 1000.0
    trading_mode: Literal["spot", "futures"] = "spot"
    # Optional; wenn None, wird der Horizont aus dem Timeframe abgeleitet.
    horizon: Literal["scalping", "intraday", "swing"] | None = None
    # Optional; wenn None, wird die Reaktivität aus dem Timeframe abgeleitet.
    reactivity: Literal["hoch", "standard", "ruhig"] | None = None
    # Per-Bot-Hebel (Futures, optional; 1..5). None = Engine-Default.
    leverage: int | None = None
    risk: RiskParams | None = None
