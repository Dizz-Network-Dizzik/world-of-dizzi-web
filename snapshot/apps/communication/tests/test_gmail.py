"""Gmail-OAuth-Fundament: Flow-URL, Code-Tausch, Token-Refresh, .env-Leser."""

from __future__ import annotations

import base64
import json

import pytest

from kommapp import gmail


class _Antwort:
    def __init__(self, status_code: int, daten: dict):
        self.status_code = status_code
        self._daten = daten

    def json(self):
        return self._daten


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"kopf.{payload}.sig"


def test_flow_starten():
    flow = gmail.flow_starten("client-1", "http://127.0.0.1:8218/cb")
    assert flow["url"].startswith(gmail.AUTH_ENDPOINT)
    assert "access_type=offline" in flow["url"]
    assert "prompt=consent" in flow["url"]
    assert "mail.google.com" in flow["url"]
    assert "code_challenge=" in flow["url"] and flow["verifier"]
    assert flow["state"] in flow["url"]


def test_code_einloesen_mit_email():
    aufrufe = []

    def fake_post(url, data):
        aufrufe.append((url, data))
        return _Antwort(200, {"refresh_token": "r-1", "access_token": "a-1",
                              "id_token": _id_token("nutzer@example.com")})

    t = gmail.code_einloesen("cid", "sec", "code-x", "http://cb", "verif",
                             http_post=fake_post)
    assert t == {"refresh_token": "r-1", "access_token": "a-1",
                 "email": "nutzer@example.com"}
    url, data = aufrufe[0]
    assert url == gmail.TOKEN_ENDPOINT
    assert data["code_verifier"] == "verif"
    assert data["grant_type"] == "authorization_code"


def test_code_einloesen_fehler_ehrlich():
    with pytest.raises(RuntimeError, match="HTTP 400"):
        gmail.code_einloesen("c", "s", "x", "cb", "v",
                             http_post=lambda u, d: _Antwort(400, {}))
    # ohne Refresh-Token (z. B. prompt fehlte) ⇒ klare Ansage statt stillem Bruch
    with pytest.raises(RuntimeError, match="Refresh-Token"):
        gmail.code_einloesen("c", "s", "x", "cb", "v",
                             http_post=lambda u, d: _Antwort(200, {"access_token": "a"}))


def test_access_token_refresh():
    def fake_post(url, data):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "r-1"
        return _Antwort(200, {"access_token": "frisch-1"})

    assert gmail.access_token("c", "s", "r-1", http_post=fake_post) == "frisch-1"
    with pytest.raises(RuntimeError):
        gmail.access_token("c", "s", "r-1",
                           http_post=lambda u, d: _Antwort(200, {}))


def test_client_aus_env_datei(tmp_path, monkeypatch):
    monkeypatch.delenv("DIZZI_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIZZI_GOOGLE_CLIENT_SECRET", raising=False)
    assert gmail.client_aus_env(tmp_path) is None
    (tmp_path / ".env").write_text(
        "# Kommentar\nDIZZI_GOOGLE_CLIENT_ID=abc.apps\n"
        "DIZZI_GOOGLE_CLIENT_SECRET=geheim\nANDERES=x\n", encoding="utf-8")
    assert gmail.client_aus_env(tmp_path) == ("abc.apps", "geheim")
