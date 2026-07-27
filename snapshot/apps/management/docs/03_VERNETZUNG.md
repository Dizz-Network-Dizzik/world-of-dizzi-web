# Vernetzungs-Manifest — Dizz Management [MG]

> Pflichtteil des App-Vertrags (docs/01 §7): **was** die App mit dem Verbund teilt und
> **wovon** sie abhängt. Stand 15.06.2026 (v1-Kern gebaut). Maschinell unter
> `GET /api/manifest` (Felder `shares`, `depends`, `mcp`).

## Identität
- **id** `management` · **brand** „Dizz Management" · **name** „KI-Agenten" (★ Umdeklaration 03.07.,
  D13: KI-Agenten-Verwaltung; Social Media = erste Domäne) · **Port** `8213`
  (localhost-gebunden) · **icon** `broadcast`.
- **sensitivity** `hoch` — SENSIBEL. Steuert das KI-Routing auf `lokal_only` (lokal-first,
  nie Boost/Cloud) und stellt sensible Routen hinter verifizierte Verbindung. Begründung:
  die App verwaltet **OAuth-Tokens fremder Plattformen** und steuert **Außenwirkung** (Posten).

## Was Dizz Management TEILT (shares)
- **Stats-Kachel** (`/api/summary`, read-only): Kanäle, aktive Social-Bots, Entwürfe,
  geplante Posts, nächster Zeitplan-Slot. Display-fertige KPIs.
- **MCP-Server** (stdio, read-only, Namensraum `management_*`, `managementapp/mcp_server.py`):
  | Tool | Quelle | Inhalt |
  |---|---|---|
  | `management_kachel_stats` | `/api/stats` | Kennzahlen-Block |
  | `management_redaktionsplan` | `/api/zeitplan` | geplante Posts (zeitlich) + offene Entwürfe |
  | `management_kanal_status` | `/api/kanaele` | Kanäle mit Plattform/Handle/Verbindungsstatus |
  | `management_social_bots` | `/api/bots?aktiv=1` | aktive Themen-/Marken-Profile |
  - **Read-only ist der Standard.** Das Aktions-Tool (Veröffentlichen) läuft NICHT über MCP,
    sondern als HITL-Aktion `post_veroeffentlichen` über appkit/actions (Außenwirkung ⇒
    Freigabe-Pflicht, Stufe `verifiziert`, K4). v1 ist der Live-Pfad DORMANT.
- **Mini-Dizzi** (`POST /api/ki/frage`, Vertrag 1.5): Dizzi reicht Fragen an die app-eigene
  Social-KI weiter (lokal; beobachten + vorschlagen, NIE eigenmächtig posten).
- **Events** an Dizzi: noch nicht (`shares.events=false`) — Zeitplan-/Posting-Erinnerungen an
  Dizzi-Meldungen sind ein vorbereiteter Slot (Setting `erinnerung_vorlauf_min`, Scheduler folgt).

## Bereiche & Bereichs-Social (V18, docs/34) — seit 26.06.
- **Bereich-Achse (lokal):** Management führt eine eigene `bereiche`-Tabelle (`bereiche.py`, Muster
  Admin/Money) — übergeordnete Kategorien, an denen Kanäle/Bots/Posts hängen (`bereich_id`, `''`=Allgemein).
  Eigener social-media-`art`-Katalog; `bereiche.kontext` = Admins `bereich.management_kontext` (lose Kopplung,
  standalone-fähig). CRUD `GET/POST/PUT/DELETE /api/bereiche` (+ `/api/bereich-typen`, `/{id}/inhalt`, `/zuordnung`).
- **`GET /api/bereich/social?kontext=` (read-only, V18):** löst `kontext` zuerst über `bereiche.kontext`
  auf (Aggregat je `bereich_id`: Bots/Kanäle/Post-Zähler/nächste Slots), sonst **Fallback** auf den
  Social-Bot-Namen (rückwärtskompatibel). Speist Dizz Admins Bereichs-Cockpit über den Core-Relay
  `/querverbindung/management/bereich-social`. Veröffentlichen bleibt strikt Management-HITL (nie hierüber).

## Wovon Dizz Management ABHÄNGT (depends)
- **`depends=["creator"]`** — WEICHE Kopplung: Dizz Management EMPFÄNGT Assets von **Dizz Creating**
  (REV-3) über `POST /api/creating/empfang` (Empfangs-Slot, Management-Seite). Die Abhängigkeit ist
  einseitig-eingehend und **nicht startkritisch**: ohne Creating läuft Management eigenständig
  (manuelle Entwürfe). Die Creating-GEGENSEITE (Sende-Aufruf) + der Übergabe-Vertrag sind World-Chat.
- Optional/Laufzeit: **Dizzi-ID** (SSO; standalone-Login als Rückfall) · lokales **Ollama**
  für die KI (0 €; ohne Ollama ehrlicher Hinweis statt Halluzination).

## Cross-Zugriff (A3, auf Anfrage — geregelt, protokolliert)
- **Dizz Creating → Dizz Management** (REV-3, eingehend): Asset + Metadaten + pro-Kanal-Derivate
  ⇒ Post-Entwürfe (idempotent über `herkunft_asset_id`). v1: Empfangs-Slot steht; Übergabe-Vertrag
  + Sende-Seite = World-Chat.
- **Dizz Management → Dizz Creating** (Richtung geben, später): Management gibt dem Creating über den
  Bezug zu Konten/Bots die inhaltliche Richtung vor (APP_GRUNDLAGEN §B). Noch nicht gebaut.

## Vorbereitete Kanal-Quellen (Gesetz 5, dormant)
`GET /api/kanaele/quellen` listet die `ChannelSource`-Adapter (IG/TikTok/X/LinkedIn/YouTube/
Threads/Bluesky/Mastodon + Ayrshare/Postiz) + Verbindungsstatus. **Posten v1 DORMANT.**
Details: [04_CHANNEL_VORBEREITUNG.md](04_CHANNEL_VORBEREITUNG.md).
