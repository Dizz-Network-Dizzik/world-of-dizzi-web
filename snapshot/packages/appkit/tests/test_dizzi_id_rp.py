"""Cross-Test K1: Relying Party (appkit.dizzi_id) gegen den ECHTEN Dizzi-ID-
Provider (core) — der volle SSO-Handschlag über beide Seiten:

  RP /auth/login → IdP /id/authorize → (Login) → Code → RP /auth/callback
  → ID-Token-Prüfung (Ed25519/JWKS) → App-Session → require_level scharf.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "core"))  # Core-Paket `app` (IdP)

# In VENDIERTEN Kopien (z. B. Dizz Trading) existiert der Dizzi-Core nicht —
# dann sauber überspringen statt mit ImportError zu scheitern.
pytest.importorskip("app.id.keys",
                    reason="Dizzi-Core (IdP) nicht verfügbar — vendierter Kontext")

from appkit import auth  # noqa: E402
from appkit.app import create_app  # noqa: E402
from appkit.db import Database  # noqa: E402
from appkit.dizzi_id import install_dizzi_id  # noqa: E402
from appkit.manifest import AppManifest  # noqa: E402
from appkit.summary import Kpi  # noqa: E402


@pytest.fixture()
def idp(tmp_path, monkeypatch):
    """Frischer IdP (eigene tmp-DB + frisches Schlüsselpaar)."""
    from app import db as core_db
    from app.config import settings as core_settings
    from app.id import keys as id_keys
    monkeypatch.setattr(core_settings, "data_dir", tmp_path / "idp")
    core_db.reset_thread_conn()
    id_keys.reset_key_cache()
    from app.main import app as core_app
    with TestClient(core_app) as c:
        yield c
    core_db.reset_thread_conn()
    id_keys.reset_key_cache()


@pytest.fixture()
def rp(tmp_path, idp):
    """Vertrags-App (refapp-Manifest, Port 8290 = registrierter Client) mit
    Dizzi-ID-Anschluss; HTTP-Verkehr zum IdP läuft über dessen TestClient."""
    manifest = AppManifest(id="refapp", name="Referenz-App", brand="Dizz Ref",
                           version="0.1.0", port=8290)
    db = Database(tmp_path / "rp" / "rp.sqlite")

    router = APIRouter()

    @router.get("/api/sensibel",
                dependencies=[Depends(auth.require_level("verifiziert"))])
    def sensibel():
        return {"geheim": True}

    @router.get("/api/echtgeld",
                dependencies=[Depends(auth.require_level("hochsicher"))])
    def echtgeld():
        return {"freigegeben": True}

    app = create_app(manifest, db,
                     summary_fn=lambda: [Kpi(id="n", label="N", value=1)],
                     routers=[router])

    def _strip(url: str) -> str:
        parts = urlsplit(url)
        return parts.path + (f"?{parts.query}" if parts.query else "")

    install_dizzi_id(app, manifest, data_root=tmp_path / "rp-data",
                     http_get=lambda url: idp.get(_strip(url)),
                     http_post=lambda url, data: idp.post(_strip(url), data=data))
    with TestClient(app) as c:
        yield c
    auth.reset_identity_provider()


def _idp_login(idp: TestClient) -> None:
    r = idp.post("/id/local/setup", data={"password": "nacht-schicht-12",
                                          "next": ""}, follow_redirects=False)
    assert r.status_code == 302


def test_voller_sso_handschlag(idp, rp):
    # Vor dem Login: Standalone-Stufe 'lokal', sensible Route fail-closed.
    assert rp.get("/auth/me").json() == {"angemeldet": False, "level": "lokal"}
    assert rp.get("/api/sensibel").status_code == 403

    _idp_login(idp)                                       # 1× bei Dizzi anmelden

    # RP startet den Flow; wir laufen den Redirect von Hand (Cross-Origin).
    r = rp.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    auth_url = r.headers["location"]
    # H10: der BROWSER navigiert zu localhost (Passkey-RP-ID, eine Cookie-Welt)
    assert auth_url.startswith("http://localhost:8200/id/authorize")

    parts = urlsplit(auth_url)
    r = idp.get(parts.path + "?" + parts.query, follow_redirects=False)
    assert r.status_code == 302                           # Session da ⇒ Code sofort
    cb = urlsplit(r.headers["location"])
    assert cb.netloc == "127.0.0.1:8290" and cb.path == "/auth/callback"

    r = rp.get(cb.path + "?" + cb.query, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"

    me = rp.get("/auth/me").json()
    assert me["angemeldet"] is True
    assert me["level"] == "verifiziert" and me["via"] == "dizzi-id"
    assert me["sub"] == "dizzi"

    # Der K1-Austauschpunkt wirkt: die sensible Route ist jetzt offen.
    assert rp.get("/api/sensibel").status_code == 200
    # 'hochsicher' bleibt zu (kommt erst mit Passkey/MFA, R1.3).


def test_stepup_hochsicher_ende_zu_ende(idp, rp):
    """Echtgeld-Pfad: RP fordert 'hochsicher' an ⇒ IdP erzwingt TOTP-Step-up;
    erst danach öffnet die hochsicher-Route der App."""
    from app.id import store as id_store
    from app.id import totp as id_totp

    _idp_login(idp)

    r = rp.get("/auth/login?level=hochsicher", follow_redirects=False)
    auth_parts = urlsplit(r.headers["location"])
    assert "acr_values=hochsicher" in auth_parts.query

    # IdP: Session ist nur 'verifiziert' ⇒ Step-up statt Code
    r = idp.get(auth_parts.path + "?" + auth_parts.query, follow_redirects=False)
    assert "/id/stepup" in r.headers["location"]

    # TOTP enrollen + verifizieren (echter Code aus dem gespeicherten Secret)
    idp.get("/id/stepup?next=", follow_redirects=False)
    code = id_totp.code_now(id_store.totp_secret_klartext())
    r = idp.post("/id/stepup", data={"code": code, "next": ""},
                 follow_redirects=False)
    assert "err" not in r.headers["location"]

    # Jetzt liefert authorize den Code; RP-Callback ⇒ Stufe 'hochsicher'
    r = idp.get(auth_parts.path + "?" + auth_parts.query, follow_redirects=False)
    cb = urlsplit(r.headers["location"])
    assert cb.path == "/auth/callback"
    rp.get(cb.path + "?" + cb.query, follow_redirects=False)

    me = rp.get("/auth/me").json()
    assert me["level"] == "hochsicher" and "totp" in me["amr"]
    assert rp.get("/api/echtgeld").status_code == 200
    assert rp.get("/api/sensibel").status_code == 200      # niedrigere Stufe inklusive


def test_redirect_uri_folgt_dem_browser_host(idp, rp):
    """H10: öffnet der Nutzer die App über localhost, MUSS der Callback auf
    localhost zurückkommen (PKCE-Cookie-Host) — und der Handschlag klappt,
    weil der IdP beide Host-Varianten registriert hat."""
    _idp_login(idp)
    r = rp.get("/auth/login", headers={"host": "localhost:8290"},
               follow_redirects=False)
    parts = urlsplit(r.headers["location"])
    assert parts.netloc == "localhost:8200"            # Browser-Nav (Passkeys)
    assert "localhost%3A8290%2Fauth%2Fcallback" in parts.query

    r = idp.get(parts.path + "?" + parts.query, follow_redirects=False)
    assert r.status_code == 302                        # registriert ⇒ Code
    cb = urlsplit(r.headers["location"])
    assert cb.netloc == "localhost:8290" and cb.path == "/auth/callback"

    r = rp.get(cb.path + "?" + cb.query, headers={"host": "localhost:8290"},
               follow_redirects=False)
    assert r.status_code == 302
    assert rp.get("/auth/me").json()["angemeldet"] is True


def test_callback_mit_falschem_state(idp, rp):
    _idp_login(idp)
    r = rp.get("/auth/login", follow_redirects=False)
    parts = urlsplit(r.headers["location"])
    r = idp.get(parts.path + "?" + parts.query, follow_redirects=False)
    cb = urlsplit(r.headers["location"])
    # state manipulieren ⇒ RP lehnt ab, keine Session
    bad_q = cb.query.replace("state=", "state=MANIPULIERT")
    r = rp.get(cb.path + "?" + bad_q, follow_redirects=False)
    assert r.status_code == 400
    assert rp.get("/auth/me").json()["angemeldet"] is False


def test_logout_faellt_auf_lokal_zurueck(idp, rp):
    _idp_login(idp)
    r = rp.get("/auth/login", follow_redirects=False)
    parts = urlsplit(r.headers["location"])
    r = idp.get(parts.path + "?" + parts.query, follow_redirects=False)
    cb = urlsplit(r.headers["location"])
    rp.get(cb.path + "?" + cb.query, follow_redirects=False)
    assert rp.get("/auth/me").json()["angemeldet"] is True

    rp.post("/auth/logout")
    me = rp.get("/auth/me").json()
    assert me["angemeldet"] is False and me["level"] == "lokal"
    assert rp.get("/api/sensibel").status_code == 403     # wieder fail-closed
