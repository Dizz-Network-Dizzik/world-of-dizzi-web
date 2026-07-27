# 64 · BANK-SYNC-VERTRAG — FinTS/HBCI NUR LESEND (M-6, Bau-Spec für Bau-KI)

> **Status: VERTRAG (M-6, Architektur-KI 03.07.2026, Worktree `chat/bank-sync`). REINES DESIGN — kein Bau,
> keine Bankverbindung, kein Paket installiert.** Verträge-als-Code:
> [`apps/money/moneyapp/banksync/vertrag.py`](../apps/money/moneyapp/banksync/vertrag.py) (Stubs, Docstrings
> normativ) + `apps/money/tests/test_banksync_vertrag.py`. Bau = Bau-KI M6-1…M6-7 (§12) NACH den Gates §14.
> Vorlage: docs/62/63 (FP-3/FP-4-Muster). Quellen: money `docs/02` §Bank-Anbindung · money-importers ·
> `appkit/{vault,secrets_os,connectors,net_safe}.py` · docs/56 (Editionen) · docs/61 §3-M-5+§4 (Fundament).

## §0 · Geltung + Nicht-Ziele

**Ziel:** Kontoumsätze/-salden von DE-Konten **automatisch, aber ausschließlich lesend** in Dizz Money holen
— als **neue Quelle VOR der bestehenden importers-Pipeline** (Dispatch → camt/MT940 → Ledger). Der manuelle
Datei-Import bleibt vollwertig erhalten (er IST der Fallback für Banken ohne FinTS und der Stufe-0-Beweispfad).

**Nicht-Ziele (für immer bzw. bis eigenes Gate):** KEIN PISP/Zahlungsverkehr (read-only ist
Härtungs-Invariante, nie „Ausbaustufe") · kein Screen-Scraping · kein OFX-Parser (CSV/camt/MT940 decken die
Offline-Fälle) · kein Auto-Hintergrund-Sync in v1 (§8) · kein Eingriff in appkit (§11) · Trading :8137 bleibt
unberührt. Rollen: alles wohnt in **Money** (`moneyapp/banksync/`); appkit wird **genutzt**, nicht erweitert.

## §1 · Härtungs-Invarianten (nummeriert; Enforcement-Ort verbindlich)

| # | Invariante | Enforcement |
|---|---|---|
| I-1 | **NUR LESEND**: der Adapter darf ausschließlich Whitelist-Segmente senden (`ERLAUBTE_SEGMENTE`, deny-by-default); Zahlungs-Familien (HKCC*/HKCS*/HKCD*/HKDS*/HKDM*/HKIP*/HKPPD) strukturell ausgeschlossen. python-fints' Sende-/Transfer-API wird NIRGENDS importiert/gewrappt | `vertrag.segment_erlaubt` + Vertrags-Test heute; M6-3-Audit + Kassetten-Test |
| I-2 | **Geheimnisse nur im Vault**: PIN unter `banksync_pin_<zugang_id>` in `appkit.vault.Vault` (Fernet + DPAPI-Key); TAN wird NIE persistiert (nur flüchtig im Dialog); `BankZugang` trägt nur den Schlüssel-NAMEN; DB/API-Responses/Logs enthalten nie PIN/TAN/volle Kennung (`__repr__` maskiert) | Vertrags-Tests heute (Feld-Fläche eingefroren, repr-Maskierung); M6-6 caplog-Test |
| I-3 | **Zwei-Schlüssel**: Verbindung nur mit `Scharfschaltung` (angelegt UND bestätigt); Motor prüft VOR der Quelle, `FinTSQuelle` prüft selbst nochmal (doppelter Wächter — Definition traut niemandem, docs/63-Muster) | `pruefe_scharf` + Test heute (Wächter greift VOR NotImplementedError) |
| I-4 | **Fail-closed, nie still leer**: jeder Fehler ⇒ FEHLGESCHLAGEN mit ehrlichem Text; ABGESCHLOSSEN mit 0 Buchungen NUR mit `leer_bestaetigt` (Bank hat leeren Zeitraum aktiv bestätigt); Teil-Abrufe (gerissene Aufsetzpunkt-Kette) werden komplett verworfen | `SyncErgebnis.__post_init__` + `als_import_auftrag` (Tests heute) |
| I-5 | **Kein Parallel-Parser**: FinTS liefert camt-/MT940-ROHDATEN → bestehende `parse_inhalt`-Pipeline; Dedupe = bestehender `bewegung_hash` + UNIQUE(import_hash); `AuszugsFormat`-Werte SIND dispatch-Kürzel | Kompatibilitäts-Tests heute (`format in dispatch.FORMATE`) |
| I-6 | **Transport**: nur `https://`-Bank-URLs, Client→Bank direkt; im Sync-Pfad berührt KEIN LLM/Cloud-Dienst Bankdaten (sensible Daten ⇒ konservativste Wahl je Edition, docs/56 §4) | `BankZugang.__post_init__` (Test heute); Architektur (kein KI-Aufruf im Modul) |
| I-7 | **net_safe-Gate**: die FinTS-URL läuft VOR jedem Dialog durch `net_safe.ist_oeffentliche_url` (+ Redirect-Politik: keine; ein FinTS-Endpoint redirectet nicht) — erfüllt die docs/61 §3-M-5-Checkliste „vor dem Scharfschalten jedes ruhenden Konnektors" | M6-3 (Akzeptanzkriterium); heute als Spec-Pflicht |
| I-8 | **Retry-Politik als Code**: `retry_erlaubt` je Fehlerklasse, Basis-Default **False** (unbekannt ⇒ kein Auto-Retry); nur Verbindungs-/Teil-Abruf-Fehler automatisch wiederholbar (Backoff über `SyncStand.fehler_serie`); **AuthFehler nie** (PIN-Sperre nach wenigen Versuchen) | Klassenattribute + Test heute; M6-4 Backoff |

## §2 · FinTS-Dialogmodell (das Wissen, das Bau-KI zum Bauen braucht)

- **Protokoll:** FinTS 3.0 **PIN/TAN** über HTTPS (Segment-Nachrichten; die alten DDV/RSA-Chipkarten-Varianten
  sind NICHT Scope). Ablauf je Lauf: Dialog-Init (HKIDN/HKVVB, ggf. HKSYN für System-ID) → BPD/UPD
  (Bank-/User-Parameter: WAS die Bank kann, inkl. erlaubter Geschäftsvorfälle + TAN-Verfahren via HKTAB/3920)
  → SCA/TAN falls verlangt → Lese-Aufträge → HKEND. Die Zustandsmaschine §4 bildet genau das ab.
- **Umsatz-Abruf:** `HKKAZ` (liefert MT940) bzw. `HKCAZ` (liefert camt.052/053) — **welcher existiert, sagt die
  BPD je Bank**; Politik: camt bevorzugen (reicher an Referenzen fürs Dedupe), MT940 als Fallback. Beide Formate
  parst die BESTEHENDE Pipeline (I-5). Große Zeiträume kommen paginiert über den **Aufsetzpunkt**
  (Fortsetzungs-Marker) — die RUFT_AB-Selbstschleife; reißt die Kette, gilt der GESAMTE Abruf als
  `TeilAbrufFehler` (nie Teil-Import).
- **PSD2/SCA:** TAN kann bei Dialog-Init UND je Auftrag verlangt werden. Umsatz-Historie **> ~90 Tage** löst
  regelmäßig eine TAN aus (Banken variieren, teils 180-Tage-Exemption) ⇒ Politik: Standard-Fenster
  `STANDARD_FENSTER_TAGE=60` (TAN-arm), Folge-Läufe ab letztem Erfolg − `UEBERLAPP_TAGE=3`; das Fenster wird
  **nie gekappt** — lieber TAN-Rückfrage als stille Lücke (`abruf_fenster`/`tan_wahrscheinlich`, getestet).
  Konkrete Fenster je Bank im Bau ERHEBEN, nicht raten.
- **TAN-Verfahren** (`TanVerfahren`): zwei UI-Grundformen — **decoupled** (pushTAN: Freigabe in der Bank-App,
  Client pollt den HKTAN-Status bis Freigabe/Timeout) und **Challenge+Eingabe** (chipTAN manuell/QR, photoTAN:
  UI rendert `TanAnfrage.challenge`, Nutzer tippt die TAN). Beide sind M6-3/M6-5-Pflicht; smsTAN nur falls
  Davids Bank nichts anderes bietet (abgekündigt vielerorts).
- **Produktkennung (DK-Registrierung):** FinTS verlangt eine bei der Deutschen Kreditwirtschaft registrierte
  **Produktkennung** (kostenlos, formloser Antrag, etwas Vorlauf); python-fints erzwingt die Angabe. Kennung
  kommt aus den App-Settings (NICHT hartkodiert) → Teil von Gate **G-M6-LIB** (David registriert).
- **Rückmeldecodes:** Antworten tragen HIRMG/HIRMS-Codes (Klassen: 0xxx Erfolg · 3xxx Hinweis, z. B. 3920 =
  zugelassene TAN-Verfahren · 9xxx Fehler). Die **konkrete Code→Fehlerklassen-Tabelle wird in M6-3/M6-6 aus
  echten Antworten gefüllt** (nicht raten); Zuordnungs-REGEL steht fest: Auth-/PIN-Gruppe ⇒ `AuthFehler` ·
  TAN-Gruppe ⇒ `TanFehler` · Transport/HTTP ⇒ `VerbindungsFehler` · **unbekannt ⇒ Basis `BankSyncFehler`
  (retry_erlaubt=False, fail-closed)**.

## §3 · Datenmodell (normativ: `banksync/vertrag.py`)

| Typ | Zweck | Kern-Invarianten |
|---|---|---|
| `BankZugang` | FinTS-Zugangs-Konfiguration | frozen; Feld-Fläche EINGEFROREN (Test); nie PIN/TAN, nur `pin_vault_key`; https-Pflicht; BLZ 8-stellig; IBAN-Format; repr maskiert Kennung |
| `Scharfschaltung` | Zwei-Schlüssel-Zustand | `ist_scharf` ⇔ angelegt UND bestätigt; `pruefe_scharf(None/halb)` ⇒ `NichtScharf` |
| `TanVerfahren` / `TanAnfrage` | SCA-Datenträger für UI/Motor | TAN nie persistiert; decoupled vs. Challenge |
| `RohAuszug` | Quelle→Pipeline-Träger | roh (unangetastet); `vollstaendig=False` erreicht die Pipeline nie |
| `SyncErgebnis` | Endzustand eines Laufs | nur Terminal-Zustand; „nie still 0" (I-4) bei Konstruktion erzwungen; Fehlertext ohne Geheimnisse |
| `SyncStand` | Fortschritt je Zugang | `letzter_erfolg_bis` (Fenster-Anker) + `fehler_serie` (Backoff) |
| `UmsatzQuelle` (Protocol) | DER Quell-Vertrag | nur `quelle_id` + `hole_auszuege(von, bis)`; Impl.: `DateiQuelle` (Stufe 0, läuft) · `FinTSQuelle` (M6-3) · `AggregatorQuelle` (M6-7, gegated) |
| `als_import_auftrag` | Brücke zur Pipeline | dispatch-Felder (`inhalt/format/zielkonto/quelle`); `quelle="banksync:<id>"` |

**Persistenz (M6-1, Money-DB via `_migriere`-Hausmuster, alle mit `user_id`+`deleted_at` ⇒ DSGVO-Kaskade
automatisch):** `bank_zugaenge` (Spalten = `BankZugang`-Felder + `konto_id`-Mapping je IBAN auf ein
Money-Konto) · `bank_scharfschaltungen` · `bank_sync_staende` · `bank_sync_laeufe` (Verlauf: Ergebnis-Felder,
P8-Geist aus docs/63). PIN steht in KEINER Tabelle.

## §4 · Zustandsmaschine (normativ: `UEBERGAENGE`, vollständig getestet)

```
BEREIT → VERBINDET → AUTHENTIFIZIERT → [TAN_ERFORDERLICH ⇄] RUFT_AB ⟲ → UEBERGIBT_IMPORT → ABGESCHLOSSEN
                └─────────────┴──────────────┴──────────────┴────────────────┴→ FEHLGESCHLAGEN
                (jeder Lauf-Zustand außerdem → ABGEBROCHEN [Nutzer], außer UEBERGIBT_IMPORT)
```

Regeln: Terminale (`ABGESCHLOSSEN/FEHLGESCHLAGEN/ABGEBROCHEN`) absorbierend · `ABGESCHLOSSEN` NUR über
`UEBERGIBT_IMPORT` · jeder Lauf-Zustand kann direkt fehlschlagen (fail-closed) · `RUFT_AB`-Selbstschleife =
Aufsetzpunkt-Pagination · TAN auch MITTEN im Abruf möglich (`RUFT_AB → TAN_ERFORDERLICH → RUFT_AB`) ·
`UEBERGIBT_IMPORT` kennt kein ABGEBROCHEN (die Übergabe ist eine lokale DB-Transaktion — ganz oder gar nicht).
Der Motor (M6-4) fährt Übergänge NUR über `pruefe_uebergang` (Verstoß = `ZustandsFehler`, sichtbar).

## §5 · Fehler-Taxonomie + Retry-Politik (normativ: Klassen in `vertrag.py`)

| Klasse | Wann | `retry_erlaubt` | Nutzer-Text-Geist |
|---|---|---|---|
| `KonfigFehler` | Zugang/Aufruf strukturell ungültig | False | „Zugang unvollständig — bitte prüfen" |
| `NichtScharf` | Zwei-Schlüssel fehlt | False | „Zugang ist nicht scharfgeschaltet" |
| `VerbindungsFehler` | offline/DNS/TLS/Timeout | **True** (Backoff) | „Bank nicht erreichbar — versuche es später" |
| `AuthFehler` | PIN/Anmeldung abgewiesen | **False — NIE** | „Anmeldung abgelehnt — PIN im Vault prüfen. KEINE automatischen Wiederholungen (Sperr-Gefahr)" |
| `TanFehler` | TAN abgelehnt/Timeout | False | „TAN nicht bestätigt — bitte neu anstoßen" |
| `TeilAbrufFehler` | Aufsetzpunkt-Kette gerissen | True | „Abruf unvollständig — es wurde NICHTS importiert" |
| `FormatFehler` | Unlesbares/kein camt/MT940 | False | „Bank lieferte ein unlesbares Format" |
| `ZustandsFehler` | illegaler Motor-Übergang | False | (Programmierfehler — sichtbar machen) |

Backoff (M6-4): exponentiell über `SyncStand.fehler_serie` mit Deckel, NUR für `retry_erlaubt=True`-Klassen;
`fehler_serie` nullt bei Erfolg. Offline beim Start ⇒ sauberer `VerbindungsFehler`-Abbruch — **nie** ein
leeres „Erfolgs"-Ergebnis (I-4 erzwingt das konstruktiv).

## §6 · Secret-/TAN-Modell (appkit-Vault, OS-gebunden)

- **PIN-Fluss:** David tippt die PIN im Money-Config-UI (Kardinal-Regel 7) → `vault.put("banksync_pin_<zugang_id>", pin)`
  (`appkit.vault.Vault`: Fernet-verschlüsselt, Schlüssel DPAPI-gebunden via `secrets_os`) → DB/Settings/Repo
  sehen sie NIE. Laufzeit: `FinTSQuelle(pin_holen=vault.get)`-Naht; die PIN lebt nur im Dialog-Objekt.
  API-Responses liefern höchstens `pin_hinterlegt: bool` (nie Wert, nie Schlüssel-Liste mit Werten).
- **TAN:** ausschließlich flüchtig (Parameter im TAN-Schritt); nie DB, nie Log, nie Vault (eine TAN ist
  Sekunden gültig — Speicherung wäre nur Risiko ohne Nutzen).
- **Log-Redaktion (M6-6-Pflicht):** python-fints kann Segment-Verkehr loggen ⇒ Logging im Adapter explizit
  zähmen (Level + Schwärzungs-Filter für PIN-/TAN-Felder + Kennung); `caplog`-Test beweist „PIN taucht in
  keinem Log-Record auf".
- **Sichtbarkeit als Konnektor (Konnektivitäts-Vision):** Money registriert einen
  `FinTSKonnektor(TokenConnector)` (appkit/connectors: `richtung="lesen"`, `token_name=pin_vault_key`,
  `sensitivity="hoch"`) — der Zugang erscheint ehrlich in `/api/konnektoren` als verbunden/dormant. Der
  ABRUF läuft NICHT über den Konnektor (der ist Sichtbarkeit/Status), sondern über die `UmsatzQuelle`.

## §7 · Quelle → importers-Pipeline (Idempotenz/Dedupe)

- **Weg:** `UmsatzQuelle.hole_auszuege` → `RohAuszug` → `als_import_auftrag` → **interne** Import-Funktion
  (derselbe Codepfad wie `POST /api/import`; nie HTTP-Selbstaufruf): `parse_inhalt(inhalt, format)` →
  `Bewegung` je Umsatz → `bewegung_hash` → Buchung via Ledger; `buchungen.quelle = "banksync:fints"`.
- **Zielkonto:** je `konten_iban`-Eintrag ist beim Anlegen ein Money-Konto zugeordnet (`konto_id`-Mapping,
  M6-1); ohne Zuordnung ⇒ `KonfigFehler` (nie raten, in welches Konto Geld gebucht wird).
- **Idempotenz:** Fenster-Überlapp (3 Tage) + Pipeline-Dedupe. camt/MT940 tragen i. d. R. Bank-Referenzen
  (EndToEndId/AcctSvcrRef/:61:-Ref) ⇒ `bewegung_hash` ist eindeutig; der dokumentierte Trade-off ohne Referenz
  (common.py) bleibt unverändert gültig. **Doppel-Sync desselben Fensters = nur `duplikate`-Zähler.**
- **Bekannten 500er fixen (M6-4-Akzeptanz):** der in money dokumentierte UNIQUE(import_hash)-Race
  („paralleler Doppel-Import → 500") wird im Motor-Pfad abgefangen: IntegrityError ⇒ als Dublette zählen,
  nie 500. (Der Sync macht den Fall wahrscheinlicher — deshalb gehört der Fix in DIESES Paket.)
- **Leer-Bestätigung:** `leer_bestaetigt=True` NUR wenn der Dialog sauber endete (HKEND) UND die Bank den
  leeren Zeitraum aktiv gemeldet hat (Rückmeldecode „keine Umsätze" — Code in M6-3 aus echter Antwort
  verifizieren). Alles andere ⇒ FEHLGESCHLAGEN.

## §8 · Zwei-Schlüssel-Scharfschaltung + HITL (T5-Analogie)

- **Schlüssel 1 — Anlegen:** Zugang im UI erfassen + PIN in den Vault. Der Zugang ist damit KONFIGURIERT,
  aber tot (`Scharfschaltung.angelegt_am` gesetzt, `bestaetigt_am` leer ⇒ jede Verbindung wirft `NichtScharf`).
- **Schlüssel 2 — Scharfschalten:** getrennter, bewusster Akt. **Zielzustand:** eigene Route hinter
  `require_level("hochsicher")` (K1-Step-up). **Ehrlicher Befund (docs/61 §4):** pre-K1 sind
  verifiziert/hochsicher-Routen inert (immer 403) ⇒ **Übergangs-Weg T5-analog:** lokales, bewusstes
  ops-Skript/Settings-Flip am Rechner (Nutzer-Go) setzt `bestaetigt_am`; die HTTP-Route bleibt der Endzustand
  und ersetzt den Übergangs-Weg, sobald K1-Step-up live ist. Genau das Zwei-Schlüssel-Muster von FP-T5
  (pre-staged + zweiter bewusster Akt). Senken (Entschärfen) ist IMMER sofort erlaubt (ein Klick).
- **HITL im Betrieb:** v1 = JEDER Sync ist ein manueller „Jetzt abrufen"-Klick; die bankseitige SCA (TAN) ist
  eine zweite, unabhängige HITL-Ebene. **Auto-/Hintergrund-Sync ist bewusst NICHT in v1** — falls später
  agentisch angestoßen: `geld`-Aktionsklasse ⇒ **immer `pre_approval`** (docs/63 §4 `KLASSEN_BODEN`,
  nicht konfigurierbar) — Bank-Sync-Vorschläge laufen dann durch die K4-Inbox.

## §9 · Editionen (docs/56) + AISP-Rechtslage

| Edition | Bank-Sync-Pfad | Begründung |
|---|---|---|
| **E-LOKAL** | **FinTS direkt** (0 €/Monat): Software läuft beim Kontoinhaber, Credentials im lokalen Vault, Abruf Client→Bank | Eigenzugriff des Kontoinhabers mit eigener Software = **kein Kontoinformationsdienst i. S. d. ZAG** (Muster kommerzieller lokaler Banking-Software). ⚠️ Laien-Einschätzung, keine Rechtsberatung — vor Kommerzialisierung anwaltlich bestätigen (in G-M6-AGGREGATOR-Kontext mit erfragen) |
| **E-HYBRID** | Default weiter FinTS lokal; **optional** Aggregator-Schiene (Opt-in, gegated) | Hybrid hält Bankdaten lokal, solange der Nutzer nichts anderes wählt (docs/56 §4: sensible Daten ⇒ konservativste Wahl) |
| **E-SERVER** | **NUR Aggregator** (lizenzierter AISP: Kandidaten GoCardless Bank Account Data / finAPI / Tink — Recherche im Gate): eigener Server-Abruf fremder Konten wäre erlaubnispflichtiger Kontoinformationsdienst ⇒ bauen wir NICHT selbst | Lizenzpflicht umgangen, indem der lizenzierte Dritte abruft; `AggregatorQuelle` implementiert DENSELBEN `UmsatzQuelle`-Vertrag (liefert camt/JSON→Mapper, gleiche Pipeline) |

Edition-Default-Auflösung nach dem docs/63 §4-Muster (Edition-abhängige Grundeinstellung, fail-closed:
ungesetzt ⇒ FinTS-lokal bzw. in E-SERVER ⇒ aus, bis Aggregator konfiguriert). **Revolut** (Anforderung
docs/02) hat kein FinTS ⇒ läuft NUR über die Aggregator-Schiene oder weiter manuell (CSV/camt) — Teil von
G-M6-AGGREGATOR.

## §10 · Bibliotheks-Bewertung: python-fints — Kandidat JA, mit Auflagen

- **★ Lizenz-KORREKTUR (Ehrlichkeit vor Aktivität):** python-fints ist **LGPL-3.0, NICHT MIT** (Auftragstext
  M-6 irrte; verifiziert 03.07.2026: PyPI `fints` + GitHub raphaelm/python-fints). Kommerz-Verträglichkeit
  (alle Editionen inkl. Kauf/Abo): **ok bei Nutzung als unmodifizierte Import-Dependency**, Auflagen:
  (a) nie forken/vendorn (Copyleft griffe auf Änderungen), (b) LGPL-Lizenztext in der Auslieferung
  mitführen, (c) **Austauschbarkeit wahren** — bei Installer-/Bundle-Auslieferung (docs/56, Tauri/PyInstaller
  o. Ä.) muss das Paket ersetzbar bleiben ⇒ LGPL-Compliance-Punkt in die docs/56 §6 R-G-Checkliste aufnehmen.
  Genau dafür bleibt python-fints **vollständig hinter `FinTSQuelle` gekapselt** (austauschbar, testbar).
- **Fähigkeiten:** FinTS 3.0 PIN/TAN; Statements (HKKAZ/HKCAZ), Salden, Depots; **ABER auch SEPA-Überweisung/
  Lastschrift** ⇒ I-1-Auflage: der Adapter importiert/exponiert AUSSCHLIESSLICH Lese-Funktionen; Segment-
  Whitelist-Audit in M6-3 + Review-Pflicht „kein Transfer-Symbol referenziert".
- **Netz-Sicherheit:** reines Python auf requests/TLS (certifi); kein Binär-Blob; PSD2-TAN-Mechanik gepflegt
  (Henryk Plötz' psd2-Arbeit ist upstream); Bank-Dialekte erfordern laufende Pflege ⇒ Versions-Pin +
  Changelog-Blick bei Updates. Produktkennung Pflicht (§2).
- **Alternativen abgelehnt:** Eigenbau des Wire-Formats (Segment-/BPD-Irrsinn, verletzt Gesetz 4 ohne
  Not) · aqbanking (C/GPL, Prozess-Brücke) · Screen-Scraping (fragil, AGB-widrig). **Installation erst in
  M6-3 nach G-M6-LIB** — dieses Paket hat nichts installiert.

## §11 · Schnitt: appkit vs. moneyapp — Entscheid **Money-lokal**

**Entscheidung:** Der gesamte Bank-Sync wohnt in `moneyapp/banksync/`; **appkit wird nicht angefasst.**
Begründung (je 1 Zeile):
- **Einziger Konsument:** nur Money spricht FinTS; Banking-Semantik (Segmente, TAN, Aufsetzpunkt) ist
  Money-Domäne — eine appkit-Hebung wäre spekulative Generalisierung ohne zweiten Nutzer.
- **Das Generische existiert schon in appkit und wird GENUTZT statt dupliziert:** Secrets = `vault.Vault`
  (+`secrets_os`/DPAPI) · Außen-Gate = `net_safe.ist_oeffentliche_url` · Sichtbarkeit = `connectors.TokenConnector`
  · atomare Writes = `io_safe` (via Vault). Es entsteht KEIN zweites Framework.
- **Prozess-Sauberkeit:** appkit ist für App-Chats read-only (money-GESETZE) — der Bau-KI-Bau M6-1…M6-7 bleibt
  komplett im Money-Ordner, kein World-Chat-Koordinationsbedarf.
- **Hebe-Kriterium (Single-Source, ehrlich benannt):** sobald ein ZWEITER externer Sync dieselbe Mechanik
  braucht (z. B. Healthy-Wearable-Sync, Comm-Postfach-Pull), wird der GENERISCHE Kern — `SyncZustand` +
  Fehler-Taxonomie + `SyncErgebnis`/`SyncStand` (NICHT die FinTS-Spezifika) — nach `appkit/sync.py` gehoben
  (Muster `bereiche`→packages-Defork). Bis dahin: kein Vor-Bau.

## §12 · Bau-Plan für Bau-KI (commit-groß; jede Stufe: money-Suite grün, kein Verhaltenswechsel davor)

| Schritt | Inhalt | Akzeptanz |
|---|---|---|
| **M6-0 ✅** | dieses Paket: Vertrag + Stubs + Vertrags-Tests | Tests grün; 0 Bestands-Datei verändert |
| **M6-1** | Persistenz + CRUD: Tabellen §3 (idempotente `_migriere`-ALTER/CREATE), `GET/POST/DELETE /api/banksync/zugaenge` (+ Scharf-Status read-only), IBAN→`konto_id`-Zuordnung | Suite grün; Response enthält NIE pin/Vault-Werte (Test); DSGVO-Kaskade greift (user_id+deleted_at) |
| **M6-2** | Vault + Konnektor: PIN-Eingabe→`vault.put` (Feld ohne Echo), `pin_hinterlegt`-Anzeige, `FinTSKonnektor(TokenConnector)` registriert; Scharfschalt-Akt (Übergangs-Weg §8) | Konnektor „verbunden" erst mit PIN; `pruefe_scharf`-Pfad end-to-end; kein Geheimnis in Logs/Responses |
| **M6-3** | FinTS-Wire (NACH G-M6-LIB + G-M6-BANK): python-fints hinter `FinTSQuelle`; net_safe-Gate (I-7); BPD-gesteuert HKCAZ/HKKAZ; Aufsetzpunkt-Schleife; TAN decoupled + Challenge (`TanAnfrage`); Segment-Whitelist-Audit; Produktkennung aus Settings | **Kassetten-Tests** (synthetische/aufgezeichnete Dialog-Fixtures, NIE echte Bank in CI); Whitelist-Test; Rückmeldecode-Mapping begonnen |
| **M6-4** | Sync-Motor: Zustandsmaschine via `pruefe_uebergang`, `SyncErgebnis`-Bau, interne Import-Übergabe, IntegrityError⇒Dublette (der bekannte 500er, §7), `SyncStand`-Fortschreibung + Backoff (I-8), `bank_sync_laeufe`-Verlauf | „nie still 0"-Motor-Tests; Doppel-Sync gleicher Kassette ⇒ 2. Lauf nur Duplikate; Offline ⇒ `VerbindungsFehler`-Ergebnis |
| **M6-5** | UI (+U): Zugang-Formular (PIN→Vault), Scharf-Status, „Jetzt abrufen", TAN-Dialog beide Formen, Verlauf-Karte; CSP-strikt-konform (`data-dz-act`), K2.2-Token | isoliert am Scratch-Port (snapshot/eval), 0 Konsolenfehler; kein PIN-Echo im DOM |
| **M6-6** | Härtung: Log-Redaktions-Filter + `caplog`-Beweis (§6), Fehlercode-Tabelle aus echten Antworten vervollständigen, Backoff-Deckel | caplog-Test „PIN/TAN nie in Logs"; Fehlerpfade je Klasse getestet |
| **M6-7** | (gegated G-M6-AGGREGATOR, frühestens E-HYBRID-Bedarf) `AggregatorQuelle` real | eigener Vertrag-Anhang; gleiche Pipeline-Tests |

**Erstverbindung zur ECHTEN Bank = manueller, gegateter Nutzer-Akt am Rechner** (nie CI, nie Chat) — wie
Live-Neustarts. Reihenfolge M6-1→M6-2 ist auch OHNE Gates baubar; M6-3+ wartet auf §14.

## §13 · Test-Strategie

- **Heute (dieses Paket):** 37 Vertrags-Tests in `test_banksync_vertrag.py` (Money-Suite 299 grün = 262 Bestand + 37) — Zustandsmaschine vollständig
  (Absorption, fail-closed, einziger Weg zu ABGESCHLOSSEN), Retry-Politik, Geheimnis-Freiheit (Feld-Fläche +
  repr), Zwei-Schlüssel-Wächter VOR Wire, DateiQuelle→dispatch-Kompatibilität, Fenster-Politik. Netz-/DB-frei.
- **Bau:** je M-Schritt eigene Tests (Tabelle §12); FinTS-Verkehr ausschließlich über **Kassetten-Fixtures**
  (kein Live-Banking in Tests); Property-Tests für Fenster-/Dedupe-Idempotenz (Doppel-Lauf-Invariante).
- **Kommando** (Worktree-bewusst): `PYTHONPATH=<repo>\packages` + `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q` in `apps\money`.

## §14 · Gates an David — ★ STATUS NACH DAVIDS ANTWORT (03.07.2026, Sprachnachricht)

- **G-M6-BANK ✅ BEANTWORTET:** Erste Bank = **Sparda-Bank Nürnberg** (Genossenschafts-Gruppe; Davids
  TAN-App „SecureGo plus" bestätigt die Atruvia-IT-Welt). BLZ (Kandidat 76090500 — VERIFIZIEREN) +
  FinTS-URL + gewünschte IBANs werden in M6-1/M6-3 aus offiziellen Quellen/Onboarding erhoben, nicht
  geraten. **Zusatz-Anforderung Davids:** weitere Banken + „Online-Anbieter" (Revolut) müssen jederzeit
  ergänzbar sein — das ist bereits Design-Eigenschaft (n `BankZugang`-Datensätze · ein `UmsatzQuelle`-Vertrag
  für alle Quellarten · Aggregator-Schiene §9), kein Umbau nötig.
- **G-M6-TAN ✅ BEANTWORTET:** **SecureGo plus** = decoupled pushTAN mit biometrischer Freigabe am Handy
  (früher nutzte David chipTAN mit Karten-/Code-Scan — bleibt als zweiter Zweig relevant). ⇒ **M6-3 baut
  den decoupled-Zweig ZUERST** (HKTAN-Status-Polling bis Freigabe/Timeout), Challenge-Zweig (chipTAN QR)
  danach als Fallback.
- **G-M6-LIB ⏳ OFFEN — Davids Rückfrage, hier der Klartext (zwei getrennte Dinge):**
  1. **Lizenz-Okay:** python-fints (die Bibliothek, die das FinTS-Protokoll spricht) steht unter LGPL-3.0,
     nicht MIT. Für ein verkäufliches Produkt unkritisch, solange die §10-Auflagen gelten (unverändert
     nutzen, Lizenztext beilegen, austauschbar kapseln). Davids „Freigabe" = schlicht sein Okay dazu;
     Alternative wäre unverhältnismäßiger Eigenbau (§10). **Empfehlung: JA.**
  2. **FinTS-Produktkennung:** Die **D**eutsche **K**reditwirtschaft (DK = Dachverband der Banken, der
     FinTS betreibt — KEINE Bank, nichts mit DekaBank) verlangt für jede FinTS-Software eine einmalige,
     **kostenlose Registrierung**; die zugeteilte Kennung wird in jedem Dialog mitgesendet — ohne sie
     verweigern Banken den Zugang, und python-fints startet gar nicht erst. Zuteilung dauert
     erfahrungsgemäß einige Tage ⇒ das ist der „Vorlauf": **früh beantragen** (Online-Formular
     „FinTS-Produktregistrierung" auf fints.org), damit M6-3 nicht wartet. Konkrete David-Aufgabe;
     der Admin-Chat kann das Formular vorbereiten. **G-M6-LIB ist damit der einzige Blocker für M6-3.**
- **G-M6-AGGREGATOR ✅ GRUNDSATZ-JA (03.07.):** „Revolut & Co. umfangreich vorbereiten" ⇒ die Schiene
  bleibt designt (`AggregatorQuelle`, §9), und das Recherche-Paket (Kandidaten/Kosten/Datenfluss/AVV +
  anwaltliche Bestätigung der §9-Rechtslage vor Kommerzialisierung) wird in den Gesamt-Plan aufgenommen;
  die AKTIVIERUNG bleibt gegated (eigener Bau-Schritt M6-7 nach der Recherche).

## §15 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

Kein PISP/Zahlungsauslösung — **in DIESEM Modul für immer** (I-1 ist Identität des Lese-Moduls, nicht
Ausbaustufe; Davids Zahlungs-Vision = eigenes späteres Paket mit eigenem Vertrag, §16) · kein Screen-Scraping ·
keine PIN/TAN-Persistenz außerhalb Vault (TAN: nirgends) · kein Auto-/Hintergrund-Sync in v1 (§8; später nur
mit `geld`⇒`pre_approval`-Inbox) · kein OFX · kein Multi-Bank-Parallel-Sync (sequenziell reicht einem
Haushalt) · keine Live-Wechselkurse (eigener Backlog-Punkt, koppelbar NACH M6-3) · kein appkit-Umbau (§11,
Hebe-Kriterium abwarten) · keine Depot-/Wertpapier-Segmente (HKWPD o. Ä. — Trading-Welt bleibt getrennt,
docs/63 §0-Geist).

## §16 · ★ Davids Zukunfts-Vision (03.07.): Zahlungs-Schiene — NICHT M-6, eigener späterer Vertrag

**Davids Ziel (destilliert aus der Gate-Antwort):** einen Auftrag in Dizzi/Money erfassen → Einreichung bei
der Bank → **Freigabe ausschließlich über das Verifizierungssystem der Bank** (SecureGo plus, biometrisch am
Handy — „superschnell und einfach"); die Bank-App bleibt die letzte Instanz. Ultimately soll das Netz das
Banking ansteuern, David gibt nur noch die Bank-Freigabe.

**Einordnung (ehrlich):** Technisch ist das exakt der FinTS-Überweisungsweg (Auftrag einreichen +
decoupled-TAN-Freigabe) und architektonisch die natürliche Fortsetzung von M-6 — aber es ist GELD-BEWEGEND
und damit eine andere Risikoklasse. Es wird bewusst NICHT Teil dieses Vertrags (I-1 bleibt unangetastet),
sondern ein **eigenes, späteres Paket (Arbeitsname „Bank-Aktiv" / M-7)** mit eigenem Design-Vertrag, wenn
David es zündet. Verbindliche Leitplanken schon jetzt:

- **Getrenntes Modul mit EIGENER Segment-Whitelist** — die M-6-Lese-Whitelist wird NIE gelockert; ein
  Zahlungs-Modul bekäme eine eigene, minimale Fläche (Überweisungs- + TAN-Segmente) hinter eigenem Gate
  **G-M7-ZAHLUNG**.
- **Drei HITL-Ebenen, keine verhandelbar:** K4-Inbox (`geld` ⇒ IMMER `pre_approval`, docs/63 §4
  `KLASSEN_BODEN`) → hochsicher-Freigabe in Dizzi (K1-Step-up) → **Bank-SCA via SecureGo plus** (Davids
  gewünschte letzte Instanz — die Bank-App bestätigt, was Dizzi eingereicht hat).
- **Rechtlich:** lokal beim Kontoinhaber = klassisches Banking-Software-Modell (analog §9-AISP-Argument);
  vor Kommerzialisierung anwaltlich prüfen (derselbe Prüfauftrag wie §9/G-M6-AGGREGATOR).
- **Was M-6 dafür „umfangreich vorbereitet" (Davids Wunsch) — OHNE Vor-Bau:** der decoupled-TAN-Flow
  (M6-3) wird generisch als „Bank-Freigabe-Flow" gebaut, nicht abruf-spezifisch · die Dialog-/Zugangs-
  Schicht ist auftragsneutral (BPD kennt alle Geschäftsvorfälle) · das Datenmodell trägt n Banken ·
  das Zwei-Schlüssel-Muster ist wiederverwendbar. Mehr wäre Vor-Bau — bewusst nicht (§15-Geist).
