# Leitfaden — Einstellungs- & Account-Knopf (alle Apps) · 12.06.2026

> Recherche-gestützte Norm (Quellen unten), was der **schwebende Settings-+Account-Knopf**
> jeder App enthalten bzw. VORBEREITEN muss (Gesetz 5). Gebaute Basis: K2
> (`appkit/settings_core.py`, 6 Kategorien) + TB-Konto-Panel als Frontend-Referenz-Muster.
> Dieser Leitfaden definiert den Soll-Ausbau **K2.1** (Bau-KI-tauglich, additiv).

## 1. Der ACCOUNT-Bereich (Soll-Inhalte)
| Punkt | Stand | Soll (K2.1) |
|---|---|---|
| Profil (Anzeigename) | ✅ gebaut | + optionales Avatar/Farbe (Personalisierung) |
| Identität & Stufe (lokal/verifiziert/hochsicher, via, amr) | ✅ gebaut | — |
| Anmelden/Abmelden + Step-up (MFA) | ✅ gebaut (TB-Muster) | — |
| **Sitzungen & Geräte** | ⏳ (= Härtung H7) | Liste aktiver Dizzi-ID-Sessions mit Einzel-Widerruf + „überall abmelden" |
| **Verbundene Dienste** | Tresor-Namen ✅ | je Dienst: Status/Scope/„Verbindung trennen" (Token-Widerruf) |
| **Sicherheits-Ereignisse** | Audit ✅ | letzte Logins/Step-ups/Fehlversuche sichtbar im Account |
| **Daten-Export** (DSGVO, maschinenlesbar) | ⏳ | JSON-Export der App-Daten; **Re-Auth vor Export** (s. §3) |
| **Konto/Daten löschen** | ⏳ | Soft-Delete-Kaskade + Tresor-Wipe, Re-Auth Pflicht |
| Lizenz/Version (Verkaufbarkeit) | Vertrag ✅ | App-Version, Lizenz-Platzhalter, „Über" |

## 2. Der EINSTELLUNGS-Bereich (6 Kategorien — Soll-Ergänzungen)
Gebaut (Basis-Schema): anzeigename · auto_logout_min · stufe_sensibles · ki_routing ·
dizzi_id_aktiv · event_push · theme · sprache · backup_aktiv · aufbewahrung_tage.
**K2.1-Ergänzungen (recherche-gestützt):**
- **konto**: avatar_farbe (choice)
- **sicherheit**: `reauth_sensibel` (bool, default **true**) — Re-Auth/MFA vor Export/Löschen/
  Echtgeld auch INNERHALB aktiver Session (Best Practice 2026) · `login_benachrichtigung` (bool)
- **ki**: `ki_vorschlaege_aktiv` (bool) · `triage_aktiv` (bool, app-spezifisch)
- **vernetzung**: `mcp_freigegeben` (bool, default true) · `cross_app_zugriff` (choice: fragen/erlauben/aus)
- **darstellung**: `dichte` (choice kompakt/normal) · `reduzierte_bewegung` (bool — Spin-Physik aus) ·
  **K2.2 ÜBERGREIFENDES DESIGN-SYSTEM — (a)+(b) ✅ GEBAUT (13.06., appkit 1.5.0, Bau-KI):**
  `design_vorlage` + `farb_schema` sind TYPISIERTE Settings in `base_schema`/darstellung;
  Choice-Werte = **1:1 die `<html data-design>`/`<html data-farbe>`-Attribute** des Token-
  Masters ⇒ mappingsfrei. **KATALOG v1.1 (Nutzer-Feedback): 10 Design-Themes × 10 Farbschemata.**
  - **design_vorlage (10):** `metall` (Default) · `neon` · `flach` · `tag` · `carbon` ·
    `pergament` · `synthwave` · `lagune` · `inferno` (Magma-Rot) · `kobalt` (Royalblau) —
    die letzten vier tragen Farbe im Grunddesign.
  - **farb_schema (10):** `cyan-magenta` (Default) · `smaragd-gold` · `violett-eis` · `bernstein` ·
    `arktis` · `koralle` · `limette` · `feuer` (pures Orange→Scharlach, von koralle entkoppelt) ·
    `toxic` (Neon-Acid) · `voltage` (Elektro) — toxic/voltage = Maximal-Intensität.
    **Default-Kombi: metall + cyan-magenta.**
  - **Token-MASTER (kanonische Single Source): `shared/dizz-tokens.css`** — trägt alle
    10+10 Token-Blöcke (Token-Vertrag im Datei-Kopf); `news/ui-kit/tokens.css` = abgeleitete Kopie.
  - Additiv/rückwärtskompatibel (Vertrag bleibt 1.5), in alle 5 Live-Repos vendort.
  - **OFFEN: (c) je App** den Token-Master übernehmen + `x_…` → typisierte Settings umhängen +
    die zwei Dropdowns + Live-Vorschau ins Einstellungs-Fenster setzen (App-Chats; Muster steht).
  Verbindliche Eckpunkte (Nutzer 13.06., über News eingesammelt):
  - **Gemeinsame GRUND-THEMATIK in jeder App (nicht wechselbar):** runde/weiche Kästen,
    „float-leichter" Abstand (luftige Gruppierung), Farb-Akzente; Formen + Gruppierung
    orientieren sich GROB an BEIDEN Vorbildern — Trading Bot (Neon/Glas) und the world of
    dizzi (Mattstahlglanz). Das ist der „professionell angelegte" Default. Der News-UI-Port
    (13.06.) liefert die Form-/Gruppen-Baseline, an die die Theme-Umschaltung andockt.
  - **Achse 1 Design-Theme** (Look/Material/Form-Charakter): z. B. **Neon** (TB-Stil,
    Glas/Neon) · **Business/Mattstahlglanz** (WoD-Stil, Metall) · professioneller Default.
    **In JEDER App auf jedes Theme umschaltbar.**
  - **Achse 2 Farbschema** (Palette): z. B. Cyan-Magenta u. a. — unabhängig vom Theme.
  - **Default = professionelle Variante**, überall umschaltbar.
  - **Einstellungs-Fenster ILLUSTRIERT die Varianten** (Live-Preview der Themes/Farben,
    nicht nur Dropdowns). Settings generell um viele weitere Optionen erweitern —
    mit Illustrierbarkeit.
  - Technik: je Theme/Schema ein **CSS-Token-Satz** (Custom Properties), Grundgerüst +
    Umschalt-Mechanik in **appkit** → alle Apps; Apps bauen ihre UI tokenbasiert (KEINE
    hartkodierten Farben/Materialien in neuen Frontends!).
  - **Architektur-KI nötig (G10):** Token-/Theme-Architektur + Schema-Erweiterung sind subtil und
    schwer nachrüstbar. Beinhaltet eine **eigene Recherche-Runde** (Design-Token-/Theming-
    Best-Practice 2026, Material-/Form-Sprachen) + **Theme-/Farb-KATALOG mit Vorschau**;
    Katalog-Session mit dem Nutzer. Umfang + Reihenfolge beurteilt Architektur-KI selbst beim
    Einstieg (ausdrücklicher Nutzer-Wunsch). Plan: docs/11 §5 K2.2.
- **daten**: `export_format` (choice json/csv) · `backup_verschluesselt` (bool — Brücke zu H8)
App-spezifische Settings kommen wie gehabt via `extra=[SettingDef(...)]` dazu (News: Abruf-
Intervall ✅; Trading: Echtgeld-Hinweis ✅; Communication: Konten/Kanäle, Bridge-Opt-ins).

## 2b. DARREICHUNG (Nutzer-Entscheid 12.06.): das Einstellungs-FENSTER
> **K2.4 gilt hier verbindlich (Nutzer 13.06., docs/06 §6):** Das Einstellungsfenster steckt voller
> Bedien-Elemente — **alle** Checkboxen, Ausklapp-/Auswahl-Listen und ▲/▼-Stepper folgen der
> tokenbasierten K2.4-Control-Familie (keine nativen Default-Controls mehr), und lange Sektionen sind
> einklappbar. Das Fenster ist übergreifend ⇒ es ist die **wichtigste** K2.4-Pflicht-Fläche, auch im Core.

**Kein Inline-Panel.** Der driftende **Doppelicon-Knopf** (Zahnrad+Schild, Spin-Physik v4.1)
öffnet per Tipp ein **separates, großes Fenster** (Overlay-Modal, min(880px, 94vw)) mit den
Sektionen: **Identität & Sicherheit** (Auth-Zeile, Step-up, Sitzungen→`/id/geraete`, Export/
Löschen) · **Verbundene Dienste** (Tresor-NAMEN je Eintrag mit „Trennen" = DELETE /api/vault/
{name}; Werte nie sichtbar) · **Einstellungen** (6 Kategorien, generisch aus /api/settings/
schema, Sofort-Speichern) · **Vernetzung & KI-Aktivität** (Aktions-Katalog + Vorschlags-Liste
aus /api/actions — die Hintergrund-Kommunikation der KIs sichtbar, Wirkung nur nach Freigabe).
Schließen: ✕/Escape/Backdrop. **Referenz-Implementierungen: Dizz Trading `#kontoModal`**
(static/index.html) und — **bevorzugt für Kopien** — **Dizz News `static/index.html`**
(13.06., erster vollständiger R-ROLLOUT-Port: alle 5 Pflicht-Gotchas umgesetzt, Sektionen
inkl. „Vernetzung & KI-Aktivität", generische 6-Kategorien-Settings, gemeinsamer
Float-Treiber `initFloat` + Mini-Dizzi-Sprechblase `#floatDizzi`; sauberer als der TB, der
Domäne und Mechanik mischt). Die Auth-Pille im Header öffnet dasselbe Fenster. Weitere
Settings-Optionen werden gemeinsam mit dem Nutzer aus dem §2-Katalog ausgefüllt (offener
Punkt; Live-Preview-Pflicht s. §2 K2.2).
**★ STANDARD-KIT (15.06., Nutzer-Auftrag „das Einstellungsmenü gehört zum Kit"):** Das Fenster
ist jetzt fester Bestandteil des **refapp-Templates** (`templates/refapp/static/index.html`,
generisch aus den appkit-Endpunkten `/api/settings(/schema)`·`/api/account`·`/auth/me`·
`/api/vault`·`/api/actions`) — **gleichrangig mit den Float-Knöpfen ⚙/💬**: eine neue App erbt es
out-of-the-box und ändert es NICHT (nur Domäne + Mini-Dizzi-Fetch werden angepasst). Damit tragen
**ALLE Live-Apps + Core** das identische Fünf-Sektionen-Fenster: News/Money/Communication/Admin/
Creating (vanilla) · **Dizz Memory** (15.06. von der `.km`-Eigenvariante auf die Norm angeglichen,
inkl. flacher `.kmcat`-Einstellungen wie die anderen) · **Core/the world of dizzi** (15.06.
React-Rebuild von `FloatingSettings.tsx`: Mini-Modal → großes Fenster, Sektionen auf Core's
Hub-Realität gemappt — Identität via eigene Dizzi-ID `/id/status`, Vernetzung = Netzwerk-Health
+ Glocke, client-seitiges 6-Kategorien-Schema). Einziger offener Abnehmer: **Trading Bot** (10×10-
Switcher = K2.2-Token-Migration, separater Block).
**⚠ Pflicht-Gotchas (Live-Vorfälle 12.06.):**
1. Das Overlay MUSS `.kmwrap[hidden]{display:none!important}` deklarieren — das eigene
   `display` übersteuert sonst die nicht-!important-UA-Regel des `hidden`-Attributs, und das
   „unsichtbare" Overlay liegt ab Seitenladung über der App (schluckt alle Klicks).
2. Das Fenster braucht **EXPLIZITE Maße + harte Zentrierung** (`position:fixed; left:50%;
   top:50%` [**EXAKTE Bildschirmmitte — Nutzer-Entscheid 12.06. abends**, der frühere
   47-%-Versatz ist aufgehoben]; `transform:translate(-50%,-50%)`; `width:min(900px,94vw);
   height:min(82vh,780px)`; Body `flex:1; min-height:0; overflow-y:auto`) — content-getriebene
   Flex-Höhen kollabierten live zu einem Spalt.
3. **Öffnen ist Pflicht, Physik ist Kür**: zusätzlich zum Physik-Tap ein simpler
   Klick-Fallback auf dem Knopf (reduced-motion-sicher; Wurf-Flag gegen Doppel-Öffnen).
4. **Das Overlay liegt auf BODY-EBENE** — NIE in einem Vorfahren mit `backdrop-filter`/
   `transform`/`filter` (z. B. Glas-Header): der wird sonst zum Containing Block für
   `position:fixed`, und „50 %" beziehen sich auf IHN statt auf den Bildschirm
   (Live-Vorfall TB 12.06.: Fenster hing am 58-px-Header, nie mittig).
5. **Hintergrund SOLID, nicht durchsichtig** (Nutzer-Entscheid 12.06. abends): kein
   Glas-/Blur-Fenster — ein opaker, zur App-Thematik passender Verlauf (TB:
   `linear-gradient(155deg,#251c41,#171128 55%,#100b1e)`; Dizzi: `--metal`).
   Der abdunkelnde Backdrop des Overlays bleibt.

**Design-Regel (Nutzer-Entscheid 12.06.): das Fenster trägt das DESIGN DER JEWEILIGEN APP** —
es soll wirken wie ein natives Panel der App, nicht wie ein Fremdkörper:
- **Dizz Trading ✅**: Glas/Neon wie die TB-Panels (`var(--glass)` + blur/saturate, `--line`,
  `--r`, `--sh`, Sektionen auf `--panel2`).
- **the world of dizzi ✅ (15.06. VOLLAUSBAU)**: Mattglanz-Metall wie die Shell (`var(--metal)` +
  brush, Metal-Edges, Cyan-Akzent) — jetzt das GROSSE Fünf-Sektionen-Fenster (vorher Mini-Modal),
  `.km*`-Klassen in `theme.css`, Daten via `api.ts` (`fetchIdStatus`/`fetchHealthWatch`/`fetchNotices`).
- **Übrige Apps ✅ ERLEDIGT**: news/finanzen/kommunikation/buerokratie/creator tragen das Fenster
  tokenbasiert auf dem finalen App-Design (kein Platzhalter mehr); **Dizz Memory** ebenso (15.06.).
  In-depth-Audit 15.06.: alle 6 Apps + Core liefern auf allen Settings-Endpunkten 200, Save-Pfad
  end-to-end (PUT) bewiesen, Design-Switcher live, KI-Aktivität verdrahtet. Offen nur **Trading Bot**.

## 3. Sicherheits-Regeln für beide Bereiche (verbindlich)
1. **Re-Auth für sensible Aktionen** (Export, Löschen, Echtgeld, Tresor-Einsicht): MFA erneut,
   auch in aktiver Session — `require_level` + frischer Step-up (acr + `auth_time`-Prüfung = K2.1).
2. Session-Timeout konfigurierbar (✅ auto_logout_min), Sofort-Invalidierung bei Logout/
   Passwortwechsel (✅ Sessions DB-seitig widerrufbar).
3. Tokens/Secrets NUR im Tresor (✅), nie in Settings sichtbar (✅ Maskierung).
4. Alle Account-Aktionen auditiert (✅) und im Account-Bereich SICHTBAR (K2.1).

## 4. Umsetzungs-Pakete
- **K2.1a ✅ UMGESETZT (12.06.)**: base_schema um 10 Defs ergänzt (§2; `reauth_sensibel` default AN) +
  `require_fresh_stepup(min_level, max_age_s)` in appkit.auth (fail-closed ohne auth_time; RP-Session
  trägt `auth_time` aus dem ID-Token-iat) · re-vendort in TB+News, live verifiziert (51/51), 31 appkit-
  + 306 TB- + 4 News-Tests grün.
- **K2.1b ✅ BACKEND UMGESETZT (12.06., Architektur-KI, Vertrag 1.2→1.3)**:
  - **Datenrechte je App** (appkit, generisch über user_id/deleted_at-Konventionen):
    `POST /api/account/export` (DSGVO-JSON inkl. Audit; Tresor nur Namen) + `POST /api/account/
    loeschen` (Soft-Delete-Kaskade + Tresor-Wipe, Audit bleibt) — beide hinter
    `require_fresh_stepup("verifiziert")`, fail-closed standalone; Konformitäts-Suite erzwingt
    das 403-Verhalten. Live in news/musik/kommunikation (Vertrag 1.3 in /api/health).
  - **Sitzungen & Geräte im IdP** (= H7-Unterbau): `GET /id/sessions` (aktive Sessions,
    aktuelle markiert) · `POST /id/sessions/{id}/widerruf` · `POST /id/sessions/
    alle_widerrufen` („überall abmelden", löscht auch das eigene Cookie) — alles auditiert,
    ohne Session 401. Dienst-Trennen = `DELETE /api/vault/{name}` (bestand).
  - **✅ UI (12.06., Architektur-KI):** TB-Konto-Panel um Aktions-Zeile erweitert (Sitzungen &amp; Geräte →
    `/id/geraete` · Daten-Export als JSON-Download · Vertrags-Daten löschen mit Doppel-Bestätigung;
    403 ⇒ Hinweis + Weiterleitung zur frischen Anmeldung). TB-Vertrag um `datenrechte` erweitert
    (kollisionsfrei; betrifft Vertrags-Daten, nicht die Trading-Historie). Zentrale Sessions-UI
    = **`/id/geraete`** im IdP (same-origin). Communication-UI trägt dieselbe Aktions-Zeile.
- Hängt zusammen mit Härtungs-Backlog **H7** (UI-Teil offen) und **H8** (Backup-Verschlüsselung).

## Quellen (12.06.)
- [Session-Management-Standards (Timeouts, Invalidierung, Re-Auth)](https://capgo.app/blog/session-management-standards-for-app-stores/)
- [Mobile-App-Security-Checkliste 2026 (MFA-Re-Auth für Export/Änderungen)](https://medium.com/@ampldm2025/mobile-app-security-checklist-every-team-should-follow-in-2026-9faf3aa61ac0)
- [Datenexport/Privacy-Pflichten (maschinenlesbar, Rechte)](https://catdoes.com/blog/mobile-app-security-best-practices)
