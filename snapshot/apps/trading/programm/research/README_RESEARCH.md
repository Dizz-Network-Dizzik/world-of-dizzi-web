# Signal-Research (Option 3: fundamental andere Signale)

Ehrliche, datengetriebene Vorab-Studien, **bevor** Infrastruktur gebaut wird ("prove the ceiling before
building"). Alle Daten read-only über ccxt/Bitget (0 echtes Risiko, 0 LLM-Token). Reproduzierbar.

**Ausführung:** Daten-/Funding-Skripte mit der Backend-venv (hat `ccxt`); der CSM-Backtest mit der
Engine-venv (hat `numpy`). Caches (`_*.json`) werden im Arbeitsverzeichnis erzeugt und sind wegwerfbar.

---

## E1 — Funding-Carry / Basis (markt-neutral) → VERWORFEN (Decke praktisch zu dünn)
`funding_scan.py` (Universums-Scan annualisierter Netto-Carry) + `funding_hedgeable.py` (Schnitt mit
Spot-Hedgebarkeit). Befund (90T, Top-50 Bitget-Perps nach Volumen):
- **Majors (BTC/ETH/…): Netto-Carry ≈ 0–1 %/Jahr** — Funding deckt nur die Gebühren.
- **Fette Carry-Raten (10–18 %) sitzen ausschließlich in Perp-only-Coins ohne Spot-Market → NICHT hedgebar.**
- Hedgebar (Spot da & >1 Mio $/24h) UND stabil (≥80 % positiv & >5 % netto): praktisch **1 Pair** (SKYAI).
- **Verdikt:** Theoretisch hohe, praktisch niedrige Decke auf Bitget (~2–3 %/Jahr für einen diversifizierten,
  hedgebaren, markt-neutralen Book). Kein Home-Run → verworfen.

## E2 — Cross-Sectional Momentum (markt-neutral) → TRAGFÄHIGER EDGE
`csm_fetch.py` (Daily-Closes paginiert) + `csm_backtest.py` (vektorisierter L/S-Backtest, Lookahead-frei,
Gebühren auf Turnover, 4-Fenster-Walk-Forward + Fee-Sensitivität).
- **Signal:** ranke das Perp-Universum täglich nach Lookback-Return; **long Top-30 % / short Bottom-30 %**,
  gleichgewichtet, dollar-neutral. **Tägliches Rebalancing (H=1)** ist der Schlüssel (kurzfristiges Momentum zerfällt schnell).
- **Wichtig (Methodik):** Ein anfänglicher Lookahead-Bug (Signal aus `close[t]` UND Tagesrendite in `close[t]`)
  blähte Sharpe auf ~2,7. **Nach Korrektur** (neue Gewichte gelten ab t+1) ist das ehrliche Bild:
- **31-Pair-Universum (2 J), L=14, H=1, Q=0,30:** Netto-Sharpe **1,30 @0,06 %/Seite**, **1,04 @0,10 %**,
  +22–28 %/Jahr, max DD ~11–13 %; gebühren-tolerant bis ~0,15 %/Seite. 3 von 4 WF-Fenstern positiv.
  (Engeres 21-Survivor-Universum gab Sharpe ~1,8 — teils survivorship-getrieben → die breitere Zahl ist ehrlicher.)
- **Verdikt:** Realer, verteidigbarer, markt-neutraler Edge (Sharpe ~1,0–1,3 netto) — das mit Abstand stärkste
  Ergebnis. Rechtfertigt eine Implementierung.

### E3 — Härtung (durchgeführt) → Edge hält stand
`e3_fetch.py` (Closes + Funding) + `e3_backtest.py` (funding-bewusst + Robustheit). 31-Pair-Universum, 728T,
Setup L=14/H=1/Q=0,30, fee 0,06 %/Seite:
- **Funding-P&L: Drag nur ~0,6 %/Jahr** (Sharpe 1,30 → 1,27). **GOTCHA:** Bitget `fetch_funding_rate_history`
  liefert nur ~30T → volle Historie nicht abrufbar; daher per-Pair-Mittel als **Konstant-Proxy** über den Zeitraum.
- **Survivorship-Robustheit: stark** — 60 zufällige 18-von-31-Subsets: **100 % positiv**, Median-Sharpe 1,21,
  25 %=1,00, min 0,62. Leave-one-out 0,99–1,41 → **kein Einzel-Pair trägt den Edge** (breit getragen).
- **Zeitliche Front-Lastigkeit (Haupt-Caveat):** WF-Fenster 0,24 / 0,07 / 2,12 / 3,04 — älteres Jahr nur schwach
  positiv, jüngstes Jahr stark. Edge überall ≥0, aber Stärke zeitvariabel.
- **Verdikt E3:** Netto-Sharpe ~1,2–1,3 (full period) übersteht Gebühren, Funding und Universums-Subsampling.
  Robust + breit getragen → **rechtfertigt Implementierung**. Rest-Caveats: keine echt-delisteten Coins
  (Bitget-Datengrenze), nur 2 J Historie, konservativ sizen + monitoren.

### Implementierungs-Skizze (nach Härtung)
Cross-Sectional passt **nicht** in Freqtrades Per-Pair-Modell → neue Orchestrator-Komponente im Backend
(`csm_engine`): rankt täglich, berechnet Ziel-L/S-Gewichte, führt im Demo einen simulierten Book (0 Risiko);
Live (M6) später über gehebelte Perp-Orders. Reiht sich neben master/introspect/integration ein.

---

# Bau-KI-Trainings-Runden (18.06.2026) — Signal-Vertiefung + 2.-MN-Engine-Suche
Fortsetzung der Landkarte. Methodik verschärft: anchored Walk-Forward, kosten-/funding-inklusiv,
Korrelations-Check zu CSM (Diversifikations-Wert), Sub-Universum (Survivorship), **PBO/CSCV** (Overfitting).
Volle Details: `docs/TRAINING_NACHT_MARATHON_2026-06-17.md` (Bau-KI-Runden 7–8).

## E4 — CSM Vol-Skalierung (Verbesserung von E2/E3) → STARKER, ROBUSTER LIFT ✅
`csm_signal_research.py` + `csm_vol_robustness.py` + `csm_pbo.py`. Risk-adjusted Momentum: `mom /= Tagesvola(L)`.
- **OOS-Sharpe 0.86 → 1.88** (anchored WF; offizieller Optimizer bestätigt: oos_validated, optimal L14/**H2**/Q0.3).
- **14/14 Robustheits-Stresses** (Survivorship: liquide Majors SOGAR stärker ~3.0; kosten-robust bis 20bps; alle Q/H).
- **PBO = 0.023 (wasserdicht)**, IS-beste in 100 % der Splits eine vol-Variante. **Dreifach validiert.**
- inverse-vol Positions-Gewichtung (`csm_posweight_research.py`): bringt nichts, **equal-weight reicht**.
- **Implementiert als opt-in** `csm.DEFAULTS["vol_scaled"]` (default OFF). **Offenes Proposal: aktivieren** (`vol_scaled=true,hold=2`) ⇒ CSM qualifiziert als 2. MN-Engine. Rest-Caveat: absolute Edge zeitvariabel (Live-Forward-Track nötig).

## E5 — Short-Term Reversal (Return-Achse) → TOT ⛔
`reversal_research.py`. Long jüngste Verlierer / short Gewinner. In/OOS durchweg negativ (Krypto trendet,
revertiert nicht auf Tagesbasis). Korr zu CSM −0.33 (dieselbe Return-Achse). Kein Diversifizierer.

## E6 — Low-Vol-Anomalie (Vola-Achse) → SCHWACH, unkorreliert 🟡
`lowvol_research.py`. Long low-vol / short high-vol. OOS-Sharpe 0.24–0.49 (**< Schwelle 0.86**), PSR ~0.7.
**Korr zu CSM +0.07 (echt unkorreliert)** — als ~15–20 %-Beimischung hebt komb. Sharpe nur 1.50→1.54 (marginal).
Qualifiziert NICHT als Einzel-Engine; schwacher Kombinations-Kandidat (Plan B).

## E7 — Amihud-Illiquidität (Volumen-Achse, neue Datendimension) → PBO-FRAGIL 🟡
`volume_research.py` + `volume_pbo.py` (Dollar-Vol = close×volume). Long high-illiq / short low-illiq.
Volles Universum schwach (0.31–0.42); **liquide Majors OOS ~0.95 (> Schwelle), unkorreliert (+0.06), kosten-robust** —
ABER **PBO = 0.409 (fragwürdig)**: V/H-Selektion overfitting-anfällig, period-fragil (2/6 Fenster negativ).
Bester der 3 Hypothesen, aber **kein sauberer Edge**. §0: zu-gut-Zahl (0.95) durch PBO-Falsifikation relativiert.

## Fazit der 2.-Engine-Suche (3 Achsen erschöpft)
Return (CSM ✓ / Reversal ✗) · Vola (Low-Vol 🟡) · Volumen (Amihud 🟡). **Keine qualifizierende 2. Engine** —
der einzige robuste real-data-Edge bleibt **CSM-vol** (E4). Weitere Edges bräuchten **Orderbuch-/Tick-Daten**
(aus Tages-`close`+`volume` nicht erschließbar). ⇒ Weg zu „Master schlägt 1/N nicht-trivial" = CSM-vol aktivieren.

---

# Datenquellen-Erkundung (19.06.2026, Bau-KI R10–11) — Fundamental/Sentiment/Derivate
Auftrag: neue Datenquellen für echten Edge. Befund-Übersicht (Details: `docs/TRAINING_NACHT_MARATHON_2026-06-17.md` R10–11 + `docs/PROPOSAL_DATENQUELLEN_LERNMECHANIK_2026-06-19.md`).

## E8 — Fear&Greed-Sentiment (8 J, key-frei) → Momentum-Proxy, kein eigener Edge 🟡
`sentiment_research.py`. F&G ist prädiktiv als **MOMENTUM** (corr fwd-return +0.04…+0.13), NICHT Mean-Reversion
(naive „Fear→kaufen" in Krypto **falsch**). Greed-Timing OOS 1.19 > B&H 0.78, aber nur **+0.18 über simples
Preis-Trend** und **period-fragil**. Direktional (BTC-Beta), kein MN-Edge. Bestenfalls Risk-Overlay-Feature.

## E9 — Fundamental-Signale prädiktiv (DVOL + Kombi) → KEIN robuster Mehrwert ⛔
`fundamental_signals_research.py`. DVOL direktional prädiktiv (+0.26 h30d) ABER 0.74 korreliert mit realisierter
Vola (redundant). Kombi F&G+DVOL+Preis-Trend: **−0.02 über Gratis-Preis-Trend**. ⇒ markt-weite Fundamental-/
Sentiment-/Vola-Signale sind **Preis-Proxies**; „mehr Daten = besser" hält OOS-Mehrwert-Prüfung nicht stand.

## E10 — Derivate-Forward-Track (OI/Funding) → gestartet, braucht Wochen ⏳
`derivatives_collector.py`. OI/Liquidations/Funding-Langhistorie bei Bitget NICHT historisch (ccxt geprüft) ⇒
der dokumentierte Derivate-Edge (Funding/OI-Extreme = Mean-Reversion) ist nur **forward sammelbar** (→ `data/
derivatives_track.jsonl`, täglich laufen, ~60–90 T bis backtestbar) ODER bezahlt (Coinglass/Laevitas).

## Fazit Datenquellen
Der robuste Edge bleibt **CSM-vol** (E4). „Einfache" Daten (Sentiment/Vola/Makro) = ausgepreiste Preis-Proxies;
„wertvolle" Daten (Derivate-Historie, Orderbuch/Tick) = nicht-verfügbar/bezahlt. Strategischer Vorteil dieses
Systems ist NICHT Datenmenge, sondern die **Ehrlichkeits-Disziplin** (anchored WF/PBO), die echte von
Schein-Edges trennt. Nächster potenziell-neuer Edge: Derivate via Forward-Track (E10) in 2–3 Monaten.

---

# Bau-KI-Runden 12–13 (20.06.2026) — Hebel-B-Reparatur + 4. Return-Achsen-Probe

## E10-Update (R12) — Derivate-Forward-Track repariert + Daily-Task LIVE ✅
`derivatives_collector.py` hatte zwei stille Defekte: (1) lief nur 1× (kein Daily-Task), (2) **`price` für ALLE
Symbole `null`** (bitget `fetch_funding_rate` liefert keinen markPrice — verifiziert) ⇒ Track wäre nicht gegen
Forward-Returns backtestbar. **Fix** (Research-Skript, kein Backend): Preis via `fetch_tickers`-Batch (50/50 mit
Preis), +`oi_value`/`oi_amount`, idempotent je Tag, no-console-robust (Tee in `derivatives_track.log`, exit 0).
**Daily-Task `DizzTB-DerivTrack`** via `Register-ScheduledTask` (täglich 23:30, StartWhenAvailable) — live-verifiziert.
⇒ Track reift ab jetzt täglich self-contained; ab ~60–90 T backtestbar.

## E11 — Time-Series-Momentum (Return-Achse, 4. Probe) → TOT/REDUNDANT ⛔
`tsmom_research.py`. Per-Asset-Trend (long wenn eigene Trailing-Rendite über L>0), kosten-/funding-inkl., anchored
WF (16 Kandidaten, Schwelle ~0.97), corr-Check zu CSM-vol + Markt, Netto-Exposure gemessen.
- **raw** (Netto-Exposure erlaubt): OOS **0.94 < 0.97**, kosten-fragil (0.43 @20bps); avgNet −0.25, corr(Markt) −0.34
  ⇒ **trägt Markt-Beta, NICHT markt-neutral**. corr(CSM) +0.05 — aber die „Orthogonalität" stammt genau aus dem
  Beta, das CSM fehlt (kein Gratis-Diversifizierer, sondern unerwünschtes Risiko).
- **neutral** (demeaned → dollar-neutral): OOS **1.05 NUR @6bps**, bricht auf **0.68/0.44 @10/20bps** + period-fragil
  (Fenster-OOS 1.02/0.88/−0.71/**+3.09** = ein Glücks-Fenster trägt). corr(CSM-vol) **+0.29** (schwach korreliert,
  nicht sauber orthogonal). Strukturell IST demeaned-TSMOM = cross-sectionales Momentum = CSM-Cousin.
- **Verdikt:** Kein viabler 2.-Engine-Kandidat (a-priori bestätigt). Damit ist die **Return-Achse über 3 Proben
  erschöpft: CSM ✓ / Reversal ✗ / TSMOM ✗.** Orthogonaler Edge braucht eine NICHT-Return-Achse mit neuen Daten
  (Derivate via E10-Forward-Track / Orderbuch-Tick) — kein close-Daten-Hebel mehr in Reichweite.
