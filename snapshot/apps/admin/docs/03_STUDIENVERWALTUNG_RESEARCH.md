# Dizz Leading — Studienverwaltung (Research & Konzept)

> **Status:** Research/Konzept (19.06.2026, App-Chat/Bau-KI). NOCH NICHT gebaut.
> Persönlicher Nutzer-Wunsch: Leading zum **Gamechanger für Studenten-/Ausbildungs-
> Verwaltung** machen — eigenes Panel/Kategorie „Studien", das ein komplettes Studium
> (Modulplan · ECTS · Prüfungsversuche · Fristen · Prüfungsordnungs-Änderungen) **lückenlos
> verwaltbar** macht, gespeist aus manueller Eingabe **und** vernetzten Dokumenten (Admin/
> Memory) **und** Internet-Recherche. Umsetzung = eigene per-App-Phase MIT Nutzer (s. §8).

## 1. Zielbild (in den Worten des Nutzers, geschärft)
Eine neue Kategorie **„Studien"** in Leading. Beim Anlegen wählt man **Bildungsweg-Art**
(Universität / Fachhochschule / **Ausbildung** / dual / …). Danach gibt man konkret an:
Institution (z. B. *Universität Bayreuth*), Studiengang/Beruf, **Hauptfach**, **Nebenfach**,
Prüfungsordnungs-Jahrgang. Daraus wird — manuell, per Dokument-Upload und per Internet-
Recherche — der **komplette Modulplan** aufgebaut: welche Module Pflicht/Wahlpflicht sind,
wie viele **Leistungspunkte (ECTS)**, welche **Fristen**, wie viele **Prüfungsversuche** noch
offen sind, Stand der **Prüfungsordnung/Verordnung** und deren **Änderungen**. Ziel: nie eine
Frist verpassen, immer den genauen Stand kennen.

**Rollen-Abgrenzung im Netzwerk (warum Leading):**
- **Memory** = Wissens-/Datei-/Projektstruktur (Vault, RAG).
- **Plans** = Projekte/Aufgaben/Termine, Kalender.
- **Admin (Bürokratie)** = Dokumenten-Tresor (PO-/Modulhandbuch-/Zeugnis-PDFs).
- **Leading** = die **bürokratische Geschäftsführung** des Studiums: aggregiert die
  Dokumente (Admin) + Wissen (Memory) + Termine (Plans) zu einer **verbindlichen,
  fortschritts- und fristengetriebenen Studien-Steuerung**. Das ist exakt Leadings
  Aggregator-Rolle, nur auf die persönliche „Studien-GmbH" angewandt.

## 2. Domänen-Recherche (deutsche Hochschul-/Ausbildungs-Bürokratie)
### 2a. Universität / FH (Bologna)
- **Prüfungsordnung (PO)** = hochschulrechtliches, **verbindliches** Dokument. Definiert
  Curriculum, Pflicht-/Wahlpflicht-Module, ECTS-Summe, **Regelstudienzeit**, Fristen
  (z. B. Orientierungsprüfung, Höchststudiendauer), Noten-/Gewichtungsregeln und die
  **Wiederholungsregeln** (Versuche). Hat **Jahrgangs-/Versionsstand**; PO **ändert sich**
  (Änderungssatzungen, „konsolidierte Fassungen").
- **Modulhandbuch / Modulplan (Studienverlaufsplan)** = beschreibt je Modul: Code, Name,
  **ECTS**, Typ (**Pflicht / Wahlpflicht / Wahl**), empfohlenes Fachsemester, **Prüfungsform**
  (Klausur/mündlich/Hausarbeit/Portfolio…), Voraussetzungen, Workload, Verantwortliche.
  ECTS = **gesamter Arbeitsaufwand** (nicht nur Präsenz), Bologna-Standard.
- **Prüfungsversuche** = i. d. R. **3 Versuche je Modulprüfung**; Abschlussarbeit/Praxis-
  semester meist nur **1 Wiederholung**. **Drittversuch nicht bestanden ⇒ „endgültig nicht
  bestanden" ⇒ Exmatrikulation** (existenziell!). Gilt oft **nur für Pflichtmodule** (ein
  Wahlmodul kann ggf. getauscht werden). ⇒ **Versuch-Warner ist das kritischste Feature.**
- **Bayreuth-Spezifika:** Campus-Systeme **CAMPUSonline** (Bewerbung/Einschreibung) +
  **cmlife** (Stundenplan, Kurs-/Prüfungsanmeldung, Prüfungsergebnisse, Zeugnisse,
  Gebührenkonto). In **cmlife** lassen sich **PO + Studienverlaufsplan herunterladen**;
  **Modulhandbücher** liegen auf der jeweiligen Studiengangs-Seite; die **verbindliche** PO
  steht in den **Amtlichen Bekanntmachungen** (inkl. **konsolidierter Fassungen**),
  `amtliche-bekanntmachungen.uni-bayreuth.de`.

### 2b. Ausbildung (dual / BBiG)
- Basis = **Ausbildungsordnung + Ausbildungsrahmenplan + betrieblicher Ausbildungsplan**.
- **Berichtsheft (Ausbildungsnachweis, §43 BBiG)** = **pflicht**, **wöchentlich** geführt,
  **monatlich** gegengezeichnet, **Zulassungsvoraussetzung** zur Abschlussprüfung. Fehlt es,
  droht Nichtzulassung. ⇒ eigenes Berichtsheft-Feature + Frist-/Vollständigkeits-Wächter.
- **Zwischenprüfung + Abschlussprüfung** über die **IHK/Kammer**; Lernfelder/Prüfungs-
  bereiche statt Module; Akteure: Ausbildungsbetrieb + Berufsschule + Kammer.

### 2c. Markt-Lücke
Campus-Systeme (HISinOne, CAMPUSonline) haben Studienplaner mit grafischem Modulplan
(ECTS geplant/erreicht), diverse Stundenplan-/Studienplaner-Apps existieren. Aber: ein
**all-in-one**, das PO + Modulhandbuch **aus Dokumenten extrahiert**, **Prüfungsversuche +
Fristen + PO-Änderungen** trackt und das Ganze **netzwerk-vernetzt** (Dokumente, Wissen,
Kalender) — das ist die Lücke, die Leading füllen kann.

## 3. Datenmodell (Vorschlag, vertragskonform: id/user_id/Timestamps/Soft-Delete)
- **`bildungsweg`** — art (`universitaet|fachhochschule|ausbildung|dual|promotion|sonstiges`),
  institution, abschluss (`bachelor|master|staatsexamen|ausbildungsberuf|…`), studiengang/beruf,
  hauptfach, nebenfach (mehrere ⇒ eigene Zeilen oder JSON), **matrikelnummer (sensibel)**,
  start_semester, regelstudienzeit_semester, po_version, status (`laufend|abgeschlossen|
  abgebrochen|pausiert`); Ausbildung: kammer, ausbildungsbetrieb, berufsschule.
- **`pruefungsordnung`** — bildungsweg_id, version/jahr, quelle_url, max_versuche_default (3),
  thesis_versuche (1), ects_gesamt, regelstudienzeit, orientierungspruefung_frist,
  hoechststudiendauer, **dokument_ref** (Admin-Beleg-ID), stand_geprueft_am, **change_hash**
  (Änderungs-Erkennung).
- **`modul`** (Katalog aus Modulhandbuch) — bildungsweg_id, code, name, typ (`pflicht|
  wahlpflicht|wahl`), bereich (`hauptfach|nebenfach|schluesselqual|thesis`), ects,
  empf_semester, pruefungsform, max_versuche (override), voraussetzungen (JSON Modul-Codes),
  verantwortlich, beschreibung.
- **`modul_status`** (Fortschritt je Nutzer) — modul_id, status (`offen|geplant|angemeldet|
  bestanden|nicht_bestanden|endgueltig_nicht_bestanden|anerkannt`), **versuch_nr**, note,
  ects_erreicht, datum, semester.
- **`berichtsheft_eintrag`** (Ausbildung) — bildungsweg_id, datum_von/bis (Woche),
  taetigkeiten, stunden, status (`entwurf|eingetragen|gegengezeichnet`), unterschrift_datum.
- **Fristen** = Leadings **bestehende `fristen`-Tabelle** wiederverwenden (neue Kategorie
  `studium` + optionaler Bezug auf bildungsweg/modul) ⇒ der **Frist-Wächter** greift sofort.
- **Dokumente NICHT in Leading speichern** — Admin besitzt den Tresor; Leading hält nur
  `dokument_ref = {ziel, beleg_id, titel}` und zieht read-only über den Core-Relay.

## 4. Funktionen / UI (nutzt das neue Netzwerk-Kit)
- **Setup-Wizard:** Art → Institution → Abschluss/Studiengang → Hauptfach/Nebenfach →
  PO-Jahr. Verzweigt Uni vs. Ausbildung.
- **Studien-Cockpit:** ECTS-Fortschritt (erreicht/gesamt, je Bereich — `DzChart`-Ringe/Bars),
  **gewichteter Notenschnitt** (nach PO-Regel), Fachsemester vs. Regelstudienzeit,
  **nächste Fristen**, **Prüfungsversuch-Warner** (rote Kachel bei letztem Versuch).
- **Modulplan-Ansicht:** Raster je empfohlenem Semester, **status-farbcodiert** (gleiches
  Muster wie das Rechnungs-Status-Board/Aging aus P1).
- **Prüfungsversuch-Tracker:** je Modul Versuche genutzt/übrig, existenzielle Warnungen.
- **Frist-Wächter-Integration:** Studien-Fristen → Leading-Wächter → Push an Dizzi/Plans/Admin.
- **Änderungs-Monitor:** PO/Modulhandbuch-Diff (Hash) ⇒ Hinweis „PO geändert".
- **Berichtsheft (Ausbildung):** Wochen-Eintrag + Status + Export, Vollständigkeits-Wächter.

## 5. Daten-Beschaffung (gestuft, HITL-Pflicht)
- **A. Manuell** — funktioniert immer, Baseline.
- **B. Campus-Import** — cmlife: PO-PDF + Studienverlaufsplan + Notenauszug herunterladen;
  Stundenplan als **iCal**; Noten ggf. als CSV. Leading importiert CSV/iCal/PDF. (Hinweis:
  HISinOne/CAMPUSonline bieten i. d. R. **keine** offene API ⇒ Datei-Import statt Live-Sync.)
- **C. Dokument-Extraktion** — PO/Modulhandbuch/Transcript liegen in **Admin** → Leading
  zieht über **`GET /api/querverbindung/admin/belege`** → **lokale LLM** (Ollama, `lokal_only`
  wegen Sensibilität) extrahiert Module/ECTS/Versuchsregeln in strukturiertes JSON →
  **HITL-Review vor Übernahme** (PO ist rechtlich verbindlich, Extraktion ist Hilfsmittel,
  nie blind übernehmen).
- **D. Internet-Recherche** — aus Institution+Studiengang+PO-Jahr offizielle Quellen finden
  (z. B. Bayreuth Amtliche Bekanntmachungen / konsolidierte Fassungen), fetchen, extrahieren/
  ergänzen. **Change-Monitor:** periodisch neu fetchen + Hash-Diff ⇒ PO-/Modulhandbuch-
  Änderungen melden. Ebenfalls HITL.

## 6. Netzwerk-Integration (über bestehende Core-Relays — schon vorhanden!)
- **Admin** `…/admin/belege` — PO/Modulhandbuch/Transcript-Dokumente (read-only).
- **Memory** `…/memory/suche` — vernetztes Wissen/Notizen, semantische Anreicherung.
- **Plans** `…/plans/kalender` — Prüfungstermine/Fristen → Kalender/Aufgaben.
- **News / Communication** — optional: PO-/Fakultäts-Nachrichten; Prüfungsamt-Mails (HITL).
- **Leading-intern wiederverwenden:** `fristen` + Frist-Wächter, Mini-Dizzi (lokale KI),
  Tokens/Netzwerk-Kit (Cockpit/Board/Charts/Verknüpfungs-Chip aus P1).

## 7. Recht & Sensibilität
- **Sensibel:** Matrikelnummer, Noten, PO-Bezug ⇒ Leading ist bereits `sensitivity='hoch'`
  ⇒ KI **lokal-first**; für Noten ggf. `lokal_only`.
- **Disclaimer (Pflicht):** Allein die im **Prüfungsamt / in den Amtlichen Bekanntmachungen
  veröffentlichte PO** ist verbindlich. Leading ist ein **Hilfsmittel**, **keine Rechts-/
  Studienberatung**; extrahierte Daten sind nie automatisch verbindlich (HITL).
- **DSGVO:** vertragskonforme Tabellen ⇒ Export + Lösch-Kaskade greifen ohne Per-App-Code.

## 8. Phasen-Vorschlag (per-App-Phase MIT Nutzer)
- **P-Stud-1 (Kern):** Datenmodell + Setup-Wizard + manuelle Modul-/Status-Eingabe +
  Studien-Cockpit (ECTS/Noten/Versuche/Fristen) + Frist-Wächter-Anbindung. **Rein Leading,
  kein Netzwerk nötig — sofort wertstiftend.**
- **P-Stud-2 (Dokument-Extraktion):** Admin/Memory-Querverbindung + lokale LLM-Extraktion
  aus PO/Modulhandbuch-PDF + HITL-Review + CSV/iCal-Import.
- **P-Stud-3 (Internet + Monitor):** offizielle Quellen finden/fetchen + Änderungs-Monitor.
- **P-Stud-4 (Ausbildung-Tiefe):** Berichtsheft + IHK-Fristen + Ausbildungsrahmenplan.

## 9. Offene Fragen / Risiken
- **PDF-Extraktionsqualität** (Modulhandbücher sehr heterogen) ⇒ HITL zwingend; Start mit
  einem konkreten Pilot-Studiengang (Bayreuth, Nutzer-eigener) zum Kalibrieren.
- **Keine offiziellen Campus-APIs** ⇒ Import statt Live-Sync; cmlife-Exporte als Brücke.
- **PO-Versionierung/-Wechsel** (Studierende können in neuere PO wechseln) ⇒ version-aware.
- **Wahlpflicht-Logik** (X-aus-Y, Bereichs-Mindest-ECTS) kann komplex werden ⇒ schrittweise.
- **Uni vs. Ausbildung** sind strukturell verschieden ⇒ klare Branch-Trennung im Datenmodell.

## Quellen (Stand 19.06.2026)
- cmlife/CAMPUSonline & PO/Modulhandbuch Bayreuth: [Zentrale Studienberatung – FAQs während des Studiums](https://www.studienberatung.uni-bayreuth.de/de/studierende/waehrend-studium/index.html) · [Amtliche Bekanntmachungen / Prüfungsordnungen](https://www.amtliche-bekanntmachungen.uni-bayreuth.de/de/pruefungsordnungen/index.html) · [cmlife Hilfe](https://cm.docs.indibit.eu/cmlife-docs/)
- Prüfungsversuche / endgültiges Nichtbestehen: [Studis Online – nicht bestehen](https://www.studis-online.de/Studieren/Lernen/nicht-bestehen.php) · [Uni Bonn BZL – endgültiges Nichtbestehen](https://www.bzl.uni-bonn.de/studium/pruefungen/endgueltiges-nichtbestehen)
- Modulhandbuch/ECTS/Bologna: [FU Berlin – Module & Leistungspunkte](https://www.fu-berlin.de/studium/beratung/information_a-z/punktemodule.html) · [SRH – Modulhandbuch erklärt](https://www.mobile-university.de/studium/modulhandbuch/)
- Studienplaner/Modulplan: [HISinOne Studienplaner (Uni Freiburg)](https://wiki.uni-freiburg.de/campusmanagement/doku.php?id=hisinone%3Astudieren%3Astudienplaner) · [meinstudium.net – Modulplan](https://www.meinstudium.net/studienorganisation-und-alltag/was-ist-ein-modulplan-so-liest-du-deinen-studienverlaufsplan-richtig)
- Ausbildung/Berichtsheft: [IHK Region Stuttgart – Berichtsheft](https://www.ihk.de/stuttgart/fuer-azubis/vertraege/berichtsheft-670862)
