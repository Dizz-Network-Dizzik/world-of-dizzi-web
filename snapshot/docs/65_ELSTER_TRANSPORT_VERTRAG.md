# 65 · ELSTER-TRANSPORT-VERTRAG — ERiC-Filing für Dizz Money (M-1, Bau-Spec für Bau-KI)

> **Status: VERTRAG (M-1, Architektur-KI 04.07.2026, Worktree `chat/elster-kern`). REINES DESIGN — kein Bau,
> keine ERiC-Lib installiert, keine Übermittlung, kein Zertifikat berührt.** Verträge-als-Code:
> `apps/money/moneyapp/elster/vertrag.py` (Stubs, Docstrings
> normativ) + `apps/money/tests/test_elster_vertrag.py` (61 Tests). Bau = Bau-KI M1-1…M1-8 (§12) NACH den
> Gates §14 **und** den verordneten Vorstufen M-2/M-3/M-7 (VO-5). Zwilling zu docs/64 (M-6): dort kommen
> Kontodaten LESEND rein — hier geht die **Steuererklärung RAUS** ans Finanzamt (Davids D7-Endgame,
> höchste Sorgfaltsklasse des Netzes). Quellen: docs/58 §3.B M-1…M-7 + §3.G3 + §4 VO-5 · docs/64 (Muster) ·
> `moneyapp/{auswertung,trading_steuer}.py` · money `docs/02` · docs/56 (Editionen) · docs/61 §3/§4.

## §0 · Geltung + Nicht-Ziele

**Ziel:** Die in Money vorhandene Steuer-Datenlage (EÜR-Auswertung heute, UStVA nach M-4) **direkt,
authentifiziert und quittiert** ans Finanzamt übermitteln — über **ERiC** (ELSTER-Rich-Client, die
kostenlose native C-Bibliothek der Finanzverwaltung), gekapselt hinter einer Adapter-Grenze. „Nichts
vergessen, nichts falsch machen" heißt architektonisch: **ohne grünes Ergebnis der
M-2-Plausibilisierungs-Engine wird NIE gesendet** (I-1) — der Transport ist der Bote, nie der Prüfer.

**Nicht-Ziele (für immer bzw. bis eigenes Gate):** KEINE Steuer-BERATUNG (Money bleibt Schätz-/
Erfassungstool, Disclaimer-Pflicht bleibt) · kein Filing aus der Cloud (§9) · kein Auto-/Batch-Send
(jede Übermittlung = einzelner bewusster Nutzer-Akt) · keine ESt/KAP/SO-Formulare in v1 (spätere
Vertragserweiterung — `trading_steuer.py` liefert zwar die Datenlage, aber EÜR/UStVA gehen vor, §6) ·
kein Eingriff in appkit (§11) · M-2/M-3/M-7 werden hier NICHT mitentworfen (eigene Bau-KI-Pakete; dieser
Vertrag fixiert nur ihre **Schnittstellen**: `PlausiFreigabe`, Festschreib-Naht).

## §1 · Härtungs-Invarianten (nummeriert; Enforcement-Ort verbindlich)

| # | Invariante | Enforcement |
|---|---|---|
| I-1 | **Fail-closed-Gate:** kein Senden ohne grüne, **hash-gebundene** `PlausiFreigabe` der M-2-Engine (einziger legitimer Produzent). Frische = Datenstand-Bindung, nicht Uhrzeit: ändert sich die Quelle nach der Prüfung, ist die Freigabe stale ⇒ `GateRot` | `pruefe_gate` + `pruefe_sende_freigabe` + Tests heute |
| I-2 | **Geheimnisse nur im Vault:** Zertifikats-PIN unter `elster_pin_<zugang_id>` in `appkit.vault.Vault`; `ElsterZugang` trägt nur Schlüssel-NAME + Datei-REF aufs .pfx; PIN nie in DB/Logs/argv/env; `repr` maskiert Steuernummer; **`ElsterDatensatz.__repr__` zeigt NIE das XML** (der Datensatz IST die Steuererklärung) | Vertrags-Tests heute (Feld-Fläche, repr-Marker); M1-8 caplog |
| I-3 | **Zwei-Schlüssel + Hersteller-ID:** Senden nur mit `Scharfschaltung` (angelegt UND bestätigt) UND konfigurierter ERiC-Hersteller-ID (Settings, NIE hartkodiert — G-M1-ERIC) | `pruefe_scharf`/`pruefe_hersteller_id` VOR NotImplementedError (Tests heute) |
| I-4 | **Nie stiller Erfolg, nie stilles Scheitern:** `FilingErgebnis` konstruktiv — Erfolg ⇔ Transferticket; FEHLGESCHLAGEN verträgt kein Ticket + verlangt ehrlichen Text; offline = harter `VerbindungsFehler`-Abbruch (M-3-Prinzip, nie „0 übertragen") | `FilingErgebnis.__post_init__` (Tests heute) |
| I-5 | **Validate-only VOR jedem Senden:** `SENDET` ist ausschließlich aus `VALIDIERT_OK` erreichbar; umgekehrt braucht `validiere()` KEINE Scharfschaltung (risikofrei + niederschwellig — niemand soll die Validierung meiden) | `UEBERGAENGE` + `pruefe_sende_freigabe` (Tests heute) |
| I-6 | **Keine Doppel-Übermittlung:** Idempotenz-Anker `fall_schluessel` (formular\|jahr\|zeitraum); Korrektur = bewusste `korrektur_nr` NUR über FESTGESCHRIEBEN; `SENDET`-Leichen (Crash) + `SENDUNG_UNKLAR` + `UEBERMITTELT_OFFEN` blockieren JEDEN neuen Lauf bis zur manuellen Klärung; **Senden hat NIE `retry_erlaubt`** | `pruefe_doppel` + Retry-Klassenattribute (Tests heute) |
| I-7 | **Nur lokal:** Filing läuft ausschließlich auf dem Nutzer-Gerät; kein LLM/Cloud-Dienst berührt je Steuerdaten; E-SERVER: Modul deaktiviert (§9) | Architektur (kein KI-/Cloud-Aufruf im Modul); docs/56 §4-Regel |
| I-8 | **Prozess-Isolation:** die native ERiC-C-Lib läuft NUR in einem eigenen **Worker-Subprozess** — ein nativer Crash (Segfault) darf :8210 nie töten; PIN via stdin-Pipe in den Worker (argv/env sind prozesslistensichtbar) | M1-3-Akzeptanzkriterium; heute Spec-Pflicht + Docstring |
| I-9 | **Retry-Politik als Code:** `retry_erlaubt` je Fehlerklasse, Basis-Default **False**; einzig `VerbindungsFehler` (ERiC meldete sauber „nichts raus") ist wiederholbar | Klassenattribute + Test heute |

## §2 · ERiC-Wissen (das Minimum, das Bau-KI zum Bauen braucht — docs/58 §3.G3)

- **Was ERiC ist:** kostenlose native C-Bibliothek der Finanzverwaltung (Win/Linux/macOS), DER offizielle
  Software-Weg zu ELSTER (~200 Softwarepartner). Kern-Arbeitsmodus: ein **Vorgang** bekommt Nutzdaten-XML
  + Bearbeitungs-Flags — **validieren-only und senden sind Flags desselben Aufrufs** (deshalb ist
  validate-only architektonisch „gratis" und I-5 billig durchsetzbar). Rückgabe: Statuscode + Antwort-/
  Protokoll-Puffer (Quittung inkl. **Transferticket**). ⚠️ Die konkreten Symbolnamen/Signaturen/Flags
  werden in M1-3 **aus dem echten `ericapi.h` der heruntergeladenen Lib** gebunden — hier bewusst nicht
  „aus dem Gedächtnis" verzeichnet (Scheingenauigkeit).
- **Registrierungs-Uhr (DIE David-Latenz, Zwilling der DK-Produktkennung):** BayLfSt-Entwicklerbereich,
  5 Schritte, kostenlos; die **produktive Hersteller-ID gibt es erst NACH erfolgreicher Test-Übermittlung**
  ⇒ Wochen-Vorlauf, früh starten (G-M1-ERIC). Entwicklung/Tests laufen gegen die **ELSTER-Testumgebung**
  mit öffentlichen **Test-Zertifikaten** (nie Davids echtes Zertifikat in Tests/CI).
- **Authentifizierung:** ELSTER-Software-Zertifikat (.pfx-Datei, PIN-verschlüsselt). Typen: persönlich vs.
  Organisation (G-M1-ZERTIFIKAT). Die Datei liegt unter `data\apps\money\elster\` (Nutzer-Import via UI),
  nie im Repo; die PIN nur im Vault (I-2).
- **Versions-Realität (der wahre Betriebs-Kostenfaktor):** Formular-Schemata + ERiC-Lib wechseln
  **jährlich**; deshalb trägt jeder `ElsterDatensatz` seine `formular_version` explizit (Pflichtfeld) und
  jeder `DatensatzBauer` deklariert seine Version — eine veraltete Version fällt im ERiC-Validate laut,
  nie still. Jahres-Pflege = wiederkehrender Wartungs-Slot (§12 M1-4/M1-7-Akzeptanz).
- **Fehlercodes:** ERiC liefert numerische Rückgabecodes + Server-Antworten. Die **konkrete
  Code→Klasse-Tabelle wird in M1-3/M1-8 aus echten Headern/Antworten gefüllt** (nicht raten);
  die Zuordnungs-REGEL steht in §5 fest.

## §3 · Datenmodell + Gate (normativ: `elster/vertrag.py`)

| Typ | Zweck | Kern-Invarianten |
|---|---|---|
| `ElsterZugang` | Zugangs-Konfiguration | frozen; Feld-Fläche EINGEFROREN (Test); nur `zertifikat_pfad`-REF + `pin_vault_key`-NAME, nie Inhalte; repr maskiert Steuernummer |
| `Scharfschaltung` | Zwei-Schlüssel-Zustand | `ist_scharf` ⇔ angelegt UND bestätigt; `pruefe_scharf` ⇒ `NichtScharf` (bewusste Duplikat-Instanz des M-6-Musters, §11) |
| `SteuerFall` | WAS eingereicht wird | formular+jahr+zeitraum+korrektur_nr; UStVA verlangt Zeitraum, EÜR verbietet ihn; `fall_schluessel` OHNE korrektur_nr = Idempotenz-Anker (I-6) |
| `ElsterDatensatz` | versandfertiges Nutzdaten-XML | xml+`quell_stand_hash`+`formular_version` alle Pflicht; repr zeigt NIE xml (I-2) |
| `PlausiFreigabe` | **das M-2-Gate-Token** (I-1) | hash-gebunden an den geprüften Quell-Datenstand; einziger Produzent = M-2-Engine (Bau-KI); `pruefe_gate` prüft grün+Fall+Hash |
| `ValidierungsErgebnis` | ERiC-validate-Ausgang | konstruktiv ehrlich: grün ⇔ keine Fehlerliste, rot ⇒ ≥1 Fehler (nie stilles Rot) |
| `Quittung` | Server-Annahme-Nachweis | Transferticket Pflicht; `protokoll_roh` = unangetastetes Übertragungsprotokoll (GoBD-Archiv); repr ohne roh |
| `FilingErgebnis` | Endzustand eines Laufs | nur Terminal; Erfolg ⇔ Ticket; Sonder-Terminale verlangen ehrliche Texte (§4) |
| `DatensatzBauer` (Protocol) | DER Serialisierungs-Vertrag | `baue(fall, quelldaten) → ElsterDatensatz`; Impl.: `EuerBauer` (M1-4) · `UstvaBauer` (M1-7) |
| `EricTransport` | DIE Adapter-Grenze | Stufe 0: `sende` wirft Wächter VOR NotImplementedError; `validiere` frei; `pin_holen`-Vault-Naht |

**`berechne_quell_stand`** (sha256 über die kanonische Quelldaten-Serialisierung) ist der Kitt zwischen
M-2 und M-1: die Freigabe bindet an GENAU den geprüften Datenstand; der Datensatz trägt denselben Hash —
ändert sich ein Cent, passt nichts mehr zusammen. Die kanonische Serialisierung definiert M-2 (ein
Produzent, ein Format); M1-4 übernimmt sie.

**Persistenz (M1-1, Money-DB via `_migriere`-Hausmuster, alle mit `user_id`+`deleted_at`):**
`elster_zugaenge` (Felder = `ElsterZugang` + Scharf-Zeitstempel) · `filing_laeufe` (fall_schluessel,
zustand, korrektur_nr, fehler, fehler_art, zeitstempel — **der `pruefe_doppel`-Speicher**; ein Lauf wird
VOR dem Übergang nach SENDET persistiert, damit ein Crash eine sichtbare `SENDET`-Leiche hinterlässt,
nie ein stilles Nichts) · `filing_quittungen` (transferticket, uebermittelt_am, protokoll_roh,
datensatz_xml — das GoBD-Archiv der tatsächlich gesendeten Erklärung). *Ehrliche DSGVO-Notiz:*
`deleted_at`-Kaskade (purge_user) löscht auch das Quittungs-Archiv — die Aufbewahrungspflicht liegt beim
Steuerpflichtigen, nicht bei der Software; die UI warnt beim Purge explizit (M1-6).

## §4 · Zustandsmaschine (normativ: `UEBERGAENGE`, vollständig getestet)

```
BEREIT → BAUT_DATENSATZ → VALIDIERT → VALIDIERT_OK ══[pruefe_sende_freigabe]══> SENDET
                                                                                   ├→ QUITTUNG_ERHALTEN → FESTGESCHRIEBEN ✓
   (bis VALIDIERT_OK: jeder Zustand → FEHLGESCHLAGEN | ABGEBROCHEN [Nutzer])       ├→ FEHLGESCHLAGEN  (ERiC: sauber „nichts raus")
                                                                                   └→ SENDUNG_UNKLAR  (Ausgang unbekannt!)
                                                          QUITTUNG_ERHALTEN ────────→ UEBERMITTELT_OFFEN (Festschreibung scheiterte)
```

**5 Terminale** (Filing braucht mehr Terminal-Ehrlichkeit als Lesen — docs/64 hat 3):
`FESTGESCHRIEBEN` (Erfolg: Quittung da + M-7-Einfrierung vollzogen) · `FEHLGESCHLAGEN` (sauber
gescheitert, nichts übermittelt) · `ABGEBROCHEN` (Nutzer, **nur VOR Sendebeginn** — ab SENDET gibt es
kein Abbrechen mehr, der Ausgang wäre unklar) · **`SENDUNG_UNKLAR`** (Crash/Timeout nach Sendebeginn ohne
saubere ERiC-Antwort ⇒ blockiert den Fall-Schlüssel, manuelle Transferticket-Klärung, NIE Auto-Retry) ·
**`UEBERMITTELT_OFFEN`** (Quittung liegt vor, lokale Festschreibung scheiterte ⇒ Übermittlung zählt,
Nacharbeit lokal, Senden wird NIEMALS wiederholt). Regeln: Terminale absorbierend · `SENDET` NUR aus
`VALIDIERT_OK` (I-5) · `QUITTUNG_ERHALTEN` kennt kein FEHLGESCHLAGEN (die Übermittlung IST passiert) ·
Motor fährt Übergänge NUR über `pruefe_uebergang` (`ZustandsFehler` sichtbar, nie interpretieren).

**Der bewachte Übergang:** `VALIDIERT_OK → SENDET` führt durch **`pruefe_sende_freigabe`** — das
Vorbedingungs-Bündel in fester Prüf-Reihenfolge: Hersteller-ID (I-3) → Zwei-Schlüssel (I-3) →
Doppel-Schutz (I-6) → ERiC-Validate grün (I-5) → M-2-Gate frisch+grün (I-1). Nichts davon ist
überstimmbar; jede Verletzung wirft ihre Klasse.

## §5 · Fehler-Taxonomie + Retry-Politik (normativ: Klassen in `vertrag.py`)

| Klasse | Wann | `retry_erlaubt` | Nutzer-Text-Geist |
|---|---|---|---|
| `KonfigFehler` | Zugang/Fall/Datensatz strukturell ungültig | False | „Konfiguration unvollständig — bitte prüfen" |
| `NichtScharf` | Zwei-Schlüssel/Hersteller-ID fehlt | False | „Transport ist nicht scharfgeschaltet" |
| `GateRot` | M-2-Freigabe fehlt/rot/stale/fremd | False | „Plausibilisierung nicht grün — erst prüfen, dann senden" |
| `DoppelFilingFehler` | Fall-Schlüssel blockiert (I-6) | False | „Für diesen Zeitraum existiert bereits eine Übermittlung/ein ungeklärter Lauf" |
| `ValidierungsFehler` | ERiC-Validate rot / kein Validate-Lauf | False | „ELSTER-Prüfung meldet Fehler — Daten korrigieren" |
| `ZertifikatFehler` | Zertifikat fehlt/abgelaufen/PIN abgewiesen | **False — NIE** (Lockout-Gefahr; Text NIE mit PIN) | „Zertifikat/PIN-Problem — im Vault bzw. bei ELSTER prüfen" |
| `VerbindungsFehler` | offline/DNS/TLS/Timeout, ERiC sauber „nichts raus" | **True** (einzige) | „ELSTER-Server nicht erreichbar — später erneut" |
| `SendeUnklarFehler` | keine saubere Antwort NACH Sendebeginn | **False — NIE** | „Ausgang unklar — NICHT erneut senden; Transferticket manuell prüfen" |
| `UebermittlungAbgelehnt` | Server weist Einreichung fachlich ab | False | „Finanzamt-Server hat abgelehnt: <Grund> — korrigieren + neu einreichen" |
| `FestschreibFehler` | Festschreibung nach Quittung scheitert | False | „Übermittelt ✓, lokale Festschreibung offen — Nacharbeit nötig" |
| `ZustandsFehler` | illegaler Motor-Übergang | False | (Programmierfehler — sichtbar machen) |

**Zuordnungs-REGEL für ERiC-Codes (M1-3/M1-8 füllt die Tabelle aus echten Headern/Antworten):**
Zertifikats-/Security-Gruppe ⇒ `ZertifikatFehler` · Plausi-/Schema-Gruppe ⇒ `ValidierungsFehler` ·
Transport-Gruppe-vor-Sendung ⇒ `VerbindungsFehler` · Server-Rückweisung ⇒ `UebermittlungAbgelehnt` ·
**alles Unbekannte und alles nach Sendebeginn ohne saubere Antwort ⇒ `SendeUnklarFehler`** (fail-closed
in Richtung „lieber blockieren als doppelt senden"). Konkrete Codes hier hinzuschreiben wäre
Scheingenauigkeit — bewusst weggelassen.

## §6 · Serialisierung: Formulare, Bauer, Versions-Pflege

- **Reihenfolge: EÜR zuerst, UStVA zweite** — ★ bewusster Flip der docs/58-§3.G3-Reihenfolge
  (dort UStVA→EÜR), Begründung: (a) die EÜR-**Datenlage existiert heute** (`auswertung.eur_jahr`:
  je-Kategorie-Überschuss + steuer_relevant/steuer_art), UStVA braucht erst die M-4-USt-Datenschicht
  (Vorsteuer/§19); (b) bei §19-Kleinunternehmer-Status ist die UStVA u. U. gar nicht fällig. Der Flip
  liegt als **G-M1-FORMULARE** bei David (inkl. §19-Status-Frage) — antwortet er „UStVA zuerst", tauschen
  M1-4/M1-7 die Plätze, der Vertrag bleibt identisch (docs/58-Sync nach Antwort, Handover).
- **`DatensatzBauer`-Vertrag:** `baue(fall, quelldaten) → ElsterDatensatz`. Quelldaten-Beschaffung
  (eur_jahr-Aufruf, M-3-gekoppelte Admin-Abgleiche) gehört dem Motor/M-2, NICHT dem Bauer (ein Bauer
  serialisiert nur). Kennziffern-/Feld-Mappings der Anlage EÜR = **M1-4 am echten Schema** — kein
  Mapping-Raten im Vertrag.
- **Envelope:** TransferHeader/NutzdatenHeader (Hersteller-ID, Test-Marker, Zertifikats-Bezug) baut der
  **Transport** in M1-3/M1-5 — der Bauer liefert reine Nutzdaten. Trennung = ein Bauer bleibt
  transport-agnostisch testbar (Golden-XML-Fixtures ohne Zertifikat).
- **Versions-Pflege als Design-Eigenschaft:** `formular_version` ist Pflichtfeld an Datensatz UND Bauer;
  M1-4/M1-7-Akzeptanz enthält je eine **Jahres-Versions-Tabelle** (jahr→Schema/ERiC-Version) + der
  jährliche Pflege-Slot wandert in den Betriebs-Plan (docs/58 §3.G3: DER wahre Kostenfaktor).

## §7 · Ablauf eines Laufs (Motor-Vertrag, M1-5)

1. **BAUT_DATENSATZ:** Motor holt Quelldaten (nach M-3-Regel: Admin-Kopplung offline ⇒ harter Abbruch,
   nie still 0), berechnet `quell_stand_hash`, ruft den `DatensatzBauer`.
2. **VALIDIERT:** `EricTransport.validiere` (Worker-Subprozess, I-8) — Fehler ⇒ ehrliches
   `ValidierungsErgebnis`, UI zeigt ERiC-Fehlerliste; grün ⇒ `VALIDIERT_OK`.
3. **Gate-Moment:** UI zeigt M-2-Befund + Validate-Ergebnis; der Nutzer löst „Jetzt übermitteln" aus
   (bewusster Akt, §8). Motor persistiert den Lauf, DANN `pruefe_sende_freigabe`, DANN `SENDET`.
4. **SENDET:** ein einziger ERiC-Sende-Vorgang. Saubere Annahme ⇒ `Quittung` (Transferticket +
   Roh-Protokoll ins Archiv). Saubere Ablehnung ⇒ `UebermittlungAbgelehnt` ⇒ FEHLGESCHLAGEN. Alles
   andere ⇒ `SENDUNG_UNKLAR` (blockiert, manuell klären).
5. **QUITTUNG_ERHALTEN → FESTGESCHRIEBEN:** Motor ruft die **M-7-Festschreib-Naht**
   (`festschreiben(fall, quell_stand_hash, quittung)` — Injection wie `pin_holen`; M-7 friert den
   Datenstand GoBD-analog ein). Scheitert sie ⇒ `UEBERMITTELT_OFFEN` + `FestschreibFehler`-Nacharbeit.
6. Jeder Terminal-Zustand materialisiert als `FilingErgebnis` (konstruktiv ehrlich, I-4) in
   `filing_laeufe` — P8-Geist: der Verlauf ist dem Nutzer sichtbar (M1-6-Karte).

## §8 · Zwei-Schlüssel + HITL (T5-/M-6-Analogie, dreifach gestaffelt)

- **Schlüssel 1 — Anlegen:** Zertifikat importieren (Datei → `data\apps\money\elster\`), PIN → Vault,
  Steuernummer erfassen. Zugang ist KONFIGURIERT, aber tot (`bestaetigt_am` leer ⇒ `NichtScharf`).
- **Schlüssel 2 — Scharfschalten:** getrennter bewusster Akt; Zielzustand `require_level("hochsicher")`
  (K1-Step-up), Übergangs-Weg pre-K1 = lokales ops-Skript/Settings-Flip (exakt docs/64 §8; Senken ist
  immer ein Klick). Zusätzlich wirkt die **Hersteller-ID als dritter, externer Schlüssel** (ohne
  BayLfSt-Registrierung existiert kein scharfer Transport — I-3).
- **HITL im Betrieb:** JEDE Übermittlung = einzelner Nutzer-Klick nach sichtbarem M-2-Befund +
  Validate-Ergebnis (kein Scheduler-Hook existiert). Falls je agentisch angestoßen: Steuer-Filing ist
  `geld`-Klasse ⇒ **immer `pre_approval`** (docs/63 §4 `KLASSEN_BODEN`) — Vorschläge laufen durch die
  K4-Inbox, gesendet wird erst nach menschlicher Freigabe + allen I-Wächtern.

## §9 · Editionen (docs/56) — ELSTER-Daten sind höchst-sensibel

| Edition | Filing-Pfad | Begründung |
|---|---|---|
| **E-LOKAL** | **ERiC direkt auf dem Nutzer-Gerät** (voller Pfad) | Zertifikat+PIN+Steuerdaten bleiben lokal; klassisches Steuersoftware-Modell (WISO/Lexware-Analogie) |
| **E-HYBRID** | ERiC **lokal** (wie E-LOKAL); Server-Teile des Netzes sehen NIE Steuerdaten | docs/56 §4: sensible Daten ⇒ konservativste Wahl; Filing ist nie ein Server-Feature |
| **E-SERVER** | **Modul DEAKTIVIERT** — nur Export-Fallback | Zertifikat+PIN auf unserem Server = inakzeptable Verwahrung fremder Steuer-Identitäten; falls je gewünscht: eigenes Gate + eigene Rechts-/Haftungsprüfung, nicht dieses Paket |

**Stufen-Fallback (immer verfügbar, VO-5):** (1) **ELSTER-Portal-Weg** — heute schon: `eur_jahr`-
Auswertung + JSON/CSV-Export zum manuellen Übertragen ins Portal (der Stufe-0-Beweispfad, analog
Datei-Import in M-6); (2) **DATEV-Zwischenformat-Export** (eigener späterer Baustein, wenn ein
Steuerberater-Workflow gewünscht wird — bewusst nicht in v1); (3) ERiC-Direktversand (dieses Paket).
Der Fallback bleibt auch NACH M1-Vollausbau vollwertig erhalten (Banken-ohne-FinTS-Analogie).

## §10 · Bibliotheks-Bewertung: ERiC — gesetzt, mit 2 offenen Rechtsfragen

- **Warum ERiC (ohne Alternative):** der einzige offizielle, kostenlose Programmier-Weg zu ELSTER;
  Eigenbau des Protokolls ist nicht vorgesehen/zugelassen; Screen-Scraping des Portals verbietet sich
  (fragil, AGB). Kein Lizenz-KAUF nötig (docs/58 G1-Kontext: hier hebt keine gekaufte Komponente etwas).
- **Native C-Lib ⇒ Konsequenzen im Design:** ctypes-FFI (M1-3) · Worker-Subprozess (I-8, Crash-Schott) ·
  Plattform-/Bitness-Passung (unsere venv = Win x64) · Lib-Ablage unter `data\apps\money\elster\eric\`
  (Runtime-Artefakt, NIE im Repo — .gitignore-Pflicht in M1-3).
- **⚠️ Offene Rechtsfragen (Gates, ehrlich):** (1) **Redistribution:** dürfen die ERiC-Binaries der App
  beigelegt werden (Kauf-Edition!), oder lädt sie der Nutzer/Installer nach Registrierung selbst? Die
  Nutzungsbedingungen des BayLfSt-Entwicklerbereichs sind erst NACH Registrierung einsehbar ⇒ Teil von
  **G-M1-LIZENZ** — bis zur Antwort plant M1-3 den **Download-on-first-use-Pfad** (funktioniert in jedem
  Fall). (2) Herstellerpflichten (Impressum/Support-Kontakt in der Registrierung) = Davids
  Registrierungs-Formular (G-M1-ERIC).

## §11 · Schnitt: appkit vs. moneyapp — Entscheid **Money-lokal** (wie M-6)

- **Einziger Konsument:** nur Money spricht ELSTER; Steuer-Semantik (Formulare, Transferticket,
  Festschreibung) ist Money-Domäne — appkit-Hebung wäre spekulative Generalisierung.
- **Das Generische wird GENUTZT statt dupliziert:** Secrets = `vault.Vault`+`secrets_os` · Settings =
  Hersteller-ID-Naht · Sichtbarkeit = `connectors.TokenConnector` (`ElsterKonnektor`, `richtung="senden"`,
  `sensitivity="hoch"`, M1-2) · atomare Writes = `io_safe` (via Vault).
- **★ Hebe-Beobachtung (ehrlich, Single-Source-Radar):** das **Zwei-Schlüssel-`Scharfschaltung`-Muster
  existiert jetzt ZWEIMAL** (`banksync/vertrag.py` + `elster/vertrag.py` — bewusste Duplikat-Instanz,
  je ~12 Zeilen). Hebe-Kriterium: bei der **dritten** Instanz (Kandidat: Comm-Live-Send, Healthy-Terra,
  M-7 „Bank-Aktiv") wird das Muster nach `appkit/scharf.py` gehoben und beide Instanzen migrieren
  (bereiche→packages-Defork-Muster). Bis dahin: kein Vor-Bau. Die FILING-Zustandsmaschine ist dagegen
  fachspezifisch (5 Terminale, Sende-Semantik) — kein Hebe-Kandidat.

## §12 · Bau-Plan für Bau-KI (commit-groß; jede Stufe: Money-Suite grün; Reihenfolge beachtet VO-5)

| Schritt | Inhalt | Vorbedingung | Akzeptanz |
|---|---|---|---|
| **M1-0 ✅** | dieses Paket: Vertrag + Stubs + 61 Vertrags-Tests | — | Suite 360 grün; 0 Bestands-Datei verändert |
| **M1-1** | Persistenz + CRUD: Tabellen §3 (`_migriere`), `GET/POST/DELETE /api/elster/zugaenge` + Lauf-Historie read-only; Settings-Slot Hersteller-ID | keine (gate-frei) | Responses NIE mit PIN/Vault-Werten/XML (Test); DSGVO-Kaskade + Purge-Warnung |
| **M1-2** | Vault + Zertifikat + Konnektor: PIN→`vault.put` (ohne Echo), .pfx-Import in die Daten-Wurzel, `ElsterKonnektor(TokenConnector)`, Scharfschalt-Akt (Übergangs-Weg §8) | M1-1 | Konnektor „verbunden" erst mit Zertifikat+PIN; `pruefe_scharf` end-to-end; kein Geheimnis in Logs/Responses |
| **M1-3** | ERiC-Runtime: Download/Ablage (`data\…\eric\`, .gitignore), **eric_worker-Subprozess** (I-8, PIN via stdin), ctypes-Bindung am ECHTEN `ericapi.h`, Versions-Check, **validate-only e2e** gegen Testumgebung mit Test-Zertifikat; Code→Klasse-Tabelle begonnen | **G-M1-ERIC + G-M1-LIZENZ** | Validate eines Golden-Datensatzes liefert deterministisches `ValidierungsErgebnis`; Worker-Crash tötet :8210 nicht (Test); keine Lib im Repo |
| **M1-4** | EÜR-Bauer: `eur_jahr`(+M-3-gekoppelte Quellen) → Anlage-EÜR-Kennziffern der realen `formular_version`; kanonische Quelldaten-Serialisierung gemeinsam mit M-2 | **M-2 + M-3 + M-7 gebaut** (VO-5!) + G-M1-FORMULARE | Golden-XML-Fixtures (kein Zertifikat nötig); Jahres-Versions-Tabelle; Validate grün gegen Testumgebung |
| **M1-5** | Sende-Motor: Zustandsmaschine via `pruefe_uebergang`, Lauf-Persistenz VOR Sendung, `pruefe_sende_freigabe` am Übergang, Quittungs-Archiv, M-7-Festschreib-Naht, `SENDUNG_UNKLAR`-Recovery-UX | M1-3 + M1-4 | Motor-Tests: Crash-Leiche blockiert (I-6); Doppel-Lauf ⇒ `DoppelFilingFehler`; offline ⇒ ehrliches FEHLGESCHLAGEN; **Test-Übermittlung an ELSTER-Testumgebung** (= zugleich der Hersteller-ID-Registrierungs-Schritt!) |
| **M1-6** | UI (+U): Filing-Karte (Gate-Ampel = M-2-Befund + Validate-Liste + Verlauf), Sende-Dialog mit expliziter Bestätigung, Quittungs-/Transferticket-Ansicht, Purge-Warnung; CSP-strikt (`data-dz-act`), K2.2-Token | M1-5 | isoliert am Scratch-Port, 0 Konsolenfehler; kein XML/PIN im DOM außer bewusster Quittungs-Ansicht |
| **M1-7** | UStVA-Bauer (zweite Form) | **M-4-Datenschicht** + G-M1-FORMULARE | wie M1-4 (Golden-Fixtures, Versions-Tabelle, Zeitraum-Logik monatlich/quartalsweise) |
| **M1-8** | Härtung: Log-Redaktions-Filter + caplog-Beweis („PIN/XML nie in Logs"), Code→Klasse-Tabelle aus echten Antworten vervollständigen, Fehlerpfade je Klasse | M1-3+ | caplog-Tests; jede §5-Klasse mit realem Auslöser belegt |

**Erste ECHTE Übermittlung (Produktiv-Umgebung, Davids Erklärung) = manueller, gegateter Nutzer-Akt am
Rechner** — nie CI, nie Chat; erst nach M-2-grün + Hersteller-ID produktiv + Davids ausdrücklichem Go.
M1-1→M1-2 sind sofort zündbar (gate-frei, kein Neustart-Zwang — :8210 bleibt unberührt, static
disk-served). ⚠️ M1-4 hängt an den Bau-KI-Vorstufen M-2/M-3/M-7 — **VO-5-Reihenfolge ist verbindlich.**

## §13 · Test-Strategie

- **Heute (dieses Paket):** 61 Vertrags-Tests in `test_elster_vertrag.py` (Money-Suite **360** grün =
  299 Bestand + 61) — Zustandsmaschine vollständig (5 Terminale absorbierend, SENDET nur aus
  VALIDIERT_OK, kein Abbruch ab Sendebeginn, Quittung nie FEHLGESCHLAGEN), Retry-Politik, Geheimnis-
  Freiheit (Feld-Flächen, repr-Marker für Steuernummer/XML/Protokoll), hash-gebundenes Gate (4
  Rot-Fälle), Doppel-Schutz (Korrektur-Semantik, Crash-Leichen), Sende-Vorbedingungs-Bündel (7
  Verletzungs-Klassen), Wächter-vor-NotImplementedError. Lib-/Netz-/DB-frei.
- **Bau:** je M-Schritt eigene Tests (§12); ERiC-Verkehr in Tests ausschließlich gegen die
  **Testumgebung mit Test-Zertifikaten** (nie Davids Zertifikat, nie Produktiv-Server in CI); Golden-
  XML-Fixtures für Bauer; Property-Tests für `fall_schluessel`/`pruefe_doppel`-Idempotenz.
- **Kommando** (Worktree-bewusst): `PYTHONPATH=<repo>\packages` +
  `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q` in `apps\money`.

## §14 · Gates an David (offen formuliert; FP-5e/M-6-Stil)

- **G-M1-ERIC · ERiC-Registrierung/Hersteller-ID JETZT starten (DIE Uhr, Wochen-Latenz):** kostenlose
  Registrierung im ELSTER-Entwicklerbereich (BayLfSt prüft; 5 Schritte; die **produktive Hersteller-ID
  gibt es erst nach erfolgreicher Test-Übermittlung**, die wir in M1-5 liefern). Konkrete David-Aufgabe:
  Entwickler-Konto beantragen (elster.de → Entwicklerbereich; Impressum-/Kontaktdaten bereithalten);
  der Admin-Chat kann das Formular vorbereiten. **Ohne G-M1-ERIC bleibt M1-3+ stehen** — der Rest
  (M1-1/M1-2) ist gate-frei. *(Parallel-Analogie: DK-Produktkennung bei M-6.)*
- **G-M1-LIZENZ · ERiC-Nutzungsbedingungen/Redistribution:** dürfen die ERiC-Binaries mit der App
  ausgeliefert werden (Kauf-Edition/Installer, docs/56), oder gilt Download-on-first-use je Nutzer?
  Antwort steht in den Entwicklerbereichs-Bedingungen (erst nach G-M1-ERIC einsehbar) ⇒ David bringt
  die Terms mit; bis dahin plant M1-3 Download-on-first-use (funktioniert in jedem Fall).
- **G-M1-FORMULARE · Reihenfolge + §19-Status:** Empfehlung des Vertrags: **Anlage EÜR zuerst** (Datenlage
  da; §6-Begründung), UStVA zweite — das flippt bewusst die docs/58-G3-Reihenfolge. Fragen an David:
  (1) Bist du §19-Kleinunternehmer (⇒ UStVA entfällt vorerst)? (2) EÜR-zuerst ok? (3) ESt/KAP/SO-Ambition
  (trading_steuer-Daten) einplanen oder ruhen lassen?
- **G-M1-ZERTIFIKAT · Zertifikatstyp:** existiert schon ein ELSTER-Zertifikat (persönlich? Organisation?)
  — persönlich deckt Einzelunternehmer-EÜR; Organisation wäre der Firmen-Weg (docs/55-Rechtsform-Frage
  strahlt hier rein). Falls keins: Beantragung dauert Tage (Aktivierungs-Brief) ⇒ mit G-M1-ERIC bündeln.

## §15 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

Keine Steuer-BERATUNG/-Optimierung (Money rechnet und überträgt, es empfiehlt keine Gestaltung —
Disclaimer bleibt) · keine ESt/KAP/SO-Formulare in v1 (Erweiterung NACH EÜR/UStVA, eigener
Vertrags-Anhang) · kein Auto-/Batch-/Termin-Send (jede Übermittlung = Nutzer-Akt; falls je agentisch:
`geld`⇒`pre_approval`, §8) · kein Server-Filing (E-SERVER aus, §9) · keine geratenen ERiC-Codes/
Symbolnamen/Kennziffern (M1-3/M1-4 am echten Material) · kein DATEV-Export in v1 (benannter späterer
Baustein, §9) · kein appkit-Umbau (§11, Hebe erst bei dritter Scharfschaltungs-Instanz) · keine
M-2/M-3/M-7-Mitplanung (nur ihre Schnittstellen: `PlausiFreigabe`, M-3-Abbruch-Regel, Festschreib-Naht).

## §16 · Verhältnis zu den Vorstufen (VO-5-Kette, ehrlich verortet)

**M-2 (Plausibilisierung, Bau-KI, ZUERST)** produziert die `PlausiFreigabe` — dieser Vertrag KONSUMIERT
sie nur (I-1); die kanonische Quelldaten-Serialisierung wird dort definiert. **M-3 (harte
Admin-Kopplung)** gilt im Motor-Schritt 1: Quelldaten-Beschaffung offline ⇒ harter Abbruch. **M-7
(Jahres-Festschreibung)** liefert die Festschreib-Naht (§7 Schritt 5) — bis M-7 existiert, kann kein
Lauf FESTGESCHRIEBEN erreichen (und damit auch nicht senden wollen; die Kette hält sich selbst).
**M-4 (USt-Datenschicht)** ist Vorbedingung von M1-7. Damit ist die verordnete Reihenfolge
M-2 → M-3/M-7 → (M-4) → ERiC-Transport **konstruktiv erzwungen**, nicht nur dokumentiert.
