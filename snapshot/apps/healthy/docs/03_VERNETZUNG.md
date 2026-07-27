# Vernetzungs-Manifest — Dizz Healthy [HE]

> Pflichtteil des App-Vertrags (docs/01 §7): **was** die App mit dem Verbund teilt und
> **wovon** sie abhängt. Stand 15.06.2026 (v1-Kern gebaut). Maschinell unter
> `GET /api/manifest` (Felder `shares`, `depends`, `mcp`).

## Identität
- **id** `health` · **brand** „Dizz Healthy" · **name** „Gesundheit" · **Port** `8217`
  (localhost-gebunden) · **icon** `heart`.
- **sensitivity** `hoechst` — HOCHSENSIBEL. Steuert das KI-Routing auf `lokal_only`
  (nie Boost/Cloud) und stellt sensible Routen hinter verifizierte Verbindung.

## Was Dizz Healthy TEILT (shares)
- **Stats-Kachel** (`/api/summary`, read-only): Gewicht (jüngstes), Messwerte (30 T),
  aktive Supplements, offene Verletzungen, nächster Termin. Display-fertige KPIs.
- **MCP-Server** (stdio, read-only, Namensraum `health_*`, `healthapp/mcp_server.py`):
  | Tool | Quelle | Inhalt |
  |---|---|---|
  | `health_kachel_stats` | `/api/stats` | Kennzahlen-Block |
  | `health_gesundheits_trend` | `/api/trends?tage=30` | deterministische Messwert-Trends (Richtung, Schnitt, Referenz-Einordnung) |
  | `health_naechste_termine` | `/api/termine?kommend=1` | kommende Arzt-/Vorsorge-Termine |
  | `health_aktive_supplements` | `/api/supplements?aktiv=1` | aktuelle Supplements |
  - Bewusst **Aggregate/Trends** statt jedem Rohwert (hochsensibel): Dizzi bekommt
    genug für sanfte Hinweise, ohne dass jeder Einzelwert über den Bus geht.
- **Mini-Dizzi** (`POST /api/ki/frage`, Vertrag 1.5): Dizzi reicht Fragen an die
  app-eigene Gesundheits-KI weiter (lokal; beobachten + Hinweise, NIE Diagnose).
- **Events** an Dizzi: noch nicht (`shares.events=false`) — Termin-/Vorsorge-Push an
  Dizzi-Meldungen ist ein vorbereiteter Slot (Setting `erinnerung_vorlauf_tage`, Wächter folgt).

## Wovon Dizz Healthy ABHÄNGT (depends)
- **Keine** harte App-Abhängigkeit in v1 (`depends=[]`). Eigenständig lauffähig.
- Optional/Laufzeit: **Dizzi-ID** (SSO; standalone-Login als Rückfall) · lokales
  **Ollama** für die KI (0 €; ohne Ollama ehrlicher Hinweis statt Halluzination).

## Cross-Zugriff (A3, auf Anfrage — geregelt, protokolliert)
Keiner aktiv. Vorgesehen für später (jeweils hinter Freigabe + Audit):
- **Dizz Plans** ↔ Gesundheits-Routinen/Termine (Kalender-Kopplung).
- **Dizz Admin** ↔ Arzt-/Befund-Dokumente (sicher in Bürokratie gelagert, auf Anfrage).

## Vorbereitete Wearable-Quellen (Gesetz 5, dormant)
`GET /api/quellen` listet die `HealthSource`-Adapter (Apple/Health-Connect/Terra/BLE)
+ Verbindungsstatus. Details: [04_WEARABLE_VORBEREITUNG.md](04_WEARABLE_VORBEREITUNG.md).
