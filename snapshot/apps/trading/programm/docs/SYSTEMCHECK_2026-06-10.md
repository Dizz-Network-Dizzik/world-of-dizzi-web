# 🩺 Systemcheck & Portfolio-Ebene (2026-06-10, HEAD `2638ced`)

> **⏩ NACHTRAG (später am 10.06.):** Nach dieser Portfolio-Ebene folgte ein **Horizont-/UI-Umbau** (HEAD `2638ced`,
> 234 pytest): Gruppierung systemweit auf **Scalping/Intraday/Swing** (statt Spot/Futures; alle 6 Spot-Bots →
> Futures migriert, `trading_mode` nur noch technisch), **Auto-Upgrade pro Bot** (nach 1× manuell), Statistik-
> Übersicht mit klickbaren Magenta-Filter-Kacheln, aufgeräumtes KI-Tool (MasterMeta-König + verschachtelte
> Container), Katalog-Filterleiste, reparierte Icon-Legende. Gesamtüberblick: `PROJEKTSTAND_2026-06-10.md`.


Bestandsaufnahme nach Umsetzung der **Portfolio-Ebene P1–P5** (Schicht ÜBER den 51 Bots) +
zweier Code-Review-Runden. Ergänzt `SYSTEMCHECK_2026-06-09.md` (AI-Schichten/Connections, weiterhin gültig).
0 Echtgeld (Demo/Paper).

## 1. Live-Status
| Check | Wert |
|---|---|
| Bots | **51/51 running** (45 Futures inkl. 16 Eröffnung · 6 Spot · + MasterMeta) |
| Tests | **222 pytest grün** · 36 Backend-Module · 101 REST-Routen · 30 Test-Dateien |
| Engine | verfügbar (freqtrade dry-run, futures `defaultType: swap`) |
| Git | clean (Backup-Repo synchron) |

## 2. Portfolio-Ebene — die neue Schicht ÜBER den Bots

```
        ┌──────────────────────────────────────────────────────────────┐
        │  P5 Monitoring/Alerting (alerts.py)  → Alert-Leiste + Panel    │  read-only Aggregator
        ├──────────────────────────────────────────────────────────────┤
        │  P1 Portfolio-Risk-Governor (governor.py)                      │  greift ein (alert/derisk/pause)
        │   ├─ aggregierter Portfolio-Drawdown (Snapshots, forward-fill) │
        │   ├─ aggregierter Tagesverlust (bot_pnl since_days=1)          │
        │   ├─ Anomalie-Erkennung (robuster Z-Score / MAD)              │
        │   └─ zieht P2 als Frühwarnung ein ─────────────┐              │
        ├────────────────────────────────────────────────┼─────────────┤
        │  P2 Konzentration (concentration.py)  ◀─────────┘             │  Exposure/HHI/Cluster
        │  P3 Vola-Sizing (sizing.py)           Vorschlag + Apply        │  Stake invers zur Vola
        │  P4 Execution/Slippage (execution.py + stats.execution_costs)  │  Ist-vs-Erwartungspreis + Gebühren
        └──────────────────────────────────────────────────────────────┘
                                   ▲ liest  │ greift ein (runner.stop)
        ┌──────────────────────────┴────────▼──────────────────────────┐
        │   51 Demo-Bots  +  MasterMeta  (registry / runner / stats)     │
        └──────────────────────────────────────────────────────────────┘
```

- **P1 Governor** läuft als **erster** Teil im Autopilot-Tick (`_autopilot_step`), vor MasterMeta-Improve und
  Cull. Bei `breach` (DD ≥ `max_drawdown_pct` oder Tagesverlust ≥ `max_daily_loss_pct`) greift `action`:
  `alert` (nur melden) / `derisk` (schlechteste N Demo-Bots via `runner.stop`) / `pause` (alle Demo). Default
  **derisk**, `derisk_count=3`, debounced (`min_interval_h=1`). MasterMeta + Echtgeld geschützt; **nie löschen**.
- **P2** liefert Exposure je Basis-Asset + HHI + Korrelations-Cluster (Krypto-Majors BTC/ETH/SOL). Über dem
  Deckel → Frühwarnung im Governor (kein Auto-Pause; Konzentration ist strukturell).
- **P3** empfiehlt Stake = `clip(ref × ziel_vol / real_vol, min, max)` (driftfrei, absolut). Anwenden setzt
  Stake + startet den Bot neu. Greift erst ab ≥3 Tagen Vola-Historie.
- **P4** misst je geschlossenem Trade `open_rate` vs `open_rate_requested` (richtungsbewusste Slippage-bps) +
  reale Gebühren-bps. Dry-Run-Slippage ≈ 0 (Fill == angefordert) → **M6-Vorbereitung**.
- **P5** verdichtet Governor/Slippage/Datenfeed-Frische/gestoppte Bots zu priorisierten Alerts.

## 3. Connections (neue Endpoints)
`/api/governor` · `/api/governor/run` · `/api/governor/config` · `/api/concentration[/config]` ·
`/api/sizing[/config|/apply_all]` · `/api/bots/{id}/sizing/apply` · `/api/execution[/config]` ·
`/api/bots/{id}/execution` · `/api/alerts[/config]` · `/api/risk` (jetzt echte Portfolio-Werte).
Frontend: Monitoring/Governor/Konzentration ganz oben im KI-Tool, Sizing/Execution im Management-Bereich,
globale **Alert-Leiste** unter dem Header.

## 4. Effizienz (`cache.py`)
Ein UI-Refresh stieß `governor.evaluate` (~700 ms: 51-Bot-PnL + Snapshots) 3–4× redundant an (Governor-/
Monitoring-Panel + Alert-Leiste + `/api/risk`). **Fix:** thread-sicherer TTL-Memo (3 s) für die read-Pfade von
`governor.evaluate` / `execution.analyze`; der **eingreifende `run_once` bleibt frisch** und invalidiert nach
einem Eingriff. `alerts.operational_health` nutzt die schon berechneten Governor-Bot-Zeilen statt eines zweiten
`runner.status`-Laufs. Messung: governor warm 700→2 ms, alerts warm 244→29 ms.

## 5. Verifikation (zwei Review-Runden)
- Funktional: alles kompiliert, 222 Tests grün, keine ungenutzten Importe (AST), 101 Routen.
- Korrektheit: Forward-Fill im Drawdown, Anomalie-Floor gegen Rausch-Fehlalarme, richtungsbewusste Slippage
  (Long/Short, gegen echtes SQLite getestet). **Bugfix:** Hebel-Schätzung `SessionOpenBreakout`=2 (nicht 3).
- Interaktion: live `governor.sev == risk.sev == alerts.status` konsistent; Konzentrationswarnung fließt durch.
- **De-Risk-Pfad reversibel live getestet:** breach erzwungen → genau der schlechteste Bot pausiert → neu
  gestartet → Config zurückgesetzt → 51/51 wiederhergestellt; Audit-Kette vollständig.
- Persistenz: alle State-Dateien (`data/*.json`, gitignored) valide; Frontend-JS-Delimiter balanciert.

## 6. Offen / optional
- Governor-`action` in der Datensammelphase ggf. auf `alert` stellen, falls Auto-De-Risk zu scharf.
- Bulk-Snapshot-Query als tiefere Optimierung der ~700-ms-Kaltberechnung (read-Pfad ist gecached).
- `governor.json` u. a.: read-modify-write ohne Lock (= bestehendes `cull.py`-Muster, harmlos).
- M6 Echtgeld-Pfad · trial endgültig löschen · F Design-Abschluss.
