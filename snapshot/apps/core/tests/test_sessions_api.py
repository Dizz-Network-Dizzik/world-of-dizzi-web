"""K2.1b/H7: Sitzungen & Geräte — Liste, Einzel-Widerruf, „überall abmelden"."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.id import keys, store
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


def test_sessions_brauchen_anmeldung(client):
    assert client.get("/id/sessions").status_code == 401
    assert client.post("/id/sessions/x/widerruf").status_code == 401
    assert client.post("/id/sessions/alle_widerrufen").status_code == 401


def test_liste_und_einzel_widerruf(client):
    _login(client)
    store.create_session("verifiziert", ["pwd"])   # zweites „Gerät"
    sessions = client.get("/id/sessions").json()
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s["aktuell"]) == 1
    fremde = next(s for s in sessions if not s["aktuell"])

    r = client.post(f"/id/sessions/{fremde['id']}/widerruf").json()
    assert r["ok"] is True
    rest = client.get("/id/sessions").json()
    assert len(rest) == 1 and rest[0]["aktuell"] is True
    # Doppel-Widerruf ist idempotent-ehrlich (ok=False)
    assert client.post(
        f"/id/sessions/{fremde['id']}/widerruf").json()["ok"] is False


def test_ueberall_abmelden(client):
    _login(client)
    store.create_session("verifiziert", ["pwd"])
    r = client.post("/id/sessions/alle_widerrufen").json()
    assert r["ok"] is True and r["widerrufen"] == 2
    # Auch die eigene Session ist weg ⇒ Verwaltung verlangt neue Anmeldung
    assert client.get("/id/sessions").status_code == 401
