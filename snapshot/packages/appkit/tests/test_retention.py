"""Tests Datenhygiene (Tiefen-Review 12.06.): ``aufbewahrung_tage`` wird
durch ``Database.retention_lauf`` durchgesetzt — Audit/Defense-Journale
wachsen nicht mehr unbegrenzt, frische Einträge bleiben unangetastet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from appkit.db import Database, new_id


def _alt_iso(tage: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=tage)
            ).isoformat(timespec="seconds")


def _audit_zaehler(db: Database) -> int:
    return db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]


def test_retention_loescht_altes_und_behaelt_frisches(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    conn = db.get_conn()
    # ein alter + ein frischer Audit-Eintrag
    for created in (_alt_iso(400), _alt_iso(1)):
        conn.execute(
            "INSERT INTO audit_log (id, user_id, actor, action, detail, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (new_id(), "dizzi", "system", "test", "{}", created))
    # eine längst soft-gelöschte Settings-Zeile (Purge-Kandidat)
    conn.execute(
        "INSERT INTO app_settings (id, user_id, key, value, created_at,"
        " updated_at, deleted_at) VALUES (?,?,?,?,?,?,?)",
        (new_id(), "dizzi", "alt", "1", _alt_iso(400), _alt_iso(400), _alt_iso(400)))
    conn.commit()

    geloescht = db.retention_lauf("dizzi", tage=365)
    assert geloescht.get("audit_log") == 1
    assert geloescht.get("app_settings (purge)") == 1
    # frischer Eintrag + der Retention-Audit selbst bleiben
    assert _audit_zaehler(db) == 2


def test_retention_respektiert_defense_tabellen(tmp_path):
    from appkit.defense import Defense
    db = Database(tmp_path / "app.sqlite")
    Defense(db, "testapp")  # legt die Defense-Tabellen an
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO defense_vorfaelle (id, user_id, client, art, detail,"
        " stufe, created_at) VALUES (?,?,?,?,?,?,?)",
        (new_id(), "dizzi", "1.2.3.4", "alt", "{}", 2, _alt_iso(400)))
    conn.execute(
        "INSERT INTO defense_massnahmen (id, user_id, client, stufe, grund,"
        " bis, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (new_id(), "dizzi", "1.2.3.4", 2, "alt", 0, "abgelaufen",
         _alt_iso(400), _alt_iso(400)))
    # AKTIVE Maßnahme bleibt — egal wie alt (nur der Nutzer hebt sie auf)
    conn.execute(
        "INSERT INTO defense_massnahmen (id, user_id, client, stufe, grund,"
        " bis, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (new_id(), "dizzi", "5.6.7.8", 4, "manuell", 0, "aktiv",
         _alt_iso(400), _alt_iso(400)))
    conn.commit()

    geloescht = db.retention_lauf("dizzi", tage=365)
    assert geloescht.get("defense_vorfaelle") == 1
    assert geloescht.get("defense_massnahmen") == 1
    rest = conn.execute("SELECT status FROM defense_massnahmen").fetchall()
    assert [r["status"] for r in rest] == ["aktiv"]


def test_retention_unter_einem_tag_ist_noop(tmp_path):
    db = Database(tmp_path / "app.sqlite")
    assert db.retention_lauf("dizzi", tage=0) == {}
