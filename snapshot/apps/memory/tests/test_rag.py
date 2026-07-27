"""RAG/Vektor-Brücke L3 (sqlite-vec). Embedding ist gemockt (deterministischer
Bag-of-Words-Hash) ⇒ kein Ollama nötig; die Vektor-Mechanik (vec0 KNN, Re-Embed
auf Schreib-Ops, Reindex, semantische Suche, KI-Kontext) wird echt geprüft."""

from __future__ import annotations

import hashlib
import math
import re

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.rag import RagIndex

_W = re.compile(r"\w+", re.UNICODE)
DIM = 64


def _fake_embed(texts):
    """Stabiler (prozess-übergreifend deterministischer) Bag-of-Words-Hash →
    normierter Vektor. Wort-Überlappung ⇒ kleine L2-Distanz (semantisch ~ FTS,
    genügt für die Mechanik-Tests)."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        for w in _W.findall((t or "").lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


class _FakeResp:
    status_code = 200

    def __init__(self, antwort):
        self._a = antwort

    def json(self):
        import json
        return {"message": {"content": json.dumps({"antwort": self._a})}}


def _client(tmp_path, embed=_fake_embed, antwort="Antwort aus dem Kontext."):
    app = am.build_app(data_dir=tmp_path, embed_fn=embed, rag_dim=DIM, rag_autobuild=False,
                       start_import_timer=False, http_post=lambda url, json: _FakeResp(antwort))
    return TestClient(app)


def test_embed_none_safety(tmp_path):
    # RAG ohne embed_fn = deaktiviert: alle Operationen sind No-ops, nie Crash.
    aus = RagIndex(tmp_path / "rag.sqlite", embed_fn=None, dim=DIM)
    assert aus.aktiv is False
    assert aus.update_notiz("u", "n1", "Titel", "Text") == 0
    assert aus.search("u", "irgendwas") == []
    assert aus.build_index([{"id": "n1", "titel": "x", "inhalt": "y"}])["aktiv"] is False

    # embed_fn, die wirft ⇒ _embed fängt ab, kein Index, kein Crash.
    def kaputt(texts):
        raise RuntimeError("ollama weg")
    fehl = RagIndex(tmp_path / "rag2.sqlite", embed_fn=kaputt, dim=DIM)
    assert fehl.aktiv is True
    assert fehl.update_notiz("u", "n1", "Titel", "Text") == 0
    assert fehl.search("u", "frage") == []

    # embed_fn, die None liefert ⇒ dieselbe Degradierung. docs/62 M6: der neue
    # Default-Embedder (LocalRuntime.embed) SCHLUCKT Fehler zu None statt zu werfen —
    # der None-Safety-Guard in _embed fängt das genauso ab wie den Wurf (Paritäts-
    # Beweis für den ollama_embed → runtime.embed-Tausch).
    def liefert_none(texts):
        return None
    nichts = RagIndex(tmp_path / "rag3.sqlite", embed_fn=liefert_none, dim=DIM)
    assert nichts.aktiv is True
    assert nichts.update_notiz("u", "n1", "Titel", "Text") == 0
    assert nichts.search("u", "frage") == []


def test_index_build_und_status(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Quantencomputer",
               "inhalt": "Supraleitende Qubits und Fehlerkorrektur."})
        c.post("/api/notizen", json={"titel": "Gartenplan",
               "inhalt": "Tomaten und Basilikum im Mai."})
        r = c.post("/api/reindex").json()
        assert r["rag"]["aktiv"] is True and r["rag"]["notizen"] == 2
        assert r["rag"]["chunks"] >= 2
        st = c.get("/api/rag/status").json()
        assert st["aktiv"] is True and st["dim"] == DIM and st["notizen"] == 2


def test_semantische_suche_findet_chunk(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Quantencomputer",
               "inhalt": "Supraleitende Qubits und Fehlerkorrektur, NISQ-Ära."})
        c.post("/api/notizen", json={"titel": "Gartenplan",
               "inhalt": "Tomaten und Basilikum im Mai giessen."})
        c.post("/api/reindex")
        treffer = c.get("/api/suche/semantisch?q=qubits fehlerkorrektur").json()
        assert treffer and treffer[0]["titel"] == "Quantencomputer"
        assert "score" in treffer[0] and treffer[0]["auszug"]
        # leere/aus-Anfrage degradiert sauber
        assert c.get("/api/suche/semantisch?q=").json() == []


def test_frage_nutzt_rag_kontext(tmp_path):
    with _client(tmp_path, antwort="Laut 'Strategie 2026': Qualität zuerst.") as c:
        c.post("/api/notizen", json={"titel": "Strategie 2026",
               "inhalt": "Fokus auf Qualität und Gründlichkeit."})
        c.post("/api/reindex")
        out = c.post("/api/frage", json={"frage": "Was ist die Strategie Qualität?"}).json()
        assert "Qualität" in out["antwort"]
        assert "Strategie 2026" in out["quellen"]   # vom RAG-Retrieval geliefert


def test_reindex_baut_rag_neu(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/notizen", json={"titel": "Reindex", "inhalt": "Findwort zebra hier."})
        # Schreib-Hook hat bereits indexiert
        assert c.get("/api/rag/status").json()["chunks"] >= 1
        # Reindex baut neu + ist idempotent (gleicher Chunk-Stand)
        a = c.post("/api/reindex").json()["rag"]["chunks"]
        b = c.post("/api/reindex").json()["rag"]["chunks"]
        assert a == b and a >= 1
        assert c.get("/api/suche/semantisch?q=zebra").json()[0]["titel"] == "Reindex"
