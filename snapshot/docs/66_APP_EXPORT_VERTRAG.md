# 66 · APP-EXPORT-VERTRAG — Einzel-App als verkäufliches, self-contained Bündel (C-1, Bau-Spec für Bau-KI)

> **Status: VERTRAG (C-1, Architektur-KI 04.07.2026). Design + Stubs + Vertrags-Tests — KEIN Packaging gebaut.**
> Dieses Dokument ist die Bau-Spec analog [docs/62](62_RUNTIME_VERTRAG.md)/[63](63_AGENTEN_REGIE_VERTRAG.md)/
> [64](64_BANK_SYNC_VERTRAG.md)/[65](65_ELSTER_TRANSPORT_VERTRAG.md): ein späterer Bau-KI-Chat baut das
> Export-Tooling **ohne eigene Architektur-Entscheidung**. Grundlage: docs/56
> (Editionen + „Core immer dabei"), docs/58 §4 VO-7 (Lizenz-Politik),
> Grundgesetz 4 („ernsthaftes Vorhaben, soll ggf. verkauft werden können").

---

## §0 · Geltung, Namens-Klarstellung, Nicht-Ziele

**Geltung.** Dieser Vertrag definiert, wie aus dem Monorepo **EINE App (oder ein App-Set) + Core + der
tatsächlich genutzte appkit/ui-kit-Anteil** zu einem **self-contained, lizenzierbaren, auslieferbaren Bündel**
geschnürt wird — inklusive Lizenz-Manifest, Editionen-Zuschnitt, Daten-/Secret-Nullzustand und Update-Mechanik.

**★ Namens-Klarstellung (Befund 04.07., Ehrlichkeit vor Aktivität).** Der Auftrag C-1 nannte `ops/mirror_export`.
Befund: **`ops/mirror_export.py` EXISTIERT bereits** (entgegen der Netz-Doku „geplant") — als **Voll-Spiegel**:
`git subtree split` je App + Komplett-Kopie von appkit/ui-kit nach `data\_backups\mirrors\<id>` (Backup-
Eigenständigkeit, docs/_archiv/45). Das ist eine ANDERE Schiene als das Verkaufs-Bündel: kein Carving, kein
Lizenz-Manifest, keine Editionen, kein Nullzustand (der Spiegel enthält die volle Historie!). Entscheid:

| Schiene | Werkzeug | Zweck | Empfänger |
|---|---|---|---|
| **Spiegel** (Bestand, bleibt unverändert) | `ops/mirror_export.py` | Backup-Eigenständigkeit je App, volle git-Historie, komplettes appkit/ui-kit | wir selbst (Rollback/Weitergabe an uns) |
| **Produkt-Export** (DIESER Vertrag) | **`ops/appexport/`** (neu, Paket) | verkäufliches Bündel: gecarvt, lizenz-geprüft, editions-geschnitten, null-zuständig, updatebar | **Kunde** |

Die Netz-Doku + `_netzwerk/SYSTEM_KARTE.html` werden auf diese Zwei-Schienen-Wahrheit gesynct (Gesetz 9).

**Nicht-Ziele (OUT, hart):** kein Installer/NSIS/Tauri (Welle 1, docs/52 Z2.3) · kein Auto-Update-Kanal ·
kein DRM/Kopierschutz · kein Server-Deploy (G-DEPLOY-2 parkt) · kein Mobile · keine CI · keine Preisliste
(G-PREIS) · keine reale Bündel-Erzeugung in dieser Runde. §13 listet weitere bewusste Auslassungen.

---

## §1 · Invarianten (nummeriert; Enforcement-Ort verbindlich)

| # | Invariante | Enforcement-Ort |
|---|---|---|
| **I-1** | **Bündel = Spiegel EINES Monorepo-Commits.** App, Core, appkit, ui-kit immer im selben Stand; es gibt KEINE appkit×App-Versionsmatrix. `quelle_commit` ist Pflichtfeld. | `BUNDLE_MANIFEST.json` (§4); Builder C1-3 |
| **I-2** | **Nutzerdaten NIE im Bündel.** Keine `*.db`/`*.sqlite*`, kein `data\`-Baum, keine Backups. Die DB entsteht beim Kunden-Erststart via Migrationen (leerer Seed). | `appexport/nullzustand.py` `VERBOTENE_DATEIEN`; Builder bricht hart ab |
| **I-3** | **Secrets NIE im Bündel.** Vault leer; Secret-Muster-Scan über alle Text-Dateien des Bündels; Fund ⇒ Abbruch ohne Override-Flag. | `appexport/nullzustand.py` `SECRET_MUSTER` |
| **I-4** | **Lizenz-Ampel fail-closed.** Unbekannte Komponente/Lizenz ⇒ `rot` ⇒ nicht auslieferbar. Ampel `gruen`/`gruen_mit_auflage` ist Ausliefer-VORAUSSETZUNG je Edition. | `appexport/lizenz.py` `ampel_fuer()`; Builder verweigert bei `rot`/offenem `gate` |
| **I-5** | **LGPL-Isolation (M-6-Präzedenz, docs/64 §10).** LGPL-Komponenten nur unmodifiziert, als austauschbare Import-Dependency (nie vendorn/forken), Lizenztext liegt im Bündel. | `lizenz.py` `BEKANNTE_KOMPONENTEN` (Auflagen-Feld); Vertrags-Test |
| **I-6** | **Abschluss-Pflicht (Carving).** Beobachtete direkte appkit-Nutzung ⊆ deklarierte; transitive Hülle vollständig; 0 tote Imports; 0 Monorepo-Reste (fremde `apps.*`, `ops/`, `_netzwerk/`, absolute `C:\Dizzik`-Pfade) im Bündel. | `appexport/carving.py` `pruefe_abschluss()` + `nullzustand.py`-Scans |
| **I-7** | **Editions-Freigabe fail-closed.** App ohne ausdrückliche Freigabe für eine Edition ⇒ nicht auslieferbar. v1: healthy/management/admin nur E-LOKAL; **trading NIE**. | `appexport/editionen.py` `ist_auslieferbar()` |
| **I-8** | **Code/Daten-Trennung beim Kunden.** `programm\` (ersetzbar) strikt getrennt von `daten\` (persistent). Ein Update ersetzt NUR `programm\`. | Bündel-Layout §2; Update-Regeln §8 |
| **I-9** | **Modelle + ERiC NIE im Bündel (v1).** Download-on-first-use (M-1-Muster, docs/65 M1-3); das Lizenz-Manifest führt eine eigene `nachgeladen`-Tabelle für alles, was der Erststart holt. | `LIZENZ_MANIFEST.json` §5; `export_manifest.json` Feld `nachgeladen` |
| **I-10** | **Kein Fork.** Edition = Konfiguration, EINE Codebasis (docs/56-Kernregel). Der Builder erzeugt Paket-/Konfigurations-Varianten, nie Code-Varianten. | Bau-Plan §10; Review-Pflicht |
| **I-11** | **Export-Werkzeug importiert appkit NICHT.** `appexport` analysiert Quelltext (AST/Dateien) statt zu importieren — läuft in jedem Python ≥3.12 ohne PYTHONPATH, keine Seiteneffekte durch App-Import. | `ops/appexport/*` (kein `import appkit`); Vertrags-Test |

---

## §2 · Bündel-Anatomie (normativ)

```
<bündel>/                          ← z. B. dizzi-news_lokal_2026-07-04+e794a51/
├── programm/                      ← ERSETZBAR (Update tauscht genau diesen Baum, I-8)
│   ├── apps/core/                 ← „Core immer dabei" (docs/56 §2): Schaltzentrale, eigener Prozess :8200
│   ├── apps/<id>/                 ← die gekaufte(n) App(s) — OHNE tests/, _workfiles/, docs/, CLAUDE.md
│   ├── packages/appkit/           ← GECARVTE Hülle (§3) — ohne tests/
│   ├── packages/ui-kit/           ← KOMPLETT (Entscheid §3.4)
│   ├── shell_dist/                ← gebautes Core-Dashboard (ops/build_shell.ps1-Artefakt)
│   ├── requirements.txt           ← gepinnt (Versionen aus ops/requirements-lock.txt), Vereinigung §3.5
│   └── start_dizzi.ps1 / .cmd     ← Erststart/Start (setzt PYTHONPATH=programm\packages relativ)
├── BUNDLE_MANIFEST.json           ← §4 (Identität, quelle_commit, Edition, Inhalt)
├── LIZENZ_MANIFEST.json           ← §5 (SBOM-artig, Ampel, Warranty-of-Title-Block)
├── LICENSES/                      ← volle Lizenztexte (SPDX-Dateiname je Komponente; LGPL-Text Pflicht bei I-5)
├── lizenz.json                    ← Kauf-Lizenz des Kunden (signiert, C1-6; bis dahin Platzhalter-Schema §6.3)
└── LIESMICH.md                    ← generiert: Erststart, Systemvoraussetzungen, was nachgeladen wird (I-9)
```

- **`daten\` ist NICHT Teil des Bündels** — sie entsteht beim Kunden am Daten-Anker (Default
  `%LOCALAPPDATA%\dizzi-world\daten`, überschreibbar via Env `DIZZI_DATA_ROOT`; Pfad-Anker-Audit = C1-4,
  denn heute ist `C:\Dizzik\data` an mehreren Stellen kanonisch verdrahtet — ehrlicher Bau-Punkt, kein Ist).
- **Ausschluss-Muster (normativ, `appexport/nullzustand.py`):** `tests/`, `_workfiles/`, `docs/`, `CLAUDE.md`,
  `__pycache__/`, `*.pyc`, `.git*`, `conftest.py`, `mcp_server.py`-Dev-Varianten bleiben DRIN nur wenn im
  Export-Manifest deklariert. Bündel enthält keine git-Historie (Unterschied zur Spiegel-Schiene, §0).
- **Core-Zuschnitt:** Core wird als eigenständiger schlanker Prozess mitgeliefert (Antwort auf docs/56 §2.4-1,
  Begründung §6.2). Sein Dashboard zeigt nur lizenzierte Apps; nicht gekaufte erscheinen als „nicht installiert".

---

## §3 · Carving-Modell (Dependency-Carving)

### 3.1 Drei Mengen, eine Wahrheit
| Menge | Quelle | Wer pflegt |
|---|---|---|
| **DEKLARIERT** | `apps/<id>/export_manifest.json` Feld `appkit_direkt` (§4.1) | die App (Review-Pflicht bei appkit-Import-Änderung) |
| **BEOBACHTET** | AST-Scan über `apps/<id>/**/*.py` (ohne `tests/`): jedes `import appkit.X` / `from appkit.X import …` / `from appkit import …` (Wurzel zählt als Modul `""`→`__init__`) | `appexport/carving.py` `ermittle_direkte_nutzung()` (Bau C1-1) |
| **HÜLLE** | transitiver Abschluss von DEKLARIERT über die appkit-Binnen-Import-Kanten (AST über `packages/appkit/*.py`) | `carving.py` `huelle_aus_kanten()` (**pure, schon real**) |

### 3.2 Abschluss-Prüfung (I-6, `pruefe_abschluss()` — pure, schon real)
- `BEOBACHTET \ DEKLARIERT ≠ ∅` ⇒ **FEHLER** (App nutzt Undeklariertes — Export verweigert).
- `DEKLARIERT \ BEOBACHTET ≠ ∅` ⇒ **WARNUNG** (Über-Deklaration — erlaubt, aber gemeldet; hält Manifeste ehrlich).
- Bündel-Inhalt = HÜLLE (+ `appkit/__init__.py` immer). Die Hülle ist **deterministisch sortiert** (Reproduzierbarkeit).
- **Schwer-Module-Regel:** `ollama`, `mcp`, `runtime`, `agenten`, `app_gateway` gelten als schwer (eigene
  Dienste/Deps). Landen sie NUR über die Hülle (transitiv) im Bündel, ohne direkt deklariert zu sein ⇒ WARNUNG
  mit Kanten-Pfad — bewusste Entscheidung statt stiller Mitnahme.

### 3.3 Ehrlichkeit zur Hüllen-Größe (Gesetz 2)
Reale Messung 04.07.: News nutzt ~15, Money ~16 der 26 appkit-Module **direkt**; die transitive Hülle wird
größer sein (appkit/app.py ist Hub). Der Wert des Carvings liegt deshalb v. a. in: (a) **Beweis der
Vollständigkeit** (kein toter Import, kein Monorepo-Rest), (b) **Dritt-Dependency-Zuschnitt** je Bündel (§3.5),
(c) **Fernhalten der Schwer-Module** (§3.2), (d) der **Lizenz-Stückliste** (§5). Ein Mini-Subset ist NICHT das
Versprechen.

### 3.4 ui-kit: KOMPLETT statt gecarvt (Entscheid)
ui-kit = ~26 statische Eigenbau-Dateien (css/js, kein Python, keine Dritt-Lizenz — `_UI_BUILDER_VENDORED.txt`
ist Eigenwerk aus dem eigenen Standalone-Repo). Datei-genaues Carving brächte Bruchrisiko (HTML-Referenzen sind
statisch schwer vollständig zu beweisen) bei ~0 Ersparnis und 0 Lizenz-Gewinn ⇒ **ui-kit wird immer komplett
gebündelt**. Revision erst, falls ui-kit je Dritt-Assets aufnimmt (dann greift §5 automatisch).

### 3.5 Dritt-Dependencies (pip)
- `MODUL_PIP_DEPS` (appkit-Modul → pip-Distributionen) wird **maschinell** in C1-2 erhoben (AST-Imports ∩
  installierte Distributionen via `importlib.metadata.packages_distributions()`), NICHT handgeraten —
  der Vertrag lässt die Karte bewusst leer (`carving.py`, Kommentar dort).
- Bündel-`requirements.txt` = pip-Deps der appkit-HÜLLE ∪ `pip_eigen` der App(s) ∪ Core-Basis (fastapi/uvicorn/…),
  **Versionen gepinnt aus `ops/requirements-lock.txt`** (eine Wahrheit für Versionen, I-1-analog).
- Jede pip-Komponente MUSS im Lizenz-Manifest auftauchen (§5) — Generator und Carver teilen dieselbe Liste.

---

## §4 · Manifest-Schemata (normativ: `ops/appexport/manifest.py`)

### 4.1 `apps/<id>/export_manifest.json` — die App-Deklaration (C1-1 erzeugt sie je App)
```json
{
  "schema": 1,
  "app_id": "news",                     // = Ordner apps/<id> (Netz-Verzeichnis)
  "paket": "newsapp",                   // Python-Paket
  "port": 8216,
  "appkit_direkt": ["app", "auth", "db", "…"],   // DEKLARIERT (§3.1); sortiert
  "pip_eigen": ["feedparser"],          // App-eigene pip-Deps (nicht via appkit)
  "statisch": ["static/"],              // mitzunehmende Nicht-Python-Bäume
  "editionen": ["lokal"],               // Freigabe (fail-closed, I-7) — Teilmenge von editionen.EDITIONEN
  "sensitivitaet": "normal",            // normal|hoch|hoechst (Netz-Verzeichnis)
  "nachgeladen": [                      // I-9: was der Erststart beim Kunden holt (leer erlaubt)
    {"name": "…", "zweck": "…", "gate": null}
  ]
}
```
Validierung: `manifest.validiere_export_manifest()` (pure, schon real) — Pflichtfelder, bekannte Editionen,
sortierte `appkit_direkt`, `schema`-Versionierung. **Ort-Entscheid:** die Deklaration wohnt BEI der App
(App-Besitz, Review im App-Chat), das SCHEMA wohnt im Werkzeug (`ops/appexport` — eine Wahrheit).

### 4.2 `BUNDLE_MANIFEST.json` — die Bündel-Identität (Builder C1-3 erzeugt)
```json
{
  "schema": 1,
  "bundle_id": "dizzi-news",
  "bundle_version": "2026-07-04+e794a51",   // Datum + quelle_commit-Kurzform; lexikographisch vergleichbar
  "erzeugt_am": "2026-07-04T12:00:00",
  "quelle_commit": "e794a51…",               // I-1: der EINE Monorepo-Stand
  "edition": "lokal",
  "paket_typ": "einzel",                     // einzel|bundle|gesamt (docs/56 §2.2)
  "apps": ["core", "news"],                  // Core IMMER enthalten
  "appkit_module": ["…"],                    // die gebündelte Hülle (sortiert; Audit-Beweis)
  "lizenz_manifest_sha256": "…",             // Kopplung Bündel↔Stückliste
  "daten_anker_default": "%LOCALAPPDATA%\\dizzi-world\\daten"
}
```

---

## §5 · Lizenz-Manifest (SBOM-artig; normativ: `ops/appexport/lizenz.py`)

### 5.1 `LIZENZ_MANIFEST.json`
```json
{
  "schema": 1,
  "bundle_id": "dizzi-news", "edition": "lokal", "erzeugt_am": "…",
  "komponenten": [
    {"name": "fastapi", "version": "0.136.3", "lizenz": "MIT", "klasse": "pip",
     "isolation": null, "ampel": "gruen", "begruendung": "permissiv"},
    {"name": "fints", "version": "…", "lizenz": "LGPL-3.0-or-later", "klasse": "pip",
     "isolation": "lgpl_isoliert",
     "ampel": "gruen_mit_auflage",
     "begruendung": "M-6 docs/64 §10: unmodifiziert + austauschbar (hinter FinTSQuelle) + Lizenztext in LICENSES/"}
  ],
  "nachgeladen": [
    {"name": "ERiC", "lizenz": "proprietaer (ELSTER-Nutzungsbedingungen)", "gate": "G-M1-LIZENZ",
     "mechanik": "Download-on-first-use (docs/65 M1-3), NIE im Bündel"}
  ],
  "warranty_of_title": {"geprueft_am": null, "pruefer": null, "befund": null, "offene_punkte": []}
}
```

### 5.2 Ampel-Regelwerk (`ampel_fuer(komponente, edition)` — pure, schon real; fail-closed I-4)
| Lizenz-Klasse | E-LOKAL / E-HYBRID (eingebettet = Distribution) | E-SERVER (Betrieb ≠ Distribution, docs/56 §3) |
|---|---|---|
| permissiv (MIT, BSD-2/3, Apache-2.0, ISC, PSF-2.0, Unlicense, 0BSD, Public Domain/sqlite3) | `gruen` | `gruen` |
| MPL-2.0 (Datei-Copyleft) | `gruen_mit_auflage` (unmodifiziert; geänderte Dateien quell-offen) | `gruen_mit_auflage` |
| LGPL-2.1/3.0 | `gruen_mit_auflage` NUR mit `isolation="lgpl_isoliert"` (I-5), sonst `rot` | wie links |
| GPL-2.0/3.0, AGPL-3.0 | `rot` (nie eingebettet ausliefern) | v1 ebenfalls `rot` (AGPL-Netzwerk-Klausel; Server-seitige Werkzeug-Nutzung à la Creating/YOLO = eigenes späteres Gate, NICHT v1) |
| proprietär mit Gate (ERiC, FLUX, SQLite SEE) | `gate:<GATE-ID>` — auslieferbar erst nach Gate-Antwort | je Gate |
| **unbekannt / nicht gelistet** | **`rot`** | **`rot`** |

- **Zwei-Achsen-Norm (docs/58 VO-7):** die Ampel bewertet die **Werkzeug-/Distributions-Achse**. Die
  Output-Lizenz-Achse (was der Kunde mit Erzeugnissen darf) ist Creating-Thema und färbt die Ampel NICHT.
- **Modelle** (LLM-Gewichte, FLUX, …) sind IMMER Klasse `nachgeladen` (I-9) mit eigener Lizenz-Zeile;
  E-LOKAL bettet nur Permissives ein (docs/56 §3) — praktisch: v1 lädt Modelle nach und listet sie im
  Manifest samt Gate (G-MODELL-LIZENZ/G-FLUX-LIZENZ). Ollama-Community-Lizenzen (z. B. Llama-Community)
  werden in C1-2 je konkretem Modell erhoben — keine Pauschal-Freigabe.
- **`BEKANNTE_KOMPONENTEN`** (Startbestand in `lizenz.py`, belegt): python-fints = LGPL-3.0 (docs/64 §10,
  verifiziert 03.07.) · ERiC = proprietär/G-M1-LIZENZ (docs/65 §Gates) · FLUX = G-FLUX-LIZENZ (docs/58 §3.G)
  · sqlite3 = Public Domain (stdlib) · fastapi=MIT, uvicorn=BSD-3, httpx=BSD-3. **Alles Weitere erhebt C1-2
  maschinell** (`importlib.metadata`), Rest-Lücken bleiben `rot` bis kuratiert (I-4).
- **Warranty of Title (VO-7):** der Manifest-Block ist der Träger; v1 = Eigenerklärung auf Basis der
  vollständigen Stückliste + Prüfdatum. Ein externer Titel-Kauf/Anwalts-Check bleibt Punkt-Ankauf-Option (David).
- **DB-at-Rest / SQLite-SEE (VO-7):** Verschlüsselungs-Backend = **austauschbare Schnittstelle, Design jetzt**
  (§12.4b): höchst-Apps bekommen app-eigene, passphrasen-abgeleitete DB-Verschlüsselung (Produkt-Versprechen),
  OS-Schutz (DPAPI-Vault `secrets_os` gebaut; BitLocker im LIESMICH) als Basis darunter. Konkrete Wahl SEE
  (2000 USD, Warranty-of-Title-sauber) vs. SQLCipher (frei) vs. nur-OS = Kauf-Gate §12.4c, **editions-skaliert**
  (Defense-in-depth lokal, Pflicht ab hybrid/server). hoch/höchst-Apps bleiben in v1 aus dem Verkauf (§6.1) —
  aber als **vorbereitetes Design, nicht als Lücke**.

---

## §6 · Editionen × Pakete (docs/56 konkretisiert)

### 6.1 Editions-Freigabe-Matrix v1 (fail-closed, I-7; normativ: `editionen.py`)
| App | E-LOKAL | E-HYBRID | E-SERVER | Begründung |
|---|---|---|---|---|
| core | ∅ (immer Bestandteil, nie einzeln) | ∅ | ∅ | „Core immer dabei" (docs/56 §2.1) |
| news, memory, communication | ✅ | ⏳ nach Gates | ⏳ G-DEPLOY-2 | normal-sensitiv, kleinste Lasten |
| money | ✅ (Kern ohne Bank/ELSTER-Wire) | ⏳ | ⏳ | FinTS/ERiC-Anteile tragen eigene Gates (G-M6-*, G-M1-LIZENZ) + LGPL-Auflage I-5 |
| creating | ⏳ G-FLUX-LIZENZ/G-MODELL-LIZENZ | ⏳ | ⏳ | Modell-Lizenzen ungeklärt; 30-GB-Nachlade-Mechanik (I-9) |
| management, admin | ✅ nur E-LOKAL | ❌ | ❌ | hoch ⇒ lokal_only (Netz-Verzeichnis); local-first = Kern-Argument |
| healthy | ✅ nur E-LOKAL (Kern-Vision; DB-Schutz-Design §12.4 vorbereitet, Freischaltung nach Crypto-Wahl §12.4c) | ❌ | ❌ | höchst; local-first = **stärkstes** Argument, nur die DB-Crypto-Wahl sequenziert |
| trading | ❌ | ❌ | ❌ | **NIE exportieren** (Echtgeld-System, eigener Stack, read-only-Doktrin) |

> **★ Höchst/hoch-Apps = Kern-Vision, nicht Nachzügler (David 04.07.):** healthy/admin/management sind gerade
> DESHALB wertvoll, weil sie **lokal** laufen (Souveränität = stärkstes Argument bei den sensibelsten Daten) —
> der lokale „Dienstleister", später hybrid/server-erweiterbar. Die v1-Sperre oben ist reines Build-Sequencing
> (DB-at-Rest-Crypto muss erst stehen, §12.4b), keine Deprio. Das Schutz-**Design** wird jetzt vorbereitet; nur
> der konkrete SEE-Kauf sequenziert (§12.4c).

### 6.2 Antworten auf die offenen Architektur-Fragen aus docs/56 §2.4 (Entscheide dieses Vertrags)
1. **Core im Einzel-App-Paket = eigener schlanker Prozess** (:8200), nicht eingebettete Bibliothek.
   Begründung: EIN Stack (I-10), Dashboard/Settings/Dizzi-ID identisch in jeder Paketgröße, additiver
   Upgrade (App dazu = Ordner dazu, kein Umbau). Ressourcen-Schlankheit ist Konfigurations-, keine Architektur-Frage.
2. **Lizenz-/Feature-Flagging = signierte Offline-Lizenz-Datei** `lizenz.json` (Ed25519-Signatur; Schema §6.3).
   Kein Online-Zwang in E-LOKAL (Vertrauens-Versprechen docs/35 §1); E-SERVER darf zusätzlich server-validieren.
   Kein DRM — die Datei schaltet Sichtbarkeit/Start frei, sie „verdongelt" nicht (bewusst, §13).
3. **EINE Dizzi-ID über alle gebündelten Apps** — K1 ist gebaut; Bündel-Erststart legt die Kunden-ID an
   (Paket-übergreifender Test = Bau-Akzeptanz C1-3).
4. **Querverbindungen degradieren „dormant":** fehlt die Gegen-App, zeigt die Kante „nicht installiert"
   statt zu brechen — Bau-Punkt in `appkit/querverbindung.py` (C1-4, netzweit nützlich, auch fürs Monorepo).
5. **Additiver Upgrade-Pfad:** App dazukaufen = neues Bündel desselben `quelle_commit`-Standes ODER Update
   auf gemeinsamen Stand + neue `lizenz.json`; `daten\` bleibt unangetastet (I-8). Keine Neuinstallation.

### 6.3 `lizenz.json` (Schema-Slot; Kryptographie/Bau = C1-6, NACH G-PAKET/G-PREIS)
`{schema, kunde, apps: ["news"], edition, ausgestellt_am, gueltig_bis|null, signatur}` — Verifikation offline
(öffentlicher Schlüssel liegt im Core); Details bewusst erst mit Preis-/Vertriebsmodell (G-PREIS).

---

## §7 · Daten-/Secret-Nullzustand (normativ: `ops/appexport/nullzustand.py`)

- **DB:** Bündel enthält **keinerlei** DB-Dateien (I-2). Erststart ruft die vorhandene idempotente
  `_migriere`-Mechanik der Apps → leere Schemata am Daten-Anker. Es wird KEIN vorgefüllter Seed verschifft
  (nichts zu leaken, eine Wahrheit = Migrationen).
- **Secrets:** Vault startet leer; der Kunde tippt Schlüssel in die bestehende Config-UI (Kardinal-Regel 7).
  `SECRET_MUSTER` (api-key/token/private-key/PIN-Muster …) scannen jede Text-Datei des Bündels; Fund ⇒ Abbruch (I-3).
- **Monorepo-Reste:** `PFAD_MUSTER` (`C:\Dizzik`, `data\apps`, `_backups`, …) + Carving-Verbot fremder
  `apps.*`-Importe (I-6). `verstoesse_in_text()` ist pure und schon real; der Baum-Scanner kommt in C1-3.
- **Dizzi-ID:** keine ID-/WebAuthn-Artefakte im Bündel; die Identität entsteht beim Kunden (§6.2-3).
- **LIESMICH.md** wird generiert und benennt ehrlich: was nachgeladen wird (I-9), Daten-Anker, BitLocker-Empfehlung.

---

## §8 · Update-/Mirror-Mechanik (der eigentliche „mirror"-Vertrag)

- **Versionsbegriff:** `bundle_version = <JJJJ-MM-TT>+<sha8>` (I-1). Es gibt genau EINE Kompatibilitätsachse:
  den Monorepo-Stand. appkit/ui-kit/App werden IMMER gemeinsam aktualisiert — die Single-Source-Eigenschaft
  des Monorepos wird zur Auslieferungs-Garantie („Mirror" = das Bündel spiegelt einen Commit).
- **Update-Paket = Voll-Ersatz von `programm\`** (kein Datei-Delta, kein Patch-Kanal in v1): neues `programm\`
  wird NEBEN das alte gelegt, Umschalt-Schritt ist atomar (Ordner-Rename), `daten\` bleibt unberührt (I-8).
  Migrationen laufen beim ersten Start des neuen Standes (vorwärts, idempotent).
- **Regeln (normativ):** (a) Update nur bei gleicher `bundle_id`+`edition` und **neuerer** `bundle_version`
  (lexikographischer Datums-Vergleich) — **Downgrade verboten**; (b) Editions-/Paket-Wechsel ist KEIN Update,
  sondern neue `lizenz.json` (+ ggf. Zusatz-App-Bündel, §6.2-5); (c) jedes Update-Paket trägt vollständige
  Manifeste + `SHA256SUMS` (Integrität; Signatur-Ausbau folgt mit C1-6-Schlüsselmaterial).
- **Kanal v1 = Datei/Download, manuell angestoßen** (E-LOKAL-Versprechen: läuft ohne uns). Auto-Update/Kanäle
  = Welle 1 (Tauri) bzw. E-HYBRID/E-SERVER — OUT (§0).
- **Kompatibilitäts-Versprechen an Kunden:** innerhalb einer `bundle_id` sind Daten-Migrationen lückenlos
  vorwärts möglich, solange Updates nicht übersprungen werden ODER Migrationen kumulativ-idempotent bleiben
  (heutiges `_migriere`-Muster ist kumulativ ⇒ Überspringen erlaubt; Vertrags-Test in C1-5 sichert das je App).

---

## §9 · Schnitt: ops vs. App vs. appkit

| Artefakt | Ort | Warum |
|---|---|---|
| Werkzeug (Carver, Lizenz-Generator, Builder, Scans, CLI) | **`ops/appexport/`** (Paket) | Tooling gehört nach ops (Konvention backup_apps/mirror_export); nicht ins appkit (I-11: kein appkit-Import; Apps sollen das Werkzeug nie zur Laufzeit brauchen) |
| Deklarations-INSTANZEN | `apps/<id>/export_manifest.json` | App-Besitz; Review im App-Chat; Werkzeug validiert nur |
| Schemata + Regelwerke (Editionen, Ampel, Muster) | `ops/appexport/{manifest,editionen,lizenz,nullzustand}.py` | EINE Wahrheit im Werkzeug; Daten-getrieben, testbar |
| Bündel-Ausgabe | `C:\Dizzik\data\_export\<bundle_id>\` (außerhalb Repo) | Erzeugnisse gehören nie ins Repo; parallel zur Spiegel-Ausgabe `_backups\mirrors` |
| CLI-Aufruf (C1-1+) | `python ops\appexport\cli.py pruefe --app news` · `… export --app news --edition lokal` | Skript-Stil = ops-Konvention; kein Install nötig |

**appkit wird in dieser Runde NICHT angefasst** (Stubs leben komplett in ops). Einziger geplanter
appkit-Bau-Punkt ist die QV-Dormanz (C1-4) — World-Chat/Bau-KI, nach diesem Vertrag.

---

## §10 · Bau-Plan für Bau-KI (commit-groß; jede Stufe: appexport-Suite grün, 0 Bestands-Verhalten geändert)

| Schritt | Inhalt | Gate | Akzeptanz |
|---|---|---|---|
| **C1-0 ✅** | dieses Paket: Vertrag docs/66 + Stubs `ops/appexport/` + Vertrags-Tests | — | Tests grün; 0 Bestands-Datei verändert |
| **C1-1** | AST-Beobachter (`ermittle_direkte_nutzung`, `ermittle_appkit_kanten`) + `export_manifest.json` für **alle** Apps erzeugen + `cli.py pruefe` (read-only) | — | Abschluss-Prüfung läuft je App; Befund-Liste ehrlich (Fehler/Warnungen); Golden-Test: News-Manifest ⊆ real beobachtete Menge |
| **C1-2** | Lizenz-Manifest-Generator: `importlib.metadata` über die venv + `MODUL_PIP_DEPS`-Erhebung + LICENSES-Sammlung; `BEKANNTE_KOMPONENTEN` maschinell vervollständigen | — | Für News+Money entsteht ein vollständiges Manifest ohne `unbekannt`-Reste ODER ehrliche Rot-Liste; python-fints trägt I-5-Auflagen |
| **C1-3** | Bundle-Builder E-LOKAL/Einzel-App: Carve-Kopie (Hülle §3), requirements-Pinning, Scans I-2/I-3/I-6, LIESMICH+Manifeste, shell_dist-Einbau; Ziel `data\_export\` | Bau frei; **AUSLIEFERUNG gegated** (G-PAKET) | Pilot-Bündel startet auf Scratch-Port aus dem Export-Ordner (isoliert, preview-verifiziert); alle Scans grün; Ampel ohne rot/gate |
| **C1-4** | Pfad-Anker (`DIZZI_DATA_ROOT` netzweit statt `C:\Dizzik\data` hart) + QV-Dormanz in `appkit/querverbindung.py` | — (appkit-Arbeit, World-Chat) | Monorepo-Suiten grün; Bündel-Scan findet 0 absolute Pfade; fehlende Gegen-App ⇒ „nicht installiert", kein Fehler |
| **C1-5** | Update-Paket-Bau + Regeln §8 (Versions-Vergleich, Voll-Ersatz-Skript, SHA256SUMS) + Migrations-Kumulativitäts-Test je exportierbarer App | — | Update Alt→Neu im Test-Ordner: `daten\` byte-identisch, Migrationen laufen, Downgrade verweigert |
| **C1-6** | `lizenz.json` real (Ed25519, Offline-Verifikation im Core, Dashboard „nicht installiert/nicht lizenziert") | **G-PAKET + G-PREIS** | Signatur-Roundtrip-Tests; Core zeigt nur lizenzierte Apps |
| **C1-7** | Editions-Ausbau E-HYBRID/E-SERVER + Modell-Nachlade-Flows | **G-MODELL-LIZENZ / G-FLUX-LIZENZ / G-DEPLOY-2** | je Edition eigener Vertrags-Anhang |

Reihenfolge C1-1→C1-3 ist ohne jedes Gate baubar (Erzeugnisse bleiben in `data\_export`, nichts wird
ausgeliefert). **Erste reale Auslieferung an einen Kunden = gegateter Nutzer-Akt** (wie Live-Neustarts).

---

## §11 · Test-Strategie

- **Jetzt (C1-0, Vertrags-Tests, `ops/appexport/tests/`):** pure Regelwerke vollständig — Hüllen-Abschluss
  (Toy-Graphen inkl. Zyklus), Abschluss-Befunde (fehlend⇒Fehler, überzählig⇒Warnung), Ampel-Matrix je
  Edition (inkl. fail-closed `unbekannt`⇒rot, LGPL ohne Isolation⇒rot), Editions-Freigaben (trading nie,
  healthy nie server, unbekannte App ⇒ ∅), Manifest-Validierung (Pflichtfelder/Sortierung/Editionen),
  Nullzustands-Muster (gepflanzte Secrets/DB-Pfade/absolute Pfade werden gefangen; harmloser Text nicht),
  `NichtGebaut` für alle Bau-Stubs, I-11 (kein appkit-Import im Werkzeug).
- **Bau-Tests (Bau-KI):** Golden-Carve News (Fixture-Manifest vs. echter Scan) · Scan-Fixtures mit gepflanzten
  Verstößen im Datei-Baum · Sandbox-Import-Smoke: Bündel-Hülle in frischer venv importierbar (`--no-site`) ·
  e2e „Bündel startet isoliert am Scratch-Port" (C1-3-Akzeptanz; preview-Werkzeuge, Kardinal-Regel 10) ·
  Update-Durchstich (C1-5). **NIE**: echte Auslieferung, echte Kunden-Signaturen oder Live-Ports in Tests.
- **Suite-Aufruf:** `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q ops\appexport` (Worktree-Wurzel;
  kein PYTHONPATH nötig — I-11).

---

## §12 · Gates an David (Status 04.07.2026: ALLE OFFEN — Formulierung abgabefertig)

1. **G-PAKET — welche App zuerst standalone, welche Paket-Granularität?**
   *Empfehlung (Architektur-KI):* **News als Pilot.** Begründung: normal-sensitiv, 0 Sonder-Lizenzlasten (kein LGPL,
   kein ERiC, keine Modelle im Bündel — Ollama optional/nachgeladen), erstes UI-Muster des Netzes, kleinste
   Nachlade-Liste ⇒ sauberster Erstdurchlauf für Carving+Ampel+Nullzustand. Danach Memory. Money erst nach
   G-M1-LIZENZ/G-M6-Rest (ERiC/FinTS-Lasten), Creating erst nach G-FLUX-LIZENZ. Bundles: Empfehlung
   „Einzel-App + Gesamtnetz zuerst, freie Bundles später" (docs/56 G-PAKET-Frage) — Entscheid bei David.
2. **G-PREIS — Preis-/Lizenzmodell je Edition** (Kauf einmalig ± Update-Jahr? Hybrid-Mix? Abo nur E-SERVER?).
   Vorarbeit: docs/55 + docs/56 R-A; C1-6 (Signatur/Lizenz-Datei) wartet darauf. Keine Empfehlung ohne
   Markt-Recherche R-A1 — bewusst offen.
3. **G-MODELL-LIZENZ (inkl. G-FLUX-LIZENZ, docs/58 §3.G)** — welche Modelle je Edition offiziell lizenziert/
   eingebettet/nachgeladen; FLUX-Enterprise-Frage („Gewichte auf Endkunden-Gerät") VOR jedem Creating-Export.
   v1 umgeht das Gate für News/Memory (I-9: keine Modelle im Bündel).
4. **DB-at-Rest-Schutz für hoch/höchst-Apps (VO-7, SQLite-SEE)** — ★ KORRIGIERT 04.07. nach David-Rückfrage
   (vorher unsauber als pauschales „aufschieben" gerahmt). Drei Fragen, die getrennt gehören:
   - **(a) Sollen healthy/admin/management lokal verkäuflich sein?** → **JA — Kern-Vision, NICHT aufgeschoben.**
     Gerade bei den höchst-sensiblen Apps ist local-first/Souveränität das *stärkste* Verkaufsargument
     ([[vision-positionierung]]): sie sind der lokale „Dienstleister", der die sensibelsten Daten nie preisgibt;
     hybrid/server folgt später (G-DEPLOY-2). Die v1-Sperre in §6.1 ist **Build-Sequencing** (man liefert nichts
     aus, dessen DB-Crypto noch nicht existiert), KEINE Vision-Deprio.
   - **(b) Wie schützt das Bündel ihre DB at-rest?** → **Design JETZT** (umfängliche Vorbereitung, kein Aufschub):
     Verschlüsselungs-Backend = austauschbare Schnittstelle; für höchst (health) app-eigene, **passphrasen-
     abgeleitete DB-Verschlüsselung als Produkt-Versprechen** (unabhängig vom OS-Konto), OS-Layer
     (BitLocker + DPAPI-Vault `secrets_os`, gebaut) als Basis-Schicht darunter.
   - **(c) Womit konkret — und WANN Geld ausgeben?** → NUR das sequenziert: **SEE** (2000 USD, Single-Vendor,
     Warranty-of-Title-sauber, VO-7) vs. **SQLCipher** (frei, OpenSSL) vs. **nur OS-Layer**. Bei *pure-local*
     ist DB-Datei-Crypto Defense-in-depth über BitLocker/DPAPI hinaus (**SQLCipher/frei reicht zum Bauen +
     Ausliefern**); bei *hybrid/server* Pflicht (off-device + GDPR/DPA), dort zahlt SEEs Lizenz-Sauberkeit.
     ⇒ **SEE spezifisch kaufen, sobald** (i) ein lokaler Kunde Datei-Level-DB-Crypto fordert, ODER (ii)
     hybrid/server unparkt, ODER (iii) Warranty-of-Title-Sauberkeit fürs kommerzielle Bündel verlangt wird —
     **nicht reflexhaft vorab**; SQLCipher = freier Interims-Pfad.
   *Kurz:* Apps + Schutz-Design = **jetzt vorbereiten** (Kern-Vision); aufgeschoben wird allein die konkrete
   2000-USD-SEE-Lizenz, bis Warranty-of-Title/Server sie einfordert. **Offener David-Entscheid:** SQLCipher als
   Interims-Pfad bestätigen + SEE-Kauf an (i)/(ii)/(iii) knüpfen.

---

## §13 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

Installer (NSIS/Inno/MSI) + Tauri-Verpackung (Welle 1) · Auto-Update/Update-Server · Code-Signing-Zertifikate
(nur SHA256SUMS-Slot; Signierung = R-G2) · DRM/Kopierschutz/Verdongelung (bewusste Produkt-Entscheidung:
Lizenz-Datei schaltet frei, versklavt nicht) · App-Store/Vertriebskanäle · CI/CD · E-HYBRID/E-SERVER-Bau
(G-DEPLOY-2 parkt; nur die Ampel kennt Editionen schon) · Mobile · Preis-/EULA-Texte (G-PREIS, docs/55) ·
Creating-Modell-Distribution im Detail (nur Nachlade-Slot I-9 + Gate) · Trading-Export (NIE, §6.1) ·
Umbau/Abschaltung der Spiegel-Schiene `ops/mirror_export.py` (bleibt wie sie ist).

---

## §14 · Live-Status (mitgeführt, Gesetz 9)

- **04.07.2026 · C1-0 (Architektur-KI, Design-Runde):** Vertrag erstellt; Stubs `ops/appexport/{__init__,manifest,
  carving,lizenz,editionen,nullzustand}.py` + Vertrags-Tests `ops/appexport/tests/`; **0 Bestands-Datei
  verändert** (mirror_export.py unangetastet; appkit unangetastet). Zwei-Schienen-Klarstellung in
  Netz-Doku + SYSTEM_KARTE gesynct; docs/README-Index ergänzt. Gates §12 alle offen.
- **04.07.2026 · David-Rückfrage (SQLite-SEE) → Korrektur:** §12.4 + §5.2 + §6.1 überarbeitet — hoch/höchst-Apps
  als Kern-Vision (lokaler „Dienstleister") klargestellt, DB-at-Rest-Schutz-Design als Jetzt-Aufgabe, nur der
  konkrete SEE-Kauf sequenziert (SQLCipher = freier Interims-Pfad, SEE editions-skaliert). Kein Code berührt.
- **Nächster Schritt:** Bau-KI-Bau C1-1…C1-3 (gate-frei) nach 50-%-Schwelle; Merge + Projektstand = World-Admin
  (HANDOVER_C1_AN_WORLD-ADMIN_04-07.md an der Wurzel).
