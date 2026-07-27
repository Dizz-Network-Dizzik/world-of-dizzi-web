# 🌙 Arbeitspaket (autonom, Nacht 2) — Recherchetool-Upgrade „2.0"

**Auftrag:** Das Strategie-Recherchetool (`ai.py`) maßgeblich upgraden, sodass (1) ALLE neuen KI-Faktoren
(HMM-Regime, Fundamental/Event-Risiko, markt-neutrale Edges, OOS-/Deflated-Sharpe-Härtung) ins
Strategie-Research/in die Qualifizierung einfließen, (2) zwei explizite, prominente Entscheidungs-Scores
entstehen — **Sicherheit** (wie belastbar die Infos sind) und **Effizienz** (wie effizient die Strategie ist) —
und (3) diese in der UI klar in den Fokus rücken. Freigaben: ich wähle die sinnvollste/empfohlene Variante,
frage nicht nach. Invarianten: 30/30, Tests grün, proposal-only, 0 Risiko.

**Recherche-Grounding (Quellen im Backlog):** LLM-Strategien überoptimieren auf „schöne Backtests" →
Scores an EIGENE OOS-Daten grounden (reproduzierbar), Bias hart abwerten. Effizienz = Profit-Faktor (≥1.5
viabel/≥2 stark, >3 Overfit-Warnung) + Expectancy/RR + Drawdown, kombiniert; ≥100 Trades für Signifikanz.

## Schritte
- [x] **R1 — Scoring-Kern + neue Felder.** `efficiency` (Kategorie) + `event_sensitivity` ins Schema;
      reine, testbare `security_score()` / `efficiency_score()` → 0–100 + Begründung. Sicherheit aus
      certainty + Methode (OOS/WF vs in-sample) + backtest_count + Bias-Abzug; Effizienz aus Profit-Faktor/
      Risk/Reaktivität (Overfit-Deckel). Tests.
- [x] **R2 — Grounding an eigene Evidenz.** Match researchter Systeme an `stats.strategy_validations`/
      `optimizations` (per freqtrade_template) → Sicherheit mit REALER OOS-PF/Fenster-Zahl anheben +
      „im System validiert"-Flag. Deterministisch, reproduzierbar. Tests.
- [x] **R3 — Prompt-Upgrade.** Dem Modell die neuen System-Fähigkeiten erklären (HMM-Regime, Event-Risiko,
      MN-Sockel, Deflated-Sharpe) + `efficiency` + `event_sensitivity` + Regime-Fit anfordern; „schöner
      Backtest = Warnsignal" schärfen.
- [x] **R4 — Neue KI-Faktoren als Katalog-Dimensionen.** `event_sensitivity` (Makro-Event-Exposure),
      Regime-Fit relativ zu unseren HMM-Regimes, `market_neutral` (vorhanden) konsistent normalisieren.
- [x] **R5 — API/Integration.** `get_catalog`/`_normalize_system` hängen die Scores immer an; Re-Score
      gegen aktuelle eigene Evidenz beim Laden. Endpoint liefert Scores.
- [x] **R6 — UI in den Fokus.** Sicherheit + Effizienz als prominente, farbcodierte Score-Balken je
      Strategie in der Katalog-Tabelle; sortier-/filterbar nach beiden; die zwei primären Entscheidungs-
      Spalten. Tooltips erklären die Herleitung.
- [x] **R7 — Docs + Live-Verifikation.** RESEARCH_TOOL-Doc + Übersicht aktualisieren; Browser-Check.

## Danach (Dauer-Phase, fortlaufend)
Reguläre Systemkontrollen/Beobachtungen + Recherche WEITER; zusätzlich das Recherchetool-Verhalten
beobachten und in KLEINEN Schritten weiter verbessern (kein zweites Riesenpaket) — selbst strukturiert.
