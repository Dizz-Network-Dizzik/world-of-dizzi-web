# 🛠️ Arbeitspaket (autonom abarbeitbar) — Stand 08.06.2026, HEAD `477be34`

> **Zweck:** Den Nutzer-Backlog (`STATUS_BACKLOG_NUTZER_2026-06-08.md`) in eine **geordnete, selbstständig
> abarbeitbare Schritt-für-Schritt-Reihenfolge** überführt. Details je Punkt stehen im Backlog (IDs A1…G).
> In der nächsten Session mit Volumen **ohne Rückfrage Phase für Phase durcharbeiten**.

## ✅ Stehende Freigaben des Nutzers (gilt für die ganze Abarbeitung)
- **Autonom** Stück für Stück abarbeiten, **ohne jedes Mal nachzufragen**.
- **Token-kostende KI-Recherche/Suche** darf bei Bedarf ausgelöst werden.
- **Neustart von :8137** darf veranlasst werden (Worker per **PID ohne `/T`** → 25 Bots überleben; danach `running 25/25` prüfen).
- **Kein Echtgeld**, Demo/Paper bleibt. **25/25 durchgehend halten.**
- Feel-/Look-kritische Punkte (Wobble G, Legende E, ROI-Grafik D1, Block 3 F) bestmöglich umsetzen — finaler
  Feinschliff/Feel wird vom Nutzer später im echten Browser beurteilt.

## 🔁 Protokoll je Schritt (immer gleich)
1. Editieren in `…\Trading Bot eins\programm` (Frontend = `backend/app/static/index.html`; Backend = `backend/app/*.py`).
2. `cp` nach `…\trading-bot-trial` (Spiegel identisch halten).
3. Verifizieren: Frontend = **served-fresh :8137** bzw. :8139-Preview (`preview_*`, Konsole fehlerfrei, Screenshot).
   Backend-`.py` → :8137 neu (PID ohne /T) → `GET /api/summary` running 25/25.
4. **Committen** (kleine, thematische Commits). Nach jeder Phase: `git status` clean, `trial==source`.
5. Bei Backend-Logik: betroffene `pytest` grün halten (`…\trial\.venv\Scripts\python.exe -m pytest "…\programm\tests" -q`, Soll 38).

---

## Phase 0 — Einstieg & Bestandsaufnahme
- `STATUS_HANDOFF_DESIGN.md` + Mem („Stand"/„Gotchas") + diesen Plan + den Backlog lesen.
- Prüfen: :8137 running **25/25**, `git status` clean, **38 pytest** grün.

## Phase 1 — Bug & Automatik (Backlog A) · *Backend → 1 Neustart*
1. **A1** Katalog „direkt anlegbar" reagiert nicht → Ursache finden (`createFromCatalog`/`activateStrategy`,
   Konsole/`/api/bots`-POST), Fix + **klare Fehlermeldung statt stummem Klick**.
2. **A2** CSM „Daten aktualisieren" → **Auto-Refresh** (read-only, 0 Token/0 Orders), manueller Button optional.
3. Neustart :8137, 25/25, committen.

## Phase 2 — Daten-Fundament für Transparenz & Versionen (Backlog B1 + C2 Backend) · *Backend → 1 Neustart*
1. **B1-Backend** Mapping **Strategie/Template → Bot(s)** bereitstellen (aus Bot-Configs/Registry; ggf. `/api/...`-Feld).
2. **C2-Backend** **Versionierungs-Datenmodell**: beim Anwenden einer Verbesserung neue Version + „angewendet"-Marker
   am Bot/Strategie (an `optimizations`/`opt_params`/`master`-Fitness-Historie andocken). Fundament für C1/C3/C4.
3. pytest erweitern/grün, Neustart, 25/25, committen.

## Phase 3 — Strategie-Transparenz (Backlog B) · *Frontend served-fresh*
1. **B2** **Tabellarische Strategie-Übersicht** (sortierbar, Tooltips) + **Confidence „niedrig" erklären** + Kennzahlen-Legende.
2. **B1-Frontend** „läuft auf Bot #NN" je System; **Mehrfach-Anlage** mit klarer Zuordnung (neuer Bot = #NN).
3. **B3** „Merken" sichtbar erklären.
4. **B4** **Recherche-Modifikator** (Freitext-Schwerpunkt, an Recherche-Prompt; Token-Hinweis) + ggf. Presets.

## Phase 4 — Verbesserungs-/Versions-Management UI (Backlog C) · *Frontend*
1. **C1** „**Anwendbare Verbesserung verfügbar**" prominent anzeigen.
2. **C3** **Changelog-Panel** (welche Verbesserung → welche Version, Vorher/Nachher).
3. **C4** **Upgrade-Symbol** überall: Bots-Reiter, Statistik je Bot, Strategieanzeige.

## Phase 5 — UI-Struktur & Verständlichkeit (Backlog D) · *Frontend*
1. **D6** „ausklappen"-Texte programmweit raus (Klappbalken signalisieren selbst).
2. **D9** Highlights **fest angepinnt, kompakt** (statt `<details>`).
3. **D8** KPI-Kacheln kompakt + **Hover-Detail-Popover** (z. B. Gewinner #1 → Hover Top 10).
4. **D4** **Konto/Wallet** als Unterpunkt in „Echtgeld-Verwaltung & Transfer".
5. **D5** Große Ausklapplisten **kategorisieren** (z. B. „Echtgeld-Reife je Demo-Bot" je System).
6. **D2** **Button-Tooltip-System** programmweit (strukturierte Hover-Erklärung; „Trainingsschritt" etc.).
7. **D3** **Token-Hinweis** am Recherche-Button (Bezug B4).
8. **D1** **Trade-Details ausbauen** + **aufwändige ROI-Grafik** (Gradient-Fläche, Glow, Zonen, Marker, Drawdown-Band).
9. **D10** **Desktop-/Favicon** neu im Neon-Synthwave-Stil (SVG + .ico/PNG, `<link rel=icon>`, ggf. Manifest).
10. **D7** Icons **noch größer** (Maximum ohne Layout-Bruch) — iterativ; final mit Phase 7 abstimmen.

## Phase 6 — Motion/Spiel (Backlog E + G) · *Frontend, Feel später vom Nutzer*
1. **E** Icon-Legende als **frei schwebendes Bounce-Spielelement**: Momentum, Abprall an Panels/Rändern,
   **Screen-Wrap**, langsame Reibung → Ruhe-Schweben; **ODER** dauerhaftes randomisiertes Auto-Drift bis Anstupsen.
   Eigene RAF-Physik, **getrennt** von der Honig-Mechanik. `prefers-reduced-motion` beachten, Lesbarkeit/Hover wahren.
2. **G** **Wobble-Honig verfeinern**: viel zähflüssiger (`HONEY.lag`↓), mehr/weiter reichende Bewegung,
   **viele Bewegungsachsen** (Skew/Scherung, **per-Ecke unabhängige First-Order-Lags**, leichte Torsion) —
   weiterhin überschwingfrei (kein Bounce). Konstanten zentral in `HONEY{}`.

## Phase 7 — Block 3: Design-Harmonie (Backlog F) · *zuletzt, mit Internetrecherche*
- Fonts/Farben/Abstände/Icon-Formen (Hirn/DNA/Satellit/Besen nachschärfen), Glow/Größe (D7 final), Legende-Layout —
  **alles aufs Synthwave-Neon-Glas-Theme vereinheitlichen**. Web-Recherche zu Webdesign/Konsistenz.

## Phase 8 — Abschluss: Systemanalyse & Cleanup
- **Funktion:** 25/25, alle neuen Endpunkte/Buttons getestet, Konsole fehlerfrei; **pytest grün**; `trial==source`; git clean.
- **Code-Hygiene:** `index.html` ist sehr groß geworden → prüfen, ob **CSS/JS-Auslagerung** (separate Dateien) sinnvoll;
  tote Stellen/Dubletten entfernen; Icon-Sprite/Helper konsolidiert; Namensgebung konsistent.
- **Struktur:** Dateien/Ordner sinnvoll angeordnet, Doku stimmig.
- **Doku/Mem:** `STATUS_HANDOFF_DESIGN.md` + Mem-Notizen aktualisieren, Backlog-Punkte abhaken, neuen HEAD eintragen.

---

### Reihenfolge-Logik (kurz)
Bug zuerst (A) → Backend-Fundament gebündelt (B1/C2, 1 Neustart) → darauf aufbauend Transparenz (B) und
Versions-UI (C) → breite UI-Verständlichkeit/Struktur (D) → Motion-Spielereien (E/G) → globaler Design-Pass (F) →
Abschluss-Analyse. Backend-Änderungen früh bündeln (wenige Neustarts), Frontend-Masse served-fresh, Feel-Punkte
gegen Ende (Nutzer urteilt im Browser).
