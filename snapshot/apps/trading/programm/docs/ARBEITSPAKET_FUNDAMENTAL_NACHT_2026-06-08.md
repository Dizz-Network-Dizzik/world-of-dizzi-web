# 🌙 Arbeitspaket (autonom, über Nacht) — Fundamental-Schicht + KI-Punkte §6

**Freigaben (Nutzer, 2026-06-08):** key-freie Quellen (faireconomy + Seed-Fallback, CoinGecko); Event-
Verhalten = **defensiv dämpfen**; Umfang = **alle drei Säulen**; **voll autonom + Netz OK** (Calls,
Commits, :8137-Neustarts ohne Rückfrage). Invarianten: **30/30 Bots**, **Tests grün**, proposal-only,
0 Risiko, Echtgeld bleibt M6. Jeder Schritt = eigener Commit; nach Backend-`.py`-Änderung deploy+Neustart.

> **FORTSCHRITT:** TEIL 1 (F1–F8) ✅ + TEIL 2 (A1–A6) ✅ ERLEDIGT (Commits fb0297a…d8e923e,
> live verifiziert, **126 pytest grün, 30/30**). Jetzt TEIL 3 (Dauer-Phase: Monitoring/Recherche/Backlog).

## TEIL 1 — Oberkategorie „fundamental" (neu)
- [ ] **F1 — `fundamental.py` Kern + Kalender-Ingestion.** faireconomy `ff_calendar_thisweek.json`
      (key-frei, gecacht ≥6 h, defensiv) + **Seed-Fallback** wiederkehrender High-Impact-Events
      (FOMC/CPI/NFP, USD). Reine Parsing-/Normalisierungs-Funktionen. Tests.
- [ ] **F2 — Event-Risiko-Modell (vorausschauend).** nächstes High-Impact-Event, Stunden bis dahin,
      `event_risk ∈ {none, elevated, high}` über konfigurierbare Vor-/Nach-Fenster. Rein + getestet.
- [ ] **F3 — Persistenz + Endpoint.** Cache-Tabelle (`macro_events`) via stats; `GET /api/fundamental`
      (live, key-frei, Seed-Fallback). Live-Verifikation.
- [ ] **F4 — Krypto-Fundamentals (CoinGecko, key-frei).** BTC-Dominanz, Total-MarketCap-Trend, BTC-
      Marktdaten → leichtgewichtiges Risk-/Conviction-Proxy. Tests (gemockt).
- [ ] **F5 — Makro-Stance (key-freier Proxy).** kombiniert Event-Druck (kommende High-Impact-Dichte) +
      Krypto-Risk-Proxy (F4) → `risk_on / neutral / risk_off`. Ehrlich dokumentiert (kein echtes Fed-Signal
      ohne Key). Tests.
- [ ] **F6 — Master-Integration (defensiver Overlay).** `event_risk` + Makro-Stance dämpfen das gerichtete
      Sleeve (lehnt stärker auf den markt-neutralen Sockel) — analog `high_vol`, reversibel, tunbar via
      Master-Config (Fenster-Stunden, Dämpfungsfaktor). In Policy + Note. Tests + Live.
- [ ] **F7 — Frontend-Panel „Fundamental".** kommende High-Impact-Events, aktuelles Event-Risiko +
      Countdown, Makro-Stance, On-Chain-Kontext; Overlay-Wirkung im Master sichtbar. Browser-Verifikation.
- [ ] **F8 — Übersichts-Doc aktualisieren** (AI_SYSTEM_UEBERSICHT: neue Schicht „Fundamental" eintragen).

## TEIL 2 — KI-Punkte aus §6 (Nächste Schritte)
- [ ] **A1 — HMM-Parameter tunbar** (`n_states` u.a. via Config) — klein, Vorbereitung für A2.
- [ ] **A2 — Multivariates HMM** (Rendite + Volatilität gemeinsam, diagonale Kovarianz).
- [ ] **A3 — Regime-Übergänge antizipieren** (HMM-Übergangsmatrix → Wahrscheinlichkeit des nächsten
      Regimes → vorausschauender Allokations-Tilt).
- [ ] **A4 — Deflated-Sharpe je #Engines** (strengere OOS-Härtung der Sockel-Gewichtung).
- [ ] **A5 — Stacking / dynamischere Meta-Gewichte** (Aggregation dir↔Sockel verfeinern, z.B. nach
      Fitness-Verlauf/Performance gewichtet).
- [ ] **A6 — MasterMeta-Härtung** (ausführbare Regime-Switching-Engine an das verbesserte HMM-Regime
      koppeln/dokumentieren; soweit ohne schwere Live-Backtests sinnvoll).

## TEIL 3 — Dauer-Phase nach Abschluss (bis der Nutzer sich morgens meldet)
Wenn TEIL 1+2 fertig sind (und Zeit übrig ist), NICHT stoppen, sondern in lockerer Schleife:
- [ ] **Systemkontrolle** regelmäßig: `/api/summary` 30/30, Tests grün, Port-Owner gesund, git clean.
- [ ] **Systembeobachtung**: Master-Fitness-Verlauf, Sockel-Gewichte, aktuelles Regime/Event-Risiko;
      Auffälligkeiten notieren (kein Auto-Apply, proposal-only).
- [ ] **Gezielte Internetrecherchen** zu offenen/neuen Punkten (z.B. Deflated-Sharpe-Formeln, multivariates
      HMM, Stacking-Ensembles, On-Chain-Quellen) — Erkenntnisse sammeln.
- [ ] **Verbesserungs-Backlog pflegen**: gefundene Ideen gebündelt in einem Doc/Memory festhalten
      (für die nächste Session), ohne ungefragt große Umbauten zu starten.
Cadence locker (nicht im Sekundentakt); jede Beobachtung/Recherche kurz protokollieren.

## Reihenfolge-Logik
Fundamental zuerst (Kern-Wunsch, in sich geschlossen, key-frei sofort baubar): F1→F8. Dann die KI-
Verfeinerungen, geclustert: HMM (A1→A2→A3), dann Härtung/Aggregation (A4→A5), zuletzt A6.
Jeder Punkt einzeln verifiziert + committet. Fortschritt wird hier abgehakt.
