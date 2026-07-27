"""Tests Dizzi-ID (K1): Discovery/JWKS, Code+PKCE-Flow, Refresh-Rotation mit
Reuse-Erkennung, lokales Passwort, Google-Broker (gemockt) + Konto-Pinning."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.id import ISSUER, google, keys, store
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_keys():
    """Frischer data_dir (core-conftest) ⇒ auch frisches IdP-Schlüsselpaar."""
    keys.reset_key_cache()
    yield
    keys.reset_key_cache()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _login(client: TestClient, pw: str = "geheim-passwort") -> None:
    r = client.post("/id/local/setup", data={"password": pw, "next": ""},
                    follow_redirects=False)
    assert r.status_code == 302


def _authorize_url(challenge: str, nonce: str = "n0nce") -> str:
    return "/id/authorize?" + urlencode({
        "client_id": "refapp", "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "response_type": "code", "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "st4te", "nonce": nonce})


def test_discovery_und_jwks(client):
    d = client.get("/id/.well-known/openid-configuration").json()
    assert d["issuer"] == ISSUER
    assert d["code_challenge_methods_supported"] == ["S256"]
    assert d["id_token_signing_alg_values_supported"] == ["Ed25519"]
    jw = client.get("/id/jwks.json").json()
    assert jw["keys"][0]["kty"] == "OKP" and jw["keys"][0]["crv"] == "Ed25519"
    assert "d" not in jw["keys"][0]                       # NIE der private Teil


def test_voller_code_flow_mit_pkce(client):
    _login(client)
    verifier, challenge = _pkce()
    r = client.get(_authorize_url(challenge), follow_redirects=False)
    assert r.status_code == 302
    target = urlsplit(r.headers["location"])
    assert target.netloc == "127.0.0.1:8290"
    q = parse_qs(target.query)
    assert q["state"] == ["st4te"]
    code = q["code"][0]

    r = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier})
    assert r.status_code == 200
    tokens = r.json()
    claims = keys.verify(tokens["id_token"])
    assert claims["iss"] == ISSUER and claims["aud"] == "refapp"
    assert claims["nonce"] == "n0nce"
    assert claims["dizzi_level"] == "verifiziert" and claims["amr"] == ["pwd"]
    access = keys.verify(tokens["access_token"])
    assert access["token_use"] == "access"

    # Code ist single-use
    r2 = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier})
    assert r2.status_code == 400


def test_falscher_verifier_und_fremde_redirect_uri(client):
    _login(client)
    verifier, challenge = _pkce()
    r = client.get(_authorize_url(challenge), follow_redirects=False)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    r = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": "voellig-falsch-" + secrets.token_urlsafe(24)})
    assert r.status_code == 400

    # Nicht registrierte redirect_uri ⇒ 400 OHNE Redirect (Open-Redirect-Schutz)
    bad = "/id/authorize?" + urlencode({
        "client_id": "refapp", "redirect_uri": "http://boese.example/cb",
        "response_type": "code", "code_challenge": challenge,
        "code_challenge_method": "S256"})
    r = client.get(bad, follow_redirects=False)
    assert r.status_code == 400


def test_refresh_rotation_und_reuse_widerruft_familie(client):
    _login(client)
    verifier, challenge = _pkce()
    r = client.get(_authorize_url(challenge), follow_redirects=False)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    t0 = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier}).json()

    r1 = client.post("/id/token", data={"grant_type": "refresh_token",
                                        "client_id": "refapp",
                                        "refresh_token": t0["refresh_token"]})
    assert r1.status_code == 200
    t1 = r1.json()
    assert t1["refresh_token"] != t0["refresh_token"]

    # REUSE des alten Tokens ⇒ 400 und GANZE Familie widerrufen
    r2 = client.post("/id/token", data={"grant_type": "refresh_token",
                                        "client_id": "refapp",
                                        "refresh_token": t0["refresh_token"]})
    assert r2.status_code == 400
    r3 = client.post("/id/token", data={"grant_type": "refresh_token",
                                        "client_id": "refapp",
                                        "refresh_token": t1["refresh_token"]})
    assert r3.status_code == 400                          # Familie tot

    # Audit hat den Vorfall festgehalten
    audit = client.get("/api/audit?limit=100").json()
    assert any(e["action"] == "id_refresh_REUSE_familie_widerrufen" for e in audit)


def test_seed_clients_sind_manifest_ids_mit_finalem_port():
    """Regression (16.06.): die OAuth-Client-ids MÜSSEN die Manifest-ids der Apps
    sein (= was sie als client_id senden, appkit/dizzi_id.py) auf ihrem FINALEN
    Port — sonst läuft ihr SSO in invalid_client. War für admin/plans/memory/
    management der Fall, weil hier noch die alten Ordner-ids/Scaffold-Ports standen."""
    erwartet = {"finanzen": 8210, "memory": 8212, "management": 8213,
                "creator": 8214, "news": 8216, "health": 8217, "kommunikation": 8218,
                "admin": 8222, "tradingbot": 8137}
    for cid, port in erwartet.items():
        assert cid in store.SEED_CLIENTS, f"OAuth-Client '{cid}' fehlt ⇒ SSO bricht"
        assert store.SEED_CLIENTS[cid] == [
            f"http://127.0.0.1:{port}/auth/callback",
            f"http://localhost:{port}/auth/callback"]
    # Abgelöste Ordner-ids UND die in Dizz Admin verschmolzenen Apps (docs/28) sind raus.
    for alt in ("buerokratie", "projekte", "archiv", "social-media", "musik", "plans", "leading"):
        assert alt not in store.SEED_CLIENTS


def test_sso_authorize_fuer_manifest_id_apps_kein_invalid_client(client):
    """Flow-Regression: /id/authorize für die Manifest-id-Apps mit korrekter
    redirect_uri liefert KEIN invalid_client (400), sondern den Login-Redirect
    (302). Mit den alten Ordner-id-Seeds war das ein harter 400."""
    _, challenge = _pkce()
    for cid, port in (("admin", 8222), ("memory", 8212), ("management", 8213)):
        url = "/id/authorize?" + urlencode({
            "client_id": cid, "redirect_uri": f"http://127.0.0.1:{port}/auth/callback",
            "response_type": "code", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": "st", "nonce": "n"})
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 302, f"{cid}: erwartete Login-Redirect, kein invalid_client"


def test_userinfo_mit_access_token(client):
    _login(client)
    verifier, challenge = _pkce()
    r = client.get(_authorize_url(challenge), follow_redirects=False)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    tokens = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier}).json()
    r = client.get("/id/userinfo",
                   headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200 and r.json()["sub"] == "dizzi"
    assert client.get("/id/userinfo",
                      headers={"Authorization": "Bearer kaputt"}).status_code == 401


def test_lokales_passwort_falsch_und_setup_nur_einmal(client):
    _login(client, pw="richtig-und-lang")
    r = client.post("/id/login/local", data={"password": "falsch!!", "next": ""},
                    follow_redirects=False)
    assert r.status_code == 302 and "err=1" in r.headers["location"]
    r = client.post("/id/local/setup", data={"password": "zweites-mal", "next": ""})
    assert r.status_code == 409                           # Setup nur EINMAL


def test_google_broker_mit_pinning(client, monkeypatch):
    monkeypatch.setenv("DIZZI_GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("DIZZI_GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(google, "exchange_code",
                        lambda code, verifier, redirect_uri=None: {"id_token": "FAKE"})
    monkeypatch.setattr(google, "verify_id_token",
                        lambda tok: {"sub": "g-sub-1", "email": "dizzi@example.com"})

    r = client.get("/id/login/google?next=", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://accounts.google.com/")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]

    r = client.get(f"/id/callback/google?code=abc&state={state}",
                   follow_redirects=False)
    assert r.status_code == 302                            # Session erstellt
    assert client.get("/id/status").json()["angemeldet"] is True

    # Fremdes Google-Konto (andere sub) wird ABGELEHNT (Pinning)
    monkeypatch.setattr(google, "verify_id_token",
                        lambda tok: {"sub": "g-sub-EVIL", "email": "evil@example.com"})
    r = client.get("/id/login/google?next=", follow_redirects=False)
    state2 = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    r = client.get(f"/id/callback/google?code=abc&state={state2}",
                   follow_redirects=False)
    assert r.status_code == 403

    # State-Mismatch wird abgelehnt
    r = client.get("/id/login/google?next=", follow_redirects=False)
    r = client.get("/id/callback/google?code=abc&state=falscher-state",
                   follow_redirects=False)
    assert r.status_code == 400


def test_google_redirect_uri_host_konsistent():
    """Dauerlösung 18.06.: die Google-Callback-URI folgt dem Zugriffs-Host (nur
    Loopback) ⇒ Flow-Cookie-Host == Callback-Host, kein Cookie-Welt-Split mehr.
    Fremde Hosts (manipulierter Host-Header) fallen auf den Default zurück."""
    assert google.redirect_uri_for("127.0.0.1") == "http://127.0.0.1:8200/id/callback/google"
    assert google.redirect_uri_for("localhost") == "http://localhost:8200/id/callback/google"
    assert google.redirect_uri_for("LOCALHOST") == "http://localhost:8200/id/callback/google"
    assert google.redirect_uri_for("evil.example.com") == google.REDIRECT_URI
    assert google.redirect_uri_for("") == google.REDIRECT_URI
    assert google.redirect_uri_for(None) == google.REDIRECT_URI


def test_logout_beendet_session(client):
    _login(client)
    assert client.get("/id/status").json()["angemeldet"] is True
    client.post("/id/logout")
    assert client.get("/id/status").json()["angemeldet"] is False


def test_abgelaufener_code_wird_abgelehnt(client, monkeypatch):
    _login(client)
    verifier, challenge = _pkce()
    r = client.get(_authorize_url(challenge), follow_redirects=False)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + store.CODE_TTL_S + 5)
    r = client.post("/id/token", data={
        "grant_type": "authorization_code", "client_id": "refapp", "code": code,
        "redirect_uri": "http://127.0.0.1:8290/auth/callback",
        "code_verifier": verifier})
    assert r.status_code == 400


# --- H10: Registry-Migration auf beide Loopback-Hosts -------------------------

def test_ensure_clients_migriert_localhost_varianten():
    """Bestands-DBs (nur 127.0.0.1-URIs) bekommen die localhost-Variante
    ADDITIV dazugemerged; selbst gepflegte URIs bleiben erhalten."""
    import json as _json
    from app import db as core_db

    store.ensure_clients()
    conn = core_db.get_conn()
    # Bestand simulieren: news auf alte Ein-Host-Form + eine Custom-URI setzen
    alt = ["http://127.0.0.1:8216/auth/callback",
           "http://127.0.0.1:8216/custom"]
    conn.execute("UPDATE id_clients SET redirect_uris=? WHERE client_id='news'",
                 (_json.dumps(alt),))
    conn.commit()

    store.ensure_clients()                     # Migration laeuft erneut
    uris = store.client_redirects("news")
    assert "http://localhost:8216/auth/callback" in uris
    assert "http://127.0.0.1:8216/auth/callback" in uris
    assert "http://127.0.0.1:8216/custom" in uris   # additiv, nichts verloren
