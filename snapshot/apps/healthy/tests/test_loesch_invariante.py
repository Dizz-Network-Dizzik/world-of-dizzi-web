"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Healthy — STATIK.

Kein on_delete-Hook nötig: alle user_id-Tabellen tragen deleted_at, die
Soft-Delete-Kaskade deckt sie vollständig. Healthy ist höchst-sensibel
(lokal_only) — die Statik hält jede künftig ungedeckte Tabelle auf."""
from __future__ import annotations

from appkit import loesch_pruefung as lp
from healthapp import main as hm


def test_loesch_invariante_statisch(tmp_path):
    app = hm.build_app(data_dir=tmp_path)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=frozenset()) == []
