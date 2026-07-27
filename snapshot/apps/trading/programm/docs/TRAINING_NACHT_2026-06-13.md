# 🌙 KI-Trainings-Nachtlauf 2026-06-13 (Architektur-KI) — Lernfortschritt + ehrliche Befunde

Autonomer Trainings-Chat: die Lern-Schleifen systematisch treiben, Ergebnisse **ehrlich** messen,
Meta-Parameter tunen. Proposal-only, **0 Echtgeld**, `stats.sqlite`/`tradesv3_*` unangetastet,
appkit/Vertrag read-only. Start-HEAD `0775714`, 51/51 live, 283 Tests.

## 0 · Baseline (VOR dem Training, ehrlich gemessen)
| Messgröße | Start-Wert |
|---|---|
| `learning_status.readiness_pct` | **16 %** (255 Snapshots / 51 Bots) |
| `oos_validated`-Gewinner (optimizations) | **0 / 8** |
| Echtgeldreife Bots (`readiness.ready`) | **1 / 51** |
| Master-Politik | **v22**, Fitness **0.659** (v18 war 1.20 → ehrliche Re-Baseline) |
| Ensemble-Split | mn_share **90,6 %** / dir 9,4 % |
| MN-Sockel aktiv | **1 Engine** (nur Market-Making) |
| Regime (Snapshot) | trend_up, stay 0.81 |

## 1 · MN-Sockel — Runde 1 (csm/pairs/statarb/mm optimize, windows=3)
Daten frisch (`csm/refresh`: 80 Pairs, +26 Zeilen). Optimierer-Ergebnisse:
| Engine | Live-Sharpe (Voll-Hist) | Winner | OOS | Verdikt |
|---|---|---|---|---|
| **CSM** | 0.98 (ann 19.8 %, psr 0.913) | lookback21/hold2/q0.2 | oos 0.2 ✓ | **NICHT angewandt** — Winner Voll-Hist nur 0.24 (ann 2.7 %) → ökonomisch schlechter |
| pairs | −0.93 | entry_z 0.5 | oos −0.78 ✗ | nicht anwenden (OOS durchgefallen) |
| statarb | −1.69 | — | oos −4.18 ✗ | strukturell schwach (cross-sekt. Reversion ≠ Krypto-Momentum) |
| mm | 6.23 (psr 1.0) | gamma0.2 | (Seed-Sim) | kein klarer Gewinn → lassen |

**Befund A (umgesetzt als Code-Härtung, Commit `4d56084`):** Das MN-`oos_validated`-Flag bedeutet nur
`oos_sharpe>0` — eine zu schwache Hürde. Der CSM-„Winner" war OOS-positiv (0.2), aber über die volle
Historie deutlich schlechter als die laufende Config (Sharpe 0.24 vs 0.98). → `walk_forward` bewertet jetzt
optional die **laufende Config auf demselben OOS-Fold** (`baseline_oos_sharpe`) und setzt `improved_vs_current`
+ `apply_recommended` nur, wenn der Gewinner den Status quo dort wirklich schlägt. Kein Regressions-Vorschlag mehr.

**Befund B (load-bearing Engine — Market-Making war ein Lucky-Seed; umgesetzt, Commit `5c72921`):** Die MM-Sharpe
EINES Monte-Carlo-Laufs streut über Seeds von **2.5 bis 7.9** (Mittel ~5.4, Std ~1.35), die `psr` bleibt aber je
Lauf ~1.0 — sie misst nur Signifikanz INNERHALB eines Laufs, nicht die Seed-Streuung (**falsch beruhigend**). Der
Master wurde vom Default-Seed 42 (Sharpe **6.27**) gespeist = Lucky-Seed über dem Mittel. Da MM den ganzen Sockel
trägt, stand die Master-Edge auf einem Draw. → `status()` liefert jetzt die **20-Seed-gemittelte Sharpe (5.41)** +
`sharpe_seed_stdev` (memoisiert). Ehrlicher und niedriger.

**Befund C (Master-Deflation zu hart → killt die Diversifikation; § R-G-Hebel, anzuwenden nach Neustart):**
Quantifiziert (offline, mit ehrlicher MM 5.41) — Sockel-Komposition je `deflate_factor`:
| deflate_factor | aktive Engines | Sleeve-Fitness | 1/N-Fitness | Weighting schlägt 1/N? |
|---|---|---|---|---|
| **0.4 (aktuell)** | 1 (nur MM-Sim) | 0.580 | 0.966 | ❌ |
| 0.3 | 1 (nur MM-Sim) | 0.593 | 0.988 | ❌ |
| **0.2 (Vorschlag)** | **2 (CSM + MM)** | **1.161** | 1.073 | ✅ |
| 0.0 | 2 (CSM + MM) | 1.228 | 1.139 | ✅ |

Bei 0.4 überlebt nur die MM-**Simulation**; die real-data **CSM (0.98)** wird auf 0 gehaircutet → Mono-Engine-Sockel,
der die (degenerierte) 1/N-Benchmark verliert. Bei **0.2** qualifiziert sich CSM → echte Diversifikation (MM-Sim +
real-data) UND die gewichtete Fitness schlägt erstmals 1/N (1.16 > 1.07) = das §4-Erfolgskriterium. Methodik: die
√(2·ln N)-Deflation modelliert „bester aus N **selektiert**" — der Sockel **kombiniert** aber alle Überlebenden,
nicht selektiert einen → die volle Korrektur ist hier zu hart und konzentriert paradox 100 % auf eine Simulation,
statt den realen Edge zuzulassen. Der flache `sharpe_haircut 0.5` deckt den Per-Engine-Schätzfehler bereits ab.
→ **Aktion: `deflate_factor` 0.4 → 0.2** (reversibel via `POST /api/master/config`; in §4 explizit als Tuning-Hebel
gelistet, gegen 1/N gemessen). Reduziert zugleich die Über-Abhängigkeit von der einzelnen MM-Simulation.

## 2 · Strategie-Evidenz-Grind (anchored optimize, days=120, windows=3)
`scripts/night_train.py optimize` über alle 10 parametrisierbaren Strategien (Lauf-Log in
`data/training_log_<date>.jsonl`, gitignored). Ergebnisse:

| Strategie | oos_validated | OOS-Profit | Notiz |
|---|---|---|---|
| **MeanReversionRsi** | ✅ **True** | +0.11 % | erster OOS-validierter gerichteter Gewinner (knapp) |
| TrendFollowEma | ❌ | −5.11 % | Cross-Whipsaw, strukturell |
| MomentumMacd | ❌ | −27.38 % | Overtrading, strukturell negativ |
| FuturesMacdRsiScalp | ⚠️ Fehler | — | HTTP 500 (1m×14-Pairs-Backtest-Timeout — bekannt, langsamster Fall) |
| FuturesBreakoutVol | ❌ | −31.77 % | Donchian-Breakout in Choppy-Markt |
| FuturesBbandsBounce | ❌ | 0.00 % | keine Trades/flach im Test-Fenster |
| GridRange | ❌ | −8.11 % | |
| DcaDip | ❌ | −27.31 % | Dip-Buy in Abwärts-Markt |
| SessionOpenBreakout | ❌ | −0.29 % | |
| MasterMeta | (Neustart) | — | beim Backend-Neustart unterbrochen — im Evolve-Batch nachgeholt |

**Ergebnis:** 1/9 OOS-validiert (MeanReversionRsi, +0.11 %). Ehrliche Bestätigung der Stand-Lage: gerichtete
Krypto-Strategien sind in der aktuellen Choppy/Abwärts-Phase flächig negativ, das OOS-Gate hält korrekt. Kein
Schönrechnen. Der einzige nennenswerte Fortschritt liegt im MN-Sockel (Befund C).

## 3 · Messgrößen-Verlauf (vor/nach)

### Runde A — Backend-Neustart (Code live) + Master-Deflation 0.4→0.2
Neustart `0775714`-Code → live (honest MM `sharpe_seed_stdev` sichtbar, baseline-Gate aktiv). Dann Master gemessen:
| | aktive MN-Engines | Sockel-Fitness | 1/N-Fitness | schlägt 1/N | Sockel-Gewichte | Master-Version |
|---|---|---|---|---|---|---|
| vorher (deflate 0.4, honest MM) | 1 | 0.580 | 0.966 | ❌ | MM 0.6 | v25 |
| **nachher (deflate 0.2)** | **2** | **1.161** | 1.073 | ✅ | **CSM 0.4 + MM 0.6** | **v26** |

→ Master-Fitness **0.58 → 1.16**, Sockel diversifiziert in die real-data CSM (statt 100 % MM-Simulation), Gewichtung
schlägt jetzt 1/N. `deflate_factor 0.2` ist persistiert (`master_config`, überlebt Neustart) + reversibel.

### Runde B — Validierungs-Batch (groundet gerichteten Sleeve) + kritischer Befund D
`night_train.py validate` (windows=3, embargo=1) über alle Strategien (resumable; 1m-Scalper zuletzt). Ergebnis —
**9/10 validiert, ALLE `validated=False`** (keine besteht das WF-Mehrheits-Gate):
| Strategie | PF | Profit % | Strategie | PF | Profit % |
|---|---|---|---|---|---|
| MeanReversionRsi | 0.65 | −2.3 | FuturesBbandsBounce | 0.43 | −73.9 |
| TrendFollowEma | 1.15 | +0.6 (1/3 Fenster) | GridRange | 0.92 | −3.0 |
| MomentumMacd | 0.44 | −40.6 | **DcaDip** | **3.49** | **−5.9** |
| FuturesBreakoutVol | 0.57 | −37.0 | SessionOpenBreakout | 0.54 | −2.9 |
| | | | MasterMeta | 0.60 | −24.5 |

**Befund D (kritisch — umgesetzt, Commit folgt unten):** Nach dem Grounden allokierte der Master **46 % gerichtet
auf DcaDip** — PF **3.49** (Overfit-Flag der Metrik-Kanon: PF>3 = Overfit-Verdacht), aber `validated=False` und
**−5.9 % Gesamtrendite**. `derive_policy` nutzte den `profit_factor` OHNE das `validated`-Flag; der reine
`_confidence`-Penalty (×0.25) reichte nicht, weil PF 3.49 extrem ist → eine durchgefallene, verlustbringende
Strategie hätte die gerichtete Allokation getragen. Das Grounden hätte den Master also **schlechter** gemacht.
→ **Fix:** eine Strategie ohne bestandene OOS-Validierung bekommt **keinen** belegten gerichteten Edge (effektiver
PF auf ≤1 gekappt, `profitable` verlangt `validated`). Roh-PF bleibt zur Transparenz sichtbar.

### Runde C — Schlussmessung (alle Härtungen live, Backend 3× neu gestartet)
| Messgröße | Start (Baseline) | Ende (nach Training) |
|---|---|---|
| Master-Fitness | 0.659 (v22, Lucky-Seed-MM) | **1.161** (v29, ehrliche MM + Sockel-Diversifikation) |
| MN-Sockel aktiv | 1 (nur MM-Sim) | **2 (CSM real-data + MM)** |
| Sockel schlägt 1/N | ❌ (0.65 < 1.08) | ✅ (1.16 > 1.07) |
| MM-Edge-Schätzung | 6.27 (Seed 42, Lucky) | **5.41 ± 1.35** (20-Seed-Mittel) |
| gerichteter `dir_edge` | ~0 (keine Validierungen) | **0.0 ehrlich** (alle Strategien OOS-durchgefallen, hart gegated) |
| `oos_validated`-Optimize-Gewinner | 0/8 | 1/9 (MeanReversionRsi, +0.11 % — knapp) |
| echtgeldreife Bots | 1/51 | 1/51 (unverändert — ehrlich) |
| `readiness_pct` | 16 % | 16 % (Daten reifen über Tage, nicht in einer Nacht) |

**Fazit:** Der **reale Fortschritt** liegt in der **Ehrlichkeit + Robustheit** der Lern-Schicht, nicht in höheren
Zahlen um jeden Preis. Der Master stützt sich jetzt auf einen **echt diversifizierten** MN-Sockel (real-data CSM +
MM-Sim, schlägt 1/N) statt auf einen einzelnen Monte-Carlo-Glücks-Seed, und die gerichteten Strategien (in dieser
Choppy/Abwärts-Phase flächig negativ) können den Master **nicht mehr mit Schein-Edges kontaminieren**. Vier
Code-Härtungen schließen Ehrlichkeits-Lücken, die das System sonst zum „Lernen" schlechterer Politik verleitet hätten.

### Re-Entry-Messung (nach Datenreifung, +479 Trades / +51 Snapshots seit Sessionende)
Erste Messung beim Wiedereinstieg gegen den Anker oben:
| Messgröße | Anker (Ende NL1) | Re-Entry | Deutung |
|---|---|---|---|
| `readiness_pct` | 16 % | **20 %** (306 Snaps) | Daten reifen ✓ |
| **CSM-Sharpe** | 0.98 | **0.67** | dünner/volatiler Edge — fällt unter die Deflations-Schwelle (~0.83) |
| MN-Sockel aktiv / Fitness | 2 / 1.16 | **1 / 0.61** | CSM raus → zurück auf Mono-MM, schlägt 1/N nicht mehr |
| Regime-Zellen n≥100 | 0 | **9** | Trigger für regime-konditionierte Parameter naht (noch „≥3 Episoden" prüfen) |

**Lehre:** Das `deflate 0.2`-Tuning ist nie schlechter als 0.4, aber die Sockel-Diversifikation hängt an CSMs
Tagesform (0.67–0.98). **Der robuste Hebel ist, CSM selbst stabil > ~0.83 Sharpe zu bekommen** — nicht die
Deflation weiter zu senken. Nebenbefund: 9 Regime×Strategie-Zellen erreichen jetzt n≥100 (vorher 0) — der lang
vertagte Pfad „regime-konditionierte Parameter" wird messbar (Rest-Gate: ≥3 unabhängige Regime-Episoden je Regime).

## 4 · Was sich jetzt sammelt (für den Wiedereinstieg) + nächste Hebel
**Läuft autonom weiter (kein Eingriff nötig):**
- **Autopilot** (6 h-Tick, in-Backend, überlebt alles): Governor → MasterMeta-Improve → Auto-Upgrade (nur
  `oos_validated`) → Cull → Auto-Validate (1 Strategie/Tick). Treibt Evidenz + Politik kontinuierlich.
- **Tages-Snapshots** je Bot → `readiness_pct` wächst über Tage (16 % → braucht ~Wochen für Belastbarkeit).
- **CSM forward-track** (`csm_equity_log`) + **Regime-Snapshots** (`market_snapshots`) akkumulieren.

**Beim Wiedereinstieg ZUERST messen (Fortschritts-Check):**
1. `GET /api/master` → Sockel `active`, `fitness` vs `benchmark_1n.fitness` (schlägt die Gewichtung 1/N?),
   `mn_sleeve_live.members[].sharpe`/`sharpe_seed_stdev` (MM-Streuung), `ensemble.dir_edge` (sollte 0 bleiben,
   solange keine Strategie validiert).
2. `GET /api/meta` → `status.readiness_pct`, `optimizations` (Zahl `oos_validated`), `readiness` (echtgeldreif),
   `regime_performance_trades` (Zellen mit n≥100 — Trigger für regime-konditionierte Parameter: ≥3 Episoden je Regime).
3. CSM frisch halten: `POST /api/csm/refresh` (read-only ccxt), dann `GET /api/csm/optimize?windows=3` →
   `winner.apply_recommended` (NEU: nur True, wenn der Gewinner die laufende Config auf dem OOS-Fold schlägt).

**Nächste Hebel (priorisiert):**
- **Daten reifen lassen** = größter Hebel. Nach ein paar Tagen erneut `night_train.py optimize`/`validate` →
  prüfen, ob die regime_performance-Zellen den Schwellwert (n≥100 + ≥3 Episoden) erreichen → dann
  regime-konditionierte Parameter (bisher bewusst vertagt).
- **CSM-Edge heben** (der einzige real-data MN-Edge, aktuell Sharpe 0.98 = grenzwertig): tiefere Param-Suche /
  Funding-Proxy verbessern / breiteres Universum — Ziel: CSM robust > 1.2 Sharpe (dann trägt es ohne so niedrige
  Deflation). `improved_vs_current`/`apply_recommended` schützt jetzt vor Regressions-Anwendung.
- **Evolve-Batch** (`night_train.py evolve`, nutzt 15m → schnell, kein 1m-Hänger): tiefere Mutationssuche je
  Strategie — kann gerichtete `oos_validated`-Gewinner finden, die `optimize` verfehlt.
- **OFFENE PROPOSALS (größere, NICHT umgesetzt — Nutzer-Entscheid):**
  (a) **Deflated-Sharpe-Formel** sauberer: die √(2·ln N)-Korrektur modelliert „bester aus N **selektiert**" — der
  Sockel **kombiniert** aber. Sauberer wäre eine Korrektur, die das berücksichtigt (statt `deflate_factor` global
  zu senken). (b) **MM-Über-Abhängigkeit**: MM ist eine idealisierte Simulation; ein struktureller Konfidenz-
  Discount für Simulations-Engines ggü. forward-getrackten (CSM) wäre ehrlicher als die reine Sharpe-Höhe.
  (c) **Neue real-data Edge-Quelle** suchen (der wertvollste, aber aufwändigste Schritt) — der einzige belegte
  handelbare Edge ist dünn.

## Guardrails-Status (Nachtlauf eingehalten)
proposal-only ✓ · 0 Echtgeld ✓ · `stats.sqlite`/`tradesv3_*` unberührt ✓ · appkit/Vertrag read-only ✓ ·
Tests grün (288) ✓ · 51/51 live ✓ · alle Eingriffe reversibel (Config) oder getestet+committet (Code) ✓
**Angewandt** (über die sanktionierten Hebel): `master_config.deflate_factor 0.4→0.2` (reversibel via
`POST /api/master/config {"deflate_factor":0.4}`). Sonst nur Code-Härtungen (committet) + Evidenz-Grind.
