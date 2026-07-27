"""Vernetzungs-Manifest von Dizz Admin — WER/WO/WIE-sensibel/WAS-geteilt.

Dizz Admin = die vereinte Verwaltungs-App (Plans + Admin + Leading verschmolzen,
docs/28). Basis-Repo war ``leading`` ⇒ id auf ``admin`` umbenannt, Port 8222.

Eine von genau drei App-spezifischen Stellen (neben Domänen-Schema/-Router und
``summary_fn``); alles Übrige liefert appkit. Wird unter ``/api/manifest``
ausgeliefert und speist die Dashboard-Kachel + K2.3-Marken-Lockup.

PORT 8222 ist verbindlich (App-Vertrag). SENSIBILITÄT ``hoch`` (Geschäfts-/Steuer-/
Studien-/Mandanten-Daten) ⇒ KI lokal-first; sensible Routen nur bei verifizierter
Verbindung; der Tresor kann Fächer zusätzlich verschlüsseln (docs/28 §6).
"""

from __future__ import annotations

from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.mcp import namespaced

from . import __version__

APP_ID = "admin"

# Read-only MCP-Tools; ``namespaced()`` präfixt sie in den App-Namensraum
# (admin_geschaefts_kpis / admin_offene_rechnungen / …, docs/16 §6) — derselbe
# Präfix, den ``build_http_mcp`` im mcp_server automatisch setzt. (Bereiche/Tresor/
# Projekte-Tools folgen mit der Modul-Migration, docs/28 §4.3.)
_MCP_TOOLS = ["geschaefts_kpis", "offene_rechnungen", "naechste_fristen",
              "netzwerk_status", "studien_uebersicht", "studien_fristen",
              "pruefungsversuche_warnung",
              # Vereinte Module (docs/28): Bereichs-Achse · Tresor · Projekte · Fristen-Cockpit
              "bereiche", "fristen_cockpit", "dokumente", "projekte", "erinnerungen"]

MANIFEST = AppManifest(
    id=APP_ID,
    name="Verwaltung",              # dezenter Funktionsname (K2.3 .fn)
    brand="Dizz Admin",             # betonte Marke (K2.3 .brand)
    version=__version__,
    port=8222,                      # verbindlich (App-Vertrag)
    icon="stamp",
    sensitivity="hoch",             # Geschäfts-/Steuer-/Studien-Daten ⇒ KI lokal-first
    mcp=McpInfo(command=["<venv-python>", "adminapp/mcp_server.py"],
                tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    shares=Shares(summary=True, tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    depends=[],   # Aggregator konsumiert die Schwestern read-only über den Core (kein harter depends)
)
