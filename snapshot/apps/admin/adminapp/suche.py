"""Globale Cross-Modul-Suche von Dizz Admin (docs/30 A2) — EINE Suche über ALLE
Module: Tresor-Dokumente · Projekte/Aufgaben/Termine · Rechnungen/Kunden/Produkte/
Support/Geschäfts-Fristen · Studium (Bildungswege). Read-only; bereichs-gefiltert.

Reines Lese-Aggregat über die geteilten Domänen-Tabellen — kein Eingriff in die
Modul-Domänen. ``tabelle``/Spalten stammen aus einer festen Whitelist (``_QUELLEN``)
⇒ String-Interpolation injection-sicher. Pro Quelle eine LIKE-Query (case-insensitiv
via ``COLLATE NOCASE``); ein fehlschlagender Treffer-Topf stört die Suche nie.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel  # noqa: F401  (Konvention)

from appkit.auth import UserContext, current_user
from appkit.db import Database

# (typ, modul, tabelle, such_spalten, titel_spalte, titel_fallback, untertitel_spalte)
# Alle Tabellen tragen user_id/deleted_at/bereich_id (Bereichs-Rückgrat, docs/28 §2.2).
_QUELLEN: tuple[tuple[str, str, str, tuple[str, ...], str, str, str], ...] = (
    ("dokument", "tresor", "dokumente", ("titel", "notiz", "volltext", "korrespondent"), "titel", "datei_name", "typ"),
    ("projekt", "projekte", "projekte", ("name", "beschreibung"), "name", "name", "status"),
    ("aufgabe", "projekte", "aufgaben", ("titel", "notiz"), "titel", "titel", "status"),
    ("termin", "projekte", "termine", ("titel", "ort", "notiz"), "titel", "titel", "beginn"),
    ("rechnung", "geschaeft", "rechnungen", ("nummer", "titel"), "titel", "nummer", "status"),
    ("kunde", "geschaeft", "kunden", ("name", "firma", "email", "notiz"), "name", "name", "firma"),
    ("produkt", "geschaeft", "produkte", ("name", "notiz"), "name", "name", "art"),
    ("support", "geschaeft", "support", ("betreff", "notiz"), "betreff", "betreff", "status"),
    ("frist", "geschaeft", "fristen", ("titel", "kategorie"), "titel", "titel", "kategorie"),
    ("bildungsweg", "studium", "bildungsweg", ("institution", "studiengang", "hauptfach", "nebenfach"),
     "studiengang", "institution", "institution"),
)


class GlobalSuche:
    """Cross-Modul-Volltextsuche (LIKE) über die geteilten Tabellen."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def suche(self, user_id: str, q: str, *, bereich_id: str | None = None,
              limit: int = 40) -> dict[str, Any]:
        q = (q or "").strip()
        if not q:
            return {"q": "", "treffer": [], "anzahl": 0, "je_typ": {}}
        like = f"%{q}%"
        conn = self.db.get_conn()
        treffer: list[dict[str, Any]] = []
        je_typ: dict[str, int] = {}
        pro_quelle = max(1, min(limit, 100))
        for typ, modul, tabelle, spalten, t_sp, t_fb, u_sp in _QUELLEN:
            cols = {t_sp, t_fb, u_sp, *spalten}
            sel = ", ".join(sorted(cols | {"id", "bereich_id"}))
            where = "user_id=? AND deleted_at IS NULL AND (" + \
                    " OR ".join(f"{s} LIKE ? COLLATE NOCASE" for s in spalten) + ")"
            params: list[Any] = [user_id, *([like] * len(spalten))]
            if bereich_id is not None:
                where += " AND bereich_id=?"; params.append(bereich_id)
            try:
                rows = conn.execute(
                    f"SELECT {sel} FROM {tabelle} WHERE {where} LIMIT ?",
                    [*params, pro_quelle]).fetchall()
            except Exception:           # noqa: BLE001 — eine fehlende/leere Tabelle darf die Suche nicht kippen
                continue
            for r in rows:
                titel = (r[t_sp] if t_sp in r.keys() else "") or (r[t_fb] if t_fb in r.keys() else "") or "(ohne Titel)"
                treffer.append({
                    "typ": typ, "modul": modul, "id": r["id"],
                    "titel": str(titel),
                    "untertitel": str((r[u_sp] if u_sp in r.keys() else "") or ""),
                    "bereich_id": (r["bereich_id"] if "bereich_id" in r.keys() else "") or "",
                    "ref": f"admin:{typ}:{r['id']}",
                })
                je_typ[typ] = je_typ.get(typ, 0) + 1
        treffer.sort(key=lambda x: (x["typ"], x["titel"].lower()))
        return {"q": q, "treffer": treffer[:limit], "anzahl": len(treffer), "je_typ": je_typ}

    def build_router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/suche")
        def global_suche(q: str = "", bereich_id: str | None = None, limit: int = 40,
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """EINE Suche über alle Module — optional auf einen Bereich gefiltert
            (None=alle · ''=nur „Allgemein" · id=Bereich). Read-only."""
            return self.suche(user.user_id, q, bereich_id=bereich_id, limit=limit)

        return r
