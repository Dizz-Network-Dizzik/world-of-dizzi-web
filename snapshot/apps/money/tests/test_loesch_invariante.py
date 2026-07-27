"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Money.

STATIK: die zwei user_id-Tabellen OHNE deleted_at — ``wechselkurse`` (Kurs-Stammdaten)
+ ``trading_config`` (steuerliche Parameter) — MÜSSEN im Hook-Set stehen. DYNAMIK:
nach Konto-Löschung sind beide für den Nutzer wirklich leer.

Plan-Korrektur (Ehrlichkeit vor Aktivität): Der KA-Härtungs-Plan nahm HOOK_TABELLEN=∅
an ("Hook räumt Globales"). Die Introspektion + der Hook selbst (main.py:2700,
``DELETE FROM {t} WHERE user_id=?``) zeigen aber, dass beide Tabellen user-scoped
sind ⇒ korrigiert auf {wechselkurse, trading_config}."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from appkit import auth
from appkit import loesch_pruefung as lp
from appkit.auth import DEFAULT_USER_ID
from appkit.db import new_id, now_iso
from moneyapp import main as mm

HOOK_TABELLEN = frozenset({"wechselkurse", "trading_config"})


def test_loesch_invariante_statisch(tmp_path):
    app = mm.build_app(data_dir=tmp_path)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=HOOK_TABELLEN) == []


def test_konto_loeschen_raeumt_hook_tabellen(tmp_path):
    auth.reset_identity_provider()
    app = mm.build_app(data_dir=tmp_path)
    try:
        c = TestClient(app)
        conn = app.state.db.get_conn()
        ts = now_iso()
        u = DEFAULT_USER_ID
        conn.execute("INSERT INTO wechselkurse (id,user_id,waehrung,kurs,"
                     "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                     (new_id(), u, "USD", "0.90", ts, ts))
        conn.execute("INSERT INTO trading_config (user_id,updated_at) "
                     "VALUES (?,?)", (u, ts))
        conn.commit()
        assert all(v >= 1 for v in
                   lp.pruefe_hook_loescht(conn, u, HOOK_TABELLEN).values())

        auth.set_identity_provider(lambda _r: auth.UserContext(
            DEFAULT_USER_ID, level="verifiziert", via="dizzi-id",
            auth_time=time.time() - 5))
        assert c.post("/api/account/loeschen").json()["ok"] is True

        assert lp.pruefe_hook_loescht(conn, u, HOOK_TABELLEN) == {
            t: 0 for t in HOOK_TABELLEN}
    finally:
        auth.reset_identity_provider()
