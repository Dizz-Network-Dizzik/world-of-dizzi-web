# Arbeitspaket autonom — Block A (Engine-Vorlagen) + B + Schleuder (08.06.2026, Teil C)

Mit ÄUSSERSTER SORGFALT — wir sind in den Kerngrundlagen der KI-/Strategie-Schicht.
Systematisch, effizient, jede Strategie real per Backtest geprüft. Frontend served-fresh;
Backend → trial-Sync + :8137-Neustart + py_compile/pytest(52) grün. 30/30 halten. Nach
logischen Blöcken committen, Browser-Konsole fehlerfrei (Preview live8137). Echtgeld NICHT
anfassen (kommt bewusst erst in M6 mit Backup-Strukturen).

## Phase 1 — Schleuder/Zwille (sofort, self-contained) [index.html initLegendFloat + CSS]
- **Sichtbares Gummiband**: Linie vom Anker (Greifpunkt) zum Element während des Ziehens
  (Neon, dicker/heller mit Spannung), quer über die Seite. Auf Loslassen ausblenden.
- Richtung bleibt: Velocity ENTGEGEN der Zugrichtung (von links ziehen → nach links raus).
- **2–3× krasser**: MAXV 46→~100, speed = 8 + charge*110; --charge-Glow ~verdoppelt, scale↑.
- Spannung übers ganze Dokument: REF ≈ 0.8·Bildschirmbreite (Zug Rand-zu-Rand = max).
- Momentum hauptsächlich seitlich ABER Zug-Winkel behalten: vy*0.55 (nicht 0.4, nicht waagerecht).
- Kurzer Launch-Flash/Trail in Schussrichtung (Flow-Effekt sichtbar).

## Phase 2 — Validierungs-Backtest / Lern-Loop (Punkt E) [meta/engine, Hintergrund]
- Für die 5 neuen Eröffnungs-Bots (SessionOpenBreakout) Walk-Forward-Validierung +
  Optimierungs-Loop anstoßen (run_walkforward / run_optimization) → echtgeldreif-Gate +
  gelernte Gewinner. Im Hintergrund (Backtests langsam), danach Ergebnis prüfen.

## Phase 3 — BLOCK A: „Vorlage folgt"-Systeme lauffähig machen (GRÖSSTER BLOCK, größte Sorgfalt)
Inventar der 19 Recherche-Systeme. Zwei Wege je System:
- **3a Aktivieren auf bestehender Engine** (KEIN neuer Code), NUR bei echtem Logik-Match:
  - ORB / Overnight-Range / EU-US-Overlap / ICT-Session → `SessionOpenBreakout`
  - EMA+MACD+RSI / RSI+Stoch+EMA / VWAP+MACD Scalp → `FuturesMacdRsiScalp`
  - Bollinger+RSI Mean-Rev → `FuturesBbandsBounce`
  - Dual-EMA / ADX-Trend → `TrendFollowEma`
  - Keltner+RSI Breakout → `FuturesBreakoutVol`
  (Empfohlene Recherche-Params bleiben Anzeige; Engine fährt eigene Logik — ehrlich kennzeichnen.)
- **3b Neue Engine-Vorlagen** (echter Code + Backtest) für Archetypen ohne Match — je EINZELN,
  sorgfältig, verifiziert: **Grid**, **DCA**, **Funding-Rate-Arb**, **CME-Gap-Fill**, dann
  Markt-neutral **Pairs-Spread-Reversion**, später **Market-Making** (komplex, ggf. später).
- **Grundlegende Nachjustierung/Ergänzung** der Seed-Systeme dabei (Params/Regeln schärfen).

## Phase 4 — BLOCK B (ohne Echtgeld): Lern-Bot 3. Ebene + CSM-Loop
- **CSM geschlossener Lern-Loop**: Parameter-Mutation → Walk-Forward → Gewinner behalten
  (mutate_params/_opt_score-Muster auf CSM). Markt-neutral, kleiner Suchraum → effizient.
- **Lern-Bot 3. Ebene**: Master-Synthese → echter (proposal-only) Selbst-Verfeinerungs-Schritt.
- **NICHT**: Master-als-Echtgeld-Bot (M6, bewusst später mit Backup-Struktur).

## Phase 5 — Sonder-Systeme außerhalb des Rasters deklarieren
- Wenn ein neues System spezielle Validierungs-/Trade-Eröffnungsparameter hat (außerhalb des
  Standard-Param-Rasters), eigenes Feld/Marke + eigene Validierungs-Sicht deklarieren (analog
  trigger_type/market_neutral). Pro Fall kurz durchdenken, nicht ins Standard-Raster pressen.

## Phase 6 — Abschluss
- pytest(52+) grün, trial-Sync, :8137-Neustart, 30/30, Browser-Konsole frei, committen,
  Memory aktualisieren.
