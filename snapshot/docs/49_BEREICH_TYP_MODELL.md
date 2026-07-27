# 49 · BEREICH-TYP-MODELL — kanonisch (Heimat: Dizz Admin)

> **Status: GEBAUT in Admin (26.06.2026).** Die `bereich`-Entität lebt kanonisch in **Dizz Admin**
> (`apps/admin/adminapp/bereiche.py`). Dieses Dokument ist der **app-übergreifende Vertrag**: Money und
> Memory richten sich danach (sie koppeln heute schon lose über kontext-Strings, brauchen **keinen Code**).
> Umsetzungs-Entscheidungen vom Nutzer: 6 Typen · **ein Typ je Bereich** · sanfte Migration · erst Admin +
> Spec (appkit-Extraktion später, nur nach eigenem Go).

## 1 · Idee — Bereich-first
Ein **Bereich** (PARA-„Area": laufende Verantwortung, „Agentur Nord", „Bachelor Informatik") hat einen
**Typ** (`art`). Der Typ **schaltet die für ihn relevanten Module frei**. Man navigiert **Bereich-first**:
„ich bin gerade in Bereich Y (Typ X)" → und bekommt genau die Module von Typ X. „Geschäft" und „Studium"
sind dadurch **keine globalen Module mehr, sondern Bereichs-TYPEN**. (Die frühere globale **Filterzeile** ist
entfallen — Navigation läuft über die Bereichs-Übersicht.)

## 2 · Die Typen + ihre Module
**General-Module (jeder Bereich, typ-unabhängig):** `uebersicht · tresor · projekte · fristen`.
**Spezial-Module je Typ (zusätzlich):**

| Typ (`art`) | Label | Icon | Default-Farbe | Spezial-Module |
|---|---|---|---|---|
| `geschaeft` | Geschäft | 💼 | amber | **geschaeft** (Kunden/Rechnungen/EÜR/Mahnwesen/Abos) |
| `mandant` | Mandant | 🤝 | violett | **geschaeft** (ein Mandant trägt Geschäfts-Vorgänge) |
| `studium` | Studium | 🎓 | cyan | **studium** (Bildungsweg/Module/ECTS/Prüfungen) |
| `fortbildung` | Fortbildung | 📚 | grün | **studium** (nutzt die Studien-Werkzeuge) |
| `persoenlich` | **Persönlich Allgemein** | 🏠 | magenta | — (nur General) — **Default-Heimat** |
| `sonstiges` | Sonstiges | 📁 | cyan | — (nur General) |

**Ein Typ je Bereich** (Feld `bereich.art`); General immer dabei. Unter-Bereiche (`parent_id`) dürfen einen
**anderen** Typ haben (deckt Mischfälle ab, z. B. Mandant unter Geschäft). Kanonische Tab-Reihenfolge:
`uebersicht · tresor · projekte · (geschaeft|studium) · fristen`.

## 3 · API-Vertrag (read-only)
- **`GET /api/bereich-typen`** → `{ typen:[{id,label,icon,farbe,module}], allgemeine_module:[…], default:"persoenlich" }`
  — der Typ-Katalog, an dem die UI-Anlage (Typ-Picker) hängt. **Das ist der kanonische Vertrag.**
- **`GET /api/bereiche` / `…/{id}`** liefern je Bereich zusätzlich `"module": [...]` (typ-gesteuert) — Clients
  gaten die Modul-Leiste damit, ohne das Mapping zu doppeln.
- Helfer (Backend): `bereiche.module_fuer_typ(art) -> list[str]`, `bereiche.bereich_typen_katalog()`.
- Anlage: `art` weggelassen ⇒ Default **`persoenlich`**; explizit ungültiger Wert ⇒ neutral **`sonstiges`**.

## 4 · Migration (sanft, nichts verschieben)
`migriere_bereich_fk()` hebt Alt-Typ **`privat` → `persoenlich`** (idempotent). **Keine Daten verschoben/
gelöscht.** Bestehende `geschaeft`/`studium`-Bereiche mappen 1:1. Geschäfts-/Studien-Daten ohne passenden
Typ-Bereich bleiben über die **„Allgemein"**-Heimat (`bereich_id=''`) erreichbar. **Tresor (Fernet/Step-up)
unangetastet.**

## 5 · Wie andere Apps andocken (V-Kanten, docs/26/34)
Andere Apps speichern die `bereich`-Entität **nicht**; sie aggregieren read-only je **kontext-Schlüssel**,
den der Bereich trägt:
- **V17 · Money** ↔ `bereich.money_kontext` → Finanzspur (`/api/bereich/finanzspur?kontext=`).
- **V18 · Management** ↔ `bereich.management_kontext` → Social (`/api/bereich/social?kontext=`).
- **V19 · Memory** ↔ `bereich.memory_ref` → Wissen/Kategorie (`/api/kategorie?ordner=`).

Der **Typ** ist Admin-intern (Modul-Freischaltung); Money/Memory müssen ihn **nicht** kennen — sie bleiben
über die kontext-Strings entkoppelt und brauchen **keinen Code**. Optional könnten sie den Typ später als
Hinweis lesen (z. B. „dieser Kontext ist ein Geschäftsbereich"), aber das ist nicht erforderlich.

## 6 · appkit-Extraktion — ✅ GEBAUT 26.06. (CRUD-Gerüst; Typ-Modell bleibt admin-lokal)
**Status:** Die geteilte **CRUD-/Hierarchie-/Zuordnungs-Logik** (die in Admin/Money/Memory/Management 4×
dupliziert war, ~150 Z. je App) ist nach **`packages/appkit/bereiche.py`** extrahiert = `BereicheBasis`
(config-getrieben: `arten`/`fk_tabellen`/`kontext_spalten`; `_public`-Hook überschreibbar). Alle 4 Apps leiten
davon ab (`appkit` 122 · money 246 · memory 88 · management 38 · admin 178 grün; ~−630 Z. Duplikat weg).
**Das Typ-Modell selbst** (`module_fuer_typ`/`bereich_typen_katalog`/`TYP_SPEZIAL_MODULE`/META) **bleibt
bewusst admin-lokal** (kanonische Heimat) — Admin überschreibt nur `_public` (hängt `module` an); Money/Memory/
Management brauchen den Typ nicht. **Live erst nach gebündeltem, gegatetem Neustart der 4 Apps** (bis dahin
inert — kein App importierte vorher `appkit.bereiche`). *(Backlog-Hebel des 26.06.-Perspektiv-Marathons, docs/33.)*

## 7 · Berührte Dateien (Admin)
`apps/admin/adminapp/bereiche.py` (Typ-Modell + `/api/bereich-typen` + `module`-Feld + Migration) ·
`apps/admin/static/index.html` (Filterzeile raus · Modul-Leiste bereich-scoped · Typ-Picker bei Anlage ·
„Allgemein"-Karte · Bereich-Übersicht/Cockpit bleibt) · `apps/admin/tests/test_bereich_typ.py`.

## 8 · Status (02.07., docs/58 VO-2)
Die Gesamtsystem-Kernanalyse verordnet den **Bereichs-Kanon-Ausbau VO-2**: kanonische Bereichs-ID statt
Freitext-`kontext`-Match, netzweites Basis-Typ-Set mit stabiler Ober-Kategorie, appkit-Hebung des Typ-Modells
(bisher bewusst admin-lokal, §6) sowie ein Memory-Ober-Register als erste Anwendung.
**★ VO-2 = Vertrag `docs/67_BEREICH_KANON_VERTRAG.md` ✅ FERTIG+GEMERGT 04.07.** (appkit `bereich_register.py`/`DzBereichRegister`,
Suite 257); **alle 3 Gates (G-BEREICH-ID/-ENUM/-CUTOVER) FREIGEGEBEN 04.07.** Ober-Kategorie-Layer additiv, Typ-Modell bleibt
admin-kanonisch (§1–7 unverändert). Details: `docs/67` + `docs/58` §3.B/VO-2/§6.
