# 📚 Recherche: Fundamentalanalyse & Wirtschaftskalender in unser KI-System (2026-06-08)

Recherche-Ergebnisse + empfohlenes Design für die neue Oberkategorie **„fundamental"**
(Fundamentalanalyse, Wirtschaftskalender, wirtschaftliche Großereignisse). Quellen unten.

---

## 1. Warum es zählt (Befund)
- **Krypto ist heute stark makro-getrieben.** BTC korreliert ~0,7+ mit Tech-Aktien; die **Fed-Liquidität
  (Zinsen, QT/QE) ist die wichtigste Makro-Variable** für BTC. Risk-on (niedrige VIX) → BTC stark; risk-off
  (VIX-Spikes) → BTC fällt mit, oft heftiger.
- **Hoch-Impact-Termine (FOMC, CPI, NFP) erzeugen Volatilitäts-Spitzen.** Profi-Praxis = **event-driven
  risk management**: vor High-Impact-Events Position verkleinern / Stops weiten / pausieren. „Ein bullishes
  Chartmuster wird von einem hawkischen FOMC sofort invalidiert" → der Kalender ist ein **Risiko-FILTER**
  über technischen Signalen, kein eigenständiges Alpha.
- **Das ist genau die Lücke unseres Systems:** unser HMM-Regime ist rein preisbasiert und sieht ein Event
  erst, *wenn es im Preis steht* — der Kalender ist **vorausschauend** (Termine sind im Voraus bekannt).

## 2. Zwei Säulen der „Fundamental"-Schicht
| Säule | Daten | Beste Nutzung |
|---|---|---|
| **A. Makro / Wirtschaftskalender** | FOMC, CPI, NFP, Zinsentscheide, GDP, PPI (geplant, vorausschauend) | **Event-Risiko-Overlay** (defensiv um bekannte Termine) + langsames **Makro-Regime** (easing/tightening, risk-on/off) |
| **B. Krypto-On-Chain-Fundamentals** | Active Addresses, NVT (≈ KGV), Exchange-Flows, Transaktions-Gebühren | langsame Bewertungs-/Conviction-Signale; eher Asset-Auswahl als Regime-Overlay |

**Best-Practice-Muster:** Base-Learner → Aggregation → **Event-/Regime-Filter als Overlay** (defensive
Risikosteuerung), nicht als Return-Prediktor. Passt 1:1 zu unserem proposal-only, defensiven Master.

## 3. Datenquellen-Vergleich
| Quelle | Inhalt | Key? | Eignung für uns |
|---|---|---|---|
| **faireconomy `ff_calendar_thisweek.json`** (Forex-Factory-Community) | Wochen-Kalender: title/country/**impact** (High/Med/Low/Holiday)/date(ISO+TZ)/forecast/previous | **NEIN** (key-frei) | ✅ **Erste Wahl.** Rate-Limit 2/5 min → wöchentlich cachen. Genau die High-Impact-Events (FOMC/CPI/NFP). |
| FRED (St. Louis Fed) | Makro-Zeitreihen (CPI, Zinsen, …) — Werte, kein Vorwärts-Kalender | Free-Key | optional, für echte Makro-Werte/Überraschungen |
| Financial Modeling Prep / Finnhub | Economic-Calendar-API | Free-Key (Kalender teils Premium) | Alternative mit Key |
| Trading Economics / AlphaFlash / FXStreet | Profi-Kalender, 400+ Indikatoren, Echtzeit | Bezahlt | Overkill / kostenpflichtig |
| CoinGecko | Markt-Level-Krypto-Daten (Dominanz, Supply, Volumen) | key-frei (Demo) | optional für Säule B (leichtgewichtig) |
| CryptoQuant / Glassnode | tiefe On-Chain-Metriken (NVT, Flows) | Bezahlt | später, falls Säule B vertieft wird |

## 4. Empfohlenes Design (klar bester Weg, key-frei → autonom baubar)
Neue **Querschnitt-Schicht „Fundamental"** parallel zur Regime-Erkennung (`fundamental.py`):
1. **Ingestion:** faireconomy-Wochen-JSON, **gecacht** (≥6 h), defensiv; **Seed-Fallback** = wiederkehrende
   High-Impact-Events (FOMC ~8×/Jahr, CPI/NFP monatlich) → funktioniert auch **offline/ohne Netz**.
2. **Event-Risiko-Modell (vorausschauend):** „Sind wir im Fenster ±N h um ein High-Impact-Event?" →
   `event_risk` ∈ {none, elevated, high} + nächstes Event + Stunden bis dahin.
3. **Makro-Regime (optional):** easing/tightening / risk-on-off als langsamer Tilt.
4. **Master-Integration:** `event_risk` als **defensiver Overlay** (analog `high_vol`) — bei High-Impact-
   Fenster gerichtetes Sleeve dämpfen / stärker auf den stabilen markt-neutralen Sockel lehnen
   (proposal-only, reversibel). Persistenz in neuer Tabelle; `/api/fundamental`-Endpoint; Frontend-Panel.
5. **Tests** (rein, Seed-Daten) + Live-Verifikation.

**Prinzipien bleiben:** proposal-only, 0 Risiko, defensiv (Overlay senkt Risiko, erzeugt kein neues),
key-frei + Seed-Fallback (kein Single-Point-of-Failure), Echtgeld = Mensch (M6).

## Quellen
- [Navixa — Crypto Economic Calendar Guide](https://navixa.io/blog/crypto-economic-calendar-trading-guide)
- [Stocknear — Economic Calendar Trading Plan (CPI/FOMC/Jobs)](https://stocknear.com/learning-center/article/economic-calendar-trading-plan-cpi-fomc-and-jobs-data)
- [Coinbase Institutional — Bitcoin, Liquidity & Macro](https://www.coinbase.com/institutional/research-insights/research/market-intelligence/bitcoin-liquidity-and-macro-crossroads)
- [AInvest — Economic Data & Fed Policy reshaping crypto](https://www.ainvest.com/news/economic-data-fed-policy-signals-reshaping-crypto-market-dynamics-2512/)
- [Dataconomy — On-chain metrics to watch](https://dataconomy.com/2026/03/10/on-chain-metrics-every-crypto-investor-should-actually-be-watching/)
- [CryptoQuant — NVT Ratio guide](https://userguide.cryptoquant.com/cryptoquant-metrics/network/nvt-ratio)
- [Financial Modeling Prep — Economic Calendar API](https://site.financialmodelingprep.com/developer/docs/stable/economics-calendar)
- [Finnhub — Economic Calendar API](https://finnhub.io/docs/api/economic-calendar)
- faireconomy key-freier Feed: `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (Rate-Limit 2/5 min)
