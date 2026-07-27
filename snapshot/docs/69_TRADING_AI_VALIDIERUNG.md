# docs/69 — Trading-AI-Struktur-Validierung (READ-ONLY Review, 04.07.2026)

> **Auftrag:** Validierung der GESAMTEN KI-Entscheidungsstruktur des Trading-Bots (Dizz Trading :8137)
> mit Schwerpunkt auf den zwei neuesten, bislang un-reviewten Ebenen **T5 Politik→Hand** (FP-T5,
> `suggested_policy.json`) und **Kelly-Sizing** (FP-2, `suggested_sizing.json`) sowie der
> Gesamt-Komposition Regime→Strategie→Sizing→Order-Hand.
> **Charakter:** reine Lese-Analyse + read-only Test-Bestätigung. **KEIN Code geändert, :8137 NICHT
> angefasst, kein Live-Lauf, T5-Backend-Schlüssel (`data/policy_bridge.json`) unangetastet.**
> **Reviewer:** Architektur-KI (frischer Chat, Worktree `wt-trading-val`, Branch `chat/trading-validierung`,
> Basis master `f856ad9`). Alle Datei:Zeile-Belege beziehen sich auf diesen Stand
> (identisch mit dem Live-Checkout, Baum sauber).

## 0 · Ergebnis in einem Satz

**Die KI-Entscheidungsstruktur ist tragfähig und diszipliniert gebaut: 0 kritische und 0 hohe
Befunde — die T5-/Kelly-Klemmketten sind lückenlos fail-closed gegenüber Echtgeld und Überhebelung
(beidseitige dry_run-Gates, Faktor ≤ 1, Whitelists, Zwei-Schlüssel real), die Mathematik (Kelly,
Water-Filling, HMM-Baum-Welch, PSR) ist korrekt; 2 mittlere Befunde betreffen (a) eine faktisch
unzutreffende Begründungs-Aussage zur Governor-Kadenz in der T5-SPEC und (b) den einzigen
risiko-ERHÖHENDEN KI-Pfad (D1-Hebel-Skalierung), der als einziger kein eigenes dry_run-Gate trägt —
beides heute ohne Wirkung (dry_run flottenweit, Echtgeld-Transfer real blockiert), beides vor M6 zu
härten.**

Der beim nächsten :8137-Neustart scharf werdende Zustand (T5-Backend-Schlüssel im apply-Modus,
Engine-Schlüssel offen) ist **sicher**: bis zum expliziten Setzen von `use_policy_bridge=1` am
MasterMeta-Bot bleibt das Verhalten byte-identisch (heute reproduzierter Beleg V1–V5).

## 1 · Scope & Methode

**Geprüft (Code-Stand master `f856ad9`):**

| Ebene | Module | Prüffrage |
|---|---|---|
| T5 Politik→Hand | `backend/app/policy_bridge.py` (voll) · `engine/user_data/strategies/master_meta.py` (voll) | Klemmkette T0–T3 lückenlos? Zwei-Schlüssel umgehbar? dry_run fail-closed? |
| Kelly-Sizing FP-2 | `backend/app/sizing.py` (voll) · `backend/app/stats.py` (Expectancy-Kern) | Kelly-Mathe korrekt? K0–K6-Reihenfolge? Defaults inert? Überhebel möglich? |
| Regime-Ebene | `backend/app/hmm.py` (voll) · `backend/app/tracker.py` (Bridge-Writer + Klassifikation) | log-space Baum-Welch korrekt? Fehlklassifikation kaskadiert? |
| Politik/Gehirn | `backend/app/master.py` (voll) · `backend/app/meta.py` (Anchored-WF/Selection-Bias) · `backend/app/mn_base.py` (PSR) | Bestauswahl-Logik, profitable-Gate, Literatur-Fundierung |
| Order-Pfad/Gates | `main.py` (`_autopilot_step`, Watchdog) · `governor.py` (voll) · `concentration.py` (via Aufrufer) · `runner.py` (Env + stop/start) · `transfer.py` | Reihenfolge Governor→Sizing→Policy; Echtgeld-Gate; Watchdog-Interferenz |
| Live-Zustand (read-only) | `data/policy_bridge.json` · `data/sizing.json` · `data/bots.json` | Zwei-Schlüssel-Ist? Was wird beim nächsten Neustart wirklich scharf? |
| Belege/Tests | `test_policy_bridge.py` (33) · `test_kelly_clamps.py` (21) · `test_sizing_bridge.py` (10) · `test_kelly_ruin.py` · `test_policy_sim.py` · `engine_policy_verify.py` | Decken die Tests die Invarianten real? Laufen sie grün? |

**Methode:** adversarielle Zeilen-Lektüre mit expliziten Angriffshypothesen (Order ohne Klemme ·
stilles Default · Zwei-Schlüssel-Umgehung · Kelly-Überhebel · manipulierte/NaN-Payloads ·
Regime-Kaskade · Watchdog-macht-Governor-rückgängig) + Gegenrechnung der Mathematik (Kelly-Formel,
Water-Filling-Fixpunkt, Baum-Welch-Rekursionen, PSR-Formel) + read-only Test-Läufe:

- **Backend-Suite: 474 passed in 25.75s** (TB-venv `programm/.venv`, `TBT_NO_STARTUP=1`,
  `PYTHONPATH=packages`, 04.07.2026) — exakt der dokumentierte Soll-Stand.
- **`engine_policy_verify.py`: ALLE 5 VERIFIKATIONEN PASS** (Engine-venv, pandas 3.0.3, seed 7,
  n=800; 04.07.2026 unabhängig reproduziert; Skript räumt seine `_verify_*`-Scratch-Datei selbst auf):
  V1 ohne Opt-in byte-identisch trotz gültiger apply-Datei · V2 proposal ⇒ byte-identisch ·
  V3 L1-Entries EXAKT auf unabhängig nachgerechneter Soll-Maske (`pol_`-Tags) · V4 L3 ⇒ 0 Entries ·
  V5 L2 55→44.0 (×0.8), min_stake klemmt zuletzt, ohne aktives Regime no-op.

## 2 · Befunde nach Schwere

**Kritisch: 0. Hoch: 0.** (Ehrliches Ergebnis nach gezielter Suche — die Angriffshypothesen aus §1
wurden alle durchgespielt und scheitern an den Klemmen; Belege in §3.)

### Mittel

**M-1 · SPEC-Begründung „Governor-Schutz sofort wirksam" ist faktisch unzutreffend (Governor-Kadenz = 6 h).**
`POLICY_HAND_SPEC.md` §4 begründet den 25200-s-TTL-Entscheid u. a. mit: *„Governor-Schutz bleibt
unabhängig sofort wirksam (er pausiert Bots selbst)."* Tatsächlich wird `governor.run_once` (der
einzige eingreifende Pfad) nur an zwei Stellen aufgerufen: im Autopilot-Tick
([main.py:1330](../apps/trading/programm/backend/app/main.py)) — Default-Intervall **6 h**
(`autopilot.py:25`) — und manuell via `POST /api/governor/run` (main.py:1482). Eine zwischen zwei
Ticks entstehende Breach-Lage bleibt also bis zu ~6 h ohne Governor-Eingriff (De-Risk/Pause);
in dieser Zeit schützen nur die per-Trade-Stoplosses der Bots (z. B. MasterMeta −4 %,
master_meta.py:217) und Handeingriffe.
**Warum trotzdem kein Hoch:** die Akzeptabilität des TTL-Entscheids stützt sich im selben SPEC-Satz
zusätzlich auf „Bridge-Inhalt ausschließlich defensiv (≤1)" — und DAS stimmt (Belege §3.3); zudem
ist die 6-h-Kadenz eine seit jeher bestehende Eigenschaft, kein T5-Regress, und alles ist dry_run.
**Repro-Skizze:** Drawdown-Schwelle reißt um 12:01, letzter Tick war 12:00 ⇒ `governor_breach` wird
erst ~18:00 auditiert/enforced; die apply-Bridge von 12:00 bleibt bis dahin gültig (mode=apply, da
zum Schreibzeitpunkt ok).
**Empfehlung (E-1, §7):** Governor-Kadenz entkoppeln (eigener 15-min-Loop oder Anhängen an den
10-min-Resume-Watchdog) UND/ODER den SPEC-Satz korrigieren. Der Code-Fix ist S-Aufwand und macht
die TTL-Begründung rund.

**M-2 · D1-Hebel-Pfad ist der einzige risiko-ERHÖHENDE KI-Pfad — und der einzige ohne eigenes dry_run-Gate (M6-Härtungspflicht).**
`MasterMeta.leverage()` ([master_meta.py:272–303](../apps/trading/programm/engine/user_data/strategies/master_meta.py))
skaliert den Futures-Hebel mit der **HMM-Konfidenz** von `base_leverage` (5) bis `max_leverage`
(10): `lev = base + (maxl − base) · conf`. Das ist bewusst so gebaut (D1, „aggressiv,
regime-bewusst", dokumentiert) — aber im Kontrast zu den FP-2-/T5-Brücken: (a) **kein
dry_run-Gate** (die Regime-Bridge `hmm_regime.json` wird auch bei `dry_run=False` konsumiert,
ebenso der Regime-Override in `populate_indicators`), (b) **kein absoluter Code-Cap** —
`maxl` kommt aus `opt_params` und wird nur durch freqtrades `max_leverage`-Argument (Exchange-Limit,
bei Krypto-Futures z. T. 50–125×) gekappt; der per-Bot-Hebel-Deckel `TBT_LEVERAGE` 1–5
(runner.py:104) gilt nur für die anderen Engines, nicht für diesen Pfad.
**Heute nicht ausnutzbar:** Flotte 100 % dry_run (bots.json verifiziert), Echtgeld-Transfers real
blockiert (transfer.py: confirm-Pflicht + kein Transfer-Key, „Bewusst blockiert"), `maxl` ist ein
von Menschen gesetzter Lernparameter (aktuell 10, bots.json), und die Konfidenz ist konstruktiv
∈ [0,1] (HMM-Posterior + Engine-Klemme `max(0, min(1, conf))`).
**Aber:** die Auftragsfrage „kann die KI-Ebene je eine unsichere Order erzeugen?" hat genau hier
ihre einzige strukturelle Restantwort: dies ist der einzige Pfad, auf dem ein KI-Signal das Risiko
ERHÖHT statt nur dämpft — er muss VOR M6 (Echtgeld) denselben Gate-Standard bekommen wie die
Brücken. **Empfehlung (E-2, §7):** dry_run-Gate für Konfidenz-AUFschlag + harter Code-Cap
(z. B. 10) in `leverage()`; die rein dämpfenden Faktoren (`lev_scale`, `exposure_scale`) dürfen
gate-frei bleiben.

### Niedrig

**N-1 · Risk-Kontext-Lesefehler sind fail-open statt fail-closed (bewusst, dokumentiert — aber verschärfbar).**
`policy_bridge._risk_context` (policy_bridge.py:206–217) und `sizing.portfolio_plan`
(sizing.py:379–386) behandeln Exceptions beim Lesen von Governor/Konzentration als
`("ok", False)` — die Brücke schriebe dann im apply-Modus weiter, statt zu degradieren, und
K5/K6-Freezes entfielen. Die Docstrings begründen das („die Brücke ist Empfehlung, nicht Wächter"),
und die Wirkung ist durch Faktor ≤ 1 + `max_stake`-Kappe begrenzt; getestet ist das Verhalten
sogar explizit (`test_portfolio_plan_defensive_on_advisor_errors`). Dennoch wäre für die
apply-Betriebsart die konservativere Wahl: Governor-Lesefehler ⇒ `mode='proposal'`
(fail-closed). **Empfehlung E-3** (S-Aufwand, eine Zeile je Stelle + Testanpassung).

**N-2 · Regime-Bridge wird nicht atomar geschrieben (Inkonsistenz zum Brücken-Standard).**
`tracker.write_regime_bridge` (tracker.py:39–48) schreibt `hmm_regime.json` per direktem
`write_text` — Policy-/Sizing-Bridge nutzen `jsonstore.write_atomic` (tmp + `os.replace`, atomar
auf NTFS). Ein Torn-Read führt engine-seitig zu `None` (fail-safe) — verliert für diese eine Kerze
aber auch die DÄMPFER (`lev_scale`/`exposure_scale`; Konfidenz-Fallback 0.5 = Mittel-Hebel statt
ggf. niedrigerem Datei-Wert). Mini-Fenster (Writer ≤ 1×/h, Datei winzig), begrenzt durch den
`maxl`-Cap. **Empfehlung E-4:** auf `write_atomic` umstellen (1 Zeile).

**N-3 · Rollback-/Config-Flip-Latenz ist in der SPEC missverständlich formuliert.**
SPEC §3: Hebel „per Config-Flip ändern, **ohne Bot-Neustart** (die Engine liest die Datei je Kerze
neu)" und §4 „danach wirken Config-Flips über die DATEI **sofort**". Faktisch reisen die Hebel IM
Payload: ein Config-Flip erreicht die Engine erst mit der NÄCHSTEN geschriebenen Datei (Autopilot-
Tick, ≤ 6 h) bzw. über den TTL-Verfall der alten Datei (≤ 7 h). Der einzige SOFORT-Rollback ist
**Datei löschen** (SPEC nennt ihn korrekt als Option). Kein Sicherheitsloch (alle Hebel-Wirkungen
sind ≤ 1/defensiv), aber eine Betriebs-Erwartung, die im Ernstfall überraschen könnte.
**Empfehlung E-5:** zwei Sätze in SPEC §3/§4 präzisieren („ohne Neustart" ≠ „sofort"); optional:
`POST /api/master/policy-bridge/config` triggert direkt einen Bridge-Write (dann stimmt „sofort").

### Hinweise (keine Mängel)

**H-1 · L2-Dämpfung nutzt das Regime vom SCHREIB-Zeitpunkt, nicht das der Kerze.**
`custom_stake_amount` wendet `active.stake_scale` an (master_meta.py:264–269) — das aktive Regime
zum Autopilot-Tick. Flippt das Regime zwischen Ticks, passt der Faktor bis zu ~6–7 h nicht zum
Kerzen-Regime (immer ≤ 1, nie risikoerhöhend; L1/L3 werten dagegen korrekt per-Kerzen-Regime über
die `reg_*`-Spalten). Per-Regime-Auflösung im Stake-Pfad wäre konsistenter, braucht aber
Dataframe-Zugriff im Stake-Callback — die einfache Variante ist vertretbar. (Optionale E-6.)

**H-2 · Engine-Schlüssel = das Setzen des Parameters, nicht der geplante Neustart.**
Nach `PUT /api/bots/mastermeta` mit `use_policy_bridge=1` würde auch ein UNGEPLANTER
Bot-Neustart (Crash + Resume-Watchdog) die Anwendung armen — der gegatete Neustart ist
Wirksamkeits-, nicht Sicherheits-Gate. Betriebs-Hinweis: den PUT erst unmittelbar vor dem
gewollten Neustart absetzen. (Kein Loch: der PUT selbst IST die bewusste Zwei-Schlüssel-Handlung.)

**H-3 · docs/58-Formulierung „Deflated-Sharpe/PSR/PBO" ist zu 2/3 wörtlich, zu 1/3 sinngemäß.**
PSR: exakt die López-de-Prado-Formel inkl. Skew/Kurtosis-Korrektur und fail-conservative Guards
(mn_base.py:121–133 — verifiziert). Deflated-Sharpe: als vereinfachter, konservativer
Multiple-Testing-Haircut ∝ √(2·ln N) umgesetzt (master.py:204), nicht als exakte Bailey-Prado-DSR —
ehrlich so kommentiert. „PBO": kein kombinatorisches CSCV, sondern ein Anchored-Walk-Forward-
Selection-Bias-Gate (Selektion nur auf Train, Gewinner EINMAL auf ungesehenem Test,
`confident=oos_validated` gated die Auto-Anwendung; meta.py:238–313). Für die Datenmenge ist das
die angemessenere Kontrolle; die docs/58-Kurzformel sollte man nur nicht wörtlich zitieren.

**H-4 · Kelly wird als begrenzter TILT angewandt, nicht als rohe Kapital-Fraktion — bewusst konservativ.**
`mult = clip(1 + λ·kelly_eff, floor, cap)` auf den vol-getargeteten Stake (sizing.py:179–180),
mit λ ≤ 1 erzwungen, kelly ≤ 1 mathematisch, Stake absolut in [min_stake, max_stake] geklemmt.
Der Ruin-Beleg (`test_kelly_ruin.py`, SPEC §5/§6: Voll-Kelly P(DD≥50 %)=100 % vs. Viertel-Kelly
6.5 %) begründet λ=0.25 im direkteren Frame — die Tilt-Anwendung ist nochmals defensiver. Sauber.

## 3 · Bestätigungen („validiert/sauber") mit Belegen

**3.1 · Das Zwei-Schlüssel-Prinzip hält — auch gegen die Lern-Loops.**
Backend-Schlüssel liegt exakt wie SPEC §8 (live gelesen: `data/policy_bridge.json` =
apply + L1+L2+L3 + floor 0.5 + TTL 25200); `suggested_policy.json` existiert NICHT (das laufende
Vor-T5-Backend kennt den Writer nicht). Engine-Schlüssel offen: `bots.json` → mastermeta
`manual_params: null`, 0 Treffer für `use_policy_bridge`/`use_sizing_bridge` in der gesamten
Registry. **Kein automatischer Pfad kann den Engine-Schlüssel setzen:** der Optimizer-Grid-Raum
(`meta.STRATEGY_PARAMS`) enthält keinerlei Bridge-Flags (grep-verifiziert: 0 Treffer in meta.py) —
`_mastermeta_improve`/Auto-Upgrade können ihn konstruktiv nie erzeugen; der runner reicht nur durch
(runner.py:88–98).

**3.2 · Die 7-Gate-Kette der Engine ist vollständig und jede Stufe fail-safe.**
`_policy_levers` (master_meta.py:122–174): (1) `use_policy_bridge` Default 0 ⇒ Datei wird NIE
gelesen (Z. 135–138, jeder Parse-Fehler ⇒ None); (2) `dry_run`-Gate — `not bool(config.get
("dry_run", True)) ⇒ None` (Z. 139–140; Default True spiegelt freqtrades eigenen Default, Echtgeld
⇒ hart raus); (3) Datei fehlt/kaputt/veraltet/`mode≠'apply'` ⇒ None (Z. 145–153; fehlender `ts` ⇒
Alter „unendlich"); Logik-**Whitelist** `_POLICY_LOGICS` (Z. 118, 162 — unbekannte Logik ⇒ Default
bleibt); `stake_scale` **Hard-Clamp [0.1, 1.0]** (Z. 168). NaN-/Inf-Payloads geprüft: durch die
`max(0.1, min(1.0, …))`-Reihenfolge landet NaN auf 1.0 (neutral), +Inf auf 1.0, −Inf auf 0.1 —
nie > 1, nie Absturz. Identische Gate-Disziplin im Sizing-Pfad (`_sizing_bridge_stake`,
Z. 85–104: eigener Bot via `TBT_BOT_ID`, `stake > 0`-Guard, Frische, mode, dry_run in
`custom_stake_amount` Z. 254).

**3.3 · Die „Politik kann nie hochhebeln"-Invariante ist durchgängig belegt.**
T0: `_stake_scale` konstruktiv in [floor, 1.0], monoton in der Konfidenz (policy_bridge.py:91–98);
Konfidenz-Quelle `master._confidence` ∈ [0,1] (master.py:105–123). Engine: Faktor-Clamp [0.1, 1.0]
+ Anwendung multiplicativ auf den Grundwert, danach freqtrade-`[min_stake, max_stake]`
(master_meta.py:264–269 — „min_stake klemmt zuletzt", V5-Beleg). Kelly-Kette: K4–K6 monoton
nicht-erhöhend (Property P3), `final ≤ max_stake` immer (sizing.py:217), Water-Filling hält
`Σ stake×mot ≤ cap` oder meldet ehrlich `budget_infeasible` (P2; Fixpunkt-Konstruktion
sizing.py:249–273 nachgerechnet: `s = rest/denom` garantiert die Budget-Invariante je Runde).
Komposition T5×Kelly: `stake_final = clamp(policy_scale × kelly_bridge_stake)` ≤ Kelly-Stake —
die Politik kann die K4–K6-Klemmen konstruktiv nicht überbieten. Property-Tests decken genau
diese Invarianten (PT1–PT7 · P1–P6, je 200 seeded Fälle; Testnamen-Auszug §1-Tabelle), Suite grün.

**3.4 · Klemmketten-Reihenfolge und Degradation sind korrekt verdrahtet.**
Autopilot-Tick: Governor ZUERST, dann Sizing-Bridge, dann Policy-Bridge, alle exception-getrennt
(main.py:1330–1344). Breach ⇒ `mode='proposal'` beidseitig: im Writer (policy_bridge.py:157–158,
sizing.py:413) UND als Engine-Gate (`mode != 'apply'` ⇒ None). Governor-warn/Konzentrations-
Treffer ⇒ Logik-Freeze VOR der `switched`-Berechnung (policy_bridge.py:120, 139–140) — die
Dämpfung (≤1) bleibt dabei erlaubt, exakt die SPEC-§2-Semantik. K5 klemmt nur betroffene Assets,
K6 flottenweit, Freeze hebt nie auf `min_stake` an (sizing.py:326–351).

**3.5 · Der Governor-Eingriff wird vom Resume-Watchdog NICHT rückgängig gemacht.**
Angriffshypothese geprüft und verworfen: `governor.run_once` pausiert via `runner.stop` →
`_stop_locked` setzt `update_status(bot_id, "stopped")` (runner.py:360); der Watchdog
(`_reconcile_fleet`, main.py:253–255) fasst ausschließlich Status `paper_running`/`live_running`
an. Governor-pausierte Bots bleiben pausiert. Zusätzlich bestätigt: Governor stoppt NUR
dry_run-Bots und schützt den MasterMeta-Singleton (governor.py:250–255, 310–311); der
identitätssichere Stop (nur cmdline-verifizierte PIDs, kein `/T`) verhindert Collateral-Kills
(runner.py:338–356 — der 16.06.-Fix ist drin, Regressionstests grün).

**3.6 · Kelly-Mathematik korrekt.**
`_expectancy_from_profits` (stats.py:354–378): W aus entschiedenen Trades (0-Profit neutral),
b = Ø-Gewinn/Ø-Verlust, E[R] = W·b − (1−W), f\* = W − (1−W)/b — die klassische Kelly-Formel;
ohne Verluste bleibt Kelly None („NIE aus reinen Gewinnern hochrechnen", Guards Z. 369/371).
K1-Abschläge multiplikativ ∈ (0,1] (shrink n/(n+k) monoton in n, sim_discount ≤ 1 erzwungen,
sizing.py:119–120). Konfigurations-Härtung: λ ∈ [0,1], floor ≤ cap, min ≤ max erzwungen
(sizing.py:113–121). Edge-Quellen-Gating (K0) mit Mindest-Stichproben je Quelle, „auto" mit
ehrlichem Fallback (sizing.py:130–156).

**3.7 · Echtgeld ist mehrschichtig ausgeschlossen (Stand heute).**
(a) dry_run-Gates in BEIDEN Engine-Konsumenten (Sizing + Policy); (b) `portfolio_plan` plant
Echtgeld-Bots NIE (nur informativ `skipped`, sizing.py:377/394 — Doppel-Schutz vor der Brücke);
(c) Governor pausiert nur dry_run; (d) `transfer.py`: confirm-Zwang + Paper-Modus + „Echter
Transfer erfordert Key MIT Transfer-Recht (aktuell read-only). Bewusst blockiert."; (e) Flotte
100 % dry_run (Registry verifiziert). Einzige M6-Vorleistung mit Gate-Lücke: M-2 (Hebel-Pfad).

**3.8 · HMM: das docs/58-Urteil „korrektes log-space Baum-Welch" bestätigt sich auf Zeilen-Ebene.**
Forward-/Backward-Rekursionen, Posterior γ = exp(α+β−ll), ξ-Normierung per logsumexp, Re-Estimation
mit Varianz-Floor (gegen EM-Kollaps), numerisch stabiles logsumexp mit Max-Shift (hmm.py:17–101);
multivariat mit diagonaler Kovarianz + **Dual-Init** (deterministisch + Warm-Start, behalten wird
die höhere Log-Likelihood — gegen lokale Optima UND für Label-Kontinuität) + `_sanitize_init`
(Wahrscheinlichkeiten ≥ 1e-6 renormiert, hmm.py:144–204). Konfidenz = Posterior des aktuellen
Zustands ∈ [0,1] konstruktiv. Regime-Label über Rendite-Mittelwert-Rang, Antizipation aus der
Übergangszeile — alles sauber.

**3.9 · Eine Regime-Fehlklassifikation kaskadiert NICHT ungebremst.**
Vier unabhängige Dämpfer: (a) die Engine fährt primär ihr EIGENES vola-normiertes z+Hysterese-
Regime; das HMM überschreibt NUR die jüngste Kerze und nur bei frischer Datei (master_meta.py:
341–347 — Backtests bleiben lookahead-frei); (b) die Politik blendet bei niedriger HMM-Konfidenz
Richtung regime-gemittelter Sicht (master.py:377–379); (c) T0-`profitable`-Gate: Switches nur auf
validated + PF>1 (master.py:346 — heute: 0 Strategien ⇒ 0 Switches); (d) L2/L3 wirken nur
defensiv. Worst Case einer Fehlklassifikation ist damit eine falsch-konservative Allokation plus
per-Trade-Stoploss — kein Verstärkungspfad. (Rest-Exposition: der D1-Hebel-Pfad, s. M-2.)

**3.10 · Validierungs-Disziplin gegen Overfitting ist real implementiert.**
Anchored-Walk-Forward mit Train-only-Selektion und einmaligem OOS-Test (meta.py:238–313),
Auto-Anwendung hart auf `oos_validated` gegated (main.py:1309); Ehrlichkeits-Gate kappt
un-validierte PFs auf ≤ 1 in der Bestauswahl (master.py:332–338); `UNVALIDATED_CONF_PENALTY`
0.25 (master.py:102); MN-Sockel-Härtungskette Haircut + Deflation √(2·ln N) + PSR-Faktor +
`sim_discount` für synthetische Engines + 1/N-Benchmark als Ehrlichkeits-Referenz
(master.py:193–254). Der einzige selbst-mutierende KI-Pfad (Auto-Anwendung gelernter Params)
ist OOS-gegated, event-risk-aware, versioniert und auditiert (main.py:1309–1316).

**3.11 · Was beim nächsten :8137-Neustart wirklich scharf wird (Live-Dateien verifiziert).**
Backend-Neustart: Autopilot beginnt `suggested_policy.json` im **apply**-Modus zu schreiben
(Backend-Schlüssel liegt) — die Hand ignoriert sie weiter (Engine-Schlüssel offen, 3.1) ⇒
byte-identisches Verhalten (V1-Beleg). Die **Kelly-Brücke bleibt AUS**: das Live-`sizing.json`
enthält keine Bridge-Keys ⇒ Defaults greifen (`bridge_enabled: false`) — es wird KEINE
`suggested_sizing.json` geschrieben. Live-aktiv im Sizing sind heute nur Vol-Targeting
(target 0.8 %) + Expectancy-Tilt als **proposal-only-Empfehlungen**. Nach dem späteren Setzen des
Engine-Schlüssels multipliziert L2 daher den freqtrade-`proposed_stake` (T3-Grundwert-Fallback,
master_meta.py:249/264–269) — die Kette funktioniert wie spezifiziert auch ohne Kelly-Brücke.

## 4 · T5 Politik→Hand — Detail-Urteil

**Logisch korrekt, Klemmen greifen, fail-closed gegenüber Echtgeld: JA** (Belege 3.1–3.4, V1–V5).
Beantwortung der Auftragsfragen im Einzelnen:

- **„Kann die KI-Ebene über diese Schiene je eine unsichere/echtgeld-wirksame Order erzeugen?"
  Nein.** Der Payload kann Entries nur unterdrücken (L3), zwischen zwei whitelisted Long-Logiken
  wählen (L1 — beides bestehende, lookahead-freie Signal-Familien derselben Engine; Shorts nicht
  umschaltbar) und Stakes dämpfen (L2, ≤ 1). Ein manipulierter Payload (fremde Logik-Strings,
  scale > 1, NaN, kaputtes JSON, fehlender ts) wird engine-seitig neutralisiert
  (Whitelist/Hard-Clamp/fail-safe; `test_engine_validates_and_hard_clamps_payload` + eigene
  NaN-Analyse). Echtgeld: dry_run-Gate in der Engine + die Brücke wird für Echtgeld-Bots gar nicht
  erst geplant.
- **dry_run-/Echtgeld-Sperre wirklich fail-closed?** Ja — mit der präzisen Aussage: `config.get
  ("dry_run", True)` spiegelt freqtrades eigenen Default (fehlender Key = dry_run); explizites
  `dry_run: false` schließt das Gate. Getestet (`test_engine_gate2_real_money_hard_excluded`).
- **Zwei-Schlüssel umgehbar?** Nein (3.1). Einzige Nuance: H-2 (der PUT ist der Schlüssel, nicht
  der Neustart).
- **Rest-Risiken:** M-1 (Governor-Kadenz-Begründung), N-1 (fail-open bei Advisor-Fehlern), N-3
  (Rollback-Latenz-Formulierung) — alle ohne Auswirkung auf die Kern-Sicherheitsaussage, weil der
  Payload-Inhalt konstruktiv ≤ 1/defensiv ist.

## 5 · Kelly-Sizing — Detail-Urteil

**Mathematisch korrekt angewandt, Interaktion mit T5/Regime sicher: JA** (Belege 3.3, 3.6, H-4).

- Expectancy→Kelly-Formel korrekt, keine Winrate-Naivität (der 90-%-Winrate-Fall aus SPEC §6
  wird durch negativen Kelly verkleinert, nie gehebelt — `kelly_floor` 0.5).
- K0–K6-Reihenfolge normativ eingehalten und getestet (K4-vor-K6-Reihenfolge-Beleg
  `test_clamp_order_budget_before_freeze_documented`); Water-Filling erhält relative
  Kelly-Gewichte, floort ehrlich, meldet Infeasibilität statt still zu verletzen.
- Defaults inert bestätigt — sowohl im Code (alle FP-2-Keys Default aus, sizing.py:42–73) als auch
  im LIVE-Zustand (3.11: Brücke aus; nur der seit 25.06. bewusst aktive Expectancy-Tilt läuft,
  proposal-only).
- **Doppel-Dämpfungs-Frage (T5×Kelly×Regime):** Die drei Ebenen komponieren multiplikativ nur nach
  UNTEN (Kelly-Tilt ≤ cap, aber Stake ≤ max_stake; Policy-Scale ≤ 1; Exposure/lev_scale ≤ 1) —
  eine Über-Dämpfung ist möglich (z. B. Governor-warn-Freeze + L2 0.5 + vol-Faktor), eine
  Über-Hebelung nicht. Über-Dämpfung ist ein Ertrags-, kein Sicherheitsrisiko und durch
  `min_stake`-Floors begrenzt. Kein zirkulärer Feedback-Pfad gefunden: die Brücken lesen
  Politik/Plan und schreiben Dateien; die Engine liest Dateien und platziert dry_run-Orders;
  die Lern-Loops lesen Trade-DBs — der Kreis schließt sich nur über reale (Paper-)Ergebnisse,
  nicht über die Brücken selbst.

## 6 · Gesamt-Architektur & Komposition — Urteil

Die Kette **HMM (log-space BW, korrekt) → Politik (`derive_policy`: Ehrlichkeits-Gates,
Konfidenz-Blending, MN-Härtung) → Klemmketten (T0–T3 / K0–K6, monoton defensiv) → Brücken
(atomar, TTL, mode-Gates) → Hand (7 Gates, Whitelists, Hard-Clamps) → per-Trade-Stoplosses →
Governor (Portfolio-Notbremse, dry_run-only)** komponiert sauber; jede Schicht kann die nächste
nur verschärfen, nie lockern. Reihenfolge-Fallen wurden gezielt gesucht: Governor-vor-Brücken ✓,
K4-vor-K5/K6 ✓, Freeze-vor-switched ✓, min_stake-zuletzt ✓, Watchdog-vs-Governor ✓ (3.5).
Versteckte Kopplungen: die einzige gefundene Asymmetrie ist der D1-Hebel-Pfad (M-2); die
Tick-Synchronität von L2 (H-1) und die Rollback-Latenz (N-3) sind Betriebs-Nuancen.
Literatur-Fundierung: PSR wörtlich korrekt, DSR sinngemäß-konservativ, „PBO" als
Selection-Bias-Gate (H-3), Kelly-Ruin-Beleg reproduzierbar in der Suite, 1/N-Benchmark
(DeMiguel) als Ehrlichkeits-Referenz. **Das docs/58-Urteil „Software-Kern exzellent" bestätigt
sich; die zwei neuen Ebenen halten diesen Standard.**

## 7 · Empfehlungen (gegated — Umsetzung NUR durch TB-Chat/Bau-KI; nichts hiervon blockiert den nächsten gegateten Neustart)

| ID | Empfehlung | Bezug | Aufwand | Wann |
|---|---|---|---|---|
| E-1 | Governor-`run_once` in schnelleren Takt (eigener 15-min-Loop oder an den 10-min-Resume-Watchdog hängen; Debounce existiert schon) + SPEC-§4-Satz korrigieren | M-1 | S | nächstes TB-Paket |
| E-2 | **VOR M6 Pflicht:** `leverage()`-Konfidenz-AUFschlag nur bei `dry_run=True` + absoluter Code-Cap (z. B. 10); dämpfende Faktoren gate-frei lassen | M-2 | S | vor jedem Echtgeld-Schritt |
| E-3 | `_risk_context`/`portfolio_plan`: Governor-Lesefehler ⇒ fail-closed (`proposal`/kein Upsizing) statt „ok" | N-1 | S | nächstes TB-Paket |
| E-4 | `tracker.write_regime_bridge` auf `jsonstore.write_atomic` | N-2 | S | nächstes TB-Paket |
| E-5 | SPEC §3/§4 Rollback-Latenz präzisieren; optional Config-POST triggert Sofort-Write der Bridge | N-3 | S | mit E-1 |
| E-6 | (optional) L2-Scale per-Kerzen-Regime auflösen statt `active`@Tick | H-1 | M | bei Gelegenheit |
| E-7 | (Doku) docs/58-Kurzformel „DSR/PSR/PBO" → „DSR-Haircut/PSR/Anchored-WF-Selection-Gate" | H-3 | S | Doku-Runde |

## 8 · Was NICHT geprüft wurde (ehrlich)

- Die **17 übrigen Strategie-Engines** zeilengenau (nur MasterMeta voll; die 6 neuen Engines waren
  am 26.06. lookahead-geprüft `has_bias=No`, alle laufen in der grünen Suite).
- Das **Innenleben der MN-Engines** (csm/pairs/statarb/mm) — geprüft wurde ihre Härtungs-/
  Gewichtungs-Schicht in `master.py`, nicht die Simulationskerne (eigene Tests grün).
- `fundamental.py` (Event-Risiko-Quelle), `cull.py`, `ai.py` (Recherche-Katalog),
  `concentration.py`-Innenleben (nur Konsumenten-Seite), Frontend/`index.html` — das
  **T5-UI-Panel gegen die docs/60-UX-Kette** ist weiterhin die offene World-Admin-Auflage.
- **Kein Live-Lauf, kein Neustart, keine Order** (Auftrag); `engine_policy_verify.py` war der
  einzige Engine-venv-Prozess (selbst-aufräumend, verifiziert).
- Die Monte-Carlo-ZAHLEN aus SPEC §5/§6 wurden nicht neu erzeugt (die erzeugenden Tests
  `test_kelly_ruin.py`/`test_policy_sim.py` liefen in der grünen 474er-Suite mit).
- Prozess-/PID-Management (`runner._scan_bot_pids` etc.) nur auf Governor-/Watchdog-Interferenz,
  nicht als eigenes Audit (16.06.-Identitäts-Fix + Regressionstests vorhanden).

---
*Erstellt 04.07.2026, Architektur-KI-Review-Chat (read-only). Suite-Läufe: Backend 474 passed (25.75 s) ·
engine_policy_verify V1–V5 PASS — beide am heutigen master `f856ad9`.*
