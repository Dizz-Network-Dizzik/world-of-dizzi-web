"""DzCharta — Verzeichnis-KEIM (V-BIZZI-2, B2 · Runde 3, §B4 / D2).

Die **einzige Subjekt-Quelle** für ``charta.antrag_bauen`` (CH-5): Rollen +
Bereiche je Identität, mit Zeitpunkt-Parameter für Policy-Replay. Zuweisung/Entzug
sind ``verzeichnis.rolle``-Ereignisse (hash_only — Personendaten bleiben löschbar,
Gate #3; die Chronik-Klasse ``verzeichnis.*`` ist dafür reserviert).

★ KEIM, kein Provisorium: B5 baut GENAU dies per Dual-Read zum Vollmodul aus
(SSO/SCIM). ★ Die App-Verdrahtung (WO laut §B4: ``apps/core/app/verzeichnis/``
+ core-DB ``extra_schema``) ist an die Core-Integration deferiert — hier liegt die
wiederverwendbare KEIM-Logik (Single-Source-Muster wie chronik/charta).
"""

from __future__ import annotations

import sqlite3

from . import chronik as C
from .db import new_id, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS verzeichnis_rollen (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  rolle       TEXT NOT NULL,
  bereich_id  TEXT NOT NULL DEFAULT '',
  gueltig_ab  TEXT NOT NULL,
  gueltig_bis TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_verzeichnis_user ON verzeichnis_rollen (user_id, deleted_at);
"""


def _gueltig(conn: sqlite3.Connection, zum: str):
    return conn.execute(
        "SELECT user_id, rolle, bereich_id FROM verzeichnis_rollen "
        "WHERE deleted_at IS NULL AND gueltig_ab<=? AND (gueltig_bis='' OR gueltig_bis>?)",
        (zum, zum))


def rollen_von(conn: sqlite3.Connection, user_id: str, *, zum: str | None = None) -> dict:
    """Rollen + Bereiche einer Identität — nur GÜLTIGE Zeilen. ``zum`` (ISO)
    ermöglicht Replay auf einen historischen Zeitpunkt (gueltig_ab/bis + Soft-Delete)."""
    zum = zum or now_iso()
    rows = conn.execute(
        "SELECT rolle, bereich_id FROM verzeichnis_rollen WHERE user_id=? AND deleted_at IS NULL "
        "AND gueltig_ab<=? AND (gueltig_bis='' OR gueltig_bis>?)", (user_id, zum, zum)).fetchall()
    return {"rollen": {r["rolle"] for r in rows},
            "bereiche": {r["bereich_id"] for r in rows if r["bereich_id"]}}


def zuweisen(conn: sqlite3.Connection, *, user_id: str, rolle: str, bereich_id: str = "",
             gueltig_ab: str | None = None, subjekt: str = "system") -> None:
    """Weist eine Rolle zu (+ ``verzeichnis.rolle``-Ereignis, hash_only) — auf der
    offenen Verbindung, ohne Commit (dieselbe ``db.transaktion()`` wie der Aufrufer)."""
    ts = now_iso()
    conn.execute(
        "INSERT INTO verzeichnis_rollen (id, user_id, rolle, bereich_id, gueltig_ab, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)", (new_id(), user_id, rolle, bereich_id, gueltig_ab or ts, ts, ts))
    C.schreibe(conn, art="verzeichnis.rolle", subjekt=subjekt,
               nutzlast={"tat": "zuweisung", "rolle": rolle, "bereich_id": bereich_id})


def entziehen(conn: sqlite3.Connection, *, user_id: str, rolle: str, bereich_id: str = "",
              subjekt: str = "system") -> None:
    """Entzieht eine Rolle (Soft-Delete + ``verzeichnis.rolle``-Ereignis, hash_only)."""
    ts = now_iso()
    conn.execute(
        "UPDATE verzeichnis_rollen SET deleted_at=?, gueltig_bis=?, updated_at=? "
        "WHERE user_id=? AND rolle=? AND bereich_id=? AND deleted_at IS NULL",
        (ts, ts, ts, user_id, rolle, bereich_id))
    C.schreibe(conn, art="verzeichnis.rolle", subjekt=subjekt,
               nutzlast={"tat": "entzug", "rolle": rolle, "bereich_id": bereich_id})


def belegschaft(conn: sqlite3.Connection, *, edition: str = "bizzi", zum: str | None = None) -> list[dict]:
    """Aggregierte Belegschaft für den Erreichbarkeits-Enumerator (CH-14): Rollen +
    Bereiche je Identität. Assurance/Frische = best case (``hochsicher``/frisch) —
    der Bericht beantwortet „wer ist STRUKTURELL fähig, sofern stark authentifiziert"."""
    zum = zum or now_iso()
    users: dict[str, dict] = {}
    for r in _gueltig(conn, zum):
        u = users.setdefault(r["user_id"], {"rollen": set(), "bereiche": set()})
        u["rollen"].add(r["rolle"])
        if r["bereich_id"]:
            u["bereiche"].add(r["bereich_id"])
    return [{"art": "mensch", "id": uid, "assurance": "hochsicher", "frisch_s": 0,
             "edition": edition, "rollen": sorted(v["rollen"]), "bereiche": sorted(v["bereiche"])}
            for uid, v in sorted(users.items())]
