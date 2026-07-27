# 80 · V-BIZZI-1 — DzChronik-VERTRAG: Chronik-Kern + Chronist + Prüfkern (B1-Bau-Spec für Bau-KI)

> **Status: VERTRAG (V-BIZZI-1, Architektur-KI 11.07.2026, Reihe „World of Bizzi Admin", Worktree `chat/bizzi`).
> REINES DESIGN — kein Bau.** Die drei Bau-Gates sind entschieden: **G-BIZZI-MVP ✓ · G-BIZZI-POLICY-ENGINE ✓
> (Eigenbau+Cedar-Schatten) · G-BIZZI-CHRONIK ✓ (Parameter wie docs/79 §2 #3) — Davids Wort 11.07.2026.**
> **B1-Bau braucht zusätzlich Davids ausdrückliches Vorbaustein-Wort** (docs/79 §4 B1) — dieser Vertrag macht
> ihn jederzeit zündbar. Quellen (normativ absteigend): docs/79 (D1 · D7 · §1-i/ii/iii · Gate #3 · B1) ·
> docs/77 §2 (DzChronik) + §5 · Code-Grounding 11.07.: `packages/appkit/{db,io_safe,secrets_os}.py` ·
> `apps/core/app/id/keys.py` · `apps/money/moneyapp/{ledger,main}.py` (5 Schreibpfade) · docs/68 (U-6-Naht).
> Ziel-Läufer: **Bau-KI baut** (B1, ~3 Runden, §11); **Architektur-KI nimmt ab** (F5-Review gegen §10).
>
> **★ G-BZ-DELTA eingespielt 12.07.2026 (Bau-Chat, Worktree `wt-bizzi`):** die Controlling-Zweitinstanz
> `docs/84` §A (Befunde **BZ-C-1…12**) ist in diesen Vertrag eingearbeitet — 6 HOCH-Patches (BZ-C-1…6, davon
> BZ-C-1/-6 zünd-kritisch) + mittel/niedrig. **Neue Invarianten C-15…C-17**, neue §§ 6.0 (Übernahme-Ereignis),
> 4.6 (Wiederherstellungs-Verbund), 12 (Prüfnachweis für den WA-Merge). B1-Urteil docs/84 §A3:
> **„ja — mit Patches BZ-C-1…6".** Was wo eingespielt wurde: **§12**.

## §0 · Geltung + Nicht-Ziele

**Ziel:** Das beweisende Rückgrat der Bizzi-Säule als **netzweiter appkit-Baustein** (D1) — Outbox →
Chronist → append-only Segmente → Epochen/Merkle → Siegel — **plus** seine erste produktive Ernte:
**„Chronik als Dizz-Money-GoBD-Feature"** (≡ der einzige erlaubte Vorbaustein ≡ Money-M-2-Unterbau).
Nach B1 gilt ehrlich: *„Chronik produktiv als GoBD-Feature in Dizz Money"* — Festschreibung eines
EÜR-Monats ist ein kryptographischer Akt (§146(4) AO-Nachvollziehbarkeit), und `bizzi-pruef` existiert
als Misstrauens-Werkzeug („Trauen Sie uns nicht — rechnen Sie nach").

**Nicht-Ziele (B1):** KEINE Zeugen/Kollegium/Attestation (B7, `bizzikit`) · keine Charta/Entscheide
(B2 — `entscheid_id` wird nur als leere Spalte vorbereitet) · keine FiBu-Profile/SKR (B3) · keine
Anker-Gestaltung (B7, Gate #15) · kein TPM (Gate #12, ◇) · keine Chronik-Pflicht für andere Apps
(v1-Quelle = nur money; Erweiterung = Konfig-Eintrag, kein Umbau) · **kein Verhaltens-Bruch
irgendeines bestehenden Endpoints** (D5-Geist: alles additiv).

## §1 · Härtungs-Invarianten (nummeriert; Enforcement-Ort verbindlich)

| # | Invariante | Enforcement |
|---|---|---|
| C-1 | **Atomarität:** die Outbox-Zeile entsteht in **derselben** `db.transaktion()` wie die Tabellen-Mutation; `chronik.schreibe()` committet NIE selbst (db.py-Warnung gilt); Commit = beide Wahrheiten oder keine | `chronik.schreibe(conn, …)` nimmt die offene Conn; Test: Rollback ⇒ keine Outbox-Zeile |
| C-2 | **Kanon fail-loud:** Nutzlast nur aus `str/int/bool/None/dict/list`; `float`/NaN ⇒ `ChronikFehler` VOR Commit; `int` nur \|n\| ≤ 2^53−1; **Geldbeträge sind Dezimal-Strings** (Minor-Units), nie JSON-Numbers — `MAX_MINOR` = 2^63−1 > 2^53 würde RFC-8785-Zahlen verlustbehaftet machen | `kanon()`-Wächter (Tests: Grenzen, float, verschachtelt) |
| C-3 | **Datenklassen-Zwang:** unbekannte `art` ⇒ Fehler; Freitext-Felder erreichen die Nutzlast NUR als Feld-Hashes (gepfeffert, C-15), wenn die Klasse es verlangt (§3); hash_only-Klassen tragen keine Nutzlast (`"nutzlast":""`) | `KLASSEN`-Registry + `schreibe()`-Wächter (Tests je Klasse) |
| C-4 | **Kette:** `h_n = SHA-256(h_{n−1} ‖ JCS(zeile_ohne_sig))`; `sig` = Ed25519 über `h_n`; Zeile wird ge-`fsync`t BEVOR `epoche` in der App-DB gestempelt wird | `chronist`-Übernahme (Property-Tests: 1-Bit-Flip ⇒ Bruch) |
| C-5 | **Idempotenz:** Übernahme ist über `(app, i)` idempotent; Crash zwischen fsync und Stempel ⇒ beim Recovery wird NUR nachgestempelt, nie doppelt angehängt; **nachgestempelt wird nur bei identischem `nutzlast_hash`** — Hash-Differenz ⇒ FORK-Stopp (C-16) | Übernahme-Algorithmus §4.2 (Crash-Tests §7) |
| C-6 | **Epochen-Schließregel (docs/79 §1-i, exakt):** Epoche schließt bei **4096 Ereignissen** ODER wenn das **älteste unversiegelte Ereignis > 60 s** alt ist ODER bei **Flush** (siegelpflichtiger Antrag); **leere Epochen entstehen nie** (lazy öffnen); Ereignis-`ts` in der Zukunft gilt für Schließregel/Alarm als sofort fällig (Alter = ∞) + GELB-Log „Uhr-Anomalie" (BZ-C-11) | `chronist`-Tick (Tests: alle drei Trigger + nie-leer + Uhr-Rücksprung) |
| C-7 | **Merkle:** Blatt = `h_n`; Domain-Separation `0x00` (Blatt) / `0x01` (Knoten); ungerades Element steigt **unverändert** auf (kein Duplizieren — CVE-2012-2459-Klasse); Einschluss-Beweise je Blatt prüfbar | `chronik.merkle_*` (Property-Tests Größen 1…17) |
| C-8 | **Siegel:** quorum-parametrisch (1 / 2-of-3 / 3-of-5 — Gate #3); v1 aktiv = **quorum=1 Selbstsiegel des Chronisten**; `prev_siegel`-Kette; Siegel-Dateien via `io_safe` atomar | `chronist.siegle()` + `chronik_pruef` (Golden) |
| C-9 | **Festschreibung fail-closed:** ohne Siegel der deckenden Epoche KEINE Festschreibungs-Bestätigung (Chronist tot ⇒ Fehler, nie „ok"); Buchungs-Schreibpfade in versiegelte Zeiträume ⇒ **409** mit Klartext-Hinweis; Korrektur nur als Gegenbuchung im offenen Zeitraum | `festschreibung`-Strecke §6.3 (e2e-Tests) |
| C-10 | **Retention-Immunität strukturell:** `chronik_ausgang` hat **keine `user_id`-Spalte** ⇒ `retention_lauf`/`soft_delete_user`/`export_user` (arbeiten über `user_tabellen()` = user_id-Filter) fassen sie per Konstruktion nie an — die Chronik erleidet nicht das `audit_log`-Schicksal (docs/77-Grounding) | Schema §2.2 + Test, der die Spaltenliste festschreibt |
| C-11 | **Bestand unangetastet:** `ledger.py` bleibt **byte-identisch** (`git diff` leer — docs/79 §1-iii); kein bestehender Endpoint ändert Response/Statuscode; alle Money- und appkit-Bestands-Tests bleiben grün (Zahlen §10, beim DoD-Durchlauf nachgeführt) | DoD §10 (mechanisch geprüft) |
| C-12 | **Schlüssel-Disziplin:** Stamm-, Chronist-Schlüssel + Feld-Hash-Pfeffer (C-15) via `secrets_os` (DPAPI, atomar); nie in Repo/Chat; Nicht-Windows-Klartext-Fallback bleibt ehrlich über `verfuegbar()` angesagt | Ablage §2.6 (Muster `keys.py`) |
| C-13 | **Ein Prüfkern, drei Pflichten (docs/79 §1-ii):** `chronik_pruef` läuft identisch als Offline-CLI, als pytest-Golden-Harness und (ab B4) als EXTF-Rückspiel-Wächter — kein Drift zwischen „was wir testen" und „was der Prüfer prüft" | ein Modul, drei Einstiege (§5) |
| C-14 | **Ein Schreiber:** genau EIN Chronist je Instanz über eine **OS-erzwungene exklusive Datei-Sperre** (Windows `msvcrt.locking` / POSIX `flock` — lebt und stirbt mit dem Prozess, **keine Alters-Übernahme**); Segment-Schreiben ohne gehaltene Sperre = Programmierfehler ⇒ fail-loud | Lock §4.4 (Test: zweiter Tick blockiert/bricht ab, solange die OS-Sperre steht) |
| C-15 | **Feld-Hash-Pfeffer (BZ-C-6):** `feld_hash()` und der `nutzlast_hash` von **hash_only**-Klassen sind **HMAC-SHA-256 mit Instanz-Pfeffer** (`pfeffer.bin`, §2.6) — ohne Pfeffer kein Wörterbuch-Rückschluss auf Namen/Zwecke; Format `"hmac256:<hex64>"`. `nutzlast_hash` von voll/struktur-Klassen (Integritäts-Anker über `kanon()`) bleibt `sha256:` | `feld_hash`-Wächter (Test: ohne Pfeffer-Datei ⇒ Fehler; je Instanz stabil, über Instanzen verschieden) |
| C-16 | **Fork-Schutz (BZ-C-3):** Nachstempeln nur bei identischem `nutzlast_hash` (C-5); Hash-Differenz an `(app,i)` ⇒ Chronist stoppt diese Quelle fail-loud (`status.json:"fork_verdacht"` + `defense.event_hook`), kein Stempeln; App-DB + `data\chronik\` sind EIN Restore-Verbund (§4.6) | §4.2/§4.6 (Restore-Simulations-Test §7) |
| C-17 | **Format-Evolution (BZ-C-9):** `kanon()` erzwingt ASCII-Objekt-Schlüssel (`^[a-z0-9_.]+$`) ⇒ RFC-8785-Identität bewiesen statt behauptet; jede Änderung am Zeilen-/Siegel-Format ist additiv und wird als `chronik.format`-Ereignis in der Kette selbst angekündigt; `chronik_pruef` prüft versions-bewusst | §2.1 + Kanon-Test (Nicht-ASCII-Schlüssel ⇒ Fehler) |

## §2 · Formate (normativ — Bau-KI hat hier keine Freiheitsgrade)

### 2.1 Kanon `kanon(obj) -> str` (RFC-8785-konform durch Subset-Disziplin)
JCS in voller Allgemeinheit braucht ES6-Zahlen-Serialisierung. Wir **verbieten die Problemfälle** statt sie
nachzubauen — auf dem erlaubten Subset ist `json.dumps(obj, ensure_ascii=False, sort_keys=True,
separators=(",", ":"))` **exakt RFC-8785-identisch** (UTF-8, sortierte Keys, keine Whitespaces):
- erlaubt: `dict` (str-Keys, **ASCII** `^[a-z0-9_.]+$`) · `list` · `str` · `bool` · `None` · `int` mit \|n\| ≤ 2^53−1;
- verboten (⇒ `ChronikFehler`, fail-loud VOR Commit): `float` (inkl. NaN/Inf), `int` > 2^53−1, **Nicht-ASCII-Objekt-Schlüssel**, alle anderen Typen;
- **Geld-Regel:** Beträge in Minor-Units als **Dezimal-String** (`"betrag_minor": "1250"`, Vorzeichen erlaubt) —
  konsistent mit „Geld ist nie Float" (ledger.py) und immun gegen Zahlen-Semantik jeder JSON-Implementierung.
- Hashes im Format `"sha256:<hex64>"` (Integritäts-Anker) bzw. `"hmac256:<hex64>"` (gepfefferte Feld-/hash_only-Hashes, C-15) · Signaturen `"ed25519:<kid>:<base64url>"` · Zeiten ISO-8601 UTC (`now_iso()`-Format).
- **ASCII-Schlüssel-Begründung (BZ-C-9):** RFC 8785 sortiert Schlüssel nach UTF-16-Code-Units, Python nach Codepoints — für Schlüssel außerhalb der BMP divergieren die Bytes. Auf dem ASCII-Subset ist die RFC-8785-Identität **bewiesen** (Schlüssel sind ohnehin schema-eigene Bezeichner; Nutzdaten stehen in den Werten, die RFC-konform serialisiert werden). Ein Prüfer mit Fremd-Implementierung rechnet bit-gleich nach.

**Format-Evolution (C-17):** Änderungen am Zeilen-/Siegel-Format sind **additiv**; jeder Wechsel wird als
Ereignis `chronik.format` (voll: `{von, nach, felder}`) in der Kette selbst angekündigt, bevor das neue
Feld auftritt. `chronik_pruef` liest die aktive Format-Version aus der Kette und prüft versions-bewusst
(B2 ist ihr erster Konsument: `entscheid_hash`).

### 2.2 Outbox `chronik_ausgang` (je Quell-DB; Schema-Konstante `appkit/chronik.py::AUSGANG_SCHEMA`)
```sql
CREATE TABLE IF NOT EXISTS chronik_ausgang (
  i            INTEGER PRIMARY KEY AUTOINCREMENT,  -- strikte Totalordnung JE App-DB
  art          TEXT NOT NULL,                      -- Datenklassen-Schlüssel (§3), z. B. 'money.buchung'
  nutzlast     TEXT NOT NULL,                      -- kanon()-Ausgabe ('' bei hash_only-Klassen)
  nutzlast_hash TEXT NOT NULL,                     -- 'sha256:…' (voll/struktur) | 'hmac256:…' (hash_only, C-15) — IMMER gesetzt
  entscheid_id TEXT NOT NULL DEFAULT '',           -- Charta-Bindung ab B2; v1 immer ''
  subjekt      TEXT NOT NULL,                      -- 'u:<user_id>' | 'system' | später 'agent:<id>'
  created_at   TEXT NOT NULL,
  epoche       INTEGER                             -- NULL bis vom Chronisten übernommen (= Rückstands-Messgröße)
);
CREATE INDEX IF NOT EXISTS idx_chronik_ausgang_offen ON chronik_ausgang (epoche) WHERE epoche IS NULL;
```
**Bewusst KEINE `user_id`-Spalte** (C-10) — das Subjekt lebt im Ereignis. **`subjekt` trägt ausschließlich
die opake user_id** (`'u:<uuid>'`, `db.py:103` = `uuid4`) — **NIE Login-/Anzeigename** (BZ-C-10; sonst
kollabiert das Pseudonymitäts-Argument aus §3). Die Konstante wird von der nutzenden App an ihr
`extra_schema` gehängt (v1: nur money) — **kein Eingriff in `_BASE_SCHEMA`**, keine netzweite Schema-Änderung
durch den Vorbaustein.

### 2.3 Segment-Zeile + Kette
Segment-Datei je Epoche: `E<epoche 8-stellig>.dzc`, **JSON-Lines**, nur Append (O_APPEND). Eine Zeile =
`kanon()` des vollständigen Objekts (inkl. `sig`) + `\n`:
```json
{"n":48211,"app":"money","i":9317,"ts":"2026-07-08T21:14:03+00:00","art":"money.buchung",
 "subjekt":"u:7f3a…","entscheid":"","nutzlast_hash":"sha256:ab12…","nutzlast":{…},
 "prev":"sha256:9c0d…","sig":"ed25519:kid…:MEQ…"}
```
- `n` = globale, epochenübergreifend fortlaufende Nummer (beginnt bei 1, nie zurückgesetzt);
  `ts` = `created_at` der Outbox-Zeile (App-Behauptung; Beweiszeit ist IMMER die Siegel-Zeit — docs/77 §2.6).
- **hash_only-Zeilen** tragen `"nutzlast":""` und `nutzlast_hash` als `"hmac256:…"` (C-15); voll/struktur tragen die kanonische Nutzlast + `"sha256:…"`.
- **Kette:** `h_n = SHA-256( h_{n−1} ‖ UTF8(kanon(zeile_ohne_sig)) )`; `h_{n−1}` als 32 Roh-Bytes.
  `prev` der Zeile n trägt `h_{n−1}` als `"sha256:<hex>"` (redundant zur Rechnung — macht Segmente einzeln lesbar).
- **Genesis:** Zeile `n=1` ist IMMER `{"app":"chronik","i":0,"art":"chronik.genesis","subjekt":"system",
  "nutzlast":{"version":"1","angelegt":"<ts>","stamm_kid":"<thumbprint>"}}` mit `prev = "sha256:" + "0"×64`.
- **Signatur:** `sig = Ed25519(h_n)` (32-Byte-Digest wird signiert), base64url; `kid` = JWK-Thumbprint des
  Chronist-Schlüssels. Verifikation: Zeile parsen → `sig` entfernen → `kanon()` → `h_n` rechnen → Signatur prüfen.

### 2.4 Epoche + Merkle
- Epochen-Nummern fortlaufend ab 1; **Schließregel = C-6** (4096 ∨ ältestes-unversiegelt > 60 s ∨ Flush).
- **Merkle über die Epoche:** Blätter = `h_n` aller Zeilen der Epoche in Ketten-Reihenfolge.
  `blatt = SHA-256(0x00 ‖ h_n)` · `knoten = SHA-256(0x01 ‖ links ‖ rechts)` · ungerades Element steigt
  unverändert auf. Wurzel = `wurzel` der Epoche.
- **Einschluss-Beweis** (Basis der Notar-Anker B7; v1 baubar + prüfbar): `{"epoche":1234,"n":48211,
  "blatt":"sha256:…","pfad":[{"seite":"L","hash":"sha256:…"},…],"wurzel":"sha256:…"}`.

### 2.5 Siegel (Datei `S<epoche 8-stellig>.json`, io_safe-atomar)
```json
{"epoche":1234,"wurzel":"sha256:…","prev_siegel":"sha256:…","ereignisse":4096,
 "von_n":44116,"bis_n":48211,"zeit":"2026-07-08T21:14:09+00:00","quorum":1,
 "zeugen":[{"id":"chronist","kid":"…","sig":"ed25519:…:…"}]}
```
- Signiert wird `SHA-256(UTF8(kanon(siegel_ohne_zeugen)))`; `prev_siegel` = dieser Hash des Vorgänger-Siegels
  (Genesis-Epoche: `"sha256:" + "0"×64`) — die Siegel bilden ihre eigene Kette.
- **Quorum-Parametrik (Gate #3):** `quorum=1` (persönliche Edition/Money-M-2 — Selbstsiegel) · `2-of-3`
  (Bizzi S/M) · `3-of-5` (L/XL). v1 implementiert quorum=1 vollständig; das Format trägt Mehr-Zeugen ab
  Tag 1 (B7 ergänzt nur Zeugen-Prozesse + Runden-Protokoll in `bizzikit`, kein Format-Bruch).

### 2.6 Schlüssel + Schlüsselbrief + Pfeffer (Muster = `core/app/id/keys.py`, Zweckbindung getrennt)
- **Eigene Schlüssel, NIE der IdP-Key** (Signatur-Domänen nicht mischen): `data\chronik\stamm_key.json`
  (Instanz-Stammschlüssel) + `data\chronik\chronist_key.json` (Arbeitsschlüssel) — beide Ed25519-JWK
  (joserfc `OKPKey`, `kid` = Thumbprint), Ablage via `secrets_os.schreibe_geheim/lese_geheim` (DPAPI, atomar),
  erzeugt beim ersten Chronist-Start (C-12).
- **Feld-Hash-Pfeffer (C-15, BZ-C-6):** `data\chronik\pfeffer.bin` — 32 zufällige Bytes, erzeugt beim ersten
  Chronist-Start, Ablage via `secrets_os` wie die Schlüssel. `feld_hash(text)` und hash_only-`nutzlast_hash`
  sind `"hmac256:" + HMAC-SHA-256(pfeffer, UTF8(text))`. **Ohne Pfeffer** ist ein Feld-Hash nicht gegen ein
  Wörterbuch rückrechenbar; die kontrollierte Herausgabe (Prüfer-Fall) läuft über `bizzi-pruef … --pfeffer`
  (§5). Verlust des Pfeffers macht künftige Freitext-/hash_only-Verifikation unmöglich, lässt aber
  Kette/Signaturen/Salden-Replay unberührt (§9, Aufbewahrungs-Verbund).
- **Roh-Signaturen** über `cryptography.hazmat…Ed25519PrivateKey` (vorhandene transitive Dependency von
  joserfc — **keine neue Dependency**); JWK↔cryptography-Konvertierung in `chronik.py` gekapselt.
- **Schlüsselbrief** `data\chronik\schluesselbrief.json`: `kanon`-JSON `{"modul":"chronist","kid":"…",
  "pubkey":{öffentliches JWK},"gueltig_ab":"…"}` + `"brief_sig"` = Ed25519(Stammschlüssel) über den
  kanon-Hash. `chronik_pruef` verifiziert: Stamm beglaubigt Chronist, Chronist signiert Zeilen/Siegel.
  (Öffentliche Schlüssel liegen zusätzlich als `stamm_pub.json` im Chronik-Verzeichnis — der Prüfer braucht
  kein DPAPI.)

### 2.7 Dateilayout (Laufzeit-Daten, außerhalb Repo)
```
C:\Dizzik\data\chronik\
  segmente\E00000001.dzc …      (append-only; nur der Chronist schreibt — ACL-Härtung §4.5)
  siegel\S00000001.json …       (io_safe-atomar)
  stamm_key.json · chronist_key.json · stamm_pub.json · schluesselbrief.json
  pfeffer.bin                   (Feld-Hash-Pfeffer, C-15; secrets_os/DPAPI; Teil des Aufbewahrungs-Verbunds)
  status.json                   (NUR Cache/Anzeige: letztes n/h, je App letztes i, offene Epoche,
                                 Rückstand, fork_verdacht — Wahrheit sind IMMER die Segmente; Rebuild beim Start möglich)
  chronist.lock                 (Instanz-Lock, C-14 — OS-erzwungene exklusive Datei-Sperre)
```

## §3 · Datenklassen-Tabelle v1 (≡ Prüfvorlage für G-BIZZI-SCHREDDER — anwaltlich gegenzuprüfen vor Pilot)

**Klassen-Mechanik:** `voll` = kanonische Nutzlast komplett in der Kette · `struktur` = strukturierte
Kerndaten in der Kette, **Freitexte nur als gepfefferte Feld-Hashes** (`hmac256:` über UTF-8, C-15; leere
Felder entfallen) · `hash_only` = Kette trägt nur `nutzlast_hash` (gepfeffert), Daten leben in App-Tabellen
(Soft-Delete/Retention wie gehabt) ⇒ **Krypto-Schreddern**: Löschung tötet die Daten, der Hash beweist nur
noch „da war etwas Bestimmtes".

**Klassenübergreifende Freitext-Regel (BZ-C-8):** Auch in **voll**-Klassen erreichen personenbezogene
Freitexte (Namen, Verwendungszwecke, IBAN) die Nutzlast **nur als gepfefferte Feld-Hashes** — „voll" meint
die strukturierte Steuer-Nutzlast (C-3 gilt klassenübergreifend). V-BIZZI-3/6 definieren ihre Feldlisten
unter dieser Regel (deckt die Gate-#3-Zusage „fibu.*/ap.* voll in Kette" ohne Klartext-Personenbezug).

| `art` | Klasse | Inhalt in der Kette | Rechtsgrund / Löschverhalten |
|---|---|---|---|
| `chronik.genesis` | voll | version, angelegt, stamm_kid | technisch; kein Personenbezug |
| `chronik.format` | voll | von, nach, felder | technisch (Format-Evolution C-17); kein Personenbezug |
| `money.uebernahme` | voll | stichtag, letzte_buchung_rowid, konten [{konto_id, saldo_minor als String}] | technischer Anker des Chronik-Anschlusses an Bestandsdaten (§6.0, BZ-C-1); kein Freitext |
| `money.buchung` | **struktur** | buchung_id, datum, quelle, bereich_id?, kategorie_id?, postings [{konto_id, betrag_minor als String}], notiz_hash?, gegenpartei_hash?, verwendungszweck_hash? | §147 AO/GoBD-Geist (Kerndaten); Freitexte (Namen!) nur als gepfefferter Hash ⇒ Konto-Löschung (KA-H1) bleibt vollziehbar; verbleibendes Buchungs-Gerippe ist pseudonym (UUIDs ohne Auflösungstabelle) |
| `money.storno` | struktur | buchung_id, datum_storno, **postings** (invertierte Gegenwerte — self-contained, deckt auch Vor-Genesis-Stornos, BZ-C-1) | wie `money.buchung` |
| `money.umklassung` | struktur | buchung_id, kategorie_id | GoBD-Journalfunktion (Umkategorisierung im offenen Zeitraum, §6.2, BZ-C-2); kein Freitext |
| `money.beleg` | struktur | buchung_id, beleg_titel_hash?, beleg_ref_hash? | Nachvollziehbarkeit der Belegzuordnung (§6.2, BZ-C-2); Freitexte nur als gepfefferter Hash |
| `money.festschreibung` | voll | zeitraum "YYYY-MM", bis_i (letzte gedeckte Outbox-Nr.), salden_hash (§6.3), beweisgrad ("voll" \| "db-stand", §6.0) | §146(4) AO — der Zweck des Features; kein Freitext |
| `money.ustva_freigabe` | voll | zeitraum, quell_stand (sha256 aus docs/68 U-6), zahllast_minor als String | Steuer-Nutzlast, Art. 17(3)(b) DSGVO deckt; **Slot** — verdrahtet erst, wenn der finale M-2-Freigabe-Akt existiert (kein toter Code in B1) |
| `charta.version` | voll (reserviert B2) | policy_version, artikel_hash | Policy-Replay-Basis |
| `fibu.*` / `ap.*` | voll (reserviert B3/B6) | per V-BIZZI-3/6, unter der Freitext-Regel oben | Gate #3: „fibu.*/ap.* voll in Kette" (strukturierte Steuer-Nutzlast; Freitexte gepfeffert) |
| `verzeichnis.*` / `botschaft.*` | hash_only (reserviert B5/B7+) | nur nutzlast_hash (gepfeffert, C-15) | Gate #3; Personendaten bleiben löschbar |

**Naht zum frischen Core-Lösch-Pfad (KA-H1, verbindlich):** Segmente sind append-only — deshalb dürfen
personenbezogene **Klartexte strukturell nie** hinein (genau das erzwingt C-3). Die Konto-Löschung löscht
zusätzlich **unübernommene** Outbox-Zeilen des Subjekts mit (`epoche IS NULL` — sie sind noch kein Beweis);
übernommene Zeilen bleiben als pseudonymes Gerippe.
**§147-AO-Kaskaden-Ausnahme (BZ-C-7):** money nimmt `buchungen`, `postings`, `festschreibungen` von der
Lösch-Kaskade AUS, solange die §147-AO-Frist läuft (Art. 17(3)(b) DSGVO deckt es) — Konto-Löschung in money =
Stammdaten + Freitexte; das Buchungs-Gerippe bleibt pseudonym (subjekt-UUID ohne Auflösungstabelle). Der
Lösch-Lauf toleriert, dass der Chronist eine `epoche IS NULL`-Zeile im Crash-Fenster schon übernommen hat
(das Stempel-`UPDATE` trifft dann 0 Zeilen = legal, wird nur gezählt — nie Fehler). Das ist die
Art.-17(3)(b)-Grenzziehung dieser Tabelle — der Anwaltstermin (Gate #14) prüft GENAU diese Spalte
„Löschverhalten" + die Ausnahme-Liste + die Frist-Ablauf-Frage (docs/84 §A2 P-7).

## §4 · Der Chronist (`appkit/chronist.py`)

### 4.1 Architektur: Tick-Modell, kein Daemon
Der Chronist läuft als **Tick** (`python -m appkit.chronist --tick`, venv-Python): ein Durchlauf übernimmt
alle offenen Outbox-Zeilen, schließt fällige Epochen, siegelt, endet. Start-Modell §4.5. Quellen-Registry v1 =
Konstante/Konfig `data\chronik\quellen.json`: `[{"app":"money","db":"<default_db_path('money')>"}]` —
eine weitere App = ein Eintrag (KEIN Code-Umbau; genau die D1-Pointe: der Kern ist appkit, netzweit ladbar).

### 4.2 Übernahme-Algorithmus (ein Tick; Reihenfolge ist Vertragsbestandteil)
1. **Instanz-Lock nehmen** (§4.4) — sonst sauberer Abbruch („Chronist läuft bereits").
2. **Recovery-Scan:** offenes Segment lesen; letzte Zeile kein vollständiges JSON (torn write) ⇒ Datei auf die
   letzte vollständige Zeile kürzen (die EINZIGE erlaubte Nicht-Append-Operation; nur auf unversiegelten
   Segmenten; Zähler in status.json). Kopf laden: letztes `n`/`h_n`, je App letztes übernommenes `i`
   (status.json ist Cache; bei Inkonsistenz Segmente scannen — Segmente sind die Wahrheit).
3. **Je Quelle:** `SELECT i, art, nutzlast, nutzlast_hash, entscheid_id, subjekt, created_at FROM
   chronik_ausgang WHERE epoche IS NULL ORDER BY i` —
   - `(app,i)` bereits im Segment (Crash nach fsync, vor Stempel): **nachstempeln nur, wenn der `nutzlast_hash`
     der Outbox-Zeile mit dem der Segment-Zeile übereinstimmt** (C-5) ⇒ `epoche` nachstempeln. **Hash-Differenz
     ⇒ FORK-Befund (C-16):** Chronist stoppt diese Quelle fail-loud (kein Stempeln, keine Übernahme), meldet
     über `defense.event_hook` + `status.json:"fork_verdacht"` und wartet auf manuelle Klärung (§4.6). Ein
     Stempel-`UPDATE` mit 0 getroffenen Zeilen (Outbox-Zeile zwischenzeitlich gelöscht, §3-Naht) ist dagegen
     legal und wird nur gezählt.
   - sonst: Zeile bauen (§2.3), an Segment anhängen; **fsync vor jedem Stempel-Batch** (C-4); dann in kurzer
     eigener Txn `UPDATE chronik_ausgang SET epoche=? WHERE i=?`.
4. **Schließregel prüfen (C-6):** fällig ⇒ Merkle bauen, Siegel signieren + atomar schreiben, status.json
   aktualisieren; nächste Epoche **lazy** öffnen (erst beim nächsten Ereignis — leere Epochen nie).
   Ereignis-`ts` in der Zukunft ⇒ Alter = ∞ (sofort fällig) + GELB-Log „Uhr-Anomalie" (BZ-C-11).
5. **Rückstand melden:** `epoche IS NULL`-Zähler + Alter des ältesten offenen Ereignisses → status.json;
   Überschreitung (Default: > 15 min Alter; Zukunfts-`ts` zählt als sofort fällig) ⇒ Alarm über
   `defense.event_hook` der Quelle-App (docs/77 §2.6).

### 4.3 `flush_und_warte(zeitraum_deadline_s: float) -> Siegel`
Für siegelpflichtige Akte (Festschreibung §6.3). Persönliche Edition (quorum=1): direkter In-Process-Aufruf
`chronist.tick(flush=True)` unter dem Instanz-Lock (wartet aufs Lock, wenn der Task-Tick gerade läuft).
Bizzi-Editionen (getrennte Konten): Datei-Watch auf das erwartete Siegel mit Timeout. **Timeout ⇒ Fehler,
nie „ok"** (C-9). Rückgabe = geparstes, verifiziertes Siegel der deckenden Epoche. **Aufruf-Reihenfolge
(BZ-C-5):** `flush_und_warte()` wird immer NACH dem Commit der auslösenden `db.transaktion()` gerufen — der
Chronist liest nur Committetes, ein Aufruf innerhalb der offenen Txn liefe per Design in den Timeout.

### 4.4 Instanz-Lock (C-14, BZ-C-4)
`chronist.lock` wird als **OS-erzwungene exklusive Datei-Sperre** gehalten (Windows: `msvcrt.locking`
bzw. `CreateFile` ohne Share-Mode; POSIX: `flock`) — die Sperre lebt und stirbt mit dem Prozess; das OS gibt
sie bei Prozess-Ende frei. **Es gibt KEINE Alters-Übernahme** (kein „PID tot / älter als N min"-Heuristik: sie
ist unter Windows-PID-Wiederverwendung unzuverlässig und erlaubt bei Standby/IO-Blockade zwei Schreiber). Ein
hängender Chronist äußert sich als Rückstands-Alarm (§4.2 Schritt 5), **nie** als zweiter Schreiber. PID +
Startzeit stehen als Diagnose IN der Lock-Datei, sind aber nie Übernahme-Kriterium. Der C-14-Assert lautet
„eigene OS-Sperre wird gehalten (Handle offen)", nicht „Lock-Datei existiert". `flush_und_warte` (In-Process)
wartet blockierend auf dieselbe OS-Sperre.

### 4.5 Start-Modell + Windows-ACL-Layering (D7 — Bau-Regel, wörtlich)
- **(a) LOGIK-Tests konten-agnostisch:** die gesamte pytest-Suite läuft unter EINEM Konto (tmp-Pfade injiziert).
- **(b) HÄRTE = Installations-Schicht:** persönliche Edition = Scheduled Task **„DizzNetwork-Chronist"**
  (Muster `backup_apps`: venv-Python, Minuten-Trigger) unter dem Nutzer-Konto — **ein Konto ist akzeptiert**
  (Kette+Siegel tragen die Beweislast; Ehrlichkeits-Kasten §9). Bizzi-Editionen: eigenes Dienst-Konto
  „bizzi-chronist", Datei-ACL (nur dieses Konto schreibt `segmente\`), App-Konten nur lesend — legt der
  Installer an (B7/docs/66-Schiene), nicht pytest.
- **(c) Integrationsprobe:** `bizzi-pruef --acl-probe` verifiziert am lebenden System, dass der aufrufende
  Prozess Segmente NICHT schreiben kann (erwartet: PermissionError; unter Ein-Konto-Edition meldet sie
  ehrlich „Stufe-1-Härtung nicht aktiv").

### 4.6 Wiederherstellungs-Verbund (BZ-C-3 — Restore-Sicherheit)
App-DBs und `data\chronik\` sind **EIN Restore-Verbund** — nur paarweise aus demselben Snapshot
zurückspielen, nie einzeln. Sonst entstehen zwei stille Fehlerbilder: (a) DB älter als Kette ⇒ eine neue
Buchung erhält ein `i`, das in der Kette mit anderem Inhalt existiert (ohne C-16 würde es still als
„übernommen" gestempelt, ohne je angehängt zu werden — Beweis-Verlust); (b) Chronik älter als DB ⇒ Historie
fehlt, das nächste Siegel kettet auf einen zurückgerollten Kopf. **Bau-Regeln:**
- `ops/backup_apps.py` MUSS `data\chronik\` im Backup-Scope haben (DoD §10) — heute nicht garantiert.
- Nach **jedem** Restore ist `bizzi-pruef pruefe` + `salden-replay` **Pflicht, VOR dem nächsten Chronist-Tick**.
- C-16 fängt Fall (a) (Fork-Stopp statt Stempel); `bizzi-pruef bericht` fängt Fall (b), indem es prüft, dass
  jede `festschreibungen.siegel_hash`-Referenz als Siegel-Datei existiert (zurückgerollte Chronik fällt auf).

## §5 · `chronik_pruef` — der Prüfkern (`appkit/chronik_pruef.py`, CLI `bizzi-pruef`)

**Ein Modul, drei Einstiege (C-13):** (1) Offline-CLI (auch an Prüfer herausgebbar — nur stdlib +
`cryptography` für Signaturen; liest NUR `stamm_pub.json`/`schluesselbrief.json`, nie DPAPI), (2)
pytest-Fixture über Golden-Segmenten (§7), (3) ab B4: EXTF-Rückspiel-Wächter.

| Kommando | Prüft | Exit |
|---|---|---|
| `pruefe [--von E --bis E]` | Kette lückenlos (h-Rechnung Zeile für Zeile) · Signaturen (Schlüsselbrief → Chronist) · Merkle-Wurzeln · Siegel-Kette (`prev_siegel`) · Quorum erfüllt · n/i-Monotonie je App · aktive Format-Version aus `chronik.format`-Ereignissen (C-17) | 0 grün · 2 Bruch (mit erster Bruchstelle: Epoche/n/Grund) |
| `salden-replay --app money [--bis-siegel S]` | rechnet die Konto-Salden aus `money.uebernahme` (Anker) + `money.buchung/storno`-Ereignissen nach und vergleicht gegen die App-DB (Summe aller Salden = 0 UND Übereinstimmung je Konto); bei `money.festschreibung` gegen deren `salden_hash` unter Beachtung des `beweisgrad` (§6.0) | 0/2 wie oben · 3 Divergenz (Konto + Differenz) |
| `beweis --n N` | erzeugt + verifiziert den Merkle-Einschluss-Beweis (§2.4) für Zeile N | 0/2 |
| `acl-probe` | Stufe-1-Härtung am lebenden System (§4.5c) | 0 aktiv · 4 nicht aktiv (ehrlich) |
| `bericht` | menschenlesbarer Prüfbericht (alle obigen + Bestand: Epochen, Zeitraum, Siegel-Zeiten; Restore-Wächter §4.6: jede `festschreibungen.siegel_hash`-Referenz existiert; Genesis-Datum vs. ältestes Ereignis + nicht-monotone Siegel-Zeiten als Hinweis, BZ-C-11) | wie `pruefe` |

**`--pfeffer <datei>` (C-15):** optionale Herausgabe des Feld-Hash-Pfeffers an den Prüfer — nur damit kann ein
Klartext gegen einen Feld-/hash_only-Hash verifiziert werden. Ohne `--pfeffer` prüft `bizzi-pruef` Kette,
Signaturen, Merkle, Siegel und Salden vollständig (die brauchen den Pfeffer nicht).

**Replay-Semantik (v1, ehrlich):** `salden-replay` beweist „die Kette deckt die heutige DB" für Beträge/
Konten ab dem `money.uebernahme`-Stichtag (§6.0). Freitexte sind gepfefferte Feld-Hashes — Divergenz dort ist
als Hash-Differenz erkennbar, ohne Klartext. Cross-App-Totalordnung wird NICHT behauptet (docs/77 §2.6): je
App strikt über `i`, epochen-weise happened-before — für die Buchhaltung beweisbar ausreichend (Ledger ist je
App-DB totalgeordnet).

## §6 · Money-M-2-Anbindung (die B1-Verdrahtung — der Vorbaustein konkret)

### 6.0 Chronik-Anschluss an Bestandsdaten: das `money.uebernahme`-Ereignis (BZ-C-1)
B1 zündet auf der **echten** Money-DB mit Jahren an Buchungen VOR dem Chronik-Genesis. Ein Salden-Replay aus
der leeren Kette gegen die volle DB divergiert sonst ab Tag 1 (das Demo-/Beweis-Kommando wäre rot). Deshalb:
- **Beim ERSTEN Chronik-Anschluss** von money schreibt die Zündungs-Migration in EINER `db.transaktion()`
  genau EIN `money.uebernahme`-Ereignis: `{stichtag, letzte_buchung_rowid, konten:[{konto_id, saldo_minor}]}`
  = die Ist-Salden aller Konten zum Stichtag (Beträge als Dezimal-Strings).
- **Replay-Formel ab dann:** `saldo(konto) = uebernahme.saldo + Σ postings der Ereignisse nach dem Stichtag`.
- **Beweisgrad je Festschreibung (§6.3):** Zeiträume vollständig NACH dem Stichtag ⇒ `beweisgrad:"voll"`
  (lückenloser Ketten-Beweis). Ältere Zeiträume sind festschreibbar mit `beweisgrad:"db-stand"` — das Siegel
  deckt den `salden_hash`, die Ketten-Gegenprobe beginnt aber erst am Stichtag. Der Beweisgrad wird in Antwort
  + Karte **ehrlich ausgewiesen** (nie „voll bewiesen" behaupten, wo nur der DB-Stand gesiegelt ist).

### 6.1 Outbox-Helper (`appkit/chronik.py`, öffentliche API)
```python
def schreibe(conn, *, art: str, nutzlast: dict, subjekt: str, entscheid_id: str = "") -> None
```
validiert Klasse (C-3) + Kanon (C-2, ASCII-Keys C-17), berechnet `nutzlast_hash` (voll/struktur: `sha256:`
über `kanon(nutzlast)`; hash_only: gepfefferter `hmac256:`, C-15), INSERTet in `chronik_ausgang` — **auf der
übergebenen offenen Verbindung, ohne Commit** (C-1). Dazu: `kanon()`, `feld_hash(text) -> str | None`
(None bei leer; sonst gepfefferter `hmac256:`, C-15), `merkle_wurzel(blaetter)`, `merkle_beweis(...)`,
Schlüssel-/Brief-/Pfeffer-Verwaltung.

### 6.2 Die Money-Schreibpfade (moneyapp/main.py — Stand 11.07., alle bereits `db.transaktion()`)
**Fünf wertbildende Pfade:**
| Pfad (heute) | Ereignis(se) |
|---|---|
| `POST /api/buchungen` (~Z. 884) | 1× `money.buchung` (quelle `manuell`; FX-Buchung = dieselbe Art, 4 Postings) |
| `POST /api/buchungen/split` (~Z. 932) | 1× `money.buchung` **je Zeilen-Buchung** (gleiche Txn) |
| `POST /api/import` (~Z. 984) | 1× `money.buchung` je importierter Buchung (quelle `import:<fmt>`) |
| Serie verbuchen (~Z. 2427) | 1× `money.buchung` (quelle `serie`) |
| `DELETE /api/buchungen/{id}` (~Z. 1275) | 1× `money.storno` |

**Vier weitere `UPDATE buchungen`-Pfade (BZ-C-2, code-verifiziert 12.07. — MÜSSEN mit):**
| Pfad (heute) | Wächter + Ereignis |
|---|---|
| Kategorie zuweisen (~Z. 1246) | im versiegelten Zeitraum ⇒ **409**; offen ⇒ erlaubt + `money.umklassung` (gleiche Txn) |
| Beleg anhängen (~Z. 1366) | auch im versiegelten Zeitraum ERLAUBT (verbessert Nachvollziehbarkeit, ändert keine Werte) + `money.beleg` (gepfefferte Titel-/Ref-Hashes) |
| Beleg entfernen (~Z. 1412) | im versiegelten Zeitraum ⇒ **409**; offen ⇒ erlaubt + `money.beleg` (leere Hashes = Entfernung) |
| Kategorie-Löschung Bulk (~Z. 1743) | `UPDATE`-`WHERE` schließt versiegelte Zeiträume aus (versiegelte Buchungen behalten ihre archivierte Kategorie); die App meldet die Aussparung |

**Regel statt Stellenliste (BZ-C-2, verschärft):** JEDER Block, der `buchungen`/`postings` schreibt, braucht
entweder `chronik.schreibe()` + `pruefe_offen()`-Wächter **in derselben Transaktion** ODER eine begründete
Vertrags-Ausnahme (nur wirkungsfreie Metadaten). Buchungs-Edits in-place sind verboten (Storno + Neu). Bau-KI
verifiziert die Vollständigkeit beim Bau per Grep `(INSERT INTO|UPDATE)\s+(buchungen|postings)` gegen diese
zwei Tabellen; neue Treffer ⇒ Vertrag ergänzen, nie still auslassen. Nutzlasten exakt nach §3.

### 6.3 Festschreibungs-Strecke EÜR (dünn — „Monats-Sperre = Siegel-Referenz")
- **Tabelle (money `extra_schema`):** `festschreibungen (id, user_id, zeitraum TEXT 'YYYY-MM' UNIQUE je user,
  status TEXT offen|versiegelt, bis_i INTEGER, salden_hash TEXT, beweisgrad TEXT, siegel_epoche INTEGER,
  siegel_hash TEXT, created_at, updated_at, deleted_at)` — normale Vertrags-Tabelle (user_id!), der BEWEIS
  liegt in der Kette.
- **`POST /api/festschreibung {zeitraum}`** — die Schritte (1)–(3) laufen in **EINER** `db.transaktion()`
  (BEGIN IMMEDIATE serialisiert alle Schreiber; der Hash entsteht INNERHALB der Sperre — BZ-C-5):
  (1) **Wächter:** Zeitraum vollständig vergangen + alle Vormonate mit Buchungen festgeschrieben oder leer
  (Lücken-Ehrlichkeit: Meldung, kein Zwang) · (2) `salden_hash` = `sha256:` über `kanon()` der
  Konto-Salden-Liste des Zeitraums (nur Konten mit Bewegung; Beträge als Strings) + `beweisgrad` je §6.0 ·
  (3) `festschreibungen`-Zeile (status `offen`) + `chronik.schreibe(money.festschreibung)`. **Commit.**
  Danach (außerhalb der Txn): (4) `flush_und_warte()` → Siegel · (5) Zeile auf `versiegelt` + Siegel-Referenzen.
  **Crash zwischen (3) und (5):** Ereignis ist in der Kette, Zeile bleibt `offen` ⇒ nächster Aufruf/Start
  holt idempotent nur die Siegel-Referenz nach (kein zweites Ereignis). Antwort enthält Epoche + Siegel-Hash
  + Beweisgrad — **die Quittung ist ein kryptographischer Beweis, kein Toast** (docs/77 §5.5).
- **Wächter in den Schreibpfaden:** ein zentraler Helfer `pruefe_offen(user_id, datum)` blockt
  `status IN ('offen','versiegelt')` (BZ-C-5: auch das kurze `offen`-Fenster während einer laufenden
  Festschreibung ist gesperrt) und wird in JEDEM Schreibpfad **innerhalb derselben Schreib-Transaktion** wie
  der INSERT/UPDATE aufgerufen (kein TOCTOU-Fenster). `datum` im gesperrten Zeitraum ⇒ **409**
  `{"error": "Zeitraum YYYY-MM ist festgeschrieben — Korrektur als Gegenbuchung im offenen Monat"}`; Storno
  einer Buchung mit `datum` im gesperrten Zeitraum ⇒ ebenfalls 409 (Gegenbuchung statt Soft-Delete —
  GoBD-Denkweise). Aufgerufen in allen fünf wertbildenden Pfaden **und** den vier UPDATE-Pfaden nach §6.2.
- **KA-H1-Ausnahme:** die Konto-Lösch-Engine ruft `pruefe_offen` NICHT — deshalb nimmt sie
  `buchungen/postings/festschreibungen` von der Kaskade aus (§3-Naht, BZ-C-7); sie tastet festgeschriebene
  Buchungen also nicht an.
- **UI (B1-minimal):** Karte „GoBD-Festschreibung" in den Money-Einstellungen — Monat wählen, Liste der
  Festschreibungen mit Siegel-Referenz + Beweisgrad, Rückstands-Anzeige (`/api/chronik/status`:
  Outbox-Rückstand, letzte Epoche/Siegel-Zeit, Chronist-Zustand, `fork_verdacht`). Feel-Politur ist NICHT B1.

### 6.4 UStVA-Slot
`money.ustva_freigabe` bindet an `quell_stand` (docs/68 U-6 — der Hash existiert dort bereits als
Kopplungs-Mechanik M-4→M-2→M-1). Verdrahtung ERST, wenn der finale Freigabe-Akt (M-2-Bau) existiert;
B1 registriert nur die Datenklasse. Damit gilt ab M-2-Bau: die PlausiFreigabe wird chronik-beweisbar,
ohne dass irgendjemand zurückkommen und die Chronik umbauen muss.

## §7 · Test-Katalog (Vertragsbestandteil; venv-Python, repo-relativ, `PYTHONPATH=packages`)

| Block | Fälle (Mindestumfang) |
|---|---|
| **Kanon** (`packages/appkit/tests/test_chronik_kanon.py`) | Ordnung/Nesting/Unicode-Werte deterministisch · float/NaN/int>2^53 ⇒ Fehler · **Nicht-ASCII-Objekt-Schlüssel ⇒ Fehler** (C-17) · Geld-String-Regel · `feld_hash` leer/None · **`feld_hash` ohne Pfeffer-Datei ⇒ Fehler; gleicher Text ⇒ gleicher `hmac256:` je Instanz, verschieden über Instanzen** (C-15) |
| **Kette+Merkle Property** (`test_chronik_kette.py`) | seeded Zufalls-Folgen (`random.Random(0xD1221)`, ≥ 200 Fälle, KEIN neues Paket): verify grün; 1-Bit-Flip in beliebiger Zeile/Position ⇒ `pruefe` nennt exakt die erste Bruchstelle · Merkle Größen 1…17: jeder Einschluss-Beweis verifiziert, manipulierter Pfad fällt · odd-promote gegen Referenz-Vektoren |
| **Chronist** (`test_chronist.py`) | Übernahme + Rückstempeln · alle drei Schließregel-Trigger + nie-leer · **Uhr-Rücksprung ⇒ Zukunfts-ts sofort fällig + GELB** (BZ-C-11) · Idempotenz: Crash-Simulation nach fsync/vor Stempel ⇒ kein Doppel-Append · **Fork: (app,i) im Segment mit anderem `nutzlast_hash` ⇒ Fork-Stopp statt Stempel** (C-16) · **0-Zeilen-Stempel-UPDATE (Zeile gelöscht) ⇒ legal, gezählt** (BZ-C-7) · torn write ⇒ Recovery-Kürzung · **Instanz-Lock: zweiter Tick blockiert/bricht ab, solange die OS-Sperre gehalten wird — auch bei ‚alter' Lock-Datei** (C-14/BZ-C-4) · Rückstands-Messung |
| **Restore-Verbund** (`test_chronik_restore.py`, BZ-C-3) | DB älter als Kette (i-Kollision, anderer Inhalt) ⇒ Fork-Abbruch statt Stempel · Chronik älter als DB ⇒ `bericht`-Befund via fehlende `festschreibungen.siegel_hash`-Referenz |
| **Golden** (`test_chronik_golden.py` + `tests/golden/chronik/`) | eingecheckte Fixture-Segmente+Siegel (deterministisch mit Test-Schlüssel + Test-Pfeffer erzeugt, Generator-Skript dabei): `pruefe`/`salden-replay`/`beweis` grün · je eine manipulierte Variante pro Fehlerklasse ⇒ erwarteter Exit-Code. **Diese Fixtures sind der CI-Golden-Harness (C-13)** |
| **Money-Anbindung** (`apps/money/tests/test_chronik_anbindung.py`) | jeder der fünf wertbildenden + vier UPDATE-Pfade erzeugt exakt seine Ereignisse in derselben Txn (Rollback-Test: Fehler nach Outbox-INSERT ⇒ nichts persistiert) · **409/Erlaubnis-Matrix der vier UPDATE-Pfade** (BZ-C-2) · **Umklassung erzeugt Ereignis; Bulk spart versiegelte aus** · Nutzlast-Formate nach §3 · Freitexte + Anzeigenamen der Test-Nutzer erscheinen NIE im Klartext (Grep über erzeugte Segmente, BZ-C-10) |
| **Bestands-Anschluss** (`test_chronik_uebernahme.py`, BZ-C-1) | Bestands-DB mit Vor-Genesis-Buchungen ⇒ nach `money.uebernahme`-Ereignis `salden-replay` grün · Festschreibung vor/nach Stichtag trägt korrekten `beweisgrad` · Vor-Genesis-Storno (postings self-contained) repliziert korrekt |
| **Festschreibung e2e** (`test_festschreibung.py`) | offen→versiegelt happy path (In-Process-Chronist) · 409-Wächter alle neun Pfade · **Buchung/Storno während offener Festschreibung ⇒ 409** (BZ-C-5) · **salden_hash entsteht unter der Schreibsperre** (Serialisierungs-Test) · Crash offen ⇒ idempotente Nachholung · Chronist tot ⇒ Fehler, nie ok (C-9) · `salden_hash`-Replay-Gegenprobe |
| **Struktur-Wächter** | `chronik_ausgang`-Spaltenliste OHNE user_id (C-10) · `soft_delete_user` auf money lässt `buchungen/postings/festschreibungen` unberührt (BZ-C-7) · `git diff --stat ledger.py` leer (C-11, Merge-Gate) · Bestands-Suiten money + appkit grün (aktuelle Zahlen im DoD nachführen) |

## §8 · Editionen + Parametrik
- `quorum` lebt in `data\chronik\konfig.json` (`{"quorum": 1}`); Bizzi-Editionen setzen 2-of-3/3-of-5 —
  **Format und Prüfkern sind ab v1 quorum-fähig**, nur die Zeugen-PROZESSE fehlen bis B7 (`bizzikit`).
- Sichtbarkeit: der Vorbaustein ist Teil der persönlichen Edition (Money-Feature) — KEIN `bizzikit`-Import
  irgendwo in B1 (das Paket existiert noch gar nicht; D1 ist genau dafür da).
- Ausbau-Nähte (nur benannt, nichts vorgebaut): Zeugen-Gegenzeichnung (B7) · Schatten-Segment-Versand (B8) ·
  Anker (B7) · Charta-`entscheid_id`/`entscheid_hash` (B2, via `chronik.format`-Ereignis C-17) ·
  `fibu.*`-Festschreibung=Siegel je Periode (B3, ersetzt die dünne EÜR-Strecke NICHT — sie ist ihr Spezialfall
  und bleibt).

## §9 · Ehrlichkeits-Kasten (Gesetz 2 — gehört wörtlich in Doku + Abnahme)
- **Schutzhöhe quorum=1 (D1, wörtlich):** beweist Unverändertheit gegen App-Bugs und nachträgliche stille
  Änderung (Kette + Signatur + Siegel-Kette) — genau die §146(4)-Nachvollziehbarkeit des Solo-Steuerpflichtigen.
  **NICHT gegen den Konto-Inhaber selbst** (er besitzt die Schlüssel; Chronik-Reset = sichtbarer Bruch, neues
  Genesis-Datum — erkennbar, nicht verhinderbar). Kollegiums-Härte (Zeugen, externe Anker) bleibt Bizzi (B7).
- **Ein-Konto-Edition:** Stufe-1-ACL-Härtung ist hier NICHT aktiv (ehrlich per `acl-probe`-Meldung);
  DPAPI schützt Schlüssel/Pfeffer nicht gegen Code im selben Konto (secrets_os-Docstring gilt).
- **Beweisgrad-Ehrlichkeit (§6.0):** für Zeiträume vor dem Chronik-Anschluss-Stichtag deckt das Siegel den
  DB-Stand (`beweisgrad:"db-stand"`), nicht den lückenlosen Ketten-Beweis — nie „voll bewiesen" behaupten.
- **Aufbewahrungs-Verbund (§4.6, C-15):** Segmente + Siegel + `stamm_pub` + Schlüsselbrief + **Pfeffer** sind
  eine 10-J-Einheit; Pfeffer-Verlust macht Freitext-/hash_only-Verifikation unmöglich, Kette/Signaturen/Salden
  bleiben prüfbar. Frist-Ablauf-Frage (voll/struktur-Nutzlasten nach 10 J in der unlöschbaren Kette) = offene
  Anwaltsfrage Gate #14 (docs/84 §A2 P-7; ◇-Option „Perioden-Pfeffer-Schreddern" benannt, nicht gebaut).
- **Wir garantieren Erkennbarkeit, nie Unmöglichkeit** (docs/77 §2.3-Merksatz — Vertriebs- und Prüfersprache).
- **Kein „GoBD-Zertifikat"** (existiert nicht, docs/75); PS 880 kommt frühestens nach Einfrieren (Gate #5).
- **Zeit:** `ts` ist App-Behauptung; Beweiszeit = Siegel-Zeit; grobe Drift wird erst mit Zeugen (B7) GELB
  (Uhr-Anomalie GELB-Log ab B1, C-6/BZ-C-11).
- **Status:** ▣ baubar-jetzt: alles in §2–§7 · ◪ mit Aufwand: ACL-Härtung als Installer-Schritt, Einschluss-
  Beweis-UI · ◇ Reifung: TPM-Wrap (Gate #12), Zeugen/Anker (B7), DSGVO-Auskunft direkt aus Segmenten
  (`--export-subjekt`; v1 decken die App-Tabellen die Auskunft — Segmente sind pseudonym), Perioden-Pfeffer-
  Schreddern (P-7).

## §10 · Definition of Done (B1) — Architektur-KI-Abnahme-Checkliste (F5)
1. Suiten grün: appkit (Bestand + neue Chronik-Blöcke) · money (Bestand + Anbindung/Festschreibung/Übernahme) ·
   core unberührt. **Gemessen beim DoD-Durchlauf 13.07.2026 (BZ-C-12e):** **appkit 528 grün / 1 skip**
   (502 Bestand + 26 Chronik: chronist/restore/golden/anbindung-Blöcke) · **money 523 grün** (497 Bestand + 26:
   anbindung/uebernahme/festschreibung/struktur) · **core 283 grün, unberührt**. `ledger.py` + `chronik.py`
   byte-identisch (`git diff` leer); `ereignis_spine.py`/`events.py` (W2-Lane) nie angefasst.
2. Golden-Harness eingecheckt + grün; `bizzi-pruef pruefe/salden-replay/bericht` laufen offline gegen die Fixtures.
3. `git diff` über `ledger.py` leer; kein bestehender Endpoint-Response verändert (Vertrags-Suiten beweisen es).
4. Scheduled-Task-Anlage dokumentiert (ops-README-Absatz, Muster backup_apps); `/api/chronik/status` + Karte da;
   `ops/backup_apps.py`-Scope umfasst `data\chronik\` (§4.6).
5. Ehrlichkeits-Kasten §9 in die Money-Doku übernommen (Wortlaut, nicht Paraphrase).
6. **Verfahrensdoku-Kurzfassung (1 Seite)** in der Money-Doku: was wird festgeschrieben, wie entsteht das
   Siegel, wo liegen Schlüssel/Pfeffer, wie prüft man mit `bizzi-pruef` (docs/84 §A2 P-1/P-6).
7. Live-Verdrahtung (Task anlegen, :8210-Neustart) = **gegatet** (Kardinal-Regel 6) — Bau ≠ Zündung.
8. Übergabe an Haupt-World-Admin (Merge + DOKU_REGISTER-Stempel dort); kein push; Secrets nie in Chat/Repo.

## §11 · Bau-KI-Bau-Schnitt (~3 Runden, Vorschlag — Größenordnung, keine Zusage)
- **Runde 1:** `appkit/chronik.py` (Kanon/ASCII-Keys/Klassen/Outbox/Merkle/Schlüssel/HMAC-Pfeffer) +
  `chronik_pruef.py` (pruefe/beweis) + Kanon-/Kette-/Merkle-Tests + Golden-Generator.
- **Runde 2:** `chronist.py` (Tick/Recovery/OS-Lock/Fork-Schutz/Siegel/flush_und_warte) + Chronist-/Restore-/
  Golden-Tests + status/Alarm.
- **Runde 3:** Money-Verdrahtung (fünf wertbildende + vier UPDATE-Pfade + `money.uebernahme`-Migration +
  Festschreibungs-Strecke + `pruefe_offen`-Wächter + Karte + `salden-replay`) + e2e + DoD-Durchlauf.
  **Lane-Achtung:** Runde 1–2 = `packages/` ⇒ seriell max-1 (nur additiv-disjunkte NEUE Module), vor Start
  beim Haupt-World-Admin anmelden (docs/79 §5.3).

## §12 · G-BZ-DELTA — Prüfnachweis (12.07.2026, für den WA-Merge gegen die BZ-C-Liste)

> Davids Wort 12.07.: „Bizzi wird Bau-Chat", Schritt 0 = G-BZ-DELTA im `wt-bizzi`. Der WA prüft am Merge
> jeden Befund gegen die hier genannte Vertragsstelle. Quelle der Befunde: `docs/84` §A1 (BZ-C-1…12) + §A2.

| Befund | Schwere | eingespielt in (docs/80) |
|---|---|---|
| **BZ-C-1** Bestandsdaten-Replay: `money.uebernahme` + `beweisgrad` + `storno.postings` | HOCH (zünd-kritisch) | §6.0 (neu) · §3-Tabelle (uebernahme/storno) · §5 salden-replay · §7 Bestands-Anschluss |
| **BZ-C-2** vier UPDATE-Pfade + Grep-Regel + `umklassung`/`beleg` | HOCH | §6.2 (Tabelle + Regel) · §3-Tabelle · §6.3-Wächter · §7 Money-Anbindung |
| **BZ-C-3** Restore-Fork / Wiederherstellungs-Verbund | HOCH | C-16 · §4.2 Schritt 3 · §4.6 (neu) · §5 bericht · §7 Restore-Verbund |
| **BZ-C-4** OS-Datei-Sperre statt Alters-Übernahme | HOCH | C-14 · §4.4 (ersetzt) · §7 Chronist |
| **BZ-C-5** Festschreibungs-Races (Hash in Txn, flush nach Commit, `offen` blockt) | HOCH | §4.3 · §6.3 (Schritt-Folge + Wächter) · §7 Festschreibung |
| **BZ-C-6** Feld-Hash-Pfeffer (HMAC) | HOCH (zünd-kritisch) | C-15 · C-3 · §2.1/§2.6/§2.7 · §3-Mechanik · §6.1 · §5 `--pfeffer` · §7 Kanon |
| **BZ-C-7** §147-Kaskaden-Ausnahme + 0-Zeilen-Stempel legal | mittel | §3-Naht · §4.2 Schritt 3 · §6.3 · §7 Struktur-Wächter |
| **BZ-C-8** voll-Klassen-Freitext-Regel | mittel | §3 (klassenübergreifende Regel) |
| **BZ-C-9** kanon ASCII-Keys + `chronik.format` | mittel | C-17 · §2.1 · §3-Tabelle (chronik.format) · §5 pruefe |
| **BZ-C-10** subjekt = opake UUID (Beispiel `u:7f3a…`) | mittel | §2.2 · §2.3-Beispiel · §7 Money-Anbindung-Grep |
| **BZ-C-11** Uhr-Rücksprung + Genesis-Plausibilität im `bericht` | niedrig | C-6 · §4.2 Schritt 4/5 · §5 bericht · §7 Chronist |
| **BZ-C-12** Kosmetik: (a) 14→15 Gates → **docs/79** · (b) §6.3-Klammer entfernt · (c) `entscheid_id`↔`entscheid` · (d) hash_only `"nutzlast":""` · (e) DoD-Zahlen | niedrig | (a) docs/79 §0/§2 · (b) §6.3 · (c) §2.2/§2.3 · (d) C-3/§2.3 · (e) §10.1 (beim Bau) |

**Nicht eingespielt (bewusst, kein Bau):** die BZ-C-12e-Bestandszahlen werden erst beim realen DoD-Durchlauf
gemessen (nicht spekulativ gesetzt); §A2-Prüffragen P-1…P-8 sind Gate-#14-/StB-Material (Anhang docs/84), kein
Vertrags-Delta. **Konsistenz-Pflicht docs/84 §B (Charta-Konserve):** die dort vorweggenommenen Patches
(`chronik.format`-Mechanik, Pfeffer, subjekt-UUID) sind hier realisiert — B2 baut ohne Nacharbeit auf.

---
> **Anschluss:** B1 ist mit diesem (nun G-BZ-DELTA-gepatchten) Vertrag zünd-fertig — Trigger war Davids
> ausdrückliches Vorbaustein-Wort (12.07.). Bau in `wt-bizzi`/`chat/bizzi`, `packages/`-Anmeldung beim WA
> vor Runde 1. **Merge = Haupt-World-Admin** (prüft §12 gegen die BZ-C-Liste). F3 (V-BIZZI-2 Charta,
> docs/84 §B als Konserve) + B2+ bleiben hinter Finanzierungs-Go.
