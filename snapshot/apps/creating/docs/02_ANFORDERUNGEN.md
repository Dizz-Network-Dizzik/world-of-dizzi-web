# Anforderungsliste — Dizz Creating — Creator

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss)
- [ ] Pipeline Bild/Video (lokale Modelle prüfen: SD-Klasse etc.)
- [ ] Asset-Verwaltung + Export
- [ ] Stats-Endpoint: Jobs, Bibliotheksgröße
- [ ] MCP-Tools: erstelle_bild (Aktion, Human-in-the-Loop)

## Quer (aus dem App-Vertrag, gilt für alle)
- [ ] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [ ] MCP-Server (read-only Tools)
- [ ] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login
- [ ] Account/Settings-Modul (Kernpaket K2)
- [ ] Daten user-scoped + sync-ready; sensible Daten lokal
- [ ] Tests + Doku-Sync (Gesetz 9)

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener Kern; **Architektur-KI** baut die Kern-Architektur **Bau-Instanz (Generierung)** +
  **Schneid-Instanz (Editing)** — gestützt auf Recherche R-A.
- **v1-Ziel:** KI-Medien-System — Bilder UND Videos **bearbeiten + analysieren** (auf Input), **Videos
  schneiden** (Zusammenarbeit mit Dizz Management), **from scratch** Bilder/Videos **neu erzeugen**.
- **Externe Dienste/Modelle:** lokal-first auf **GPU (RTX 5070 Ti)** (SD/ComfyUI-Klasse, lokale Video-Modelle);
  Cloud opt-in für hochwertige Video-Gen (R-A bewertet konkret). Stimme: Piper (aus Dizzi-Kern).
- **Aktionen:** Veröffentlichung läuft über Management (Human-in-the-Loop).
- **Marke:** Dizz Creating (bestätigt).
