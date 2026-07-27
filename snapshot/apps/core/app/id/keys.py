"""Schlüsselverwaltung von Dizzi-ID — Ed25519 (EdDSA), joserfc.

Das Schlüsselpaar entsteht beim ersten Start und liegt als privates JWK unter
``C:\\Dizzik\\data\\id\\idp_key.json`` (außerhalb Repo/OneDrive). Apps
verifizieren über das öffentliche JWKS (``/id/jwks.json``) — der private
Schlüssel verlässt den Core nie; Apps können Tokens nur PRÜFEN, nie ausstellen.

Verifier-Regel (Recherche 12.06.): Algorithmus wird GEPINNT, niemals aus dem
Token-Header übernommen. Identifier = **„Ed25519"** (vollspezifiziert nach
RFC 9864; das polymorphe „EdDSA" ist dort deprecated — joserfc warnt aktiv).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from joserfc import jwt
from joserfc.jwk import OKPKey

from ..config import settings

_key_cache: OKPKey | None = None

ALG = "Ed25519"


def _key_path() -> Path:
    return settings.data_dir / "id" / "idp_key.json"


def get_key() -> OKPKey:
    """Lädt das private JWK; erzeugt es beim allerersten Start (kid stabil).
    H2: Datei liegt DPAPI-geschützt (appkit/secrets_os) — ans Windows-Konto
    gebunden; Klartext-Bestand migriert transparent beim ersten Laden."""
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    from appkit import secrets_os
    path = _key_path()
    roh = secrets_os.lese_geheim(path)
    if roh is not None:
        _key_cache = OKPKey.import_key(json.loads(roh.decode("utf-8")))
    else:
        key = OKPKey.generate_key("Ed25519", {"alg": ALG, "use": "sig"})  # crv=alg=Ed25519
        data = key.as_dict(private=True)
        data["kid"] = key.thumbprint()
        _key_cache = OKPKey.import_key(data)
        secrets_os.schreibe_geheim(
            path, json.dumps(data, indent=1).encode("utf-8"))
    return _key_cache


def reset_key_cache() -> None:
    """Für Tests (frischer data_dir ⇒ frischer Schlüssel)."""
    global _key_cache
    _key_cache = None


def jwks() -> dict[str, Any]:
    """Öffentliches JWKS für die Relying Parties."""
    pub = get_key().as_dict(private=False)
    return {"keys": [pub]}


def sign(claims: dict[str, Any]) -> str:
    key = get_key()
    return jwt.encode({"alg": ALG, "kid": key.kid}, claims, key, algorithms=[ALG])


def verify(token: str) -> dict[str, Any]:
    """Prüft Signatur (Alg GEPINNT auf Ed25519) und liefert die Claims.
    Zeitliche/inhaltliche Prüfung (exp/iss/aud) macht der Aufrufer kontextgenau."""
    decoded = jwt.decode(token, get_key(), algorithms=[ALG])
    return dict(decoded.claims)
