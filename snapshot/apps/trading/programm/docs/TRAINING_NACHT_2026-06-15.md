# KI-Trainings-Nacht 2 — 2026-06-15 (Bau-KI, durchgängig)

> Auftrag (Nutzer): „durch die Bank weg mit voller Kraft dem Trading-Bot beim Lernen helfen,
> bis ich morgen früh wieder da bin." **Proposal-only, 0 Echtgeld.** `stats.sqlite` +
> `tradesv3_*.sqlite` NIE löschen/zurücksetzen. appkit/Vertrag read-only. Ehrlichkeit vor Zahlen:
> ein gefallenes Gate = korrektes Lernen, nicht schönrechnen. Master HEAD bei Start: `5da923f`.

## BASELINE (Start, ~00:20 UTC)
- Bots: **51 laufend, 0 echtgeldreif**.
- Master: **Fitness 0.607 (v31)**; Regime „Aufwärtstrend" (HMM-Konfidenz 99 %); Fundamental-Overlay
  Event-Risiko *elevated* (nächstes Event BOJ Policy Rate in ~26 h) → gerichtet defensiv gedämpft.
- MN-Sockel: **mono (nur MM-Simulation)**. Member-Sharpes: csm **0.28** (haircut→0, Gewicht 0),
  pairs −0.84, statarb −0.98, **marketmaking 5.42** → 100 % Gewicht. `benchmark_1n` = degeneriert (1 Engine).
  Config: `deflate_factor 0.2, sharpe_haircut 0.5, max_weight 0.6, psr_weight 1.0, sharpe_to_pf 3.0`.
- Evidenz: optimizations gespeichert 10, **oos_validated 1**. readiness ~16 % (0 ready).
- **regime_performance_trades: 9 Zellen mit n≥100** über 3 Regime (range/trend_down/trend_up) —
  Trigger für regime-konditionierte Parameter praktisch erreicht. Erste Edges:
  - `FuturesBbandsBounce/trend_down` **+0.070 %** (n=275) ✅
  - `FuturesBreakoutVol/trend_up` **+0.065 %** (n=386) ✅
  - Rest der großen Zellen negativ (Scalper/Breakout in range/trend_down klar −).

## KERN-DIAGNOSE
Der MN-Sockel trägt nur noch die **MM-Simulation** (strukturell verdächtig: Monte-Carlo, kein real-data
Edge). Der einzige real-data MN-Edge **CSM ist von 0.98→0.67→0.28 zerfallen**. Der ehrliche Hebel ist,
CSM real zu heben (Refresh/Param-Suche/Universum) — NICHT die Deflation/Haircut weiter zu senken, um ein
0.28-CSM künstlich reinzurechnen (das wäre Schönrechnen, docs-Warnung).

## RUNDEN-LOG

### Runde 1 — CSM heben (~01:00 UTC)
- **Aktion:** `POST /api/csm/refresh` (48 s, 80er-Universum, Funding 80) → `GET /api/csm/optimize?windows=3` (24 Kandidaten, 3 Folds).
- **Messung:** bester Kandidat in-sample nur **0.2 Sharpe** (lookback30/hold2/q0.3, worst 0.14), Rest negativ.
  Winner-**OOS −0.07**, `oos_validated false`; Baseline (aktuelle Config) **OOS 1.39** auf demselben Fold →
  `improved_vs_current false`, `apply_recommended false`.
- **Schluss:** CSM ist extrem **fold-volatil** (1.39 / 0.28-Vollfenster / 0.2-in-sample) und im aktuellen
  Trend-Regime real schwach. Der `improved_vs_current`-Gate hat korrekt eine schlechtere Config abgelehnt →
  **Config unverändert, KEIN Schönrechnen** (keine Deflations-/Haircut-Senkung, um 0.28 reinzurechnen).
  MN-Sockel bleibt ehrlich **mono-MM**. Echter CSM-Edge kehrt erst mit dem Regime zurück (oder neue Edge-Quelle = Nutzer-Entscheid).
- **Danach gestartet:** `night_train.py optimize` (Hintergrund) — Evidenz-Grind über alle 10 Strategien.

### Runde 2 — optimize-Batch (~01:03–01:42 UTC, anchored, days=120/windows=3)
- **Ergebnis: 0 neue `oos_validated`.** Alle 9 gerichteten Strategien fallen am OOS-Gate, `confident=False`:
  MeanReversionRsi 0.0 · TrendFollowEma −0.06 % · MomentumMacd −28.0 % · FuturesBreakoutVol −31.6 % ·
  FuturesBbandsBounce 0.0 · GridRange −7.9 % · DcaDip −14.8 % · SessionOpenBreakout −3.0 % · MasterMeta −13.9 %.
- **FuturesMacdRsiScalp (1m, zuletzt): HTTP 500** nach ~15 min (Server-seitig; 1m×14-Pairs-Backtest, bekannt langsam/fragil). Kein Crash des Batches (resumable, err geloggt).
- **Schluss:** Gerichteter Edge im aktuellen Trend-Regime flächig negativ — **Gate hält korrekt** (kein Schönrechnen).
  Deckt sich mit Nachtlauf 1. Evidenz aktualisiert (Vorschläge in optimizations); Master-Grounding folgt über `validate`.
- **Offen/Bug-Notiz:** Scalper-optimize 500 — separat prüfen (nicht-blockierend; betrifft nur diese eine 1m-Vorlage).
- **Danach gestartet:** `night_train.py validate` (Hintergrund) — re-validiert alle Strategien, groundet Master/Echtgeld-Gate.

### Runde 3 — Regime-Analyse (read-only, parallel zu validate) ★ HIGHLIGHT
`regime_data_points 306` (Episoden-Snapshots), `regime_trade_data_points 3809` (Einzel-Trades).
**Per-Trade-Zellen (n≥100) — robuste regime-konditionierte Edges:**

| Strategie | trend_up | trend_down | range |
|-----------|----------|-----------|-------|
| **FuturesBreakoutVol** | **+0.065** (n=386) | −0.184 (n=311) | −0.206 (n=234) |
| **FuturesBbandsBounce** | +0.175 (n=87) | **+0.070** (n=275) | −0.302 (n=118) |
| FuturesMacdRsiScalp | −0.262 (n=913) | −0.276 (n=674) | −0.172 (n=364) |
| SessionOpenBreakout | −0.232 (n=74) | −0.652 (n=101) | — |

**Befunde:**
1. **FuturesBreakoutVol = trend_up-Spezialist** (positiv NUR im Aufwärtstrend, negativ sonst).
2. **FuturesBbandsBounce = Trend-Spezialist** (positiv up+down, klar negativ in range).
3. **FuturesMacdRsiScalp durchweg negativ** (n≈1950 über alle Regime) → **stärkster Cull-Kandidat** (+ warf optimize-500).
4. **`regime_advice` (Heuristik) widerspricht der reifen Evidenz:** es empfiehlt für trend_up `DcaDip/GridRange/FuturesBbandsBounce`
   (basiert auf `regime_tag` + Episoden-Snapshots mit n=3), während die per-Trade-Evidenz (n≥100) FuturesBreakoutVol als
   den trend_up-Edge zeigt. ⇒ Die Regime-Empfehlung sollte evidenz-getrieben (per-Trade-Zellen) statt tag-heuristisch sein.

**TRIGGER für regime-konditionierte Parameter ERREICHT:** ≥9 Zellen mit n≥100 über 3 Regime (range/trend_down/trend_up)
UND ≥3 Regime-Episoden je Regime (Episoden-Snapshots vorhanden). Damit ist das lang vertagte „regime-konditionierte
Parameter"-Paket **reif zur Umsetzung** — das ist aber eine **architektonische Änderung (Nutzer-/World-Chat-Entscheid)**,
nicht autonom über Nacht: ich dokumentiere sie als greenlight-fertige Proposal (s. §SCHLUSS).

### Runde 4 — validate-Batch + Master-Re-Train (~01:43–02:12 UTC) ★ FORTSCHRITT
- **validate-Ergebnis: 1/10 validated → TrendFollowEma** (PF 1.13, +0.71 %, **2/3 Fenster bestanden**, n=367).
  Alle anderen fallen (0–1/3 Fenster): MomentumMacd PF0.44/−40 %, FuturesBbandsBounce PF0.42/−74 %,
  FuturesMacdRsiScalp PF0.27/−90 %, FuturesBreakoutVol PF0.58/−36 %, DcaDip PF3.23 aber nur 1/3 Fenster/−4.7 %, …
- **Kohärenz mit Runde 3:** die strenge unkonditionierte Walk-Forward lässt nur den **Trend-Follower** durch
  (passt zum anhaltenden Aufwärtstrend). Die regime-konditionellen Edges (FuturesBreakoutVol/FuturesBbandsBounce)
  fallen unkonditioniert durch — **genau deshalb braucht es regime-konditionierte Parameter** (Trigger erreicht, s.o.).
- **`POST /api/master/train` (v31→v33):** Master nimmt die neu-validierte TrendFollowEma legitim auf.
  - **Master-Fitness 0.607 → 0.631**
  - **`dir_edge` 0.0 → 0.0929** (gerichteter Sockel hat erstmals seit dem Re-Entry wieder eine echte Edge)
  - **gerichteter Anteil 0 % → 13.3 %** (mn_share 100 %→86.7 %); trend_up/trend_down = TrendFollowEma `profitable=True`.
  - MN-Sockel weiter **mono-MM** (CSM tot); `benchmark_1n` degeneriert (1 Engine).
- **Schluss:** Erster echter, sauber gegateter Fortschritt der Nacht — **kein Lockern**, sondern eine Strategie hat
  die Validierung ehrlich bestanden und der Master hat sie aufgenommen. `readiness` braucht weiter Tage (Paper-Stabilität).
- **Danach gestartet:** `night_train.py evolve` (Hintergrund, days=180/gen=2) — tiefere Mutationssuche nach weiteren OOS-Gewinnern.

### Runde 5 — evolve-Batch (~02:13– , bei PAUSE 4/10 fertig)
- **MeanReversionRsi evolve → `oos_validated=True` (+0.69 %)** ✅ — **zweiter** sauberer OOS-Fund der Nacht
  (neben validierter TrendFollowEma). TrendFollowEma −2.7 / MomentumMacd −15.4 / FuturesBreakoutVol −16.7 (alle False).
- **PAUSE durch Nutzer (~02:31 UTC):** keine neuen Runden mehr angestoßen. Der laufende evolve-Batch wurde NICHT
  forciert gekillt (Live-Maschine, Kill-Risiko) — er läuft die restlichen Strategien aus (resumable, proposal-only)
  und wird beim nächsten Einstieg ausgewertet. ScheduleWakeup-Loop beendet (nicht neu gesetzt).
- **Offen für nächsten Einstieg:** evolve-Vollergebnis sichten → bei neuen oos_validated `POST /api/master/train`
  (MeanReversionRsi-Edge ggf. aufnehmen) → Endmessung → Regime-Parameter-Proposal finalisieren.

## ZWISCHEN-BILANZ (bei Pause)
- **Master-Fitness 0.607 → 0.631** (v33), **`dir_edge` 0 → 0.093**, gerichteter Anteil **0 → 13.3 %** — durch ehrlich
  validierte TrendFollowEma. MN-Sockel weiter mono-MM (CSM real tot, nicht schöngerechnet).
- **2 oos_validated-Funde** (TrendFollowEma validate + MeanReversionRsi evolve) vs. Baseline 1.
- **Regime-konditionierter-Parameter-Trigger ERREICHT** (9 Zellen n≥100 / 3 Regime) — greenlight-fertige Proposal.
- Guardrails durchgehalten: proposal-only, 0 Echtgeld, `stats.sqlite`/`tradesv3_*` unberührt, Gates hart.

## OFFENE PROPOSALS (Nutzer-/World-Chat-Entscheid, NICHT autonom umgesetzt)
1. **Regime-konditionierte Parameter** (Trigger erreicht): Strategien je HMM-Regime ein/ausschalten + parametrisieren.
   Evidenz: FuturesBreakoutVol→trend_up, FuturesBbandsBounce→Trends; `regime_advice`-Heuristik auf per-Trade-Evidenz umstellen.
2. **FuturesMacdRsiScalp cullen** (durchweg negativ n≈1950, + optimize-500-Bug) — via Autopilot-Cull oder manuell nach Review.
3. **Scalper-optimize HTTP-500** separat debuggen (1m×14-Pairs-Backtest).
4. **Unverändert (Nachtlauf 1):** struktureller Simulations-Discount für MM (Sockel hängt an Monte-Carlo), neue real-data MN-Edge-Quelle.

