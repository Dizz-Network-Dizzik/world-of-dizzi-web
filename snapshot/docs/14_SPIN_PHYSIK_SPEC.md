# Spin-Physik — Kanonische Spezifikation (für ALLE Apps) · Stand v4.5, 20.07.2026

> **Status: FESTGESCHRIEBEN & vom Nutzer abgenommen — inkl. v4.1/v4.2/v4.3 (Abnahme
> 12.06. abends: „passt, das übernehmen wir so für alle fliegenden Objekte — unsere
> coole Spielmechanik in allen Apps").** Diese Mechanik wird in jeder App **identisch**
> umgesetzt. Referenz-Implementierung liegt fertig vor — neue Apps **kopieren** sie
> nur noch und hängen sie an (kein Neu-Erfinden). Rollout-Paket: docs/11 §5 R-ROLLOUT.
> **v4.4 (DzHalter, Davids Idee 12.07.): GEBAUT + isoliert verifiziert 15.07.;
> Feel-/Optik-Abnahme = Gate G-HALTER-OPTIK, Live-Rollout = G-HALTER-LIVE.**
> **v4.5 (Icon-Fix netzweit, 20.07.): angedockte Floats werden bei `anmelden()` in eine
> body-fixe saubere `.dzh-floatlayer` (z 60 > Schale 59, `pointer-events:none`) gehoben —
> der Body-Ebene-Invariant ist damit ERZWUNGEN statt gehofft; Icons sitzen oben auf der Mulde
> + bleiben voll klickbar, robust gegen jede App-DOM (Audit: uniformer z-Gap 41<59, nicht
> transform-Vorfahren). React-Floats melden sich via `data-dzh-hoist="off"` ab (Shell z-60 schon
> korrekt). GEMERGT + LIVE (`0269456c`), appkit 630 grün (+5 T-HALTER), live verifiziert;
> G-HALTER-LIVE vollzogen (Dev-Maschine, Shell-Rebuild + disk-served).**

## 1. Referenz-Code (kopieren, nicht neu bauen)
- **Panel-Spin-Mechanik**: `the world of dizzi/shell/src/spinFling.ts`
  (`initSpinFling({ gridSelector, cardSelector, floatSelector, onReorder })`, framework-neutral,
  rein transform-basiert). Mounten: einmal nach dem Rendern der Panels; jede Karte trägt
  `data-pid`; `onReorder(a,b)` **tauscht** die Plätze + persistiert die Reihenfolge.
- **Schwebender Knopf** (Settings/Account): `the world of dizzi/shell/src/FloatingSettings.tsx`
  — Schleuder-Slingshot + weicher Kurven-Drift + `dizzi:fling`-Empfang (wird vom Panel gekickt).
- **✅ Trading Bot (vanilla JS) — portiert (11.06.2026):** `initPanelDrag`/`honeyTick`/`beginDrag`/
  `reorderByPointer`/`finishSettle` (Honig-Lag) abgelöst durch `initSpinFling`/`sfDown`/`sfTick`/
  `sfSwap` in `Trading Bot eins/programm/backend/app/static/index.html` (gleicher Algorithmus + Feel-
  Parameter wie `spinFling.ts`; Floating-Target `#iconLegend` empfängt `dizzi:fling`; Scroll-Lock-Fix
  aktiv; Lift-Optik via `.spinlift`-CSS statt `.pdrag`). Funktional verifiziert (Grab/Lift/Lock/Swap/
  Persistenz/Fling); Feel beurteilt der Nutzer im Browser. (Kein `main::after`-160vh beim TB — s. §4:
  der Scroll-Lock ist der eigentliche Fix; der 160vh-Freiraum ist nur für KURZE Seiten gedacht.)
- **✅ App-Gerüste — Referenz verteilt (11.06.2026):** jede der 8 Apps (archiv, buerokratie, creator,
  finanzen, health, news, projekte, social-media) hat `ui-kit/` mit byte-identischer `spinFling.ts` +
  `FloatingSettings.tsx` (Template) + `README.md` (Einhäng-Checkliste, welche 3 Imports umzuverdrahten
  sind). Beim Frontend-Bau nur noch nach `shell/src/` kopieren und mounten.
- **✅ VANILLA-REFERENZPFAD (13.06.2026, via News-Port):** Apps OHNE React-Shell (Vanilla-
  `static/index.html`) kopieren NICHT über `shell/src/`, sondern vom **Dizz-News-Frontend**
  (`news/static/index.html`) — erster vollständiger R-ROLLOUT-Port: Spin v4.3 auf Karten
  (`.wrap > .card`), **gemeinsamer Float-Treiber `initFloat(id, regKey, onTap, pausiert)`**
  (Drift/Zwille/Abprall/Wrap/`dizzi:fling`, DRY für beliebig viele Floats), `#kontoModal`
  nach docs/19 §2b (alle 5 Gotchas), Mini-Dizzi-Sprechblase `#floatDizzi`. Der ältere
  TB-Port bleibt kanonisch fürs FEEL, mischt aber Domäne + Mechanik auf 3400+ Zeilen —
  **für Kopien News als Vorlage nehmen** (Komm = nächster Abnehmer). Offen (World-Chat,
  beim nächsten Rollout): app-neutralen Vanilla-Bundle (spin+float+modal) nach `ui-kit/`
  extrahieren + README um den Vanilla-Pfad ergänzen.
- **✅ DzHalter v4.4 (15.07.2026, WA):** `packages/ui-kit/float_dock.{js,css}` NEU +
  Modus-Weiche synchron in `floats.js` und `FloatingSettings.tsx` (Template **und**
  `shell/src/`) — verdrahtet in allen 8 Apps + refapp + Shell (Trading = TB-Chat, s. U3);
  Memory-Allowlist + Core-`/ui-kit`-Whitelist erweitert (greifen mit gegatetem Neustart).
  Details §2 v4.4; Vertrags-Tests: `appkit/tests/test_ux_vertrag.py` (T-HALTER).

## 2. Verhalten (so fühlt es sich an — abgenommen)
**Greifen:** Am Greifpunkt entsteht eine **harte Achse**, die exakt am Cursor klebt (kein Wobble);
einziger Freiheitsgrad ist die **Drehung**. Über **GRAB_EASE_S (0,7 s)** bauen sich Hebel +
Gravitation sanft auf → kein Start-Zappeln; der verlagerte **Schwerpunkt** sinkt und das Panel
**baumelt/schwingt** wie an einem Nagel. Bewegen der Achse schaukelt das Schwingen auf → Schleudern.

**Icon-Kick (beim Schwingen):** Trifft das gehaltene/geschwungene Panel das schwebende Element,
wird die **Oberflächen-Geschwindigkeit am Kontaktpunkt** (`v_Achse + ω × r`) als Impuls kopiert
(`dizzi:fling`-Event) → das Element fliegt weg. Leichte Berührung (< KICK_MIN) kickt nicht.

**v4.1 (12.06.2026, Nutzer-Entscheid) — drei verbindliche Ergänzungen:**
1. **Exakte Panel-Hitbox:** Kollisionen (Kick beim Schwingen + Abprall der Floats) rechnen gegen
   das **ECHTE Panel-Rechteck, auch gedreht** — das Float-Zentrum wird ins Panel-System gedreht
   und dort gegen die ungedrehten Halbmaße geklemmt (`kreisVsPanel`/`panelWinkel` in spinFling.ts;
   vanilla: `panelKreisStoss` im TB). Die alte Achsen-AABB des schrägen Panels war größer als das
   Panel und traf „durch die Luft". Ungedrehte Panels behalten den exakten AABB-Abprall.
2. **Doppelicon-Knopf:** Einstellungen + Konto/Sicherheit sind EIN verschmolzenes schwebendes
   Element (Zahnrad führt, Schild dockt unten rechts an, Magenta-Akzent) — Größe einheitlich
   **96-px-Kreis, Haupticon 44 px** (wie „the world of dizzi"). Tipp aufs Doppelicon öffnet
   Einstellungen & Konto.
3. **Float↔Float-Abprall:** Schweben MEHRERE Elemente (TB: Icon-Legende + Doppelicon), prallen
   sie **voneinander ab** und übertragen beim Zusammenstoß **jeweils ihr halbes Momentum** entlang
   der Stoß-Normalen (der Stoßer prallt mit halber Wucht zurück, der Getroffene nimmt die Hälfte
   mit; Tangential-Anteil bleibt). Ein GEHALTENES Element schiebt das freie weg. Referenz:
   `FLOATREG`/`floatAbprall` im TB-Frontend.

**Loslassen = SOFORT Schluss:** Achse/Schwerpunkt verschwinden augenblicklich, **kein Nachflug**.
- Über einem **anderen Panel** losgelassen ⇒ **sofortiger Platz-Tausch** (swap) + Stillstand.
- Im **freien Raum** losgelassen ⇒ **sofort zurück** auf den eigenen Platz (180 ms).

**v4.2 (12.06.2026 abends, Nutzer-Entscheid) — Klappzeilen-Norm (gilt app-übergreifend):**
Auf-/Zuklappen ist **AUSSCHLIESSLICH** Sache des **Toggle-Icons vorne** an der Klappzeile —
der Rest der Zeile (und des Panels) ist **Greiffläche** für die Spin-Physik.
1. **Icon groß & deutlich:** eigener Knopf-Look, **30×30 px** (Rahmen + Neon-Glow, radius 9 px),
   Chevron innen; Hover hellt NUR das Icon auf. Designdetails dürfen je App variieren,
   die Größe nicht.
2. **Klick-Zone (FOLDZONE = 44 px ab Zeilen-Anfang):** Klicks außerhalb togglen NICHT
   (preventDefault auf dem summary-Klick); Tastatur-Aktivierung (`event.detail === 0`)
   togglet weiterhin (Barrierefreiheit). Buttons/Links in der Zeile behalten ihr Verhalten.
3. **Greifen statt Toggle:** `summary` ist NICHT mehr in der INTERACTIVE-Sperrliste des
   Spin-Grabs; Pointerdown in der FOLDZONE greift nicht (Toggle-Klick), überall sonst
   startet das Greifen. Cursor auf Panel-Klappzeilen: `grab`/`grabbing`.
4. **Klick-Schlucker nach echtem Drag:** nach einem Lift (> LIFT_THRESH) wird der
   nachlaufende `click` einmalig unterdrückt (capture, 250-ms-Fallback) — sonst klappt
   das Loslassen über einer Klappzeile noch etwas auf.
   Referenz: TB `static/index.html` (FOLDZONE/inFoldZone + sfDown/sfUp).

**v4.4 (15.07.2026, Davids Wort 12.07.) — „DzHalter": Andock-Schale + Frei/Fix-Schalter:**
Die Drift-Objekte sind STANDARDMÄSSIG in einer kleinen Halterung oben rechts befestigt.
1. **Modul `packages/ui-kit/float_dock.{js,css}`** (`window.DzHalter`): globaler Modus
   `dz_floats_modus ∈ { angedockt, frei }` (localStorage je App-Origin; **Desktop-Default
   = angedockt**; Mobile-Verhalten = Gate G-HALTER-MOBILE, bis dahin ein Default überall).
   Die Schale ist `position:fixed` oben rechts (`--dzh-top`/`--dzh-right` per App-CSS
   übersteuerbar — App-Lane prüft die Top-Right-Kollision), body-level (kein transform-
   Vorfahr, §-v4.3-Regel gilt), z-index UNTER den Floats; je angemeldetem Float eine Mulde
   (`.dzh-slot`, Maß = Float-Maß) + der Frei/Fix-**Schalter** (30×30-Icon-Norm v4.2,
   Schloss-SVG zu/auf, `role="switch"`, token-/design-farbig). Umschalten schreibt
   localStorage + `body[data-floats]` und feuert `dizzi:floatsmodus` (CustomEvent).
2. **Modus-Weiche in `floats.js` + `FloatingSettings.tsx` (BEIDE synchron halten):**
   angedockt = Float sitzt auf der Slot-Mitte (Physik aus, folgt der Mulde bei Resize;
   Mulden-Optik via `data-belegt`) · frei = v4.3 unverändert · beim Freilassen startet
   jeder Float mit dem sanften Zufalls-Impuls aus `rel()` (cos·5 / sin·2.5).
3. **Der Rückflug (frei → angedockt):** Federzug zur Slot-Mitte
   `v += (ziel − pos) · K_HOME` mit **K_HOME = 0.02**, Dämpfung **FR_HOME = 0.85**;
   **Einrasten** bei Distanz < **SNAP = 6 px** (Position exakt, v = 0, lgshoot-Puls).
   Der Heimflug ignoriert Panel-Abprall, Float↔Float-Abprall, Drift und Screen-Wrap
   (fliegt frei heim), **respektiert aber `paused()`**; der FLOATREG-Abprall läuft
   generell nur noch über FREIE Floats (`frei()`-Hook, rückwärtskompatibel).
4. **Öffnen ist Pflicht (docs/19 §2b) in JEDEM Modus:** angedockt blockt nur Greifen
   (`pointerdown`) und `dizzi:fling`; der Klick öffnet über den click-Fallback (vanilla)
   bzw. den onClick-Fallback (React — deckt auch reduced-motion).
5. **reduced-motion:** DzHalter inert (keine Schale, `anmelden()` ⇒ null) — Floats wie
   bisher statisch. Ohne `float_dock.js` (z. B. altes Deployment) gilt exakt v4.3.

**v4.3 (12.06.2026 abends, Nutzer-Entscheid) — Float-Regeln (alle Drift-Objekte):**
1. **Kein Scrollbar-Flackern:** Drift-Objekte sind `position:fixed` und liegen auf
   **BODY-EBENE** (NIE in einem Vorfahren mit backdrop-filter/transform — der würde zum
   Containing Block, und der Überstand beim Screen-Wrap rechts erzeugte eine flackernde
   horizontale Scrollbar; Live-Vorfall TB: Doppelicon im Glas-`<header>`). Zusätzlich
   härtet `html,body{overflow-x:clip}` gegen JEDES seitliche Überstehen ab (clip statt
   hidden: kein Scroll-Container).
2. **Leichter Abstoß statt Dauer-Klappern:** bei Berührung zweier freier Floats gibt es
   zusätzlich zum Halbmomentum-Stoß IMMER einen **leichten** Schubs auseinander entlang
   der Stoß-Normalen (FLOAT_SEP ≈ 0,9 px/Frame ≈ Drift-Tempo) — sonst hält das Auto-Drift
   beide in Dauer-Berührung. Betonung: LEICHT, kein Wegschleudern.
3. **Generalisiert auf N Floats:** die Float↔Float-Kollision läuft paarweise über ALLE
   registrierten Drift-Objekte (TB: `FLOATREG` + `floatPaarStoss`); neue schwebende
   Elemente docken nur noch per Registry-Eintrag an.

## 3. Physik-Modell (in spinFling.ts umgesetzt)
Starrkörper-Pendel an bewegtem Pin; Pose jede Frame aus Pin + θ (dt-basiert, dt ≤ 32 ms):
`I = r·r + (w²+h²)/12` · `α = (r.x·G·ease + (r.y·a_x − r.x·a_y)) / I` ·
`ω += α·dt`, exponentiell gedämpft (HOLD_ANG_DAMP) · θ += ω·dt. Clamp `|ω| ≤ OMEGA_MAX`,
NaN-Guards. Achsen-Geschw./-Beschl. aus der Cursor-Bewegung geglättet.

## 4. Stabilität & Bekannte-Bugs-Fix (Pflicht beim Port)
- **NIE eine CSS-`transition` auf `transform` der Panel-Karte (`.card`)** — Wurzel des Core-Swing-
  Bugs (14.06.2026). Die Physik setzt das `transform` JEDEN Frame direkt; eine CSS-Transition darauf
  lässt das **gerenderte** Panel der Physik um die Transitions-Dauer **nachhinken**, während der
  Icon-Kick (`collideFloat` rechnet gegen die un-verzögerte Physik-Mitte `b.mx/b.my`) bereits dort
  trifft, wo das Panel *sein müsste* ⇒ das sichtbare Panel verrutscht von seiner Hitbox, das Float
  wird „durch die Luft" gekickt. Vanilla-`.card` (news/static/index.html) transitioniert `transform`
  aus genau diesem Grund **nicht** (nur `border-color`/`box-shadow`/`opacity`). Das Snap-Zurück beim
  Loslassen läuft über die **Inline**-Transition in `reset()`/`sfReset()` (`transform 180ms`), die die
  CSS-Regel für ihr Fenster überschreibt — nicht über eine `.card`-CSS-Transition. **Symmetrisch für
  jede künftige physik-getriebene Spin-Fläche.**
- **Scroll-Lock während des Haltens**: `overflow:hidden` auf `html`+`body`, Restore beim Loslassen
  → ein schräges Panel am unteren Rand kann die Seite **nicht vergrößern/verschieben** (Greifpunkt
  bleibt stabil). **Das ist der eigentliche Fix.** *Optional* — nur für **kurze** Seiten — zusätzlich
  großzügiger Scroll-Raum (`main::after { height: 160vh }`, wie in Dizzi); bei **langen** Content-Seiten
  (z. B. Trading Bot) **weglassen**, sonst entsteht totes Leerfeld unter dem Interface.
  - **Grid-Lock NUR bedingt (Regression-Fix 18.06.2026):** Gegen Scrollbar-Flackern beim
    Aus-dem-Bild-Schwingen sperrt `sfLock` zusätzlich das **Grid** — aber **nur, wenn das Grid
    selbst ein Scroll-Container ist** (`getComputedStyle(grid).overflowX/Y` ∈ {`auto`,`scroll`},
    z. B. `main{overflow:auto}`). Ein schmaler, zentrierter `overflow:visible`-Container (`.wrap`)
    wird **nicht** gesperrt: `overflow:hidden` hätte dort die schwingenden Panels in den engen
    Kasten geclippt (außen schwarz). So bleibt `html`+`body` der universelle Lock (Panels schwingen
    auflösungs-adaptiv über den ganzen Viewport, kein Seiten-Scrollbar), und der Grid-Lock greift
    nur dort, wo er das Flackern wirklich verhindert. Entsperrt wird erst ~220 ms nach dem Loslassen
    (nach dem 180 ms-Snap-Zurück), damit auch das Zurückschnappen nicht flackert.
- `prefers-reduced-motion` ⇒ Mechanik aus (statisch). `visibilitychange:hidden` ⇒ laufende Geste
  sauber beenden.

## 5. Feel-Parameter (abgenommene Startwerte — oben in spinFling.ts)
`G=2400 · COM_PUSH=1.8 · COM_INSET=0.12 · GRAB_EASE_S=0.7 · HOLD_ANG_DAMP=1.1 · OMEGA_MAX=14 ·
LIFT_THRESH=5 · KICK_MIN=60 · TRANSFER=1.0`. Schwebe-Drift (FloatingSettings): Steuer-Richtung
alle 2,6–5,2 s, `DRIFT_TURN=0.012` (lange weiche Kurven), `FR=0.994`.
DzHalter-Rückflug (v4.4): `K_HOME=0.02 · FR_HOME=0.85 · SNAP=6px` (floats.js + FloatingSettings).

## 6. Aufsetzen in einer neuen App (Checkliste)
1. `spinFling.ts` + den schwebenden Knopf (Settings/Account) aus Dizzi übernehmen.
2. Panels mit `data-pid` versehen; `initSpinFling(...)` nach dem Render mounten; `onReorder` = swap+persist.
3. Floating-Element so bauen, dass es `dizzi:fling`-Events empfängt (Slingshot + Drift wie Dizzi).
4. Scroll-Lock-Fix + `main::after`-Freiraum übernehmen.
5. Design-Baseline (A2): Mattglanz-Metall, Cyan/Magenta, scharfe Kanten.
