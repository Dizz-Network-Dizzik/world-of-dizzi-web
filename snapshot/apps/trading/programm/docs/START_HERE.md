> # ⚠️ HISTORISCH (Stand 06.06.2026) — SUPERSEDED
> Dieses Dokument beschreibt den **5-Bot-Prototyp vor der Monorepo-Migration** (alter Pfad
> `C:\Dizzik\code\Trading Bot eins`, „Projekt BotT/Trading Bot Trial", 5 Bots / 6 Strategien).
> **Aktueller Einstieg = `programm/Übergabe/00_START_HERE.md`** (Monorepo-Pfad, 50 Bots / 18
> Strategien, Lern-Ebenen, Kelly-Sizing). Der Text unten bleibt als historischer Beleg erhalten.

# START HERE — Projekt BotT (Einstieg für neuen Chat) · HISTORISCH

Dieses Dokument ist der **einzige nötige Einstieg**, um nahtlos weiterzuarbeiten.
Es fasst Projekt, Struktur, Stand und nächste Schritte zusammen. Details stehen
in den verlinkten Dokumenten.

---

## 1. Was ist das?
**Trading Bot Trial („Projekt BotT")** — eine Desktop-/Web-App, um mehrere
**Krypto-Trading-Bots** (Bitget) zu verwalten. **Hybrid-Architektur:** die
deterministische Engine **Freqtrade** handelt; eine **KI** recherchiert nur
periodisch Strategien und analysiert Performance (laufender Handel = 0 LLM-Token).

- **Projektpfad:** `C:\Dizzik\code\Trading Bot eins\programm`
- **Plattform:** Windows · Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312`)
- **Dashboard:** `http://127.0.0.1:8137` (Desktop-Icon „Trading Bot Trial" oder `scripts/launch.ps1`)
- **Modus:** Demo/Paper (`TBT_DRY_RUN=true`) — **kein echtes Geld**. Bitget-Key ist read-only.

## 2. Aktueller Stand (06.06.2026)
Fertig: **M0–M5 + UI v3.1 + Futures-Betrieb + Live-Recherche-Tool.**
- **5 Demo-Bots laufen** (dry-run, 5m): 2 Spot (`Auto-MeanRev-Demo` 9b453b57,
  `Auto-Momentum-Demo` 06ec195c) + 3 Futures Hebel 3× (`Fut-MacdRsi-Demo` 1a1fc5c3,
  `Fut-Breakout-Demo` 4c39d958, `Fut-BBands-Demo` 32ffc3af).
- **6 lauffähige Strategien**: 3 Spot (TrendFollowEma, MeanReversionRsi, MomentumMacd)
  + 3 Futures (FuturesMacdRsiScalp, FuturesBreakoutVol, FuturesBbandsBounce).
- **Recherche-Tool LIVE**: echte Web-Suche (Anthropic `web_search`), Futures-Fokus,
  Scope ≤ 1 Tag, Alters-Aussortierung; Quellen inkl. YouTube „Trading Strategie
  Analyse" + „Trading Strategy Testing".

## 3. Architektur (kurz)
```
Dashboard (backend/app/static/index.html)
   │  REST
FastAPI-Orchestrator (backend/app/main.py)
   ├─ registry.py   Bot-Verwaltung (data/bots.json) + Engine-Config-Generierung
   ├─ runner.py     startet/stoppt je Bot `python -m freqtrade trade` (dry-run)
   ├─ engine.py     Backtests (lädt Daten autom.)
   ├─ stats.py      Statistik-DB (data/stats.sqlite) + Trades/Equity aus Trade-DBs
   ├─ risk.py       Limits/Kill-Switch
   ├─ ai.py         Krypto-Strategie-Katalog (Web-Recherche) + Performance-Analyse + Chat
   ├─ exchange.py   Bitget-Salden via CCXT (read-only)
   ├─ transfer.py   Transfers mit Pflicht-Bestätigung
   └─ audit.py      Audit-Log (data/audit.log)
        │ je Bot 1 Prozess
   Freqtrade (engine/.venv) ── CCXT ──► Bitget (Spot + Futures)
```

## 4. Projektstruktur (wichtigste Dateien)
```
trading-bot-trial/
├─ README.md                 Überblick + Status
├─ requirements.txt          Backend-Abhängigkeiten
├─ .env / .env.example       Secrets (Bitget read-only, ANTHROPIC_API_KEY, Limits)
├─ backend/app/              Orchestrator (siehe Architektur oben) + static/index.html (Dashboard)
├─ engine/                   Freqtrade (eigene .venv)
│   ├─ README.md             Engine-Bedienung (Backtest/Dry-Run)
│   ├─ read_backtest_stats.py
│   └─ user_data/
│       ├─ config_<botid>.json     auto-generierte Bot-Configs
│       ├─ config_bot1_dryrun.json Vorlage
│       └─ strategies/*.py         Strategie-Vorlagen (3 Spot + 3 Futures + samples)
├─ data/                     bots.json, stats.sqlite, strategy_catalog.json,
│                            research_sources.json, research_config.json, runners.json, audit.log
├─ scripts/                  launch.ps1, create_desktop_shortcut.ps1, check_setup.py,
│                            check_env_lines.py, overnight_report.ps1
└─ docs/                     siehe unten
```

## 5. Wichtigste Dokumente (in dieser Reihenfolge lesen)
1. **docs/START_HERE.md** — dieses Dokument.
2. **docs/HANDOFF.md** — detaillierter Stand, Bugfixes, bekannte Einschränkungen,
   priorisierte Restliste. **Maßgebliche Quelle.**
3. **docs/RESEARCH_TOOL.md** — Konzept des Krypto-Recherche-Tools (Schema, Scope,
   Futures, Sessions, Quellen, Alters-Logik).
4. **docs/ARCHITECTURE.md** — Architektur + Roadmap (M0–M7).
5. **docs/BEDIENUNG.md** — Bot im Demo-Modus bedienen.
6. **docs/SETUP_USER.md** — manuelle Nutzer-Schritte (Keys/.env).
7. **docs/LEGAL.md** — Recht/Steuer DE (BaFin, §23 EStG, DAC8).
- Mem-Collection **„Projekt BotT"**: Notiz „Übersicht (Schnellblick)" + „Zusammenfassung".

## 6. App starten / bedienen
```powershell
# Dashboard starten (Desktop-Icon „Trading Bot Trial" oder:)
.\scripts\launch.ps1                      # öffnet http://127.0.0.1:8137
# Manuell:
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8137
```
Bot anlegen → Strategie wählen (Markt Spot/Futures wird automatisch gesetzt) →
Start/Stop/Logs/Backtest/Details im Dashboard. Engine-Befehle: `engine/README.md`.

## 7. Nächste Schritte (priorisiert)
- ✅ **(erledigt 06.06.2026)** Statistik-Übersicht nach Futures/Spot getrennt
  (`/api/summary` mit `trading_mode`/`leverage` + `groups`).
- ✅ **(erledigt 06.06.2026)** Status-Erkennung robuster: Bots per `config_<id>.json`
  in der Prozess-Kommandozeile (CIM) erkannt → korrekt auch nach uvicorn-Neustart.
- ✅ **(erledigt 06.06.2026, UI v4)** Kategorisiertes Parameter-Modell
  (`category`/`optional`, nur relevante Parameter), echte Param-Specs für die
  6 lauffähigen Strategien + Vorschau beim Anlegen; **Inline-Aufklapp-UI** (Strategie-
  & Bot-Details unter der Zeile statt rechtem Drawer); **Backtest-Button entfernt**;
  **Design-Overhaul** (Dark Glassmorphism, violett-neon, matt/weich). Details: `docs/HANDOFF.md`.
0. ⏳ **GROSSE v5-Wunschliste + offene Fragen liegen in `docs/HANDOFF.md` (Abschnitt
   „v5 …"). WARTET AUF NUTZER-„LOS".** Erst Fragen klären, dann Gesamtsystem neu
   durchdenken (Daten/Lernen ist der Nordstern), dann meilensteinweise bauen.
1. **Katalog-Refresh** (mit API-Key) → AI-Systeme erhalten kategorisierte Parameter.
2. **Tiefere Recherche**, die zwei YouTube-Kanäle stärker gewichten.
3. **Weitere Engine-Vorlagen** für recherchierte (Futures-)Systeme.
4. Später **M6** (Echtgeld klein + Bitget-Subaccounts + Steuer-Export), dann **M7** (Docker/Server).

## 8. Bekannte Einschränkungen / Hinweise
- **Prozesse:** venv-`python.exe` ist ein Starter → **2 OS-Prozesse pro Bot** (5 Bots = 10 normal).
- **Status nach Server-Neustart**: jetzt robust — Bots werden per Kommandozeile
  (`config_<id>.json`, CIM) erkannt, nicht mehr nur per PID (Fix vom 06.06.2026).
- ⚠️ **uvicorn immer mit der Projekt-`.venv` starten** (`scripts/launch.ps1` tut das).
  Basis-Python312 hat **kein** FastAPI → `ModuleNotFoundError`.
- Manuell erstellte Bots übernehmen Markt/TF aus Strategie (Fix erfolgt); ältere Test-Bots evtl. löschen.
- ⚠️ **Sicherheit:** Es liegt ein Klartext-Key unter `1 API Key/david-api-key1.txt`.
  Der Key gehört **nur** in `.env`. Datei am besten **löschen** (ist jetzt in `.gitignore`).

## 9. Vorschlag: erster Prompt im neuen Chat
> „Lies `docs/START_HERE.md` und `docs/HANDOFF.md` im Projekt
> `…\Code Projekte\trading-bot-trial` sowie die Mem-Collection ‚Projekt BotT'.
> Die 5 Demo-Bots sollen weiterlaufen. Mach weiter mit: **[gewünschter Schritt
> aus Abschnitt 7]**. Budget bitte im Blick behalten."
