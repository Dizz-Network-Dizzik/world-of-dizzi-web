# Design-System „Mattglanz-Metall" (v2)

> **Dashboard-Anzeige-Schema (v3-Plan, 11.06.2026):** Nur die **obersten zwei Panels** werden
> in voller Detail-/App-Ansicht gezeigt; **alle übrigen als kompakte Übersichts-Kacheln**
> (Größe wie die „in Planung"-Kacheln). Per Drag schiebt der Nutzer die zwei gewünschten Panels
> nach oben → Position = Detailtiefe. Reihenfolge bleibt `panel_order` (user-scoped).
> Umsetzung steht aus (Bau-KI). Details: Systemübersicht §3.

> **v2 (10.06.2026, nach Nutzer-Sichtung):** v1 war dem Nutzer zu farblos. Korrektur:
> Metall bleibt die Bühne, aber **Cyan/Magenta sind die Hauptdarsteller** — deutlich
> farbiger, **Glow ausdrücklich erlaubt**, verspielt-angelehnt ans Trading-Bot-Neon,
> durch die Matt-Metallic-Optik aber edler. Konkret umgesetzt:
> Satin-Chrom-Titel mit Cyan-Glow + Magenta-Untertitel · Cyan→Magenta-Leuchtlinie
> unterm Kopf · jede Kachel mit leuchtender Akzentkante, Icons abwechselnd Cyan/Magenta
> mit Glow, Hover = Doppel-Glow (Cyan+Magenta) · Status-Pills farbig (Magenta „in Planung",
> Grün-Glow „aktiv") · **Hintergrund: wandernde Aurora (Cyan/Magenta) + mattes
> Synthwave-Perspektiv-Raster** am Boden · **Panels mittig in 2 Spalten** (860px-Achse) ·
> **Karten per Drag verschiebbar** (einfache Mechanik, Reihenfolge wird user-scoped als
> Setting `panel_order` im Core gespeichert) · `prefers-reduced-motion` respektiert.
> Die v1-Regel „Akzentfarbe ist Licht, nicht Lack" gilt weiter — nur ist das Licht jetzt heller.

> **★ TOKEN-LADEN VEREINHEITLICHT (19.06.2026, World-Chat):** Alle 10 Vanilla-Apps laden die
> Design-Tokens jetzt EINHEITLICH per `<link rel="stylesheet" href="/ui-kit/tokens.css">`
> (render-blocking im `<head>`; der Anti-FOUC-Inline-`<script>` setzt `data-design/-farbe`
> vorab aus localStorage). Das frühere Inline-`<style>`-Token-Modell (news/finanzen/
> kommunikation/buerokratie/creator) ist damit **aufgelöst** — ein Token-WERT-Change ist
> jetzt **nur** „Master `shared/dizz-tokens.css` ändern + vendoren" (genau wie die übrigen
> 6 Kit-Dateien), kein Per-App-Edit mehr. Der Master wurde um die globalen semantischen
> RGB-Tripel **`--warn-rgb`/`--bad-rgb`** ergänzt (Werte = exakt die `--warn`/`--bad`-Hex;
> `--ok-rgb` war schon da) — nötig, weil finanzen/komm sie nutzten. creator-Drift
> (`--control-bg` = `--bg-deep` → kanonisch `--panel-solid`; fehlende `--txt`/`--panel-solid`)
> dabei auf kanonisch gezogen (Eingabefeld minimal heller — Feel-Check). Alle 12 `tokens.css`
> (Master + refapp + 10 Apps) byte-identisch (md5 `9fb8ba08`).

---

## Historie: v1-Herleitung (Ausgangspunkt, 10.06. früher)

> Abgeleitet aus der Design-Studie am Trading-Bot-Frontend (10.06.2026).
> Vorgabe des Nutzers: Designsprache des Trading Bot spiegeln, aber Grundmuster
> **Neon → Mattglanz-Metall**; Farbstimmung **Cyan/Magenta bleibt**.

## 1. Befund der Studie (Trading Bot, `backend/app/static/index.html`)

Theme „Retro-Chrome Arcade (Synthwave/Y2K)":

| Token | Wert | Rolle |
|---|---|---|
| `--bg` | `#070611` | Hintergrund (violett-schwarz) |
| `--acc` | `#2fe7ff` | **Cyan** (Primär-Akzent) |
| `--acc2` | `#ff3df0` | **Magenta** (Sekundär-Akzent) |
| `--ok` / `--warn` / `--bad` | `#3dffb0` / `#ffd23d` / `#ff5470` | Statusfarben |
| `--fg` / `--mut` | `#eef0ff` / `#9f93c6` | Text / gedämpft |
| `--panel(2)` | rgba-Violett-Glas | Panel-Flächen, Glassmorphism |
| `--chrome` | mehrstufiger Metall-Gradient | poliertes Chrom (Bevels/Typo) — **die Brücke zu uns!** |
| Fonts | **Orbitron** (Display) + **Chakra Petch** (UI) | Schrift-Rollen |
| Wirkung | starker Glow (`box-shadow`-Neon), Glas, Grid-Linien cyan/magenta | „Neon" |

## 2. Übersetzung Neon → Mattglanz-Metall

Grundidee: **gleiche Familie, andere Oberfläche.** Der Trading Bot ist die Neon-Spielhalle;
the world of dizzi ist der **gebürstete Titan-Kommandostand** derselben Welt.

| Aspekt | Trading Bot (Neon) | the world of dizzi (Mattglanz-Metall) |
|---|---|---|
| Hintergrund | Violett-Schwarz `#070611` | **Graphit-Anthrazit** `#0c0e12` (neutraler, metallischer, kein Violettstich) |
| Flächen | Glas (durchscheinend, violett) | **Gebürstetes Metall**: satinierte Gradients `#161a21→#1d232c`, feine horizontale Brush-Textur, KEINE Transparenz-Spielerei |
| Akzente | Cyan `#2fe7ff` + Magenta `#ff3df0`, breit eingesetzt | **DIESELBEN Farbwerte**, aber dosierter: Cyan = Interaktion/Aktiv, Magenta = Hervorhebung/Alarm-Akzent; auf Metall wirken sie wie beleuchtete Instrumenten-Markierungen |
| Glow | starker Neon-Schein um Elemente | **fast kein Glow**; stattdessen *Kanten-Licht*: 1px helle Ober-Kante + dunkle Unter-Kante (gefrästes Metall), Akzentfarbe nur als schmale Leucht-Linie (z. B. 2px Unterstrich, Pill-Rand) |
| Chrom | `--chrome` poliert, spiegelnd | **Satin-Variante**: gleicher Gradient-Aufbau, aber flachere Kontraste `#d7dce6→#8b93a6→#c4cad8` = matt gebürstet |
| Statusfarben | ok/warn/bad | **identisch übernehmen** (`#3dffb0`/`#ffd23d`/`#ff5470`) — Wiedererkennung über die Produktfamilie |
| Typo | Orbitron + Chakra Petch | **identisch übernehmen** (Familien-Klammer); Orbitron sparsamer (nur H1/Panel-Titel/Großwerte), tabular-nums für Zahlen |
| Bewegung | verspielt (Wobble, Schleuder) | **ruhig & präzise**: kurze, gedämpfte Übergänge (120–180 ms ease-out), keine Spiel-Physik im Grundgerüst (Verspieltes später als bewusste Einzelstücke) |

## 3. Token-Entwurf (CSS Custom Properties, Basis für Phase 1)

```css
:root { /* world of dizzi — Mattglanz-Metall v1 */
  --bg:#0c0e12;            /* Graphit */
  --bg-deep:#08090c;
  --metal:linear-gradient(180deg,#1d232c 0%,#161a21 55%,#12151b 100%);
  --metal-edge-top:rgba(255,255,255,.07);   /* gefräste Oberkante */
  --metal-edge-bot:rgba(0,0,0,.55);         /* Schattenkante */
  --brush:repeating-linear-gradient(180deg,rgba(255,255,255,.012) 0 1px,transparent 1px 3px);
  --satin:linear-gradient(180deg,#d7dce6 0%,#9aa2b4 38%,#8b93a6 52%,#c4cad8 100%);
  --fg:#e8ecf4; --mut:#8d96a8;
  --cy:#2fe7ff;  /* Cyan — Interaktion/Aktiv   (vom Trading Bot) */
  --mg:#ff3df0;  /* Magenta — Hervorhebung      (vom Trading Bot) */
  --ok:#3dffb0; --warn:#ffd23d; --bad:#ff5470;  /* identisch */
  --line:rgba(141,150,168,.16);
  --r:14px;
  --sh:0 10px 28px -14px rgba(0,0,0,.8);   /* Tiefe statt Glow */
  --t:140ms ease-out;                       /* Bewegungs-Disziplin */
}
```

Regeln:
1. **Akzentfarbe ist Licht, nicht Lack**: Cyan/Magenta nie als Flächenfüllung, nur als
   Linien, Indikatoren, aktive Zustände, Daten-Visualisierung.
2. **Jede Platte hat Kanten**: `--metal` + Ober-/Unterkante; Panels wirken gefräst, nicht geklebt.
3. **Hierarchie über Material**: wichtiger = hellere/satiniertere Fläche, nicht = mehr Glow.
4. **Dark only** in v1 (Settings-Anschluss für Themes vorbereitet, Grundgesetz 5).

## 4. Offen für Nutzer-Geschmack (nach erstem Sichtkontakt in M1)
- Brush-Textur sichtbarer/unsichtbarer
- Magenta-Anteil (aktuell bewusst sparsam geplant)
- Eck-Radien (14px = etwas technischer als Trading Bot 16px)

---

## 5. Marken-Lockup — Doppelname-Norm (K2.3, netzwerkweit) · 13.06.2026

> **Nutzer-Entscheid (docs/11 REV-7):** Jede App hat ihren eigenen Markennamen, aber der alte
> beschreibende Name soll NICHT verschwinden. Überall, wo eine App benannt wird, steht die
> **Marke betont vorne** und der **Funktionsname dezent dahinter** — damit jeder trotz Eigenmarke
> sofort weiß, welche App das ist. Diese Norm ist verbindlich für ALLE Flächen im Netzwerk.

### 5.1 Die Regel (Reihenfolge-Invariante)
**Marke zuerst (betont) · Funktion dahinter (gedämpft)** — nie umgekehrt, nie nur eins davon.

```
Dizz Money · Finanzmanagement
└──┬─────┘   └──────┬───────┘
 betont          dezent
```

### 5.2 Datenquelle — mappingsfrei, kein neues Feld
Die kanonischen Werte liegen **bereits im Vernetzungs-Manifest** (`appkit/manifest.py`):
- `manifest.brand` → die **Marke** (z. B. `"Dizz Money"`) = der betonte Name.
- `manifest.name`  → die **Funktion** (z. B. `"Finanzmanagement"`) = der dezente Name dahinter.

⇒ Dies ist eine **reine Render-Norm**: KEIN neues Vertragsfeld, KEINE appkit-Änderung
(Vertrag bleibt 1.5). Jede benennende Fläche liest `brand` + `name` aus dem Manifest/Summary
und rendert das Lockup — analog zur mappingsfreien Design-Achsen-Logik aus K2.2.

### 5.3 Visuelle Behandlung (tokenbasiert — passt sich K2.2-Themes an)
| Teil | Schrift | Größe | Farbe/Token | Glow |
|---|---|---|---|---|
| **Marke** (`brand`) | Display (Orbitron/Satin-Chrom) | volle Titelgröße | `--satin` / Akzent | Theme-Glow erlaubt |
| Funktion (`name`) | UI (Chakra Petch) | ~0.62–0.7× | `--mut` (gedämpft) | kein Glow |

- Trenner: Mittelpunkt `·` (oder dünner Bindestrich) bzw. zweite Zeile / Kicker — je Fläche, aber
  **konsistent je Flächentyp**. Keine hartkodierten Farben (K2.2-Token, Invariante §0c.4).
- Auf engem Raum (Tab-Chip, Monitor) darf die Funktion umbrechen oder per `title`/Tooltip wandern,
  **aber die Marke bleibt immer sichtbar und betont**.

### 5.4 Wo die Norm greift (alle benennenden Flächen)
1. **App-Frontend-Kopf** (H1-Titelblock jeder App).
2. **Browser-Tab** `<title>` = `"<brand> — <name>"` (z. B. `"Dizz Money — Finanzmanagement"`) —
   trägt beide Namen auch für Screenreader/`aria-label` und Tab-Unterscheidung.
3. **Core-Dashboard-Kachel** (`core/app/panels.py` + Shell): Kachel-Titel = Lockup.
4. **Desktop-Monitor** „Dizz Network" (`ops/monitor/monitor_app.cs`, verlegt 02.07.): Dienst-Chip = Lockup.
5. **Tauri-Fenstertitel** (später, sobald Desktop-Schale steht).

### 5.5 Kanonisches Mapping (Ist-Stand der Manifeste, 13.06.)
| App-ID | `brand` (betont) | `name` (dezent) |
|---|---|---|
| `finanzen` | **Dizz Money** | Finanzmanagement |
| `news` | **Dizz News** | News Compact |
| `kommunikation` | **Dizz Communication** | Nachrichtenverkehr |
| `creator` | **Dizz Creating** | Medien-Suite |
| `tradingbot` | **Dizz Trading** | Trading Bot |
| `musik` (🧊) | **Dizz Music** | Musik-Co-Produzent |
| Scaffolds (Memory/Admin/Plans/Management/Healthy/Leading) | „Dizz …" | beim Bau setzen |

> **Wording-Feinschliff** (z. B. „News Compact"→„Nachrichten") ist eine kleine App-Chat-Mikro-
> Aufgabe am `manifest.name` — die Norm rendert, was im Manifest steht, und ist davon entkoppelt.

### 5.6 Rollout-Disziplin
- **✅ Erste Referenz GEBAUT (13.06., Core-Dashboard-Kachel):** `PanelManifest.brand`
  (`core/app/panels.py`) + kanonische Seed-Marken + `.lockup`/`.fn` in `shell/PanelCard.tsx`
  + `theme.css`. Browser-verifiziert (alle 13 Kacheln, Computed-Style + Screenshot): Marke =
  Orbitron/Satin-Chrom/UPPERCASE, Funktion = Chakra Petch / `--mut` / kleiner. System-Panel
  ohne Marke zeigt nur den Namen (Fallback `brand ?? name`).
- **Offen (Assistenz-KI-tauglich** — Referenz existiert, Tests grün, keine Design-Entscheidung,
  nicht sicherheits-/geld-kritisch, G10): je **App-Frontend-Kopf** + Browser-**`<title>`** +
  **Desktop-Monitor**-Chip. Wording-Feinschliff je `manifest.name` = App-Chat-Mikro.
- Plan-/Stapel-Verankerung: docs/11 §5b REV-7 · Chat-Management §4 (K2.3).

---

## 6. K2.4 — UI-Controls & einklappbare Panels (netzwerkweit, übergreifend) · 13.06.2026

> **Nutzer-Befund:** Die Standard-Browser-Controls (Ankreuzkästchen, Auswahl-Listen, ▲/▼-Stepper)
> passen NICHT zum Mattglanz-Metall/Neon-Konzept, und große Panels sollen einklappbar sein. K2.4
> macht alle interaktiven Bedien-Elemente UND große Panels theme-konform — als tokenbasierte
> Komponenten-Schicht. **Gilt überall**, besonders im **Einstellungsfenster** (docs/19 §2b) und
> ausdrücklich **auch im Core/World-of-Dizzi (:8200)** — der Core ist selbst eine (system-
> verwaltende) App und trägt dieselbe Designsprache wie jede andere.

### 6.1 Grundsatz
Jedes native Default-Control wird durch eine **tokenbasierte Komponente** ersetzt, die die Material-
Logik der Panels erbt (`--metal`/Kanten/Satin + Cyan = aktiv / Magenta = Akzent). Native Zugänglichkeit
bleibt erhalten (echtes Input behalten, Tastatur/Focus/ARIA) — Recherche-Linie 2025/26: „Default-Element
behalten, nur die Optik via `appearance` ersetzen — **nie** `display:none`".

### 6.2 Control-Familie (Best-Practice-gestützt)
| Control | Technik | Optik (Token) |
|---|---|---|
| **Checkbox/Radio** | echtes `<input>` + `appearance:none`; Label umschließt (Trefferfläche); `:focus-visible`-Akzent-Ring; `prefers-reduced-motion` | gefräste Metall-Box/Kreis; `:checked` = Cyan-Füllung + Häkchen, leichter Glow |
| **Stepper / Zahlenfeld** (z. B. Seed-Wähler Creating) | `<input type=number>`, native Spinner aus, eigene **▲/▼-Knöpfe**; ↑/↓-Tastatur bleibt; aria | Satin-Chrom-Knöpfe im Look der Panel-Klapp-Knöpfe |
| **Select / Ausklapp-Liste** | **`appearance: base-select`** (Chromium/Opera GX ⇒ offene Liste voll stylebar: `::picker`/`::picker-icon`/`::checkmark`/`:open`); **Fallback** `appearance:none` + Token-Pfeil (Verkaufbarkeit) | Knopf wie Stepper; Liste = Metall-Fläche, Akzent-Hover, Cyan-Häkchen |
| **Toggle/Schalter** (optional) | Checkbox-Basis, als Schiebeschalter gerendert | Bahn Metall, Knauf Satin, an = Cyan |

### 6.3 Einklappbare Panels (Progressive Disclosure)
> **★ 04.07.2026 — Norm v2 GILT (docs/70 §3.3, aus UX-Audit docs/60 F-3; Gate G-UX-COLLAPSE ✅ David
> 04.07.):** ganzer Panel-Kopf klickbar + je App EINE Default-offene Kern-Sektion. Umgesetzt als
> **Opt-in-Attribute** (`data-dz-kopf-klick`/`data-dz-offen`) im Kit (collapse.js/controls.css); die
> **Glow-Disziplin unten bleibt vollständig** (Kopf bekommt KEINEN Hover-Glow, nur der Chevron leuchtet).
> Der Rollout setzt die Attribute je App im UX-2-Paket (docs/70 §7). Die 14.06.-Detail-Norm unten bleibt
> ansonsten gültig — nur „Kopf `cursor:default` / nur Chevron klappt" ist damit abgelöst.
- **Große Panels sind einklappbar** (Klapp-Kopf, `aria-expanded`, Tastatur, reduced-motion) — Optik =
  bestehende **Klappzeilen-/Spin-Knopf-Norm** (docs/14 v4.2, FOLDZONE 44px), nicht neu erfinden.
> **FINAL 14.06.2026 — am Probe-Muster `news/ui-kit/panel-probe.html` abgenommen + netzwerkweit
> ausgerollt (News·Money·Komm·Creating·Memory·Admin + Core; Trading folgt separat).** Die Punkte
> unten sind die verbindliche Norm; das Probe-HTML ist die lauffähige Kopier-Referenz.
- **Aufklapp-Toggle der GROSSEN Ober-Panels:** **1:1 das Trading-Bot-Muster.** Der **Panel-Kopf ist FLACH**
  (transparent, kein Solid-Knopf) und trägt nur Titel + Toggle. Der Toggle ist **LINKS, mittig**, ein
  **kleiner ~30px-Glas-Kasten mit dem accent-Pfeil DRIN** (▼ offen / ▶ zu), tokenbasiert
  (`rgba(var(--control-akzent-rgb),…)`, `.dz-chevron{order:-1}`). **Eingeklappt = Cyan (Akzent), OFFEN = Magenta.**
- **Der Toggle ist die EINZIGE Hover-Fläche des Panels (verbindlich):** **nur** `.dz-chevron` reagiert auf die
  Maus (`.dz-chevron:hover` → stärkerer Glow, im offenen Zustand magenta). Kopf, Körper, Karte reagieren **NIE**.
- **NUR der Toggle klappt:** `.dz-panel-kopf{cursor:default}`, `.dz-chevron{cursor:pointer}`; `collapse.js`
  togglet nur bei Klick auf den Chevron (Tastatur/`detail===0` weiter). Klick auf Titel/Rest klappt NICHT.
- **DREI Zustands-Glows — alle NUR im OFFENEN Zustand, KEINE Maus-Interaktion:**
  1. **Glühende Kopf-Leiste** (`.dz-panel-kopf::after`, Magenta→Cyan→transparent, `flex:1`): OFFEN = leuchtet,
     ZU = `display:none` (dann steht die Kurzanzeige).
  2. **KOPF-BOX** („Panel im Panel"): in Knopf-Höhe über die ganze Kopf-Breite ein dezent magenta-getöntes Feld
     mit 1px-Ring + Glow — `.dz-panel:not([data-dz-collapsed])>.dz-panel-kopf{background:rgba(var(--mg-rgb),.05);
     box-shadow:inset 0 0 0 1px rgba(var(--mg-rgb),.16),0 0 16px rgba(var(--mg-rgb),.10),inset 0 0 18px rgba(var(--cy-rgb),.04)}`.
     Ring als **inset-box-shadow** (kein border ⇒ kein Layout-Sprung); der Kopf trägt dafür IMMER
     `position:relative;border-radius:9px;padding:3px 7px 6px;transition`.
  3. **Toggle = Magenta** (Box + Pfeil), s. o.
- **LINKER AKZENT-STREIFEN (verbindlich, 1:1 TB `.panel::after`):** an **JEDER** Karte/jedem Panel ein
  **zweifarbiger Streifen am linken Rand** — oben **Magenta** → unten **Cyan**, 3px, `top/bottom:13px`,
  Magenta-Glow (`background:linear-gradient(180deg,var(--mg),var(--cy))`). **Statisch** (Panel-Identität,
  unabhängig vom Auf/Zu), **kein** Maus-Effekt. Umsetzung: `.card::before` umgewidmet (war die 2px-Top-Linie);
  Core = `.card .accent`; Memory = `.pane.dz-panel::before`.
- **KARTEN/PANELS GLÜHEN NIE BEIM HOVERN (verbindlich, FINAL — Wurzel der 14.06.-Iteration):** Es gibt
  **netzwerkweit KEINE `.card:hover`-Glow-Regel mehr** (DAS war der eigentliche Übeltäter: der generische Card-
  Außenglow ließ den ganzen Kopf beim Hovern aufleuchten und imitierte den „offen"-Marker — auch an nicht-
  klappbaren Karten wie „Konten"; das Zwischen-`.card:not(.dz-panel):hover` reichte NICHT, die Regel ist jetzt
  ganz raus). Eine Karte/ein Panel glüht **NUR (a) offen** (Kopf-Leiste + Kopf-Box) **und (b) beim GREIFEN/
  Schleudern** (`.spinlift` / Core `.dragging`). Sonst Ruhezustand. Einzige Hover-Reaktion: der Toggle-Knopf.
  - **⚠ ZWEITER Leck-Weg (Gotcha, 14.06.): der `.dz-panel-kopf` ist ein `<button>`** ⇒ die App-weite
    Regel **`button:hover{box-shadow:glow}`** leuchtet ihn beim Hovern auf (sieht aus wie die Kopf-Box).
    Weder `.card:hover` noch `.dz-chevron` ⇒ leicht zu übersehen. **Norm (controls.css):**
    `.dz-panel[data-dz-collapsed] > .dz-panel-kopf:hover{box-shadow:none}` (0,4,0 schlägt `button:hover`
    0,1,1; nur eingeklappt — OFFEN gewinnt die Kopf-Box 0,3,0 ohnehin). Inline-Apps separat mitziehen.
- **Bewegungsmechanik gehört dazu (verbindlich):** jedes Panel trägt die **Spin-Physik** (docs/14 v4.3,
  `spinfling.js` `initSpinFling`): greifen → schwingen → schleudern; **beim Greifen glüht das ganze Panel**
  (`.spinlift`); Loslassen über einem anderen Panel = **Platz-Tausch** (Reihenfolge in localStorage).
- **Unter-Ebene (kleinere, untergeordnete Klappsachen, z. B. `<details>` „… manuell anlegen", „vergangene
  Reports"):** dort **NUR ein kleines Dreieck** (~7px Chevron, gedämpft → Akzent bei offen/Hover), **KEIN**
  Glas-Kasten — der große Toggle ist **ausschließlich** für ganze Panels reserviert. Canonical: `details >
  summary.dz-fold/.dz-sub` (controls.css); bei Inline-`<details>` den Big-Box-Stil auf das kleine Dreieck umstellen.
- **Welche Panels werden einklappbar (Regel):** **die meisten größeren Ober-Panels** → einklappbares
  `.dz-panel` (großer Toggle); **wichtige** Panels zeigen eingeklappt zusätzlich eine **High-Level-Kurzanzeige**
  (`.dz-panel-kurz`). Kleine/untergeordnete Klappsachen bleiben kleine Dreiecke. Je App durchgehen.
- **⚠ Verteilungs-Gotcha (für jede künftige Panel-Änderung beachten!):** Die Apps binden die K2.4-CSS
  unterschiedlich ein. **Kanonisch ist `news/ui-kit/controls.css`** — von dort per Datei-KOPIE (gleicher
  MD5) an alle 7 Stellen: `news·archiv·finanzen·kommunikation·creator·buerokratie/ui-kit/controls.css` +
  `the world of dizzi/shell/src/controls.css`. **ABER der Runtime kommt nicht überall aus controls.css:**
  - **Gelinkt (controls.css greift sofort):** News, Money, Memory, Admin (`<link …/ui-kit/controls.css>`), Core-Shell.
  - **INLINE (eigener `<style>`-Block, separat mit-editieren!):** Communication + Creating.
  - **Skin-Overrides (höhere Spezifität, separat mitziehen!):** **Money** + **Creating** definieren
    `.card.dz-panel>.dz-panel-kopf{…}` selbst (Kopf-Box braucht dort `.card.dz-panel:not([data-dz-collapsed])>
    .dz-panel-kopf`, 0,4,0, um zu gewinnen). **Memory** nutzt **`.pane.dz-panel`** (Spalten statt Karten):
    Links-Streifen = `.pane.dz-panel::before`, Kopf-Box als Ring-Auflage (solider Spalten-Kopf bleibt).
  - **`.card`-Ebene ist IMMER App-lokal:** Links-Streifen (`.card::before`) + „kein `.card:hover`" + `.spinlift`
    leben in jeder App-`index.html` (controls.css besitzt `.card` nicht) ⇒ je App einzeln pflegen.
  (Stand 14.06. netzwerkweit ausgerollt + browser-verifiziert: News+Komm+Memory per Computed-Style.)
- **Wichtige Panels zeigen eingeklappt eine High-Level-Kurzanzeige** (Top-Schlagzeile/Kennzahl/Anzahl),
  automatisch aus den Panel-Daten bzw. `/api/summary`. Beispiele: News „Artikel" → Top-Schlagzeile +
  Anzahl; Money → Saldo; Creating → laufende Jobs.
- Knüpft an das vorhandene Core-Muster an (Dashboard: Top-2 detailliert + Rest 1-Zeilen-Summary) ⇒ K2.4
  verallgemeinert es als **Panel-Collapse-Norm** für ALLE App-Frontends + Core.

### 6.4 Token-Schicht (Komponenten-Ebene)
Neue **Komponenten-Tokens** (`--control-bg`/`--control-rand`/`--control-akzent`/`--control-haken`/
`--panel-kopf` …) zeigen NUR auf semantische Tokens (docs/_archiv/23 §3 Drei-Schichten-Vorschlag) ⇒ jedes der
10×10-Themes erbt die Controls automatisch, **null Komponenten-Änderung je Theme**. Heimat: Master
`shared/dizz-tokens.css` + neues **ui-kit-Bundle `controls.css` + `collapse.js`** (app-neutral, Single
Source — Apps referenzieren die Schicht, kopieren keine Werte; Token-Vertrag wie K2.2).

### 6.5 Geltungsbereich (übergreifend — vollständig)
1. **Alle App-Frontends** (News/Money/Komm/Creating + künftige Memory/…).
2. **Einstellungsfenster** (docs/19 §2b) — steckt voller Controls ⇒ Pflicht-Anwendung.
3. **Core / World-of-Dizzi (:8200)** — Dashboard-Panels (einklappbar + Kurzanzeige), DizziConsole,
   Settings-Modal; **und der Core bekommt auch den vollen K2.2-Theme-Switcher + K2.3-Lockup** (er ist
   eine App wie jede andere — bisher fixes Mattglanz-Theme; das wird angeglichen).

### 6.6 Rollout (wie K2.3)
- **✅ K2.4-(a) GEBAUT + browser-verifiziert (13.06.):** Komponenten-Tokens im Token-Master
  (`shared/dizz-tokens.css` + `news/ui-kit/tokens.css`) · **ui-kit-Bundle `news/ui-kit/controls.css`
  + `collapse.js`** (Checkbox/Radio/Toggle/Select[base-select+Fallback]/Stepper + einklappbare Panels
  mit Kurzanzeige) · lebende Referenz `news/ui-kit/controls-demo.html`. Verifiziert: Token-Vererbung
  über Themes (Metall+cyan ⇄ Neon+toxic), `appearance:base-select` aktiv, Collapse+`aria-expanded`,
  Stepper. **Das ist die Kopier-Referenz für alle Frontends + Core.**
- **✅ CORE-SHELL adoptiert (13.06., `fd3d632`):** Der Core (React) konsumiert jetzt den Token-Master
  + `controls.css` (vendierte Kopien `shell/src/dizz-tokens.css`/`controls.css`); `theme.css` aliasiert
  die Core-Altnamen (`--metal`→`--panel` …) ⇒ **voll 10×10** ohne Bruch (Default wertgleich). Zwei-Achsen-
  **Switcher im Einstellungs-Modal** (`FloatingSettings`, `.dz-select`), persistiert `design_vorlage`/
  `farb_schema` + localStorage-Anti-FOUC; `App.tsx` zieht den Server-Stand nach. Browser-verifiziert
  (voller Re-Theme kobalt+voltage). Damit hat der Core K2.2 + K2.4 (+ K2.3 in den Kacheln).
- **K2.4-(b) Rollout je App** (Controls + Collapse einsetzen) = **Assistenz-KI-tauglich** nach dieser Referenz.
  Offen klein im Core: restliche native Controls auf `.dz-*` + Panel-Collapse (Assistenz-KI).
- **Neue Frontends (z. B. Memory) bauen von Anfang an mit K2.4** — kein Default-Control mehr.
- Verankerung: docs/11 §5b REV-8 · docs/19 §2b · Chat-Management §3/§4.

### 6.7 Quellen (Recherche 13.06.)
Chrome for Developers / MDN „appearance: base-select" (Customizable `<select>`, Chrome/Edge 134, 03/2025) ·
moderncss.dev (Custom Radios/Checkboxes via `appearance:none`) · CSS-Tricks „Zero Trickery Custom Radios
and Checkboxes" · UXPin / IxDF „Progressive Disclosure" (2026) · Scott Loway „accessible number stepper".

---

## 7. Design-Katalog: `neon` = der „Dizz Trading"-Look (Nutzer-Wunsch 14.06.2026)

Der bestehende Trading-Bot-Look (Retro-Chrome-Arcade / Synthwave) ist als **erstklassige,
netzwerkweit wählbare Designoption** festgeschrieben — das **`neon`-Theme** im Token-Master.

- **Faithful (Werte 1:1 aus dem echten TB-Frontend** `Trading Bot eins/programm/backend/app/static/
  index.html` :root): `--bg #070611`, violettes Glas-Panel, **Chrom-Leiste** (`--satin` = TB `--chrome`),
  `--r 16px`, der TB-Schatten, `--blur blur(16px) saturate(1.15)`. ⇒ Wer auf **irgendeiner** App (oder
  dem Core) `data-design="neon"` wählt, bekommt die Trading-Bot-Optik — kombinierbar mit jedem der 10
  Farbschemata. Browser-verifiziert 14.06.
- **`neon`-extras (optionale Struktur-Schicht):** die *strukturelle* TB-Signatur — das bewegte Synthwave-
  **Scanline-Grid** (Tokens `--grid-a`/`--grid-b`), die **Verlaufs-Knöpfe** und der starke **Glow** — ist
  bewusst KEIN Kern-Token (der Token-Vertrag aus §… bleibt sauber/mappingsfrei), sondern eine kleine
  **opt-in CSS-Schicht**, die ein Frontend zusätzlich einbinden kann, wenn es unter `neon` den vollen
  Arcade-Vibe will. Das TB-Frontend hat sie schon; andere Apps können sie übernehmen.
- **Plan:** Der **TB-Switcher-Retrofit** (Bau-KI) hebt das TB-Frontend aufs Token-System und setzt **`neon`
  als TB-Default** ⇒ TB sieht aus wie jetzt, gewinnt aber den Umschalter (alle 10×10). Verankert: docs/11
  §5b REV-9 · Chat-Management §3 [TR]. Token-Master + `news/ui-kit`-Kopie + Core-Shell synchron (14.06.).
