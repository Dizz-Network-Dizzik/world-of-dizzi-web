# Anforderungsliste — Dizz Management — KI-Agenten-Verwaltung (erste Domäne: Social Media)

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss) — v1 GEBAUT 15.06.2026
- [x] Redaktions-/Planungs-Modell (Kanäle · Social-Bots · Posts/Entwürfe · Zeitplan, `domain.py`)
- [x] Konnektor-Slots für Plattform-APIs (vorbereitet, deaktiviert) — `ChannelSource`-Adapter
      (8 Plattformen + Ayrshare/Postiz), DORMANT (Gesetz 5, `channels.py`, docs/04)
- [x] Stats-Endpoint: geplante Posts u. a. (`/api/stats` + Kachel); Reichweite = Analytics-Slot (dormant)
- [x] MCP-Tools: `management_redaktionsplan`, `management_kanal_status` (+ kachel_stats, social_bots)
- [x] **Plus (über die Liste hinaus):** Creating-Empfang (REV-3) · HITL-Veröffentlichung (dormant)
      · übergeordnete Social-KI (Mini-Dizzi + `/api/plan`)

## Quer (aus dem App-Vertrag, gilt für alle) — erfüllt
- [x] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [x] MCP-Server (read-only Tools, Namensraum `management_*`)
- [x] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login
- [x] Account/Settings-Modul (Kernpaket K2)
- [x] Daten user-scoped + sync-ready; sensible Daten lokal (sensitivity `hoch` ⇒ `lokal_only`)
- [x] Tests (17 grün) + Doku-Sync (Gesetz 9)

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener schlanker FastAPI-Kern.
- **v1+Ziel:** **ALLE Kanäle** vorbereitet/ansteuerbar (IG/TikTok/X/LinkedIn/YouTube/Threads/Bluesky/…);
  benannte „Social-Bots" (Themen-/Marken-Profile), die **KI-gesteuert übergreifend** Inhalte (v. a. Video)
  **erstellen + posten**; zusätzlich **übergreifende KI-Verwaltungs-Ebene** (interagiert, hilft beim Kanal-Mgmt).
- **Externe Dienste:** Plattform-APIs hinter EINEM `SocialChannel`-Adapter; Unified-Provider (Ayrshare) als
  opt-in (lokal-first-Default). OAuth-Token-Tresor (K2).
- **Aktionen (posten/planen):** Außenwirkung → Human-in-the-Loop (K4).
- **Kopplung:** enge Zusammenarbeit mit **Dizz Creating** (Erstellung→Verteilung).
- **Marke:** Dizz Management (bestätigt).
