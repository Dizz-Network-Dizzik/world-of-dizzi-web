"""Kanal-Quellen von Dizz Management — der austauschbare Plattform-Stecker.

═══════════════════════════════════════════════════════════════════════════════
GESETZ 5 — VORBEREITUNG, NICHT BAU. Dieses Modul ist bewusst ein Gerüst aus
dokumentierten Slots. v1 PLANT/ENTWIRFT lokal; das echte Posten an fremde Kanäle
(Instagram/TikTok/X/LinkedIn/YouTube/…) ist hier so weit vorbereitet, dass die
spätere Anbindung ein **Stecker** ist, kein Umbau. Posten an echte Kanäle bleibt
v1 DORMANT (Recht/Opt-in/Plattform-Richtlinien) — ausdrücklich Teil des Auftrags
(Gesetz 5): die Anschlüsse stehen im Code UND in der Systemübersicht
(SYSTEMUEBERSICHT.md) + docs/04_CHANNEL_VORBEREITUNG.md.
═══════════════════════════════════════════════════════════════════════════════

Kernidee (docs/RECHERCHE §2–§3, §6): Plattform-APIs sind fragmentiert und ändern
sich ständig. Die App spricht deshalb NIE direkt mit einer konkreten Plattform im
Domänen-Code (kein if/else-Wildwuchs), sondern gegen EIN Interface
``ChannelSource``. Plattform-Eigenheiten (Limits, Formate, OAuth-Scopes) leben als
Adapter-Konfig. Austauschbar dahinter: entweder ein Adapter je Plattform ODER EIN
Unified-Provider-Adapter (Ayrshare) für alle.

Vorbereitete Adapter (dokumentierte Slots — v1 DORMANT, ehrlich „nicht verbunden"):

- ``OAuthChannelSource``  — Basis für DIREKTE Plattform-APIs (0 €, volle Tiefe,
                            viel Wartung). Auth über OAuth-Token im **Token-Tresor**
                            (appkit/vault.py); ``verbunden()`` ist True, sobald der
                            Token da ist. Konkret: Instagram/Threads (Meta Graph),
                            X/Twitter, LinkedIn, YouTube (Google), Bluesky (AT-Proto),
                            Mastodon (Instanz-Token).
- ``UnifiedProviderSource`` — EINE Integration für ~alle Kanäle über Ayrshare
                            (13+ Kanäle, eigener MCP-Server). Cloud-API, Token-Tresor-
                            gated, **opt-in + kostet** ⇒ verletzt den 0-€-Anspruch,
                            daher NICHT Default (lokal-first).
- ``PostizSource``        — **OSS-Selfhost** (Postiz, REST-API) als 0-€-Unified-Pfad:
                            eine self-gehostete Instanz übernimmt das Multi-Kanal-
                            Posten/Scheduling. base_url + API-Key im Tresor.

── Veröffentlichen = Außenwirkung (docs/RECHERCHE §3–§5) ──────────────────────────
``publish`` ist NIE eigenmächtig: der Aufruf läuft hinter der HITL-Aktion
``post_veroeffentlichen`` (Stufe 'verifiziert', appkit/actions.py). Selbst NACH der
Freigabe ist Live-Posten v1 dormant — die Adapter werfen ``KanalNichtVerbunden``,
bis ein Token im Tresor liegt UND der Live-Pfad bewusst scharfgeschaltet wird.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

# Vom Netzwerk unterstützte / vorbereitete Plattformen (docs/RECHERCHE §2).
# Reihenfolge = UI-Default. Erweiterbar ohne Domänen-Umbau (neuer Adapter unten).
PLATTFORMEN: tuple[str, ...] = (
    "instagram", "tiktok", "x", "linkedin", "youtube",
    "threads", "bluesky", "mastodon",
)


# ── Normiertes Austausch-Format (was die Domäne an einen Adapter übergibt) ────
@dataclass
class OutboundPost:
    """Ein veröffentlichungsfertiger Post, normiert — unabhängig von der Zielplattform.

    Die Domäne baut das aus einem ``posts``-Datensatz; jeder Adapter mappt es auf
    seine Plattform-API. ``format`` ist das Seitenverhältnis (9:16/1:1/16:9), das die
    pro-Kanal-Derivate tragen. ``extern_ref`` ist der stabile Post-Schlüssel
    (Idempotenz beim späteren Sync/Status-Abruf)."""

    text: str = ""
    hashtags: str = ""
    medien: list[str] = field(default_factory=list)   # Pfade/Asset-Refs (DAM)
    format: str = ""                                  # 9:16 | 1:1 | 16:9 | …
    heikel: bool = False                                # REV-4: kanal-/AVS-konforme Behandlung
    titel: str = ""
    extern_ref: str = ""                              # Plattform-Post-ID (nach Publish)


class KanalNichtVerbunden(RuntimeError):
    """Adapter ist deklariert, aber (noch) nicht verbunden/scharf — ehrlich statt raten."""


# ── Interface (der Vertrag, gegen den die Domäne arbeitet) ────────────────────
class ChannelSource(ABC):
    """Ein Social-Media-Kanal als austauschbarer Stecker. v1 = Posten DORMANT.
    Adapter implementieren ``verbunden`` (ehrlich) + ``publish`` (Außenwirkung,
    hinter HITL). ``analytics`` (Reichweite/Engagement) ist ein späterer Slot."""

    name: str = "kanal"
    plattform: str = "kanal"

    @abstractmethod
    def verbunden(self) -> bool:
        """True, wenn der Kanal nutzbar ist (OAuth-Token im Tresor / Selfhost
        erreichbar). Ehrlich statt optimistisch — ungenutzte Slots melden False."""

    @abstractmethod
    def publish(self, post: OutboundPost) -> dict[str, Any]:
        """Veröffentlicht einen Post (Außenwirkung!). v1 dormant ⇒ ``KanalNichtVerbunden``.
        Erst scharf, wenn Token vorhanden UND Live-Pfad freigeschaltet."""

    def analytics(self, extern_ref: str = "") -> dict[str, Any]:
        """Reichweite/Engagement (späterer Slot). v1 leer/dormant."""
        if not self.verbunden():
            raise KanalNichtVerbunden(f"{self.name} nicht verbunden — keine Analytics.")
        raise KanalNichtVerbunden("Analytics-Abruf ist v1 noch nicht freigeschaltet (Slot).")

    def status(self) -> dict[str, Any]:
        """Für UI/MCP: was ist das, ist es verbunden, was fehlt zur Aktivierung?"""
        return {"name": self.name, "plattform": self.plattform,
                "verbunden": self.verbunden(), "posten_scharf": False}


# ── Direkte Plattform-APIs (0 €, OAuth-Token-Tresor-gated) ────────────────────
class OAuthChannelSource(ChannelSource):
    """Basis für DIREKTE Plattform-APIs. Auth über ein OAuth-Token im App-Token-
    Tresor (appkit/vault.py, Name = ``token_name``) — NIE in app_settings, NIE im
    Repo. ``verbunden()`` wird True, sobald der Token da ist; ``publish`` ist auch
    dann v1 dormant (Live-Pfad bewusst scharfzuschalten).

    ── Aktivierung (Gesetz 5: vorbereitet, nicht aktiv) ──────────────────────
    1. App in der Plattform-Developer-Konsole registrieren (App-ID/Secret), die
       nötigen ``SCOPES`` anfragen, OAuth-Redirect einrichten.
    2. Den erhaltenen (Refresh-)Token verschlüsselt in den Token-Tresor legen
       (token_name). Refresh-Rotation ist ein vorgesehener Slot.
    3. ``publish`` auf den echten API-Call der Plattform umstellen (Endpoint je
       Adapter unten dokumentiert) + Rate-Limit/Retry/Backoff (docs/RECHERCHE §6)."""

    # Pro-Plattform überschrieben (Doku für die spätere Aktivierung):
    API_DOC = ""
    SCOPES: tuple[str, ...] = ()

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str | None = None) -> None:
        self._vault_get = vault_get or (lambda _n: None)
        self.token_name = token_name or f"{self.plattform}_oauth_token"

    def verbunden(self) -> bool:
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "plattform": self.plattform,
                "verbunden": self.verbunden(), "posten_scharf": False,
                "token_name": self.token_name, "scopes": list(self.SCOPES),
                "api_doc": self.API_DOC,
                "hinweis": "Direkte Plattform-API (0 €). OAuth-Token im Tresor "
                           "hinterlegen ⇒ verbunden; echtes Posten erst mit "
                           "scharfgeschaltetem Live-Pfad (v1 DORMANT, Recht/Opt-in)."}

    def publish(self, post: OutboundPost) -> dict[str, Any]:
        if not self.verbunden():
            raise KanalNichtVerbunden(
                f"{self.name} nicht verbunden — OAuth-Token fehlt im Tresor "
                f"(erwarteter Name: {self.token_name!r}).")
        raise KanalNichtVerbunden(
            f"{self.name}-Live-Posten ist v1 noch nicht freigeschaltet "
            "(Adapter-Gerüst steht; Aktivierung = Live-Pfad + Plattform-Review).")


class InstagramSource(OAuthChannelSource):
    """Instagram (Meta Graph API, Content Publishing). Braucht ein Business-/Creator-
    Konto + verknüpfte Facebook-Seite; Medien per Container-Upload, dann Publish."""

    name = "Instagram"
    plattform = "instagram"
    API_DOC = "https://developers.facebook.com/docs/instagram-platform/content-publishing"
    SCOPES = ("instagram_basic", "instagram_content_publish", "pages_show_list")


class ThreadsSource(OAuthChannelSource):
    """Threads (Meta Threads API). Eigene API-Familie neben Instagram, gleiche Meta-
    Developer-Welt; Text-zentriert mit Medien-Anhang."""

    name = "Threads"
    plattform = "threads"
    API_DOC = "https://developers.facebook.com/docs/threads"
    SCOPES = ("threads_basic", "threads_content_publish")


class TikTokSource(OAuthChannelSource):
    """TikTok (Content Posting API). Direct-Post oder Upload-to-Inbox; Audit-Status
    der App entscheidet, ob öffentlich gepostet werden darf (sonst privat)."""

    name = "TikTok"
    plattform = "tiktok"
    API_DOC = "https://developers.tiktok.com/doc/content-posting-api-get-started"
    SCOPES = ("video.publish", "video.upload")


class XSource(OAuthChannelSource):
    """X / Twitter (API v2). Tweet-Erstellung + Medien-Upload; Tarif-/Rate-Limit-
    abhängig (kostenpflichtige Tiers für höhere Volumina)."""

    name = "X (Twitter)"
    plattform = "x"
    API_DOC = "https://docs.x.com/x-api/posts/creation-of-a-post"
    SCOPES = ("tweet.write", "tweet.read", "users.read", "media.write")


class LinkedInSource(OAuthChannelSource):
    """LinkedIn (Posts/UGC API). Persönliches Profil oder Organisations-Seite;
    ``w_member_social`` für das Posten im Namen des Mitglieds."""

    name = "LinkedIn"
    plattform = "linkedin"
    API_DOC = "https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api"
    SCOPES = ("w_member_social", "r_basicprofile")


class YouTubeSource(OAuthChannelSource):
    """YouTube (Data API v3, videos.insert). Resumable-Upload des Videos +
    Metadaten (Titel/Beschreibung/Tags/Sichtbarkeit). Google-OAuth."""

    name = "YouTube"
    plattform = "youtube"
    API_DOC = "https://developers.google.com/youtube/v3/docs/videos/insert"
    SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)


class BlueskySource(OAuthChannelSource):
    """Bluesky (AT-Protokoll, offen). Kein klassisches OAuth — App-Passwort/Session
    gegen den PDS; Token (App-Passwort) liegt im Tresor. Offen & 0 €."""

    name = "Bluesky"
    plattform = "bluesky"
    API_DOC = "https://docs.bsky.app/docs/get-started"
    SCOPES = ("com.atproto.repo.createRecord",)


class MastodonSource(OAuthChannelSource):
    """Mastodon (offen, instanz-basiert). Zugriffstoken pro Instanz; ``write:statuses``
    zum Posten. Instanz-URL gehört zur Adapter-Konfig (späterer Slot)."""

    name = "Mastodon"
    plattform = "mastodon"
    API_DOC = "https://docs.joinmastodon.org/methods/statuses/"
    SCOPES = ("write:statuses", "write:media")


# ── Unified-Provider (Ayrshare) — opt-in, kostet, hat eigenen MCP ─────────────
class UnifiedProviderSource(ChannelSource):
    """EINE Integration für ~alle Kanäle über einen Unified-Posting-Anbieter
    (Ayrshare, docs/RECHERCHE §2). Cloud-API ⇒ API-Key im Tresor nötig, ausdrücklich
    **opt-in** und ggf. **kostenpflichtig** (verletzt den 0-€-Anspruch, daher nicht
    Default). Spart enorm Wartung (jede Plattform-API ändert sich ständig).

    Hinweis: Ayrshare bietet einen eigenen MCP-Server für KI-Agenten — ein späterer
    Integrationspfad, sobald der Nutzer den Provider opt-in aktiviert."""

    name = "Ayrshare (Unified)"
    plattform = "unified"
    API_DOC = "https://www.ayrshare.com/docs/"

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str = "ayrshare_api_key") -> None:
        self._vault_get = vault_get or (lambda _n: None)
        self.token_name = token_name

    def verbunden(self) -> bool:
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "plattform": self.plattform,
                "verbunden": self.verbunden(), "posten_scharf": False,
                "token_name": self.token_name, "api_doc": self.API_DOC,
                "hinweis": "Unified-Posting-API (13+ Kanäle, eigener MCP-Server). "
                           "API-Key im Tresor ⇒ verbunden. Opt-in + kostet ⇒ kein "
                           "Default; direkte Plattform-APIs bleiben der 0-€-Vorzug."}

    def publish(self, post: OutboundPost) -> dict[str, Any]:
        if not self.verbunden():
            raise KanalNichtVerbunden(
                f"{self.name} nicht verbunden — API-Key fehlt im Tresor "
                f"(erwarteter Name: {self.token_name!r}).")
        raise KanalNichtVerbunden(
            "Unified-Live-Posten ist v1 noch nicht freigeschaltet (opt-in + Aktivierung).")


# ── Postiz (OSS-Selfhost) — 0-€-Unified-Pfad ──────────────────────────────────
class PostizSource(ChannelSource):
    """OSS-Selfhost-Unified-Pfad über eine self-gehostete **Postiz**-Instanz
    (REST-API, n8n/Zapier-anbindbar, docs/RECHERCHE §2). 0 €, voll in eigener Hand,
    aber Betriebsaufwand (eigene Instanz). base_url + API-Key im Tresor."""

    name = "Postiz (Selfhost)"
    plattform = "postiz"
    API_DOC = "https://docs.postiz.com/public-api"

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 token_name: str = "postiz_api_key", base_url: str = "") -> None:
        self._vault_get = vault_get or (lambda _n: None)
        self.token_name = token_name
        self.base_url = base_url

    def verbunden(self) -> bool:
        try:
            return bool(self._vault_get(self.token_name))
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "plattform": self.plattform,
                "verbunden": self.verbunden(), "posten_scharf": False,
                "token_name": self.token_name, "api_doc": self.API_DOC,
                "hinweis": "OSS-Selfhost (Postiz). Eigene Instanz + API-Key im Tresor "
                           "⇒ 0-€-Unified-Posten/Scheduling; Betrieb in eigener Hand."}

    def publish(self, post: OutboundPost) -> dict[str, Any]:
        if not self.verbunden():
            raise KanalNichtVerbunden(
                f"{self.name} nicht verbunden — API-Key/Instanz fehlt im Tresor "
                f"(erwarteter Name: {self.token_name!r}).")
        raise KanalNichtVerbunden(
            "Postiz-Live-Posten ist v1 noch nicht freigeschaltet (Instanz + Aktivierung).")


# ── Factory + Registry ────────────────────────────────────────────────────────
_DIREKT: dict[str, type[OAuthChannelSource]] = {
    "instagram": InstagramSource, "threads": ThreadsSource, "tiktok": TikTokSource,
    "x": XSource, "linkedin": LinkedInSource, "youtube": YouTubeSource,
    "bluesky": BlueskySource, "mastodon": MastodonSource,
}


def adapter_fuer(plattform: str,
                 vault_get: Callable[[str], str | None] | None = None
                 ) -> ChannelSource | None:
    """Liefert den Adapter zu einer Plattform (direkt) bzw. den Unified-Pfad
    (``ayrshare``/``unified`` → Ayrshare, ``postiz`` → Selfhost). Unbekannt ⇒ None.
    Genau diese Funktion nutzt der Publish-Handler — KEIN if/else-Wildwuchs in der
    Domäne (docs/RECHERCHE §6)."""
    p = (plattform or "").strip().lower()
    if p in _DIREKT:
        return _DIREKT[p](vault_get=vault_get)
    if p in ("ayrshare", "unified"):
        return UnifiedProviderSource(vault_get=vault_get)
    if p == "postiz":
        return PostizSource(vault_get=vault_get)
    return None


def kanaele_status(vault_get: Callable[[str], str | None] | None = None
                   ) -> list[dict[str, Any]]:
    """Übersicht aller bekannten/vorbereiteten Kanal-Adapter + ihr Verbindungsstatus
    — für UI (Kanal-Panel) und MCP. Macht die vorbereiteten Anschlüsse SICHTBAR
    (Gesetz 5: Bewusstsein über ihr Vorhandensein), ohne sie scharf zu schalten."""
    quellen: list[ChannelSource] = [Klass(vault_get=vault_get)
                                    for Klass in _DIREKT.values()]
    quellen.append(UnifiedProviderSource(vault_get=vault_get))
    quellen.append(PostizSource(vault_get=vault_get))
    out = []
    for q in quellen:
        s = q.status()
        s.setdefault("name", q.name)
        out.append(s)
    return out
