# 📐 Metrik-Kanon & Recherche — Definition eines Trading-Systems (2026-06-09)

Recherche-gegroundete Grundlage für das Recherchetool-Upgrade: **welche Metriken/Parameter definieren ein
Trading-System klar**, **was sammelt jede einzelne AI im Bot**, und **wo findet man gut definierte, effiziente
Systeme**. Leitsatz aus der Recherche: **„Never trust a single metric"** — ein robustes System besteht mehrere
Filter; fällt es bei ≥2 durch, vor Echtgeld untersuchen.

## 1. Der Metrik-Kanon (klar definiert, mit Formeln)
| Metrik | Definition / Formel | Richtwert |
|---|---|---|
| **Profit-Faktor (PF)** | Bruttogewinne / Bruttoverluste | >1 profitabel · ≥1.5 viabel · >3 Overfit-Verdacht |
| **Win-Rate (w)** | Anteil Gewinn-Trades | kontextabhängig (niedrig ok bei hohem RR) |
| **Expectancy (R)** | `w·RR − (1−w)`, mit `RR = PF·(1−w)/w` | >0 nötig; >0.1R gut |
| **Max-Drawdown (MaxDD)** | größter Peak-to-Trough-Verlust | kleiner = besser; Kapitalerhalt/Tail-Risiko |
| **Calmar / CAR-MDD** | annualisierte Rendite / MaxDD | ≥1 solide · ≥2 stark |
| **Sharpe** | Überrendite / Gesamt-Vola | >1 gut (risikoadjustiert) |
| **Sortino** | Überrendite / **Downside**-Vola | >1.5 gut · >2 stark |
| **SQN** (Van Tharp) | `Expectancy/σ · √Trades` | kombiniert Edge·Konsistenz·Häufigkeit |
| **Deflated/Probabilistic Sharpe** | Sharpe korrigiert für #Trials, n, Schiefe/Kurtosis | P(echte Sharpe>0); gegen Multiple-Testing/fat tails |
| **Trade-Signifikanz** | ≥100 Trades | darunter statistisch schwach |
| **Parameter-Robustheit** | ±10 % um Optimum ähnliche Performance | instabil = Overfit-Signal |
| **OOS / Walk-Forward** | Out-of-Sample-Bestätigung | Pflicht vor Echtgeld |

## 2. Was sammelt / gewichtet jede AI im System (Ist-Stand)
| AI / Modul | Sammelt | Legt Wert auf |
|---|---|---|
| **meta.py** (Einzelstrategie-Lernen) | PF, Return %, MaxDD %, Trades, Win-Rate je Strategie | OOS-Walk-Forward, Selektions-Bias-Konfidenz |
| **master.py** (Ensemble) | OOS-Sharpe, Konfidenz, PF, Regime-Allokation, mn_share | OOS-Härtung: **PSR · Deflated-Sharpe · Kappung · Soft-Voting** |
| **mn_base** (CSM/Pairs/StatArb/MM) | ann_pct, total_return, **maxdd, Sharpe, Skew, Kurtosis, PSR** | Sharpe + fat-tail-korrigierte PSR |
| **hmm.py** (Regime) | Regime, Konfidenz, Persistenz, Übergangs-Wahrsch. | global-konsistente, stabile Regime |
| **fundamental.py** (Overlay) | Event-Risiko, Makro-Stance, On-Chain, DVOL, Makro-Surprise | defensives Dämpfen vor High-Impact-Events |
| **tracker.py** | Regime, trend_z, Vol-Regime, Volatilität | vola-normierte Einordnung |
| **ai.py** (Recherchetool) | **Sicherheit + Effizienz (0–100)** + jetzt **Metrik-Kanon** | an EIGENE OOS-Evidenz gegroundet, Bias-Abwertung |

## 3. Recherchetool-Upgrade (dieser Stand)
Vorher gründete der **Effizienz-Score auf einem Maß (Profit-Faktor)**. Jetzt ist er ein **Multi-Metrik-
Komposit** (`ai.compute_metrics` + `efficiency_score`): PF-Basis, justiert nach **Calmar**, **Expectancy (R)**,
**Drawdown-Strafe** und **Trade-Signifikanz**, mit **Overfit-Deckel bei PF>3**. Jedes recherchierte System
trägt jetzt ein `metrics`-Objekt (PF, Win-Rate, MaxDD, Return, Trades, Expectancy_R, Calmar, signifikant),
abgeleitet aus der eigenen OOS-Evidenz — reproduzierbar, nicht „schöner Backtest". (Sharpe/Sortino/SQN je
Freqtrade-System brauchen Trade-Level-Renditen → Ausbaustufe; die MN-Engines liefern Sharpe/PSR bereits.)

## 4. Wo findet man gut definierte, effiziente Systeme (Quellen)
- **awesome-systematic-trading** (paperswithbacktest/wangzhe3224) — kuratierte Libraries, **40+ akademische
  Strategie-Papers nach Sharpe sortiert**, 55 Quant-Bücher. (GitHub)
- **Robert Carver — „Systematic Trading"** (Standardwerk Systemdesign/Risiko-Skalierung).
- **QuantifiedStrategies.com** — Performance-Metriken + dokumentierte Backtests.
- **BuildAlpha — Robustness-Testing-Guide** (Parameter-Stabilität, Monte-Carlo, OOS).
- **QuantInsti-Blog** — systematisches Trading, Regime/HMM, Walk-Forward.

### Quellen (Web-Recherche 06/2026)
- [QuantifiedStrategies — Trading Performance/Metriken](https://www.quantifiedstrategies.com/trading-performance/)
- [Nurp — 5 Key Metrics for Automated Trading](https://nurp.com/algorithmic-trading-blog/5-key-metrics-automated-trading-systems/)
- [TradingWyckoff — Advanced Metrics (SQN/K-Ratio)](https://tradingwyckoff.com/en/algorithmic-trading/advanced-trading-metrics/)
- [BuildAlpha — Robustness Testing Guide](https://www.buildalpha.com/robustness-testing-guide/)
- [awesome-systematic-trading (GitHub)](https://github.com/paperswithbacktest/awesome-systematic-trading)
- [Carver — Systematic Trading (Buch)](https://www.amazon.com/Systematic-Trading-designing-trading-investing/dp/0857194453)
