# 39 · UI-KIT-VEREINHEITLICHUNG + PANEL-TOOL v4 + KONNEKTIVITÄTS-VISION

> **Stand 21.06.2026 (World-Admin-Chat).** Großes Nutzer-Briefing nach dem WhatsApp-Konnektor-PoC.
> Dieses Dokument BÜNDELT die nächste Groß-Phase: **UI-Vereinheitlichung** (Kopf-Norm + greifbare
> Panels) · **Panel-Bautool v4** (alle neuen Elemente + Oberregister/Ebenen + überall deployen) ·
> **UI-Kit-Vollständigkeit** · die **Konnektivitäts-Vision** (festschreiben, später kommerziell ausbauen).
> Reihenfolge unten in §7. **Implementierung MIT Nutzer / gegated — dieser Eintrag ist der Plan.**

## 0 · Leitlinie (Nutzer-O-Ton, verbindlich)
- **Der App-Kopf ist netzwerkweit EIN Format** — wie bei **News / Creating / Communication**: Marken-Lockup
  (App-Name betont + Funktionsname dezent dahinter, K2.3) zentriert, rechts der **Auth-/Stufen-Status**
  (angemeldet · verifiziert · **hochsicher**-Symbol), darunter der **Akzent-Streifen** mit der Tagline
  (z. B. Creating: „Deals · Bild/Video/Musik · ein Erschaffensprozess"). Dieser Kopf wird **fest im UI-Kit
  verankert** und auf ALLE Apps gezogen.
- **Layout zentriert, nicht vollgepfropft** — Bildschirm nur so voll wie nötig.
- **Alles, was an Elementen entsteht, gehört ins UI-Kit** — auch für Funktionen, die eine App noch nicht
  hat: „die Oberfläche liegt schon bereit". Das Panel-Bautool muss ALLE Element-Arten kennen.
- **Finale Feinjustage** jeder App-UI passiert über das **Panel-Bautool** (mit Nutzer).
- **Konnektivität = Kernziel**, aber nach dieser UI-Phase weiter ausgebaut; Telegram als einfacher
  nächster Konnektor, Meta produktiv erst mit Business-Unterlagen (Gewerbe).

---

## 1 · WP-A — KOPF-NORM im UI-Kit (kanonischer App-Kopf)
**Ziel:** EIN Kopf-Element, das jede App identisch trägt; der Inhalt (Name, Tagline, Sensitivity) kommt
aus dem Manifest.
- **Spec (kanonische Quelle = `news` / `creator` / `kommunikation` Kopf):**
  - Zeile 1: **Marken-Lockup** (`brand` betont + `name` dezent, docs/06 §5 / K2.3), zentriert.
  - rechts: **Stufen-Indikator** `angemeldet · verifiziert · hochsicher` + **Hochsicher-Symbol**
    (für `sensitivity=hoechst`; Symbol ist bereits im Kit).
  - Zeile 2: **Akzent-Streifen** (zweifarbig Magenta→Cyan, TB-Muster) mit **Tagline** je App.
- **Umsetzung:** Kopf als Kit-Baustein in `shared/` (CSS + kleines Markup-/Render-Muster), vendort über
  `ops/sync_appkit.py`. Tokenbasiert, CSP-strikt (keine Inline-Handler).
- **Rollout auf abweichende Köpfe:** **Admin · Memory · Management · Health** (dort ist gerade eine
  divergente Kopf-Variante) → auf die Norm ziehen. Bei diesen Apps gleich die Seite **darunter**
  mit-aufräumen (zentrieren, entrümpeln), wo viel angefasst wird.
- **Trading Bot:** Kopf passt grob; **Hochsicher-Symbol ergänzen** + grober UI-Pass. Eigener TB-Schritt
  (TB-Repo, gegated) — Nutzer nennt das als einen der ersten gewünschten Schritte.

### 1b · WP-A — KANONISCHE KOPF-NORM (Spezifikation, 22.06.2026)
> Nutzer-Urteil 22.06.: **richtig = News · Communication · Money · Creating** · **falsch = Management ·
> Health · Memory · Admin**. Die richtige Form ist KEIN Sonder-Markup, sondern eine schlanke CSS-Struktur
> (aus `news/static/index.html` extrahiert) + der `header::after`-Akzentstreifen. Diese Form wird kanonisch
> ins shared Kit gehoben (zusammen mit der App-Shell-Glow-Promotion aus docs/_archiv/41) und auf die 4 falschen ausgerollt.

> **★ AUSGEROLLT 23.06.2026 (World-Admin-Chat, mit Nutzer §5d, Design-Richtung B „auch zentrieren"):**
> Die Kopf-Norm (`.dz-appkopf` + `.dz-kopf-brand/-sub/-spacer/-hochsicher` + Akzentstreifen, alles bereits
> kanonisch in `shared/controls.css`) ist auf **alle 4 abweichenden Apps** gezogen + die Seiten **zentriert
> statt vollgepfropft** (max-width-Zentrierung): **Memory** (archiv `57055f6`) · **Management** (social-media
> `d232acf`) · **Health** (`9c8215c`, inkl. 🛡 Hochsicher + kpibar) · **Admin** (`ed57f23`, Inhalt war via
> `.wrap` schon zentriert; Kopf voll-breit wie die Oberregister-Leisten). Je App per Screenshot/DOM verifiziert.
> **★ ALLE 8 KÖPFE auf der Kit-Klasse (23.06., Nutzer „alle 8" + Marken-Variante B = solid-cyan):** auch die 4
> „richtigen" Apps migriert — **News** (`df9a1e5`) · **Money** (finanzen `cbb916e`) · **Communication** (komm
> `d5e070f`, + Hochsicher-🛡 + 2 Pillen) · **Creating** (creator `20889b6`). Marke netzweit von satin → **solid-cyan**
> (`var(--cy)`, token-/schema-getrieben), inline-Kopf-Dubletten (`header`/`h1`/`.sub`/`.headline`) entfernt; je App
> per DOM/eval verifiziert, alle 8 Frontends 200. **GOTCHA gelernt:** `kommunikation` + `creator` **laden
> `controls.css` NICHT** (sie inlinen das Kit „1:1 aus controls.css") ⇒ der `.dz-appkopf`-Block ist dort **inline
> gespiegelt** (Quelle shared/controls.css, bei Kit-Änderung mitziehen) statt riskant global eingehängt. Echtes
> Single-Source dort = der größere **Kit→shared-De-Fork** (docs/33-Backlog), separater Schritt.
> **★ DESIGN-/GLOW-AUDIT 24.06. (Nutzer „echte Perfektion"):** sichtbar netzweit konsistent + **live verifiziert**
> (Kopf, Panels, alle Glows, der Streifen-beim-Ausklappen `.dz-panel-kopf::after`, Chevron, Typografie). Umgesetzt:
> **Admin-Nav-Glows → Kit-Klassen** `.dz-navtab`/`.dz-berchip` (`admin 2864748`, inline-Glow raus); **Panel-Titel
> kanonisch Orbitron-uppercase netzweit** (Kit `.dz-panel-titel`, `world 899fc8f` + re-vendort; komm satin→Orbitron
> `db4ea4d`, creator schon Orbitron). **Bewusst AUFGESCHOBEN (risikoreich + unsichtbar):** `komm`/`creator` vom
> Inline-Kit auf `controls.css` **de-forken** (≈80 Z. minifiziertes CSS in CSP-strikten Live-Apps entfernen — nach
> Titel-Sync ist ihr Inline-Kit eine getreue Kopie, also 0 sichtbarer Gewinn) + `.card::before`-Akzentstreifen ins
> Kit zentralisieren. ⇒ als „Kit→shared-De-Fork" (docs/33) für einen eigenen, sorgfältig verifizierten Durchgang.

> **★ KIT→SHARED DE-FORK — (A) ✅ UMGESETZT + verifiziert 24.06.2026 (World-Admin-Chat):** **komm `9636fc5`** +
> **creator `07b650b`** laden jetzt `/ui-kit/controls.css` (`<link>` im `<head>` VOR dem inline `<style>` ⇒ App-Regeln
> gewinnen Gleichstand). Ihr inline-gespiegeltes Kit wurde chirurgisch ENTFERNT (komm −80 Z., creator −83 Z.:
> dz-check/-toggle/-select/-stepper/-panel/-kopf/-chevron/-titel/-kurz + @media reduced-motion), **nur App-Eigenheiten
> behalten**: komm = `.card.dz-panel{padding:8px}` + `.dz-panel-koerper`-`.4em`-Seitenrand (Kit=`.2em`) + komm-eigener
> `.dz-chip`(.mg/.done) mit gepinntem `white-space:normal` (Kit-Chip setzt `nowrap`); creator = Karten-Panel-Skin,
> **Satin-Gradient-Titel** (`background:var(--satin)`-clip, NICHT der solide Kit-Titel) + Padding-Resets
> `.dz-check/-toggle>input{padding:0}`/`.dz-stepper>button` + stale `.dz-panel-titel{font-weight:700}`-Dublette raus.
> **Verifikation (preview_eval über komm-proxy:8418/creator-proxy:8424, transitions-disabled, Panel offen+zu, Chips
> injiziert):** computed-styles Vorher==Nachher = **NULL Regression** auf .dz-check/-select/-stepper/-panel-kopf/
> -chevron(::before)/-panel-titel/-appkopf/KOPF-BOX/-panel-koerper/-chip(.mg/.done); `controls.css` HTTP 200; 0
> Konsolenfehler; 6 komm-Panels intakt. **md5 controls.css = Master byte-gleich über alle 8 Apps (0 Drift; (A) ändert
> controls.css NICHT, nur das Laden).** KEIN Push.
>
> **★ (B) `.card::before` ✅ ZENTRALISIERT 24.06. (Nutzer-Wahl: Kanon = V2) — Vorbedingung „identisch" war VERLETZT, daher erst kanonisiert:**
> Die Annahme „token-getrieben identisch" traf NICHT zu. grep über alle App-`index.html` zeigte **zwei divergente
> Varianten**: **V1** (news · kommunikation · creator · finanzen + buerokratie) = `box-shadow 0 0 12px rgba(--mg-rgb,.55);
> opacity:.9` (kein z-index/pointer-events); **V2** (health · admin · social-media + projekte + refapp-Template) =
> `box-shadow …,.5; z-index:2; pointer-events:none` (kein opacity). Dazu App-Erweiterungen (admin `.card.acc::before`,
> finanzen `#view-register .card::before{opacity:.85}`); **archiv (Memory) hat GAR KEIN `.card`/`.card::before`** (eigenes
> Karten-Modell). Eine EINZIGE Kit-Regel hätte 3–4 Apps sichtbar verändert ⇒ Variante zuerst als **Nutzer-/§5d-Entscheid**
> vorgelegt; **Nutzer wählte V2** (`.5`-Glow + `z-index:2` + `pointer-events:none`, voll deckend — technisch sauberer).
> **Umgesetzt:** V2-`.card::before` als App-Shell-Block in `shared/controls.css`; inline-Basis aus allen **7** Apps raus
> (V1-Apps news/komm/creator/finanzen bewusst von `.55`/`opacity:.9` → V2 vereinheitlicht; V2-Apps health/admin/social-media
> 0 visuelle Änderung); controls.css **netzweit re-vendort (md5 = Master, 0 Drift)**. **App-lokal behalten:** admin
> `.card.acc::before` + `.bcard::before`/`.bcard:hover`, finanzen `#view-register .card::before{opacity:.85}`. archiv unberührt
> (kein `.card`); **buerokratie/projekte (abgewickelt) bleiben inline**; **refapp-Template ✅ nachgezogen 24.06.** (lädt Kit, inline `.card::before` raus, controls.css = Master, live V2-verifiziert). **Verifiziert
> (preview_eval Vorher/Nachher):** komm/creator/finanzen V1→V2 exakt (box-shadow `.5`, opacity voll, z-index 2, pointer-events
> none); finanzen-Register-Override = opacity 0.85 **erhalten**; admin/health unverändert V2; Streifen rendert, `controls.css`
> 200, 0 Konsolenfehler. **Commits:** news `c6b9d25` · finanzen `e7eb4a1` · komm `a8dde2f` · creator `1c41dc2` · health
> `9aa66ad` · social-media `4d7a06b` · admin `d63ff2c` · world (shared+docs). KEIN Push. Detail docs/_archiv/41 §5b.

**Kanonisches Markup (Kopf-Region):**
```html
<header class="dz-appkopf">
  <h1 class="dz-brand">dizz <appname></h1>
  <span class="dz-sub"><tagline></span>          <!-- z. B. „kuratierte Quellen · KI nur lokal" -->
  <span class="dz-kopf-spacer"></span>
  <span class="dz-hochsicher" title="Höchst sensibel — lokal-only">🛡</span>  <!-- NUR bei sensitivity=hoechst -->
  <span class="pill" data-dz-act="openKontoModal">…</span>   <!-- Auth/Stufen-Pille (Dizzi-ID) -->
</header>
```

**Umgesetzt in `shared/controls.css`** (universell von allen 8 Apps geladen — `netkit.css` ist NICHT überall vendort; daher dort statt netkit). Klassen kollisionssicher `dz-appkopf`/`dz-kopf-brand`/`dz-kopf-sub`/`dz-kopf-spacer`/`dz-kopf-hochsicher` + `.dz-navtab.on`/`.dz-berchip.on` (weil `summary.dz-sub` in controls.css schon belegt ist).
**Kanonisches CSS (= News-Regeln, tokenisiert):**
```css
.dz-appkopf{display:flex;align-items:baseline;gap:14px;padding:26px 0 10px;position:relative}
.dz-brand{margin:0;font-size:21px;font-weight:900;letter-spacing:.14em;text-transform:lowercase;
  color:var(--cy);filter:drop-shadow(0 0 14px rgba(var(--cy-rgb),.35))}
.dz-sub{color:var(--mg);font-size:11px;letter-spacing:.22em;text-transform:uppercase;
  text-shadow:0 0 12px rgba(var(--mg-rgb),.55)}
.dz-kopf-spacer{flex:1}
.dz-appkopf::after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;
  background:linear-gradient(90deg,var(--cy),var(--mg) 60%,transparent);
  box-shadow:0 0 12px rgba(var(--cy-rgb),.5),0 0 18px rgba(var(--mg-rgb),.25)}
.dz-hochsicher{color:var(--mg);font-size:13px;filter:drop-shadow(0 0 8px rgba(var(--mg-rgb),.6))}
```
(Die `.pill`-Auth-Optik liegt bereits in `controls.css`; nur Kopf-Lockup + Streifen + Hochsicher-Symbol sind neu im Kit.)

**Admin-Sonderfall (Oberregister):** Admin trägt UNTER dem Kopf die `.modulbar`/`.mtab` (Seiten) +
`.kontextbar`/`.berchip` (Bereichs-Filter). Die Kopf-Norm ersetzt NUR die Kopf-Region (über dem Oberregister);
die `.mtab.on`/`.berchip.on`-Aktiv-Glows wandern als **Kit-Variante** mit ins App-Shell-Kit (docs/_archiv/41 Befund B).

**Rollout-Checkliste je App (Management/Health/Memory/Admin):**
1. Kit-Block in `shared/netkit.css` (App-Shell) ergänzen, an alle 8 `ui-kit/netkit.css` vendoren (md5-0-Drift).
2. Je App die Kopf-Region in `static/index.html` auf das kanonische Markup ziehen (Marke/Tagline/Sensitivity je App).
3. **Browser-Verifikation auf Scratch-Port** (Live = disk-served, nicht stören): snapshot/eval, Kopf-Optik = News-deckungsgleich, Akzentstreifen rendert, Hochsicher-Symbol nur bei hoechst, 0 Konsolenfehler.
4. App-Tests grün (Frontend-Asserts), committen. **Erst nach Verifikation** — kein Blind-Edit an Live-Köpfen.
5. Inline-Shell-Glows der App durch die Kit-Klassen ersetzen (docs/_archiv/41 Abgleich-Checkliste: jedes glühende Element → genau eine Kit-Regel).

## 2 · WP-B — Admin: Kategorien als GREIFBARE Panels

> **★ UMGESETZT 23.06.2026 (admin `f13a075`, Nutzer „genau dasselbe überall, standard eingeklappt"):**
> Jedes Feld in JEDEM Modul ist jetzt ein **offizielles `.card.dz-panel`** mit Panel-Kopfzeile (Chevron-Toggle
> + Icon + Titel) + `.dz-panel-koerper`, `data-dz-collapsible`: **greifbar/schwingbar/tauschbar** (DizzSpin) +
> **klappbar** (collapse.js), **starten eingeklappt** (Kit-Norm). `nachRender` ruft `DizzSpin.initSpinFling`
> (re-init-fest über Modul-Wechsel: `grid._spin`-Guard bindet den Listener 1×, Panels werden je Render neu
> entdeckt). **Reihenfolge-Persistenz PRO MODUL** (`spinfling.js`-Erweiterung: `storageKey` darf eine
> Funktion sein, je Speichern/Restore frisch ausgewertet ⇒ liest das aktive Modul trotz 1× gebundenem
> Listener; rückwärts-kompatibel, netzweit re-vendort 0 Drift). **Geschäft** 5 Felder · **Tresor/Projekte/Studium/Fristen**
> je 1 · **Übersicht** Querverbindungen/Unter-Bereiche/Modul-Übersicht (Bereichs-Identität bleibt Kopf-Card);
> a5-cockpit lädt dynamisch in den Panel-Körper (`renderA5Cockpit` ohne `card-koerper`-Wrapper). Verifiziert
> per DOM/eval, 0 Konsolenfehler. **Nutzer-Entscheidungen 23.06.:** alle Panels starten **eingeklappt** wie
> die Kit-Norm überall (kein Sonderfall offen); **Reihenfolge-Persistenz pro Modul** ✅ umgesetzt (s. o.).
**Befund:** Dizz Admins „großer Wurf"-Kategorien (Tresor/Projekte/Geschäft, das neue **Oberregister**-
Format) sind **keine offiziellen `dz-panel`** ⇒ man kann sie nicht greifen/bewegen/klappen.
- **Ziel:** Beim Klick in eine Kategorie echte **greif- & bewegbare Panels** sehen.
- Innerhalb der Kategorien **Collapse-Ebene-1** für Blöcke wie die **Netzwerkübersicht** (Klapp-Button).
- **Memory-Kopf** ebenfalls auf die Norm (siehe WP-A).

## 3 · WP-C — PANEL-BAUTOOL v4 (alle Element-Arten + Ebenen + Deploy)
**Befund (Tool-Audit 21.06., `tools/panel-builder.html`):** Palette hat `header` (nur fett),
`text/select/checkbox/radio/toggle/tabs/stepper/badge/progress/table/kpi/chart/icon`,
`subpanel` (Klapp-Rang 1/2/3) + DOM-Extraktor. **FEHLT:**
- **(a) Kanonischer App-Kopf** als eigenes Element (Marken-Lockup + Stufen + Streifen + Hochsicher).
- **(b) Oberregister / Register-Container** (Admins Tab-Ebene, die ganze Sektionen umschaltet) als
  **Struktur-Element mit Ebenen** — nicht nur die simple Inline-`tabs`-Leiste.
- **(c) Weitere neue Elemente** aus Apps seit v3: `gauge` (Readiness/Scores), `scatter` (Korrelation),
  `heatmap` (Posting-/Auslastungs-Zeiten), `ring`/Aktivitäts-Ringe (Health), `timeline`/Gantt,
  `cockpit`-Spalten (Admin-Querverbindungen), `metric-card`/Sparkline, `upload`, Verknüpfungs-Chip, Command-Palette.
- **(d) Ebenen einfügen** (Nutzer-Wunsch: Layer-Konzept fürs Register-/Tab-Format).
- **(e) Extraktor nachziehen** (`rawExtract`/`collect`), damit er Oberregister + die neuen Elemente erkennt.
- **Deploy:** Das v4-Tool ist Teil des Gesamt-Kits ⇒ **überall aktualisieren**. Kanonisch bleibt
  `the world of dizzi/tools/panel-builder.html`; je App liegt eine Kopie in `…/ui-kit/panel-builder.html`
  (für den 1-Klick-App-UI-Import). **Gotcha (Repo-Lock):** die Kopie in jede App-`ui-kit` macht der
  jeweilige App-Chat ODER der World-Chat, wenn das Repo frei ist — nie in ein belegtes App-Repo vendoren.
- **✅ STAND (21.06., World-Chat):** Kanonisches `tools/panel-builder.html` = **v4 GEBAUT + browser-verifiziert**
  (Preview :8450, 0 Konsolenfehler): Palette **7 Kategorien / 31 Elemente**; **App-Kopf**-Element
  (brand/funktion/tagline/stufe/hochsicher), **Oberregister/Ebenen**-Container (nestbar, Drag/Drop/Reorder/
  Delete über ein generisches `CONTAINER`-Konzept), neue Viz `gauge/scatter/ring/timeline/cockpit/metric`
  + `upload`/`cmdk`; Extraktor erweitert (`mk`/ELSEL/COMPOSITE + Seiten-Kopf/Register-Prepend) + Spec-Export
  (inkl. Ebenen-Nesting + docs/39-Norm-Hinweis) verifiziert. **OFFEN = Deploy:** Kopie der v4 in jede
  App-`ui-kit` (per-App, Repo-Lock) + optional `heatmap`/`waterfall` als eigene Viz-Elemente (heute via `chart`-ctype).
- **✅ v5 (21.06., World-Chat) — Bearbeitungs-UX überarbeitet + browser-verifiziert** (0 Konsolenfehler):
  Elemente in **Realgröße/kompakt** (kein Riesen-Inline-Editor mehr) · **Doppelklick → schwebendes
  Bearbeiten-Fenster** (Modal mit Live-Vorschau + „Was/Bearbeiten"-Hilfe + Feldern) · **Palette-Hover-Tooltip**
  je Element (Live-Vorschau + Erklärung + Parameter, inkl. Stil-Erklärung primary/ghost/danger/mini/icon) ·
  **Container** klarer (Knopf „+ hier hinein" + Aktiv-Highlight + Verschachtelung) · per-Element **Breite**
  (auto/schmal/halb/breit/voll) + optionale **Kurzbeschreibung daneben** · **echte Kopfzeile/Oberregister beim
  Import** (Extraktor übernimmt brand/funktion/tagline/stufe/hochsicher + Register-Tabs). **OFFEN (optional):**
  echtes Frei-Drag-Resize einzelner Elemente (heute Breite-Auswahl); heatmap/waterfall als eigene Elemente.
- **✅ v6 (21.06., World-Chat) — Struktur + Direkt-Manipulation + Probe** (browser-verifiziert, 0 Fehler):
  **App-Kopf/Oberregister = Seitenkopf-Zone** (eigene Top-Zone, NICHT mehr ins Panel anlegbar — Palette
  routet sie automatisch dorthin, eigener „Seitenkopf"-Badge) · **Einzelelemente per Ecke größen-ziehen**
  (`ew/eh`, live) zusätzlich zur Breite-Auswahl · **Hover mit In-Kontext-Vorschau** (Element im Mini-Panel-
  Rahmen) · **Extraktor auf echte App-Klassen getunt — Probe gegen Dizz Admin** (`header>.kopfzeile>.lockup
  .brand/.fn`, `nav.modulbar/.kontextbar`→Oberregister-Tabs, `.card`→Panels); Import legt den Seitenkopf
  full-width oben an. **OFFEN (nächster Schritt, Nutzer):** freies XY-Verschieben einzelner Elemente (heute
  Reorder via ⋮⋮ + Resize), Panel-Kopf-Notiz mit „schlau übersetzen", noch ausführlichere Hover-Texte.
- **✅ v7 (21.06., World-Chat) — WYSIWYG-Seitenkopf** (browser-verifiziert, 0 Fehler): Der **Seitenkopf
  wird direkt als finale Kopfzeile gerendert** — KEIN Tool-Panel-Rahmen / kein Klapp-Kopf / kein „Seitenkopf"-
  Badge mehr. `appkopf` zeigt Marken-Lockup (Marke + Funktion) + Akzent-Streifen (Magenta→Cyan) + Stufe-Badge
  + Hochsicher-Symbol genau wie im echten UI; `oberregister` = echte Tab-Leiste (erste Ebene aktiv). Doppelklick
  → Bearbeiten-Fenster bleibt; leerer Seitenkopf wird automatisch entfernt. **OFFEN (nächster Schritt, Nutzer-
  Wunsch „alles in finaler Optik"):** dieselbe WYSIWYG-Treue auf reguläre Panels/Elemente ausweiten (Chip-Rahmen
  nur bei Hover/Auswahl), freies XY-Verschieben einzelner Elemente, Panel-Kopf-Notiz mit „schlau übersetzen".
- **✅ v8 (21.06., World-Chat) — Organisches Anlegen + WYSIWYG-Tiefe** (browser-verifiziert, 0 Fehler):
  **„+ Element einfügen"-Auswahl-Dialog** — auf „+ hier hinein" / leeres Panel öffnet sich ein nach Kategorien
  gruppierter Chooser mit Live-Vorschau + Erklärung je Element, **kontext-kuratiert** (im Seitenkopf nur
  App-Kopf/Oberregister, sonst die Panel-Elemente) · **„＋ Neues Panel" in der Palette (Struktur & Ebenen)**
  statt in der Tool-Kopfleiste · **Panel-Doppelklick → Überschrift + Zweck-Beschreibung**, aus der das Tool per
  Stichwort **passende Elemente vorschlägt** (Umsatz→KPI/Chart, Liste→Tabelle, Frist→Timeline, Score→Gauge …;
  Klick fügt ein) + Zweck fließt in den „An die KI"-Export · **WYSIWYG-Optik:** Einzelelement-Rahmen nur bei
  Hover, Struktur-Container mit gestrichelten Linien (App-Kopf-Ästhetik). **OFFEN (nächster Schritt):** freies
  XY-Verschieben einzelner Elemente; faithful-ere Mini-Vorschauen für Box-Elemente (table/chart/gauge).
- **✅ v9 (21.06., World-Chat) — Probeblend-Vorschauen + leuchtende Vorschläge + Höhen-Resize** (browser-
  verifiziert, 0 Fehler): **echte Mini-Renders** in `pv()` für Tabelle (Zellen-Raster), Chart (Balken/Linie/
  Donut je ctype), Gauge (SVG-Bogen + Wert), Aktivitäts-Ringe, Fortschritt (Füllbalken), Metrik (Wert+Trend+
  Sparkline), Streudiagramm (Punkte), Zeitstrahl (Balken), Cockpit (Mini-Spalten) — sichtbar auf der Fläche,
  im Hover-„Probeblend" UND im Einfüge-Dialog · **leuchtende Vorschläge im Auswahl-Dialog** (Elemente, die zum
  Panel-Zweck passen, glühen + „★ passt zum Zweck") · **Höhen-Resize für ALLE Elemente** (Ecke zieht Breite
  UND Höhe). **OFFEN (v10 — der letzte große Baustein):** freies XY-Verschieben einzelner Elemente auf einem
  Panel-Raster, das nur beim Ziehen sichtbar wird.
- **✅ v10 (21.06., World-Chat) — WYSIWYG-Engine: freies Raster-Verschieben + 1:1-Elemente** (browser-
  verifiziert, 0 Fehler): Panel-Elemente sind **absolut auf einem Panel-Raster** (GCOLS 12 × GROWH 26) — **frei
  verschiebbar** (Ganzkörper-Drag, grid-snap) + **größen-ziehbar** (Ecke, Breite UND Höhe); das **Raster
  erscheint NUR während des Ziehens** · **keine ⋮⋮-Griffe mehr; jedes Element rendert 1:1 wie in der UI**
  (echter Knopf je Stil, Schieberegler mit Knubbel, Schalter-Pille, Checkbox/Radio, Dropdown, Stepper) ·
  **gestrichelte Rahmen** an Panels UND Elementen (= belegter Platz) · **Einfach-Klick wählt aus** (solider
  Rahmen), **Doppelklick** = Detail-Fenster · **Kopfzeile = Panel-Kopf** (Auswahl „Kopfzeile" öffnet den
  Panel-Kopf-Editor statt eines freien Elements) · Beschreibung wahlweise **unter** dem Element · größeres
  Hover-Fenster. **OFFEN (nächste Runde):** Raster auch in Unterpanels/Containern; **Verknüpfungen/Aktionen**
  (Knopf → öffnet Fenster/Panel); noch ausführlichere Hover-Parametertexte.
- **✅ v11 (21.06., World-Chat) — Element-Skalierung + neue Elemente + Recherche/App-Durchlauf** (browser-
  verifiziert, 0 Fehler): **Skalierungs-Bug behoben** — das Element selbst füllt jetzt seine Box (SVG-Charts/
  Gauge/Ring/Scatter `width/height:100%`, Zeitstrahl/Fortschritt/Bar-Chart füllen Breite+Höhe; Chart-SVG
  94→250px beim Höherziehen verifiziert) · **neue Element-Arten** aus dem App-Durchlauf: **Liste, Kanban-Board,
  Kalender, Kontakt/Avatar, Heatmap** (echte Mini-Renders + Editier-Felder + Hilfe) · **Mini-⊕ am Panel-Kopf**
  (öffnet den Einfüge-Dialog für dieses Panel) · **größere Hover-Fenster** (322px). **Internet-Recherche**
  bestätigt die Architektur (Grid + Drag/Resize + Snap + Ghost-Vorschau, State `{x,y,w,h}` = `gx/gy/gw/gh`;
  gridstack.js / react-grid-layout / UI Bakery). **OFFEN (nächste Runde):** Verknüpfungen/Aktionen
  (Knopf→öffnet Fenster/Panel), Vorschlags-Mockups aus dem Panel-Zweck, Raster in Containern/Unterpanels,
  tailored Editier-Felder je Element, akkurates Startup-Import-Prefill bis in tiefe Ebenen.
- **✅ v12 (21.06., World-Chat) — Verknüpfungen/Aktionen + Vorschlags-Mockup + tieferer Import** (browser-
  verifiziert, 0 Fehler): **Aktion/Verknüpfung-Feld** je Element (z. B. „öffnet Panel »Details«", „springt zu
  Memory") + **↪-Marker** am Element + im „An die KI"-Export · **„✨ Vorschlags-Layout erzeugen"** im
  Panel-Editor — aus dem beschriebenen Zweck wird ein komplettes Starter-Layout ins Panel gesetzt (verifiziert
  1→7 Elemente) · **Extraktor erkennt** zusätzlich **Liste/Board/Kalender/Kontakt/Heatmap/Icon** (akkuratere
  Übernahme bestehender UIs). **OFFEN:** freies Raster in Containern/Unterpanels; tailored Editfelder je
  Element; Startup-Import-Prefill-Tiefe (alle Ebenen automatisch).
- **✅ v13 (21.06., World-Chat) — Multi-Page-Seitenmechanik + 4-Feld-Hilfe + lebender Hover** (browser-
  verifiziert, 0 Fehler): **Seiten-Mechanik** — das Oberregister schaltet jetzt INTERAKTIV ganze SEITEN um
  (Reiter klicken → nur die Panels DIESER Seite, wie Admins Übersicht/Projekte/Geschäft/Studium); Panels
  tragen `page`, Anlegen/Import seiten-bewusst (verifiziert: Übersicht 1 / Projekte 2 / Geschäft 1, Umschalten
  isoliert sauber) · **Hover bedeutend ausgebaut** (362px): Element in einem **lebenden Beispiel-Panel** + 4
  Zeilen **Was · Wann/wofür · Parameter · braucht-Verknüpfung/Daten** (Select→Tabelle-Filter, Radio=Modus-
  Umschalter, Kontakt=Communication-Vernetzung …); HELP für ALLE ~35 Elemente 4-feldrig; Detail-Fenster
  ebenso. **OFFEN:** Live-„App-UI laden" automatisch über ALLE Seiten (klickt die echten Reiter durch);
  freies Raster in Containern; tailored Editfelder je Element.
- **✅ v14 (21.06., World-Chat) — §3.1 ECHTE LIVE-VOLL-ÜBERNAHME + PREFILL + CSP-FIX** (live an Dizz Admin
  :8222 / Proxy :8422 verifiziert, 0 Konsolenfehler, netzwerkweit ausgerollt, 0 Drift): **`walkAndExtract`**
  klickt die echten Oberregister-/`.modulbar`-Reiter **programmatisch durch** und extrahiert **je Seite**
  (Panel.page getaggt; Live-Tab pro Schritt NEU gesucht, weil das Register bei jedem Wechsel neu gebaut wird)
  · **zweistufige Navigation erkannt** (Admin Bereich×Modul: robuste **Bereichs-Vorauswahl** per Polling auf
  einen konkreten `kontextbar`-Chip, sonst zeigen Module nur den leeren Navigator) · **Raster-Mapping** aus
  echten `getBoundingClientRect` im fixen **1280×900-iframe** (Panel-x/w relativ zu `.wrap`, Element-
  gx/gy/gw/gh per Zeilen-Cluster — KPI-Kacheln liegen nebeneinander, Formulare in Zeilen) · **Prefill je
  Element aus DOM-Attributen** (`eprops`): Button-`variant`+humanisierte `aktion` (aus `data-dz-act`/href),
  Select-`<option>`-Texte, Tabellen-Spalten/Zeilen, KPI/Metrik-Werte, Cockpit-Spalten, Badge-State — Doppel-
  klick zeigt den IST-Zustand. **★ CSP-BLOCKER GEFUNDEN+GELÖST:** CSP-strikte Apps liefern `/ui-kit/*.html`
  mit `script-src 'self' 'nonce-…'` ⇒ das Inline-`<script>` des Tools wurde blockiert (Tool-JS lief
  same-origin GAR NICHT). Fix: JS in **externe `panel-builder.js`** ausgelagert (`script-src 'self'` erlaubt
  gleich-Herkunft) ⇒ **Tool ist jetzt ZWEI Dateien** (html+js, immer zusammen vendoren). **OFFEN:** Rest-
  Unschärfen (titellose Cards = „Panel", Status-Pillen→Board-Fehlerkennung, Metrik-`trend`-Default); §3.2–3.6.
- **✅ v15 (21.06., World-Chat) — §3.2 + §3.5 + §3.6 + Politur + Desktop-Schnellzugriff** (live an Dizz Admin
  verifiziert, 0 Konsolenfehler, netzwerkweit ausgerollt 0 Drift): **§3.2** Panel-Editor-Selektor „Seite"
  (Panel umhängen, wenn Oberregister >1 Seite) · **§3.5** Element-Bindung `p.zielId` (Auswahl anderes Panel/
  Element) → sichtbarer **↪-Marker** (Aktion + Zielname) + Export · **§3.6** Panel- & Unterpanel-„Standard-
  Zustand" offen/eingeklappt (Chevron umschaltbar, Import erfasst echten `open`-Stand, Export vermerkt es) ·
  **Politur** Board-Fehlerkennung entschärft + Metrik-`trend` nur noch bei echter DOM-Quelle. **★ Desktop-
  Integration:** `?lade=1`-URL-Parameter ⇒ Tool startet „App-UI laden" automatisch (+ `replaceState`-Putz);
  das native **Dizz-Network-Fenster (Monitor, netzweit `ops/monitor/monitor_app.cs`, verlegt 02.07.)** hat dafür je
  App einen **Bautool-Chip** unten (→ `…:PORT/ui-kit/panel-builder.html?lade=1`); zudem „Netzwerk-Dashboard"-
  Button entfernt + Sprachzeile („lauscht auf …") nach oben unter den Titel. **OFFEN:** §3.3 (freies Raster in
  Containern) + §3.4-Rest.
- **✅ v16 (21.06., World-Chat) — Trading Bot + Core erfassbar + Extraktor robuster** (beide live-verifiziert
  auf Scratch, Admin-Regression grün, netzwerkweit ausgerollt 0 Drift): Extraktor erkennt jetzt das Muster
  **„Panel umschließt ein `<details>`"** (Titel aus `<summary>`, TB-Panels) + **`.card`-KPI-Kacheln**
  (`.big`/`.lbl`) + **klappt `<details>` vor dem Auslesen auf** (sonst rect=0) + Core-Titel `.head .name`;
  Timeout 22→42 s. Tool zusätzlich in **TB** (`backend/app/static/ui-kit/` + `/ui-kit`-Route in `main.py`) und
  **Core** (`core/ui-kit/` + Route) deployt; APPMAP +8137/+8200. **Monitor v2.6:** Bautool-Reihe + Trading +
  Core. **OFFEN:** TB :8137 + Core :8200 neu starten (gated) für die Live-Route.
- **✅ v17 (21.06., World-Chat) — §3.3 + §3.4, Roadmap KOMPLETT** (standalone + Admin-Regression verifiziert,
  0 Fehler, netzwerkweit ausgerollt 0 Drift): **§3.3** Container-Blätter (Subpanel/Oberregister) auf eigenem
  `pgrid` (frei verschieb-/größen-ziehbar, gleiche Drag-Engine); **§3.4** Tabellen-Spaltennamen (+Export) +
  Fortschritt-Wert % als getaylorte Editfelder. **docs/_archiv/40 §3.1–§3.6 alle ✅.**
- **✅ v18 (21.06., World-Chat) — MASZSTABSGETREUER MODUS (Layout 1:1)**: Import erfasst echte Pixel-Rechtecke
  (Panel `rx/ry/rw/rh`, Element `ex/ey/ew/eh`, Kopfzeile als `header`-Element) + `refW`; Render absolut-px
  skaliert auf Canvas-Breite (`SC=canvasW/refW`) ⇒ volle Breite, exakte Proportionen/Abstände/Höhen, Drag/Resize
  in px. Admin-verifiziert (Panels 1180, 15-px-Lücken, KPI 279 px exakt). **ABER optisches 1:1 fehlt noch** ⇒
  docs/_archiv/40 §3.0 (Pixel-Mirror) = eigener Bau-KI-4.8-Extra-Chat (Nutzer-Entscheid).
- **✅ v19 (22.06., Bau-KI-4.8-Extra-Chat) — PIXEL-MIRROR: echtes optisches 1:1 (docs/_archiv/40 §3.0 ERLEDIGT)**, 5 Runden,
  an Dizz Admin verifiziert, netzwerkweit 0 Drift. Statt `pv()`-Nachbau wird die **echte gerenderte DOM mit der
  echten App-CSS** im Shadow-Root gespiegelt (erfasst bei echter Browser-Breite ⇒ ganze Seite 1:1: volle-Breite-
  Leisten + zentrierter schmaler Inhalt). Seiten-Umschalten übers echte Oberregister; native `<details>`+Drill-down
  klappen auf; **Doppelklick = Hintergrund-Info** (inkl. Glow-Kennzeichnung, fest aus UI-Kit); **✎-Bearbeiten-Ebene**
  mit ebenen-farbigen gestrichelten Rahmen (Hauptpanel/Unterpanel/Element) + greifen/Größe/löschen/einfügen; jeder
  Oberregister-Reiter + Bereich-Chip als Einzel-Element; **Drill-down** („Alle Bereiche" → Studium → Biologie-Detail)
  erfasst, offline-aufklappbar **und bearbeitbar**. **Glow-Audit → docs/_archiv/41** (Übergabe an World-Admin-Chat: dz-*-Glows
  kanonisch im Kit ✅, App-Shell-Glows je App inline ⇒ Empfehlung ins shared Kit zu promoten). Details: docs/_archiv/40 §2 v19.

## 4 · WP-D — UI-Kit-Vollständigkeit
- Jedes in WP-A/C entstandene **gute Design wird kanonisch ins UI-Kit** gelegt (`shared/`) und netzwerkweit
  vendort → **0 Drift**, überall verfügbar — auch für noch nicht gebaute Funktionen („UI liegt bereit").
- Bei **allen** Apps prüfen, dass das **Hochsicher-Symbol** korrekt sitzt (ist im Kit enthalten).

## 5 · WP-E — KONNEKTIVITÄTS-VISION (festschreiben; Ausbau später, kommerziell)
> Schärft [docs/35](35_KONNEKTIVITAET_VISION.md). Kernbild des Nutzers:
- **Das Network ist offen für ALLE Verbindungen** — es soll den Dschungel aus Apps/Plattformen/Kanälen
  **handlich** machen: alles **connecten**, und in der jeweiligen App laufen **alle kommunikativen Kanäle
  in EINEM Nachrichten-Strom** zusammen — auf einen Blick observierbar.
- **Pro Kontakt kanalübergreifend:** „von diesem Kontakt kam jetzt eine Nachricht auf **Instagram**, eine
  auf **Telegram**, früher mal eine **WhatsApp**" — eine Identität, alle Kanäle, ein Thread (= D1
  Unified-Inbox/Smart-Contacts, bereits gebaut; Vision = es überall durchziehen).
- **Reihenfolge Konnektoren:** WhatsApp ✅ (PoC, schwer wg. Meta) → **Telegram** (einfach: Bot-Token, rein
  lokal, kein Review) als nächster, ABER **hinten angestellt** (nach der UI-Phase) → **Meta produktiv**
  erst mit **Business-Unterlagen** (Gewerbeanmeldung) → weitere Kanäle (Signal/Matrix-Bridges, Schiene A/B).
- **Zwei kleine Communication-Fixes** (aus dem PoC, kleines Paket, Communication-Chat ODER World-Chat wenn frei):
  1. **Echtzeit-Auffrischen** der Vorschlagsliste nach „Test senden" (heute Reload nötig — `metaTest()`
     ruft `renderKiAktivitaet()` nicht; Fix = eine Zeile, analog `sendenVorschlag`).
  2. **Template-Versand** im In-App-Test (`_MetaTestIn.template` wird nicht in die Vorschlags-Params
     gereicht ⇒ außerhalb 24-h-Fenster kein Senden ohne Handy-Trick).

## 6 · WhatsApp-Konnektor — STATUS (PoC ✅)
- Verbunden + **end-to-end live bewiesen**: App → HITL-Freigabe (Stufe verifiziert, Dizzi-ID-Login) →
  echter Meta-Graph-Call → `executed`, gültige `wamid`. Token im **Tresor**, `phone_number_id`
  `1140191385851923`, `graph_version` v23.0. Gegateter `:8218`-Neustart durch, Backup unter
  `…\backups\komm-meta-golive-20260621\`.
- **Gotchas gelernt:** (1) Empfänger im **internationalen Format ohne `+`/`0`** (`49…`), sonst Meta
  `#131030`. (2) **Freier Text** wird nur im **offenen 24-h-Fenster** zugestellt (Meta nimmt ihn sonst an
  [wamid], liefert aber nicht) — Templates kommen immer an. (3) Inbound braucht Tunnel/Server (offen).

---

## 7 · REIHENFOLGE
1. **JETZT, World-Chat-Fundament (Repo `the world of dizzi`, keine App-Repos):**
   - WP-C Panel-Bautool **v4** (App-Kopf + Oberregister/Ebenen + neue Elemente + Extraktor) — kanonisch.
   - WP-A **Kopf-Norm** als Kit-Baustein in `shared/` bauen (Fundament; Rollout folgt).
2. **Kleine Wins (Repo frei ⇒ machbar):** die zwei Communication-Fixes (§5).
3. **UI-Groß-Phase MIT Nutzer (gegated, App für App):** Kopf-Norm + Layout-Aufräumen ausrollen auf
   Admin · Memory · Management · Health; Admin-Panels greifbar (WP-B); Feinjustage je App über das Panel-Tool.
4. **Trading Bot:** Kopf-Norm + Hochsicher-Symbol + grober UI-Pass (TB-Repo, gegated) — früher Nutzer-Wunsch.
5. **UI-Kit-Vollständigkeit + netzwerkweites Vendoring** (WP-D), 0 Drift; Panel-Tool v4 überall.
6. **Konnektivität weiter:** Telegram-Konnektor → Meta produktiv (mit Gewerbe) → Unified-Stream überall (§5).
