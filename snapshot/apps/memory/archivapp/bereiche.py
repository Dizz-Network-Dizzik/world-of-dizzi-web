"""Bereichs-Achse von Dizz Memory — die typisierte Über-Kategorisierung über der
Ablage (PARA-„Area": laufende Verantwortung/Thema ohne Enddatum).

Die generische CRUD-/Hierarchie-/Zuordnungs-Logik kommt aus **``appkit.bereiche``**
(``BereicheBasis`` — Single-Source des Gerüsts, docs/49 §6). Memory trägt nur seine
Konfiguration (ablage-/wissens-naher ``art``-Katalog · FK ``ordner``/``notizen`` ·
KEINE kontext-Spalte) + zwei memory-eigene Stücke: die FK-Migration
(``migriere_bereich_fk``) und die **Notiz-Vererbung** (``effektiv_bereich_where`` +
``inhalt``-Override) — Memory bindet ``bereich_id`` primär am **Ordner**, die Notiz
**erbt** ihn (lose Notizen tragen ihn direkt).

``bereiche`` trägt ``user_id`` + ``deleted_at`` ⇒ DSGVO-Export/Lösch-Kaskade greifen
generisch (appkit ``user_tabellen``). Die ``bereich_id``-FK-Spalten werden idempotent
per ALTER nachgerüstet — das Domänen-``_SCHEMA`` in ``main.py`` bleibt unangetastet.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from appkit import bereich_register
from appkit.auth import UserContext, current_user
from appkit.bereiche import BereicheBasis
from appkit.bereiche import BereichInBasis as BereichIn
from appkit.bereiche import BereichPatchBasis as BereichPatch
from appkit.bereiche import ZuordnungIn
from appkit.db import Database

# Typisierte Achsen — auf das Wissens-/Ablage-Konzept zugeschnitten (vgl. Mem-Collections:
# Projekte · Lebensbereiche · Wissensgebiete · Referenz). ``parent_id`` trägt die Hierarchie.
BEREICH_ART = ("projekt", "lebensbereich", "wissen", "referenz", "sonstiges")
# BER-2 (docs/67 §4.2): jede ``art`` MUSS auf genau eine netzweite Ober-Kategorie mappen.
# Bau-Zeit-Assert — ein neuer art-Wert ohne Mapping bricht den Import sofort (fail-fast).
bereich_register.mapping_validieren(BEREICH_ART)

# BER-3.1 (docs/67 §5): die ``bereiche``-DDL kommt Single-Source aus appkit
# (``schema_bereiche``), statt sie hier 4× im Netz zu duplizieren (B-4). Memory koppelt
# NICHT über ``kontext`` ⇒ keine kontext-Spalte. Wertgleich zum Alt-Literal — der
# Golden-DDL-Vertragstest (``packages/appkit/tests/test_bereich_register.py``) beweist es.
SCHEMA_BEREICHE = bereich_register.schema_bereiche()

# Domänen-Tabellen mit ``bereich_id``-FK: der Ordner ist die primäre Bindung, die Notiz
# kann (für lose Notizen / Override) eine eigene tragen.
_BEREICH_FK_TABELLEN = ("ordner", "notizen")


def migriere_bereich_fk(db: Database) -> None:
    """Idempotent: rüstet ``bereich_id`` (TEXT, ``''`` = Allgemein) an ``ordner`` und
    ``notizen`` nach (+ Index) und dann die BER-1-``kanon_id``-Spalte. Wird beim App-Start
    einmal aufgerufen (fresh wie Bestands-DB). Die FK-Nachrüstung läuft seit BER-3.1 über
    die geteilte appkit-Mechanik (``bereich_register.migriere_bereich_fk``, B-4/docs/67 §5)
    — wortgleich zur vormals memory-lokalen Schleife; Memory bleibt Herrin seiner
    FK-Whitelist ``_BEREICH_FK_TABELLEN``."""
    bereich_register.migriere_bereich_fk(db, _BEREICH_FK_TABELLEN)
    # BER-1 (MIG-KANON-1, docs/67 §7 P1): additive kanon_id-Spalte + Index für die Bindung
    # an die kanonische Admin-Bereichs-ID (idempotent, ''-Default ⇒ 0 Verhaltenswechsel).
    # Memory löst kanon-only auf (kein kontext, docs/67 §6/ME-1); memory_ref bleibt ③-Fallback.
    bereich_register.migriere_kanon_id(db)


def effektiv_bereich_where(alias: str = "n") -> str:
    """SQL-Bedingung „effektiver Bereich der Notiz = :bereich". Eigenes ``bereich_id``
    gewinnt; sonst erbt sie vom Ordner. Erwartet den Parameter ``:bereich`` ZWEIMAL
    (eigenes Feld + Ordner-Unterabfrage) und ``:user`` für die Ordner-Unterabfrage."""
    return (f"(({alias}.bereich_id = :bereich) OR ({alias}.bereich_id = '' "
            f"AND {alias}.ordner_id IN (SELECT id FROM ordner WHERE user_id = :user "
            f"AND bereich_id = :bereich AND deleted_at IS NULL)))")


class KanonIn(BaseModel):
    """Bindungs-Request für ``PUT /api/bereiche/{bid}/kanon`` (BER-1, docs/67 §3.1)."""

    kanon_id: str = ""


class Bereiche(BereicheBasis):
    """Memory-Bereichs-Achse: generische CRUD aus ``appkit.bereiche`` + Notiz-Vererbung."""

    arten = BEREICH_ART
    art_default = "sonstiges"
    fk_tabellen = _BEREICH_FK_TABELLEN
    kontext_spalten = ()        # Memory koppelt nicht über kontext

    def _public(self, row) -> dict[str, Any]:
        """Additiv die netzweite ``ober_kategorie`` (BER-2, docs/67 §4.2) — Single-Source
        via ``bereich_register.mit_ober_kategorie`` (Memory hat sonst kein ``_public``)."""
        return bereich_register.mit_ober_kategorie(row)

    @property
    def register(self) -> bereich_register.DzBereichRegister:
        """``DzBereichRegister`` (Komposition, docs/67 §5.1/§6): Memory bindet kanon-only
        (``kontext_spalte=""`` ⇒ Auflöse-Stufe ② strukturell aus; ③ = Ordner-Name).
        Lazy + gecacht."""
        reg = getattr(self, "_register", None)
        if reg is None:
            reg = self._register = bereich_register.DzBereichRegister(self.db, kontext_spalte="")
        return reg

    def inhalt(self, user_id: str, bereich_id: str) -> dict[str, Any]:
        """Memory-Override: Zähler je Tabelle — direkt zugeordnete Ordner + Notizen mit
        EFFEKTIVEM Bereich = ``bereich_id`` (eigene Zuordnung ODER über den Ordner geerbt)."""
        conn = self.db.get_conn()
        ordner = conn.execute(
            "SELECT count(*) FROM ordner WHERE user_id=? AND bereich_id=? AND deleted_at IS NULL",
            (user_id, bereich_id)).fetchone()[0]
        notizen = conn.execute(
            "SELECT count(*) FROM notizen n WHERE n.user_id=:user AND n.deleted_at IS NULL "
            "AND " + effektiv_bereich_where("n"),
            {"user": user_id, "bereich": bereich_id}).fetchone()[0]
        zaehler = {k: v for k, v in (("ordner", ordner), ("notizen", notizen)) if v}
        return {"bereich_id": bereich_id, "zaehler": zaehler, "gesamt": ordner + notizen}

    # --- Router -------------------------------------------------------------
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

        # WICHTIG: die Literal-Route /zuordnung MUSS vor /{bid} stehen (sonst fängt
        # der {bid}-Platzhalter „zuordnung" als Bereich-id ab).
        @r.put("/api/bereiche/zuordnung")
        def bereich_zuordnen(body: ZuordnungIn, user: UserContext = Depends(current_user)):
            return self.zuordnen(user.user_id, body.tabelle, body.id, body.bereich_id)

        # BER-1: kanon-status-Feed (Broken-Link-Wächter, docs/67 §3.3) — Literal-Route
        # vor /{bid}. ``anker_extra.ordner`` = Ordner-Namen (die V19-Alt-Kante = memory_ref,
        # docs/34/67 §6): OHNE sie meldet der Wächter jeden korrekten memory_ref als dangling.
        @r.get("/api/bereiche/kanon-status")
        def bereiche_kanon_status(user: UserContext = Depends(current_user)):
            ordner = [row["name"] for row in self.db.get_conn().execute(
                "SELECT name FROM ordner WHERE user_id=? AND deleted_at IS NULL",
                (user.user_id,)).fetchall()]
            return {"ok": True, "bereiche": self.register.kanon_status(user.user_id),
                    "anker_extra": {"ordner": ordner}}

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

        # BER-1: Bindung an die kanonische Admin-Bereichs-ID (docs/67 §3.1/§6; P2-Backfill).
        # 4-segmentige Pfade — kollidieren nicht mit /{bid}. Fail-closed (I-4/I-10).
        @r.put("/api/bereiche/{bid}/kanon")
        def bereich_kanon_binden(bid: str, body: KanonIn,
                                 user: UserContext = Depends(current_user)):
            return self.register.verknuepfen(user.user_id, bid, body.kanon_id)

        @r.delete("/api/bereiche/{bid}/kanon")
        def bereich_kanon_loesen(bid: str, user: UserContext = Depends(current_user)):
            return self.register.loesen(user.user_id, bid)

        return r
