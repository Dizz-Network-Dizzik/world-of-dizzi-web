"""Dizzi-ID-Relying-Party — macht eine Vertrags-App SSO-fähig (K1-Anschluss).

``install_dizzi_id(app, manifest)`` hängt vier Routen an (/auth/login,
/auth/callback, /auth/logout, /auth/me) und installiert den Identitäts-
Provider aus ``appkit.auth``: ab dann liefert ``current_user`` die per
Dizzi-ID verifizierte Identität, und ``require_level("verifiziert")``-Routen
werden automatisch scharf — exakt der im Vertrag fixierte Austauschpunkt.

Ablauf (Authorization Code + PKCE, App = public client):
  /auth/login → 302 Dizzi-ID /id/authorize (PKCE-Verifier + state in
  Kurz-Cookies) → Nutzer meldet sich EINMAL bei Dizzi-ID an → /auth/callback
  tauscht den Code, prüft das ID-Token (EdDSA via JWKS, Alg GEPINNT, iss/aud/
  nonce/exp) und legt eine HMAC-signierte App-Session ab (Cookie).
  Standalone-Rückfall: ohne Login bleibt die App auf Stufe 'lokal' nutzbar.

Das App-Session-Geheimnis liegt in einer Datei im App-Datenverzeichnis —
bewusst NICHT in app_settings (das /api/settings-Endpoint würde es zeigen).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc import jwt as jose_jwt
from joserfc.jwk import KeySet

from . import auth
from .manifest import AppManifest

DEFAULT_ISSUER = "http://127.0.0.1:8200/id"
# H10 (docs/18 §6): Der ISSUER bleibt die OIDC-Identität (iss-Claim + server-
# seitige /token- und /jwks-Aufrufe — dort ist der Host egal, beides Loopback).
# Der BROWSER wird aber IMMER zu localhost navigiert: WebAuthn akzeptiert eine
# IP nicht als RP-ID (Passkeys nur auf localhost), und Session-Cookies sind
# host-gebunden — ein fester 127.0.0.1-Browserpfad spaltete die IdP-Session in
# zwei Welten und brach den Passkey-Step-up aus Apps (Echtgeld-Gate).
DEFAULT_NAV_ISSUER = "http://localhost:8200/id"
# Hosts, für die wir die App-Callback-URI HOST-KONSISTENT aus dem Request
# ableiten (PKCE-Cookie und Callback müssen im selben Cookie-Host leben).
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})
SESSION_TTL_S = 12 * 3600

# Test-Haken: Tests ersetzen httpx-Aufrufe durch TestClient-Aufrufe des IdP.
HttpGet = Callable[[str], Any]
HttpPost = Callable[[str, dict], Any]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class DizziIdRP:
    """Relying-Party-Zustand einer App (Schlüssel-Cache, Session-Signatur)."""

    def __init__(self, manifest: AppManifest, data_root: Path,
                 issuer: str = DEFAULT_ISSUER,
                 http_get: HttpGet | None = None,
                 http_post: HttpPost | None = None,
                 nav_issuer: str | None = None) -> None:
        self.m = manifest
        self.issuer = issuer.rstrip("/")
        # Browser-Navigation (authorize) — getrennt vom iss (s. DEFAULT_NAV_ISSUER).
        self.nav = (nav_issuer or DEFAULT_NAV_ISSUER).rstrip("/")
        self.redirect_uri = f"{manifest.url}/auth/callback"
        self.cookie = f"dizz_{manifest.id}_session"
        self._http_get = http_get or (lambda url: httpx.get(url, timeout=5.0))
        self._http_post = http_post or (lambda url, data: httpx.post(url, data=data, timeout=5.0))
        self._jwks: KeySet | None = None
        self._jwks_ts = 0.0
        self._secret = self._load_secret(data_root)

    def request_redirect_uri(self, request: Request) -> str:
        """H10: Callback-URI HOST-KONSISTENT zum aufrufenden Browser ableiten —
        das PKCE-Cookie lebt auf dem Host, über den der Nutzer die App öffnet
        (localhost ODER 127.0.0.1); der Callback muss auf DEMSELBEN Host landen,
        sonst fehlt das Cookie. Beide Varianten sind im IdP registriert.
        Unbekannte Hosts (z. B. TestClient 'testserver') ⇒ Manifest-URI."""
        host = (request.headers.get("host") or "").strip().lower()
        if host.split(":")[0] in _LOOPBACK_HOSTS:
            return f"http://{host}/auth/callback"
        return self.redirect_uri

    # --- App-Session (HMAC-signiertes Cookie) --------------------------------

    def _load_secret(self, data_root: Path) -> bytes:
        # H2: DPAPI-geschützt (secrets_os); hex-Klartext-Bestand migriert
        # transparent beim ersten Lesen.
        from . import secrets_os
        path = data_root / "apps" / self.m.id / "rp_session_secret.txt"
        roh = secrets_os.lese_geheim(path)
        if roh is not None:
            return bytes.fromhex(roh.decode("utf-8").strip())
        secret = secrets.token_bytes(32)
        secrets_os.schreibe_geheim(path, secret.hex().encode("utf-8"))
        return secret

    def _sign_session(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        mac = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return f"{_b64(raw)}.{_b64(mac)}"

    def read_session(self, token: str | None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None
        try:
            raw_b64, mac_b64 = token.split(".", 1)
            raw = _unb64(raw_b64)
            expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, _unb64(mac_b64)):
                return None
            payload = json.loads(raw)
            if float(payload.get("exp", 0)) < time.time():
                return None
            return payload
        except Exception:
            return None

    # --- ID-Token-Prüfung (JWKS, Alg GEPINNT) ---------------------------------

    def _keys(self) -> KeySet:
        if self._jwks is None or time.time() - self._jwks_ts > 3600:
            r = self._http_get(f"{self.issuer}/jwks.json")
            r.raise_for_status()
            self._jwks = KeySet.import_key_set(r.json())
            self._jwks_ts = time.time()
        return self._jwks

    def verify_id_token(self, token: str, nonce: str) -> dict[str, Any]:
        # Alg GEPINNT: Ed25519 (vollspezifiziert, RFC 9864) — nie aus dem Header.
        decoded = jose_jwt.decode(token, self._keys(), algorithms=["Ed25519"])
        c = dict(decoded.claims)
        if c.get("iss") != self.issuer:
            raise ValueError("ID-Token: falscher Aussteller")
        if c.get("aud") != self.m.id:
            raise ValueError("ID-Token: falsche Audience")
        if float(c.get("exp", 0)) < time.time():
            raise ValueError("ID-Token: abgelaufen")
        if nonce and c.get("nonce") != nonce:
            raise ValueError("ID-Token: nonce-Mismatch")
        return c


def install_dizzi_id(app: FastAPI, manifest: AppManifest, data_root: Path,
                     issuer: str = DEFAULT_ISSUER,
                     http_get: HttpGet | None = None,
                     http_post: HttpPost | None = None,
                     nav_issuer: str | None = None) -> DizziIdRP:
    """Hängt die SSO-Routen an und installiert den Identitäts-Provider."""
    rp = DizziIdRP(manifest, data_root, issuer, http_get, http_post,
                   nav_issuer=nav_issuer)
    router = APIRouter(tags=["auth"])
    pkce_cookie = f"dizz_{manifest.id}_pkce"

    @router.get("/auth/login")
    def login(request: Request, level: str = Query("")):
        """SSO starten. ``?level=hochsicher`` fordert Step-up (acr_values) an —
        z. B. vor Echtgeld-Bereichen (Dizz Trading)."""
        from urllib.parse import urlencode
        verifier = secrets.token_urlsafe(48)
        challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)
        redirect_uri = rp.request_redirect_uri(request)   # H10: host-konsistent
        params = {
            "client_id": manifest.id, "redirect_uri": redirect_uri,
            "response_type": "code", "scope": "openid",
            "code_challenge": challenge, "code_challenge_method": "S256",
            "state": state, "nonce": nonce}
        if level:
            params["acr_values"] = level
        # H10: Browser zur NAV-Basis (localhost — Passkeys!), nicht zum iss-Host.
        url = f"{rp.nav}/authorize?" + urlencode(params)
        resp = RedirectResponse(url, status_code=302)
        resp.set_cookie(pkce_cookie,
                        json.dumps({"v": verifier, "s": state, "n": nonce,
                                    "r": redirect_uri}),
                        httponly=True, samesite="lax", max_age=600, path="/auth")
        return resp

    @router.get("/auth/callback")
    def callback(request: Request, code: str = Query(""), state: str = Query(""),
                 error: str = Query("")):
        if error:
            return JSONResponse({"error": error}, status_code=400)
        raw = request.cookies.get(pkce_cookie)
        if not raw or not code:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        try:
            flow = json.loads(raw)
        except ValueError:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if not secrets.compare_digest(state, flow.get("s", "")):
            return JSONResponse({"error": "invalid_state"}, status_code=400)
        try:
            r = rp._http_post(f"{rp.issuer}/token", {
                "grant_type": "authorization_code", "client_id": manifest.id,
                "code": code,
                # exakter redirect_uri-Abgleich: dieselbe URI wie im authorize
                # (H10: aus dem PKCE-Cookie; Fallback = Manifest-URI/Bestand)
                "redirect_uri": flow.get("r") or rp.redirect_uri,
                "code_verifier": flow["v"]})
            r.raise_for_status()
            tokens = r.json()
            claims = rp.verify_id_token(tokens["id_token"], flow.get("n", ""))
        except Exception:
            return JSONResponse({"error": "sso_fehlgeschlagen"}, status_code=502)
        session = rp._sign_session({
            "sub": claims["sub"], "level": claims.get("dizzi_level", "verifiziert"),
            "amr": claims.get("amr", []), "via": "dizzi-id",
            "auth_time": float(claims.get("iat", time.time())),  # K2.1: Re-Auth-Frische
            "exp": time.time() + SESSION_TTL_S})
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(rp.cookie, session, httponly=True, samesite="lax",
                        max_age=SESSION_TTL_S, path="/")
        resp.delete_cookie(pkce_cookie, path="/auth")
        return resp

    @router.post("/auth/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(rp.cookie, path="/")
        return resp

    @router.get("/auth/me")
    def me(request: Request):
        s = rp.read_session(request.cookies.get(rp.cookie))
        if s is None:
            return {"angemeldet": False, "level": "lokal"}
        return {"angemeldet": True, "sub": s["sub"], "level": s["level"],
                "amr": s.get("amr", []), "via": s.get("via")}

    app.include_router(router)

    # Identitäts-Provider (der im Vertrag fixierte K1-Austauschpunkt):
    # Dizzi-ID-Session ⇒ deren Stufe; sonst Standalone-Rückfall 'lokal'.
    def _provider(request: Request) -> auth.UserContext:
        s = rp.read_session(request.cookies.get(rp.cookie))
        if s is not None:
            return auth.UserContext(user_id=s["sub"], level=s["level"],
                                    via="dizzi-id", auth_time=s.get("auth_time"))
        return auth.UserContext(user_id=auth.DEFAULT_USER_ID, level="lokal",
                                via="standalone")

    auth.set_identity_provider(_provider)
    manifest.auth.status = "aktiv"
    return rp
