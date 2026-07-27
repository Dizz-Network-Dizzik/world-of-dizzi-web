import pytest

from app.ai import rag


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_vec(text: str) -> list[float]:
    """Deterministischer Fake: Themen-Wörter bekommen orthogonale Vektoren."""
    v = [0.0] * rag.EMBED_DIM
    if "Tauri" in text:
        v[0] = 1.0
    elif "SQLite" in text:
        v[1] = 1.0
    else:
        v[2] = 1.0
    return v


@pytest.fixture
def fake_embed(monkeypatch):
    async def fake(texts):
        return [_fake_vec(t) for t in texts]
    monkeypatch.setattr(rag, "embed", fake)


# --- Chunking ----------------------------------------------------------------

def test_chunk_short_text():
    assert rag.chunk_text("Hallo Welt") == ["Hallo Welt"]


def test_chunk_respects_paragraphs():
    text = "Absatz eins.\n\nAbsatz zwei."
    assert rag.chunk_text(text) == ["Absatz eins.\n\nAbsatz zwei."]


def test_chunk_splits_long_text():
    text = "\n\n".join(f"Absatz {i} " + "x" * 400 for i in range(10))
    chunks = rag.chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= rag.CHUNK_CHARS for c in chunks)


def test_chunk_oversized_paragraph():
    chunks = rag.chunk_text("y" * 3000)
    assert len(chunks) >= 2
    assert all(len(c) <= rag.CHUNK_CHARS for c in chunks)


# --- Index + Suche -------------------------------------------------------------

@pytest.mark.anyio
async def test_index_and_search(tmp_path, fake_embed):
    (tmp_path / "a.md").write_text("Tauri ist unser App-Rahmen.", encoding="utf-8")
    (tmp_path / "b.md").write_text("SQLite speichert alle Daten.", encoding="utf-8")
    (tmp_path / "c.exe").write_bytes(b"binary")  # wird ignoriert
    res = await rag.index_folder("dizzi", tmp_path)
    assert res["files_indexed"] == 2
    hits = await rag.search("dizzi", "Was ist Tauri?", k=1)
    assert len(hits) == 1
    assert "Tauri" in hits[0]["text"]
    assert hits[0]["source"] == "a.md"


@pytest.mark.anyio
async def test_reindex_skips_unchanged(tmp_path, fake_embed):
    (tmp_path / "a.md").write_text("Tauri ist unser App-Rahmen.", encoding="utf-8")
    await rag.index_folder("dizzi", tmp_path)
    res2 = await rag.index_folder("dizzi", tmp_path)
    assert res2["files_indexed"] == 0
    assert res2["skipped"] == 1
    assert rag.status()["chunks"] == 1  # keine Duplikate


@pytest.mark.anyio
async def test_index_excludes_node_modules(tmp_path, fake_embed):
    (tmp_path / "node_modules" / "paket").mkdir(parents=True)
    (tmp_path / "node_modules" / "paket" / "README.md").write_text("Fremd", encoding="utf-8")
    (tmp_path / "echt.md").write_text("Tauri ist unser App-Rahmen.", encoding="utf-8")
    res = await rag.index_folder("dizzi", tmp_path)
    assert res["files_indexed"] == 1


@pytest.mark.anyio
async def test_search_empty_index():
    assert await rag.search("dizzi", "irgendwas") == []


@pytest.mark.anyio
async def test_search_user_scoped(tmp_path, fake_embed):
    (tmp_path / "a.md").write_text("Tauri ist unser App-Rahmen.", encoding="utf-8")
    await rag.index_folder("dizzi", tmp_path)
    assert await rag.search("gast", "Was ist Tauri?") == []


def test_status_shape():
    s = rag.status()
    assert s["docs"] == 0 and s["chunks"] == 0 and s["embed_model"] == rag.EMBED_MODEL


# --- M6 (docs/62 C1e): embed über die LocalRuntime ---------------------------

@pytest.mark.anyio
async def test_embed_routes_through_runtime(monkeypatch):
    """embed() ruft runtime().a_embed mit dem Standard-Embed-Modell (Paritäts-Pin)
    und reicht die rohen Vektoren durch (KEINE L2-Norm — Index-Politik bleibt hier)."""
    seen: dict = {}

    class _Rt:
        async def a_embed(self, texts, *, modell, timeout=120.0):
            seen["texts"] = texts
            seen["modell"] = modell
            return [[0.1] * rag.EMBED_DIM for _ in texts]

    monkeypatch.setattr(rag, "runtime", lambda: _Rt())
    out = await rag.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == rag.EMBED_DIM
    assert seen["modell"] == rag.EMBED_MODEL and seen["texts"] == ["a", "b"]


@pytest.mark.anyio
async def test_embed_raises_when_runtime_fails(monkeypatch):
    """a_embed schluckt Fehler zu None ⇒ embed() WIRFT wie zuvor (die Aufrufer
    index_folder/search brechen ab statt None-Vektoren zu verarbeiten)."""
    class _Rt:
        async def a_embed(self, texts, *, modell, timeout=120.0):
            return None

    monkeypatch.setattr(rag, "runtime", lambda: _Rt())
    with pytest.raises(RuntimeError):
        await rag.embed(["x"])
