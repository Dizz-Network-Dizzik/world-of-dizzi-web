"""Perf-Regression (27.06.2026, Funktions-Forscher-Brille): ``/api/konversationen``
aggregiert je Konversation (LEFT JOIN nachrichten + 2 korrelierte Subqueries
„jüngste Nachricht je Konversation"). OHNE Index auf ``nachrichten(konversation_id)``
scannt SQLite die ganze ``nachrichten``-Tabelle je Konversation ⇒ O(K×N): live ~12 s
bei 2150 Konversationen (limit-unabhängig, da GROUP BY/ORDER BY MAX(rowid) vor LIMIT).
Mit ``idx_nachrichten_konv`` wird jede Aggregation/Subquery ein Index-SEEK (~360×).

Dieser Test fängt eine Index-Drift sofort: er prüft (a) dass der Index existiert und
(b) dass der Query-Plan KEINEN vollen ``nachrichten``-Scan mehr enthält.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from kommapp.main import build_app

# Basis-Variante der echten Handler-Query (ohne optionale Filter) — der Plan ist
# datenunabhängig, daher genügt das frisch gebaute Schema ohne Sync.
_KONV_SQL = (
    "SELECT k.id, k.titel, k.kanal_typ, k.konto_id, k.schlummern_bis, "
    "COUNT(n.id) AS nachrichten, "
    "COALESCE(SUM(CASE WHEN n.gelesen=0 THEN 1 ELSE 0 END), 0) AS ungelesen, "
    "(SELECT COALESCE(NULLIF(gesendet_at, ''), created_at) FROM nachrichten "
    " WHERE konversation_id=k.id AND deleted_at IS NULL ORDER BY rowid DESC LIMIT 1) AS letzte, "
    "(SELECT von_adresse FROM nachrichten WHERE konversation_id=k.id AND deleted_at IS NULL "
    " ORDER BY rowid DESC LIMIT 1) AS letzter_von "
    "FROM konversationen k "
    "LEFT JOIN nachrichten n ON n.konversation_id=k.id AND n.deleted_at IS NULL "
    "WHERE k.user_id=? AND k.deleted_at IS NULL "
    "AND (k.schlummern_bis = '' OR k.schlummern_bis <= ?) "
    "GROUP BY k.id ORDER BY MAX(n.rowid) DESC LIMIT ?")


def test_idx_nachrichten_konv_existiert_und_plan_ohne_full_scan(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app):           # Lifespan ⇒ Schema + Indizes sind angelegt
        pass
    dbfile = next(tmp_path.rglob("*.sqlite"))
    con = sqlite3.connect(dbfile)
    try:
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='nachrichten'")}
        assert "idx_nachrichten_konv" in idx, f"Perf-Index fehlt: {idx}"
        plan = [r[3] for r in con.execute(
            "EXPLAIN QUERY PLAN " + _KONV_SQL, ("dizzi", "2026-01-01T00:00", 20))]
    finally:
        con.close()
    # ein voller Scan der nachrichten-Tabelle (Alias ``n`` oder Name) = die Regression
    voll = [p for p in plan if p.startswith("SCAN") and p.split()[1] in ("n", "nachrichten")]
    assert not voll, f"voller nachrichten-Scan im Query-Plan (Perf-Regression): {plan}"
