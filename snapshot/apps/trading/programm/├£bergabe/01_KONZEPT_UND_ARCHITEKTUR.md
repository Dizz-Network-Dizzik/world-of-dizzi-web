# Konzept & Architektur — Dizz Trading

## 1. Grundkonzept (die Vision)
- **Hybrid:** Freqtrade (deterministisch) **handelt**; eine KI/Meta-Schicht **plant, bewertet & lernt**
  (Recherche, Regime-Erkennung, Parameter-/Strategie-Optimierung, Ensemble-Politik). Laufender Handel
  kostet **0 LLM-Token**.
- **Nur Krypto (Bitget)**, Kurzfrist-Fokus (Scalping/Intraday, Futures long+short).
- **Sicherheit zuerst:** harte Limits je Bot, Portfolio-Risiko-Governor darüber, mehrstufige Gates
  vor Echtgeld — alles erst Demo/Paper (`dry_run`).
- **Nordstern:** ein **selbst-verfeinernder Meta-Algorithmus**, der aus eigener Bot-Performance **und**
  Marktbeobachtung (Regime) **und** einem markt-neutralen Sockel lernt, welche Edge-Quelle wann trägt —
  und das laufend verbessert. Echtgeld nur per ausdrücklicher Freigabe (`docs/RUNBOOK_ECHTGELD.md`).

## 2. Ort & Struktur (Monorepo)
Seit 24.06.2026 lebt alles im Monorepo `dizz-network` (`apps/trading`). Der TB hat einen **eigenen
Stack** (kein appkit-`create_app`): echter Code + Doku in `programm/`.
```
apps/trading/
├── CLAUDE.md                 App-Regeln (Geld-System, read-only für andere Chats)
└── programm/
    ├── backend/app/          Orchestrator (FastAPI) — 40 Module (s. u.)
    │   └── static/index.html Dashboard (Single-File HTML/CSS/JS, vom Backend ausgeliefert)
    ├── engine/
    │   ├── .venv/            Freqtrade-venv (eigener Interpreter)
    │   └── user_data/
    │       ├── strategies/*.py   18 Strategie-„Engines" + tbt_common.py + sample
    │       ├── config_<id>.json  auto-generierte Bot-Configs
    │       └── tradesv3_<id>.sqlite  Trade-DBs je Bot
    ├── data/                 bots.json, stats.sqlite, *.json (State je Subsystem), audit.log
    ├── docs/                 echte TB-Doku (START_HERE/HANDOFF sind historisch, s. Übergabe)
    ├── Übergabe/             dieser Einstieg
    ├── scripts/              launch.ps1, backup_kern.py, night_train.py, …
    └── tests/                50+ Dateien, 474 Tests (TBT_NO_STARTUP=1)
```

## 3. Backend-Module (`backend/app/`, 40) — nach Rolle
**Kern/Orchestrierung**
- `main.py` — FastAPI, ~110 Endpunkte; Konstanten `IMPLEMENTED_STRATEGIES` (18), `STRATEGY_PARAMS`,
  `PARAMETRIZABLE_STRATEGIES`; Autopilot-Tick `_autopilot_step`.
- `registry.py` — Bot-CRUD (`data/bots.json`) + Engine-Config-Generierung.
- `runner.py` — start/stop je Bot (`freqtrade trade`-Subprozess), Status-Erkennung per Kommandozeile,
  injiziert Env-Brücken (`TBT_REGIME_FILE`, **`TBT_SIZING_FILE`/`TBT_BOT_ID`**, **`TBT_POLICY_FILE`**, `TBT_OPT_PARAMS`).
- `engine.py` — Backtests + Walk-Forward (Param-Injektion via Env). `stats.py` — SQLite `stats.sqlite`
  (backtest_runs · snapshots · market_snapshots · strategy_validations · optimizations · bot_upgrades)
  + read-only Trade-DB-Leser (Equity/Trades/Expectancy). `tracker.py` — schreibt Snapshots + die
  **Regime-Bridge** `hmm_regime.json`.

**Lern-Ebenen** (Detail: `02_LERNSYSTEM`)
- `meta.py` — Lerner Stufe 1 (Aggregation, Vorschläge, `run_optimization`/Walk-Forward, Konsistenz-Gate,
  Regime-/Session-Empfehlung). `master.py` — Ensemble Stufe 2 (regime-gerichtete Strategien + MN-Sockel,
  gewichtet nach OOS-Edge). `hmm.py` — Gaussian-HMM (Baum-Welch/Viterbi) Regime-Erkennung.
  `autopilot.py` — Hintergrund-Loop (Default 6 h).
- Markt-neutraler Sockel (simuliert, 0 Risiko): `csm.py` (Cross-Sectional-Momentum), `pairs.py`
  (Pairs + StatArb), `marketmaking.py` (Avellaneda-Stoikov), `mn_base.py` (geteilte Basis),
  `mn_learn.py` (Anchored-Walk-Forward-Optimierer), `mn_paper.py` (persistente Paper-Bot-Instanzen).

**Risiko & Allokation**
- `governor.py` — Portfolio-Risk-Governor (aggregierter Drawdown/Tagesverlust/Anomalie → alert/derisk/pause;
  schützt Echtgeld + MasterMeta). `concentration.py` — Korrelations-/Klumpen-Analyse (HHI, Asset-/Cluster-Caps).
- `sizing.py` — Vol-Targeting + **fraktionaler Kelly** + **Portfolio-Klemmkette K4–K6** + **Sizing-Bridge**
  `suggested_sizing.json` (FP-2, `docs/KELLY_SIZING_SPEC.md`). `execution.py` — Slippage/Gebühren-Tracking
  (M6-Vorbereitung). `universe.py` — kuratiertes Coin-Universum. `fundamental.py` — Event-Kalender/Makro-Overlay.
  `risk.py` — harte Limits/Kill-Switch-Bewertung. `cull.py` — Auto-Culling chronisch schlechter Demo-Bots.

**Infrastruktur/Anbindung**
- `ai.py` — KI-Strategie-Katalog + Web-Recherche + Scoring (proposal-only). `exchange.py` — Bitget/ccxt
  (read-only). `transfer.py` — Transfers (echte bewusst blockiert). `audit.py` — Append-only-Audit-Log.
- `jsonstore.py` — atomares, resilientes JSON-IO. `cache.py` — TTL-Memo. `sessions.py` — Börsen-Sessions.
  `alerts.py` · `maintenance.py` · `report.py` · `introspect.py`/`integration.py`/`mcp_tools.py`/`vertrag.py`
  (Telemetrie/Netz-Anbindung/Pfade).

## 4. Prozess-Realität
- venv-`python.exe` ist ein Redirector → **2 OS-Prozesse pro Bot** (Backend-Starter + Freqtrade-Worker-Kind).
  50 Bots ≈ 100 Prozesse. Benannt: Backend `DizzTrading-Server.exe`, Bots `DizzTrading-Bot.exe`.
- Backend läuft **ohne** `--reload` → `.py`-Änderung wirkt erst nach `:8137`-Neustart (gegated).
  Frontend (`index.html`) wird pro Request frisch ausgeliefert → nur Seite neu laden.

## 5. Datenfluss (Gehirn → Hand, venv-übergreifend)
Backend und Freqtrade-Engine laufen in **getrennten venvs/Prozessen** und sprechen über **Bridge-Dateien**:
- **`hmm_regime.json`** (`tracker.write_regime_bridge` → `master_meta.py`): Live-Regime + HMM-Konfidenz +
  Event-`lev_scale` + Vol-Targeting-`exposure_scale` → steuert Sub-Logik + Hebel der MasterMeta-Engine.
- **`suggested_sizing.json`** (`sizing.write_bridge_auto` → `master_meta.custom_stake_amount`, FP-2):
  geklemmter Stake-Plan → **opt-in**, proposal-Default, nur `dry_run`. Ohne Opt-in byte-identisch.
- **`suggested_policy.json`** (`policy_bridge.write_bridge_auto` → `master_meta._policy_levers`, FP-T5,
  **Gate G-T5 offen**): Regime-Bestauswahl der Master-Politik → Sub-Logik-Wahl (L1) / Stake-Dämpfung ≤1
  (L2) / Edge-Gating (L3); Klemmkette Politik→Governor→Konzentration→Sizing. **Opt-in**, proposal-Default,
  nur `dry_run`, ohne Opt-in byte-identisch. SPEC: `docs/POLICY_HAND_SPEC.md`.
