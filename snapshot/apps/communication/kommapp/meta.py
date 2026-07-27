"""Meta-Konnektor (WhatsApp Business Cloud API + Instagram-DMs) — DORMANT gegen die
echte Graph-API (docs/38, Paket Meta-Konnektor).

═══════════════════════════════════════════════════════════════════════════════
GESETZ 5 — VORBEREITUNG, gegen die ECHTE API gebaut, aber bis zu den Meta-Tokens
**dormant**: ``verfuegbar()`` ist False, solange kein Token im Tresor liegt; jeder
echte Graph-Call passiert erst mit Token. Aufbauend auf dem W4-Connector-Gerüst
(``appkit/connectors.py`` :: ``ExternalConnector``) + D1 (Unified-Inbox/Smart-
Contacts/Unified-Reply). Sicherheit (sensitivity hoechst): Inhalte lokal, **Senden
= K4-HITL ``verifiziert``, fail-closed** (nie autonom). Tokens/App-Secret/Verify-
Token im **Tresor** (OS-Secret-Store), NIE in DB/Settings.
═══════════════════════════════════════════════════════════════════════════════

API-Grundlagen (gegen Metas Live-Doku gegengecheckt 21.06.2026 — Versionen/
Permissions ändern sich, ``graph_version`` ist darum eine Einstellung):

- **WhatsApp Cloud API** — Versand: ``POST https://graph.facebook.com/<version>/
  <PHONE_NUMBER_ID>/messages`` mit ``Authorization: Bearer <token>``. Body:
  ``{messaging_product:"whatsapp", recipient_type:"individual", to:<wa_id>,
  type:"text"|"template", text:{body}|template:{name,language:{code}}}``.
  **24-h-Regel:** freie (Session-)Textnachrichten nur ≤24 h nach der letzten
  Nutzer-Nachricht; außerhalb nur vorab genehmigte **Templates**.
  Permissions: ``whatsapp_business_messaging`` (+ ``_management``).
- **Instagram-DMs** — Versand: ``POST .../<IG_ID>/messages`` mit
  ``{recipient:{id:<IGSID>}, message:{text:<text>}}`` (24-h-Fenster analog).
  Permissions: ``instagram_basic`` + ``instagram_manage_messages`` (+ Seiten-Rechte).
- **Inbound** läuft bei Meta NUR über **Webhooks** (Meta pusht an eine öffentliche
  HTTPS-URL) ⇒ lokal braucht es einen Tunnel/Server (docs/38 §2). Der Empfänger ist
  hier gebaut; das tatsächliche Empfangen hängt am Tunnel (dokumentierter Slot).
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Callable

from appkit.connectors import (ExternalConnector, KonnektorNichtVerbunden)

# Default-Graph-Version (Einstellung ``graph_version`` überschreibt sie — Meta
# rollt regelmäßig neue Versionen; v23.0 ist der aktuelle stabile Stand 06/2026).
GRAPH_VERSION = "v23.0"
GRAPH_BASE = "https://graph.facebook.com"

# Mit diesen kanal_typ-Schlüsseln dockt der Meta-Konnektor an D1 (channels.py) an.
META_KANAELE = ("whatsapp", "instagram")

# http_post-Konvention (JSON, injizierbar ⇒ netzfrei testbar). Default = httpx.
HttpPost = Callable[..., Any]


class MetaApiFehler(RuntimeError):
    """Die Graph-API hat einen Fehler gemeldet (mit Roh-Payload für die Diagnose)."""

    def __init__(self, nachricht: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(nachricht)
        self.payload = payload or {}


def _default_post(url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
    import httpx
    return httpx.post(url, json=json, headers=headers, timeout=20.0)


def graph_send(url: str, token: str, body: dict[str, Any],
               http_post: HttpPost | None = None) -> dict[str, Any]:
    """Ein Graph-API-POST (Bearer-Token, JSON). Hebt bei HTTP≥400 ``MetaApiFehler``
    mit der Graph-Fehlermeldung. ``http_post`` injizierbar (Tests = Fake)."""
    poster = http_post or _default_post
    r = poster(url, json=body, headers={"Authorization": f"Bearer {token}",
                                        "Content-Type": "application/json"})
    try:
        data = r.json()
    except Exception:
        data = {}
    code = int(getattr(r, "status_code", 200) or 200)
    if code >= 400:
        msg = (data.get("error", {}) or {}).get("message") or f"HTTP {code}"
        raise MetaApiFehler(msg, data)
    return data


# ── Outbound-Body-Builder (rein, ohne Netz) ───────────────────────────────────
def whatsapp_body(an: str, text: str | None = None, template: str | None = None,
                  sprache: str = "de") -> dict[str, Any]:
    """WhatsApp-Send-Body. ``template`` gesetzt ⇒ Template-Nachricht (außerhalb des
    24-h-Fensters Pflicht); sonst freie Session-Textnachricht."""
    body: dict[str, Any] = {"messaging_product": "whatsapp",
                            "recipient_type": "individual", "to": str(an)}
    if template:
        body["type"] = "template"
        body["template"] = {"name": template, "language": {"code": sprache}}
    else:
        body["type"] = "text"
        body["text"] = {"body": text or ""}
    return body


def instagram_body(igsid: str, text: str) -> dict[str, Any]:
    """Instagram-DM-Send-Body (Text). ``igsid`` = Instagram-scoped ID des Empfängers."""
    return {"recipient": {"id": str(igsid)}, "message": {"text": text or ""}}


# ── Inbound-Webhook (Verify + Signatur + Normierung) ──────────────────────────
def webhook_verify(mode: str | None, token: str | None, challenge: str | None,
                   erwartet: str | None) -> str | None:
    """Verify-Handshake (GET): Meta schickt ``hub.mode=subscribe`` + ``hub.verify_token``
    + ``hub.challenge``. Stimmt das Token mit dem hinterlegten überein ⇒ ``challenge``
    zurück (Meta erwartet genau diesen String), sonst None ⇒ 403."""
    if mode == "subscribe" and token and erwartet and hmac.compare_digest(token, erwartet):
        return challenge or ""
    return None


def pruefe_signatur(raw: bytes, header: str | None, app_secret: str | None) -> bool:
    """X-Hub-Signature-256 prüfen (HMAC-SHA256 des ROH-Bodys mit dem App-Secret).
    **Fail-closed:** eine Signaturprüfung, die mangels App-Secret nicht verifizieren
    kann, darf NICHT durchwinken ⇒ ohne App-Secret (oder ohne gültigen Header) ``False``.
    (Die Außen-Aktivierung setzt das App-Secret in der Config-UI; der Endpunkt weist
    Inbound ohne Secret zusätzlich explizit ab — defense-in-depth.)"""
    if not app_secret:
        return False
    if not header or not header.startswith("sha256="):
        return False
    erwartet = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(erwartet, header.split("=", 1)[1])


def _iso(ts: Any) -> str:
    """Meta-Timestamp (Unix-Sekunden, str/int) → ISO-8601 (UTC); leer ⇒ jetzt."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(tz=timezone.utc).isoformat()


def _norm(kanal: str, frm: str, text: str, extern_id: Any, ts: Any) -> dict[str, Any] | None:
    """Eine eingehende Nachricht auf das kanal-agnostische Schema normieren
    (passt 1:1 in ``_einsortieren``). ``von_adresse`` = der reine Handle/die
    Telefon-/IGSID ⇒ die Smart-Contact-Unifikation matcht den Alias sauber."""
    frm = str(frm or "").strip()
    if not frm:
        return None
    return {"kanal_typ": kanal, "extern_id": str(extern_id or f"{kanal}:{frm}:{ts}"),
            "von_adresse": frm, "an_adressen": "ich", "betreff": "",
            "text": text or "", "gesendet_at": _iso(ts),
            "thread_schluessel": f"{kanal}:{frm.lower()}"}


def _wa_text(m: dict[str, Any]) -> str:
    if m.get("type") == "text":
        return (m.get("text", {}) or {}).get("body", "")
    return f"[{m.get('type', 'nachricht')}]"          # Bild/Audio/… als Platzhalter


def webhook_parse(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Webhook-Event-Payload (WhatsApp ODER Instagram) → Liste normierter
    eingehender Nachrichten. Robust gegen fehlende Felder (nie Crash)."""
    out: list[dict[str, Any]] = []
    for entry in (payload.get("entry") or []):
        # WhatsApp: entry.changes[].value.messages[]
        for ch in (entry.get("changes") or []):
            val = ch.get("value", {}) or {}
            if not (val.get("messaging_product") == "whatsapp"
                    or ch.get("field") == "messages"):
                continue
            for m in (val.get("messages") or []):
                n = _norm("whatsapp", m.get("from", ""), _wa_text(m),
                          m.get("id"), m.get("timestamp"))
                if n:
                    out.append(n)
        # Instagram: entry.messaging[].message
        for ms in (entry.get("messaging") or []):
            msg = ms.get("message", {}) or {}
            if msg.get("is_echo"):                    # eigene gesendete nicht zurückspielen
                continue
            n = _norm("instagram", (ms.get("sender", {}) or {}).get("id", ""),
                      msg.get("text", ""), msg.get("mid"), ms.get("timestamp"))
            if n:
                out.append(n)
    return out


# ── W4-Connectoren (ExternalConnector) — dormant bis Token im Tresor ──────────
class MetaChannelConnector(ExternalConnector):
    """Gemeinsame Basis der Meta-Kanäle über das W4-Gerüst. ``verfuegbar()`` ist
    True, sobald der Access-Token im Tresor liegt; ``senden`` ist die Außen-Kante
    (läuft in der App nur hinter K4-HITL). ``vault_get``/``config_get``/``http_post``
    werden injiziert (Standalone-testbar)."""

    kind = "messenger"
    richtung = "beides"
    sensitivity = "hoechst"
    token_name = ""
    permissions: tuple[str, ...] = ()
    API_DOC = ""
    kanal_typ = ""

    def __init__(self, vault_get: Callable[[str], str | None] | None = None,
                 config_get: Callable[..., Any] | None = None,
                 http_post: HttpPost | None = None) -> None:
        self._vault_get = vault_get or (lambda _n: None)
        self._config_get = config_get or (lambda _k, d=None: d)
        self._http_post = http_post

    def _token(self) -> str | None:
        try:
            return self._vault_get(self.token_name)
        except Exception:
            return None

    def verfuegbar(self) -> bool:
        return bool(self._token())

    def senden(self, an: str, text: str | None = None,
               template: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def info(self):
        i = super().info()
        i.extra = {"version": self._config_get("graph_version", GRAPH_VERSION),
                   "permissions": list(self.permissions),
                   "token_name": self.token_name, "api_doc": self.API_DOC,
                   "kanal_typ": self.kanal_typ}
        return i


class WhatsAppConnector(MetaChannelConnector):
    """WhatsApp Business Cloud API. Versand über ``/<phone_number_id>/messages``;
    Session-Text vs. Template (24-h-Regel)."""

    id = "whatsapp"
    kanal_typ = "whatsapp"
    label = "WhatsApp Business (Cloud API)"
    token_name = "meta_whatsapp_token"
    permissions = ("whatsapp_business_messaging", "whatsapp_business_management")
    API_DOC = "https://developers.facebook.com/docs/whatsapp/cloud-api"
    aktivierung = ("WABA + Telefonnummer + dauerhafter System-User-Token (Tresor "
                   "'meta_whatsapp_token') + phone_number_id (Einstellung); App-Review "
                   "für whatsapp_business_messaging. Außerhalb 24 h nur Templates.")

    def senden(self, an: str, text: str | None = None,
               template: str | None = None) -> dict[str, Any]:
        token = self._token()
        if not token:
            raise KonnektorNichtVerbunden(
                "WhatsApp nicht verbunden — Token fehlt im Tresor (meta_whatsapp_token).")
        pnid = self._config_get("whatsapp_phone_number_id", "")
        if not pnid:
            raise KonnektorNichtVerbunden(
                "WhatsApp: phone_number_id fehlt (Einstellung whatsapp_phone_number_id).")
        version = self._config_get("graph_version", GRAPH_VERSION)
        url = f"{GRAPH_BASE}/{version}/{pnid}/messages"
        body = whatsapp_body(an, text=text, template=template,
                             sprache=self._config_get("whatsapp_template_sprache", "de"))
        return graph_send(url, token, body, http_post=self._http_post)


class InstagramConnector(MetaChannelConnector):
    """Instagram-DMs (über die verknüpfte Seite / IG-User). Versand über
    ``/<ig_user_id>/messages`` mit ``recipient:{id:<IGSID>}``."""

    id = "instagram"
    kanal_typ = "instagram"
    label = "Instagram-DMs"
    token_name = "meta_instagram_token"
    permissions = ("instagram_basic", "instagram_manage_messages", "pages_messaging")
    API_DOC = ("https://developers.facebook.com/docs/instagram-platform/"
               "instagram-api-with-instagram-login/messaging-api")
    aktivierung = ("IG-Profikonto (Business/Creator) + verknüpfte Seite + Token (Tresor "
                   "'meta_instagram_token') + ig_user_id (Einstellung); App-Review für "
                   "instagram_manage_messages. 24-h-Antwortfenster.")

    def senden(self, an: str, text: str | None = None,
               template: str | None = None) -> dict[str, Any]:
        token = self._token()
        if not token:
            raise KonnektorNichtVerbunden(
                "Instagram nicht verbunden — Token fehlt im Tresor (meta_instagram_token).")
        igid = self._config_get("instagram_user_id", "")
        if not igid:
            raise KonnektorNichtVerbunden(
                "Instagram: ig_user_id fehlt (Einstellung instagram_user_id).")
        version = self._config_get("graph_version", GRAPH_VERSION)
        url = f"{GRAPH_BASE}/{version}/{igid}/messages"
        return graph_send(url, token, instagram_body(an, text or ""),
                          http_post=self._http_post)


def baue_connectoren(vault_get: Callable[[str], str | None] | None = None,
                     config_get: Callable[..., Any] | None = None,
                     http_post: HttpPost | None = None
                     ) -> dict[str, MetaChannelConnector]:
    """Die Meta-Connectoren als ``kanal_typ → MetaChannelConnector`` — verdrahtet mit
    Tresor/Einstellungen/HTTP. Genau dieses Dict reicht die App an D1 (channels.py)
    UND an die W4-Registry (/api/konnektoren)."""
    return {
        "whatsapp": WhatsAppConnector(vault_get, config_get, http_post),
        "instagram": InstagramConnector(vault_get, config_get, http_post),
    }
