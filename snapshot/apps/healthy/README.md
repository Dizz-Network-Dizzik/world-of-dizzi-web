# Dizz Healthy — Health

> Eigenständige App im Netzwerk **the world of dizzi** — einzeln lauffähig und verkaufbar,
> aber über **Dizzi-ID (Single-Sign-On)**, den **App-Vertrag** und das **MCP-Protokoll**
> nahtlos mit dem Gesamtsystem verbunden.

**Zweck:** Gesundheits-Watching: Vitalwerte, Gewohnheiten, Termine — der Gesundheits-Überblick.

| Doku | Inhalt |
|---|---|
| [docs/00_VISION.md](docs/00_VISION.md) | Was die App tut |
| [docs/01_APP_VERTRAG.md](docs/01_APP_VERTRAG.md) | Wie sie ans Gesamtsystem andockt |
| [docs/02_ANFORDERUNGEN.md](docs/02_ANFORDERUNGEN.md) | Kern-Umfang (Anforderungsliste) |
| [docs/03_VERNETZUNG.md](docs/03_VERNETZUNG.md) | Vernetzungs-Manifest (was geteilt/abhängig) |
| [docs/04_WEARABLE_VORBEREITUNG.md](docs/04_WEARABLE_VORBEREITUNG.md) | Wearable/Mobile-Anschlüsse (Gesetz 5) |

**Status:** **v1-Kern GEBAUT** (15.06.2026) — Messwerte/Supplements/Verletzungen/Training/Termine,
deterministische Trends + lokale KI-Hinweise (keine Diagnose), FHIR/LOINC, read-only MCP, Frontend.
20 Tests grün, browser-verifiziert. Wearable/Mobile umfangreich VORBEREITET (Gesetz 5, nicht gebaut).
**Port (Core):** 8217 · **Sensibilität:** hoechst (KI strikt lokal, nie Cloud/Boost).
