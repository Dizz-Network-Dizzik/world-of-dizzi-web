# Architektur — Dizz Trading

> **Stand 03.07.2026.** Einstieg für neue Chats = `programm/Übergabe/` (4 Dateien). Dieses Dokument
> ist die technische Architektur-Referenz. (Frühere Fassung beschrieb den 5-Bot-Prototyp vor der
> Monorepo-Migration.)

## Grundprinzip: Hybrid
Eine **deterministische Engine** handelt; die **KI** denkt nur periodisch nach.
- **Engine (Freqtrade):** führt Trades regelbasiert aus — schnell, auditierbar, **0 LLM-Token** im
  Dauerbetrieb.
- **KI-/Meta-Schicht (Python):** läuft auf Anstoß bzw. im Autopilot-Loop — Recherche, Regime-Erkennung,
  Performance-Analyse, Ensemble-Politik. Erzeugt **Konfiguration/Empfehlungen**, keinen ungeprüften
  Live-Handelscode.

## Komponenten
```
┌────────────────────────────────────────────────────────────┐
│  Dashboard  backend/app/static/index.html (Single-File)     │
└───────────────┬────────────────────────────────────────────┘
                │ lokale REST-API (~110 Endpunkte)
┌───────────────▼────────────────────────────────────────────┐
│  Orchestrator-Backend (FastAPI, programm/.venv)             │
│  • Registry/Runner (Bot-CRUD, Prozesse)                     │
│  • Lern-Ebenen: hmm · meta · master · autopilot             │
│  • Markt-neutraler Sockel: csm · pairs · marketmaking (Sim) │
│  • Risiko/Allokation: governor · concentration · sizing     │
│  • execution · universe · fundamental · cull · risk         │
│  • ai (Katalog/Recherche) · exchange · transfer · audit     │
└───────┬───────────────────────────────┬────────────────────┘
        │ je Bot 1 Prozess              │ Bridge-Dateien (venv-übergreifend)
┌───────▼─────────┐  ┌──────────────┐   │ hmm_regime.json · suggested_sizing.json · suggested_policy.json
│ Freqtrade-Bot 1 │ …│ Freqtrade-N  │ ──┴─► Bitget (dry_run; read-only Keys)
└─────────────────┘  └──────────────┘   engine/.venv, je Bot eigene Config + Trade-DB
```

## Stack
| Schicht | Technologie |
|---|---|
| Dashboard | Single-File HTML/CSS/JS (`backend/app/static/index.html`) |
| Backend | Python 3.12, FastAPI (`programm/.venv`) |
| Engine | Freqtrade (`programm/engine/.venv`, eigener Interpreter) |
| Börse | ccxt → Bitget (aktuell `dry_run`, read-only) |
| Datenhaltung | SQLite (`data/stats.sqlite` + Trade-DBs je Bot) |
| KI | Claude API (`anthropic`) — nur für Recherche/Analyse, proposal-only |

## Datenfluss Gehirn → Hand (venv-übergreifend)
Backend und Freqtrade laufen in getrennten venvs → Kopplung über **atomare Bridge-Dateien**:
- **`hmm_regime.json`** — Live-Regime + HMM-Konfidenz + Event-`lev_scale` + Vol-Targeting-`exposure_scale`
  → `master_meta.py` schaltet Sub-Logik + Hebel.
- **`suggested_sizing.json`** (FP-2) — geklemmter Stake-Plan (K4–K6) → `master_meta.custom_stake_amount`,
  opt-in / proposal-Default / nur `dry_run`. Ohne Opt-in byte-identisch. SPEC: `KELLY_SIZING_SPEC.md`.
- **`suggested_policy.json`** (FP-T5, Gate G-T5 offen) — Regime-Bestauswahl der Master-Politik →
  Sub-Logik-Wahl (L1) / Stake-Dämpfung ≤1 (L2) / Edge-Gating (L3) der MasterMeta-Engine; Klemmkette
  Politik→Governor→Konzentration→Sizing, opt-in / proposal-Default / nur `dry_run`. Ohne Opt-in
  byte-identisch. SPEC: `POLICY_HAND_SPEC.md`.

## Autopilot-Reihenfolge (`autopilot.py`, Default 6 h)
`governor` → `sizing`-Bridge → `policy`-Bridge → `mastermeta_improve` → `auto_upgrade` → `cull` → `auto_validate`
(exception-fest getrennt; Governor zuerst, damit ein breach-Portfolio erst de-riskt wird).

## Roadmap (Meilensteine)
| M | Inhalt | Status |
|---|---|---|
| M0–M5 | Fundament · Engine · Orchestrator · Multi-Bot-Dry-Run · KI-Module | ✅ |
| — | Skalierung: 50-Bot-Flotte, 18 Strategien, Lern-Ebenen, Governor, Kelly-Sizing | ✅ (03.07.) |
| M6 | Echtgeld klein (Subaccounts, gestaffelt, Steuer-Export) | ⏳ gegated (`RUNBOOK_ECHTGELD.md`) |
| M7 | Server-Auslagerung / Deployment-Editionen | ⏳ Planung (Netz docs/56) |

## Roadmap-Details siehe
`Übergabe/03_STAND_UND_BETRIEB.md` (offene Punkte) · `RUNBOOK_ECHTGELD.md` (M6-Gate) ·
`KELLY_SIZING_SPEC.md` (FP-2) · `RESEARCH_TOOL.md` (Katalog).
