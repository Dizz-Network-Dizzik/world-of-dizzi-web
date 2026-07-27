# 🌙 Arbeitspaket UI + Horizont-Modell (Nachtschicht 2026-06-10)

Großer UI-/Struktur-Block, autonom auszuführen nach finalem „Loslegen". Demo/0 Risiko. Ausgangsstand:
HEAD `45a5221`, 222 pytest grün, :8137 51/51. Reihenfolge nach Abhängigkeiten (Fundament zuerst).

## Geklärte Grundsatz-Entscheidungen (Nutzer)
- **Horizont-Modell (voller Umbau):** neues, gespeichertes BotConfig-Feld `horizon` ∈ {scalping, intraday,
  swing} als **primäre Gruppierung systemweit**. `trading_mode` (spot/futures) bleibt technisches
  Exchange-Attribut (Engine braucht es) — nur noch übers Hebel-Icon sichtbar.
- **Kategorien:** Scalping / Intraday / Swing (+ **Börsenöffnung** eigene Kategorie, überschreibt Horizont).
  Spot/Futures sind KEINE Gruppierungs-Dimension mehr.
- **Alle Bots → Futures:** die 6 Spot-Bots werden auf Futures konvertiert (Hebel, `:USDT`-Pairs, Config-Neu,
  Bot-Neustart). AI-Lern-DB NICHT zurücksetzen.
- **Echtgeld-Reife je Demo-Bot:** in einen Aufklapp-Container verpacken (nicht löschen).
- **Auto-Upgrade:** pro Bot — nach 1× manuellem Upgrade werden weitere **validierte** Verbesserungen
  automatisch angewandt, IMMER mit Versions-Bump + Changelog.

## Zeit-Horizont-Grenzen (recherchiert, key-frei; Quellen s. u.)
Standard-Krypto-Definitionen: Scalping = Sek–Min (1–5m), Intraday/Day = Min–Std innerhalb des Tages
(5m–1h), Swing = Tage (4h–1d+). Daraus die Schwellen (Ableitung aus `timeframe`):
- **scalping**: tf ≤ 5m  (1m, 3m, 5m)
- **intraday**: 15m ≤ tf ≤ 1h  (15m, 30m, 1h)
- **swing**: tf ≥ 4h  (4h, 1d, …)
- **Börsenöffnung**: Strategie `SessionOpenBreakout` → eigene Kategorie (unabhängig vom tf).

---

## BLOCK 0 — Fundament: Horizont-Modell (zuerst!)
- `models.py`: `BotConfig.horizon: Literal["scalping","intraday","swing"]` (+ in `BotCreate` optional;
  Default aus Timeframe abgeleitet, Helper `derive_horizon(timeframe, strategy)`).
- `registry.py`: Horizont beim Anlegen setzen; **Migration** `assign_missing_horizons()` (idempotent, im
  Startup) für alle bestehenden Bots aus dem Timeframe; Börsenöffnung erkennt Strategie.
- **Spot→Futures-Konvertierung**: Einmal-Migration der 6 Spot-Bots (trading_mode=futures, `:USDT`-Pairs,
  Hebel-Default, Config neu, einzeln neu starten). Lern-DB bleibt.
- `main.py /api/summary`: Gruppierung `groups` von futures/spot → **scalping/intraday/swing** (+ Börsenöffnung
  als eigener Schlüssel oder Flag). `_strategy_leverage`/Hebel-Icon bleibt.
- Tests: `derive_horizon`, Migration, Gruppierung. **Backend-Änderung → :8137-Neustart.**

## BLOCK 1 — Auto-Upgrade pro Bot (Backend)
- `models.py`: `BotConfig.auto_upgrade: bool = False`.
- `main.py`: beim ersten manuellen `apply_opt` → `auto_upgrade=True` setzen. Im Autopilot-Tick (oder bei neuem
  validiertem Gewinner): für alle Bots mit `auto_upgrade=True` den validierten Gewinner ihrer Strategie
  automatisch anwenden (DRY über `_apply_learned_params` → Version++ + Changelog + Neustart). Nur **validierte**
  Gewinner (gleiche Schwelle wie MasterMeta). Audit-Event `auto_upgrade_applied`.
- Tests: erst nach 1× manuell; nur validierte; Version/Changelog steigen.

## BLOCK 2 — Statistik-Übersicht (oben)
- Hover-Mini-Fenster (`cardpop`) ENTFERNEN · Wertungs-Sortierung ENTFERNEN · **Drawdown-Feld/Spalte komplett raus**.
- Obere KPI-Kacheln (grobe Statistik) → **klickbare, sticky Filter** (Toggle: aktiv bleibt aktiv). Aktiv =
  **Magenta** (`--acc2`) eingefärbt (Rahmen/Glow).
- **Grau-silberne Schrift → Theme-Schrift** (`--fg`/`--mut` statt des silbernen Tons; betrifft die KPI-Kacheln).
- **„Führende Bots" unter die großen Icon-Kacheln** pinnen — dort wird die Sortierung festgelegt.
- **Filter-Logik:** jeder aktive Filter rechnet über **ALLE** Bots neu → neue **Top-3** + die **ganze gefilterte
  Kategorie** (kurz) ausgeben. Für **jede** Filterart (inkl. Horizont-Kategorien). Mehrfachauswahl kombinierbar.

## BLOCK 3 — Lernbot / KI-Tool (großes Aufräumen)
Leitlinie: detailliert, aber nur dort ausklappen wo nötig; verschachteln, Struktur durchziehen.
- **MasterMeta = König (fix):** kompakte **Statistik-Ausgabe immer sichtbar** (außerhalb jeder Aufklappung),
  ganz oben. Darunter/daneben verpackt:
  - **„Algorithmus auf Echtgeld heben"** → hoch zur MasterMeta-Control, als **beobachtbarer Flow**
    (Status → „auf Echtgeld setzen" → „Geld überweisen" → „tradet"). Echtgeld-Reife-Container hier mit rein.
  - **Meta-Algorithmus (über alle Strategien)** → in den MasterMeta-Block verpacken.
- **Verschachteln/komprimieren** in sinnvolle Container (Aufklapp):
  - Vol-Targeting (P3, mini) · markt-neutrale Engines (CSM/Pairs/StatArb/Market-Making) → 1 Container
    „Markt-neutrale Edge-Engines" · Auto-Cull (Aussortierung) · Ausführungsqualität/Slippage (P4) ·
    Lern-Gedächtnis/Speicher-Lifecycle.
- **Verbesserungshistorie:** „Top-Performance-Verbesserungsversionen" sichtbar + „mehr ausklappen"
  (alle Filtermethoden + Statistiken).
- **Selbstanalyse:** kurze Erklärung ergänzen, wofür sie vorbereitet/dient.
- **Manuelle Upgrade-Buttons prüfen:** wo nach der Auto-Upgrade-Regel noch nötig — Rest reduzieren/erklären.

## BLOCK 4 — Krypto-Strategie-Katalog
- **Filter-/Studies-Leiste oben:** tabellarische Deklaration + Filter nach Strategie-Parametern UND Bewertung
  (Sicherheit / Güte / geschätzte Profitabilität). Nach Horizont-Kategorie filterbar.
- **Gruppierung:** Spot raus; Top-Ebene = **Scalping / Intraday / Swing**, **Börsenöffnung** + **Markt-neutral/
  Arbitrage** als eigene aufklappbare Unter-System-Container (Dreifach-Schachtelung ok).
- **„Verbesserung auf ALLE Bots gleichzeitig anwenden"** je Strategie/Kategorie (nutzt Auto-Upgrade-Pfad).
- Hebel-/Futures-Icons bleiben überall erhalten.

## BLOCK 5 — Icon-Legende (Physik-Redesign)
- **Aufklapp-/Öffnen-Mechanismus** klar wiederherstellen (man muss sie zuverlässig öffnen können).
- **Bildschirmrand = saubere Bounce-Grenze** (Panel darf nicht im Rand verschwinden).
- **Schleuder neu (Twistel):** Spannung baut sich NICHT beim Greifen auf, sondern sobald man das Icon-Panel
  über die **Ränder anderer Panels** zieht. An diesen Kreuzungspunkten: **unsichtbare** Zwille (keine sichtbare
  Linie), die Icons fangen an zu **glühen** (Spannungs-Glow steigt mit Auslenkung). Loslassen → relief →
  schleudert das Panel von genau diesen Punkten weg.

## BLOCK 6 — Abschluss (Pflicht)
- Systemweit prüfen: wo muss die neue Kategorisierung überall eingebaut sein? Funktionalität gewährleistet?
- **Systemcheck-Schleife bis 2× am Stück sauber:** alle Tests grün, Code-Review (Korrektheit + Effizienz +
  Interaktion der neuen Kategorisierung), Fehler beheben, wiederholen. Erst dann „fertig".
- :8137-Neustarts nach Backend-Änderungen (venv-Python, ohne `--reload`). 51/51 halten.

## Freigaben für die Nacht
Autonom ohne Rückfrage · Token-Recherche erlaubt (Horizont-Grenzen final) · :8137-Neustarts erlaubt ·
222+ Tests grün halten · am Ende Doku + (auf Zuruf) Commit/Backup.

Quellen (Horizont-Definitionen): TradeLink, Mubite, YouHodler, Altrady (Krypto-Timeframe-Guides 2026).
