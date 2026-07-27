# 70 · UX-KONSOLIDIERUNG — Design-System-Vertrag (F-1…F-8 + MG-1 + Trading-Cockpit-IA)

> **Status: DESIGN-VERTRAG 04.07.2026 (Architektur-KI 5, design-only).** Gießt die 8 netzweiten Konfusions-Muster
> des FP-6-UX-Audits (docs/60 F-1…F-8) + MG-1 in **EIN kanonisches Design-System-Upgrade**
> (ui-kit/appkit-Bausteine + Normen), damit der spätere Bau-KI-Rollout **konsistent statt fragmentiert**
> ausfällt. Zusätzlich: **Trading-Cockpit-Informationsarchitektur** (read-only-Analyse :8137, reiner
> Design-Vorschlag) inkl. der offenen World-Admin-Auflage **T5-Panel ↔ docs/60-Gegenprüfung** (§5.4).
>
> **Kein Pixel-Rollout in diesem Paket.** Bestands-Frontends bleiben byte-unverändert; geliefert werden
> Vertrags-Stubs (ui-kit `ux-kit.css/js`, additive collapse-/controls-Erweiterung, appkit `netz`/
> `fehlerseite`/`sichtbarkeit`/`sprachregister`) + Tests. Umsetzung: Bau-KI-Pakete UX-0…UX-6 + UX-T (§7),
> nach der 50-%-Budget-Schwelle (docs/57).
> Quellen-Kette: docs/60 (Audit + Gate-Antworten) · docs/06 (Design-System/K2.3/K2.4) · docs/39 (Kopf-Norm)
> · docs/19 (K2.2-Fenster) · docs/58 §3.F (Regie-UX-Kanon) · docs/56 (Editionen).

## 0 · TL;DR

1. **Neun kanonische Bausteine** (§3), je EINMAL im Kit gebaut, netzweit adoptierbar: `DzUx`-Familie
   (Netz-Leiste · Gesperrt-Zustand · Leer-Zustand · Toast · Kontext-Confirm · Agenten-Chip · Tooltip-Norm
   · Format-Normen) + Collapse-Norm v2 + appkit-Fehlerseite + App-Verzeichnis + Sichtbarkeits-Politik
   + Sprachregister.
2. **Stufe-0-Adoption** (§4): alles opt-in (neue Dateien, neue Attribute, neue Statuswerte) — eine App,
   die nichts ändert, sieht exakt aus wie heute. Der Rollout ist damit App-für-App gefahrlos.
3. **Trading-Cockpit** (§5): Statusband + 5 Arbeitsräume + sichtbare König→Ensemble→Flotte-Hierarchie
   als Design-Vorschlag (KEIN Code, :8137 unberührt); T5-Panel-Gegenprüfung: 2 konkrete Nacharbeiten
   (F-5/F-6), Rest vorbildlich.
4. **Ehrliche Trennung** (§6): Was hier spec-bar ist (Mechanik, Semantik, Wording, IA) vs. was visuelle
   Iteration mit David braucht (Dichte, Feinabstände, Cockpit-Feel).
5. **Alle David-Gates beantwortet** (§10, David 04.07.): G-UX-COLLAPSE ✅ JA (Kopf-Klick, Supersede
   docs/06 §6.3 aktiv) · G-UX-ANREDE ✅ „du" · G-UX-TB-COCKPIT ✅ Struktur angenommen (Feel-Check
   läuft im UX-T, kein separates Gate); G-UX-AUTH/G-UX-LOGIN schon zuvor beantwortet. **Kein Gate
   blockiert mehr ein Rollout-Paket** — nur noch operative Tore (UAC/Neustart je App, TB-Chat für UX-T).

## 1 · Ist-Zustand (Kit-Inventur + Befund-Verdichtung, verifiziert 04.07.)

**Was das Kit HEUTE kann** (`packages/ui-kit`, Single-Source, von allen Apps via `appkit.ui_kit_path()`
serviert): Token-Master `tokens.css` (10×10-Achsen + K2.4-Komponenten-Tokens) · `controls.css`
(Controls-Familie, Panel-Collapse-Optik, Kopf-Norm `.dz-appkopf`, `.dz-chip`, `.dz-table`, `.dz-badge` …)
· `collapse.js` (Collapse/Stepper/Upload/`data-dz-act`-Delegation) · `netkit.css/js` (Viewswitch, ⌘K,
Facetten, KPI-Leiste, Cockpit-Kacheln) · charts/floats/spinfling/background/clickwave/reading.

**Was fehlt — die 8+1 Lücken aus docs/60, auf ihre technische Wurzel gebracht:**

| F# | Muster | Technische Wurzel (verifiziert) |
|---|---|---|
| F-1 | Apps = Navigations-Inseln | Kein Netz-Baustein im Kit; **kein kanonisches App-Verzeichnis** in appkit (nur Core kennt die 10 Apps via eigene Panel-Seeds) |
| F-2 | Stille Leere statt Gesperrt | `Summary.status` kennt nur `ok\|leer\|fehler` (summary.py); auth-geschützte Endpoints liefern still `[]` bei 200; keine Sichtbarkeits-Politik als Code |
| F-3 | Collapse-First versteckt Inhalt | `collapse.js` erzwingt `setze(false)` beim Laden (Norm 18.06.) — **kein** Default-offen-Mechanismus; docs/06 §6.3 „NUR der Chevron klappt" ⇒ Kopf = toter Klick (CO-2/ME-1/TR-2) |
| F-4 | 404 = rohes JSON (8/8) | `create_app()` installiert **keinen** Exception-Handler ⇒ FastAPI-Default `{"detail":"Not Found"}` |
| F-5 | Mikro-Icons ohne Tooltip | Keine Tooltip-Norm/-Komponente im Kit; keine Pflicht-Konvention |
| F-6 | Insider-Sprache im Kunden-UI | Kein kanonisches Kunden-Lexikon; jede App textet selbst (HITL/DORMANT/§R-G/⌘K) |
| F-7 | Feedback/Empty ungleich verteilt | Vorbilder existieren (Memory „✓ gespeichert", Mgmt-Empty-States, Healthy-Prompts, News-Tooltips), aber **nicht als Kit-Baustein** |
| F-8 | Datums-/Anrede-/Label-Chaos | Keine zentrale Datums-Formatierung (rohe RFC822/ISO-Strings), keine Anrede-Norm, 3 Anmelde-Pill-Wortlaute |
| MG-1 | Agenten-Identität unsichtbar | Kein Herkunfts-/Agenten-Baustein; Management-UI ohne „Agent"-Vokabular trotz D13 |

## 2 · Grundsätze (Design-Verfassung dieses Vertrags)

1. **Token-only.** Jeder neue Baustein verbraucht ausschließlich `var(--…)`-Tokens (docs/06, Token-Vertrag
   in tokens.css). **Kein Hex-Wert in neuen Kit-Dateien** — testgepinnt (§8, T-TOKEN).
2. **Opt-in = Stufe-0.** Neues Verhalten hängt IMMER an neuen Dateien, neuen Attributen
   (`data-dz-offen`, `data-dz-kopf-klick`), neuen Parametern (Default = Bestandsverhalten) oder neuen
   Statuswerten. Eine unangefasste App rendert byte-identisch.
3. **Klartext vorn, Interna hinten.** Sichtbares Label = Kunden-Sprache; Fachbegriff/Interna wandern in
   `title`-Tooltip oder Doku (F-6). Perspektive = zahlender Neukunde (docs/60), nicht David.
4. **Zustände sind explizit, nie geraten.** `gesperrt ≠ leer ≠ fehler`. Eine App behauptet NIE
   „alles in Ordnung", wenn sie die Datenbasis nicht sehen darf (MO-1-Verbot, testgepinnt).
5. **CSP-strikt-tauglich.** Keine Inline-Handler; alles über `addEventListener`/`data-dz-act`
   (Delegations-Muster aus collapse.js). Keine Inline-`style=`-Attribute in Komponenten-Markup
   (docs/37-Falle: Nonce gilt nicht für Style-Attribute).
6. **Barrierefrei per Konstruktion.** Echte Buttons, `aria-label`/`aria-expanded`/`aria-live`,
   `:focus-visible`-Ringe (K2.4-Linie), `prefers-reduced-motion` respektiert.
7. **Positiv-Muster verallgemeinern statt neu erfinden.** Die Vorbilder aus dem eigenen Netz (Memory/
   Management/Healthy/News, docs/60 F-7) sind die Referenz-Semantik der Bausteine.

## 3 · Die neun kanonischen Bausteine

> Namenskonvention: neue Kit-Dateien **`ux-kit.css` + `ux-kit.js`** (EIN Paar, Namensraum `window.DzUx`)
> — bewusst gebündelt wie netkit, damit Adoption = 2 `<link>/<script>`-Zeilen je App. Python-Seite:
> vier neue appkit-Module + zwei additive Erweiterungen. Alle APIs unten sind die VERBINDLICHE Signatur
> (Verträge-als-Code, Stubs liegen bei).

### 3.1 · B-NAV — Netz-Leiste (F-1: „zurück ins Netz, rüber zur Schwester-App")

**Problem:** Außer Core hat keine App einen Link zur Zentrale oder zu Schwester-Apps (5× belegt).
**Baustein (zweiteilig):**
- **appkit `netz.py` — das kanonische App-Verzeichnis (NEU, Single-Source):**
  `NETZ_APPS: tuple[NetzApp, ...]` mit `id · brand · name · port · icon · sensitivity` für alle
  10 Apps + `CORE_URL = "http://127.0.0.1:8200"` (Konvention wie app_gateway). Router
  `netz_router()` ⇒ `GET /api/netz/apps` (statische Daten, KEIN Cross-App-Call, funktioniert offline).
  In `create_app(netz=True)` enthalten (opt-out-Parameter). **Damit hat das Netz erstmals EINE
  code-kanonische Quelle „welche Apps gibt es"** — Core-Panels können später darauf umziehen.
- **ui-kit `DzUx.netzleiste(el?)`:** rendert in den `.dz-appkopf` (vor der Auth-Pille) einen kompakten
  **„⌂ Netz"-Knopf**; Klick öffnet ein Popover (Optik = `.dz-cmdk`-Familie): oben prominent
  **„Zur Zentrale"** (CORE_URL), darunter die Apps als Mini-Lockups (Marke betont + Funktion dezent,
  K2.3), aktuelle App markiert, `sensitivity=hoechst` trägt 🛡. Daten von `/api/netz/apps`;
  **Fallback bei Fehlschlag: nur der Zentrale-Link** (ehrlich, nie leeres Popover). Esc/Backdrop
  schließt; Tastatur-navigierbar (`role="menu"`).
**Norm dazu:** Der Netz-Knopf ist Pflichtteil der Kopf-Norm (docs/39 §1b wird um ihn ergänzt);
Core-Kacheln (CO-2) ziehen nach: ganze Kopfzeile klappt + „Seite öffnen" dauerhaft sichtbar (Core-eigener
Bau-KI-Task, gleiche Norm).
**Deckt:** KO-7 · AD-3 · MG-4 · HE-3 · CR-5 · CO-2 (Norm-Teil).

### 3.2 · B-LOCK — Gesperrt-Zustand (F-2: 🔒 statt stiller Leere; G-UX-AUTH ✅ als Code)

**Problem:** Money maskiert unangemeldet alles als stille Leere („0,00 € · alles im grünen Bereich"),
Comm/Healthy zeigen alles — zwei Vertrauensmodelle, Kunde kann keines lernen.
**Baustein (dreiteilig):**
- **appkit `summary.py` (additiv):** `Summary.status` erhält den vierten Wert **`"gesperrt"`**.
  Kachel-Vertrag: `status="gesperrt"` ⇒ Panel zeigt 🔒 + `note` (z. B. „Mit Dizzi-ID anmelden, um deine
  Finanzen zu sehen") statt Pseudo-Nullen. KPI-Werte dürfen dann NUR maskiert (`"•••"`) reisen.
- **appkit `sichtbarkeit.py` (NEU) — die entschiedene Editions-Matrix als Entscheidungsfunktion:**
  ```python
  Edition = Literal["lokal-pur", "hybrid", "vollserver"]      # docs/56
  Zugriff = Literal["frei", "anmelden", "reauth", "wand"]
  def zugriff(edition, level, *, klasse="lesen", sensitivity="normal") -> Zugriff
  def gesperrt_summary(manifest, grund, kpi_labels=()) -> Summary   # 🔒-Kachel, KPIs "•••"
  def gesperrt_payload(grund, login_url="/id/login") -> dict        # statt stillem [] in Endpoints
  ```
  **Matrix (= G-UX-AUTH-Antwort David 03.07., hier verbindlich kodiert):**
  | Edition | Regel |
  |---|---|
  | **vollserver** | ohne Anmeldung `wand` (Login-Wand, ganze App = ein großes `.dz-gesperrt`) |
  | **hybrid** | lokale Funktionen `frei`; **jeder Server-Funktions-Zugriff** (Boost/Sync/Remote, `klasse="server"`) ⇒ `anmelden` (≥ verifiziert) |
  | **lokal-pur** | nutzbar ohne Login (`frei` — auch hoch/höchst-Ansicht, bewusst: das Gerät IST die Grenze); Differenzierung NUR `klasse="hochsicher"` (Echtgeld · Export · Löschen · Tresor-Werte · Live-Schaltung) ⇒ `reauth` |
  Fail-closed: unbekannte Edition/Klasse ⇒ strengste Antwort. **Konsequenz der Matrix — ehrlich
  benannt:** In der heutigen Lokal-pur-Realität ist *Moneys Vollmaskierung* die Abweichung (nicht
  Healthys Offenheit); Money zeigt künftig lokal die Daten UND der 🔒-Zustand greift überall dort, wo
  wirklich Anmeldung fehlt (Hybrid/Vollserver bzw. hochsichere Aktionen). Nie wieder stille Leere.
- **ui-kit:** `.dz-gesperrt` (Panel-Fläche: 🔒-Glyph, EIN Erklär-Satz, CTA „Anmelden (Dizzi-ID)" →
  `/id/login?zurueck=<app-url>`) + `DzUx.gesperrt(el, {grund, loginUrl})` +
  `DzUx.gesperrtKpis(el, labels)` (KPI-Zeile als „🔒 •••"-Masken). Login-Seite selbst (MO-4:
  Erklärsatz + Registrier-Pfad + „Zurück zu {App}") = Core-Bau-KI-Task nach derselben Norm
  (`zurueck`-Parameter gehört ab jetzt zum Anmelde-Link-Vertrag).
**Deckt:** MO-1 · CO-1 · KO-2 · HE-2 · MO-4 (Norm-Teil).

### 3.3 · B-FOLD — Collapse-Norm v2 (F-3: Inhalt sichtbar, Kopf klickbar)

**Problem:** Alle Panels starten hart eingeklappt (collapse.js `setze(false)`), News zeigt beim Öffnen
0 Nachrichten; Kopf-Klick tut nichts (docs/06 §6.3), TB schreibt „(aufklappbar)" in den Titel als Krücke.
**Baustein (collapse.js v2 + controls.css-Anhang, beides additiv über Attribute):**
- **`data-dz-offen`** am Panel ⇒ Panel startet OFFEN. **Norm: pro App EXAKT EINE Default-offene
  Kern-Sektion** (die App-Antwort auf „Warum bin ich hier?"): News→Artikel · Money→Register ·
  Comm→Inbox · Memory→Notizliste · Mgmt→Agenten/Redaktion · Admin→Bereichs-Übersicht ·
  Creating→Schaffen · Healthy→Übersicht · Core→oberste 2 Panels (bestehendes Schema) · TB→Statusband (§5).
- **`data-dz-kopf-klick`** am Panel ODER an einem Vorfahren (`closest()`, z. B. `<body>` = App-weit)
  ⇒ der GANZE Kopf togglet (nicht mehr nur der Chevron); Kit setzt dann `cursor:pointer` auf den Kopf.
  **Die Glow-Disziplin vom 14.06. bleibt vollständig:** Kopf-Hover erzeugt weiterhin KEINEN Glow,
  der Chevron bleibt der einzige Glow-Träger, Karten glühen nie beim Hovern. Nur die KLICK-Fläche wächst.
- **Chevron-Affordance +:** unter `[data-dz-kopf-klick]` bekommt der Chevron einen dezent pulsierenden
  Erst-Hinweis? **Nein — bewusst verworfen** (Bewegungs-Disziplin docs/06 §2); stattdessen: eingeklappte
  Panels zeigen die vorhandene `.dz-panel-kurz`-Kurzanzeige konsequent (Rollout-Checkliste), das IST
  die Affordance („da ist Inhalt drin").
- **ME-1-Norm:** Aktionen, die in ein eingeklapptes Panel zielen („+ Notiz" → Editor), MÜSSEN das
  Ziel-Panel programmatisch öffnen + hinscrollen/fokussieren. Dafür `DzUx.oeffnePanel(panel)` (nutzt
  die collapse.js-Mechanik, feuert `aria-expanded` korrekt).
**⚠ Norm-Supersede (ehrlich ausgewiesen) — ✅ freigegeben 04.07.:** Dieser Baustein ÜBERSCHREIBT
docs/06 §6.3 „NUR der Toggle klappt / Kopf `cursor:default`" (David-Abnahme 14.06.) zugunsten der
docs/60-F-3-Linie (Audit-Evidenz 03.07.: Kopf-Klick = bestes Muster im Netz, Chevron-only = 3× belegte
Konfusion). Die 14.06.-Iteration drehte sich im Kern um **Glow-Lecks** — die bleiben alle gefixt.
**Gate G-UX-COLLAPSE ✅ JA (David 04.07., §10):** Supersede aktiv, UX-2 entsperrt.
**Deckt:** NE-1 · CO-2 · TR-2 · ME-1.

### 3.4 · B-404 — Fehlerseite (F-4: nie wieder rohes JSON im Browser)

**Problem:** `{"detail":"Not Found"}` in 8/8 Stacks — Sackgasse ohne Rückweg.
**Baustein: appkit `fehlerseite.py` (NEU):** `install_fehlerseiten(app, manifest)` registriert einen
`StarletteHTTPException`-Handler (404/405/…) mit **strikter Content-Negotiation**:
- HTML **nur wenn** `"text/html"` im `Accept`-Header **UND** Pfad nicht unter `/api/` ⇒ Browser-Navigation.
- Alles andere (API-Clients, `fetch` mit Default-`Accept: */*`, Tests) bekommt **exakt die bisherige
  JSON-Antwort** — der API-Vertrag (docs/16, FP-7-Audit-Basis) bleibt byte-stabil.
Die Seite selbst: self-contained Markup, lädt `/ui-kit/tokens.css` + `/ui-kit/controls.css` (serviert
jede App selbst ⇒ offline-fest), zeigt Marken-Lockup (K2.3: `manifest.brand` + `manifest.name`),
EINEN Satz („Diese Seite gibt es hier nicht.") + zwei Wege: **„Zur App-Startseite"** (`/`) und
**„Zur Zentrale"** (`CORE_URL`). Kein Suchfeld, keine Spielerei — eine Tür, zwei Ausgänge.
In `create_app(fehlerseite=True)` per Default AKTIV (wirkt erst beim je gegateten App-Neustart; für
API-Konsumenten wertgleich, s. o.). **TB-Pendant:** eigener Stack ⇒ eigene kleine 404-Route im
UX-T-Paket (gegated, §5/§7) nach derselben Zwei-Ausgänge-Norm.
**Deckt:** CO-10 · NE-4 · MO-7 · KO-8 · ME-7 · AD-4 · MG-4 · TR-4 (TR via UX-T).

### 3.5 · B-TIP — Tooltip-/Mikro-Icon-Norm (F-5)

**Problem:** ⊛ (3 Apps), „🔓 normal" (Memory-Vault), „● ?"/„× Var." (Creating), Senden-Button ohne
Label (Core) — der „was ist das?"-Dauerton.
**Baustein + Norm:**
- **PFLICHT-Konvention (lint-bar):** Kein interaktives Element ohne **sichtbares Label ODER
  (`title` UND `aria-label`)**. Icon-only-Buttons IMMER mit beidem.
- **ui-kit `[data-dz-tip]`:** getönter Token-Tooltip (CSS-only via `::after`, Position oben/unten per
  `data-dz-tip-pos`, `max-width`, entsteht NUR bei `:hover`/`:focus-visible`) — für Stellen, wo der
  native `title` zu flüchtig ist. `title` wird ZUSÄTZLICH gesetzt (Screenreader/Touch-Fallback).
- **`DzUx.pruefeTooltips(root?)`:** Dev-Helfer — loggt alle interaktiven Elemente ohne
  Label/`title`/`aria-label` in die Konsole. Wird Teil der Rollout-Verifikation je App
  (preview_eval-Schritt: Erwartung 0 Funde).
- **Wortlaut-Katalog für die belegten Mikro-Icons** (verbindlich, Bau-KI setzt nur noch ein):
  | Element | `title`/Tooltip |
  |---|---|
  | ⊛ (Bereichs-Symbol) | „Bereich: ordnet diesen Eintrag einem Lebensbereich zu (verwaltet in Dizz Admin)" |
  | 🔓/🔒 Memory-Vault-Toggle | „Vault: 🔒 = verschlüsselt ablegen (Passwort nötig) · 🔓 = normal speichern" |
  | Senden-Knopf (Core) | „Senden" (+ `aria-label`) |
  | „× Var."-Stepper (Creating) | „Anzahl Varianten je Erzeugung" |
  | „● ?"-Statuspunkt (Creating) | „Status unbekannt — Dienst noch nicht geprüft" |
  | TB-Katalog-Zählerreihe (TR-3) | je Zahl: „5 Basis-Strategien · 8 markt-neutral · 1 Session-Eröffnung · …" |
**Deckt:** MO-6 · ME-4/ME-6 · CR-4 · CO-5 · TR-3 (Wortlaut; Einbau UX-T).

### 3.6 · B-WORT — Sprachregister (F-6: Kunden-Sprache vorn)

**Problem:** „HITL" als Button-Text, „v1 DORMANT", „(Gesetz 5)", „REV-3, POST /api/…",
„Apache-Verkaufs-Anker", „waterproof-kommerziell", ⌘K auf Windows.
**Baustein: appkit `sprachregister.py` (NEU) — das kanonische Kunden-Lexikon als Code:**
```python
KUNDEN_LEXIKON: dict[str, str]      # Insider-Begriff -> Kunden-Label (Anzeige-Text)
INTERNA_MUSTER: tuple[str, ...]     # Begriffe/Muster, die im Kunden-UI NIE sichtbar sein dürfen
def kunden_label(begriff) -> str    # kanonische Übersetzung (KeyError-frei: Identität als Fallback)
def pruefe_text(text) -> list[str]  # Lint: gefundene Insider-Begriffe (für Tests + Rollout-Checkliste)
```
Kern-Einträge (verbindlich; vollständige Liste im Modul):
| Insider | Kunden-Label (sichtbar) | Interna-Ort |
|---|---|---|
| „Senden (HITL)" | **„Senden (mit Freigabe)"** | Tooltip: „Human-in-the-Loop: nichts geht ohne dein OK raus" |
| „v1 DORMANT" | **„vorbereitet — bewusst noch aus"** | Doku |
| „(Gesetz 5)" / „(V18)" / „REV-3, POST /api/…" | **ersatzlos raus** aus Kunden-Texten | Doku/Tooltip |
| „Apache-Verkaufs-Anker" / „waterproof-kommerziell" | **„kommerziell nutzbar"** | Tooltip: Lizenzname |
| „idempotent" | **„mehrfach klicken ist unschädlich"** | — |
| ⌘K (auf Windows) | **„Strg K"** — plattformabhängig via `DzUx.format.kuerzel("K")` | — |
**Shortcut-Norm:** sichtbare Kürzel IMMER plattformrichtig (`navigator.platform`-Weiche im Kit);
Tooltip darf beide nennen. **Regel:** Sektions-Erklärtexte sprechen zum Kunden (Muster: Management,
docs/60-Lob), Interna wandern in `title` oder Doku — `pruefe_text()` ist der Wächter in Tests +
Rollout-Checkliste je App.
**Deckt:** KO-3/KO-6 · MG-2/MG-3 · CR-3 · T5-Panel (§5.4).

### 3.7 · B-ECHO — Feedback-Familie (F-7: Toast · Leer-Zustand · Kontext-Confirm)

**Problem:** Stummes Watchlist-Add (NE-2), Löschen ohne Rückmeldung (ME-3), Confirm mit falschem Titel
(ME-2), Batch-Leiste scharf bei 0 Auswahl (MO-3), leere Selects ohne CTA (MO-2), Meldungen ohne
Quittieren (CO-3). Vorbilder existieren im Netz — jetzt Kit-Standard:
- **`DzUx.toast(text, {art})`** — EIN Toast-Container je Seite (unten mittig, `aria-live="polite"`,
  auto-dismiss ~4 s, `art: ok|warn|fehler` = Token-Farben, reduced-motion-fest). Norm: **jede
  zustandsändernde Aktion quittiert** („In ‚X' gespeichert", „Gelöscht", „Übernommen — wirkt ab …",
  TB-T5-Muster). Kein Toast für reines Navigieren.
- **`DzUx.leer(el, {text, cta})`** + `.dz-leer` — Leer-Zustand MIT nächstem Schritt: Glyph + 1 Satz +
  optionaler CTA-Button (`data-dz-act`-verdrahtet). Norm-Formel = Management/Healthy-Muster:
  *„Noch kein(e) X — [nächster Schritt] (z. B. …)"*. Ein Leer-Zustand ohne Weg ist ein Bug.
- **`DzUx.bestaetigen({aktion, objekt, gefahr}) -> Promise<bool>`** — Kontext-Confirm als Kit-Modal:
  nennt IMMER das echte, AKTUELLE Objekt („Notiz ‚UX-Audit Testnotiz' löschen?" — nie stale, ME-2),
  `gefahr:true` färbt den Primärknopf `--bad` und fordert den bewussten Klick (kein Enter-Default).
- **Kontext-Regeln (Norm, kein Code):** destruktive Aktionen sind `disabled`, solange ihr Kontext leer
  ist (kein „Buchen" ohne Konto, MO-2); Batch-Leisten erscheinen erst ab ≥1 Auswahl (MO-3); Meldungs-
  Listen brauchen „Alle quittieren" + zählen nur echte Meldungen (CO-3, App-Task nach dieser Norm).
**Deckt:** NE-2 · ME-2/ME-3 · MO-2/MO-3 · CO-3 (Norm).

### 3.8 · B-NORM — Format-Normen (F-8: Datum · Anrede · Anmelde-Pill)

- **Datum:** `DzUx.format.datum(wert, {mitZeit=true})` — nimmt ISO-8601 UND RFC-822 (die zwei realen
  Feed-Formate) + `Date`; rendert deutsch-relativ: **„heute 14:33" · „gestern 09:12" · „Mo 01.07." ·
  „01.07.2025"** (älter als das laufende Jahr mit Jahr). Unparsebares ⇒ Rohstring (ehrlich, nie „Invalid
  Date"). Serverseitiges Pendant `sprachregister.datum_de()` mit identischen Regeln (Paritäts-Tests §8)
  für server-gerenderte Flächen.
- **Anrede:** **EINE Netz-Norm: „du"** — locker-respektvoll, Healthy-Ton = Referenz (die beste App im
  Audit). Konsequenz: Dizzi-Chat-Sie-Reste werden im Wording-Pass mitgezogen. Formal Geschmacks-Entscheid
  ⇒ **Gate G-UX-ANREDE** (§10), Empfehlung „du"; als `sprachregister.ANREDE = "du"` kodiert.
- **Anmelde-Pill (EIN Wortlaut netzweit):** unangemeldet **„Anmelden (Dizzi-ID)"** · angemeldet
  **„{anzeigename} · {stufe}"** (Stufen-Wörter: lokal/verifiziert/hochsicher wie auth.py). Nie mehr
  „Dizzi-ID" nackt (ME-6) oder „Anmelden" ohne Kontext (TB).
**Deckt:** NE-3 · KO-5 · HE-1 · ME-6.

### 3.9 · B-AGENT — Agenten-Identität sichtbar (MG-1, nach docs/58 §3.F-Kanon)

**Problem:** Core verkauft Management als „KI-Agenten", die App zeigt das Wort „Agent" nirgends (D13-
Nachzug fehlt); netzweit ist KI-erzeugter Inhalt nicht als solcher gekennzeichnet.
**Baustein:** `.dz-agentchip` + `DzUx.agentchip({name, rolle, status, autonomie})` — kompakter
Herkunfts-Chip (Agent-Glyph + Name, Status-Punkt `laeuft|wartet|aus`, optional Autonomie-Kürzel mit
Tooltip „arbeitet nur mit deiner Freigabe" = Pre-Approval-Stufe aus docs/63). **Norm: JEDE von einem
Agenten/einer KI erzeugte Karte/Zeile/Nachricht trägt den Chip** („Wer hat das getan?" — §3.F
Agent-Karte-Miniatur). Doppelnutzen: erfüllt gleich das **AI-Act-Art.-50(1)-Chatbot-Label**
(02.08.2026, docs/58 G2) an Chat-Flächen: Chip-Variante `DzUx.agentchip({ki:true})` = „KI" +
Tooltip „Du sprichst mit einer KI (läuft lokal)".
Management-Kopf-Nachzug (Untertitel „KI-Agenten-Verwaltung · Domäne: Social Media" + Panel-Gliederung)
= Bau-KI-Task Z4-Kette; der Chip hier ist sein Baustein.
**Deckt:** MG-1 · AI-Act-50(1)-Vorgriff.

## 4 · Adoptions-Modell (Stufe-0) + Rollout-Reihenfolge

**Mechanik:** `packages/ui-kit` ist Single-Source und wird von jeder App disk-serviert ⇒ nach dem Merge
liegen `ux-kit.css/js` sofort unter `/ui-kit/…` bereit, **ohne dass irgendeine App sich ändert**
(kein Neustart nötig für Statics; appkit-Python wirkt erst beim je gegateten App-Neustart). Eine App
adoptiert in DREI additiven Schritten:
1. `<link rel="stylesheet" href="/ui-kit/ux-kit.css">` + `<script defer src="/ui-kit/ux-kit.js">` in den
   `<head>` (Muster News-Head, docs/70-Referenz).
2. Attribute setzen: `data-dz-offen` auf die EINE Kern-Sektion, `data-dz-kopf-klick` auf `<body>`.
3. Bausteine an den belegten Fundstellen einsetzen (Tabellen §3, docs/60-App-Tabellen als Checkliste).
**Wertgleichheits-Garantie:** Schritt 1 allein ändert NICHTS Sichtbares (ux-kit definiert nur neue
Klassen/Attribute); jedes sichtbare Delta entsteht erst durch Schritt 2/3 — pro App einzeln
verifizierbar (Scratch-Port, preview_snapshot/eval, Kardinalregel 10).

**Rollout-Reihenfolge (= docs/60-Quick-Win-Kette, verfeinert; Details §7):**
UX-0 Kit-Merge → UX-1 Sweep F-4+F-5+F-6 (viel Wirkung, null Risiko) → UX-2 F-3+F-7-Mechanik →
UX-3 F-1 Netz-Leiste → UX-4 F-2 Sichtbarkeit (Money zuerst: MO-1/CO-1) → UX-5 F-7/F-8-Vollausbau +
MG-1-Kopf → UX-6 Login-Seite (MO-4) → UX-T Trading (gegated). Je Paket: **Pilot-App zuerst** (News für
Mechanik — reifste UI; Money für F-2 — härtester Fall), dann mechanisch die übrigen; jede App einzeln
browser-verifiziert + committet.

## 5 · Trading-Cockpit — Informationsarchitektur (Design-Vorschlag, KEIN Code)

> Basis: read-only-Kartierung 04.07. (`apps/trading/programm/backend/app/static/index.html`, 3925 Z.,
> Monolith-SPA; 5 Haupt-`<details>`-Sektionen + 6-stufig verschachtelter KI-Bereich; ~50-Bot-Tabelle
> ×8 Spalten, 18-Strategien-Katalog, Regime-Matrix 18×3, ~100 kpi-mini bei Vollausklappung).
> **:8137 bleibt unangetastet; Umsetzung = UX-T, eigener TB-Chat, gegated.**

### 5.1 · Befund in einem Satz
Das Cockpit ist funktional ehrlich (DEMO-Badge, Warnbanner, Kosten-Hinweise = Netz-Bestwert), aber es
ist ein **Panel-STAPEL ohne Rang**: 5 gleichrangige Klapp-Sektionen + ein 6-Ebenen-Tiefenraum dahinter;
die zentrale Führungsfrage („Geht's dem System gut? Verdient es? Droht was?") beantwortet erst ein
Klick-Pfad, nicht die Seite selbst.

### 5.2 · Zielbild: „Vom Panel-Stapel zum Cockpit" — 3 Aufmerksamkeits-Ebenen

**A · STATUSBAND (immer sichtbar, die EINE Default-offene Sektion nach F-3):** eine schmale Leiste
direkt unterm Kopf mit den sechs Daueranzeigen — **Modus** (DEMO/ECHTGELD-Badge, bleibt) ·
**Markt-Regime** (▲/▼/↔ aus `/api/regime`, mit Klartext-Tooltip) · **Portfolio heute** (Equity + Tages-PnL)
· **Flotten-Puls** (n Bots aktiv / n gestoppt) · **Wächter** (Governor ok/warn/breach als Ampel-Chip) ·
**Daten-Frische** (ersetzt das reine Warnbanner: grün „live", gelb „Snapshot 51 min alt"). Alles
existierende Datenquellen, nur hochgerollt. Warnbanner bleibt für CRIT.

**B · FÜNF ARBEITSRÄUME (Oberregister-Muster wie Admin `.modulbar` — existiert im Kit-Umfeld):**
| Raum | Inhalt (heutige Sektionen → einsortiert) | Antwort auf |
|---|---|---|
| **1 Überblick** | Statistik-Übersicht + Highlights + **MasterMeta-König prominent** | „Wie steht's?" |
| **2 Flotte** | Bots-Verwaltung (50er-Tabelle, Suche, Bot-Drilldown) | „Wer arbeitet für mich?" |
| **3 Strategie-Labor** | Katalog (18) · Lern-Bot/Meta · Lern-Synthese · Regime-Matrix | „Was lernt es?" |
| **4 Steuerung & Risiko** | Governor · Konzentration · Sizing/Kelly · **T5 Politik→Hand** · Auto-Cull · Execution | „Wo sind die Hebel/Grenzen?" |
| **5 Konto & System** | Echtgeld-Verwaltung & Transfer · Audit · Assistent · Einstellungen | „Verwaltung" |
Progressive Disclosure BLEIBT das TB-Idiom (details-Ebenen im Raum), aber der Erst-Blick ist ein
Register mit 5 klaren Türen statt 5 grauer Balken. Poll-Mechanik/Endpoints unverändert.

**C · HIERARCHIE SICHTBAR (Mission-Control, docs/58 §3.F):** Im Überblick wird die reale Befehlskette
als 3-Ebenen-Baum gezeigt — **König** (MasterMeta, `.mmfixed` bleibt Anker) → **Ensemble** (6 Engines
als Karten mit je 1 Status + 1 Kernzahl) → **Flotte** (aggregiert: „50 Bots · 42 aktiv · 3 auffällig",
Klick → Raum 2). Der TB ist faktisch die erste Agenten-Regie des Netzes — dieselbe Bildsprache wie
B-AGENT (Status-Punkt, Rollen-Label), damit Kunde EIN Modell lernt.

**Statusklarheit (raumübergreifend):** EIN Ampel-Vokabular (`--ok/--warn/--bad`, ist da) + F-5-Pflicht
auf alle kpi-mini/Pills/Zähler (TR-3) + F-8-Datumsnorm auf alle Zeitstempel.

### 5.3 · Was NICHT angefasst wird (bewusst)
Eigener TB-Kopf/Stack (TR-1) bleibt vorerst (bekannter Zustand, „bewusst später", docs/60); das
Cockpit-Zielbild ist innerhalb des TB-Looks umsetzbar (neon-Theme trägt alle Bausteine, Token-Vertrag
identisch). Keine Funktions-/Engine-Änderung, kein Endpoint-Umbau — reine Anordnung + Wording.

### 5.4 · T5-Panel-Gegenprüfung (World-Admin-Auflage aus docs/60-Nachtrag) — ERLEDIGT

Geprüft: „Politik→Hand-Brücke"-Panel (index.html ~2732–2769, `loadPolicyBridge()`), gegen F-1…F-8:
| Muster | Befund | Urteil |
|---|---|---|
| F-3 Collapse | nutzt das TB-details-Idiom konsistent | ✓ passt |
| F-7 Feedback | defensive „Backend älter als FP-T5"-Hinweiszeile · „✓ Übernommen — wirkt ab dem nächsten Autopilot-Tick" | ✓ **vorbildlich** (Netz-Referenz für Toast-Wortlaut) |
| F-2 Ehrlichkeit | Zwei-Schlüssel-Zustand („scharf erst mit Backend- UND Engine-Schlüssel") explizit | ✓ vorbildlich |
| F-5 Tooltips | 6 kpi-mini-Chips (Brücke/Modus/L1/L2/L3/Floor) **ohne title** | ✗ Nacharbeit UX-T |
| F-6 Sprache | „Politik→Hand-Brücke" · „L1/L2/L3" · „stake_scale ×0.8" · „proposal/apply" als sichtbare Labels | ✗ Nacharbeit UX-T |
| F-8 Datum | keine Roh-Timestamps im Panel gesichtet | ✓ |
**Verbindliche Kunden-Labels für UX-T** (Interna in den Tooltip): „Politik→Hand-Brücke" →
**„Master-Steuerung: Empfehlung → Ausführung"** · L1 → **„Logik-Wahl"** · L2 → **„Einsatz-Dämpfung"** ·
L3 → **„Einstiegs-Bremse"** · `stake_scale ×0.8` → **„Einsatz ×0,8"** · proposal/apply →
**„Vorschlags-Modus / Ausführungs-Modus"**. Fazit: Auflage geprüft, Panel strukturell sauber,
2 Wording-/Tooltip-Nacharbeiten — keine Sofort-Aktion (read-only, gegated).

## 6 · Ehrlich: Was ist spec-bar, was braucht visuelle Iteration

**Hier verbindlich spec-bar (dieser Vertrag):** Mechanik + Semantik aller 9 Bausteine (APIs, Zustände,
Attribute, fail-closed-Regeln) · Wortlaute (Lexikon, Tooltips, Pill, Confirm-Formel, Leer-Formel) ·
Editions-Matrix als Code · IA-Struktur des TB-Cockpits (Räume, Statusband-Inhalt, Hierarchie-Ebenen) ·
Adoptions-/Test-Modell.

**Braucht visuelle Iteration mit David (Bau-KI-Rollout, je Feel-Check):** Dichte/Abstände der Netz-Leiste
im Popover · exakte Toast-Position/-Dauer · Gesperrt-Flächen-Größe (KPI-Maske vs. Voll-Panel je Kontext)
· Agentchip-Glyph · TB-Cockpit ALLES Visuelle (Raum-Reihenfolge, Statusband-Verdichtung, Baum-Optik) ·
Anrede-Feinklang einzelner Texte. Dieser Feel-Check braucht **kein separates Design-Gate** — er fällt
ohnehin im gegateten Live-Rollout an (UAC/Neustart je App; für das TB-Cockpit im eigenen TB-Chat). **Nicht
spec-bar und nicht versprochen:** dass die erste Pixel-Fassung „schön" ist — der Vertrag garantiert
Konsistenz + Verständlichkeit; Schönheit entsteht im Feel-Loop (docs/06-Historie zeigt: v1→v2 war Nutzer-Urteil).

## 7 · Bau-Plan (Bau-KI, nach 50 %; jedes Paket klein & einzeln grün-committbar)

| Paket | Inhalt | Abhängigkeit | Größe |
|---|---|---|---|
| **UX-0** | dieses Paket mergen (Kit-Dateien + appkit-Module + Tests) | — | fertig (Architektur-KI) |
| **UX-1** | Sweep F-4/F-5/F-6: `fehlerseite` aktiv lassen (Default), Tooltip-Katalog §3.5 einsetzen, Wording-Pass mit `pruefe_text` je App (inkl. KO-3-Button, MG-2-Texte, CR-3-Labels) | UX-0 | S je App |
| **UX-2** | F-3/F-7-Mechanik: ux-kit einbinden, `data-dz-offen`/`data-dz-kopf-klick`, Toast/Leer/Confirm an den belegten Stellen (NE-1/NE-2, ME-1/ME-2/ME-3, MO-2/MO-3, CO-2/CO-3) | UX-0 (G-UX-COLLAPSE ✅) | M |
| **UX-3** | F-1: `netz_router` je App aktiv + `DzUx.netzleiste` in alle 8 Köpfe + Core-Kachel-Kopf (CO-2-Rest) | UX-0 | S–M |
| **UX-4** | F-2: Money zuerst (MO-1 + Stats „gesperrt" ⇒ CO-1), dann Comm/Healthy-Abgleich auf die Matrix; Core-Panel rendert 🔒 | UX-0 | M |
| **UX-5a** | ⏱ **AI-Act-Vorziehung (Frist 02.08.2026):** `DzUx.agentchip({ki:true})` an ALLE Chat-/KI-Dialog-Flächen (Dizzi-Chat Core · Vault-Chat · Mini-Dizzi · Agenten-UIs). Erfüllt AI-Act Art. 50(1) (Chatbot-Offenlegung). Bewusst aus UX-5 herausgelöst, damit die Compliance NICHT hinter dem vollen F-8-Paket hängt. | UX-0 | S |
| **UX-5** | F-8-Vollausbau (Datumsnorm an allen Fundstellen NE-3/KO-5) + Anrede-Pass („du", G-UX-ANREDE ✅) + MG-1-Kopf/Panel-Nachzug + Agentchip an übrigen KI-erzeugten Flächen | UX-0 | M |
| **UX-6** | Login-Seite Core (MO-4: Erklärsatz · Registrier-Pfad · „Zurück zu {App}" via `zurueck`-Param) | UX-0 | S |
| **UX-T** | Trading gegated (eigener TB-Chat): Statusband + 5 Räume + Hierarchie-Baum (§5.2, G-UX-TB-COCKPIT ✅) + T5-Wording (§5.4) + TB-404 + TR-3-Tooltips | TB-Chat + Neustart | L |
Danach: **G-UX-LOGIN-Folge-Audit** (eingeloggte UX, mit David am Rechner — sinnvoll NACH UX-4, docs/60).

> **⏱ Termin-Merker (der „AI-Act-Hinweis"):** EU AI Act **Art. 50(1)** verlangt ab **02.08.2026**, dass
> jede KI-Chat-Oberfläche dem Nutzer klar sagt „du sprichst mit einer KI" (nicht in AGB versteckt).
> Unser fertiger Baustein dafür ist `DzUx.agentchip({ki:true})` (Chip „KI" + Tooltip „läuft lokal") ⇒
> **UX-5a** oben zieht genau das vor. (Die *zweite* AI-Act-Pflicht — maschinenlesbare Markierung
> KI-erzeugter Medien — greift erst 02.12.2026 und wird separat in Creatings Output-Pipeline behandelt,
> docs/58 §3.G G2 · P21.1 — NICHT Teil dieses UX-Pakets.)

## 8 · Test-Strategie

**In diesem Paket (liegen bei, appkit-Suite):** `tests/test_ux_vertrag.py` —
- **T-NETZ:** Verzeichnis vollständig (10 Apps), IDs/Ports einzigartig + verzeichnis-konform, URLs wohlgeformt, Router liefert JSON.
- **T-404:** HTML nur bei `Accept: text/html` UND Nicht-`/api/`-Pfad; `/api/*` + `*/*` liefern exakt das bisherige JSON; Marke + beide Ausgänge in der Seite; 200-Routen unberührt.
- **T-LOCK:** Matrix-Tabelle Edition×Klasse×Stufe (inkl. fail-closed bei Unbekanntem); `Summary` akzeptiert `gesperrt`; `gesperrt_summary` maskiert Werte („•••"), nie Zahlen; Verbots-Pin: gesperrt-Kachel trägt NIE „alles im grünen Bereich"-artige Texte (note-Pflicht).
- **T-WORT:** Lexikon übersetzt alle Kern-Einträge; `pruefe_text` findet HITL/DORMANT/§-Referenzen; kein Kunden-Label enthält selbst Insider-Begriffe; `datum_de`-Regeln (heute/gestern/Wochentag/Jahr + RFC822- und ISO-Parsing + Rohstring-Fallback).
- **T-TOKEN:** `ux-kit.css` existiert + enthält **keinen** Hex-Farbwert (`#rrggbb`-Lint, token-only); tokens.css trägt weiterhin alle Vertrags-Tokens beider Achsen; `ux-kit.js`/`collapse.js` tragen die Opt-in-Marker (`data-dz-offen`, `data-dz-kopf-klick`, `DzUx.`) — pinnt den Kit-Vertrag gegen versehentliches Weg-Refactoring.
**Im Rollout (Norm je App, Kardinalregel 10):** Scratch-Port + `preview_snapshot`/`preview_eval`:
(1) `DzUx.pruefeTooltips()` ⇒ 0 Funde, (2) genau EINE Sektion default-offen, (3) 404-Browser-Probe zeigt
die Seite / `curl -H "Accept: application/json"` zeigt JSON, (4) `pruefe_text` über die sichtbaren
UI-Strings der App ⇒ 0 Funde, (5) 0 Konsolenfehler. JS-Änderungen am Kit: Verifikation im Browser
(node ist auf dem System nicht verfügbar — kein `node --check`; dafür Marker-Pins in T-TOKEN).

## 9 · Invarianten (prüfbar)

1. Neue Kit-Dateien sind token-only (kein Hex) — T-TOKEN.
2. Ohne neue Attribute/Aufrufe rendert jede Bestands-App byte-identisch (Stufe-0) — Konstruktion + Rollout-Verifikation.
3. `/api/*` antwortet IMMER JSON, unabhängig vom Accept-Header — T-404.
4. `gesperrt`, `leer`, `fehler` sind DREI verschiedene, sichtbar verschiedene Zustände; gesperrt maskiert Werte und nennt den Weg (Anmelden-CTA) — T-LOCK.
5. Kein interaktives Element ohne Label/`title`+`aria-label` (Rollout-Gate je App via `pruefeTooltips`).
6. Sichtbare Kunden-Texte sind frei von `INTERNA_MUSTER` — `pruefe_text` in Tests + Rollout.
7. Anmelde-Pille hat netzweit EINEN Wortlaut (§3.8).
8. Jede KI-/Agenten-erzeugte Fläche trägt Herkunft (Agentchip) — spätestens mit UX-5 (AI-Act 50(1): 02.08.).
9. apps/trading bleibt in diesem Paket byte-unverändert (read-only) — `git diff` beweist.

## 10 · David-Gates — ✅ ALLE BEANTWORTET (04.07.2026)

| Gate | Frage | Entscheid (David 04.07.) |
|---|---|---|
| **G-UX-COLLAPSE** | F-3-Norm-v2: ganzer Panel-Kopf klickbar (ersetzt docs/06 §6.3 „nur Chevron", 14.06.) + je App EINE Default-offene Kern-Sektion? Glow-Disziplin bleibt. | **✅ JA** — Kopf-Klick + Default-offene Kern-Sektion umsetzen; Glow-Disziplin bleibt unangetastet. Damit ist der Supersede docs/06 §6.3 → docs/70 §3.3 **aktiv**; UX-2 ist entsperrt. |
| **G-UX-ANREDE** | Netz-Anrede „du" (Healthy-Ton) statt Sie/Misch? | **✅ „du"** — netzweite Anrede-Norm; `sprachregister.ANREDE = "du"` gilt. Sie-Reste (Dizzi-Chat) im UX-5-Wording-Pass mitziehen. |
| **G-UX-TB-COCKPIT** | Cockpit-IA §5.2 (Statusband + 5 Räume + König→Ensemble→Flotte-Baum) als Bau-Grundlage für UX-T? | **✅ delegiert an Architektur-KI → Struktur ANGENOMMEN** (David 04.07.: „überleg selbst, mach's"). Die IA-Struktur ist die verbindliche Bau-Grundlage. **Der visuelle Feel-Check braucht KEIN separates Gate mehr** — er passiert ohnehin IM UX-T, weil das eine Live-TB-Änderung mit Davids UAC + gegatetem :8137-Neustart ist (TB-Chat). Das natürliche TB-Gate deckt den Feel-Check ab. |
| **G-UX-AUTH** | (früher beantwortet) Editions-Sichtbarkeits-Politik | ✅ als Code in `sichtbarkeit.py` (Matrix §3.2). |
| **G-UX-LOGIN** | (früher beantwortet) eingeloggte-UX-Folge-Audit | ✅ Folge-Audit sinnvoll NACH UX-4 (mit David am Rechner). |

**⇒ Kein Gate blockiert mehr irgendein Rollout-Paket.** Der gesamte Bau-KI-Rollout UX-1…UX-T ist
freigegeben; einzige verbleibende Tore sind operativ, nicht Design: Davids UAC/Neustart je Live-App
(Kardinalregel 6) und für UX-T zusätzlich der eigene TB-Chat (Kardinalregel 5).

## 11 · Berührte Dateien & Doku-Sync

**Neu (dieses Paket):** `docs/70` (diese Datei) · `packages/ui-kit/ux-kit.css` · `packages/ui-kit/ux-kit.js`
· `packages/appkit/netz.py` · `packages/appkit/fehlerseite.py` · `packages/appkit/sichtbarkeit.py`
· `packages/appkit/sprachregister.py` · `packages/appkit/tests/test_ux_vertrag.py`.
**Additiv erweitert:** `packages/ui-kit/collapse.js` (Opt-in-Attribute) · `packages/ui-kit/controls.css`
(F-3-Anhang, attribut-gescoped) · `packages/appkit/summary.py` (+`gesperrt`) · `packages/appkit/app.py`
(Parameter `fehlerseite`/`netz`, Default wertgleich für API-Clients).
**Doku-Sync (klein, additiv):** docs/06 §6.3 erhält Supersede-Verweis auf docs/70 §3.3 (gegated via
G-UX-COLLAPSE) · docs/60-Fazit erhält 1-Zeilen-Verweis „Bausteine + Rollout = docs/70" · docs/README-Index.
**Unberührt:** alle `apps/**`-Frontends (insbesondere `apps/trading` — 0 Byte) · alle bestehenden
Kit-Dateien außer den zwei genannten additiven Anhängen · Core.
