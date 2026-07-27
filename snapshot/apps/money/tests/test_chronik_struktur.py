"""test_chronik_struktur.py — Struktur-Wächter (Vertrag §7 / C-10 / BZ-C-7).

- ``chronik_ausgang`` hat **keine ``user_id``-Spalte** (C-10) ⇒ retention/soft_delete fassen die
  Chronik per Konstruktion nie an.
- Die Konto-Löschung (DSGVO) lässt ``buchungen/postings/festschreibungen`` **unberührt** (BZ-C-7,
  §147-AO-Aufbewahrung überlagert Art. 17) — die anderen Nutzer-Tabellen werden regulär soft-gelöscht.
(``ledger.py`` byte-identisch = Merge-Gate, im DoD per ``git diff`` geprüft.)
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from appkit import auth, chronik
from appkit.auth import DEFAULT_USER_ID
from moneyapp import chronik_naht
from moneyapp import main as mm


@pytest.fixture(autouse=True)
def _reset():
    chronik.reset_kontext()
    auth.reset_identity_provider()
    yield
    chronik.reset_kontext()
    auth.reset_identity_provider()


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_chronik_ausgang_ohne_user_id(tmp_path):
    app = mm.build_app(data_dir=tmp_path)
    spalten = {r["name"] for r in app.state.db.get_conn().execute("PRAGMA table_info(chronik_ausgang)")}
    assert "user_id" not in spalten                        # C-10
    assert {"i", "art", "nutzlast", "nutzlast_hash", "epoche", "subjekt"} <= spalten


def test_konto_loeschung_bewahrt_buchungsdaten(tmp_path):
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        aufw = c.post("/api/konten", json={"name": "Aufwand", "typ": "expense"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                       "betrag": "50,00", "datum": "2026-04-04"})
        c.post("/api/festschreibung", json={"zeitraum": "2026-04"})

        auth.set_identity_provider(lambda _r: auth.UserContext(
            DEFAULT_USER_ID, level="verifiziert", via="dizzi-id", auth_time=time.time() - 5))
        assert c.post("/api/account/loeschen").json()["ok"] is True

        conn = db.get_conn()
        # BZ-C-7: die aufbewahrungspflichtigen Tabellen bleiben UNBERÜHRT (deleted_at IS NULL)
        for t in ("buchungen", "postings", "festschreibungen"):
            aktiv = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE deleted_at IS NULL").fetchone()[0]
            assert aktiv >= 1, f"{t} wurde fälschlich gelöscht (BZ-C-7 verletzt)"
        # Gegenprobe: normale Nutzer-Tabellen (konten) sind regulär soft-gelöscht
        offene_konten = conn.execute("SELECT COUNT(*) FROM konten WHERE deleted_at IS NULL").fetchone()[0]
        assert offene_konten == 0


def test_soft_delete_user_direkt_bewahrt(tmp_path):
    """Die Kaskade selbst (db.soft_delete_user mit moneys behalten-Set) lässt die Tabellen unberührt."""
    with _client(tmp_path) as c:
        db = c.app.state.db
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        aufw = c.post("/api/konten", json={"name": "Aufwand", "typ": "expense"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": giro, "nach_konto": aufw,
                                       "betrag": "9,00", "datum": "2026-05-05"})
        db.soft_delete_user(DEFAULT_USER_ID, behalten=("audit_log", *chronik_naht.BEWAHRE_BEI_LOESCHUNG))
        conn = db.get_conn()
        assert conn.execute("SELECT COUNT(*) FROM buchungen WHERE deleted_at IS NULL").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM postings WHERE deleted_at IS NULL").fetchone()[0] >= 2
