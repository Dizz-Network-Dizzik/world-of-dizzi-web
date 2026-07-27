"""MCP-Server des Trading-Bot-Panels (read-only, stdio).

Exponiert die KI-Zustände des Trading-Bot-Projekts (MasterMeta, Governor,
Master-Ensemble, Flotte) als MCP-Tools — für Dizzi als Host UND für jeden
anderen MCP-Client (z. B. Claude Code; Claude-Interop per Architektur).

Strikt READ-ONLY: kein Tool startet/stoppt/ändert irgendetwas am Trading.
Standort-Hinweis (bewusste Abweichung, dokumentiert): Ziel-Architektur ist,
dass dieser Server ins Trading-Bot-Projekt selbst zieht; v1 lebt er bei Dizzi,
um das fremde Repo/HEAD-Tracking nicht zu stören.

Start (stdio):  <venv-python> connectors/tradingbot/mcp_server.py
WICHTIG: niemals auf stdout schreiben (zerstört JSON-RPC) — nur stderr/Logging.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compact  # noqa: E402

BASE = os.environ.get("DIZZI_TRADINGBOT_URL", "http://127.0.0.1:8137")

mcp = FastMCP(
    "tradingbot",
    instructions="Read-only Einblick in das Trading-Bot-Projekt von dizzi: "
                 "Flotte, Master-Ensemble, MasterMeta-Bot, Governor, Risiko.",
)

# Tool-Namen tragen den App-Namensraum "tradingbot_" (docs/16 §6) — bei
# direkten FastMCP-Servern über den Funktionsnamen (= Tool-Name). So
# kollidieren sie nicht, sobald ein Host mehrere App-Server bündelt.


def _get(path: str) -> dict[str, Any]:
    try:
        r = httpx.get(f"{BASE}{path}", timeout=5.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": f"Trading Bot nicht erreichbar ({path}): {e}"}


@mcp.tool
def tradingbot_fleet_status() -> dict:
    """Flotten-Überblick: Bots, offene/geschlossene Trades, Trefferquote, ROI, Kategorien."""
    data = _get("/api/summary")
    return data if "error" in data else compact.compact_fleet(data)


@mcp.tool
def tradingbot_master_status() -> dict:
    """Master-Ensemble (oberste Lern-Ebene): aktives Regime, Gewichte, Market-Neutral-Anteil, Fitness."""
    data = _get("/api/master")
    return data if "error" in data else compact.compact_master(data)


@mcp.tool
def tradingbot_mastermeta_status() -> dict:
    """MasterMeta-Bot (KI-Flaggschiff): HMM-Regime + Konfidenz, Hebel, Event-Risiko, Autopilot."""
    data = _get("/api/mastermeta")
    return data if "error" in data else compact.compact_mastermeta(data)


@mcp.tool
def tradingbot_governor_status() -> dict:
    """Portfolio-Governor (Risiko-Wächter): Konfiguration, letzter Report, jüngste De-Risk-Aktionen."""
    data = _get("/api/governor")
    return data if "error" in data else compact.compact_governor(data)


@mcp.tool
def tradingbot_konzentration() -> dict:
    """Portfolio-Konzentration: HHI, Cluster-Anteile, Limits."""
    data = _get("/api/concentration")
    return data if "error" in data else compact.compact_concentration(data)


@mcp.tool
def tradingbot_alerts() -> Any:
    """Aktuelle Alerts/Warnungen des Trading-Bot-Systems."""
    data = _get("/api/alerts")
    return data if isinstance(data, dict) and "error" in data else compact.compact_alerts(data)


if __name__ == "__main__":
    mcp.run()  # stdio
