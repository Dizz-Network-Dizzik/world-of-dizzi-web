"""Risiko-Wächter — prüft globale und Bot-Limits, liefert Kill-Switch-Signal.

Vollausbau (laufende Überwachung mit Auto-Stopp) folgt in M3. Hier stehen die
reinen Bewertungsfunktionen, die das Orchestrator-Backend und später der
Live-Loop nutzen.
"""

from __future__ import annotations

from .config import Settings
from .models import BotConfig


def evaluate_global(settings: Settings, total_invested_eur: float, drawdown_pct: float) -> dict:
    """Bewertet globale Sicherheitslimits. Bei Verletzung -> Kill-Switch."""
    violations: list[str] = []
    if drawdown_pct >= settings.global_max_drawdown_pct:
        violations.append(
            f"Globaler Drawdown {drawdown_pct:.1f}% >= Limit {settings.global_max_drawdown_pct:.1f}%"
        )
    if total_invested_eur > settings.global_capital_cap_eur:
        violations.append(
            f"Eingesetztes Kapital {total_invested_eur:.0f}EUR > Cap {settings.global_capital_cap_eur:.0f}EUR"
        )
    return {"ok": not violations, "kill_switch": bool(violations), "violations": violations}


def evaluate_bot(bot: BotConfig, daily_loss_pct: float, drawdown_pct: float, trades_today: int) -> dict:
    """Bewertet die Limits eines einzelnen Bots."""
    violations: list[str] = []
    if daily_loss_pct >= bot.risk.max_daily_loss_pct:
        violations.append(f"Tagesverlust {daily_loss_pct:.1f}% >= {bot.risk.max_daily_loss_pct:.1f}%")
    if drawdown_pct >= bot.risk.max_drawdown_pct:
        violations.append(f"Drawdown {drawdown_pct:.1f}% >= {bot.risk.max_drawdown_pct:.1f}%")
    if trades_today > bot.risk.max_trades_per_day:
        violations.append(f"Trades heute {trades_today} > {bot.risk.max_trades_per_day}")
    return {"ok": not violations, "kill_switch": bool(violations), "violations": violations}
