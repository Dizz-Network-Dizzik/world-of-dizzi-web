"""Gmail-Anbindung — OAuth 2.0 (Loopback, RFC 8252) für IMAP/SMTP via XOAUTH2.

Nutzt den VORHANDENEN Google-Desktop-Client der Dizzi-ID (ein Client fürs
ganze Netzwerk; Keys in ``C:\\Dizzik\\data\\.env``): zusätzlich zum
Login-Scope holt sich Dizz Communication hier den Mail-Scope
(``https://mail.google.com/``) mit ``access_type=offline`` — das
**Refresh-Token wandert in den K2-Tresor**, Access-Tokens werden je
Sync-Lauf frisch getauscht (sie leben nur ~1 h).

Alle HTTP-Aufrufe sind injizierbar (netzfrei testbar); PKCE + state wie im
Dizzi-ID-Broker. Der Consent selbst ist ein Nutzer-Schritt im Browser.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
MAIL_SCOPE = "https://mail.google.com/"

HttpPost = Callable[[str, dict[str, str]], Any]   # (url, form-data) -> Response


def _b64url(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


def client_aus_env(data_root: Path | None = None) -> tuple[str, str] | None:
    """Liest DIZZI_GOOGLE_CLIENT_ID/SECRET aus der zentralen ``.env``
    (gleicher Desktop-Client wie die Dizzi-ID). None = nicht konfiguriert."""
    import os
    cid = os.environ.get("DIZZI_GOOGLE_CLIENT_ID", "")
    sec = os.environ.get("DIZZI_GOOGLE_CLIENT_SECRET", "")
    if not (cid and sec):
        env = (data_root or Path(r"C:\Dizzik\data")) / ".env"
        if env.is_file():
            werte: dict[str, str] = {}
            for zeile in env.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if zeile and not zeile.startswith("#") and "=" in zeile:
                    k, _, v = zeile.partition("=")
                    werte[k.strip()] = v.strip()
            cid = cid or werte.get("DIZZI_GOOGLE_CLIENT_ID", "")
            sec = sec or werte.get("DIZZI_GOOGLE_CLIENT_SECRET", "")
    return (cid, sec) if cid and sec else None


def flow_starten(client_id: str, redirect_uri: str) -> dict[str, str]:
    """Baut Autorisierungs-URL + PKCE/state. Liefert {url, verifier, state}."""
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(16)
    url = AUTH_ENDPOINT + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"openid email {MAIL_SCOPE}",
        "access_type": "offline", "prompt": "consent",   # erzwingt Refresh-Token
        "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state})
    return {"url": url, "verifier": verifier, "state": state}


def _post(url: str, data: dict[str, str]):
    import httpx
    return httpx.post(url, data=data, timeout=15.0)


def code_einloesen(client_id: str, client_secret: str, code: str,
                   redirect_uri: str, verifier: str,
                   http_post: HttpPost | None = None) -> dict[str, Any]:
    """Tauscht den Code; liefert {refresh_token, access_token, email}.
    E-Mail kommt aus dem id_token-Payload (direkt über TLS vom Google-
    Token-Endpoint bezogen ⇒ Quelle vertrauenswürdig, keine Signaturprüfung
    nötig — gleiche Begründung wie im Dizzi-ID-Broker)."""
    r = (http_post or _post)(TOKEN_ENDPOINT, {
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    if r.status_code != 200:
        raise RuntimeError(f"Google-Token-Tausch fehlgeschlagen (HTTP {r.status_code})")
    t = r.json()
    email = ""
    id_token = t.get("id_token", "")
    if id_token.count(".") == 2:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        try:
            email = json.loads(base64.urlsafe_b64decode(payload)).get("email", "")
        except Exception:
            email = ""
    if not t.get("refresh_token"):
        raise RuntimeError("Google lieferte kein Refresh-Token "
                           "(prompt=consent erwartet eines)")
    return {"refresh_token": t["refresh_token"],
            "access_token": t.get("access_token", ""), "email": email}


def access_token(client_id: str, client_secret: str, refresh_token: str,
                 http_post: HttpPost | None = None) -> str:
    """Frisches Access-Token je Sync-Lauf (Refresh-Grant)."""
    r = (http_post or _post)(TOKEN_ENDPOINT, {
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"Google-Token-Refresh fehlgeschlagen (HTTP {r.status_code})")
    tok = r.json().get("access_token", "")
    if not tok:
        raise RuntimeError("Google lieferte kein Access-Token")
    return tok
