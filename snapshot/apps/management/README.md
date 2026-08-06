# Dizz Management — KI-Agenten-Verwaltung (erste Domäne: Social Media)

> Eigenständige App im Netzwerk **the world of dizzi** — einzeln lauffähig und verkaufbar,
> aber über **Dizzi-ID (Single-Sign-On)**, den **App-Vertrag** und das **MCP-Protokoll**
> nahtlos mit dem Gesamtsystem verbunden.

**Zweck:** Kanäle, Inhaltsplanung, Veröffentlichung und Auswertung an einem Ort.

| Doku | Inhalt |
|---|---|
| `docs/00_VISION.md` | Was die App tut |
| `docs/01_APP_VERTRAG.md` | Wie sie ans Gesamtsystem andockt |
| `docs/02_ANFORDERUNGEN.md` | Kern-Umfang (Anforderungsliste) |
| `docs/03_VERNETZUNG.md` | Was die App teilt / wovon sie abhängt |
| `docs/04_CHANNEL_VORBEREITUNG.md` | Kanal-Adapter-Slots (Gesetz 5, dormant) |

**Status:** v1-Kern GEBAUT (id `management`, Port **8213**, sensitivity `hoch` ⇒ KI lokal-first).
Domäne: Kanäle · Social-Media-Bots · Posts/Entwürfe · Zeitplan · Creating-Empfang (REV-3) ·
HITL-Veröffentlichung (DORMANT). Paket: `managementapp` (aus `templates/refapp`).

**Start (Entwicklung):**
```
<venv-python> -m uvicorn managementapp.main:app_factory --factory --host 127.0.0.1 --port 8213 --app-dir .
```
**Tests:** `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest tests/ -q`

---

> **Zu diesem Auszug:** Veröffentlicht ist von dieser App nur diese README. Ihr Code und ihre eigene Doku (`docs/`) sind seit dem 6. August 2026 nicht mehr Teil des öffentlichen Auszugs; die netzweiten Gesetze und Verträge, nach denen sie gebaut ist, liegen in [`docs/`](../../docs/README.md).
