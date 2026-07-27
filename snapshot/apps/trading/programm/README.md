# Trading Bot Trial (Projekt BotT)

Skalierbare Desktop-Anwendung zur Verwaltung mehrerer Krypto-Trading-Bots.
**Hybrid-Architektur:** Eine deterministische Engine (Freqtrade) führt die Trades
aus; eine KI-Komponente übernimmt nur periodische Strategie-Recherche und
Performance-Analyse. Der laufende Handel verbraucht dadurch **keine LLM-Token**.

> ⚠️ **Risiko & Recht:** Automatisierter Handel mit echtem Geld ist riskant.
> Siehe [docs/LEGAL.md](docs/LEGAL.md). Erst Paper-Trading (Dry-Run), dann
> Echtgeld mit Mini-Beträgen und harten Limits. Kein Rechts-/Steuerrat.

> 👉 **Neuer Chat / Wiedereinstieg? Starte mit [docs/START_HERE.md](docs/START_HERE.md).**

## Status

**M0 ✅ · M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ · M5 ✅ — KI-Module ergänzt.**
FastAPI-Backend (Port 8137): Bot-Registry, Konto/Risiko/Audit, Backtest,
Statistik-DB (SQLite), Kill-Switch, editierbare Parameter, Live-Dry-Run je Bot
(start/stop/Logs, mehrere parallel), Transfers mit Pflicht-Bestätigung sowie
**KI-Strategie-Katalog (refreshbar/anpinnbar) + Performance-Analyse**; Web-
Dashboard inkl. Kommandozeile. Start per **Desktop-Icon „Trading Bot Trial"**.

**UI v2:** Statistik-Übersicht oben, Detail-Drawer rechts, Strategie-Auswahl
(gruppiert) + Paper-Kapital beim Anlegen, Krypto-Katalog (krypto-spezifisch /
allgemein) mit ausklappbaren Recherche-Quellen, Audit-Log mit dt. Uhrzeit.
**Recherche ist krypto-fokussiert** (nicht-krypto-taugliche Strategien werden
gefiltert).

Bedienung: **[docs/BEDIENUNG.md](docs/BEDIENUNG.md)**.
Nächster Schritt: **M6** (Echtgeld klein + Bitget-Subaccounts + Steuer-Export).

Roadmap siehe Plandatei und [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Die Bau-Chronik — protokollierte Arbeitsstände

Der Bot wurde nicht in einem Rutsch gebaut, sondern in datierten Runden mit
Nachtläufen, Systemchecks und Tiefenprüfungen. Diese Protokolle liegen bei —
sie zeigen, wie das System tatsächlich entstanden ist:

| Strang | Dokumente |
|---|---|
| **Trainingsläufe** | [TRAINING_NACHT_2026-06-13](docs/TRAINING_NACHT_2026-06-13.md) · [TRAINING_NACHT_2026-06-15](docs/TRAINING_NACHT_2026-06-15.md) · [TRAINING_NACHT_MARATHON_2026-06-17](docs/TRAINING_NACHT_MARATHON_2026-06-17.md) |
| **Systemchecks** | [SYSTEMCHECK_2026-06-09](docs/SYSTEMCHECK_2026-06-09.md) · [SYSTEMCHECK_2026-06-10](docs/SYSTEMCHECK_2026-06-10.md) · [SYSTEMCHECK_REVIEW_2026-06-08](docs/SYSTEMCHECK_REVIEW_2026-06-08.md) · [SYSTEMSTAND_SPEICHER_2026-06-09](docs/SYSTEMSTAND_SPEICHER_2026-06-09.md) |
| **Tiefenanalysen** | [TB_TIEFENANALYSE_2026-06-25](docs/TB_TIEFENANALYSE_2026-06-25.md) · [MASTERMETA_TIEFENPRUEFUNG_2026-06-25](docs/MASTERMETA_TIEFENPRUEFUNG_2026-06-25.md) · [AI_SYSTEM_UEBERSICHT_2026-06-08](docs/AI_SYSTEM_UEBERSICHT_2026-06-08.md) |
| **Recherche** | [RESEARCH_FUNDAMENTAL_2026-06-08](docs/RESEARCH_FUNDAMENTAL_2026-06-08.md) · [RECHERCHE_METRIKEN_2026-06-09](docs/RECHERCHE_METRIKEN_2026-06-09.md) · [PROPOSAL_DATENQUELLEN_LERNMECHANIK_2026-06-19](docs/PROPOSAL_DATENQUELLEN_LERNMECHANIK_2026-06-19.md) |
| **Arbeitspakete & Stände** | [ARBEITSPAKET_BACKLOG_BC](docs/ARBEITSPAKET_BACKLOG_BC_2026-06-09.md) · [ARBEITSPAKET_FUNDAMENTAL_NACHT](docs/ARBEITSPAKET_FUNDAMENTAL_NACHT_2026-06-08.md) · [ARBEITSPAKET_RECHERCHETOOL](docs/ARBEITSPAKET_RECHERCHETOOL_2026-06-09.md) · [ARBEITSPAKET_UI_NACHT](docs/ARBEITSPAKET_UI_NACHT_2026-06-10.md) · [PROJEKTSTAND_2026-06-10](docs/PROJEKTSTAND_2026-06-10.md) · [VERBESSERUNGS_BACKLOG](docs/VERBESSERUNGS_BACKLOG_2026-06-09.md) · [MIGRATION_EINORDNER](docs/MIGRATION_EINORDNER_2026-06-09.md) · [UEBERGABE_ADMIN_2026-06-18](docs/UEBERGABE_ADMIN_2026-06-18.md) · [HANDOFF](docs/HANDOFF.md) |
| **Frühe Runden** | [docs/archiv/](docs/archiv/) — die drei Autonom-Arbeitspakete + Nutzer-Backlog vom 08.06. |

*Nicht enthalten: das Echtgeld-Runbook und die Key-Einrichtung — Betriebs-Interna.*

## Struktur

```
trading-bot-trial/
├─ backend/        FastAPI-Orchestrator (Bot-Registry, Risiko, Statistik, KI)
│  └─ app/         config.py · audit.py · main.py
├─ engine/         Freqtrade-Configs & Strategie-Vorlagen (pro Bot)
│  └─ strategies/
├─ app/            Tauri-Desktop-App (UI) — folgt ab M2
├─ docs/           LEGAL.md · ARCHITECTURE.md · DEPLOY.md (M7)
├─ data/           lokale DBs, Logs, Audit-Trail (nicht versioniert)
├─ .env.example    Vorlage für Secrets/Keys
└─ requirements.txt
```

## Schnellstart (Entwicklung, M0/M1)

```powershell
# 1) Python-Umgebung
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) Secrets anlegen
Copy-Item .env.example .env   # danach .env mit echten Werten füllen

# 3) Backend-Healthcheck (sobald M1/M2 läuft)
uvicorn backend.app.main:app --reload
```

## Sicherheits-Grundsätze

- **Paper-First:** Jede Strategie zuerst im Dry-Run, dann Backtest, dann Echtgeld.
- **Harte Limits:** Max Loss je Trade/Tag/gesamt → automatischer Kill-Switch.
- **Bestätigte Transfers:** Ein-/Auszahlungen nie automatisch, immer manuell.
- **Lückenlose Doku:** Jeder relevante Vorgang landet im Audit-Log (DAC8/Steuer).
- **API-Keys minimal:** Zuerst read-only; Withdraw-Rechte niemals an Bots geben.
