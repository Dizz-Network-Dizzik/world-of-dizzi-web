# MasterMeta-Tiefenprüfung (25.06.2026)

> Audit im Rahmen der offenen TB-Liste (World-Admin-Nachtlauf). Read-only-Analyse von
> `backend/app/master.py`, `meta.py`, `tracker.py`, `engine/.../master_meta.py`. Ehrlich (Gesetz 2):
> Befunde + reale Lücken, kein Schönreden. **0 Akut-Bugs gefunden** — der Master ist sauber und
> diszipliniert gebaut; die Punkte unten sind Architektur-Wahrheiten + Wert-Hebel, keine Defekte.

## Leitfrage
„Greift der Master wirklich auf ALLES, spielen alle Systeme sinnvoll zusammen, wird er langfristig
exponentiell schlauer?"

## 1. Das „Gehirn": `master.derive_policy` zieht tatsächlich auf alles
Die abgeleitete Ensemble-Politik konsolidiert **alle** Edge-Quellen:
- **Gerichtete Strategien** (alle in `meta.STRAT_REGIME`), je Regime der beste Kandidat nach
  `PF × regime_fit`. **Ehrlichkeits-Gate:** eine Strategie ohne bestandene OOS-Validierung wird hart
  auf `eff_pf ≤ 1` gekappt (`derive_policy`, Z. 330‑331) → trägt **0** zum gerichteten Edge bei. Das ist
  genau das „kappt unvalidierte gerichtete auf PF≤1" — verifiziert korrekt (verhindert, dass ein
  Overfit-PF>3 bei negativer Realrendite die Allokation trägt, Bsp. DcaDip PF 3.49 / −5.9 %).
- **Markt-neutraler Sockel** (CSM/Pairs/StatArb/Market-Making) über `mn_sleeve` mit einer ungewöhnlich
  ehrlichen Härtungskette: Sharpe-Haircut → **Deflated-Sharpe** (Multiple-Testing ∝ √(2·ln N)) → **PSR**
  (López de Prado) → **sim_discount** (synthetische MM-Engine) → Konfidenz-Shrink → max-Weight-Cap →
  **1/N-Benchmark** (DeMiguel et al. 2009, als Ehrlichkeits-Referenz). Das ist State-of-the-Art und
  bewusst defensiv-pessimistisch.
- **HMM-Regime** (`tracker` → Snapshot): aktuelles Regime + Konfidenz + **antizipiertes nächstes Regime**
  + Halte-Wahrscheinlichkeit; der gerichtete Sleeve wird darauf konditioniert und bei unsicherem Regime
  sanft aufs Mittel zurückgeblendet (`derive_policy`, Regime-Blend Z. 358‑374).
- **Fundamental-Overlay** (Event-Risiko-Kalender + Makro-Stance) dämpft die **effektive** gerichtete Quote.
- **Vol-Targeting** → `suggested_exposure` (0..1, defensiv, **proposal-only**).

**Selbst-Verfeinerung** (`train_step`): Ratchet — innerhalb derselben Evidenz wird nur höhere Fitness
übernommen; ändert sich die Evidenz (`_evidence_fp`: Strategie-PFs + MN-Sharpes + Gewichtungs-Methodik),
**Re-Baseline**. Damit kann die persistierte Politik nicht auf veralteter, optimistischerer Evidenz
„festhängen". Sauber.

**Befund 1 (positiv):** Das Gehirn ist vollständig + ehrlich gehärtet. Im aktuellen Zustand (keine
Strategie PF>1, „Daten reifen") fällt der gerichtete Edge auf 0 → `_meta_split` gibt `mn_share→1.0` →
der Master stützt sich **korrekt defensiv auf den MN-Sockel**. Das ist gewolltes, ehrliches Verhalten.

## 2. Die „Hand": was real live ausgeführt wird (die zentrale Lücke)
Die **ausführende** `MasterMeta`-Freqtrade-Engine (`master_meta.py`) ist EIN aggressiver Futures-Bot
(BTC/ETH/SOL, Hebel-Basis 5). Sie konsumiert über die **Bridge-Datei** `data/hmm_regime.json`
(`tracker.write_regime_bridge` → `TBT_REGIME_FILE`) live genau:
- **HMM-Regime** → schaltet die Sub-Logik (trend_up→MACD-Long · range→BB-Mean-Reversion-Long ·
  trend_down→MACD-Short), überschreibt die jüngste Kerze.
- **HMM-Konfidenz** → skaliert den Hebel (Basis→max).
- **Fundamental `lev_scale`** → drosselt den Hebel defensiv vor Events.

**Befund 2 (die Wahrheit über „greift auf ALLES"):** Gehirn und Hand sind **partiell** gekoppelt.
Live an die Hand fließen Regime + Konfidenz + Event-Hebel-Scale. **NICHT** an die Hand fließen:
1. Die **per-Regime-Strategie-Auswahl** der Politik (z. B. „in range bevorzuge FuturesBbandsBounce") —
   der MasterMeta-Bot nutzt seine **eigene fixe** Sub-Logik je Regime, nicht die gelernte Bestauswahl.
2. Die **MN-Sockel-Gewichtung** (mn_share) — der Sockel ist **simulation-only**, es gibt bis M6 keinen
   Ausführungs-Pfad. Korrekt so (kein Real-Geld-MN bis Freigabe).
3. **`suggested_exposure` / Vol-Targeting / Expectancy** — **proposal-only**, NICHT ins Live-Sizing
   verdrahtet (freqtrade nutzt festen `stake_amount`; nur der `leverage()`-Callback liest Konfidenz +
   lev_scale, aber NICHT die Exposure-Empfehlung).

Das ist **kein Bug**, sondern Architektur: eine Politik auf **Portfolio-Ebene** (Allokation über die
ganze Flotte + MN-Engines) lässt sich nicht 1:1 in eine einzelne per-Pair-freqtrade-Strategie pressen.
Aber: die „Intelligenz" der Strategie-Auswahl + des Sizings ist heute **beratend** (UI/Flotte), nicht
**ausführend**. Das ehrlich zu benennen ist wichtig — der Master ist näher an einem „Portfolio-Berater
+ regime-gekoppelter Einzel-Bot" als an einem „einen Schalter, der alles steuert".

## 3. Wird er „exponentiell schlauer"? — ehrliche Einordnung
**Nein, nicht exponentiell.** Der Master ist ein disziplinierter **Hill-Climbing-Ratchet** mit
Re-Baseline. Er verbessert sich **monoton**, wenn (a) OOS-Validierungen gerichtete Edges bestätigen und
(b) die MN-Forward-Tracks die Sim-Sharpes live halten/widerlegen. Gedeckelt ist er durch die **Qualität
der zugrundeliegenden Edges** und die **„Daten reifen"-Schranke** (≥90 T Historie + ≥3 Regime). Der
echte Sprung — ein selbst-trainierender RL-Agent über Live-Märkte — ist im Code explizit als **späterer
großer Ausbau** markiert (`master.py` Modul-Docstring, Blueprint §6). Die ehrliche Formel ist also:
**„kompoundiert via Ratchet + ehrliche Re-Baseline, datenreife-gegated"**, nicht „exponentiell".

## 4. Wechselwirkung mit den frischen Arbeiten dieser Session
- **Shorts (Task 1/B):** Die jetzt short-fähigen gerichteten Engines verbessern den **realisierten** Edge
  trend-getaggter Strategien im `trend_down` (der MasterMeta-Bot shortet dort ohnehin schon). Positive
  Wechselwirkung **ohne** Master-Änderung — die Politik bevorzugt im Abwärtstrend weiter Trend-Strategien
  (`_REG_MAP: trend_down→trend`), die nun auch verdienen können statt nur auszusetzen.
- **MN-Paper-Bots (Task 2):** Werden **bewusst NICHT** vom Master ingestiert — `MN_ENGINES` zieht die
  **kanonischen** Engine-Edges (eine globale Config je Engine), nicht beliebige Nutzer-Instanzen. Das ist
  die richtige Trennung (sonst könnte ein optimistisch getunter Paper-Bot die Sockel-Gewichtung
  verzerren). Bei Bedarf wäre „best paper-bot je Engine als Kandidat" ein bewusster späterer Schritt.

## 5. Empfohlene Wert-Hebel (FREIGABE-/Entscheidungs-nötig, keine Bugs)
1. **Expectancy-Sizing live-fähig machen** (Task 4): heute ist Sizing nur vol-basiert + proposal-only;
   `suggested_exposure` erreicht die Hand nicht. → siehe Sizing-Arbeit dieser Session (Erwartungswert/
   Kelly mit harten Caps, opt-in, proposal-only) als ehrliche Vorstufe zum echten M6-Sizing.
   **★ UMGESETZT 03.07.2026 (FP-2, Branch `chat/tb-kelly`):** Klemmkette K0–K6 + Brücke
   `suggested_sizing.json` → `custom_stake_amount` (opt-in · proposal-only-Default · nur dry_run) —
   normative SPEC inkl. Ruin-Beleg: **`docs/KELLY_SIZING_SPEC.md`**.
2. **Politik→Hand enger koppeln (optional, größer):** die per-Regime-Bestauswahl der Politik könnte den
   MasterMeta-Bot tatsächlich umschalten (statt fixer Sub-Logik) — bräuchte eine Strategie-Auswahl-Bridge
   analog zur Regime-Bridge. Architektur-Entscheid (Nutzer), kein Schnellschuss.
   **★ GEBAUT 03.07.2026 (FP-T5, Branch `chat/tb-t5`):** Brücke `suggested_policy.json` → Sub-Logik-
   Wahl/Stake-Dämpfung/Edge-Gating der MasterMeta-Engine, Klemmkette Politik→Governor→Konzentration→
   Sizing + Sim-/Byte-Identitäts-Beleg — normative SPEC: **`docs/POLICY_HAND_SPEC.md`**.
   **Gate G-T5 OFFEN:** Defaults inert/proposal-only, scharf erst nach Nutzer-Entscheid (SPEC §8).
3. **MN-Sockel-Ausführung (M6):** erst mit Echtgeld-Freigabe; bis dahin korrekt sim-only.

**Fazit:** Der Master ist exzellent als ehrliches Portfolio-**Gehirn** (zieht auf alles, hart gehärtet,
defensiv korrekt). Die **Ausführung** ist heute bewusst partiell (Regime+Hebel live, Strategie-Auswahl +
Sizing + MN beratend). „Exponentiell schlauer" ist aspirational; real ist es ein sauberer, datenreife-
gegateter Ratchet. Größte ehrliche Hebel = Expectancy-Sizing (in Arbeit) + optional eine Strategie-
Auswahl-Bridge.
