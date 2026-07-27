"""Connector-Katalog — dormante Dienst-Slots (Gesetz 5) für das Konten-Panel.

Macht die Konnektivitäts-Vision (docs/35) sichtbar: ALLE sinnvollen Kanäle/Dienste,
über die jemand schreiben könnte, als ehrliche **DORMANTE** Slots (W4
``DormantConnector``) — KEIN echter Plattform-Call ohne Tokens. Die AKTIVEN Adapter
(E-Mail in ``mail.py``, WhatsApp/Instagram in ``meta.py``, Telegram in ``telegram.py``)
leben dort; hier stehen die weiteren **vorbereiteten** Anschlüsse mit recherche-
fundiertem Aktivierungs-Pfad (Stand 26.06.2026 — APIs/Versionen/Permissions ändern
sich, vor Aktivierung gegen die Live-Doku prüfen).

Jeder Slot wird über ``ConnectorRegistry`` in ``/api/konnektoren`` sichtbar
(``verbunden=False``, ``dormant=True``, ``hinweis`` = Aktivierungs-Pfad). Senden bliebe
auch nach Aktivierung HITL (K4, fail-closed)."""
from __future__ import annotations

from appkit.connectors import DormantConnector

# (id, label, kind, richtung, aktivierung) — id muss eindeutig sein (nicht email/
# whatsapp/instagram/telegram: das sind die aktiven Adapter).
_KATALOG: tuple[tuple[str, str, str, str, str], ...] = (
    ("facebook_messenger", "Facebook Messenger", "messenger", "beides",
     "Meta Graph (Page Messaging): Facebook-Seite + Seiten-Token im Tresor, "
     "App-Review pages_messaging. Baugleich zu WhatsApp/Instagram (meta.py)."),
    ("threads", "Threads (Meta)", "messenger", "beides",
     "Meta Threads API: Token im Tresor; text-zentriert. Teil der Meta-Graph-Familie."),
    ("x_twitter", "X / Twitter DMs", "messenger", "beides",
     "X API v2: POST /2/dm_conversations/with/:id/messages + DM-Webhook. "
     "Developer-Account + kostenpflichtiger Tier + DM-Scopes."),
    ("linkedin", "LinkedIn", "messenger", "beides",
     "LinkedIn Messaging: Marketing-/Partner-Developer-Freigabe (InMail) ODER "
     "Drittanbieter-API (z. B. Unipile). Stark gegated."),
    ("slack", "Slack", "chat", "beides",
     "Slack Web API (chat.postMessage) + Events API; Bot-Token im Tresor, "
     "Scopes chat:write / im:history."),
    ("discord", "Discord", "chat", "beides",
     "Discord Bot-API: Bot-Token im Tresor; DMs nur bei gemeinsamem Server/Opt-in (Intents)."),
    ("signal", "Signal", "messenger", "beides",
     "Kein offizielles Dritt-API: lokale Brücke (signal-cli/signald) ODER "
     "Matrix-Bridge (Schiene B). Rein lokal möglich."),
    ("sms_rcs", "SMS / RCS", "sms", "beides",
     "Über einen Provider (Twilio/Vonage/…): API-Key im Tresor; kostenpflichtig. "
     "RCS wo verfügbar."),
    ("matrix", "Matrix", "messenger", "beides",
     "Schiene B: lokaler Homeserver (Conduit) + mautrix-Bridges; opt-in je Dienst. "
     "Architektur-Entscheidung — Architektur-KI-Park."),
    ("snapchat", "Snapchat", "messenger", "lesen",
     "KEIN offener Consumer-DM-API. Nur Webview (Schiene A, manuell); die offizielle "
     "Messaging-API ist auf Brand↔Creator beschränkt (Allowlist)."),
)


def _slot(id_: str, label: str, kind: str, richtung: str, aktivierung: str) -> DormantConnector:
    """Ein dormanter Katalog-Slot als ``DormantConnector`` (verfuegbar()==False)."""
    return type("Slot_" + id_, (DormantConnector,), {
        "id": id_, "label": label, "kind": kind, "richtung": richtung,
        "sensitivity": "hoch", "aktivierung": aktivierung})()


def dormante_konnektoren() -> list[DormantConnector]:
    """Alle vorbereiteten Dienst-Slots (Gesetz 5) — für die ConnectorRegistry."""
    return [_slot(*row) for row in _KATALOG]
