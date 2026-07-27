# 04 · Meta-Konnektor (WhatsApp + Instagram) — App-Stand & Aktivierung

> **Gesetz 5:** gegen die **echte** Graph-API gebaut, aber **DORMANT** — bis ein
> Token im Tresor liegt, ist `verfuegbar()==False` und jeder Call fail-closed.
> Spec/Onboarding: [the world of dizzi/docs/38_META_KONNEKTOR.md]. Aufbau auf
> D1 (Unified-Inbox/Smart-Contacts/Unified-Reply) + W4 (`appkit/connectors.py`).

## 1 · Was gebaut ist (`kommapp/meta.py` + Wiring)
- **W4-Connectoren** (`ExternalConnector`): `WhatsAppConnector` (`whatsapp`) +
  `InstagramConnector` (`instagram`), gemeinsame Basis `MetaChannelConnector`.
  Sichtbar über `GET /api/konnektoren` und (D1-Kanal-Sicht) `GET /api/kanaele`.
- **Outbound (Graph-API, real):**
  - WhatsApp: `POST https://graph.facebook.com/<version>/<phone_number_id>/messages`
    — **Session-Text** (`type:text`) vs. **Template** (`type:template`, außerhalb des
    24-h-Fensters Pflicht). `whatsapp_body(...)`.
  - Instagram: `POST .../<ig_user_id>/messages` mit `{recipient:{id:<IGSID>}, message:{text}}`.
  - **Senden = K4-HITL** (`nachricht_senden`, `verifiziert`, fail-closed) — über die
    D1-Unified-Reply (`/api/smartkontakte/{id}/antwort`) oder die Test-Sende. Nie autonom.
- **Inbound (Webhook):** `GET/POST /api/kanaele/meta/webhook`.
  - GET = Verify-Challenge (`hub.verify_token` ↔ Tresor `meta_webhook_verify_token`).
  - POST = Events: **X-Hub-Signature-256** (HMAC-SHA256 mit `meta_app_secret`) →
    `meta.webhook_parse` → `_einsortieren` in die Unified-Inbox + **Smart-Contact-
    Unifikation** (Telefon/IGSID → kanonischer Kontakt, Herkunfts-Label).
  - ⚠️ **Eingang braucht eine öffentliche HTTPS-URL** (Tunnel cloudflared/ngrok oder
    Server). Outbound läuft auch rein lokal. (docs/38 §2 — Betriebs-Frage, kein Code-Blocker.)
- **Config-UI:** Einstellungsfenster › „Messenger-Kanäle (Meta)" — Status, Token/IDs
  eintragen (Verbinden/Trennen), Test-Sende (HITL).

## 2 · Secrets & Config — wo liegt was
| Wert | Ablage | Name |
|------|--------|------|
| WhatsApp Access-Token | **Tresor** | `meta_whatsapp_token` |
| Instagram Access-Token | **Tresor** | `meta_instagram_token` |
| App-Secret (Webhook-Signatur) | **Tresor** | `meta_app_secret` |
| Webhook-Verify-Token | **Tresor** | `meta_webhook_verify_token` |
| WhatsApp `phone_number_id` | Setting (kein Secret) | `whatsapp_phone_number_id` |
| Instagram `ig_user_id` | Setting | `instagram_user_id` |
| Graph-Version | Setting | `graph_version` (Default `v23.0`) |
| WhatsApp Template-Sprache | Setting | `whatsapp_template_sprache` |

Tokens **nie** in DB/Settings/Repo. Das Audit hält nur, WELCHE Felder gesetzt wurden — nie die Werte.

## 3 · Permissions / API-Version (gegen Live-Doku gegenchecken!)
Graph-Versionen + Permission-Namen ändern sich — `graph_version` ist darum eine Einstellung.
Stand 21.06.2026 (Default v23.0):
- **WhatsApp:** `whatsapp_business_messaging` (+ `whatsapp_business_management`).
- **Instagram:** `instagram_basic` + `instagram_manage_messages` (+ Seiten-Rechte).
Quellen: developers.facebook.com/docs/whatsapp/cloud-api · .../instagram-platform.

## 4 · Aktivierung (wenn die Meta-Freigaben da sind, docs/38 §1)
Der **Engpass ist Metas Business-Onboarding** (Business-Verifizierung + WABA/IG + App-
Review — Wochen), NICHT der Code. Ist das durch:
1. **Token in den Tresor** (Config-UI „Verbinden") + `phone_number_id`/`ig_user_id` als
   Setting ⇒ `verfuegbar()` wird True ⇒ **Outbound live** (HITL-Freigabe sendet real).
2. **Inbound:** Verify-Token + App-Secret hinterlegen, Webhook in der Meta-App auf die
   **öffentliche** URL (Tunnel/Server) `…/api/kanaele/meta/webhook` zeigen, Felder
   `messages` (WA) bzw. Messaging (IG) abonnieren ⇒ eingehende Nachrichten landen in der
   Unified-Inbox.
3. **24-h-Regel** beachten: außerhalb des Fensters nur genehmigte Templates (WA).

## 5 · Schneller End-to-End-Beweis (optional, docs/38 §4)
**Telegram** (nur Bot-Token, kein Review, Webhook ODER Long-Polling ⇒ rein lokal) wäre der
schnellste echte Beweis ohne Wochen-Wartezeit — als Pilot denkbar (heute Slot/dormant).
