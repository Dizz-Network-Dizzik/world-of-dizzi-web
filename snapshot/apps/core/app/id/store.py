"""Persistenz von Dizzi-ID — Codes, Sessions, Refresh-Familien, Identität.

Sicherheitsgrundsätze:
- Geheimnisse (Codes, Session-IDs, Refresh-Tokens) werden NUR GEHASHT
  gespeichert (SHA-256) — ein DB-Leak gibt keine verwendbaren Tokens her.
- Authorization-Codes: single-use, 60 s TTL, PKCE-S256-Challenge gebunden.
- Refresh-Tokens: Rotation je Nutzung; Wiederverwendung eines alten Tokens
  (Reuse) widerruft die GESAMTE Familie (RFC 9700) und wird auditiert.
- Lokales Passwort: scrypt (stdlib, memory-hard; n=2^14, r=8, p=1).
- Single-User Stufe 1: genau EINE Identität (user_id 'dizzi'); Google-Konto
  wird beim ersten Login GEPINNT — spätere Logins müssen dieselbe sub liefern.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from .. import db
from ..config import DEFAULT_USER_ID

CODE_TTL_S = 60
SESSION_TTL_S = 12 * 3600
ACCESS_TTL_S = 15 * 60
IDTOKEN_TTL_S = 10 * 60
REFRESH_TTL_S = 30 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS id_clients (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    client_id     TEXT NOT NULL UNIQUE,
    redirect_uris TEXT NOT NULL,         -- JSON-Liste
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT
);
CREATE TABLE IF NOT EXISTS id_codes (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    code_hash      TEXT NOT NULL UNIQUE,
    client_id      TEXT NOT NULL,
    redirect_uri   TEXT NOT NULL,
    challenge      TEXT NOT NULL,        -- PKCE S256-Challenge
    nonce          TEXT,
    level          TEXT NOT NULL,
    amr            TEXT NOT NULL,        -- JSON-Liste
    expires_at     REAL NOT NULL,
    used_at        TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS id_sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    sid_hash    TEXT NOT NULL UNIQUE,
    level       TEXT NOT NULL,
    amr         TEXT NOT NULL,           -- JSON-Liste
    expires_at  REAL NOT NULL,
    created_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE TABLE IF NOT EXISTS id_refresh (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    family      TEXT NOT NULL,           -- Rotations-Familie (Reuse-Erkennung)
    client_id   TEXT NOT NULL,
    level       TEXT NOT NULL,
    amr         TEXT NOT NULL,
    expires_at  REAL NOT NULL,
    created_at  TEXT NOT NULL,
    rotated_at  TEXT,                    -- gesetzt = verbraucht (Nachfolger existiert)
    revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_id_refresh_family ON id_refresh (family);
CREATE TABLE IF NOT EXISTS id_identity (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL UNIQUE,
    google_sub        TEXT,              -- beim ersten Google-Login gepinnt
    google_email      TEXT,
    pw_scrypt         TEXT,              -- json {salt, hash} | NULL = kein lokales Passwort
    totp_secret       TEXT,              -- Base32; gesetzt = Enrollment begonnen
    totp_confirmed_at TEXT,              -- gesetzt = MFA aktiv (Step-up möglich)
    totp_last_counter INTEGER NOT NULL DEFAULT 0,  -- Replay-Schutz (RFC 6238)
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS id_lockout (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    zweck         TEXT NOT NULL,         -- 'passwort' | 'totp' | 'webauthn'
    fehlversuche  INTEGER NOT NULL DEFAULT 0,
    gesperrt_bis  REAL NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    UNIQUE (user_id, zweck)
);
CREATE TABLE IF NOT EXISTS id_webauthn (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    cred_id       TEXT NOT NULL UNIQUE,  -- base64url der Credential-ID
    public_key    TEXT NOT NULL,         -- COSE-Blob (JSON, s. webauthn.py)
    alg           INTEGER NOT NULL,
    sign_count    INTEGER NOT NULL DEFAULT 0,
    aaguid        TEXT,
    label         TEXT,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,
    deleted_at    TEXT
);
CREATE TABLE IF NOT EXISTS id_webauthn_chal (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    zweck         TEXT NOT NULL,         -- 'register' | 'assert'
    challenge     TEXT NOT NULL,         -- base64url (raw bytes)
    expires_at    REAL NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (user_id, zweck)
);
"""

# Spalten-Nachrüstungen für Bestands-DBs (idempotent; Fehler 'duplicate column'
# wird geschluckt). Neue Spalten IMMER auch oben ins CREATE aufnehmen.
_MIGRATIONS = [
    "ALTER TABLE id_identity ADD COLUMN totp_secret TEXT",
    "ALTER TABLE id_identity ADD COLUMN totp_confirmed_at TEXT",
    "ALTER TABLE id_identity ADD COLUMN totp_last_counter INTEGER NOT NULL DEFAULT 0",
    # H4: Lockout-Tabelle auch in Bestands-DBs (IF NOT EXISTS = idempotent)
    """CREATE TABLE IF NOT EXISTS id_lockout (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, zweck TEXT NOT NULL,
        fehlversuche INTEGER NOT NULL DEFAULT 0,
        gesperrt_bis REAL NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL, UNIQUE (user_id, zweck))""",
    # R1.3b: WebAuthn-Tabellen in Bestands-DBs nachrüsten
    """CREATE TABLE IF NOT EXISTS id_webauthn (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, cred_id TEXT NOT NULL UNIQUE,
        public_key TEXT NOT NULL, alg INTEGER NOT NULL,
        sign_count INTEGER NOT NULL DEFAULT 0, aaguid TEXT, label TEXT,
        created_at TEXT NOT NULL, last_used_at TEXT, deleted_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS id_webauthn_chal (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, zweck TEXT NOT NULL,
        challenge TEXT NOT NULL, expires_at REAL NOT NULL, created_at TEXT NOT NULL,
        UNIQUE (user_id, zweck))""",
]

def _conn():
    conn = db.get_conn()
    # Schema idempotent sicherstellen — Prüfung über sqlite_master statt einer
    # Prozess-Merkliste (id(conn) kann nach GC recycelt werden; Tests wechseln
    # zudem den DB-Pfad pro Test). Der Lookup ist billig.
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='id_clients'"
    ).fetchone()
    if row is None:
        conn.executescript(_SCHEMA)
        conn.commit()
    else:
        import sqlite3
        for mig in _MIGRATIONS:
            try:
                conn.execute(mig)
            except sqlite3.OperationalError:
                pass  # Spalte existiert bereits
        conn.commit()
    return conn


def _h(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# --- Clients (die Apps des Netzwerks als Relying Parties) --------------------

# Soll-Apps + Referenz: Ports aus den App-Vertrag-Stubs (docs/01 je App).
# H10: BEIDE Loopback-Hosts je Client — der RP leitet die Callback-URI
# host-konsistent aus dem Browser-Request ab (localhost ODER 127.0.0.1);
# die Registry muss beide Varianten kennen (exakter redirect-Abgleich bleibt).
def _beide_hosts(port: int) -> list[str]:
    return [f"http://127.0.0.1:{port}/auth/callback",
            f"http://localhost:{port}/auth/callback"]


# Schlüssel = MANIFEST-id (das, was die App als ``client_id`` sendet, s.
# appkit/dizzi_id.py) auf ihrem FINALEN Port. KORRIGIERT 16.06.: vorher standen
# hier die alten ORDNER-ids (buerokratie/projekte/archiv/social-media) mit
# Scaffold-Ports — dadurch hatten admin/plans/memory/management GAR KEINEN Client
# und ihr SSO-Login lief in ``invalid_client`` (exakter redirect_uri-Abgleich).
SEED_CLIENTS: dict[str, list[str]] = {
    "finanzen": _beide_hosts(8210),    # Dizz Money
    "memory": _beide_hosts(8212),      # Dizz Memory (Ordner archiv)
    "management": _beide_hosts(8213),  # Dizz Management (Ordner social-media)
    "creator": _beide_hosts(8214),     # Dizz Creating
    "news": _beide_hosts(8216),
    "health": _beide_hosts(8217),
    "kommunikation": _beide_hosts(8218),
    "admin": _beide_hosts(8222),       # Dizz Admin (vereint; Basis-Repo admin/adminapp, vormals leading)
    "refapp": _beide_hosts(8290),
    "tradingbot": _beide_hosts(8137),
    # plans (:8211) + leading (:8219) wurden in Dizz Admin verschmolzen (docs/28) ⇒
    # keine eigenen SSO-Clients mehr (abgewickelt 19.06.).
}


def ensure_clients() -> None:
    conn = _conn()
    # Guard zählt + prüft die H10-Migration: wächst SEED_CLIENTS (neue App!)
    # ODER fehlt einem Bestands-Client die localhost-Variante, wird nachgesät/
    # gemerged (nur ADDITIV — selbst gepflegte URIs bleiben erhalten).
    # Re-Seed, sobald EIN SEED-Client fehlt (robuster als die alte Zähl-Heuristik:
    # eine Schlüssel-Umbenennung — z. B. archiv→memory, 16.06. — wäre sonst nie
    # nachgesät worden). deleted_at-gefiltert: ein bewusst stillgelegter Orphan
    # zählt als „nicht vorhanden", wird aber nicht neu angelegt (kein SEED-Key).
    vorhandene = {r["client_id"] for r in conn.execute(
        "SELECT client_id FROM id_clients WHERE deleted_at IS NULL")}
    probe = conn.execute(
        "SELECT redirect_uris FROM id_clients WHERE client_id='news'").fetchone()
    migriert = probe is not None and "localhost" in probe["redirect_uris"]
    if SEED_CLIENTS.keys() <= vorhandene and migriert:
        return
    ts = db.now_iso()
    for client_id, uris in SEED_CLIENTS.items():
        row = conn.execute(
            "SELECT id, redirect_uris FROM id_clients WHERE client_id=?",
            (client_id,)).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO id_clients (id, user_id, client_id, redirect_uris, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (client_id) DO NOTHING""",
                (db.new_id(), DEFAULT_USER_ID, client_id, json.dumps(uris), ts, ts))
            continue
        vorhanden = json.loads(row["redirect_uris"])
        merged = vorhanden + [u for u in uris if u not in vorhanden]
        if merged != vorhanden:
            conn.execute(
                "UPDATE id_clients SET redirect_uris=?, updated_at=? WHERE id=?",
                (json.dumps(merged), ts, row["id"]))
    conn.commit()


def client_redirects(client_id: str) -> list[str] | None:
    row = _conn().execute(
        "SELECT redirect_uris FROM id_clients WHERE client_id=? AND deleted_at IS NULL",
        (client_id,)).fetchone()
    return json.loads(row["redirect_uris"]) if row else None


# --- Authorization-Codes (PKCE-gebunden, single-use, 60 s) -------------------

def issue_code(client_id: str, redirect_uri: str, challenge: str,
               nonce: str | None, level: str, amr: list[str]) -> str:
    code = secrets.token_urlsafe(32)
    conn = _conn()
    conn.execute(
        """INSERT INTO id_codes (id, user_id, code_hash, client_id, redirect_uri,
                                 challenge, nonce, level, amr, expires_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (db.new_id(), DEFAULT_USER_ID, _h(code), client_id, redirect_uri,
         challenge, nonce, level, json.dumps(amr), time.time() + CODE_TTL_S, db.now_iso()))
    conn.commit()
    return code


def redeem_code(code: str, client_id: str, redirect_uri: str,
                verifier: str) -> dict[str, Any] | None:
    """Single-use-Einlösung inkl. PKCE-Prüfung. None = ungültig (Grund wird
    bewusst nicht unterschieden — keine Orakel für Angreifer)."""
    conn = _conn()
    row = conn.execute("SELECT * FROM id_codes WHERE code_hash=?", (_h(code),)).fetchone()
    if row is None or row["used_at"] is not None or row["expires_at"] < time.time():
        return None
    if row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
        return None
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected, row["challenge"]):
        return None
    # M-2: die Einlösung selbst ist die ATOMARE Gate (WHERE ... AND used_at IS NULL
    # + rowcount) — sonst könnten zwei nebenläufige Anfragen denselben Auth-Code
    # doppelt einlösen (beide passieren die SELECT-Prüfung oben). Verliert eine das
    # Rennen (rowcount 0), ist der Code schon weg ⇒ ungültig.
    cur = conn.execute("UPDATE id_codes SET used_at=? WHERE id=? AND used_at IS NULL",
                       (db.now_iso(), row["id"]))
    conn.commit()
    if cur.rowcount != 1:
        return None
    return {"user_id": row["user_id"], "nonce": row["nonce"],
            "level": row["level"], "amr": json.loads(row["amr"])}


# --- IdP-Sessions (das „einmal anmelden" des SSO) ----------------------------

def create_session(level: str, amr: list[str]) -> str:
    sid = secrets.token_urlsafe(32)
    conn = _conn()
    conn.execute(
        """INSERT INTO id_sessions (id, user_id, sid_hash, level, amr, expires_at, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (db.new_id(), DEFAULT_USER_ID, _h(sid), level, json.dumps(amr),
         time.time() + SESSION_TTL_S, db.now_iso()))
    conn.commit()
    return sid


def get_session(sid: str | None) -> dict[str, Any] | None:
    if not sid:
        return None
    row = _conn().execute(
        "SELECT * FROM id_sessions WHERE sid_hash=? AND revoked_at IS NULL",
        (_h(sid),)).fetchone()
    if row is None or row["expires_at"] < time.time():
        return None
    return {"user_id": row["user_id"], "level": row["level"],
            "amr": json.loads(row["amr"])}


def revoke_session(sid: str | None) -> None:
    if not sid:
        return
    conn = _conn()
    conn.execute("UPDATE id_sessions SET revoked_at=? WHERE sid_hash=?",
                 (db.now_iso(), _h(sid)))
    conn.commit()


# --- K2.1b/H7: Session-Übersicht + gezielter Widerruf -------------------------

def list_sessions(aktuelle_sid: str | None = None) -> list[dict[str, Any]]:
    """Alle AKTIVEN Sessions (für die Account-Übersicht); die Session der
    aktuellen Anfrage ist markiert. IDs sind die DB-IDs — die geheimen
    Session-Tokens (sid) verlassen den Store weiterhin nie."""
    aktuelle_hash = _h(aktuelle_sid) if aktuelle_sid else None
    rows = _conn().execute(
        "SELECT * FROM id_sessions WHERE revoked_at IS NULL AND expires_at > ? "
        "ORDER BY created_at DESC", (time.time(),)).fetchall()
    return [{"id": r["id"], "level": r["level"], "amr": json.loads(r["amr"]),
             "created_at": r["created_at"], "expires_at": r["expires_at"],
             "aktuell": r["sid_hash"] == aktuelle_hash} for r in rows]


def revoke_session_id(session_id: str) -> bool:
    """Widerruft EINE Session über ihre DB-ID (Einzel-Widerruf aus der UI)."""
    conn = _conn()
    cur = conn.execute(
        "UPDATE id_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
        (db.now_iso(), session_id))
    conn.commit()
    return cur.rowcount > 0


def revoke_all_sessions() -> int:
    """„Überall abmelden": widerruft ALLE aktiven Sessions (inkl. der
    aktuellen — der Aufrufer muss sich danach neu anmelden)."""
    conn = _conn()
    cur = conn.execute(
        "UPDATE id_sessions SET revoked_at=? WHERE revoked_at IS NULL",
        (db.now_iso(),))
    conn.commit()
    return cur.rowcount


# --- Refresh-Tokens: Rotation + Familien-Reuse-Erkennung (RFC 9700) ----------

def issue_refresh(client_id: str, level: str, amr: list[str],
                  family: str | None = None) -> str:
    token = secrets.token_urlsafe(48)
    conn = _conn()
    conn.execute(
        """INSERT INTO id_refresh (id, user_id, token_hash, family, client_id,
                                   level, amr, expires_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (db.new_id(), DEFAULT_USER_ID, _h(token), family or db.new_id(), client_id,
         level, json.dumps(amr), time.time() + REFRESH_TTL_S, db.now_iso()))
    conn.commit()
    return token


def rotate_refresh(token: str, client_id: str) -> dict[str, Any] | None:
    """Rotiert ein Refresh-Token. Reuse eines bereits rotierten Tokens
    widerruft die GESAMTE Familie und liefert {'reuse': True}."""
    conn = _conn()
    row = conn.execute("SELECT * FROM id_refresh WHERE token_hash=?", (_h(token),)).fetchone()
    if row is None or row["client_id"] != client_id:
        return None
    if row["revoked_at"] is not None or row["expires_at"] < time.time():
        return None
    if row["rotated_at"] is not None:                     # REUSE erkannt!
        conn.execute("UPDATE id_refresh SET revoked_at=? WHERE family=? AND revoked_at IS NULL",
                     (db.now_iso(), row["family"]))
        conn.commit()
        return {"reuse": True, "family": row["family"]}
    # M-2: die Rotation selbst ist die ATOMARE Gate (WHERE ... AND rotated_at IS NULL
    # + rowcount). Verliert eine nebenläufige Anfrage das Rennen, wurde derselbe
    # Refresh-Token faktisch zweimal benutzt = Reuse ⇒ die GESAMTE Familie widerrufen
    # (RFC-6819-Rotation), statt zweimal neue Tokens auszugeben.
    cur = conn.execute("UPDATE id_refresh SET rotated_at=? WHERE id=? AND rotated_at IS NULL",
                       (db.now_iso(), row["id"]))
    conn.commit()
    if cur.rowcount != 1:
        conn.execute("UPDATE id_refresh SET revoked_at=? WHERE family=? AND revoked_at IS NULL",
                     (db.now_iso(), row["family"]))
        conn.commit()
        return {"reuse": True, "family": row["family"]}
    new_token = issue_refresh(client_id, row["level"], json.loads(row["amr"]),
                              family=row["family"])
    return {"reuse": False, "token": new_token, "level": row["level"],
            "amr": json.loads(row["amr"]), "user_id": row["user_id"]}


# --- H4: Lockout (Brute-Force-Bremse für Passwort + TOTP) --------------------
# Durchgesetzt DIREKT in check_local_password/totp_verify — eine künftige
# Route kann die Bremse nicht vergessen (fail-closed am Credential-Check).

LOCKOUT_SCHWELLE = 5                     # freie Versuche, danach Sperrfenster
LOCKOUT_BASIS_S = 30.0                   # 30 s, je weiterem Fehlversuch ×2
LOCKOUT_MAX_S = 3600.0


def lockout_rest(zweck: str) -> float:
    """Verbleibende Sperrzeit in Sekunden (0 = frei). Für Routen/UI."""
    row = _conn().execute(
        "SELECT gesperrt_bis FROM id_lockout WHERE user_id=? AND zweck=?",
        (DEFAULT_USER_ID, zweck)).fetchone()
    if row is None:
        return 0.0
    return max(0.0, row["gesperrt_bis"] - time.time())


def _lockout_fehlversuch(zweck: str) -> None:
    conn = _conn()
    conn.execute(
        """INSERT INTO id_lockout (id, user_id, zweck, fehlversuche, updated_at)
           VALUES (?, ?, ?, 0, ?)
           ON CONFLICT (user_id, zweck) DO NOTHING""",
        (db.new_id(), DEFAULT_USER_ID, zweck, db.now_iso()))
    row = conn.execute(
        "SELECT fehlversuche FROM id_lockout WHERE user_id=? AND zweck=?",
        (DEFAULT_USER_ID, zweck)).fetchone()
    n = row["fehlversuche"] + 1
    sperre = 0.0
    if n >= LOCKOUT_SCHWELLE:            # exponentielles Backoff ab Schwelle
        sperre = min(LOCKOUT_MAX_S, LOCKOUT_BASIS_S * 2 ** (n - LOCKOUT_SCHWELLE))
    conn.execute(
        "UPDATE id_lockout SET fehlversuche=?, gesperrt_bis=?, updated_at=? "
        "WHERE user_id=? AND zweck=?",
        (n, time.time() + sperre if sperre else 0, db.now_iso(),
         DEFAULT_USER_ID, zweck))
    conn.commit()


def _lockout_reset(zweck: str) -> None:
    conn = _conn()
    conn.execute("DELETE FROM id_lockout WHERE user_id=? AND zweck=?",
                 (DEFAULT_USER_ID, zweck))
    conn.commit()


# --- Identität: lokales Passwort (scrypt) + Google-Pinning -------------------

def _identity_row():
    return _conn().execute("SELECT * FROM id_identity WHERE user_id=?",
                           (DEFAULT_USER_ID,)).fetchone()


def _ensure_identity() -> None:
    conn = _conn()
    ts = db.now_iso()
    conn.execute(
        """INSERT INTO id_identity (id, user_id, created_at, updated_at)
           VALUES (?, ?, ?, ?) ON CONFLICT (user_id) DO NOTHING""",
        (db.new_id(), DEFAULT_USER_ID, ts, ts))
    conn.commit()


def _scrypt(pw: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1)


def has_local_password() -> bool:
    row = _identity_row()
    return bool(row and row["pw_scrypt"])


def set_local_password(pw: str) -> None:
    if len(pw) < 8:
        raise ValueError("Passwort zu kurz (min. 8 Zeichen)")
    _ensure_identity()
    salt = secrets.token_bytes(16)
    blob = json.dumps({"salt": salt.hex(), "hash": _scrypt(pw, salt).hex()})
    conn = _conn()
    conn.execute("UPDATE id_identity SET pw_scrypt=?, updated_at=? WHERE user_id=?",
                 (blob, db.now_iso(), DEFAULT_USER_ID))
    conn.commit()


def check_local_password(pw: str) -> bool:
    """Passwort-Prüfung MIT Lockout (H4): gesperrte Fenster lehnen sofort ab,
    Fehlversuche zählen, Erfolg setzt zurück."""
    if lockout_rest("passwort") > 0:
        return False
    row = _identity_row()
    if not row or not row["pw_scrypt"]:
        return False
    data = json.loads(row["pw_scrypt"])
    expected = bytes.fromhex(data["hash"])
    ok = hmac.compare_digest(_scrypt(pw, bytes.fromhex(data["salt"])), expected)
    if ok:
        _lockout_reset("passwort")
    else:
        _lockout_fehlversuch("passwort")
    return ok


def upgrade_session(sid: str | None, level: str, add_amr: str) -> bool:
    """Step-up: hebt eine bestehende Session auf eine höhere Stufe (R1.3)."""
    if not sid:
        return False
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM id_sessions WHERE sid_hash=? AND revoked_at IS NULL",
        (_h(sid),)).fetchone()
    if row is None or row["expires_at"] < time.time():
        return False
    amr = json.loads(row["amr"])
    if add_amr not in amr:
        amr.append(add_amr)
    conn.execute("UPDATE id_sessions SET level=?, amr=? WHERE id=?",
                 (level, json.dumps(amr), row["id"]))
    conn.commit()
    return True


# --- TOTP-MFA (RFC 6238) — Enrollment + Step-up-Verifikation ------------------

# F7: Der TOTP-Seed ist ein DAUER-Geheimnis (2. Faktor der Netz-SSO) und darf
# nicht klartextlich in dizzi.sqlite liegen (nächtliches Backup → OneDrive).
# Spaltenformat: 'DPAPI1:' + base64(DPAPI-Blob) — TEXT-sicheres Pendant zu
# secrets_os.MAGIC. Bestand (reines Base32, kein Präfix) migriert transparent
# beim ersten Lesen + eager beim ersten id-Request (totp_seed_migrieren).
_TOTP_MAGIC = "DPAPI1:"


def _totp_schuetzen(secret: str) -> str:
    from appkit import secrets_os
    if not secrets_os.verfuegbar():
        return secret            # ehrlicher Klartext-Fallback (Nicht-Windows)
    blob = secrets_os.schuetze_wert(secret.encode("ascii"))
    return _TOTP_MAGIC + base64.b64encode(blob).decode("ascii")


def _totp_lesen(wert: str) -> str:
    """Spaltenwert → Klartext-Seed; Klartext-Bestand wird einmalig umgeschrieben."""
    from appkit import secrets_os
    if wert.startswith(_TOTP_MAGIC):
        blob = base64.b64decode(wert[len(_TOTP_MAGIC):])
        return secrets_os.entschuetze_wert(blob).decode("ascii")
    if secrets_os.verfuegbar():          # Bestands-Migration (einmalig)
        conn = _conn()
        conn.execute(
            "UPDATE id_identity SET totp_secret=?, updated_at=? WHERE user_id=?",
            (_totp_schuetzen(wert), db.now_iso(), DEFAULT_USER_ID))
        conn.commit()
    return wert


def totp_secret_klartext() -> str | None:
    """Entschlüsselter Seed (Enrollment-Anzeige/QR + Verify + Tests)."""
    row = _identity_row()
    if not row or not row["totp_secret"]:
        return None
    return _totp_lesen(row["totp_secret"])


def totp_seed_migrieren() -> None:
    """Eager-Migration eines Klartext-Alt-Seeds — deterministisch beim ersten
    id-Request nach dem Deploy, nicht erst beim nächsten Step-up."""
    row = _identity_row()
    if row and row["totp_secret"] and not row["totp_secret"].startswith(_TOTP_MAGIC):
        _totp_lesen(row["totp_secret"])


def totp_state() -> dict[str, Any]:
    row = _identity_row()
    if not row or not row["totp_secret"]:
        return {"enrolled": False, "confirmed": False}
    return {"enrolled": True, "confirmed": row["totp_confirmed_at"] is not None}


def totp_begin_enroll(secret: str) -> None:
    """Startet das Enrollment (pending bis zur ersten Verifikation).
    Ein BESTÄTIGTES Enrollment wird nie still überschrieben."""
    _ensure_identity()
    row = _identity_row()
    if row["totp_confirmed_at"] is not None:
        raise ValueError("MFA bereits aktiv")
    conn = _conn()
    conn.execute(
        "UPDATE id_identity SET totp_secret=?, totp_last_counter=0, updated_at=? WHERE user_id=?",
        (_totp_schuetzen(secret), db.now_iso(), DEFAULT_USER_ID))
    conn.commit()


def totp_verify(code: str) -> bool:
    """Prüft einen Code (Replay-sicher, MIT Lockout H4); bestätigt beim ersten
    Erfolg das Enrollment. True = akzeptiert."""
    from . import totp as totp_mod
    if lockout_rest("totp") > 0:
        return False
    row = _identity_row()
    if not row or not row["totp_secret"]:
        return False
    counter = totp_mod.verify(_totp_lesen(row["totp_secret"]), code,
                              row["totp_last_counter"])
    if counter is None:
        _lockout_fehlversuch("totp")
        return False
    _lockout_reset("totp")
    conn = _conn()
    conn.execute(
        """UPDATE id_identity SET totp_last_counter=?,
                  totp_confirmed_at=COALESCE(totp_confirmed_at, ?), updated_at=?
           WHERE user_id=?""",
        (counter, db.now_iso(), db.now_iso(), DEFAULT_USER_ID))
    conn.commit()
    return True


# --- R1.3b: WebAuthn/Passkey — Challenges + Credentials ----------------------
WEBAUTHN_CHAL_TTL_S = 300


def webauthn_set_challenge(zweck: str, challenge_b64: str) -> None:
    """Hinterlegt die EINE laufende Challenge je Zweck (register|assert).
    Eine neue überschreibt die alte ⇒ höchstens eine offene Ceremony."""
    conn = _conn()
    conn.execute(
        """INSERT INTO id_webauthn_chal (id, user_id, zweck, challenge, expires_at, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (user_id, zweck) DO UPDATE SET
             challenge=excluded.challenge, expires_at=excluded.expires_at,
             created_at=excluded.created_at""",
        (db.new_id(), DEFAULT_USER_ID, zweck, challenge_b64,
         time.time() + WEBAUTHN_CHAL_TTL_S, db.now_iso()))
    conn.commit()


def webauthn_take_challenge(zweck: str) -> str | None:
    """Liest die Challenge und LÖSCHT sie (single-use). None = keine/abgelaufen."""
    conn = _conn()
    row = conn.execute(
        "SELECT challenge, expires_at FROM id_webauthn_chal WHERE user_id=? AND zweck=?",
        (DEFAULT_USER_ID, zweck)).fetchone()
    conn.execute("DELETE FROM id_webauthn_chal WHERE user_id=? AND zweck=?",
                 (DEFAULT_USER_ID, zweck))
    conn.commit()
    if row is None or row["expires_at"] < time.time():
        return None
    return row["challenge"]


def webauthn_add_credential(cred_id: str, public_key: str, alg: int,
                            sign_count: int, aaguid: str | None,
                            label: str | None) -> None:
    conn = _conn()
    ts = db.now_iso()
    conn.execute(
        """INSERT INTO id_webauthn (id, user_id, cred_id, public_key, alg,
                                    sign_count, aaguid, label, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (db.new_id(), DEFAULT_USER_ID, cred_id, public_key, alg, sign_count,
         aaguid, label or "Passkey", ts))
    conn.commit()


def webauthn_credentials(include_secret: bool = False) -> list[dict[str, Any]]:
    """Aktive Credentials. Ohne ``include_secret`` ohne den Public-Key-Blob
    (für die Geräte-Liste; der Key ist kein Geheimnis, aber gehört nicht in
    die UI)."""
    rows = _conn().execute(
        "SELECT * FROM id_webauthn WHERE user_id=? AND deleted_at IS NULL "
        "ORDER BY created_at", (DEFAULT_USER_ID,)).fetchall()
    out = []
    for r in rows:
        d = {"id": r["id"], "cred_id": r["cred_id"], "alg": r["alg"],
             "label": r["label"], "sign_count": r["sign_count"],
             "created_at": r["created_at"], "last_used_at": r["last_used_at"]}
        if include_secret:
            d["public_key"] = r["public_key"]
        out.append(d)
    return out


def webauthn_get(cred_id: str) -> dict[str, Any] | None:
    r = _conn().execute(
        "SELECT * FROM id_webauthn WHERE user_id=? AND cred_id=? AND deleted_at IS NULL",
        (DEFAULT_USER_ID, cred_id)).fetchone()
    return dict(r) if r else None


def webauthn_update_sign_count(cred_id: str, sign_count: int) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE id_webauthn SET sign_count=?, last_used_at=? WHERE user_id=? AND cred_id=?",
        (sign_count, db.now_iso(), DEFAULT_USER_ID, cred_id))
    conn.commit()


def webauthn_delete(db_id: str) -> bool:
    conn = _conn()
    cur = conn.execute(
        "UPDATE id_webauthn SET deleted_at=? WHERE user_id=? AND id=? AND deleted_at IS NULL",
        (db.now_iso(), DEFAULT_USER_ID, db_id))
    conn.commit()
    return cur.rowcount > 0


def webauthn_state() -> dict[str, Any]:
    n = _conn().execute(
        "SELECT COUNT(*) AS n FROM id_webauthn WHERE user_id=? AND deleted_at IS NULL",
        (DEFAULT_USER_ID,)).fetchone()["n"]
    return {"enrolled": n > 0, "anzahl": n}


def pin_google(sub: str, email: str) -> bool:
    """Pinnt das Google-Konto beim ersten Login; danach muss jede Anmeldung
    dieselbe ``sub`` liefern. False = fremdes Konto (abgelehnt)."""
    _ensure_identity()
    row = _identity_row()
    if row["google_sub"] is None:
        conn = _conn()
        conn.execute(
            "UPDATE id_identity SET google_sub=?, google_email=?, updated_at=? WHERE user_id=?",
            (sub, email, db.now_iso(), DEFAULT_USER_ID))
        conn.commit()
        return True
    return hmac.compare_digest(row["google_sub"], sub)
