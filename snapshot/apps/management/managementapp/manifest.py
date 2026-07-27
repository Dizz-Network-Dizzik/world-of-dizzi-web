"""Vernetzungs-Manifest von Dizz Management — WER/WO/WIE-sensibel/WAS-geteilt.

Eine von genau drei App-spezifischen Stellen (neben Domänen-Schema/-Router und
``summary_fn``); alles Übrige liefert appkit. Wird unter ``/api/manifest``
ausgeliefert und speist die generische Dashboard-Kachel + K2.3-Marken-Lockup
(``brand`` betont · ``name`` dezent, docs/06 §5).

PORT 8213 ist verbindlich (App-Vertrag docs/01).

SENSIBILITÄT ``hoch`` ist hier KEIN Detail, sondern Sicherheits-Schalter: das
KI-Routing startet damit auf ``lokal_only`` (settings_core.base_schema) — Inhalte
gehen NIE an Boost-/Cloud-Modelle, und sensible Routen stehen nur bei verifizierter
Verbindung bereit. Begründung: die App verwaltet OAuth-Tokens fremder Plattformen
und steuert Außenwirkung (Posten) — beides sicherheitskritisch (docs/RECHERCHE §5).
Veröffentlichen bleibt zusätzlich Human-in-the-Loop (K4) und v1 DORMANT.
"""

from __future__ import annotations

from appkit.manifest import AppManifest, McpInfo, Shares
from appkit.mcp import namespaced

from . import __version__

APP_ID = "management"

# MCP-Tools KURZ deklarieren; ``namespaced()`` präfixt sie in den App-Namensraum
# (<id>_<tool> ⇒ management_kachel_stats / management_redaktionsplan / …, docs/16 §6) —
# derselbe Präfix, den ``build_http_mcp`` im mcp_server automatisch setzt. So bleiben
# Manifest und tatsächliche Tool-Namen konsistent (kollisionsfest beim Bündeln
# mehrerer App-Server durch den Leading-/Core-Agenten).
_MCP_TOOLS = ["kachel_stats", "redaktionsplan", "kanal_status", "social_bots",
              "auswertung"]

MANIFEST = AppManifest(
    id=APP_ID,
    name="KI-Agenten",              # dezenter Funktionsname (K2.3 .fn) — Umdeklaration 03.07. (D13):
    #                                 Management = KI-Agenten-Verwaltung; Social Media = erste Domäne
    brand="Dizz Management",        # betonte Marke (K2.3 .brand)
    version=__version__,
    port=8213,                      # verbindlich (App-Vertrag)
    icon="broadcast",
    sensitivity="hoch",             # SENSIBEL ⇒ KI lokal_only; OAuth-Tokens + Außenwirkung
    mcp=McpInfo(command=["<venv-python>", "managementapp/mcp_server.py"],
                tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    shares=Shares(summary=True, tools=[namespaced(APP_ID, t) for t in _MCP_TOOLS]),
    depends=["creator"],            # erhält Assets von Dizz Creating (REV-3, Empfangs-Slot)
)
