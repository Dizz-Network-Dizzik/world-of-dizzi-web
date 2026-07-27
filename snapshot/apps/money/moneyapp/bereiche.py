"""Bereichs-Rückgrat von Dizz Money — die typisierte **Bereich**-Achse (Area/PARA),
an der sich die Money-Domänen (Konten · Buchungen · Budgets · Cashflow · EÜR · Sparziele ·
Abos) gliedern lassen. Ein **Bereich = „Area"** (laufende Verantwortung ohne Enddatum —
„Geschäftsführung Ludwig Hülsen Nagelfabrik", „Privat", ein Mandant); Konten/Buchungen
leben *in* einem Bereich (``bereich_id``, ``''`` = „Allgemein"/unzugeordnet).

Die generische CRUD-/Hierarchie-/Zuordnungs-Logik kommt aus **``appkit.bereiche``**
(``BereicheBasis`` — Single-Source des Gerüsts, das früher in Admin/Money/Memory/
Management 4× dupliziert war, docs/49 §6). Money trägt nur seine Konfiguration: eigener
finanznaher ``art``-Katalog, FK-Tabellen (Konto/Buchung/Serie), die ``kontext``-Spalte
(= Admins ``bereich.money_kontext`` der V17-Finanzspur) und einen ``zuordnen``-Override
(Money-FK-Tabellen tragen ``updated_at`` und bumpen es bei Re-Zuordnung). Die Pro-Bereich-
Aggregation/das Cockpit sitzen in ``main.py`` (kennt Ledger/``auswertung``), NICHT hier.

``bereiche`` trägt ``user_id`` + ``deleted_at`` ⇒ DSGVO-Export/Lösch-Kaskade greifen
generisch (appkit ``user_tabellen``), kein Per-App-Code.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from appkit import bereich_register
from appkit.auth import UserContext, current_user
from appkit.bereiche import (BereicheBasis, BereichInBasis, BereichPatchBasis,
                             ZuordnungIn)
from appkit.db import Database, now_iso

# Money-eigene Bereich-Typen (finanznah; bewusst abweichend vom Admin-Enum — Nutzer-Wahl).
BEREICH_ART = ("geschaeft", "privat", "projekt", "mandant", "investment", "sonstiges")
# BER-2 (docs/67 §4.2): jede ``art`` MUSS auf genau eine netzweite Ober-Kategorie mappen.
# Bau-Zeit-Assert (fail-fast bei ungemapptem art). ``privat`` → ``persoenlich`` bis MIG-ART-1.
bereich_register.mapping_validieren(BEREICH_ART)

# Money-Domänen-Tabellen, die eine ``bereich_id`` tragen (Konto = Default, Buchung = Override,
# Serie/Abo = direkt). Whitelist ⇒ die ``zuordnen``-SQL-Interpolation ist sicher (kein Injection).
_BEREICH_FK_TABELLEN = ("konten", "buchungen", "serien")

# BER-3.1 (docs/67 §5): die ``bereiche``-DDL kommt Single-Source aus appkit
# (``schema_bereiche``), statt sie hier 4× im Netz zu duplizieren (B-4). Money koppelt
# über ``kontext`` (= Admins ``bereich.money_kontext``, V17). Wertgleich zum Alt-Literal
# — der Golden-DDL-Vertragstest (``packages/appkit/tests/test_bereich_register.py``) beweist es.
# (Die bereich_id-FK-Nachrüstung der Money-Domänen-Tabellen läuft in ``main.py._migriere``.)
SCHEMA_BEREICHE = bereich_register.schema_bereiche(("kontext",))


def migriere_bereich(db: Database) -> None:
    """MIG-KANON-1 (docs/67 §7 P1, BER-1): rüstet die additive ``kanon_id``-Spalte + Index
    idempotent an ``bereiche`` nach — die Bindung an die kanonische Admin-Bereichs-ID.
    Additiv, ``''``-Default ⇒ 0 Verhaltenswechsel (Auflösung bleibt Stufe-0-wertgleich,
    solange keine Bindung gesetzt ist, docs/67 I-3/I-7).

    Anders als Admin/Management/Memory kennt Money bisher **keine** eigene bereiche-
    Migrationsfunktion (die Spalten-Nachrüstung läuft in ``main.py._migriere`` für die
    Domänen-Tabellen); die kanon-Spalte wird daher beim Aufbau der Bereichs-Achse sicher-
    gestellt (``Bereiche.__init__``, einmal beim App-Start) — idempotent, ledger-fremd."""
    bereich_register.migriere_kanon_id(db)


def _strip_kontext(v):
    """``kontext`` ist der stabile V17-Kopplungsschlüssel ⇒ Whitespace normalisieren."""
    return v.strip() if isinstance(v, str) else v


class BereichIn(BereichInBasis):
    kontext: str = ""
    _norm = field_validator("kontext")(_strip_kontext)


class BereichPatch(BereichPatchBasis):
    kontext: str | None = None
    _norm = field_validator("kontext")(_strip_kontext)


class KanonIn(BaseModel):
    """Bindungs-Request für ``PUT /api/bereiche/{bid}/kanon`` (BER-1, docs/67 §3.1)."""

    kanon_id: str = ""


class Bereiche(BereicheBasis):
    """Money-Bereichs-Achse: generische CRUD aus ``appkit.bereiche`` + Money-Konfiguration."""

    arten = BEREICH_ART
    art_default = "sonstiges"
    fk_tabellen = _BEREICH_FK_TABELLEN
    kontext_spalten = ("kontext",)

    def __init__(self, db: Database) -> None:
        super().__init__(db)
        # Money hat keine dedizierte startup-Migration in bereiche.py (s. migriere_bereich);
        # die additive kanon_id-Spalte wird hier einmal beim Aufbau der Achse sichergestellt.
        migriere_bereich(db)

    def _public(self, row) -> dict[str, Any]:
        """Additiv die netzweite ``ober_kategorie`` an die API-Ausgabe hängen
        (BER-2, docs/67 §4.2) — Single-Source via ``bereich_register.mit_ober_kategorie``."""
        return bereich_register.mit_ober_kategorie(row)

    @property
    def register(self) -> bereich_register.DzBereichRegister:
        """``DzBereichRegister`` (Komposition, docs/67 §5.1): kanon_id-Bindung + Dual-Read-
        Auflösung ①kanon→②kontext auf derselben ``bereiche``-Tabelle. Lazy + gecacht."""
        reg = getattr(self, "_register", None)
        if reg is None:
            reg = self._register = bereich_register.DzBereichRegister(
                self.db, kontext_spalte="kontext")
        return reg

    def zuordnen(self, user_id: str, tabelle: str, row_id: str,
                 bereich_id: str) -> dict[str, Any]:
        """Wie ``BereicheBasis.zuordnen``, ABER Money-FK-Tabellen (konten/buchungen/serien)
        tragen ``updated_at`` ⇒ bei Re-Zuordnung mitbumpen (Konsistenz der Domänen-Zeile)."""
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

    # --- Router (CRUD; Zuordnung/Cockpit folgen Money-spezifisch in main.py) ----
    def build_router(self) -> APIRouter:
        r = APIRouter()

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

        # BER-1: kanon-status-Feed (Broken-Link-Wächter, docs/67 §3.3) — ebenfalls
        # Literal-Route, MUSS vor /{bid} stehen. Read-only, in jeder Migrationsphase
        # gültig (fehlt die kanon_id-Spalte ⇒ kanon_id='').
        @r.get("/api/bereiche/kanon-status")
        def bereiche_kanon_status(user: UserContext = Depends(current_user)):
            return {"ok": True, "bereiche": self.register.kanon_status(user.user_id),
                    "anker_extra": {}}   # V17-Alt-Schlüssel = kontext/Bereichs-Name (im Feed)

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
        # 4-segmentige Pfade — kollidieren nicht mit /{bid}. Fail-closed (Eindeutigkeit I-4,
        # MIG-KANON-1 nötig); die EINZIGEN kanon_id-Schreiber (I-10).
        @r.put("/api/bereiche/{bid}/kanon")
        def bereich_kanon_binden(bid: str, body: KanonIn,
                                 user: UserContext = Depends(current_user)):
            return self.register.verknuepfen(user.user_id, bid, body.kanon_id)

        @r.delete("/api/bereiche/{bid}/kanon")
        def bereich_kanon_loesen(bid: str, user: UserContext = Depends(current_user)):
            return self.register.loesen(user.user_id, bid)

        return r
