"""KA-H1/A2 — der HTTP-Endpoint ``POST /api/account/loeschen`` + sein Re-Auth-Gate
(Option A: lokales Passwort ODER frischer TOTP-Code IM REQUEST).

Die Lösch-ENGINE selbst (Kaskade / harte Räumung / RAG-Purge / Löschbeleg) prüft
``test_loesch_invariante``. HIER geht es NUR um das Gate:
  * fail-closed ohne Credential und bei falschem Passwort — es wird NICHTS gelöscht,
  * Erfolg über BEIDE Pfade (Passwort und TOTP), Engine läuft, SSO-Cookie wird geräumt,
  * der H4-Lockout sticht auch bei korrektem Passwort (Sperre vor Prüfung).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.config import DEFAULT_USER_ID
from app.id import store, totp
from app.main import app

client = TestClient(app)

_PW = "loeschen-123"  # ≥ 8 Zeichen (Mindestlänge von set_local_password)


def _seed_konto() -> str:
    """Identität + Passwort + eine aktive Session anlegen; sid der Session zurück."""
    store.set_local_password(_PW)                 # legt zugleich id_identity an
    return store.create_session("verifiziert", ["pwd"])


def _identitaet_da() -> bool:
    return store._identity_row() is not None


def test_ohne_credential_403_nichts_geloescht():
    sid = _seed_konto()
    r = client.post("/api/account/loeschen", json={})
    assert r.status_code == 403
    assert _identitaet_da()                       # Identität unangetastet
    assert store.get_session(sid) is not None     # Session lebt weiter


def test_falsches_passwort_403_nichts_geloescht():
    sid = _seed_konto()
    r = client.post("/api/account/loeschen", json={"passwort": "ganz-falsch"})
    assert r.status_code == 403
    assert _identitaet_da()
    assert store.get_session(sid) is not None


def test_korrektes_passwort_loescht_und_raeumt_cookie():
    sid = _seed_konto()
    r = client.post("/api/account/loeschen", json={"passwort": _PW})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Engine lief: Identität + Session sind hart weg.
    assert not _identitaet_da()
    assert store.get_session(sid) is None
    # SSO-Cookie-Löschung liegt im Response (Client-Hygiene).
    assert "dizzi_id_session" in r.headers.get("set-cookie", "")
    # Löschbeleg im behaltenen audit_log.
    assert "daten_geloescht" in [e["action"] for e in db.audit_recent(DEFAULT_USER_ID)]


def test_totp_pfad_loescht():
    secret = totp.new_secret()
    store.totp_begin_enroll(secret)               # legt id_identity + Seed (pending) an
    r = client.post("/api/account/loeschen", json={"totp": totp.code_now(secret)})
    assert r.status_code == 200
    assert not _identitaet_da()


def test_lockout_sticht_trotz_korrektem_passwort():
    _seed_konto()
    # H4-Sperre erzwingen, ohne die Schwelle hart zu kodieren.
    for _ in range(store.LOCKOUT_SCHWELLE + 1):
        store._lockout_fehlversuch("passwort")
    assert store.lockout_rest("passwort") > 0
    r = client.post("/api/account/loeschen", json={"passwort": _PW})
    assert r.status_code == 403
    assert _identitaet_da()                        # nichts gelöscht trotz korrektem PW
