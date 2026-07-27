# Lernsystem (KI-/Meta-Schicht) — Detail

Ziel: ein selbst-verfeinernder Meta-Algorithmus, der aus eigener Performance + Marktregime + einem
markt-neutralen Sockel lernt. **Kette:** sammeln → auswerten/empfehlen → testen (Walk-Forward) →
Gewinner → anwenden → Gates → (später) Echtgeld. Alles **proposal-only** bis zur ausdrücklichen
Freigabe. Viele empirische Teile **aktivieren sich selbst**, sobald genug Laufzeit-Daten vorliegen.

## 1. Datensammlung — `tracker.py` + `stats.py`
- **`snapshots`** (Tabelle): 1 Zeile/Bot/**Tag** (UPSERT) — equity, profit_pct, trades, winrate,
  max_drawdown, strategy, trading_mode. Debounced aus `GET /api/summary`.
- **`market_snapshots`**: stündlich BTC/USDT — price, **regime** (aus dem HMM), **volatility**,
  vol_regime, trend_z, regime_conf, next_regime, regime_stay_prob.
- Per-Trade bleibt in den Freqtrade-Trade-DBs (on-demand read-only gelesen). Keine Tickdaten, < MB/Jahr.

## 2. Regime-Erkennung — `hmm.py` (+ Bridge)
Gaussian-HMM (Baum-Welch-EM + Viterbi) über mehrere Features → verdeckte Zustände
`trend_up`/`trend_down`/`range` + Konfidenz + antizipiertes nächstes Regime + Halte-Wahrscheinlichkeit.
`tracker` exportiert das Live-Regime in **`hmm_regime.json`**; die MasterMeta-Engine liest es
venv-übergreifend und schaltet Sub-Logik + Hebel (mehr Konfidenz → mehr Hebel, gedrosselt nach
Event-Risiko + Vol-Targeting).

## 3. Lerner Stufe 1 — `meta.py`
- `aggregate()` Ø Profit/DD/Winrate je Strategie · `proposals()` regelbasierte Hinweise (proposal-only).
- **Parameter-Optimierung:** `optimize_proposals()` erzeugt ein Kandidaten-Raster; **`run_optimization(
  strategy, params, days, windows)`** testet **real** (Backtest bzw. **Anchored-Walk-Forward** bei
  `windows≥2`, robuster gegen Overfitting), kürt den Gewinner (multi-objektiv: Profit − DD-Gewicht −
  Overtrade-Strafen), persistiert in `stats.optimizations`. Param-Injektion über **Env `TBT_OPT_PARAMS`**
  in den Subprozess — Live-Bots ohne Env nutzen Defaults (unverändert).
- **Regime-/Session-Empfehlung:** `regime_advice()`/`session_advice()` — empirisch (Trades → Tage) mit
  Fallback regelbasiert (`STRAT_REGIME`-Tags trend/range/volatil; `source`-Feld zeigt welches).
- **Konsistenz-Gate:** `consistency()` (Historie + Ø-Profit + Equity-Trend + Volatilitäts-Stabilität)
  — liefert auch die realisierte Tages-Vola, auf der das Sizing aufsetzt.

## 4. Ensemble Stufe 2 — `master.py`
`derive_policy()` setzt aus ALLEN Edge-Quellen eine regime-bedingte **Ensemble-Politik** zusammen:
- **Gerichteter Sleeve:** je Regime die beste OOS-**validierte** Strategie (unvalidierte werden auf
  PF≤1 gekappt — Ehrlichkeits-Gate), nach HMM-Konfidenz mit der regime-gemittelten Sicht geblendet,
  Regime-Übergang antizipiert.
- **Markt-neutraler Sockel** (`mn_sleeve`): CSM/Pairs/StatArb/MM, hart gehärtet (Sharpe-Haircut →
  **Deflated Sharpe** gegen Multiple-Testing → PSR → **`sim_discount`** für synthetische MM → Shrinkage
  → Max-Weight-Cap → 1/N-Benchmark).
- **Dynamischer Meta-Split** dir↔Sockel (gerichtet schwach → Sockel trägt mehr) + Fundamental-Overlay
  (Event-/Makro-Dämpfung) + Vol-Targeting → `suggested_exposure`.
- `train_step()` = Ratchet: akzeptiert nur verbesserte Fitness, re-baseline bei neuer Evidenz.

## 5. Markt-neutraler Sockel (simuliert, 0 Risiko)
`csm.py` (Cross-Sectional-Momentum, belegt positiver Edge ~Sharpe 1.3), `pairs.py` (Pairs-Spread +
StatArb-Korb), `marketmaking.py` (Avellaneda-Stoikov). Alle lookahead-frei, mit `mn_learn.py`
(Anchored-Walk-Forward). Persistente Instanzen via `mn_paper.py` (`/api/mn-paper`). Der Master zieht
die **kanonischen** Engine-Edges (nicht beliebige Paper-Instanzen). Live-Ausführung erst mit M6.

## 6. Autopilot — `autopilot.py` (Hintergrund-Loop, Default 6 h)
`_autopilot_step` (in `main.py`), Reihenfolge **normativ**, jeder Teil exception-fest getrennt:
1. **`governor.run_once`** — Portfolio-Risiko zuerst (bei breach de-risken, bevor verbessert wird).
2. **`sizing.write_bridge_auto`** — FP-2 Sizing-Bridge schreiben (nach dem Governor, damit breach die
   Brücke sofort auf proposal degradiert). Default aus ⇒ no-op.
3. **`_mastermeta_improve`** — HMM/Master/Fundamental konsultieren, MasterMeta per Walk-Forward
   optimieren, anwenden nur wenn confident + kein Event-Block.
4. **`_auto_upgrade_bots`** — OOS-validierte Gewinner auf freigeschaltete Bots übernehmen.
5. **`cull.run_once`** — chronisch schlechte Demo-Bots auto-cullen (Lern-Daten bleiben).
6. **`_auto_validate_strategy`** — EINE noch unvalidierte Engine je Tick per Walk-Forward validieren.

## 7. Sizing/Kelly (FP-2) — `sizing.py`
Vol-Targeting setzt das **Risiko-Budget** (Stake invers zur realisierten Vola); der **Kelly-Tilt**
(opt-in) verschiebt es nach dem belegten **Erwartungswert/Edge** (NICHT Winrate): positiver Kelly →
moderat hoch (fraktionaler Kelly λ≤0.25, hart gedeckelt), negativer → runter (nie hochhebeln). Darüber
die **Portfolio-Klemmkette K4→K5→K6** (Budget · Konzentration · Governor als letztes Wort) und die
opt-in **Brücke zur Hand**. Ruin-Beleg + normative Reihenfolge: **`docs/KELLY_SIZING_SPEC.md`**.

## 8. Gates bis Echtgeld (mehrstufig, Detail `03_STAND_UND_BETRIEB` + `RUNBOOK_ECHTGELD`)
Validierungs-Gate (OOS-Backtest, Trades>0 & DD<50 %, kein Profit-Zwang) → Konsistenz-Gate (stabile
Historie) → Promote (neuer, **gestoppter** Echtgeld-Bot) → Governor/Concentration-Aufsicht →
`transfer.py` blockt echte Transfers, `dry_run=false` handelt real erst mit Trade-fähigem Key (M6).
