"""F1: appkit-Naht Database.transaktion() — atomarer Schreibblock
(BEGIN IMMEDIATE → COMMIT/ROLLBACK), Nesting fail-loud. Netzfrei."""

from __future__ import annotations

import pytest

from appkit.db import Database


def _db(tmp_path) -> Database:
    db = Database(tmp_path / "tx.sqlite")
    conn = db.get_conn()
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    return db


def test_commit_bei_erfolg(tmp_path):
    db = _db(tmp_path)
    with db.transaktion() as conn:
        conn.execute("INSERT INTO t (x) VALUES (1)")
        conn.execute("INSERT INTO t (x) VALUES (2)")
    assert db.get_conn().execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"] == 2
    assert not db.get_conn().in_transaction     # Txn sauber geschlossen, Write-Lock frei


def test_rollback_bei_exception(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        with db.transaktion() as conn:
            conn.execute("INSERT INTO t (x) VALUES (1)")
            conn.execute("INSERT INTO t (x) VALUES (2)")
            raise RuntimeError("boom mitten im Write")
    assert db.get_conn().execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"] == 0
    assert not db.get_conn().in_transaction
    # Txn geschlossen ⇒ ein anschließendes selbst-committendes db.audit schreibt normal
    db.audit("u1", "user", "ereignis", {"k": "v"})
    assert db.get_conn().execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"] == 1


def test_nesting_fail_loud(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(RuntimeError, match="Transaktion"):
        with db.transaktion() as conn:
            conn.execute("INSERT INTO t (x) VALUES (1)")
            with db.transaktion():          # verschachtelt ⇒ fail-loud
                pass
    assert not db.get_conn().in_transaction                 # äußere Txn per Rollback beendet
    assert db.get_conn().execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"] == 0
