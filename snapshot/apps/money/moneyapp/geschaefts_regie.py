"""RG-8 (docs/83 §6): Geschäfts-Kopplung — die dormante ``beleg_vorschlagen``-Naht (money).

Die Agenten-Regie **schlägt** einen Beleg vor, **Money bucht** (nie der Agent). Die
geld-Klasse erzwingt das bereits im Katalog (App ``finanzen`` ⇒ ``KLASSEN_BODEN`` =
pre_approval, unlockbar); diese Naht fügt nur den Registry-VERTRAG ``beleg_vorschlagen``
hinzu (level ``hochsicher`` ⇒ Klasse ``geld``) + das Ereignis ``beleg_angelegt`` (Zeiger).

**Dormant + geld-sicher (docs/83 §6 „kein EÜR-/Buchungs-Code angefasst"):** der Handler legt
einen Beleg-ENTWURF in eine EIGENE Review-Tabelle (``beleg_vorschlaege``) — er fasst weder
``ledger``/Buchungen noch EÜR noch Festschreibung an. David prüft die Entwürfe und hebt sie
über Moneys bestehende, manuelle Belegs→EÜR-Strecke (Festschreibung = Siegel, unangetastet).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from appkit import ereignis_spine
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, new_id, now_iso

#: Ereignis-Typ (Zeiger): ein Beleg-Entwurf wurde angelegt. v1 speist NUR den Ereignis-Strom
#: (docs/83 §6-Tabelle) — kein Konsument zündet daraus.
BELEG_ANGELEGT = "beleg_angelegt"

#: Money ist ``sensitivity='hoch'`` ⇒ die Zeiger erreichen via ``ereignis_zustellbar`` nur
#: hoch/höchst-Agenten (lokal_only).
_QUELLE_SENS = "hoch"

SCHEMA_BELEG_VORSCHLAG = """
CREATE TABLE IF NOT EXISTS beleg_vorschlaege (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    bereich_id    TEXT NOT NULL DEFAULT '',
    betrag_minor  INTEGER NOT NULL DEFAULT 0,    -- int Minor-Units (nur Review/Anzeige, NIE gebucht)
    waehrung      TEXT NOT NULL DEFAULT 'EUR',
    gegenpartei   TEXT NOT NULL DEFAULT '',
    zweck         TEXT NOT NULL DEFAULT '',
    mail_ref      TEXT NOT NULL DEFAULT '',       -- Herkunft (z. B. kommunikation:nachricht:<id>)
    status        TEXT NOT NULL DEFAULT 'entwurf',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT                            -- KA-H1 Lösch-Invariante (Soft-Delete-Kaskade)
);
"""


def registriere_ereignis_typen(register: Any) -> None:
    """``beleg_angelegt`` im Spine-Register anmelden (nur Skalare, kein Betrag/Zweck-Freitext)."""
    register.register(BELEG_ANGELEGT, ("bereich_id", "status"))


def _betrag_minor(wert: Any) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0


def beleg_vorschlag_anlegen(db: Database, user_id: str, *, bereich_id: str = "",
                            betrag_minor: Any = 0, waehrung: str = "EUR",
                            gegenpartei: str = "", zweck: str = "", mail_ref: str = "",
                            ereignis_register: Any = None) -> dict[str, Any]:
    """Legt einen Beleg-ENTWURF in die Review-Tabelle (NIE eine Buchung) und emittiert
    ``beleg_angelegt`` als Zeiger in DERSELBEN Tx (Outbox-Garantie, docs/83 §1). Rein
    additiv — der ledger/EÜR-Kern wird nicht berührt."""
    ts = now_iso()
    vid = new_id()
    with db.transaktion() as conn:
        conn.execute(
            "INSERT INTO beleg_vorschlaege (id, user_id, bereich_id, betrag_minor, waehrung, "
            "gegenpartei, zweck, mail_ref, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,'entwurf',?,?)",
            (vid, user_id, bereich_id, _betrag_minor(betrag_minor), (waehrung or "EUR")[:8],
             str(gegenpartei)[:200], str(zweck)[:500], str(mail_ref)[:200], ts, ts))
        if ereignis_register is not None:
            ereignis_spine.ereignis_anlegen(
                conn, user_id, BELEG_ANGELEGT, register=ereignis_register,
                ref=f"finanzen:beleg_vorschlag:{vid}",
                payload={"bereich_id": bereich_id, "status": "entwurf"},
                quelle_sens=_QUELLE_SENS)
    db.audit(user_id, "user", "beleg_vorschlag_angelegt",
             {"id": vid, "bereich_id": bereich_id})
    return {"id": vid, "status": "entwurf", "gebucht": False}


def registriere(actions: Any, db: Database, ereignis_register: Any = None) -> None:
    """Registriert ``beleg_vorschlagen`` (level ``hochsicher`` ⇒ Klasse ``geld`` ⇒ Boden
    pre_approval, docs/83 §6). Der Handler bucht NIE — er legt einen Entwurf ab."""
    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        user_id = params.get("user_id", DEFAULT_USER_ID)
        return beleg_vorschlag_anlegen(
            db, user_id, bereich_id=params.get("bereich_id", ""),
            betrag_minor=params.get("betrag_minor", params.get("betrag", 0)),
            waehrung=params.get("waehrung", "EUR"),
            gegenpartei=params.get("gegenpartei", ""),
            zweck=params.get("zweck", ""), mail_ref=params.get("mail_ref", ""),
            ereignis_register=ereignis_register)

    actions.register(
        "beleg_vorschlagen", _handler, level="hochsicher",
        beschreibung="Beleg-ENTWURF vorschlagen (geld ⇒ immer pre_approval). Legt NIE eine "
                     "Buchung an — nur einen Entwurf für Davids Belegs→EÜR-Strecke.")


def build_router(db: Database) -> APIRouter:
    """Read-only Liste der Beleg-Entwürfe (Review-Fläche; die Buchung bleibt Davids Hand)."""
    r = APIRouter()

    @r.get("/api/beleg-vorschlaege")
    def beleg_vorschlaege(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, bereich_id, betrag_minor, waehrung, gegenpartei, zweck, mail_ref, "
            "status, created_at FROM beleg_vorschlaege WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 200", (user.user_id,)).fetchall()
        return [dict(row) for row in rows]

    return r
