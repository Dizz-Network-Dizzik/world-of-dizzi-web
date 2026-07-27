# Stand, Betrieb & offene Punkte — Dizz Trading

## ✅ Stand (03.07.2026)
- **Flotte:** 50 Bots (alle `dry_run`, Futures) über **12 aktiv geflogene** von **18 lauffähigen
  Strategien**. Markt-neutraler Sockel (CSM/Pairs/StatArb/MM) als Lern-Ebene extra (Paper/Sim).
- **KI-Lern-Ebenen komplett:** Regime-HMM · Meta-Lerner (Stufe 1) · Master-Ensemble (Stufe 2) ·
  Autopilot (6-h-Loop) · Governor · Concentration · Vol-Targeting + Kelly-Sizing (FP-2) · Execution-
  Tracking · Cull · Universe · Fundamental-Overlay.
- **Suite:** 474 grün (`TBT_NO_STARTUP=1`, 50+ Dateien). **Echtgeld:** bewusst blockiert (M6).
- **„Daten-reifen"-Phase:** empirische Teile (Regime-Performance, „bereit 🚀"-Reife, MN-OOS-Re-Test)
  schärfen sich mit mehr Laufzeit; nächste Reife-Schwelle ≥90 Tage.

## 18 lauffähige Strategien (`engine/user_data/strategies/`)
**Futures (long+short):** FuturesMacdRsiScalp · FuturesBreakoutVol (Donchian) · FuturesBbandsBounce ·
SessionOpenBreakout (ORB Asia/London/US) · Supertrend · TtmSqueeze · EmaAdxTrend · UtBotEma ·
AsianRangeScalp · RsiDivergence · GaussianScalp · **MasterMeta** (regime-schaltend, HMM-gekoppelt).
**Spot-Vorlagen (vorhanden, nicht in der Live-Flotte):** TrendFollowEma · MeanReversionRsi ·
MomentumMacd · GridRange · DcaDip · VwapReversion.
Geteilte Helfer in `tbt_common.py` (die 6 neuen + Session-Engines migriert; Alt-Engines behalten
bewusst lokale Helfer). Invariante **„keine Vorlagen-Leichen"** (`docs/RESEARCH_TOOL.md`): jedes
top-bewertete System hat einen echten Ausführungspfad (Freqtrade-Template ODER MN-Paper-Engine).

## ⚠️ Betriebs-Gotchas (unbedingt beachten)
- **`:8137` NIE eigenmächtig neu starten** (Geld-System, gegated: Nutzer-Go + Backup-first + UAC).
- **uvicorn/Tests nur mit den Projekt-venvs** (`.venv` Backend, `engine\.venv` Freqtrade). Basis-Python
  hat kein FastAPI. Tests: `TBT_NO_STARTUP=1` + `PYTHONPATH=…\dizz-network\packages`.
- **`/api/bots/{id}/kill` ist ein SOFT-Schalter** (nur Registry-Status `stopped` + Audit, **kein
  Prozess-Kill**). Zombie heilen = **`/stop`→`/start`** (`/stop` = echter Kill, cmdline-identitätssicher).
- **Sandbox** blockt HTTP-`DELETE`/`/stop` → autorisierte Live-Calls (Bot löschen/Restart) brauchen
  `dangerouslyDisableSandbox`.
- **Backend ohne `--reload`** → `.py`-Änderung erst nach `:8137`-Neustart wirksam; Frontend served-fresh.
- **Frontend isoliert verifizieren** auf Scratch-Port (`preview_snapshot`/`preview_eval`), **NIE** :8137.

## `:8137`-Neustart — korrekte Prozedur (nur gegated)
1. **Backup-first** (`scripts/backup_kern.py` bzw. der Netz-Backup-Task `DizzNetwork-AppBackup`).
2. `py_compile` + **`pytest` grün** (474).
3. Port-Owner ermitteln: `Get-NetTCPConnection -LocalPort 8137 -State Listen` → `OwningProcess`;
   uvicorn killen (`taskkill /F /PID <pid>`), auf Port-frei warten.
4. `scripts/launch.ps1` (startet `DizzTrading-Server.exe` + Auto-Resume der Bots + Monitor).
5. Verifizieren: `/api/summary` → running = 50/50, `/health` ok, Governor/Concentration `severity` ok.

## 📌 Offene Punkte (priorisiert)
1. **Kelly-Sizing (FP-2) aktivieren** (wenn gewünscht): Branch `chat/tb-kelly` mergen → `/api/sizing/config`
   `{bridge_enabled:true}` (erst `proposal` beobachten) → `bridge_mode:"apply"` → am MasterMeta-Bot
   opt_param `use_sizing_bridge:1` + gegateter Neustart. Rollback: Flag zurück/Datei löschen. SPEC:
   `docs/KELLY_SIZING_SPEC.md`.
2. **Daten reifen lassen** → empirisches Regime-/Session-Lernen, „bereit 🚀"-Reife, MN-OOS-Re-Test
   (≥90 T) aktivieren sich selbst.
3. **T5 Politik→Hand ★ GEBAUT 03.07. (FP-T5):** Bridge `suggested_policy.json` + Klemmkette + Hebel
   L1–L3 komplett, alle Defaults inert — **Gate G-T5 OFFEN** (Autonomie-Entscheid liegt bei David,
   `docs/POLICY_HAND_SPEC.md` §8). Scharf wird nichts vor der Antwort.
4. **M6 Echtgeld klein** (`docs/RUNBOOK_ECHTGELD.md`): hochsicheres Gate, Bitget-Subaccounts +
   Trade-Key, gestaffelt 10 %→100 %, Steuer-Export. Bleibt strikt blockiert bis ausdrückliche Freigabe.
5. **M7 Server-Auslagerung** (Deployment-Editionen, docs/56 im Netz).

## Maßgebliche TB-Doku (`programm/docs/`)
`ARCHITECTURE.md` · `BEDIENUNG.md` · `RESEARCH_TOOL.md` · `RUNBOOK_ECHTGELD.md` · `SETUP_USER.md` ·
`KELLY_SIZING_SPEC.md` (FP-2) · `MASTERMETA_TIEFENPRUEFUNG_2026-06-25.md`. **Hinweis:** `docs/START_HERE.md`
+ `docs/HANDOFF.md` sind der **historische 06.06.-Stand** (Prototyp) — dieser Übergabe-Ordner ist der
aktuelle Einstieg. Voller Live-Stand: Gedächtnis-Notiz `trading-bot-eins-stand` (+ `-gotchas`,
`-boerseneroeffnungen`).
