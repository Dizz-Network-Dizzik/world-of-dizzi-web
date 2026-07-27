"""RAG (Memory L3): Wissen aus freigegebenen Ordnern.

Eigene SQLite-DB (rag.sqlite) mit sqlite-vec für die Vektor-Suche;
Embeddings lokal via Ollama (bge-m3, 1024 Dimensionen, mehrsprachig/Deutsch).
Indexiert v1 nur Text-Formate (.md/.txt); Re-Index überspringt Unverändertes
(mtime-Vergleich). Treffer fließen mit Quellenangabe in den System-Prompt.
"""

from __future__ import annotations

import sqlite3
import struct
import threading
from pathlib import Path
from typing import Any

import sqlite_vec

from .. import db
from ..config import settings
from .providers import runtime

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
TEXT_SUFFIXES = {".md", ".txt"}
EXCLUDED_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".venv", ".pytest_cache"}

_local = threading.local()


def _rag_path() -> Path:
    return settings.db_dir / "rag.sqlite"


def get_conn() -> sqlite3.Connection:
    path = _rag_path()
    cached: sqlite3.Connection | None = getattr(_local, "conn", None)
    if cached is None or getattr(_local, "path", None) != path:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        # M-3: rag.sqlite hatte weder WAL noch busy_timeout ⇒ Index + Suche liefen
        # bei Nebenläufigkeit auf "database is locked". Beide nachgezogen (wie appkit/core).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS rag_docs (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                mtime REAL NOT NULL, chunks INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL, user_id TEXT NOT NULL,
                ord INTEGER NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
                USING vec0(embedding float[{EMBED_DIM}]);
        """)
        conn.commit()
        _local.conn = conn
        _local.path = path
    return cached or _local.conn


def reset_thread_conn() -> None:
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _local.path = None


def chunk_text(text: str) -> list[str]:
    """Absatz-bewusstes Chunking: ~CHUNK_CHARS Zeichen, mit Überlappung."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(cur) + len(p) + 2 <= CHUNK_CHARS:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            while len(p) > CHUNK_CHARS:  # Über-langer Absatz: hart teilen
                chunks.append(p[:CHUNK_CHARS])
                p = p[CHUNK_CHARS - CHUNK_OVERLAP:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


async def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings über die lokale Runtime (docs/62 M6, 4. hartverdrahtete Stelle):
    ``a_embed`` spricht denselben ``/api/embed``-Endpunkt (bge-m3). ``a_embed``
    schluckt Transportfehler zu ``None`` (fail-safe); die Aufrufer hier
    (``index_folder``/``search``) erwarten aber echte Vektoren — daher wird
    ``None`` zum Fehler, exakt die frühere Wurf-Semantik (Ollama weg ⇒ Exception)."""
    vecs = await runtime().a_embed(texts, modell=EMBED_MODEL)
    if vecs is None:
        raise RuntimeError(f"Embedding fehlgeschlagen (/api/embed, Modell {EMBED_MODEL})")
    return vecs


def _vec_blob(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


async def index_folder(user_id: str, folder: Path) -> dict[str, Any]:
    """Indexiert alle Text-Dateien; unveränderte (mtime) werden übersprungen."""
    conn = get_conn()
    added = skipped = 0
    files = [p for p in sorted(folder.rglob("*"))
             if p.suffix.lower() in TEXT_SUFFIXES and p.is_file()
             and not (EXCLUDED_DIRS & {part.lower() for part in p.parts})]
    for f in files:
        mtime = f.stat().st_mtime
        row = conn.execute("SELECT id, mtime FROM rag_docs WHERE path=?", (str(f),)).fetchone()
        if row and abs(row["mtime"] - mtime) < 0.5:
            skipped += 1
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks = chunk_text(text)
        if not chunks:
            continue
        vectors = await embed(chunks)
        ts = db.now_iso()
        if row:  # alte Version raus (Chunks + Vektoren)
            old_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM rag_chunks WHERE doc_id=?", (row["id"],))]
            conn.executemany("DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in old_ids])
            conn.execute("DELETE FROM rag_chunks WHERE doc_id=?", (row["id"],))
            conn.execute("UPDATE rag_docs SET mtime=?, chunks=?, updated_at=? WHERE id=?",
                         (mtime, len(chunks), ts, row["id"]))
            doc_id = row["id"]
        else:
            doc_id = db.new_id()
            conn.execute(
                "INSERT INTO rag_docs (id, user_id, path, mtime, chunks, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (doc_id, user_id, str(f), mtime, len(chunks), ts, ts))
        for i, (c, v) in enumerate(zip(chunks, vectors)):
            cur = conn.execute(
                "INSERT INTO rag_chunks (doc_id, user_id, ord, text, created_at) VALUES (?,?,?,?,?)",
                (doc_id, user_id, i, c, ts))
            conn.execute("INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                         (cur.lastrowid, _vec_blob(v)))
        conn.commit()
        added += 1
    db.audit(user_id, "ki", "rag_indexed",
             {"folder": str(folder), "files_indexed": added, "skipped": skipped})
    return {"files_indexed": added, "skipped": skipped, "total_files": len(files)}


def remove_user(user_id: str) -> dict[str, int]:
    """DSGVO-Purge (KA-H1): löscht ALLE RAG-Zeilen + Vektoren des Nutzers aus der
    separaten ``rag.sqlite``. ``vec_chunks`` ist per ``rowid == rag_chunks.id``
    gebunden (wie in ``index_folder``) — erst die Vektoren, dann Chunks, dann Docs.
    Idempotent; die Core-Haupt-DB-Kaskade sieht diese eigene DB nicht."""
    conn = get_conn()
    chunk_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM rag_chunks WHERE user_id=?", (user_id,))]
    conn.executemany("DELETE FROM vec_chunks WHERE rowid=?",
                     [(i,) for i in chunk_ids])
    n_chunks = conn.execute(
        "DELETE FROM rag_chunks WHERE user_id=?", (user_id,)).rowcount
    n_docs = conn.execute(
        "DELETE FROM rag_docs WHERE user_id=?", (user_id,)).rowcount
    conn.commit()
    return {"rag_docs": n_docs, "rag_chunks": n_chunks}


async def search(user_id: str, query: str, k: int = 3) -> list[dict[str, Any]]:
    """k nächste Wissens-Chunks zur Frage (Cosine-Nähe via vec0)."""
    conn = get_conn()
    if conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()["n"] == 0:
        return []
    qv = (await embed([query]))[0]
    rows = conn.execute(
        """SELECT c.text, c.user_id, d.path, v.distance
           FROM vec_chunks v
           JOIN rag_chunks c ON c.id = v.rowid
           JOIN rag_docs d ON d.id = c.doc_id
           WHERE v.embedding MATCH ? AND v.k = ?
           ORDER BY v.distance""",
        (_vec_blob(qv), k * 2),
    ).fetchall()
    out = [
        {"text": r["text"], "source": Path(r["path"]).name, "distance": r["distance"]}
        for r in rows if r["user_id"] == user_id
    ]
    return out[:k]


def status() -> dict[str, Any]:
    conn = get_conn()
    docs = conn.execute("SELECT COUNT(*) AS n FROM rag_docs WHERE deleted_at IS NULL").fetchone()["n"]
    chunks = conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()["n"]
    return {"docs": docs, "chunks": chunks, "embed_model": EMBED_MODEL, "dim": EMBED_DIM}
