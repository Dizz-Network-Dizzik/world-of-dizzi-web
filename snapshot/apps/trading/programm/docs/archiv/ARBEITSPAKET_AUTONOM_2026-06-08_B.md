# Arbeitspaket autonom — UI/Lern-Upgrades + Schleuder-Physik (08.06.2026, Teil B)

Autonom am Stück abarbeiten, ohne Rückfragen. Frontend = served-fresh (kein Neustart);
Backend-`.py` → trial-Sync + :8137-Neustart (Port-Owner via `Get-NetTCPConnection`,
trial-venv, ohne --reload) + `py_compile`/`pytest` (52) grün. 30/30 halten. Nach
logischen Blöcken committen, im Browser (Preview `live8137`) Konsole-fehlerfrei prüfen.

## Phase 1 — Bot-Detail: Basis-Config vs. Lern-Version (Task 15 + 16) [index.html]
- `botHasLearnedVersion(b)` = `opt_version>=1`; `botHasBaseConfig` = opt_params + v0.
- „AI-optimiert/Lern-Version vN" NUR bei `botHasLearnedVersion` (nicht bei bloßem opt_params).
  → Eröffnungs-Bots (Session-Setup = Basis, v0) zeigen KEIN „AI-optimiert".
- `improvementBox(b,id)`: reicher Versions-/Vorschlag-Status: „Basis-System (v0) läuft" →
  „Lern-Vorschlag da → Version N baubar (X Lernadaptionen, Test %)" → bei aktiver Version
  „Lern-Version vN aktiv". Modifizierte Bots klar mit Version markiert.
- Reset-Button nur bei Lern-Version (nicht Basis-Config zerstören). upgradeBadge/upgN/
  „verfügbare Verbesserungen"-Listing auf `botHasLearnedVersion` umstellen.
- STATUS: Helfer + upgradeBadge erledigt; Rest (Zeilen-Badge, Detail-Box, Reset, Listing) offen.

## Phase 2 — Icons/Buttons + Open-Glow (Task 21 + 20) [index.html CSS+Markup]
- Start-Button NICHT mehr permanent farbig (Status „läuft" macht das obsolet) → neutral.
- Details-Button (▸) farbig + schöneres Icon; wenn das Detail OFFEN ist → Button verliert
  Farbe UND die offene Zeile/Strategie bekommt starken Glow (`.openrow`/`.detail-open`).
- Generell schönere Icons bei Aktionen (Anlegen etc.). Details-Button bekommt eigenes Icon.

## Phase 3 — Nested-Details Auto-Collapse (Task 19) [index.html JS]
- Beim Schließen eines `<details>` alle inneren `<details>` ebenfalls schließen (delegiert
  via toggle-Listener) → beim Wiederöffnen ist innen alles zu.

## Phase 4 — Statistik: permanenter Sort-Toggle + Ranking (Task 17) + Eröffnungs-Writer (Task 18) [index.html]
- Permanente Anzeige „sortiert nach: <Statistik>" + Toggle (Profit live / Winrate / Trades /
  Profit abs). Re-sortiert die Bot-Tabellen + zeigt permanentes Register der führenden Bots.
- Statistik-Übersicht: dritte Sektion „Börseneröffnungen" (neben Futures/Spot), eigene
  Statistik, in Sortier-/Ausgaberaster aufgenommen (Bots mit strategy=SessionOpenBreakout).

## Phase 5 — ROI-Grafik deutlich detaillierter (Task 22) [index.html]
- Recherche-Basis: Equity-Kurve + Underwater/Drawdown-Subplot (rot unter 0), High-Water-
  Marker (neue Hochs), Achsen/Grid/Nulllinie, Start/Ende-Werte, ROI/MaxDD-Badges, Hover.
- `richEquitySvg` ersetzen/erweitern: zweigeteilt (Equity oben + Underwater unten), Marker,
  Achsenbeschriftung, Drawdown-Schattierung. Deutlich reicher als Sparkline.

## Phase 6 — Schleuder-Physik (Task 25) [index.html `initLegendFloat`]
- **Anchor-Slingshot:** Bei pointerdown Anker = Element-Mitte merken. Spannung = Zug-Distanz
  vom Anker. Loslassen → Geschwindigkeit ENTGEGEN der Zugrichtung (`unit(anchor-cur)*speed`).
  (von links reinziehen → schnellt nach links weg.)
- **Mehr Spannung übers ganze Dokument:** Referenz = ~0.7·Bildschirm-Diagonale (statt halbe
  Mindest-Dimension) → Zug über fast den ganzen Screen lädt Maximum; `speed = 4 + charge*48`,
  `MAXV` 18→46 → „schießt richtig los".
- **Momentum hauptsächlich seitlich:** `vy *= 0.4` (lateral dominant).
- **Sauberer Abprall ganz oben:** Decken-Reflexion robust (clamp + reflect), kein Tunneling.
- `--charge`-Glow weiter aus Zug-Distanz/Referenz.

## Phase 7 — Eröffnung in Lern-Schicht prüfen (Task 23) [meta/master/csm]
- Verifizieren/ergänzen: per-Strategie-Lernen, Master-Algorithmus, CSM, KI-Meta-Sektion —
  ist „Session/Eröffnung" strukturell eingebaut? (session_performance/advice schon da.)
  Ggf. Master/CSM um Session-Bewusstsein ergänzen (mind. Doku/Anzeige).

## Phase 8 — Trading-Aspekte-Audit (Task 24) [ai.py] + Nutzer-Info
- Recherche zeigt: Market-Making + Pairs-/Statistical-Arbitrage sind die großen, noch nicht
  explizit vertretenen Aspekte. → In den KI-Recherche-Prompt als Pflicht-Abdeckung aufnehmen
  (+ ggf. Seed). Danach NUTZER INFORMIEREN + FRAGEN, ob eigener Recherche-Schwerpunkt/Kapitel
  wie bei Börseneröffnungen gewünscht.

## Phase 9 — Abschluss
- `pytest` (52) grün, trial-Sync, :8137-Neustart (nur bei Backend), 30/30, Browser-Konsole
  fehlerfrei, committen. Memory aktualisieren ([[trading-bot-eins-boerseneroeffnungen]],
  [[trading-bot-eins-stand]]).
