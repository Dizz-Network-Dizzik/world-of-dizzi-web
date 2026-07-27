"""Härtungs-Tests (Tiefen-Review 12.06.): der ``next``-Parameter der
IdP-Seiten ist Angreifer-beeinflussbar (Link in E-Mail/Webseite) und darf
weder als Open-Redirect noch als XSS-Träger funktionieren."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.id import keys, routes
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


def _login(client: TestClient) -> None:
    client.post("/id/local/setup", data={"password": "nacht-schicht-12",
                                         "next": ""}, follow_redirects=False)


# --- _safe_next (pure) ---------------------------------------------------------

def test_safe_next_erlaubt_relative_und_eigene_hosts():
    assert routes._safe_next("/id/geraete") == "/id/geraete"
    assert routes._safe_next("http://localhost:8200/id/authorize?x=1") \
        == "http://localhost:8200/id/authorize?x=1"
    assert routes._safe_next("http://127.0.0.1:8137/auth/callback") \
        == "http://127.0.0.1:8137/auth/callback"


def test_safe_next_verwirft_fremde_ziele():
    assert routes._safe_next("https://evil.example/phish") == ""
    assert routes._safe_next("//evil.example/phish") == ""        # schema-relativ
    assert routes._safe_next("/\\evil.example") == ""             # Backslash-Trick
    assert routes._safe_next("javascript:alert(1)") == ""
    assert routes._safe_next("http://localhost.evil.example/") == ""
    assert routes._safe_next("") == ""
    # RD-1 (28.06.): Backslash-Confusion — Python urlsplit sieht host=localhost, der
    # Browser (WHATWG '\' -> '/') navigiert zu evil.com ⇒ MUSS verworfen werden.
    assert routes._safe_next("https://evil.com\\@localhost/") == ""
    assert routes._safe_next("https://localhost@evil.com/") == ""   # userinfo-Trick
    # Control-Chars (CRLF) ⇒ Header-/HTML-Injection, auch im Relativ-Pfad verwerfen.
    assert routes._safe_next("/foo\r\nSet-Cookie: evil=1") == ""
    assert routes._safe_next("/ok\tx") == ""


# --- Open-Redirect über den Login-Flow ------------------------------------------

def test_login_redirect_folgt_keinem_fremden_next(client: TestClient):
    r = client.post("/id/local/setup",
                    data={"password": "nacht-schicht-12",
                          "next": "https://evil.example/phish"},
                    follow_redirects=False)
    assert r.status_code == 302
    assert "evil.example" not in r.headers["location"]
    assert r.headers["location"].startswith("/id/")


# --- XSS über die eingebetteten Seiten -------------------------------------------

def test_login_seite_escaped_next_payload(client: TestClient):
    payload = '/x"><script>alert(1)</script>'
    r = client.get("/id/login", params={"next": payload})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text


def test_stepup_seite_escaped_next_payload(client: TestClient):
    _login(client)
    payload = "/x'></form><script>alert(1)</script>"
    r = client.get("/id/stepup", params={"next": payload})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
