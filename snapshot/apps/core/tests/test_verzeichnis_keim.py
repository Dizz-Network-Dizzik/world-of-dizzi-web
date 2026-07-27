"""§B4 Verzeichnis-KEIM (V-BIZZI-2, D2) — Core-Naht der Subjekt-Quelle (Lese-Substrat).

Pinnt: Tabelle je Verbindung angelegt (auch Test-DB) · ``rollen_von`` liefert die
Subjekt-Quelle für ``charta.antrag_bauen`` (leer = deny-default, fail-closed) · nur
GÜLTIGE Zeilen (gueltig_ab/bis + Soft-Delete) · Replay-Zeitpunkt ``zum`` ·
``belegschaft``-Aggregat (CH-14) · Lese-Routen. Der schreibende Pfad
(zuweisen/entziehen mit verzeichnis.rolle-Chronik-Events) ist bewusst NICHT hier
(reitet mit dem netzweiten Chronik-Schritt) — die Tests setzen Rollen direkt in die
Tabelle, wie es der spätere Schreibpfad tut.

Die KEIM-Logik selbst ist Single-Source + voll getestet in appkit
(``test_charta_verzeichnis.py``); hier verifizieren wir NUR die Core-Integration.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.config import DEFAULT_USER_ID
from app.main import app
from app.verzeichnis import rollen as keim

client = TestClient(app)

_U = DEFAULT_USER_ID
_U2 = "u:" + "c" * 12
_VOR = "2000-01-01T00:00:00+00:00"
_NACH = "2099-01-01T00:00:00+00:00"


def _rolle_setzen(user_id, rolle, bereich_id="", *, gueltig_ab=None,
                  gueltig_bis="", deleted_at=None):
    """Direkter Insert — simuliert den (deferierten) Schreibpfad ``zuweisen()``."""
    conn = db.get_conn()
    ts = db.now_iso()
    conn.execute(
        "INSERT INTO verzeichnis_rollen (id, user_id, rolle, bereich_id, gueltig_ab, "
        "gueltig_bis, created_at, updated_at, deleted_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (db.new_id(), user_id, rolle, bereich_id, gueltig_ab or ts, gueltig_bis,
         ts, ts, deleted_at))
    conn.commit()


def test_schema_je_verbindung_angelegt():
    """``_ensure_verzeichnis_schema`` legt die Tabelle auch in der frischen Test-DB an."""
    cols = {r["name"] for r in db.get_conn().execute("PRAGMA table_info(verzeichnis_rollen)")}
    assert {"user_id", "rolle", "bereich_id", "gueltig_ab", "gueltig_bis", "deleted_at"} <= cols


def test_leere_quelle_ist_deny_default():
    """Ohne Rolle liefert die Quelle leer ⇒ ``charta.pruefe`` verweigert (CH-1) — ehrlich."""
    assert keim.rollen_von(_U) == {"rollen": [], "bereiche": []}


def test_rollen_von_liefert_gueltige():
    _rolle_setzen(_U, "buchhaltung", "b:kanon")
    _rolle_setzen(_U, "fibu_leitung", "b:kanon")
    assert keim.rollen_von(_U) == {"rollen": ["buchhaltung", "fibu_leitung"],
                                   "bereiche": ["b:kanon"]}


def test_soft_delete_und_abgelaufen_ausgeschlossen():
    _rolle_setzen(_U, "aktiv", "b:1")
    _rolle_setzen(_U, "entzogen", "b:1", deleted_at="2026-07-13T10:00:00+00:00")
    _rolle_setzen(_U, "abgelaufen", "b:1", gueltig_bis=_VOR)     # gueltig_bis in der Vergangenheit
    assert keim.rollen_von(_U)["rollen"] == ["aktiv"]


def test_replay_zeitpunkt():
    """``zum`` liest historisch: eine erst ab _NACH gültige Rolle zählt heute nicht."""
    _rolle_setzen(_U, "zukunft", "b:1", gueltig_ab=_NACH)
    assert keim.rollen_von(_U)["rollen"] == []                  # heute noch nicht gültig
    assert keim.rollen_von(_U, zum=_NACH)["rollen"] == ["zukunft"]


def test_belegschaft_aggregiert():
    _rolle_setzen(_U, "buchhaltung", "b:1")
    _rolle_setzen(_U2, "revision", "b:2")
    leute = {p["id"]: p for p in keim.belegschaft()}
    assert leute[_U]["rollen"] == ["buchhaltung"] and leute[_U]["assurance"] == "hochsicher"
    assert leute[_U2]["bereiche"] == ["b:2"]


def test_route_rollen():
    _rolle_setzen(_U, "buchhaltung", "b:kanon")
    r = client.get("/api/verzeichnis/rollen")
    assert r.status_code == 200
    assert r.json() == {"rollen": ["buchhaltung"], "bereiche": ["b:kanon"]}


def test_route_belegschaft():
    _rolle_setzen(_U, "buchhaltung", "b:kanon")
    r = client.get("/api/verzeichnis/belegschaft")
    assert r.status_code == 200
    assert any(p["id"] == _U and p["rollen"] == ["buchhaltung"] for p in r.json())
