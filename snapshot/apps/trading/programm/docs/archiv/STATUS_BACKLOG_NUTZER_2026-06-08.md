# 📋 Backlog — Nutzer-Wünsche (aufgenommen 08.06.2026, HEAD `477be34`)

> Konkrete Arbeitsbefehle für die **nächste Sitzung**. Demo/Paper, **kein Echtgeld**, **25/25 halten**.
> Arbeitsweise je Punkt: editieren in `…\Trading Bot eins\programm` → `cp` nach `…\trading-bot-trial` →
> **:8137 served-fresh** (Frontend) bzw. :8139-Preview verifizieren (Konsole fehlerfrei) → committen.
> Frontend = `backend/app/static/index.html`. Voraussetzung: erst `STATUS_HANDOFF_DESIGN.md` + Mem lesen.
> **Reihenfolge-Empfehlung:** A (Bug) → B (Transparenz) → C (Versions-Management, groß) → D (UI-Details) → E (Legende-Spiel) → F (Block 3 Design).

---

## ✅ FORTSCHRITT (autonomer Lauf, committet bis HEAD `351004f`)
**Erledigt & verifiziert (Frontend served-fresh, 25/25 gehalten, Konsole fehlerfrei):**
- **A1** ✅ Katalog-Anlegen repariert (entfernte `#b-name/#b-wallet/#b-cap` → Modal-eigene Felder `m-name`/`m-wallet`/`m-cap`;
  defensive Reads; Erfolgs-/Fehler-Toast). **Bonus:** `toast()` war app-weit nie definiert (ReferenceError) → Neon-Toast + CSS ergänzt.
- **A2** ✅ CSM-Daten Auto-Refresh (read-only, 0 Token, max. 1×/Tag, kein Loop) + „Jetzt aktualisieren"-Button.
- **B1** ✅ „läuft auf #NN"-Badges (Katalog/Engine-Karten), Modal-Hinweis + Erfolgs-Toast mit neuer #NN.
- **B2** ✅ (Teil) Confidence „niedrig" erklärt (Katalog-Kopf). *Offen: volle sortierbare Strategie-Tabelle.*
- **B3** ✅ „Merken" erklärt.
- **D3** ✅ Token-Hinweis am Recherche-Button (`.toktag`).
- **D6** ✅ „ausklappen"-Texte programmweit raus (0× im DOM).
- **D7** ✅ Icons größer (`.ic` 1.42em, `.sled` 1.5em) — Layout geprüft. *Kann in Block 3 final justiert werden.*
- **D10** ✅ Neon-Synthwave-Favicon (Inline-SVG-Data-URI).
- **D8** ✅ KPI-Kachel-Hover-Detail (Bester Bot → Hover Top-10, klickbar).
- **D9** ✅ Highlights als festes kompaktes Band (nicht mehr aufklappbar).
- **D4** ✅ Konto/Wallet in „Echtgeld-Verwaltung & Transfer" integriert (Panel 7→6).
- **D2** ✅ (Teil) Master „Ersten Trainingsschritt" erklärt. *Offen: Tooltip-System programmweit.*
- **C1+C4** ✅ „Upgrade verfügbar"-Badge in Bot-Zeilen (pulsierend, Klick=anwenden) + Bot-Detail-Hinweis + Katalog-Badge;
  angewendet = „Lern-Version aktiv" (C2-lite). Frontend aus `meta.optimizations`+`bot.opt_params`, kein Neustart.
- **D1** ✅ (Teil) aufwendigere **Equity-/ROI-Grafik** `richEquitySvg` (Gradient-Fläche, Glow-Linie, Start-Baseline,
  Min/Max/End-Marker) im Bot-Detail + CSM. *Offen: zusätzliche Trade-Detail-Spalten.*
- **G** ✅ Wobble-Honig **viel zähflüssiger + mehrachsig** (`honeyTick`: lag↓, Skew X+Y + Torsion, First-Order/kein Bounce).
  *Feel beurteilt der Nutzer im echten Browser.*
- **E** ✅ Icon-Legende als **frei schwebendes Bounce-Spielelement** (`initLegendFloat`: greifen+werfen/Momentum, Abprall
  Decke/Boden+Panels, Screen-Wrap, Reibung + Auto-Drift; reduced-motion=statisch). Physik verifiziert, *Feel im Browser.*
- **D2** ✅ **Globales Neon-Tooltip-System** — wertet alle `title=` programmweit zu gestylten Hover-Erklärungen auf (delegiert).
- **D5** ✅ „Echtgeld-Reife je Demo-Bot" **nach System gruppiert** (Muster für große Listen).
- **B4** ✅ **Recherche-Modifikator** — Freitext-Schwerpunkt (`#cat-focus`) fließt via `?focus=` mit hoher Priorität in
  den KI-Recherche-Prompt (`_research_with_ai`). Erster Backend-Lauf + :8137-Neustart (venv-Python!), 25/25.
- **C2+C3** ✅ **Versions-Nummern + Changelog** — `BotConfig.opt_version` (+1 je Upgrade), `apply_opt` versioniert+loggt;
  neue Tabelle `bot_upgrades` + `GET /api/upgrades`; Frontend „AI-optimiert vN"/„Lern-Version vN" + Panel
  „Verbesserungs-Historie (Changelog)". End-to-End live verifiziert (apply→v1→Changelog→reset→Basis), 25/25.
  → **Damit ist das komplette Verbesserungs-/Versions-Management (C1–C4) fertig.**

- **B2** ✅ Sortierbare **Strategie-Volltabelle** (`catalogTable`) oben im Katalog (Name/Markt/TF/Horizont/Regime/Vertrauen/läuft-auf/Status).
- **D1-Rest** ✅ Trade-Detail-Tabelle um **Dauer** + **Profit €** erweitert.

**F Design-Harmonie — laufend (iterativ, mit Nutzer-Look-Urteil):**
- ✅ **Legende-Verfeinerung:** Mini-Modus (nur Oberkategorien, `#lgMini`/`.mini`); **Schleuder-Physik** (Impuls-Ausstoß
  statt Teleport, Zentral-Schub beim Loslassen); **Spannungsaufbau-Glow** (`--charge` Cyan→Magenta, steigt zur Mitte).
- ✅ **Internetrecherche** (Orbitron=Display/Zahlen, Chakra Petch=UI, Glas/Neon, Zahlen-Ausrichtung, Kontrast 4.5:1).
- ✅ **Typo-Pass 1:** Font-Rollen waren bereits sauber (Orbitron Display / Chakra Petch UI) → tabular-nums auf
  Zahlen/Tabellen, App-Titel mehr Präsenz.
- ✅ **Neon-Pass 2:** Cyan/Magenta dominanter (Hintergrund-Orbs), **Schrift-Hierarchie nach Relevanz** (Tier1 Panel-Titel
  kräftiger Cyan-Neon → abnehmend bis Tier4 Zusatz ruhig), Icon-Glow ausbalancierter+mehr (Doppel-Glow).
- ✅ **Legende-Schleuder:** Wurfrichtung wird voll umgesetzt (links/rechts/wohin); ohne Richtung radial.
- ✅ **Aufklapp-Marker:** offene `<details>` mit linkem Neon-Balken + Tint + Glow + stärkerem Kopf-Icon-Glow.
- ✅ **Upgrade unübersehbar:** `.pill.upg` stark aufgewertet + prominenter `.upgbanner` + **„Verfügbare Verbesserungen"-Listing
  je Sektor** (Futures/Spot, „Alle upgraden") im Lern-Tab.
- ⏳ **Offen (braucht konkrete Nutzer-Richtung beim Browser-Review):** Schrift-Größen je Stelle feinjustieren,
  Icon-FORMEN nachschärfen (Hirn/DNA/Satellit/Besen — bewusst NICHT blind geändert, da subjektiv), weitere Glow-/Abstands-Feindosierung.
**Alles andere aus dem Backlog (A–E, G, C, D, B) ist erledigt.**

---

## A) BUG / Funktion — zuerst

### A1 — Katalog: „direkt anlegbar" reagiert nicht
- **Symptom (Nutzer):** Unter „Lauffähige Engine-Vorlagen — direkt anlegbar" Häkchen gesetzt, Knopf gedrückt → **nichts passiert**. Vermutung: Strategie/System läuft schon auf einem Bot.
- **TODO:** `createFromCatalog()` / `activateStrategy()` / `createFromTemplate` in `index.html` prüfen — wirft die Funktion still einen Fehler? (Konsole, fehlender `toast`, `validated`-Gate, `MODE`-Abhängigkeit, doppelte Tag/Name-Kollision?). Reproduzieren via :8139 + `preview_console_logs`. Backend `/api/bots` POST-Antwort prüfen.
- **Erwartung:** Entweder Bot wird angelegt **oder** klare Fehlermeldung (Toast/Inline) **warum nicht**. Kein stummer Klick.

### A2 — CSM „Daten aktualisieren" automatisieren
- **Symptom:** Im Cross-Sectional-Momentum-Panel (Lern-Bot) muss man „Daten aktualisieren" (`runCsmRefresh`) manuell drücken — unklar warum.
- **TODO:** Auto-Refresh einbauen (z. B. beim Panel-Öffnen + periodisch/täglich, read-only ccxt, 0 Token/0 Orders) **oder** klar beschriften, dass es bewusst manuell ist (warum). Nutzer-Präferenz: **automatisch**. Manuellen Button als optionalen „jetzt aktualisieren" behalten.

---

## B) Strategie-Transparenz & Verständlichkeit

### B1 — „Welche Strategie läuft schon in welchem Bot?"
- **TODO:** Im Katalog (und ggf. Strategie-Liste) je System anzeigen, **ob/auf welchen Bots** es bereits läuft (Bot-#NN-Tags verlinken). Mapping aus den Bot-Configs (`strategy`/`template` → Bot-Tag) ableiten.
- **Mehrfach-Anlage erlaubt:** Trotz vorhandener Zuweisung **zweiten Bot** mit demselben System anlegen können. Beim Anlegen klar zeigen: *„System X läuft bereits auf #07 — neuer Bot wird #NN"* (welche Nummer der neue bekommt, klare Zuordnung).

### B2 — Strategie-Daten tabellarisch & verständlich
- **Problem:** Beim Ausklappen „recherchierte Systeme" steht überall **„niedrig"** (Confidence) → wirkt unklar/unseriös; die zusammengefassten Kennzahlen versteht man nicht.
- **TODO:** Für **alle** Strategien eine **tabellarische Übersicht** (sortierbar, `SORTHEAD`-Muster) mit klaren Spalten + Tooltips: Name · Markt · Timeframe · Confidence (+ Erklärung was „niedrig/mittel/hoch" heißt + woher) · Eignung/Regime · Kernparameter · „läuft auf Bot(s)". Legende/Erklärtext für die Kennzahlen.
- **Confidence/Recherche-Qualität hinterfragt:** Erklären, **warum** fast alles „niedrig" ist (Self-Critique-Cap, dünne Belege) und das ehrlich einordnen (passt zum „nicht bankfähig"-Stand). Ggf. Confidence-Herleitung sichtbar machen.

### B3 — „Merken"-Funktion erklären
- **Problem:** Pin/„Merken" im Katalog unklar.
- **TODO:** Inline-Mikrocopy/Tooltip: „Merken = Strategie bleibt beim Katalog-Refresh erhalten (wird nicht als veraltet aussortiert)". Sichtbarer machen (nicht nur im title).

---

### B4 — Recherche-Tool: Modifikator / Schwerpunkt-Eingabe
- **Wunsch:** Vor dem Auslösen der KI-Recherche soll man die Suche per **Freitext-Eingabe** (Eingabeleiste, ggf.
  später Spracheingabe) **modifizieren / Schwerpunkte setzen** können. Beispiel: *„Markt sieht fundamental sehr
  negativ aus — suche vorrangig nach Systemen, die auf Short-Trades ausgelegt sind."*
- **TODO:** Eingabefeld am Recherche-Tool (neben „Recherche aktualisieren"); der Text wird als zusätzlicher
  Kontext/Direktive an den Recherche-Prompt gehängt (Backend `catalog`-Recherche). Bedenken: kostet Token (vgl. D3).
  Optional Presets (z. B. „Short-Fokus", „Range/Mean-Reversion", „hohe Volatilität"). Spracheingabe später.

## C) Verbesserungs- & Versions-Management (großes Feature)

### C1 — Anwendbare Verbesserungen sichtbar machen
- **TODO:** Wenn für eine Strategie/Bot Verbesserungs­vorschläge (gelernte Gewinner/Optimierungen) **bereitstehen**, prominent als **„Anwendbare Verbesserung verfügbar"** anzeigen (Badge/Karte), nicht versteckt im Lern-Tab.

### C2 — Versionierung beim Anwenden
- **TODO:** Beim Anwenden einer Verbesserung → **neue Version** der Strategie/des Bots erzeugen + deklarieren („ab hier Verbesserung angewendet → **v1**"). Der betroffene Bot wird **upgegradet** und fortan unter **neuem Versionsnamen** geführt; sichtbar markiert „Verbesserung angewendet".
- Backend: vermutlich an `optimizations`/`opt_params`/`master`-Versionierung andocken (Fitness-Verlauf existiert bereits).

### C3 — Changelog-Panel
- **TODO:** Eigenes Panel/Tabelle: **welche Verbesserung wurde wann in welche Version** übernommen — nachverfolgt + ausgewertet (vorher/nachher-Kennzahlen).

### C4 — Upgrade-Symbolik überall
- **TODO:** Bei den Strategien — **in den Bots, im Statistik-Fenster (je Bot) und in der Strategieanzeige** — ein **Symbol** (neues Neon-Icon, z. B. `ic-trend-up`/`ic-rocket`/eigenes „upgrade") wenn „Verbesserung möglich/verfügbar". Intuitiv: *„Strategie X: neue Version verfügbar → upgraden & testen"*.

---

## D) UI-Detail & Verständlichkeit

### D1 — Trade-Details ausbauen + ROI-Grafik aufwerten
- **Trade-Details (je Bot):** selbstständig sinnvolle **zusätzliche Trade-Details** ergänzen (z. B. Dauer, R-Multiple, MAE/MFE, Gebühren, Richtung, Exit-Grund, kumuliert).
- **ROI-Grafik:** aktuell zu simpel (dunkler Hintergrund + 1 Linie, `svg.roispark`). **Aufwendigere Grafik im Synthwave-Design** bauen: Gradient-Fläche unter der Kurve, Neon-Glow-Linie, Gewinn/Verlust-Zonen, Gridraster (schon da), Marker/Tooltips, evtl. Drawdown-Band. (Überschneidet sich mit Block 3.)

### D2 — Button-Tooltips programmweit (strukturierte Hover-Erklärung)
- **TODO:** **Alle** Buttons bekommen bei Hover eine **schön strukturierte Erklärung**, was genau passiert (nicht nur `title=`; eigenes Tooltip-System im Theme — Kasten mit Titel + Kurzbeschreibung).
- **Explizit genannt:** „Trainingsschritt"/`runMasterTrain` im Master-Algorithmus-Panel besser erklären. Auch „Recherche aktualisieren", „Backtest", „Analyse", „Verdichten", „Loop ausführen", Promote etc.

### D3 — Token-Hinweis am Recherche-Button
- **Problem:** „Recherche aktualisieren" löst echte KI-Recherche aus → **kostet Token**.
- **TODO:** Im Button visuell kennzeichnen, dass es **Token kostet** (z. B. kleines `ic-bolt`/Token-Icon + Tooltip „kostet API-Token"). Ggf. Bestätigungs-Hinweis.

### D4 — Konto/Wallet unter „Echtgeld-Verwaltung & Transfer" integrieren
- **TODO:** Das komplette **Konto/Wallet-Panel** (Bitget-Hauptkonto, read-only) als **Unterpunkt** in das Panel **„Echtgeld-Verwaltung & Transfer"** einklappbar integrieren (ein Echtgeld-Bereich statt zwei getrennte Panels).

### D5 — Große Ausklapplisten kategorisieren
- **Problem:** Sehr lange Ausklapplisten unübersichtlich. **Explizit:** „Echtgeld-Reife je Demo-Bot" (Lern-Bot) → unter **Kategorisierung je System** gruppieren.
- **TODO:** Generell bei allen großen Ausklapplisten Gruppierung/Kategorisierung (Handelsart/Markt/System) für besseren Überblick.

---

### D6 — „ausklappen"-Text aus Panel-Köpfen entfernen
- **Problem:** Auf einigen Panels steht noch „— ausklappen" / „ein-/ausklappen" (in verschiedenen Formulierungen).
  Redundant, seit die **farbigen Klappbalken vorne** das Auf-/Zuklappen selbst signalisieren.
- **TODO:** Alle „ausklappen"-Varianten aus den `<summary>`-Texten entfernen (programmweit), einheitlich.

### D7 — Icons noch deutlich größer
- **TODO:** Icon-Größe weiter anheben — **so groß wie möglich, ohne die Struktur/das Layout grundlegend zu brechen**
  (`.ic`/`.sled`/Legende). Iterativ im Browser prüfen.

### D8 — KPI-Kacheln: kompakt + Hover-Detail
- **Wunsch:** Die oben angezeigten Statistik-Kacheln (Registerkarten) **schön kompakt/klar** halten, aber bei **Hover**
  ein Detail-Popover mit mehr Infos zeigen.
- **Beispiel:** Gewinner-Kachel zeigt nur **#1**; bei Hover erscheinen die **Top 10**. Analog für andere Kacheln
  (mehr Kontext/Details im Hover-Fenster, Kachel selbst bleibt minimal). Eigenes Theme-Popover.

### D9 — Highlights kompakter & fest angepinnt
- **Wunsch:** Highlights **kleiner, fest angepinnt, NICHT aufklappbar** — kompakt oben, zeigt die **wichtigsten
  statistischen Kennzahlen auf einen Blick** + erwähnt **besondere Learnings/System-Hinweise**.
- **TODO:** Aus dem aufklappbaren `<details>` ein **festes, kompaktes Highlight-Band** machen (oben in der Statistik).

### D10 — Desktop-/App-Icon neu designen (Neon-Synthwave)
- **Wunsch:** Das **Desktop-Icon** (Favicon / App-/Tab-Icon) richtig geil **neonartig im Synthwave-Stil** mit den
  Theme-Farben (Cyan `--acc #2fe7ff` / Magenta `--acc2 #ff3df0`, Glas/Glow) neu gestalten.
- **TODO:** Eigenes Icon zeichnen (SVG, passend zum neuen `.ic`-Stil — z. B. Chart/Bolt/Bot-Motiv mit Neon-Glow,
  ggf. dunkler abgerundeter Hintergrund). Als `favicon.svg` + `favicon.ico`/PNG-Größen einbinden (`<link rel="icon">`
  in `index.html`), und falls PWA/Manifest vorhanden, dort die App-Icons mitliefern. Im Browser-Tab + als
  Desktop-Verknüpfung prüfen.

## E) Icon-Legende als frei schwebendes Spielelement (Physik)

- **Wunsch:** Die Icon-Legende final als **frei rechts im Raum schwebendes Spielelement**.
- **Physik (NICHT Honig — hier mit Bounce/Momentum):**
  - Packen & losschleudern → **behält Momentum** (Wurf-Geschwindigkeit).
  - **Prallt ab** von Panels, Decke, Boden, Bildschirmrändern.
  - **Screen-Wrap:** verlässt rechten Rand → kommt links wieder rein (und umgekehrt), kann dort wieder an Panels abprallen.
  - Verliert **langsam** Momentum (Reibung) → bleibt irgendwann an einem Ort **in der Schwebe** stehen.
  - **ODER** dauerhaftes **automatisches, randomisiertes Soft-Movement** (driftet frei umher), bis man es in eine Richtung **anstupst**.
- **Hinweis:** Eigene RAF-Physik (Velocity, Wand-/Panel-Kollision via getBoundingClientRect, Wrap-around, Friction). Klar getrennt von der Honig-Mechanik (`honeyTick`). Performance/`prefers-reduced-motion` beachten. Legende muss benutzbar bleiben (Hover stoppt Drift? Inhalt lesbar).

---

## G) Wobble-Honig — Verfeinerung (Folge von (0))

- **Wunsch:** Die Honig-Mechanik (`honeyTick`/`HONEY{}` in `index.html`) soll **viel zähflüssiger** werden,
  **mehr/weitere Bewegung** zeigen und **viele Bewegungsachsen** der Panels bekommen.
- **TODO:**
  - **Viskosität rauf:** `HONEY.lag`/`lagSettle` deutlich kleiner (träger, längeres Nachfließen) — aber weiter
    First-Order (KEIN Bounce). Ggf. Lag distanz-/geschwindigkeitsabhängig (mehr „Ziehen" = mehr Zerfließen).
  - **Mehr Bewegung:** stärkerer/weiter reichender Stretch (`stretchK`/`stretchMax` hoch), ausgeprägteres
    Schwerkraft-Sacken, längeres träges Setzen.
  - **Viele Bewegungsachsen:** nicht nur 1 Stretch-Achse + Sag — zusätzlich **Scherung/Skew**, **per-Ecke
    unabhängiges Nachfließen** (alle 4 Ecken eigene First-Order-Lags), evtl. leichte Rotation/Torsion, sodass
    das Panel mehrachsig wie Honig verläuft. Weiterhin monoton/überschwingfrei (kein Gummi).
- **Feel beurteilt der Nutzer im echten Browser** (Preview pausiert RAF). Konstanten in `HONEY{}` zentral halten.

## F) Block 3 — Design-Harmonie (war ohnehin geplant, zuletzt)
- Internetrecherche Webdesign; **jede** Schriftart/Farbe/Abstände/Icons aufs Synthwave-Neon-Glas-Theme feinabstimmen.
- Icon-Formen nachschärfen (Hirn/DNA/Satellit/Besen), Glow/Größe final, Legende-Layout.
- Überschneidet sich mit D1 (ROI-Grafik) und der Reticle/Icon-Optik.

---

### Status zum Zeitpunkt der Aufnahme
- **(0) Wobble-Honig** ✅ (HEAD `0484b21`, Feel abgesegnet).
- **Block 2 Neon-Icons + Legende + Status-Reticle + Euro-Icon + größere Icons** ✅ (HEAD `477be34`).
- 25/25 live, git clean. UI-Code 0 Emoji.
