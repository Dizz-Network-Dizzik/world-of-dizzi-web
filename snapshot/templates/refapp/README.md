# Referenz-App des App-Vertrags (K3) — Kopier-Anleitung

> Diese App ist die **lebende Referenz-Implementierung** des App-Vertrags
> (`the world of dizzi/docs/16_APP_VERTRAG_SPEC.md`). Jede neue Netzwerk-App
> entsteht durch **Kopieren dieser Vorlage** — nicht durch Neu-Erfinden.

## Neue App aufsetzen (Checkliste)

1. **appkit vendoren** (nach Vertrags-Freeze R1.6):
   `venv-python ops/sync_appkit.py --to ../<app-ordner>`
2. **Vorlage kopieren**: `refapp/` → `<app-ordner>/<paketname>/` (Paket umbenennen,
   z. B. `money`), dazu `mcp_server.py` + `tests/`.
3. **Manifest anpassen** (`main.py`): id, name, brand („Dizz …"), Port aus dem
   App-Vertrag-Stub (8210–8217), icon, **sensitivity** (steuert KI-Routing!),
   mcp.tools, shares, depends.
4. **Domäne einsetzen** — genau drei Stellen:
   - `_SCHEMA` (Domänen-Tabellen, zwingend mit UUID/user_id/Timestamps/Soft-Delete),
   - Domänen-Router (Request-Modelle auf MODUL-Ebene — PEP-563-Falle, s. Kommentar),
   - `summary()` (display-fertige KPIs für die Dashboard-Kachel).
5. **Tests**: `tests/test_contract.py` kopieren, APP_ID/Import anpassen —
   `conformance.check_contract` erzwingt den Vertrag maschinell.
6. **Frontend kommt mit dem Template** (H-5) — `ui-kit/` (kanonisches Kit), `static/index.html`
   (Standard-Skelett **inkl. vollständigem Einstellungs-/Konto-Fenster**) und der `/ui-kit`-Mount mit
   `no-cache` (H-1) sind bereits enthalten; beim Kopieren der Vorlage erbst du sie automatisch.
   **Nur anpassen:** Marke/Funktion im Kopf, die `<main>`-Panels (Domäne) und der EINE Mini-Dizzi-Stub
   (`/api/ki/frage`). **Das Einstellungs-/Konto-Fenster bleibt UNVERÄNDERT** (= Standard-Kit, Norm
   docs/19 §2b): fünf Sektionen (Identität & Sicherheit · Design · Verbundene Dienste · Vernetzung &
   KI-Aktivität · Einstellungen), K2.4-Controls, 10×10-Design-Switcher mit Live-Vorschau — **generisch
   aus den appkit-Endpunkten** (`/api/settings(/schema)` · `/api/account` · `/auth/me` · `/api/vault` ·
   `/api/actions`), funktioniert out-of-the-box, weil JEDE Vertrags-App diese Endpunkte hat. Tokens sind
   **verlinkt** (`/ui-kit/tokens.css`, Single-Source); `?v=` ist dank no-cache **optional**. Standard-
   Verhalten (Panels/Collapse/Spin/Floats/Hintergrund-Slot) ist verdrahtet. Normen: Panel/Design
   **docs/06 §6.3**, Settings+Floats **docs/19 §2b**, Spin **docs/14**, Hintergründe **docs/_archiv/24**.
   Vollausbau-Referenz (identisches Muster mit Domäne): `news/static/index.html`.
7. **Start**: `venv-python -m uvicorn <paket>.main:app_factory --factory
   --host 127.0.0.1 --port <port> --app-dir <app-ordner>`
8. **Autostart registrieren** (App überlebt Sessionende/Reboot): eine Zeile in der App-Tabelle
   von `the world of dizzi/ops/install_autostart.ps1` ergänzen (Task/Spec/Port/Dir/Factory),
   dann das Skript EINMAL erhöht ausführen (fordert UAC selbst an). Die robuste Startmechanik
   (`dizz-server.exe` = echte Basis-Interpreter-Kopie im venv, umgeht den Redirector-Stub) steckt
   in `ops/launch_app.ps1` — generisch, nichts pro App anzupassen.
9. **In Dizzi anbinden**: `DIZZI_CONTRACT_APPS="<id>=http://127.0.0.1:<port>"`
   (Panel wird automatisch live; kein Dizzi-Code nötig).
10. **Schutzstufen**: sensible Routen mit
   `Depends(require_level("verifiziert"|"hochsicher"))` deklarieren — sie sind
   vor K1 fail-closed (403) und werden mit Dizzi-ID automatisch scharf.

## Was die Vorlage zeigt

| Datei | Zeigt |
|---|---|
| `refapp/__init__.py` | appkit-Auffindung (vendiert ODER kanonisch) |
| `refapp/main.py` | Manifest · Domänen-Schema · Router · summary_fn · Factory |
| `mcp_server.py` | read-only MCP über der eigenen HTTP-API (stdio) |
| `tests/test_contract.py` | Vertrags-Konformität + Domänen-Beispiel |
| `static/index.html` | Standard-Frontend (Lockup · einklappbares Panel · SVG-Floats · Spin · **vollständiges Einstellungs-/Konto-Fenster** · Mini-Dizzi-Stub) |
| `ui-kit/` | kanonisches UI-Kit (tokens/controls/collapse/floats/spinfling/background) — same-origin via `/ui-kit` (no-cache) |

## Standard-Kit — was JEDE App teilt (kanonische Quelle + Norm)

Übergreifende Standards, die bei neuer App 1:1 übernommen werden. Das **Behavioral-Kit ist
netzwerkweit byte-identisch** (per MD5 verifiziert) — daran wird NICHT pro App herumgebaut.

| Standard | Kanonische Quelle | Norm |
|---|---|---|
| Backend-Vertrag (Manifest · SSO · read-only Stats · MCP · Schutzstufen) | `appkit` (vendort) + dieses Template | docs/16 |
| Design-Tokens (10 Designs × 10 Farben) | `shared/dizz-tokens.css` (Master) | docs/06 |
| Controls (Checkbox/Select/Stepper) + Panel-Collapse | `shared/controls.css` + `shared/collapse.js` | docs/06 §6 |
| Panel-Optik FINAL (Kopf-Box · Links-Streifen · Toggle-Hover · kein Card-Hover) | `controls.css` + App-`.card`-Ebene | docs/06 §6.3 |
| Float-Knöpfe (⚙ Konto · 💬 Mini-Dizzi · SVG-Doppelicon · Charge/Spinlift/lgshoot) | `shared/floats.js` + `.floatacct/.floatdizzi`-CSS + Icon-Sprite (News) | docs/14 · docs/19 §2b |
| **DzHalter** Float-Andock-Schale (Slots + Frei/Fix-Schalter · Default angedockt · Rückflug) | `ui-kit/float_dock.{js,css}` — VOR `floats.js` laden | docs/14 v4.4 |
| Panel-Spin-Physik v4.3 (greifen→schwingen→schleudern→Impuls auf Floats) | `shared/spinfling.js` | docs/14 |
| Hintergründe (D4 design-spezifisch) + D5-Renderer-Slot `#bg-stage` | `shared/background.css` + `shared/background.js` | docs/_archiv/24 |
| **Einstellungs-/Konto-Fenster** (5 Sektionen · 10×10-Switcher · K2.4-Controls · HITL · 5 Gotchas) — **VOLLES Kit-Element**, gehört zu ⚙/💬 dazu | `templates/refapp/static/index.html` (= News-Muster, generisch) | docs/19 §2b |
| **Autostart** (Logon-Task, überlebt Sessionende) | `ops/install_autostart.ps1` + `ops/launch_app.ps1` | (Eintrag + 1× UAC) |
| Dizzi-Vernetzung (Auto-Panel · MCP-Namensraum `<id>_<tool>` · Mini-Dizzi-Slot) | appkit + `DIZZI_CONTRACT_APPS` | docs/16 §6 |

**Ehrlicher Stand der Single-Source-Disziplin (geplante Härtung, kein Blocker):**
- **Tokens** werden derzeit pro App INLINE im `<style>` geführt (Werte netzwerkweit konsistent;
  `shared/dizz-tokens.css` ist der Master, per-App-`ui-kit/tokens.css` = Kopien). Konsolidierung
  (alle Apps gegen die EINE Datei linken statt inline) ist ein vorgemerkter Schritt.
- **Spin/Floats/Controls** sind als verlinkte ui-kit-Dateien sauber single-sourced; einige Apps
  führen `initSpinFling`/Token-Blöcke historisch zusätzlich inline (verhaltensgleich) — Aufräumen
  zur reinen Verlinkung ist Maintainability, kein Funktions-Blocker.
- **Einstellungs-/Konto-Fenster** ist (wie die Tokens) pro App INLINE im `static/index.html` — das
  **Template ist die kanonische Quelle**, alle Live-Apps tragen dasselbe Muster (Core in React, sonst
  vanilla). Extraktion in ein gemeinsames JS-Modul = vorgemerkte Maintainability-Härtung; das Fenster
  ist überall verhaltensgleich und endpunkt-generisch, daher kein Funktions-Blocker.
- **Dizzi↔App-AI: bereits aktiv.** Dizzi liest Panels/Stats aller angedockten Apps, beobachtet
  sie (L4-Observer) und **reicht Fragen an die Mini-Dizzi jeder App weiter** (Core
  `POST /api/ki/app/{app_id}` → deren `POST /api/ki/frage`, „Mini-Dizzi-Verbund", Vertrag 1.5).
  Plus isolierter MCP-Server je App (`<id>_<tool>`). **Offen (Leading-Schritt):** die AUTONOME
  Orchestrierung — Dizzi wählt selbst die passende(n) App(s), kombiniert Antworten und ruft
  Aktions-Tools (Querverbindungs-Verträge). Der Zugriff steht; die Eigenständigkeit folgt.
