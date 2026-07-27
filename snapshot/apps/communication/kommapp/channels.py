"""Kanal-Connectoren von Dizz Communication — der austauschbare Multi-Kanal-Stecker.

═══════════════════════════════════════════════════════════════════════════════
GESETZ 5 — VORBEREITUNG, NICHT BAU. Dieses Modul ist das Gerüst, das die
Konnektivitäts-Vision (docs/35 §2: „Dizz Communication = das Vernetzungs-
Flaggschiff") app-seitig trägt. EINE Schnittstelle ``ChannelConnector``, viele
Stecker. v1 hat GENAU EINEN aktiven Kanal — **E-Mail** (IMAP/SMTP/XOAUTH2 aus
mail.py, der risikofreie Kern). Telegram/WhatsApp/Instagram/Snapchat sind
**vorbereitete, dormante Stecker**: sie sind sichtbar (``/api/kanaele`` + Mode-
Schalter im Einstellungsfenster), aber jeder Abruf/Versand scheitert EHRLICH
(fail-closed), bis ein Live-Pfad scharfgeschaltet wird. Bewusstsein über das
Vorhandensein dieser Anschlüsse ist ausdrücklich Teil des Auftrags (Gesetz 5) —
sie stehen im Code UND in der Doku (docs/03_KANAL_VORBEREITUNG.md).
═══════════════════════════════════════════════════════════════════════════════

── INTEGRATIONS-PUNKT (docs/35 §5.1 + docs/36 W4) ──────────────────────────────
Der World-Chat baut ein universelles appkit-Connector-Gerüst
(``appkit/connectors.py``, ein ``ExternalConnector``-Interface, das JEDE App erbt).
Diese App-seitige ``ChannelConnector``-Schicht ist BEWUSST so geschnitten, dass
sie SPÄTER darauf aufsetzt: ``status()`` liefert bereits das Vokabular
(verbunden/aktiv/weg/modus_setting), und ``senden`` ist die einzige Außen-Kante
(hinter K4-HITL). Sobald appkit das Gerüst stellt, werden diese Klassen davon
ab­geleitet — KEIN Domänen-Umbau. Bis dahin lebt die Schicht hier (Standalone-
Konnektivität: jede App trägt ihre Konnektoren selbst, docs/35 §1).

── Sicherheit (sensitivity hoechst) ───────────────────────────────────────────
``senden`` ist NIE eigenmächtig: der Aufruf läuft ausschließlich hinter der
HITL-Aktion ``nachricht_senden`` (Stufe 'verifiziert', appkit/actions.py). Selbst
NACH der Freigabe ist der Versand bei dormanten Kanälen fail-closed (sie werfen
``KanalNichtVerbunden``), bis der echte Plattform-Pfad scharf ist. Echte Adapter
gibt es für **WhatsApp/Instagram** (``meta.py``, Graph-API) und **Telegram**
(``telegram.py``, Bot-API) — dormant bis Token im Tresor; Snapchat/Bridges bleiben
vorbereitete Slots (Schiene A/B, Architektur-KI-Park).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from .mail import KANAL_EMAIL

# Die Kanäle, die Communication kennt/vorbereitet. Reihenfolge = UI-Default.
# ``email`` ist der EINE aktive Stecker; der Rest ist dormant (W4-Gerüst folgt).
KANAELE: tuple[str, ...] = (KANAL_EMAIL, "telegram", "whatsapp", "instagram", "snapchat")


@dataclass
class AusgehendeNachricht:
    """Eine versandfertige Nachricht — kanal-unabhängig normiert (Unified Reply).

    Die Domäne baut das aus dem unified Kontakt-Thread; jeder Connector mappt es
    auf seinen Kanal. ``an`` ist die Ziel-Identität im jeweiligen Kanal (E-Mail-
    Adresse / Handle / Telefon); ``betreff`` trägt nur E-Mail (Messenger ignorieren
    es). ``konto_id`` benennt bei E-Mail das absendende Konto."""

    an: str
    text: str = ""
    betreff: str = ""
    kanal_typ: str = KANAL_EMAIL
    konto_id: str = ""
    kontakt_id: str = ""
    konversation_id: str = ""
    template: str = ""               # optional: WA-Template (außerhalb des 24-h-Fensters; E-Mail ignoriert es)


class KanalNichtVerbunden(RuntimeError):
    """Connector ist deklariert, aber (noch) nicht verbunden/scharf — ehrlich
    statt etwas vorzutäuschen (fail-closed)."""


# ── Interface (der Vertrag, gegen den die Domäne arbeitet) ────────────────────
class ChannelConnector(ABC):
    """Ein Kommunikations-Kanal als austauschbarer Stecker. Unterklassen
    implementieren ``verbunden`` (ehrlich) + ``senden`` (Außenwirkung, hinter
    HITL). Empfang läuft v1 über die kanal-eigenen Sync-/Ingest-Pfade (E-Mail:
    mail.py; Simulation: Demo-Ingest) — der Connector bündelt Status + Versand."""

    name: str = "Kanal"
    kanal_typ: str = "kanal"
    aktiv: bool = False               # True = real gebauter Kanal, False = dormanter Slot
    weg: str = ""                     # wie der Live-Pfad später entsteht (Schiene A/B/native API)
    modus_setting: str = ""           # K2-Setting, das den Kanal später scharfschaltet

    @abstractmethod
    def verbunden(self) -> bool:
        """True, wenn über den Kanal real gesendet werden kann. Ehrlich statt
        optimistisch — dormante Slots melden immer False."""

    @abstractmethod
    def senden(self, out: AusgehendeNachricht) -> dict[str, Any]:
        """Versendet eine Nachricht (Außenwirkung!). Dormant ⇒ ``KanalNichtVerbunden``."""

    def status(self) -> dict[str, Any]:
        """Für UI (``/api/kanaele``) und Bewusstsein über die Slots (Gesetz 5)."""
        return {"kanal_typ": self.kanal_typ, "name": self.name,
                "aktiv": self.aktiv, "verbunden": self.verbunden(),
                "weg": self.weg, "modus_setting": self.modus_setting,
                "integration_punkt": "appkit/connectors.py (docs/36 W4)"}


# ── E-Mail — der EINE aktive Stecker ──────────────────────────────────────────
class EmailConnector(ChannelConnector):
    """E-Mail = der risikofreie, real funktionierende Kanal (mail.py). ``senden``
    delegiert an die bestehende, tresor-gestützte SMTP-Strecke (über ``sende``);
    der eigentliche Versand läuft weiter hinter der HITL-Freigabe. ``verbunden``
    ist True, sobald ein sendefähiges (SMTP-) Konto existiert.

    ``sende``/``konto_vorhanden`` werden injiziert (wie ``vault_get`` bei den
    anderen Apps), damit die Schicht ohne App-Wiring testbar bleibt."""

    name = "E-Mail"
    kanal_typ = KANAL_EMAIL
    aktiv = True
    weg = "IMAP/SMTP + XOAUTH2 (mail.py) — der risikofreie Kern"

    def __init__(self, konto_vorhanden: Callable[[], bool] | None = None,
                 sende: Callable[[AusgehendeNachricht], dict[str, Any]] | None = None) -> None:
        self._vorhanden = konto_vorhanden or (lambda: False)
        self._sende = sende

    def verbunden(self) -> bool:
        try:
            return bool(self._vorhanden())
        except Exception:
            return False

    def senden(self, out: AusgehendeNachricht) -> dict[str, Any]:
        if self._sende is None or not self.verbunden():
            raise KanalNichtVerbunden(
                "Kein sendefähiges E-Mail-Konto (SMTP) vorhanden — Konto verbinden.")
        return self._sende(out)

    def status(self) -> dict[str, Any]:
        s = super().status()
        s["hinweis"] = ("E-Mail ist der aktive Kanal: Abruf (IMAP/XOAUTH2) und Versand "
                        "(SMTP) laufen real. Senden bleibt HITL (verifiziert, fail-closed).")
        return s


# ── Dormante Messenger-Stecker (Gesetz 5: vorbereitet, ohne Funktion) ─────────
class _DormanterKanal(ChannelConnector):
    """Gemeinsame Basis der vorbereiteten Messenger-Stecker. v1 ist Empfang
    simuliert (Demo-Ingest) und Versand fail-closed: ``senden`` scheitert EHRLICH,
    bis der Live-Pfad (Schiene A Webview / Schiene B Matrix-Bridge / native API)
    scharfgeschaltet wird. Das ist Architektur-Entscheidung + Architektur-KI-Park (docs/35 §6)."""

    aktiv = False

    def verbunden(self) -> bool:
        return False

    def senden(self, out: AusgehendeNachricht) -> dict[str, Any]:
        raise KanalNichtVerbunden(
            f"{self.name} ist noch nicht verbunden — Kanal vorbereitet (Gesetz 5). "
            f"Aktivierung über {self.weg}.")

    def status(self) -> dict[str, Any]:
        s = super().status()
        s["hinweis"] = (f"{self.name}: VORBEREITET ohne Funktion (Gesetz 5). Empfang v1 "
                        f"simuliert (Demo-Ingest), Versand fail-closed. Aktivierung über "
                        f"{self.weg}; Mode-Schalter: {self.modus_setting or '—'}.")
        return s


class _AdapterKanal(_DormanterKanal):
    """Messenger mit einem ECHTEN (aber dormant-bis-Token) Adapter dahinter — Meta
    (``meta.py``, Graph-API) ODER Telegram (``telegram.py``, Bot-API). Ist ein Adapter
    verdrahtet, gilt der Kanal als ``aktiv`` (echter Stecker da) und ``verbunden``
    spiegelt die Token-Verfügbarkeit; ``senden`` delegiert an den Adapter (real bzw.
    fail-closed). OHNE verdrahteten Adapter bleibt es ein reiner Gesetz-5-Slot (dormant).
    Der Adapter ist bewusst nur DUCK-getypt (kein Import) — channels.py bleibt von
    meta.py/telegram.py entkoppelt; main.py verdrahtet beide."""

    def __init__(self, adapter: Any | None = None) -> None:
        self._adapter = adapter
        self.aktiv = adapter is not None     # echter Adapter vorhanden ⇒ aktiv

    def verbunden(self) -> bool:
        try:
            return bool(self._adapter and self._adapter.verfuegbar())
        except Exception:
            return False

    def senden(self, out: AusgehendeNachricht) -> dict[str, Any]:
        if self._adapter is None:
            return super().senden(out)        # reiner Slot ⇒ fail-closed
        # ``template`` nutzt nur Meta außerhalb des 24-h-Fensters; Telegram ignoriert es.
        return self._adapter.senden(an=out.an, text=out.text,
                                    template=(out.template or None))  # real oder fail-closed

    def status(self) -> dict[str, Any]:
        s = ChannelConnector.status(self)
        if self._adapter is None:
            s["hinweis"] = (f"{self.name}: VORBEREITET ohne Funktion (Gesetz 5). "
                            f"Aktivierung über {self.weg}; Mode-Schalter: "
                            f"{self.modus_setting or '—'}.")
            return s
        try:
            mi = self._adapter.info()
        except Exception:
            mi = None
        s["aktivierung"] = getattr(self._adapter, "aktivierung", "")
        s["hinweis"] = ((mi.hinweis if mi else "")
                        or f"{self.name}: echter Adapter, dormant bis Token im Tresor.")
        if mi is not None:
            s["permissions"] = (mi.extra or {}).get("permissions", [])
            s["api_doc"] = (mi.extra or {}).get("api_doc", "")
        return s


class TelegramConnector(_AdapterKanal):
    """Telegram — echter Stecker über die **Bot-API** (``telegram.TelegramBotConnector``),
    dormant bis Bot-Token im Tresor. Lokal über Long-Polling (kein Webhook/App-Review);
    Empfänger = numerische chat_id."""

    name = "Telegram"
    kanal_typ = "telegram"
    weg = "Telegram Bot-API — Token im Tresor (telegram_bot_token), lokal via Long-Polling"
    modus_setting = "bridge_telegram_vorbereitet"   # etablierter SettingDef-Key (beibehalten)


class WhatsAppConnector(_AdapterKanal):
    """WhatsApp — echter Stecker über die **WhatsApp Business Cloud API**
    (``meta.WhatsAppConnector``), dormant bis Token im Tresor. (Alternativ-Pfade
    Schiene A/B bleiben denkbar, aber die Cloud-API ist der gebaute Weg.)"""

    name = "WhatsApp"
    kanal_typ = "whatsapp"
    weg = "WhatsApp Business Cloud API (Graph) — Token im Tresor + phone_number_id"
    modus_setting = "bridge_whatsapp_vorbereitet"


class InstagramConnector(_AdapterKanal):
    """Instagram-DMs — echter Stecker über die **Instagram-Messaging-/Graph-API**
    (``meta.InstagramConnector``), dormant bis Token im Tresor."""

    name = "Instagram"
    kanal_typ = "instagram"
    weg = "Instagram-Messaging-API (Graph) — Token im Tresor + ig_user_id"
    modus_setting = "kanal_instagram_vorbereitet"


class SnapchatConnector(_DormanterKanal):
    """Snapchat — vorbereiteter Stecker. Snap hat keine offene Messaging-API ⇒
    der einzige realistische Live-Pfad ist Webview (Schiene A, manuell)."""

    name = "Snapchat"
    kanal_typ = "snapchat"
    weg = "Webview (Schiene A) — Snapchat hat keine offene Messaging-API"
    modus_setting = "kanal_snapchat_vorbereitet"


# ── Registry + Factory ────────────────────────────────────────────────────────
def registry(email_konto_vorhanden: Callable[[], bool] | None = None,
             email_sende: Callable[[AusgehendeNachricht], dict[str, Any]] | None = None,
             adapter: dict[str, Any] | None = None
             ) -> dict[str, ChannelConnector]:
    """Alle bekannten Connectoren als ``kanal_typ → ChannelConnector`` (Reihenfolge =
    ``KANAELE``). E-Mail wird mit dem realen Versand/Status-Prüfer verdrahtet;
    ``adapter`` (``kanal_typ → echter Adapter`` aus ``meta.py``/``telegram.py``)
    verdrahtet WhatsApp/Instagram/Telegram mit der echten API (dormant bis Token).
    Genau diese Funktion nutzt der Versand-Handler — KEIN if/else-Wildwuchs in der Domäne."""
    adapter = adapter or {}
    return {
        KANAL_EMAIL: EmailConnector(konto_vorhanden=email_konto_vorhanden,
                                    sende=email_sende),
        "telegram": TelegramConnector(adapter=adapter.get("telegram")),
        "whatsapp": WhatsAppConnector(adapter=adapter.get("whatsapp")),
        "instagram": InstagramConnector(adapter=adapter.get("instagram")),
        "snapchat": SnapchatConnector(),
    }


def connector_fuer(kanal_typ: str,
                   email_konto_vorhanden: Callable[[], bool] | None = None,
                   email_sende: Callable[[AusgehendeNachricht], dict[str, Any]] | None = None,
                   adapter: dict[str, Any] | None = None
                   ) -> ChannelConnector | None:
    """Connector zu einem ``kanal_typ`` (unbekannt ⇒ None)."""
    return registry(email_konto_vorhanden, email_sende, adapter).get(
        (kanal_typ or "").strip().lower())


def kanaele_status(email_konto_vorhanden: Callable[[], bool] | None = None,
                   adapter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Übersicht aller Kanäle + Verbindungsstatus für UI/MCP — macht die
    (auch dormanten) Anschlüsse SICHTBAR (Gesetz 5). Reihenfolge = ``KANAELE``."""
    reg = registry(email_konto_vorhanden=email_konto_vorhanden, adapter=adapter)
    return [reg[k].status() for k in KANAELE]
