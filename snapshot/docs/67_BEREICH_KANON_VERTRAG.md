# 67 · BEREICHS-KANON — Vertrag (VO-2: BER-1 / BER-2 / BER-3 + ME-1)

> **Status: DESIGN-VERTRAG (04.07.2026, Architektur-KI) — kein Bau, keine DB-Migration, kein Rollout.**
> Bau-Spec analog docs/62–66: dieser Vertrag + Verträge-als-Code in `packages/appkit/bereich_register.py`
> (+ Vertrags-Tests) legen ALLE Architektur-Entscheidungen fest, damit Bau-KI ohne Design-Entscheid baut
> und migriert. Auftrag: docs/58 §3.B (BER-1/2/3, ME-1) + §4 VO-2. Grundlage: docs/49 (Typ-Modell,
> bleibt admin-kanonisch) · docs/34 (V17–V19-Mechanik) · docs/26 (Querverbindungs-Registry) ·
> `packages/appkit/bereiche.py` (`BereicheBasis`, seit 26.06. Single-Source des CRUD-Gerüsts).
> **Gates:** G-BEREICH-ID ✅ · G-BEREICH-ENUM ✅ · G-BEREICH-CUTOVER ✅ — **alle FREIGEGEBEN 04.07.2026 (David)**; §12. Bau-Pakete: §9.

## 0 · TL;DR
Der **Bereich** ist die netzweite Ordnungs-Achse (privat/geschäftlich/…), über die Money · Memory ·
Management · Admin heute nur **lose per Freitext-String** koppeln (`kontext`-Match, case-insensitiv,
Name-/Bot-/Ordner-Fallbacks). Umbenennen bricht Links **still**; Mehrdeutigkeit wird per `LIMIT 1`
verschluckt; vier `art`-Kataloge divergieren; die `bereiche`-DDL liegt 4× im Netz. Dieser Vertrag setzt:

1. **BER-1** — die **kanonische Bereichs-ID** = `bereiche.id` des **Admin-Bereichs** (Admin ist die
   Heimat der Entität, docs/49). Konsumenten-Apps tragen sie in einer neuen additiven Spalte
   **`kanon_id`** an ihrer lokalen `bereiche`-Tabelle. Auflösung läuft künftig über die
   **Dual-Read-Kette** `kanon → kontext → App-Alt-Fallback` — rückwärtskompatibel, jede Stufe meldet
   ihre `quelle`. Ein **Broken-Link-Wächter** (read-only, pure appkit-Logik) erkennt dangling und
   mehrdeutige Kanten, BEVOR und NACHDEM migriert wird.
2. **BER-2** — ein netzweites **Basis-Typ-Set aus 5 stabilen Ober-Kategorien** ÜBER den app-lokalen
   `art`-Katalogen (die bleiben). Jede App-`art` mappt auf genau eine Ober-Kategorie; App-Erweiterungen
   erlaubt, aber map-pflichtig. Enum-Angleich Money **`privat`→`persoenlich`** = benannter Schritt
   MIG-ART-1 (Gate G-BEREICH-ENUM).
3. **BER-3** — `DzBereichRegister` in **`packages/appkit/bereich_register.py`**: Auflösekette,
   Verknüpfung, Wächter, Ober-Kategorien, Schema-Generator (DDL-Single-Source), Migrations-Phasenmodell.
   Setzt auf `BereicheBasis` **auf** (Komposition) — `appkit/bereiche.py` bleibt **unverändert**.
4. **ME-1** — das **Memory-Ober-Register** als erste Anwendung des kanonischen Musters
   (Bereich→Landing→Ordner/Notizen, Roll-up-Endpoint, `parent_id`-Baum); die Baum-/Roll-up-Helfer
   liegen in appkit und gelten für alle vier Apps.

**Leitplanken:** additiv & fail-closed · Dual-Read vor Cutover · Backup-first je Phase · V-Kanten
V16–V19 bleiben durchgehend intakt · kein Konsument bricht zu irgendeinem Zeitpunkt.

## 1 · Ist-Zustand (Befund, verifiziert 04.07.)

**Vier lokale `bereiche`-Achsen** (alle auf `BereicheBasis`, appkit): Admin (`adminapp/bereiche.py`,
Typ-Modell-Heimat) · Money (`moneyapp/bereiche.py`) · Memory (`archivapp/bereiche.py`) · Management
(`managementapp/bereiche.py`).

**Die Kopplung (V17/V18/V19, docs/34):** Admin-Bereiche tragen drei Freitext-Slots
(`money_kontext` · `management_kontext` · `memory_ref`, `adminapp/bereiche.py:94–96`); das
Bereichs-Cockpit (`aggregat.bereich_spuren`) schickt sie per Core-Relay an die Quell-Apps. Dort:

| Kante | Konsument | Auflösung heute | Fallback (Alt-Mechanik) |
|---|---|---|---|
| V17 | Money `/api/bereich/finanzspur?kontext=` | `LOWER(kontext)=LOWER(?)` **oder** `LOWER(name)=…`, kontext bevorzugt, `LIMIT 1` ohne definierte Sekundär-Ordnung (`moneyapp/main.py:1945–1950`) | Kategorie-Namen-Match |
| V18 | Management `Domain.social(kontext)` | `LOWER(kontext)=LOWER(?)`, `ORDER BY sort_order, name LIMIT 1` (`domain.py:430–433`) | Social-Bot-Namen-Match |
| V19 | Memory `/api/kategorie?ordner=` | **Ordner-NAME** (kein Bereichs-Bezug!) | — |

**Schuld-Klassen daraus:**
- **B-1 Stille Broken-Links:** Umbenennen von `kontext`/Name/Ordner ⇒ Cockpit-Spur leer, niemand merkt es.
- **B-2 Stille Mehrdeutigkeit:** zwei Bereiche mit gleichem `kontext` (case-insensitiv) ⇒ `LIMIT 1`
  wählt willkürlich (Money sogar ohne definierte Ordnung).
- **B-3 Enum-Divergenz** (`art`): admin `geschaeft·studium·mandant·fortbildung·persoenlich·sonstiges` ·
  money `geschaeft·privat·projekt·mandant·investment·sonstiges` (**`privat` noch nicht angeglichen**;
  Admin hat `privat→persoenlich` bereits migriert, `adminapp/bereiche.py:132`) · memory
  `projekt·lebensbereich·wissen·referenz·sonstiges` · management `kunde·marke·kampagne·projekt·persoenlich·sonstiges`
  ⇒ netzweite Roll-ups unmöglich.
- **B-4 DDL-Duplikat:** 4× fast identisches `SCHEMA_BEREICHE` + 3× eigene `migriere_*`-Funktion,
  trotz `BereicheBasis`.
- **B-5 Kein Bereichs-Bezug in V19:** Memory koppelt am Ordner-Namen statt an seiner eigenen
  Bereichs-Achse (die existiert und `parent_id`-Hierarchie + Notiz-Vererbung schon trägt).

**Warum jetzt:** der Bau-KI-Bau der Agenten-Regie (Z4.1/Z4.2, docs/63) arbeitet **pro Bereich**
(Autonomie-Stufen je Bereich, `geld`/`gesundheit` fest `pre_approval`). Ohne kanonische ID und stabile
Ober-Kategorie erbt er B-1–B-3 als Fundament-Schuld.

## 2 · Zielbild

```
                Admin-Bereich  (Heimat der Entität, docs/49)
                id = ★ KANONISCHE BEREICHS-ID (netzweit)
                money_kontext / management_kontext / memory_ref  (bleiben: sprechende Alt-Schlüssel)
                     │  Cockpit/Relay sendet BEIDE: kanon=<id> & kontext=<slot>
      ┌──────────────┼──────────────────┐
   Money           Management         Memory
   bereiche        bereiche           bereiche
   + kanon_id ◄────┴─── neue additive Spalte, bindet lokalen Bereich an den Kanon
   Auflösekette je App:  ① kanon_id (exakt)  ② kontext (CI, eindeutig)  ③ App-Alt-Fallback
                          └─ appkit DzBereichRegister ─┘   └─ app-lokal (Kategorie/Bot/Ordner)
```

- **Eine** Identität pro realem Lebens-Bereich, vergeben von Admin, konsumiert per `kanon_id`.
- Die App-Bereiche bleiben **app-eigene Zeilen** (lokal-first, standalone-fähig ohne Admin);
  `kanon_id=''` = ungebunden, alles funktioniert wie heute.
- Ober-Kategorie liegt als **Netz-Layer über** den `art`-Katalogen; das Admin-Typ-Modell
  (Modul-Freischaltung) bleibt unberührt admin-kanonisch.

## 3 · BER-1 — Kanonische Bereichs-ID + Broken-Link-Wächter

### 3.1 Die ID
- **Kanonische Bereichs-ID = `bereiche.id` des Admin-Bereichs** (UUID-String aus `appkit.db.new_id`).
  Kein neues Format, kein Präfix-Namensraum — die Spalten-Semantik (`kanon_id`) trägt die Bedeutung.
- **Unveränderlich & nie recycelt** (Soft-Delete behält die Zeile). Admin-`bereiche` trägt selbst
  **keine** `kanon_id` (es IST der Kanon — Invariante I-2).
- **Spaltenvertrag Konsumenten** (money/management/memory): `kanon_id TEXT NOT NULL DEFAULT ''` +
  Index `idx_bereiche_kanon (user_id, kanon_id)`; additiv per idempotentem ALTER
  (`migriere_kanon_id`, PRAGMA-Guard — Muster `migriere_bereich_fk`).
- **Eindeutigkeit:** pro `user_id` bindet eine `kanon_id` höchstens EINEN lokalen Bereich
  (`verknuepfen` erzwingt das fail-closed; Bestands-Verstöße meldet der Wächter). Umgekehrt ist
  n:1 NICHT erlaubt — ein lokaler Bereich trägt höchstens eine `kanon_id` (Spalte, kein Join-Table;
  bewusst einfach — Mehrfach-Bindung war nie ein realer Fall).

### 3.2 Die Auflösekette (Dual-Read)
Kanonisch in `DzBereichRegister.aufloesen(user_id, *, kanon="", kontext="")` → `Aufloesung`:

| Stufe | Regel | `quelle` |
|---|---|---|
| ① kanon | `kanon_id = ?` exakt (case-sensitiv), nur nicht-gelöschte | `"kanon"` |
| ② kontext | `LOWER(kontext)=LOWER(?)`, `kontext<>''`, Ordnung `sort_order, name` | `"kontext"` |
| ③ App-Fallback | **app-lokal NACH** `bereich_id is None` (Money: Name-/Kategorie-Match · Management: Bot-Name · Memory: Ordner-Name) | app-eigen (`"fallback"`-Konvention) |

- `Aufloesung = (bereich_id | None, quelle, mehrdeutig)`. **`mehrdeutig=True`**, wenn die Stufe >1
  Treffer hatte (Wahl bleibt deterministisch `sort_order, name` — B-2 wird sichtbar statt still;
  Moneys bisher undefinierte Sekundär-Ordnung wird damit vereinheitlicht).
- Fehlt die `kanon_id`-Spalte (Migration nicht gelaufen), fällt Stufe ① **lautlos** auf ② durch
  ⇒ `aufloesen(kontext=…)` ist **Stufe-0-wertgleich** zur heutigen kontext-Auflösung (Invariante I-3).
- Apps mit `kontext_spalten=()` (Memory) überspringen ② strukturell.
- Auflösung ist **immer user-scoped** (wie heute); Cross-App-User-Mapping bleibt Dizzi-ID-Thema
  (docs/17), außerhalb dieses Vertrags.

### 3.3 Verträge der V-Kanten (additiv, bricht nichts)
- **Query-Param `kanon=`** zusätzlich zu `kontext=` an: Money `GET /api/bereich/finanzspur`,
  Management `GET /api/bereich/social` (Memory: §6). Die Core-Relays
  (`/api/querverbindung/…/finanzspur|bereich-social|kategorie`) reichen `kanon` durch.
- Admin-Cockpit (`aggregat.bereich_spuren`) sendet **beide**: `kanon=<bereich.id>` +
  `kontext=<slot>`. Die Antworten tragen bereits `quelle` (Money: `"bereich"|"kategorie"`) —
  erweitert auf `"kanon"|"kontext"|<app-fallback-name>`, damit das Cockpit die Bindungsgüte zeigt.
- Die drei Admin-Slots (`money_kontext`/…) **bleiben** als sprechende Alt-Schlüssel + Anzeige;
  führend wird die ID. Kein Slot wird gelöscht (Rückwärts-Leiter).
- **Neu je Konsument:** `GET /api/bereiche/kanon-status` → `{"bereiche":[{id, name, kanon_id,
  kontext?}], "anker_extra": {…}}` — der Wächter-Feed (read-only; Memory liefert unter
  `anker_extra.ordner` zusätzlich seine Ordner-Namen für die V19-Alt-Kante).

### 3.4 Broken-Link-Wächter
- **Kern = pure appkit-Logik** (`bereich_register.waechter_report`), ohne HTTP/DB — voll testbar:
  Eingabe Admin-Bereiche + je Kante ein `AnkerIndex` (kanon-Set, kontext- und namens-Zählung,
  case-insensitiv); Ausgabe standardisierter Report.
- **Befunde je Kante & Bereich:** `ok` (kanon-Bindung trifft) · `alt` (nur kontext-/Namens-Treffer,
  keine kanon-Bindung — funktioniert, aber fragil) · `dangling` (Slot/ID gesetzt, kein Treffer) ·
  `mehrdeutig` (>1 Treffer) · `ungenutzt` (Slot leer) · `verwaist_app` (Reverse-Check D4/F18: app-seitige `kanon_id` ohne lebenden Admin-Bereich — Richtung App→Admin, im Vorwärts-Loop unsichtbar). Zusammenfassung mit Zählern je Befund.
- **Läufe:** on-demand — Admin `GET /api/bereiche/waechter` (bündelt die drei `kanon-status`-Feeds
  per Core-Relay, best-effort: App offline ⇒ Kante `unbekannt`, wirft nie) + ops-CLI-Aufruf für
  Migrations-Reports. **Kein Daemon**, rein lesend, verändert nie Daten (Invariante I-6).
- Der Wächter ist **Vorbedingung und Nachweis** der Migration: Baseline-Report vor P1, 0 `dangling`
  als Cutover-Gate (§7).

## 4 · BER-2 — Basis-Typ-Set (Ober-Kategorien)

### 4.1 Das Set (netzweit, geschlossen, appkit-kanonisch)
`OBER_KATEGORIEN = ("persoenlich", "geschaeftlich", "bildung", "projekt", "sonstiges")`
— Semantik: `persoenlich` = privates Leben/Vermögen · `geschaeftlich` = Erwerb/Mandate/Marken ·
`bildung` = Bildung & Wissen (Studium, Fortbildung, Wissensgebiete, Referenz) · `projekt` =
zeitlich begrenztes Vorhaben · `sonstiges` = neutraler Rest. Das Set ist bewusst klein (Roll-ups,
Agenten-Politik je Ober-Kategorie); Erweiterung nur per Vertrags-Update dieses Dokuments.

### 4.2 Default-Mapping (jede App-`art` → genau EINE Ober-Kategorie)
| App | Mapping |
|---|---|
| admin | geschaeft→geschaeftlich · mandant→geschaeftlich · studium→bildung · fortbildung→bildung · persoenlich→persoenlich · sonstiges→sonstiges |
| money | geschaeft→geschaeftlich · mandant→geschaeftlich · investment→persoenlich¹ · projekt→projekt · privat→persoenlich (bis MIG-ART-1) · persoenlich→persoenlich · sonstiges→sonstiges |
| memory | projekt→projekt · lebensbereich→persoenlich · wissen→bildung · referenz→bildung · sonstiges→sonstiges |
| management | kunde→geschaeftlich · marke→geschaeftlich · kampagne→projekt · projekt→projekt · persoenlich→persoenlich · sonstiges→sonstiges |

¹ Davids Investments (Depots/TB) sind Privatvermögen; geschäftliche Investments laufen ohnehin in
`geschaeft`-Bereichen. App-Override möglich (1 Zeile).

- **Regeln:** unbekannte `art` ⇒ `sonstiges` (fail-closed neutral). Apps DÜRFEN ihren `art`-Katalog
  erweitern, MÜSSEN aber je neuer `art` das Mapping deklarieren — `mapping_validieren(arten, mapping)`
  ist der Vertrags-Check (Test + Bau-Zeit-Assert). Die **App-`art`-Kataloge bleiben** (Nutzer-nahe
  Sprache je Domäne ist Absicht, kein Unfall); kanonisch wird nur die Ober-Ebene.
- **API-Sichtbarkeit (Bau):** `_public`-Antworten aller vier Apps tragen additiv
  `"ober_kategorie": …` (aus `ober_kategorie_fuer(art)`); Roll-up-/Cockpit-/Agenten-Flächen gruppieren
  danach. Das Admin-Typ-Modell (`module_fuer_typ` etc.) bleibt unverändert admin-kanonisch (docs/49) —
  Ober-Kategorie gated KEINE Module.

### 4.3 MIG-ART-1 · Enum-Angleich `privat` → `persoenlich` (Money) — Gate G-BEREICH-ENUM
Benannter, idempotenter Migrations-Schritt (Muster: Admin hat ihn 26.06. vollzogen):
`UPDATE bereiche SET art='persoenlich' WHERE art='privat'` + `arten`-Tuple-Tausch in
`moneyapp/bereiche.py` (+ DDL-Kommentar). Keine Daten verschoben/gelöscht; Frontend-Label-Check
gehört zum Bau-Paket. David-Go ✅ 04.07. (§12); das Default-Mapping trägt bis zum Bau beide Schreibweisen.

## 5 · BER-3 — `DzBereichRegister` (appkit-Modul)

### 5.1 Schnitt zum Bestand
**Neues Modul `packages/appkit/bereich_register.py`** — `packages/appkit/bereiche.py`
(`BereicheBasis`) bleibt **byte-unverändert** (Invariante I-1). Das Register arbeitet per
**Komposition** auf derselben `Database` (es kennt nur die `bereiche`-Tabelle, NIE Domänen-Tabellen).

### 5.2 API-Oberfläche (Verträge-als-Code; Stubs liegen bei, voll implementiert wo pure)
```python
OBER_KATEGORIEN; OBER_MAPPING_DEFAULT                 # §4-Kanon als Code
ober_kategorie_fuer(art, extra=None) -> str            # unbekannt ⇒ "sonstiges"
mapping_validieren(arten, mapping) -> None|raise       # jede art gemappt, Ziele im Set

schema_bereiche(kontext_spalten=(), *, mit_kanon=False) -> str
    # DDL-Single-Source: erzeugt die bereiche-DDL (+Indizes); reproduziert die vier
    # Bestands-Schemata WERTGLEICH (Vertrags-Test, kommentar-/whitespace-normalisiert).
migriere_kanon_id(db) -> None                          # idempotenter ALTER + Index (P1)

@dataclass(frozen=True) class Aufloesung: bereich_id: str|None; quelle: str; mehrdeutig: bool
class DzBereichRegister:                               # Komposition: (db) wie BereicheBasis
    aufloesen(user_id, *, kanon="", kontext="") -> Aufloesung        # §3.2-Kette ①+②
    verknuepfen(user_id, bereich_id, kanon_id) -> dict  # fail-closed: Eindeutigkeit, Spalten-Check
    loesen(user_id, bereich_id) -> dict                 # kanon_id := ''
    kanon_status(user_id) -> list[dict]                 # Wächter-Feed (§3.3)

anker_index(bereiche, *, extra_namen=()) -> AnkerIndex  # Prüf-Index einer Kante (Memory: Ordner-Namen)
waechter_report(admin_bereiche, anker_je_kante) -> dict # §3.4, pure
backfill_vorschlaege(admin_bereiche, kante, app_bereiche) -> list[dict]  # §7 P2, NUR eindeutige, dry-run
baum_bauen(bereiche) -> list[dict]                      # parent_id → Baum; verwaiste/zyklische → Wurzel + Flag
rollup_zaehler(baum, zaehler_je_bereich) -> list[dict]  # Zähler die Hierarchie hochsummiert (ME-1)
```

### 5.3 Invarianten des Moduls
- **Rein additiv**: kein bestehender appkit-/App-Pfad ändert Verhalten, solange keine App das Modul
  importiert (wie `appkit.bereiche` vor dem 26.06. — bewährtes Adoptionsmuster).
- `aufloesen` ohne `kanon_id`-Spalte ≡ heutige kontext-Auflösung (Stufe-0-wertgleich, I-3).
- Schreibpfade (`verknuepfen`/`loesen`) sind die EINZIGEN Schreiber von `kanon_id`; beide auditieren
  (`db.audit`), beide fail-closed (fehlende Spalte ⇒ klarer Fehler „MIG-KANON-1 nicht gelaufen", 
  keine stillen No-ops).
- Wächter/Backfill/Baum/Roll-up sind **pure** (keine DB, kein HTTP) — die App-Adapter füttern sie.

## 6 · ME-1 — Memory-Ober-Register (erste Anwendung, kanonisches Muster)

**Muster, nicht Memory-Sonderweg:** die drei Bausteine (Baum · Roll-up · Übersichts-Endpoint) sind
appkit-kanonisch und gelten wortgleich für Money/Management/Admin.

- **View-State-Kanon (3 Ebenen):** ① **Ober-Register** = Bereichs-Karten aus dem Roll-up (oberster
  View-State der App) → ② **Bereichs-Landing** (Zähler, Unter-Bereiche, letzte Inhalte, Ober-Kategorie)
  → ③ **Inhalt** (Memory: Ordner/Notizen bereichs-gefiltert über die bestehende Vererbung
  `effektiv_bereich_where`). URL-Hash-Kanon: `#bereich=<id>` (Ebene ②), zurück = Ebene ①.
- **Roll-up-Endpoint-Vertrag (je App):** `GET /api/bereiche/uebersicht` →
  `{"baum":[{…bereich, "ober_kategorie", "zaehler", "rollup", "kinder":[…]}], "verwaiste": n}`
  — `baum_bauen` + `rollup_zaehler` aus appkit, `zaehler` = das bestehende `inhalt()` je Bereich
  (Memory zählt via Vererbung — Override bleibt), `rollup` = Zähler inkl. aller Unter-Bereiche.
  Read-only; Literal-Route VOR `/{bid}` registrieren (bekannte Falle).
- **V19-Anhebung:** Memorys Kanten-Ziel wird der **Memory-Bereich** (per `kanon`/`kontext`-Auflösung
  wie V17/V18 — Memory bekommt dafür im Bau die `kontext`-Spalte NICHT: Auflösung läuft `kanon`-only
  ①→③), Aggregat = Notizen/Ordner mit effektivem Bereich; **Ordner-Namen-Match bleibt Alt-Fallback ③**
  (`memory_ref` funktioniert unverändert weiter). `/api/kategorie?ordner=` bleibt bestehen.
- **Memory-Bau (Bau-KI, ME-1.1):** Übersichts-Endpoint + Ober-Register-UI (Ebene ①/②) + V19-kanon-Pfad.
  Die `parent_id`-Hierarchie + Notiz-Vererbung existieren bereits — ME-1 ist Navigations-/Vertragsbau,
  kein Datenmodell-Umbau.

## 7 · Migrations-Strategie (die 4 Konsumenten; fail-closed, backup-first)

**Phasenmodell** (`MIG_PHASEN`), je App unabhängig, jede Phase: frisches Backup (`ops/backup_apps.py`)
→ Schritt → Wächter-Report → Doku-Sync. Live-Neustarts wie immer gegated.

| Phase | Schritt | Schutz |
|---|---|---|
| **P0 Bestand** | Wächter-Baseline-Report über V17/18/19 (read-only, sofort möglich) | verändert nichts |
| **P1 Spalte** (MIG-KANON-1) | `migriere_kanon_id` an money/management/memory-`bereiche` | additiv, idempotent, `''`-Default ⇒ Verhalten unverändert |
| **P2 Backfill** (MIG-KANON-2) | `backfill_vorschlaege`: Admin-Slot ↔ App-kontext/Name **eindeutig** matchbar ⇒ Vorschlag `kanon_id`; Schreiben NUR aus der HITL-Liste (Admin-UI/ops-CLI zeigt Vorschläge, David bestätigt) | nur eindeutige Matches; mehrdeutig/leer ⇒ Report, nie raten |
| **P3 Dual-Read** | Apps adoptieren `aufloesen()` (①→②→③); Cockpit/Relays senden `kanon`+`kontext`; `quelle` sichtbar im Cockpit | leere `kanon_id` ⇒ wertgleich heute; kein Pfad entfällt |
| **P4 Cutover** (MIG-KANON-3, Gate G-BEREICH-CUTOVER ✅) | ID wird führend: Slots werden Anzeige-/Altfeld, Doku sagt „Bindung = kanon_id" | NUR bei Wächter-Report **0 dangling/0 mehrdeutig** auf V17–V19; Fallback-Stufen ②/③ bleiben ≥1 Release als Not-Leiter |

- **V-Kanten-Erhalt:** alle Schritte additiv; `kontext=`-Params, Alt-Fallbacks und `memory_ref`
  funktionieren bis nach P4 unverändert (docs/26-Kanten V2–V15 sind bereichs-unabhängig und
  unberührt; V16 nutzt keine Bereichs-Schlüssel).
- **Lösch-Semantik:** Soft-Delete eines Admin-Bereichs kaskadiert NICHT (App behält `kanon_id`,
  Wächter meldet `verwaist_app` (Reverse-Check), David entscheidet). Fail-closed: nie Auto-Löschen/Auto-Umhängen. P4-Cutover-Gate = 0 `dangling`/0 `mehrdeutig`/0 `verwaist_app`.
- **Reihenfolge-Empfehlung:** Management zuerst (kleinste Suite, klarste Kante), dann Money,
  dann Memory (V19-Anhebung + ME-1 zusammen), Admin-Cockpit-Seite parallel zu P3.

## 8 · Schnitt (was wohin — Begründung)

| Ebene | Inhalt | Warum |
|---|---|---|
| **appkit-kanonisch** (`bereich_register.py`) | ID-/Spaltenvertrag, Auflösekette ①②, Wächter-/Backfill-Logik, Ober-Kategorien + Mapping-Validierung, DDL-Generator, Baum/Roll-up, Phasenmodell | netzweit identische Semantik = Single-Source; pure Logik gehört ins Framework |
| **App-lokal** | `art`-Kataloge (+ Mapping-Deklaration), `kontext_spalten`, FK-Tabellen, `inhalt()`-Overrides (Memory-Vererbung, Management-Post-Status), Alt-Fallback ③, Router | Domänen-Wissen und Nutzer-Sprache je App; appkit kennt keine Domänen-Tabellen |
| **admin-kanonisch** | die `bereich`-Entität selbst (ID-Vergabe!), Typ-Modell/Modul-Freischaltung (docs/49 unverändert), Slots als Alt-Schlüssel, Cockpit + Wächter-Sammel-Report | Admin ist Heimat der Entität; Ober-Kategorie ersetzt das Typ-Modell NICHT — sie liegt darüber |

## 9 · Bau-Plan (Bau-KI; alle Pakete klein & einzeln grün-committbar)

| Paket | Inhalt | Gate | Abhängt von |
|---|---|---|---|
| BER-0 *(erledigt in dieser Runde)* | docs/67 + `bereich_register.py`-Stubs + Vertrags-Tests | — | — |
| BER-1.1 | `migriere_kanon_id` in den 3 Apps verdrahten (Start-Hook) + `aufloesen()`-Adoption Money/Management (③ bleibt) + `kanon=`-Param V17/V18 + Relay-Durchreich + `kanon-status`-Endpoints | **G-BEREICH-ID ✅ · e2e geschlossen 06.07. (F6/F17/F18): Core-Relays reichen `kanon` durch + `kanon-status`-Core-Route + `aufloesen()`-Prod-Adoption Money/Mgmt/Memory (V19 kanon-only) + Reverse-Wächter `verwaist_app`** | BER-0 |
| BER-1.2 | Wächter-Adapter (AnkerIndex je Kante) + Admin `GET /api/bereiche/waechter` + Cockpit-Anzeige `quelle`/Befunde + Backfill-HITL-Liste (P2-UI) | G-BEREICH-ID ✅ | BER-1.1 |
| BER-2.1 | `ober_kategorie` additiv in `_public` aller 4 Apps + Mapping-Asserts | — (gate-frei) | BER-0 |
| BER-2.2 | MIG-ART-1 Money `privat→persoenlich` (+Label-Check) | **G-BEREICH-ENUM ✅** | BER-2.1 |
| BER-3.1 | DDL-Adoption: 4 Apps beziehen `SCHEMA_BEREICHE` aus `schema_bereiche(…)` (Vertrags-Test sichert Wertgleichheit) + Migrations-Konsolidierung | Backup-first | BER-0 |
| ME-1.1 | Memory `uebersicht`-Endpoint + Ober-Register-UI (Ebenen ①/②) + V19-kanon-Pfad | — | BER-1.1 |
| BER-1.3 | Cutover P4 (Slots→Anzeige, Doku-Umschwenk) | **G-BEREICH-CUTOVER ✅** + techn. Wächter 0/0 | alle |

## 10 · Test-Strategie
- **Jetzt (Vertrags-Tests, appkit-Suite):** DDL-Generator ≡ die 4 Bestands-Schemata (golden,
  normalisiert) · Auflösekette (kanon exakt; kontext CI; Präzedenz; Mehrdeutigkeits-Flag;
  ohne Spalte wertgleich; user-Isolation) · `verknuepfen` fail-closed (Eindeutigkeit, fehlende
  Spalte, 404) · `migriere_kanon_id` idempotent (fresh + rerun) · Wächter-Klassifikation
  (ok/alt/dangling/mehrdeutig/ungenutzt) · Backfill nur-eindeutig/dry-run · Ober-Kategorien
  (Vollständigkeit aller 4 Kataloge, fail-closed, Validierung) · Baum (Verschachtelung,
  verwaiste, Zyklen-Fail-safe) · Roll-up-Summen. **Bestand: appkit-Suite bleibt unverändert grün.**
- **Bau-Phase (je Paket):** App-Suite grün + je Kante ein End-to-End-Vertragstest
  (kanon-Param → `quelle="kanon"`) + Wächter-Report-Snapshot vor/nach jeder Migration.

## 11 · Invarianten (prüfbar)
- **I-1** `appkit/bereiche.py` (`BereicheBasis`) bleibt in dieser Runde byte-unverändert; API wertgleich.
- **I-2** Kanonische ID = Admin-`bereiche.id`; Admin trägt selbst keine `kanon_id`; IDs nie recycelt.
- **I-3** `aufloesen(kontext=…)` ohne `kanon_id`-Spalte ≡ heutige kontext-Auflösung (Stufe-0).
- **I-4** Pro `user_id`: eine `kanon_id` ↔ höchstens ein lokaler Bereich; Verstöße fail-closed bzw. Wächter-Befund.
- **I-5** Jede App-`art` mappt auf genau eine Ober-Kategorie; unbekannt ⇒ `sonstiges`; Set nur per Vertrags-Update erweiterbar.
- **I-6** Wächter ist read-only und wirft nie; App offline ⇒ Kante `unbekannt`, kein Fehler.
- **I-7** Migration additiv + idempotent + backup-first; kein Schritt löscht/verschiebt Nutzdaten; Cutover nur bei 0 dangling/0 mehrdeutig.
- **I-8** V16–V19 (docs/26/34) bleiben in jeder Phase funktionsfähig; `kontext=`/`memory_ref` mindestens bis nach P4.
- **I-9** Typ-Modell (Modul-Freischaltung) bleibt admin-kanonisch (docs/49); Ober-Kategorie gated keine Module.
- **I-10** `kanon_id`-Schreiber sind ausschließlich `verknuepfen`/`loesen` (+ bestätigter Backfill); beide auditiert.

## 12 · David-Gates — ✅ ALLE FREIGEGEBEN (04.07.2026)
> David hat am 04.07. alle drei Gates bestätigt: *„wenn für jedes einzelne die klare Empfehlung JA
> vorliegt, sind sie alle freigegeben"* — die empfohlenen Maßnahmen sind die fürs Gesamtvorhaben besten.
> Damit ist der Bau (§9) **nicht mehr Gate-blockiert**; es bleiben nur die technischen Vorbedingungen
> (Backup-first, Wächter-Report). Reihenfolge jetzt rein abhängigkeits-getrieben.

1. **G-BEREICH-ID ✅ FREIGEGEBEN** — Alt-`kontext`-Strings werden per bestätigtem Backfill an die
   kanonische Admin-Bereichs-ID gebunden (`kanon_id`); kontext bleibt als Anzeige/Fallback. ⇒ schaltet
   **BER-1.1 / BER-1.2** (und damit ME-1.1) frei. Wächter überwacht; behebt B-1/B-2, bevor die
   Agenten-Regie (Z4.1/Z4.2) die Schuld erbt.
2. **G-BEREICH-ENUM ✅ FREIGEGEBEN** — Money `privat`→`persoenlich` (MIG-ART-1, idempotent, nur Money;
   Admin-Präzedenz existiert). ⇒ schaltet **BER-2.2** frei. Einziger Alt-Wert, der das netzweite Set stört.
3. **G-BEREICH-CUTOVER ✅ FREIGEGEBEN** — Cutover P4 ist grundsätzlich genehmigt; die **Ausführung**
   bleibt an die technischen Vorbedingungen gebunden (frisches Backup + Wächter-Report **0 dangling /
   0 mehrdeutig**; Fallback-Stufen ②/③ bleiben ≥1 Release als Not-Leiter). Kein Termindruck — P0–P3
   liefern den Wert bereits, P4 folgt sauber danach.

## 13 · Berührte Dateien & Doku-Sync
- **Diese Runde:** `docs/67` (neu) · `packages/appkit/bereich_register.py` (neu) ·
  `packages/appkit/tests/test_bereich_register.py` (neu). Sonst nichts.
- **Bau-Phase (Doku-Sync-Pflichten):** docs/49 §8 (Verweis auf 67; Ober-Kategorie-Ergänzung) ·
  docs/34/26 (kanon-Param an V17–V19 falten) · docs/58 §3.B/§4 (VO-2 → „Vertrag docs/67") ·
  SYSTEMDATENBLATT (Bereichs-Cockpit-Spur) · App-`_workfiles` der 4 Apps · MEMORY-Notizen.
