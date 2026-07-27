# Engine (Freqtrade) — Bedienung

Eigene venv unter `engine/.venv`. Freqtrade 2026.5.1, exchange = Bitget.
Alle Befehle aus dem Ordner `engine/` ausführen.

## Setup (einmalig)

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install freqtrade
freqtrade create-userdir --userdir user_data
```

## Daten laden

```powershell
.\.venv\Scripts\freqtrade.exe download-data --userdir user_data `
  --config user_data/config_bot1_dryrun.json --timeframe 1h --days 180
```

## Backtest (Pflicht vor jedem Echtgeld-Einsatz)

```powershell
.\.venv\Scripts\freqtrade.exe backtesting --userdir user_data `
  --config user_data/config_bot1_dryrun.json --strategy TrendFollowEma
```

## Paper-Trading (Dry-Run, Live-Daten, KEIN echtes Geld)

```powershell
.\.venv\Scripts\freqtrade.exe trade --userdir user_data `
  --config user_data/config_bot1_dryrun.json --strategy TrendFollowEma
```

## Dateien

- `user_data/config_bot1_dryrun.json` — Config Bot 1 (Bitget Spot, dry_run=true).
- `user_data/strategies/trend_follow_ema.py` — Katalog-System „Trendfolge".
- `user_data/backtest_results/` — Backtest-Reports (nicht versioniert).

## Erster Backtest-Befund (Referenz, 10.12.2025–04.06.2026, 1h)

Pipeline verifiziert. Die Beispielstrategie war im Bärenmarkt unprofitabel
(**−11,73 %**), schlug aber den Markt deutlich (Market change **−42,78 %**).
Schwachpunkt: das `exit_signal` (EMA-Kreuz abwärts) verkauft zu spät
(−21,9 % Summe). **Das ist Tuning-Material für M5 (KI-Optimierung)** — für M1
zählt nur, dass Datendownload, Strategie, Backtest und Reports funktionieren.

> ⚠️ Vergangene Backtests sind keine Garantie für zukünftige Ergebnisse.
> Erst Paper-Run, dann Echtgeld mit Mini-Beträgen und harten Limits.
