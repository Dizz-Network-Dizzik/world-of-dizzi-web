"""Google-Brokering von Dizzi-ID (RFC 8252: System-Browser + Loopback + PKCE).

Dizzi-ID ist hier selbst OAuth-Client bei Google: der Nutzer meldet sich im
Browser bei Google an, Google ruft den Loopback-Callback des Core (:8200),
Dizzi-ID prüft das Google-ID-Token (RS256 gegen Googles JWKS, iss/aud/exp)
und pinnt das Konto (store.pin_google). Ab dann ist Google nur noch der
Schlüssel ZUR Dizzi-Session — Apps sehen ausschließlich Dizzi-ID-Tokens.

Live-Voraussetzung (5-Minuten-Schritt des Nutzers, docs/17 §Einrichtung):
Google-Cloud-OAuth-Client (Typ Desktop) anlegen und in C:\\Dizzik\\data\\.env
DIZZI_GOOGLE_CLIENT_ID + DIZZI_GOOGLE_CLIENT_SECRET hinterlegen.
Tests mocken ``exchange_code``/``verify_id_token`` — der Flow selbst ist
vollständig gebaut und getestet.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISS = ("https://accounts.google.com", "accounts.google.com")

# Callback-URI: HOST-KONSISTENT zum Zugriff (Dauerlösung 18.06.). Früher fest
# `localhost` — das brach den Login, sobald der Nutzer den Core auf `127.0.0.1`
# öffnete: der Flow-Cookie (`_GFLOW_COOKIE`) entsteht auf dem Zugriffs-Host, Google
# kehrt aber auf den FESTEN Host zurück ⇒ Cookie-Welt-Split ⇒ `invalid_request`.
# Jetzt wird die Callback-URI aus dem Request-Host abgeleitet (``redirect_uri_for``,
# nur Loopback) und im Flow-Cookie mitgeführt, sodass Authorize- und Token-Schritt
# IDENTISCH sind und Cookie-Host == Callback-Host gilt. Desktop-Google-Clients
# akzeptieren beide Loopback-Formen ohne Console-Registrierung (RFC 8252).
REDIRECT_URI = "http://localhost:8200/id/callback/google"   # Default/Fallback
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def redirect_uri_for(host: str | None) -> str:
    """Google-Callback host-konsistent zum aktuellen Zugriff (verhindert den
    Cookie-Welt-Split). NUR Loopback-Hosts werden akzeptiert (Schutz vor einem
    fremd-gesetzten Host-Header); sonst der Default ``REDIRECT_URI``."""
    h = (host or "").strip().lower()
    if h in _LOOPBACK:
        return f"http://{h}:8200/id/callback/google"
    return REDIRECT_URI

_jwks_cache: dict[str, Any] = {"ts": 0.0, "keys": None}


def configured() -> bool:
    return bool(os.environ.get("DIZZI_GOOGLE_CLIENT_ID")
                and os.environ.get("DIZZI_GOOGLE_CLIENT_SECRET"))


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def auth_url(state: str, challenge: str, redirect_uri: str = REDIRECT_URI) -> str:
    return GOOGLE_AUTH + "?" + urlencode({
        "client_id": os.environ.get("DIZZI_GOOGLE_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
    })


def exchange_code(code: str, verifier: str,
                  redirect_uri: str = REDIRECT_URI) -> dict[str, Any]:
    """Tauscht den Google-Code gegen Tokens. ``redirect_uri`` MUSS dieselbe sein
    wie im Authorize-Schritt (OAuth-Pflicht) — daher aus dem Flow-Cookie. In Tests gemockt."""
    r = httpx.post(GOOGLE_TOKEN, data={
        "client_id": os.environ.get("DIZZI_GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("DIZZI_GOOGLE_CLIENT_SECRET", ""),
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }, timeout=10.0)
    r.raise_for_status()
    return r.json()


def _google_keys() -> KeySet:
    now = time.time()
    if _jwks_cache["keys"] is None or now - _jwks_cache["ts"] > 3600:
        r = httpx.get(GOOGLE_JWKS, timeout=10.0)
        r.raise_for_status()
        _jwks_cache["keys"] = KeySet.import_key_set(r.json())
        _jwks_cache["ts"] = now
    return _jwks_cache["keys"]


def verify_id_token(id_token: str) -> dict[str, Any]:
    """Prüft Googles ID-Token: Signatur (RS256, Alg gepinnt), iss, aud, exp.
    Liefert die Claims (sub/email). In Tests gemockt."""
    decoded = jwt.decode(id_token, _google_keys(), algorithms=["RS256"])
    claims = dict(decoded.claims)
    if claims.get("iss") not in GOOGLE_ISS:
        raise ValueError("Google-ID-Token: falscher Aussteller")
    if claims.get("aud") != os.environ.get("DIZZI_GOOGLE_CLIENT_ID", ""):
        raise ValueError("Google-ID-Token: falsche Audience")
    if float(claims.get("exp", 0)) < time.time():
        raise ValueError("Google-ID-Token: abgelaufen")
    return claims
