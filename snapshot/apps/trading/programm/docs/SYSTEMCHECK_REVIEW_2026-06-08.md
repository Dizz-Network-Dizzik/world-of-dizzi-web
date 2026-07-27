# Systemcheck · Tiefen-Review · Handoff (2026-06-08)

Großer Systemcheck + Architektur-Review (Fokus KI/Lern-Schicht) am Ende einer sehr großen
Session. Ergebnis: **System gesund, Code professionell** → Backup angelegt; nächste Session
startet mit **Option A** (Master-Ensemble / 3. Lern-Ebene).

## 1. Systemcheck — alles grün
- **Tests:** 71 pytest grün (15 Test-Dateien, reine Logik gut abgedeckt).
- **Live:** :8137 **30/30** Bots running (25 Demo-Scalper + 5 Eröffnungs-Bots).
- **Git:** sauber, HEAD `3272281`, 84 Commits. Nur Code/Docs getrackt.
- **Security/Hygiene:** `.gitignore` deckt `.env`/`*.key`/`1 API Key/`/`data/`/`*.sqlite`/`*.log`/
  venvs ab; der API-Key-File ist **leer (0 B) + ignored** → **keine Secrets/Daten im Repo**.
- **Cruft (nur in gitignored `data/`):** alte `uvicorn_*.log` + zwei `strategy_catalog.json.*.bak`
  → aufgeräumt (funktional irrelevant).

## 2. Code-Struktur — professionell
- Backend 6104 Zeilen / 24 Module mit klarer Verantwortung + Docstrings. Größte: `main.py`
  (1180, alle Routen), `ai.py` (998, Recherche/Katalog), `meta.py` (628, Lern-Aggregation),
  `stats.py` (469), `pairs.py` (430), `csm.py` (344), `marketmaking.py` (238).
- Engine: 11 Freqtrade-Strategien (inkl. neu SessionOpenBreakout/GridRange/DcaDip).
- Frontend: 1 SPA `index.html` (2420 Z., bewusst build-frei).
- **Lern-Schicht (Status):**
  - **per-Strategie:** `meta.run_optimization`/`run_evolution` (Walk-Forward, Multi-Objective-
    Score, Selektions-Bias/Deflated-Sharpe-Hygiene) — proposal-only.
  - **Markt-neutral (4 Sim-Engines):** CSM/Pairs/StatArb/MarketMaking, je `optimize()` über
    `mn_learn` (Walk-Forward, bester Ø-Sharpe). 0-Risiko, self-tuning.
  - **Master (`master.py`):** verdichtet validierte Strategie-Erkenntnisse zu einer versionierten
    Regime→Strategie/Parameter-Politik, Fitness-selbstbewertend (behält nur bessere Version).

## 3. Verbesserungs-Findings (priorisiert) — Recherche-gestützt
Recherche (Ensemble/Meta-Learning für Trading) bestätigt die Richtung: mehrstufiges Ensemble
(Base-Learner → Aggregation → Meta-Learner) + Regime-Switching + dynamische Modell-Selektion.

1. **[GROSS · Option A] Master ingestiert die MN-Engines NICHT.** CSM/Pairs/StatArb/MM sind
   starke, OOS-getunte, **markt-neutrale** Edge-Quellen — der Master allokiert aber nur über
   `STRAT_REGIME` (Freqtrade). → Master zu einem **Ensemble über ALLE Edge-Quellen** ausbauen:
   gerichtete Strategien (regime-abhängig) **+** markt-neutrale Engines (regime-UNabhängig,
   als stabiler Sockel). Gewichtung nach jüngster OOS-Performance/Sharpe + Konfidenz. Das ist
   der Kern Richtung „krassester Bot": ein selbst-zusammengesetzter Meta-Algorithmus.
2. **[MITTEL · DRY] MN-Engines duplizieren Boilerplate.** `get_config/set_config` (über
   `csm._meta_get/_set`), `get_state/status`-Gerüst, Equity-Ausdünnung, Stats (sharpe/ann/maxdd)
   sind 3–4× kopiert. → `mn_base.py` extrahieren (config-Helfer + `equity_stats(returns,equity)`
   + downsample). Spart ~150 Zeilen, eine Quelle der Wahrheit, leichter erweiterbar.
3. **[MITTEL] Regime-Erkennung naiv** (`tracker.market_snapshot`: Preis vs. SMA20).
   → Volatilitäts-Regime ergänzen + optional ein leichtgewichtiges HMM/Schwellen-Modell
   (Recherche: HMM+Ensemble für Regime-Shift). Verbessert die Master-Allokation direkt.
4. **[KLEIN] `main.py` (1180 Z.)** → optional in APIRouter gruppieren (bots/meta/mn/research)
   für Navigierbarkeit. Kein Muss (single-file = leicht auffindbar, Nutzer-Wunsch „flexibel").
5. **[KLEIN] Master-Trainingsschritt automatisieren** (z. B. nach jedem Lern-Loop einen
   `master.train_step` triggern), damit die Politik mit der Evidenz mitwächst.

## 4. NÄCHSTE SESSION — Agenda (Option A zuerst)
**Ziel:** Master = selbst-verfeinernder **Meta-/Ensemble-Algorithmus über alle Edge-Quellen**,
der effizient Verbesserungen einsammelt → langfristig „der krasseste Bot".

Schritte (in dieser Reihenfolge):
1. **`mn_base.py` DRY-Refactor** der 4 MN-Engines (Finding 2) — saubere Basis, dann:
2. **Master ingestiert MN-Engines** (Finding 1): `master.derive_policy` erweitern um die
   MN-Edges (Sharpe+Konfidenz aus `csm/pairs/marketmaking.status()` + StatArb); Ensemble-
   Politik = {regime-gerichtete Strategie(n)} + {markt-neutraler Sockel gewichtet n. Sharpe}.
   Fitness um die MN-Beiträge erweitern; `master.status()`/Frontend-Panel zeigen das Ensemble.
3. **Auto-`train_step`** nach Lern-Loops (Finding 5) + Fitness-Verlauf sichtbar.
4. **Regime-Erkennung** verbessern (Finding 3) — speist die Allokation.
5. Danach iterativ: bessere Gewichtungs-/Meta-Learner-Logik (Recherche: Stacking/Soft-Voting/
   dynamische Gewichte), mehr OOS-Härtung.

## 5. Backup & Wiedereinstieg
- **Backup:** `Trading Bot eins` → **`Trading Bot Backup`** (eingefrorener Snapshot inkl. git).
- **Live unberührt:** :8137 läuft aus `trading-bot-trial` (eigene venvs) — vom Rename NICHT betroffen.
- **Nächste Session — Kopierbefehl** (Working-Copy aus dem Backup herstellen), dann Option A starten:
  ```powershell
  Copy-Item "%USERPROFILE%\OneDrive\Code Projekte\Trading Bot Backup" `
            "%USERPROFILE%\OneDrive\Code Projekte\Trading Bot eins" -Recurse
  ```
- **Workflow bleibt:** editieren in `…\Trading Bot eins\programm` → cp nach `…\trading-bot-trial`
  → :8137-Neustart (trial-venv-Python, Port-Owner via `Get-NetTCPConnection -LocalPort 8137`,
  ohne --reload) → committen. 30/30 + Tests grün halten. Details: [[trading-bot-eins-gotchas]].
