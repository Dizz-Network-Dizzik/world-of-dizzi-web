# 🗺️ Projekt „Trading Bot eins" — Gesamtstand & Plan (2026-06-10)

**Was es ist:** Krypto-Trading-Bot-Manager (Hybrid Freqtrade-Engine + eigene KI-/Meta-Schicht), der mehrere
Strategien parallel fährt, sich selbst verbessert und ein Gesamt-Portfolio überwacht. **Demo/Paper, 0 Echtgeld** —
Echtgeld erst per ausdrücklicher Freigabe (M6).

## Wo wir stehen
| Kennzahl | Wert |
|---|---|
| Flotte | **51 Bots** (alle Futures, **alle dynamisch gestreut**): 19 Scalping · 15 Intraday · 1 Swing · 16 Börsenöffnung + MasterMeta |
| Live | **51/51 laufen** (`:8137`), Engine verfügbar |
| Code | **278 Tests grün**, 37 Backend-Module, ~117 REST-Routen, 38 Test-Dateien |
| Git | Haupt-Repo `7a2118f` clean · Backup-Refresh ausstehend |
| Risiko | **0 Echtgeld** — reines Paper-Trading |

## Architektur (4 Schichten)
```
UI / DASHBOARD        Statistik · KI-Tool · Katalog · Bots · Icon-Legende
PORTFOLIO-EBENE       P1 Governor · P2 Konzentration · P3 Vola-Sizing · P4 Slippage · P5 Alerts
KI-/LERN-EBENE        MasterMeta-König + Autopilot · 3 Lern-Ebenen · Gaussian-HMM · Fundamental-Overlay · Ensemble
BOT-/ENGINE-EBENE     51 Bots · Freqtrade (dry-run) · Bitget-Daten
```

## Erledigt
- **Fundament (M1–M5):** Orchestrator + Dashboard, Multi-Bot-Registry, Risiko-Parameter, Freqtrade-Integration,
  Ein-Ordner-Migration (Live = Git-Quelle).
- **KI-/Lern-System:** 3 Lern-Ebenen (Meta / 4 markt-neutrale Sim-Engines / Master-Ensemble), Gaussian-HMM,
  Fundamental-Overlay (Kalender/Event-Risiko, FRED-Makro, On-Chain, DVOL), MasterMeta-Bot + Autopilot, Auto-Cull,
  Recherchetool (Multi-Metrik-Kanon).
- **Portfolio-Ebene (P1–P5):** Risk-Governor, Konzentrations-Bewusstsein (HHI/Cluster), Vola-Sizing,
  Slippage-Tracking (M6-Prep), Monitoring/Alerting, `cache.py` (Effizienz).
- **Horizont-/UI-Umbau (10.06.):** Zeit-Horizont-Modell (Scalping/Intraday/Swing) systemweit statt Spot/Futures
  (alle Bots → Futures), Auto-Upgrade pro Bot, Statistik mit klickbaren Filter-Kacheln, aufgeräumtes KI-Tool
  (MasterMeta-König), Katalog mit Filterleiste, reparierte Icon-Legende.
- **„Pairs streuen" (10.06., HEAD `0d1798b`):** `universe.py` = Single Source of Truth — kuratiertes, liquiditäts-
  gestaffeltes Bitget-USDT-Perp-Universum (14 Coins/3 Tiers), aus dem Freqtrade per VolumePairList **dynamisch
  nach Volumen** horizont-gedeckelt auswählt (Scalping Top-5/10, Intraday Top-8/14, Swing Top-10/14). `pair_mode`
  static|dynamic, `diversify_fleet`, `/api/universe(+/diversify)`. **Beseitigt den BTC/ETH/SOL-Klumpen**:
  concentration HHI ~3000→**848**, Majors-Cluster ~100%→**27%**. ai-Recherchetool kennt das Universum; UI zeigt
  je Bot die gehandelten Coins. Flotte live re-gestreut, Backup refresht.
- **Effizienz-/Infra-/UI-Folge-Runden (10.06., bis `2054ea4`):** **429-Last behoben** (`ccxt_async_config`
  enableRateLimit/rateLimit 500 je Bot → ~90/h→einstellig), FastAPI-**Lifespan** statt `on_event`, **Read-Caches** auf
  summary/meta/concentration/sizing/execution/governor (+Invalidierung nach Mutationen), stats Schema/Migration
  nur 1×/DB-Pfad, Trade-DBs **read-only**, exchange Client-Reuse+Cache+Timeout (M6-Prep), **SpreadFilter** in der
  Pairlist-Kette. **UI**: MasterMeta-König nur Kern-Stats+kompakter Graf sofort (Rest ausklappbar), Statistik-Upgrade-
  Badge, KI-Panels default eingeklappt + Filter erhält Zustand, Legenden-Schleuder (Gegenvektor) + Screen-Wrap,
  Katalog erklärt Universum; **alle Graphen** kompakter mit Y-Raster/Werten/Zeitachse/ROI; Upgrade-Banner „Alle/
  Auswählen…"-Dialog. **Autopilot „Pausieren" entfernt** (König läuft permanent).
- **Robustheit + Lernsektor (10.06.):** **Auto-Resume nach Systemausfall** (`_resume_fleet`: gecrashte „running"-Bots
  beim Backend-Start gestaffelt nachstarten, end-to-end bewiesen) · Lern-Loop: **Random-Search-Startpool** +
  **Embargo 1** + **Auto-Validierung** (1 unvalidierte Engine-Strategie je Autopilot-Tick → Evidenz wächst selbst).
- **METHODIK-HÄRTUNG (10.06. nachts, `347bfba`, 278 Tests):** Tiefen-Review der KI-Ebene umgesetzt —
  **anchored Walk-Forward** (Kandidaten-Selektion NUR auf dem Trainings-Fenster, einmaliger OOS-Test des Gewinners
  auf dem ungesehenen Test-Fenster; `oos_validated`/`timeframe` persistiert; vorher war der „Gewinner" ein best-of-N
  auf den Validierungsfenstern = Selektions-Bias) · Validierungs-Gate je Fenster jetzt **Profit > 0** · **Pairs-Auswahl
  kausal** (Formation-Phase 180 T; Live-Beweis: Pairs-Sharpe positiv→−1,24 = alter Wert war Lookahead, Gewicht jetzt 0) ·
  **HMM** Dual-Init/Warm-Start aus persistiertem Modell + 300 Kerzen · **Master**: Deflated-Sharpe-Korrektur AKTIV
  (deflate_factor 0.4) + **1/N-Benchmark** (DeMiguel) im Ensemble-Panel · **Auto-Upgrade** rollt nur noch OOS-validierte
  Gewinner bei Timeframe-Match aus (manuell mit Warnung weiter möglich) · bisect/Backtest-Lock/TTL-Memo.

## Roadmap / Offen
- **Kurzfristig:** Flotte ein paar Tage laufen lassen → Auto-Upgrade/Governor/Slippage/Echtgeld-Reife mit echten
  Daten beobachten (P3-Sizing greift ab ≥3 Tagen Vola-Historie).
- **Mittelfristig:** „Pairs streuen" ✅ **erledigt** (10.06., dynamisches Volumen-Universum, Klumpen weg) ·
  UI-Feinschliff nach Browser-Durchgang · optional bezahlte Tief-On-Chain-Daten.
- **Erledigt (Folge-Runden):** ✅ Bitget-429-Last (Rate-Limit je Bot) · ✅ `jsonstore`-WinError5-Härtung · ✅ Effizienz-
  Caches + stats-Optimierung · ✅ SpreadFilter. **Optional offen:** Konzentrations-Metrik misst das *zulässige
  Universum*, nicht offene Positionen (optimistisch — optional verfeinern).
- **Später-Liste (bewusst vertagt, mit Trigger):** *Optuna/Bayesian-Optimization* → nach M6 (lohnt erst bei
  deutlich größeren Parameter-Suchräumen; bis dahin deckt der Random-Search-Startpool das ab, ohne neue
  Dependency). *Regime-konditionierte Parametersätze* (je Regime ein Gewinner statt einem global) → erst wenn
  mehrere Strategie×Regime-Zellen **n≥100 Trades** UND **≥3 unabhängige Regime-Episoden je Regime** haben
  (messbar in `/api/meta.regime_performance_trades`; sonst Stichproben-Drittelung × Multiple-Testing = Overfit).
- **Großer Schritt — M6 (Echtgeld):** Bitget-Live-Keys, beobachtbarer „Auf Echtgeld heben"-Flow (freigeben →
  überweisen → live), echte Slippage-Messung greift. Voraussetzung: konsistente Daten + echtgeldreife Strategien +
  ausdrückliche Freigabe.
- **Aufräumen:** `trading-bot-trial`-Ordner (eingefrorener Rollback) löschen, sobald der neue Stand stabil läuft.

## Kurz gesagt
Produkt steht — vollständige Lern-KI + Portfolio-Risiko-Schicht + aufgeräumtes UI, getestet/committet/gesichert.
Nächster Hebel = Zeit (Daten reifen) + Diversifikation; großer offener Schritt = M6 (Echtgeld, hinter Freigabe).
