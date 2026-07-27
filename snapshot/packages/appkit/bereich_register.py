"""Bereichs-Kanon (appkit) — Verträge-als-Code zu **docs/67** (VO-2: BER-1/2/3 + ME-1).

**Design-Stufe 0 (04.07.2026):** dieses Modul ist rein additiv — keine App importiert es
bisher (Adoptionsmuster wie ``appkit.bereiche`` vor dem 26.06.). ``appkit/bereiche.py``
(``BereicheBasis``) bleibt unverändert; das Register arbeitet per **Komposition** auf
derselben ``Database`` und kennt AUSSCHLIESSLICH die ``bereiche``-Tabelle (nie
Domänen-Tabellen — App-Fallbacks Stufe ③ bleiben app-lokal, docs/67 §8).

Bausteine (docs/67-Paragraphen in Klammern):
  * **Ober-Kategorien** (§4, BER-2) — das netzweite 5er-Basis-Typ-Set ÜBER den app-lokalen
    ``art``-Katalogen + Default-Mapping + Validierung (App-Erweiterungen map-pflichtig) +
    ``mit_ober_kategorie`` = geteilter ``_public``-Baustein (additiv ``ober_kategorie``).
  * **Schema-Single-Source** (§5) — ``schema_bereiche()`` erzeugt die ``bereiche``-DDL
    aller vier Apps wertgleich (Vertrags-Test); ``migriere_kanon_id()`` = MIG-KANON-1;
    ``migriere_bereich_fk()`` = die geteilte ``bereich_id``-FK-Nachrüstung (B-4).
  * **``DzBereichRegister``** (§3) — kanonische ID (= Admin-``bereiche.id``) als
    ``kanon_id``-Bindung + Dual-Read-Auflösekette ① kanon → ② kontext (Stufe ③ = App).
  * **Broken-Link-Wächter** (§3.4) + **Backfill-Vorschläge** (§7 P2) — pure Logik,
    read-only/dry-run; die App-Adapter füttern sie (``anker_index``/``kanon_status``).
  * **Baum + Roll-up** (§6, ME-1-Muster) — ``parent_id``-Baum und hierarchisch
    aufsummierte Zähler für die ``/api/bereiche/uebersicht``-Verträge.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from fastapi import HTTPException

from appkit.db import Database, now_iso

# ── BER-2 · Ober-Kategorien (docs/67 §4 — geschlossenes Netz-Set) ───────────────
#: Erweiterung NUR per Vertrags-Update von docs/67 (Invariante I-5).
OBER_KATEGORIEN: tuple[str, ...] = (
    "persoenlich", "geschaeftlich", "bildung", "projekt", "sonstiges")

#: Default-Mapping aller bekannten App-``art``-Werte (admin·money·memory·management)
#: auf ihre Ober-Kategorie. Ein flaches Dict trägt alle vier Kataloge, weil gleiche
#: ``art``-Namen netzweit auf dieselbe Ober-Kategorie zeigen (Vertrags-Test prüft
#: Vollständigkeit). ``privat`` bleibt gemappt, bis MIG-ART-1 (G-BEREICH-ENUM) läuft.
OBER_MAPPING_DEFAULT: dict[str, str] = {
    # admin (docs/49)
    "geschaeft": "geschaeftlich", "mandant": "geschaeftlich",
    "studium": "bildung", "fortbildung": "bildung",
    "persoenlich": "persoenlich", "sonstiges": "sonstiges",
    # money
    "privat": "persoenlich", "investment": "persoenlich", "projekt": "projekt",
    # memory
    "lebensbereich": "persoenlich", "wissen": "bildung", "referenz": "bildung",
    # management
    "kunde": "geschaeftlich", "marke": "geschaeftlich", "kampagne": "projekt",
}


def ober_kategorie_fuer(art: str, extra: Mapping[str, str] | None = None) -> str:
    """Ober-Kategorie einer App-``art``. ``extra`` = App-Override/-Erweiterung
    (gewinnt über den Default). Unbekannte ``art`` ⇒ ``"sonstiges"`` (fail-closed)."""
    if extra and art in extra:
        return extra[art]
    return OBER_MAPPING_DEFAULT.get(art, "sonstiges")


def mapping_validieren(arten: Sequence[str], extra: Mapping[str, str] | None = None) -> None:
    """Vertrags-Check (Bau-Zeit-Assert + Test): jede App-``art`` MUSS auf genau eine
    Ober-Kategorie aus dem Set mappen. Verstöße ⇒ ``ValueError`` (fail-closed)."""
    merged = {**OBER_MAPPING_DEFAULT, **(extra or {})}
    fehlend = [a for a in arten if a not in merged]
    if fehlend:
        raise ValueError(f"art ohne Ober-Kategorie-Mapping: {fehlend} (docs/67 §4.2)")
    kaputt = {a: merged[a] for a in arten if merged[a] not in OBER_KATEGORIEN}
    if kaputt:
        raise ValueError(f"Mapping-Ziel außerhalb OBER_KATEGORIEN: {kaputt}")


def mit_ober_kategorie(row: Any, extra: Mapping[str, str] | None = None) -> dict[str, Any]:
    """BER-2 · der geteilte ``_public``-Enrichment-Schritt (docs/67 §4.2): Row → dict +
    **additiv** ``ober_kategorie`` (aus ``ober_kategorie_fuer(art)``). Hält das Mapping
    Single-Source — die vier App-``_public``-Hooks rufen NUR dies auf, statt die
    Ober-Kategorie-Logik je App zu doppeln (``BereicheBasis`` bleibt unberührt, I-1).
    ``extra`` = optionaler App-Override, unverändert an ``ober_kategorie_fuer``
    durchgereicht. Rein additiv (kein Bestandsfeld wird verändert); fehlt ``art`` ⇒
    ``sonstiges`` (fail-closed, wirft nicht). Ober-Kategorie liegt ÜBER dem Typ-Modell —
    sie gated KEINE Module (docs/67 §4.2/I-9)."""
    d = dict(row)
    d["ober_kategorie"] = ober_kategorie_fuer(d.get("art", ""), extra)
    return d


# ── BER-3 · Schema-Single-Source + Migrations-Helfer (docs/67 §5/§7) ────────────
#: Whitelist sicherer SQL-Bezeichner (Spalten-/Tabellennamen), die ROH in DDL/ALTER
#: interpoliert werden. Geteilt von ``schema_bereiche`` (kontext-Spalten),
#: ``migriere_bereich_fk`` (FK-Tabellen) und ``DzBereichRegister`` (kontext-Spalte) —
#: EINE Strenge in der ganzen Datei (docs/71 R-17).
_SPALTEN_NAME = re.compile(r"[a-z_][a-z0-9_]*\Z")


def schema_bereiche(kontext_spalten: Sequence[str] = (), *, mit_kanon: bool = False) -> str:
    """Die kanonische ``bereiche``-DDL (Single-Source, docs/67 §5.2): reproduziert die
    vier Bestands-Schemata wertgleich (Vertrags-Test, kommentar-/whitespace-normalisiert)
    — admin ``("memory_ref","money_kontext","management_kontext")`` · money/management
    ``("kontext",)`` · memory ``()``. ``mit_kanon=True`` ergänzt die BER-1-Spalte
    ``kanon_id`` + Index (Zielbild nach MIG-KANON-1; Bestands-DBs rüsten stattdessen
    per ``migriere_kanon_id`` nach). Die ``kontext_spalten`` werden Whitelist-geprüft
    (roh in die DDL interpoliert ⇒ kein Injection; dieselbe Strenge wie
    ``DzBereichRegister.kontext_spalte``, docs/71 R-17)."""
    for k in kontext_spalten:
        if not _SPALTEN_NAME.match(k):
            raise ValueError(f"Ungültiger kontext-Spalten-Bezeichner: {k!r}")
    spalten = [
        "id            TEXT PRIMARY KEY",
        "user_id       TEXT NOT NULL",
        "name          TEXT NOT NULL",
        "art           TEXT NOT NULL DEFAULT 'sonstiges'",
        "parent_id     TEXT NOT NULL DEFAULT ''",
        "farbe         TEXT NOT NULL DEFAULT 'cyan'",
        "icon          TEXT NOT NULL DEFAULT 'folder'",
        "status        TEXT NOT NULL DEFAULT 'aktiv'",
        "beschreibung  TEXT NOT NULL DEFAULT ''",
        *[f"{k} TEXT NOT NULL DEFAULT ''" for k in kontext_spalten],
        *(["kanon_id      TEXT NOT NULL DEFAULT ''"] if mit_kanon else []),
        "sort_order    INTEGER NOT NULL DEFAULT 0",
        "created_at    TEXT NOT NULL",
        "updated_at    TEXT NOT NULL",
        "deleted_at    TEXT",
    ]
    ddl = ("CREATE TABLE IF NOT EXISTS bereiche (\n    "
           + ",\n    ".join(spalten) + "\n);\n"
           "CREATE INDEX IF NOT EXISTS idx_bereiche ON bereiche (user_id, status, sort_order);\n"
           "CREATE INDEX IF NOT EXISTS idx_bereiche_parent ON bereiche (user_id, parent_id);\n")
    if mit_kanon:
        ddl += "CREATE INDEX IF NOT EXISTS idx_bereiche_kanon ON bereiche (user_id, kanon_id);\n"
    return ddl


def migriere_kanon_id(db: Database) -> None:
    """MIG-KANON-1 (docs/67 §7 P1): rüstet ``kanon_id`` (TEXT, ``''`` = ungebunden) +
    Index idempotent an ``bereiche`` nach. SQLite ``ALTER ADD COLUMN`` ist nicht
    idempotent ⇒ PRAGMA-table_info-Guard (Muster ``migriere_bereich_fk``). Fehlt die
    ``bereiche``-Tabelle (noch), passiert nichts. Rein additiv — Default ``''`` lässt
    jedes Bestandsverhalten unverändert (Invariante I-3/I-7)."""
    conn = db.get_conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(bereiche)")}
    if not cols:
        return
    if "kanon_id" not in cols:
        conn.execute("ALTER TABLE bereiche ADD COLUMN kanon_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bereiche_kanon ON bereiche (user_id, kanon_id)")
    conn.commit()


def migriere_bereich_fk(db: Database, tabellen: Sequence[str]) -> None:
    """Single-Source der ``bereich_id``-FK-Nachrüstung (docs/67 §1 B-4/§5): rüstet die
    additive ``bereich_id``-Spalte (TEXT, ``''`` = „Allgemein"/unzugeordnet) + Index
    ``idx_<tabelle>_bereich`` idempotent an jeder EXISTIERENDEN Tabelle aus ``tabellen``
    nach (fehlt die Tabelle noch ⇒ übersprungen). Hebt die zuvor in Admin/Memory
    wortgleich duplizierte Schleife (B-4). Die App bleibt Herrin ihrer FK-Whitelist
    (§8, App-lokal) und etwaiger app-eigener Zusatz-Schritte — appkit trägt nur die
    generische Mechanik. SQLite ``ALTER ADD COLUMN`` ist NICHT idempotent ⇒
    PRAGMA-table_info-Guard. Tabellen-Bezeichner Whitelist-geprüft (kein Injection)."""
    conn = db.get_conn()
    for t in tabellen:
        if not _SPALTEN_NAME.match(t):
            raise ValueError(f"Ungültiger Tabellen-Bezeichner: {t!r}")
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        if cols and "bereich_id" not in cols:   # cols leer ⇒ Tabelle (noch) nicht da
            conn.execute(f"ALTER TABLE {t} ADD COLUMN bereich_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{t}_bereich ON {t} (user_id, bereich_id)")
    conn.commit()


# ── BER-1 · Kanonische ID + Dual-Read-Auflösekette (docs/67 §3) ─────────────────
#: Migrations-Phasen je Konsumenten-App (docs/67 §7; P0–P4).
MIG_PHASEN: tuple[str, ...] = ("bestand", "spalte", "backfill", "dual_read", "cutover")


@dataclass(frozen=True)
class Aufloesung:
    """Ergebnis der Auflösekette: ``quelle`` ∈ ``"kanon"``/``"kontext"``/``""`` (kein
    Treffer — App-Fallback Stufe ③ ist Sache der App). ``mehrdeutig=True`` = die Stufe
    hatte >1 Treffer (Wahl deterministisch ``sort_order, name``; Wächter meldet B-2)."""

    bereich_id: str | None
    quelle: str
    mehrdeutig: bool = False


class DzBereichRegister:
    """Kanonische Bindung der app-lokalen Bereichs-Achse an den Netz-Kanon
    (= Admin-``bereiche.id``, docs/67 §3.1). Komposition neben ``BereicheBasis`` —
    gleiche ``Database``, eigener Zuständigkeits-Schnitt: NUR ``kanon_id``-Bindung
    + Auflösung + Wächter-Feed; CRUD bleibt bei ``BereicheBasis``.

    ``kontext_spalte`` = Name der App-kontext-Spalte (money/management ``"kontext"``,
    Memory ``""`` = Stufe ② strukturell übersprungen). Whitelist-geprüfter Bezeichner
    ⇒ sichere SQL-Interpolation (kein Injection; Muster ``fk_tabellen``)."""

    def __init__(self, db: Database, *, kontext_spalte: str = "kontext") -> None:
        if kontext_spalte and not _SPALTEN_NAME.match(kontext_spalte):
            raise ValueError(f"Ungültiger Spalten-Bezeichner: {kontext_spalte!r}")
        self.db = db
        self.kontext_spalte = kontext_spalte

    # --- Helfer -------------------------------------------------------------
    def _spalten(self) -> set[str]:
        return {r["name"] for r in self.db.get_conn().execute("PRAGMA table_info(bereiche)")}

    def _row(self, user_id: str, bid: str):
        return self.db.get_conn().execute(
            "SELECT * FROM bereiche WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (bid, user_id)).fetchone()

    def _kanon_pflicht(self) -> None:
        """Schreibpfade sind fail-closed: ohne ``kanon_id``-Spalte klarer Fehler statt
        stillem No-op (docs/67 §5.3)."""
        if "kanon_id" not in self._spalten():
            raise HTTPException(
                409, "kanon_id-Spalte fehlt — Migration MIG-KANON-1 "
                     "(bereich_register.migriere_kanon_id) ist nicht gelaufen.")

    # --- Auflösekette (Dual-Read ①→②; Stufe ③ = App) --------------------------
    def aufloesen(self, user_id: str, *, kanon: str = "", kontext: str = "") -> Aufloesung:
        """Docs/67 §3.2: ① ``kanon_id`` exakt (case-sensitiv) → ② ``kontext``
        case-insensitiv (``<>''``), Ordnung ``sort_order, name``. Jede Stufe ohne
        Treffer fällt auf die nächste durch (auch dangling kanon — Not-Leiter bleibt;
        der Wächter macht es sichtbar). Fehlt die ``kanon_id``-Spalte, wird Stufe ①
        lautlos übersprungen ⇒ ``aufloesen(kontext=…)`` ist Stufe-0-wertgleich zur
        heutigen kontext-Auflösung (Invariante I-3). Immer user-scoped."""
        kanon = (kanon or "").strip()
        kontext = (kontext or "").strip()
        conn = self.db.get_conn()
        spalten = self._spalten()
        if kanon and "kanon_id" in spalten:
            rows = conn.execute(
                "SELECT id FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
                "AND kanon_id=? ORDER BY sort_order, name",
                (user_id, kanon)).fetchall()
            if rows:
                return Aufloesung(rows[0]["id"], "kanon", len(rows) > 1)
        if kontext and self.kontext_spalte and self.kontext_spalte in spalten:
            rows = conn.execute(
                f"SELECT id FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
                f"AND {self.kontext_spalte}<>'' "
                f"AND LOWER({self.kontext_spalte})=LOWER(?) ORDER BY sort_order, name",
                (user_id, kontext)).fetchall()
            if rows:
                return Aufloesung(rows[0]["id"], "kontext", len(rows) > 1)
        return Aufloesung(None, "", False)

    # --- Bindung (die EINZIGEN kanon_id-Schreiber, Invariante I-10) -----------
    def verknuepfen(self, user_id: str, bereich_id: str, kanon_id: str) -> dict[str, Any]:
        """Bindet einen lokalen Bereich an die kanonische ID. Fail-closed:
        Eindeutigkeit pro User (eine ``kanon_id`` ↔ höchstens EIN Bereich, I-4);
        Re-Bindung desselben Bereichs (Korrektur) ist erlaubt und auditiert."""
        kanon_id = (kanon_id or "").strip()
        if not kanon_id:
            raise HTTPException(400, "kanon_id fehlt (zum Lösen: loesen()).")
        self._kanon_pflicht()
        if self._row(user_id, bereich_id) is None:
            raise HTTPException(404, "Bereich nicht gefunden.")
        conn = self.db.get_conn()
        anderer = conn.execute(
            "SELECT id FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
            "AND kanon_id=? AND id<>?", (user_id, kanon_id, bereich_id)).fetchone()
        if anderer is not None:
            raise HTTPException(
                409, f"kanon_id bereits an Bereich {anderer['id']} gebunden "
                     "(Eindeutigkeit pro User, docs/67 I-4).")
        conn.execute("UPDATE bereiche SET kanon_id=?, updated_at=? WHERE id=? AND user_id=?",
                     (kanon_id, now_iso(), bereich_id, user_id))
        conn.commit()
        self.db.audit(user_id, "user", "bereich_kanon_verknuepft",
                      {"bereich_id": bereich_id, "kanon_id": kanon_id})
        return {"ok": True, "bereich_id": bereich_id, "kanon_id": kanon_id}

    def loesen(self, user_id: str, bereich_id: str) -> dict[str, Any]:
        """Löst die kanonische Bindung (``kanon_id := ''``)."""
        self._kanon_pflicht()
        if self._row(user_id, bereich_id) is None:
            raise HTTPException(404, "Bereich nicht gefunden.")
        conn = self.db.get_conn()
        conn.execute("UPDATE bereiche SET kanon_id='', updated_at=? WHERE id=? AND user_id=?",
                     (now_iso(), bereich_id, user_id))
        conn.commit()
        self.db.audit(user_id, "user", "bereich_kanon_geloest", {"bereich_id": bereich_id})
        return {"ok": True, "bereich_id": bereich_id, "kanon_id": ""}

    # --- Wächter-Feed (App-Seite von GET /api/bereiche/kanon-status) ----------
    def kanon_status(self, user_id: str) -> list[dict[str, Any]]:
        """Read-only-Feed für den Broken-Link-Wächter (docs/67 §3.3): je nicht
        gelöschtem Bereich ``{id, name, kanon_id, kontext}`` (``''``, wenn Spalte/
        Konfiguration fehlt — der Feed funktioniert in JEDER Migrationsphase)."""
        spalten = self._spalten()
        sel_kanon = "kanon_id" if "kanon_id" in spalten else "''"
        sel_kontext = (self.kontext_spalte
                       if self.kontext_spalte and self.kontext_spalte in spalten else "''")
        rows = self.db.get_conn().execute(
            f"SELECT id, name, {sel_kanon} AS kanon_id, {sel_kontext} AS kontext "
            "FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY sort_order, name", (user_id,)).fetchall()
        return [dict(r) for r in rows]


# ── BER-1 · Broken-Link-Wächter + Backfill (docs/67 §3.4/§7 — pure, read-only) ──
#: Die drei Bereichs-Kanten: (Kante, Admin-Slot-Feld). docs/34 V17/V18/V19.
WAECHTER_KANTEN: tuple[tuple[str, str], ...] = (
    ("V17", "money_kontext"), ("V18", "management_kontext"), ("V19", "memory_ref"))

#: Befund-Katalog des Wächters (docs/67 §3.4).
WAECHTER_BEFUNDE: tuple[str, ...] = (
    "ok", "alt", "dangling", "mehrdeutig", "ungenutzt", "unbekannt", "verwaist_app")


@dataclass(frozen=True)
class AnkerIndex:
    """Prüf-Index EINER Kante aus Sicht der Konsumenten-App: gebundene kanonische IDs +
    case-insensitive Zählung der kontext-Schlüssel und Fallback-Namen. Wird vom
    App-Adapter aus ``kanon_status()`` (+ ``extra_namen``, z. B. Memorys Ordner-Namen
    für die V19-Alt-Kante oder Moneys Kategorie-Namen) gebaut — der Wächter selbst
    bleibt DB-/HTTP-frei."""

    kanon: frozenset[str]
    kontext: Mapping[str, int]
    namen: Mapping[str, int]


def anker_index(bereiche: Iterable[Mapping[str, Any]], *,
                extra_namen: Iterable[str] = ()) -> AnkerIndex:
    """Baut den ``AnkerIndex`` einer Kante aus dem ``kanon_status``-Feed der App."""
    kanon: set[str] = set()
    kontext: Counter[str] = Counter()
    namen: Counter[str] = Counter()
    for b in bereiche:
        k = (b.get("kanon_id") or "").strip()
        if k:
            kanon.add(k)
        c = (b.get("kontext") or "").strip().lower()
        if c:
            kontext[c] += 1
        n = (b.get("name") or "").strip().lower()
        if n:
            namen[n] += 1
    for extra in extra_namen:
        e = (extra or "").strip().lower()
        if e:
            namen[e] += 1
    return AnkerIndex(frozenset(kanon), dict(kontext), dict(namen))


def _kante_pruefen(kanon_id: str, schluessel: str, anker: AnkerIndex) -> dict[str, str]:
    """Befund eines Admin-Bereichs auf EINER Kante: kanon-Bindung gewinnt (``ok``);
    sonst kontext-/Namens-Treffer = ``alt`` (funktioniert, aber fragil — B-1-Klasse),
    >1 Treffer = ``mehrdeutig`` (B-2 wird sichtbar statt still), leerer Slot =
    ``ungenutzt``, kein Treffer = ``dangling``."""
    if kanon_id and kanon_id in anker.kanon:
        return {"befund": "ok", "quelle": "kanon"}
    if not schluessel:
        return {"befund": "ungenutzt", "quelle": ""}
    for quelle, index in (("kontext", anker.kontext), ("name", anker.namen)):
        n = index.get(schluessel.lower(), 0)
        if n == 1:
            return {"befund": "alt", "quelle": quelle}
        if n > 1:
            return {"befund": "mehrdeutig", "quelle": quelle}
    return {"befund": "dangling", "quelle": ""}


def waechter_report(admin_bereiche: Iterable[Mapping[str, Any]],
                    anker_je_kante: Mapping[str, AnkerIndex]) -> dict[str, Any]:
    """Der Broken-Link-Report (docs/67 §3.4): je Admin-Bereich × Kante ein Eintrag.
    Pure + read-only + wirft nie (Invariante I-6): fehlt der Index einer Kante
    (App offline) ⇒ ``befund="unbekannt"`` statt Fehler. Baseline vor P1,
    Cutover-Nachweis vor P4 (0 dangling / 0 mehrdeutig, §7). Zusätzlich Reverse-
    Check (D4/F18): app-seitige kanon_id ohne lebenden Admin-Bereich ⇒ 'verwaist_app'."""
    kanten: list[dict[str, Any]] = []
    admin_liste = list(admin_bereiche)          # Iterable wird 2× gebraucht (Reverse-Check)
    for b in admin_liste:
        for kante, slot in WAECHTER_KANTEN:
            eintrag: dict[str, Any] = {
                "kante": kante, "bereich_id": b.get("id", ""),
                "bereich_name": b.get("name", ""),
                "schluessel": (b.get(slot) or "").strip()}
            anker = anker_je_kante.get(kante)
            if anker is None:
                eintrag.update(befund="unbekannt", quelle="")
            else:
                eintrag.update(_kante_pruefen(eintrag["bereich_id"],
                                              eintrag["schluessel"], anker))
            kanten.append(eintrag)
    # D4/F18 Reverse-Check: app-seitige kanon_id ohne lebenden (nicht-gelöschten)
    # Admin-Bereich ist im Vorwärts-Loop unsichtbar ⇒ eigener Befund 'verwaist_app'.
    admin_ids = {(b.get("id") or "") for b in admin_liste} - {""}
    for kante, _slot in WAECHTER_KANTEN:
        anker = anker_je_kante.get(kante)
        if anker is None:
            continue                      # Feed offline ⇒ oben bereits 'unbekannt'
        for verwaist in sorted(anker.kanon - admin_ids):
            kanten.append({"kante": kante, "bereich_id": "", "bereich_name": "",
                           "schluessel": verwaist, "befund": "verwaist_app", "quelle": "kanon"})
    zaehlung = Counter(e["befund"] for e in kanten)
    return {"kanten": kanten,
            "zusammenfassung": {b: zaehlung.get(b, 0) for b in WAECHTER_BEFUNDE}}


def backfill_vorschlaege(admin_bereiche: Iterable[Mapping[str, Any]], kante: str,
                         app_bereiche: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """MIG-KANON-2-Dry-Run (docs/67 §7 P2): schlägt ``kanon_id``-Bindungen vor, wo
    Admin-Slot ↔ App-``kontext`` **eindeutig** matcht. Schreibt NICHTS — das Setzen
    läuft über die bestätigte HITL-Liste via ``verknuepfen()``. Fail-closed: kein
    Vorschlag bei mehrdeutigem kontext (App-Seite), doppelt beanspruchtem Slot
    (Admin-Seite) oder bereits bestehender Bindung (egal welcher Seite)."""
    slots = dict(WAECHTER_KANTEN)
    if kante not in slots:
        raise ValueError(f"Unbekannte Kante: {kante!r} (erlaubt: {sorted(slots)})")
    slot = slots[kante]
    app_liste = list(app_bereiche)
    je_kontext: dict[str, list[Mapping[str, Any]]] = {}
    for a in app_liste:
        k = (a.get("kontext") or "").strip().lower()
        if k:
            je_kontext.setdefault(k, []).append(a)
    gebunden_kanon = {(a.get("kanon_id") or "").strip()
                      for a in app_liste if (a.get("kanon_id") or "").strip()}
    admin_liste = list(admin_bereiche)
    slot_zaehlung = Counter((b.get(slot) or "").strip().lower()
                            for b in admin_liste if (b.get(slot) or "").strip())
    vorschlaege: list[dict[str, Any]] = []
    for b in admin_liste:
        s = (b.get(slot) or "").strip()
        if not s or b.get("id", "") in gebunden_kanon:
            continue                                  # leer bzw. schon gebunden
        if slot_zaehlung[s.lower()] > 1:
            continue                                  # Admin-seitig doppelt beansprucht
        treffer = je_kontext.get(s.lower(), [])
        if len(treffer) != 1 or (treffer[0].get("kanon_id") or "").strip():
            continue                                  # mehrdeutig bzw. Ziel schon gebunden
        vorschlaege.append({
            "kante": kante, "app_bereich_id": treffer[0].get("id", ""),
            "app_name": treffer[0].get("name", ""), "kanon_id": b.get("id", ""),
            "admin_name": b.get("name", ""), "kontext": s})
    return vorschlaege


# ── ME-1 · Baum + Roll-up (docs/67 §6 — kanonisches Übersichts-Muster) ──────────
def baum_bauen(bereiche: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``parent_id``-Liste → Baum (je Knoten ``kinder``-Liste; Eingabe-Reihenfolge
    bleibt erhalten — ``liste()`` liefert bereits ``sort_order, name``). Fail-safe für
    kaputte Bestände: Knoten mit fehlendem Parent oder Zyklus in der Ahnenkette werden
    zur Wurzel gerettet und tragen ``verwaist=True`` (die CRUD verhindert Zyklen,
    ``_wuerde_zyklus`` — hier Gürtel+Hosenträger)."""
    knoten = {b["id"]: {**b, "kinder": []} for b in bereiche}

    def _anker_ok(bid: str) -> bool:
        gesehen = {bid}
        cur = (knoten[bid].get("parent_id") or "")
        while cur:
            if cur in gesehen or cur not in knoten:
                return False                          # Zyklus bzw. fehlender Parent
            gesehen.add(cur)
            cur = (knoten[cur].get("parent_id") or "")
        return True

    wurzeln: list[dict[str, Any]] = []
    for bid, k in knoten.items():
        pid = (k.get("parent_id") or "")
        if pid and _anker_ok(bid):
            knoten[pid]["kinder"].append(k)
        else:
            if pid:
                k["verwaist"] = True
            wurzeln.append(k)
    return wurzeln


def rollup_zaehler(baum: list[dict[str, Any]],
                   zaehler_je_bereich: Mapping[str, Mapping[str, int]]) -> list[dict[str, Any]]:
    """Reichert den Baum in-place an (und gibt ihn zurück): je Knoten ``zaehler``
    (eigene ``inhalt()``-Zähler), ``rollup`` (inkl. aller Unter-Bereiche, je Schlüssel
    summiert) und ``rollup_gesamt``. Kern des ``/api/bereiche/uebersicht``-Vertrags."""
    def _rek(k: dict[str, Any]) -> Counter[str]:
        eigen = dict(zaehler_je_bereich.get(k["id"], {}) or {})
        summe: Counter[str] = Counter(eigen)
        for kind in k["kinder"]:
            summe.update(_rek(kind))
        k["zaehler"] = eigen
        k["rollup"] = dict(summe)
        k["rollup_gesamt"] = sum(summe.values())
        return summe

    for wurzel in baum:
        _rek(wurzel)
    return baum
