# 32 · KERN-DAUERSCHLEIFE (über Nacht) — totale Durchleuchtung + Verstehen + Hinterdenken + **Funktions-Beweis (live antouchen)** + Verbesserungs-Recherche

> **★ DAS ULTIMATE-TOOL (Nutzer-Klarstellung 27.06.2026):** Diese Schleife ist der *ultimative, fortlaufend verfeinerte
> Generalbefehl* des Netzes — das eine Werkzeug, mit dem „the world of dizzi" von **allen Seiten** durchleuchtet wird:
> **jede App einzeln · jedes Modul einzeln · jede Verbindung zwischen den Modulen · jede Funktionalität** — und seit dem
> 27.06. nicht mehr nur *gelesen/verstanden*, sondern **funktionell angetoucht** (Brille 8, §0.6 R8): real ausgelöst und
> in Aktion gesehen. **Anspruch:** dass **kein Fehler, keine Ineffizienz, keine Unreinheit** dem Gesamtplan durchschlüpft.

> **Wesen (Nutzer-O-Ton, verbindlich):** EINE abrufbare Dauer-Routine, die das Gesamtkonstrukt
> „the world of dizzi" **von ALLEN Seiten absolut durchleuchtet** — nicht stichprobenhaft abhakt,
> sondern jede App, jeden Code-Pfad, jede Funktion/Verknüpfung, jede Segment-Interaktion, jede
> Cross-App-Kante (V2–V19), jeden Sorgfaltskern, Kit/appkit, Daten/Sicherheit/Recht **erst
> ERFASST, dann WIRKLICH VERSTEHT, dann sinnig HINTERDENKT** — und das Ganze fest gegen das
> **Gesamtziel des ultimativen Produkts** (§0.5 North-Star) wiegt. Eingebaut: eine **parallele
> Verbesserungs-Recherche** (2026-Stand) + ein **Abgleich Absicht-vs-Realität** („haben WIR etwas
> vergessen?") + eine **Effizienz-/Architektur-Linse** + (neu) eine **Perspektiv-Rotation jede 2.
> Runde** (§0.6). Jeder Lauf **akkumuliert** Fortschritt: er liest das letzte Runden-Fazit + den
> offenen Backlog und macht DORT eine Ebene tiefer weiter — **nie nur „clean" re-bestätigen.**
>
> **Drei Bewegungen, immer in dieser Reihenfolge — das Herz der Schleife:**
> 1. **ERFASSEN** — alles aufnehmen/enumerieren (was existiert: Routen, Module, Funktionen,
>    Datenmodell, Frontend, MCP, Kanten, dormante Slots). Vollständig, nicht selektiv.
> 2. **VERSTEHEN** — die *Funktionsweise* je Teil so durchdringen, dass ich Zweck, Datenfluss,
>    Invarianten **end-to-end in eigenen Worten erklären** kann. Kann ich es nicht erklären → tiefer
>    lesen, bis ich es kann. (Verstehen ist die Voraussetzung; ohne es ist jeder Befund Raten.)
> 3. **HINTERDENKEN** — das kritische Nach-Denken auf Basis des Verstandenen. Die **vier
>    Killerfragen** an JEDES Teil: (i) **Vergessen?** Fehlt ein Feature/eine Funktion/ein Slot, den
>    unsere eigene Vision/Plan/Doku verspricht oder den die Referenzklasse 2026 hat? (ii) **Falsch/
>    fragil?** Ist funktional/coding-seitig etwas nicht ideal (Bug, Edge-Case, fragiler Pfad)?
>    (iii) **Ineffizient?** Wo wird unnötig Arbeit getan (Algorithmus, Query, Redundanz, Duplikat,
>    fehlendes Caching, Doppel-Code, der ins shared-Kit gehört)? (iv) **North-Star?** Bringt das das
>    Produkt näher an das ultimative Ziel (§0.5) — und wenn nicht, **was würde es?**
>
> **Trigger:** sagt der Nutzer sinngemäß „die **große Kern-Dauerschleife über Nacht** laufen
> lassen" (o. ä.), gilt GENAU dieser Ablauf — **ohne Rückfrage**. Kanonisch + Gedächtnis
> [[kern-dauerschleife]]. Festgehalten 20.06., perfektioniert 20.06., **vertieft 22.06.2026**
> (Verstehen-zuerst + North-Star + TB-Vollintegration + Effizienz-Linse + Perspektiv-Rotation).
>
> **Abbruch nur auf Nutzer-„Stopp".** Standard = mehrere Durchläufe hintereinander (Default 2, wenn
> nicht anders gesagt); nach jedem Lauf Doku-Sync + **sofort weiter, eine Ebene tiefer** (§9.5).

---

## §0 · Geltungsbereich + das Vollständigkeits-Prinzip

**Apps (alle Live):** news · finanzen/Money · archiv/Memory · kommunikation/Communication ·
creator/Creating · social-media/Management · health/Healthy · admin/Dizz Admin · **Core**
**· + Trading Bot / „Dizz Trading" (:8137)** — VOLLES Analyse-Subjekt jeder Runde.

**Trading Bot — voll durchleuchten, aber read-only:** TB wird **jede Runde gleichberechtigt
erfasst, verstanden, hinterdacht, recherchiert und (read-only/Scratch) getestet** — kein Abstrich,
obwohl er schon sehr tief gebaut ist (gut gebaut ⇒ dann werden eben selten Funde auftauchen, und
das ist ein gültiges, ehrliches Ergebnis). **ABER:** TB ist eigener Stack + eigener Trainings-Chat
⇒ die Schleife **ändert nichts am TB-Repo und startet `:8137` nicht neu** (beides bleibt
TB-Chat-Domäne + ausdrücklicher Nutzer-Go). TB-Funde → **Backlog (docs/33) + eine ausdrückliche
„→ TB-Chat"-Übergabe-Notiz**. TB-Tests laufen read-only in TBs **eigenen** venvs (`programm\.venv`
Backend / `engine\.venv` Engine — Gotcha venv-Trennung), nie gegen Live-Daten; gegen Test-Pollution
`TBT_NO_STARTUP=1` setzen (sonst triggert die Suite den echten Backend-Lifespan).

**Vollständigkeits-Prinzip:** Die Schleife ist **enumerativ**, nicht stichprobenartig. Für JEDEN
Durchlauf: jede App · jede Querverbindung (docs/26 + docs/34) · jeder Sorgfaltskern · jeder Quer-/
Infra-Punkt wird **explizit erfasst, verstanden, hinterdacht und abgehakt** (§10 = Abhak-Garantie).
Bewusst Übersprungenes (z. B. repo-locked) wird **namentlich vermerkt**, nie stillschweigend
ausgelassen. **„Verstanden" ist ein Abhak-Kriterium, nicht nur „geprüft":** ein Punkt gilt erst als
berührt, wenn ich seine Funktionsweise erklären könnte.

---

## §0.5 · DER NORTH-STAR — das Gesamtziel, das NIEMALS vergessen wird

> Jede Runde beginnt damit, sich das **Endbild** zu vergegenwärtigen, und endet damit, jeden Befund
> dagegen zu wiegen. Das ist kein Deko-Satz, sondern die **Mess-Rubrik** der Schleife. Quelle:
> docs/00 (Vision) · docs/01 (Grundgesetze) · docs/11 (Gesamtplan) · docs/35 (Konnektivität) +
> Gedächtnis [[world-of-dizzi-stand]].

**Das ultimative Produkt — die Facetten (gegen JEDE wird gewogen):**
1. **Vollständig & umfangreich** — alle versprochenen Fähigkeiten existieren und sind verdrahtet; keine halben/vergessenen Fäden.
2. **Flexibel** — austauschbar/erweiterbar (Adapter-Slots, swappbare Modelle, Konnektor-Gerüst, Token-Achsen), nichts hart verdrahtet, wo es offen sein sollte.
3. **Professionell & sauber gecodet** — strukturell, nachvollziehbar, verkaufs-/übergabefähig (Gesetz 4).
4. **Effizient** — kein unnötiger Aufwand (Algorithmen, Queries, Speicher, Doppelarbeit); skaliert.
5. **Systematisch aufgebaut** — EIN Kit, EIN Vertrag, EIN Muster netzwerkweit; 0 Drift; Konsistenz vor Sonderwegen.
6. **Detailtief & verfeinert** — bis in die Edge-Cases poliert; nichts „läuft schon irgendwie".
7. **Eigene Verteidigungssysteme** — defense-in-depth (appkit/defense, Security-Header, CSP voll-strikt, fail-closed HITL, Rate-Limits) sind echt scharf, nicht nur vorhanden.
8. **Hochsicherheits-Datenlagerung** — Tresor Fernet-at-rest + OS-Secret-Store + Dizzi-ID-Step-up + `hoechst`⇒lokal_only + Hochsicher-Gate (extern gesperrt) halten Daten **absolut** sicher.
9. **Konnektivität als Kernziel** — alles connectbar, pro App ein zusammenlaufender Nachrichten-Strom, pro Kontakt kanalübergreifend (docs/35).
10. **UX-Exzellenz** — finale, ruhige, systematische Oberfläche (§5d-Phase; Werkzeug = Panel-Bautool); EIN Kopf-Standard, einheitliche Glows.
11. **Datenhoheit** — Daten bei der Quelle, DSGVO „weg = weg", lokal-first.

**Anwendung:** Jeder Befund/Vorschlag bekommt im Backlog einen **North-Star-Bezug** („hebt Facette
X"). Findet die Schleife **keine** Bug-Wins mehr, fragt sie aktiv: *Welche Facette ist am
schwächsten ausgeprägt — und welcher konkrete Schritt würde sie heben?* (= Anti-Leerlauf, §9.5).

---

## §0.6 · PERSPEKTIV-ROTATION — jede 2. Runde eine hart andere Brille (Nutzer-Wunsch 22.06.)

> **Warum:** Eine einzige Betrachtungsweise (der gründliche Standard-Ingenieur) hat blinde Flecken —
> sie findet, wonach sie strukturell sucht. Um das Netz **wirklich von allen Seiten** zu sehen,
> wechselt die Schleife **bei jedem zweiten Lauf** (wenn mehrere am Stück laufen) **hart die
> Perspektive**: sie nimmt bewusst eine fremde Rolle/Denkhaltung ein und durchläuft dieselbe
> enumerative Abdeckung (§0–§10) **durch diese Brille** — die vier Killerfragen werden von der Rolle
> neu gerahmt. Ziel: Funde aufdecken, die die Standard-Linse systematisch übersieht.

**Mechanik:**
- **Ungerade Läufe (1, 3, 5, …) = STANDARD-Linse:** der gründliche Ingenieur (Verstehen → Hinterdenken
  → North-Star), wie oben. Geht in der Tiefe weiter, wo der letzte Standard-Lauf aufhörte.
- **Gerade Läufe (2, 4, 6, …) = PERSPEKTIV-Lauf:** nimm die **nächste Rolle aus dem Roster** (zyklisch),
  **deklariere sie explizit zu Beginn des Laufs** („PERSPEKTIVE Lauf N: <Rolle> — Leitfrage: …"), und
  prüfe das ganze Netz durch DIESE Brille. Die Rolle ersetzt nicht die Abdeckung (§10 bleibt Pflicht),
  sie **rahmt die Fragen um**.

**Perspektiv-Roster (zyklisch; je Rolle die Leitfrage):**
1. **Angreifer / Red-Team** — „Wie breche/missbrauche ich das? Wo umgehe ich ein Gate, exfiltriere
   Daten, schmuggle Injection (CSV/MD/Prompt), erzwinge einen Zustand, den der Entwickler nicht bedacht
   hat?" (Fokus: Facetten 7+8 — Verteidigung, Hochsicher-Lagerung, HITL-fail-closed, Hochsicher-Gate).
2. **Produkt-Skeptiker / neuer Nutzer** — „Ich sehe das zum ersten Mal. Was verwirrt mich? Was fehlt
   offensichtlich? Würde ich dafür zahlen? Wo wirkt die App dumm/unfertig gegenüber der 2026-Referenzklasse?"
   (Fokus: Facetten 1+6+10 — Vollständigkeit, Verfeinerung, UX/Verkaufbarkeit; speist §6b + §6c).
3. **Zukunfts-Architekt / Skaleur** — „In 12 Monaten mit 100× Daten, Multi-User, 20 Konnektoren — was
   bricht zuerst? Welche heute bequeme Entscheidung wird zur Sackgasse? Wo fehlt Entkopplung/ein Slot?"
   (Fokus: Facetten 2+4+5 — Flexibilität, Effizienz/Skalierung, Architektur; speist §7.5).
4. **Rechts- / Datenschutz-Auditor** — „Wo verarbeite ich personenbezogene/sensible Daten ohne
   Rechtsgrund/Löschpfad? Hält jeder Disclaimer (Steuer/Health/Studium = keine Beratung)? Verlässt
   irgendwas unbemerkt das Gerät? Greift `on_delete`/`purge` wirklich überall?" (Fokus: Facetten 8+11).
5. **Chaos- / Ausfall-Ingenieur** — „Was, wenn Ollama weg ist, der Core offline, die DB gelockt, die
   Platte voll, ein Cross-App-Ziel 500 wirft, ein Subprozess hängt? Degradiert alles sauber (best-effort)
   oder crasht/korrumpiert etwas?" (Fokus: Robustheit, Fehlerpfade, fail-safe — §2B, §3, RAG/Defense).
6. **Wartungs-Erbe** — „Ein fremder Entwickler erbt das morgen ohne mich. Versteht er Modul X in 5 min?
   Ist die Absicht dokumentiert, die Namensgebung klar, der Sorgfaltskern selbsterklärend? Wo ist
   verstecktes Wissen, das nur im Kopf existiert?" (Fokus: Facetten 3+5 — Professionalität, Übergabe).
7. **★ Software-Visionär / Perfektions-Fanatiker** (NEU 27.06.2026, Nutzer-Wunsch) — die eine Brille,
   die bewusst NICHT fragt „ist es kaputt?" (das decken 1–6 ab), sondern **„ist es das BESTE, was
   technologisch möglich ist?"** Ein kompromissloser Visionär, der je Kern/Modul die funktional,
   technologisch UND architektonisch **überlegene, umfassendste, effizienteste** Lösung sucht.
   **Leitfragen je Kern:** Gibt es einen eleganteren Algorithmus / eine bessere Datenstruktur? Ist das
   Pattern **State-of-the-Art 2026**? Wäre eine modernere Bibliothek/Architektur überlegen (Performance,
   Speicher, Lesbarkeit, Wartbarkeit, Skalierung)? Lässt sich die Funktionalität **mächtiger/umfassender**
   machen? Wo liegt der größte Hebel für Qualität/Effizienz/„Wow"? **Arbeitsweise:** recherche-getrieben
   (WebSearch / Anbieter-Doku für den 2026-Best-Practice-Stand — Verfahren/Libs/Patterns/Benchmarks),
   den Ist-Code dagegen messen, JEDEN Level-up mit **Hebel + Quelle** begründen. **Maßstab = Perfektion,
   nicht „funktioniert"** — das technologisch beste, effizienteste, umfangreichste, verkaufs-/übergabe­fähige
   Ergebnis. **Ehrlichkeit (Gesetz 2) bleibt absolut:** was bereits Spitze/State-of-the-Art ist, wird SO
   benannt — kein „besser geht immer" um des Refactors willen (Gesetz 4); Vorschläge priorisiert mit echtem
   Hebel, reine Bug-Suche bleibt 0-Akut-ehrlich. **Output:** priorisierte Vision-/Level-up-Liste je Runde;
   Umsetzung = Freigabe-nötig / im Worktree. (Fokus: Facetten 1 Vollständig · 3 Professionell · 4 Effizient
   · 6 Detailtief — die North-Star-treibende Brille schlechthin; speist §6a + §7.5.)

8. **★ Funktions-Forscher / Hands-on-Tüftler** (NEU 27.06.2026, Nutzer-Wunsch) — die Brille, die **nicht beim Lesen
   stehenbleibt, sondern alles ANFASST und in Aktion sieht.** Haltung: neugierig, hands-on, will jeden Pfad selbst
   auslösen und live laufen sehen — *„das ist der Code, das ist die Steuerung, das ist die Verknüpfung → aktiviert →
   läuft (oder eben nicht)."* **Leitfrage je Teil:** „Tut es REAL, was der Code verspricht? Ich rufe den Endpunkt auf,
   fülle das Formular, klicke den Button, löse das Tool/den Flow aus und verfolge den Datenfluss durch ALLE Schichten
   (Route → Logik → DB → Antwort → Frontend → Cross-App-Relay) bis zum echten Ergebnis." **Arbeitsweise:** jede Funktion/
   jeden Endpunkt/jede Verknüpfung **funktionell auf einem Scratch-Port / isoliert ausführen** (echte Requests, echte
   Eingaben, echte lokale KI-/Tool-Calls, Konnektor-`lesen_sicher`, HITL-`propose` ohne `approve`, dry-run), den Effekt
   **verifizieren** (preview_snapshot/eval, DB-/Audit-Effekt, Statuscode, Rückgabe-Shape) und **Edge-Cases provozieren**
   (leere/große/bösartige Eingaben). Deckt **Laufzeit-Fehler** auf, die statisches Lesen übersieht: falsche Verdrahtung,
   500er, leere/halbe Antworten, kaputte Migrationen, tote Buttons, Relay-Mismatches, live abgelehnte KI-Schemata,
   hängende Subprozesse. **EINZIGE AUSNAHMEN (sonst ist ALLES erlaubt, was nicht-detrimental ist):** (a) **kein
   eigenmächtiger Neustart** von Live-Prozessen (Gesetz 6 — funktionell wird auf Scratch-/Isolat-Instanzen + read-only
   geprüft, Live nie gekillt); (b) **das Trading-Bot-Recherche-Tool wird NICHT autonom angesteuert** (TBs `research/`-
   Tooling = eigener Stack, kosten-/last-/API-sensibel ⇒ nur lesen/verstehen, nicht auslösen). **Sicherheit bleibt
   absolut:** hoechst/hoch nie an Cloud-Modelle; jede **Außenwirkung** (senden/posten/buchen/Echtgeld) bleibt
   **HITL-fail-closed** = wird nur VORGESCHLAGEN, nie ausgelöst; destruktive Ops nur auf Wegwerf-/Scratch-Daten.
   **Maßstab = der Live-Beweis:** ein Teil gilt erst als „funktionell ✓", wenn ich es **laufen gesehen** habe — nicht,
   wenn der Code „richtig aussieht". (Fokus: Facetten 1 Vollständig · 4 Effizient · 6 Detailtief — die **Funktions-
   Wahrheit**; ergänzt die Lese-Brillen 1–7 um den tatsächlichen Vollzug; speist §2.(4) + §6a.)

(Mehr als 8 Läufe ⇒ Roster zyklisch weiter; bei Bedarf eigene Rollen ergänzen, z. B.
**Performance-Profiler**, **A11y/Barrierefreiheit**, **Internationalisierung**.)

**Disziplin (Lehre aus dem Perspektiv-Marathon R3–R6, 22.06.):**
1. **Grep-Funde gegen False-Positives prüfen, BEVOR sie ins Ledger gehen** — Substring-Treffer (`eval(`
   matcht `_retrieval(`) und **mehrzeilige Calls** (Timeout/Param auf der Folgezeile) erzeugen Schein-Funde;
   jeden Treffer am echten Code verifizieren, sonst ist die Bilanz unehrlich.
2. **Perspektiv-Erschöpfungs-Regel → AKTIONSMODUS:** Hat jede Roster-Brille einmal gelaufen und liefert nur
   noch *vorausschauenden Backlog* (keine akuten Bugs — der erwartete Zustand auf einem audit-cleanen Netz),
   schaltet die Schleife von **Analyse** auf **Aktion**: sichere Backlog-Wins umsetzen (test-geführt, je Commit
   reviewbar) bzw. die **schwächste North-Star-Facette** treiben (§9.5). **Wiederholtes Re-Scannen ohne neue
   Fund-Klasse ist verboten** (kein Selbstzweck) — der Wert liegt dann im Bauen/Verbessern, nicht im erneuten Suchen.
3. **Unbeaufsichtigte Läufe (z. B. Ganztags-Auto-Zyklus):** analyse-/backlog-/doku-lastig bleiben; Code-Wins nur
   wenn **trivial + sicher + test-grün**, je einzeln committet; **KEINE blinden Visual-/Live-App-Änderungen**
   (die brauchen das Nutzer-Auge, §5d); nichts Großes/Riskantes ohne Freigabe.
4. **★★ BREITE vor TIEFE-Streckung — die KARDINAL-Regel der Perspektiv-Rotation (Nutzer-Klarstellung 27.06.2026):**
   **JEDE Perspektive durchleuchtet IMMER das KOMPLETTE System** — alle 10 Apps + Core + TB + alle Cross-App-Kanten
   (V2–V19) + Infra + ALLE Sorgfaltskerne — durch IHRE Brille. **Breite = nicht verhandelbar:** die Perspektive
   wechselt ERST, wenn die **§10-Abdeckungs-Matrix für DIESE Brille vollständig abgehakt** ist (nicht vorher). Es ist
   FALSCH, die Abdeckung über mehrere Perspektiven zu *verteilen* (jede Brille nur eine frische Scheibe) — der Sinn
   der Rotation ist, dass **derselbe Code durch jede Brille anders aussieht**; jede Brille muss ihn also sehen.
   - **TIEFE ist adaptiv (Nutzer-Wahl 27.06., NICHT die Breite):** je Brille die Sorgfaltskerne/heiklen Pfade
     **zeilennah**, schon-bestätigt-saubere Trivial-Teile **schneller** (aber berührt + abgehakt). „Bestätigt sauber"
     senkt die GRAB-Tiefe, **streicht NIE die Abdeckung**.
   - **Was die alte „Frische-Tiefe-Regel" WIRKLICH meinte (korrigiert):** sie gilt für die **Tiefen-Kadenz INNERHALB
     einer Brille** und für das Vermeiden, **dieselbe** Brille auf **demselben** sauberen Kern stumpf zu wiederholen —
     **NICHT** dafür, eine *neue* Brille Bereiche überspringen zu lassen, die eine *frühere* Brille schon gesehen hat.
   - **Pro Perspektive eine `§10-PERSPEKTIV-MATRIX`** (in docs/33): jede Zelle (App/Kante/Infra/Sorgfaltskern) bekommt
     ✓/⚙/📋/⏸ FÜR DIESE BRILLE. Erst volle Matrix ⇒ nächste Brille. So ist „jede Persönlichkeit hat alles gesehen" **belegbar**.
   - **★ KEINE PAUSE ZWISCHEN DEN PERSPEKTIVEN (Nutzer-Wunsch 27.06.):** ist eine Brillen-Zeile voll, rollt die NÄCHSTE
     Brille **nahtlos im selben Fluss** weiter — keine Pause, kein „weiter?"-Halt, keine Übergabe-Unterbrechung. Voll-
     System-Bilanz der fertigen Brille schreiben + sofort die nächste Brillen-Zeile beginnen (im selben oder nächsten
     Wakeup). Die Schleife läuft durchgehend bis Nutzer-„Stopp"/„ich bin zurück".

**Funde aus Perspektiv-Läufen werden perspektiv-getaggt** (`[Persp: Angreifer]` …), damit sich am Ende
beurteilen lässt, **was die Brille zusätzlich gebracht hat** (§8 Perspektiv-Wirkungs-Bilanz).

---

## §1 · PRE-FLIGHT + RE-GROUNDING (einmal pro Runde, vor den App-Pässen)

1. **Re-Grounding (zuerst, damit akkumuliert wird):** das **letzte Runden-Fazit** (docs/33) + den
   **offenen Backlog** + den North-Star (§0.5) lesen. Festlegen, **welche Ebene** diese Runde gräbt
   (§9.5), **wo** sie ansetzt (nicht bei Null — DORT weiter), und — bei geradem Lauf — **welche
   Perspektive** (§0.6) gilt; die Rolle + Leitfrage **explizit ausgeben**.
2. **Repo-Lock-Scan (§0b Chat-Management):** `git -C <repo> status --porcelain` für ALLE Repos.
   Dirty/aktive Repos = anderer Chat → **nicht anfassen** (nur read-only mitprüfen, namentlich
   vermerken). Delegations-Stand mitführen (TB / ggf. App-Chats).
3. **Netzweiter Kit-Drift-Scan:** `md5sum` der Kit-Dateien (tokens/controls/background/collapse/
   spinfling/floats/charts/netkit + dz-tokens + panel-builder) je App gegen `shared/`-Master bzw.
   `tools/`-Master; `ops/sync_appkit.py --check ../<app>` je App. Jede Abweichung = Drift-Fund.
4. **Test-Baseline:** je App die zuletzt bekannte grüne Testzahl als Soll mitführen (Regression fällt sofort auf).
5. **Live-Lauf-Status:** Core `/api/health/watch` (Soll 10/10) + alle Ports HTTP 200 read-only. Lücken = Befund.

---

## §2 · PER-APP-TIEFENPASS — Erfassen → Verstehen → Hinterdenken (für JEDE App)

> Drei Bewegungen je App. Die feste Checkliste A–F lebt in „Verstehen/Hinterdenken" — aber erst
> **nach** dem echten Erfassen+Verstehen. Befunde → sicherer Win (direkt) oder Backlog (groß/riskant).
> Im Perspektiv-Lauf (§0.6) zusätzlich durch die Rollen-Brille.

### (1) ERFASSEN — was existiert (vollständig)
Inventarisieren: Module/Dateien · alle Routen · alle Funktionen/Helfer · Datenmodell/Tabellen/
Migrationen · Frontend-Panels + Call-Sites · MCP-Tools · Cross-App-Endpunkte · **dormante Slots**
(Gesetz-5-Adapter) · Settings. Nichts auslassen — Grundlage für „haben wir was vergessen".

### (2) VERSTEHEN — die Funktionsweise wirklich durchdringen
Zweck, Datenfluss und Invarianten **end-to-end in eigenen Worten erklären können** (Eingang→Speicher→
Anzeige→Cross-App; tragende Invarianten wie Ledger Summe=0, RAG fail-safe, HITL fail-closed). Kann
ich es nicht erklären → tiefer lesen. Ergebnis (bei Änderung): knappe **Funktions-Landkarte** im Fazit.

### (3) HINTERDENKEN — Checkliste A–F + die vier Killerfragen
**A · Code-Pfad-Vollständigkeit & Verdrahtung** (tote Routen/Funktionen/verwaiste Calls; TODO/FIXME;
Dead Code). **B · Segment-Interaktion INNERHALB der App** (idempotente Migrationen/Alt-DB-Restart-sicher;
FK/on_delete/Soft-Delete; Reihenfolge-Annahmen; Async-Clobber; Fehlerpfade best-effort). **C · Cross-App-
Andock-Punkte** (Vertragstreue, best-effort, Idempotenz, HITL bei Außenwirkung, Storno/on_delete). **D ·
Kit-/appkit-Konsistenz** (byte-gleich zu shared; appkit `--check`; Token per `<link>`; lokale Forks =
De-Fork-Kandidat; App-Shell-Glows/Kopf-Norm aus dem Kit?). **E · Tests + kritische Pfade** (venv-pytest
grün; deckt Ledger-Invariante/Krypto-Step-up/HITL/RAG/Injection/on_delete ab; Lücke ⇒ Test nachziehen).
**F · UI-Struktur** (grob; Panel-Bündelung; systematische Anordnung; Kopf-Norm; **finale Optik = §5d /
Panel-Bautool** — Schleife liefert Struktur-Vorschlag + setzt klar empfohlene Wins um, nichts subjektiv-final).

### (4) AUSPROBIEREN — den Live-Vollzug erzwingen (Pflicht in der Funktions-Forscher-Brille §0.6 R8; in den Lese-Brillen optional, wo ein Zweifel nur durch Ausführen zu klären ist)
Nicht nur lesen — **auslösen**: den Endpunkt/Flow/das Tool **auf einem Scratch-Port oder isoliert real aufrufen**, mit
echten Eingaben (inkl. Edge-Cases), und den Effekt end-to-end **verifizieren** (Statuscode, Rückgabe-Shape, DB-/Audit-
Wirkung, Frontend via `preview_snapshot`/`preview_eval`, Cross-App-Relay-Ergebnis). **Ausnahmen:** kein Live-Neustart
(Scratch/Isolat statt Live); TB-`research/`-Tool **nicht autonom** auslösen; **Außenwirkung nur als HITL-`propose`** (kein
`approve`); destruktiv nur auf Wegwerf-Daten; **hoechst/hoch nie an Cloud**. **Ein Teil ist erst „funktionell ✓", wenn es
laufen gesehen wurde** — nicht, wenn der Code richtig aussieht.

**TB-Anpassung der A–F (eigener Stack):** A/B/C/E/F gelten 1:1 (Orchestrator-Backend + Engine-Strategien
+ `research/` + Vanilla-Frontend). **D** ist kein appkit/Kit-Byte-Check (TB nutzt kein `create_app`),
sondern: *welche Netz-Standards weicht TB bewusst ab (eigene Baseline-CSP, eigenes Frontend) und welche
Angleichung ist offen/sinnvoll?* (CSP voll-strikt + K2.2-Token-Retrofit + `install_defense()`-Rest = bekannte
offene Fäden, §6c). **E** nutzt TBs eigene venvs read-only (`TBT_NO_STARTUP=1`; Futures `:USDT`; Backtests
`--cache none`; Lookahead-Falle).

---

## §3 · CROSS-APP-PASS — die V-Matrix end-to-end

> **Registry = docs/26 (V2–V16) + docs/34 (V17–V19).** Die Schleife läuft JEDEN Eintrag ab. Zu jeder
> Kante erst Datenfluss verstehen (Sender→Relay→Empfänger→Rück-Lese), dann prüfen.

- **V2–V11 → Memory-Archiv** (news/creator/komm/plans→admin/admin/management/money/health/trading): Sender
  taggt korrekt (strom/sensibel), Core-Relay auditiert+idempotent, Empfänger idempotent + per-(app,strom)-Regeln + Cleanup-pristine.
- **V5 Communication↔Plans/Admin-Kalender** (bidirektional inkl. Rücksync; Default-Ziel `admin`; iCal-Idempotenz).
- **V14 Money←Trading-Steuer** (§20/§23/§32d, read-only TB-Brücke, Paper-gelabelt).
- **V15 Money↔Admin-Beleg-Link** (`verknuepfung`/`belege`, bidirektional; Re-Link reaktiviert Soft-Delete; Beleg-Wechsel löst Altlink — H-18-Regressionswächter).
- **V16 Admin←Money-EÜR** (steuer-relevante Ausgaben in die EÜR gefaltet).
- **V17/V18/V19 Bereichs-Querverbindungen** (A5, docs/34): Money `finanzspur` · Management `social` · Memory `kategorie` → Core-Relays → Admin-Bereichs-Cockpit; read-only/best-effort, nur Kennzahlen, HITL in der Quelle.
- **TB-Kanten:** **V11 Trading→Memory** (`report.py`, best-effort, sensibel, HITL) · **V14 Money←Trading-Steuer**
  (read-only Brücke) · **Core-Health-Watch** `app:tradingbot` · **Per-App-MCP-Connector** (6 read-only Tools) ·
  **Rück-Lese** `GET /api/wissen/suche`.

**Pro Kante:** (1) Vertrag/Version beidseitig; (2) Core-Relay vorhanden + auditiert + 404 wenn Ziel nicht
angedockt; (3) best-effort (Ziel offline ⇒ leere Sicht, kein Crash); (4) read-only — keine Außenwirkung über
die Kante; (5) Idempotenz + Storno/on_delete-Cleanup; (6) keine toten Sender-Kanten auf abgewickelte Apps
(plans/leading/musik/buerokratie/projekte); (7) Killerfrage „Vergessen?": fehlt eine sinnvolle Kante, die die Vision impliziert?

---

## §4 · QUER-/INFRA-PASS (Core + netzwerkweite Mechanik)

- **Core-Relays + `/api/health/watch`** (10 Ziele): jeder Relay erreichbar, best-effort, auditiert.
- **MCP-Gateway** (zentral `core/app/ai/mcp_gateway.py` + per-App `appkit/app_gateway.py`): opt-in,
  Bearer-Pflicht (`compare_digest`), Verwaltung nur localhost, **read-only-Härtung** (Aktions-Tools extern
  gesperrt), **Hochsicher-Gate** (Krypto/Echtgeld/hoechst extern gesperrt, befristete Freigabe lokal),
  Föderations-Auto-Off wenn Core führt.
- **SSO/Dizzi-ID** (keine toten Clients) · **Autostart** (Tasks → echte Ordner/Ports) · **defense**
  (Loopback nie gedrosselt, ≥1.21.1) · **Security-Header** · **CSP voll-strikt** (script-src nonce,
  style-src behält unsafe-inline = 1.24.1-Fix) · **`csv_safe`** in allen Exporten · **OS-Secret-Store** (Keys nie DB).
- **appkit-Vertrag (1.5)** netzwerkweit identisch; Helfer (querverbindung/mini_dizzi/push) konsistent.

---

## §5 · DATEN / SICHERHEIT / RECHT-PASS (= North-Star-Facetten 7+8+11)

- **DSGVO:** jede sensible Tabelle hat `on_delete`/Soft-Delete + `purge_user`/`remove_user`; keine lösch-pflichtige Spalte ohne `deleted_at`.
- **Verteidigungssysteme (Facette 7) — echt scharf?** defense drosselt bei Last; Security-Header auf jeder Antwort (auch Guard-Abweisungen); CSP ohne Lücke; HITL fail-closed.
- **Hochsicherheits-Datenlagerung (Facette 8):** Tresor Fernet-at-rest, Key im OS-Secret-Store (nie DB),
  verschlüsselt ⇒ nicht FTS-indexiert, Lese-Step-up 403; `hoechst`/`hoch` ⇒ KI lokal_only; Hochsicher-Gate extern dicht.
- **Recht/Haftung:** Steuer = Schätztool (keine Beratung); Health = keine Diagnose; Studium = keine Beratung
  (PO verbindlich). Disclaimer sichtbar + im Export (MD-/CSV-Injection-Schutz).
- **Daten-bei-der-Quelle:** Querverbindungen duplizieren nicht; Eigentümer bleibt Eigentümer.

---

## §6 · PARALLELE RECHERCHE- & LÜCKEN-DIMENSION (läuft DURCHGEHEND mit)

> Bei JEDER App + Kante zusätzlich diese drei Fragen + jeden Fund SOFORT in docs/33. WebSearch nutzen, wenn der 2026-Stand unklar ist.

- **(a) Code/Effizienz/Architektur:** bessere/effizientere/robustere Umsetzung (Bibliothek/Algorithmus/Muster/
  API, 2026)? Konkret Ineffizienz: O(n²), N+1-Queries, fehlende Indizes, Wiederholarbeit ohne Caching,
  Voll-Scans, **Duplikate, die ins shared-Kit/appkit gehören**, unnötige Allokationen. Etwas „nicht ganz richtig"?
- **(b) Feature/2026-Standard:** welche Features nach dem 2026-Standard der Referenzklasse fehlen (vgl. docs/_archiv/27/30)?
- **(c) ★ ABSICHT vs. REALITÄT — „haben WIR etwas vergessen?":** alle **„OFFEN"/„FÜR-WORLD-CHAT"/„nächste
  Schritte"**-Notizen (docs + Gedächtnis + App-WIEDEREINSTIEGs) gegen das Gebaute abgleichen; alle **dormanten
  Slots** (welche sollten scharf sein? welche sind tote Vorbereitung?); **Vision-Abgleich** (docs/00/11/35: welche
  Endbild-Fähigkeit fehlt/ist halb?). **TB-eigene offene Fäden** mitführen: CSP voll-strikt (Nonce + ~104 Inline-
  Handler), K2.2-Retrofit, `install_defense()`-Rest, CSM-`vol_scaled`-Aktivierung am ≥90-Tage-Re-Test.

**Klassifikation jedes Funds (in docs/33):** `sicherer Win` (klein/risikofrei ⇒ DIREKT umsetzen+committen) ·
`Freigabe-nötig` (Umfang/UI-§5d/Risiko ⇒ Backlog) · `Architektur-KI-Park` (hart/nicht-blockierend). Je Fund: App,
Kurzbegründung, **geschätzter Hebel + North-Star-Facette** (+ Perspektiv-Tag, falls aus einem Perspektiv-Lauf).

---

## §7 · SORGFALTSKERN-TIEFENREVIEW (ab Runde 2, dann jede Runde — zeilennah)

Kritische Module **zeilennah lesen** (nicht nur Tests), mit dem Anspruch, ihre Logik **erklären zu können**:
- **Money** `ledger.py` + `trading_steuer.py` (int-Minor-Units, Balance-Invariante pro Währung, Decimal an Rändern, §20/§23 kalendarisch/Freigrenze, Determinismus).
- **Memory** `rag.py` + `vault.py` (RAG fail-safe + Dim-Check; Vault `..`-pfad-sicher, `yaml.safe`, BOM-Strip, `purge_user`).
- **Admin** `tresor.py` (Fernet-at-rest, Key im OS-Secret-Store, kein FTS-Leak, Dizzi-ID-Step-up 403).
- **Communication / Management** (Senden/Veröffentlichen = HITL `verifiziert`, fail-closed).
- **Health** (`hoechst` ⇒ lokal_only, „keine Diagnose"-Disziplin).
- **News / Creating** (KI per JSON-Schema-Grammatik; LoRA/Kohya-Echtbetrieb).
- **Core/Gateway** (read-only-Härtung + Hochsicher-Gate halten dicht).
- **Trading Bot (read-only):** Echtgeld-`/api/transfer` = Stufe `hochsicher` (doppelt: confirm + echter Transfer
  „bewusst blockiert"); destruktiv = `verifiziert`; `runner` killt nur cmdline-verifizierte PIDs (Collateral-Kill-Fix);
  KI-Ehrlichkeit (`_validate_strategy` Mehrheit UND Aggregat-Profit; Walk-Forward/PSR; CSM lookahead-frei, `vol_scaled` AUS).
Ziel: **0 Bugs bestätigen** oder Fund test-geführt fixen (TB-Fund ⇒ Backlog + TB-Chat-Übergabe, nicht selbst fixen).

---

## §7.5 · EFFIZIENZ- & ARCHITEKTUR-TIEFENLINSE (ab Runde 3, dann jede Runde)

> Eigenständige Linse für Facetten 3+4+5. Je Lauf ≥1 Domäne so durchleuchten:
- **Algorithmik/Daten:** Hot-Paths auf Komplexität; DB-Queries auf N+1/fehlende Indizes/Voll-Scans; cachebare Wiederholarbeit; unnötige Serialisierung.
- **Architektur/Wiederverwendung:** Duplikat-Code über Apps → shared/appkit (De-Fork); saubere Schichtung; Verträge konsistent; **Flexibilität** (Adapter/Registry statt Hartverdrahtung).
- **Skalierung:** hält das Muster bei wachsenden Datenmengen/Apps/Kanälen? Wo bricht es zuerst?
Funde → `sicherer Win` (direkt) oder Backlog mit Hebel. Keine Mikro-Optimierung um ihrer selbst willen.

---

## §8 · RUNDEN-ABSCHLUSS

1. **Sichere Wins** test-geführt umsetzen + im jeweiligen App-Repo committen (shared/appkit NUR am Master + vendoren).
2. **Backlog pflegen** (docs/33): neue Funde mit Klassifikation + North-Star-Facette + Hebel (+ Perspektiv-Tag); erledigte abhaken. **Vergessene-Fäden-Ledger** (§6c) führen.
3. **North-Star-Scorecard** (kurz): schwächste Facette dieser Runde → konkreter nächster Schritt (speist Re-Grounding).
4. **Perspektiv-Wirkungs-Bilanz** (nach Perspektiv-Läufen): welche Funde kamen **nur** durch die Brille (hätte die
   Standard-Linse sie verpasst)? Tabelle Lauf×Perspektive×Funde — so wird beurteilbar, ob der Perspektivwechsel etwas bringt.
5. **Doku-Sync (G9):** docs/33-Fazit + ggf. Funktions-Landkarten + Gedächtnis [[world-of-dizzi-stand]] + Chat-Management §0.
6. **Gegatete Live-Restarts** sammeln (nicht pro Fix) → EIN konsolidierter Go-Live-Vorschlag (Nutzer-Go, Backup-first). Frontend disk-served greift ohne Neustart.
7. **Sofort die nächste Runde** (§9.5), bis Anzahl erreicht bzw. „Stopp".

---

## §9 · LEITPLANKEN (immer)

- **shared/appkit** nur am Master ändern + neu vendoren; `ops/sync_appkit.py --to ../<app>` je Repo (`--all` VERALTET).
  Kits via `cp shared/* <app>/ui-kit/` + md5-Gegencheck (0 Drift). Panel-Bautool: Master `tools/`, immer html+js zusammen.
- **Nie zwei Chats im selben Repo** (Repo-Lock §0b). Vor JEDER Änderung an einem Repo dessen `git status` prüfen.
- **TB-Repo nicht ändern, `:8137` nicht neu starten** (TB-Chat + Nutzer-Go) — **Schreib-/Restart-Sperre, KEINE
  Analyse-Ausnahme:** TB wird trotzdem jede Runde voll durchleuchtet/verstanden/hinterdacht/read-only getestet; Funde → Backlog + TB-Chat-Übergabe.
- **★ Zwei harte Funktions-Ausnahmen (auch für die Funktions-Forscher-Brille §0.6 R8):** (1) **kein eigenmächtiger
  Neustart** irgendeines Live-Prozesses (funktionell immer auf Scratch/Isolat); (2) **TBs `research/`-Recherche-Tool wird
  NIE autonom angesteuert** (kosten-/last-/API-sensibel). Alles andere Nicht-Detrimentale darf die Brille aktiv auslösen/
  antouchen — Außenwirkung aber nur als HITL-`propose`, destruktiv nur auf Wegwerf-Daten.
- **Live-Prozesse NIE eigenmächtig neu starten** — Restarts gegated (Nutzer-Go, Backup-first). Disk-servierte Frontends greifen ohne Neustart; Python/appkit erst beim Neustart.
- venv `C:\Dizzik\data\tools\venv`; Verifikation auf **Scratch-Ports** (Live nie stören); `preview_snapshot`/`preview_eval` statt screenshot.
- **UI-Finalisierung = §5d** (subjektive Letzt-Optik mit Nutzer / Panel-Bautool); **klar empfohlene strukturelle/Norm-/Feature-Wins** darf der World-Chat in der UI-Phase autonom umsetzen (Nutzer-Auftrag 22.06.).
- **Backlog ist Pflicht**; nichts Großes/Riskantes eigenmächtig. **Ehrlichkeit (Gesetz 2):** lieber „0 Bugs, hier die nächste Wertgrenze" als künstliche Funde.

---

## §9.5 · RUNDEN-PROGRESSION & ANTI-LEERLAUF (so akkumuliert die Schleife)

> Jede Runde gräbt **eine Ebene tiefer** und setzt beim letzten Fazit + offenen Backlog an. **Nie nur „clean"
> re-bestätigen** — ist eine Ebene erschöpft, steigt sie zur nächsten Wertgrenze auf. Gerade Läufe = Perspektiv-Läufe (§0.6).

- **R1 (Standard) — Breite/Drift:** Pre-Flight + alle Apps A–F + TB + Cross-App-Volllauf + erste Recherche-Funde.
- **R2 (Perspektive 1: Angreifer) — Modul-/Sorgfaltskern-Tiefe** durch die Sicherheits-Brille: §7 zeilennah; Gates/Injection/Exfil/Bypass.
- **R3 (Standard) — Effizienz & Architektur:** §7.5 scharf; De-Fork/Wiederverwendung; Recherche-Vertiefung.
- **R4 (Perspektive 2: Produkt-Skeptiker) — Absicht vs. Realität:** §6c als Hauptachse — vergessene Fäden, dormante Slots, Vision-Lücken, UX/Verkaufbarkeit.
- **R5 (Standard) — Backlog-Abarbeitung:** sichere Wins aus dem akkumulierten Backlog umsetzen; Go-Lives bündeln.
- **R6 (Perspektive 3: Zukunfts-Architekt) — Skalierung/Architektur-Schulden** + Wertgrenzen-Aufstieg.
- **R7+ — Anti-Leerlauf:** ist Bug-Suche erschöpft, treibt die Schleife die **schwächste North-Star-Facette**
  (§0.5) voran (Konnektivität/Verteidigungstiefe/Test-Abdeckung/Doku-Perfektion/Verkaufbarkeit); Perspektiv-Roster zyklisch weiter.
  **Jeder Lauf produziert Vorwärtsbewegung** (Fix · sicherer Win · fundierter Backlog-Eintrag · konkret benannter nächster Schritt). „Nochmal clean" zählt NICHT als Runde.

- **★ Visionär-Brille (Roster 7) — jederzeit einflechtbar, NICHT bug-erschöpfungs-gebunden:** anders als
  1–6 fragt sie „ist es das Beste?" statt „ist es kaputt?" und liefert daher AUCH auf einem 0-Akut-Bug-Netz
  echten Vorschub (Level-up-Liste). Sie ist die natürliche Anti-Leerlauf-Brille, wenn die Bug-Suche
  konvergiert ist (§0.6 Regel 2). **Handover 27.06.: diese Brille ZUERST durch den ganzen Roster ziehen,
  dann zyklisch 1–6 weiter** (bis der Nutzer zurück ist).

(Die Stufen sind Richtwerte; die Schleife endet nie aus sich heraus, nur auf „Stopp".)

---

## §10 · ABDECKUNGS-GARANTIE (die Abhak-Liste — „nichts übersehen")

> Ein Durchlauf ist erst vollständig, wenn JEDE Zelle berührt + im Fazit (docs/33) vermerkt ist
> (✓ verstanden/geprüft · ⚙ gefixt · 📋 Backlog · ⏸ repo-locked übersprungen). „Verstanden" = Funktionsweise erklärbar.
> **★ PRO PERSPEKTIVE (§0.6 R4, Nutzer-Klarstellung 27.06.):** Diese ganze Liste wird FÜR JEDE Brille einzeln
> abgehakt — die Perspektive wechselt erst bei voller Matrix. Adaptive Tiefe (Sorgfaltskerne zeilennah, Bestätigtes
> schneller) senkt den Aufwand je Zelle, streicht aber KEINE Zelle. Bei mehreren Wakeups: die Matrix akkumuliert über
> die Wakeups derselben Brille, bis sie voll ist.

**Pre-Flight/Re-Grounding:** ☐ letztes Fazit + Backlog gelesen ☐ North-Star vergegenwärtigt ☐ Ebene festgelegt
☐ **Perspektive deklariert (bei geradem Lauf)** ☐ Repo-Lock-Scan ☐ Kit-Drift-md5 ☐ appkit `--check` ☐ Test-Baseline ☐ Health-Watch 10/10 + Ports 200.

**Apps (je Erfassen→Verstehen→Hinterdenken A–F):** ☐ news ☐ finanzen ☐ archiv ☐ kommunikation ☐ creator
☐ social-media ☐ health ☐ admin ☐ Core ☐ **Trading Bot (read-only)**.

**Cross-App-Kanten:** ☐ V2 ☐ V3 ☐ V4 ☐ V5(+Rücksync) ☐ V6 ☐ V7 ☐ V8 ☐ V9 ☐ V10 ☐ V11 ☐ V14 ☐ V15 ☐ V16
☐ V17 ☐ V18 ☐ V19 ☐ **TB V11/V14/Health-Watch/MCP/Rück-Lese** ☐ keine toten Sender-Kanten ☐ fehlende sinnvolle Kante?

**Quer/Infra:** ☐ Core-Relays ☐ Health-Watch ☐ MCP-Gateway (read-only+Hochsicher-Gate) ☐ SSO ☐ Autostart
☐ defense ☐ Security-Header ☐ CSP voll-strikt ☐ csv_safe ☐ Secret-Store ☐ appkit-Vertrag.

**Daten/Sicherheit/Recht:** ☐ DSGVO on_delete/purge ☐ Verteidigung wirksam (Facette 7) ☐ Hochsicher-Lagerung dicht (Facette 8) ☐ Sensitivität-Routing/lokal_only ☐ Recht/Disclaimer ☐ Daten-bei-der-Quelle.

**Sorgfaltskerne (ab R2):** ☐ ledger/steuer ☐ rag/vault ☐ tresor ☐ HITL senden/publish ☐ health-lokal_only ☐ news/creating-KI ☐ Core/Gateway-Härtung ☐ **TB Echtgeld-Gate/Prozess-Integrität/KI-Ehrlichkeit (read-only)**.

**Effizienz & Architektur (ab R3):** ☐ ≥1 Domäne Komplexität/Queries/Caching ☐ Duplikate→shared ☐ Flexibilität/Entkopplung.

**Funktions-Beweis (Brille 8, §0.6 R8):** ☐ je App ≥1 Kern-Flow live ausgelöst+verifiziert (Scratch/read-only) ☐ tote Buttons/500er/leere Antworten geprüft ☐ ≥1 Cross-App-Relay real durchgespielt ☐ Ausnahmen gewahrt (kein Live-Neustart · kein TB-`research`-Autostart · Außenwirkung nur `propose`).

**Recherche- & Lücken-Dimension:** ☐ je App (a) Code/Effizienz ☐ je App (b) Feature/2026 ☐ (c) Absicht-vs-Realität / vergessene Fäden ☐ Funde klassifiziert + North-Star-Bezug (+ Perspektiv-Tag) in docs/33.

**Abschluss:** ☐ sichere Wins committet ☐ Backlog + Vergessene-Fäden-Ledger gepflegt ☐ North-Star-Scorecard
☐ **Perspektiv-Wirkungs-Bilanz (bei Perspektiv-Läufen)** ☐ Doku-Sync ☐ Go-Live-Liste ☐ nächste Runde gestartet (oder „Stopp").
