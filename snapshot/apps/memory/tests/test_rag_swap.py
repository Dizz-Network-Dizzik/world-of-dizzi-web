"""Swappbares Embedding-Modell + batched/abbruch-sicheres Re-Index-Werkzeug (D3).
Embedding ist gemockt (deterministischer Bag-of-Words-Hash, beliebige Dimension)
⇒ Ollama-frei. Geprüft: Dim-/Modell-Wechsel-Migration der vec-Tabelle, make_rag-
Dimensionsauflösung, status-Modell, reindex (idempotent/abbruch-sicher/orphan/Progress),
sowie die Re-Index-API (Hintergrund-Lauf + Status + Abbrechen)."""

from __future__ import annotations

import hashlib
import math
import re
import time

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.rag import EMBED_DIM, RagIndex, make_rag

_W = re.compile(r"\w+", re.UNICODE)


def _fake_embed(dim):
    """Embedder fester Dimension (deterministisch) — simuliert ein bestimmtes Modell."""
    def f(texts):
        out = []
        for t in texts:
            v = [0.0] * dim
            for w in _W.findall((t or "").lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out
    return f


DIM = 64
_FE = _fake_embed(DIM)


def _client(tmp_path):
    app = am.build_app(data_dir=tmp_path, embed_fn=_FE, rag_dim=DIM,
                       rag_autobuild=False, start_import_timer=False)
    return TestClient(app)


def _notizen(n, prefix="n"):
    return [{"id": f"{prefix}{i}", "user_id": "u", "titel": f"T{i}",
             "inhalt": f"inhalt nummer {i} zebra alpha"} for i in range(n)]


# ----- make_rag: Modellname → Dimension -----------------------------------
def test_make_rag_dim_aufloesung(tmp_path):
    # bekanntes Modell ⇒ Registry-Dimension
    r = make_rag(tmp_path / "a.sqlite", embed_fn=_fake_embed(1024), modell="bge-m3")
    assert r.dim == 1024 and r.modell == "bge-m3"
    # explizite Dimension gewinnt
    r2 = make_rag(tmp_path / "b.sqlite", embed_fn=_fake_embed(DIM), modell="bge-m3", dim=DIM)
    assert r2.dim == DIM
    # unbekanntes Modell + aktiver Embedder ⇒ Dimension wird geprobt
    r3 = make_rag(tmp_path / "c.sqlite", embed_fn=_fake_embed(48), modell="mystery-embed")
    assert r3.dim == 48 and r3.modell == "mystery-embed"
    # unbekanntes Modell ohne Embedder ⇒ Default-Dimension (keine Probe möglich)
    r4 = make_rag(tmp_path / "d.sqlite", embed_fn=None, modell="mystery-embed")
    assert r4.dim == EMBED_DIM


# ----- Migration bei Modell-/Dimensionswechsel ----------------------------
def test_dim_wechsel_migriert_vec_tabelle(tmp_path):
    p = tmp_path / "rag.sqlite"
    r1 = RagIndex(p, embed_fn=_fake_embed(64), dim=64, modell="modelA")
    assert r1.update_notiz("u", "n1", "T", "viel text hier zebra") >= 1
    assert r1.status()["chunks"] >= 1 and r1.status()["dim"] == 64

    # neues Modell mit ANDERER Dimension ⇒ vec-Tabelle wird verworfen + neu gebaut
    r2 = RagIndex(p, embed_fn=_fake_embed(32), dim=32, modell="modelB")
    st = r2.status()
    assert st["dim"] == 32 and st["chunks"] == 0 and st["modell"] == "modelB"
    # in neuer Dimension wieder befüllbar (kein „dimension mismatch")
    assert r2.update_notiz("u", "n1", "T", "viel text hier zebra") >= 1
    assert r2.status()["dim"] == 32 and r2.status()["chunks"] >= 1


def test_modell_wechsel_gleiche_dim_verwirft_chunks(tmp_path):
    p = tmp_path / "r.sqlite"
    a = RagIndex(p, embed_fn=_fake_embed(64), dim=64, modell="alpha")
    a.update_notiz("u", "n1", "T", "inhalt zebra")
    assert a.status()["chunks"] >= 1
    # gleiche Dimension, ANDERES Modell ⇒ Embeddings unvergleichbar ⇒ geleert
    b = RagIndex(p, embed_fn=_fake_embed(64), dim=64, modell="beta")
    assert b.status()["chunks"] == 0 and b.status()["modell"] == "beta"


def test_gleiches_modell_behaelt_index(tmp_path):
    p = tmp_path / "r.sqlite"
    a = RagIndex(p, embed_fn=_fake_embed(64), dim=64, modell="bge-m3")
    a.update_notiz("u", "n1", "T", "inhalt zebra")
    n = a.status()["chunks"]
    # erneutes Öffnen mit identischem Modell/Dim ⇒ KEINE Migration, Index bleibt
    b = RagIndex(p, embed_fn=_fake_embed(64), dim=64, modell="bge-m3")
    assert b.status()["chunks"] == n >= 1


# ----- reindex: idempotent · abbruch-sicher · orphan · Fortschritt --------
def test_reindex_idempotent_und_progress(tmp_path):
    r = RagIndex(tmp_path / "r.sqlite", embed_fn=_fake_embed(64), dim=64, modell="m")
    fortschritt = []
    res = r.reindex(_notizen(5), on_progress=lambda f, g, c: fortschritt.append((f, g, c)))
    assert res["notizen"] == 5 and res["gesamt"] == 5
    assert res["abgebrochen"] is False and res["chunks"] >= 5
    assert fortschritt[-1][0] == 5 and fortschritt[-1][1] == 5     # Endstand 5/5
    # idempotent: zweiter Lauf = gleicher Chunk-Stand
    res2 = r.reindex(_notizen(5))
    assert res2["chunks"] == res["chunks"]


def test_reindex_abbruch_sicher(tmp_path):
    r = RagIndex(tmp_path / "r.sqlite", embed_fn=_fake_embed(64), dim=64, modell="m")
    zaehler = {"n": 0}

    def abort():
        zaehler["n"] += 1
        return zaehler["n"] > 3        # nach 3 Notizen abbrechen

    res = r.reindex(_notizen(6), should_abort=abort)
    assert res["abgebrochen"] is True
    assert 1 <= res["notizen"] < 6     # nur ein Teil verarbeitet …
    assert r.status()["chunks"] >= 1   # … und das Verarbeitete ist gültig indexiert


def test_reindex_orphan_cleanup(tmp_path):
    r = RagIndex(tmp_path / "r.sqlite", embed_fn=_fake_embed(64), dim=64, modell="m")
    r.reindex(_notizen(3))
    assert r.status()["notizen"] == 3
    # n2 ist „gelöscht" ⇒ Re-Index mit nur 2 Notizen entfernt die verwaisten Chunks
    res = r.reindex(_notizen(2))
    assert res["notizen"] == 2 and r.status()["notizen"] == 2


def test_reindex_inaktiv_ist_noop(tmp_path):
    r = RagIndex(tmp_path / "r.sqlite", embed_fn=None, dim=64)
    res = r.reindex(_notizen(3))
    assert res["aktiv"] is False and res["chunks"] == 0


# ----- Re-Index-API (Hintergrund-Lauf) ------------------------------------
def test_api_reindex_hintergrund_und_abbrechen(tmp_path):
    with _client(tmp_path) as c:
        for i in range(4):
            c.post("/api/notizen", json={"titel": f"N{i}", "inhalt": f"inhalt {i} zebra"})
        start = c.post("/api/rag/reindex").json()
        assert start["ok"] is True and start.get("gestartet") is True
        assert start["modell"] == "bge-m3"

        st = {"laeuft": True}
        for _ in range(100):                       # Fake-Embed ⇒ in ms fertig
            st = c.get("/api/rag/reindex/status").json()
            if not st["laeuft"]:
                break
            time.sleep(0.05)
        assert st["laeuft"] is False
        assert st["gesamt"] == 4 and st["fertig"] == 4 and st["prozent"] == 100.0
        assert st["chunks"] >= 4 and st["abgebrochen"] is False

        # Abbrechen, wenn kein Lauf aktiv ⇒ sauber laeuft=False
        ab = c.post("/api/rag/reindex/abbrechen").json()
        assert ab["ok"] is True and ab.get("laeuft") is False
