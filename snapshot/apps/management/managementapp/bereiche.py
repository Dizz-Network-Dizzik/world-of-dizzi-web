"""Bereichs-Rückgrat von Dizz Management — die typisierte **Bereich**-Achse (Area/PARA),
an der sich die Social-Domänen (Kanäle · Social-Bots · Posts/Entwürfe · Zeitplan) je
Kategorie gliedern lassen. Ein **Bereich = „Area"** (laufende Verantwortung ohne Enddatum
— „Social Media Manager für Ludwig Hülsen Nagelfabrik", eine eigene Marke, ein Mandant).

Die generische CRUD-/Hierarchie-/Zuordnungs-Logik kommt aus **``appkit.bereiche``**
(``BereicheBasis`` — Single-Source des Gerüsts, docs/49 §6). Management trägt nur seine
Konfiguration (social-media-naher ``art``-Katalog + Anzeige-Metadaten · FK ``kanaele``/
``social_bots``/``posts`` · die ``kontext``-Spalte = Admins ``bereich.management_kontext``
der V18-Social-Spur) + drei Eigenheiten: kontext-Strip · ``zuordnen``-``updated_at``-Bump
(Domänen-Zeilen tragen ``updated_at``) · ein eigenes ``inhalt`` (mit Post-Status-Aufschlüsselung).
Anders als Admin gibt es KEINE typ-gegateten Module — der Typ ist nur Anlage-/Anzeige-Metadatum.

``bereiche`` trägt ``user_id`` + ``deleted_at`` ⇒ DSGVO greift generisch (appkit ``user_tabellen``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from appkit import bereich_register
from appkit.auth import UserContext, current_user
from appkit.bereiche import BereicheBasis, BereichInBasis, BereichPatchBasis, ZuordnungIn
from appkit.db import Database, now_iso

# Management-eigene Bereich-Typen (social-media-nah; bewusst abweichend vom Admin-/Money-Enum).
# Ein Bereich trägt GENAU EINEN Typ; er gated keine Module (anders als Admin), sondern liefert
# nur Anlage-/Anzeige-Metadaten.
BEREICH_ART = ("kunde", "marke", "kampagne", "projekt", "persoenlich", "sonstiges")
# BER-2 (docs/67 §4.2): jede ``art`` MUSS auf genau eine netzweite Ober-Kategorie mappen.
# Bau-Zeit-Assert — ein neuer art-Wert ohne Mapping bricht den Import sofort (fail-fast).
bereich_register.mapping_validieren(BEREICH_ART)

# Anzeige-Metadaten je Typ (Label · Icon · Default-Farbe) für UI-Anlage/Picker.
BEREICH_ART_META: dict[str, dict[str, str]] = {
    "kunde":       {"label": "Kundenmandat",  "icon": "🤝", "farbe": "amber"},
    "marke":       {"label": "Eigene Marke",  "icon": "✨", "farbe": "cyan"},
    "kampagne":    {"label": "Kampagne",      "icon": "🚀", "farbe": "magenta"},
    "projekt":     {"label": "Projekt",       "icon": "📁", "farbe": "violett"},
    "persoenlich": {"label": "Persönlich",    "icon": "🏠", "farbe": "gruen"},
    "sonstiges":   {"label": "Sonstiges",     "icon": "📦", "farbe": "cyan"},
}
# Default-Typ bei der Anlage = „Eigene Marke" (häufigster Fall in einem Social-Tool).
BEREICH_ART_DEFAULT = "marke"

# Domänen-Tabellen mit ``bereich_id``-FK (Top-Level-Entitäten von Management).
_BEREICH_FK_TABELLEN = ("kanaele", "social_bots", "posts")

# BER-3.1 (docs/67 §5): die ``bereiche``-DDL kommt Single-Source aus appkit
# (``schema_bereiche``), statt sie hier 4× im Netz zu duplizieren (B-4). Management koppelt
# über ``kontext`` (= Admins ``bereich.management_kontext``, V18). Wertgleich zum Alt-Literal
# — der Golden-DDL-Vertragstest (``packages/appkit/tests/test_bereich_register.py``) beweist es.
SCHEMA_BEREICHE = bereich_register.schema_bereiche(("kontext",))


def bereich_typen_katalog() -> list[dict[str, Any]]:
    """Der Management-lokale Typ-Katalog für die UI-Anlage/den Picker:
    je Typ ``{id, label, icon, farbe}`` in fester Reihenfolge."""
    return [{"id": art, **BEREICH_ART_META[art]} for art in BEREICH_ART]


def migriere_bereich(db: Database) -> None:
    """Idempotent: rüstet ``bereich_id`` an den Management-Domänen-Tabellen nach +
    ``plattform`` an ``social_bots`` (optionaler Ziel-Plattform-Slot, ②). So bleibt das
    sensible ``domain.py``-SCHEMA unangetastet. SQLite ``ALTER ADD COLUMN`` ist NICHT
    idempotent ⇒ PRAGMA-table_info-Guard. Indizes erst NACH gesichertem ALTER."""
    conn = db.get_conn()
    for t in _BEREICH_FK_TABELLEN:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        if cols and "bereich_id" not in cols:   # cols leer ⇒ Tabelle (noch) nicht da
            conn.execute(f"ALTER TABLE {t} ADD COLUMN bereich_id TEXT NOT NULL DEFAULT ''")
    bcols = {r["name"] for r in conn.execute("PRAGMA table_info(social_bots)")}
    if bcols and "plattform" not in bcols:
        conn.execute("ALTER TABLE social_bots ADD COLUMN plattform TEXT NOT NULL DEFAULT ''")
    for t in _BEREICH_FK_TABELLEN:
        if {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_bereich ON {t} (user_id, bereich_id)")
    conn.commit()
    # BER-1 (MIG-KANON-1, docs/67 §7 P1): additive kanon_id-Spalte + Index für die Bindung
    # an die kanonische Admin-Bereichs-ID (idempotent, ''-Default ⇒ 0 Verhaltenswechsel).
    bereich_register.migriere_kanon_id(db)


def _strip_kontext(v):
    """``kontext`` ist der stabile V18-Kopplungsschlüssel ⇒ Whitespace normalisieren."""
    return v.strip() if isinstance(v, str) else v


class BereichIn(BereichInBasis):
    art: str = BEREICH_ART_DEFAULT
    kontext: str = ""
    _norm = field_validator("kontext")(_strip_kontext)


class BereichPatch(BereichPatchBasis):
    kontext: str | None = None
    _norm = field_validator("kontext")(_strip_kontext)


class KanonIn(BaseModel):
    """Bindungs-Request für ``PUT /api/bereiche/{bid}/kanon`` (BER-1, docs/67 §3.1)."""

    kanon_id: str = ""


class Bereiche(BereicheBasis):
    """Management-Bereichs-Achse: generische CRUD aus ``appkit.bereiche`` + Management-Konfiguration."""

    arten = BEREICH_ART
    art_default = BEREICH_ART_DEFAULT
    fk_tabellen = _BEREICH_FK_TABELLEN
    kontext_spalten = ("kontext",)

    def _public(self, row) -> dict[str, Any]:
        """Additiv die netzweite ``ober_kategorie`` an die API-Ausgabe hängen
        (BER-2, docs/67 §4.2) — Single-Source via ``bereich_register.mit_ober_kategorie``."""
        return bereich_register.mit_ober_kategorie(row)

    @property
    def register(self) -> bereich_register.DzBereichRegister:
        """``DzBereichRegister`` (Komposition, docs/67 §5.1): kanon_id-Bindung + Dual-Read-
        Auflösung ①kanon→②kontext (V18). Lazy + gecacht."""
        reg = getattr(self, "_register", None)
        if reg is None:
            reg = self._register = bereich_register.DzBereichRegister(
                self.db, kontext_spalte="kontext")
        return reg

    def zuordnen(self, user_id: str, tabelle: str, row_id: str,
                 bereich_id: str) -> dict[str, Any]:
        """Wie ``BereicheBasis.zuordnen``, ABER Management-FK-Tabellen tragen ``updated_at``
        ⇒ bei Re-Zuordnung mitbumpen (Konsistenz der Domänen-Zeile)."""
        if tabelle not in self.fk_tabellen:
            raise HTTPException(400, f"Unbekannte Tabelle: {tabelle!r}.")
        if bereich_id and not self._existiert(user_id, bereich_id):
            raise HTTPException(400, "Bereich existiert nicht.")
        conn = self.db.get_conn()
        row = conn.execute(f"SELECT id FROM {tabelle} WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (row_id, user_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        conn.execute(f"UPDATE {tabelle} SET bereich_id=?, updated_at=? WHERE id=? AND user_id=?",
                     (bereich_id, now_iso(), row_id, user_id))
        conn.commit()
        self.db.audit(user_id, "user", "bereich_zuordnung",
                      {"tabelle": tabelle, "id": row_id, "bereich_id": bereich_id})
        return {"ok": True, "tabelle": tabelle, "id": row_id, "bereich_id": bereich_id}

    def inhalt(self, user_id: str, bereich_id: str) -> dict[str, Any]:
        """Management-Override: Zähler je Domänen-Tabelle (Kanäle · Social-Bots · Posts;
        ALLE Tabellen, auch mit 0) + Posts zusätzlich je Status (Redaktions-Stand)."""
        conn = self.db.get_conn()
        zaehler: dict[str, int] = {}
        for t in self.fk_tabellen:
            n = conn.execute(f"SELECT count(*) FROM {t} WHERE user_id=? AND bereich_id=? "
                             "AND deleted_at IS NULL", (user_id, bereich_id)).fetchone()[0]
            zaehler[t] = n
        post_status = {
            r["status"]: r["n"] for r in conn.execute(
                "SELECT status, count(*) AS n FROM posts WHERE user_id=? AND bereich_id=? "
                "AND deleted_at IS NULL GROUP BY status", (user_id, bereich_id)).fetchall()}
        return {"bereich_id": bereich_id, "zaehler": zaehler,
                "post_status": post_status, "gesamt": sum(zaehler.values())}

    # --- Router -------------------------------------------------------------
    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/bereich-typen")
        def bereich_typen(user: UserContext = Depends(current_user)):
            """Management-lokaler Bereich-Typ-Katalog: je Typ Label/Icon/Farbe (für UI-Anlage/
            Picker). Read-only; KEINE typ-gegateten Module (anders als Admin)."""
            return {"typen": bereich_typen_katalog(), "default": BEREICH_ART_DEFAULT}

        @r.get("/api/bereiche")
        def bereiche_liste(art: str = "", status: str = "",
                           parent_id: str | None = None,
                           user: UserContext = Depends(current_user)):
            return self.liste(user.user_id, art=art, status=status, parent_id=parent_id)

        @r.post("/api/bereiche")
        def bereich_anlegen(body: BereichIn, user: UserContext = Depends(current_user)):
            return self.anlegen(user.user_id, body)

        # WICHTIG: Literal-Route /zuordnung MUSS vor /{bid} stehen (sonst fängt der
        # {bid}-Platzhalter „zuordnung" als Bereich-id ab).
        @r.put("/api/bereiche/zuordnung")
        def bereich_zuordnen(body: ZuordnungIn, user: UserContext = Depends(current_user)):
            return self.zuordnen(user.user_id, body.tabelle, body.id, body.bereich_id)

        # BER-1: kanon-status-Feed (Broken-Link-Wächter, docs/67 §3.3) — Literal-Route
        # vor /{bid}. ``anker_extra.bots`` = Social-Bot-Namen (die V18-Alt-Kante, docs/34).
        @r.get("/api/bereiche/kanon-status")
        def bereiche_kanon_status(user: UserContext = Depends(current_user)):
            bots = [row["name"] for row in self.db.get_conn().execute(
                "SELECT name FROM social_bots WHERE user_id=? AND deleted_at IS NULL",
                (user.user_id,)).fetchall()]
            return {"ok": True, "bereiche": self.register.kanon_status(user.user_id),
                    "anker_extra": {"bots": bots}}

        @r.get("/api/bereiche/{bid}/inhalt")
        def bereich_inhalt(bid: str, user: UserContext = Depends(current_user)):
            if self._row(user.user_id, bid) is None:
                raise HTTPException(404, "Bereich nicht gefunden.")
            return self.inhalt(user.user_id, bid)

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

        # BER-1: Bindung an die kanonische Admin-Bereichs-ID (docs/67 §3.1; P2-Backfill).
        # 4-segmentige Pfade — kollidieren nicht mit /{bid}. Fail-closed (I-4/I-10).
        @r.put("/api/bereiche/{bid}/kanon")
        def bereich_kanon_binden(bid: str, body: KanonIn,
                                 user: UserContext = Depends(current_user)):
            return self.register.verknuepfen(user.user_id, bid, body.kanon_id)

        @r.delete("/api/bereiche/{bid}/kanon")
        def bereich_kanon_loesen(bid: str, user: UserContext = Depends(current_user)):
            return self.register.loesen(user.user_id, bid)

        return r
