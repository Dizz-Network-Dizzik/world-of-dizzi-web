# Anforderungsliste — Dizz News — News Compact

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten, damit späteres
> Einzel-Arbeiten nahtlos erweitern kann. Wird vor dem Bau in einer Fragerunde finalisiert.

## Kern (Muss)
- [ ] Quellen-/Sektor-Modell (Vorbild: ein kuratierter News-Skill)
- [ ] Report-Generierung + Ablage
- [ ] Stats-Endpoint: letzter Report, Sektoren
- [ ] MCP-Tools: aktueller_report, sektor_news

## Quer (aus dem App-Vertrag, gilt für alle)
- [ ] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [ ] MCP-Server (read-only Tools)
- [ ] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login
- [ ] Account/Settings-Modul (Kernpaket K2)
- [ ] Daten user-scoped + sync-ready; sensible Daten lokal
- [ ] Tests + Doku-Sync (Gesetz 9)

## Entschieden (Fragerunde 3, 11.06. — s. docs/RECHERCHE.md + Plan §6b)
- **Bauweise:** eigener schlanker Feed-Kern (feedparser + OPML); FreshRSS/Miniflux nur Konzept-Blaupause.
- **v1:** Ausbau des bestehenden News-Skills (Sektor-/Fixquellen-Logik) +
  **getaktete Automatik** (Timer, deckt kompletten Zeitraum automatisch ab; zusätzlich manuell startbar) +
  **übergreifende KI-Ebene** (zusammenfassen, Fragen beantworten, schön darstellen).
- **Externe Dienste:** RSS/Atom/JSON Feed/WebSub (0 €); KI-Summary lokal (Ollama), NewsAPI nur opt-in.
- **Marke:** Dizz News (bestätigt).
