"""RG-8 (docs/83 §6): Geschäfts-Kopplung — die admin-Seite (Fristen-Vertrag + Projektion).

Drei dormante Nähte, alle gate-frei mit Fakes:
- **``frist_vorschlagen``** (Registry-Aktion, level ``lokal`` ⇒ Klasse ``entwurf``): die Regie
  schlägt aus einer erkannten Termin-Mail einen Fristen-ENTWURF vor. Der Handler legt ihn in
  eine EIGENE Review-Tabelle (``frist_vorschlaege``) — er fasst weder Aufgaben/Rechnungen noch
  das Fristen-Cockpit an (Admins Bereichs-/Fristen-Heimat bleibt unberührt).
- **``frist_naht``** (Ereignis, Zeiger): der Fristen-Wächter meldet nahende Fristen aus dem
  bestehenden Cockpit in den Spine (v1 nur Ereignis-Strom/Bericht, docs/83 §6). At-least-once:
  der Wächter läuft dormant (kein Scheduler wired), der Konsument dedupt (§1).
- **„Geschäfts-Regie"-Projektion** (read-only): welcher Bereich → welche Agenten/Abos/Läufe.
  Die Wahrheit lebt in Management (Regie-Karte); Admin PROJIZIERT sie über einen injizierbaren
  Fetch (Fake im Test, real = Management-Relay). Ohne Verbindung: ehrlich „nicht verbunden".
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from appkit import ereignis_spine
from appkit.auth import DEFAULT_USER_ID, UserContext, current_user
from appkit.db import Database, new_id, now_iso

#: Ereignis-Typ (Zeiger): eine Frist naht. Nur Skalare (Bereich + Art), kein Titel-Freitext.
FRIST_NAHT = "frist_naht"

#: Admin ist ``sensitivity='hoch'`` ⇒ die Zeiger erreichen nur hoch/höchst-Agenten (lokal_only).
_QUELLE_SENS = "hoch"

#: Dringlichkeits-Stufen (aus dem Cockpit-Bucket), die als „naht" gelten.
NAHT_DRINGLICHKEITEN = ("ueberfaellig", "heute", "woche")

SCHEMA_FRIST_VORSCHLAG = """
CREATE TABLE IF NOT EXISTS frist_vorschlaege (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    bereich_id  TEXT NOT NULL DEFAULT '',
    titel       TEXT NOT NULL DEFAULT '',
    faellig     TEXT NOT NULL DEFAULT '',        -- ISO-Datum (Review; NIE eine echte Aufgabe)
    mail_ref    TEXT NOT NULL DEFAULT '',        -- Herkunft (z. B. kommunikation:nachricht:<id>)
    status      TEXT NOT NULL DEFAULT 'entwurf',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT                             -- KA-H1 Lösch-Invariante (Soft-Delete-Kaskade)
);
"""


def registriere_ereignis_typen(register: Any) -> None:
    """``frist_naht`` im Spine-Register anmelden (nur Skalare)."""
    register.register(FRIST_NAHT, ("bereich_id", "art"))


def frist_vorschlag_anlegen(db: Database, user_id: str, *, titel: str = "", faellig: str = "",
                            bereich_id: str = "", mail_ref: str = "") -> dict[str, Any]:
    """Legt einen Fristen-ENTWURF in die Review-Tabelle (NIE eine echte Aufgabe/Frist)."""
    ts = now_iso()
    vid = new_id()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO frist_vorschlaege (id, user_id, bereich_id, titel, faellig, mail_ref, "
        "status, created_at, updated_at) VALUES (?,?,?,?,?,?,'entwurf',?,?)",
        (vid, user_id, bereich_id, str(titel)[:200], str(faellig)[:32],
         str(mail_ref)[:200], ts, ts))
    conn.commit()
    db.audit(user_id, "user", "frist_vorschlag_angelegt", {"id": vid, "bereich_id": bereich_id})
    return {"id": vid, "status": "entwurf"}


def registriere(actions: Any, db: Database) -> None:
    """Registriert ``frist_vorschlagen`` (level ``lokal`` ⇒ Klasse ``entwurf``, docs/83 §6).
    Der Handler legt nur einen Entwurf ab — keine Aufgabe, keine Frist, kein Cockpit-Write."""
    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        user_id = params.get("user_id", DEFAULT_USER_ID)
        return frist_vorschlag_anlegen(
            db, user_id, titel=params.get("titel", ""), faellig=params.get("faellig", ""),
            bereich_id=params.get("bereich_id", ""), mail_ref=params.get("mail_ref", ""))

    actions.register(
        "frist_vorschlagen", _handler, level="lokal",
        beschreibung="Fristen-Entwurf vorschlagen (entwurf). Legt NIE eine echte Aufgabe/Frist "
                     "an — nur einen Entwurf für Davids Fristen-Cockpit.")


def frist_naht_pruefen(db: Database, fristen: list[dict[str, Any]], *,
                       ereignis_register: Any,
                       dringlichkeiten: tuple[str, ...] = NAHT_DRINGLICHKEITEN,
                       user_id: str = DEFAULT_USER_ID) -> int:
    """Dormanter Fristen-Wächter: emittiert ``frist_naht`` (Zeiger) je nahender Frist aus dem
    bestehenden Cockpit (``FristenCockpit.cockpit``-Einträge: art/faellig/bereich_id/ref +
    dringlichkeit-Bucket). Liefert die Anzahl gemeldeter Fristen. At-least-once — ohne
    Scheduler läuft es nicht von selbst; der Konsument dedupt (§1)."""
    n = 0
    for f in fristen or []:
        if f.get("dringlichkeit") not in dringlichkeiten:
            continue
        ref = str(f.get("ref") or f.get("id") or "")
        with db.transaktion() as conn:
            ereignis_spine.ereignis_anlegen(
                conn, user_id, FRIST_NAHT, register=ereignis_register,
                ref=f"admin:frist:{ref}",
                payload={"bereich_id": f.get("bereich_id", ""), "art": str(f.get("art", ""))[:40]},
                quelle_sens=_QUELLE_SENS)
        n += 1
    return n


def build_router(db: Database,
                 regie_karte_fetch: Callable[[str], dict[str, Any]] | None = None) -> APIRouter:
    """``/api/frist-vorschlaege`` (Review-Liste) + ``/api/geschaefts-regie`` (read-only
    Projektion der Management-Regie-Karte; ``regie_karte_fetch`` injizierbar, sonst ehrlich
    „nicht verbunden")."""
    r = APIRouter()

    @r.get("/api/frist-vorschlaege")
    def frist_vorschlaege(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.get_conn().execute(
            "SELECT id, bereich_id, titel, faellig, mail_ref, status, created_at "
            "FROM frist_vorschlaege WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 200", (user.user_id,)).fetchall()
        return [dict(row) for row in rows]

    @r.get("/api/geschaefts-regie")
    def geschaefts_regie(bereich_id: str = "",
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """Read-only Projektion: welcher Bereich → welche Agenten/Abos/letzten Läufe (docs/83
        §6). Die Wahrheit lebt in Management; hier nur die Anzeige-Projektion."""
        if regie_karte_fetch is None:
            return {"bereich_id": bereich_id, "verbunden": False,
                    "hinweis": "Management-Regie nicht verbunden — Projektion leer."}
        try:
            karte = regie_karte_fetch(bereich_id) or {}
        except Exception as e:
            return {"bereich_id": bereich_id, "verbunden": False,
                    "hinweis": f"Management-Regie nicht erreichbar: {type(e).__name__}"}
        return {"bereich_id": bereich_id, "verbunden": True,
                "agenten": karte.get("agenten", []), "abos": karte.get("abos", []),
                "laeufe": karte.get("laeufe", [])}

    return r
