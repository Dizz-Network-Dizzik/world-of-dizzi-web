# PROPOSAL (World-Chat) — Funding-Rate-Carry als 2. markt-neutrale Engine

**Status:** Proposal-only (strukturell ⇒ World-Chat-Entscheid). Erstellt 17.06.2026 (Bau-KI 4.8, KI-Trainings-Chat).
**Kein Code im Live-Pfad geändert.** Dieser Entwurf bündelt Motivation + Design + ehrliche Risiken + Architektur-Fragen.

> ## ⛔ EMPIRISCHE EVALUIERUNG (Runde 3, 18.06.) — ERGEBNIS: aktuell NICHT viabel
> Die Funding-Carry-Edge wurde **gemessen** (read-only, `research/funding_carry_backtest.py` + `funding_scan.py`),
> wie vom Trainings-Auftrag verlangt („sauber gegen Kosten rechnen"). **Ehrliches Ergebnis:**
> - **Variante B (cross-sectional perp-only) — strukturell GESCHEITERT.** OOS-kombiniert Sharpe **−6.76**.
>   Die **Funding-only-Sharpe +16.19** ist die **Fata Morgana** (ignoriert die Preis-Beine, die −7.74 scoren).
>   Grund (sample-UNabhängige Mathematik): Funding (~bps/Tag) ertrinkt in der idiosynkratischen **Preis-Varianz**
>   der funding-gerankten Beine (~%/Tag). `beta_BTC ≈ +0.05` (markt-neutral zu BTC, aber NICHT zur Einzel-Drift).
>   ⇒ **Meine Runde-2-Empfehlung „Variante B zuerst" war FALSCH** — durch Evidenz korrigiert.
> - **Variante A (cash-and-carry, gleiches Asset) — Carry-Decke zu dünn.** Netto-Carry-Scan (90 T): 25/50 Perps
>   net>0, aber nur **3 robust** (pos_share≥70 % ∧ net>5 %) — obskure Small-Caps (BEAT/LAB/SKYAI, instabiles
>   Funding). Die **liquiden, hedgebaren Majors (BTC/ETH/BNB) tragen ~0,2–0,4 %/Jahr ≈ NULL nach Gebühren.**
> - **Verdikt:** Funding-Carry ist auf diesem Venue **derzeit keine viable 2. MN-Engine** — kein Tuning-Problem,
>   ein **struktureller** Befund. §0-konform gemeldet statt das Gate zu lockern. **Caveat:** Bitget-Funding-Historie
>   nur ~34 T (Endpoint-Limit) ⇒ die ZAHLEN sind nicht robust, aber die STRUKTUR-Befunde (B: Varianz-Dominanz;
>   A: Majors-Carry≈0) sind es. Der Entwurf unten bleibt als **Referenz**, falls sich die Carry-Bedingungen ändern
>   (dann NUR Variante A, gleiches Asset, mit Spot-Hedge + Stress-Test). Details: §8 unten.

---

## 1. Warum (die ehrliche Lücke)

Der Master-Sockel hat **genau EINE aktive Engine: Market-Making (MM)** — und das ist eine **Simulation**.
Code-verifiziert (`master.py:220–231`): bei N=1 aktiver Engine ist die gewichtete Sockel-Fitness **per
Konstruktion identisch mit der 1/N-Benchmark** (`fitness == benchmark_1n.fitness`, live v70: 1.0313 == 1.0313).
Die Gewichtungs-Maschinerie (haircut/conf_shrink/max_weight/softmax/deflation) ist **wirkungslos**, solange
es nur eine Engine zu gewichten gibt.

**Konsequenz:** „Master schlägt 1/N" kann erst dann ECHT zutreffen, wenn eine **zweite, unkorrelierte,
qualifizierte** Edge-Quelle existiert. CSM erreicht die Schwelle nicht (Sharpe 0.24–0.27 < Haircut+Deflation
≈ 0.83) und ist **signal-/datengebunden, nicht tuninggebunden** — `deflate_factor` zu senken wäre ein §0-Verstoß
(Messung schwächen). Pairs/StatArb sind in trend-dominiertem Markt strukturell negativ.

Es fehlt eine **reale** (nicht-simulierte) markt-neutrale Edge-Quelle. **Funding-Rate-Carry** ist der naheliegendste
ehrliche Kandidat: ein beobachtbarer Cashflow, unkorreliert zu Momentum (CSM) und Microstruktur (MM).

---

## 2. Was schon existiert (wir bauen NICHT bei Null)

| Asset | Datei | Was es liefert |
|---|---|---|
| Carry-Universums-Scan | `research/funding_scan.py` | Bitget-Perps nach **Netto**-Carry (Funding − 0.32 % Roundtrip-Fee), `pos_share` (Stabilität %), `vol_pct` (Funding-Streuung) |
| Hedgebarkeits-Schnitt | `research/funding_hedgeable.py` | Filtert auf Perps mit **liquidem Spot-Market** (>1 Mio USDT/24h) = echtes Cash-and-Carry-Universum |
| Funding-Fetch + Drag | `backend/app/csm.py:94–104, 135–136` | zieht schon `fetch_funding_rate_history`, speichert `funding_avg`, nutzt Funding als **Kosten**-Proxy in CSM |
| MN-Engine-Vertrag | `mn_base.py` + `master.MN_ENGINES` | `config_get/set`, `equity_stats` (Sharpe/PSR/MaxDD, **PSR korrigiert Schiefe+Kurtosis**), `status()`-Shape |

→ Die Funding-Carry-**Mess**-Logik (inkl. ehrlicher Fee-Modellierung) ist research-seitig **fertig**. Der Vorschlag
ist die **Produktivierung** dieses Wissens als Sockel-Engine mit dem Standard-Vertrag — nicht neue Forschung.

---

## 3. Zwei Design-Varianten (ehrliche Trade-offs)

**Variante A — Cash-and-Carry (echt markt-neutral, braucht Spot-Leg)**
Long Spot + Short Perp auf Pairs mit positivem Netto-Carry (aus `funding_hedgeable`). Delta-neutral (Spot-Long
hebt Perp-Short auf), kassiert Funding (Short-Perp empfängt von Longs). Edge = Funding − Fees − Slippage beider Legs.
- ✅ Echte Markt-Neutralität; **+**: deckt sich 1:1 mit dem bereits gescannten hedgebaren Universum.
- ⚠️ Braucht Spot-Marktdaten + zweites Leg; Basis-Blowout-Risiko (Short-Squeeze treibt Perp-Prämie).

**Variante B — Cross-Sectional Funding (perp-only, dollar-neutral)** ← **empfohlen für den Start**
Long die Perps mit dem **negativsten** Funding (als Long empfängt man Funding bei Funding<0), Short die mit dem
**positivsten** Funding, gleiche Notional je Seite. Erntet die Funding-**Dispersion**, market-neutral durch
Konstruktion (∑Long-Notional = ∑Short-Notional). Spiegelt die CSM-Struktur, nur auf Funding statt Momentum.
- ✅ Kein Spot-Leg nötig (passt zum perp-only-System); reuse der CSM-Cross-Sectional-Mechanik.
- ⚠️ Nicht perfekt markt-neutral (Rest-Beta zwischen Long/Short-Korb möglich) → muss gemessen/gehedged werden.

---

## 4. Konkrete Implementierung (plug-in in den bestehenden Vertrag)

Neues Modul `backend/app/funding.py` (Muster wie `csm.py`):

```
DEFAULTS = {lookback_periods, n_long, n_short, rebalance_periods,
            taker_fee_bps, slippage_bps, min_history, capital}
refresh()  -> ccxt fetch_funding_rate_history je Symbol -> Tabelle funding_rates(symbol, ts, rate)
simulate() -> je Rebalance: ranke nach trailing Funding -> Long/Short-Körbe (Var. B) bzw.
              hedgebare Carry-Positionen (Var. A) -> realisiertes Funding akkumulieren,
              Turnover-Kosten (taker_fee + slippage) abziehen -> Perioden-Returns
              -> mn_base.equity_stats()   # liefert Sharpe/PSR/MaxDD identisch zu CSM/MM
status()   -> {ready, stats:{sharpe, psr, days, ...}}   # gleiche Shape wie csm.status
optimize(windows) -> anchored Walk-Forward über (lookback, n_long/n_short, rebalance)
```

Registrierung: `master.MN_ENGINES += [("funding", funding.status)]`. Damit wird `n_eval = 5` → die
Deflation steigt ehrlich von √(2·ln 4) auf √(2·ln 5) (mehr Multiple-Testing-Abzug für alle).
API-Routen analog CSM: `GET /api/funding`, `GET /api/funding/optimize`, `POST /api/funding/refresh`.

---

## 5. Ehrliche Qualifikations-Gates & Risiken (damit es KEINE neue Fata Morgana wird)

1. **Kosten-inklusiv von Anfang an** — Funding-Carry lebt/stirbt an Fees + Slippage. `funding_scan` rechnet
   bereits mit 0.32 % Roundtrip; die Engine muss Rebalance-Turnover-Kosten je Periode abziehen (nicht nur 1×).
2. **Short-Tail-Charakter** — Carry verdient klein+stetig, verliert groß bei Basis-Blowout (Squeeze). Die
   hohe Sharpe ist die **Signatur** dieses Profils und allein KEIN Qualitätsbeweis. **PSR** (`mn_base.psr`,
   korrigiert für Kurtosis) ist hier das entscheidende Härtungsmaß — fat tails drücken PSR korrekt.
3. **Schwelle gilt unverändert** — die Engine bekommt nur dann Master-Gewicht, wenn ihre **gehärtete** Sharpe
   (Sharpe − Haircut − Deflation) > 0 UND PSR signifikant. Reicht der reale Netto-Carry nach Kosten nicht,
   **qualifiziert sie sich nicht — und das ist die ehrliche Antwort.**
4. **Stress-Fenster ausweisen** — MaxDD über bekannte Basis-Blowout-Perioden separat berichten (nicht nur den
   Vollzeitraum-MaxDD), damit der Tail sichtbar bleibt.
5. **Markt-Neutralität messen (Var. B)** — Rest-Beta des Long/Short-Korbs gegen den BTC+ETH+SOL-Index ausweisen.

---

## 6. Ehrliche Erwartung

Funding-Carry ist ein **real dokumentierter** Krypto-Edge (Basis-Trade), aber kein Free Lunch: nach Fees +
Tail-Risiko ist der robuste Netto-Carry oft moderat. Möglich, dass die Engine eine **echte, aber kleine**
Sharpe liefert (z. B. 0.8–1.5 nach Kosten) — das würde **reichen**, um als 2. Engine zu qualifizieren und den
Master ECHT (nicht nur per Konstruktion) über 1/N zu heben, weil die Funding-Edge **unkorreliert** zu MM ist
(Diversifikations-Gewinn). Genauso möglich: nach ehrlichen Kosten bleibt zu wenig → dann ist das Ergebnis
„kein 2. Edge belegt", was den Stand nicht verschlechtert, sondern nur ehrlich abschließt.

---

## 7. Architektur-Fragen für den World-Chat (Entscheid nötig)

- **Variante A oder B zuerst?** (Empfehlung: B = perp-only, weil kein Spot-Datenpfad nötig und CSM-Mechanik reusebar.)
- **Daten:** eigene Tabelle `funding_rates` (mirror `csm_prices`) im geteilten `mn_base`-Schema? Refresh-Takt
  (Funding alle 8 h ⇒ täglicher Refresh genügt)?
- **Rebalance-Treue:** Perioden-Turnover-Kosten — pauschal (taker+slippage bps) oder pair-spezifisch aus Ticker-Spread?
- **N_eval-Effekt akzeptiert?** 5. Engine erhöht die Deflation für ALLE (ehrlich, aber dämpft auch MM minimal).
- **Wer baut:** App-Chat (Bau-KI) nach World-Chat-Architektur-Freigabe; appkit/Vertrag bleiben unberührt (rein TB-interne Engine).

---

**Zusammenfassung:** Eine `funding.py`-Engine nach dem bestehenden MN-Vertrag, gespeist aus der schon
vorhandenen Funding-Research, kosten-inklusiv und PSR-gehärtet — der einzige ehrliche Weg, dem Master eine
**zweite, reale, unkorrelierte** Edge-Quelle zu geben und „über 1/N" von einer Konstruktions-Tautologie in
ein echtes Ergebnis zu verwandeln.

---

## 8. EMPIRISCHE EVALUIERUNG (Runde 3, 18.06.2026) — Methode + Daten + Verdikt

**Methode (`research/funding_carry_backtest.py`, read-only/public ccxt, 0 Echtgeld):**
- Preise: `csm_prices` (2 J Tagesschluss, 50 liquide Perps, schon in der DB). Funding: ccxt Bitget
  `fetch_funding_rate_history`, auf Tages-Summe aggregiert, als Snapshot `research/_funding_hist.json` eingefroren.
- Variante-B-Backtest cross-sectional, dollar-neutral, täglich rebalanced; **Funding-P&L UND Preis-P&L der Beine
  GETRENNT** gemessen, Turnover-Kosten (taker 6 bps + slippage 2 bps, positions-persistenz-bewusst) abgezogen.
- Point-in-time: Signal = trailing-Funding bis t−1; Realisierung über [t, t+1] (kein Lookahead).
- Anchored Split: 60 % Train (Param-Wahl nach combined Sharpe) → 40 % OOS-Test mit eingefrorenen Params.

**Ergebnis (OOS-Test, lookback=3/k=3 aus Train):**
| Metrik | Wert | Lesart |
|---|---|---|
| Funding-only Sharpe | **+16.19** | Fata Morgana (ignoriert Preis-Beine) |
| Preis-Beine-only Sharpe | **−7.74** | die Beine driften adversiv |
| **Kombiniert + Kosten Sharpe** | **−6.76** | die EINZIGE zählende Zahl |
| PSR(combined) | 0.111 | nicht signifikant |
| MaxDD(combined) | −27.5 % | |
| beta_BTC | +0.05 | markt-neutral zu BTC, aber Einzel-Drift dominiert |
| gehärtete Sharpe (−Haircut 0.5 −Deflation 0.36@N=5) | **−7.61** | **qualifiziert NICHT** |

**Variante-A-Decke (`funding_scan.py`, 90 T, Fee-Drag 1.30 %/Jahr):** 25/50 Perps net-Carry>0; nur **3 robust**
(BEAT 18.2 % · LAB 14.8 % · SKYAI 12.2 % net/Jahr — Small-Caps, hohe Funding-Vol); liquide Majors BTC/ETH/BNB
≈ 0,2–0,4 %/Jahr (≈ 0 nach Gebühren). ⇒ Selbst die strukturell korrekte Variante A hat auf hedgebaren Majors
**keine** Decke; positiver Carry nur auf illiquiden Namen mit fraglichem Spot-Hedge + instabilem Funding.

**Limitierungen (ehrlich):** Bitget-Funding-Historie nur ~34 T pro Symbol (Endpoint) ⇒ Backtest-Span
2026-05-16 → 06-17 (OOS 11 T). Die ZAHLEN sind daher nicht robust; die STRUKTUR-Befunde (B: Preis-Varianz ≫
Funding ⇒ Carry-Signal ertrinkt; A: Majors-Carry ≈ 0) sind sample-unabhängig und tragen das Verdikt.

**Konsequenz:** Funding-Carry **vom Tisch als nächster Hebel** (ehrlich, kein gelockertes Gate). Falls je
reaktiviert: NUR Variante A (gleiches Asset, Spot-Hedge), mit längerer Funding-Historie (andere Quelle/tiefere
Pagination) + expliziten Basis-Blowout-Stress-Fenstern. Der echte nächste Hebel liegt woanders (s. WIEDEREINSTIEG).
