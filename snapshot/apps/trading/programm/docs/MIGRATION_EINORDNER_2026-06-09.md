# 🔧 Migrationsplan: ein Arbeitsordner + ein Backup (mit Rollback)

Ziel: den Kopier-/Deploy-Schritt `programm → trial` ganz abschaffen → Live-Betrieb direkt aus
`Trading Bot eins\programm`, `trading-bot-trial` stilllegen, `Trading Bot Backup` als einziges Backup.
**Status: VORBEREITET — Ausführung gemeinsam/überwacht** (einziger Schritt mit echtem Live-Blast-Radius).

## Warum überwacht (Risiken, ehrlich)
- venv-Neubau (freqtrade/**TA-Lib** auf Windows) kann zicken.
- 30 laufende Bot-Prozesse + ihre `tradesv3_<id>.sqlite` müssen sauber mitgenommen werden (sonst
  Historie-Verlust). Während der Umstellung ist das System kurz „unten" (bei Demo unkritisch).
- `config.DATA_DIR = parents[2]` → läuft der Backend aus `programm`, nutzt er **`programm\data`**;
  die Live-Daten liegen aber in `trial\data` → **müssen vorher kopiert werden**, sonst sieht die API
  die Bots nicht. (Genau deshalb kein Teil-Umzug nur des Backends.)

## Safety-First-Schritte (in dieser Reihenfolge)
1. **Frisches Voll-Backup** der Live-Daten: `trial\data` + alle `engine\user_data\tradesv3_*.sqlite` +
   `config_*.json` → datierter Ordner in `Trading Bot Backup` (zusätzlich zum Code-Snapshot). Verifizieren.
2. **venvs in `programm` bereitstellen:** entweder neu anlegen (Backend- + Engine-venv, wie in trial)
   ODER — pragmatisch — die trial-venvs per Interpreter-Pfad weiternutzen, bis ein sauberer Neubau steht.
3. **Live-Daten kopieren:** `trial\data` → `programm\data`; `tradesv3_*.sqlite` + `config_*.json` an die
   programm-Engine-Pfade (Pfade in den Configs auf `programm` umschreiben).
4. **Ein Bot als Kanary:** EINEN Demo-Bot aus `programm` starten, 5–10 Min beobachten (Trades/DB-Schreiben
   ok?). Erst dann die restlichen 29.
5. **:8137 aus `programm`** starten (Backend-venv, cwd=programm). `/api/summary` muss 30/30 zeigen,
   `equity`/Trades der Bots müssen weiterlaufen.
6. **trial einfrieren:** alte uvicorn/Bots in trial stoppen, `trading-bot-trial` als Archiv kennzeichnen
   (nicht löschen). `.bak`/`_backup_*`-Ballast dort aufräumen.
7. **Workflow-Doku aktualisieren** (kein cp-Schritt mehr; Quelle = Live = `programm`).

## Rollback (falls etwas hakt)
- Jeder Schritt ist reversibel: solange trial nicht gelöscht ist, einfach **trial wieder als Live**
  starten (alte Prozedur) — Daten dort sind unberührt, bis Schritt 6.
- Das frische Voll-Backup (Schritt 1) erlaubt jederzeit Wiederherstellung der Live-Daten.
- Kein Schritt überschreibt Originale destruktiv vor der Kanary-Bestätigung (Schritt 4).

## Präzise Erkenntnisse (runner.py) — was der Flip GENAU braucht
- `runner.py`: `ENGINE_DIR = PROJECT_ROOT/engine`, `PYTHON_EXE = ENGINE_DIR/.venv/Scripts/python.exe`,
  Bots starten als `Popen([PYTHON_EXE, -m freqtrade trade ... config_<id>.json], cwd=ENGINE_DIR)`.
  → Läuft der Backend aus `programm`, sucht der Runner zwingend **`programm/engine/.venv`** (existiert NICHT)
  und **`programm/engine/user_data`** (Configs/Trade-DBs). Beides muss vor dem Flip in `programm` liegen.
- **Konkret nötig:** (1) `programm/engine/.venv` bereitstellen — entweder Verzeichnis-**Junction** auf
  `trial/engine/.venv` (`mklink /J`, kein TA-Lib-Neubau, schnell/risikoarm) ODER sauberer Neubau;
  (2) `programm/engine/user_data` mit den 60 `tradesv3_*.sqlite` + 33 `config_*.json` befüllen;
  (3) `programm/.venv` (Backend) analog (Junction) oder uvicorn mit trial-Interpreter + cwd=programm;
  (4) `programm/data` mit der Backend-Lern-/Markt-DB befüllen.
- **Empfohlene risikoarme Variante:** venvs per **Junction** wiederverwenden (kein Neubau), Daten kopieren,
  Kanary-Bot, dann Rest. Voll reversibel (Junction löschen → alter Zustand).
- **Status Schritt 1 (Live-Daten-Backup) ✅ erledigt:** `Trading Bot Backup/live_data_2026-06-09`
  (60 Trade-DBs + 33 Configs + Backend-data).

## Übergang bis dahin
Bis zur Migration killt das neue **`scripts/deploy.ps1`** die Drift-Fehlerklasse: es kopiert IMMER alle
Code-Dateien korrekt (ohne data) + Neustart + 30/30-Check — kein Hand-Kopieren mehr (das war die Ursache
des `ai.py`-Drifts). Nach jeder Backend-Änderung: `deploy.ps1` statt manuellem cp.

---

## ✅ ERLEDIGT 2026-06-09 — Ein-Ordner-Konsolidierung vollzogen
- venvs per **Junction** in programm (`.venv`, `engine\.venv` → trial) — kein TA-Lib-Neubau.
- Live-Daten nach programm kopiert: `data/` (Registry bots.json, stats-DB, catalog), 58 Configs, 60 Trade-DBs.
- Validierung: freqtrade läuft via Junction-venv aus programm; Config lädt aus programm-Pfad.
- **Flip:** 60 trial-freqtrade-Prozesse + uvicorn gestoppt → 30 Bots via runner aus programm gestartet
  (ok=30) → uvicorn aus programm → **30/30**, Master v6/Fitness 1.2912 aus migrierter stats-DB, engine_available.
- Verifiziert: 60 freqtrade-Prozesse aus PROGRAMM, 0 aus trial; Backend nutzt programm/data + programm/engine
  (PROJECT_ROOT aus __file__). 153 pytest grün aus programm.
- **trial eingefroren** (`_ARCHIVIERT_2026-06-09.txt`) = Rollback-Reserve. Per-Bot-Configs gitignored.
- **`scripts/deploy.ps1` ist jetzt OBSOLET** (kein programm→trial-Deploy mehr; Quelle = Live = programm).
  → Neustart künftig: uvicorn aus `programm` (Backend-venv-Junction), Bots via runner/Backend.

## Restbeobachtung
trial-`.bak`/`_backup_*`-Ballast kann gelöscht werden, sobald die Migration über Tage stabil ist (noch nicht).
