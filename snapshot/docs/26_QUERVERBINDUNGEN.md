# 26 · QUERVERBINDUNGEN — Übergabe-Verträge zwischen den Apps (Phase 2)

> Kanonische Spec der App-zu-App-Datenflüsse. Das **Register** (welche Verbindung, was
> fließt) steht in [docs/11 §5c](11_GESAMTPLAN.md) (V1–V16). **Dieses** Dokument legt die
> **technische Mechanik** fest: Transport, Vertrag, Sicherheit, Helfer/Relay-API.
> Stand: **15.06.2026 — Memory-Archiv-Transport GEBAUT + live verifiziert.**
>
> **★ POST-MERGE-NACHTRAG (19.06.2026):** Plans + Admin + Leading sind zu **Dizz Admin** (id `admin`, :8222)
> verschmolzen (docs/_archiv/28). Verbindungen, die unten noch auf `plans`/`leading` lauten, gelten jetzt für `admin`:
> die **internen** Kanten (V6 Memory↔Plans-Projektwissen, V7 Memory↔Admin, V12 Admin→Plans-Frist) werden
> **In-Prozess-Aufrufe** innerhalb von Dizz Admin (kein Core-Relay mehr); **externe** Kanten laufen unter app-id
> `admin` mit erhaltenen Strömen (docs/_archiv/28 §5). Sender publizieren als `admin` (nicht `plans`/`leading`).
> **OFFEN (World-Chat):** appkit-`sende_termin`-Default `ziel="plans"`→`"admin"` (Master + vendoren) + Communications
> V5-Sender `plans→admin` — s. docs/_archiv/29 §4.

## 1. Prinzip (gilt für JEDE Verbindung)
**Übergabe-Vertrag** (docs/_archiv/23): Daten bleiben bei der **Quelle** · das **Ziel** entscheidet,
wie es sie aufnimmt · jede Übergabe ist **idempotent + auditiert**. Sensitivität reist mit
(Geld/Gesundheit ⇒ HITL + `sensibel`-Flag). **World-Chat entwirft den Vertrag, App-Chats
bauen die Sendeseite.**

## 2. Transport = ÜBER DEN CORE (Nutzer-Entscheid 15.06.)
```
   Sender-App ──POST──►  Dizzi-Core  ──POST──►  Ziel-App
   (kennt nur Core)      (Relay, kennt          (Empfangs-Slot)
                          alle App-URLs,
                          auditiert zentral)
```
- **Warum Core:** zentrale Auffindung (Apps kennen nur die Core-URL), **zentrale Audit-Sicht
  über JEDEN Querfluss** (Grundlage für Leading-Aggregation + autonome Dizzi-Orchestrierung),
  Entkopplung. Gleiches Muster wie Mini-Dizzi (`/api/ki/app/{id}`) + Event-Push (`/api/events`).
- **Auth:** **kein Token nötig.** `current_user` fällt standalone auf den Single-User `dizzi`
  (Stufe `lokal`) zurück; Vertrauensgrenze = **localhost-Bindung + appkit-Guard** (Host-Allowlist
  + Origin/CSRF). Server-zu-Server-POSTs (ohne Origin) passieren den Guard — wie Defense-Hub.
  (Verifiziert 15.06.: tokenloser localhost-Zugriff = HTTP 200.)

## 3. Der Memory-Archiv-Vertrag (V2/V3/V4 + alle „→ Memory"-Kanten)
Dizz Memory = **zentrales Archiv** des Netzwerks. Eine App archiviert ein Element; Memory legt
eine durchsuchbare Notiz an (FTS + RAG).

**Umschlag (Core-Relay ⇄ Memory-Empfänger, identisch):**
| Feld | Typ | Bedeutung |
|------|-----|-----------|
| `titel` | str | Überschrift (leer ⇒ erste Inhaltszeile) |
| `inhalt` | str | Rumpf (Markdown ok) |
| `quelle` | str | Referenz/URL beim Absender (Frontmatter) |
| `app` | str | absendende App-id (→ `import_quelle`; Default-Ordner) |
| `tags` | str[] | werden zu Memory-**Labels** |
| `ordner` | str | Ziel-Ordner-Pfad (`A/B`, angelegt falls fehlt; Default = `app`) |
| `ref` | str? | **Idempotenz-Schlüssel** (z. B. `news:artikel:42`) — sonst Inhalts-Hash |
| `sensibel` | bool | markiert sensibel ⇒ Memory-KI **nur lokal** |
| `strom` | str? | **Strom-/Inhalts-Typ** der Quelle (`wochenbericht` vs. `artikel`) — Schlüssel der Archiv-Regel (§8) |
| `explizit` | bool | `true` = Nutzer-Klick „archivieren" ⇒ **schlägt jede Regel** (§8) |

**Antwort:** `{ ok, status: "archiviert" | "vorhanden" | "uebersprungen", id }` · **idempotent** (zweites Senden
mit gleichem `ref`/Inhalt ⇒ `vorhanden`, gleiche `id`) · **auditiert** (Memory: `querverbindung_
empfangen`; Core: `querverbindung_relay`).

**Herkunftslabel (automatisch, §9.1):** Memory hängt JEDEM Querverbindungs-Archiv genau ein erkennbares
Quell-App-Label an (aus `app` abgeleitet, Label-Art `herkunft`, eigene Optik) — Sender müssen dafür nichts tun.

**Empfänger:** Memory `POST /api/querverbindung/archivieren` — **steht** (archiv, Herkunftslabel inklusive).
**Rücklesen** (die „↔"-Richtung) ✅ **GEBAUT 15.06.** (§4c): appkit-Helfer `memory_suche(q, semantisch=…)`
+ Core-Relay `GET /api/querverbindung/{ziel}/suche` + parametrische MCP-Tools `memory_suche`/`memory_semantisch`.

## 4. API — was schon gebaut ist (15.06.)
**Core-Relay** (`core/app/main.py`): `POST /api/querverbindung/{ziel}` — Umschlag im Body,
leitet an `{ziel_base}/api/querverbindung/archivieren` weiter, auditiert, 404 wenn Ziel nicht
angedockt, ehrlicher Hinweis wenn Ziel offline. Ziel = App-id (Default-Archiv = `memory`).

**appkit-Helfer** (`appkit/querverbindung.py`, ab appkit **1.7.0**):
```python
from appkit.querverbindung import archiviere
archiviere("news", titel, inhalt, quelle="…", tags=["finanzen"],
           ref="news:artikel:42", strom="wochenbericht", explizit=False)  # ziel="memory"
# -> {"ok": True, "status": "archiviert"|"vorhanden"|"uebersprungen", "id": …}  (wirft NIE)
```
Tests: appkit `test_querverbindung.py` (4) · core `test_querverbindung_relay.py` (3).
**Live verifiziert 15.06.** (End-to-End Core→Memory: archiviert · idempotent · zentral auditiert).

### 4b. ZWEITER Vertragstyp — Kalender (V5, ✅ GEBAUT 15.06.)
Neben dem Memory-Archiv-Umschlag gibt es einen **Kalender-Umschlag** für Termin-/Einladungs-Daten:
**Core-Relay** `POST /api/querverbindung/{ziel}/kalender` → `{ziel}/api/querverbindung/kalender`
(Default-Ziel `plans`), zentral auditiert (`querverbindung_kalender_relay`). **appkit-Helfer** (ab **1.9.0**):
```python
from appkit.querverbindung import sende_termin
sende_termin("kommunikation", "Kickoff", "2026-07-01T15:00", ende="…", ort="…",
             beschreibung="…", quelle="komm:konv:42", ref="komm:termin:42")  # ziel="plans"
# -> {"ok": True, "status": "eingetragen"|"vorhanden", "id": …}  (wirft NIE)
```
**Umschlag:** `titel · beginn(Pflicht) · ende · ganztags · ort · beschreibung · app · quelle · ref`.
**Empfänger:** Plans `POST /api/querverbindung/kalender` legt einen **Termin** an (`quelle=app`,
`extern_id=ref`), **idempotent** (gleicher iCal-Dedupe). Tests: appkit (2) · core (2) · plans (1) · komm (1).
**Live verifiziert** (Communication→Core→Plans: eingetragen + idempotent).

**★ RÜCKSYNC Plans→Communication ✅ GEBAUT 17.06. (World-Chat) — derselbe Kalender-Umschlag, andere Ziel-Seite:**
Der Core-Relay `POST /api/querverbindung/{ziel}/kalender` ist **generisch** (`ziel` = beliebige angedockte App)
⇒ KEIN neuer Vertragstyp, KEIN Core-Eingriff. **Sender** (Plans): „→ Kommunikation"-Knopf je Termin →
`POST /api/termine/{id}/an-komm` → `sende_termin("plans", …, ziel="kommunikation", ref="plans:termin:<id>")`.
**Empfänger** (Communication, `sensitivity=hoechst`): `POST /api/querverbindung/kalender` legt den Termin in
der schlanken read-only Tabelle `kalender_termine` ab (idempotent `quelle×extern_id`), `GET /api/kalender/termine`
(Filter `von`), `DELETE /api/kalender/termine/{id}` (Soft-Delete der lokalen Erinnerung — Quelle unberührt) +
„Anstehende Termine"-Panel mit ✕. **Nur Daten, kein Aktions-Auslöser.** Damit ist Communication↔Plans
**vollständig bidirektional** (V5 hin, Rücksync zurück). Plans `kalender_post`-Injektion (Tests). Tests:
komm (4: eintragen/idempotent · beginn-Pflicht · von-Filter · DELETE) · plans (1: Umschlag/Ziel/ref).
**Live verifiziert** (Plans→Core→Communication: eingetragen · idempotent `vorhanden` · Cleanup pristine).

### 4c. RÜCK-LESE — das „↔" (V5–V11, ✅ GEBAUT 15.06., appkit 1.10.0)
Die Gegenrichtung zum Archiv-Vertrag: eine App **fragt** das zentrale Archiv (Default Memory) ab, statt
abzulegen. Gegenstück zu `archiviere`. Wieder **über den Core** (Apps kennen nur den Core; zentral auditiert).
**Core-Relay** `GET /api/querverbindung/{ziel}/suche?q=…&semantisch=0|1&limit=N` → `{ziel}/api/suche`
(FTS5, Param `limit`) bzw. `{ziel}/api/suche/semantisch` (RAG/Vektor, Param `k`); auditiert
(`querverbindung_suche_relay`). **appkit-Helfer** (ab **1.10.0**):
```python
from appkit.querverbindung import memory_suche
memory_suche("ezb zinsen", limit=8)                 # Wortsuche (FTS5)
memory_suche("geldanlage", semantisch=True)         # Bedeutungssuche (RAG)
# -> {"ok": True, "treffer": [ {…Notiz-Meta, "auszug": …}, … ], "anzahl": n}  (wirft NIE, [] bei Fehler)
```
**Parametrische MCP-Tools** (für den Core-Agent/Leading): `build_http_mcp(..., query_tools=[…])` baut Tools
mit `q`+`anzahl`-Parametern; Memorys `mcp_server.py` exponiert so `memory_suche` (FTS) + `memory_semantisch`
(RAG) read-only im Namensraum `memory_*`. **Umschlag:** `q` (Suchtext) · `semantisch` (bool) · `limit`.
**Antwort:** `{ziel, ok, treffer[], anzahl}` bzw. ehrlicher `fehler` (Ziel offline ⇒ leere Treffer).
**Timeout (appkit 1.13.1, 17.06.):** `memory_suche(..., timeout=…)` (Default 5,0 s für explizite Suchen); der
mini_dizzi-Rück-Lese-Pfad (`_rueck_lese`) ruft mit **2,5 s**, damit ein träger Core/Memory die KI-Antwort nicht
spürbar verzögert — degradiert weiter sauber zu leeren Treffern.
Tests: appkit `test_querverbindung.py` (memory_suche, 4) · `test_mcp_appkit.py` (query_tools, 3) ·
core `test_querverbindung_relay.py` (Such-Relay, 4). **Live verifiziert 15.06.** (Notiz angelegt → über
Core-Relay per FTS gefunden → gelöscht; Memory pristine). Offen: semantischer Treffer braucht RAG-Einbettung
(degradiert sauber zu `[]`); die Rück-Lese-**Sendeseiten** je App (V5–V11) docken hieran an (App-Chats).

## 5. Sicherheit / HITL
- `sensibel=True` für **V9 Memory↔Money · V10 Memory↔Healthy · V11 Memory↔Trading** (+ generell
  Geld/Gesundheit). Healthy = `hoechst` ⇒ Memory-KI lokal_only; das Senden selbst erst nach
  **K4-HITL-Freigabe** (die sendende App schlägt die Archivierung als Aktion vor; Stufe
  `verifiziert`). **Nie ein Echtgeld-/Aktions-Auslöser** — nur Daten ablegen.
- Core auditiert jeden Relay (`von`/`ziel`/`ref`/`sensibel`/`status`).

## 6. Sendeseiten = App-Chat-Aufgaben (gegen diesen Vertrag)
Je Sender: appkit (≥1.7.0) **vendoren** (World-Chat: `ops/sync_appkit.py --to <repo>`), dann den
Auslöser bauen + `archiviere(...)` rufen. Idempotenz-`ref` je Quelle stabil wählen.
- **V2 News→Memory** (`news`) ✅ **GEBAUT 15.06.** (`41d7c78`, Tag-Reduktion `e36eb24`, **live-verifiziert** News→Core→Memory):
  `report_lauf` versucht nach jeder Report-Erstellung Auto-Archiv (`strom=sektor_report`,
  `ref=news:report:<id>`, **`tags=[]`** — Sektoren im Body, Herkunftslabel „News" zentral via Memory §9.1; Memory-Regel gated) · `POST /api/reports/{rid}/archivieren`
  = expliziter Knopf (`explizit=True`). appkit **1.7.0** vendort, `build_app(+archiv_post)` testbar.
  **UI-Knopf ✅** („in Memory archivieren" in der Report-Ansicht, browser-verifiziert :8297).
  **OFFEN:** Artikel-Strom (`artikel`) später. ⇒ **V2 funktional komplett** (auto via Regel + Zuruf-Knopf).
- **V3 Creating→Memory** (`creator`) ✅ **GEBAUT 15.06.** (`baac478`+`+Knopf`, **live-verifiziert**):
  `POST /api/assets/{id}/archivieren` reicht Asset-**Metadaten** (Modus/Modell/Lizenz/Rechte/Meta —
  Binärdatei bleibt im DAM) als Notiz an Memory (`strom=asset`, `ref=creator:asset:<id>`, heikle Inhalte ⇒ `sensibel`);
  „Memory"-Knopf je Galerie-Karte (browser-verifiziert :8294). appkit 1.7.0 vendort. **OFFEN:** Rezept-/
  Charakter-Strom später.
- **V4 Communication→Memory** (`kommunikation`) ✅ **GEBAUT 15.06.** (`3841c04`, **live-verifiziert**):
  `POST /api/konversationen/{id}/archivieren` reicht die ganze Konversation (Thread) als Notiz an Memory
  (`strom=mail`, `ref=komm:konv:<id>`, `tags=[kanal_typ]`); „in Memory"-Knopf in der Thread-Ansicht
  (browser-verifiziert :8298). appkit 1.7.0 vendort. **OFFEN:** Anlagen-Inhalt · einzelne Nachricht · `sensibel`-Default klären.
- **V5 Communication↔Plans-Kalender** (`kommunikation`→`plans`) ✅ **GEBAUT 15.06.** (komm `a456a82` · plans `74ee929` ·
  core/appkit `efb930d`, **live-verifiziert** Communication→Core→Plans): **ZWEITER Vertragstyp** (Kalender, §4b). `_sende_konv_termin`
  baut aus einer Konversation ein Event (Titel=Betreff, Beschreibung=Absender+Auszug) · `POST /api/konversationen/{id}/kalender`
  (`beginn` Pflicht, `ref=komm:termin:<konv_id>`) → Core-Relay `/plans/kalender` → Plans-Empfänger (Termin, idempotent).
  „→ Kalender"-Knopf in der Thread-Ansicht (Datums-Prompt). appkit **1.9.0** (`sende_termin`) in komm vendort.
  **OFFEN:** automatische Datums-Extraktion aus Mails (v1: Nutzer gibt das Datum an); Rück-Richtung (Plans→Comm).
- **V6 Plans→Memory** (`plans`) ✅ **GEBAUT 15.06.** (`4c75d93`, **live-verifiziert** Plans→Core→Memory + Cleanup):
  appkit 1.7.0 vendort · `_archiviere_projekt` (Metadaten + Fortschritt + Aufgaben-Überblick als Markdown) ·
  `POST /api/projekte/{pid}/archivieren` (`strom=projekt`, `ref=plans:projekt:<id>`, `explizit=True`) · ⇲-„In Memory"-
  Knopf je Projektkarte · `archiv_post`-Capture-Test · **keine Tags** (Herkunftslabel „Plans" zentral via Memory §9.1).
  **OFFEN:** Strom `meilenstein`/`projekt_notiz` später; optionales Auto-Archiv bei Status→abgeschlossen.
- **V7 Admin→Memory** (`admin`) ✅ **GEBAUT 15.06.** (`3f24de4`, **live-verifiziert** Admin→Core→Memory + Cleanup):
  appkit 1.7.0 vendort · `_archiviere_dokument` reicht Dokument-**Metadaten** (Typ/Datei/Notiz/Volltext-Auszug —
  Binärdatei bleibt im Admin-Vault, wie V3) · `POST /api/dokumente/{id}/archivieren` (`strom=dokument`,
  `ref=admin:dokument:<id>`, `explizit=True`, **Steuer/Vertrag⇒`sensibel`**, Nutzer-Tags reisen mit) · ⇲-Memory-Knopf
  je Dokumentkarte · Capture-Test. **Nebenbei gefixt** (pre-existing, beim Deploy aufgedeckt): Admin v2-Migrations-
  Ordering — `idx_dokumente_sha` lag im SCHEMA und scheiterte im `executescript` auf einer v1-DB („no such column:
  sha256") ⇒ Index nach `_migrate`-ALTER verschoben; Live-:8222-DB v1→v2 migriert.
- **V8 Management→Memory** (`management`) ✅ **GEBAUT 15.06.** (`1d779da`, **live-verifiziert** Management→Core→Memory + Cleanup):
  `_archiviere_post` reicht einen Post (Plattform/Status/Text/Hashtags/Medien-Überblick — Medien-Binärdaten bleiben
  im DAM/Verweis) · `POST /api/posts/{pid}/archivieren` (`strom=post_log`, `ref=management:post:<id>`, `explizit=True`,
  heikle Inhalte ⇒ `sensibel`, Plattform als Tag) · ⇲-Memory-Knopf je Post-Zeile · Capture-Test. appkit 1.8.0 (schon vendort).
- **V9 Money→Memory** (`finanzen`) ✅ **GEBAUT 15.06.** (`da64883`, **live-verifiziert** Money→Core→Memory + Cleanup):
  ERSTE sensible Querverbindung. `_archiviere_beleg` reicht eine Buchung (Datum/Betrag/Kategorie/Gegenpartei/Zweck/Notiz
  aus dem Double-Entry-Ledger) · `POST /api/buchungen/{id}/archivieren` (`strom=beleg`, `ref=finanzen:beleg:<id>`,
  `explizit=True`, **immer `sensibel=True`** ⇒ Memory-KI lokal_only; Kategorie als Tag) · ⇲-Knopf je Transaktionszeile ·
  Capture-Test. NIE ein Echtgeld-/Aktions-Auslöser. **`sensibel`-Flow end-to-end verifiziert** (Notiz korrekt sensibel).
- **V10 Healthy→Memory** (`health`) ✅ **GEBAUT 15.06.** (`21c106a`, **live-verifiziert** Health→Core→Memory + Cleanup):
  Health = `hoechst`. `_archiviere_verletzung` reicht eine Verletzung (Körperregion/Schweregrad/Status/Beschreibung/Notiz) ·
  `POST /api/verletzungen/{id}/archivieren` (`strom=verletzung`, `ref=health:verletzung:<id>`, `explizit=True`, **immer
  `sensibel=True`**; Körperregion als Tag) · ⇲-Knopf je Eintrag · Capture-Test. **HITL = bewusster, bestätigter Nutzer-Knopf
  (starker Confirm-Dialog).** OFFEN/deferred: die formale K4-ActionRegistry-Stufe (verifiziert-Step-up; Health hat noch keine
  Registry) — der lokale, einzeln bestätigte Klick reicht für v1.
- **V11 Trading→Memory** (`sensibel=True`, eigener Stack — kein appkit-Rezept, K4-HITL): Reports.

## 7. Betriebs-Lehre (15.06.)
**Live-Server können dem committeten Code hinterherhinken.** Memorys `/api/querverbindung/
archivieren` war im Code + Tests da, fehlte aber im LAUFENDEN :8212 (vor-Endpoint gestartet) ⇒
404. **Nach jedem Empfänger-Bau den Ziel-Server neu starten** und die Live-Route prüfen
(`/openapi.json`), nicht nur die Tests. (Audit-Routine erweitern: Live-Routen ≠ Code.)

## 8. Archiv-Regeln — Steuerung „automatisch vs. auf Zuruf" (Nutzer-Wunsch 15.06.)
Der Nutzer muss **pro Vernetzung klipp & klar festlegen**, was automatisch ins Memory-Archiv
wandert und was nur auf Zuruf (z. B.: *jeden* Wochen-News-Report automatisch, Einzelartikel nur
manuell). Konfiguriert **in Memory** = die zentrale Autorität & Single Source.

**Recherche / etablierte Muster:** **Readwise Reader** = *manuell per Default*; Auto-Verarbeitung
nur **opt-in je Quelle** + **Filter** je Feed. **Zapier/IFTTT** = **Trigger → Filter (skip-if) →
Action** je Automatik. ⇒ Übernommen: **konservativer Default (nichts flutet ungefragt)**, Auto
bewusst je Strom freischalten, optionale Filter. (Quellen unten.)

### 8.1 Adressierung — (Quell-App × Strom)
Jede Quelle hat benannte **Ströme** (Inhalts-Typen). Beispiele: News `artikel`/`sektor_report`/
`wochenbericht` · Creating `asset`/`rezept`/`charakter` · Communication `mail`/`anhang`/`thread` ·
Money `beleg`/`report` · Healthy `bericht` · Trading `report` · Admin `dokument`/`frist` · Plans
`projekt_notiz`/`meilenstein` · Management `kampagne`/`post_log`. ⇒ Granularität **bis auf den Typ**.
Der Umschlag trägt dafür `strom` + `explizit` (§3).

### 8.2 Regel je (app, strom) — Tabelle `archiv_regeln` in Memory
| Feld | Werte / Bedeutung |
|------|-------------------|
| `modus` | `aus` · **`manuell`** (auf Zuruf) · `auto` · `auto_gefiltert` |
| `filter` | nur bei `auto_gefiltert`: Tags⊇X · Schlüsselwort in Titel/Inhalt · Mindest-Relevanz · Kategorie/Sektor |
| `ziel_ordner` | Default-Ablage im Vault (z. B. `News/Wochenberichte`) |
| `sensibel` | Override (erzwingt `lokal_only`) |

- **Default = `manuell`** (Readwise-Prinzip: nichts ungefragt). **Selbst-registrierend:** sieht Memory
  ein neues `(app, strom)`, legt es als `manuell` an und zeigt es im Panel ⇒ nie „verschluckt", nie
  „flutet".
- **Sensible Ströme** (Money/Healthy/Trading): `auto` nur mit Stufe `verifiziert` + Warnung;
  Empfehlung bleibt `manuell`.

### 8.3 Durchsetzung — Autorität = Memory
Memorys Empfangs-Handler (`/api/querverbindung/archivieren`) wendet die Regel an:
- `explizit=true` → **immer archivieren** (Nutzer-Zuruf schlägt jede Regel).
- sonst nach `modus`: `auto` → archivieren · `auto_gefiltert` → nur wenn Filter trifft ·
  `manuell` / `aus` / kein-Treffer → **`uebersprungen`** (KEINE Notiz; Grund in der Antwort).
- Antwort-Status: `archiviert` · `vorhanden` · **`uebersprungen`** (+ Grund).

Der **Core-Relay bleibt dummer, auditierender Durchgang** (loggt auch `strom`/`explizit`/Ergebnis);
Memory entscheidet. **Sender** rufen `archiviere(...)` immer mit `strom`; der explizite „archivieren"-
Knopf setzt `explizit=true`. (Optimierung, optional: Sender lesen die Regeln vorab und senden
`manuell`-Ströme gar nicht erst — spart Last; nicht Pflicht.)

### 8.4 Zwei „auf Zuruf"-Wege
- **(a) Knopf in der Quelle** „in Memory archivieren" → `explizit=true` (Kern, einfach & klar).
- **(b) optional später — Eingangskorb in Memory:** `auto`-Kandidaten als **Vorschläge** sammeln,
  Nutzer behält/verwirft (Readwise „Feed → save"). Reicherer Modus, nicht für v1 nötig.

### 8.5 UI
**„Archiv-Regeln"-Panel in Memory**: Tabelle **Quelle × Strom** mit Modus-Auswahl (K2.4-Controls),
Filter-Editor, Ziel-Ordner — eine Stelle, klipp & klar. Neue Ströme tauchen automatisch (Default
`manuell`) auf.

### 8.6 Bau-Split
- **World-Chat (✅ 15.06.):** Umschlag +`strom`/`explizit` (Core-Relay + appkit-Helfer + Tests).
- **Memory-Engine ✅ GEBAUT (15.06., archiv `8a79af6`):** `archiv_regeln`-Tabelle + Regel-Anwendung im
  Empfangs-Handler (Status `uebersprungen`) + **`GET/PUT/DELETE /api/archiv-regeln`** + Selbst-
  Registrierung + Filter (Tags/Schlüsselwort) + `ziel_ordner`/`sensibel`-Override. 34 archiv-Tests,
  **live verifiziert** (manuell-Default überspringt, keine Notiz). **Panel ✅ GEBAUT** (Sektion
  „Archiv-Regeln" im Einstellungs-Fenster `archiv/static/index.html`, browser-verifiziert :8292;
  archiv `ecedc86`): Tabelle Quelle × Strom, Modus-Dropdown, Filter, Ziel-Ordner, sensibel, Löschen,
  manuelles Anlegen.
- **Reihenfolge-Invariante (erfüllt):** die Engine steht ⇒ `auto`-Sender sind freigegeben; der Nutzer
  setzt die Modi per API/Panel, Default bleibt `manuell` (nichts flutet ungefragt).

**Quellen (Recherche):** [Readwise Reader Docs](https://docs.readwise.io/reader/docs) ·
[Ghostreader (manuell-Default/opt-in)](https://docs.readwise.io/reader/docs/faqs/ghostreader) ·
[Reader Filtering Syntax](https://docs.readwise.io/reader/guides/filtering/syntax-guide) ·
[Zapier vs IFTTT (Trigger→Filter→Action)](https://clickup.com/blog/zapier-vs-ifttt/).

## 9. Memory-Feinschliff (Nutzer-Wunsch 15.06., aus Sender-Feel-Check) — ✅ GEBAUT 15.06.
> ✅ **KOMPLETT GEBAUT 15.06. (World-Chat, archiv `fdaed6c` · news `e36eb24`):** alle drei Punkte
> (9.1 Herkunfts-Labels · 9.2 Label-Löschen-UI · 9.3 Regel-Filter-Feld) + News-Tag-Reduktion.
> 100 archiv-pytest · 85 news-pytest grün; browser-verifiziert (:8292: Herkunfts-Reihe Magenta/⇲,
> ✕ je Label, Filter-Feld bei „auto + Filter"). Gehört VOR die weiteren Sender (betrifft alle
> Querverbindungs-Archive) — Reihenfolge erfüllt. Design-Notizen unten bleiben als Referenz.

### 9.1 Herkunfts-Labels (Grundlabels) — KERN ✅
**✅ GEBAUT:** Empfangs-Handler vergibt GARANTIERT genau ein Herkunftslabel (Map `_HERKUNFT_NAME`
news→News/creator→Creating/kommunikation→Communication/management→Management/finanzen→Money/
admin→Admin/plans→Plans/health→Healthy/trading→Trading; unbekannt ⇒ Titlecase). Eigene Frontend-Optik
(Magenta-Kontur + ⇲-Marke, eigene `.herk-reihe` abgesetzt vom normalen Pool, Notiz-Karte ⇲-Badge). News
sendet KEINE Sektor-Tags mehr (`tags=[]`, Sektoren im Body). **→ Seit §9.5 (15.06.) eine eigene System-Art
`labels.art='herkunft'`** (statt des anfänglichen `herkunft`-Booleans): eigener Namensraum, keine Kollision/
Beförderung mehr, system-verwaltet (kein Lösch-✕). Helfer `_herkunft_label_id` erzeugt nur in `art='herkunft'`.
**Problem (Original):** Sender schicken granulare Tags (News = ALLE Sektoren ⇒ 11 Labels = Lärm). **Ziel (Nutzer):**
jedes über eine Querverbindung archivierte Element trägt **absolut sicher EIN Herkunfts-Label** (die
Quell-App), **besonders erkennbar** als „Archiv aus einer anderen App".
**Design — zentral in Memory (= garantiert, sender-unabhängig):**
- Empfangs-Handler `/api/querverbindung/archivieren` wendet ein **Herkunfts-Label** an, abgeleitet aus
  `app`: news→**News** · creator→**Creating** · kommunikation→**Communication** · management→**Management** ·
  finanzen→**Money** · admin→**Admin** · plans→**Plans** · health→**Healthy** · trading→**Trading**
  (kleiner Map in Memory; unbekannt ⇒ Titlecase der id).
- **Neue Label-Art `herkunft`** (Spalte `herkunft` an `labels`, idempotente Migration) + **deutlich
  unterscheidbare Optik** im Frontend (reservierte Farbe/Icon-Präfix, z. B. „⇲"-Stil) ⇒ sofort sichtbar
  „kam aus App X". Herkunfts-Labels gehören NICHT in den normalen Label-Pool-Lärm.
- **Sender-Tag-Lärm reduzieren:** News schickt KEINE Sektor-Tags mehr (Sektoren stehen im Notiz-Body);
  das Herkunfts-Label „News" reicht. Creating/Communication-Tags sind schon minimal.

### 9.2 Label-Verwaltung — Löschen (Memory) ✅
**✅ GEBAUT:** Backend `DELETE /api/labels/{id}` (Soft-Delete + `notiz_labels`-Zuordnungen lösen +
betroffene Notizen re-indexieren) bestand bereits; **Frontend ergänzt**: ✕-Lösch-Control je Label-Chip
in der Ablage-Spalte links (`labelChip`/`loescheLabel`, Bestätigungsdialog, Auswahl-Reset wenn das
gelöschte Label gerade aktiv war).

### 9.3 Archiv-Regeln-Panel — Filter-Feld in der Anlege-Zeile ✅
**✅ GEBAUT:** in der „+ Regel"-Zeile ein Filter-Feld (`tag1, tag2 | wort`) ergänzt — eingeblendet
wenn Modus=`auto_gefiltert` (gespiegelt von den Bestandszeilen), beim Anlegen via `_parseFilter`
mit-gesendet (`secArchivRegeln` + Anlege-Handler `verdrahteRegeln` in `archiv/static/index.html`).
**Nutzer-Lob bestätigt:** Archiv-Regeln NUR in Memory-Einstellungen = richtig; Bestandsregeln sind sicht-
und verwaltbar = gut so.

### 9.4 Reihenfolge (erfüllt) — JETZT weiter mit den Sendern
1. ✅ **9.1 Herkunfts-Labels** (Map + `herkunft`-Spalte + Handler-Auto-Label + Frontend-Optik) + ✅ **News-Tag-Reduktion**.
2. ✅ **9.2 Label-Löschen** (Backend bestand, Frontend ergänzt).
3. ✅ **9.3 Filter-Feld** (Memory Frontend).
4. ✅ **V5 Communication↔Plans-Kalender** (`a456a82`/`74ee929`/`efb930d`, zweiter Vertragstyp, live-verifiziert) ·
   ✅ **V6 Plans** · ✅ **V7 Admin** · ✅ **V8 Management** · ✅ **V9 Money** · ✅ **V10 Healthy** — alle live-verifiziert.
   **NÄCHST: nur noch V11 Trading→Memory** (eigener Stack — kein appkit-Rezept, direkter Core-Relay-POST aus dem TB, K4-HITL).
   Danach Rück-Lese-Richtungen (`memory_suche` MCP) + Leading-Aggregation (V16).
- **Aufräumung 15.06.:** die 11 verwaisten **News-Sektor-Labels** (biotech/energie/finanzen/geopolitik/
  handel/ki/krypto/makro/prozessoren/quantum/rohstoffe, alle anzahl=0 aus den V2-Live-Tests) wurden im
  Live-Memory gelöscht (Nutzer-Auftrag). Verbleibend: bild/email (creator/komm), idee/reise (Nutzer), systemtest.

### 9.5 ✅ UMGESETZT (15.06., archiv `3ecb777`) — echte separate System-Labels (Enum `art`)
> **Nutzer-Entscheid: jetzt gebaut** (Null-Daten-Change = sauberster Zeitpunkt, vor jeglichem Herkunfts-Daten-
> aufkommen). Herkunfts-Labels sind nun eine **eigene System-Art** mit **eigenem Namensraum**, NICHT mehr die
> normalen frei erstell-/löschbaren Nutzer-Labels. Die **Namens-Kollision/„Beförderung" ist weg**: ein Nutzer-
> „Money" und ein Herkunfts-„Money" **koexistieren** getrennt.
>
> **Recherche-Fazit (Web 15.06., Quellen unten):** SQLite hat **keinen nativen ENUM-Typ** ⇒ „Enum" =
> `TEXT`-Spalte (app-validiert), erweiterbarer als der Boolean (weitere System-Arten später möglich, z. B.
> `smart`/`auto`), Boolean→Text trivial, **kein Lock-in** (anders als Postgres-Enum). Lookup-Tabelle wäre
> Over-Engineering. **Kniff für getrennte Eindeutigkeit:** SQLite-**partielle Unique-Indizes** statt Tabellen-`UNIQUE`.
>
> **So gebaut (archivapp/main.py + static/index.html + Tests):**
> 1. Schema/`_SCHEMA`: `labels.art TEXT NOT NULL DEFAULT 'normal'` statt Boolean `herkunft`, **ohne** Tabellen-`UNIQUE`.
> 2. Migration (idempotent): `ALTER ADD art` → Backfill `UPDATE … art='herkunft' WHERE herkunft=1` →
>    **Tabellen-Rebuild** für Alt-DBs (erkannt an der noch vorhandenen Legacy-Spalte `herkunft` via
>    `PRAGMA table_info` — bewusst NICHT am `UNIQUE` im CREATE-SQL, da SQLite Inline-Kommentare behält und
>    der Schema-Kommentar „Unique-Indizes" erwähnt; sonst feuerte der Rebuild auf jeder frischen DB unnötig.
>    Der Rebuild droppt zugleich die Legacy-Spalte `herkunft`) → zwei partielle Indizes
>    `ux_labels_norm`/`ux_labels_herk` (`WHERE art=…`).
> 3. `_herkunft_label_id` sucht/erzeugt nur in `art='herkunft'` — **befördert kein Nutzer-Label**.
> 4. `label_anlegen` + `_label_id` (Tags/Import) auf `art='normal'` eingegrenzt ⇒ greifen nie ein Herkunfts-Label.
> 5. Frontend: Schalter auf `l.art==='herkunft'`; Herkunfts-Chips **ohne Lösch-✕** (system-verwaltet), eigene
>    Magenta-/⇲-Reihe; „+ Label" erzeugt nur normale Labels.
> 6. `labels_liste`/`_labels_of` liefern `art` + abgeleitetes Bequemlichkeitsfeld `herkunft` (bool); MCP/KPI unberührt.
>
> **Tests:** Koexistenz gleichnamiger Arten (`test_herkunft_und_nutzerlabel_koexistieren`) + **Alt-DB-Rebuild**
> (`test_migration_alt_db_herkunft_boolean_zu_art_enum`, simuliert die Live-:8212-DB) + Herkunfts-Tests auf `art`.
> **102 archiv-pytest grün; Live-:8212 migriert verifiziert** (art da, herkunft+UNIQUE weg, 5 Labels art='normal',
> partielle Indizes); browser-:8292 (Koexistenz „Money"×2, Herkunfts-Chips ohne ✕).
> **Quellen:** [PostgreSQL Enum-Doku](https://www.postgresql.org/docs/current/datatype-enum.html) ·
> [MySQL ENUM Best Practices (Devart)](https://blog.devart.com/enum-in-mysql.html) ·
> [Choosing MySQL boolean types (openark)](https://code.openark.org/blog/mysql/choosing-mysql-boolean-data-types).
>
> **Optionaler Folge-Feinschliff (nicht nötig):** „Labels"-KPI könnte nur `art='normal'` zählen (System-Labels raus);
> Editor-✕ entfernt eine Notiz↔Herkunft-Zuordnung weiterhin (Label bleibt) — bewusst belassen.

## 10. OFFENE PUNKTE / VERBESSERUNGS-BACKLOG (gesammelt 15.06., Nutzer-Auftrag „jeden aufnehmen")
> Vollständige Liste der offenen Arbeiten + Verbesserungs-Ideen der Querverbindungs-Phase. Infrastruktur-/
> App-übergreifende Punkte stehen ZUSÄTZLICH in docs/_archiv/25 Hardening-Backlog (dort H-7…H-13).

### 10.1 Restliche Sender / Vertragstypen
- **V11 Trading→Memory** — der TB ist ein EIGENER Stack (kein appkit/`create_app`, eigene DB-Schicht). Sender = direkter
  Core-Relay-POST aus dem TB (`POST {core}/api/querverbindung/memory`) + K4-HITL (Trading-Daten sensibel). Strom `report`,
  `ref=trading:report:<id>`, `sensibel=True`. NIE ein Trade-/Aktions-Auslöser — nur Report-Daten ablegen.
  **★ ✅ LIVE 16.06. (Go-Live durchgeführt, Nutzer-Go):** Empfang+Sender gebaut + abgestimmt (Herkunfts-Map `tradingbot→Trading`,
  TB-Sender `c9b8a0f` trifft Vertrag exakt). TB-Branches in master `0699ab4` gemergt (309 T), `:8137` neu (V11-Endpoint live ·
  Flotte 51/51, O15 zurück · Heartbeat aktiv), **Live-E2E:** Report→Memory archiviert/`sensibel`/„Trading"/idempotent + Cleanup
  (Memory pristine). ⇒ **V11 KOMPLETT LIVE.** Offen (Nutzer): 2 Zombies O04/O13 aufräumen (gated M2). Details **§11.5.**
- **Rück-Lese-Richtungen (die „↔" in V5–V11):** ✅ **MECHANIK GEBAUT 15.06.** (appkit 1.10.0, §4c) — appkit-Helfer
  `memory_suche(q, semantisch=…)` + Core-Relay `GET …/{ziel}/suche` + parametrische MCP-Tools `memory_suche`/
  `memory_semantisch` (Memory `mcp_server`). Apps fragen das Archiv jetzt ab.
  **★ ✅ SENDESEITEN LIVE 16.06. (World-Chat, appkit 1.13.0):** statt N uneinheitlicher Per-App-Eingriffe (Apps sind
  KI-heterogen: Plans=LLM-Prompt, Money=deterministisch) zentral in **`mini_dizzi._fallback`** verdrahtet — gegated per
  Setting `ki_wissen_rueck_lese` (Default an) zieht der Ollama-Fallback JEDER App app-übergreifendes Wissen aus Dizz Memory
  (`querverbindung.memory_suche`, best-effort, wirft nie, `memory_get`-Injektion für Tests). appkit 1.12.0→**1.13.0** in alle
  11 Repos vendort (alle Test-Suites grün), 10 create_app-Apps neu gestartet ⇒ Setting live, Core-Watch 12/12. (Plans/Admin/
  News/TB haben zusätzlich ihre frühere Per-App-Rück-Lese.) **OFFEN:** **Plans→Communication-Kalender-Rücksync** (V5 zweite Richtung).
- **V12–V16** (docs/11 §5c): u. a. Money↔Trading, Money↔Admin, **Leading←Admin/Plans/Memory/Money** (V16, Aggregation, zuletzt).

### 10.2 V5-Kalender-Feinschliff (Communication↔Plans)
- **`ref=komm:termin:<konv_id>` ist immutabel:** eine Konversation ⇒ genau EIN Termin; falsches Datum + Neu-Senden ⇒ `vorhanden`
  (Korrektur greift nicht). → Update-Pfad (PATCH des Termins per ref) ODER `ref` inkl. Datum (mehrere Events je Konversation).
- **Keine ISO-Validierung von `beginn`** (Nutzer-Prompt) ⇒ Schrott-Datum landet roh im Kalender. → validieren/normalisieren (Sender + Empfänger).
- **Auto-Datums-Extraktion aus dem Mail-Body** (v1: Nutzer gibt das Datum an) — NLP/iCal-`VEVENT`-Erkennung in der Mail.
- **Mail-Termin ist nicht an ein Projekt gekoppelt** — optionales `projekt_id`-Linking beim Eintragen.

### 10.3 Memory-Polish (s. auch docs/_archiv/25 H-10/H-11)
- **Tag-Label-Wachstum:** Element-Tags (Dokument/Plattform/Kategorie/Körperregion) werden zu normalen Labels und akkumulieren —
  Aufräum-/Merge-UI oder „Tag (flüchtig) vs. Label (kuratiert)"-Trennung (H-10). **„Labels"-KPI** nur `art='normal'` zählen.
- **N+1** in Listen-/Suchpfaden — batchen, falls die Notizzahl groß wird (H-11).

### 10.4 Infrastruktur (s. docs/_archiv/25)
- ~~**H-9 appkit-Versions-Vereinheitlichung**~~ ✅ erledigt (alle 9 aktiven Apps auf appkit 1.12.0).
- ~~**H-7 appkit `on_delete`-Hook**~~ ✅ **GEBAUT 16.06.** (appkit 1.11.0): Account-Löschung räumt app-eigene
  Artefakte; Memory hängt `RagIndex.remove_user` + `MarkdownVault.purge_user` ein (Vault + RAG, DSGVO „weg = weg").
- ~~**H-2 Security-Response-Header**~~ ✅ **GEBAUT 16.06.** (appkit 1.12.0): `install_security_headers` (nosniff/
  no-referrer/SAMEORIGIN) netzwerkweit + Core.
- **H-12 formale K4-HITL-Stufe** (verifiziert-Step-up) für Money/Healthy, wenn Mehr-Nutzer/Step-up-Auth scharf wird.
- **H-13 CRLF-Normalisierung** (kosmetisch).

## 11. V11 Trading→Memory — Vertrag + SENDER GEBAUT + GO-LIVE-PLAN
> **Höchste Vorsicht (Nutzer-Auftrag): der Trading Bot darf NICHT falsch angefasst werden — absolute Perfektion.**
> Der TB ist ein EIGENER Stack + ein **App-Chat (📦)**; `appkit/`/`vertrag.py` sind dort READ-ONLY.
> **★ STAND 16.06.: BEIDE Seiten gebaut + aufeinander abgestimmt — V11 ist GO-LIVE-reif, aber der Live-Gang ist jetzt
> eine flotten-wirksame Großaktion (s. §11.5).** Empfangs-/Transport-Seite **fertig + live bewiesen** (§10.1: Core-Relay,
> Memory-Empfang, `tradingbot→Trading`-Label, `sensibel`-Flow, Idempotenz — verifiziert, Memory pristine). **Sendeseite
> ✅ GEBAUT vom TB-Chat** (Branch `feat/v11-trading-memory-sender`, Commit `c9b8a0f`) — trifft den Vertrag §11.1 EXAKT
> (World-Chat-Review 16.06., read-only: `report.py` POSTet roh an `:8200/api/querverbindung/memory` mit app=tradingbot/
> strom=report/sensibel=true/explizit/ref=`trading:report:<datum>`). ⇒ Mechanik passt; offen ist nur der **orchestrierte Go-Live**.

### 11.1 Vertrag (unveränderlich)
- **Endpoint:** `POST http://127.0.0.1:8200/api/querverbindung/memory` (Core-Relay; KEIN appkit-Helfer — der TB hat
  `querverbindung.py` nicht; rohes httpx/urllib genügt, KEIN appkit-Re-Vendoring).
- **Umschlag (JSON):** `app:"tradingbot"` · `strom:"report"` · `ref:"trading:report:<stabile-id>"` (Idempotenz) ·
  `sensibel:true` (**IMMER** — sensitivity `hoechst` ⇒ Memory-KI lokal_only) · `titel` · `inhalt` (Markdown-Text) ·
  optional `quelle`/`tags`/`ordner`. `explizit:true` beim Nutzer-Zuruf (schlägt jede Memory-Regel).
- **Antwort:** `{ziel:"memory", ok, status:"archiviert"|"vorhanden"|"uebersprungen", id}`.

### 11.2 Sicherheits-Schienen (NICHT verhandelbar)
1. **NIE Trading-Logik/Bot-Configs/Freqtrade/Bot-/Lern-DBs anfassen.** Der Sender LIEST nur bereits berechnete
   Status-/Report-Daten und POSTet Text. Niemals ein Trade-/Transfer-/Aktions-Auslöser.
2. **Additiv + isoliert:** EIN neuer Endpoint (+ optional EIN UI-Knopf). Keine bestehende Route/kein Verhalten ändern.
3. **Best-effort / fail-safe:** der ganze Sende-Pfad in `try/except`, kurzer Timeout (~5 s), **wirft NIE** in den
   Trading-Pfad. Core/Memory offline ⇒ der Bot läuft identisch weiter (nur Log-Hinweis).
4. **K4-HITL (hoechst):** v1 = expliziter, bestätigter Nutzer-Knopf „Report in Memory archivieren" (`explizit=true`),
   KEIN Auto-Versand. Gold-Standard = über die TB-`ActionRegistry`/`/api/actions` (Vorschlag→Freigabe Stufe
   `verifiziert`→Handler sendet). Niemals stillschweigend im Hintergrund senden.
5. **Backup-Disziplin zuerst** (TB-Ritual), auf eigenem Branch arbeiten, Tests grün halten (TB-master 299, V11-Branch **304**),
   NICHT ungefragt auf master. Sender-Test gemockt (Umschlag-Felder korrekt + best-effort wirft nicht). ✅ alles erfüllt.
6. **`:8137`-Neustart ist World-Chat** (Protokoll) — und seit der Tiefen-Reparatur eine **flotten-wirksame Großaktion**
   (Resume-Watchdog/ccxt-Timeout/O-DEF/Heartbeat/O15/Zombie-Bereinigung). **Voller Go-Live-Plan + Merge-Reihenfolge: §11.5.**

### 11.3 Was der Sender GEBAUT hat (TB, `report.py`, read-only-Review 16.06.)
`programm/backend/app/report.py` (neu, isoliert): `_gather()` liest **READ-ONLY** Status (Flotte/**Bot-Health/Heartbeat**
[neu aus dem „Bot-tot"-Fix]/Master/Evidenz) · `build_markdown()` = pure → (titel, markdown, `ref=trading:report:<datum>`) ·
`_post_relay()` roher **urllib**-POST (5 s) an `CORE_BASE:8200` + `/api/querverbindung/memory` · `archivieren()` best-effort
→ **wirft NIE** (Core/Memory offline ⇒ `{ok:false}`, Bot unbeeinflusst). `main.py`: additiver `POST /api/report/archivieren`.
`index.html`: **expliziter bestätigter HITL-Knopf** „Report in Memory archivieren" (confirm + Toast; KEIN Auto-Versand).
`test_report.py` (5): Umschlag exakt + best-effort. Der Report trägt jetzt auch die **Heartbeat-Health** je Bot.

### 11.4 Sender-Review (World-Chat, read-only) — Vertrag §11.1/§11.2 ERFÜLLT ✅
Jeder Punkt geprüft: Endpoint + Umschlag (app=tradingbot/strom=report/sensibel=true/explizit/ref) **exakt** · best-effort/
wirft-nie · additiv/isoliert (Trading-Logik/Configs/DBs unberührt, nie ein Trade-Auslöser) · HITL = bestätigter Knopf ·
Branch + Tests grün (304). Browser-verifiziert (Endpoint+Knopf da, **NICHT geklickt ⇒ kein echter Versand**). ⇒ Die
Empfangsseite (§10.1, live bewiesen mit simuliertem tradingbot-POST) und der Sender passen 1:1. **Keine Mechanik-Änderung nötig.**

### 11.5 GO-LIVE ✅ DURCHGEFÜHRT (16.06., World-Chat, auf ausdrücklichen Nutzer-Go) — V11 IST LIVE
**Ergebnis:** Backup-Tag `v11-golive-rollback-5c6a890` · `fix/fleet-resume-watchdog` (FF) + `feat/v11-trading-memory-sender`
(3-Wege-Merge, nur WIEDEREINSTIEG-Konflikt sauber gelöst) in TB-master `0699ab4`, **309 Tests grün** (Test-Isolation greift,
0 Pollution). `:8137` neu gestartet (PID 29960): **V11-Endpoint `/api/report/archivieren` live · Flotte 51/51 (O15 zurück, war 50/51)
· Heartbeat-Ampel auf allen 51 aktiv** (flaggt korrekt die 2 Zombies O04/O13 `536d8890`/`dac2caf8`). **Live-E2E:** Report über den
TB-Endpoint → Memory **archiviert · sensibel=True · Herkunft „Trading" · idempotent** (2. Versand = vorhanden) → Cleanup (Notiz +
Trading-Label) → **Memory pristine (5 Labels)**. **⇒ V11 Trading→Memory KOMPLETT LIVE.**
**OFFEN/FÜR-NUTZER (nicht autonom):** die 2 Zombies O04/O13 bleiben `stale` (Subprozesse überlebten den Backend-Neustart, laufen
mit Alt-Config ohne Timeout) — die Heartbeat-Erkennung flaggt sie, das **Aufräumen = Kill+Neustart der 2 Bots** (gated M2-Schritt,
bewusst nicht autonom). `train/nacht-3` (KI-Training) bewusst NICHT gemergt. **Historischer Plan unten (Stand vor dem Go-Live):**

Die TB-Reparatur war tief ⇒ der Live-Gang ist NICHT mehr „nur :8137 neu starten". Sorgfältig, mit Backup, **nur auf ausdrücklichen Nutzer-Go**:
1. **Drei+ offene Branches auf TB-master** (alle reviewbar): `feat/v11-trading-memory-sender` (V11) · `fix/fleet-resume-watchdog`
   (Resume-Watchdog **+ Test-Isolations-Fix `TBT_NO_STARTUP`**) · `train/nacht-3-2026-06-16` (Master-Netto-Gate-Härtung) ·
   älter `feat/tb-k22-design-k24-odef` (K2.2/O-DEF, „wartet auf Abnahme+Merge").
2. **★ MERGE-REIHENFOLGE-GOTCHA:** der V11-Branch entstand VOR dem Test-Isolations-Fix. Ohne `TBT_NO_STARTUP` feuern die
   V11-Tests (`TestClient(main.app)`) den Lifespan-`_run_startup` gegen das **ECHTE Backend** (genau die gerade gefixte
   Test-Pollution: audit-Spam + `runner.start`/Resume gegen die Live-Flotte). ⇒ **`fix/fleet-resume-watchdog` MUSS vor/mit V11
   in master**, bevor irgendeine V11-Test-/Suite läuft.
3. **:8137-Neustart = flotten-wirksame Großaktion** (EIN Neustart aktiviert ALLES Committete): V11-Endpoint · **Resume-Watchdog**
   (startet prozess-tote „running"-Bots periodisch nach, holt **O15** zurück) · **ccxt-Timeout-Migration** (patcht ALLE Bot-Configs) ·
   **O-DEF** (vorher Loopback-Drossel-Check — Dashboard-Polling ≤240 GET/min) · **Heartbeat-Ampel** · Auto-Resume bereinigt die
   **O04/O13-Zombies**. ⇒ Das ist kein Nebenbei-Schritt — bewusst, Backup zuerst (`programm_current_<head>`), Nutzer-Go.
4. **Live-E2E** (nach dem Neustart): `/openapi.json` zeigt `/api/report/archivieren` → einen Report über den HITL-Knopf bzw.
   den Endpoint senden ⇒ in Memory `archiviert`/`sensibel`/Herkunft „Trading"/idempotent prüfen ⇒ **Cleanup:** Notiz löschen
   **UND** das Herkunfts-Label „Trading" per `DELETE /api/labels/{id}` (überlebt das Notiz-Löschen; sonst 6 statt 5 Labels).
5. **Hoheit:** die TB-§6-Übergabe weist „mergen + Neustart + Live-E2E" dem World-Chat zu — ABER wegen Echtgeld-Sensibilität +
   Live-Flotten-Eingriff macht der World-Chat das **nur mit ausdrücklichem Nutzer-Go**, als bewussten Schritt. Bis dahin: alles
   vorbereitet, TB unangetastet. Danach §5c/§11 + WIEDEREINSTIEG nachziehen.

## 12. V15 · Beleg-Link Money ↔ Admin (DRITTER Vertragstyp, ✅ GEBAUT + LIVE 17.06.)
Bidirektionaler **Beleg-Link**: eine Dizz-Money-**Buchung** ↔ ein Dizz-Admin-**Dokument** (Rechnung/Quittung/
Vertrag). Money treibt (jede Buchung sucht ihren GoBD-Beleg), aber **beide Seiten speichern eine Referenz** ⇒
voll bidirektional. Anderer Umschlag als Archiv (§3) + Kalender (§4b) — der **dritte Vertragstyp**.

### 12.1 Mechanik (zwei additive Core-Relays, generisch)
- **Lookup** `GET /api/querverbindung/{ziel}/belege?q=&limit=` → `{ziel}/api/belege` (Default Admin liefert
  `[{ref:"admin:dokument:<id>", titel, typ, datum}]`). appkit-Helfer `belege_holen(ziel="admin", q=…)`.
- **Verknüpfung** `POST /api/querverbindung/{ziel}/verknuepfung` → `{ziel}/api/querverbindung/verknuepfung`.
  Umschlag `{von_app, von_ref, von_titel, ziel_ref, notiz}` (z. B. `von_ref=finanzen:buchung:42`,
  `ziel_ref=admin:dokument:7`). appkit-Helfer `verknuepfe(von_app, von_ref, von_titel, ziel_ref, ziel="admin")`.
  Beide best-effort/**werfen nie**, zentral auditiert. appkit **1.14.0**.

### 12.2 Money-Seite (Treiber, `finanzen`)
Migration `buchungen.beleg_ref` + `beleg_titel`. `GET /api/belege-auswahl` (zieht Admin-Dokumente über den
Lookup-Relay) · `POST /api/buchungen/{id}/beleg` {ref,titel}: setzt die **Vorwärts-Referenz** UND meldet Admin die
**Rück-Referenz** (`verknuepfe`) · `DELETE …/beleg` UND `DELETE /api/buchungen/{id}` (Storno) **melden Admin
`loese_verknuepfung`** (Audit-Fix 17.06.) ⇒ Admin räumt seine Rück-Ref, kein verwaister „verwendet in N"-Hinweis.
UI: je Buchung ein 📎-Knopf → Beleg-Auswahl aus Admin; verknüpft = „📎 Beleg"-Pill (klick = lösen). `von_titel` =
Gegenpartei/Zweck (Import) ⇒ Notiz (manuell) ⇒ Datum, **max. 60 Z.** (bewusst nur ein Anzeige-Label; Finanzdaten
bleiben bei der Quelle Money/`hoch`). Injektion `verknuepfung_post`/`belege_get` (Tests). NIE ein Echtgeld-Auslöser.

### 12.3 Admin-Seite (Empfänger, `buerokratie`)
Neue Tabelle `dokument_verknuepfungen` (idempotent `von_ref × dok_id`). `GET /api/belege` (Lookup-Quelle) ·
`POST /api/querverbindung/verknuepfung` (Empfang der Rück-Referenz; parst `ziel_ref=admin:dokument:<id>`,
prüft Dokument-Existenz) · `GET /api/verknuepfungen?dok_id=` (eine Query für die UI, kein N+1) ·
`DELETE /api/verknuepfungen/{id}` (Soft-Delete). UI: „🔗 N Buchung(en)"-Badge je Dokument (klick = Details + lösen).

### 12.4 Tests + Live-E2E
Tests: appkit (4: verknuepfe/belege_holen je Happy + best-effort) · core (4: beide Relays + 404 + offline) ·
buerokratie (3) · finanzen (4). **Live-E2E (Core+Admin+Money neu gestartet):** Admin-Dok hochgeladen → Money-Beleg-
Auswahl zeigt es über den Core-Relay → Money verknüpft → Admin-Rück-Referenz angelegt → Money-Buchung trägt
`beleg_ref` → Idempotenz `vorhanden` → **Cleanup pristine** (beide Seiten 0 Reste). Damit ist V15 voll bidirektional live.
## 13. V14 · Trading & Steuer in Money (Money ← Trading, ✅ GEBAUT + LIVE 17.06.)
Nutzer-Leitidee: **Money ist die steuerlich-rechtliche Instanz** für die Trading-Gewinne —
Einstiegskapital + Verlauf tracken, Versteuerungs-Schwellen überwachen, jederzeit dem Finanzamt
sauber darlegbar. **Erkenntnis:** der Trading-Bot läuft `proposal-only, 0 Echtgeld` (Paper) ⇒ die
maßgebliche Echtgeld-Schiene gehört nach Money; der TB liefert read-only nur den Performance-Verlauf.
**KEINE Steuerberatung — ein Schätz-/Dokumentationswerkzeug.**

### 13.1 Steuer-Engine (`moneyapp/trading_steuer.py`, rein/testbar — der rechtliche Kern)
Zwei Regime (Nutzer-Entscheid „beides", Recherche dt. Recht 2025/26):
- **§ 20 Futures/Perpetuals** (Bitget-Bot, Termingeschäft): Abgeltungsteuer `e/(4+k)` (§ 32d Abs. 1;
  k=KiSt-Satz, 9 % ⇒ 24,45 %), Soli 5,5 %, **Sparer-Pauschbetrag 1.000 € als Freibetrag** (nur Überschuss
  steuerpflichtig), Verluste voll verrechenbar (JStG 2024) + Vortrag, **Anlage KAP** (ausl. Börse = Selbsterklärung).
- **§ 23 Spot**: **1-Jahr-Haltefrist** (kalendarisch, schaltjahr-sicher; Verkauf am Jahrestag noch steuerpflichtig)
  ⇒ danach **steuerfrei**; innerhalb der Frist **Freigrenze 1.000 € = alles-oder-nichts** (> Grenze ⇒ GESAMTER
  Gewinn mit persönlichem Satz), **Anlage SO**.
`jahres_auswertung` aggregiert je Jahr + Regime + erzeugt die **Schwellen-Vorwarnung**; `kapital_stand`
liefert investiert/aktueller Wert/unrealisiert. 19 Engine-Tests (Referenzzahlen verifiziert).

### 13.2 Money-Seite (`finanzen`)
Tabellen `trading_kapital` (einlage/entnahme/bewertung = Echtgeld-Verlauf), `trading_realisierung`
(§20/§23, signierter Netto-Betrag, kauf_datum für die Haltefrist), `trading_config` (Pauschbetrag-/
Freigrenze-Rest, persönl. Satz, KiSt — Default KiSt 9 %). Endpoints `/api/trading/{config|kapital|
kapital/stand|realisierungen|steuer|steuer/export|tb-performance}` (CRUD + Jahres-Steuer-Übersicht +
**vorzeigbarer Jahresbericht** `steuer/export` als Markdown/CSV/JSON, gegliedert nach Anlage KAP §20 /
Anlage SO §23 mit Einzelposten + Summen + Disclaimer — „dem Finanzamt darlegen", `jahres_bericht_markdown`).
Frontend-Panel „Trading & Steuer" (Kapital-Stand, Jahres-Steuer je Regime, Vorwarnungen, Realisierungen/
Kapital erfassen, Steuer-Parameter, Bericht/CSV-Export, TB-Performance read-only). 6 Endpoint- + 21 Engine-Tests.

### 13.3 V14-Brücke (read-only TB-Performance)
`GET /api/trading/tb-performance` zieht die TB-Kennzahlen über den Core (`/api/panels/tradingbot/stats`)
— **rein informativ, als Paper gelabelt**, best-effort, `tb_get`-Injektion. **Kein TB-Eingriff, nie ein
Trade-/Echtgeld-Auslöser.** **Live-E2E** (Money neu gestartet): Config-Default KiSt 9 % · Kapital-Stand ·
Futures 500 € steuerpflichtig + AbgSt 122,25 € (= 50000/4,09) · Spot über Freigrenze ⇒ alles steuerpflichtig ·
2 Warnungen · TB-Brücke read-only running=51 · Cleanup pristine. 24 Tests gesamt (19 Engine + 5 Endpoints).