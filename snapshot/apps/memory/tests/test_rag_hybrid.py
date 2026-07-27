"""Hybrid-Retrieval (docs/50 3.1): RRF-Fusion (FTS5 + Vektor) + L2-Normalisierung
(P1.3, vec0-L2 ≡ Kosinus) + injizierbarer Reranker. Alles Ollama-frei
(embed_fn/rerank_fn gemockt) — die Mechanik wird echt geprüft."""

from __future__ import annotations

import hashlib
import math
import re

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.rag import RagIndex, _l2_normalize, make_rag, rrf_fuse

_W = re.compile(r"\w+", re.UNICODE)
DIM = 64


def _fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * DIM
        for w in _W.findall((t or "").lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
        out.append(v)            # ABSICHTLICH un-normiert: rag._embed normalisiert
    return out


def _client(tmp_path, embed=_fake_embed, rerank=None):
    app = am.build_app(data_dir=tmp_path, embed_fn=embed, rag_dim=DIM,
                       rag_autobuild=False, start_import_timer=False,
                       rerank_fn=rerank)
    return TestClient(app)


# ===================== RRF-Fusion (rein) =====================
def test_rrf_fuse_rang_basiert_deterministisch():
    # b: rang2+rang1, a: rang1+rang3, c: rang3+rang2 ⇒ b vorne, a vor c
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "a"]], k=60)
    assert [d for d, _ in fused] == ["b", "a", "c"]
    # Score-Formel exakt: b = 1/62 + 1/61
    assert abs(dict(fused)["b"] - (1 / 62 + 1 / 61)) < 1e-12


def test_rrf_fuse_leere_quelle_degradiert():
    # eine Quelle leer ⇒ Reihenfolge der anderen bleibt erhalten
    assert [d for d, _ in rrf_fuse([[], ["x", "y", "z"]])] == ["x", "y", "z"]
    assert rrf_fuse([[], []]) == []


def test_l2_normalize_macht_einheitsvektor():
    v = _l2_normalize([3.0, 4.0] + [0.0] * 62)
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-9
    assert _l2_normalize([0.0] * DIM) == [0.0] * DIM     # Null-Vektor unverändert


def test_normalisierung_l2_rang_gleich_kosinus(tmp_path):
    """Kernaussage P1.3: nach L2-Normalisierung rankt die vec0-L2-Distanz wie
    Kosinus — der nächste Treffer ist der mit größter Wort-Überlappung."""
    rag = make_rag(tmp_path / "r.sqlite", embed_fn=_fake_embed, dim=DIM)
    rag.update_notiz("u", "n1", "Alpha", "qubit fehlerkorrektur supraleiter")
    rag.update_notiz("u", "n2", "Beta", "tomaten basilikum garten mai")
    hits = rag.search("u", "qubit fehlerkorrektur", k=5)
    assert hits and hits[0]["notiz_id"] == "n1"


# ===================== Reranker-Hook (injizierbar, fail-safe) ===============
def test_rerank_ohne_fn_behaelt_reihenfolge(tmp_path):
    rag = RagIndex(tmp_path / "r.sqlite", embed_fn=_fake_embed, dim=DIM)
    assert rag.hat_reranker is False
    kand = [("a", "txt a"), ("b", "txt b")]
    assert rag.rerank("frage", kand) == ["a", "b"]


def test_rerank_dreht_um_und_ist_failsafe(tmp_path):
    # Reranker, der die Reihenfolge umkehrt (höchster Score zuletzt im Input)
    def umkehr(frage, kand):
        return [(i, float(r)) for r, (i, _) in enumerate(kand)]   # letzter = höchster
    rag = RagIndex(tmp_path / "r.sqlite", embed_fn=_fake_embed, dim=DIM, rerank_fn=umkehr)
    assert rag.hat_reranker is True
    assert rag.rerank("f", [("a", "x"), ("b", "y"), ("c", "z")]) == ["c", "b", "a"]

    # Reranker, der wirft ⇒ Eingangs-Reihenfolge (fail-safe)
    def boom(frage, kand):
        raise RuntimeError("reranker weg")
    rag2 = RagIndex(tmp_path / "r2.sqlite", embed_fn=_fake_embed, dim=DIM, rerank_fn=boom)
    assert rag2.rerank("f", [("a", "x"), ("b", "y")]) == ["a", "b"]


# ===================== Hybrid-Endpoint (FTS + Vektor → RRF) ==================
def test_hybrid_endpoint_fusioniert(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Quantencomputer",
               "inhalt": "Supraleitende Qubits und Fehlerkorrektur, NISQ-Ära."})
        c.post("/api/notizen", json={"titel": "Gartenplan",
               "inhalt": "Tomaten und Basilikum im Mai giessen."})
        c.post("/api/reindex")
        treffer = c.get("/api/suche/hybrid?q=qubits fehlerkorrektur").json()
        assert treffer and treffer[0]["titel"] == "Quantencomputer"
        assert treffer[0]["auszug"]
        assert c.get("/api/suche/hybrid?q=").json() == []    # leer degradiert


def test_hybrid_ohne_rag_faellt_auf_fts(tmp_path):
    """RAG aus (kein embed_fn) ⇒ Vektor-Quelle leer ⇒ Hybrid = reine FTS, nie leer
    bei vorhandenem Wort-Treffer."""
    with _client(tmp_path, embed=None) as c:
        c.post("/api/notizen", json={"titel": "Zebra", "inhalt": "Findwort zebra hier."})
        treffer = c.get("/api/suche/hybrid?q=zebra").json()
        assert treffer and treffer[0]["titel"] == "Zebra"
