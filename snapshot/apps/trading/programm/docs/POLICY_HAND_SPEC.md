# Politik→Hand SPEC — Regime-Bestauswahl → MasterMeta-Engine (FP-T5 / Gate G-T5)

> **Stand:** 03.07.2026 · Branch `chat/tb-t5` · Umsetzung von `MASTERMETA_TIEFENPRUEFUNG_2026-06-25.md`
> Empfehlung #2 („Politik→Hand enger koppeln") nach exakt dem FP-2-Muster (`KELLY_SIZING_SPEC.md`).
> **Sicherheits-Grundsatz:** JEDER neue Hebel ist opt-in mit inertem Default. Ohne Opt-in ist das
> Verhalten byte-identisch zu vorher (Beleg: §6 + `test_policy_bridge.py`).
> **★ Gate G-T5 BEANTWORTET (David, 03.07.2026)** — Entscheid + Aktivierungszustand in §8. Die
> CODE-Defaults bleiben bewusst inert (die Byte-Identitäts-Garantie gilt weiter); die Aktivierung
> läuft ausschließlich über CONFIG + die zwei gegateten Neustarts (Backend + MasterMeta-Bot).

## 0 · Lage vorher (Warum)

- Das **Gehirn** (`master.derive_policy`) ist vollständig: je Regime die beste validierte Strategie
  (+ Params + Konfidenz), MN-Sockel, Fundamental-Overlay, Vol-Targeting.
- Die **Hand** (MasterMeta-Engine, `engine/user_data/strategies/master_meta.py`) ist nur PARTIELL
  gekoppelt: Regime + HMM-Konfidenz + Hebel-/Exposure-Scale (`hmm_regime.json`, D1) und Stakes
  (`suggested_sizing.json`, FP-2). **NICHT gekoppelt war die per-Regime-STRATEGIE-BESTAUSWAHL**
  (Tiefenprüfung Befund 2, Punkt 1): die Hand fährt eine FIXE Sub-Logik je Regime
  (trend_up→MACD-Long · range→BB-MR-Long · trend_down→MACD-Short), egal was die Politik lernt.
- Empfehlung #2 nannte den Fix und die Bedingung: „bräuchte eine Strategie-Auswahl-Bridge analog
  zur Regime-Bridge. **Architektur-Entscheid (Nutzer), kein Schnellschuss.**" ⇒ deshalb Gate G-T5:
  dieser Bau liefert die komplette, getestete Mechanik — SCHARF wird nichts ohne Davids Antwort.

## 1 · Was die Politik der Hand sagen kann (T0-Destillat, `policy_bridge.derive_payload`)

Die Politik wählt **Flotten-Strategien**; die Hand besitzt nur 2 Long-Logiken + 1 Short-Logik.
Übersetzt wird über den `STRAT_REGIME`-**Tag** der Bestauswahl — ehrlich, ohne so zu tun, als könnte
die Hand jede Strategie fahren:

| Politik-Bestauswahl (Tag) | Hand-Logik (long) | Hand-Logik (short, nur trend_down) |
|---|---|---|
| `trend` (z. B. TrendFollowEma) | `trend_macd` (MACD-Kreuz + ADX) | `trend_macd_short` |
| `range` (z. B. FuturesBbandsBounce) | `range_bb` (BB-Unterband + RSI) | — kein Pendant ⇒ Default + `note` |
| `volatil` / unbekannt | — kein Pendant ⇒ Default + `note` | — Default |

- **`stake_scale` je Regime** = `scale_floor + (1 − scale_floor) · Konfidenz` falls `profitable`
  (validated + PF>1), sonst `scale_floor`. **Hart in [`scale_floor`, 1.0] — NIE > 1** (die Politik
  kann die Hand nur dämpfen, nie hochhebeln). Monoton in der Konfidenz.
- **`enabled` je Regime** (nur Hebel L3): das `profitable`-Flag der Bestauswahl.
- **`params` fließen als Transparenz MIT, werden aber NICHT angewendet.** Bewusst: (a) Params einer
  Fremd-Strategie sind nicht 1:1 auf die MasterMeta-Sub-Logik übertragbar, (b) es entstünde eine
  Doppel-Quelle zu `TBT_OPT_PARAMS` (MasterMeta hat seinen EIGENEN gegateten Lern-Loop
  `_mastermeta_improve`). Param-Transplantation = expliziter Folge-Entscheid (§8 Stufe 3).
- **Heutige Datenlage („Daten reifen"):** KEINE Strategie ist validated-profitable ⇒ `apply` hieße
  heute: **0 Logik-Switches** (kein belegter Edge), **L2 dämpft auf `scale_floor`** (Default 0.5×)
  und **L3 würde ALLE Entries aussetzen**. Das ist die ehrliche Konsequenz der Beleglage — die
  Kopplung beginnt erst zu „arbeiten", wenn OOS-Validierungen Edges bestätigen.

## 2 · Klemmkette (normativ): **T0 Politik → T1 Governor → T2 Konzentration → T3 Sizing**

Die Politik ist die ERSTE Stufe der Kette und kann von jeder späteren nur VERSCHÄRFT werden:

- **T0 Politik** (`derive_payload`, rein/deterministisch): destilliert Bestauswahl → Logik/Scale/
  Enabled, hart geklemmt (§1).
- **T1 Governor** (letztes Wort auf Portfolio-Ebene): `breach` ⇒ **`mode` degradiert auf
  `proposal`** — die Hand wendet NICHTS an (identisch FP-2 P5). `warn` ⇒ **Logik-Freeze** (alle
  Logiken = Default, kein Verhaltens-Churn in angespannter Lage); die rein defensive
  Stake-Dämpfung (≤1) bleibt anwendbar.
- **T2 Konzentration:** `warn` UND die Hand-Assets (BTC/ETH/SOL) sind im über-gedeckelten
  Asset/Cluster ⇒ ebenfalls **Logik-Freeze** (strukturelle Klumpen-Lage: dämpfen ja, umschalten nein).
- **T3 Sizing** (engine-seitig): der Politik-Faktor multipliziert den **Sizing-Grundwert**
  (Kelly-Bridge-Stake aus K4–K6, sonst `proposed_stake`) und wird ZULETZT von freqtrades
  `[min_stake, max_stake]` geklemmt. **Faktor ≤ 1 ⇒ die Politik kann nie über die
  K4–K6-Klemmen von FP-2 hinaus erhöhen.**

**Invarianten (Property-Tests, seeded random 200 Fälle, `tests/test_policy_bridge.py`):**
- PT1 Scale-Kappe: `scale_floor ≤ stake_scale ≤ 1.0` für jedes Regime, jede Config.
- PT2 Breach-Degradation: Governor `breach` ⇒ Payload-`mode == "proposal"`.
- PT3 Logik-Freeze: Governor `warn`/`breach` ODER Konzentrations-Treffer ⇒ Logik = Default, `switched=False`.
- PT4 Whitelist: Logik nur aus {trend_macd, range_bb, trend_macd_short}; trend_down IMMER Default.
- PT5 Edge-Gating-Semantik: `enabled == profitable` gdw. L3 an, sonst `enabled == True`.
- PT6 Mode-Konsistenz: `apply` nur wenn konfiguriert UND kein breach.
- PT7 Determinismus: gleiche Inputs ⇒ gleicher Payload (modulo `ts`).
- Engine-seitige Monotonie: `final_stake ≤ Grundwert` für JEDEN Payload-Scale (seeded, 50 Fälle) +
  Hard-Klemme [0.1, 1.0] gegen manipulierte Payloads (Defense-in-Depth).

## 3 · Die drei Hebel L1–L3 (einzeln schaltbar, ALLE Default AUS)

| Hebel | Config-Key | Wirkung bei `apply` | Risiko-Richtung |
|---|---|---|---|
| **L1 Logik-Wahl** | `apply_logic` | Sub-Logik je Regime folgt der Politik-Bestauswahl (Tag-Map §1); Politik-Trades tragen `pol_`-Tags (Trade-DB-sichtbar) | Verhaltens-Änderung; §5: nur mit strenger Evidenz + zusammen mit L2 |
| **L2 Stake-Dämpfung** | `apply_stake` (+ `scale_floor`) | `stake × stake_scale(aktives Regime)`, Faktor ≤ 1 | NUR defensiv (nimmt Risiko raus) |
| **L3 Edge-Gating** | `gate_unprofitable` | Regime ohne belegten Edge: Entries ausgesetzt (long + short) | NUR defensiv (weniger Trades) |

Die Hebel reisen im Payload (`levers`) — David kann sie per Config-Flip ändern, **ohne Bot-Neustart**
(die Engine liest die Datei je Kerze neu; nur die Env-Pfade sind armed-until-restart).

## 4 · Brücke zur Hand — `suggested_policy.json` (Muster `suggested_sizing.json`/`hmm_regime.json`)

**Kette Gehirn → Hand** (jede Stufe fail-safe → fixes Default-Verhalten):

| Stufe | Ort | Gate | Default |
|---|---|---|---|
| 1 | Backend-Config | `bridge_enabled` | **False** ⇒ Datei wird NICHT geschrieben |
| 2 | Backend-Config | `bridge_mode` | **"proposal"** ⇒ Engine wendet NIE an |
| 3 | Governor | breach ⇒ Degradation auf proposal · warn ⇒ Logik-Freeze | automatisch |
| 4 | Konzentration | warn + Hand-Assets ⇒ Logik-Freeze | automatisch |
| 5 | Engine opt_param | `use_policy_bridge` | **0** ⇒ Datei wird NIE gelesen |
| 6 | Engine freqtrade-Config | `dry_run == True` | **Echtgeld hart ausgeschlossen** (M6 tabu) |
| 7 | Engine Frische | `ts` ≤ `policy_max_age_s` (Default 25200 s = 7 h) | veraltet ⇒ ignorieren |

- **Writer:** `policy_bridge.write_bridge_auto()` im Autopilot-Tick direkt NACH dem Governor und der
  Sizing-Bridge (`main._autopilot_step`), atomar via `jsonstore.write_atomic`. Payload: `{ts, mode,
  governor_severity, concentration_hit, logic_frozen, levers, scale_floor, active, regimes, ensemble,
  suggested_exposure}` — `regimes[reg]` trägt Strategie/Tag/Logik/switched/enabled/profitable/
  Konfidenz/stake_scale/params (Transparenz) je Regime.
- **Pfad-Vertrag:** `TBT_POLICY_FILE` (runner setzt IMMER, analog `TBT_REGIME_FILE`/`TBT_SIZING_FILE`)
  → Fallback relativ zur Strategie-Datei. **Armed-until-restart:** laufende Bots sehen die neue
  Env-Variable erst nach ihrem nächsten (Nutzer-gegateten) Neustart; danach wirken Config-Flips
  über die DATEI sofort (ohne weitere Neustarts).
- **Frische vs. Autopilot-Takt (★ G-T5-Takt-Entscheid, an TB-Chat delegiert):** der Autopilot tickt
  Default alle **6 h**. Das Frische-Gate ist auf **25200 s (7 h = Takt + 1 h Puffer)** gesetzt —
  deckt genau EIN Tick-Fenster: apply läuft zwischen den Ticks NICHT fail-safe leer, aber eine
  Bridge von einem toten/hängenden Backend verfällt nach spätestens einem verpassten Tick.
  Bewusst NICHT gewählt: `autopilot.interval_h` auf 0.25 h senken — das würde alle übrigen
  Tick-Schritte (mastermeta_improve-Backtests, cull, auto_validate) mit-beschleunigen (Compute +
  Verhaltens-Churn im ganzen System, nur um eine Datei öfter zu schreiben). Governor-Schutz bleibt
  unabhängig sofort wirksam (er pausiert Bots selbst); die breach⇒proposal-Degradation der Bridge
  greift zum nächsten Tick — akzeptabel, weil der Bridge-Inhalt ausschließlich defensiv ist (≤1).
- **Rollback (ohne Neustart wirksam):** `bridge_enabled: false` setzen (nächster Tick schreibt
  nicht mehr; die Engine ignoriert die alternde Datei nach `policy_max_age_s` von selbst) ODER
  Datei löschen ODER einzelne Hebel aus. Config-Flip via `POST /api/master/policy-bridge/config`;
  Vorschau/Transparenz via `GET /api/master/policy-bridge` (schreibt nichts).

## 5 · Sim-Beleg: Politik-gekoppelt vs. statisch (seeded Lauf 03.07.2026, Code = `test_policy_sim.py`)

Stilisiertes Markov-Regime-Modell (sticky 0.95), je (Regime × Logik) ein Zwei-Punkt-Edge, drei
Hände GEPAART über gemeinsame Zufallszahlen: **static** (fixe Default-Zuordnung) · **logic** (nur
L1, Evidenz-Gate n≥30 + positiv + Ratchet-Marge) · **full** (L1 + L2-Dämpfung auf 0.5 ohne positiv
geschätzten Edge). Schätzer mit PERSISTENTEM Pfad-Bias ~1/√Evidenz (σ=0.3 ≈ striktes OOS-Gate ·
σ=0.6 = pessimistischer Stress). 1200 Pfade × 250 Trades, f=5 %:

| Szenario | Hand | Median-End | P(DD≥30 %) | P(DD≥50 %) |
|---|---|---|---|---|
| A Welt=Default, OOS-Gate σ=0.3 | static | ×6.770 | 85.2 % | 17.8 % |
| | logic | ×6.586 | 85.6 % | 18.4 % |
| | full | ×6.471 | 84.6 % | 17.8 % |
| A Welt=Default, schwach σ=0.6 | static | ×6.770 | 85.2 % | 17.8 % |
| | logic | ×5.652 | 87.1 % | 24.4 % |
| | full | ×5.035 | 82.2 % | 22.1 % |
| B Welt INVERTIERT (Trend), σ=0.6 | static | ×0.910 | 99.8 % | 79.8 % |
| | logic | ×4.582 | 91.1 % | 33.7 % |
| | full | ×4.454 | 85.1 % | 25.5 % |
| C nirgends Edge, σ=0.6 | static | ×0.443 | 99.8 % | 91.0 % |
| | logic | ×0.443 | 99.8 % | 91.0 % |
| | full | ×0.547 | 97.8 % | 77.2 % |

**Lesart (ehrlich, beide Richtungen):**
1. **Der Wert ist real:** irrt die fixe Zuordnung strukturell (B — z. B. choppy Bull, in dem MR
   die Trendfolge schlägt), blutet die statische Hand (×0.91, DD50 80 %), während die gekoppelte
   den Edge erntet (×4.45–4.58, DD50 26–34 %). Genau dieser Fall ist der Grund für T5.
2. **Der Preis ist real:** mit schwachem Schätzer kostet L1 auch in der „richtigen" Welt ~17 %
   Wachstum und kann das DD-Risiko LEICHT erhöhen (+1.9 pp) — mit striktem Evidenz-Gate (σ=0.3)
   schrumpft der Preis auf ~3 % (nahezu kostenlos). ⇒ **L1 nur mit strengem validated-Gate und
   möglichst zusammen mit L2 aktivieren.**
3. **Die Sicherung trägt (Kern-Beleg für G-T5):** die VOLLE Kopplung (L1+L2) war in **jedem**
   Szenario DD-defensiver als statisch; sieht die Politik nur Rauschen (C), ist sie strikt besser
   (Median ×0.547 vs ×0.443, DD50 77 % vs 91 %). Weil der Faktor ≤ 1 ist und Switches nur auf
   „belegten" Edge erfolgen, **kann die Kopplung das Ruin-Risiko gegenüber heute nicht erhöhen.**

## 6 · Byte-Identitäts- & Funktions-Verifikation (echtes pandas/talib, Engine-venv)

`engine\.venv\Scripts\python.exe tests\engine_policy_verify.py` (seed 7, 800 Kerzen, pandas 3.0.3),
Lauf 03.07.2026 — Ausgabe:

```
V1 PASS: ohne Opt-in byte-identisch (df.equals) trotz gültiger apply-Datei
V2 PASS: mode='proposal' ⇒ byte-identisch (die Hand wendet nie an)
V3 PASS: L1-Logik-Tausch ⇒ 2 Entries folgen EXAKT der Soll-Maske, Tags ['pol_trend_macd']
V4 PASS: L3-Edge-Gating (alle Regime aus) ⇒ 0 Long- und 0 Short-Entries
V5 PASS: L2-Stake-Dämpfung 55→44.0 (×0.8) · min_stake klemmt zuletzt · ohne aktives Regime no-op
```

V3-Kern ist die SET-Gleichheit der Entry-Maske gegen eine unabhängig nachgerechnete Soll-Maske
über alle 800 Kerzen (nicht die Entry-Anzahl). Dazu die Suite-Anker im Backend-venv:
**468 Tests grün** (435 Bestand + 33 neue), insbesondere `test_sizing_bridge.py` UNVERÄNDERT grün
gegen die umstrukturierte `custom_stake_amount` (= Äquivalenz des Sizing-Pfads) und
`test_policy_bridge.py::test_engine_gate1_optin_default_off` / `…no_optin_stake_byte_identical`.

## 7 · Config-Referenz (neu; alle Defaults inert)

Backend (`policy_bridge.json` via `POST /api/master/policy-bridge/config`):

| Key | Default | Wirkung |
|---|---|---|
| `bridge_enabled` | false | Brücke: Datei schreiben (Autopilot-Tick) |
| `bridge_mode` | `"proposal"` | `"apply"` = Engine darf (nur dry_run) anwenden |
| `bridge_max_age_s` | 25200 | Engine-Frische-Gate = Takt + 1 h (min 60; §4 Takt-Entscheid) |
| `apply_logic` | false | Hebel L1 (Sub-Logik-Umschaltung) |
| `apply_stake` | false | Hebel L2 (Stake-Dämpfung ≤ 1) |
| `gate_unprofitable` | false | Hebel L3 (Regime ohne Edge aussetzen) |
| `scale_floor` | 0.5 | L2-Unterkante, hart in [0.1, 1.0] |

Engine (opt_params des MasterMeta-Bots): `use_policy_bridge` (Default 0 = Datei wird NIE gelesen) ·
`policy_max_age_s` (Default 25200).

## 8 · ★ G-T5 — BEANTWORTET (David, 03.07.2026)

**Die Frage war: Wie viel Autonomie darf die Regime-Politik über die tatsächlich gehandelte
Strategie-Logik und Positionsgröße des MasterMeta-Bots bekommen?**

**★ Davids Entscheid (03.07.2026, TB-Chat):**
- **Stufe 1 (nur dämpfen, L2): GO** — „absolut vertretbar und go".
- **Stufe 2 (umschalten in engen Klemmen, L1): GO nach TB-Chat-Empfehlung** — die Bedingung
  „≥ 1 validated-profitable Strategie je Regime" erzwingt der Mechanismus SELBST (T0-profitable-Gate:
  heute 0 Switches; die Umschaltung beginnt erst, wenn OOS-Validierungen Edges bestätigen).
- **L3 (Edge-Gating): GEWÜNSCHT** — mit der ausgesprochenen Konsequenz: MasterMeta pausiert
  Entries, bis Edges validieren (Exits/offene Positionen laufen normal weiter).
- **Zusatzfragen an den TB-Chat delegiert** („passt an, wie Du denkst"): **Takt** = Frische-TTL
  25200 s statt Autopilot-Beschleunigung (Begründung §4) · **`scale_floor` = 0.5 bestätigt**
  (halbieren ist spürbar defensiv, hungert den Bot aber nicht aus; Sim §5 lief mit 0.5) ·
  **L3 = an** (siehe oben).
- **Stufe 3 („weiter"): NICHT jetzt — Zukunftsplan.** Bestätigte Lesart: erst wenn Stufe 2 mit
  GEREIFTEN Daten erprobt ist (≥ 90-T-Historie, echte Switches beobachtet + bewertet). Dann je
  EIGENER Entscheid + Bau: Faktor > 1 (Politik darf aufsizen) · Param-Transplantation (löst den
  TBT_OPT_PARAMS-Doppel-Quellen-Konflikt) · MN-Sockel-Ausführung (M6-nah). Gehört in die
  World-Admin-Zukunftsplanung, NICHT in dieses Paket.

**Aktivierungszustand nach diesem Entscheid (Zwei-Schlüssel-Prinzip):**
1. **Backend-Schlüssel (vom TB-Chat vorbereitet):** `data/policy_bridge.json` liegt im Live-Datenverzeichnis
   mit `{bridge_enabled: true, bridge_mode: "apply", apply_stake: true, apply_logic: true,
   gate_unprofitable: true, scale_floor: 0.5, bridge_max_age_s: 25200}` — das ALTE laufende Backend
   kennt die Datei nicht (kein Writer-Konflikt, 0 Wirkung); ab dem nächsten gegateten Backend-Neustart
   schreibt der Autopilot die Bridge im apply-Modus.
2. **Engine-Schlüssel (bewusst offen gelassen):** der MasterMeta-Bot hat `use_policy_bridge` noch
   NICHT gesetzt — Arming = `PUT /api/bots/mastermeta` manual_params `{"use_policy_bridge": 1}` +
   gegateter MasterMeta-Bot-Neustart (bots.json wird NIE am laufenden Server vorbei editiert).
   Erst mit BEIDEN Schlüsseln wendet die Hand an — bis dahin weiter byte-identisch.

| Stufe | Was die Politik darf | Konsequenz mit HEUTIGER Datenlage | Risiko-Charakter |
|---|---|---|---|
| **0 — nur vorschlagen** (Status quo, Default) | nichts; Vorschau via `GET /api/master/policy-bridge` | keine — byte-identisches Verhalten | 0 |
| **1 — nur dämpfen** (`apply` + L2, optional L3) | Risiko RAUSNEHMEN: Stake ×[0.5..1] nach Edge-Konfidenz; optional Regime ohne belegten Edge aussetzen | MasterMeta-Stake dauerhaft ×0.5 (nichts validiert); mit L3: Entry-Pause bis Edges validieren | rein defensiv — kann Ruin-Risiko NICHT erhöhen (Beleg §5.3) |
| **2 — umschalten in engen Klemmen** (zusätzlich L1) | die gelernte Bestauswahl je Regime real fahren (Tag-Map §1), innerhalb: Governor-/Konzentrations-Freeze, nur validierte Edges, dry_run | HEUTE 0 Switches (kein belegter Edge) — beginnt erst mit reifenden Daten zu schalten | Verhaltens-Änderung; §5.2: nur mit striktem Gate ≈ kostenlos, erntet Inversionen |
| **3 — weiter** (NICHT gebaut, nur benannt) | Faktor > 1 (aufsizen), Param-Transplantation, MN-Sockel-Ausführung | — | je eigener Entscheid + Bau; M6-nah |

**Pflicht-Sicherungen (in JEDER Stufe, nicht verhandelbar, alle gebaut + getestet):** dry_run-only
hart (Echtgeld-Pfad tot) · Governor-breach ⇒ proposal · warn/Klumpen ⇒ Logik-Freeze · Frische-TTL ·
fail-safe bei fehlender/kaputter/alter Datei · Faktor ≤ 1 · Rollback ohne Neustart · Engine-seitige
Hard-Klemmen gegen manipulierte Payloads.

**Ursprüngliche Zusatzfragen (alle 03.07. entschieden, s. o.):** Takt (→ TTL 25200) ·
`scale_floor` (→ 0.5 bestätigt) · L3 (→ an). Die ursprüngliche Empfehlung (Stufe 1 sofort, Stufe 2
über das validated-Gate) wurde von David übernommen.

**NICHT-SCOPE dieses Pakets:** Echtgeld (M6) · ML-Re-Trainings (daten-blockiert ≥90 T) ·
Param-Transplantation (§1) · MN-Sockel-Ausführung · Auto-Restart von Bots.
