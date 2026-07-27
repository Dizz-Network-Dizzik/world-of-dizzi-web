# Recherche-Dossier — Dizz Management (KI-Agenten-Verwaltung; Domänen-Recherche: Social Media)

> Stand 11.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> Zweck: Konnektoren, Standards und **jetzt vorzusehende** Verbindungs-Vorbereitungen.

## 1. Feature-Baseline (Marktstandard)
Multi-Kanal-Posten + **Scheduling**, pro-Kanal-Vorschau/Anpassung (Text/Medien/Hashtags), Content-
Kalender, Entwürfe/Freigabe, **Unified Inbox** (Kommentare/DMs), Analytics (Reichweite/Engagement),
Asset-Bibliothek, Wiederverwendung/Recycling. Vorbilder: Buffer, Hootsuite, Agorapulse, Postiz (OSS).

## 2. Standard-Datenquellen & Konnektoren
- **Plattform-APIs direkt:** Meta (Facebook/Instagram/Threads) Graph API, **X/Twitter** API,
  **LinkedIn**, **TikTok** (Developer/Content Posting API), YouTube, Pinterest, Reddit, **Bluesky**
  (AT-Protokoll, offen), Mastodon (offen), Google Business Profile, Telegram.
- **Unified-Posting-APIs** (1 Integration für alle, kostenpflichtig/Tiers): **Ayrshare** (13+ Kanäle,
  **eigener MCP-Server für KI-Agenten**), **Outstand**, **Postforme**, **Upload-Post**, **Zernio/Late**.
- **OSS-Selfhost:** **Postiz** (REST-API, n8n/Zapier-anbindbar) als Referenz für 0-€-Pfad.
- **Automations-Bus:** n8n/Make/Zapier-kompatible Webhooks.

## 3. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **`SocialChannel`-Adapter-Interface** (publish/schedule/analytics/inbox) mit Implementierungen je
  Plattform ODER **einem** Unified-Provider-Adapter (Ayrshare) dahinter — austauschbar.
- **OAuth-Token-Tresor** je Kanal (Refresh-Rotation) — Andockpunkt jetzt anlegen.
- **Medien-Pipeline-Slot**: Upload/Transcode/pro-Kanal-Format (Hochformat/Seitenverhältnisse).
- **Aktions-Tool mit Human-in-the-Loop** (K4): „posten/planen" ist eine Außenwirkungs-Aktion →
  Bestätigungsstufe vorsehen (kein eigenmächtiges Veröffentlichen).
- **Überschneidung mit Dizz Creating** (Content-Erstellung) klar trennen: Creating = produzieren,
  Management = verteilen/planen/auswerten.

## 4. App-eigener KI-Wächter-Kern
Beste Posting-Zeiten, Engagement-Muster, Hashtag-Wirkung, Themen-Performance, Antwort-Vorschläge für
die Inbox, Content-Recycling-Kandidaten. Schlägt Plan/Texte vor — **Veröffentlichen nur mit Bestätigung**.

## 5. Sensible Daten & Sicherheit
OAuth-Tokens fremder Plattformen sind sicherheitskritisch (Token-Tresor, Scopes minimal, Rotation).
Veröffentlichen = Außenwirkung → **immer Human-in-the-Loop**. Plattform-Richtlinien/Rate-Limits
beachten (kein Spam/Automations-Verstoß).

## 6. Tech-Standards & Best-Practice (gegen Spaghetti)
- **Ein** Kanal-Interface; Plattform-Eigenheiten (Limits, Formate) als Adapter-Konfig, nicht als
  if/else-Wildwuchs.
- Unified-Provider (Ayrshare) spart enorm Wartung (jede Plattform-API ändert sich ständig) — **aber**
  Kosten + Drittpartei-Abhängigkeit gegen 0-€/Lokal-Anspruch abwägen.
- Idempotentes Scheduling (kein Doppel-Post), Retry/Backoff bei Rate-Limit; alle Zeiten UTC.

## 7. Offene Entscheidungsfragen → Fragerunde
1. **Welche Kanäle** nutzt du wirklich (Instagram/TikTok/X/LinkedIn/YouTube/…)? → bestimmt Adapter-Umfang.
2. **Unified-Provider Ayrshare** (schnell, wartungsarm, kostet, hat MCP-Server) **vs. direkte
   Plattform-APIs** (0 €, viel Wartung) **vs. Postiz selfhost**?
3. Abgrenzung **Dizz Management ↔ Dizz Creating** final ziehen (Verteilen vs. Erstellen).
4. Soll Dizzi Inbox-Antworten **vorschlagen** (immer mit Freigabe) — ja/nein?

## Quellen
- [Ayrshare — Social Media API (inkl. MCP)](https://www.ayrshare.com/)
- [Outstand — Unified Social Media API](https://www.outstand.so/)
- [Postiz — OSS Scheduling](https://postiz.com/)
- [Zapier — beste Social-Tools 2026](https://zapier.com/blog/best-social-media-management-tools/)
