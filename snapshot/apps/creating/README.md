# Dizz Creating — Creator

> Eigenständige App im Netzwerk **the world of dizzi** — einzeln lauffähig und verkaufbar,
> aber über **Dizzi-ID (Single-Sign-On)**, den **App-Vertrag** und das **MCP-Protokoll**
> nahtlos mit dem Gesamtsystem verbunden.

**Zweck:** Bild-, Video- und Musik-Erstellung sowie -Bearbeitung — lokale Kreativ-Werkbank.
Die Generierung läuft über **ComfyUI** als externen Dienst; die App steuert Job-Queue,
GPU-Zuteilung, Asset-Verwaltung und die Kennzeichnung erzeugter Inhalte.

| Doku | Inhalt |
|---|---|
| [docs/00_VISION.md](docs/00_VISION.md) | Was die App tut |
| [docs/01_APP_VERTRAG.md](docs/01_APP_VERTRAG.md) | Wie sie ans Gesamtsystem andockt |
| [docs/02_ANFORDERUNGEN.md](docs/02_ANFORDERUNGEN.md) | Kern-Umfang (Anforderungsliste) |
| [workflows/README.md](workflows/README.md) | Die ComfyUI-Graph-Bibliothek (Bild · Video · Audio) |

**Port-Vorschlag (Core):** 8214.

> **Hinweis zu diesem Auszug:** Enthalten sind Architektur, Verträge und die
> Workflow-Bibliothek dieser App. Die Kern-Implementierung ist in diesem öffentlichen
> Snapshot bewusst nicht enthalten.
