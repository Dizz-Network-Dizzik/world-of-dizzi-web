# 03 · Dizz Money — GoBD-Festschreibung: Verfahrensdoku-Kurzfassung (V-BIZZI-1, B1)

> **Status: PRODUKTIV-BAUSTEIN, Live-Zündung gegatet.** Erstellt beim B1-DoD-Durchlauf 13.07.2026
> (Bau-Chat „World of Bizzi Admin", Worktree `wt-bizzi`). Normativ: `docs/80_CHRONIK_VERTRAG.md`
> (§6 Money-Anbindung, §9 Ehrlichkeit). Diese Seite ist die **Verfahrensdoku-Kurzfassung** (docs/80
> §10.6): sie erklärt in einer Seite, *was* festgeschrieben wird, *wie* das Siegel entsteht, *wo* die
> Schlüssel liegen und *wie* man mit `bizzi-pruef` selbst nachrechnet.

## Was ist die Chronik?

Jeder wertbildende oder umklassierende Schreibpfad in Dizz Money (Buchung, Split, Import, Serie,
Storno, Kategorie-/Beleg-Änderung) schreibt **in derselben Datenbank-Transaktion** ein signiertes
Ereignis in eine Outbox (`chronik_ausgang`). Ein separater Prozess, der **Chronist**, übernimmt diese
Ereignisse in eine **append-only, hash-verkettete, Ed25519-signierte** Segment-Datei und fasst je Epoche
einen **Merkle-Baum** zu einem **Siegel** zusammen. Beträge stehen als Dezimal-String in der Kette
(nie Float); personenbezogene Freitexte (Namen, Verwendungszwecke) **nur als gepfefferte Feld-Hashes** —
der Klartext verlässt die App-Tabellen nie in die (unlöschbare) Kette.

## Was wird festgeschrieben?

Eine **GoBD-Festschreibung** (Money-Einstellungen → Karte „GoBD-Festschreibung", oder
`POST /api/festschreibung {zeitraum:"YYYY-MM"}`) friert einen **abgeschlossenen Monat** ein:

1. **Wächter** (in der Schreibsperre): der Zeitraum muss vollständig vergangen sein; offene Vormonate
   mit Buchungen werden als Hinweis gemeldet (keine Erzwingung).
2. **`salden_hash`** = SHA-256 über die kanonisierte Konto-Salden-Liste des Monats (nur Konten mit
   Bewegung, Beträge als String) — entsteht **innerhalb** der Schreibsperre (kein TOCTOU).
3. Eine `festschreibungen`-Zeile (Status `offen`) + ein `money.festschreibung`-Ereignis. **Commit.**
4. Der Chronist siegelt die deckende Epoche (`flush_und_warte` — **ohne Siegel gibt es keine
   Bestätigung**, nie „ok"). 5. Die Zeile wird `versiegelt` und trägt Epoche + Siegel-Hash + **Beweisgrad**.

**Beweisgrad** (ehrlich ausgewiesen): `voll` = der Monat liegt vollständig nach dem Chronik-Anschluss-
Stichtag, die Kette deckt ihn lückenlos. `db-stand` = älterer Monat; das Siegel deckt den DB-Stand, die
Ketten-Gegenprobe beginnt erst am Stichtag. Ab dann gilt: **Schreibpfade in einen festgeschriebenen Monat
⇒ HTTP 409** — Korrektur nur als Gegenbuchung im offenen Monat (Storno statt Löschen, GoBD-Denkweise).

## Wo liegen Schlüssel + Pfeffer?

`C:\Dizzik\data\chronik\` (außerhalb des Repos): `stamm_key.json` + `chronist_key.json` (Ed25519,
DPAPI-verschlüsselt via `secrets_os`) · `pfeffer.bin` (32 B Feld-Hash-Pfeffer) · `stamm_pub.json` +
`schluesselbrief.json` (öffentlich, **damit der Prüfer ohne DPAPI verifiziert**) · `segmente/` · `siegel/`
· `status.json` (nur Cache). **Aufbewahrungs-Verbund (10 Jahre):** Segmente + Siegel + `stamm_pub` +
Schlüsselbrief + Pfeffer gehören zusammen; das nächtliche Backup (`ops/backup_apps.py`, AES-verschlüsselt)
sichert `data\chronik\` im **selben Snapshot** wie die money-DB — nur paarweise zurückspielen (docs/80 §4.6).

## Wie prüft man selbst nach? (`bizzi-pruef` — „Trauen Sie uns nicht")

Der Prüfkern ist offline lauffähig und **an den Prüfer herausgebbar** (stdlib + `cryptography`; liest nur
`stamm_pub.json`/`schluesselbrief.json`, nie DPAPI/Schlüssel):

```
python -m appkit.chronik_pruef --dir C:\Dizzik\data\chronik pruefe        # Kette · Merkle · Siegel · Monotonie
python -m appkit.chronik_pruef --dir …\chronik beweis --n 4211            # Einschluss-Beweis einer Zeile
python -m appkit.chronik_pruef --dir …\chronik salden-replay --money-db …\finanzen.sqlite
python -m appkit.chronik_pruef --dir …\chronik bericht --money-db …\finanzen.sqlite
```

Exit 0 = grün · 2 = Ketten-/Siegel-Bruch (mit erster Bruchstelle) · 3 = Salden-Divergenz (Konto +
Differenz). `salden-replay` rechnet die Konto-Salden aus dem `money.uebernahme`-Anker + den
Buchungs-/Storno-Ereignissen nach und vergleicht gegen die DB; `voll`-Festschreibungen werden zusätzlich
gegen ihren `salden_hash` gegengeprüft. Nach **jedem** Restore ist `pruefe` + `salden-replay` Pflicht,
bevor der Chronist wieder läuft.

---

## Ehrlichkeits-Kasten (docs/80 §9, wörtlich — Gesetz 2)

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
