# 🩺 Systemcheck & AI-Architektur (2026-06-09, HEAD `ee40cb7`)

Vollständige Bestandsaufnahme: Live-Status, AI-Struktur-Grafik (wo der MasterMeta-Bot sitzt), alle
Connections (Frontend↔Backend, intra-Backend, AI↔AI, venv-übergreifend), Sicherheits-/Lern-Mechaniken,
Review-Befunde. 0 Echtgeld (Demo/Paper).

## 1. Live-Status
| Check | Wert |
|---|---|
| Bots | **51/51 running** (45 Futures inkl. 16 Eröffnung · 6 Spot · + MasterMeta) |
| Tests | **181 pytest grün** · 30 Backend-Module · 83 REST-Routen · 24 Test-Dateien |
| Engine | verfügbar (freqtrade dry-run, futures `defaultType: swap`) |
| AI-Modul | konfiguriert (Anthropic-Key, nur fürs Recherchetool) |
| MasterMeta | Futures · Hebel dyn. 5–10× (je HMM-Konfidenz, event-gedrosselt) · Long+Short · Autopilot lebt |
| Sicherheit | Notfall-Stop `stoploss_on_exchange` in **jeder** Config (überlebt Systemausfall) |
| Last | ~104 python-Prozesse, ~38 GB RAM frei |
| Git | clean (HEAD `ee40cb7`); Backup-Repo synchron |

## 2. AI-System — systematische Grafik (Schichtenmodell)

```
                              ┌────────────────────────────────────────────┐
                              │  FRONTEND (index.html, served-fresh)        │
                              │  KI-Tool-Panels · Statistik · Bot-Verwaltung │
                              └───────────────┬─────────────────────────────┘
                                   83 REST-Routen (/api/…)  HTTP 127.0.0.1:8137
                              ┌───────────────┴─────────────────────────────┐
                              │  BACKEND  (FastAPI, main.py = Orchestrator)  │
                              └───────────────┬─────────────────────────────┘
   SCHICHT 0 · DATEN ────────────────────────┼─────────────────────────────────────────
   ccxt/Bitget(1h)  FRED(Makro)  blockchain.com(On-Chain)  Deribit(DVOL)  Kalender(Events)
   SCHICHT 1 · WAHRNEHMUNG ──────────────────┼─────────────────────────────────────────
     hmm.py ──► tracker.decode_regime ──► Regime + Konfidenz   ┐
     fundamental.py ─► Event-Risiko · Makro · On-Chain · DVOL  ┘ (defensiver Overlay)
   SCHICHT 2 · EDGE-QUELLEN (Sub-AIs) ───────┼─────────────────────────────────────────
     meta.py  Einzelstrategie-Optimierer (Walk-Forward/Evolution) · ai.py Recherchetool (Metrik-Kanon)
     csm.py · pairs.py (+StatArb) · marketmaking.py  ── markt-neutrale Sim-Engines (mn_base/mn_learn)
   SCHICHT 3 · MASTER-ENSEMBLE ──────────────┼─────────────────────────────────────────
     master.py  verdichtet ALLE Edges → gerichtet + markt-neutraler Sockel; regime-konditioniert (HMM),
                fundamental-gedämpft, OOS-gehärtet (PSR/Deflated-Sharpe/Kappung/Soft-Voting)
   SCHICHT 4 · AUSFÜHRUNG + LIFECYCLE ───────┼─────────────────────────────────────────
     runner.py ─► 51 freqtrade-Subprozesse (eigene venv, Trade-DB, Notfall-Stop on-exchange)
     autopilot.py ─► periodischer Tick: MasterMeta-Verbesserung + cull.py (Auto-Aussortierung)
        ┌─────────────────────────────────────────────────────────────────────┐
        │  ★ MasterMeta-BOT (id=mastermeta) — HIER SITZT DER BOT               │
        │  Die EINZIGE Strategie, die die Meta-Idee als eigener Live-Bot fährt.│
        │  • liest Live-HMM/Fundamental über die Bridge-Datei (venv-übergreif.)│
        │  • aggressiv: Futures, Hebel 5→10× nach Konfidenz, Long+Short        │
        │  • autopilot verbessert ihn (nur OOS-validiert) + cullt schlechte Bots│
        └─────────────────────────────────────────────────────────────────────┘
```

**Verortung:** Der MasterMeta-Bot lebt in Schicht 4 (Ausführung), wird aber von allen darüberliegenden
AIs gespeist — die ausführende Verkörperung der Meta-Ebene (Regime+Hebel aus HMM, Politik aus Master,
Drosselung aus Fundamental, Lernen aus den Peer-Optimierungen).

## 3. Connections
### 3a. Frontend ↔ Backend (HTTP, 83 Routen, served-fresh)
Panels↔Endpoints: `loadMasterMeta→/api/mastermeta` · `loadMaster→/api/master` · `loadCsm/Pairs/Statarb/Mm`
· `loadMeta→/api/meta` · `loadCull→/api/cull` · `loadUpgrades→/api/upgrades` · `masterMetaPerf→/api/mastermeta`.

### 3b. Intra-Backend (Modul-Abhängigkeiten, geprüft — keine Waisen, keine ungenutzten Importe)
```
master.py ──► meta · csm · pairs · marketmaking · fundamental · mn_base   (Ensemble-Hub)
main._autopilot_step ──► _mastermeta_improve (consults master·tracker·fundamental·meta·stats) + cull.run_once
cull.py ──► meta(consistency) · stats(bot_pnl) · registry(delete_bot) · runner(stop)
tracker.py ──► hmm · mn_base · fundamental(lazy) ;  runner.py ──► tracker(lazy, Bridge)
registry/runner/autopilot/cull ──► jsonstore (atomar+resilient) ;  registry-Mutatoren unter RLock
```

### 3c. Venv-übergreifend (Backend ↔ Engine) — die EINZIGEN Brücken
1. `config_<id>.json` (Backend→Engine) inkl. **`order_types` Notfall-Stop** (`stoploss_on_exchange`).
2. `tradesv3_<id>.sqlite` (Engine→Backend) — Trades/Equity.
3. Env `TBT_OPT_PARAMS` — gelernte Parameter (inkl. base/max_leverage, Session).
4. Env `TBT_REGIME_FILE` + `data/hmm_regime.json` — **HMM-/Fundamental-Bridge** (Regime·Konfidenz·
   event_risk·lev_scale) → steuert Hebel/Regime des MasterMeta live.

### 3d. AI ↔ AI
- **Master ◄ alle Edges** (meta-Ranking + 4 MN-Engines), regime-konditioniert, fundamental-gedämpft.
- **MasterMeta-Bot ◄ Sub-AIs** (`_mastermeta_consult`: HMM/Master/Fundamental + Peer-Optimierungen).
- **Autopilot ►** OOS-validierte Gewinner anwenden → `master.train_step`; **Cull ►** schlechte Demo-Bots
  verwerfen (Learnings bleiben).

## 4. Sicherheits- & Lifecycle-Mechaniken (neu)
- **Notfall-Stop:** `registry._write_engine_config` setzt `order_types` mit `stoploss_on_exchange=true`
  (stop=market, interval 60) → echter Börsen-Stop, überlebt Strom-/Systemausfall. Pro Bot per
  Laufzeit-Log (`Strategy using order_types`) verifizierbar; auf allen 51 Bots aktiv.
- **Auto-Cull (`cull.py`):** verwirft chronisch schlechte **Demo**-Bots automatisch (Selbst-Bewertung via
  `meta.consistency`+`bot_pnl`). KONSERVATIV — nur wenn ALLES zutrifft: ≥5 T Historie ∧ ≥20 Trades ∧
  Ø≤−15 % ∧ Trend≤−1 %/T. MasterMeta + Echtgeld immer geschützt. Im Autopilot-Tick (debounced 12 h).
- **Lern-DB-Garantie:** `delete_bot`/Cull fassen `stats.sqlite` + Trade-DB NIE an → Wissen bleibt.
- **Persistenz:** `jsonstore.py` (tmp+os.replace +`.bak`, resilient) für bots.json/runners.json/
  autopilot.json/cull.json → crash-/OneDrive-Sync-fest; `registry`-Mutatoren + `runner.start/stop` thread-safe.

## 5. Review-Befunde dieser Runde
- ✅ **FIX:** MasterMeta (vor dem Notfall-Stop-Feature angelegt) hatte `order_types:None` = keinen
  Notfall-Stop — ausgerechnet der Bot mit dem höchsten Hebel. Live gefixt + `ensure_master_bot` schreibt
  die Config jetzt **idempotent immer** auf den aktuellen Standard (kann nie wieder fehlen).
- ✅ Cull-Ausführungspfad live getestet (force: 51 geprüft, 0 verworfen — korrekt bei frischer Flotte).
- ✅ AST-Scan: keine ungenutzten Importe; alle 30 Module kompilieren; keine Waisen-Module.
- 🟡 Watch: 51 Bots ≈ ~104 Prozesse → Commit-/Pagefile-Limit beobachten (0x800705af trat einmal auf).

## 6. Fazit
Architektur sauber geschichtet, Kopplungen minimal & explizit, neue Sicherheits-/Lifecycle-Module greifen
(verifiziert). Funktionalität ✓ · Effizienz ✓ (PID-Cache, Debounce, lazy Imports, DRY, atomare Writes) ·
Flexibilität ✓ (alles tunbar/abschaltbar). **181 Tests grün, 51/51 live, live == source.**
