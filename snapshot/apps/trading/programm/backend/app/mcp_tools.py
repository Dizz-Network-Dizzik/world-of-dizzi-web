"""Deklarative MCP-Tool-Liste von Dizz Trading — EINE Quelle für (a) den stdio-MCP-
Server (``connectors/tradingbot/mcp_server.py``, Core-Agent) und (b) das per-App-MCP-
Gateway (``main.py`` → ``appkit.app_gateway``, Standalone-Betrieb). Reine Daten —
kein MCP-Import ⇒ die laufende App liest sie ohne MCP-Abhängigkeit ein.

Jeder Eintrag ``(tool_name, api_pfad, beschreibung)`` = read-only GET auf die
App-API (Namensraum ``tradingbot_`` wird automatisch gesetzt, docs/16 §6).
Strikt read-only: kein Tool startet/stoppt/ändert Trading; Echtgeld-Gate unberührt."""

from __future__ import annotations

MCP_TOOLS: list[tuple[str, str, str]] = [
    ("flotte",       "/api/summary",       "Flotten-Überblick: Bots, offene Trades, Trefferquote, ROI."),
    ("master",       "/api/master",        "Master-Ensemble: aktives Regime, Gewichte, MN-Anteil, Fitness."),
    ("mastermeta",   "/api/mastermeta",    "MasterMeta-Bot: HMM-Regime + Konfidenz, Hebel, Event-Risiko, Autopilot."),
    ("governor",     "/api/governor",      "Portfolio-Governor: Konfiguration, letzter Report, De-Risk-Aktionen."),
    ("konzentration","/api/concentration", "Portfolio-Konzentration: HHI, Cluster-Anteile, Limits."),
    ("alerts",       "/api/alerts",        "Aktuelle Alerts und Warnungen des Trading-Bot-Systems."),
]

MCP_INSTRUCTIONS = (
    "Read-only Einblick in Dizz Trading (Krypto-Algorithmus-System): "
    "Flottenstatus, Master-Ensemble, HMM-Regime, Portfolio-Governor, "
    "Konzentration, Alerts. Keine Schreib- oder Steuer-Aktionen."
)
