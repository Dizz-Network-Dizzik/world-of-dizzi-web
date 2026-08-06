# Dizzi-Core — `core` :8200

> Headless Core-Service (FastAPI) im Netzwerk **the world of dizzi** — KI-Orchestrator + Hub.
> Geteilter Code (appkit/ui-kit) liegt in `../../packages/`.

**Zweck:** KI-Orchestrator (lokale Modelle via Ollama, JSON-Schema-Grammatik), **Panel-Registry**
(`/api/panels` — Online-Status aller Apps), **MCP-Hub** (`app/ai/tools.py` zieht alle App-Gateways an
EINEN Punkt), **Health-Watch** (`/api/health`, 10 Ziele), **Dizzi-ID-SSO** (Passkeys, nur localhost).

| Wo | Inhalt |
|---|---|
| `app/` · `tests/` | Code + Tests |

**Tests:** `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q` (Soll 288).
**Restart (gegated):** `dizz-server.exe -m uvicorn app.main:app --port 8200 --app-dir "<core>"` (Pfad **quoten**).

---

> **Zu diesem Auszug:** Veröffentlicht ist von dieser App nur diese README. Ihr Code und ihre eigene Doku (`docs/`) sind seit dem 6. August 2026 nicht mehr Teil des öffentlichen Auszugs; die netzweiten Gesetze und Verträge, nach denen sie gebaut ist, liegen in [`docs/`](../../docs/README.md).
