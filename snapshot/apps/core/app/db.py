"""SQLite-Schicht.

Schema-Grundsätze (Systemübersicht §4, gelten für JEDE Tabelle):
- UUID-Primärschlüssel (sync-fähig, kollisionsfrei über Geräte)
- ``user_id`` (Multi-User-Vorbereitung Stufe 3)
- ``created_at``/``updated_at`` (ISO-8601 UTC) und ``deleted_at`` als
  Soft-Delete — Voraussetzung für spätere CRDT-Synchronisation.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,          -- JSON
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    UNIQUE (user_id, key)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    actor       TEXT NOT NULL,          -- 'user' | 'ki' | 'system'
    action      TEXT NOT NULL,
    detail      TEXT NOT NULL,          -- JSON
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at);
CREATE TABLE IF NOT EXISTS chat_messages (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,          -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    provider    TEXT,                   -- welcher Provider geantwortet hat
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages (user_id, created_at);
CREATE TABLE IF NOT EXISTS episodes (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    summary     TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'episode',  -- 'episode' | 'essenz' (konsolidiert)
    started_at  TEXT NOT NULL,
    ended_at    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes ON episodes (user_id, ended_at);
CREATE TABLE IF NOT EXISTS observations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    source      TEXT NOT NULL,          -- z. B. 'tradingbot'
    data        TEXT NOT NULL,          -- JSON-Schnappschuss (kompakt)
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs ON observations (user_id, source, created_at);
CREATE TABLE IF NOT EXISTS notices (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    source      TEXT NOT NULL,          -- z. B. 'tradingbot'
    severity    TEXT NOT NULL,          -- 'info' | 'warn' | 'vorschlag'
    title       TEXT NOT NULL,
    detail      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    read_at     TEXT,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_notices ON notices (user_id, created_at);
CREATE TABLE IF NOT EXISTS memory_facts (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    fact        TEXT NOT NULL,
    source      TEXT NOT NULL,          -- 'explizit' | 'auto'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
"""

_local = threading.local()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # M-3: Der Hub hat die meisten nebenläufigen Schreiber (SSO/IdP + KI + Panels).
    # Ohne busy_timeout wirft ein kollidierender Schreiber sofort "database is locked"
    # statt kurz zu warten — derselbe Fix wie appkit.db (5000 ms).
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_defense_schema(conn: sqlite3.Connection) -> None:
    """M-4: Seit der Core-Hub ``install_defense`` DAUERHAFT installiert, sind die
    Defense-Tabellen fester Bestandteil des Core-Schemas. Wie das übrige ``_SCHEMA``
    werden sie JE VERBINDUNG angelegt (IF NOT EXISTS), damit jede Core-DB — auch die
    frischen Test-DBs der ``temp_db``-Fixture — sie führt, statt nur der einen
    Import-Zeit-DB, die ``Defense.__init__`` einmalig bespielt. Single-Source:
    ``appkit.defense.DEFENSE_SCHEMA`` (kein DDL-Duplikat). Sehr früher Import (appkit
    noch nicht auf sys.path) ⇒ still überspringen — ``install_defense`` legt die
    Tabellen dann beim App-Import an."""
    try:
        from appkit.defense import DEFENSE_SCHEMA
    except Exception:
        return
    conn.executescript(DEFENSE_SCHEMA)


def _ensure_verzeichnis_schema(conn: sqlite3.Connection) -> None:
    """§B4 Verzeichnis-KEIM (V-BIZZI-2, D2, docs/84): die einzige vertrauenswürdige
    Subjekt-Quelle der Charta — Rollen + Bereiche je Identität (speist
    ``charta.antrag_bauen``, CH-5). Wie das übrige Schema JE VERBINDUNG angelegt
    (IF NOT EXISTS), damit auch die frischen Test-DBs (``temp_db``-Fixture) die
    Tabelle führen. Single-Source: ``appkit.charta_verzeichnis.SCHEMA`` (kein
    DDL-Duplikat, Muster ``_ensure_defense_schema``). Sehr früher Import (appkit
    noch nicht auf sys.path) ⇒ still überspringen — der nächste Verbindungs-Lauf
    legt die Tabelle an. NUR das Lese-Substrat (Tabelle); die schreibenden
    ``verzeichnis.rolle``-Chronik-Events reiten mit dem netzweiten Chronik-Schritt
    mit (Core hat heute kein Chronik-Substrat/keinen Versiegler)."""
    try:
        from appkit.charta_verzeichnis import SCHEMA
    except Exception:
        return
    conn.executescript(SCHEMA)


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Eine Verbindung je Thread (sqlite3-Objekte sind nicht thread-übergreifend)."""
    path = db_path or settings.db_path
    cached: sqlite3.Connection | None = getattr(_local, "conn", None)
    if cached is None or getattr(_local, "path", None) != path:
        cached = _connect(path)
        cached.executescript(_SCHEMA)
        _ensure_defense_schema(cached)      # M-4: Defense-Tabellen je Verbindung sichern
        _ensure_verzeichnis_schema(cached)  # §B4: Verzeichnis-KEIM-Tabelle je Verbindung sichern
        cached.commit()
        _local.conn = cached
        _local.path = path
    return cached


def reset_thread_conn() -> None:
    """Für Tests: erzwingt frische Verbindung (z. B. nach DB-Pfad-Wechsel)."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _local.path = None


def alle_user_ids() -> list[str]:
    """Alle Nutzer mit Daten (Multi-User-Vorbereitung Stufe 3, docs/50 P6.1) — für die
    PER-NUTZER-Hintergrund-Loops. Vereinigt die ``user_id`` über die per-Nutzer-Tabellen;
    der Single-User ``DEFAULT_USER_ID`` ist IMMER dabei ⇒ im Single-User-Betrieb exakt
    ``[dizzi]`` (Default-Verhalten unverändert), im Multi-User-Fall alle aktiven Nutzer."""
    from .config import DEFAULT_USER_ID
    conn = get_conn()
    ids: set[str] = {DEFAULT_USER_ID}
    for tabelle in ("chat_messages", "memory_facts", "episodes", "app_settings"):
        try:                                  # Tabelle fehlt (alte DB) ⇒ überspringen
            for r in conn.execute(f"SELECT DISTINCT user_id FROM {tabelle}"):
                if r["user_id"]:
                    ids.add(r["user_id"])
        except sqlite3.OperationalError:
            pass
    return sorted(ids)


# --- Settings (Key-Value, JSON-Werte, user-scoped) -------------------------

def setting_get(user_id: str, key: str, default: Any = None) -> Any:
    row = get_conn().execute(
        "SELECT value FROM app_settings WHERE user_id=? AND key=? AND deleted_at IS NULL",
        (user_id, key),
    ).fetchone()
    return json.loads(row["value"]) if row else default


def setting_put(user_id: str, key: str, value: Any) -> None:
    conn = get_conn()
    ts = now_iso()
    conn.execute(
        """INSERT INTO app_settings (id, user_id, key, value, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (user_id, key)
           DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, deleted_at=NULL""",
        (new_id(), user_id, key, json.dumps(value, ensure_ascii=False), ts, ts),
    )
    conn.commit()


def settings_all(user_id: str) -> dict[str, Any]:
    rows = get_conn().execute(
        "SELECT key, value FROM app_settings WHERE user_id=? AND deleted_at IS NULL",
        (user_id,),
    ).fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


# --- Audit-Log (jede Aktion mit Wirkung wird protokollierbar) ---------------

def audit(user_id: str, actor: str, action: str, detail: dict[str, Any] | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (id, user_id, actor, action, detail, created_at) VALUES (?,?,?,?,?,?)",
        (new_id(), user_id, actor, action, json.dumps(detail or {}, ensure_ascii=False), now_iso()),
    )
    conn.commit()


def audit_recent(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT actor, action, detail, created_at FROM audit_log "
        "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [
        {"actor": r["actor"], "action": r["action"],
         "detail": json.loads(r["detail"]), "created_at": r["created_at"]}
        for r in rows
    ]


# --- Datenrechte (KA-H1 / DSGVO Art. 17): Lösch-Kaskade ---------------------
# Der Core baut FastAPI direkt (kein appkit ``create_app``) und hatte daher gar
# KEINEN Lösch-Pfad — Identität/Sessions/Chat/Memory/Observations überlebten eine
# Konto-Löschung. Diese Helfer spiegeln ``appkit/db.py:210-293`` auf die Core-
# eigene conn-Verwaltung. Die HARTE Räumung der Tabellen OHNE ``deleted_at``
# (Identität/Auth, RAG, agent_laeufe) + der HTTP-Endpoint liegen in
# ``konto_loeschung.py`` (Endpoint gegatet, s. dortiger Docstring).

def user_tabellen() -> list[tuple[str, bool]]:
    """Alle Tabellen mit ``user_id``-Spalte: ``(Name, hat_deleted_at)`` — über die
    Vertrags-Konvention (``sqlite_master`` + ``PRAGMA table_info``, wie appkit)."""
    conn = get_conn()
    namen = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]
    out = []
    for t in namen:
        spalten = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
        if "user_id" in spalten:
            out.append((t, "deleted_at" in spalten))
    return out


def soft_delete_user(
    user_id: str,
    behalten: tuple[str, ...] = ("audit_log", "id_clients"),
) -> dict[str, int]:
    """Lösch-Kaskade (Soft-Delete-Konvention): markiert alle Nutzer-Zeilen als
    gelöscht. ``audit_log`` bleibt (Löschbeleg der Löschung selbst); ``id_clients``
    bleibt (das sind die App-/RP-Registrierungen des Netzes = KEINE Nutzerdaten;
    ein Soft-Delete bräche das netzweite SSO). Tabellen OHNE ``deleted_at`` werden
    übersprungen — die räumt der harte Hook (``konto_loeschung._raeume_core_artefakte``)."""
    conn = get_conn()
    ts = now_iso()
    zaehler: dict[str, int] = {}
    for t, hat_deleted in user_tabellen():
        if t in behalten or not hat_deleted:
            continue
        cur = conn.execute(
            f"UPDATE {t} SET deleted_at=? WHERE user_id=? AND deleted_at IS NULL",
            (ts, user_id))
        if cur.rowcount:
            zaehler[t] = cur.rowcount
    conn.commit()
    return zaehler
