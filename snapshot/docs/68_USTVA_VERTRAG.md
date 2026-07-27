# 68 · UStVA-VERTRAG — USt-Datenschicht + §19-Kleinunternehmer + Vorsteuer für Dizz Money (M-4, Bau-Spec für Bau-KI)

> **Status: VERTRAG (M-4, Architektur-KI 04.07.2026, Worktree `chat/ustva-kern`). REINES DESIGN — kein Bau,
> keine echte Berechnung gegen Echtdaten, keine Übermittlung, kein UI.** Verträge-als-Code:
> [`apps/money/moneyapp/ustva/vertrag.py`](../apps/money/moneyapp/ustva/vertrag.py) (Stufe 0,
> Docstrings normativ) + `apps/money/tests/test_ustva_vertrag.py`. Zwilling zu docs/65 (M-1):
> dort fährt der **Transport** die Erklärung ans Finanzamt — hier entsteht der **validierte
> UStVA-INHALT**, den er fährt. Zusammen vollenden sie Davids D7-Endgame (docs/58 §3.B M-1…M-7).
> Quellen: docs/58 §3.B + §4 VO-5 · docs/65 (Kopplungs-Zwilling) · `moneyapp/{auswertung,
> trading_steuer,ledger,main}.py` (Datenlage) · money `docs/02` · docs/56/65 §9 (Editionen) ·
> docs/61 §2.2/§4 (Härtung).

## §0 · Geltung + Nicht-Ziele

**Ziel:** Aus der Money-Buchungslage (Double-Entry-Ledger, Minor-Units) einen **vollständigen,
nachvollziehbaren, hash-gebundenen UStVA-Datensatz** je Voranmeldungszeitraum erzeugen — Kennziffer
für Kennziffer aus klassifizierten Buchungen hergeleitet, nie geschätzt. Dazu gehören die beiden
Rechts-Weichen, die VOR jeder UStVA stehen: **§19-Kleinunternehmer-Status** (ist überhaupt eine
UStVA fällig?) und **Vorsteuer-Abzug** (was mindert die Zahllast?). „Nichts vergessen, nichts falsch
machen" heißt hier: **jede Buchung des Zeitraums ist entweder klassifiziert oder der Datensatz
entsteht nicht** (U-1) — geld- und rechtskritisch gibt es kein stilles Default.

**Nicht-Ziele (für immer bzw. bis eigenes Gate):** KEINE Steuer-BERATUNG (Money bleibt Schätz-/
Erfassungstool, Disclaimer-Pflicht bleibt — money docs/02) · keine Übermittlung (das ist M-1,
docs/65) · keine Plausibilisierungs-ENGINE (das ist M-2, Bau-KI — dieser Vertrag liefert ihr nur den
kanonischen Prüfgegenstand) · keine USt-**Jahreserklärung** (eigene spätere Vertragserweiterung,
gleiche Datenschicht) · keine Bilanzierung/SKR (M-5, an Rechtsform-Entscheid) · keine
KI-Klassifikation in v1 (nur deterministische Regeln + Mensch; KI darf später VORSCHLAGEN,
`geld` ⇒ `pre_approval`, docs/63 §4) · kein Eingriff in appkit (§10) · keine Sonderregime
(§13b-Bau-Leistungen im Detail, §25/§25a Reise/Differenz, Fahrzeug-Einzelbesteuerung,
Organschaft, §15a-Berichtigung, EU-KU-Regelung §19a) — solche Sachverhalte fallen in v1
**laut auf Rot** statt still falsch (§4).

## §1 · Härtungs-Invarianten (nummeriert; Enforcement-Ort verbindlich)

| # | Invariante | Enforcement |
|---|---|---|
| U-1 | **Fail-closed-Klassifikation:** eine Buchung ohne eindeutige USt-Klassifikation (Regel-Treffer oder manueller Entscheid) blockiert den GESAMTEN Zeitraum ⇒ `KlassifikationUnklar` mit Buchungs-IDs; NIE stilles Default, NIE Heuristik-Raten | `klassifiziere` + `pruefe_vollstaendig` (Tests heute) |
| U-2 | **Kein Recht raten:** Schwellenwerte/KZ-Zuordnungen leben in **Jahres-Tabellen** (`SCHWELLEN`, `KZ_KATALOG`); ein Jahr ohne Eintrag wirft `SchwellenUnbekannt`/`KatalogUnbekannt` — Recht ist DATENSTAND mit Pflege-Slot, nie Code-Konstante; JEDE KZ trägt ihr VERIFY-Flag bis zum Abgleich am echten ERiC-Schema (M4-4) | Jahres-Tabellen + `katalog_fuer`/`schwellen_fuer` (Tests heute) |
| U-3 | **§19-Konflikte sind hart:** im Kleinunternehmer-Status wird KEIN UStVA-Datensatz erzeugt, KEINE USt in Rechnungen ausgewiesen, KEIN Vorsteuerabzug gebucht ⇒ `KleinunternehmerKonflikt`; ig-Erwerbe/§13b-Bezüge im KU-Status ⇒ ebenfalls Rot (v1: manuelle Klärung, nie still ignoriert — die Steuerschuld kann trotzdem entstehen!) | `pruefe_ku_konflikt` + `erzeuge_ustva`-Wächter (Tests heute) |
| U-4 | **Ledger unberührt:** die USt-Achse lebt in SEITEN-Tabellen (`ust_*`); keine Spalte, keine Semantik-Änderung am Sorgfaltskern `ledger.py`/`buchungen`; Klassifikation referenziert `buchung_id`, mutiert nie | Architektur + Bestands-Tests bleiben grün (heute) |
| U-5 | **Herkunfts-Manifest:** jeder KZ-Betrag zerfällt nachvollziehbar in Buchungs-IDs (`HerkunftsPosten`); ein Datensatz ohne lückenlose Herkunft besteht `pruefe_summen` nicht — GoBD-Geist: Auswertung ist ableitbar, nie behauptet | `UStVADatensatz` + `pruefe_summen` (Tests heute) |
| U-6 | **Hash-Bindung an M-2/M-1:** `kanonische_serialisierung` (deterministisch, sortiert) + `quell_stand` (sha256 via `elster.vertrag.berechne_quell_stand`) — die M-2-`PlausiFreigabe` bindet an GENAU diesen Stand; 1 Cent Änderung ⇒ `GateRot` in M-1 (docs/65 I-1). **Kein Filing ohne grünes M-2-Gate — M-4 erzeugt, M-2 prüft, M-1 sendet; keine Rolle überspringt eine andere** | `kanonische_serialisierung` + Kopplungs-Tests heute (e2e gegen `elster.pruefe_gate`) |
| U-7 | **Rundung ist Gesetz, nicht Geschmack:** BMG-KZ in **vollen Euro, Centbeträge abgeschnitten Richtung Null** (`euro_voll`); Steuer aus voll-Euro-BMG ist bei 19 %/7 % **exakt ganzzahlig in Cent** (BMG_€ × Satz), sonstige Steuer-KZ centgenau; Zahllast-Formel (§5) ist EINE Funktion, nie verstreute Arithmetik | `euro_voll` + `pruefe_summen` (Tests heute, inkl. Negativ-Fälle) |
| U-8 | **Zeitraum-Integrität:** `UStVAZeitraum` validiert konstruktiv (Monat 1–12/Quartal 1–4), erzeugt EXAKT das `SteuerFall.zeitraum`-Format aus docs/65 (`"YYYY-MM"`/`"YYYY-Qn"`); Soll-Versteuerung ist in v1 gesperrt (`KonfigFehler` — Money ist Kassen-/Ist-Pfad, §2), nie stillschweigend „irgendwie" periodisiert | `UStVAZeitraum` + `VoranmeldungsKonfig` (Tests heute, Roundtrip gegen `SteuerFall`) |
| U-9 | **Nur lokal + HITL:** USt-Klassifikation/Erzeugung läuft ausschließlich lokal (E-SERVER erbt docs/65 §9: Steuer ist nie ein Server-Feature); jede Übergabe an M-1 ist ein bewusster Nutzer-Akt; agentisch nur als Vorschlag durch die K4-Inbox (`geld` ⇒ `pre_approval`, docs/63) | Architektur (kein Cloud-/Auto-Pfad im Modul); docs/65 §8/§9 |

## §2 · USt-Wissen (das Minimum, das Bau-KI zum Bauen braucht — Rechtsstand 2025/2026)

- **UStVA-Mechanik:** Voranmeldung je Zeitraum ans Finanzamt (via ELSTER = M-1). Bemessungsgrundlagen
  (Umsätze) werden in **vollen Euro** gemeldet, Steuer-/Vorsteuerbeträge **centgenau**; die Zahllast
  (KZ 83) errechnet sich aus Steuern minus Vorsteuern (§5). Abgabe bis zum **10. Tag** nach
  Zeitraum-Ende; **Dauerfristverlängerung** (+1 Monat) ist ein eigener Antrag, Monats-Anmelder
  zahlen dafür eine **1/11-Sondervorauszahlung** (Anrechnung im letzten Zeitraum des Jahres, KZ 39).
- **Zeitraum-Regeln (Stand 2025, jährlich VERIFY):** Monats-Abgabe bei Vorjahres-USt-Zahllast
  **> 9.000 €**; sonst Quartal; bei Vorjahres-Zahllast **≤ 2.000 €** kann das FA von Voranmeldungen
  ganz befreien (nur noch Jahreserklärung). Neugründer: keine Monats-Pflicht mehr (ausgesetzt).
  ⇒ Modell kennt alle drei Modi (`MONAT`/`QUARTAL`/`JAHR_BEFREIT`); WELCHER gilt, ist Konfiguration
  + David-Gate (G-M4-ZEITRAUM), nie Ableitung im Code (das FA legt fest, nicht wir).
- **Ist- vs. Soll-Versteuerung:** Money ist ein Zahlungs-Ledger ⇒ natürlicher Pfad ist
  **Ist-Versteuerung** (§20 UStG: auf Antrag u. a. bei Gesamtumsatz Vorjahr ≤ 800.000 €;
  Freiberufler ohne Buchführungspflicht ohnehin). Periodisierung = Vereinnahmung/Verausgabung =
  Buchungsdatum im Ledger. **Soll**-Versteuerung bräuchte Leistungs-/Rechnungsdaten, die Money heute
  nicht führt ⇒ v1 gesperrt (U-8); ob der §20-Antrag gestellt ist/wird = Teil von G-M4-ZEITRAUM.
- **★ §19-Reform 2025 (JStG 2024 — das NEUE Recht, das dieser Vertrag abbildet):** Kleinunternehmer-
  Umsätze sind seit 01.01.2025 **echt steuerfrei** (vorher: „Steuer wird nicht erhoben"). Grenzen:
  Vorjahres-Gesamtumsatz **≤ 25.000 €** UND laufendes Jahr **≤ 100.000 €**. ★ Die 100.000er-Grenze
  wirkt **HART unterjährig**: der Umsatz, mit dem sie überschritten wird, unterliegt bereits der
  Regelbesteuerung — kein Prognose-Modell mehr (das alte 22.000/50.000-Prognose-Recht wird bewusst
  NICHT modelliert; Jahre < 2025 werfen `SchwellenUnbekannt`). Kleinunternehmer geben grundsätzlich
  **keine UStVA** ab (und seit 2025 i. d. R. keine USt-Jahreserklärung, außer auf Aufforderung).
  **Verzicht** auf §19 (Option zur Regelbesteuerung) bindet **5 Kalenderjahre**. Gesamtumsatz-Maß:
  **vereinnahmte** Entgelte (Netto-Logik, da steuerfrei). EU-Variante (§19a, KU-IdNr.) = Nicht-Ziel.
- **Rechnungs-Folgen:** Kleinunternehmer dürfen KEINE USt ausweisen (sonst wird sie nach §14c
  geschuldet — U-3 blockiert das konstruktiv); empfohlener Rechnungs-Hinweis auf die Steuerfreiheit
  nach §19 UStG; erleichterte Pflichtangaben (§34a UStDV, Wortlaut VERIFY in M4-6). Kleinunternehmer
  sind von der E-Rechnungs-**Ausstellungs**pflicht dauerhaft befreit, müssen aber empfangen können.
  Regelbesteuerer: USt-Ausweis Pflichtangabe (§14 Abs. 4); **Kleinbetragsrechnung ≤ 250 €** mit
  erleichterten Angaben (§33 UStDV) — relevant für die Vorsteuer-Nachweis-Regel (§7).
- **Steuersätze:** der Code kennt nur die Satz-MENGE {19 %, 7 %, 0 %} als zulässige Werte —
  **WELCHER Satz für welche Kategorie gilt, ist immer Nutzer-Regel** (§4), nie Code-Konstante
  (Satz-Politik ändert sich, zuletzt Gastronomie; Raten wäre U-2-Bruch).
- **VERIFY-Politik (Anti-Scheingenauigkeit, docs/65-Geist):** alle KZ-Nummern in §5 sind nach bestem
  Wissen benannt und semantisch begründet, tragen aber `verify=True` bis zum Abgleich mit dem
  **echten ERiC-Jahres-Schema** in M4-4 (das Schema kommt mit M1-3/G-M1-ERIC ins Haus). Ein
  Datensatz aus einem unverifizierten Katalog erreicht das Filing nie ohne ERiC-Validate (M-1 I-5)
  — doppelter Boden statt Vertrauen in Gedächtnis-Nummern.

## §3 · Datenmodell (normativ: `ustva/vertrag.py`)

| Typ | Zweck | Kern-Invarianten |
|---|---|---|
| `UStKategorie` | semantische Zwischenschicht Buchung→KZ (§4) | geschlossene Enum; Sachverhalte außerhalb ⇒ bleiben unklassifiziert ⇒ U-1 |
| `KlassifikationsRegel` | Kategorie-Default (kategorie_id → UStKategorie + Satz + VoSt-Status) | frozen; Satz nur aus {190,70,0} ‰; Widerspruchs-Checks (z. B. `UMSATZ_19` verlangt Satz 190) |
| `Klassifikation` | der Entscheid je Buchung | frozen; trägt `quelle` (REGEL\|MANUELL) + USt-Split; Feld-Fläche eingefroren (Test) |
| `UstSplit` | brutto = netto + ust, konstruktiv | Cent-Ints; `split_aus_brutto` deterministisch (kaufmännisch aufs Netto, USt = Rest — EINE Konvention); Satz 0 ⇒ ust 0 |
| `Schwellen` / `SCHWELLEN` | §19-Jahres-Grenzen (§6) | nur 2025/2026; `schwellen_fuer(jahr)` wirft sonst (U-2) |
| `VerzichtsErklaerung` | §19-Option zur Regelbesteuerung | bindet 5 Kalenderjahre (`bindet_bis_jahr` konstruktiv = ab_jahr+4) |
| `StatusBefund` | Ergebnis der §19-Prüfung | Form + maschinenlesbarer Grund + menschlicher Text; nie Form ohne Grund |
| `KzZuordnung` / `KZ_KATALOG` | UStKategorie→KZ je Jahr (§5) | `richtung` (BMG_MIT_SATZ\|BMG_INFO\|STEUER\|VORSTEUER\|ABZUG) macht die Zahllast-Formel generisch; `verify`-Flag Pflicht |
| `KzWert` | ein gemeldeter Betrag | KZ-String + Betrag + Einheit (EURO_VOLL für BMG, CENT für Steuer); BMG verlangt volle Euro |
| `HerkunftsPosten` | Manifest-Zeile (U-5) | (kz, buchung_id, betrag_cent); Datensatz-Konstruktor verlangt Herkunft nur zu vorhandenen KZ |
| `UStVADatensatz` | DER Produkt-Typ (frozen) | zeitraum + kz_werte + herkunft + besteuerungsform + berichtigung + erstellt_am; keine Dubletten-KZ; NIE im KU-Status konstruierbar (U-3) |
| `VoranmeldungsKonfig` | Zeitraum-Typ/Dauerfrist/Ist-Soll | SOLL ⇒ `KonfigFehler` (v1, U-8); JAHR_BEFREIT ⇒ `erzeuge_ustva` wirft `ZeitraumFehler` (nichts anzumelden) |
| `UStVAZeitraum` | Voranmeldungszeitraum | Monat/Quartal validiert; `schluessel()` = docs/65-Format; `grenzen()` = ISO-Datumsfenster; `faelligkeit_nominal()` ehrlich „nominal" (ohne §108-AO-Verschiebung — Bau) |

**Persistenz-Plan (M4-1, Money-DB via `_migriere`-Hausmuster, alle mit `user_id`+`deleted_at`;
Ledger-Tabellen UNBERÜHRT — U-4):** `ust_regeln` (kategorie_id → ustkategorie, satz_promille,
vorsteuer_status — die Kategorie-Default-Achse NEBEN `steuer_relevant`/`steuer_art`, die
ESt-Achse bleibt was sie ist) · `ust_klassifikationen` (buchung_id, ustkategorie, satz_promille,
netto_cent, ust_cent, vorsteuer_status, vorsteuer_verbot_grund, quelle, entschieden_am — der
Buchungs-Override + Audit-Spur) · `ust_zeitraeume` (zeitraum_schluessel, konfig-Snapshot,
datensatz_json, quell_stand_hash, erstellt_am — der erzeugte Datensatz als GoBD-naher Snapshot;
Festschreibung selbst = M-7) · `ku_status` (jahr, form, grund, verzicht_ab_jahr, befund_text).

## §4 · Klassifikations-Architektur: Buchung → `UStKategorie` (fail-closed, U-1)

**Die Enum (geschlossen; alles außerhalb bleibt unklar ⇒ Rot):**

| Wert | Bedeutung (Ausgangs-/Umsatzseite) |
|---|---|
| `UMSATZ_19` / `UMSATZ_7` | steuerpflichtige Lieferungen/Leistungen 19 %/7 % |
| `UMSATZ_STFREI_MIT_VST` | steuerfrei MIT VoSt-Abzug (z. B. Ausfuhr, §4 Nr. 1a/2–7) |
| `UMSATZ_IG_LIEFERUNG` | innergemeinschaftliche Lieferung (§4 Nr. 1b; ZM-Pflicht — Bau-Notiz M4-4) |
| `UMSATZ_STFREI_OHNE_VST` | steuerfrei OHNE VoSt-Abzug (§4 Nr. 8–29) |
| `UMSATZ_13B_LEISTENDER` | Umsätze, für die der EMPFÄNGER die Steuer schuldet (§13b Abs. 5) |
| `UMSATZ_EU_B2B` | nicht steuerbare sonstige Leistung EU-B2B (§18b; ZM-Pflicht) |
| `UMSATZ_NICHT_STEUERBAR` | übrige nicht steuerbare Umsätze (Leistungsort Ausland u. a.) |

| Wert | Bedeutung (Eingangs-/Erwerbsseite) |
|---|---|
| `ERWERB_IG_19` / `ERWERB_IG_7` | innergemeinschaftlicher Erwerb 19 %/7 % (Steuer UND ggf. VoSt) |
| `BEZUG_13B` | bezogene Leistung, für die WIR die Steuer schulden (§13b — Steuer UND ggf. VoSt) |
| `EINGANG_VST` | Eingangsleistung mit abziehbarer Vorsteuer (§15 Abs. 1 Nr. 1) |
| `EINGANG_EUST` | Einfuhr mit entrichteter Einfuhrumsatzsteuer (§15 Abs. 1 Nr. 2) |
| `EINGANG_OHNE_VST` | Eingang ohne VoSt (keine USt ausgewiesen: KU-Lieferant, steuerfrei, privat nah) |

| Wert | Bedeutung (neutral) |
|---|---|
| `KEIN_UMSATZ` | kein Leistungsaustausch: Privateinlage/-entnahme Geld, Steuerzahlungen ans FA, Kapitalertrag/Trading-Ergebnis (`trading_steuer.py` ist EStG-§20/§23-Welt — umsatzsteuerlich KEIN Umsatz), durchlaufende Posten |

**Zuordnungs-Mechanik (Hausmuster „Konto-Default + Buchung-Override", hier Kategorie-Ebene):**
`ust_regeln` gibt je Money-Kategorie einen Default (`KlassifikationsRegel`); `ust_klassifikationen`
überschreibt je Buchung (`quelle=MANUELL` schlägt `REGEL`). `klassifiziere(buchung, regeln,
overrides)` ist eine **reine Lookup-Funktion**: Override → Kategorie-Regel → sonst
`KlassifikationUnklar`. **Keine Heuristik, keine Betrags-/Text-Raterei, keine KI in v1** —
die bestehende lernende Regel-Engine (`regeln.py`) kategorisiert weiter nur die Money-Kategorie;
die USt-Folge hängt IMMER an einer expliziten Nutzer-Regel oder einem Einzel-Entscheid.
**Automatisch ist genau EINE Zuordnung:** Buchungen mit `netto == 0` (interner Transfer zwischen
eigenen Konten, Ledger-Semantik) sind `KEIN_UMSATZ` — das ist dokumentierte Strukturaussage,
kein Raten (Test).

**Vollständigkeits-Wächter:** `pruefe_vollstaendig(bewegungen, klassifikationen, zeitraum)` —
JEDE Buchung des Zeitraums mit `netto != 0` braucht eine Klassifikation; fehlt eine ⇒
`KlassifikationUnklar` mit der ID-Liste (UI-Arbeitsvorrat, M4-6). Erst danach darf
`erzeuge_ustva` überhaupt rechnen. **Bewusst KEINE eigene Zustandsmaschine:** der
Datensatz-Lebenszyklus ist eine Wächter-KETTE (`pruefe_vollstaendig` → `pruefe_summen` →
`uebergabe_an_filing`); der einzige echte Zustands-Lauf (Senden) gehört M-1 und wird nicht
dupliziert (docs/65 §4 bleibt die einzige Filing-Maschine im Netz).

## §5 · KZ-Katalog: `UStKategorie` → Kennziffern (Jahres-Tabelle, U-2/U-7)

**Katalog-Semantik:** `KZ_KATALOG[jahr][kategorie] → KzZuordnung(kz_bmg, kz_steuer, richtung,
verify)`. `richtung` macht die Zahllast generisch: `BMG_MIT_SATZ` (Steuer = BMG_€ × Satz, exakt
ganzzahlig in Cent — U-7) · `BMG_INFO` (nur Meldung, keine Steuerwirkung) · `STEUER` (centgenauer
Steuerbetrag, gemeldet) · `VORSTEUER` (centgenau, mindert) · `ABZUG` (KZ 39). Jahre: **2025 + 2026**
(inhaltsgleich); andere Jahre ⇒ `KatalogUnbekannt`.

| UStKategorie | KZ (BMG → Steuer) | richtung | Vertrauen |
|---|---|---|---|
| `UMSATZ_19` | **81** → (rechnerisch) | BMG_MIT_SATZ 19 % | semantisch sicher, verify |
| `UMSATZ_7` | **86** → (rechnerisch) | BMG_MIT_SATZ 7 % | semantisch sicher, verify |
| `UMSATZ_IG_LIEFERUNG` | **41** | BMG_INFO | semantisch sicher, verify |
| `UMSATZ_STFREI_MIT_VST` | **43** | BMG_INFO | semantisch sicher, verify |
| `UMSATZ_STFREI_OHNE_VST` | **48** | BMG_INFO | semantisch sicher, verify |
| `UMSATZ_13B_LEISTENDER` | **60** | BMG_INFO | semantisch sicher, verify |
| `UMSATZ_EU_B2B` | **21** | BMG_INFO | semantisch sicher, verify |
| `UMSATZ_NICHT_STEUERBAR` | **45** | BMG_INFO | semantisch sicher, verify |
| `ERWERB_IG_19` | **89** → (rechnerisch) | BMG_MIT_SATZ 19 % | semantisch sicher, verify |
| `ERWERB_IG_7` | **93** → (rechnerisch) | BMG_MIT_SATZ 7 % | semantisch sicher, verify |
| `BEZUG_13B` | **84 → 85** (Sammel-KZ „andere Leistungen"; §13b-Differenzierung 46/47, 73/74 = Bau-VERIFY) | BMG + STEUER | Zuordnungs-REGEL (s. u.) |
| `EINGANG_VST` | **66** | VORSTEUER | semantisch sicher, verify |
| `ERWERB_IG_*`-Vorsteuer | **61** | VORSTEUER | semantisch sicher, verify |
| `EINGANG_EUST` | **62** | VORSTEUER | semantisch sicher, verify |
| `BEZUG_13B`-Vorsteuer | **67** | VORSTEUER | semantisch sicher, verify |
| Sondervorauszahlung | **39** | ABZUG (nur letzter Zeitraum) | semantisch sicher, verify |
| Zahllast/Überschuss | **83** | (berechnet, §-Formel unten) | semantisch sicher, verify |

**Zuordnungs-REGELN statt geratener Detail-KZ (U-2 — M4-4 füllt am echten Schema):**
(1) **§13b-Differenzierung:** das amtliche Formular unterscheidet §13b-Bezüge nach Fallgruppen
(EU-Dienstleistung §13b Abs. 1 · GrESt-Fälle · übrige) mit je eigenem BMG/Steuer-Paar — v1 führt
EINE Sammel-Kategorie `BEZUG_13B`; die Aufspaltung auf die richtigen Paare (46/47, 73/74, 84/85)
macht M4-4 gegen das ERiC-Schema, die SUMME ist heute schon korrekt hergeleitet. (2) **Sonstige
Steuer-KZ** (unrichtiger Ausweis §14c, Wechsel der Besteuerungsform, §17-Berichtigungen, ig.
Fahrzeug-KZ, §15a, Durchschnittssätze): in v1 NICHT klassifizierbar ⇒ solche Sachverhalte bleiben
unklar ⇒ Rot (U-1) — bewusst, statt falscher KZ. (3) **Berichtigte Anmeldung:** Flag am Datensatz
(`berichtigung=True`, gespiegelt in `SteuerFall.korrektur_nr` > 0 — M-1 I-6 regelt den Ablauf);
die amtliche Flag-KZ setzt M4-4.

**Rundung + Zahllast (U-7, EINE Funktion `pruefe_summen`/`zahllast_cent`):**
`euro_voll(cent)` schneidet Richtung Null (−1.234,56 € → −1.234 €; Entgeltminderungen machen
negative BMG legitim). Zahllast = Σ Steuern − Σ Vorsteuern − Abzüge:
`KZ83_cent = Σ(BMG_MIT_SATZ: bmg_euro × satz_cent_je_euro) + Σ(STEUER-KZ) − Σ(VORSTEUER-KZ) − KZ39`.
Negativ = Überschuss (Erstattung) — zulässig und ehrlich auszuweisen. **Bekannte, dokumentierte
Differenz:** Steuer aus abgeschnittener Perioden-BMG ≠ Summe der centgenauen Beleg-USt; die
Beleg-Summe (aus den `UstSplit`s des Manifests) ist der **Plausi-Vergleichswert für M-2**
(Toleranzregel definiert M-2, nicht wir — wir liefern beide Zahlen).

## §6 · §19-Kleinunternehmer: Status-Modell + Schwellen (U-2/U-3)

- **`SCHWELLEN` (nur neues Recht):** 2025/2026 → `vorjahr_max = 25.000 €`, `laufend_max =
  100.000 €`, Modus **hart**. `pruefe_kleinunternehmer(jahr, vorjahresumsatz_cent,
  laufender_umsatz_cent, verzicht)` → `StatusBefund`:
  Verzicht aktiv (Bindung läuft) ⇒ `REGELBESTEUERUNG/verzicht` · Vorjahr > 25 k ⇒
  `REGELBESTEUERUNG/vorjahr_ueberschritten` (gilt ab Jahresbeginn) · laufend > 100 k ⇒
  `REGELBESTEUERUNG/laufend_ueberschritten` — **unterjährig SOFORT; der überschreitende Umsatz
  selbst ist bereits steuerpflichtig** (Docstring + Test; der präzise Schnitt „dieser eine Umsatz"
  ist Bau M4-2 am Ledger-Datum) · sonst `KLEINUNTERNEHMER`.
- **Gesamtumsatz-Regel (konservativ, fail-closed in die RICHTIGE Richtung):** Maß = vereinnahmte
  Entgelte des Unternehmens (§19 Abs. 2); bestimmte steuerfreie Umsätze zählen NICHT mit — die
  exakte Abgrenzungsliste ist VERIFY (M4-2). Bis dahin gilt: **im Zweifel MITZÄHLEN** — der
  konservative Fehler führt zu „eher Regelbesteuerung/eher UStVA abgeben", nie zu „fälschlich
  keine Erklärung". `gesamtumsatz_cent(...)` rechnet auf klassifizierten Summen (reine Funktion);
  Kapitalerträge/Trading (`KEIN_UMSATZ`) zählen NIE (kein Leistungsaustausch).
- **Verzicht (§19 Abs. 3):** `VerzichtsErklaerung(ab_jahr)` bindet 5 Kalenderjahre
  (`bindet_bis_jahr = ab_jahr + 4`); Rückkehr zu §19 erst danach UND nur wenn die Schwellen es
  hergeben. Ob Verzicht für David sinnvoll ist (Vorsteuer aus Investitionen!), ist **keine
  Code-Frage**: G-M4-STATUS + G-M4-VORSTEUER, Money berät nicht (§0).
- **Konflikt-Wächter `pruefe_ku_konflikt` (U-3):** im KU-Status verboten und werfend:
  UStVA-Erzeugung (`erzeuge_ustva`) · USt-Ausweis in Ausgangs-Klassifikationen (`UMSATZ_19/7`
  mit `ust_cent > 0`) · `EINGANG_VST`-Abzug (§19: kein VoSt-Abzug). **ig-Erwerbe/§13b-Bezüge im
  KU-Status ⇒ ebenfalls `KleinunternehmerKonflikt` mit ehrlichem Text** (die Steuerschuld kann
  trotz §19 real entstehen — Erwerbsschwelle etc.; v1 klärt das ein MENSCH, das Modul spielt
  nicht Steuerberater — §0). **Umschalter:** `ku_status` ist Jahres-Konfiguration mit Befund-
  Historie; der Wechsel KU↔Regel ändert NIE rückwirkend erzeugte Datensätze (U-5-Snapshots),
  ein unterjähriger Zwangs-Wechsel (100 k) teilt das Jahr in zwei Regime-Fenster (Bau M4-2).
- **Rechnungs-Regel:** `pruefe_rechnung_kleinunternehmer(ust_ausgewiesen_cent)` wirft bei > 0 —
  die Naht für jedes künftige Rechnungs-Modul (heute: Klassifikations-Wächter; §14c-Risiko
  gehört in den Wächter-Text).

## §7 · Vorsteuer: Abzugs-Modell (§15, an der realen Money-Datenlage)

- **Grund-Modell:** jede Eingangs-Klassifikation trägt `UstSplit` (brutto/netto/ust, Cent-Ints)
  + `VorsteuerStatus`: `ABZIEHBAR` (→ KZ 66/61/62/67 je Kategorie) · `NICHT_ABZIEHBAR` (mit
  Pflicht-`VorsteuerVerbotsGrund`) · `TEILWEISE` (**v1: wirft** — §15-Abs.-4-Aufteilung/
  Privatanteile sind Bau M4-3 mit echter Aufteilungs-Doku, kein stiller Prozentsatz).
- **`VorsteuerVerbotsGrund` (geschlossen):** `KEINE_ORDNUNGSGEMAESSE_RECHNUNG` (kein Abzug ohne
  Rechnung i. S. d. §14; Kleinbetrags-Erleichterung ≤ 250 € — Nachweis-Anker ist die bestehende
  **Beleg-Kante `buchungen.beleg_ref`** (V15, `admin:dokument:<id>`): M4-3 kann „ABZIEHBAR ohne
  Beleg-Ref" zur Warn-/Blockier-Regel machen, Vertrag legt heute nur den Anker fest) ·
  `PARAGRAF_15_1A` (Aufwendungen i. S. d. §4 Abs. 5 EStG: Geschenke > 50 €, Repräsentation …) ·
  `KLEINUNTERNEHMER_STATUS` (eigener §19-Status ⇒ nie Abzug, U-3) · `PRIVAT` (nichtunternehmerisch)
  · `STEUERFREIE_VERWENDUNG` (§15 Abs. 2 — Eingang dient VoSt-schädlichen Umsätzen; v1 nur
  ganz-oder-gar-nicht, Aufteilung s. o.).
- **★ Bewirtungs-Falle (dokumentierte Regel + Test):** angemessene, nachgewiesene Bewirtung ⇒
  **Vorsteuer zu 100 % abziehbar**, obwohl ertragsteuerlich nur 70 % Betriebsausgabe sind
  (§15 Abs. 1a S. 2) — die EÜR-Achse (`steuer_art`) und die USt-Achse dürfen hier bewusst
  auseinanderfallen; wer die 70 % auf die VoSt durchschlägt, verschenkt Geld, wer 100 % EÜR
  ansetzt, erklärt falsch. Konstante `BEWIRTUNG_VOST_VOLL = True` + Vertrags-Test halten das fest.
- **`EINGANG_OHNE_VST` ist ehrlich:** Eingänge ohne ausgewiesene USt (KU-Lieferant, steuerfreie
  Leistung, Privatkauf) sind KEIN Verbots-Fall, sondern schlicht ohne Split (ust = 0) — die
  Unterscheidung „keine USt da" vs. „USt da, aber Abzug verboten" bleibt im Datenmodell sichtbar
  (Plausi-Futter für M-2).
- **Split-Konvention:** `split_aus_brutto(brutto_cent, satz_promille)` — Netto = brutto/(1+Satz)
  kaufmännisch auf Cent, USt = brutto − netto (Summen-Invariante konstruktiv, nie zwei
  Rundungen). Belegausweis schlägt Rechenweg: weist die Rechnung die USt aus, gilt der
  Beleg-Betrag (Feld `ust_cent` manuell überschreibbar, `quelle=MANUELL`).

## §8 · Kopplung an M-1/M-2 (die Naht, wegen der es diesen Vertrag gibt)

```
M-4 erzeugt                    M-2 prüft (Bau-KI)                 M-1 transportiert (docs/65)
UStVADatensatz ──kanonisch──▶  PlausiFreigabe(hash, grün) ──▶  UstvaBauer (M1-7) → ERiC
      │                              ▲                                ▲
      └── quell_stand(sha256) ───────┴── identischer Hash ────────────┘   (U-6; stale ⇒ GateRot)
```

- **Kanonik:** `kanonische_serialisierung(datensatz)` = kompaktes JSON mit fester Feld-Reihenfolge,
  KZ aufsteigend sortiert, Cent-Ints (nie Float), UTF-8 — EIN Produzent, EIN Format (docs/65 §3:
  für den UStVA-Pfad definiert M-4 die Quelldaten-Kanonik, M-2 konsumiert sie, M1-7 übernimmt sie).
  `quell_stand(datensatz)` ruft `elster.vertrag.berechne_quell_stand` (Money-interner Import —
  bewusst KEINE Kopie der Hash-Funktion).
- **Zeitraum-Format:** `UStVAZeitraum.schluessel()` liefert exakt das docs/65-`SteuerFall`-Format
  (`"YYYY-MM"` / `"YYYY-Qn"`) — Kopplungs-Test konstruiert `SteuerFall(FormularArt.USTVA, …)`
  aus dem M-4-Zeitraum (Roundtrip heute grün, U-8).
- **Übergabe-Naht:** `uebergabe_an_filing(datensatz, konfig)` → `(SteuerFall, quelldaten_dict)`
  für den M1-7-`UstvaBauer`. Wächter VOR der Übergabe (Defense in depth, auch wenn M-1 erneut
  prüft): Besteuerungsform ≠ KU (U-3) · `pruefe_summen` bestanden (U-5/U-7) · Zeitraum passt zur
  Konfig. Die M-2-Freigabe prüft NICHT M-4 (Rollentrennung: M-1 `pruefe_gate` ist der einzige
  Gate-Prüfer — keine zweite, abweichende Gate-Logik im Netz).
- **M-2-Vorbedingung bleibt HART:** dieser Vertrag macht Filing nicht möglich — er macht es
  vorbereitbar. Ohne grüne, hash-gebundene `PlausiFreigabe` sendet M-1 nie (docs/65 I-1);
  M-4 liefert M-2 dafür den Prüfgegenstand + beide Summen-Sichten (§5).
- **Berichtigung:** neuer Datensatz (`berichtigung=True`, neuer Hash) + `korrektur_nr`-Erhöhung
  im `SteuerFall` — M-1 I-6 regelt Doppel-Schutz; M-4 mutiert NIE einen erzeugten Snapshot (U-5).

## §9 · Editionen + Härtung + Agenten

- **Editionen:** erbt docs/65 §9 unverändert — UStVA-Erzeugung ist reine Lokal-Berechnung
  (E-LOKAL/E-HYBRID: voll; **E-SERVER: Steuer-Modul deaktiviert**, nur Export-Fallback). Der
  Stufen-Fallback gilt auch hier: der erzeugte Datensatz ist als JSON/CSV exportierbar und
  manuell ins ELSTER-Portal übertragbar, BEVOR M-1 je scharf ist (Portal-Weg = Stufe-0-Beweispfad).
- **Härtung (docs/61-Anschluss):** Stufe 0 fügt KEINE Endpoints hinzu (Angriffsfläche 0);
  M4-1/M4-6-APIs laufen über die appkit-Hausmuster (Auth/CSRF/Defense — Money steht heute bei
  0 Funden, docs/61 §2.2, und das bleibt Akzeptanzkriterium). Klassifikations-Texte sind
  Nutzer-Eingaben ⇒ beim Export gilt der bestehende MD-/CSV-Injection-Schutz als Muster
  (`trading_steuer.py`-Vorbild).
- **Agenten (docs/63):** USt-Arbeit ist `geld`-Klasse ⇒ fest `pre_approval`; ein Agent darf
  Klassifikations-VORSCHLÄGE in die K4-Inbox legen (M4-Bau, optional), aber nie klassifizieren,
  erzeugen oder übergeben ohne menschliche Freigabe (U-9).

## §10 · Schnitt: appkit vs. moneyapp — Entscheid **Money-lokal** (wie M-1/M-6)

- **Einziger Konsument:** nur Money führt Bücher; UStVA/§19/Vorsteuer ist deutsches USt-Recht =
  Money-Fachdomäne. appkit-Hebung wäre spekulative Generalisierung (dieselbe Begründung wie
  docs/64 §11/docs/65 §11 — dritte bestätigte Instanz des Schnitt-Musters).
- **Genutzt statt dupliziert:** Hash = `elster.vertrag.berechne_quell_stand` (Money-intern,
  EINE Hash-Konvention für die ganze Steuer-Strecke) · Persistenz = `_migriere`-Hausmuster ·
  spätere APIs = appkit `create_app`-Muster. **Kein neues Scharfschaltungs-Duplikat** (M-4 sendet
  nichts — die Zwei-Schlüssel-Frage bleibt allein bei M-1; der Hebe-Zähler aus docs/65 §11
  bleibt bei ZWEI Instanzen).
- **Hebe-Radar (ehrlich):** die Jahres-Tabellen-Technik (`SCHWELLEN`/`KZ_KATALOG` mit
  fail-closed-Zugriff) könnte bei einer dritten Rechts-Tabellen-Instanz (Kandidat: M-5 SKR,
  Healthy-Kataloge) als Muster nach appkit wandern — bis dahin kein Vor-Bau.

## §11 · Bau-Plan für Bau-KI (commit-groß; jede Stufe: Money-Suite grün; abhängigkeits-getrieben wie docs/67 §9)

| Schritt | Inhalt | Vorbedingung | Akzeptanz |
|---|---|---|---|
| **M4-0 ✅** | dieses Paket: Vertrag + Stufe-0-Stubs + Vertrags-Tests | — | Suite grün; 0 Bestands-Datei verändert |
| **M4-1** | Persistenz + Regel-/Klassifikations-CRUD: Tabellen §3 (`_migriere`), `GET/POST /api/ust/regeln`, Klassifikations-Override-API, „offene Buchungen des Zeitraums"-Liste (U-1-Arbeitsvorrat) | keine (gate-frei) | Ledger-Tabellen byte-gleich (U-4); Responses ohne Geheimnisse; docs/61-Muster eingehalten |
| **M4-2** | §19 live: `ku_status`-Verwaltung, Gesamtumsatz-Monitor am Ledger (Ist-Zufluss-Logik), Schwellen-Wächter mit Warn-Stufen (80 %/100 %), unterjähriger Regime-Schnitt | G-M4-STATUS (Faktenlage) | Schwellen-Tests an synthetischen Jahren; Warnung VOR Überschreiten; Abgrenzungsliste Gesamtumsatz VERIFY erledigt |
| **M4-3** | Vorsteuer-Rechner: Split-Erfassung im Buchungs-/Import-Fluss, Verbots-Gründe-UI, Beleg-Ref-Kopplung (`beleg_ref`-Warnregel), TEILWEISE-Aufteilung (§15 Abs. 4) mit Doku-Pflicht | M4-1 + G-M4-VORSTEUER | Bewirtungs-Regel e2e; kein Abzug ohne expliziten Status; Aufteilung nur mit erfasster Begründung |
| **M4-4** | UStVA-Rechner: Aggregation Zeitraum→`UStVADatensatz` (Manifest, beide Summen-Sichten), **KZ-Katalog-VERIFY am echten ERiC-Schema** (alle `verify`-Flags auflösen, §13b-Differenzierung, Berichtigungs-Flag-KZ, KZ-39-Mechanik) | M4-1..3 + ERiC-Schema im Haus (M1-3 / G-M1-ERIC) | Golden-Datensätze deterministisch; `pruefe_summen` gegen handgerechnete Fixtures; Katalog 0×verify |
| **M4-5** | M-2-Anbindung + Filing-Übergabe: kanonische Serialisierung an M-2-Engine, `uebergabe_an_filing` an M1-7-`UstvaBauer`, Zeitraum-Snapshot in `ust_zeitraeume` (M-7-Festschreib-Anschluss) | **M-2 gebaut** (VO-5!) + M4-4 | e2e: Datensatz → Freigabe → `pruefe_gate` grün; 1-Cent-Mutation ⇒ `GateRot`; Snapshot unveränderlich |
| **M4-6** | UI Steuer-Cockpit (+U): KU-Status-Karte (Schwellen-Ampel), Zeitraum-Karte (offen/vollständig/erzeugt), Klassifikations-Arbeitsvorrat, Export-Fallback-Knopf; CSP-strikt, K2.2-Token | M4-1+ (Karten schrittweise) | isoliert am Scratch-Port, 0 Konsolenfehler; Disclaimer sichtbar (Schätztool, keine Beratung) |
| **M4-Soll** (★ Flexibilität, World-Admin-Recherche 06.07.) | **Soll-Versteuerung** (§13/§16: Steuer entsteht bei *Rechnungsstellung* statt Zahlungseingang) als `VoranmeldungsKonfig`-Option statt v1-`KonfigFehler`; Ist↔Soll je Jahr umschaltbar; Zeitraum-Snapshot leseseitig nach Rechnungs-/Leistungsdatum. Deckt Bilanzierende (GmbH/UG) · > 800.000 € · Verkaufs-Kunden | M4-1..3 (Struktur steht = reine Config-Achse) | Ist↔Soll-Golden-Perioden divergieren korrekt (Zahlungs- vs. Rechnungsdatum); Bestands-Ist-Fälle byte-gleich |

**Sofort zündbar: M4-1 (gate-frei).** M4-2/M4-3 nach den Fakten-Gates (reine David-Antworten,
keine externe Latenz). M4-4 wartet konstruktiv auf das ERiC-Schema (dieselbe Uhr wie M-1: G-M1-ERIC).
M4-5 erst NACH M-2 — **VO-5 bleibt verbindlich**; nichts hier weicht die Reihenfolge auf.

### §11.1 · Szenarien-Abdeckung & geplante Flexibilität (★ World-Admin-Recherche 06.07.2026)

**Prinzip — „für alle Szenarien bereit" = Konfiguration + Jahres-Tabellen, NICHT Code-Zweige** (U-2). Der ganze Szenarien-Raum wird von **wenigen Konfig-Achsen** aufgespannt; das sich ändernde Recht liegt als Datenstand — kein Sonderfall wird hart verdrahtet. Damit ist das Modul strukturell schon „verkaufs-flexibel"; die Achsen:

| Achse | Szenarien | Stand |
|---|---|---|
| USt-Status | §19-Kleinunternehmer ↔ Regelbesteuerung (+ Verzicht 5 J. · unterjähriger 100k-Wechsel) | ✅ **M4-2** (25k/100k = Reform 2025) |
| **Versteuerungsart** | **Ist (§20) ↔ Soll** | ⚠️ v1 blockt Soll (`KonfigFehler`) → **M4-Soll** = die EINZIGE echte Lücke |
| Voranmeldungs-Zeitraum | monatlich / vierteljährlich / jährlich-befreit | ✅ Config; **Schwellen 2025 (> 9.000 € monatl. · 2.000–9.000 € quart. · < 2.000 € befreit) gehören in die Jahres-Tabelle** (2025 geändert!) — VERIFY M4-4 |
| Dauerfrist + 1/11-Sondervorauszahlung | mit / ohne | Config-Flag (KZ 39) — M4-4 |
| Vorsteuer | voll / keine / anteilig §15 Abs. 4 (dok. Schlüssel) · Bewirtung · Verbotsgründe | ✅ **M4-3** |

**Der eine echte Flexibilitäts-Bau = `M4-Soll` (Tabelle oben):** **Ist** braucht einen Antrag und geht nur bis 800.000 € Vorjahresumsatz; **Soll ist der gesetzliche Default** und für **Bilanzierende (GmbH/UG), > 800k, viele normale Betriebe Pflicht**. Ein Verkaufs-Kunde bzw. eine spätere GmbH-Umwandlung braucht Soll ⇒ als reine Config-Option nachbauen (**Bau-KI, kein Architektur-KI**). Davids heutige Lage (Regelbesteuerung / Quartal / Ist / Vorsteuer=ja) ist von M4-2 + M4-3 **voll abgedeckt** — M4-Soll ist Zukunfts-/Verkaufs-Vorsorge, kein Eigenbedarf.

**Nicht-Ziele bleiben fail-loud** (§13b-Reverse-Charge · ig-Erwerbe/Lieferungen + ZM · §15a-Berichtigung · §25a-Differenz · Organschaft · §19a-EU-KU — §0): bei so einem Sachverhalt wirft das Modell hart erkennbar (`KleinunternehmerKonflikt` / manuelle Klärung), nie still falsch — genau die bestehende Design-Linie.

*Recherche-Belege (World-Admin 06.07., keine Steuer-Beratung — Faktenlage fürs Modell): § 20 UStG Ist-/Soll + 800k-Grenze (lexware · finom · shoperate) · UStVA-Schwellen/Fristen 2025 (pandotax · lexware) · §19-Reform 2025 25k/100k + Verzicht (IHK Stuttgart · BMF-Schreiben 18.03.2025).*

## §12 · Test-Strategie

- **Heute (dieses Paket):** Vertrags-Tests in `test_ustva_vertrag.py` — lib-/netz-/DB-frei, rein
  auf den Stufe-0-Typen: Jahres-Tabellen fail-closed (U-2) · Klassifikator-Lookup + Unklar-Wurf +
  netto-0-Regel (U-1) · Vollständigkeits-Wächter mit ID-Liste · §19-Befunde (Verzicht-Bindung,
  Vorjahr/laufend, hart-Semantik) · KU-Konflikt-Matrix (U-3) · Split-Determinismus + Fixpunkte
  (119 → 100/19) · `euro_voll` Richtung Null (±) · Zahllast-Formel gegen handgerechnete Fixtures
  (inkl. Erstattungs-Fall) · Manifest-Pflicht (U-5) · Kanonik-Stabilität (Permutation ⇒ gleicher
  Hash; 1-Cent ⇒ anderer Hash) · **Kopplung an docs/65 e2e** (Zeitraum-Roundtrip in `SteuerFall`;
  `PlausiFreigabe`+`pruefe_gate` grün/stale; KU ⇒ Übergabe wirft) · Feld-Flächen-Anker.
- **Bau:** je M4-Schritt eigene Tests (§11); Golden-Perioden-Fixtures (synthetische Ledger-Monate
  mit handgerechneter UStVA); Property-Tests für Split (∀ brutto,satz: netto+ust=brutto) und
  `euro_voll`; ERiC-Validate der Golden-Datensätze gegen die Testumgebung (via M-1, nie produktiv).
- **Kommando** (Worktree-bewusst): `PYTHONPATH=<repo>\packages` +
  `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q` in `apps\money`.

## §13 · Gates an David (offen formuliert; M-1/M-6-Stil — Faktenfragen, keine Beratung)

- **G-M4-STATUS · §19-Kleinunternehmer oder Regelbesteuerung?** Faktenlage bitte: (1) Gesamtumsatz
  2025 ≤ 25.000 €? (2) 2026 bisher — Kurs auf ≤ 100.000 €? (3) Was wurde dem Finanzamt im
  Gründungs-/Erfassungsbogen erklärt (KU beansprucht? Verzicht erklärt ⇒ 5-Jahres-Bindung läuft)?
  Der Code baut BEIDE Pfade; die Antwort ist Konfiguration (`ku_status`), kein Umbau. Bei KU ruht
  die UStVA-Schiene (M4-2-Wächter läuft trotzdem — er meldet, WENN Regelbesteuerung naht).
- **G-M4-ZEITRAUM · Voranmeldungs-Rhythmus:** Was hat das FA festgelegt — monatlich, quartalsweise,
  oder befreit (Vorjahres-Zahllast ≤ 2.000 €)? Dazu: Ist-Versteuerung (§20) beantragt/gewünscht?
  Dauerfristverlängerung gewünscht? (Vertrags-Default bis zur Antwort: QUARTAL + IST + ohne
  Dauerfrist — die häufigste Kleinbetriebs-Lage; NUR Default der Konfig, nichts rechnet damit.)
- **G-M4-VORSTEUER · Ist Vorsteuer-Abzug für dich relevant?** Stehen Investitionen/nennenswerte
  Betriebsausgaben mit ausgewiesener USt an? (Falls ja UND KU-Status: das ist der klassische
  Verzichts-Abwägungsfall — die ABWÄGUNG gehört zu Steuerberater/David, nicht in Money; das Modul
  liefert nur die Zahlen beider Welten.) Antwort steuert, ob M4-3 früh oder spät zündet.
- **Bezug G-M1-FORMULARE (offen, docs/65 §14):** die EÜR-vor-UStVA-Reihenfolge bleibt dort
  gegated — mit diesem Vertrag ist die UStVA-Datenschicht DESIGNT, der Flip ist also in beide
  Richtungen frei; Davids §19-Antwort (G-M4-STATUS) beantwortet die dortige Teilfrage gleich mit.

## §14 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

Keine Steuer-BERATUNG/Gestaltungs-Empfehlung (KU-Verzicht-Abwägung = Mensch) · keine geratenen
Detail-KZ für §13b-Fallgruppen/Sonder-Tatbestände (Zuordnungs-REGEL steht, M4-4 füllt am Schema) ·
kein Alt-Recht vor 2025 (22 k/50 k-Prognose-Welt wird nicht modelliert — fail-closed via U-2) ·
keine USt-Jahreserklärung (spätere Erweiterung derselben Schicht) · keine §15-Abs.-4-
Aufteilungs-Mathematik in v1 (TEILWEISE wirft; M4-3 mit Doku-Pflicht) · keine Fälligkeits-
Verschiebung nach §108 AO (nominal + ehrlicher Name; Feiertags-Quelle = Bau) · keine ZM
(Zusammenfassende Meldung — eigener Baustein NACH ersten ig-Umsätzen, im Katalog nur als
ZM-Pflicht-Notiz an 41/21) · kein Soll-Versteuerungs-Pfad (gesperrt bis Leistungsdaten existieren) ·
keine KI-Klassifikation (v1 deterministisch; später nur Vorschlag + `pre_approval`).

## §15 · Verhältnis zu den Vorstufen (VO-5-Kette, ehrlich verortet)

**M-2 (Plausibilisierung, Bau-KI, ZUERST)** bekommt von M-4 den kanonischen Prüfgegenstand + beide
Summen-Sichten und bleibt der EINZIGE Freigabe-Produzent — M-4 prüft Vollständigkeit/Arithmetik
(U-1/U-5/U-7), M-2 prüft PLAUSIBILITÄT (Zeitraum-Abdeckung, Ausreißer, Money↔Admin-Abgleich).
**M-3 (harte Kopplung)** betrifft M-4 nur mittelbar (Quelldaten-Beschaffung im Motor, docs/65 §7).
**M-7 (Festschreibung)** friert nach Filing auch die `ust_zeitraeume`-Snapshots ein (M4-5-Naht).
**M-1 (Transport)** konsumiert via M1-7-`UstvaBauer` exakt die §8-Übergabe. Damit gilt VO-5
konstruktiv: M-2 → M-3/M-7 → **M-4 (jetzt designt)** → M1-7-Wire — und G-M1-FORMULARE kann den
EÜR/UStVA-Vortritt frei entscheiden, ohne dass irgendwo Architektur fehlt.
