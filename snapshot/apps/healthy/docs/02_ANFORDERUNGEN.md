# Anforderungsliste — Dizz Healthy — Health

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss) — v1-Stand 15.06.2026
- [x] Mess-/Gewohnheits-Modell + Trends — Messwerte (FHIR-nah) + Supplements/Verletzungen/
      Training; deterministische `trends()` + lokale KI-Hinweise (`/api/analyse`, keine Diagnose)
- [x] Termin-Engine (CRUD, Kategorien) — **Erinnerungs-PUSH an Dizzi-Meldungen = Slot**
      (Setting `erinnerung_vorlauf_tage`, Frist-Wächter folgt)
- [x] Stats-Endpoint: heutige Werte/Gewohnheiten (`/api/stats` + `/api/summary`)
- [x] MCP-Tools: `health_gesundheits_trend`, `health_naechste_termine` (+ kachel_stats, aktive_supplements)

## Quer (aus dem App-Vertrag, gilt für alle)
- [x] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [x] MCP-Server (read-only Tools, Namensraum `health_*`)
- [x] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login (`install_dizzi_id`)
- [x] Account/Settings-Modul (Kernpaket K2, generisch aus appkit)
- [x] Daten user-scoped + sync-ready; sensible Daten lokal (sensitivity `hoechst` ⇒ KI lokal_only)
- [x] Tests (20, grün) + Doku-Sync (Gesetz 9)
- [x] **Wearable/Mobile VORBEREITET** (Gesetz 5): HealthSource-Adapter + BLE/GATT + FHIR + Mobile-Brücke
      (docs/04) — dormant, sichtbar über `/api/quellen`

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener schlanker FastAPI-Kern (keine OSS-Einbettung).
- **v1:** KI-Interaktion + **manuelle Dateneingabe** (Supplements, Verletzungen, Trainingsergebnisse,
  Gewicht, Schlaf, Ernährung) + KI-Auswertung (Trends/Belastung-Erholung — nur Hinweise, KEINE Diagnose).
- **Externe Dienste:** v1 keine; Wearable/Smartwatch **umfangreich vorbereitet** (`HealthSource`-Adapter,
  BLE/GATT, FHIR-Schema, Mobile-Brücke) — Gerät holt der Nutzer zur Bauphase. Lokal-first.
- **Sensibilität:** HÖCHST → strikt lokal, kein Boost-Modell.
- **Marke:** Dizz Healthy (bestätigt).
