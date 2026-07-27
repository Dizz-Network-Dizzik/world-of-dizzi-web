"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Management — STATIK.

Kein on_delete-Hook nötig: alle user_id-Tabellen tragen deleted_at, die
Soft-Delete-Kaskade deckt sie vollständig. Die Statik macht jede künftig
neu angelegte ungedeckte Tabelle rot (management ist hoch-sensibel — lokal_only)."""
from __future__ import annotations

from appkit import loesch_pruefung as lp
from managementapp import main as mm


def test_loesch_invariante_statisch(tmp_path):
    app = mm.build_app(data_dir=tmp_path)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=frozenset()) == []
