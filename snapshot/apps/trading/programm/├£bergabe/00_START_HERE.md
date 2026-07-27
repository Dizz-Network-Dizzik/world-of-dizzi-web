# ÜBERGABE — Dizz Trading (Start für einen neuen Chat)

> Dieser Ordner ist **self-contained**: mit diesen 4 Dateien findet sich ein neuer Chat sofort
> wieder ein. Lesereihenfolge: dieses Dokument → `01_KONZEPT_UND_ARCHITEKTUR` → `02_LERNSYSTEM`
> → `03_STAND_UND_BETRIEB`. Voller Live-Stand im Gedächtnis: Notiz **`trading-bot-eins-stand`**.
>
> **Stand dieser Übergabe: 03.07.2026.** (Frühere Fassungen beschrieben den 5-Bot-Prototyp vom
> 06.06.2026 vor der Monorepo-Migration — diese Version ist auf das heutige System gezogen.)

## Was ist das?
**Dizz Trading** [TR] — die Trading-App im **Monorepo „the world of dizzi"**. Eine Krypto-Bot-Flotte
mit KI-Lern-Ebenen. **Hybrid:** die deterministische Engine **Freqtrade** handelt (0 LLM-Token im
Dauerbetrieb); eine **KI-/Meta-Schicht** recherchiert Strategien, wertet Performance aus, erkennt
Marktregime und **lernt** einen selbst-zusammengesetzten Meta-Algorithmus über alle Edge-Quellen.

- **Code (kanonisch):** `C:\Dizzik\code\dizz-network\apps\trading\programm` — **EIN git-Repo**
  (Monorepo, seit 24.06.2026; der alte Pfad `C:\Dizzik\code\Trading Bot eins` ist **gelöscht**).
- **Plattform:** Windows · Python 3.12 · Dashboard `http://127.0.0.1:8137`
- **Modus:** **Demo/Paper** (`dry_run=true` für ALLE Bots) → **kein echtes Geld**, keine echten Orders.
  Echtgeld ist ein bewusst hochgesichertes, noch **nicht** scharfgeschaltetes Gate (M6, `RUNBOOK_ECHTGELD.md`).

## ⚠ Geld-System — Betriebsregeln (verbindlich)
- **`:8137` NIE eigenmächtig neu starten** — gegated (Nutzer-Go + Backup-first + UAC am Rechner).
  Andere Chats fassen die laufende Flotte **read-only** an.
- **Bot anlegen/löschen/Restart** = Geld-System ⇒ Nutzer präsent/bestätigt (Gesetz 2: ehrlich vor aktiv).
- **Sandbox-Gotcha:** HTTP-`DELETE`/`/stop` an die API werden als „Datei-Löschung" geblockt →
  autorisierte Live-Calls brauchen `dangerouslyDisableSandbox`.
- **Secrets** (Bitget-/Anthropic-Keys) NIE in Repo/Chat — nur in `.env` (gitignored, siehe `SETUP_USER.md`).

## Sofort starten (WICHTIG: eigene venvs!)
```powershell
cd "C:\Dizzik\code\dizz-network\apps\trading\programm"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8137
# Dashboard: http://127.0.0.1:8137   (oder Autostart-Task / scripts\launch.ps1)
```
- Es gibt **zwei** venvs: `programm\.venv` (Backend: FastAPI/ccxt/anthropic) + `programm\engine\.venv`
  (Freqtrade/TA-Lib). Basis-Python hat **kein** FastAPI → immer die `.venv` nehmen.
- Die Bots laufen als **eigene Freqtrade-Prozesse** (`DizzTrading-Bot.exe`), das Backend als
  `DizzTrading-Server.exe`. Sie **überleben einen uvicorn-Neustart** (Erkennung per Kommandozeile),
  **nicht** einen Maschinen-Neustart → dann greift der Autostart-Task `DizzTrading-Autostart`
  (Login-Trigger, `launch.ps1` → Backend + Auto-Resume der Bots).

## Tests (vor jedem `:8137`-Neustart grün halten)
```powershell
cd "C:\Dizzik\code\dizz-network\apps\trading\programm"
$env:TBT_NO_STARTUP=1
$env:PYTHONPATH="C:\Dizzik\code\dizz-network\packages"
.\.venv\Scripts\python.exe -m pytest -q          # aktuell 474 grün (50+ Test-Dateien)
```
`TBT_NO_STARTUP=1` verhindert, dass die Test-Suite die echte Flotte/Threads hochfährt.

## Aktueller Stand (03.07.2026) — Kurzfassung
- **50 Bots** (alle `dry_run`, Futures) über **12 aktiv geflogene** von **18 lauffähigen Strategien**.
- **KI-Lern-Ebenen komplett:** Regime-HMM · Meta-Lerner (Stufe 1) · Master-Ensemble (Stufe 2) ·
  markt-neutraler Sockel (CSM/Pairs/StatArb/Market-Making, simuliert) · Autopilot (6-h-Loop) ·
  Governor (Portfolio-Risiko) · Concentration (Klumpen) · Vol-Targeting + **Kelly-Sizing (FP-2)**.
- **„Daten-reifen"-Phase:** viele empirische Teile aktivieren sich selbst mit mehr Laufzeit (≥90 T).
- **Echtgeld** bewusst blockiert (M6-Gate). Details + nächste Schritte: `03_STAND_UND_BETRIEB`.

## Vorschlag: erster Prompt im neuen Chat
> „Lies `apps/trading/programm/Übergabe/` (alle 4 Dateien) + die Mem-Notiz `trading-bot-eins-stand`.
> Die Flotte läuft (read-only, NICHT eigenmächtig neu starten). Mach weiter mit **[Punkt aus
> `03_STAND_UND_BETRIEB`]**. Budget im Blick, nach jedem Schritt Suite grün + verifizieren."
