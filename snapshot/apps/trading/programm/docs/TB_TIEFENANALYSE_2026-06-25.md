# Trading Bot — Tiefenanalyse-Schleife (ab 25.06.2026)

> **Nutzer-Auftrag:** den Trading Bot „perfekt durchleuchten" — die einzelnen Funktionsmuster, das
> KI-Learning, **wie alles zusammenspielt, ob alles passt**. Modifizierte Endlos-Kernanalyse, fokussiert
> NUR auf TB (eigener Stack). Erfassen → Verstehen → Hinterdenken; ehrlich (Gesetz 2): lieber „0 Bugs +
> nächste Wertgrenze" als künstliche Funde. Sichere Code-Wins test-grün + committet; Live-Aktivierung
> gegated. Akkumuliert über Runden; jede Runde eine Ebene tiefer.

## Architektur-Landkarte (Erfassen) — das KI-Learning-Gefüge
```
Markt → tracker (HMM-Regime + Vola + Fundamental) ─┐
                                                    ├─ Bridge-Datei → MasterMeta-Engine (Live-Hebel/Sub-Logik)
meta.py (Lern-Herz):                                │
  • aggregate/proposals (regelbasiert, proposal)    │
  • run_optimization (anchored Walk-Forward)         │
  • run_evolution (anchored, QuantEvolve-light)      │
  • regime_advice / session_advice (empirisch-wenn-reif)
  • consistency (Echtgeld-Reife-Gate)                │
        │ persistiert Gewinner (oos_validated)        │
        ▼                                             ▼
stats (snapshots/validations/optimizations) → master.derive_policy (Ensemble:
  gerichtet PF-gated + MN-Sockel CSM/Pairs/StatArb/MM hart-gehärtet + HMM + Fundamental + Vol-Target)
        │ train_step (Ratchet + Re-Baseline)
        ▼
autopilot (Nachtlauf: evolve/optimize, proposal-only) · governor (Risk-Override) · runner (Prozesse)
```

## Runde 1 (25.06.) — Lern-Herz `meta.py` (Optimierung/Evolution/Regime-Advice) zeilennah
**Befund: 0 Bugs, hochwertige ML-Hygiene — ehrlich gegen Lookahead, Selektions-Bias und Overfit.**

- **`run_optimization` (anchored Walk-Forward):** Kandidaten (3 Anker + Random-Search-Sample) werden
  NUR auf dem **Trainings-Fenster** verglichen; der Gewinner wird **genau EINMAL** auf dem in der Selektion
  ungesehenen **Test-Fenster** geprüft. Nach außen zählen die **OOS-Zahlen** des Test-Fensters (nicht die
  Trainings-Werte). `confident`/`oos_validated` = Test bestanden (Profit>0 ∧ DD<50% ∧ Trades>0). `windows≤1`
  = reiner In-Sample-Vergleich → **nie** confident. ⇒ Kein best-of-N-Selektions-Bias; Auto-Apply nur OOS-validiert.
- **`_anchored_ranges`:** Train (älter) → **Embargo** (Default 1 T, gegen fenster-übergreifende Trades) → Test
  (jüngste ≥20 T). Sauberer anchored-WF-Schnitt.
- **`_opt_score`:** Komposit = Profit − Gewicht·|Drawdown| − Overtrade-Strafe (Multi-Objective; bestraft genau
  das Overtrading, das anderswo als Edge-Fresser identifiziert wurde). **`sample_params`:** Random-Search im
  [min,max]-Raum (Bergstra & Bengio 2012 — bei wenigen wirksamen Parametern besser als Raster). Solide.
- **`run_evolution`:** Mutation + Selektion über **alle** Generationen ausschließlich auf dem Trainings-Fenster
  (sonst kontaminierte die wiederholte Auswahl das Test-Fenster); finaler Gewinner **einmal** OOS-getestet,
  ehrliche OOS-Zahlen persistiert. Generationen-Vergleich über den **Trainings**-Score — die OOS-Zahlen fließen
  nie in die Generationen ein. Kein Test-Leak; OOS-Gate als Backstop gegen Overfit-Propagation.
- **`regime_advice`:** empirisch (Ø-Profit je Regime) NUR bei `n ≥ _MIN_ADVICE_N` ∧ `avg_profit > 0`, sonst
  regelbasiert (Strategie-Regime-Tag × Markt-Regime). Fallback-Hierarchie per-Trade → Tages-Aggregat →
  regelbasiert. ⇒ **kein Empfehlen auf dünnem/negativem Sample** (die „Daten-reifen"-Disziplin; = der frühere
  R2-Autopilot-Fix). `consistency` = Echtgeld-Reife-Gate (Historie + Ø nicht stark negativ + Trend + Stabilität).

**Hinterdenken (ehrlich):** Die zwei Lern-Loops sind State-of-the-Art-sauber. Die EINZIGE strukturelle Grenze
ist keine Schwäche des Codes, sondern die **Datenreife**: das Test-Fenster (≥20 T, intraday) kann bei jungen
Bots dünn sein → `oos_validated` bleibt meist False → nichts wird auto-angewandt. Das ist **korrektes**
Verhalten (lieber nichts anwenden als Overfit), nicht ein Bug. Mit wachsender Historie greift der Loop schärfer.

**Zusammenspiel-Urteil (Runde 1):** meta.py liefert die ehrlichen Lern-Signale (OOS-validierte Gewinner +
empirisches Regime-Advice), master.derive_policy verdichtet sie PF-gated mit dem MN-Sockel. Die Kette ist
**konsistent**: nichts Unvalidiertes trägt die gerichtete Allokation; der Master fällt defensiv auf den
MN-Sockel zurück. Passt.

## Runde 2 (25.06.) — Selbstverbesserungs-Orchestrierung `autopilot.py` + `_autopilot_step` + `governor.py`
**Befund: 0 Bugs. Die autonome Lern-/Risiko-Maschinerie ist textbook-sicher gegated — nichts kann
autonom Risiko ERHÖHEN oder Unvalidiertes ausrollen.**

- **`autopilot.py`** = reiner Scheduler (Default alle 6 h): serialisierter Step (`_step_lock`, skip wenn
  läuft), **exception-fest** (ein Fehler tötet den Daemon-Loop nie), Anlauf-Versatz (kein schwerer Backtest
  beim Boot), stop()/Config zeitnah (30 s Tick), Zustand+History in `autopilot.json`. Die Arbeit steckt im
  registrierten `step_fn` = `_autopilot_step`.
- **`_autopilot_step` (alle 6 h, 5 Teile je exception-ISOLIERT, bewusste Reihenfolge):**
  1. **`governor.run_once` ZUERST** — Risiko-Override, de-risk vor jeder Optimierung auf entgleister Lage.
  2. **`_mastermeta_improve`** — Master-Selbstverbesserung (train_step-Ratchet, proposal).
  3. **`_auto_upgrade_bots`** — wendet validierte Gewinner an, **DOPPELT HART GEGATET:** nur Bots mit
     `auto_upgrade=True` (per-Bot opt-in, nur nach 1× manuellem Upgrade), **Gate 1 `oos_validated`** (nur
     anchored-WF-bestätigte Gewinner, nie In-Sample-best-of-N), **Gate 2 Timeframe-Match**; idempotent,
     exception-fest pro Bot.
  4. **`cull.run_once`** — chronisch schlechte Demo-Bots auto-cullen (Learnings/DBs bleiben).
  5. **`_auto_validate_strategy`** — groundet je Tick EINE noch unvalidierte Engine per Walk-Forward
     (proposal-only, compute-bounded ~Minuten, No-op wenn alle abgedeckt). Schließt Recherche→Evidenz ehrlich.
- **`governor.run_once`** = der EINZIGE autonome Live-Bot-Mutations-Pfad — und **rein defensiv:** greift nur
  bei `breach` (harte Schwelle, getrennt von `warn`), Aktion ∈ {alert·derisk(schlechteste N stoppen)·pause(alle)},
  **MasterMeta via `protect_master` ausgenommen**, **nur `dry_run`-Bots**, **debounced** (`min_interval_h`),
  enabled-gated, identitäts-sicherer `runner.stop` (kein Kollateral-Kill), exception-isoliert pro Bot, Alerts
  (warn+Anomalien als robuster Z-Score ggü. Flotte) IMMER geloggt. ⇒ Kann Risiko **nur senken**, nie erhöhen.

**Zusammenspiel-Urteil (R2):** Die Self-Improvement-Schleife ist sicherheits-architektonisch vorbildlich —
**risk-first**, alle Auto-Aktionen sind entweder **defensiv** (Governor pausiert nur), **proposal-only**
(improve/validate) oder **hart OOS-/opt-in-gegated** (auto-upgrade). Kein Pfad kann autonom Exposure erhöhen
oder einen unvalidierten Gewinner live ausrollen. Passt — und ist erstaunlich diszipliniert für einen
autonomen Trading-Loop.

## Runde 3 (25.06.) — Regime-Anker `hmm.py` + Selbst-Cull `cull.py`
**Befund: 0 Bugs. Der Regime-Anker, von dem das ganze System abhängt, ist hochwertig + kausal.**

- **`hmm.py` — `fit` (Baum-Welch EM):** lehrbuch-korrekt + numerisch robust. Forward-Backward + xi-Akkumulation
  komplett im **Log-Space** (`_logsumexp`, kein Underflow); **Varianz-Boden** `max(vf, v)` (vf = max(1e-9,
  0.01·Gesamt-Varianz)) gegen die klassische EM-Degeneration (Zustand kollabiert auf 0-Varianz → ∞-Likelihood);
  alle Re-Estimation-Divisionen guarded (`denom>1e-12`, `gsum>1e-12`); deterministische Quantil-Init; Konvergenz-
  Break bei `|Δll|<tol`; Daten-Guard (`T<n_states·4 → None`). **`fit_mv`** (multivariat) mit **Dual-Init** gegen
  lokale EM-Optima.
- **`classify`:** Regime-Label per **Mittelwert-RANG** (niedrigster Zustands-Mittel-Return = trend_down, höchster =
  trend_up — robust gegen EM's beliebige Zustands-Nummerierung); `confidence` = `post_last[cur]` = **gefilterte**
  Posterior des aktuellen Zustands (für t=T identisch zur Smoothing-Posterior, also **kausal — kein Future-Leak**);
  `persistence` (Anteil letzte 12 Schritte im selben Zustand); **`_anticipate`** = nächstes Regime + `stay_prob`
  aus der HMM-Übergangszeile des aktuellen Zustands (speist die Master-Regime-Antizipation, A3). **Lookahead:** das
  HMM-Regime überschreibt live NUR die jüngste Kerze (master_meta `_hmm_regime_override`), Backtests nutzen das
  Schwellen-Regime ⇒ kein Lookahead im Live-Handel. `None` bei zu wenig Daten ⇒ Caller fallen sauber auf das
  Schwellen-Regime zurück.
- **`cull.py`:** Auto-Cull NUR wenn **ALLE** konservativen Bedingungen zusammen zutreffen (≥`min_days`(5) Historie ∧
  ≥`min_trades`(20) ∧ Ø-Profit ≤ −15% ∧ Equity-Trend ≤ −1%/Tag) ⇒ trifft nur **echte Dauer-Verlierer**, nie frische/
  kurz-schwache Bots. **MasterMeta geschützt**, nur `dry_run`, **Learnings bleiben** (nur `registry.delete_bot` ⇒
  stats.sqlite + Trade-DBs unberührt), debounced (12 h), exception-fest pro Bot, identitäts-sicherer `runner.stop`;
  `evaluate()` = read-only Verdikte für die UI-Transparenz.

**Zusammenspiel-Urteil (R3):** Der HMM-Regime-Anker ist die Eingabe für ALLES (regime_advice, derive_policy,
Antizipation, der Live-MasterMeta-Hebel via Bridge) — und er ist statistisch sauber, numerisch robust und kausal.
Das Selbst-Cull ist konservativ genug, dass es nie versehentlich gute/junge Bots verwirft und nie Wissen vernichtet.
Passt vollständig.

## Laufende Bilanz (R1–R3)
Lern-Herz (meta) · Selbstverbesserungs-Orchestrierung (autopilot/governor) · Regime-Anker (hmm) · Selbst-Cull —
**durchweg 0 Akut-Bugs, Architektur-KI-Niveau.** Das ist (Gesetz 2) das ehrlich erwartete Ergebnis bei diesem audit-gehärteten
Kern; die wiederkehrende „Fund-Klasse" ist nicht *Bug*, sondern die **Datenreife-Schranke** (alle Lern-Gates warten
korrekt auf Evidenz). Kein künstlicher Fund.

## Runde 4 (25.06.) — die Engines (Muster + Lookahead) + Backtest-Harness `engine.py`
**Befund: 0 Bugs. Die Lern-DATEN-Pipeline ist sauber — damit ist die KI-Learning-Kette end-to-end verifiziert.**

- **Engine-Muster-Konsistenz (alle 12 Strategien):** Spot-Engines (mean_reversion_rsi/momentum_macd/
  trend_follow_ema/grid_range/dca_dip/vwap_reversion) durchweg `process_only_new_candles=True`, `can_short=False`
  (spot-korrekt), KEIN `leverage`-Callback (spot braucht keinen), gemeinsamer `_opt()`-Env-Reader + `_apply_cooldown`-
  Overtrading-Bremse (opt-in, Default 0 = aus). Futures-Engines (5 + MasterMeta) zusätzlich `can_short`+`leverage`.
- **Lookahead-Freiheit:** **0× `shift(-N)`** netzweit (kein Zukunfts-Zugriff). Stichprobe `vwap_reversion` zeilennah:
  rein **rollierende Vergangenheitsfenster** (VWAP/dev_std), Crossover via `.shift(1)` (close[t]<Band ∧
  close[t-1]≥Band = echter Durchstich, kein Current-Bar-Trick), Entry ab der Folgekerze (freqtrade-Standard, kein
  Fill auf der Signal-Kerze) ⇒ strukturell lookahead-frei. Konsistent mit den 6 zuvor gelesenen Engines.
- **`engine.py` (Backtest-Harness, der die Lern-Loops füttert):** **`--cache none` in JEDEM param-injizierten Lauf**
  (run_backtest_with_params/range/walkforward) — mit Begründung: env-`TBT_OPT_PARAMS` ändern die Strategie-DATEI
  nicht, ohne `--cache none` würde freqtrade ein veraltetes Cache-Ergebnis servieren (die dokumentierte Falle,
  überall korrekt). `_BT_LOCK` serialisiert (kein Clobbering paralleler Läufe auf gemeinsamen Daten). Großzügiger
  Timeout (1800 s) + `TimeoutExpired`-Catch (der anchored Loop ruft ohne per-Call-try → ein ungefangener Timeout
  würde sonst `run_optimization`/`run_evolution` als HTTP 500 sprengen). returncode≠0 → graceful `{ok:False}`.
  `ensure_data` lädt die Kerzen EINMAL (Mehrfach-Backtests des Lern-Loops laden nicht je Kandidat neu = effizient).

**Zusammenspiel-Urteil (R4):** Schließt die KI-Learning-Kette: die Lern-ALGORITHMEN (R1) sind sauber, die
ORCHESTRIERUNG (R2) hart gegated, der REGIME-Anker (R3) kausal — **und die DATEN, auf denen gelernt wird (R4),
sind cache-sauber + lookahead-frei.** Ein Overfit-Kandidat kann also nicht durch verschmutzte/zukunfts-kontaminierte
Backtest-Daten „glänzen"; das OOS-Gate sieht ehrliche Zahlen. End-to-end: **es passt.**

## ★ Zwischen-Fazit (R1–R4) — die KI-Learning-Kette ist end-to-end verifiziert
Lern-Algorithmen (meta: anchored-WF/Evolution/Regime-Advice) · Orchestrierung (autopilot/governor: risk-first,
proposal/defensiv/OOS-gegated) · Regime-Anker (hmm: korrektes Baum-Welch, kausal) · Engines + Backtest-Harness
(lookahead-frei, cache-sauber) ⇒ **durchweg 0 Akut-Bugs, Architektur-KI-Niveau.** Das Lernen ist ehrlich, kann nichts
Unvalidiertes/Zukunfts-Kontaminiertes ausrollen, und das Risiko nur senken. Die einzige Grenze bleibt die
**Datenreife** (korrekt durch die Gates abgebildet) — kein Code-Mangel.

## Runde 5 (25.06.) — MN-Sockel-Lern-Loop `mn_learn.py` + Gewinner-Anwendungspfad
**Befund: 0 Bugs, exemplarisch ehrlich — inkl. eines Regressions-Gates, das viele Systeme verpassen.**

- **`mn_learn.walk_forward` (generischer anchored WF für CSM/Pairs/StatArb/MM):** Selektion (bester Ø-Sharpe,
  Tie-break robusterer Worst-Case) NUR auf den älteren Folds; der **jüngste Fold bleibt ungesehen** und testet
  EINMAL nur den Gewinner → `oos_sharpe`/`oos_validated` (Sharpe>0). `equal_folds` reduziert `windows`, wenn ein
  Fold sonst <90 T würde (statistische Aussagekraft). **★ REGRESSIONS-GATE:** wird `baseline` (= laufende
  Engine-Config) übergeben, wird sie auf DEMSELBEN ungesehenen OOS-Fold bewertet — `apply_recommended` verlangt
  zusätzlich, dass der Gewinner die **laufende Config dort schlägt** (`improved_vs_current`), nicht nur OOS-positiv
  ist. ⇒ kein ökonomisch schlechterer Parametersatz wird als anwendbarer „Gewinner" gelabelt (Doc zitiert den
  realen Fall: CSM-Winner OOS-positiv, aber über Voll-Historie schwächer). Subtil + wichtig — selten so sauber.
- **`_apply_learned_params` (DRY-Kern aller Apply-Pfade):** **MERGE statt REPLACE** — die Basis-Identität bleibt
  (bei `SessionOpenBreakout` wird die `session` London/US/Asia NIE überschrieben); Version++, optionaler Bot-
  Neustart (Engine liest `TBT_OPT_PARAMS` neu), Changelog (`record_upgrade`).
- **`bot_apply_opt` (manueller Apply):** wendet den letzten Gewinner an + schaltet `auto_upgrade` scharf (das
  per-Bot-opt-in aus R2). **Ehrlich:** warnt explizit, wenn der Gewinner KEINE OOS-Validierung hat („manuell
  erlaubt, aber Overfit-Risiko") und bei Timeframe-Abweichung. ⇒ der manuelle Pfad ist transparent über das Gate,
  das er bewusst überspringen lässt; der AUTO-Pfad bleibt hart gegated.

**Zusammenspiel-Urteil (R5):** Der komplette Lernen→Anwendung-Weg ist an jeder Stelle ehrlich + sicher: Lernen
(meta/mn_learn) liefert OOS-validierte, regressions-geprüfte Vorschläge → manueller Apply (Nutzer-Override mit
Warnungen) ODER Auto-Apply (oos_validated+TF+opt-in) → `_apply_learned_params` (identitäts-erhaltend, Version,
Changelog, Neustart). Nichts überschreibt die Bot-Identität, nichts wendet Unvalidiertes ohne explizite Nutzer-
Aktion an. Passt vollständig.

## Runde 6 (25.06.) — Daten-/Lern-Persistenzschicht `stats.py`
**Befund: 0 Bugs. Saubere Trennung „Bot-Live-Trade-DBs (read-only) vs. Lern-Gedächtnis (stats.sqlite)".**

- **`_ro_connect` (zentrale Sicherheit):** jeder Lese-Zugriff auf eine vom freqtrade-Prozess beschriebene
  `tradesv3_<id>.sqlite` läuft über `sqlite3.connect("…?mode=ro", uri=True)` — **echt read-only**: keine
  Write-Lock-Interaktion mit dem schreibenden Bot-Prozess, kein versehentliches Anlegen/Schreiben. ⇒ das Backend
  kann die Live-Trade-Daten der Bots **nicht** korrumpieren. Alle Read-Pfade (bot_pnl/equity_curve/recent_trades/
  open_positions/closed_trades_for_regime/execution_costs) nutzen es; `con.close()` im finally, Exception→graceful.
- **`_conn` (stats.sqlite):** Schema-Init via Double-Checked-Locking (`_inited`+`_init_lock`, einmal/Prozess);
  `_migrate` = idempotente additive ALTERs (`try/except sqlite3.OperationalError`) — Alt-DB-restart-sicher.
  *(Hinweis: stats.sqlite hat genau EINEN Schreiber = das Backend; die Bots schreiben nur ihre EIGENEN
  tradesv3-DBs ⇒ keine Multi-Writer-SQLITE_BUSY-Contention auf stats.sqlite. Kein busy_timeout-Bedarf hier.)*
- **`bot_pnl`:** ehrlich — `profit_abs` = Summe `close_profit_abs` **nur geschlossener** Trades (realisiert, kein
  unrealisierter Open-Profit), `profit_pct` relativ zum Demo-Wallet; parametrisierte SQL (kein Injection),
  `since_days`-Filter nur auf geschlossene Trades (offene bleiben aktuell), graceful.
- **`reset_bot_trades` (einzige destruktive Op):** löscht NUR die Trade-DB (+WAL/SHM, freqtrade legt sie leer neu
  an), **Lern-Tabellen (snapshots/validations/optimizations/ledger) bleiben unberührt**, exception-fest pro Datei.
  Der Endpunkt `reset_bot_stats` hält die dokumentierte Vorbedingung ein: **`was_running` → stop → reset → start**
  (kein Race auf der offenen DB), auditiert.

**Zusammenspiel-Urteil (R6):** Die Persistenz ist die saubere Grundlage des ganzen Lernens — die Bots' Geld-/
Trade-Daten sind read-only-geschützt, das Lern-Gedächtnis (stats.sqlite) ist der einzige beschreibbare Speicher
(ein Schreiber, idempotente Migrationen), und die einzige Lösch-Operation ist gegen die Lern-Tabellen UND gegen
Races abgesichert. Passt.

## Runde 7 (25.06.) — Risiko-/Fundamental-Schicht (`risk.py` · `fundamental.py` · `concentration.py`)
**Befund: 0 Bugs. Harte Limits sauber, externer Overlay fail-safe + nur risiko-senkend, Klumpen-Analyse read-only.**

- **`risk.py`:** reine Hard-Limit-Evaluatoren — global (Drawdown ≥ Limit ODER Kapital > Cap → `kill_switch`) +
  per-Bot (Tagesverlust/Drawdown/Trades-pro-Tag aus `RiskParams` → `kill_switch`). Seiteneffektfrei, klare
  Schwellen, liefern nur das Signal (der Loop/Governor handelt darauf).
- **`fundamental.py` (externer Daten-Overlay) — fail-safe + defensiv:** `fetch_calendar` mit geordnetem Fallback
  **frischer Cache → live (10 s-Timeout) → stale Cache → Seed-Kalender** (deterministisch FOMC-first-Friday/CPI/NFP),
  **key-frei**, wirft NIE nach außen (alle Exceptions gefangen). ⇒ ohne Netz arbeitet das Event-Risiko aus dem
  Seed weiter. `event_risk` vorausschauend (high = im pre/post-Fenster, elevated = nächstes HI-Event im Vorfeld),
  proximitäts- + event-typ-gewichtete Dämpfung (FOMC>CPI>NFP, näher=stärker). **`dir_scale` nur ≤1** („senkt nur
  Risiko"). Speist `master._fundamental_overlay.total_scale` (dort try/except-gewrappt → 1.0 bei Fehler) UND den
  Bridge-`lev_scale` → der ganze Fundamental-Pfad kann den Hebel/gerichteten Sleeve nur DÄMPFEN, nie anheben.
- **`concentration.py`:** read-only Klumpen-/Korrelations-Analyse — `_live_exposure` summiert per-Asset/Cluster
  das Notional×Hebel aus **read-only** `open_positions`-Reads (HHI-artig, „das ehrliche Klumpenrisiko"); schreibt
  NUR die eigene Config (Cluster/Schwellen), KEINE Bot-/Trade-Mutation, kein runner-Eingriff. Reine Monitoring-Sicht.

**Zusammenspiel-Urteil (R7):** Die Risiko-Schicht ist dreistufig sauber getrennt — **harte Limits** (risk.py, Signal),
**autonome Reaktion** (governor R2, defensiv), **vorausschauender Overlay** (fundamental, fail-safe + nur senkend),
**Transparenz-Sicht** (concentration, read-only). Kein Risiko-Pfad kann autonom Exposure ERHÖHEN. Passt.

## ★ Zwischen-Fazit (R1–R7) — KI-Learning + Risiko end-to-end durchleuchtet
Lern-Algorithmen · Orchestrierung · Regime-Anker · Engines/Backtest-Daten · Lernen→Anwendung · Persistenz ·
Risiko/Fundamental = **durchweg 0 Akut-Bugs, Architektur-KI-Niveau.** Das ist (Gesetz 2) das ehrlich erwartete Ergebnis
dieses audit-gehärteten Kerns; KEINE künstlichen Funde. Wiederkehrendes Muster: jede autonome Aktion ist
**proposal-only, defensiv (nur risiko-senkend), oder hart OOS-/opt-in-gegated**; die einzige reale Grenze ist die
**Datenreife** (alle Gates warten korrekt auf Evidenz).

## Runde 8 (25.06.) — Frontend↔Backend-Vertrag + MCP-Connector + Netz-Anbindung
**Befund: 0 Bugs. Vertrag konsistent, externe Flächen strikt read-only, Netz-Sender HITL/fail-safe.**

- **Routen↔UI-Abgleich (99 Routen vs. 52 UI-Calls, sauber in Python):** **0 echte Phantom-Calls.** Die 5
  scheinbaren (`/api/settings`, `/api/settings/schema`, `/api/vault`, `/api/actions`, `/api/ki/frage`) sind
  **appkit-Vertrag-Routen**, die `vertrag.install_vertrag(app)` (main.py:41) mountet — nicht als `@app.get` in
  main.py, daher im Roh-Grep „fehlend", aber real vorhanden (SSO/Vault/HITL-Actions/Mini-Dizzi). Die 5 „toten"
  Routen sind real definiert + extern genutzt: `/api/risk` (Read-Endpoint), `/api/wissen/suche` (V11-Netz-
  Rück-Lese), `/api/component/*` (UI-Builder-Tool-Protokoll). ⇒ kein toter/falscher Vertrag.
- **MCP-Connector (`mcp_tools.py`):** 6 Tools, **ausnahmslos read-only GETs** (flotte/master/mastermeta/governor/
  konzentration/alerts), Namensraum `tradingbot_`; explizit „kein Tool startet/stoppt/ändert Trading; Echtgeld-
  Gate unberührt." EINE Quelle für stdio-MCP-Server (Core-Agent) + per-App-Gateway. Die externe Agenten-/Netz-
  Fläche kann den Handel **nicht** beeinflussen.
- **Netz-Sender V11 (`report.py` Trading→Memory):** baut Markdown-Report, legt ihn **best-effort** via Core-Relay
  in Memory ab. **HITL: NUR auf expliziten Nutzer-Knopf (`explizit=True`) — kein Auto-Versand.** **Wirft NIE** in
  den Trading-/HTTP-Pfad (best-effort gewrappt). `sensibel:True` IMMER (Trading=hoechst ⇒ Memory-KI lokal_only).

**Zusammenspiel-Urteil (R8):** Die Außen-/Netz-Schicht ist konsistent + dicht: der Vertrag stimmt, die MCP-/Agenten-
Fläche ist strikt lesend (kann nie handeln), der einzige ausgehende Daten-Pfad (V11) ist HITL-gated + fail-safe +
sensitivitäts-korrekt. Passt.

---

## ★★ GESAMT-FAZIT — Trading Bot end-to-end durchleuchtet (R1–R8, 25.06.2026)
**Über die GANZE Tiefe — KI-Learning, Funktionsmuster, Zusammenspiel — durchweg 0 Akut-Bugs, Architektur-KI-Niveau.**
Abgedeckt zeilennah:
1. **Lern-Algorithmen** (meta: anchored Walk-Forward + Evolution + Regime-Advice) — OOS-gated, kein Selektions-Bias.
2. **Selbstverbesserungs-Orchestrierung** (autopilot/governor) — risk-first, defensiv/proposal/hart-gegated.
3. **Regime-Anker** (hmm: Baum-Welch korrekt, numerisch robust, kausal).
4. **Engines + Backtest-Daten** (12 Strategien lookahead-frei, engine.py cache-sauber).
5. **Lernen→Anwendung** (mn_learn Regressions-Gate, _apply_learned_params MERGE/identitäts-erhaltend).
6. **Persistenz** (stats.py: Trade-DBs read-only, Lern-DB einziger Schreiber, sichere Reset-Op).
7. **Risiko/Fundamental** (risk hard-limits, fundamental fail-safe+nur-senkend, concentration read-only).
8. **Vertrag/MCP/Netz** (konsistent, MCP strikt read-only, V11 HITL/fail-safe).

**Durchgängiges Prinzip (warum „es passt"):** JEDE autonome Aktion ist entweder **proposal-only**, **defensiv
(senkt nur Risiko)** oder **hart OOS-/opt-in-gegated**; nichts kann autonom Exposure erhöhen, Unvalidiertes
ausrollen, die Bot-Identität überschreiben, die Live-Trade-Daten korrumpieren oder über die MCP-/Netz-Fläche
handeln. Die EINZIGE strukturelle Grenze ist die **Datenreife** (kein Code-Mangel — die Gates warten korrekt auf
Evidenz; bis ≥90 T Historie + ≥3 Regime validiert keine konditionale gerichtete Edge).

## Runde 9 (25.06., autonom) — operative/Infra-Schicht I: `execution.py` + `universe.py`
**Befund: 0 Bugs. Reine read-only/Config-Module ohne Risiko-Fläche (ehrliche Ergänzung zum Kern-Fazit:
der KI-Learning-KERN war R1–R8 durch, ein paar OPERATIVE Module waren noch frische Lese-Fläche).**
- **`execution.py` (Slippage/Kosten-Tracking, M6-Prep):** `execution_for` read-only aus den geschlossenen
  Trades (via `stats.execution_costs`→`_ro_connect`): Ø/worst Slippage+Fee+Cost in bps, **Trend** (jüngstes
  Fenster − Baseline = steigende Slippage/sinkende Liquidität), Flags auf Schwellen. Schreibt nur eigene Config.
  Im Dry-Run Slippage ~0 (Fill=angefordert) — die Messung ist die ehrliche M6-Vorbereitung.
- **`universe.py` (Pair-Auswahl):** `candidates_for`/`number_assets_for` = reine, deterministische Auswahl aus
  dem kuratierten, liquiditäts-gestaffelten 14-Coin-Universum (Tier1/2/3). `pairlists_for` = freqtrade-Kette
  StaticPairList → **VolumePairList** (Top-N nach 24h-quoteVolume, 30-min-Refresh) → **SpreadFilter**
  (`max_spread_ratio` 0.5% = Ausführungs-/Slippage-Schutz). Keine Mutation, keine DB.

## Runde 10 (25.06.) — operative/Infra-Schicht II: maintenance/integration/alerts/sessions
**Befund: 0 Akut-Bugs, aber der ERSTE nicht-triviale Fund der ganzen Analyse (latent, low-severity).**

- **📋 FUND (latent, Facette 4/6) — `maintenance.compact_snapshots`/`compact_market` Rollup-Überschreibung:**
  Der Monats-/Tages-Rollup nutzt `INSERT … ON CONFLICT(bot_id,month) DO UPDATE SET … = excluded.*` —
  d. h. er **ersetzt** den Aggregat-Wert mit dem Aggregat NUR der aktuellen `old`-Charge (Roh-Zeilen `< cutoff`).
  Bei **inkrementeller** Verdichtung (Cutoff wandert; derselbe Monat wird über mehrere Läufe rollupt) gehen die
  früheren Tage verloren → `avg_profit_pct`/`n_days`/`avg_winrate`/`trades_closed`/`max_drawdown` des Monats
  spiegeln dann nur die LETZTE Charge (`last_equity`=letzter Wert ist hingegen korrekt). **LATENT, nicht aktiv:**
  `compact` läuft NIE automatisch (nicht im Autopilot-Tick/kein Scheduler; `/api/maintenance/run` Default
  `dry_run=True`, `integration.command` Default `dry_run=True`) — der Fehler manifestiert sich nur bei
  **wiederholtem manuellem** `dry_run=false` über einen Grenz-Monat. **Roh-Daten (jüngste) + Lern-Tabellen
  (validations/optimizations/ledger) sind NIE betroffen** (rollup-vor-delete, nur disposable Snapshots).
  - **✅ GEFIXT 25.06. (Nutzer-Freigabe, test-grün):** Der Cutoff wird jetzt auf die **Perioden-Grenze gesnappt**
    — `compact_snapshots` auf den **Monatsanfang** (`.replace(day=1)`), `compact_market` auf **Tages-Mitternacht**
    (`.replace(hour=0,…)`). ⇒ nur VOLLSTÄNDIGE (ganz ältere) Perioden werden rollupt; jede Periode genau EINMAL &
    vollständig → die `excluded.*`-Ersetzung ist korrekt UND idempotent. + Regressionstest
    `test_compact_snapshots_only_complete_months` (Grenz-Monat bleibt komplett roh; wäre auf dem alten Tages-Cutoff
    durchgefallen). 387 Tests grün. Backend-Code — greift live beim nächsten Server-Neustart (compact läuft ohnehin
    nur auf manuellen Trigger).
- **Sonst sauber:** `prune_orphans` löscht nur `backtest_runs` verwaister Bots (Lern-Tabellen unberührt),
  dry_run-default, audited. `integration.py` `state` = read-only Health-Descriptor (`health:"ok"`+Metriken),
  `command` dry_run-default-True. `sessions.py` = reine Zeit→Session-Abbildung (kanonische Bänder/Open-Fenster,
  pure). `alerts.py` = read-only Health-/Alert-Aggregation (data_feed/operational, nach Level sortiert).

**Zusammenspiel-Urteil (R10):** Die Infra-Schicht ist sauber; der eine latente Rollup-Fund betrifft nur den
verdichteten Monats-VIEW unter manueller wiederholter Compaction — kein aktiver Pfad, keine Roh-/Lern-Daten,
kein Geld-Pfad. ⇒ als Backlog-Item für den Nutzer (low-prio), nicht nacht-autonom gefixt.

## ★★★ TB-LESE-FLÄCHE VOLLSTÄNDIG (R1–R10) — Endbilanz
Alle substanziellen + operativen TB-Module zeilennah gelesen: **0 Akut-Bugs**, **1 latenter low-severity-Fund
gefunden UND ✅ gefixt** (maintenance-Rollup-Überschreibung → Perioden-Snap, 387 Tests). Der KI-Learning-Kern + das Zusammenspiel sind ehrlich verifiziert
(jede autonome Aktion proposal-only/defensiv/hart-gegated; einzige Grenze = Datenreife). „Ob alles passt" → **ja**,
mit dem einen notierten Lifecycle-Detail.

## ★ Ab R11 = ANTI-LEERLAUF (§0.6) — Lese-Fläche erschöpft, NICHT re-scannen

## ★ Ab R11 = ANTI-LEERLAUF (§0.6) — Lese-Fläche erschöpft, NICHT re-scannen
Die substanziellen TB-Module sind jetzt zeilennah abgedeckt. Re-Scannen derselben sauberen Kerne wäre Selbstzweck.
Der reale Wert liegt ab hier in **gegateten Wert-Hebeln** (Nutzer-Freigabe), nach Hebel sortiert:
1. **≥90-Tage-Re-Test der konditionalen Edges + CSM-`vol_scaled`** — der eigentliche „Daten-reifen"-Meilenstein
   (a-priori OOS-Sharpe 0.86→1.88); erst dann kann überhaupt eine gerichtete Edge PF>1 validiert werden + der
   Master gerichtet tragen statt sich defensiv auf den MN-Sockel zu stützen. **Daten-blockiert bis die Historie reift.**
2. **Expectancy→Hand voll wirken lassen** — `vol_target_pct` beobachten/nachtunen + (mit Reife) Sizing-Empfehlungen
   selektiv anwenden; D1-Exposure-Scale unter echten Vola-Spikes beobachten.
3. **MN-Paper-Bot-Forward-Track** — Kalender-PnL der Paper-Bots über Tage akkumulieren (ehrlicher OOS-Live-Test der
   MN-Sockel-Sharpes, parallel zur Sim).
4. **Short-Validierung** — sobald genug Short-Trade-Historie da ist, die neuen Short-Spiegel per Walk-Forward gegen
   die Long-Seite gegenchecken (entstehen Shorts profitabel im Abwärts-Regime?).
Diese sind NICHT nacht-autonom umsetzbar (Geld-System/Daten-Reife/Freigabe) ⇒ die Schleife meldet ehrlich
Konvergenz und wartet auf Nutzer-Input bzw. die Datenreife, statt weiter „0 Bugs" zu re-bestätigen.
