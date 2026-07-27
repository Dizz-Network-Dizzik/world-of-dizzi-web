"""Generischer Bereichs-Scaffold (appkit) — die geteilte CRUD-/Hierarchie-/
Zuordnungs-Mechanik der „Area"-Achse (docs/49 BEREICH-TYP-MODELL).

**Warum hier:** Admin · Money · Memory · Management trugen dieselbe Bereichs-CRUD
bisher **4× dupliziert** (~150 Z. identische Logik je App). Dieses Modul ist die
**Single-Source** dieses Gerüsts; jede App leitet ``BereicheBasis`` ab und setzt nur
ihre Konfiguration (art-Katalog, FK-Tabellen, kontext-Spalten) bzw. überschreibt den
``_public``-Hook. **Kanonische Heimat des Typ-Modells bleibt Dizz Admin**
(``module_fuer_typ``/``bereich_typen_katalog`` — app-spezifisch, NICHT hier).

**Vertrag:** Die App besitzt die ``bereiche``-Tabelle (CREATE TABLE in der App, inkl.
ihrer kontext-Spalten) und den Router. ``bereiche`` trägt ``user_id`` + ``deleted_at``
⇒ DSGVO-Export/Lösch-Kaskade greifen generisch (appkit ``user_tabellen``), kein
Per-App-Code. Tabellen-Namen in ``zuordnen``/``inhalt`` sind whitelist-geprüft
(``fk_tabellen``) ⇒ sichere Interpolation, kein SQL-Injection.

Beispiel (Memory)::

    class Bereiche(BereicheBasis):
        arten = ("projekt", "lebensbereich", "wissen", "referenz", "sonstiges")
        fk_tabellen = ("ordner", "notizen")
        kontext_spalten = ()        # Memory koppelt nicht über kontext
"""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import HTTPException
from pydantic import BaseModel

from appkit.db import Database, new_id, now_iso

#: Netzweit identischer Status-Katalog (alle 4 Apps gleich).
BEREICH_STATUS: tuple[str, ...] = ("aktiv", "ruhend", "abgeschlossen", "archiviert")


def coerce(wert: str, erlaubt: Sequence[str], default: str) -> str:
    """Klemmt einen Eingabewert auf die erlaubte Menge (sonst Default)."""
    return wert if wert in erlaubt else default


class BereichInBasis(BaseModel):
    """Gemeinsame Anlage-Felder. Apps mit kontext-Kopplung erben + ergänzen sie
    (z. B. ``kontext: str = ""`` bzw. die drei Admin-kontext-Felder)."""

    name: str
    art: str = "sonstiges"
    parent_id: str = ""
    farbe: str = "cyan"
    icon: str = "folder"
    beschreibung: str = ""


class BereichPatchBasis(BaseModel):
    name: str | None = None
    art: str | None = None
    parent_id: str | None = None
    farbe: str | None = None
    icon: str | None = None
    status: str | None = None
    beschreibung: str | None = None
    sort_order: int | None = None


class ZuordnungIn(BaseModel):
    tabelle: str               # Domänen-Tabelle (Whitelist ``fk_tabellen``)
    id: str                    # Zeilen-id der Entität
    bereich_id: str = ""       # '' = Zuordnung lösen (→ Allgemein)


class BereicheBasis:
    """DB-gestützte CRUD + Validierung der Bereichs-Achse (app-unabhängig).

    Unterklassen konfigurieren:
      * ``arten`` — erlaubter art-Katalog (tuple); ungültig ⇒ „sonstiges".
      * ``art_default`` — Default-art bei der Anlage (nur informativ; das Body-Modell trägt den Form-Default).
      * ``fk_tabellen`` — Whitelist der ``bereich_id``-tragenden Domänen-Tabellen (für ``zuordnen``/``inhalt``).
      * ``kontext_spalten`` — zusätzliche Spalten in ``bereiche`` + Body (z. B. ``("kontext",)`` oder
        ``("memory_ref","money_kontext","management_kontext")`` oder ``()``).
    und überschreiben optional ``_public(row)`` (Standard = identisch; Admin hängt ``module`` an).
    """

    arten: tuple[str, ...] = ("sonstiges",)
    art_default: str = "sonstiges"
    fk_tabellen: tuple[str, ...] = ()
    kontext_spalten: tuple[str, ...] = ()

    def __init__(self, db: Database) -> None:
        self.db = db

    # --- Helfer -------------------------------------------------------------
    def _row(self, user_id: str, bid: str):
        return self.db.get_conn().execute(
            "SELECT * FROM bereiche WHERE id=? AND user_id=? AND deleted_at IS NULL",
            (bid, user_id)).fetchone()

    def _existiert(self, user_id: str, bid: str) -> bool:
        return bid == "" or self._row(user_id, bid) is not None

    def _wuerde_zyklus(self, user_id: str, bid: str, neuer_parent: str) -> bool:
        """True, wenn ``neuer_parent`` über die parent-Kette auf ``bid`` zurückführt
        — verhindert Zyklen in der Bereichs-Hierarchie."""
        gesehen = {bid}
        cur = neuer_parent
        while cur:
            if cur in gesehen:
                return True
            gesehen.add(cur)
            row = self._row(user_id, cur)
            cur = row["parent_id"] if row else ""
        return False

    def _public(self, row) -> dict[str, Any]:
        """Row → dict für die API. Standard = identisch; Admin überschreibt
        (hängt das typ-gesteuerte ``module`` an, docs/49)."""
        return dict(row)

    # --- Operationen --------------------------------------------------------
    def liste(self, user_id: str, *, art: str = "", status: str = "",
              parent_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM bereiche WHERE user_id=? AND deleted_at IS NULL"
        args: list[Any] = [user_id]
        if art:
            sql += " AND art=?"; args.append(art)
        if status:
            sql += " AND status=?"; args.append(status)
        if parent_id is not None:
            sql += " AND parent_id=?"; args.append(parent_id)
        sql += " ORDER BY sort_order, name"
        return [self._public(r) for r in self.db.get_conn().execute(sql, args).fetchall()]

    def holen(self, user_id: str, bid: str) -> dict[str, Any] | None:
        row = self._row(user_id, bid)
        return self._public(row) if row else None

    def anlegen(self, user_id: str, body: BereichInBasis) -> dict[str, Any]:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Name fehlt.")
        if body.parent_id and not self._existiert(user_id, body.parent_id):
            raise HTTPException(400, "Übergeordneter Bereich existiert nicht.")
        bid = new_id()
        ts = now_iso()
        spalten = ["id", "user_id", "name", "art", "parent_id", "farbe", "icon",
                   "status", "beschreibung", *self.kontext_spalten,
                   "sort_order", "created_at", "updated_at"]
        werte = [bid, user_id, name, coerce(body.art, self.arten, "sonstiges"),
                 body.parent_id, body.farbe, body.icon, "aktiv", body.beschreibung,
                 *[getattr(body, k, "") for k in self.kontext_spalten], 0, ts, ts]
        conn = self.db.get_conn()
        conn.execute(
            f"INSERT INTO bereiche ({','.join(spalten)}) "
            f"VALUES ({','.join('?' * len(spalten))})", werte)
        conn.commit()
        self.db.audit(user_id, "user", "bereich_angelegt", {"id": bid, "art": body.art})
        return self.holen(user_id, bid)  # type: ignore[return-value]

    def aendern(self, user_id: str, bid: str, body: BereichPatchBasis) -> dict[str, Any]:
        if self._row(user_id, bid) is None:
            raise HTTPException(404, "Bereich nicht gefunden.")
        felder: dict[str, Any] = {}
        if body.name is not None:
            if not body.name.strip():
                raise HTTPException(400, "Name darf nicht leer sein.")
            felder["name"] = body.name.strip()
        if body.art is not None:
            felder["art"] = coerce(body.art, self.arten, "sonstiges")
        if body.status is not None:
            felder["status"] = coerce(body.status, BEREICH_STATUS, "aktiv")
        if body.parent_id is not None:
            if body.parent_id == bid:
                raise HTTPException(400, "Ein Bereich kann nicht sein eigener Übergeordneter sein.")
            if body.parent_id and not self._existiert(user_id, body.parent_id):
                raise HTTPException(400, "Übergeordneter Bereich existiert nicht.")
            if self._wuerde_zyklus(user_id, bid, body.parent_id):
                raise HTTPException(400, "Zyklische Bereichs-Hierarchie nicht erlaubt.")
            felder["parent_id"] = body.parent_id
        for k in ("farbe", "icon", "beschreibung", *self.kontext_spalten, "sort_order"):
            v = getattr(body, k, None)
            if v is not None:
                felder[k] = v
        if felder:
            felder["updated_at"] = now_iso()
            sql = "UPDATE bereiche SET " + ", ".join(f"{k}=?" for k in felder) + \
                  " WHERE id=? AND user_id=?"
            conn = self.db.get_conn()
            conn.execute(sql, [*felder.values(), bid, user_id])
            conn.commit()
            self.db.audit(user_id, "user", "bereich_geaendert", {"id": bid})
        return self.holen(user_id, bid)  # type: ignore[return-value]

    def loeschen(self, user_id: str, bid: str) -> bool:
        """Soft-Delete. Direkte Unter-Bereiche werden zur Wurzel hochgezogen
        (``parent_id=''``) — kein verwaister Teilbaum. Zugeordnete Entitäten
        behalten ihre ``bereich_id`` (zeigen dann auf einen gelöschten Bereich ⇒
        in den Sichten „Allgemein")."""
        if self._row(user_id, bid) is None:
            return False
        conn = self.db.get_conn()
        ts = now_iso()
        conn.execute("UPDATE bereiche SET parent_id='', updated_at=? "
                     "WHERE user_id=? AND parent_id=? AND deleted_at IS NULL",
                     (ts, user_id, bid))
        conn.execute("UPDATE bereiche SET deleted_at=?, updated_at=? "
                     "WHERE id=? AND user_id=? AND deleted_at IS NULL",
                     (ts, ts, bid, user_id))
        conn.commit()
        self.db.audit(user_id, "user", "bereich_geloescht", {"id": bid})
        return True

    def anzahl(self, user_id: str) -> int:
        return self.db.get_conn().execute(
            "SELECT count(*) FROM bereiche WHERE user_id=? AND deleted_at IS NULL "
            "AND status='aktiv'", (user_id,)).fetchone()[0]

    def zuordnen(self, user_id: str, tabelle: str, row_id: str,
                 bereich_id: str) -> dict[str, Any]:
        """Ordnet eine Domänen-Entität (Whitelist ``fk_tabellen``) einem Bereich zu —
        ``bereich_id=''`` löst die Zuordnung (→ Allgemein). ``tabelle`` whitelist-geprüft
        ⇒ Interpolation sicher (kein Injection)."""
        if tabelle not in self.fk_tabellen:
            raise HTTPException(400, f"Unbekannte Tabelle: {tabelle!r}.")
        if bereich_id and not self._existiert(user_id, bereich_id):
            raise HTTPException(400, "Bereich existiert nicht.")
        conn = self.db.get_conn()
        row = conn.execute(f"SELECT id FROM {tabelle} WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (row_id, user_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        conn.execute(f"UPDATE {tabelle} SET bereich_id=? WHERE id=? AND user_id=?",
                     (bereich_id, row_id, user_id))
        conn.commit()
        self.db.audit(user_id, "user", "bereich_zuordnung",
                      {"tabelle": tabelle, "id": row_id, "bereich_id": bereich_id})
        return {"ok": True, "tabelle": tabelle, "id": row_id, "bereich_id": bereich_id}

    def inhalt(self, user_id: str, bereich_id: str) -> dict[str, Any]:
        """„Bereich → alles": Zähler je ``fk_tabellen``-Tabelle der diesem Bereich
        zugeordneten, nicht gelöschten Einträge."""
        conn = self.db.get_conn()
        zaehler: dict[str, int] = {}
        for t in self.fk_tabellen:
            n = conn.execute(f"SELECT count(*) FROM {t} WHERE user_id=? AND bereich_id=? "
                             "AND deleted_at IS NULL", (user_id, bereich_id)).fetchone()[0]
            if n:
                zaehler[t] = n
        return {"bereich_id": bereich_id, "zaehler": zaehler, "gesamt": sum(zaehler.values())}
