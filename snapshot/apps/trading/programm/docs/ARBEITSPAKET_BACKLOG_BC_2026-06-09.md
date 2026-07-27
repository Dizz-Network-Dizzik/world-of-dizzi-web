# 🌙 Arbeitspaket (autonom, Nacht 3) — Verbesserungs-Backlog B + C

**Auftrag:** Den gesammelten Backlog (B1–B5 + C-Punkte) als eigenständiges Paket abarbeiten — Recherche
zur sauberen Integration, dann Stück für Stück selbstständig umsetzen, committen, danach wieder die
regelmäßigen Monitoring-Runs. Freigaben: empfohlene/sinnvollste Variante wählen, nicht nachfragen.
Invarianten: 30/30, Tests grün, proposal-only, 0 Risiko, key-frei wo möglich (ehrlich bei bezahlten Limits).

**Recherche-Grounding:** blockchain.com Charts-API (key-frei, JSON: Active Addresses/Tx/Hash-Rate/Fees/
Tx-Volumen → NVT). PSR (López de Prado): `sr_std=√((1+0.5·sr²−skew·sr+((kurt−3)/4)·sr²)/(n−1))`,
`PSR=Φ(sr/sr_std)` — Φ via math.erf, reines Python.

## Segmente
- [x] **W1 (B1) — Probabilistic/Deflated Sharpe Ratio.** `mn_base.equity_stats` liefert zusätzlich
      Schiefe/Kurtosis/Periode-Sharpe/n; reine `mn_base.psr()` (Φ via erf). `mn_sleeve` gewichtet jede
      Engine zusätzlich mit ihrem **PSR-Faktor** (statistische Signifikanz der Sharpe, gegen kurze/nicht-
      normale Tracks) — ergänzt den Multiple-Testing-`deflate_factor`. Tests.
- [x] **W2 (B2) — Event-typ-/Proximitäts-gewichtete Dämpfung.** `fundamental` dämpft nach Event-Typ
      (FOMC > CPI > NFP > generisch) UND stetig mit der Nähe zum Termin (näher = stärker). Tests.
- [x] **W3 (C-Makro) — Echte Makro-Werte/Überraschung.** Kalender-`actual`/`forecast`/`previous`
      (key-frei) → CPI/NFP-Surprise → fließt in `macro_stance` (heißer CPI = hawkish = risk_off-Tilt). Tests.
- [x] **W4 (C-OnChain) — Echte On-Chain-Tiefe (key-frei).** blockchain.com Charts: Active Addresses,
      NVT (MarketCap/Tx-Volumen), Hash-Rate, Fees → echtes On-Chain-Signal in `crypto_fundamentals`/
      `macro_stance` (ersetzt das dünne CoinGecko-Only-Proxy). Defensiv gecacht. Tests.
- [x] **W5 (B3) — Volatilitäts-Targeting-Sizing.** Vol-Target-Faktor (realisierte vs. Ziel-Vola) als
      zusätzlicher Allokations-Skalierer im Master-Overlay (tunbar). Bereitet M6-Sizing vor. Tests.
- [x] **W6 (B5/C) — MasterMeta↔HMM-Regime-Bridge.** Live-HMM-Regime (+Konfidenz) in eine kleine Datei
      im geteilten Data-Dir exportieren; die Engine-Strategie `master_meta.py` liest sie (venv-übergreifend),
      Fallback = eigenes Schwellen-Regime. Tests (Bridge-IO rein).
- [x] **W7 — Docs + Live-Verifikation.** Übersicht/Backlog aktualisieren; **B4 (Forward-Vola-Term-
      Struktur)** bleibt dokumentiert DEFERRED (braucht bezahlte Optionsdaten — ehrlich).

## Reihenfolge-Logik
Daten-/Härtungs-Kern zuerst (höchster Hebel, in sich geschlossen): W1 → dann Fundamental-Vertiefung
W2→W3→W4 → Sizing W5 → Infra-Bridge W6 → Docs W7. Jedes Segment einzeln verifiziert + committet;
nach Backend-`.py` deploy+Neustart, 30/30 halten. Danach: reguläre Monitoring-Runs fortsetzen.
