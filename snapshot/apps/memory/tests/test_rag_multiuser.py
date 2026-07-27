"""Multi-User-KNN-Prefilter: die semantische Suche filtert den ``user_id`` SCHON
im vec0-KNN (Metadaten-Spalte), nicht erst in Python — sonst könnten viele nähere
Fremd-Chunks die Top-k des Suchenden verdrängen (Unter-Rückgabe, kein Leak).
Kern-Dauerschleife-Backlog R3, Nutzer-Freigabe 23.06.2026."""
from __future__ import annotations

from archivapp.rag import RagIndex

DIM = 8


def _emb(texts):
    """Deterministisch: 'alice'-Text → ferne Richtung [0,1,…]; alles andere
    (Bob + Query) → [1,0,…]. So liegen Bobs Chunks bei Distanz 0 zur Query,
    Alices Chunk weit weg — der gezielte Stresstest für den Prefilter."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        if "alice" in (t or "").lower():
            v[1] = 1.0
        else:
            v[0] = 1.0
        out.append(v)
    return out


def test_knn_prefiltert_user_nicht_erst_in_python(tmp_path):
    rag = RagIndex(tmp_path / "rag.sqlite", embed_fn=_emb, dim=DIM)
    assert rag.update_notiz("alice", "a1", "alice notiz", "alice inhalt") == 1
    for i in range(15):                       # 15 nähere Bob-Chunks (Distanz 0 zur Query)
        rag.update_notiz("bob", f"b{i}", "bob notiz", "bob inhalt")
    # Alices fernerer Treffer darf NICHT aus den Top-k (k*3=12 < 15 Bob) gedrängt werden —
    # der user_id-Filter steckt jetzt im KNN, nicht im Python-Post-Filter.
    res = rag.search("alice", "such mir etwas", k=3)
    assert [x["notiz_id"] for x in res] == ["a1"]
    # Gegenprobe: Bob sieht nur seine, nie Alices (kein Cross-User-Leak).
    resb = rag.search("bob", "such mir etwas", k=5)
    assert resb and all(x["notiz_id"].startswith("b") for x in resb)


def test_remove_user_raeumt_vektoren_im_neuen_schema(tmp_path):
    rag = RagIndex(tmp_path / "rag.sqlite", embed_fn=_emb, dim=DIM)
    rag.update_notiz("alice", "a1", "alice notiz", "alice inhalt")
    rag.update_notiz("bob", "b1", "bob notiz", "bob inhalt")
    assert rag.remove_user("alice") == 1
    assert rag.search("alice", "such mir etwas", k=3) == []     # Alice weg (DSGVO)
    assert rag.search("bob", "such mir etwas", k=3)             # Bob unberührt
