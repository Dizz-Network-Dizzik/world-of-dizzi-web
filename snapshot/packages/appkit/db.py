"""SQLite-Schicht des App-Vertrags — Datenkonventionen für JEDE Tabelle.

Generalisiert aus dem bewährten Dizzi-Core (core/app/db.py). Die Konventionen
sind Vertragsbestandteil (K5 baut darauf auf, ohne sie zu ändern):
- UUID-Primärschlüssel (sync-fähig, kollisionsfrei über Geräte)
- ``user_id`` auf jeder Zeile (Multi-User-Vorbereitung Stufe 3)
- ``created_at``/``updated_at`` (ISO-8601 UTC) und ``deleted_at`` als
  Soft-Delete — Voraussetzung für spätere Synchronisation.

Anders als im Core ist die Datenbank hier eine KLASSE statt Modul-Singleton:
jede App hält ihre eigene ``Database``-Instanz (eigener Pfad unter
``C:\\Dizzik\\data\\apps\\<app_id>\\``), Tests injizieren tmp-Pfade direkt,
und mehrere Apps können im selben Prozess koexistieren (Test-Suites).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Basis-Schema des Vertrags: Settings (K2 baut darauf auf) + Audit-Log
# (Pflicht — K1 protokolliert hier später alle Auth-Ereignisse).
_BASE_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS app_actions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,          -- registrierte Aktion (ActionRegistry)
    params      TEXT NOT NULL,          -- JSON
    source      TEXT NOT NULL,          -- 'ki' | 'mcp' | 'user'
    status      TEXT NOT NULL,          -- pending|approved|rejected|executed|failed|expired
    result      TEXT,                   -- JSON (nach Ausführung)
    expires_at  REAL NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions ON app_actions (user_id, status, created_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


class Database:
    """Eine SQLite-Datenbank einer App — Verbindungen je Thread, Schema beim
    ersten Zugriff. ``extra_schema`` sind die Domänen-Tabellen der App (müssen
    den Konventionen oben folgen)."""

    def __init__(self, db_path: Path, extra_schema: str = "") -> None:
        self.db_path = Path(db_path)
        self._schema = _BASE_SCHEMA + extra_schema
        self._local = threading.local()

    def get_conn(self) -> sqlite3.Connection:
        cached: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if cached is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            cached = sqlite3.connect(self.db_path)
            cached.row_factory = sqlite3.Row
            cached.execute("PRAGMA journal_mode=WAL")
            cached.execute("PRAGMA foreign_keys=ON")
            # Concurrent-Writer warten lassen statt sofort SQLITE_BUSY: bei parallelem
            # User-Write + Querverbindungs-/Relay-Write (anderer Request-Thread) blockt
            # SQLite bis 5 s, statt „database is locked" an den Nutzer durchzureichen.
            # (synchronous bleibt bewusst FULL — Durability für Finanz-/Tresor-Daten.)
            cached.execute("PRAGMA busy_timeout=5000")
            self._apply_schema(cached)
            cached.commit()
            self._local.conn = cached
        return cached

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        """Wendet das Schema an — robust gegen eine einzelne DDL-Anweisung, die
        auf einer ALT-DB scheitert, weil sie auf eine erst per App-Migration
        (``ALTER ... ADD COLUMN``) nachgerüstete Spalte verweist (z. B.
        ``CREATE INDEX … (neue_spalte)``). ``executescript`` würde sonst den
        GANZEN Schema-Lauf abbrechen ⇒ App-Start scheitert beim Neustart auf
        Bestands-DBs. Happy-Path unverändert (executescript); NUR im Fehlerfall
        Statement-für-Statement, Einzelfehler überspringen — die App-Migration
        rüstet die Spalte nach, der nächste Verbindungs-Lauf legt Index/DDL an.
        (Wurzel-Härtung gegen die Bug-Klasse „Schema-DDL auf Migrations-Spalte",
        docs/25 H-8; CREATE TABLE IF NOT EXISTS bleibt voll erhalten.)"""
        try:
            conn.executescript(self._schema)
        except sqlite3.OperationalError:
            for stmt in self._schema.split(";"):
                if stmt.strip():
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass

    def reset_thread_conn(self) -> None:
        """Für Tests: erzwingt eine frische Verbindung im aktuellen Thread."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
        self._local.conn = None

    @contextmanager
    def transaktion(self):
        """Atomarer Schreibblock: BEGIN IMMEDIATE → COMMIT bei Erfolg,
        ROLLBACK bei Exception. Additiv — bestehende get_conn()-Nutzung
        (Statement + eigenes commit()) bleibt unverändert gültig.
        BEGIN IMMEDIATE nimmt die Write-Sperre sofort (wartet via
        busy_timeout=5000) statt Deferred-Upgrade mitten im Block
        (SQLITE_BUSY-Falle). WICHTIG: im Block KEINE Helfer aufrufen,
        die selbst committen (db.audit/setting_put/…) — die würden die
        offene Transaktion vorzeitig persistieren. Kein Nesting: eine
        bereits offene Txn dieses Threads = Programmierfehler ⇒ fail-loud."""
        conn = self.get_conn()
        if conn.in_transaction:
            raise RuntimeError(
                "transaktion(): in diesem Thread ist bereits eine Transaktion offen — "
                "verschachtelte transaktion()-Blöcke sind nicht unterstützt")
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()

    # --- Settings (Key-Value, JSON-Werte, user-scoped; K2 baut darauf auf) --

    def setting_get(self, user_id: str, key: str, default: Any = None) -> Any:
        row = self.get_conn().execute(
            "SELECT value FROM app_settings WHERE user_id=? AND key=? AND deleted_at IS NULL",
            (user_id, key),
        ).fetchone()
        return json.loads(row["value"]) if row else default

    def setting_put(self, user_id: str, key: str, value: Any) -> None:
        conn = self.get_conn()
        ts = now_iso()
        conn.execute(
            """INSERT INTO app_settings (id, user_id, key, value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, key)
               DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, deleted_at=NULL""",
            (new_id(), user_id, key, json.dumps(value, ensure_ascii=False), ts, ts),
        )
        conn.commit()

    def settings_all(self, user_id: str) -> dict[str, Any]:
        rows = self.get_conn().execute(
            "SELECT key, value FROM app_settings WHERE user_id=? AND deleted_at IS NULL",
            (user_id,),
        ).fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # --- Audit-Log (jede Aktion mit Wirkung wird protokollierbar) ------------

    def audit(self, user_id: str, actor: str, action: str,
              detail: dict[str, Any] | None = None) -> None:
        conn = self.get_conn()
        conn.execute(
            "INSERT INTO audit_log (id, user_id, actor, action, detail, created_at) VALUES (?,?,?,?,?,?)",
            (new_id(), user_id, actor, action,
             json.dumps(detail or {}, ensure_ascii=False), now_iso()),
        )
        conn.commit()

    def audit_recent(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.get_conn().execute(
            "SELECT actor, action, detail, created_at FROM audit_log "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {"actor": r["actor"], "action": r["action"],
             "detail": json.loads(r["detail"]), "created_at": r["created_at"]}
            for r in rows
        ]

    # --- Datenrechte (K2.1b, Vertrag 1.3): Export + Lösch-Kaskade ------------
    # Arbeitet über die Vertrags-Konventionen (user_id/deleted_at auf jeder
    # Tabelle) — funktioniert damit für JEDE App ohne Per-App-Code.

    def user_tabellen(self) -> list[tuple[str, bool]]:
        """Alle Tabellen mit ``user_id``-Spalte: (Name, hat_deleted_at)."""
        conn = self.get_conn()
        namen = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        out = []
        for t in namen:
            spalten = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
            if "user_id" in spalten:
                out.append((t, "deleted_at" in spalten))
        return out

    def export_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """DSGVO-Export: ALLE Zeilen des Nutzers, je Tabelle, maschinenlesbar.
        Inklusive Audit-Log (Transparenz); Tresor-WERTE sind nie dabei."""
        conn = self.get_conn()
        out: dict[str, list[dict[str, Any]]] = {}
        for t, _ in self.user_tabellen():
            rows = conn.execute(f"SELECT * FROM {t} WHERE user_id=?",
                                (user_id,)).fetchall()
            out[t] = [dict(r) for r in rows]
        return out

    def retention_lauf(self, user_id: str, tage: int) -> dict[str, int]:
        """Datenhygiene (Tiefen-Review 12.06.): setzt das K2-Setting
        ``aufbewahrung_tage`` DURCH — vorher existierte es nur als Schalter.
        Endgültig gelöscht wird, was älter als ``tage`` ist:
        - ``audit_log``-Einträge (das Protokoll wächst sonst unbegrenzt),
        - Defense-Vorfälle und beendete Defense-Maßnahmen,
        - längst SOFT-gelöschte Zeilen ALLER user-Tabellen (Purge).
        Läuft beim App-Start (create_app-Lifespan) — billig und idempotent."""
        if tage < 1:
            return {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=tage)
                  ).isoformat(timespec="seconds")
        conn = self.get_conn()
        geloescht: dict[str, int] = {}

        def _del(name: str, sql: str, params: tuple) -> None:
            n = conn.execute(sql, params).rowcount
            if n:
                geloescht[name] = geloescht.get(name, 0) + n

        _del("audit_log",
             "DELETE FROM audit_log WHERE user_id=? AND created_at<?",
             (user_id, cutoff))
        tabellen = {t for t, _ in self.user_tabellen()}
        if "defense_vorfaelle" in tabellen:
            _del("defense_vorfaelle",
                 "DELETE FROM defense_vorfaelle WHERE created_at<?", (cutoff,))
        if "defense_massnahmen" in tabellen:
            _del("defense_massnahmen",
                 "DELETE FROM defense_massnahmen WHERE status!='aktiv' "
                 "AND updated_at<?", (cutoff,))
        for t, hat_deleted in self.user_tabellen():
            if hat_deleted and t != "audit_log":
                _del(f"{t} (purge)",
                     f"DELETE FROM {t} WHERE deleted_at IS NOT NULL AND deleted_at<?",
                     (cutoff,))
        conn.commit()
        if geloescht:
            self.audit(user_id, "system", "retention_gelaufen",
                       {"tage": tage, "geloescht": geloescht})
        return geloescht

    def soft_delete_user(self, user_id: str,
                         behalten: tuple[str, ...] = ("audit_log",)) -> dict[str, int]:
        """Lösch-Kaskade (Soft-Delete-Konvention): markiert alle Nutzer-Zeilen
        als gelöscht. ``audit_log`` bleibt bewusst (Nachvollziehbarkeit der
        Löschung selbst); Tabellen ohne deleted_at werden übersprungen."""
        conn = self.get_conn()
        ts = now_iso()
        zaehler: dict[str, int] = {}
        for t, hat_deleted in self.user_tabellen():
            if t in behalten or not hat_deleted:
                continue
            cur = conn.execute(
                f"UPDATE {t} SET deleted_at=? WHERE user_id=? AND deleted_at IS NULL",
                (ts, user_id))
            if cur.rowcount:
                zaehler[t] = cur.rowcount
        conn.commit()
        return zaehler


def default_db_path(app_id: str, data_root: Path | None = None) -> Path:
    """Standard-Datenpfad einer App: ``<root>/apps/<app_id>/<app_id>.sqlite``.

    ``data_root`` default = ``C:\\Dizzik\\data`` (außerhalb OneDrive,
    Datei-Sperren-Lehre aus dem Trading Bot); per Env ``DIZZ_<ID>_DATA_DIR``
    übersteuerbar (config.py der App bzw. Tests).
    """
    root = data_root or Path(r"C:\Dizzik\data")
    return root / "apps" / app_id / f"{app_id}.sqlite"
