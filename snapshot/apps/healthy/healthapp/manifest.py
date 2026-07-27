"""Vernetzungs-Manifest von Dizz Healthy — WER/WO/WIE-sensibel/WAS-geteilt.

Eine von genau drei App-spezifischen Stellen (neben Domänen-Schema/-Router und
``summary_fn``); alles Übrige liefert appkit. Wird unter ``/api/manifest``
ausgeliefert und speist die generische Dashboard-Kachel + K2.3-Marken-Lockup
(``brand`` betont · ``name`` dezent, docs/06 §5).

PORT 8217 ist verbindlich (App-Vertrag docs/01).

SENSIBILITÄT ``hoechst`` ist hier KEIN Detail, sondern Sicherheits-Schalter: das
KI-Routing startet damit auf ``lokal_only`` (settings_core.base_schema) — Inhalte
gehen NIE an Boost-/Cloud-Modelle, und sensible Routen stehen nur bei verifizierter
Verbindung bereit. Bewusst die strengste Stufe (Gesundheitsdaten, docs/RECHERCHE §5).
"""

from __future__ import annotations

from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.mcp import namespaced

from . import __version__

APP_ID = "health"

# MCP-Tools KURZ deklarieren; ``namespaced()`` präfixt sie in den App-Namensraum
# (<id>_<tool> ⇒ health_kachel_stats / health_gesundheits_trend / …, docs/16 §6) —
# derselbe Präfix, den ``build_http_mcp`` im mcp_server automatisch setzt. So bleiben
# Manifest und tatsächliche Tool-Namen konsistent (kollisionsfest beim Bündeln
# mehrerer App-Server durch den Leading-/Core-Agenten).
_MCP_TOOLS = ["kachel_stats", "gesundheits_trend", "naechste_termine",
              "aktive_supplements"]

MANIFEST = AppManifest(
    id=APP_ID,
    name="Gesundheit",              # dezenter Funktionsname (K2.3 .fn)
    brand="Dizz Healthy",           # betonte Marke (K2.3 .brand)
    version=__version__,
    port=8217,                      # verbindlich (App-Vertrag)
    icon="heart",
    sensitivity="hoechst",          # HOCHSENSIBEL ⇒ KI lokal_only, nie Cloud/Boost
    mcp=McpInfo(command=["<venv-python>", "healthapp/mcp_server.py"],
                tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    shares=Shares(summary=True, tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    depends=[],                     # Cross-Zugriff (Plans=Routinen, Admin=Arztdoku) folgt auf Anfrage
)
