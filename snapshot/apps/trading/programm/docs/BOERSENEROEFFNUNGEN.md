# Börseneröffnungen im Trading — Recherche & System-Integration

> Sonder-Thema „Markt-/Session-Eröffnungen": Trade-Systeme, die **nicht** primär auf
> Chart-Indikatoren beruhen („der Graph macht X"), sondern auf der **Zeit-Struktur des
> Marktes** — den Eröffnungen der großen Handelszonen (Asien/Tokio, London/EU, USA/NY)
> und den daran hängenden Volatilitäts-/Liquiditäts-Mustern. Stand 2026-06-08.
> Reine Demo/Paper-Forschung, kein Echtgeld.

## 1. Warum Eröffnungen? (Marktlogik)

Krypto handelt 24/7, trotzdem zeigen Volumen und Volatilität **klare, über Jahre
stabile „Sessions"**, getrieben von der geografischen Handelsaktivität. An den
Eröffnungen strömen institutionelle Orders in den Markt → **Volatilitäts- und
Liquiditäts-Spitzen**, große Impuls-Bewegungen, oft gefolgt von Mean-Reversion.
Genau diese wiederkehrende Zeit-Struktur ist ausbeutbar — und besonders wertvoll
für **Lern-Instanzen**, weil die Muster *zeitlich verankert* und damit
reproduzierbar sind (anders als rein indikator-getriebene Signale).

## 2. Session-Fenster (UTC) — die „Opens"

Alle Zeiten in **UTC** (System-intern), zusätzlich NY-Referenz (ICT-Konvention).

| Session            | Open-Fenster (UTC) | Charakter |
|--------------------|--------------------|-----------|
| **Asia** (Tokio)   | 00:00–02:00        | niedrigere Vola, stabiler; „Asian Range" als Referenz |
| **London / EU**    | 07:00–09:00        | höchstes Volumen der EU-Zone; Trend-Initiierung |
| **US / NY**        | 13:00–15:00        | US-Aktien-/CME-Open 13:30; hohe Vola |
| **EU↔US-Overlap**  | 13:00–16:00        | **Vola-/Liquiditäts-Peak** (~16–17 UTC „tea time") |
| **Late US**        | 21:00–23:00        | empirisch beste BTC-Stundenrenditen (22–23 UTC) |

**ICT-Killzones** (NY-Lokalzeit, zur Einordnung): Asia 19–22, London 02–05,
NY 07–10. Empirie: EU- (08–16:30 UTC) und US-Stunden (14:30–21 UTC) liegen
über dem Schnitt, Asien-Stunden eher darunter — Ausnahme **Monday-Asia-Open**.

## 3. Trade-Systeme auf Eröffnungs-Basis

Jedes System ist *zeitlich getriggert* (Session-Open-Fenster) — die Indikatoren
dienen nur der Bestätigung, nicht als Haupt-Auslöser.

1. **Opening Range Breakout (ORB)** — Kern-System.
   - Opening Range = High/Low der ersten N Min nach Open (typisch 15 min; 5–60).
   - Long, wenn eine 5m-Kerze über das Range-High schließt (Short unter Range-Low);
     Kerzen-Range > Ø der letzten 5 Kerzen, Body mehrheitlich außerhalb,
     Volumen ≥ 1,5× Schnitt.
   - Stop am gegenüberliegenden Range-Ende; TP als Measured Move (Range-Höhe),
     Teilgewinne 2:1/3:1, Rest auf Breakeven. Max. 1 Trade je Seite/Session.
   - Trefferquote real ~40–60 %.

2. **Gap-and-Go / Opening Drive** — Impuls in Gap-Richtung; spielt sich in den
   ersten 30–90 min ab; Stop unter VWAP; verliert der Trade sofort VWAP = Fehlschlag.

3. **CME-Gap-Fill (krypto-spezifisch)** — Wochenend-Gap zwischen CME-Future und
   Spot; ~77 % füllen binnen einer Woche Richtung Freitags-Close. (Hinweis:
   CME 24/7 ab Ende Mai 2026 → Lebenszyklus dieses Edges läuft aus, bleibt aber
   als Muster lehrreich.)

4. **Session-Open-Momentum / Killzone** — In den Open-Fenstern Richtung des
   ersten Impulses traden (Order-Block/OTE-Logik), außerhalb der Fenster pausieren.

5. **Monday-Asia-Open-Effekt** — Intraday-Trendfolge ist von So ~19:00 NY
   (≈ 00:00 UTC Mo) ~24 h stark positiv (Tokio-Open). → zeit-getriggerte Long-/
   Trend-Neigung am Wochenstart.

6. **Opening-Fade / Failed-Breakout** — Niedrig-Volumen-Gap oder gescheiterter
   ORB → Gegenrichtung zurück zu Prior-Close/VWAP (Mean-Reversion am Open).

## 4. Integration ins System (Architektur)

Eröffnung wird **First-Class-Konzept**, kein Einzel-Bot:

- **`backend/app/sessions.py`** (neu, shared): kanonische `SESSION_OPENS`
  (UTC-Fenster), `session_for(dt)` (welche Session/welches Open), `opening_window(dt)`
  (im Open-Fenster? welche Session?). Eine Quelle für Backend, Lern-Schicht, Tests.

- **Recherche-Tool (`ai.py`)**: 
  - Neue System-Felder `trigger_type` (`signal` | `session_open`), `opening_session`
    (asia|london|us|eu_us_overlap|none), `opening_range_min`.
  - `research_config.opening_focus` (Toggle, Default an).
  - **Eigenes Eröffnungs-Kapitel** im Recherche-Prompt: fordert explizit
    Eröffnungs-Systeme (ORB, Gap-and-Go, CME-Gap, Session-Momentum, Monday-Asia,
    Opening-Fade) inkl. Session-Zeiten in UTC und `trigger_type='session_open'`.
  - **Seed-Katalog** um genau diese Systeme erweitert (laufen ohne API-Key).

- **Engine (`session_open_breakout.py`, neu)**: lauffähige Freqtrade-ORB-Strategie,
  zeitlich an Session-Opens verankert, via `TBT_OPT_PARAMS` parametrisierbar →
  der konkrete „Sonder-Trade", den Eröffnungs-Katalog-Systeme aktivieren können.

- **KI / Lern-Schicht (`meta.py`, `tracker.py`)**: 
  - `tracker.market_snapshot` speichert zusätzlich die **Session** des Snapshots.
  - `meta.session_performance_per_trade()` — Ø Trade-Profit je (Strategie × Session)
    aus den echten geschlossenen Trades (Session = Session-Fenster des Trade-Schluss),
    analog zur bestehenden Regime-Auswertung.
  - `meta.session_advice()` — „beste Eröffnung/Session" je Bot/Strategie →
    Präzisions-Hinweis für die Lern-Instanz; in `report()` eingehängt.
  - Opening-Hinweise in den KI-Prompts (Analyse/Critique/Chat).

- **Frontend (`index.html`)**: Recherche-Toggle „Börseneröffnungen-Schwerpunkt",
  Katalog-Badge „Eröffnung · <Session>" auf `session_open`-Systemen, KI-Anzeige
  „beste Session", Tooltip-Erklärungen.

## 5. Quellen (Auswahl)

- Opening Range Breakout: litefinance.org, tradethatswing.com, tradersmastermind.com
- Crypto-Session-Effekte: amberdata.io (Volatility Dispersion / Rhythm of Liquidity),
  Springer „crypto trades at tea time", arxiv 2109.12142 (Periodicity)
- ICT-Killzones: innercircletrader.net, tradingrage.com
- CME-Gap: whaleportal.com, bitget academy, coindesk (24/7-Umstellung Mai 2026)
- Gap-and-Go / VWAP: highstrike.com, tradezella.com
- Monday-Asia-Open / Intraday-Seasonality: concretumgroup.com,
  quantifiedstrategies.com, quantpedia.com (Overnight Seasonality in Bitcoin)
