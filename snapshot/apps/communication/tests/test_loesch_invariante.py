"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Communication — STATIK.

Kein on_delete-Hook nötig: alle user_id-Tabellen tragen deleted_at, die
Soft-Delete-Kaskade (db.soft_delete_user) deckt sie vollständig. Die Statik
hält das durch — eine künftig neu angelegte ungedeckte Tabelle macht sie rot."""
from __future__ import annotations

from appkit import loesch_pruefung as lp
from kommapp.main import build_app


def test_loesch_invariante_statisch(tmp_path):
    app = build_app(data_dir=tmp_path, start_timer=False)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=frozenset()) == []
