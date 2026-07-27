"""Tests R1.3 (K1+): TOTP-Zweitfaktor + Step-up auf 'hochsicher'."""

from __future__ import annotations

import sys
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.id import keys, store, totp
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_keys():
    keys.reset_key_cache()
    yield
    keys.reset_key_cache()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# --- TOTP-Einheit (RFC 6238) ---------------------------------------------------

def test_totp_roundtrip_drift_und_replay():
    secret = totp.new_secret()
    t = 1_750_000_000.0
    code = totp.code_now(secret, at=t)
    counter = totp.verify(secret, code, last_counter=0, at=t)
    assert counter is not None

    # Replay desselben Codes wird abgelehnt (last_counter fortgeschrieben)
    assert totp.verify(secret, code, last_counter=counter, at=t) is None

    # ±1 Fenster Drift wird akzeptiert, ±2 nicht
    code_prev = totp.code_now(secret, at=t - totp.STEP_S)
    assert totp.verify(secret, code_prev, last_counter=0, at=t) is not None
    code_old = totp.code_now(secret, at=t - 2 * totp.STEP_S)
    assert totp.verify(secret, code_old, last_counter=0, at=t) is None

    # Müll wird abgelehnt; Leerzeichen-Eingabe normalisiert
    assert totp.verify(secret, "abc123", 0, at=t) is None
    spaced = code[:3] + " " + code[3:]
    assert totp.verify(secret, spaced, 0, at=t) is not None

    assert totp.otpauth_uri(secret).startswith("otpauth://totp/Dizzi-ID")


# --- Step-up-Flow ---------------------------------------------------------------

def _login(client: TestClient) -> None:
    client.post("/id/local/setup", data={"password": "nacht-schicht-12",
                                         "next": ""}, follow_redirects=False)


def _stepup(client: TestClient, next_url: str = "") -> None:
    """Enrollment + Verifikation mit echtem Code aus dem gespeicherten Secret."""
    r = client.get("/id/stepup?next=", follow_redirects=False)
    assert r.status_code == 200                            # Enrollment-Seite
    secret = store.totp_secret_klartext()
    assert secret
    code = totp.code_now(secret)
    r = client.post("/id/stepup", data={"code": code, "next": next_url},
                    follow_redirects=False)
    assert r.status_code == 302 and "err" not in r.headers["location"]


def test_stepup_hebt_session_auf_hochsicher(client):
    _login(client)
    assert client.get("/id/status").json()["level"] == "verifiziert"
    _stepup(client)
    s = client.get("/id/status").json()
    assert s["level"] == "hochsicher"
    assert s["mfa"] == {"enrolled": True, "confirmed": True}

    # Audit festgehalten
    audit = client.get("/api/audit?limit=50").json()
    assert any(e["action"] == "id_stepup_ok" for e in audit)


def test_authorize_erzwingt_stepup_fuer_hochsicher(client):
    import base64
    import hashlib
    import secrets as pysecrets
    _login(client)
    verifier = pysecrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    auth_url = "/id/authorize?" + urlencode({
        "client_id": "refapp", "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "response_type": "code", "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s", "nonce": "n",
        "acr_values": "hochsicher"})

    # Session nur 'verifiziert' ⇒ Umleitung zum Step-up, KEIN Code
    r = client.get(auth_url, follow_redirects=False)
    assert r.status_code == 302 and "/id/stepup" in r.headers["location"]

    _stepup(client)
    r = client.get(auth_url, follow_redirects=False)
    assert r.status_code == 302
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    tokens = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier}).json()
    claims = keys.verify(tokens["id_token"])
    assert claims["dizzi_level"] == "hochsicher"
    assert "totp" in claims["amr"] and "pwd" in claims["amr"]


def test_stepup_falscher_code_und_replay(client):
    _login(client)
    r = client.get("/id/stepup?next=", follow_redirects=False)
    assert r.status_code == 200
    r = client.post("/id/stepup", data={"code": "000000", "next": ""},
                    follow_redirects=False)
    assert "err=1" in r.headers["location"]
    assert client.get("/id/status").json()["level"] == "verifiziert"

    secret = store.totp_secret_klartext()
    code = totp.code_now(secret)
    assert client.post("/id/stepup", data={"code": code, "next": ""},
                       follow_redirects=False).status_code == 302
    # Derselbe Code nochmal (Replay) ⇒ abgelehnt
    r = client.post("/id/stepup", data={"code": code, "next": ""},
                    follow_redirects=False)
    assert "err=1" in r.headers["location"]


def test_stepup_ohne_session_geht_zum_login(client):
    r = client.get("/id/stepup?next=", follow_redirects=False)
    assert r.status_code == 302 and "/id/login" in r.headers["location"]


def test_sensitivity_mapping():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from appkit.auth import sensitivity_level
    assert sensitivity_level("normal") == "lokal"
    assert sensitivity_level("hoch") == "verifiziert"
    assert sensitivity_level("hoechst") == "hochsicher"


# --- F7: TOTP-Seed DPAPI-Spaltenschutz ----------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_totp_seed_liegt_nicht_klartext_in_der_db(client):
    """F7: nach dem Enrollment steht in der Spalte ein DPAPI-Blob, kein Base32-
    Klartext — Verify läuft trotzdem über den entschlüsselten Seed."""
    _login(client)
    client.get("/id/stepup?next=", follow_redirects=False)      # startet Enrollment
    roh = store._identity_row()["totp_secret"]
    klar = store.totp_secret_klartext()
    assert roh.startswith(store._TOTP_MAGIC) and roh != klar and klar not in roh
    r = client.post("/id/stepup", data={"code": totp.code_now(klar), "next": ""},
                    follow_redirects=False)
    assert r.status_code == 302 and "err" not in r.headers["location"]


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_totp_klartext_bestand_wird_transparent_migriert(client):
    """F7: ein vor dem Fix klartextlich gespeicherter Alt-Seed wird beim ersten
    Lesen einmalig geschützt umgeschrieben — der Seed selbst bleibt gültig."""
    _login(client)
    client.get("/id/stepup?next=", follow_redirects=False)      # legt id_identity an
    alt = totp.new_secret()
    conn = store._conn()
    conn.execute("UPDATE id_identity SET totp_secret=? WHERE user_id=?",
                 (alt, store.DEFAULT_USER_ID))                   # Vor-F7-Klartext simulieren
    conn.commit()
    assert store.totp_verify(totp.code_now(alt)) is True         # Verify migriert nebenbei
    assert store._identity_row()["totp_secret"].startswith(store._TOTP_MAGIC)
    assert store.totp_secret_klartext() == alt
