# PROPOSAL — Datenquellen & Lern-Mechaniken: wo echter Edge herkommt (Bau-KI-Runde 10, 19.06.2026)

**Charakter:** Strategische System-Durchleuchtung + Recherche + priorisierte Roadmap. Proposal-only, 0 Echtgeld, kein Code geändert.
**Auftrag (Nutzer):** Das ganze System durchleuchten (wie der Lernprozess + die KI-Ebenen interagieren), recherchieren wo Verbesserung herkommt (jenseits von „laufen lassen"), besonders **neue Datenquellen** (Live-Wirtschaftsdaten/Fundamental in Realtime) — was machen starke Bots, um eine erfolgreichere Lern-KI zu bauen.

---

## 1. WIE DAS SYSTEM HEUTE LERNT (Code-Durchleuchtung)

**Drei Lern-Ebenen + Overlay (verifiziert im Code):**
1. **Strategie-Ebene (`meta.py`):** klassische TA-Strategien (RSI/MACD/BBands/Grid/DCA/SessionOpen) werden per **anchored Walk-Forward** (optimize/evolve/validate) getunt; nur `oos_validated`-Gewinner zählen. **Input = NUR Preis (OHLCV).**
2. **MN-Sockel (`csm/pairs/marketmaking`):** markt-neutrale Sim-Edges (Cross-Sectional Momentum = der eine echte; Pairs/StatArb negativ; MM = Avellaneda-Stoikov-Sim). **Input = NUR Preis** (CSM) bzw. synthetisch (MM).
3. **Master-Ensemble (`master.py`):** aggregiert validierte Erkenntnisse → Regime→Strategie-Allokation + Sockel-Gewichtung. Deflated-Sharpe/PSR/1-N-Benchmark.
4. **Autopilot (`autopilot.py`):** treibt alle 6 h einen Verbesserungs-Schritt (Governor → MasterMeta-Improve → Auto-Upgrade → Cull → Auto-Validate).
5. **HMM-Regime (`hmm.py`):** Gaussian-HMM über den BTC+ETH+SOL-Index.

**★ ZENTRALER BEFUND — die Fundamental-Schicht ist REICH, wird aber nur DEFENSIV genutzt:**
`fundamental.py` (624 Z.) zieht bereits **key-frei**: Wirtschaftskalender (ForexFactory: FOMC/CPI/NFP + `macro_surprise` actual-vs-forecast → hawkish/dovish), CoinGecko (BTC-Dominanz/MCap-Trend), On-Chain (blockchain.info: Active Addresses/NVT/Hash-Rate), Deribit **DVOL** (Options-implizite Vola). **ABER:** all das fließt NUR in `dir_scale` = ein **Risk-Off-Schalter**, der das gerichtete Sleeve bei Events DÄMPFT. **Es wird KEIN einziges dieser Signale als prädiktives FEATURE genutzt.** Die Daten sind da — der Edge daraus liegt brach.

**⇒ Die zwei strukturellen Grenzen:**
- (a) Strategien/Engines handeln **nur auf Preis** + klassischer TA — keine alternativen Daten als Alpha.
- (b) Reiche Fundamental-Daten werden **defensiv (dämpfen) statt prädiktiv (vorhersagen)** verwendet.
- (c) Das „Lernen" ist **Parameter-Tuning** (Grid/Evolve auf Backtest-Sharpe), **kein Feature→Signal-Modell** (kein ML/Kalibrierung).

---

## 2. WAS STARKE QUANT-/CRYPTO-BOTS NUTZEN (Recherche)

| Datenquelle | Dokumentierter Edge | In DIESEM System? |
|---|---|---|
| **Funding-Raten** (Extreme >0.1 %/8 h) | überhitzt → Mean-Reversion/Korrektur | teils (csm zieht ~30 T, nur als **Drag**, nicht Feature) |
| **Open Interest** (OI-Trend) | Leverage/Sentiment; OI↑+Funding↑ = fragil | ❌ nicht erfasst |
| **Liquidations-Cluster** | Reversal-Punkte (Long/Short-Kaskaden) | ❌ nicht erfasst |
| **Orderbuch-Imbalance/Tiefe** | Microstruktur, Execution, kurzfr. Signal | ❌ nicht erfasst |
| **On-Chain** (Adressen/NVT/Flows) | Adoption/Bewertung | teils (nur Overlay) |
| **Sentiment** (Fear&Greed/Social) | Extreme = Mean-Reversion | ❌ nicht erfasst |
| **Makro/Cross-Asset** (DXY, Rates, Risk) | Regime/Risk-On-Off | teils (Kalender nur Overlay) |
| **Options-Vola (DVOL/Skew)** | Vol-Regime, Tail-Risiko | teils (DVOL nur Overlay) |

**Mechanik (was funktioniert, ehrlich):** Ensemble-ML (Gradient Boosting/Random Forest) auf Features → Richtungs-/Mean-Reversion-Wahrscheinlichkeit; Multi-Timeframe; **Signal-Kalibrierung** > rohe Trefferquote. **Warnung:** die zitierten „65–67 % directional accuracy" sind notorisch in-sample/cherry-picked — Krypto-ML overfittet brutal. Die **PBO/anchored-WF-Disziplin dieses Systems ist genau der Schutz**, der den meisten Hobby-Bots fehlt.

**Live-Daten-Connectors (Claude/MCP — vom Nutzer erwähnt):** Trading Economics MCP (Live-Wirtschaftsdaten/Kalender/Indikatoren), Alpha Vantage MCP (Markt/FX), TradingView MCP (TA/Charts), Anthropic „Claude for Financial Services" (pre-built Finanz-Connectors). → real existierend; nutzbar als Feature-Feed.

---

## 3. EHRLICHE MACHBARKEIT (ccxt Bitget, LIVE geprüft)

| Methode | Verfügbar? | Konsequenz |
|---|---|---|
| `fetchOpenInterest` | ✅ live | OI nur **live** sammelbar |
| `fetchOpenInterestHistory` | ❌ | **keine OI-Historie** → nicht direkt backtestbar |
| `fetchFundingRateHistory` | ✅ aber **nur ~30 T** | kurze Historie (R3 bestätigt) |
| `fetchLiquidations` | ❌ (Bitget) | **keine** öffentl. Liquidations über ccxt |
| `fetchOrderBook` | ✅ live | Imbalance nur **live** (Snapshot) |

**★ DER EIGENTLICHE ENGPASS:** Die wertvollsten Derivate-Daten (OI, Liquidations, Funding-Langhistorie) sind bei Bitget **nicht historisch** abrufbar — nur **live/forward**. ⇒ Man kann ihren Edge **nicht sofort backtesten**, sondern muss ihn **forward über Wochen/Monate sammeln** ODER eine **bezahlte Daten-Quelle** (Coinglass/Laevitas/Amberdata/Kaiko) für historische Derivate kaufen. Das ist die zentrale strategische Weichenstellung.

---

## 4. PRIORISIERTE ROADMAP (Edge × Machbarkeit × Ehrlichkeit)

**★ HEBEL A — Vorhandene Fundamental-Daten von DEFENSIV auf PRÄDIKTIV (sofort machbar, 0 neue Datenquelle):**
Die Daten sind schon da (Kalender/`macro_surprise`/On-Chain/DVOL/CoinGecko). Statt nur `dir_scale` zu dämpfen: als **Features** in eine Vorhersage-Schicht. Z.B. `macro_surprise.direction` (hawkish/dovish) + DVOL-Trend + Dominanz-Trend → ein **Regime-/Tilt-Signal**, anchored-WF + PBO-validiert. **Geringes Risiko, nutzt Brachliegendes.** Ehrliche Erwartung: moderater, aber sauberer Test, ob diese Signale überhaupt prädiktiv sind (viele sind ausgepreist).

**★ HEBEL B — Forward-Daten-Sammlung starten (der ehrliche Weg zu Derivate-Edge):**
Einen **read-only Daten-Track** bauen, der OI + Funding + Orderbuch-Imbalance + Fear&Greed **täglich live** mitschreibt (eigene Tabelle, wie `csm_equity_log`). Nach Wochen/Monaten ist eine **backtestbare Historie** da → dann OI/Funding-Extreme als Mean-Reversion-Signal ehrlich validieren. **Startet die Uhr für den wertvollsten Edge.** Kostenlos, aber Geduld nötig.

**★ HEBEL C — Sentiment (Fear&Greed, alternative.me, key-frei, HAT Historie):**
Im Gegensatz zu OI hat der Fear&Greed-Index **historische Daten** → sofort backtestbar. Extreme-Fear→Long-Tilt ist ein dokumentierter (wenn auch ausgepreister) Mean-Reversion-Edge. **Schnell + ehrlich testbar.**

**★ HEBEL D — Live-Makro-Feed (Trading Economics MCP / key-freie Alternativen):**
Makro-Regime-Features (DXY, US-Rates, Risk-Sentiment) als Regime-Kontext. Trading Economics MCP (guest-Tier limitiert / bezahlt) oder key-freie Quellen (FRED hat das System teils schon). Für ein DEMO-System: erst prüfen, ob Makro-Features OOS überhaupt tragen, bevor bezahlt.

**★ HEBEL E — Ehrliche ML-Feature-Schicht (Mechanik-Upgrade, NACH A–D):**
Wenn Features da sind: ein **kalibriertes** Modell (logistische Regression / Gradient Boosting) Features→Wahrscheinlichkeit, streng **anchored-WF + PBO + Kalibrierungs-Check** (sagt 60 % ⇒ trifft 60 %?). Hürde: numpy/sklearn nicht im Backend-venv (reines Python) → entweder reines-Python-Logit (machbar) oder Engine-venv. **Hier ist die PBO-Disziplin entscheidend** — Krypto-ML overfittet sonst.

**❌ NICHT empfohlen (Ehrlichkeit):** sofort bezahlte Tick/Orderbuch-Daten für HFT-artige Signale — DIESES System hat **keinen Latenz-Vorteil** (Demo, tägliche/stündliche Frequenz); der Edge von Microstruktur/Latenz ist für uns nicht abgreifbar.

---

## 5. EHRLICHE GESAMT-EINSCHÄTZUNG

- **Der größte Hebel ist NICHT eine einzelne neue Datenquelle** (Funding/OI/Sentiment sind öffentlich → weitgehend ausgepreist; R3 hat Funding-Carry schon als nicht-viabel entlarvt), sondern: **(1)** die schon-vorhandenen Daten **prädiktiv statt defensiv** nutzen (Hebel A), **(2)** die fehlenden Derivate-Daten **forward sammeln** (Hebel B), **(3)** eine **kalibrierte, PBO-disziplinierte** Feature-Schicht (Hebel E).
- **Was uns von „durch die Decke gehenden" Bots unterscheidet, ist NICHT Cleverness, sondern Daten-Zugang (historische Derivate) + Latenz** — beides für ein ehrliches Demo-System nur begrenzt/bezahlt erschließbar.
- **Unser struktureller Vorteil:** die **Ehrlichkeits-Disziplin** (anchored WF, PBO, sim_discount, deflated Sharpe). Die meisten Hobby-/Hype-Bots zeigen In-Sample-Mirages; unser System würde einen echten Feature-Edge erkennen UND einen falschen ablehnen.
- **Konkreter Startpunkt-Vorschlag (kostenlos, ehrlich, sofort):** Hebel **C (Fear&Greed, backtestbar)** + **B (Forward-Track OI/Funding/Orderbuch starten)** parallel — der erste gibt sofort ein ehrliches Ja/Nein, der zweite baut die Uhr für den Derivate-Edge auf. Hebel A als prädiktiver Re-Use des Vorhandenen. Alles mit der bestehenden anchored-WF/PBO-Methodik.

**Nächster Entscheid (Nutzer):** Welchen Hebel zuerst treiben? Empfehlung: **C + B** (kostenlos, ehrlich, sofort startbar). Bezahlte Daten (Coinglass/Trading-Economics) nur, wenn ein Forward-Test/Backtest den Edge vorab belegt.
