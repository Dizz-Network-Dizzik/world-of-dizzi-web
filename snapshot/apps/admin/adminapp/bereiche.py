"""Bereichs-Rückgrat von Dizz Admin (docs/28 §2) — die typisierte Kontext-/
Kategorie-Achse, an der ALLE Module hängen (Tresor · Projekte · Geschäft ·
Studium · Fristen). PARA-Prinzip: ein **Bereich = „Area"** (laufende Verantwortung
ohne Enddatum — „Studium Informatik", „Geschäft X", ein Mandant); ein Projekt /
eine Rechnung / ein Dokument lebt *in* einem Bereich (``bereich_id``-FK, ``''`` =
„Allgemein"/unzugeordnet).

Eigenes Modul (wird beim Domänen-Split Phase 2 zu ``domain/bereiche.py``). Die
``bereich_id``-Spalten der Domänen-Tabellen werden idempotent per ALTER nachgerüstet
(``migriere_bereich_fk``) — das sensible ``domain.py``-SCHEMA bleibt unangetastet;
die per-Entity-CRUD-Verdrahtung folgt mit der Modul-Migration (Phase 2/3).

``bereiche`` trägt ``user_id`` + ``deleted_at`` ⇒ DSGVO-Export/Lösch-Kaskade
(appkit ``user_tabellen``) greifen ohne Per-App-Code.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from appkit import bereich_register
from appkit.auth import UserContext, current_user
from appkit.bereiche import BereicheBasis, BereichInBasis, BereichPatchBasis, ZuordnungIn
from appkit.db import Database

# ── Bereich-Typ-Modell (KANONISCH, docs/49_BEREICH_TYP_MODELL) ─────────────────
# Admin ist die Heimat der ``bereich``-Entität: der **Typ** (``art``) eines Bereichs
# schaltet die für ihn relevanten Module frei (Bereich-first-Navigation). Genau EIN
# Typ je Bereich; General-Module sind immer da, Spezial-Module hängen am Typ. Money/
# Memory koppeln lose über kontext-Strings (V17/18/19) und richten sich nach der Spec.
BEREICH_ART = ("geschaeft", "studium", "mandant", "fortbildung", "persoenlich", "sonstiges")
# BER-2 (docs/67 §4.2): jede ``art`` MUSS auf genau eine netzweite Ober-Kategorie mappen.
# Bau-Zeit-Assert — ein neuer art-Wert ohne Mapping bricht den Import sofort (fail-fast).
bereich_register.mapping_validieren(BEREICH_ART)
BEREICH_STATUS = ("aktiv", "ruhend", "abgeschlossen", "archiviert")

# Module, die JEDER Bereich trägt (typ-unabhängig).
ALLGEMEINE_MODULE = ("uebersicht", "tresor", "projekte", "fristen")
# Spezial-Module je Typ (ZUSÄTZLICH zu den General-Modulen).
TYP_SPEZIAL_MODULE: dict[str, tuple[str, ...]] = {
    "geschaeft": ("geschaeft",),
    "mandant": ("geschaeft",),          # ein Mandant trägt Geschäfts-Vorgänge (Rechnungen …)
    "studium": ("studium",),
    "fortbildung": ("studium",),        # Fortbildung nutzt die Studien-Werkzeuge
    "persoenlich": (),
    "sonstiges": (),
}
# Anzeige-Metadaten je Typ (Label · Icon · Default-Farbe) für die UI-Anlage/den Picker.
BEREICH_TYP_META: dict[str, dict[str, str]] = {
    "geschaeft":   {"label": "Geschäft",             "icon": "💼", "farbe": "amber"},
    "studium":     {"label": "Studium",              "icon": "🎓", "farbe": "cyan"},
    "mandant":     {"label": "Mandant",              "icon": "🤝", "farbe": "violett"},
    "fortbildung": {"label": "Fortbildung",          "icon": "📚", "farbe": "gruen"},
    "persoenlich": {"label": "Persönlich Allgemein", "icon": "🏠", "farbe": "magenta"},
    "sonstiges":   {"label": "Sonstiges",            "icon": "📁", "farbe": "cyan"},
}
# Default-Typ bei der Anlage = „Persönlich Allgemein" (Heimat für Persönlich-Übergreifendes).
# Hinweis: ein EXPLIZIT ungültiger ``art``-Wert wird neutral zu „sonstiges" geklemmt
# (``_coerce``); fehlt ``art`` ganz, greift dieser Form-Default.
BEREICH_ART_DEFAULT = "persoenlich"

# Kanonische Tab-Reihenfolge der Module (General + Spezial mittig, „Fristen" zuletzt).
_MODUL_REIHENFOLGE = ("uebersicht", "tresor", "projekte", "geschaeft", "studium", "fristen")


def module_fuer_typ(art: str) -> list[str]:
    """Die sichtbaren Module eines Bereichs-Typs: General + typ-spezifisch, dedupliziert,
    in kanonischer Tab-Reihenfolge. Unbekannter Typ ⇒ nur die General-Module."""
    erlaubt = set(ALLGEMEINE_MODULE) | set(TYP_SPEZIAL_MODULE.get(art, ()))
    return [m for m in _MODUL_REIHENFOLGE if m in erlaubt]


def bereich_typen_katalog() -> list[dict[str, Any]]:
    """Der kanonische Typ-Katalog (UI-Anlage + App-übergreifender Vertrag, docs/49):
    je Typ ``{id, label, icon, farbe, module}`` in fester Reihenfolge."""
    return [{"id": art, **BEREICH_TYP_META[art], "module": module_fuer_typ(art)}
            for art in BEREICH_ART]

# BER-3.1 (docs/67 §5): die ``bereiche``-DDL kommt Single-Source aus appkit
# (``schema_bereiche``), statt sie hier 4× im Netz zu duplizieren (B-4). Admin ist die Heimat
# der Entität und trägt die drei V17/18/19-kontext-Slots (memory_ref/money_kontext/
# management_kontext); es trägt selbst KEINE ``kanon_id`` (es IST der Kanon, I-2). Wertgleich
# zum Alt-Literal — der Golden-DDL-Vertragstest (``packages/appkit/tests/…``) beweist es.
SCHEMA_BEREICHE = bereich_register.schema_bereiche(
    ("memory_ref", "money_kontext", "management_kontext"))

# Domänen-Tabellen, die eine ``bereich_id``-FK tragen (Top-Level-Entitäten; Positionen
# erben über die Rechnung, Studienmodul/-frist über den Bildungsweg, kpi_snapshot ist
# Aggregat). Geschäft+Studium (leading) + Projekte (Plans, Phase 2C). Tresor folgt.
# Die per-Entity-CRUD-Verdrahtung von ``bereich_id`` ist die spätere Zuordnungs-Phase.
_BEREICH_FK_TABELLEN = ("kunden", "produkte", "rechnungen", "fristen", "support", "bildungsweg",
                        "projekte", "aufgaben", "termine", "dokumente")


def migriere_bereich_fk(db: Database) -> None:
    """Idempotent: rüstet ``bereich_id`` (TEXT, ``''`` = Allgemein) an den Domänen-
    Tabellen nach UND topt neue Kontext-Spalten der ``bereiche``-Tabelle nach (z. B.
    ``management_kontext``, A5/V18). Fresh wie Bestands-DB — SQLite ADD COLUMN ist nicht
    idempotent, daher PRAGMA-table_info-Guard. Wird beim App-Start einmal aufgerufen.

    Die ``bereich_id``-FK-Nachrüstung läuft seit BER-3.1 über die geteilte appkit-Mechanik
    (``bereich_register.migriere_bereich_fk``, B-4/docs/67 §5) — wortgleich zur vormals
    admin-lokalen Schleife (inline-Index); Admin bleibt Herr seiner FK-Whitelist. Die
    bereiche-eigenen Nachzügler-Schritte (``management_kontext``, ``privat``→``persoenlich``)
    bleiben admin-lokal. Admin trägt selbst KEINE ``kanon_id`` (es IST der Kanon, I-2)."""
    bereich_register.migriere_bereich_fk(db, _BEREICH_FK_TABELLEN)
    conn = db.get_conn()
    # Nachzügler-Spalten der bereiche-Tabelle (additive A5-Kontext-Slots auf Bestands-DBs).
    bcols = {r["name"] for r in conn.execute("PRAGMA table_info(bereiche)")}
    if bcols and "management_kontext" not in bcols:
        conn.execute("ALTER TABLE bereiche ADD COLUMN management_kontext TEXT NOT NULL DEFAULT ''")
    # Bereich-Typ-Modell (docs/49): Alt-Typ ``privat`` → ``persoenlich`` (sanft, idempotent —
    # nach dem ersten Lauf trifft kein Datensatz mehr zu; KEINE Daten verschoben/gelöscht).
    if bcols:
        conn.execute("UPDATE bereiche SET art='persoenlich' WHERE art='privat'")
    conn.commit()


# ── Modelle (Basis aus appkit; admin-eigene kontext-Felder V17/18/19) ──────────
class BereichIn(BereichInBasis):
    art: str = BEREICH_ART_DEFAULT
    memory_ref: str = ""
    money_kontext: str = ""
    management_kontext: str = ""


class BereichPatch(BereichPatchBasis):
    memory_ref: str | None = None
    money_kontext: str | None = None
    management_kontext: str | None = None


class Bereiche(BereicheBasis):
    """Admin-Bereichs-Rückgrat: generische CRUD aus ``appkit.bereiche`` (``BereicheBasis``)
    + admin-Spezifika (Typ-Modul-Hook ``_public`` · Export-Bundle). Admin ist die kanonische
    Heimat des Typ-Modells (``module_fuer_typ``/``bereich_typen_katalog``)."""

    arten = BEREICH_ART
    art_default = BEREICH_ART_DEFAULT
    fk_tabellen = _BEREICH_FK_TABELLEN
    kontext_spalten = ("memory_ref", "money_kontext", "management_kontext")

    def __init__(self, db: Database, vault_root: Path | None = None) -> None:
        super().__init__(db)
        self.vault_root = Path(vault_root) if vault_root else None  # A3-Export: Dokument-Dateien

    def _public(self, row) -> dict[str, Any]:
        """Admin-Override: additiv die netzweite ``ober_kategorie`` (BER-2, docs/67 §4.2)
        + das typ-gesteuerte ``module`` (docs/49). Beide gaten das Frontend, ohne ein
        Mapping zu doppeln; die Ober-Kategorie liegt ÜBER dem Typ-Modell (gated keine
        Module, I-9)."""
        d = bereich_register.mit_ober_kategorie(row)
        d["module"] = module_fuer_typ(d.get("art", ""))
        return d

    # --- A3: Bereichs-Export-Bundle (DSGVO-Portabilität, docs/30) -----------
    def _rows(self, sql: str, params: list) -> list[dict[str, Any]]:
        try:
            return [dict(r) for r in self.db.get_conn().execute(sql, params).fetchall()]
        except Exception:   # noqa: BLE001 — fehlende Tabelle darf das Bundle nicht kippen
            return []

    def export_bundle(self, user_id: str, bereich_id: str) -> tuple[bytes, str]:
        """Packt ALLE Inhalte eines Bereichs als ZIP: ``bereich.json`` (Stammdaten) +
        je Modul-Tabelle eine JSON (zugeordnete, nicht gelöschte Einträge) + die
        Kind-Datensätze (Rechnungs-Positionen/Mahnungen, Studienmodule/-fristen,
        Abo-Vorlagen) + die Vault-Dateien der Dokumente (verschlüsselte nur als
        Hinweis). Reines Lese-Aggregat — verändert nichts. ``(zip_bytes, dateiname)``."""
        bereich = self.holen(user_id, bereich_id)   # None ⇒ Aufrufer hat 404 geprüft
        manifest: dict[str, Any] = {
            "app": "admin", "format": "dizz-admin-bereich-export/1",
            "exportiert_am": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bereich_id": bereich_id, "bereich_name": (bereich or {}).get("name", ""),
            "tabellen": {}, "dateien": 0, "verschluesselt_uebersprungen": 0,
            "hinweis": ("DSGVO-Datenportabilität: alle diesem Bereich zugeordneten Inhalte "
                        "aus Dizz Admin. Verschlüsselte Dokument-Dateien sind aus "
                        "Sicherheitsgründen nicht enthalten (nur Metadaten)."),
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            if bereich:
                z.writestr("bereich.json", json.dumps(bereich, ensure_ascii=False, indent=2))
            # Haupttabellen (generisch über die Bereichs-FK-Whitelist)
            for t in _BEREICH_FK_TABELLEN:
                rows = self._rows(f"SELECT * FROM {t} WHERE user_id=? AND bereich_id=? "
                                  "AND deleted_at IS NULL", [user_id, bereich_id])
                if rows:
                    manifest["tabellen"][t] = len(rows)
                    z.writestr(f"{t}.json", json.dumps(rows, ensure_ascii=False, indent=2))
            # Kind-Datensätze an ihren Parents (Rechnung/Bildungsweg)
            rechn_ids = [r["id"] for r in self._rows(
                "SELECT id FROM rechnungen WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL",
                [user_id, bereich_id])]
            for kind in ("rechnung_positionen", "mahnungen"):
                if rechn_ids:
                    ph = ",".join("?" * len(rechn_ids))
                    rows = self._rows(
                        f"SELECT * FROM {kind} WHERE user_id=? AND rechnung_id IN ({ph}) "
                        "AND deleted_at IS NULL", [user_id, *rechn_ids])
                    if rows:
                        manifest["tabellen"][kind] = len(rows)
                        z.writestr(f"{kind}.json", json.dumps(rows, ensure_ascii=False, indent=2))
            bw_ids = [r["id"] for r in self._rows(
                "SELECT id FROM bildungsweg WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL",
                [user_id, bereich_id])]
            for kind in ("studienmodul", "studienfrist"):
                if bw_ids:
                    ph = ",".join("?" * len(bw_ids))
                    rows = self._rows(
                        f"SELECT * FROM {kind} WHERE user_id=? AND bildungsweg_id IN ({ph}) "
                        "AND deleted_at IS NULL", [user_id, *bw_ids])
                    if rows:
                        manifest["tabellen"][kind] = len(rows)
                        z.writestr(f"{kind}.json", json.dumps(rows, ensure_ascii=False, indent=2))
            # Abo-Vorlagen dieses Bereichs (eigene bereich_id, nicht in der FK-Whitelist)
            abos = self._rows("SELECT * FROM rechnung_abo WHERE user_id=? AND bereich_id=? "
                              "AND deleted_at IS NULL", [user_id, bereich_id])
            if abos:
                manifest["tabellen"]["rechnung_abo"] = len(abos)
                z.writestr("rechnung_abo.json", json.dumps(abos, ensure_ascii=False, indent=2))
            # Vault-Dateien der Dokumente (unverschlüsselt); verschlüsselte nur zählen
            if self.vault_root is not None:
                for d in self._rows(
                        "SELECT id, datei_pfad, datei_name, verschluesselt FROM dokumente "
                        "WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL",
                        [user_id, bereich_id]):
                    if d.get("verschluesselt"):
                        manifest["verschluesselt_uebersprungen"] += 1
                        continue
                    voll = (self.vault_root / d["datei_pfad"]).resolve()
                    if (voll.is_relative_to(self.vault_root.resolve()) and voll.is_file()):
                        z.writestr(f"dokumente/{d['id']}_{d['datei_name']}", voll.read_bytes())
                        manifest["dateien"] += 1
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        name = (bereich or {}).get("name", "bereich") or "bereich"
        # Header-sicher: nur ASCII-Alnum/-/_ (Umlaute etc. → _, sonst latin-1-Fehler).
        safe = "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "-_" else "_"
                       for ch in name)[:40] or "bereich"
        self.db.audit(user_id, "user", "bereich_exportiert",
                      {"bereich_id": bereich_id, "tabellen": manifest["tabellen"],
                       "dateien": manifest["dateien"]})
        return buf.getvalue(), f"dizz-admin-bereich-{safe}.zip"

    # --- Router -------------------------------------------------------------
    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/bereich-typen")
        def bereich_typen(user: UserContext = Depends(current_user)):
            """Kanonischer Bereich-Typ-Katalog (docs/49): je Typ Label/Icon/Farbe +
            die Module, die er freischaltet. Read-only; der app-übergreifende Vertrag,
            an dem die UI-Anlage hängt (und auf den Money/Memory sich beziehen)."""
            return {"typen": bereich_typen_katalog(),
                    "allgemeine_module": list(ALLGEMEINE_MODULE),
                    "default": BEREICH_ART_DEFAULT}

        @r.get("/api/bereiche")
        def bereiche_liste(art: str = "", status: str = "",
                           parent_id: str | None = None,
                           user: UserContext = Depends(current_user)):
            return self.liste(user.user_id, art=art, status=status, parent_id=parent_id)

        @r.post("/api/bereiche")
        def bereich_anlegen(body: BereichIn, user: UserContext = Depends(current_user)):
            return self.anlegen(user.user_id, body)

        # WICHTIG: die Literal-Route /zuordnung MUSS vor /{bid} stehen (sonst fängt
        # der {bid}-Platzhalter „zuordnung" als Bereich-id ab).
        @r.put("/api/bereiche/zuordnung")
        def bereich_zuordnen(body: ZuordnungIn, user: UserContext = Depends(current_user)):
            return self.zuordnen(user.user_id, body.tabelle, body.id, body.bereich_id)

        @r.get("/api/bereiche/waechter")
        def bereiche_waechter(user: UserContext = Depends(current_user)):
            """BER-1 Broken-Link-Wächter (docs/67 §3.4): bündelt die ``kanon-status``-Feeds
            der drei Konsumenten (Money/Management/Memory, via Core-Relay, best-effort) und
            klassifiziert je Bereich × Kante (``ok``/``alt``/``dangling``/``mehrdeutig``/
            ``ungenutzt``/``unbekannt``). Read-only — macht verwaiste/fragile Kanten sichtbar,
            statt still ins Leere zu zeigen. Literal-Route ⇒ MUSS vor /{bid} stehen."""
            from . import aggregat
            return aggregat.bereich_waechter(self.liste(user.user_id))

        @r.get("/api/bereiche/{bid}/inhalt")
        def bereich_inhalt(bid: str, user: UserContext = Depends(current_user)):
            if self._row(user.user_id, bid) is None:
                raise HTTPException(404, "Bereich nicht gefunden.")
            return self.inhalt(user.user_id, bid)

        @r.get("/api/bereiche/{bid}/export")
        def bereich_export(bid: str, user: UserContext = Depends(current_user)):
            """A3: alle Inhalte des Bereichs als ZIP-Paket (DSGVO-Portabilität)."""
            if self._row(user.user_id, bid) is None:
                raise HTTPException(404, "Bereich nicht gefunden.")
            daten, dateiname = self.export_bundle(user.user_id, bid)
            return Response(content=daten, media_type="application/zip",
                            headers={"Content-Disposition":
                                     f'attachment; filename="{dateiname}"'})

        @r.get("/api/bereiche/{bid}/cockpit")
        def bereich_cockpit(bid: str, request: Request, jahr: int = 0,
                            user: UserContext = Depends(current_user)):
            """A5 (d, docs/34): Bereichs-Cockpit-Daten — bündelt die drei Querverbindungs-
            Spuren des Bereichs (Finanzspur/Money · Social/Management · Wissen/Memory) über
            die appkit-Helfer + Core-Relays. Read-only, best-effort (Core/Ziel offline ⇒
            leere Spur, kein Fehler). + **Externe-Tool-Konnektoren** dieses Bereichs
            (docs/35 §3, dormant). Die visuelle Cockpit-Darstellung ist UI/UX (§5d)."""
            b = self.holen(user.user_id, bid)
            if b is None:
                raise HTTPException(404, "Bereich nicht gefunden.")
            from . import aggregat
            res = aggregat.bereich_spuren(b, jahr=jahr)
            # Externe-Tool-Konnektoren dieses Bereichs (admin-lokal, dormant).
            konn = getattr(request.app.state, "konnektoren", None)
            res["konnektoren"] = konn.liste(user.user_id, bereich_id=bid) if konn else []
            return res

        @r.get("/api/bereiche/{bid}")
        def bereich_holen(bid: str, user: UserContext = Depends(current_user)):
            b = self.holen(user.user_id, bid)
            if b is None:
                raise HTTPException(404, "Bereich nicht gefunden.")
            return b

        @r.put("/api/bereiche/{bid}")
        def bereich_aendern(bid: str, body: BereichPatch,
                            user: UserContext = Depends(current_user)):
            return self.aendern(user.user_id, bid, body)

        @r.delete("/api/bereiche/{bid}")
        def bereich_loeschen(bid: str, user: UserContext = Depends(current_user)):
            if not self.loeschen(user.user_id, bid):
                raise HTTPException(404, "Bereich nicht gefunden.")
            return {"ok": True}

        return r
