# 🧠 Trading Bot eins — KI-/Lern-System auf einen Blick (Stand 2026-06-08)

> Übersicht über **alles, was selbst lernt / sich selbst verbessert**. Demo/Paper, **0 echtes Risiko**,
> keine Orders — Echtgeld erst M6 mit ausdrücklicher Freigabe. HEAD `25f8b9d`, **103 pytest grün**, **30/30 Bots live** (:8137).

> **⏩ UPDATE 2026-06-10 (234 pytest, 51/51, HEAD `2638ced`):** Neue **Portfolio-Ebene P1–P5** (Risk-Governor ·
> Konzentration · Vola-Sizing · Slippage · Monitoring) + **Horizont-Modell** (Gruppierung systemweit
> Scalping/Intraday/Swing statt Spot/Futures; alle Bots Futures) + **Auto-Upgrade pro Bot** + großer UI-Umbau.
> Gesamtüberblick: **`PROJEKTSTAND_2026-06-10.md`**, Details: **`SYSTEMCHECK_2026-06-10.md`**.
>
> **⏩ UPDATE 2026-06-09 (HEAD `ee40cb7`, 181 pytest, 51/51):** Aktuellster Gesamtcheck inkl. Grafik &
> Connections jetzt in **`SYSTEMCHECK_2026-06-09.md`**. Neu seit diesem Dokument:
> **MasterMeta-Bot** (feste ID `mastermeta`, aggressiv Futures, dyn. Hebel 5–10×, Long+Short) +
> **`autopilot.py`** (selbst-verbessernder Tick alle 6 h, nur OOS-validierte Walk-Forward-Gewinner) ·
> **`cull.py`** (Auto-Aussortierung chronisch schlechter Demo-Bots, konservativ, Learnings bleiben) ·
> **Notfall-Stop** `stoploss_on_exchange` in jeder Bot-Config (überlebt Systemausfall) ·
> **Recherchetool-Metrik-Kanon** (`ai.compute_metrics`: PF/Calmar/Expectancy/Signifikanz, an Eigen-OOS
> gegroundet — Details `RECHERCHE_METRIKEN_2026-06-09.md`) · atomare/thread-sichere Persistenz (`jsonstore.py`).

---

## 0. Status auf einen Blick

| | Wert |
|---|---|
| Bots live (:8137) | **30/30** (25 Scalper + 5 Eröffnungs-Bots) |
| Tests | **103 grün** |
| Master-Politik | **v5** · Ensemble: gerichtet ~10 % / markt-neutraler Sockel ~90 % |
| Aktiver Sockel | CSM **40 %** + Market-Making **60 %** (Pairs/StatArb 0 %, da Sharpe ≤ 0) |
| Aktuelles Regime (HMM) | **Seitwärts (range)**, Konfidenz **97 %** → gerichtet bevorzugt FuturesBbandsBounce |

---

## 1. Die große Architektur — 3 Lern-Ebenen + 2 Querschnitte

```
                          ┌───────────────────────────────────────────────────────────┐
                          │   MARKT  (Bitget, read-only ccxt — Preise/Funding/Kerzen)   │
                          └───────────────┬───────────────────────────┬───────────────┘
                                          │                           │
            ┌─────────────────────────────┘                           └───────────────────────┐
            ▼                                                                                  ▼
┌───────────────────────────────┐   ┌────────────────────────────────┐   ╔═══════════════════════════════════╗
│  EBENE 1                       │   │  EBENE 2                       │   ║  QUERSCHNITT: REGIME-ERKENNUNG     ║
│  Per-Strategie-Lernen          │   │  Markt-neutrale Sim-Engines    │   ║  tracker.py + hmm.py               ║
│  meta.py                       │   │  csm · pairs · statarb · mm    │   ║                                   ║
│                                │   │  (mn_base.py + mn_learn.py)    │   ║  Gaussian-HMM (Baum-Welch+Viterbi)║
│ • Raster-Optim. (Walk-Forward) │   │                                │   ║  → trend_up / range / trend_down  ║
│ • Evolution (Mutation+Selekt.) │   │ • je Engine optimize()         │   ║  + Konfidenz + Persistenz         ║
│ • Multi-Objective + Deflated-  │   │   Walk-Forward (mn_learn)      │   ║  + Vola-Regime (calm/norm/turb.)  ║
│   Sharpe-Hygiene               │   │ • 0-Risiko-Simulation,         │   ╚═══════════════════╤═══════════════╝
│ • proposal-only                │   │   reines Python                │                       │ Regime + HMM-Konfidenz
└───────────────┬────────────────┘   └────────────────┬───────────────┘                       │
                │ strategy_validations                 │ status(): Sharpe/Ann/MaxDD            │
                │ + optimizations (PF, Konfidenz)       │ je Engine (OOS)                       │
                └───────────────────┬───────────────────┴───────────────────────────────────────┘
                                    ▼
                    ╔═══════════════════════════════════════════════════════════╗
                    ║  EBENE 3 — MASTER-ENSEMBLE  (master.py)                    ║
                    ║  „selbst-zusammengesetzter Meta-Algorithmus über ALLE      ║
                    ║   Edge-Quellen"                                            ║
                    ║                                                           ║
                    ║   ┌─ GERICHTETER SLEEVE ──────┐   ┌─ MARKT-NEUTR. SOCKEL ┐ ║
                    ║   │ beste Strategie je Regime  │   │ mn_sleeve():         │ ║
                    ║   │ regime-BEDINGT (HMM)       │   │ • nur positive Sharpe│ ║
                    ║   │ → aktuelles Regime         │   │ • OOS-Härtung        │ ║
                    ║   │   dominiert (blend=Konf.)  │   │   (Haircut+Shrink)   │ ║
                    ║   └────────────┬───────────────┘   │ • Konzentr.-Kappung  │ ║
                    ║                │                    │ • Soft-Voting        │ ║
                    ║                │  dynamischer Split └──────────┬───────────┘ ║
                    ║                └──── nach OOS-Edge ────────────┘             ║
                    ║   (gerichtet schwach → Sockel trägt mehr)                   ║
                    ║                                                           ║
                    ║   train_step(): bewerten → NUR bessere Version behalten    ║
                    ║   (versioniert, Fitness-Verlauf; Rebaseline b. Methodik-   ║
                    ║    Wechsel) — tunbar via Master-Config                     ║
                    ╚════════════════════════════╤══════════════════════════════╝
                                                 │ Ensemble-Politik (proposal-only)
                                                 ▼
                          ┌───────────────────────────────────────────┐
                          │  ANZEIGE / FREIGABE                        │
                          │  Frontend-Panel · /api/master · /api/regime│
                          │  → Mensch entscheidet (Echtgeld = M6)      │
                          └───────────────────────────────────────────┘

   ╔═ QUERSCHNITT: AUTO-TRAIN ════════════════════════════════════════════════════════════╗
   ║  Nach JEDEM Lern-Loop (meta optimize/evolve · MN set_config · master config)          ║
   ║  → _auto_train() ruft master.train_step() → Politik wächst automatisch mit der Evidenz║
   ╚═══════════════════════════════════════════════════════════════════════════════════════╝
```

**Lesart:** Markt → drei Edge-Quellen lernen unabhängig (Ebene 1 & 2) → der **Master (Ebene 3)** verdichtet
sie zu **einer** gewichteten Ensemble-Politik, konditioniert auf das aktuelle **Regime** (HMM-Querschnitt),
und verfeinert sich nach jedem Lern-Loop selbst (Auto-Train-Querschnitt). **Nichts handelt selbst** — die
Politik ist ein Vorschlag.

---

## 2. Die Bausteine im Detail

### Ebene 1 — Per-Strategie-Lernen (`meta.py`)
Lernt **die besten Parameter je Freqtrade-Strategie** aus echten Backtests.
```
   Kandidaten-Parameter ─► Walk-Forward-Backtest (mehrere OOS-Fenster, Embargo)
                           ─► Multi-Objective-Score (Profit·Konsistenz·DD)
                           ─► Anti-Overfit: Selektions-Bias-/Deflated-Sharpe-Hygiene
                           ─► Gewinner-Vorschlag (proposal-only) → strategy_validations + optimizations
```
| Funktion | Rolle |
|---|---|
| `optimize_proposals()` | Kandidaten-Parametersätze vorschlagen |
| `run_optimization()` | Raster real per Backtest/Walk-Forward prüfen, Gewinner küren |
| `run_evolution()` | Mutation → Walk-Forward → Multi-Objective-Selektion über Generationen |
| `report()` | Aggregation je Strategie + Daten-Reife + Synthese (`insights`) |

### Ebene 2 — Markt-neutrale Sim-Engines (`csm` · `pairs` · `statarb` · `marketmaking`)
Vier **eigenständige, richtungs-neutrale** Edge-Quellen (passen nicht in Freqtrades Per-Pair-Modell).
Gemeinsamer Sockel: **`mn_base.py`** (Config/Meta-Store/`equity_stats`/`downsample`), Lern-Loop: **`mn_learn.py`**.
```
   echte Tages-Closes (csm_prices) ─► simulate() (reines Python, lookahead-frei)
                                     ─► optimize(): Walk-Forward über N OOS-Fenster (bester Ø-Sharpe)
                                     ─► status(): Sharpe / Ann / MaxDD  ──► geht an den Master
```
| Engine | Edge |
|---|---|
| **CSM** | Cross-Sectional Momentum (long Top-/short Bottom-Quantil) |
| **Pairs** | Spread-Mean-Reversion korrelierter Paare (Z-Score) |
| **StatArb** | Korb-Reversion (jedes Symbol vs. Korb-Mittel) |
| **Market-Making** | Avellaneda-Stoikov (Spread + Inventar, Monte-Carlo) |

### Ebene 3 — Master-Ensemble (`master.py`)  ← Herzstück
```
   derive_policy():
     ┌ gerichtet:  beste Strategie je Regime, KONDITIONIERT aufs aktuelle HMM-Regime
     │             dir_fitness = blend·(aktuelles Regime) + (1-blend)·Mittel ,  blend = HMM-Konfidenz
     ├ Sockel:     mn_sleeve() = nur positive Sharpe, OOS-gehärtet (Haircut + Konfidenz-Shrink),
     │             Einzelgewicht gekappt (max_weight), optional Soft-Voting (Softmax)
     └ Split:      mn_share dynamisch nach OOS-Edge (PF-Währung)  →  ensemble_fitness
   train_step():  Politik bewerten → nur BESSERE Version behalten (versioniert, Fitness-Verlauf)
                  Ausnahme Rebaseline: bei Methodik-/Config-Wechsel neu kalibrieren
```
**Tunbar (Master-Config, `POST /api/master/config`):** `sharpe_haircut`, `conf_shrink`, `max_weight`,
`weight_temp`, `sharpe_to_pf`.

### Querschnitt — Regime-Erkennung (`tracker.py` + `hmm.py`)
```
   1h-Renditen ─► Gaussian-HMM: fit (Baum-Welch/EM, log-stabil) → viterbi (globaler MAP-Pfad)
                  → aktueller Zustand → Label (trend_up/range/trend_down) + Konfidenz + Persistenz
   Fallback:    vola-normiertes Schwellen-Modell (classify_regime) liefert weiter trend_z
   Vola:        classify_volatility → calm/normal/turbulent (relativ zur Baseline)
   gespeichert: market_snapshots(regime, vol_regime, trend_z, regime_conf)  →  speist die Allokation
```

### Querschnitt — Fundamental: Wirtschaftskalender & Event-Risiko (`fundamental.py`)
**Vorausschauende** Risiko-Schicht (kennt Events, BEVOR sie im Preis stehen — anders als das HMM).
```
   Wirtschaftskalender (faireconomy, key-frei, gecacht, Seed-Fallback)
        ─► event_risk: none / elevated / high  (Fenster vor/um FOMC·CPI·NFP)
   CoinGecko /global (key-frei) ─► BTC-Dominanz, MarketCap-Trend ─► crypto_risk
        ─► macro_stance: risk_on / neutral / risk_off
   ──► Master-Overlay (TAKTISCH, defensiv): dämpft die EFFEKTIVE gerichtete Quote
       (lehnt vor High-Impact-Events stärker auf den Sockel). Verändert NICHT die
       persistierte Fitness (zeitvariabel → kein Versions-Churn).
```
| Funktion | Rolle |
|---|---|
| `fetch_calendar()` | key-freier Kalender, Fallback-Kette live→Cache→alt→Seed |
| `event_risk()` | vorausschauende Risiko-Stufe + nächstes Event + `dir_scale` |
| `crypto_fundamentals()` / `macro_stance()` | CoinGecko-Kontext + kombinierte Markt-Stance |
| `master._fundamental_overlay()` | taktischer Dämpfungs-Overlay (effektive Sockel-Quote) |

### Querschnitt — Selbst-Verwaltung & Gedächtnis (`maintenance.py`, Versionierung)
| Mechanismus | Was er „lernt"/verwaltet |
|---|---|
| `maintenance` (learning_ledger, snapshots_monthly, market_daily) | verdichtet das Lern-Gedächtnis, Lifecycle/Pruning |
| `bot_upgrades` + `opt_version` | versioniertes Verbesserungs-/Upgrade-Management je Bot (Changelog) |
| `master_policy` | versionierte Ensemble-Politik mit Fitness-Verlauf |

---

## 3. Der Lern-Kreislauf (Sequenz)

```
   (1) Markt-Daten holen (read-only)         tracker.market_snapshot · csm.refresh
            │
   (2) Edge-Quellen lernen                    meta.run_optimization/evolution · *.optimize()
            │   (proposal-only, OOS-gehärtet)
   (3) Evidenz speichern                       strategy_validations · optimizations · csm_equity_log
            │
   (4) AUTO-TRAIN                              _auto_train() → master.train_step()
            │
   (5) Ensemble-Politik ableiten + bewerten    derive_policy (regime-bedingt) → Fitness
            │   nur bessere Version behalten
   (6) Anzeigen                                Frontend · /api/master · /api/regime
            │
   (7) Mensch entscheidet  ───────────────────►  (Echtgeld = M6, separate Freigabe)
            └──────────────────────── zurück zu (1) ──────────────────────────┘
```

---

## 4. Daten-Substrat (SQLite)

| Tabelle | Inhalt |
|---|---|
| `backtest_runs`, `snapshots` | rohe Backtest-/Tages-Kennzahlen je Bot |
| `strategy_validations` | validierte Strategie-Erkenntnisse (PF, Fenster) — **Master-Input** |
| `optimizations` | beste Parametersätze je Strategie — **Master-Input** |
| `csm_prices`, `csm_meta`, `csm_equity_log` | Preis-Store + Config + Forward-Tracking der MN-Engines |
| `market_snapshots` | Regime · vol_regime · trend_z · **regime_conf** (HMM) — **Allokations-Input** |
| `master_policy` | versionierte Ensemble-Politik + Fitness-Verlauf |
| `bot_upgrades` | Upgrade-/Versions-Changelog je Bot |
| `learning_ledger`, `snapshots_monthly`, `market_daily` | verdichtetes Lern-Gedächtnis (Lifecycle) |

---

## 5. Eiserne Prinzipien

- **proposal-only:** Jeder Lern-Schritt schlägt nur vor — **nichts wird automatisch real angewendet**.
- **0 echtes Risiko:** alles Demo/Paper; MN-Engines sind reine Simulationen; keine Orders.
- **OOS zuerst:** Walk-Forward, Deflated-/Haircut-Sharpe, Konfidenz nach OOS-Länge — gegen Overfitting.
- **keep-if-better:** der Master behält nur Verbesserungen (versioniert) → kann nie „verschlimmbessern".
- **Echtgeld = Mensch:** Ausführung/Echtgeld bleibt M6 mit ausdrücklicher Freigabe + Backup-Strukturen.

---

## 6. Nächste Schritte / offene Punkte

### ✅ Fundamental-Schicht (NEU, 2026-06-08) — Wirtschaftskalender/Event-Risiko/Makro/On-Chain
Eingebaut: `fundamental.py` (key-frei: faireconomy-Kalender + CoinGecko + Seed-Fallback),
vorausschauendes Event-Risiko, Makro-Stance, **defensiver Master-Overlay**, `/api/fundamental`,
Frontend-Panel. Siehe RESEARCH_FUNDAMENTAL + ARBEITSPAKET_FUNDAMENTAL_NACHT.

### ✅ KI-/Lern-System (NEU erledigt, Nacht-Arbeitspaket TEIL 2 — Commits …d8e923e)
- [x] **HMM-Parameter tunbar** (`n_states` via Config + `/api/regime/config`).
- [x] **Multivariates HMM** (Rendite + Volatilität, diagonale Kovarianz; `classify_mv`).
- [x] **Regime-Übergänge antizipieren** (HMM-Übergangsmatrix → `next_regime`/`stay_prob` → Forward-Tilt).
- [x] **Deflated-Sharpe je #Engines** (`deflate_factor`, Multiple-Testing-Haircut, tunbar).
- [x] **Stacking / dynamische Meta-Gewichte** (`_meta_split`: Softmax-`meta_temp` + `meta_floor`).
- [x] **MasterMeta** vola-normiert gehärtet (konsistent mit `tracker.classify_regime`).

### ✅ Recherchetool 2.0 (NEU, 2026-06-09)
Strategie-Recherche (`ai.py`) liefert zwei prominente Entscheidungs-Scores **🛡 Sicherheit** + **⚡ Effizienz** (0–100), an EIGENE OOS-Validierung gegroundet; neue Felder `efficiency`/`event_sensitivity`; Prompt kennt die neuen KI-Faktoren; UI rückt beide Scores in den Fokus (Katalog-Tabelle + Karten). Siehe ARBEITSPAKET_RECHERCHETOOL.

### 🔭 Weiter offen / Ideen (für später)
- [ ] Vollkopplung MasterMeta ↔ python-HMM über eine Regime-Export-Bridge (venv-übergreifend).
- [ ] Echte On-Chain-Tiefe (CryptoQuant/Glassnode, bezahlt) statt CoinGecko-Markt-Level.
- [ ] Echte Makro-Werte/Überraschungen (FRED-Key) statt Proxy-Stance.
- [ ] **F (Nicht-KI):** Design-Harmonie-Abschlusspass · **M6:** Echtgeld-Pfad mit Backup-Strukturen.

### 🖥️ Nicht-KI / aus dem älteren Backlog (laut Memory)
- [ ] **F — Design-Harmonie (Abschluss-Pass):** Schrift-Größen-Feinjustage, Glow-/Abstands-Dosierung
      nach Geschmack (Nutzer-Zuruf). Rest des großen UI-Backlogs (A–E, G, C, D) ist erledigt.
- [ ] **M6 — Echtgeld-Pfad:** Backup-Strukturen + ausdrückliche Freigabe, bevor irgendetwas real handelt.

### ✅ Diese Session erledigt (Referenz)
Option A komplett (mn_base-DRY · Master ingestiert MN-Engines · Auto-Train · Regime vola-normiert) →
+ Iteration 1 (OOS-gehärtete, gekappte, soft-votbare Sockel-Gewichtung, tunbar) →
+ Iteration 2 (echtes Gaussian-HMM) → + Iteration 3 (HMM-Regime aktiv in die Allokation).
Commits `081d864` … `25f8b9d`.

---

## 7. Mini-Glossar
- **OOS** = Out-of-Sample (Test auf ungesehenen Daten).
- **Sharpe** = Rendite je Risiko (annualisiert). **PF** = Profit-Faktor (Gewinne/Verluste; >1 = profitabel).
- **Walk-Forward** = rollierende OOS-Fenster statt einzelnem Backtest.
- **HMM** = Hidden-Markov-Modell; verborgene Zustände (= Regimes) erzeugen die beobachteten Renditen.
- **Sleeve** = Teil-Portfolio (gerichtet vs. markt-neutral). **Sockel** = stabiler markt-neutraler Anteil.
- **Fitness** = Selbstbewertung der Master-Politik (höher = besser); keep-if-better.
