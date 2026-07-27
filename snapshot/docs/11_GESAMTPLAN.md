# Gesamtplan — das Riesenpaket (Stand 11.06.2026, laufend gepflegt)

> Entstanden aus 10_RIESENPAKET_BRIEFING.md + Fragerunde 1.
> Vier Pivot-Entscheidungen sind gefallen (s. §1). Dieser Plan ist die **Bau-Ordnung** mit
> **Bau-KI-/Architektur-KI-Sortierung** und **Session-Volumen-Schnitt**. Lebendes Dokument.
>
> **⚡ Operativer Live-Status NICHT hier, sondern im Lotsen:**
> DIZZ_NETWORK_CHAT_MANAGEMENT.md **§0 = Netzwerk-
> Dashboard** (Status-Ampel/Fundament/nächstes Paket je App) · §0b Repo-Lock · §0c
> Invarianten · §0d STATUS-KOPF-Norm. Modell-Stufen (🟦 Assistenz-KI/🟩 Bau-KI/🟪 Architektur-KI): G10 +
> §3-Kopf. Dieser Plan = das große WARUM/Bau-Reihenfolge; der Lotse = das tagesaktuelle WO-STEHT-WAS.
>
> **★★★ PLAN-STATUS 22.06.2026 — UI-PHASE LÄUFT (Kopf-Norm + Großrunde) · Panel-Bautool FERTIG.**
> **(1) Panel-Bautool ✅ FERTIG** (v19 Pixel-Mirror, optisches 1:1, netzweit committet `54ed9d6`, 0 Drift; docs/_archiv/40 §3.0 / docs/_archiv/42; Glow-Audit docs/_archiv/41) — der eigene Bau-KI-Extra-Chat ist abgeschlossen; das Tool ist ab jetzt das Werkzeug der **§5d-UI-Finalisierung**.
> **(2) UI-GROSSPHASE BEGONNEN (Nutzer-Go 22.06., autonom):** **(a) Kopf-Norm** = der News/Communication/Money/Creating-Kopf (Marken-Lockup + Stufen/Hochsicher + Magenta→Cyan-Akzentstreifen) wird **kanonisch ins shared Kit** gehoben (docs/39 WP-A) **inkl. App-Shell-Glow-Promotion** (docs/_archiv/41) → Rollout auf die abweichenden Köpfe **Management · Health · Memory · Admin** (Admin-Oberregister als Kit-Variante). **(b) UI-Großrunde je App** (kernlauf-artig: erfassen→verstehen→UI-Fit→klar empfohlene Wins direkt anwenden; TB ausgenommen). **(c)** Kern-Dauerschleife (docs/32) um **Perspektivwechsel jede 2. Runde** erweitert. ⇒ Die §5d-Leitlinie „UI-Final nur mit Nutzer" gilt weiter für subjektive Letzt-Optik; **klar empfohlene strukturelle/Norm-/Feature-Wins setzt der World-Chat in dieser Phase autonom um** (Nutzer-Auftrag).
> **(3) Konnektivität** bleibt Kernziel (WhatsApp PoC live; Telegram nächster Konnektor NACH dieser UI-Phase). **(4) R-STRUKTUR** weiter offen (eigene Migrations-Session, Obername-Rückfrage).
>
> **★ PLAN-ERWEITERUNG 20.06.:** Die netzwerkweite **MCP-/Konnektivitäts-Schicht steht** — Per-App-Gateway in JEDER
> Live-App (`/mcp` standalone, opt-in/Token/read-only, auto-Abschaltung im Verbund) + alle App-`mcp_server.py` als
> Core-Connectoren ⇒ Dizzis Agent UND ein zentrales Gateway erreichen das ganze Netz an EINEM Endpunkt (appkit 1.20).
> **Neue/aktualisierte Bau-Stränge:** A5 V17/V18/V19 Bereichs-Querverbindungen (Money/Management/Memory ↔ Admin-Bereiche) ·
> B Dizz-Admin-Tiefe (docs/_archiv/30) · **Trading-Bot-„Ultimate"** (Mini-Dizzi + Per-App-Gateway + appkit 1.13→1.20, eigener
> TB-Chat, einheitlich über Mini-Dizzi) · der vom Nutzer **freigegebene Schleifen-Backlog [docs/33]** (Feature-/UI-Wins
> je App; health-Ziel = 3 Gruppen-Panels + 1 konfigurierbares Übersichtspanel). UI-Finalisierung bleibt §5d (mit Nutzer).
>
> **⬚ Geplante Vernetzungs-Bausteine (Nutzer-Ideen 13.06., Detail im Lotsen §4):**
> (1) **Desktop-Monitor „Dizz Network"** (natives Statusfenster, klickbare Direkt-Links) von TB
> ins Core-Repo verlegen — er überwacht das ganze Netzwerk, gehört also zum Core (`the world of
> dizzi/desktop/` o. ä.). (2) **Per-App-Monitor, föderations-gated:** jede App darf ein eigenes
> kleines Front-/Status-Panel haben, aber im Verbund zeigt nur EIN zentrales Dizz-Network-Panel
> (das Verbindungstool erkennt „wir laufen übers Netzwerk" — analog Mini-Dizzi „es lauscht nur
> EINER"). Braucht eine Konzept-Runde (Single-Instance-übers-Netz, wer zeigt/wer schweigt).

> **★★★ MAJOR-PHASE NEU 19.06.2026 — ADMIN-KONSOLIDIERUNG (Plans + Admin + Leading → EINE App „Admin"):**
> Fundamentaler Merge der drei Verwaltungs-Apps zu **Dizz Admin** = „kranke Verwaltungs-/Admin-Hilfs-KI-App".
> **Rückgrat = Bereiche/Kontexte (Kategorie-Achse):** Nutzer legt einen Bereich an (z. B. „Studium Informatik",
> „Geschäft X", Fortbildung); daran hängen kategorisiert: **Tresor-Dokumente** (Fächer + Extra-Sicherheit +
> Memory-Verweise) · **Projektmanagement** (aus Plans, bereichs-zugeordnet + Projekt-Unterkategorien) ·
> **Geschäftsführung** (aus Leading: GoBD-Rechnungen/KPI/EÜR/Cockpit/Aggregator + **Studien-Modul/ECTS**) ·
> **Fristen** (kategorie-gefiltert). **Vernetzung:** Money (per-Bereich-Finanzen + Spuren) · Management (Social-Bots
> per Bereich) · Creator/Communication · Memory. **Standalone + föderiert + SuperAI-Kern-steuerbar.** Konsolidiert
> bestehende Module (kein Greenfield). **Position: VOR der per-App-UI-Phase (§5d), wahrscheinlich VOR A3-Charts**
> (leadings Chart/netzwerk-kit + netkit im Merge-Scope → A3 pausieren/falten). **Eigener World-Admin-Chat** plante
> + setzte um (Repo **`admin`** [vormals `leading`, Rename 20.06.] /Paket `adminapp`, id `admin`, :8222). **✅ STATUS 19.06.: MERGE KOMPLETT + LIVE
> (Phase 0–6, `311d466`) · vereinte bereichs-zentrierte UI „großer Wurf" gebaut + scratch-verifiziert · Post-Merge-
> Altlasten-Cleanup (mein Repo + Core) + 2 Features (iCal-Feed, globale Suche), Admin 126 / Core 151 Tests grün.**
> Detail: **docs/_archiv/28** (Merge), **docs/_archiv/29** (Post-Merge-Audit), **docs/_archiv/30** (Feature-Recherche). Die V-Kanten/
> App-Roster im Verlauf unten beschreiben den PRE-MERGE-Stand (Historie); plans/leading sind jetzt **Dizz Admin**,
> die internen Kanten V6/V7/V12 werden In-Prozess-Aufrufe (docs/_archiv/28 §5). **OFFEN:** Feel-Check 👤 + gated :8222-/
> Core-Neustart (live schalten) + World-Chat-Reste (appkit-`sende_termin`-Default + Komm-V5 `plans→admin`, Kits→shared).

> **★★★ MAJOR-PHASE NEU 19.06.2026 — REMOTE-MCP-GATEWAY am Core („eine Verbindung zu allem"):** Der Core bündelt
> die per-App-MCP-Tools (heute stdio, je App `<id>_*`) zu **EINEM remote HTTP-MCP-Endpunkt** (MCP-Spec 2026:
> Streamable-HTTP, OAuth 2.1 / Dynamic Client Registration **über Dizzi-ID**). ⇒ Eine externe KI (Claude, IDE-Agent,
> künftige Agenten) verbindet sich **einmal** mit Dizzi/Core und erreicht das **ganze Netzwerk** read-only sofort;
> jede Schreib-/Aktion bleibt **K4-HITL-freigabepflichtig** (nie eigenmächtig), Least-Privilege je Tool (docs/16 §6),
> Audit über alles. Das ist die direkte Umsetzung der Nutzer-Vision „die EINE Zugriffsverbindung, über die alles
> andere gewährleistet ist". **✅ v1 GEBAUT + getestet 19.06.** (`core/app/ai/mcp_gateway.py`, `POST /mcp`
> JSON-RPC; opt-in + Bearer-Token + read-only; Core **154** grün) — Architektur/Nutzung: **docs/31**.
> **OFFEN:** gegateter Core-Neustart ⇒ live · v2 = OAuth/Dizzi-ID-DCR + Schreibaktionen über K4-HITL +
> alle App-Connectoren. Recherche: **docs/_archiv/30 §H1/§3**.

## 1. Gefällte Entscheidungen (Fragerunde 1, 11.06.)
1. **Identität** = **„Dizzi-ID" brokert Google.** Ein schlanker eigener Identitäts-Dienst ist die
   zentrale Stelle; Anmeldung per Google (Loopback-IP + PKCE, Googles empfohlener Desktop-Weg);
   für Echtgeld zusätzlich Passkey/MFA (FIDO2).
2. **Konto-Scope jetzt** = **Single-User-Sicherheits-Gate.** Nur der Nutzer; ein Login schützt
   sensible/Echtgeld-Bereiche. Multi-User-Architektur wird **vorbereitet** (Daten user-scoped),
   aber noch nicht ausgebaut.
3. **Aufbau** = **Föderation, nicht Monolith.** Jede App ist **eigenständig** (eigenes Konto +
   eigene Einstellungen, einzeln betrachtbar/verkaufbar), ABER alle sind **top vernetzt**: Dizzi-ID
   ist der **Identitäts-Provider mit Single-Sign-On** — **einmal auf Dizzi anmelden → automatisch
   in allen verbundenen Apps eingeloggt.** Standalone genutzt/verkauft funktioniert jede App auch
   mit ihrem eigenen Login.
4. **Architektur-KI-Fokus (bis 21.06.)** = **nur die geteilte Kern-Architektur.** Fundamente, die sich
   durch alles ziehen und schwer nachrüstbar sind. UI & einzelne Apps füllt danach Bau-KI.

## 2. Das Zielbild in einem Satz
Ein **Netzwerk eigenständiger Apps** (Dizzi als Dach + Kommandozentrale, Trading Bot, Finanzen,
Bürokratie, …), die **einzeln verkaufbar** sind, aber über **Dizzi-ID (SSO)**, einen
**gemeinsamen App-Vertrag** und das **MCP-Interaktions-Protokoll** zu einem nahtlosen
Gesamtsystem zusammenwachsen — verkaufs-/service-tauglich, vom Code bis zur Oberfläche.

## 3. Die geteilte Kern-Architektur (Architektur-KI — vor 21.06.)
Sechs Bau-Pakete. Jede App **konsumiert** sie, **enthält** sie aber selbst (Föderation):

### K1 — Dizzi-ID (Identitäts-Dienst) — **HART ausgelegt (Echtgeld bald)**
- OIDC-Provider im Dizzi-Kern: Google-Brokering (Loopback+PKCE), Token-Ausstellung,
  **Passkey/MFA Pflicht** für sensible/Echtgeld-Bereiche, Refresh-Rotation, strenge
  „verifizierte Verbindung" als Daten-Tor (nicht nur vorbereitet — scharf).
- **SSO-Fluss**: Login auf Dizzi → signierter Ausweis → jede App akzeptiert ihn (Relying Party).
- Standalone-Modus jeder App: eigener lokaler Login als Fallback.
- Sicherheits-Stufen: „verifizierte Verbindung" als Gate für sensible Daten; Echtgeld-Stufe
  erfordert Passkey/MFA. Audit-Log aller Auth-Ereignisse.

### K2 — Account- & Settings-Core (wiederverwendbares Modul)
- Ein **Modul-Muster**, das jede App einbettet (Föderation): Konto-Profil, Einstellungs-Schema
  (typisiert, versioniert), sichere Secret-Ablage (.env-Muster außerhalb Repo/OneDrive).
- Einstellungs-Kategorien (aus Recherche, finalisieren in Fragerunde 2): KI-Routing (lokal/Boost,
  Sensibel-Domänen), Sprache/Stimme/Wake-Word, Dienst-Konnektoren (Gmail/Kalender/…),
  Sicherheit (MFA/Passkey/Sessions), Vernetzung (welche Apps verbunden), Darstellung/Theme,
  Daten/Backup, Konto (Profil/Login-Methoden).

### K3 — App-Vertrag (das Andock-Skelett)
- Generalisierung des Panel-/MCP-Musters zum **Standard-Vertrag** jeder App:
  (a) eigener Ordner + Gesetze + Doku, (b) read-only Stats-Endpoint (Dashboard-Kachel),
  (c) **MCP-Server** (KI-Interaktion), (d) **Dizzi-ID-Relying-Party**, (e) Account+Settings-Modul,
  (f) Deep-Link, (g) Vernetzungs-Manifest (welche Daten/Tools es teilt).
- **Referenz-Implementierung** (eine Vorlage), die jede neue App kopiert.

### K4 — AI-Interaktions-Protokoll (Dizzi ↔ App-KIs)
- Verallgemeinerung des in Phase 4 gebauten MCP-Tool-Bus: Lese-Tools (Standard), Aktions-Tools
  mit **Human-in-the-Loop**-Stufen, Event-Push App→Dizzi, L4-Beobachtung, Vorschlags-Pipeline.
- Sicherheits-Regel bleibt: beobachten + vorschlagen, nie eigenmächtiger Eingriff; sensible
  Aktionen hinter verifizierter Verbindung.

### K5 — Geteilte Datenmodelle & Sync-Basis
- Schema-Konventionen (UUID/user_id/Timestamps/Soft-Delete) als gemeinsame Bibliothek;
  Sensibel-Kennzeichnung von Daten (steuert lokal-only-Routing); Sync-Vorbereitung (Stufe 3).

### K6 — Trading Bot ↔ Gesamtschema-Angleichung (architektonischer Teil)
- Trading Bot als Relying Party an Dizzi-ID; Account+Settings-Modul nachrüsten; App-Vertrag
  formal erfüllen (er hat schon Stats + MCP). **Echtgeld-Gate an Dizzi-ID-Hochsicherheit koppeln.**

## 4. Was Bau-KI macht (jederzeit, NICHT Architektur-KI-Zeit verbrauchen)
> **Strategie-Kern: Architektur-KI-Zeit ist knapp → alles Nicht-Architektur JETZT mit Bau-KI erledigen,
> damit Fables Fenster zu 100 % in K1–K6 fließt.**

### O-Prep (sofort, Bau-KI — macht Architektur-KI den Boden frei)
- **Ordnerstruktur scaffolden**: alle geplanten Apps als Geschwister-Ordner (neben Dizzi +
  Trading Bot in „C:\Dizzik\code"), je mit: Gesetze-Kopie, WIEDEREINSTIEG-Stub, Vernetzungs-/
  App-Vertrag-Stub, Anforderungsliste, leere docs-Struktur.
- **Übergreifendes Verständnisdokument** schreiben (auch ohne Vorwissen lesbar; eigene Datei).
- **Anforderungslisten** je App (Kern-Umfang umreißen).
- **Bestehende Doku überarbeiten** (Dizzi + Trading Bot Projektpläne/Systemübersichten auf den
  Gesamt-Rahmen ausrichten).

### O-UI (Bau-KI, jederzeit)
- **Dizzi-Feinschliff**: schärfere Kanten (Panels + Fenster), bildschirm-adaptive Größen (sauberer
  Reihen-Umbruch auf jedem Monitor), Icon-Auto-Drift erhöhen, Slingshot-Momentum langsamer/
  gleichmäßiger, obere Detail-Panels breiter / untere in zwei Reihen.
- **Trading-Bot Spin-Physik**: neue Panel-Mechanik (Achse am Greifpunkt, beweglich; Schwerpunkt
  verlagert; Schwingen→Schleudern; Kollision kopiert Momentum aufs getroffene schwebende Icon).
- **Schwebender Account+Settings-Knopf je App** (sobald K1/K2 stehen): der **driftende Schleuder-Knopf**
  aus dem verteilten `ui-kit/` (`FloatingSettings` + `spinFling`, Spin-Physik docs/14) wird in JEDER App
  eingebaut und um einen **Account-Icon/-Bereich erweitert** → ein einziger frei umherfliegender Knopf
  öffnet **Konto UND Einstellungen** (genau wie in „the world of dizzi"). Speist sich aus dem K2-Account/
  Settings-Core (6 Kategorien) + Dizzi-ID-Konto (K1). Trading-Bot: Konto+Settings als schwebendes
  Doppel-Fenster mit derselben Spin-Mechanik.

### O-Fill (Bau-KI, nach Kern)
- Feature-Implementierung je App auf dem App-Vertrag; Content; Doku-Pflege.

## 5. Session-Volumen-Schnitt (Bau-Reihenfolge)
**Phase R0 — JETZT, Bau-KI (kein Architektur-KI nötig):**
- R0.1 ✅ Ordner-Scaffolding aller 8 Apps (Commit `64eade9`, `ops/scaffold_apps.py`): Geschwister
  in „C:\Dizzik\code" — finanzen, buerokratie, projekte, social-media, creator, archiv, news, health;
  je Gesetze + Gesamtverständnis + Wiedereinstieg + Vision + App-Vertrag + Anforderungsliste.
- R0.2 ✅ Übergreifendes Verständnisdokument (`docs/12_GESAMTVERSTAENDNIS.md`, Kopie in jeder App).
- R0.3 ⏳ Doku-Überarbeitung Dizzi + Trading Bot (Dizzi-Docs angereichert; TB-Angleichung = R1.6).
- R0.4 ✅ Dizzi-UI-Feinschliff (Commit `ae97758`: scharfe Kanten, adaptives Raster, Drift/Slingshot).
  ✅ Trading-Bot-Spin-Physik portiert (11.06., Bau-KI): `initSpinFling`/`sfSwap` lösen Honig-Drag in
  `static/index.html` ab, `#iconLegend` empfängt `dizzi:fling`; Spin-Physik-Referenz (`ui-kit/`) in
  alle 8 App-Gerüste verteilt. Spec docs/14 §1.

**Phase R1 — Architektur-KI, vor 21.06. (je Punkt ≈ 1 Session):**
- R1.1 ✅ **K3 App-Vertrag + Referenz-Vorlage (12.06., Architektur-KI)** — Norm `docs/16_APP_VERTRAG_SPEC.md`;
  Bibliothek `appkit/` (Manifest+Deep-Link · Summary-Kachel-Format „immer 200" · DB-Konventionen als
  `Database`-Klasse · **Auth-Slot = K1-Austauschpunkt, Schutzstufen lokal<verifiziert<hochsicher,
  fail-closed vor K1** · App-Fabrik `create_app` · MCP-Helfer · **maschinelle Konformität**
  `conformance.check_contract`); Kopier-Vorlage `templates/refapp/` (Domäne in 3 Stellen: Schema/
  Router/summary_fn; PEP-563-Falle dokumentiert); Vendoring `ops/sync_appkit.py` (versions-gestempelt,
  Drift-Check beidseitig; **Vendoring erst nach Freeze R1.6**); Dizzi-Core konsumiert Vertrags-Apps
  **generisch** (`panels.register_contract_app` + env `DIZZI_CONTRACT_APPS`, kein Per-App-Mapping).
  Tests: appkit 10 + refapp 3 + core 80 (77+3) — alle grün. 8 App-Vertrag-Stubs verweisen auf die Norm.
- R1.2 ✅ **K1 Dizzi-ID Kern (12.06., Architektur-KI)** — OIDC-Provider `core/app/id/` (Issuer :8200/id):
  Discovery/JWKS · Authorize+Token (Code+**PKCE Pflicht**, single-use/60 s, exakter redirect-Abgleich) ·
  **Ed25519**-Tokens (RFC 9864, Alg gepinnt) · **Refresh-Rotation + Familien-Reuse-Widerruf** (RFC 9700) ·
  Login lokal (scrypt) + **Google-Broker** (RFC 8252 Loopback+PKCE, Konto-**Pinning**; Live = 5-Min-
  Nutzer-Schritt docs/17 §3) · Secrets nur gehasht · Audit komplett. RP-Anschluss `appkit/dizzi_id.py`:
  `install_dizzi_id()` = /auth-Routen + Identitäts-Provider am K3-Slot (require_level wird scharf;
  standalone-Fallback `lokal`); in refapp-Vorlage verdrahtet. Doku docs/17. Tests: core 89 (80+9) +
  appkit 13 (10+3 SSO-Cross) + refapp 3 = 105 grün.
- R1.3 ✅ **K1+ Sicherheits-Stufen (12.06., Architektur-KI)** — **TOTP-MFA (RFC 6238, stdlib-pur)** mit Replay-
  Schutz (last_counter) + Enrollment über `/id/stepup` (Secret+otpauth-URI, erster gültiger Code
  aktiviert); **Step-up-Mechanik**: `authorize?acr_values=hochsicher` erzwingt MFA, Session-Upgrade
  `verifiziert→hochsicher` (amr+`totp`), Tokens tragen die Stufe; RP fordert per
  `/auth/login?level=hochsicher` an. `sensitivity_level()`-Mapping (normal→lokal · hoch→verifiziert ·
  hoechst→hochsicher) als K5-Routing-Basis. **WebAuthn/Passkey = vorbereiteter Slot R1.3b** (gleiche
  Step-up-Mechanik, amr `webauthn`; braucht Nutzer-Hardware live). Tests: core 95 (+6) + Cross-Test
  Echtgeld-Route end-to-end (RP `hochsicher` erst nach TOTP) = 112 gesamt.
- R1.3b ✅ **WebAuthn/Passkey GEBAUT + LIVE (12.06., Architektur-KI)** — eigener Verifier
  `core/app/id/webauthn.py` (Mini-CBOR/COSE selbst + ECDSA-P256/Ed25519/SHA-256 aus `cryptography`,
  **KEINE neue Abhängigkeit**, F-Q1-konform) + Routen register/stepup (begin/finish) + Store
  (`id_webauthn`/`_chal`) + UI (`/id/geraete`, `/id/stepup`); prüft Challenge/Origin/RP-ID-Hash/
  **Signatur**/**Klon-Schutz** (sign_count), keine Attestation (Single-User). Browser-Navigation
  **host-relativ** (`_NAV`), weil WebAuthn eine IP nicht als RP-ID akzeptiert (`localhost` ja).
  **Live mit Nutzer verifiziert** (Windows Hello: Passkey „Mein PC" + Hochsicher-Step-up per Geste;
  DB+Audit belegt). 6 Tests; dizzi 168 grün. Details docs/17.
- R1.4 ✅ **K2 Account/Settings-Core (12.06., Architektur-KI)** — `appkit/settings_core.py`: typisiertes,
  versioniertes Schema (`SettingDef`: bool/int/float/str/choice + Grenzen + `sensitive`-Maskierung) in
  den **6 Kategorien**; Basis-Schema für ALLE Apps (sensible Apps starten `ki_routing=lokal_only`);
  PUT strikt validiert, `x_`-Namensraum frei (**Vertrag 1.0→1.1**, Chronik docs/16). `/api/settings/
  schema` (generisches Settings-Panel) + `/api/account` (Profil/Identität/SSO-Zustand) +
  **Token-Tresor** `appkit/vault.py` (Fernet-verschlüsselt, `/api/vault` liefert nur NAMEN, Werte nie
  über HTTP, auditiert; ehrliche Einordnung im Docstring). Tests 118 gesamt (23 appkit+refapp / 95 core).
- R1.5 ✅ **K4 KI-Interaktions-Protokoll (12.06., Architektur-KI)** — Sicherheits-Regel als Code: **beobachten +
  vorschlagen, nie eigenmächtig.** `appkit/actions.py`: Aktions-Vorschläge propose→pending→approve/
  reject/expired (TTL 24 h); **Freigabe verlangt die HITL-Stufe der Aktion** (lokal/verifiziert/
  hochsicher — Echtgeld-Aktionen damit hinter K1+TOTP), Handler laufen erst NACH Nutzer-Freigabe,
  alles auditiert; `/api/actions`-Endpoints (**Vertrag 1.1→1.2**). **Event-Push App→Dizzi**:
  `appkit/events.py` (best-effort, Setting-Gate `event_push`) → Core `POST /api/events` ⇒ Glocke +
  L4-Beobachtung. **L4 generalisiert**: `observe_contract_apps()` beobachtet ALLE angebundenen
  Vertrags-Apps (Kachel-Snapshots) und meldet neue pending-Vorschläge einmalig in der Glocke
  (Vorschlags-Pipeline). Tests 124 gesamt (27 appkit/refapp + 97 core).
- R1.6 ✅ **K5 KONSOLIDIERT + K6 GEBAUT (12.06. früh, Architektur-KI, Nutzer wach).**
  **K5**: faktisch in K2/K3 entstanden — Konventionen-Bibliothek = `appkit/db.py`, Sensibel-
  Kennzeichnung = Manifest-`sensitivity` + `sensitivity_level()` + `lokal_only`-Default; Sync bewusst
  Stufe 3. **K6 (architektonische Angleichung, LIVE auf :8137)**: appkit in den TB **vendort**
  (`programm/appkit`, joserfc ins TB-venv); dafür appkit refaktoriert zu **einbettbarem
  `contract_router(include=…)`** (Bestands-Apps wählen kollisionsfreie Endpoints — TB lässt
  summary/account/audit/health beim Legacy bis zur Voll-Angleichung R2.0, dokumentiert).
  `backend/app/vertrag.py`: Manifest (Dizz Trading, hoechst, Vertrag 1.2) + **Dizzi-ID-RP**
  (/auth/*, SSO aktiv) + Vertrags-Settings/Tresor/Aktionen (Daten getrennt unter
  `Dizzik\data\apps\tradingbot\`) + **Echtgeld-Gate**: ECHTER Transfer (bitget_configured &&
  !dry_run) verlangt `hochsicher` (fail-closed; Paper bleibt frei) — R-B-Linie. App-Titel „Dizz
  Trading — Orchestrator". **Live verifiziert: Neustart, Manifest/auth/Settings ok, Flotte 51/51
  Auto-Resume.** Tests: TB 302 passed (davon 3 neue test_vertrag) + vendierte appkit-Suite läuft mit
  (RP-Cross-Tests skippen sauber ohne IdP-Code). → **PHASE R1 KOMPLETT.**

**Phase R2 — Bau-KI, nach Kern (O-Fill + O-UI je App):**
- R2.0 ⏳ **Dizz Trading voll angleichen** (erste Bau-App). ✅ **Frontend-Auth/Konto (12.06., Bau-KI,
  TB `b5eb5b5`)**: Header-Auth-Pille (/auth/me) + Panel „Konto & Einstellungen" (Anmelden/Abmelden,
  **Echtgeld-Step-up→hochsicher**, generisches Settings-Rendering aus `/api/settings/schema` über alle
  6 Kategorien mit Sofort-Speichern/Validierung) — **Referenz-Muster für alle Apps**, live verifiziert.
  ⏳ Rest R2.0: Kachel-Umzug Legacy→Vertrag (optional, TB-Summary ist reich) · floating Account-Knopf
  (Spin-Mechanik, vanilla-Port von FloatingSettings) · TB-Doku-Voll-Pass.
- R2.1 ✅ **Dizz News v0.1 (12.06., eigenes git `1e168db`, LIVE :8216)** — erste Schwester-App,
  beweist die ganze Kette: refapp-Kopie + Feed-Kern (httpx+feedparser, Dedupe, Sektoren, kuratierte
  Seeds tagesschau/heise/Guardian) + **getaktete Automatik** (Daemon-Tick, K2-Settings Intervall/
  Schalter — feuerte live von selbst) + App-Vertrag komplett (SSO aktiv, Settings, MCP, Kachel) +
  **generisch in Dizzi angedockt** (`.env: DIZZI_CONTRACT_APPS` ⇒ Panel „news" aktiv, KPIs Quellen/
  Artikel/Abruf — NULL Core-Sondercode). 4 Tests; 45 echte Artikel beim Erst-Abruf.
  ✅ **Stufe 2 (12.06., news `a3b3667`): KI-Ebene + Oberfläche** — `ki.py` Briefing (Überblick +
  ⚑wichtig) + Fragen (Antwort NUR aus dem Artikel-Bestand, mit Belegen; ehrlich bei leerem
  Bestand/Ollama-Ausfall) lokal via Ollama · `static/index.html` auf GET / (Briefing-Karte mit
  Frage-Feld, Artikel mit Sektor-Tags, Quellen-Verwaltung, Datenrechte-Zeile). 39 Tests;
  Live-Beweis: Briefing 25,9 s über 40 echte Artikel. Offen: Spin/Floating-Knopf in der UI.
- ✅ **R-MUSIC-KERN (12.06., Architektur-KI, musik `00f2673`, LIVE :8220, vorgezogen auf Nutzer-Zuruf
  „Kernsubstanz mit Architektur-KI"):** alle 4 Ebenen als Kern — (1) Pattern-Engine `TrackState`
  (JSON sync-ready, deterministische pure Ops, Anker heilig, Genre-Profile als Daten/Techno v1)
  (2) Generator-Protokoll + GPU-Queue-Anbindung creator/engine (Adapter=R2-Fill; ehrliche Grenze:
  Klasse geteilt, Prozess-Verbund=R2.9) (3) Analyse stdlib-pur (Onsets/BPM) + **LiveAnalyzer**
  (PCM-Push, Rollfenster, Pattern-Mitschrieb — keine Aufnahme) (4) **MusicSource-Registry mit
  Fähigkeits-Gates = Rechtslinie als Code** (Spotify/YouTube download ⇒ 403 §95a; SoundCloud-
  Publishing-Slot; LokaleBibliothek voll). Dazu MIDI-Export SMF Typ 1 stdlib-pur + Co-Produzent-
  Dialog (deutsches Regelwerk → Op-Liste, LLM-Hook-Slot, Projekt-Gedächtnis, Ergründungs-
  Rückfragen). App-Vertrag komplett, generisch in Dizzi angedockt (Panel musik). 59 Tests.
  R2-Fill (Bau-KI): Frontend/Spin, Ollama-Hook, ACE-Step/SAO-Adapter, WASAPI-Zuführung,
  SoundCloud-OAuth, librosa-Tonart.
- ✅ **R2.2-FUNDAMENT Communication E-Mail-Schiene (12.06., Architektur-KI, kommunikation `cc67279`,
  LIVE :8218):** die schwer nachrüstbare Substanz — **kanal-agnostisches Schema** (konto→
  konversation→nachricht + Kontakte-Klammer; kanal_typ+extern_id ⇒ Matrix/Webview später OHNE
  Umbau) · `KanalQuelle`-Schnitt + **ImapQuelle stdlib** (XOAUTH2-SASL [MS-Basic-Auth-Ende
  30.04.2026], **UIDVALIDITY/UIDNEXT-Sync-Zustandsmaschine** als pure Funktion, injizierbare
  Factory = netzfrei testbar) · Threading (References-Wurzel) · **Senden = HITL-Aktion
  `verifiziert`** (standalone ⇒ 403, getestet) · Geheimnisse NUR im Tresor (tresor_ref).
  Vertrag komplett (hoechst ⇒ lokal_only), generisch angedockt, 39 Tests.
  R2.2-Fill (Bau-KI): Gmail-Scopes/Token-Refresh, Sync-Automatik, Posteingang-UI, KI-Triage
  lokal; danach Schiene A Webview + Schiene B Matrix.
- ✅ **R-MONEY-KERN (12.06., Architektur-KI, finanzen `14a2727`, LIVE :8210)**: der F-Q1-Kern mit
  erhöhter Sorgfaltspflicht — eigener **Double-Entry-Ledger** `moneyapp/ledger.py` (Geld =
  ganzzahlige Minor-Units, nie Float; Decimal nur am Rand mit ROUND_HALF_UP; Posting/Buchung
  mit **harter Invariante Summe=0** im Konstruktor ⇒ unbalancierte Buchung unmöglich;
  typ-orientierter Anzeige-Saldo) + vertragskonforme App (appkit `create_app` ⇒ Vertrag 1.4 +
  Dizz Defense + Dizzi-ID frei; Domäne konten/buchungen/postings, Betrag INTEGER; Router bucht
  nur nach Ledger-Prüfung) + read-only MCP. **Property-Tests** (deterministisch/seed: Roundtrip
  2000× exakt invers, 500 Zufallssysteme global konsistent, 2000× unbalanciert abgelehnt) +
  E2E; 80 Tests. In Dizzi via `.env` angedockt (Panel finanzen aktiv, NULL Core-Code).
  R2-Fill (Bau-KI): Import CSV/CAMT/MT940, Budgets/Cashflow, FinTS/Revolut (AISP, nur lesend),
  Steuer-Sektor, Frontend (Fenster-/Spin-Norm).
- R2.2+ **je App** (Money [Kern ✅ s. o.], Admin, **Memory** [vorm. Knowledge, REV-5],
  Management, **Creating** [= Video/Bild **+ Musik**-Modus, REV-1; Engine+Musik-Kern ✅;
  Architektur-KI-Schwergewicht s. R2.9], Healthy, Plans, **Communication** [Fundament ✅ s. o.],
  **Leading** [exklusiv; als Aggregator ZULETZT — nach Admin/Money/Communication]), pro App:
  - (a) Domänen-Kern + Konnektor-Adapter (auf der K3-Referenz-Vorlage),
  - (b) Stats-Endpoint + MCP-Tools (Dashboard-Kachel + Dizzi-Anbindung),
  - (c) **schwebender Doppelicon-Knopf + Einstellungs-FENSTER** (ui-kit `FloatingSettings`+
    `spinFling`; Tipp öffnet das zentrierte Fenster nach docs/19 §2b: Identität/Dienste/
    KI-Aktivität/Einstellungen — **im DESIGN der jeweiligen App** [TB+Dizzi ✅; übrige Apps:
    Design-Baseline als markierte Zwischenlösung bis zum Frontend-Bau]; aus K2-Core + Dizzi-ID),
  - (d) Spin-Physik-Panels (ui-kit bereits verteilt) + Design-Baseline (Metall/Cyan-Magenta).
- **R-ROLLOUT (Bau-KI, freigegeben — Mechanik ABGENOMMEN 12.06. abends)**: Das
  „Übernahme-System" — Spin-/Float-Mechanik **v4.1–v4.3** (docs/14: exakte Hitbox,
  Doppelicon, Halbmomentum, Klappzeilen-Norm v4.2, Float-Regeln v4.3 Body-Ebene/
  overflow-x:clip/leichter Abstoß/N-Float-Registry) + **Fenster-Norm** (docs/19 §2b:
  50 % Mitte, solid, Body-Ebene) verbindlich in ALLE Apps übernehmen — zuerst die
  drei Live-UIs **news/kommunikation/musik**, dann jede neue App ab Tag 1
  (ui-kit-Refresh + Einhäng-Checkliste). „Unsere coole Spielmechanik in allen Apps."
- **K2.2 (Bau-KI-tauglich, Grundgerüst JETZT ablegen — Nutzer-Auftrag 12.06. abends)**:
  **Settings-/Konto-VOLLAUSBAU**: (a) **Design-Vorlagen und Farb-Schemata SEPARAT
  wählbar** (zwei Settings: `design_vorlage` [z. B. Glas/Neon · Metall · Flat-Dunkel …]
  × `farb_schema` [Cyan-Magenta · weitere Paletten] — technisch als CSS-Token-Satz je
  App, Norm in docs/06/19); (b) Settings-Katalog docs/19 §2 KOMPLETT ausdefinieren
  (gemeinsame Session mit Nutzer); (c) Konto-Verwaltung ausbauen (docs/19 §1-Soll:
  Avatar/Farbe, Sicherheits-Ereignisse sichtbar, Dienst-Scopes); (d) Grundgerüst in
  `appkit/settings_core.py` ablegen, damit JEDE App es ab sofort mitbekommt.
- **F-DEF „Dizz Defense" (Architektur-KI; Name+Politik entschieden 12.06. spätabends, docs/_archiv/20 §5)**:
  - **F-DEF1 ✅ GEBAUT (12.06. spätabends, Architektur-KI, Vertrag 1.3→1.4)**: `appkit/defense.py` =
    Per-App-Immunsystem — Sensorik-Middleware (äußerste Schicht) + Regel-Engine (Brute-Force/
    Pfad-Scan/Köder/Signaturen/Raten) + EWMA-Basislinie + Stufenwerk S0–S5 mit Autonomie-
    Politik (S1/S2 autonom befristet + Wiederholer-Eskalation; S4/S5 = HITL-Aktionen, „panik"
    schaltet S4 selbst; Lokal-Schonung) + Cockpit-API + persistentes Journal + Settings;
    in `create_app` default AN, Konformität prüft mit. Tests: 15 neue (appkit 172 gesamt
    dizzi-seitig grün), vendort in news/komm/musik/TB (**aktiv ab deren nächstem Neustart**),
    Komm-Katalog-Test angepasst. Bestands-Apps: `install_defense()` (TB = O-DEF).
  - **F-DEF2 ✅ GEBAUT (12.06. spätnachts, Architektur-KI)**: **Föderations-Immunität**
    (`core/app/defense_hub.py` = Dizzi-SOC-Dach, Minuten-Takt im Lifespan: sammelt Sperren
    aller Vertrags-Apps, verteilt sie an alle über `POST /api/defense/verbund`; Echo-Schutz
    `verbund:`-Präfix, Loopback/Lockdown nie geteilt, Glocke) — **live verifiziert** (Köder
    auf News ⇒ Komm+Music sperren automatisch) · **LLM-Triage** (`llm_triage` lokal Ollama
    JSON-Schema, Daemon-Thread, ehrlicher Fallback, Journal `ki_triage`, Gate
    `defense_triage_aktiv`) · **KI-Selbstschutz** (`pruefe_prompt` Prompt-Injection-Heuristik
    als appkit-Primitiv). 35 Defense-Tests; alle Suiten grün; vendort+Apps neu gestartet.
  - O-DEF (Bau-KI, danach): Cockpit-UI je App (Fenster-Norm), Berichte, TB-`install_defense`,
    PyRASP-/CrowdSec-/Cloudflare-Adapter (Opt-ins bestätigt), Marketing/Whitepaper je App.
  Recherche/Architektur: **docs/_archiv/20_RECHERCHE_DEFENSE_KI.md (R-C)**; Sicherheits-Einbettung
  docs/18 §7.
- **R-STRUKTUR (Nutzer-Auftrag 12.06. nachts, eigene Migrations-Session, NACH Tiefen-Review)**:
  **Endgültige Datenstruktur** — EIN übergeordneter Ordner (Name vom Nutzer noch zu nennen,
  RÜCKFRAGE offen), darin je App ein Ordner mit: (a) **`Appfiles <App>/`** = die Anwendung
  (Code/Repo), (b) **`Workfiles <App>/`** = perfekte Arbeits-Doku (Wiedereinstieg,
  Gesetze, Vertrag-Verweis) — so geformt, dass auch fremde KI-Sessions ohne Vorwissen an
  der Einzel-App perfekt weiterarbeiten können, (c) auf oberster Ebene das **technische
  Mega-Datenblatt** (Systemübersicht: Kurzfassungen + In-Depth je App + Netzwerk-Zusammenspiel).
  Arbeitsmodell: Einzel-Chats je App + EIN Verwaltungs-Chat fürs große Ganze (Kontext-Schonung).
  Migrations-Checkliste: git-Pfade, OneDrive, TB-Autostart-Task (launch.ps1-Pfad!), venvs,
  Desktop-Verknüpfungen, DIZZI_CONTRACT_APPS. Gedächtnis: dizzi-ziel-ordnerstruktur.
- R2.9 **Dizz Creating — Medien-Suite (Video/Bild + Musik, REV-1) — Architektur-KI-SCHWERGEWICHT.**
  ✅ **Engine-Kern R1.7 GEBAUT (12.06., Architektur-KI)**: `creator/engine/` (eigenes git `56c97b8`, 7 Tests) —
  **JobQueue** (GPU-seriell, Status/Progress/Cancel-pending; laufende GPU-Jobs nicht abbrechbar) ·
  **Generator-Protokoll** + ComfyUI-Adapter (POST /prompt → History-Polling, workflow-agnostisch,
  test-injizierbar) · **Editor-Protokoll** + ffmpeg-Fundament (cut/concat/silencedetect + Parser).
  ✅ **Musik-Kern GEBAUT (12.06., Architektur-KI, `musik/`)**: 4 Ebenen (Pattern-Engine/Analyse/MusicSource/
  MIDI/Dialog) — wird **Musik-Modus** von Creating (REV-1).
  ✅ **SUITE-KERN GEBAUT (13.06. nachts, Architektur-KI, creator `a66a8ca`, LIVE :8214, 121 Tests)**:
  `creatorapp/` = **Zeitachse** (timeline.py, das Verschränkungs-Herz) + **Sound-Symbiose**
  (symbiose.py: score_plan/BPM-Empfehlung/beat_sync/Ducking-ffmpeg-Bauer) + **DAM** (Assets mit
  Modell+Lizenz/Rechten, Varianten) + **Schutz** (Illegal-Sperre §184b KONSTANTE,
  auditiert) + **Musik-Kern physisch eingeschmolzen** (creatorapp/musik, Quelle
  `musik/` eingefroren `c95f5ae`; :8220 läuft bis zum UI-Umzug) + App-Vertrag 1.5/Dizzi-ID-RP/
  EINE GPU-JobQueue; Panel `creator` im Dashboard live. Details: creator/WIEDEREINSTIEG_PROMPT.md.
  ✅ **KONZEPT-UPGRADE §R-E (13.06., 2. In-Depth-Runde, Nutzer: „bombastisch, alle Register")**:
  Suite = SCHAFFENSPROZESS (Brief→Storyboard→Produktion→Veredlung→Schnitt+Symbiose→Export) ·
  **Stil-Identität** (eigene LoRAs lokal/16 GB, Charakter-Locking, Sound-Signatur, Voice-Clone) ·
  **Rezept-System** (Reproduzierbarkeit, verkaufbare Presets) · **Bearbeitung gleichwertig**
  (Inpaint/SAM/ControlNet · Reframe/Captions/RIFE · Demucs-Stems/Mastering) ·
  **KI = Kreativ-Direktor** (ergründen→orchestrieren[HITL]→Geschmack lernen).
  ✅ **KATEGORIE-SYSTEM §R-F (13.06., 3. Runde)**: „in ihrer Kategorie unschlagbar" —
  Kategorie-Profile als DATEN je Kunst (Bild 9 Kategorien inkl. Foto-Treue-8-Punkte-
  Framework „nicht als KI erkennbar" · Video 10 Formate mit Plattform-Schnittregeln ·
  Musik 10 Seed-Genres + ACE-Tag-Vokabular); Kategorie=Handwerk, Stil-Profil(E2)=Handschrift.
  ⏳ **R2.9-Fill (Reihenfolge §R-E E6 + §R-F F5):** **(a0) Kategorie-System (katalog/ +
  /api/kategorien)** · (a) ComfyUI+Bild-Gen+Bild-Veredlung (profilgesteuert) · (b) Rezepte+
  Charaktere/Stil-Profile · (c) Video Wan 2.2+Editing/Veredlung · (d) Musik-Render+Stems/
  Mastering · (e) Symbiose E2E · (f) Kreativ-Direktor-Orchestrierung · (g) Suite-UI (Bau-KI) ·
  (h) LoRA-Training + Management-/Memory-Brücke. Dossiers: §R-A/§R-D/§R-E/§R-F.
- Querverbindungen scharfschalten (Money↔Trading, News→Memory, Creating→Management, Admin→Plans …).

## 5b. PLAN-REVISION (Fragerunde 4, 13.06.2026 — Nutzer-Entscheid, VERBINDLICH)
> Diese Revision hat VORRANG vor älteren Einzelnennungen weiter unten; bei Widerspruch gilt §5b.
> Hintergrund: der Nutzer will aus den Medien-Apps **echte, professionelle Profi-Werkzeuge** machen
> (Verkaufs-Anspruch G4) und hat drei Apps neu zugeschnitten. Recherche-Dossiers: `creator/docs/
> RECHERCHE.md` (Voll-Update R-D), `finanzen/docs` (Klarna/Revolut), `memory/docs`.

### REV-1 — Dizz Creating = Medien-Suite (Video/Bild **+ Musik** in EINEM Tool)
- **Dizz Music wird in Dizz Creating eingeschmolzen.** Es gibt KEINE eigenständige Music-App mehr;
  der gebaute `musik`-Kern (Pattern-Engine, Analyse, MusicSource, MIDI, Dialog — alle 4 Ebenen)
  wird zum **Musik-MODUS** von Creating. Creating bekommt umschaltbare Modi:
  **Bild · Video · Musik** (gemeinsame Shell, gemeinsame JobQueue/GPU, gemeinsame KI/DAM).
- **Anspruch (hart):** Profi-Arbeitswerkzeug, mit dem man **Social-Media-Content jedweder Art**
  produziert — Bilder/Videos generieren UND bearbeiten/schneiden, Musik erstellen/bearbeiten/holen.
  Hier fließt **viel Architektur-KI-Effort** rein (Kern-Architektur der Engine + Modus-Verschränkung).
- **Sound-Symbiose Musik↔Video (REV-2):** Kernanforderung, eigener Architektur-Block.
- **DAM (Asset-Verwaltung):** zentrales Verwaltungssystem aller Erzeugnisse (Bild/Video/Audio),
  Varianten/Versionen/Rechte; Brücken zu **Dizz Management** (Verteilen/Posten) und **Dizz Memory**
  (Archiv/Wissen). Social-Media-Automatisierung (REV-3) baut darauf auf.
- Port-Konsequenz: Creating bleibt **8214**; 8220 (alt Music) wird frei (Music-Funktionen
  laufen im Creating-Prozess; gemeinsame GPU-Queue ohnehin geplant). `musik`-Ordner =
  Kern-Quelle, die in Creating integriert wird (Migrations-Detail bei der Umsetzung).
- **Architektur-KI-Last:** HOCH. Mehrere Recherche-Runden gelaufen (13.06., s. creator/docs RECHERCHE §R-D);
  Die Architektur-KI soll die schwierigen Teile (Modus-übergreifende Timeline, Sound-Symbiose,
  DAM-Schema) als Kern-Architektur lösen.

### REV-2 — Sound-Symbiose Musik-Modus ↔ Video-Modus
Wenn man im Video-Modus vertont, soll der Musik-Modus **perfekt mitspielen** (kein loses Nebeneinander):
- **Auto-Scoring**: Video-Schnittpunkte/Szenen (PySceneDetect) ⇒ der Musik-Modus erzeugt/passt einen
  Track an die Schnitt-Struktur an (Länge, Stimmung, Akzente auf Cuts).
- **Beat-Sync**: BPM/Beats des Tracks ⇒ Schnitte/Übergänge/Effekte rasten auf den Takt
  (ffmpeg fps↔BPM, Audio-reaktive Übergänge).
- **Ducking/Mix**: automatische Side-Chain-Kompression (ffmpeg `sidechaincompress`) — Musik duckt
  unter Sprache/Sound-FX; sauberer Mix als ein Schritt.
- **Technik-Anker (Recherche 13.06.):** **LTX-2** (Lightricks, Jan 2026) generiert **synchronisiertes
  Audio+Video nativ** — als Premium-Pfad vorzusehen; klassischer Pfad = getrennte Spuren +
  Symbiose-Logik (MoviePy/ffmpeg) als verlässlicher 0-€-Boden. Beide als Adapter.

### REV-3 — Social-Media-Automatisierung (Creating ↔ Management) = Priorität
Wichtigstes Fernziel der Medien-Schiene: benannte „Social-Media-Bots" (Themen-/Marken-Profile),
die **KI-gesteuert übergreifend** Content erzeugen (Creating) und posten (Management), inkl. Musik
(Symbiose). Stufen: (a) Creating→Management-Übergabe-Vertrag (Asset+Metadaten+Kanal-Derivate);
(b) Management orchestriert Kanäle (IG/TikTok/X/YouTube/LinkedIn); (c) Automatik mit HITL-Freigabe.

### REV-5 — Dizz Knowledge → **Dizz Memory** (umbenannt) + Mem-ähnliche UI
- **Marke „Dizz Memory"** (eingängiger für ein Notiz-/Wissens-/Gedächtnis-Tool). Ordner-`id`
  bleibt vorerst `archiv` (Code/Scaffold-Pfad; harte Umbenennung = R-STRUKTUR-Migration).
- **UI-Soll (an Mem.ai angelehnt):** dreigeteilt — **oben** KI-Interaktions-Panel (mit der
  App-eigenen KI + Dizzi-Sprache reden), **links** Ordnerstruktur-/Verwaltungs-Dashboard
  (Ordner + **Labels**, KI-gestützt strukturieren), **Mitte/rechts** eigene Notizen + Editor +
  Einstellungen. Strukturierte Ordnerarbeit, KI verwaltet übergreifend (verschieben/labeln/
  verknüpfen mit HITL). Import aus Mem.ai (bestand schon als Quelle).

### REV-6 — Dizz Money: Multi-Bank + Revolut + Klarna (ehrlicher Weg)
Recherche 13.06.: **direkte** Open-Banking-APIs von Revolut/Klarna verlangen **TPP/AISP-Lizenz +
eIDAS-Zertifikat** — für ein Einzelnutzer-Tool nicht direkt nutzbar. Daher gestuft:
1. **FinTS/HBCI** (DE-Banken direkt, 0 €, keine Lizenz) = Primärweg, mehrere Konten.
2. **CSV/CAMT/MT940-Import** für ALLES (Revolut/Klarna/N26 … exportieren Umsätze) = sofort,
   universell, lokal — der pragmatische Multi-Quellen-Boden.
3. **Bezahlter Aggregator als Opt-in-Slot** (Klarna Kosma / Tink / GoCardless, AISP-nur-lesend):
   vorbereiteter `BankSource`-Adapter (Gesetz 5), scharf nur bei bewusster Nutzer-Freigabe.
   Klarna-BNPL-Käufe = eigener Klarna-Consumer-Export, kein Bankkonto (im Schema getrennt führen).
Bleibt bei der Linie „nur lesen (AISP), keine Zahlungen" (Fragerunde 3).

### REV-7 — Marken-Doppelname / „Lockup"-Norm (= K2.3, Nutzer-Wunsch 13.06.)
**Entscheid:** Jede App behält ihren **Markennamen betont vorne** (das ist der „richtige" Name —
Dizz Money, Dizz News, …), aber der bisherige **beschreibende Funktionsname bleibt dezent dahinter**
(Finanzmanagement, Nachrichten, …). So weiß jeder trotz der Eigenmarke **auf einen Blick, welche App
das ist** — die Marke verschwindet nicht, der alte Name verschwindet auch nicht.
1. **Render-Norm, kein neues Datenfeld.** Die kanonischen Werte liegen schon im Manifest
   (`brand` = Marke, `name` = Funktion) — KEIN Vertrags-/appkit-Bruch (additiv, Vertrag bleibt 1.5).
   Kanonische Spec: **docs/06 §5 „Marken-Lockup"**. Reihenfolge-Invariante: **Marke zuerst (betont),
   Funktion dahinter (gedämpft)** — nie umgekehrt.
2. **Überall einheitlich**, wo eine App benannt wird: App-Frontend-Kopf · Browser-Tab-`<title>` ·
   Core-Dashboard-Kachel (`panels.py`/Shell) · Desktop-Monitor-Chip („Dizz Network") · später
   Tauri-Fenstertitel. Tokenbasiert (Marke = Satin-Chrom-Akzent, Funktion = `--mut`), passt sich
   so automatisch den K2.2-Themes an.
3. **Rollout je Fläche** = kleiner, gleichförmiger Schritt; nach der ERSTEN Referenz (Core-Dashboard
   + News als Frontend-Muster, 🌍/Bau-KI) ist die Per-App-Übernahme **Assistenz-KI-tauglich**.
4. **Wording-Feinschliff je App** (z. B. „News Compact"→„Nachrichten", „Nachrichtenverkehr"→
   „Kommunikation/Postfach") = kleine App-Chat-Mikro-Aufgabe am `manifest.name`; die Norm selbst
   ist davon unabhängig (sie rendert, was im Manifest steht). Scaffolds (Memory/Admin/…) bekommen
   ihr Funktions-`name` beim Bau.

**Umsetzung:** ✅ **Erste Referenz gebaut (13.06., Core-Dashboard-Kachel)** — `PanelManifest.brand`
+ Seed-Marken + `.lockup`/`.fn`-Render, alle 13 Kacheln browser-verifiziert (Spec docs/06 §5).
Offen = Assistenz-KI-Rollout je App-Frontend + `<title>` + Desktop-Monitor.

### REV-8 — K2.4 UI-Controls & einklappbare Panels (Nutzer-Wunsch 13.06.)
**Entscheid:** Die nativen Browser-Controls (Ankreuzkästchen, Ausklapp-/Auswahl-Listen, ▲/▼-Stepper
wie der Seed-Wähler) und große, unübersichtliche Panels passen nicht zum Konzept. K2.4 macht **alle
Bedien-Elemente UND große Panels theme-konform**: tokenbasierte Control-Familie (Checkbox/Radio/Stepper/
Select via `appearance:none`/`base-select`, zugänglich) + **einklappbare große Panels mit High-Level-
Kurzanzeige im eingeklappten Zustand** (Progressive Disclosure). **Übergreifend** — besonders das
**Einstellungsfenster** und **ausdrücklich auch der Core/World-of-Dizzi (:8200)** (eigene App ⇒ erbt
zusätzlich K2.2-Theme-Switcher + K2.3-Lockup). Recherche-gestützt (2025/26). Kanonische Spec **docs/06 §6**.
**Umsetzung:** K2.4-(a) Norm + ui-kit-Bundle (`controls.css`/`collapse.js`) + Token-Master + erste Referenz
(News + Core) = 🌍/Bau-KI; K2.4-(b) Rollout je App = Assistenz-KI. Neue Frontends (Memory) bauen sofort mit K2.4.

### REV-9 — Der „Dizz Trading"-Look als erstklassige Designoption (Nutzer-Wunsch 14.06.)
**Entscheid:** Der jetzige Trading-Bot-Look (Retro-Chrome/Synthwave-Neon) soll erhalten bleiben UND als
**netzwerkweit wählbares Design** verfügbar sein. Umgesetzt im Token-System (leicht — ein `data-design`-
Block): das **`neon`-Theme** trägt jetzt die TB-Werte **1:1** (docs/06 §7, browser-verifiziert 14.06.;
Token-Master + ui-kit-Kopie + Core-Shell synchron). ⇒ `data-design="neon"` auf jeder App/dem Core = die
TB-Optik, frei mit allen 10 Farbschemata kombinierbar. Die strukturelle TB-Signatur (Scanline-Grid/
Verlaufs-Knöpfe/Glow) = optionale **„neon-extras"**-CSS-Schicht (kein Kern-Token). **Folge für den
TB-Switcher-Retrofit (Bau-KI):** TB aufs Token-System heben mit **`neon` als Default** — TB sieht aus wie
jetzt, bekommt aber den Umschalter (10×10) + K2.4-Controls.

## 5c. QUERVERBINDUNGS-PLAN (Phase 2 — App-zu-App-Vernetzung, Nutzer-Entscheid 15.06.2026)
> Stand: alle 11 Apps + Core live, alle an Core gebunden (SSO/MCP/Stats = das **Rückgrat**, steht).
> Phase 2 baut die **direkten App-zu-App-Datenflüsse**. Visualisierung: Interaktionskarte (World-Chat).
>
> **★ TRANSPORT-FUNDAMENT GEBAUT (15.06., Spec docs/26):** Transport = **über den Core** (Nutzer-Entscheid).
> Core-Relay `POST /api/querverbindung/{ziel}` (auditiert zentral) + appkit-Helfer `archiviere()` (appkit
> **1.7.0**) + Memory-Empfänger live (Server neu gestartet — war STALE). **End-to-End verifiziert** (Core→
> Memory: archiviert · idempotent · auditiert). ⇒ V2/V3/V4 + alle „→Memory"-Kanten brauchen jetzt nur noch
> ihre **Sendeseite** (App-Chats: appkit ≥1.7.0 vendoren, `archiviere(...)` rufen).
>
> **★ STEUER-SCHICHT „Archiv-Regeln" (Nutzer 15.06., docs/26 §8):** Der Nutzer legt **je (Quell-App ×
> Strom) klipp & klar** fest, was automatisch ins Archiv wandert: `aus` · **`manuell`** (auf Zuruf) ·
> `auto` · `auto_gefiltert` (+Filter). **Konfiguriert IN Memory** (zentrale Autorität), **Default
> `manuell`** (nichts flutet ungefragt; Readwise-Prinzip), selbst-registrierend. Umschlag +`strom`/
> `explizit` ✅ gebaut. **INVARIANTE: die Regel-Engine (Memory-App-Chat: `archiv_regeln`-Tabelle +
> Panel + Status `uebersprungen`) landet VOR dem ersten `auto`-fähigen Sender** — sonst archiviert
> Memory ungefragt alles. **★ ENGINE ✅ GEBAUT (15.06., archiv `8a79af6`):** `archiv_regeln`-Tabelle +
> Empfangs-Handler (Status `uebersprungen`) + `GET/PUT/DELETE /api/archiv-regeln` + Selbst-Registrierung
> + Filter; 34 archiv-Tests, live verifiziert. **Panel ✅ GEBAUT** (Sektion im Einstellungs-Fenster,
> browser-verifiziert; archiv `ecedc86`). ⇒ Steuer-Schicht komplett nutzbar.
> **★ V2 (News→Memory) ✅ ERSTE SENDESEITE GEBAUT + LIVE (15.06., news `41d7c78`):** `report_lauf`
> Auto-Archiv (`strom=sektor_report`, Regel-gated) + expliziter Knopf-Endpoint (`/api/reports/{id}/
> archivieren`); appkit 1.7.0 in news vendort; End-to-End News→Core→Memory verifiziert (archiviert/
> idempotent, aufgeräumt). ⇒ **Muster für V3/V4/… steht** (App ruft `archiviere(...)` mit ihrem `strom`).

**Muster für JEDE Verbindung (docs/_archiv/23 „Übergabe-Vertrag"):** Daten bleiben bei der **Quelle** ·
das **Ziel bestätigt** (HITL, Stufe nach Sensitivität) · jede Übergabe ist **idempotent + auditiert**.
Pro Verbindung = ein kleiner Vertrag (Felder + HITL-Stufe). **World-Chat** entwirft den Vertrag,
die **App-Chats** bauen die Sendeseite. Sensitivität reist mit: Geld (Money/Trading) **read-only + HITL,
nie Echtgeld-Auslöser**; Healthy (`hoechst`) gibt nur **Termin-Meta**, keine Messwerte.

**★ LEITIDEE — Dizz Memory = übergeordnetes Archiv des Netzwerks (Nutzer 15.06.):** Memory ist nicht nur
eine App, sondern der **netzwerkweite, menschlich zugreifbare/durchsuchbare/bearbeitbare Archiv- &
Wissens-Layer** für die verwaltenden Apps. Apps, die NICHT direkt vernetzt sind, legen Informationen
**über Memory** zwischen und greifen sie **anderswo** wieder ab (z. B. Managements automatisierte
Posting-Daten → in Memory archiviert → in Admin/Leading sichtbar). Memory hat dafür bereits den
Empfangs-Slot `POST /api/querverbindung/archivieren` (idempotent/auditiert) + kombinierte FTS/semantische
Suche + MCP `memory_suche`. ⇒ Jede „→ Memory"-Kante hat die **Empfangsseite schon stehen**; zu bauen
sind die Sendeseiten + das Rücklesen (`memory_suche`).

**Verbindungs-Register (alle werden gebaut — Nutzer 15.06., erweitert):**

| # | Verbindung | Was fließt | Empfangsseite | Status |
|---|------------|-----------|---------------|--------|
| V1 | **Creating → Management** | fertige Medien-Assets → Kanal-Post-Entwürfe (REV-3, „Social-Media-Bots") | `/api/creating/empfang` ✅ | Sendeseite (DAM) bauen |
| V2 | **News → Memory** | relevante Artikel/Sektor-Reports → Archiv | `/api/querverbindung/archivieren` ✅ | Sendeseite |
| V3 | **Creating → Memory** | Erzeugnisse/Rezepte/Assets → Archiv | Memory-Slot ✅ | Sendeseite |
| V4 | **Communication → Memory** | wichtige Mails/Nachrichten **+ Anlagen** → Notizen/Rücklagen/Archiv | Memory-Slot ✅ | neu *(Nutzer-Priorität)* |
| V5 | **Communication ↔ Plans** | Termine/Einladungen aus Mails ↔ Plans-**Kalender** (beide Richtungen) | Plans Calendar-Slot | **✅ VOLL BIDIREKTIONAL** — hin: GEBAUT 15.06. (komm→Core→Plans, ZWEITER Vertragstyp `sende_termin`/appkit 1.9.0); **zurück ✅ GEBAUT 17.06. (World-Chat)**: Plans „→ Kommunikation"-Knopf (`POST /api/termine/{id}/an-komm`) → Komm-Empfänger `POST /api/querverbindung/kalender` (read-only Tabelle `kalender_termine` + Panel + DELETE), generischer Relay/kein neuer Vertragstyp, 5 Tests, **Live-E2E** eingetragen+idempotent+Cleanup (docs/26 §4b). Offen: Auto-Datums-Extraktion aus Mails |
| V6 | **Memory ↔ Plans** | Projekt-Wissen/Notizen archivieren ↔ rücklesen | Memory-Slot ✅ + `memory_suche` | **Sendeseite ✅ GEBAUT 15.06.** (`4c75d93`, Plans→Memory live); Rücklese-Richtung offen |
| V7 | **Memory ↔ Admin** | Dokument-/Vorgangs-Wissen archivieren ↔ rücklesen | Memory-Slot ✅ + `memory_suche` | **Sendeseite ✅ GEBAUT 15.06.** (`3f24de4`, Admin→Memory live; Dokument-Metadaten); Rücklese-Richtung offen |
| V8 | **Memory ↔ Management** | Posting-Daten/Kampagnen archivieren ↔ rücklesen (Brücke zu Admin/Leading) | Memory-Slot ✅ + `memory_suche` | **Sendeseite ✅ GEBAUT 15.06.** (`1d779da`, Management→Memory live; Post-Log); Rücklese-Richtung offen |
| V9 | **Memory ↔ Money** | Finanz-Notizen/Report-Verweise archivieren ↔ rücklesen | Memory-Slot ✅ + `memory_suche` | **Sendeseite ✅ GEBAUT 15.06.** (`da64883`, Money→Memory live, Beleg, immer `sensibel`); Rücklese offen |
| V10 | **Memory ↔ Healthy** | Gesundheits-Notizen archivieren ↔ rücklesen | Memory-Slot ✅ | **Sendeseite ✅ GEBAUT 15.06.** (`21c106a`, Health→Memory live, Verletzung, immer `sensibel`+Confirm-HITL); K4-Step-up + Rücklese offen |
| V11 | **Memory ↔ Trading** | Trading-**Reports** schnell ablegen ↔ rücklesen | Memory-Slot ✅ | **✅ LIVE 16.06.** (Go-Live durchgeführt, Nutzer-Go): TB-Branches in master `0699ab4` gemergt (309 T), :8137 neu (V11-Endpoint live · Flotte 51/51, O15 zurück · Heartbeat aktiv), Live-E2E Report→Memory archiviert/sensibel/Trading/idempotent + Cleanup. Details docs/26 §11.5 |
| V12 | **Admin → Plans** | Dokument-Fristen (Frist-Wächter) → Aufgaben/Termine | Plans `CalendarSource` (Slot) | **✅ LIVE 16.06. (World-Chat)**: Admin `_frist_an_plans` + HITL `POST /api/aufgaben/{id}/an-plans` schaltet den V12-Slot scharf (V5-Kalender-Vertrag `sende_termin`, `ref=admin:frist:<id>`, idempotent, best-effort); `kalender_post`-Injektion + 2 Tests (Admin 39 grün). Commit `eda52a2`, Admin neu gestartet, **Live-E2E** Admin→Core→Plans = `eingetragen` + Cleanup. |
| V13 | **Healthy → Plans** | Gesundheits-**Termin-Meta** → Kalender (keine Werte, `hoechst`) | Plans Calendar-Slot | **✅ LIVE 16.06. (World-Chat)**: Healthy `_termin_an_plans` + HITL `POST /api/termine/{id}/an-plans` (V5-Vertrag `sende_termin`, `ref=health:termin:<id>`); **hoechst-konform: nur Meta (Titel/Datum/Ort/Kategorie), KEINE notiz/Werte** — Unit-Test + **Live-E2E** belegen: kein Wert-Leak in Plans. `kalender_post`-Injektion + 2 Tests (Healthy 23 grün). Commit `a1dc58c`, neu gestartet, E2E `eingetragen` + Cleanup. |
| V14 | **Money ↔ Trading** | Trading-Gewinne **steuerlich** in Money (Einstiegskapital/Verlauf/Schwellen) · Performance read-only ← | beidseitig neu | **✅ GEBAUT + LIVE 17.06. (World-Chat, Training pausiert)**: Money = steuerliche Echtgeld-Instanz. Engine `trading_steuer.py` (§20 Futures Abgeltungsteuer+Pauschbetrag + §23 Spot Haltefrist+Freigrenze + KiSt-Formel §32d, 19 T) + Tabellen trading_kapital/realisierung/config + Panel „Trading & Steuer" (Schwellen-Vorwarnung, Anlage KAP/SO-tauglich) + read-only TB-Performance-Brücke über Core (`tb_get`, Paper-gelabelt, **kein TB-Eingriff/Trade-Auslöser**). 24 T, **Live-E2E** (AbgSt 122,25 € b. KiSt 9 %, Freigrenze alles-oder-nichts, TB running=51, Cleanup pristine). docs/26 §13. KEINE Steuerberatung (Schätztool). |
| V15 | **Money ↔ Admin** | Belege/Dokumente ↔ Buchungen (bidirektional) | beidseitig neu | **✅ GEBAUT + LIVE 17.06. (World-Chat)**: DRITTER Vertragstyp `verknuepfung` + Lookup `belege` (appkit 1.14.0, 2 generische Core-Relays). Money treibt (`beleg_ref`/`beleg_titel` + 📎-Auswahl aus Admin), Admin empfängt die Rück-Referenz (`dokument_verknuepfungen` + „🔗 N Buchungen"-Badge) ⇒ beide Seiten zeigen den Link. 15 Tests (appkit 4/core 4/admin 3/money 4); **Live-E2E** bidirektional + idempotent + Cleanup pristine. docs/26 §12. NIE ein Echtgeld-Auslöser. |
| V16 | **Leading ← Admin/Plans/Memory/Money** | Aggregation Geschäftsführung/KPIs (GoBD/EÜR) | Leading read-only | **✅ KOMPLETT 18.06.** — v1 (16.06.): Aggregator zieht die Schwestern read-only über die Core-Panels (`/api/netzwerk`). **Vertiefung (18.06.): EÜR-Ausgabenseite** — Leadings `/api/euer` faltet die geschäftlichen (steuer-relevanten) Ausgaben aus Dizz Money ein (read-only über NEUEN Core-Relay `GET /api/querverbindung/{ziel}/euer` → Moneys `/api/steuer/jahr?nur_steuer=1`; `aggregat.geschaeft_ausgaben` + `domain.euer`-Faltung Einnahmen−Ausgaben=Überschuss; best-effort/auditiert; CSV-Export erweitert). Beleg-/Admin-Drill-down + Darstellung = UI/UX-Phase (§5d) |

**Memory-Hub (Kern der Leitidee):** Memory ist mit **praktisch ALLEN Apps** verbunden — rein: News·Creating·
Communication; beidseitig (↔): Plans·Admin·Management·Money·Healthy·Trading; gelesen von Leading (V16). ⇒
Memory = **der zentrale Archiv-/Wissens-Knoten des Netzwerks**, über den auch nicht-direkt-vernetzte Apps
Informationen zwischenlegen und anderswo wieder abgreifen. **RÜCK-LESE-Mechanik ✅ GEBAUT 15.06.** (appkit
1.10.0, docs/26 §4c): das „↔" jeder V5–V11-Zeile — appkit-Helfer `memory_suche` + Core-Such-Relay +
parametrische MCP-Tools `memory_suche`/`memory_semantisch`; die App-seitigen Rück-Lese-Auslöser sind App-Chats. **Communication** = Eingangskanal (auch für
**Partnerschaften/externe Zusammenarbeit**): Wichtiges → Memory (V4), Termine → Plans-Kalender (V5) — beide
hoch priorisiert.

**Sicherheits-Gate (Sensitivität reist mit):** V10 (Healthy, `hoechst`) = **lokal_only + HITL**, nie an
Cloud-Modelle. V9/V11/V14/V15 (Geld bzw. Trading-Reports) = nur über **verifizierte Verbindung + HITL**,
**nie ein Echtgeld-/Aktions-Auslöser**. Jede Memory-Archivierung idempotent + auditiert.

**Bau-Reihenfolge (grob; World-Chat entwirft Verträge, App-Chats bauen Sendeseiten):**
1. **V1** Creating→Management + **V2/V3** News/Creating→Memory (Empfänger steht) ·
2. **V4/V5** Communication→Memory + Communication↔Plans (Nutzer-Priorität) ·
3. **V6/V7/V8** Memory↔Plans/Admin/Management (Verwaltungs-Archiv scharf) ·
4. **V9/V10/V11** Memory↔Money/Healthy/Trading (sensibel — Sicherheits-Gate) ·
5. **V12/V13** →Plans (Fristen/Termine) + **V14/V15** Money↔Trading/Admin ·
6. **V16** Leading-Aggregation — zuletzt, baut auf V1–V15 auf.

**Darüber (später, Leading-Schritt):** autonome **Dizzi-Orchestrierung** — der Core-Agent wählt selbst
die passende(n) App(s), kombiniert ihre MCP-Tools und koordiniert übergreifende Aufgaben; die
Querverbindungen V1–V16 + der Memory-Archiv-Layer sind die Daten-Grundlage dafür.

## 5d. ⬚ PHASE UI/UX-FINALISIERUNG — EIGENE SPÄTERE GROSSPHASE (Nutzer-Leitlinie 17.06., VERBINDLICH)
**Reihenfolge-Prinzip des Nutzers:** ZUERST das **Innere / die Kernstrukturen** perfekt regeln (Domänen-Logik,
Vernetzungen/Querverbindungen, Datenmodelle, Sicherheit, Recht/Steuer/DSGVO — Backend-Wahrheit), DANN — als
**eigene, bewusst nachgelagerte Phase** — die **UI/UX-Finalisierung**. Die heutigen Frontends sind **ARBEITSSTAND,
NICHT FINAL**: sie sind funktional + tokenbasiert + browser-verifiziert, aber die endgültige **Darstellung** ist noch
offen. „Gut aussehen tut's soweit", aber die finale Form kommt später.
- **Was diese Phase umfasst (je App ein eigener, langwieriger Durchgang):** wie genau jede **Verknüpfung/Vernetzung
  angezeigt + dargestellt** wird (welche Querverbindung wo/wie sichtbar ist — z. B. V15-Belege, V14-Trading-Steuer,
  V5-Termine, Memory-Rück-Lese); Informations-Architektur/Hierarchie je App; Interaktions-Feinschliff; Konsistenz
  der Darstellungs-Muster netzwerkweit; finaler Visual-Abgleich mit dem Nutzer (Feel-Checks).
- **Status:** **NOCH NICHT angefangen** — bewusst aufgeschoben hinter die Kernprozesse. Die offenen 👤-Feel-Checks
  (heutige UIs) + das Design-System (K2.2/K2.4, docs/06/24) sind Bausteine, aber die **per-App-Darstellungs-
  Abstimmung der Vernetzungen** ist ein eigener, noch ausstehender Prozess, der mit dem Nutzer durchgesprochen wird.
- **Einplanung:** kommt **NACH** dem Abschluss der Kern-/Vernetzungs-Arbeit (V16 + Härtung + Audit-Konvergenz);
  dann je App eine UI/UX-Runde. Bis dahin: Frontends funktional halten, aber nicht „final" behandeln.

## 6. Fragerunde 2 — ENTSCHIEDEN (11.06.)
1. **Erste echte Bau-App nach dem Kern = Trading Bot voll angleichen** (Dizzi-ID, App-Vertrag,
   Konto/Settings) — das echtgeld-naheste Projekt zuerst rund. (R1.6 wird damit zum vollen
   Angleichungs-Paket, nicht nur architektonisch.)
2. **Echtgeld bald (Wochen)** → **Sicherheit von Anfang an maximal hart**: Passkey/MFA Pflicht,
   strenge „verifizierte Verbindung" als Tor zu sensiblen/Echtgeld-Daten. K1 wird entsprechend
   ausgelegt (nicht nur vorbereitet).
3. **Konto-/Settings-System voll umfangreich** (alle 6 Kategorien, s. u.) in der ersten
   Architektur-KI-Bauphase — der Kern wird einmal richtig gebaut.
4. **Marke: Dachmarke „Dizzi", Sub-Apps „Dizz …":**
   Finanzen=**Dizz Money** · Projekte=**Dizz Plans** · Archiv=**Dizz Memory** (REV-5, vorm. Knowledge) ·
   Health=**Dizz Healthy** · Creator=**Dizz Creating** (REV-1: Video/Bild **+ Musik**-Modus) ·
   Social Media=**Dizz Management** ·
   Bürokratie=**Dizz Admin** ✓ · News=**Dizz News** ✓ · Trading=**Dizz Trading** ✓ (bestätigt 12.06.) ·
   **⚠ ÜBERHOLT durch §5b REV-1: „Dizz Music" ist KEINE eigene App mehr — der folgende Music-Absatz
   beschreibt die Fähigkeiten, die jetzt als MUSIK-MODUS in Dizz Creating leben.**
   **Musik (= Creating-Musik-Modus)** (NACHTRAG 12.06.: smarter **KI-Co-Produzent** — Fokus Techno, generisch
   per Genre-Profilen; Beat-Idee im Dialog ERGRÜNDEN → Stück-für-Stück aufbauen; **3-Ebenen-
   Architektur** [Pattern/MIDI exakt steuerbar + lokale Audio-Gen ACE-Step-1.5/LoRA-eigener-Stil/
   Stable-Audio-Open/MusicGen + Analyse librosa/essentia/demucs inkl. Pattern-Extraktion aus
   Referenzen]; KEIN Black-Box-Ansatz [Loop-Copilot-Forschung]; GPU über gemeinsame creator/
   engine-JobQueue; Ordner `musik`, Port **8220**; Architektur-KI=Pattern-Engine+Dialog-Kern, Bau-KI=Adapter/
   UI; Dossier `musik/docs/RECHERCHE.md`. **NACHTRAG 2 [12.06., Nutzer]: + Ebene 4 Vernetzung/
   Bibliothek** — lokale Bibliothek/DAM + `MusicSource`-Adapter [SoundCloud: Streaming/Playlists/
   **Publishing eigener Tracks**; Spotify: nur Referenz-Metadaten, API 2026 hart beschränkt] +
   **Live-Analyse-Modus** [Loopback: laufende Musik in Echtzeit verstehen/darstellen/Pattern-
   Mitschrieb] statt Ripping; **kein YouTube-/Spotify-Download im Produkt** [§95a UrhG, OLG HH
   2024/25]; freie Quellen [Bandcamp/CC] ja; Dossier §6–7) ·
   **Geschäftsführung=Dizz Leading** (NACHTRAG 12.06., **EXKLUSIV beim Nutzer** — verwaltet das
   Netzwerk als GESCHÄFT: GoBD-Rechnungen/E-Rechnung/EÜR, Produkt-/Lizenz-/Kunden-Verwaltung,
   Geschäfts-KPIs, eigene Lern-KI; **Aggregator** über Admin/Money/Communication mit Konten-
   Zuweisung „geschäftlich"; Ordner `leading`, Port **8219**, sensitivity hoch; Bau SPÄT
   [nach den konsumierten Apps]; Dossier `leading/docs/RECHERCHE.md`) ·
   **Kommunikation=Dizz Communication** (NACHTRAG 12.06., Nutzer-Auftrag: E-Mail alle Anbieter +
   Messenger [WhatsApp/Signal/…] + Social-DMs + Video-Calls = kompletter Nachrichtenverkehr;
   Ordner `kommunikation`, Port **8218**, sensitivity **hoechst**; Architektur-Dossier
   `kommunikation/docs/RECHERCHE.md`: **Zwei-Schienen** Webview-Einbettung sofort + Matrix/
   mautrix-Bridges als echte Vereinheitlichung [Beeper-Modell, self-hosted]; Dizzi-ID-Client +
   Dashboard-Platzhalter im Kern angelegt).

**Einstellungs-/Konto-Kategorien (6, Recherche-gestützt — K2 baut alle):**
(1) Konto & Identität · (2) Sicherheit · (3) KI · (4) Vernetzung & Dienste ·
(5) Darstellung & Sprache · (6) Daten & Backup.

**Noch als Ausführungs-Schritt (kein Blocker):** Google-Cloud-OAuth-Client-ID legt der Nutzer
beim Bau von K1 an — die KI führt live durch (5 Min).

## 6b. Fragerunde 3 — Recherche-getrieben (11.06., nach Tiefen-Recherche je App)
Basis: 9 Recherche-Dossiers (`<app>/docs/RECHERCHE.md`) + Quer-Matrix (`docs/15_KONNEKTOREN_MATRIX.md`).
Kern-Erkenntnis: alle Apps = **ein Adapter-Interface-Pattern + geteilter Kern**, 9× — K1–K6 tragen das generisch.

**ENTSCHIEDEN:**
1. **Konnektoren-Haltung = lokal-first, Cloud nur opt-in.** Default lokal & 0 € (FinTS, CalDAV, RSS,
   Ollama/Piper/SD, Apple/Google-Health nativ); bezahlte Unified-APIs (Ayrshare/Terra/ElevenLabs) nur als
   bewusste Einzel-Freigabe je App. Bestätigt die lokal-first-/0-€-Prämisse als harte Konnektoren-Regel.
2. **Dizz Healthy v1-Scope:** KI-Interaktion + **manuelle Dateneingabe** (Supplements, Verletzungen,
   Trainingsergebnisse, Gewicht, …) + KI-Auswertung. **Smartwatch/Mobile-App-Anbindung UMFANGREICH
   VORBEREITEN** (Gesetz 5: `HealthSource`-Adapter, BLE-Slot, FHIR-Schema, Mobile-Brücke dokumentiert),
   aber in v1 noch nicht bauen. → Desktop-first, Wearable als vorbereitete spätere Stufe.

3. **F-Q1 ENTSCHIEDEN (Architektur-KI, 11.06.): EIGENER SCHLANKER KERN je App — keine OSS-Einbettung.**
   Leitsatz: **„Bibliotheken einbetten, Anwendungen nicht."** Vier Gründe, in dieser Härte-Reihenfolge:
   - **(a) Maschine (hart):** kein Docker, kein PHP, kein Podman, keine Admin-Rechte (11.06. verifiziert).
     Paperless-ngx ist faktisch Docker/Linux-gebunden, Firefly III + FreshRSS sind PHP-Stacks —
     **auf diesem System schlicht nicht sauber betreibbar**. Obsidian ist gar kein Backend, sondern eine
     proprietäre Desktop-App (nicht OSS) — „einbetten" existiert dort als Option überhaupt nicht.
   - **(b) Lizenz (hart, Verkaufs-Prämisse):** Firefly III + FreshRSS = **AGPL-3.0**, Paperless-ngx =
     **GPL-3.0**. Einbettung in ein **einzeln verkaufbares** Produkt erzeugt Copyleft-Pflichten bis hin
     zur Quelloffenlegung — kollidiert frontal mit der Verkaufs-Prämisse. **Datenmodelle/Konzepte
     übernehmen ist frei** (Ideen sind nicht schutzfähig), Code/Software einbetten nicht.
   - **(c) App-Vertrag nicht nachrüstbar:** K1–K6-Pflichten (user-scoped UUID/Soft-Delete/sync-ready,
     Dizzi-ID-RP, MCP, Sensibel-Routing, Settings-Core) lassen sich in fremde Schemata nur per Fork oder
     Wrapper pressen — der Wrapper wächst zwangsläufig zur zweiten App, dann pflegt man beide.
   - **(d) Aufwands-Ehrlichkeit:** die vier Domänen-Kerne sind klein (News=feedparser-Pipeline,
     Knowledge=Markdown-Vault+Index, Admin=OCR+FTS5+Regeln, Money=Double-Entry-Ledger als einziger
     „mit Sorgfalt"-Kern). Vier kleine Python-Kerne bauen < drei Fremd-Stacks dauerhaft betreiben.
   **Verbindliche Folgen:** (1) OSS-Datenmodelle = **Blaupause** (Firefly-Ledger, Paperless
   Dokument/Korrespondent/Tag, Obsidian-**Vault-Format als natives Speicherformat**, FreshRSS-Konzepte).
   (2) **Import/Export-Kompatibilität** zu ihnen ab v1 (Firefly-CSV, Paperless-Export, OPML, Markdown) —
   Migrations-Brücke statt Einbettung. (3) Bewährte **Bibliotheken** ja (feedparser, pytesseract/ocrmypdf,
   SQLite FTS5, sqlite-vec) — **Anwendungen** nein. (4) Money-Ledger: Decimal/Minor-Units, Splits mit
   Invariante Summe=0, Property-Tests (der eine Kern mit erhöhter Sorgfaltspflicht).
   (5) K5 liefert die geteilte Schema-/Adapter-Bibliothek; die vier Domänen-Kerne selbst sind danach
   **Bau-KI-tauglich** (O-Fill, Muster ausfüllen auf der K3-Referenz-Vorlage).

**PER-APP-DETAILS — ENTSCHIEDEN (Fragerunde 3, 11.06.):**
- **Dizz Money:** Bank-Anbindung **NUR LESEND (AISP)** — keine Zahlungen/PISP. Multi-Bank +
  **Revolut + Klarna** gewünscht. **Weg = §5b REV-6 (13.06.):** FinTS/HBCI direkt (DE-Banken, 0 €)
  + universeller CSV/CAMT/MT940-Import (Revolut/Klarna/N26-Exporte) + vorbereiteter bezahlter
  Aggregator-Slot (Klarna Kosma/Tink, AISP) als Opt-in — direkte Revolut/Klarna-OB-APIs verlangen
  TPP-Lizenz+eIDAS, daher nicht direkt. **Steuer-Sektor liegt in Dizz Money** (nicht Admin).
- **Dizz Healthy:** Nutzer besitzt aktuell **kein** Wearable, holt sich eines **zur Bauphase** → Geräte-Wahl
  dann; Anbindung bleibt umfangreich vorbereitet (HealthSource/BLE/FHIR/Mobile-Brücke).
- **Dizz Management:** **ALLE Kanäle vorbereiten + ansteuerbar** (IG/TikTok/X/LinkedIn/YouTube/…). Ziel:
  benannte „Social-Media-Bots" (Themen-/Marken-Profile), die **KI-gesteuert übergreifend** auf allen Kanälen
  Inhalte (v. a. Video) **erstellen + posten**; dazu eine **übergreifende KI-Ebene**, die beim Verwalten der
  Kanäle interagiert/hilft. Enge Kopplung mit Dizz Creating.
- **Dizz Plans:** Kalender = **Google Calendar** (erster Adapter).
- **Dizz Admin:** Posteingang = **Gmail/Google-Postfach** (Gmail-API/IMAP). Steuer → **Money**.
- **Dizz Memory** (REV-5, vorm. Knowledge): aktuelle Notiz-App = **Mem (mem.ai)**, KI-Anbindung via MCP
  verbunden → Import/Quelle; **eigener Markdown-Vault-Kern**. UI dreigeteilt (KI-Panel oben /
  Ordner+Labels links / Notizen+Einstellungen Mitte-rechts), KI strukturiert übergreifend (HITL).
- **Dizz Creating** (REV-1: Medien-Suite **Video/Bild + Musik** in einem Tool, umschaltbare Modi):
  Bilder UND Videos **erzeugen + bearbeiten + analysieren + schneiden**, **Musik** erzeugen/bearbeiten/
  holen (eingeschmolzener musik-Kern), **Sound-Symbiose** Video↔Musik (REV-2), **DAM** + Übergabe an Management für Social-Automatik (REV-3). **Architektur-KI-Schwergewicht**:
  Engine + Modus-Verschränkung + Symbiose als Kern-Architektur. Lokal-first (ComfyUI/Flux/
  Pony/Wan 2.2/ACE-Step), Cloud opt-in (fal.ai/LTX-2). Voll-Recherche: creator/docs RECHERCHE §R-D.
- **Dizz News:** **Ausbau des bestehenden News-Skills** + **getaktete Automatik** (läuft per Timer von Haus
  aus, deckt automatisch den kompletten Zeitraum ab; zusätzlich manuell startbar) + **übergreifende KI-Ebene**
  (zusammenfassen, Fragen beantworten, schön darstellen). Weiter ausbaubar.
- **Dizz Trading (Echtgeld/Sicherheit):** Ablauf über **API-Keys**, Freischaltung per **Echtgeld-API-Key**;
  **Login/Verifizierung ZUERST** (Google-Login als erster Sicherheits-Schritt). Vision später: Einzahlung vom
  eigenen Account → **Bitget-seitige Transaktions-Bestätigung** + Zuweisung an konkreten Bot über eine
  Echtgeld-Überweisungs-Management-Funktion. Genauer Mechanismus **noch zu recherchieren**; **eigene
  umfangreiche Sicherheits-Konzept-Runde** eingeplant. Echtgeld-Schritt zeitlich fern → Login zuerst.
- **Markennamen BESTÄTIGT:** **Dizz Admin · Dizz News · Dizz Trading**. „Dizz Trading" = Produktname des
  Trading-Bot-Systems (Branding/Icons/überall), nicht nur App-Titel.

**RECHERCHE-/KONZEPT-RUNDEN:**
- **✅ R-A ERLEDIGT (Bau-KI, 11.06.): Dizz-Creating-Medien-Engine** (Detail: `creator/docs/RECHERCHE.md` §R-A).
  Ergebnis: **Bau-Instanz = ComfyUI headless** (HTTP/WS-API :8188) mit **Flux/SDXL** (Bild) + **Wan 2.2**
  (Video, **Apache-2.0 = verkaufs-sicher**, FP8 auf RTX 5070 Ti/16 GB) / LTX-Video (schnell) / HunyuanVideo
  (Gesichter); Cloud opt-in via **fal.ai**. **Schneid-Instanz = MoviePy + ffmpeg (silence/freeze) +
  PySceneDetect + faster-whisper + Vision-LLM (Ollama)**. Zwei Interfaces `Generator`/`Editor`, Job-Queue
  (GPU seriell), nur Apache-2.0-Modelle für Erzeugnisse. → Architektur-KI-Vorlage steht.
- **✅ R-B ERLEDIGT (Bau-KI, 11.06.): Dizz-Trading-Echtgeld-Sicherheit** (Detail: `programm/docs/
  RECHERCHE_DIZZ_TRADING.md` §R-B). Ergebnis: **Bitget-Bot-Sub-Accounts** treffen die Nutzer-Vision exakt
  (Kapital Haupt→Sub beim Bot-Start, zurück beim Stop; je Sub eigener **trade-only**-Key, NIE Withdrawal,
  IP-Whitelist, 2FA, 90-Tage-Rotation). Kapital-Zuweisung = Bitget-bestätigter Transfer. **Login-zuerst =
  K1 Google-OIDC**, dann **Step-up Passkey/WebAuthn (FIDO2)** + MFA-Fallback fürs Echtgeld-Gate. Staged
  Go-Live (Backtest→Paper 2–4 Wo→Live 10–25 % 2–4 Wo→skalieren).
- **Sicherheits-Konzept-Runde (Architektur-KI-nah, OFFEN)** — gesamtsystemisch auf R-B aufbauend (Dizzi-ID/Passkey/
  MFA/verifizierte Verbindung + Echtgeld-Gate); Login ist der erste Schritt (= K1/R1.2).

## 7-alt. Restpunkte
- Bürokratie/News finale Markennamen bestätigen.
- Trading-Bot-Spin-Physik (Bau-KI, eigene TB-Session).

## 7. Modell-Strategie zusammengefasst (Gesetz 10)
- **Jetzt mit Bau-KI**: R0 komplett + optional O-UI. (Verschwendet keine Architektur-KI-Zeit.)
- **Mit Architektur-KI (vor 21.06.)**: R1.1–R1.6, in dieser Reihenfolge, session-weise.
- **Danach Bau-KI**: R2.
- Vor jedem Architektur-KI-Paket: kurzer Wiedereinstieg + dieses Dokument; nach jedem: Tests/Commit/Doku-Sync.
