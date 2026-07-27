# Kanal-Vorbereitung — Dizz Management [MG] (Gesetz 5, dormant)

> **Gesetz 5: vorbereiten, nicht bauen.** Dieses Dokument macht die vorbereiteten
> Plattform-Anschlüsse SICHTBAR — Bewusstsein über ihr Vorhandensein ist Teil des
> Auftrags. Code: [`managementapp/channels.py`](../managementapp/channels.py).
> Stand 15.06.2026 (v1-Kern). **Posten an echte Kanäle bleibt v1 DORMANT** (Recht/
> Opt-in/Plattform-Richtlinien) — die App PLANT/ENTWIRFT lokal.

## Warum ein Adapter-Interface (kein if/else-Wildwuchs)
Plattform-APIs sind fragmentiert und ändern sich ständig (docs/RECHERCHE §6). Der
Domänen-Code spricht deshalb NIE direkt mit einer Plattform, sondern gegen EIN Interface
`ChannelSource` (`verbunden` · `publish` · `analytics`-Slot · `status`). Plattform-
Eigenheiten (Limits, Formate, OAuth-Scopes) leben als Adapter-Konfig. Austauschbar
dahinter: ein Adapter je Plattform ODER EIN Unified-Provider-Adapter.

## Sichtbarkeit
`GET /api/kanaele/quellen` liefert alle bekannten Adapter + `verbunden` (Token im Tresor?)
+ `posten_scharf` (v1 immer `false`). Liest nur **Tresor-NAMEN**, nie Geheimnisse.

## Vorbereitete Adapter

| Adapter | Plattform | Auth | Status v1 |
|---|---|---|---|
| `InstagramSource` | instagram | Meta Graph (OAuth, `instagram_content_publish`) | dormant |
| `ThreadsSource` | threads | Meta Threads API (OAuth) | dormant |
| `TikTokSource` | tiktok | Content Posting API (OAuth, `video.publish`) | dormant |
| `XSource` | x | X API v2 (OAuth, `tweet.write`) | dormant |
| `LinkedInSource` | linkedin | Posts/UGC API (OAuth, `w_member_social`) | dormant |
| `YouTubeSource` | youtube | Data API v3 `videos.insert` (Google-OAuth) | dormant |
| `BlueskySource` | bluesky | AT-Protokoll (App-Passwort/Session, offen) | dormant |
| `MastodonSource` | mastodon | Instanz-Token (`write:statuses`, offen) | dormant |
| `UnifiedProviderSource` | unified | **Ayrshare** (Cloud, API-Key) — opt-in, kostet, eigener MCP | dormant |
| `PostizSource` | postiz | **OSS-Selfhost** (REST-API, base_url + Key) — 0 € | dormant |

`adapter_fuer(plattform, vault_get)` liefert den passenden Adapter (direkt) bzw. den
Unified-Pfad (`ayrshare`/`postiz`) — genau das nutzt der Publish-Handler.

## Strategie (lokal-first, 0 €)
- **Default = direkte Plattform-APIs** (0 €, volle Tiefe, viel Wartung). OAuth-Token je
  Kanal im **Token-Tresor** (appkit/vault.py) — NIE in `app_settings`, NIE im Repo.
- **Opt-in Unified**: `unified_provider`-Setting auf `ayrshare` (wartungsarm, kostet, hat
  MCP für KI-Agenten) ODER `postiz` (OSS-Selfhost, 0 €, Betriebsaufwand). Default `aus`.
- Der **0-€/Lokal-Anspruch** gegen Drittpartei-Abhängigkeit/Kosten abwägen (Nutzer-Entscheid).

## Aktivierung (wenn ein Kanal scharf gehen soll)
1. App in der Plattform-Developer-Konsole registrieren (App-ID/Secret), nötige `SCOPES`
   anfragen, OAuth-Redirect einrichten.
2. Erhaltenen (Refresh-)Token verschlüsselt in den Token-Tresor legen (`token_name`,
   z. B. `instagram_oauth_token`) — Refresh-Rotation ist ein vorgesehener Slot.
3. Den `publish`-Pfad des Adapters auf den echten API-Call umstellen (Endpoint je Adapter
   im Docstring dokumentiert) + Rate-Limit/Retry/Backoff, alle Zeiten UTC.
4. **Außenwirkung bleibt HITL.** Veröffentlichen läuft NUR über die Aktion
   `post_veroeffentlichen` (Stufe `verifiziert`) — der Nutzer gibt jeden Post frei.

## Vorbereitete Felder im Datenmodell (Sync-/Live-Slots)
- `kanaele.token_name` / `kanaele.extern_id` / `kanaele.etag` — OAuth-Token-Bezug +
  Konto-Sync-Slots.
- `posts.extern_id` / `posts.etag` — Plattform-Post-ID nach Publish (Idempotenz/Status).
- `posts.format` / `asset-Derivate` — pro-Kanal-Seitenverhältnisse (Hoch-/Querformat).

## Medien-Pipeline (Slot)
Upload/Transcode/pro-Kanal-Format ist über die Creating-Derivate (REV-3) vorgedacht:
Dizz Creating liefert bereits pro-Kanal-Varianten (9:16/1:1/16:9); Management trägt sie als
`posts.medien` + `format`. Ein eigener Transcode-Schritt ist ein späterer Slot.
