"""Netzweite Lösch-Invariante (KA-H1, DSGVO Art. 17) für Dizz Admin — STATIK.

Keine user_id-Tabelle ohne deleted_at (HOOK_TABELLEN = ∅). Die EXTERNEN Artefakte
(Vault-Dateien + dokumente_fts + Fernet-Key) räumt der on_delete-Hook (tresor.on_delete)
— dynamisch abgedeckt von ``test_tresor_v3.py``. Hier nur die Statik."""
from __future__ import annotations

from adminapp import main as am
from appkit import loesch_pruefung as lp


def test_loesch_invariante_statisch(tmp_path):
    app = am.build_app(data_dir=tmp_path, start_wachter=False)
    conn = app.state.db.get_conn()
    assert lp.user_tabellen_ohne_deckung(
        conn, hook_tabellen=frozenset()) == []
