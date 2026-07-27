"""Tests R1.3b: WebAuthn/Passkey — Verifier (CBOR/COSE/Signatur) + Routen.

Echte Authenticator-Hardware gibt es im Test nicht ⇒ ein **Software-
Authenticator** (cryptography) erzeugt gültige Registrierungs-/Assertion-
Daten. Die echte Geräte-Ceremony (Windows Hello o. ä.) läuft live mit dem
Nutzer; hier wird die Krypto-/Protokoll-Logik deterministisch geprüft."""

from __future__ import annotations

import hashlib
import json
import struct

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.id import ISSUER, store, webauthn
from app.main import app

ORIGIN = "http://testserver"     # TestClient-Host ⇒ _origin_rpid leitet das ab
RP_ID = "testserver"


# --------------------------------------------------- Mini-CBOR-Encoder (Test)
def _cbor_enc(val) -> bytes:
    if isinstance(val, bool):  # vor int!
        raise TypeError("bool nicht unterstützt")
    if isinstance(val, int):
        mt, v = (0, val) if val >= 0 else (1, -1 - val)
        return _head(mt, v)
    if isinstance(val, bytes):
        return _head(2, len(val)) + val
    if isinstance(val, str):
        b = val.encode(); return _head(3, len(b)) + b
    if isinstance(val, list):
        out = _head(4, len(val))
        for x in val:
            out += _cbor_enc(x)
        return out
    if isinstance(val, dict):
        out = _head(5, len(val))
        for k, x in val.items():
            out += _cbor_enc(k) + _cbor_enc(x)
        return out
    raise TypeError(type(val))


def _head(mt: int, v: int) -> bytes:
    if v < 24:
        return bytes([mt << 5 | v])
    if v < 256:
        return bytes([mt << 5 | 24, v])
    if v < 65536:
        return bytes([mt << 5 | 25]) + v.to_bytes(2, "big")
    return bytes([mt << 5 | 26]) + v.to_bytes(4, "big")


class SoftAuthenticator:
    """Ein ES256-Software-Passkey für die Tests."""

    def __init__(self, rp_id: str = RP_ID, sign_count: int = 0):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = b"cred-" + hashlib.sha256(
            self.key.private_numbers().private_value.to_bytes(32, "big")).digest()[:11]
        self.rp_id_hash = hashlib.sha256(rp_id.encode()).digest()
        self.sign_count = sign_count

    def _cose(self) -> dict:
        nums = self.key.public_key().public_numbers()
        return {1: 2, 3: -7, -1: 1,
                -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}

    def attestation_object(self) -> bytes:
        auth = (self.rp_id_hash + bytes([0x41])             # UP + AT
                + struct.pack(">I", self.sign_count)
                + b"\x00" * 16                              # aaguid
                + struct.pack(">H", len(self.cred_id)) + self.cred_id
                + _cbor_enc(self._cose()))
        return _cbor_enc({"fmt": "none", "attStmt": {}, "authData": auth})

    def assertion(self, client_data_json: bytes, sign_count: int | None = None,
                  uv: bool = True):
        sc = self.sign_count if sign_count is None else sign_count
        # Echter Plattform-Authenticator (Windows Hello) leistet User Verification
        # ⇒ UV-Flag (0x04) neben UP (0x01). Hochsicher-Step-up verlangt UV (M-1);
        # uv=False bildet einen reinen UP-Authenticator ab (dann Ablehnung erwartet).
        flags = 0x01 | (0x04 if uv else 0x00)
        auth = self.rp_id_hash + bytes([flags]) + struct.pack(">I", sc)
        sig = self.key.sign(auth + hashlib.sha256(client_data_json).digest(),
                            ec.ECDSA(hashes.SHA256()))
        return auth, sig


def _client_data(typ: str, challenge_b64: str, origin: str = ORIGIN) -> bytes:
    return json.dumps({"type": typ, "challenge": challenge_b64,
                       "origin": origin}).encode()


# ------------------------------------------------------------- Verifier-Unit
def test_register_und_assertion_roundtrip():
    auth = SoftAuthenticator()
    chal = webauthn.b64url_encode(b"challenge-123456789012345678901234")
    cd = _client_data("webauthn.create", chal)
    cred = webauthn.register_verify(cd, auth.attestation_object(),
                                    challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID)
    assert cred["alg"] == -7
    assert cred["cred_id"] == webauthn.b64url_encode(auth.cred_id)

    auth.sign_count = 5
    chal2 = webauthn.b64url_encode(b"assert-challenge-0123456789012345")
    cd2 = _client_data("webauthn.get", chal2)
    ad, sig = auth.assertion(cd2)
    neu = webauthn.assertion_verify(cd2, ad, sig, public_key_blob=cred["public_key"],
                                    challenge_b64=chal2, origins={ORIGIN},
                                    rp_id=RP_ID, stored_sign_count=0)
    assert neu == 5


def test_falsche_challenge_und_origin_und_signatur():
    auth = SoftAuthenticator()
    chal = webauthn.b64url_encode(b"x" * 24)
    cred = webauthn.register_verify(
        _client_data("webauthn.create", chal), auth.attestation_object(),
        challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID)
    cd = _client_data("webauthn.get", chal)
    ad, sig = auth.assertion(cd)
    # falscher Origin
    with pytest.raises(webauthn.WebAuthnError):
        webauthn.assertion_verify(cd, ad, sig, public_key_blob=cred["public_key"],
                                  challenge_b64=chal, origins={"http://evil"},
                                  rp_id=RP_ID, stored_sign_count=0)
    # manipulierte Signatur
    with pytest.raises(webauthn.WebAuthnError):
        webauthn.assertion_verify(cd, ad, sig[:-1] + bytes([sig[-1] ^ 1]),
                                  public_key_blob=cred["public_key"],
                                  challenge_b64=chal, origins={ORIGIN},
                                  rp_id=RP_ID, stored_sign_count=0)


def test_sign_count_regression_blockt_klon():
    auth = SoftAuthenticator()
    chal = webauthn.b64url_encode(b"y" * 24)
    cred = webauthn.register_verify(
        _client_data("webauthn.create", chal), auth.attestation_object(),
        challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID)
    cd = _client_data("webauthn.get", chal)
    ad, sig = auth.assertion(cd, sign_count=3)
    with pytest.raises(webauthn.WebAuthnError):   # 3 <= stored 5 ⇒ Klon
        webauthn.assertion_verify(cd, ad, sig, public_key_blob=cred["public_key"],
                                  challenge_b64=chal, origins={ORIGIN},
                                  rp_id=RP_ID, stored_sign_count=5)


def test_stepup_verlangt_user_verification():
    """M-1: verlange_uv=True (Hochsicher-Step-up) lehnt einen reinen UP-Authenticator
    (uv=False) ab; ohne Flag bleibt die normale Zeremonie unberührt; mit UV geht es durch."""
    auth = SoftAuthenticator()
    chal = webauthn.b64url_encode(b"z" * 24)
    cred = webauthn.register_verify(
        _client_data("webauthn.create", chal), auth.attestation_object(),
        challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID)
    cd = _client_data("webauthn.get", chal)
    ad0, sig0 = auth.assertion(cd, uv=False)        # nur User Presence
    with pytest.raises(webauthn.WebAuthnError):     # Step-up MUSS UV verlangen
        webauthn.assertion_verify(cd, ad0, sig0, public_key_blob=cred["public_key"],
                                  challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID,
                                  stored_sign_count=0, verlange_uv=True)
    # Normale Zeremonie (ohne verlange_uv) akzeptiert denselben UP-Authenticator.
    assert webauthn.assertion_verify(cd, ad0, sig0, public_key_blob=cred["public_key"],
                                     challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID,
                                     stored_sign_count=0) == 0
    # Mit echter User Verification geht der Step-up durch.
    ad1, sig1 = auth.assertion(cd, uv=True, sign_count=1)
    assert webauthn.assertion_verify(cd, ad1, sig1, public_key_blob=cred["public_key"],
                                     challenge_b64=chal, origins={ORIGIN}, rp_id=RP_ID,
                                     stored_sign_count=0, verlange_uv=True) == 1


# --------------------------------------------------------------- Routen-E2E
@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/id/local/setup", data={"password": "geheim-passwort", "next": ""},
               follow_redirects=False)            # ⇒ verifiziert-Session-Cookie
        yield c


def _take(client, zweck: str) -> str:
    """Holt die im Begin gesetzte Challenge ohne sie zu verbrauchen (Test)."""
    row = store._conn().execute(
        "SELECT challenge FROM id_webauthn_chal WHERE zweck=?", (zweck,)).fetchone()
    return row["challenge"]


def test_route_register_und_stepup_hochsicher(client):
    auth = SoftAuthenticator()
    # Registrieren
    assert client.post("/id/webauthn/register/begin").json()["rp"]["id"] == RP_ID
    chal = _take(client, "register")
    cd = _client_data("webauthn.create", chal)
    r = client.post("/id/webauthn/register/finish", json={
        "id": webauthn.b64url_encode(auth.cred_id), "label": "Test-Key",
        "response": {"clientDataJSON": webauthn.b64url_encode(cd),
                     "attestationObject": webauthn.b64url_encode(auth.attestation_object())}})
    assert r.json() == {"ok": True, "label": "Test-Key"}
    assert client.get("/id/status").json()["passkey"] == {"enrolled": True, "anzahl": 1}

    # Step-up auf hochsicher per Passkey
    auth.sign_count = 1
    client.post("/id/webauthn/stepup/begin")
    chal2 = _take(client, "assert")
    cd2 = _client_data("webauthn.get", chal2)
    ad, sig = auth.assertion(cd2)
    r = client.post("/id/webauthn/stepup/finish", json={
        "id": webauthn.b64url_encode(auth.cred_id),
        "response": {"clientDataJSON": webauthn.b64url_encode(cd2),
                     "authenticatorData": webauthn.b64url_encode(ad),
                     "signature": webauthn.b64url_encode(sig)}})
    assert r.json() == {"ok": True, "level": "hochsicher"}
    assert client.get("/id/status").json()["level"] == "hochsicher"


def test_route_register_braucht_session():
    with TestClient(app) as anon:
        assert anon.post("/id/webauthn/register/begin").status_code == 401


def test_route_stepup_ohne_passkey_400(client):
    assert client.post("/id/webauthn/stepup/begin").status_code == 400
