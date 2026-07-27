"""KA-H1 (DSGVO Art. 17) für Dizzi-Core — die Lösch-ENGINE (konto_loeschung).

Der Core hatte GAR KEINEN Lösch-Pfad (der „größere" KA-H1-Befund): Identität, Sessions,
Chat, Memory, Observations, RAG und agent_laeufe überlebten eine Konto-Löschung.
``loesche_konto()`` ist die Engine (Kaskade + harte Räumung + RAG-Purge).

STATIK: keine user_id-Tabelle der Haupt-DB ohne Deckung (deleted_at ODER Hart-Hook ODER
Ausnahme). DYNAMIK: nach ``loesche_konto()`` sind Identität/Sessions/Codes/Refresh/Lockout/
WebAuthn-Challenge/agent_laeufe + RAG des Nutzers wirklich weg, die Kaskade-Tabellen sind
soft-gelöscht, und ``id_clients`` (Netz-App-Registrierungen) + ``audit_log`` überleben.

Der HTTP-Endpoint + sein Re-Auth-Gate (Option A) werden separat geprüft:
``tests/test_loesch_endpoint.py``. Diese Datei bleibt bewusst engine-nah (GPU-/HTTP-frei)."""
from __future__ import annotations

from app import db
from app import konto_loeschung as kl
from app.ai import agenten_laeufe, rag
from app.config import DEFAULT_USER_ID
from app.id import store
from appkit import loesch_pruefung as lp

# audit_log = Löschbeleg; id_clients = Netz-App-Registrierungen (kein Nutzerdatum).
AUSNAHMEN = frozenset({"audit_log", "id_clients"})


def _alle_schemata():
    """Alle lazily angelegten user_id-Tabellen materialisieren, damit die Statik das
    VOLLE Schema sieht: Haupt-DB (_SCHEMA + defense), id_* (Store), agent_laeufe."""
    db.get_conn()
    store._conn()
    agenten_laeufe._ensure_schema()


def test_loesch_invariante_statisch():
    _alle_schemata()
    offen = lp.user_tabellen_ohne_deckung(
        db.get_conn(), hook_tabellen=frozenset(kl.HART_TABELLEN),
        ausnahmen=AUSNAHMEN)
    assert offen == []


def test_loesche_konto_raeumt_identitaet_rag_und_agenten():
    _alle_schemata()
    conn = db.get_conn()
    u = DEFAULT_USER_ID
    ts = db.now_iso()

    # Kaskade-Tabellen (deleted_at): je 1 Zeile.
    conn.execute("INSERT INTO chat_messages (id,user_id,role,content,created_at) "
                 "VALUES (?,?,?,?,?)", (db.new_id(), u, "user", "geheim", ts))
    conn.execute("INSERT INTO memory_facts (id,user_id,fact,source,created_at,"
                 "updated_at) VALUES (?,?,?,?,?,?)",
                 (db.new_id(), u, "vertraulich", "explizit", ts, ts))
    conn.commit()

    # Hart-Tabellen über die ECHTEN Store-Wege (id_* mit DEFAULT_USER_ID).
    store.create_session("verifiziert", ["pwd"])                 # id_sessions
    store.issue_refresh("core", "verifiziert", ["pwd"])          # id_refresh
    store._ensure_identity()                                     # id_identity
    store.issue_code("core", "http://127.0.0.1/x", "chal", None, "verifiziert", ["pwd"])  # id_codes
    store._lockout_fehlversuch("passwort")                       # id_lockout
    store.webauthn_set_challenge("register", "chalb64")          # id_webauthn_chal
    store.ensure_clients()                                       # id_clients (müssen ÜBERLEBEN)
    conn.execute("INSERT INTO agent_laeufe (id,user_id,agent_id,definition,status,"
                 "started_at) VALUES (?,?,?,?,?,?)",
                 (db.new_id(), u, "a1", "{}", "laeuft", ts))
    conn.commit()

    # RAG: doc + chunk + Vektor (rowid == rag_chunks.id, wie index_folder).
    rconn = rag.get_conn()
    rconn.execute("INSERT INTO rag_docs (id,user_id,path,mtime,chunks,created_at,"
                  "updated_at) VALUES (?,?,?,?,?,?,?)",
                  ("d1", u, "/x.md", 1.0, 1, ts, ts))
    cur = rconn.execute("INSERT INTO rag_chunks (doc_id,user_id,ord,text,created_at) "
                        "VALUES (?,?,?,?,?)", ("d1", u, 0, "wissen", ts))
    rconn.execute("INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                  (cur.lastrowid, rag._vec_blob([0.0] * rag.EMBED_DIM)))
    rconn.commit()

    # Vorher: Hart-Tabellen + RAG geseedet.
    assert all(v >= 1 for v in
               lp.pruefe_hook_loescht(conn, u, frozenset(kl.HART_TABELLEN)).values())
    assert rconn.execute("SELECT COUNT(*) AS n FROM rag_chunks WHERE user_id=?",
                         (u,)).fetchone()["n"] == 1
    clients_vorher = conn.execute(
        "SELECT COUNT(*) AS n FROM id_clients WHERE deleted_at IS NULL").fetchone()["n"]
    assert clients_vorher >= 1

    res = kl.loesche_konto(u)
    assert res["ok"] is True

    # Kaskade: chat/memory soft-gelöscht (deleted_at gesetzt).
    assert conn.execute("SELECT deleted_at FROM chat_messages").fetchone()["deleted_at"] is not None
    assert conn.execute("SELECT deleted_at FROM memory_facts").fetchone()["deleted_at"] is not None
    # Hart: alle Identitäts-/Auth-Tabellen + agent_laeufe wirklich weg.
    assert lp.pruefe_hook_loescht(conn, u, frozenset(kl.HART_TABELLEN)) == {
        t: 0 for t in kl.HART_TABELLEN}
    # RAG wirklich weg (Docs + Chunks + Vektoren).
    assert rconn.execute("SELECT COUNT(*) AS n FROM rag_docs WHERE user_id=?", (u,)).fetchone()["n"] == 0
    assert rconn.execute("SELECT COUNT(*) AS n FROM rag_chunks WHERE user_id=?", (u,)).fetchone()["n"] == 0
    assert rconn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"] == 0
    # id_clients (App-Registrierungen) UNBERÜHRT ⇒ SSO bleibt heil.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM id_clients WHERE deleted_at IS NULL"
    ).fetchone()["n"] == clients_vorher
    # Löschbeleg im (behaltenen) audit_log.
    assert "daten_geloescht" in [e["action"] for e in db.audit_recent(u)]


def test_rag_purge_fehler_wird_auditiert_nicht_geschluckt(monkeypatch):
    """Ein fehlschlagender RAG-Purge blockiert die Primärlöschung NICHT, hinterlässt
    aber einen ``rag_purge_fehlgeschlagen``-Audit-Marker (Fehler = gemeldeter, kein
    stiller Zustand — sonst könnten abgeleitete Embeddings unsichtbar überleben)."""
    _alle_schemata()
    u = DEFAULT_USER_ID
    store._ensure_identity()                      # etwas Reales zum Löschen

    def _boom(_uid):
        raise RuntimeError("rag.sqlite kaputt")
    monkeypatch.setattr(rag, "remove_user", _boom)

    res = kl.loesche_konto(u)

    # Primärlöschung bleibt erfolgreich (RAG ist nie lauf-kritisch)…
    assert res["ok"] is True
    assert store._identity_row() is None
    # …aber der Fehler ist GEMELDET, nicht geschluckt.
    actions = [e["action"] for e in db.audit_recent(u)]
    assert "rag_purge_fehlgeschlagen" in actions
    assert "daten_geloescht" in actions           # Löschbeleg trotzdem geschrieben
