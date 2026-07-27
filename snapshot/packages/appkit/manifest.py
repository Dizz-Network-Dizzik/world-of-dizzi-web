"""Vernetzungs-Manifest — die maschinenlesbare Identität jeder App.

Das Manifest beantwortet für Dizzi (und jeden anderen Verbund-Teilnehmer):
WER ist die App, WO läuft sie, WIE sensibel sind ihre Daten, WAS teilt sie
(Stats/Tools/Events) und WOVON hängt sie ab. Es wird unter ``/api/manifest``
ausgeliefert und ist die Grundlage der generischen Dashboard-Anbindung —
Dizzi braucht KEINEN Per-App-Code mehr, um eine vertragskonforme App zu zeigen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field

from . import CONTRACT_VERSION

# Sensibilität steuert später das KI-Routing (K5): 'hoch'/'hoechst' ⇒ Inhalte
# gehen NIE an Boost-/Cloud-Modelle und stehen nur bei verifizierter Verbindung
# bereit. Die Stufe wird JETZT deklariert, damit kein Nachrüsten nötig ist.
Sensitivity = Literal["normal", "hoch", "hoechst"]


class AuthInfo(BaseModel):
    """Identitäts-Anbindung der App (K1-Slot).

    ``status='vorbereitet'`` bedeutet: der Slot existiert, Dizzi-ID ist noch
    nicht gebaut — Routen mit Schutzstufe verweigern fail-closed (auth.py).
    K1 stellt auf ``'aktiv'`` um, ohne dass sich der Vertrag ändert.
    """

    sso: str = "dizzi-id"               # akzeptierter Identitäts-Provider
    standalone: bool = True             # eigener lokaler Login als Rückfall
    status: Literal["vorbereitet", "aktiv"] = "vorbereitet"


class McpInfo(BaseModel):
    """Wie der MCP-Server der App gestartet wird (stdio-Prozess, read-only v1)."""

    transport: Literal["stdio"] = "stdio"
    command: list[str] = []             # z. B. ["<venv-python>", "mcp_server.py"]
    tools: list[str] = []               # Tool-Namen (informativ, für Übersichten)


class Shares(BaseModel):
    """Was die App mit dem Verbund teilt (Vernetzungs-Vertrag)."""

    summary: bool = True                # /api/summary für die Dashboard-Kachel
    tools: list[str] = []               # geteilte MCP-Tools (Namen)
    events: bool = False                # Event-Push an Dizzi (kommt mit K4)


class AppManifest(BaseModel):
    id: str                             # technischer Schlüssel, z. B. 'finanzen'
    name: str                           # Anzeigename, z. B. 'Finanzmanagement'
    brand: str                          # Marke, z. B. 'Dizz Money'
    version: str                        # App-Version (semver)
    contract: str = CONTRACT_VERSION    # erfüllte Vertrags-Version
    host: str = "127.0.0.1"             # localhost-gebunden bis Auth-Vollausbau
    port: int
    icon: str = "box"                   # Icon-Schlüssel der Dizzi-Shell
    sensitivity: Sensitivity = "normal"
    auth: AuthInfo = AuthInfo()
    mcp: McpInfo = McpInfo()
    shares: Shares = Shares()
    depends: list[str] = []             # App-IDs, von denen diese App liest

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Deep-Link: öffnet die eigenständige App-Oberfläche aus Dizzi heraus."""
        return f"http://{self.host}:{self.port}"
