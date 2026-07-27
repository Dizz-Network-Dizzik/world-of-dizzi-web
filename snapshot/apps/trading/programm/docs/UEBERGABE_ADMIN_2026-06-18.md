# Übergabe an den World-/Admin-Chat — „Dizz Trading" KI-Training (Bau-KI-Runden 1–6, 18.06.2026)

**Quelle:** TB-Trainings-App-Chat (Bau-KI 4.8). **HEAD:** `c078f42` · **Tests:** 327 grün (`.venv`-pytest) · **Repo clean** · 51/51 live, 0 stale.
**Charakter dieser Übergabe:** Alle Befunde sind **proposal-only, 0 Echtgeld**. Kein Backend-Neustart, kein Fleet-Eingriff durch den Trainings-Chat.
Dieses Dokument bündelt, **was der World-/Admin-Chat (strukturell/Ops) noch tun muss** — getrennt von dem, was im Trainings-Chat bleibt.

---

## ⚠️ 1. KRITISCH — was der nächste `:8137`-Neustart auslöst (VOR dem Neustart lesen)

Ein einziger Backend-Neustart lädt neuen Code **+ persistierte Config** auf einmal. Bewusst-Liste:

| Quelle | Effekt beim Neustart |
|---|---|
| **R5: `sim_discount=0.5`** (persistiert in `master_config`) | **Live-Master-Fitness sinkt 1.0313 → 0.6601.** GEWOLLT/ehrlich (MM ist eine optimistische Sim, jetzt zu 50 % diskontiert). **Reversibel:** `POST /api/master/config {"sim_discount":1.0}`. Code-Default bleibt 1.0. |
| **R2: regime_advice-Fix** (`_MIN_ADVICE_N=30 ∧ avg>0`) | RANGE empfiehlt nicht mehr FuturesMacdRsiScalp (die Verlust-Strategie). Rein advisory, treibt keine Allokation. |
| ältere committete Pakete (Vor-Training) | V11-Report-Sender + O-DEF + Bot-Health-Ampel + ccxt-Timeout-Migration (siehe WIEDEREINSTIEG §6). |

→ **Der World-Chat muss die Fitness-Senkung 1.03→0.66 WISSEN, bevor er neu startet.** Das ist kein Bug, sondern die ehrlichere Messung.
→ **Offene Entscheidung:** soll `sim_discount=0.5` zum Code-**Default** werden (MASTER_DEFAULTS)? (Derzeit Default 1.0, nur Runtime-Config = 0.5.)

---

## 2. Strukturelle Proposal-Entscheidungen (Architektur-Runde nötig — NICHT eigenmächtig im Training)

| Proposal | Stand nach Training | Empfehlung |
|---|---|---|
| **Regime-Gating** BBands/BreakoutVol/DcaDip | ⛔ **OOS-REFUTIERT (R4):** der regime-konditionierte Edge ist non-stationär (Vorzeichen-Flip train→test), Gate **schadet** OOS (t −4.40). | **NICHT bauen** — würde Live verschlechtern. |
| **Funding-Carry-Engine** (2. MN-Edge) | ⛔ **NICHT viabel (R3):** Variante B OOS combined Sharpe −6.76; liquide Majors Carry ≈0 nach Gebühren. | **Nicht bauen.** (Doku: `PROPOSAL_FUNDING_CARRY_ENGINE.md §8`.) |
| **FuturesMacdRsiScalp RETIRE** (G) | 🔬 stark gestützt durch ALLE Runden: 3285 Paper-Trades, verliert in jedem Regime + jeder Session; Evolve −34 %, live −3 %/Bot (10 Bots = größtes Verlust-Cluster). | **Retire / `echtgeldreif_disabled`** — bester struktureller Hebel. |
| **SessionOpenBreakout REVIEW** (H) | 🔬 283 Trades negativ; 16 Bots; near-breakeven OOS. | Review: retiren oder auf wenige Bots reduzieren. |
| **Pairs+StatArb Regime-Gate** (F) | 🔬 Engines strukturell negativ (Sharpe −0.89/−1.16); Regime-Gating generell OOS-fragil (R4). | **Niedrige Prio** — eher zurückstellen. |
| **GESETZE.md** fehlt im TB-Repo | offen (Infrastruktur) | Bei Gelegenheit anlegen (G10-Inhalt aus `DIZZ_NETWORK_CHAT_MANAGEMENT.md §3`). |

---

## 3. Ops (World-/Admin-Chat)

- **Backup-Snapshot nach dieser Session:** `programm_current_c078f42` (secret-frei, Junctions/`bin`/`.venv` aus) — Guardrail-Disziplin.
- **Netzwerk-Dashboard-Testzahl** auf **327** aktualisieren (`DIZZ_NETWORK_CHAT_MANAGEMENT.md §0`), falls noch 304/343 steht.

---

## 4. ★★ NEU — CSM Vol-Skalierung: aktivierungs-fertiger Edge (Entscheid: aktivieren?)

**Runde 7 (18.06.) hat den ersten echten OOS-Lift der Session gefunden + opt-in implementiert:**
- **Risk-adjusted Momentum** (`mom /= Tagesvola`) hebt CSM OOS-Sharpe **0.86 → 1.88** (anchored WF, PSR 0.99). **14/14 Robustheits-Stresses bestanden** (Survivorship entkräftet, kosten-/parameter-robust). Full-sample A/B: 0.24 → 1.41.
- **Implementiert als opt-in** `csm.py` `vol_scaled` (default OFF = Live unverändert), Optimizer-Grid erweitert, **Suite 329 grün**. NICHT aktiviert.
- **★ PAYOFF bei Aktivierung:** CSM qualifiziert als **2. aktive MN-Engine** (1.41 > Schwelle 0.833) ⇒ mit `sim_discount=0.5` (R5) = erster **ehrlicher 2-Engine-Sockel** (real-data CSM + diskontierte MM-Sim); „Master schlägt 1/N" wird **nicht-trivial** (statt N=1-Tautologie).
- **ENTSCHEID (Nutzer/World-Chat):** aktivieren? = `POST /api/csm/config {"vol_scaled":true}` + :8137-Neustart. Ändert das Live-CSM-Signal; ehrliche Erwartung: Performance marktphasen-abhängig (CSM-Edge zeitvariabel), aber der Lift über raw Momentum ist robust. **Empfehlung: aktivieren** — bestvalidierter Edge der Session, default-OFF macht es risikofrei reversibel (`vol_scaled:false`).

## 5. BLEIBT IM TRAININGS-CHAT (App-Chat — NICHT World-Chat-Sache)

- ⏳ **Daten reifen lassen** = die VORAUSSETZUNG für jede zeit-konditionale Edge-Validierung. **Re-Test-Trigger:** Trade-Historie **≥90 Tage UND ≥3 mehrtägige Regime-Episoden** → `research/regime_gate_backtest.py` + `research/coarse_regime_feasibility.py` erneut laufen (R4/R6 dann valide wiederholbar).
- 🔬 **CSM weiter:** der Optimizer kennt jetzt `vol_scaled` ⇒ künftige `/api/csm/optimize`-Läufe können es selbst vorschlagen; mit reifenden Daten neu prüfen.

---

## 6. 7-Runden-Bilanz (ehrlich, fürs Protokoll)

| R | Hebel | Ergebnis |
|---|---|---|
| 1 | Code-Audit | Master-Fitness = **100 % MM-Sim**, **==1/N bei N=1** (nicht „über") — Baselines korrigiert |
| 2 | regime_advice-Fix + Reife-Audit | 3-Zeilen-Bug behoben; Daten-Tor „passiert" (später relativiert) |
| 3 | Funding-Carry | ⛔ tot — Funding ertrinkt in Preis-Varianz |
| 4 | Regime-Gating | ⛔ non-stationär — schadet OOS |
| 5 | MM sim_discount | ✅ angewandt 0.5 — Headline ehrlich 1.03→0.66 |
| 6 | Coarser-Regime | ⛔ daten-blockiert — ROOT: 9-Tage-Trade-Historie |
| **7** | **CSM Vol-Skalierung** | ✅✅ **erster echter OOS-Lift: 0.86→1.88 (14/14 robust), opt-in implementiert** |

**Netto:** **EIN echter, OOS-robuster Edge gefunden (R7 CSM Vol-Skalierung)** + Mess-Ehrlichkeit deutlich gehärtet (R1/R5) + **3 Sackgassen sauber ausgeschlossen** (R3/R4/R6, statt als In-Sample-Mirage gebaut). Bei Aktivierung von R7+R5 zusammen: erster ehrlicher 2-Engine-Sockel, Master schlägt 1/N nicht-trivial.
Volle Details: `programm/docs/TRAINING_NACHT_MARATHON_2026-06-17.md` (Bau-KI-Runden 1–7) + `WIEDEREINSTIEG_PROMPT.md` (Mess-Baselines).
