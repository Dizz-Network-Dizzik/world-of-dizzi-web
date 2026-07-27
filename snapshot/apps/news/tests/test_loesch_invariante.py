"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz News — STATIK.

Keine user_id-Tabelle ohne deleted_at (HOOK_TABELLEN = ∅ — alle user-Tabellen
tragen deleted_at, die Soft-Delete-Kaskade deckt sie). Die Kind-Tabelle
watchlist_artikel hängt OHNE eigene user_id am Nutzer und ist für die Statik
unsichtbar — sie deckt ``test_news_watchlist.py`` (test_konto_loeschen_raeumt_
watchlist_artikel_hart) dynamisch ab."""
from __future__ import annotations

from appkit import loesch_pruefung as lp
from newsapp import main as nm


def test_loesch_invariante_statisch(tmp_path):
    app = nm.build_app(data_dir=tmp_path, start_timer=False)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=frozenset()) == []
