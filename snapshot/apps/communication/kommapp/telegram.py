"""Telegram-Konnektor (Bot-API) — DORMANT gegen die echte API, scharf ab Bot-Token.

═══════════════════════════════════════════════════════════════════════════════
GESETZ 5 — VORBEREITUNG, gegen die ECHTE Telegram-Bot-API gebaut, aber bis zum
Bot-Token im Tresor **dormant**: ``verfuegbar()`` ist False, solange kein Token
liegt; jeder echte API-Call passiert erst mit Token. Aufbauend auf dem W4-Gerüst
(``appkit/connectors.py`` :: ``ExternalConnector``) + D1 (Unified-Inbox/Smart-
Contacts/Unified-Reply, ``channels.py``). Sicherheit (sensitivity hoechst):
Inhalte lokal, **Senden = K4-HITL ``verifiziert``, fail-closed** (nie autonom).
Bot-Token im **Tresor** (OS-Secret-Store), NIE in DB/Settings.
═══════════════════════════════════════════════════════════════════════════════

Warum Telegram der „einfache" Konnektor ist (vs. Meta):
- **Kein App-Review, kein Tunnel.** Bot via @BotFather anlegen → Token. Empfang
  läuft lokal über **Long-Polling** (``getUpdates``) statt über einen Webhook mit
  öffentlicher HTTPS-URL ⇒ rein lokal lauffähig (anders als Meta, docs/38 §2).
- **Outbound:** ``POST https://api.telegram.org/bot<token>/sendMessage`` mit
  ``{chat_id, text}``. Es gibt KEINE Templates/24-h-Regel (der ``template``-
  Parameter aus der Connector-Schicht wird ignoriert). Telegram-Eigenheit: ein
  Bot kann nur Chats anschreiben, die ihn ZUERST kontaktiert haben (``chat_id``
  entsteht erst durch eine eingehende Nachricht).
- **Inbound:** ``getUpdates`` liefert seit dem letzten ``offset`` neue Updates;
  ``offset = letzte update_id + 1`` quittiert sie (server-seitiges Abräumen). Der
  Offset wird von der App persistiert (Einstellung ``telegram_offset``).

API gegen die Live-Doku gegengecheckt (24.06.2026): https://core.telegram.org/bots/api
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from appkit.connectors import ExternalConnector, KonnektorNichtVerbunden

TELEGRAM_API = "https://api.telegram.org"

# Mit diesem kanal_typ dockt der Telegram-Konnektor an D1 (channels.py) an.
TELEGRAM_KANAL = "telegram"

# http_post-Konvention (JSON, injizierbar ⇒ netzfrei testbar). Default = httpx.
HttpPost = Callable[..., Any]


class TelegramApiFehler(RuntimeError):
    """Die Bot-API hat einen Fehler gemeldet (``ok:false`` oder HTTP≥400) — mit
    Roh-Payload für die Diagnose."""

    def __init__(self, nachricht: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(nachricht)
        self.payload = payload or {}


def _default_post(url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
    import httpx
    return httpx.post(url, json=json, headers=headers, timeout=20.0)


def telegram_call(token: str, method: str, body: dict[str, Any],
                  http_post: HttpPost | None = None) -> Any:
    """Ein Bot-API-Call (``/bot<token>/<method>``, JSON). Hebt bei ``ok:false`` oder
    HTTP≥400 ``TelegramApiFehler`` mit Telegrams ``description``. Gibt sonst das
    ``result`` zurück. ``http_post`` injizierbar (Tests = Fake)."""
    poster = http_post or _default_post
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    r = poster(url, json=body, headers={"Content-Type": "application/json"})
    try:
        data = r.json()
    except Exception:
        data = {}
    code = int(getattr(r, "status_code", 200) or 200)
    if code >= 400 or not data.get("ok", False):
        msg = data.get("description") or f"HTTP {code}"
        raise TelegramApiFehler(msg, data)
    return data.get("result")


# ── Outbound-Body-Builder (rein, ohne Netz) ───────────────────────────────────
def telegram_body(chat_id: str | int, text: str) -> dict[str, Any]:
    """sendMessage-Body. ``chat_id`` = numerische Chat-ID des Empfängers (Telegram
    kennt keine freie Handle-Adressierung für Bots)."""
    return {"chat_id": str(chat_id), "text": text or ""}


# ── Inbound (getUpdates → kanal-agnostisches Schema) ──────────────────────────
def _iso(ts: Any) -> str:
    """Telegram-Timestamp (Unix-Sekunden) → ISO-8601 (UTC); leer/ungültig ⇒ jetzt."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(tz=timezone.utc).isoformat()


def _absender_label(frm: dict[str, Any]) -> str:
    """Menschen-lesbarer Absender (für die Inbox-Liste): @username bzw. Vorname."""
    user = (frm.get("username") or "").strip()
    if user:
        return f"@{user}"
    vor = (frm.get("first_name") or "").strip()
    nach = (frm.get("last_name") or "").strip()
    return (vor + (" " + nach if nach else "")).strip()


def _msg_text(m: dict[str, Any]) -> str:
    """Text einer Nachricht; nicht-Text (Foto/Sticker/…) als ehrlicher Platzhalter."""
    if m.get("text"):
        return m["text"]
    for art in ("photo", "video", "audio", "voice", "document", "sticker", "location"):
        if m.get(art):
            return f"[{art}]"
    return "[nachricht]"


def _norm(m: dict[str, Any]) -> dict[str, Any] | None:
    """Eine eingehende Telegram-Nachricht auf das kanal-agnostische Schema normieren
    (passt 1:1 in ``_einsortieren``). ``von_adresse`` = die numerische ``chat_id``
    (= das Antwortziel für sendMessage); der Klartext-Name liegt im ``betreff``
    (Inbox-Label). Robust gegen fehlende Felder (nie Crash)."""
    chat = m.get("chat", {}) or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    frm = m.get("from", {}) or {}
    return {"kanal_typ": TELEGRAM_KANAL,
            "extern_id": f"telegram:{chat_id}:{m.get('message_id', '')}",
            "von_adresse": str(chat_id), "an_adressen": "ich",
            "betreff": _absender_label(frm), "text": _msg_text(m),
            "gesendet_at": _iso(m.get("date")),
            "thread_schluessel": f"telegram:{chat_id}"}


def updates_parse(updates: list[dict[str, Any]] | None
                  ) -> tuple[list[dict[str, Any]], int | None]:
    """``getUpdates``-Result (Liste von Update-Objekten) → ``(normierte Nachrichten,
    next_offset)``. ``next_offset`` = höchste ``update_id`` + 1 (None, wenn keine
    Updates). Verarbeitet ``message`` + ``channel_post`` (eigene Echos/Edits werden
    übersprungen). Robust gegen fehlende Felder."""
    out: list[dict[str, Any]] = []
    max_uid: int | None = None
    for up in (updates or []):
        uid = up.get("update_id")
        if isinstance(uid, int):
            max_uid = uid if max_uid is None else max(max_uid, uid)
        m = up.get("message") or up.get("channel_post")
        if not m:
            continue                       # edited_message/callback_query/… ignorieren
        n = _norm(m)
        if n:
            out.append(n)
    return out, (max_uid + 1 if max_uid is not None else None)


# ── W4-Connector (ExternalConnector) — dormant bis Token im Tresor ────────────
class TelegramBotConnector(ExternalConnector):
    """Telegram über die **Bot-API**, dormant bis Bot-Token im Tresor. ``verfuegbar()``
    ist True, sobald der Token liegt; ``senden`` ist die Außen-Kante (läuft in der App
    nur hinter K4-HITL); ``abrufen`` zieht per Long-Polling (``getUpdates``). Die
    Injektionen ``vault_get``/``config_get``/``http_post`` machen den Connector
    standalone-testbar (netzfrei)."""

    id = "telegram"
    label = "Telegram (Bot-API)"
    kind = "messenger"
    richtung = "beides"
    sensitivity = "hoechst"
    kanal_typ = "telegram"
    token_name = "telegram_bot_token"
    API_DOC = "https://core.telegram.org/bots/api"
    aktivierung = ("Bot via @BotFather anlegen → Token (Tresor 'telegram_bot_token'). "
                   "Lokal über Long-Polling (getUpdates) — KEIN Webhook/öffentliche URL, "
                   "KEIN App-Review. Empfänger = numerische chat_id (der Bot kann nur "
                   "Chats anschreiben, die ihn zuerst kontaktiert haben).")

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
        """Eine Nachricht senden (``sendMessage``). ``template`` existiert bei Telegram
        nicht und wird ignoriert (Signatur-Parität mit der Connector-Schicht)."""
        token = self._token()
        if not token:
            raise KonnektorNichtVerbunden(
                "Telegram nicht verbunden — Bot-Token fehlt im Tresor (telegram_bot_token).")
        an = str(an or "").strip()
        if not an:
            raise KonnektorNichtVerbunden("Telegram: Empfänger (chat_id) fehlt.")
        res = telegram_call(token, "sendMessage", telegram_body(an, text or ""),
                            http_post=self._http_post)
        return {"gesendet": True, "an": an,
                "message_id": (res or {}).get("message_id")}

    def abrufen(self, offset: int = 0) -> tuple[list[dict[str, Any]], int | None]:
        """Inbound per Long-Polling (``getUpdates``, ``timeout=0`` ⇒ sofort die
        ausstehenden Updates, kein Hängen). Liefert ``(normierte Nachrichten,
        next_offset)``. Ohne Token ⇒ ``([], offset)`` (best-effort, kein Crash)."""
        token = self._token()
        if not token:
            return [], offset
        res = telegram_call(token, "getUpdates",
                            {"offset": int(offset or 0), "timeout": 0},
                            http_post=self._http_post)
        nachrichten, next_off = updates_parse(res if isinstance(res, list) else [])
        return nachrichten, (next_off if next_off is not None else offset)

    def bot_info(self) -> dict[str, Any]:
        """``getMe`` — für die Config-UI (Bot-Username/Name). Best-effort: ohne Token
        bzw. bei Fehler ⇒ ``{}`` (nie Crash)."""
        token = self._token()
        if not token:
            return {}
        try:
            return telegram_call(token, "getMe", {}, http_post=self._http_post) or {}
        except Exception:
            return {}

    def info(self):
        i = super().info()
        i.extra = {"token_name": self.token_name, "api_doc": self.API_DOC,
                   "kanal_typ": self.kanal_typ, "transport": "long-polling (getUpdates)"}
        return i


def baue_connector(vault_get: Callable[[str], str | None] | None = None,
                   config_get: Callable[..., Any] | None = None,
                   http_post: HttpPost | None = None) -> TelegramBotConnector:
    """Den Telegram-Connector verdrahtet mit Tresor/Einstellungen/HTTP. Reicht die App
    an D1 (channels.py, als ``adapter``) UND an die W4-Registry (/api/konnektoren)."""
    return TelegramBotConnector(vault_get, config_get, http_post)
