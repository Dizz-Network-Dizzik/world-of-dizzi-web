"""WebAuthn/Passkey-Verifier (R1.3b) — eigener schlanker Kern (F-Q1).

Die kryptografische Substanz (ECDSA P-256, Ed25519, SHA-256) kommt aus der
geprüften ``cryptography``-Bibliothek; alles WebAuthn-Spezifische (CBOR des
COSE-Schlüssels, authenticatorData-Layout, Ceremony-Prüfungen nach W3C
WebAuthn Level 2) ist hier **klein und auditierbar** umgesetzt — keine
zusätzliche Abhängigkeit, passend zum Sicherheits-Anspruch des Produkts.

Bewusste Vereinfachung (ehrlich, docs/18): **Attestation wird NICHT geprüft.**
Single-User, lokal — wir vertrauen dem EIGENEN Gerät des Nutzers; der Beweis,
welches Authenticator-Modell verwendet wird, ist hier ohne Nutzen und würde
nur Komplexität (Hersteller-Zertifikatsketten) bringen. Verifiziert werden:
Challenge-Bindung, Origin, RP-ID-Hash, User-Presence und — bei der Anmeldung —
die **Assertion-Signatur** über den frischen Daten plus der Klon-Schutz
(sign_count-Regression). Das ist der sicherheitsrelevante Kern.

Unterstützte Algorithmen (COSE ``alg``): **-7 (ES256)** und **-8 (EdDSA/
Ed25519)** — die beiden, die Plattform-Authenticatoren (Windows Hello, Touch
ID) und FIDO2-Keys praktisch immer anbieten.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

COSE_ES256 = -7
COSE_EDDSA = -8
SUPPORTED_ALGS = (COSE_ES256, COSE_EDDSA)


class WebAuthnError(ValueError):
    """Ceremony-Verstoß (Challenge/Origin/Signatur/Flags). Bewusst eine
    knappe Meldung — kein Orakel über den genauen Fehlgrund nach außen."""


# --------------------------------------------------------------- base64url
def b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# ------------------------------------------------------------- Mini-CBOR
# Nur die für COSE-Keys + attestationObject nötigen Major-Typen (0–5).
# Kanonisch genug für unseren Zweck; unbekannte Typen ⇒ Fehler statt Raten.
def _cbor(data: bytes, i: int) -> tuple[Any, int]:
    first = data[i]
    mt, ai = first >> 5, first & 0x1F
    i += 1
    if ai < 24:
        val = ai
    elif ai == 24:
        val = data[i]; i += 1
    elif ai == 25:
        val = int.from_bytes(data[i:i + 2], "big"); i += 2
    elif ai == 26:
        val = int.from_bytes(data[i:i + 4], "big"); i += 4
    elif ai == 27:
        val = int.from_bytes(data[i:i + 8], "big"); i += 8
    else:
        raise WebAuthnError("CBOR: nicht unterstützte Länge")
    if mt == 0:                      # unsigned int
        return val, i
    if mt == 1:                      # negative int
        return -1 - val, i
    if mt == 2:                      # byte string
        return data[i:i + val], i + val
    if mt == 3:                      # text string
        return data[i:i + val].decode("utf-8"), i + val
    if mt == 4:                      # array
        out = []
        for _ in range(val):
            v, i = _cbor(data, i)
            out.append(v)
        return out, i
    if mt == 5:                      # map
        out = {}
        for _ in range(val):
            k, i = _cbor(data, i)
            v, i = _cbor(data, i)
            out[k] = v
        return out, i
    raise WebAuthnError("CBOR: nicht unterstützter Typ")


def cbor_decode(data: bytes) -> Any:
    val, _ = _cbor(data, 0)
    return val


# --------------------------------------------------- authenticatorData
@dataclass
class AuthData:
    rpid_hash: bytes
    up: bool                 # User Present
    uv: bool                 # User Verified
    sign_count: int
    aaguid: bytes | None = None
    cred_id: bytes | None = None
    cose_key: dict | None = None


def parse_auth_data(raw: bytes) -> AuthData:
    if len(raw) < 37:
        raise WebAuthnError("authData zu kurz")
    rpid_hash = raw[:32]
    flags = raw[32]
    sign_count = int.from_bytes(raw[33:37], "big")
    ad = AuthData(rpid_hash=rpid_hash, up=bool(flags & 0x01),
                  uv=bool(flags & 0x04), sign_count=sign_count)
    if flags & 0x40:                 # AT — attested credential data present
        aaguid = raw[37:53]
        cred_len = int.from_bytes(raw[53:55], "big")
        cred_id = raw[55:55 + cred_len]
        cose, _ = _cbor(raw, 55 + cred_len)   # COSE-Key direkt aus dem Rest
        ad.aaguid, ad.cred_id, ad.cose_key = aaguid, cred_id, cose
    return ad


# ----------------------------------------------------- COSE → Pubkey
def cose_alg(cose_key: dict) -> int:
    return int(cose_key.get(3))      # COSE-Label 3 = alg


def _public_key_from_cose(cose: dict):
    kty = cose.get(1)                # 2=EC2, 1=OKP
    alg = cose.get(3)
    if kty == 2 and alg == COSE_ES256:
        x = int.from_bytes(cose[-2], "big")
        y = int.from_bytes(cose[-3], "big")
        return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    if kty == 1 and alg == COSE_EDDSA:
        return ed25519.Ed25519PublicKey.from_public_bytes(cose[-2])  # OKP x
    raise WebAuthnError("Nicht unterstützter Schlüsseltyp/Algorithmus")


def cose_key_blob(cose: dict) -> str:
    """COSE-Key kompakt + transportfähig speichern (nur die nötigen Labels)."""
    alg = cose.get(3)
    if cose.get(1) == 2 and alg == COSE_ES256:
        return json.dumps({"alg": alg, "x": cose[-2].hex(), "y": cose[-3].hex()})
    if cose.get(1) == 1 and alg == COSE_EDDSA:
        return json.dumps({"alg": alg, "x": cose[-2].hex()})
    raise WebAuthnError("Nicht unterstützter Schlüsseltyp/Algorithmus")


def _public_key_from_blob(blob: str):
    d = json.loads(blob)
    if d["alg"] == COSE_ES256:
        x = int.from_bytes(bytes.fromhex(d["x"]), "big")
        y = int.from_bytes(bytes.fromhex(d["y"]), "big")
        return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    if d["alg"] == COSE_EDDSA:
        return ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(d["x"]))
    raise WebAuthnError("Nicht unterstützter Algorithmus im Blob")


# ----------------------------------------------------- Ceremony-Prüfungen
def _client_data(client_data_json: bytes, erwartet_typ: str,
                 challenge_b64: str, origins: set[str]) -> None:
    cd = json.loads(client_data_json.decode("utf-8"))
    if cd.get("type") != erwartet_typ:
        raise WebAuthnError("clientData: falscher type")
    if cd.get("challenge") != challenge_b64:
        raise WebAuthnError("clientData: Challenge stimmt nicht (Replay?)")
    if cd.get("origin") not in origins:
        raise WebAuthnError(f"clientData: fremder Origin {cd.get('origin')!r}")


def register_verify(client_data_json: bytes, attestation_object: bytes, *,
                    challenge_b64: str, origins: set[str], rp_id: str) -> dict[str, Any]:
    """Registrierung prüfen ⇒ Credential-Daten zum Speichern.
    (Attestation-Statement bewusst ignoriert — s. Modul-Docstring.)"""
    _client_data(client_data_json, "webauthn.create", challenge_b64, origins)
    att = cbor_decode(attestation_object)
    ad = parse_auth_data(att["authData"])
    if ad.rpid_hash != hashlib.sha256(rp_id.encode()).digest():
        raise WebAuthnError("RP-ID-Hash passt nicht")
    if not ad.up:
        raise WebAuthnError("User Presence fehlt")
    if ad.cred_id is None or ad.cose_key is None:
        raise WebAuthnError("Keine Credential-Daten in authData")
    if cose_alg(ad.cose_key) not in SUPPORTED_ALGS:
        raise WebAuthnError("Authenticator bietet keinen unterstützten Algorithmus")
    return {
        "cred_id": b64url_encode(ad.cred_id),
        "public_key": cose_key_blob(ad.cose_key),
        "alg": cose_alg(ad.cose_key),
        "sign_count": ad.sign_count,
        "aaguid": ad.aaguid.hex() if ad.aaguid else None,
        "uv": ad.uv,
    }


def assertion_verify(client_data_json: bytes, authenticator_data: bytes,
                     signature: bytes, *, public_key_blob: str,
                     challenge_b64: str, origins: set[str], rp_id: str,
                     stored_sign_count: int, verlange_uv: bool = False) -> int:
    """Anmeldung prüfen: Origin/Challenge/RP-ID/UP + SIGNATUR + Klon-Schutz.
    Liefert den neuen sign_count (zum Persistieren) oder wirft.

    ``verlange_uv=True`` (Hochsicher-Step-up, M-1): erzwingt zusätzlich
    **User Verification** (``ad.uv`` — Biometrie/PIN wurde geleistet, nicht nur
    ein Tap). Der Aufrufer muss dann in den Assertion-Options ebenfalls
    ``userVerification:"required"`` senden, damit der Authenticator UV auch
    ausführt. Default False lässt normale Zeremonien unverändert (nur UP)."""
    _client_data(client_data_json, "webauthn.get", challenge_b64, origins)
    ad = parse_auth_data(authenticator_data)
    if ad.rpid_hash != hashlib.sha256(rp_id.encode()).digest():
        raise WebAuthnError("RP-ID-Hash passt nicht")
    if not ad.up:
        raise WebAuthnError("User Presence fehlt")
    if verlange_uv and not ad.uv:
        raise WebAuthnError("User Verification erforderlich (Hochsicher-Step-up)")
    # Signatur über authenticatorData || SHA-256(clientDataJSON)
    signed = authenticator_data + hashlib.sha256(client_data_json).digest()
    key = _public_key_from_blob(public_key_blob)
    try:
        if isinstance(key, ed25519.Ed25519PublicKey):
            key.verify(signature, signed)
        else:                        # ES256: DER-Signatur, SHA-256
            key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise WebAuthnError("Signatur ungültig")
    # Klon-Schutz (W3C §7.2 Schritt 21): sign_count darf nicht zurücklaufen.
    # Authenticatoren ohne Zähler melden konstant 0 ⇒ dann keine Prüfung.
    if ad.sign_count != 0 or stored_sign_count != 0:
        if ad.sign_count <= stored_sign_count:
            raise WebAuthnError("sign_count-Regression — möglicher Klon")
    return ad.sign_count
