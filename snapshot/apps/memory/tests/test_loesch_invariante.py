"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Memory — STATIK.

Keine user_id-Tabelle bleibt ohne Lösch-Deckung. Die DYNAMIK (der on_delete-Hook
räumt archiv_regeln + notiz_links hart) deckt ``test_on_delete.py`` bereits ab —
hier nur die Statik, die jede KÜNFTIG neu angelegte ungedeckte Tabelle rot macht."""
from __future__ import annotations

from appkit import loesch_pruefung as lp
from archivapp import main as am

HOOK_TABELLEN = frozenset({"archiv_regeln", "notiz_links"})


def test_loesch_invariante_statisch(tmp_path):
    app = am.build_app(data_dir=tmp_path,
                       embed_fn=lambda ts: [[0.0] * 8 for _ in ts],
                       rag_dim=8, rag_autobuild=False, start_import_timer=False,
                       http_post=lambda url, json: None)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=HOOK_TABELLEN) == []
