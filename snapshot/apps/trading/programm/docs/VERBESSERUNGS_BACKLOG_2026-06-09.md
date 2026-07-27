# 🔭 Verbesserungs-Backlog & Beobachtungs-Log (Dauer-Phase ab 2026-06-09)

Lebendes Dokument der autonomen Dauer-Phase nach Abschluss des Fundamental-/KI-Arbeitspakets
(HEAD `9b78a21`, 126 pytest, 30/30). Sammelt **Systembeobachtungen** + **recherchegestützte
Verbesserungsideen** für die nächste Session. Nichts hiervon wird ungefragt groß umgebaut.

---

## A. Systembeobachtungen (Monitoring)
| Zeit (UTC) | Beobachtung |
|---|---|
| ~Zyklus 1 | 30/30 Bots laufen, trades_closed ~435, Demo-PnL ~−96 € (Paper, erwartbar rot). Git clean, 126 Tests. |
| ~Zyklus 1 | **Regime über Nacht `range` → `trend_down`** (multivariates HMM, Konfidenz 1.0, stay 0.95). Erkennung adaptiert sauber. |
| ~Zyklus 1 | Master `train_step` → v6 (rebaselined: v5 hatte die neuen Config-Keys A4/A5 noch nicht → einmalige Resync, jetzt trend_down-konditioniert). |
| ~Zyklus 1 | Sockel csm 0.40 / mm 0.60; Event-Risiko `none` (nächstes High-Impact CPI in <40 h → wird bald `elevated`/`high`). |

| ~Zyklus 5 | **Fundamental-Overlay LIVE aktiviert**: Event-Risiko `none`→`elevated` (CPI in ~36 h) → total_scale 0.75 dämpft gerichtet, effektiver Sockel 0.901→0.924. F6 wirkt end-to-end in Produktion. ✓ |

| ~Tag-Zyklus | **:8137-API war kurz down** (HTTP 000 ~1 Zyklus) + einmaliger PowerShell-Fehler 0x800705af (Commit-/Pagefile-Limit, trotz 49 GB freiem RAM). Per Standard-Prozedur neu gestartet → wieder 30/30, git clean. Beobachten: ggf. Pagefile/Commit-Limit erhöhen, falls wiederkehrend (62 python-Prozesse). |
> **STATUS 2026-06-09 (Nacht 3):** B1 (PSR `W1`), B2 (Event-Daempfung `W2`), B3 (Vol-Targeting `W5`),
> B5/C MasterMeta<->HMM-Bridge (`W6`), C echte Makro-Surprise (`W3`) + echte On-Chain-Tiefe (`W4`) **UMGESETZT**
> (Commits 728b5aa…). **B4 (Forward-Vola-Term-Struktur) DEFERRED** — braucht bezahlte Optionsdaten (ehrlich).

> **STATUS 2026-06-09 (Tag):** **B4 (DVOL-Forward-Vola, key-frei via Deribit) UMGESETZT** (live DVOL 47.34, in macro_stance). **Speicher-Vereinfachung Teil 1 UMGESETZT** (`scripts/deploy.ps1` killt die Drift-Fehlerklasse) — finale Ein-Ordner-Migration (30 Bots/venvs) als PLAN bereit (`docs/MIGRATION_EINORDNER`), supervised auszuführen. **FRED-Key zuletzt gemeinsam** (Anleitung: `docs/ANLEITUNG_FRED_API`). Tiefere bezahlte On-Chain-Daten weiterhin out.

> **STATUS 2026-06-09 (FRED):** **Echte Makro-Werte via FRED UMGESETZT & LIVE** (Key in .env, NFCI+Fed-Funds → echtes Makro-Regime in macro_stance; live NFCI -0.494/FedFunds 3.63%/neutral). Damit sind alle key-freien + FRED-Datenquellen angebunden. **Offen nur noch:** finale Ein-Ordner-Migration (supervised), tiefere BEZAHLTE On-Chain-Daten.

> **STATUS 2026-06-10 (Portfolio-Ebene):** Die recherchierte **nächste Reifestufe = Schicht ÜBER den Bots**
> ist **UMGESETZT** (P1–P5, 222 pytest, :8137 51/51, live verifiziert inkl. reversiblem De-Risk-Test):
> **P1 Portfolio-Risk-Governor** (`governor.py` — aggregierter DD/Tagesverlust/Anomalien → alert/derisk/pause,
> läuft zuerst im Autopilot-Tick) · **P2 Konzentration/Korrelation** (`concentration.py` — Exposure/HHI/Cluster,
> speist Governor als Frühwarnung) · **P3 Vola-Sizing** (`sizing.py` — Stake invers zur Vola, Vollausbau von
> B3/W5) · **P4 Execution/Slippage** (`execution.py` + `stats.execution_costs` — Ist-vs-Erwartungspreis +
> Gebühren, M6-Prep) · **P5 Monitoring/Alerting** (`alerts.py` — Alert-Leiste + Panel). Dazu `cache.py`
> (TTL-Memo, Effizienz: Mehrfach-`evaluate` je Refresh → 1×). Code-Review: Hebel-Bug (SessionOpen 2× statt
> 3×) gefixt, Refresh-Redundanz eliminiert. Doku: `docs/SYSTEMCHECK_2026-06-10.md`. **Offen/optional:**
> Governor-`action` ggf. `alert` (statt derisk) in der Datensammelphase; Bulk-Snapshot-Query als tiefere
> Optimierung der ~700-ms-Kaltberechnung.

> **ENTSCHEIDUNG 2026-06-10 (Konzentrations-Deckel):** **Kein aktiver Deckel-Eingriff** — P2 bleibt reine
> WARNUNG. Begründung: der eigentliche Schaden der Konzentration (viele korrelierte Bots verlieren
> gleichzeitig) ist bereits doppelt abgedeckt — ① Per-Trade-Stop-Loss je Strategie (−2…−6 %, DCA −18 %, +
> `stoploss_on_exchange` als echte Börsen-Order) begrenzt die Tiefe jedes Einzelverlusts; ② Governor (P1)
> fängt den aggregierten Gesamt-Drawdown/Tagesverlust ab — unabhängig von der Ursache. Ein aktiver Deckel
> würde profitable Bots vorsorglich pausieren, nur weil korreliert → redundant + Fehl-Stopps. Daher NICHT bauen.
>
> **AUF DEM PLAN (DEFERRED, nach Stabilisierung) — „Pairs streuen" (Diversifikation):** den Bots mehr/andere
> liquide Paare geben (statt nur BTC/ETH/SOL), um die Gesamt-Korrelation an der Wurzel zu senken (fängt das ab,
> was korrelierte Stops bei Gap/Slippage + gleichzeitigem Feuern offenlassen). Bewusst später: erst soll der
> aktuelle Stand (P1–P5) stabil laufen. Erst als Plan ausarbeiten, nichts ungefragt umbauen.

## B. Recherchegestützte Verbesserungsideen (priorisiert)

### B1 · [HOCH] Echter Deflated/Probabilistic Sharpe Ratio (verfeinert A4)
Unser A4 nutzt nur den Erwartungswert-des-Maximums-Term `√(2·ln N)`. Der **vollständige DSR/PSR**
(Bailey & López de Prado 2014) korrigiert zusätzlich für **Stichprobenlänge T** und **Schiefe/Kurtosis**
der Renditen — kurze, nicht-normale Tracks (genau unsere MN-Engines!) werden so ehrlicher entwertet.
→ `mn_learn`/Engines liefern bereits Renditereihen; PSR = `Z((SR−SR*)·√(T−1) / √(1−γ₃·SR+((γ₄−1)/4)·SR²))`.
Konkret: PSR je Engine berechnen (gegen SR*=0) und als zusätzlichen Konfidenz-/Haircut-Faktor nutzen.
Quelle: davidhbailey.com/dhbpapers/deflated-sharpe.pdf, en.wikipedia.org/wiki/Deflated_Sharpe_ratio.

### B2 · [MITTEL] Event-typ-/Proximitäts-gewichtete Dämpfung (verfeinert F6)
Empirie: FOMC-Vol-Sprung BTC +0,44 pp, Volumen 2,39× (ScienceDirect 2026); CPI→FOMC = größtes
Risikofenster. → Dämpfung nicht binär (high/elevated), sondern **nach Event-Typ skalieren**
(FOMC > CPI > NFP) und **stetig mit der Nähe** (z.B. exponentiell ansteigend zum Termin). Macht den
Overlay treffsicherer.

### B3 · [MITTEL] Volatilitäts-Targeting als Sizing-Schicht
Best Practice rund um Events = Positionsgröße an Ziel-Vola koppeln. Da wir proposal-only sind: ein
**Vola-Target-Faktor** (realisierte vs. Ziel-Vola) als weiterer Allokations-Skalierer neben dem
Event-Overlay — würde später auch echtes Sizing für M6 vorbereiten.

### B4 · [NIEDRIG] Forward-Vola-Term-Struktur
„Knicks" in der Forward-Vol-Kurve markieren Event-Fenster — nur mit Optionsdaten (bezahlt) sinnvoll.
Parken bis echte Datenquelle vorhanden.

### B5 · [NIEDRIG/Infra] Regime-Export-Bridge venv-übergreifend
MasterMeta (Engine-venv) nutzt jetzt ein vola-normiertes Schwellen-Regime; echte Kopplung ans
python-Gaussian-HMM bräuchte eine Bridge (z.B. HMM-Regime in eine Datei/Tabelle exportieren, die die
Strategie liest). Größerer Infra-Schritt.

## C. Bereits offen aus der Übersicht (nicht vergessen)
- Vollkopplung MasterMeta ↔ HMM (= B5) · echte On-Chain-Tiefe (CryptoQuant/Glassnode, bezahlt) ·
  echte Makro-Werte (FRED-Key) statt Proxy · **F Design-Abschluss (Nicht-KI)** · **M6 Echtgeld-Pfad**.

## Quellen
- [Bailey & López de Prado — The Deflated Sharpe Ratio (PDF)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Deflated Sharpe Ratio — Wikipedia](https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio)
- [Probabilistic Sharpe Ratio — Portfolio Optimizer](https://portfoliooptimizer.io/blog/the-probabilistic-sharpe-ratio-hypothesis-testing-and-minimum-track-record-length-for-the-difference-of-sharpe-ratios/)
- [Scheduled FOMC statements & intraday macro event risk in crypto — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612326006021)
- [Amberdata — Crypto Options Analytics: CPI/FOMC & Volatility](https://blog.amberdata.io/crypto-options-analytics-cpi-surprise-fomc-outlook-crypto-volatility)
