"""RAG/Vektor-Brücke (Gedächtnis-Ebene L3) für Dizz Memory.

Semantische Suche im Vault — die inhaltliche Ergänzung zur FTS5-Volltextsuche
(`main.suche`): FTS findet exakte Wörter, RAG findet *Bedeutung* (Paraphrasen,
Synonyme, sprachübergreifend).

**Bewusst identischer Stack wie der abgenommene Core-L3-RAG**
(`the world of dizzi/core/app/ai/rag.py`): Embeddings lokal über **Ollama
`/api/embed` mit `bge-m3` (1024-dim, mehrsprachig)** + Vektor-Suche via
**sqlite-vec** (`vec0`). Dadurch **kein Modell-Download, kein Duplikat, 0 €** —
Memory teilt das Embedding-Modell mit dem Core. Anders als der Core ist diese
Variante **synchron** (passt zum übrigen sync-archivapp) und das Embedding ist
**injizierbar** (`embed_fn`) ⇒ Tests laufen Ollama-frei.

Eigene `rag.sqlite` neben der App-DB: die sqlite-vec-Extension wird nur in DIESE
Connection geladen — die appkit-DB (read-only Vertrag) bleibt unangetastet.

Robustheit: kein/leerer Text ⇒ kein Embed-Call; Ollama nicht erreichbar ⇒ leise
leer (die KI/Suche fällt auf FTS zurück), **nie ein Crash**. RAG ist *deaktiviert*,
solange kein ``embed_fn`` gesetzt ist (Default) — der Prod-Einstieg
(`main.app_factory`) hängt das echte Ollama-Embed ein.

──────────────────────────────────────────────────────────────────────────────
GESETZ-5-SLOT — Verbund mit Dizzis zentralem L3 (docs/11 §4, docs/16):
Der Vault unter ``<data>/apps/memory/vault/`` ist Markdown — exakt das Format,
das der Core-L3 (`core/app/ai/rag.py::index_folder`) indexiert. Sobald der
Verbund läuft, kann Dizzi den Memory-Vault als freigegebenen Wissensordner
einhängen (``DIZZI_CONTRACT_APPS="memory=…"`` + Ordner-Freigabe), ODER Memory
exponiert ``/api/suche/semantisch`` als read-only MCP-Tool (param. Tool =
appkit-Erweiterung, FÜR WORLD-CHAT). Beide Wege nutzen DASSELBE bge-m3 ⇒
Vektorräume sind kompatibel. Dieser Kommentar markiert den Andockpunkt.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Any, Callable

import sqlite_vec

# Default identisch zum Core-L3 (Vektorräume bleiben kompatibel); Host via Env
# überschreibbar (CH-1, 28.06. — Remote-Embedder/Nicht-Standard-Port):
OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODELL = "bge-m3"
EMBED_DIM = 1024
CHUNK_ZEICHEN = 1200
CHUNK_UEBERLAPP = 150

# vec0-Schema-Version: 'u1' = mit ``user_id``-Metadaten-Spalte (Multi-User-KNN-
# Prefilter, 23.06.2026). 'u2' = Vektoren werden L2-normalisiert gespeichert (docs/50
# P1.3/3.1) ⇒ die vec0-L2-Distanz rankt identisch zur Kosinus-Ähnlichkeit, modell-
# unabhängig. Stimmt der in ``rag_meta`` gespeicherte Wert nicht, verwirft
# ``_migriere_modellwechsel`` die vec0-Tabelle (kein ALTER möglich) ⇒ der Re-Index
# baut sie im neuen Layout neu (der Vault ist die Quelle der Wahrheit). Ein Schema-
# Sprung u1→u2 erzwingt so EINMALIG den Re-Index mit normalisierten Vektoren.
VEC_SCHEMA = "u2"

# Bekannte lokale Ollama-Embedding-Modelle → Embedding-Dimension. Damit ist der
# Modell-Tausch reibungsfrei: der Aufrufer gibt nur den Namen, die Dimension kommt
# von hier (unbekannte Modelle werden zur Laufzeit per ``_probe_dim`` erkannt).
# Stand 2026 (Recherche-Kandidaten für docs/30-W5; der finale Tausch wartet auf die
# World-Chat-Empfehlung — bis dahin bleibt ``bge-m3`` Default):
#   bge-m3 ........... 1024  aktueller Default: multilingual (100+), 8K-Ctx, hybrid (dense+sparse)
#   qwen3-embedding .. 1024  0.6B — beste multilinguale Qualität 2026, DIM-GLEICH ⇒ Tausch ohne Migration
#   snowflake-arctic-embed2  1024  multilingual, retrieval-stark
#   mxbai-embed-large  1024  English-first, Genauigkeit
#   nomic-embed-text .  768  klein/schnell, sehr verbreitet (englisch-lastig)
#   embeddinggemma ...  768  Google, leicht/effizient, multilingual („läuft überall")
#   all-minilm .......  384  sehr leicht (Edge/Tests)
EMBED_MODELLE: dict[str, int] = {
    "bge-m3": 1024,
    "qwen3-embedding": 1024,
    "snowflake-arctic-embed2": 1024,
    "mxbai-embed-large": 1024,
    "nomic-embed-text": 768,
    "embeddinggemma": 768,
    "all-minilm": 384,
}

EmbedFn = Callable[[list[str]], list[list[float]]]

_WS = re.compile(r"\s+")


def ollama_embed(texts: list[str], *, url: str = OLLAMA_URL,
                 modell: str = EMBED_MODELL) -> list[list[float]]:
    """Default-Embedding: lokal über Ollama (``modell``, Default bge-m3). Synchron,
    0 €. Wirft bei Netzfehler — die Aufrufer fangen das ab (RAG ist best-effort)."""
    import httpx
    r = httpx.post(f"{url}/api/embed",
                   json={"model": modell, "input": texts}, timeout=120.0)
    r.raise_for_status()
    return r.json()["embeddings"]


def embed_dim(modell: str, default: int | None = None) -> int | None:
    """Embedding-Dimension eines bekannten Modells (Registry) oder ``default``."""
    return EMBED_MODELLE.get((modell or "").strip(), default)


def _probe_dim(embed_fn: EmbedFn) -> int | None:
    """Ermittelt die Embedding-Dimension empirisch (ein Test-Embed). Fail-safe:
    bei Embedder-Fehler ``None`` ⇒ der Aufrufer nimmt einen Default. Nur nötig,
    wenn das Modell NICHT in ``EMBED_MODELLE`` steht."""
    try:
        v = embed_fn(["dimension probe"])
        if isinstance(v, list) and v and isinstance(v[0], list) and v[0]:
            return len(v[0])
    except Exception:
        pass
    return None


# Reranker (Cross-Encoder): bewertet (Anfrage, Kandidaten-Text)-Paare direkt und
# ordnet die Hybrid-Treffer final um. Injizierbar wie ``embed_fn`` ⇒ Tests laufen
# Reranker-frei; der Prod-Einstieg kann z. B. ein lokales **bge-reranker-v2-m3**
# (BAAI, mehrsprachig) anhängen. Signatur: ``(frage, [(id, text), …]) -> [(id, score)]``
# (höher = relevanter). Fehlt der Reranker oder wirft er, bleibt die RRF-Reihenfolge.
RerankFn = Callable[[str, list[tuple[str, str]]], list[tuple[str, float]]]


def make_rag(db_path: Path, *, embed_fn: EmbedFn | None = None,
             modell: str = EMBED_MODELL, dim: int | None = None,
             rerank_fn: "RerankFn | None" = None) -> "RagIndex":
    """Baut den ``RagIndex`` mit aufgelöster Dimension — die EINE Stelle, an der
    Modellname↔Dimension gekoppelt werden (Swap-Kapselung). Dimension =
    ``dim`` (explizit) → Registry → Probe (nur wenn aktiv) → ``EMBED_DIM``.
    ``rerank_fn`` (optional) hängt einen Cross-Encoder-Reranker für die Hybrid-Suche an."""
    modell = (modell or EMBED_MODELL).strip()
    d = dim or EMBED_MODELLE.get(modell)
    if d is None and embed_fn is not None:
        d = _probe_dim(embed_fn)
    return RagIndex(db_path, embed_fn=embed_fn, dim=d or EMBED_DIM, modell=modell,
                    rerank_fn=rerank_fn)


def chunk_text(text: str) -> list[str]:
    """Absatz-bewusstes Chunking (~CHUNK_ZEICHEN, mit Überlappung) — wie L3."""
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(cur) + len(p) + 2 <= CHUNK_ZEICHEN:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            while len(p) > CHUNK_ZEICHEN:        # über-langer Absatz: hart teilen
                chunks.append(p[:CHUNK_ZEICHEN])
                p = p[CHUNK_ZEICHEN - CHUNK_UEBERLAPP:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def _vec_blob(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def _l2_normalize(v: list[float]) -> list[float]:
    """Vektor auf Einheitslänge bringen (docs/50 P1.3). Für normierte Vektoren gilt
    ``‖a−b‖² = 2 − 2·cos(a,b)`` ⇒ die L2-Distanz-Rangfolge (sqlite-vec vec0) ist
    IDENTISCH zur Kosinus-Rangfolge — modell-unabhängig, ohne Cosinus-Distanz-Slot.
    Null-Vektor ⇒ unverändert (kein Div/0)."""
    norm = math.sqrt(sum(x * x for x in v))
    if norm <= 0.0:
        return v
    return [x / norm for x in v]


def rrf_fuse(ranglisten: list[list[str]], *, k: int = 60,
             gewichte: list[float] | None = None) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (Cormack et al. 2009): mehrere Ranglisten (je eine
    geordnete Liste von IDs, bester zuerst) zu EINER fusionieren —
    ``score(d) = Σ_i gewicht_i / (k + rang_i(d))`` (rang 1-basiert). Score-frei ⇒
    robust gegen unvergleichbare Skalen (BM25 vs. Kosinus). ``k=60`` = der TREC-
    Standard (OpenSearch/Elastic/Weaviate-Default); kleinere Korpora dürfen kleiner
    wählen. Liefert ``[(id, score)]`` absteigend (stabil bei Gleichstand: erste
    Erstsichtung gewinnt). Leere Listen werden ignoriert (degradiert sauber zu
    „nur die nicht-leere Quelle")."""
    gew = gewichte or [1.0] * len(ranglisten)
    score: dict[str, float] = {}
    reihenfolge: list[str] = []
    for liste, g in zip(ranglisten, gew):
        for rang, doc in enumerate(liste, start=1):
            if doc not in score:
                score[doc] = 0.0
                reihenfolge.append(doc)
            score[doc] += g / (k + rang)
    # stabile Sortierung: nach Score absteigend, bei Gleichstand Erstsichtungs-Index
    idx = {d: i for i, d in enumerate(reihenfolge)}
    return sorted(score.items(), key=lambda kv: (-kv[1], idx[kv[0]]))


def _snippet(text: str, n: int = 200) -> str:
    s = _WS.sub(" ", (text or "")).strip()
    return s[:n] + ("…" if len(s) > n else "")


class RagIndex:
    """Vektor-Index über den Notizen. Thread-lokale sqlite-vec-Connection.

    ``embed_fn(texts) -> list[list[float]]`` ist injizierbar; ``None`` schaltet
    RAG ab (``aktiv == False`` — alle Operationen sind dann No-ops). ``dim`` muss
    zur Embedding-Länge passen (1024 für bge-m3; Tests nutzen kleine Dim)."""

    def __init__(self, db_path: Path, embed_fn: EmbedFn | None = None,
                 dim: int = EMBED_DIM, modell: str = EMBED_MODELL,
                 rerank_fn: "RerankFn | None" = None) -> None:
        self.db_path = Path(db_path)
        self._embed_fn = embed_fn
        self._rerank_fn = rerank_fn
        self.dim = dim
        self.modell = modell or EMBED_MODELL
        self._local = threading.local()

    @property
    def aktiv(self) -> bool:
        return self._embed_fn is not None

    @property
    def hat_reranker(self) -> bool:
        return self._rerank_fn is not None

    def rerank(self, frage: str, kandidaten: list[tuple[str, str]]) -> list[str]:
        """Ordnet ``kandidaten`` (``[(id, text)]``) per Cross-Encoder-Reranker um und
        gibt die IDs in neuer Reihenfolge zurück. Ohne Reranker / bei Fehler / bei
        unbrauchbarer Ausgabe bleibt die EINGANGS-Reihenfolge (fail-safe, nie Crash)."""
        ids = [i for i, _ in kandidaten]
        if not self._rerank_fn or not (frage or "").strip() or not kandidaten:
            return ids
        try:
            bewertet = self._rerank_fn(frage, kandidaten)
            geordnet = [i for i, _ in sorted(bewertet, key=lambda kv: -kv[1])]
        except Exception:
            return ids
        # nur bekannte IDs übernehmen, fehlende hinten anhängen (Vollständigkeit).
        bekannt = set(ids)
        out = [i for i in geordnet if i in bekannt]
        out += [i for i in ids if i not in set(out)]
        return out if out else ids

    def probe(self) -> bool:
        """True, wenn der Embedder tatsächlich einen brauchbaren Vektor liefert
        (Ollama erreichbar + Modell geladen + Dimension passt). ``aktiv`` sagt nur,
        dass ein Embedder GESETZT ist; ``probe`` prüft, ob er FUNKTIONIERT — für
        Werkzeuge/Diagnose. Fail-safe (False statt Crash)."""
        return bool(self.aktiv and self._embed(["probe"]))

    # --- Connection ---------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        cached: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if cached is not None:
            return cached
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Parallel-Writer (Index-Lauf) + Reader (semantische Suche) warten lassen statt
        # sofortigem SQLITE_BUSY — sonst degradiert RAG bei Gleichzeitigkeit still zu leer.
        conn.execute("PRAGMA busy_timeout=5000")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        # Daten-Tabellen + Meta (Modell/Dim) — Meta zuerst lesbar machen.
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                notiz_id   TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                chunk_idx  INTEGER NOT NULL,
                text       TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_rag_chunks ON rag_chunks (notiz_id);
            CREATE TABLE IF NOT EXISTS rag_meta (key TEXT PRIMARY KEY, value TEXT);
        """)
        self._migriere_modellwechsel(conn)
        # vec0-Dimension ist beim Anlegen fixiert ⇒ erst NACH der Migration (die die
        # Tabelle bei Dim-/Schema-Wechsel verwirft) mit der aktuellen Dimension anlegen.
        # ``user_id`` als vec0-METADATEN-Spalte ⇒ die KNN-Suche filtert den Nutzer SCHON
        # IM Index (Multi-User-Prefilter), statt erst in Python ⇒ kein Fremd-Chunk
        # verdrängt die Top-k des Suchenden (vec0 ≥0.1.x).
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
            f"USING vec0(user_id TEXT, embedding float[{self.dim}])")
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('dim',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(self.dim),))
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('modell',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (self.modell,))
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('vec_schema',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (VEC_SCHEMA,))
        conn.commit()
        self._local.conn = conn
        return conn

    def _migriere_modellwechsel(self, conn: sqlite3.Connection) -> None:
        """Embedding-Modell/Dimension swappbar: vergleicht das in ``rag_meta``
        gespeicherte Modell/Dim mit dem aktuellen.
        • **Dim-Wechsel** ⇒ die vec0-Tabelle hat die falsche (fixe) Dimension ⇒
          DROP + Chunks verwerfen (vollständiger Re-Index nötig).
        • **gleiche Dim, anderes Modell** ⇒ Vektoren sind nicht vergleichbar ⇒
          Chunks/Vektoren leeren (Re-Index re-embeddet mit dem neuen Modell).
        Frische DB (kein Meta) ⇒ kein Eingriff. Idempotent; ein etwaiges Doppel-
        Migrieren paralleler Start-Connections endet konsistent (leerer Index in
        korrekter Dimension), da der Re-Index ohnehin neu aufbaut."""
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM rag_meta")}
        alt_dim = int(meta["dim"]) if meta.get("dim", "").isdigit() else None
        alt_modell = meta.get("modell")
        # Schema-Upgrade: eine Bestands-DB (alt_dim gesetzt) ohne die aktuelle
        # ``vec_schema``-Marke trägt die vec0-Tabelle noch OHNE ``user_id``-Spalte ⇒
        # falsches Layout (vec0 kennt kein ALTER) ⇒ verwerfen + Re-Index baut sie neu.
        schema_veraltet = alt_dim is not None and meta.get("vec_schema") != VEC_SCHEMA
        if (alt_dim is not None and alt_dim != self.dim) or schema_veraltet:
            conn.executescript("DROP TABLE IF EXISTS vec_chunks; DELETE FROM rag_chunks;")
        elif alt_modell is not None and alt_modell != self.modell:
            conn.execute("DELETE FROM rag_chunks")
            try:
                conn.execute("DELETE FROM vec_chunks")
            except sqlite3.OperationalError:
                pass
        conn.commit()

    def reset_thread_conn(self) -> None:
        """Tests: frische Connection im aktuellen Thread erzwingen."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
        self._local.conn = None

    # --- Embedding (guarded) ------------------------------------------------
    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddet eine Liste; gibt [] zurück, wenn RAG aus ist oder der
        Embedder (Ollama) fehlschlägt — die Aufrufer degradieren dann auf FTS."""
        if not self._embed_fn or not texts:
            return []
        try:
            vecs = self._embed_fn(texts)
        except Exception:
            return []
        # None-Safety: nur brauchbare, dimensions-konforme Vektoren behalten.
        if not isinstance(vecs, list) or len(vecs) != len(texts):
            return []
        for v in vecs:
            if not isinstance(v, list) or len(v) != self.dim:
                return []
        # L2-Normalisierung (docs/50 P1.3): einheitliche Länge ⇒ vec0-L2-Distanz
        # rankt wie Kosinus, egal welches Embedding-Modell. Zentral hier, damit
        # Schreiben (update_notiz) UND Abfrage (search) dieselbe Norm nutzen.
        return [_l2_normalize(v) for v in vecs]

    # --- Schreiben ----------------------------------------------------------
    def remove_notiz(self, notiz_id: str) -> None:
        if not self.aktiv:
            return
        conn = self._conn()
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM rag_chunks WHERE notiz_id=?", (notiz_id,))]
        if ids:
            conn.executemany("DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in ids])
            conn.execute("DELETE FROM rag_chunks WHERE notiz_id=?", (notiz_id,))
            conn.commit()

    def remove_user(self, user_id: str) -> int:
        """Entfernt ALLE Vektoren eines Nutzers (Chunks + vec-Zeilen) — für die
        DSGVO-Konto-Löschung (appkit on_delete-Hook, H-7). Gibt die Anzahl
        entfernter Chunks zurück (0 wenn RAG aus)."""
        if not self.aktiv:
            return 0
        conn = self._conn()
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM rag_chunks WHERE user_id=?", (user_id,))]
        if ids:
            conn.executemany("DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in ids])
            conn.execute("DELETE FROM rag_chunks WHERE user_id=?", (user_id,))
            conn.commit()
        return len(ids)

    def update_notiz(self, user_id: str, notiz_id: str, titel: str,
                     text: str, created_at: str = "") -> int:
        """Re-embeddet eine einzelne Notiz (Hook für Schreib-Ops). Titel fließt
        in den ersten Chunk-Kontext ein. Gibt die Anzahl Chunks zurück (0 wenn
        RAG aus, leer oder Ollama nicht erreichbar — immer fail-safe)."""
        if not self.aktiv:
            return 0
        self.remove_notiz(notiz_id)
        voll = f"{titel}\n\n{text}".strip() if titel else (text or "").strip()
        chunks = chunk_text(voll)
        if not chunks:
            return 0
        vecs = self._embed(chunks)
        if not vecs:                              # Ollama weg ⇒ nichts indexieren
            return 0
        conn = self._conn()
        for i, (c, v) in enumerate(zip(chunks, vecs)):
            cur = conn.execute(
                "INSERT INTO rag_chunks (notiz_id, user_id, chunk_idx, text, created_at) "
                "VALUES (?,?,?,?,?)", (notiz_id, user_id, i, c, created_at))
            conn.execute("INSERT INTO vec_chunks (rowid, user_id, embedding) VALUES (?, ?, ?)",
                         (cur.lastrowid, user_id, _vec_blob(v)))
        conn.commit()
        return len(chunks)

    def build_index(self, notizen: list[dict[str, Any]]) -> dict[str, Any]:
        """Baut den Index komplett neu aus allen Notizen
        (``[{id, user_id, titel, inhalt, created_at}]``). Idempotent."""
        if not self.aktiv:
            return {"aktiv": False, "notizen": 0, "chunks": 0}
        conn = self._conn()
        conn.execute("DELETE FROM vec_chunks")
        conn.execute("DELETE FROM rag_chunks")
        conn.commit()
        chunks = 0
        for n in notizen:
            chunks += self.update_notiz(
                n.get("user_id", "dizzi"), n["id"], n.get("titel", ""),
                n.get("inhalt", ""), n.get("created_at", ""))
        return {"aktiv": True, "notizen": len(notizen), "chunks": chunks}

    # --- Suche --------------------------------------------------------------
    def search(self, user_id: str, q: str, k: int = 8) -> list[dict[str, Any]]:
        """Semantische Suche: nächste Chunks zur Anfrage, je Notiz der beste
        Treffer. Liefert ``[{notiz_id, snippet, score}]`` (score: höher = näher).
        Leer bei RAG-aus/leerer Anfrage/keinem Index — nie ein Crash."""
        if not self.aktiv or not (q or "").strip():
            return []
        conn = self._conn()
        try:
            if conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()["n"] == 0:
                return []
            qv = self._embed([q])
            if not qv:
                return []
            rows = conn.execute(
                """SELECT c.notiz_id, c.text, v.distance
                   FROM vec_chunks v JOIN rag_chunks c ON c.id = v.rowid
                   WHERE v.user_id = ? AND v.embedding MATCH ? AND v.k = ?
                   ORDER BY v.distance""",
                (user_id, _vec_blob(qv[0]), max(k * 3, 12))).fetchall()
        except Exception:
            return []
        beste: dict[str, dict[str, Any]] = {}      # je Notiz nur den besten Chunk
        for r in rows:
            if r["notiz_id"] in beste:             # user_id-Filter steckt jetzt im KNN (oben)
                continue
            beste[r["notiz_id"]] = {
                "notiz_id": r["notiz_id"], "snippet": _snippet(r["text"]),
                "score": round(1.0 / (1.0 + float(r["distance"])), 4),
                "distanz": round(float(r["distance"]), 4)}
            if len(beste) >= k:
                break
        return list(beste.values())

    def reindex(self, notizen: list[dict[str, Any]], *,
                should_abort: Callable[[], bool] | None = None,
                on_progress: Callable[[int, int, int], None] | None = None,
                orphan_cleanup: bool = True) -> dict[str, Any]:
        """Idempotenter, **abbruch-sicherer** Re-Index aller Notizen — das Werkzeug
        für große Vaults und für den Modellwechsel.

        Verarbeitet **Notiz für Notiz** (jede Notiz = ein Embed-Batch + eine
        ``update_notiz``-Transaktion). Es gibt **kein** globales DELETE vorab:
        ⇒ ein Abbruch lässt die bereits verarbeiteten Notizen gültig indexiert,
        ein erneuter Lauf vervollständigt (resumable); der Speicher bleibt klein
        (streamt). ``should_abort()`` wird vor jeder Notiz geprüft;
        ``on_progress(fertig, gesamt, chunks)`` nach jeder Notiz. Fehler je Notiz
        werden gezählt, brechen den Lauf NICHT ab (fail-safe).

        Verwaiste Chunks (Notiz gelöscht) werden am Ende entfernt — aber NUR bei
        vollständigem Lauf, damit ein Abbruch keine noch-nicht-besuchten Notizen kappt."""
        if not self.aktiv:
            return {"aktiv": False, "notizen": 0, "gesamt": 0, "chunks": 0,
                    "fehler": 0, "abgebrochen": False}
        notizen = list(notizen)
        gesamt = len(notizen)
        fertig = chunks = fehler = 0
        gesehen: set[str] = set()
        abgebrochen = False
        for n in notizen:
            if should_abort and should_abort():
                abgebrochen = True
                break
            try:
                chunks += self.update_notiz(
                    n.get("user_id", "dizzi"), n["id"], n.get("titel", ""),
                    n.get("inhalt", ""), n.get("created_at", ""))
            except Exception:
                fehler += 1
            gesehen.add(n["id"])
            fertig += 1
            if on_progress:
                try:
                    on_progress(fertig, gesamt, chunks)
                except Exception:
                    pass
        if orphan_cleanup and not abgebrochen:
            conn = self._conn()
            verwaist = [r["notiz_id"] for r in conn.execute(
                "SELECT DISTINCT notiz_id FROM rag_chunks").fetchall()
                if r["notiz_id"] not in gesehen]
            for nid in verwaist:
                self.remove_notiz(nid)
        return {"aktiv": True, "notizen": fertig, "gesamt": gesamt,
                "chunks": chunks, "fehler": fehler, "abgebrochen": abgebrochen}

    def status(self) -> dict[str, Any]:
        if not self.aktiv:
            return {"aktiv": False, "modell": self.modell, "dim": self.dim,
                    "bekannt": self.modell in EMBED_MODELLE, "chunks": 0, "notizen": 0}
        conn = self._conn()
        chunks = conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()["n"]
        notizen = conn.execute(
            "SELECT COUNT(DISTINCT notiz_id) AS n FROM rag_chunks").fetchone()["n"]
        return {"aktiv": True, "modell": self.modell, "dim": self.dim,
                "bekannt": self.modell in EMBED_MODELLE, "chunks": chunks, "notizen": notizen}
