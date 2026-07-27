"""Universelles Connector-Gerüst (Konnektivität = Kernziel, docs/35 §5.1 / docs/36 W4).

EIN einheitliches Muster für EXTERNE Quellen/Senken (Messenger, Kalender, Office-/
Projekt-Tools, KI-Tools, …), das JEDE App erbt — damit jede App auch STANDALONE
konnektiv ist (wie sie ihr eigenes ``defense``/``/mcp`` trägt). Bewusst nach dem
bewährten Gesetz-5-Wearable-Muster (health/sources.py): Interface + DORMANTE Adapter
(ehrlich „nicht verbunden") + sichtbarer Status über ``/api/konnektoren``.

GRENZEN (Sicherheit, docs/35 §5.2/§5.4 — verbindlich):
- **Lesen** ist read-only + best-effort (Quelle offline ⇒ leer, nie Crash).
- **Schreiben/Senden/Außenwirkung** läuft NIE autonom über dieses Gerüst, sondern über
  die **K4-HITL-Aktionen** der App (Stufe ``verifiziert``, fail-closed). Ein Connector
  DEKLARIERT nur, dass er eine Richtung kann (``richtung``); ausgeführt wird über HITL.
- **Tokens/Secrets** gehören in den OS-Secret-Store/Tresor (appkit/vault.py) — NIE in
  DB/Settings.
- **Echte Plattform-APIs** werden hier NICHT implementiert. Das Gerüst macht die spätere
  Anbindung zu einem **Stecker** (Aktivierung „wenn nötig"), kein Umbau.

Nutzung in einer App:
    reg = ConnectorRegistry()
    reg.register(MeinEmailConnector(...))          # aktiv
    reg.register(TelegramConnector())              # dormant (Stub)
    app.include_router(connectors_router(reg))     # GET /api/konnektoren (read-only)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from fastapi import APIRouter

RICHTUNGEN = ("lesen", "senden", "beides")


class KonnektorNichtVerbunden(RuntimeError):
    """Adapter ist deklariert, aber (noch) nicht verbunden — ehrlich statt raten."""


@dataclass
class ConnectorInfo:
    """Selbstauskunft eines Connectors — für UI (``/api/konnektoren``) + MCP."""
    id: str
    label: str
    kind: str                       # 'messenger'|'kalender'|'office'|'projekt'|'ki'|…
    richtung: str = "lesen"         # lesen|senden|beides (senden = nur über App-HITL)
    sensitivity: str = "normal"     # normal|hoch|hoechst (Routing/Anzeige)
    verbunden: bool = False
    dormant: bool = True            # True = Stub/„noch nicht verbunden"
    hinweis: str = ""               # was fehlt zur Aktivierung (ehrlich)
    token_name: str = ""            # erwarteter Tresor-Schlüssel (NIE der Token selbst!)
    permissions: tuple[str, ...] = ()  # deklarierte Scopes (z. B. 'read:messages')
    extra: dict[str, Any] = field(default_factory=dict)


class ExternalConnector(ABC):
    """Vertrag, gegen den die App arbeitet. Adapter setzen die Klassen-Attribute +
    implementieren ``verfuegbar`` (ehrlich); ``lesen`` überschreiben aktive Quellen.

    Sicherheitslinie (docs/35 §5.2, verbindlich): **Lesen** = read-only/best-effort;
    **Senden/Außenwirkung** läuft NIE autonom hier, sondern über die K4-HITL-Aktion
    der App — ``senden`` ist nur ein DEKLARIERENDER Slot. Tokens liegen im Tresor
    (``token_name`` benennt nur den Schlüssel)."""

    id: str = "konnektor"
    label: str = "Konnektor"
    kind: str = "extern"
    richtung: str = "lesen"
    sensitivity: str = "normal"
    aktivierung: str = ""           # Doku: was schaltet ihn scharf
    token_name: str = ""            # Tresor-Schlüssel-NAME (nie das Geheimnis selbst)
    permissions: tuple[str, ...] = ()  # deklarierte Scopes (Transparenz/Audit)

    @abstractmethod
    def verfuegbar(self) -> bool:
        """True nur, wenn der Connector real nutzbar ist (Token da / Brücke verbunden).
        Ehrlich statt optimistisch — ungenutzte Slots melden False."""

    def lesen(self, **kw: Any) -> list[dict[str, Any]]:
        """Read-only-Abruf. Default = nicht verbunden (dormante Adapter erben das);
        aktive Adapter überschreiben. Wirft nie spontan — der Aufrufer ist best-effort."""
        raise KonnektorNichtVerbunden(
            f"{self.id} nicht verbunden — {self.aktivierung or 'Aktivierung ausstehend'}.")

    def lesen_sicher(self, **kw: Any) -> list[dict[str, Any]]:
        """Best-effort-Lesen: fängt ``KonnektorNichtVerbunden``/Adapter-Fehler ab und
        liefert ``[]`` — die zentrale „wirft nie"-Variante, die der Vertrag verspricht
        (Aufrufer müssen nicht jeder für sich ein try/except bauen)."""
        try:
            return list(self.lesen(**kw))
        except Exception:
            return []

    def senden(self, **kw: Any) -> dict[str, Any]:
        """DEKLARIERENDER Outbound-Slot. Standard = nicht autonom ausführbar: Senden/
        Außenwirkung läuft über die **K4-HITL-Aktion** der App (Stufe ``verifiziert``,
        fail-closed), NIE direkt über den Konnektor. Aktive Adapter dürfen hier höchstens
        einen Sende-VORSCHLAG vorbereiten (Rückgabe-dict) — ausgeführt wird via HITL."""
        raise KonnektorNichtVerbunden(
            f"{self.id}: Senden läuft ausschließlich über die K4-HITL-Freigabe "
            "(docs/35 §5.2), nie autonom über den Konnektor.")

    def info(self) -> ConnectorInfo:
        verbunden = False
        try:
            verbunden = bool(self.verfuegbar())
        except Exception:
            verbunden = False
        return ConnectorInfo(
            id=self.id, label=self.label, kind=self.kind, richtung=self.richtung,
            sensitivity=self.sensitivity, verbunden=verbunden, dormant=not verbunden,
            hinweis=("" if verbunden else (self.aktivierung or "noch nicht verbunden")),
            token_name=self.token_name, permissions=tuple(self.permissions))

    def status(self) -> dict[str, Any]:
        return asdict(self.info())


class DormantConnector(ExternalConnector):
    """Bequeme Basis für einen DEKLARIERTEN, noch nicht verbundenen Adapter (Stub).
    Unterklassen setzen id/label/kind/richtung/sensitivity/aktivierung — fertig.
    Macht den Anschluss SICHTBAR (Konnektivitäts-Vision), ohne ihn scharf zu schalten."""

    def verfuegbar(self) -> bool:
        return False


class TokenConnector(ExternalConnector):
    """Vault-bewusste Basis (vereint das admin/konnektoren-Muster): „verbunden",
    sobald ``token_name`` einen Wert im Tresor hat. ``vault_get(name)->secret|None``
    wird injiziert (NIE direkt aus DB/Settings lesen). Bleibt read-only/dormant bis
    ein echter Adapter ``lesen`` überschreibt — der Token macht ihn nur SICHTBAR
    „verbunden", schaltet aber kein Live-Lesen autonom scharf."""

    def __init__(self, vault_get: Callable[[str], Any] | None = None) -> None:
        self._vault_get = vault_get or (lambda _name: None)

    def verfuegbar(self) -> bool:
        if not self.token_name:
            return False
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False


class ConnectorRegistry:
    """Welche Connectors kennt die App, welche sind verbunden? (wie health.quellen_status)."""

    def __init__(self) -> None:
        self._conns: dict[str, ExternalConnector] = {}

    def register(self, connector: ExternalConnector) -> ExternalConnector:
        if connector.id in self._conns:
            raise ValueError(f"Connector doppelt registriert: {connector.id!r}")
        if connector.richtung not in RICHTUNGEN:
            raise ValueError(f"Unbekannte richtung: {connector.richtung!r}")
        self._conns[connector.id] = connector
        return connector

    def get(self, conn_id: str) -> ExternalConnector | None:
        return self._conns.get(conn_id)

    def liste(self) -> list[ConnectorInfo]:
        return [c.info() for c in self._conns.values()]

    def status(self) -> list[dict[str, Any]]:
        return [c.status() for c in self._conns.values()]


def connectors_router(registry: ConnectorRegistry,
                      prefix: str = "/api/konnektoren") -> APIRouter:
    """Read-only-Router: ``GET /api/konnektoren`` listet alle Connectors + Status.
    Macht die (auch dormanten) Anschlüsse sichtbar — kein Schreibpfad."""
    router = APIRouter(prefix=prefix, tags=["konnektoren"])

    @router.get("")
    def liste() -> dict[str, Any]:
        st = registry.status()
        return {"konnektoren": st, "anzahl": len(st),
                "verbunden": sum(1 for c in st if c.get("verbunden"))}

    return router
