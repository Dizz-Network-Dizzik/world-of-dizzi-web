# Kelly-Sizing SPEC — Expectancy → fraktionaler Kelly → Klemmkette → Brücke zur Hand (FP-2 / T4)

> **Stand:** 03.07.2026 · Branch `chat/tb-kelly` · Umsetzung von docs/59 §A (FP-2) auf Basis
> `MASTERMETA_TIEFENPRUEFUNG_2026-06-25.md` Empfehlung #1.
> **Sicherheits-Grundsatz:** JEDER neue Hebel ist opt-in mit inertem Default. Ohne Opt-in ist das
> Verhalten byte-identisch zu vorher (Suite-Beleg: `test_kelly_clamps.py::test_defaults_inert_*`).

## 0 · Lage vorher (Warum)

- `sizing.py` empfiehlt Stakes (Vol-Targeting × opt-in Kelly-Tilt), **proposal-only**: Anwenden nur
  per Hand über `/api/bots/{id}/sizing/apply` (Stake setzen + Bot-Neustart).
- `master.derive_policy()` berechnet `suggested_exposure` (Vol-Targeting 0.3..1) — erreicht die Hand
  nur als **Leverage-Dämpfer** der MasterMeta-Engine (Regime-Bridge `hmm_regime.json`, D1).
- **Lücke (Empfehlung #1):** der Stake-Pfad (`stake_amount`) hat KEINE Brücke; Expectancy-Sizing hat
  keinen Portfolio-Deckel und keine definierte Interaktion mit Governor/Concentration.

## 1 · Edge-Messung (K0) + Konfidenz-Abschlag (K1)

**K0 — Quelle** (`edge_source`, Default `"bot"`):
- `"bot"`: `stats.trade_expectancy(bot_id)` — geschlossene Trades aus der Live-Trade-DB des Bots
  (read-only). Mindest-Stichprobe `min_trades_kelly` (Default 20), sonst neutral.
- `"strategy"`: `stats.strategy_expectancy(strategie)` — **gepoolte** geschlossene Trades ALLER Bots
  derselben Strategie (mehr Stichprobe, gleicher Signalgeber). Mindest-Stichprobe
  `min_trades_strategy` (Default 60), sonst neutral.
- `"auto"`: Bot-Edge wenn `n_decided ≥ min_trades_kelly`, sonst Strategie-Pool wenn
  `≥ min_trades_strategy`, sonst neutral.

Kelly-Definition (unverändert, `stats._expectancy_from_profits`): `f* = W − (1−W)/b` mit Payoff
`b = Ø-Gewinn/Ø-Verlust`. Ohne Verluste (b undefiniert) → neutral, NIE aus reinen Gewinnern hochrechnen.

**K1 — Konfidenz-Abschlag** (beide Faktoren Default AUS = 1.0):
```
kelly_eff = kelly_roh × n/(n + shrink_trades) × sim_discount
```
- `shrink_trades` (Default **0** = aus; **Empfehlung 40**): Shrinkage Richtung 0 gegen
  Schätzfehler kleiner Stichproben (n=20 → ×0.33 · n=60 → ×0.60 · n=200 → ×0.83). Monoton in n.
- `sim_discount` (Default **1.0** = aus; **Empfehlung 0.85**): dry-run-Fills sind optimistisch
  (Slippage ≈ 0, siehe `stats.execution_costs`; M6-Vorbereitung) — der gemessene Edge ist eine
  Simulation. Analogie zu `master_config.sim_discount` für synthetische MN-Engines.

## 2 · Fraktionaler Kelly-Tilt (K2) + Vol-Budget (K3) — per Bot

```
K2: mult = clip(1 + kelly_fraction × kelly_eff, kelly_floor, kelly_cap)
K3: empfohlen = clip(reference_stake × (target_vol/realisierte_vol) × mult, min_stake, max_stake)
```
- `kelly_fraction` λ Default **0.25** (Viertel-Kelly), per `set_config` hart auf ≤ 1.0 geklemmt.
- HARTE per-Bot-Caps: `kelly_cap` (Default 1.5, nie hochhebeln) / `kelly_floor` (Default 0.5) /
  `min_stake`/`max_stake`. Negativer Erwartungswert ⇒ mult < 1 (verkleinern, NIE vergrößern).
- K2/K3 sind der bestehende, live geschaltete Pfad (`expectancy_enabled: true`) — unverändert,
  solange K1-Faktoren auf Default stehen.

## 3 · Portfolio-Klemmkette (K4→K5→K6) — `sizing.portfolio_plan()`

Neue Schicht ÜBER den per-Bot-Empfehlungen. **Reihenfolge ist normativ** (jede Stufe wird im
`trace` des Ergebnisses protokolliert; Property-Tests prüfen die Invarianten am Endzustand):

**K4 — Portfolio-Budget** (`portfolio_budget_pct`, Default **0** = aus):
- Margin-Basis: `margin_i = stake_i × max_open_trades_i` (eingesetztes Kapital; Hebel multipliziert
  Exposure, nicht Margin). Deckel `cap = pct/100 × Σ dry_run_wallet`.
- Überschreitung ⇒ **proportionales Herunterskalieren** (erhält die relativen Kelly-Gewichte) mit
  `min_stake`-Floors per **Water-Filling**: Bots, deren skalierter Stake unter `min_stake` fiele,
  werden auf `min_stake` gefloort und der Rest neu skaliert (Fixpunkt ≤ n Iterationen).
- Degeneriert (`cap < Σ min_stake×mot`): alle auf `min_stake`, Flag `budget_infeasible: true`
  (ehrlich melden statt still verletzen).

**K5 — Konzentrations-Klemme** (`concentration_clamp`, Default an — wirkt nur im Plan):
- Wenn `concentration.analyze().severity == "warn"`: Bots, deren Basis-Assets ein über-gedeckeltes
  Asset oder einen über-gedeckelten Cluster berühren, dürfen **nicht aufgesizet** werden:
  `stake = min(stake, aktueller_stake)`. Kein Zwangs-Downsizing (strukturelles Risiko ⇒ Streuung
  ist die Antwort, nicht Panik) — konsistent mit der Governor-Philosophie zu P2.

**K6 — Governor-Klemme** (`governor_clamp`, Default an — wirkt nur im Plan; **letztes Wort**):
- `severity == "warn"` ⇒ flottenweit kein Upsizing (`stake = min(stake, aktuell)`).
- `severity == "breach"` ⇒ zusätzlich: die **Brücke degradiert auf `proposal`** (auch wenn
  `bridge_mode: "apply"` konfiguriert ist) — in einer Breach-Lage wendet die Hand nichts
  Neues an. Aktives De-Risking bleibt Sache des Governors (Separation of Concerns).

**Freeze-Semantik:** `min(stake, aktuell)` wird NICHT zurück auf `min_stake` gehoben, wenn der
aktuelle Stake darunter liegt (Freeze heißt einfrieren, nicht anheben). Invariante daher:
`final_i ≥ min(min_stake, aktueller_stake_i)`.

**Invarianten (Property-Tests, seeded random, `tests/test_kelly_clamps.py`):**
- P1 Caps: `final_i ≤ max_stake` und `final_i ≥ min(min_stake, aktuell_i)`.
- P2 Budget: `Σ final_i×mot_i ≤ cap` ODER `budget_infeasible`-Flag gesetzt.
- P3 Monotonie: K4–K6 erhöhen NIE (`final_i ≤ per-Bot-Empfehlung_i`).
- P4 Freeze: Governor warn/breach ⇒ `final_i ≤ max(aktuell_i, 0)` für Bots mit aktuell > 0.
- P5 Breach-Degradation: breach ⇒ Bridge-Payload `mode == "proposal"`.
- P6 Idempotenz: `plan(plan(x)) == plan(x)` (stabiler Fixpunkt bei unveränderten Inputs).

## 4 · Brücke zur Hand — `suggested_sizing.json` (Muster: `hmm_regime.json`)

**Kette Gehirn → Hand** (jede Stufe fail-safe → `proposed_stake` unverändert):

| Stufe | Ort | Gate | Default |
|---|---|---|---|
| 1 | Backend-Config | `bridge_enabled` | **False** ⇒ Datei wird NICHT geschrieben |
| 2 | Backend-Config | `bridge_mode` | **"proposal"** ⇒ Engine wendet NIE an |
| 3 | Governor | breach ⇒ Degradation auf proposal | automatisch |
| 4 | Engine opt_param | `use_sizing_bridge` | **0** ⇒ Callback gibt `proposed_stake` zurück |
| 5 | Engine freqtrade-Config | `dry_run == True` | **Echtgeld hart ausgeschlossen** (M6/G-T5 tabu) |
| 6 | Engine Frische | `ts` ≤ `bridge_max_age_s` (Default 900 s) | veraltet ⇒ ignorieren |

- **Writer:** `sizing.write_bridge_auto()` im Autopilot-Tick direkt NACH dem Governor
  (`main._autopilot_step`), atomar via `jsonstore.write_atomic`. Payload: `{ts, mode,
  governor_severity, stakes: {bot_id: {stake, mot, current}}, budget}`.
- **Pfad-Vertrag:** `TBT_SIZING_FILE` (runner setzt IMMER, analog `TBT_REGIME_FILE`) →
  Fallback relativ zur Strategie-Datei. Bot-Identität: `TBT_BOT_ID` (runner setzt IMMER).
- **Konsument:** `MasterMeta.custom_stake_amount()` — klemmt den Bridge-Stake zusätzlich auf
  freqtrades `[min_stake, max_stake]`-Argumente. **Armed-until-restart:** laufende Bots lesen die
  neuen Env-Variablen erst nach ihrem nächsten (Nutzer-gegateten) Neustart.
- **Rollback:** `bridge_enabled: false` setzen (nächster Autopilot-Tick schreibt nicht mehr; Engine
  ignoriert veraltete Datei nach `bridge_max_age_s` von selbst) oder Datei löschen — beides ohne
  Neustart wirksam. Config-Flip via `POST /api/sizing/config`.

## 5 · Ruin-Risiko-Beleg (Zusammenfassung; Zahlen: `test_kelly_ruin.py` + §6)

Monte-Carlo (multiplikativ, seeded): Zwei-Punkt-Trade-Verteilung (Gewinn +b·R mit p, Verlust −R),
Equity `×(1+f·X)` je Trade. Kernbefunde (Detail-Tabelle §6):
- P(Drawdown ≥ 50 %) steigt **monoton** in der Kelly-Fraktion; **Voll-Kelly ist trotz maximalem
  Wachstum untragbar**: die Kapital-Halbierung ist der NORMALFALL (P=100 %), medianer Max-DD 87 %.
- **Viertel-Kelly (λ=0.25)** behält ~43 % des Log-Wachstums (×7.8 statt ×117), drückt aber
  P(DD≥50 %) von 100 % auf 6.5 % und P(DD≥80 %) auf 0 — Grundlage für Default λ=0.25 + `kelly_cap` 1.5.
- Negativer Erwartungswert: JEDE Fraktion > 0 verliert; Median-Endkapital < Start, monoton
  schlechter in f ⇒ `kelly_floor` schrumpft Verlierer, hebelt sie NIE (`mult < 1`).
- Fixed-Stake (nicht-kompoundierend, heutiges Verhalten) vs. fraktionaler Kelly bei gleichem
  Einsatz-Anteil: Kelly kompoundiert (×7.8 vs. ×3.3 Median) bei moderat höherer DD-Quote (6.5 % vs.
  2.8 % P(DD≥50 %)) ⇒ Expectancy-Sizing lohnt, aber NUR mit der Klemmkette dieser SPEC — höhere
  λ kippen das Verhältnis schnell (λ=0.5: P(DD≥50 %) schon 76 %).

## 6 · Sim-Vergleich Kelly vs. fixed-stake (seeded Lauf 03.07.2026, Code = `test_kelly_ruin.py`)

**Szenario A** (positiver Edge p=0.55, b=1.2 ⇒ f\*=0.175; 2000 Pfade × 250 Trades, Seed 7):

| Sizing | f je Trade | Median-Endkapital (Start 1.0) | Median-Max-DD | P(DD≥50 %) | P(DD≥80 %) |
|---|---|---|---|---|---|
| Voll-Kelly (λ=1.0) | 0.1750 | ×116.74 | 86.6 % | 100.0 % | 72.7 % |
| Halb-Kelly (λ=0.5) | 0.0875 | ×33.89 | 58.0 % | 76.4 % | 4.4 % |
| **Viertel-Kelly (λ=0.25, Default)** | 0.0438 | ×7.77 | 33.1 % | 6.5 % | 0.0 % |
| Zehntel-Kelly (λ=0.1) | 0.0175 | ×2.44 | 14.4 % | 0.0 % | 0.0 % |
| fixed-stake (gleicher Anteil 0.0438) | 0.0438 | ×3.35 | 20.7 % | 2.8 % | — |

**Szenario B** (negativer Edge p=0.9, b=0.05 — „Pennies vor der Dampfwalze", 90 % Winrate!):

| f je Trade | Median-Endkapital | P(DD≥50 %) |
|---|---|---|
| 0.05 | ×0.486 | 60.8 % |
| 0.10 | ×0.221 | 97.1 % |
| 0.20 | ×0.035 | 99.9 % |

Lesart: **Winrate-naives Sizing wäre ruinös** (Szenario B sieht mit 90 % Winrate „gut" aus) — genau
deshalb sizet der Tilt nach Kelly/Erwartungswert und `kelly_floor` verkleinert Verlierer nur.

## 7 · Config-Referenz (neu; alle Defaults inert)

| Key | Default | Wirkung |
|---|---|---|
| `edge_source` | `"bot"` | `"bot"` · `"strategy"` · `"auto"` (K0) |
| `min_trades_strategy` | 60 | Mindest-Trades Strategie-Pool |
| `shrink_trades` | 0 (aus) | Konfidenz-Shrinkage n/(n+k) (K1) |
| `sim_discount` | 1.0 (aus) | dry-run-Edge-Discount (K1) |
| `portfolio_budget_pct` | 0 (aus) | Portfolio-Margin-Deckel in % Σ Wallet (K4) |
| `concentration_clamp` | true | K5 im Plan aktiv |
| `governor_clamp` | true | K6 im Plan aktiv |
| `bridge_enabled` | false | Brücke: Datei schreiben |
| `bridge_mode` | `"proposal"` | `"apply"` = Engine darf (nur dry_run) anwenden |
| `bridge_max_age_s` | 900 | Engine-Frische-Gate |

**NICHT-SCOPE:** T5 Politik→Hand (Gate G-T5) · M6-Echtgeld · Auto-Restart von Bots.
