# 03 · Kanal-Vorbereitung — der Multi-Kanal-Stecker (Gesetz 5)

> **Gesetz 5 (Vorbereitungsmaßnahmen dokumentieren):** Dieses Dokument macht die
> vorbereiteten, noch funktionslosen Kanal-Anschlüsse **bewusst** — sie stehen im
> Code (`kommapp/channels.py`) UND hier. Status heute: **VORBEREITUNG**, nicht
> Vollbetrieb. Echte Plattform-APIs (Telegram/WhatsApp/…) sind heavy + Architektur-KI-Park
> (docs/35 §6) und bewusst NICHT umgesetzt.

Umsetzung von Paket **D1** (docs/_archiv/36) — dem „Vernetzungs-Flaggschiff" (docs/35 §2):
**ein Kontakt über alle Kanäle, ein Thread, Antwort über gewählten/letzten Kanal.**

## 1 · Die ChannelConnector-Schicht (`kommapp/channels.py`)
EIN Interface `ChannelConnector`, viele Stecker — analog zu `health/sources.py`
(Wearable-Prep) und `management` `ChannelSource`. Vertrag:
- `verbunden() -> bool` — ehrlich: kann über den Kanal **real** gesendet werden?
- `senden(AusgehendeNachricht) -> dict` — die EINZIGE Außen-Kante; dormant ⇒
  `KanalNichtVerbunden` (fail-closed).
- `status() -> dict` — für `/api/kanaele` + Bewusstsein über den Slot.

| Kanal | Status | Stecker | Live-Pfad später (`weg`) | Mode-Schalter |
|-------|--------|---------|--------------------------|---------------|
| **E-Mail** | **AKTIV** | `EmailConnector` | IMAP/SMTP + XOAUTH2 (`mail.py`) | — (real) |
| Telegram | **echter Adapter, dormant bis Token** | `TelegramConnector` → `telegram.TelegramBotConnector` | **Telegram Bot-API** — Token im Tresor (`telegram_bot_token`), **lokal via Long-Polling** (kein Webhook/Review) | `bridge_telegram_vorbereitet` |
| WhatsApp | **echter Adapter, dormant bis Token** | `WhatsAppConnector` → `meta.WhatsAppConnector` | **WhatsApp Business Cloud API** (Graph) — Token im Tresor + `phone_number_id` (→ [docs/04](04_META_KONNEKTOR.md)) | `bridge_whatsapp_vorbereitet` |
| Instagram | **echter Adapter, dormant bis Token** | `InstagramConnector` → `meta.InstagramConnector` | **Instagram-Messaging-API** (Graph) — Token im Tresor + `ig_user_id` (→ [docs/04](04_META_KONNEKTOR.md)) | `kanal_instagram_vorbereitet` |
| Snapchat | dormant (Slot) | `SnapchatConnector` | Webview (A) — keine offene Messaging-API | `kanal_snapchat_vorbereitet` |

**WhatsApp/Instagram = Meta-Konnektor (docs/04, Paket „Meta-Konnektor"):** echte Graph-
API-Connectoren über das W4-Gerüst, dormant bis Token im Tresor; Inbound über Webhook
(`/api/kanaele/meta/webhook`, braucht öffentliche URL). **Telegram = Bot-API-Konnektor
(`telegram.py`):** ebenfalls echter Adapter über das W4-Gerüst, dormant bis Bot-Token —
aber **rein lokal** (Inbound via Long-Polling `getUpdates`, KEIN Webhook/Tunnel/App-Review;
`/api/kanaele/telegram/sync`, Offset in Setting `telegram_offset`). `aktiv=True` (Adapter
da), `verbunden` = Token vorhanden. Snapchat bleibt reiner Gesetz-5-Slot.

`/api/kanaele` zeigt alle Kanäle samt Status, Mode-Schalter-Wert und Aktivitäts-
Zählern (Nachrichten/Kontakte je Kanal) — die Slots sind sichtbar, ohne scharf zu sein.

## 2 · INTEGRATIONS-PUNKT: appkit-Connector-Gerüst (docs/_archiv/36 W4)
Der World-Chat baut ein **universelles** `appkit/connectors.py`
(`ExternalConnector`-Interface, das JEDE App erbt). Die App-seitige Schicht hier
ist bewusst so geschnitten, dass sie **später darauf aufsetzt**: `status()` trägt
schon das Vokabular (verbunden/aktiv/weg/modus_setting), `senden` ist die einzige
Außen-Kante (hinter K4-HITL). Sobald appkit das Gerüst stellt, werden diese
Klassen davon abgeleitet — **kein Domänen-Umbau**. Bis dahin lebt die Schicht hier
(Standalone-Konnektivität, docs/35 §1). `status()["integration_punkt"]` weist
explizit auf `appkit/connectors.py (docs/_archiv/36 W4)`.

## 3 · Smart Contacts (Kontakt-Unifikation, `kommapp/kontakte.py`)
Ein kanonischer Kontakt (`kontakte`) bündelt mehrere Kanal-Identitäten
(`kontakt_adressen`: `kanal_typ` × `adresse`). Reine, deterministische Matching-
Logik (kein LLM, hoechst-App ⇒ lokal) liefert **Merge-VORSCHLÄGE** (gleiche Namen /
gleiche Identitäts-Stämme über Kanäle); **Merge/Split sind Nutzer-Aktionen**
(`/api/smartkontakte/{id}/zusammenfuehren|trennen`). Nachrichten werden den
**aktuellen** Aliassen zugeordnet ⇒ Merge/Split verschieben nur Aliasse, der
Verlauf folgt automatisch (keine Re-Markierung). Laut docs/35 §5.3 ist dies ein
eigener Baustein + **Kit-Kandidat** — darum modular in `kontakte.py`.

## 4 · Unified Inbox & Reply
- **Inbox:** `/api/smartkontakte/{id}/verlauf` führt die Nachrichten ALLER Kanäle
  eines Kontakts chronologisch zusammen, jede mit `kanal_typ` = **Herkunfts-Label**.
- **Reply:** `/api/smartkontakte/{id}/antwort` — Kanal **explizit** ODER automatisch
  **„letzter eingegangener"** (`letzter_kanal`); Empfänger aus den Aliassen
  abgeleitet. Senden ist IMMER **HITL** (`nachricht_senden`, Stufe `verifiziert`):
  es entsteht ein PENDING-Vorschlag, nie ein autonomer Versand.

## 5 · Simulation (Demo, docs/35 §6: „andere Kanäle simuliert")
`POST /api/kanaele/{kanal}/simulieren` täuscht eine **eingehende** Messenger-
Nachricht vor (über ein simuliertes Kanal-„Konto", `art ≠ imap/gmail/jmap` ⇒ kein
IMAP-Abruf), damit „ein Kontakt über alle Kanäle" **real demonstrierbar** ist.
**KEINE** Plattform-Anbindung — rein lokale Daten. E-Mail kommt über den echten Sync.

## 6 · Sicherheit (sensitivity `hoechst`)
- Inhalte bleiben **lokal** (`ki_routing lokal_only`); MCP sieht nie Volltexte.
- **Senden = HITL** (`verifiziert`, fail-closed). Dormante Kanäle: der HITL-Vorschlag
  wird vorbereitet/angezeigt, aber `gesperrt` markiert; eine Freigabe scheitert
  fail-closed (`KanalNichtVerbunden`) — **selbst nach Approval** (Gesetz 5).
- Geheimnisse (später: Bridge-/Plattform-Tokens) NUR im K2-Tresor.

## 7 · Aktivierung (wenn „es nötig wird", docs/35 §6)
Pro Kanal genügt ein neuer/erweiterter Adapter auf demselben Interface:
1. Live-Pfad wählen (Schiene A Webview / Schiene B Matrix-Bridge / native API).
2. Tokens/Bridge-Zugang in den Tresor; `verbunden()` auf die echte Prüfung umstellen.
3. Empfang an den Ingest-/Bridge-Pfad hängen (das Schema `konto→konversation→
   nachricht` trägt beliebige `kanal_typ` bereits), `senden` auf den echten
   Versand. Schema- und UI-Umbau entfällt — es ist ein **Stecker**.
