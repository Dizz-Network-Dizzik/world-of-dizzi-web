"""Tests Dizz Admin — Externe-Tool-Konnektoren (Konnektivitäts-Vision docs/35 §3, D2).
Datenmodell + Typen-Register + dormante Adapter + Sichtbarkeit. KEINE echten
Plattform-APIs (Architektur-KI-Park) — alles dormant, read-only.
Lauf: pytest tests/ -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adminapp import main as am
from adminapp import konnektoren as kn


def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path))


def test_typen_register_dormant(tmp_path):
    with _client(tmp_path) as c:
        t = c.get("/api/konnektoren/typen").json()
        ids = {x["typ"] for x in t["typen"]}
        assert {"google_calendar", "caldav", "notion", "todoist", "github"} <= ids
        # Ohne Tresor-Token gilt alles als nicht verbunden (ehrlich).
        assert all(x["verbunden"] is False for x in t["typen"])
        # Outbound überall aus (Steuern nur über K4-HITL).
        assert all(x["steuern"] is False for x in t["typen"])


def test_anlegen_listen_loeschen(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Mandant X", "art": "mandant"}).json()["id"]
        r = c.post("/api/konnektoren", json={"typ": "notion", "name": "Mandant-Wiki",
                                             "bereich_id": b, "extern_ref": "db-123"})
        assert r.status_code == 200
        kid = r.json()["id"]
        lst = c.get("/api/konnektoren").json()
        assert lst["zaehler"]["gesamt"] == 1
        k = lst["konnektoren"][0]
        assert k["typ"] == "notion" and k["art"] == "projekt" and k["bereich_id"] == b
        assert k["aktiv"] is False and k["verbunden"] is False        # dormant
        assert k["token_name"] == "notion_token"
        # Löschen
        assert c.delete(f"/api/konnektoren/{kid}").status_code == 200
        assert c.get("/api/konnektoren").json()["zaehler"]["gesamt"] == 0


def test_unbekannter_typ_400(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/konnektoren", json={"typ": "skynet"}).status_code == 400


def test_bereich_filter(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Studium", "art": "studium"}).json()["id"]
        c.post("/api/konnektoren", json={"typ": "caldav", "bereich_id": b})   # an Bereich
        c.post("/api/konnektoren", json={"typ": "github"})                    # global ('')
        assert len(c.get("/api/konnektoren").json()["konnektoren"]) == 2
        assert len(c.get(f"/api/konnektoren?bereich_id={b}").json()["konnektoren"]) == 1
        nur_global = c.get("/api/konnektoren?bereich_id=").json()["konnektoren"]
        assert len(nur_global) == 1 and nur_global[0]["typ"] == "github"


def test_patch_aktiv_und_name(tmp_path):
    with _client(tmp_path) as c:
        kid = c.post("/api/konnektoren", json={"typ": "trello"}).json()["id"]
        c.patch(f"/api/konnektoren/{kid}", json={"name": "Roadmap-Board", "aktiv": True})
        k = c.get("/api/konnektoren").json()["konnektoren"][0]
        assert k["name"] == "Roadmap-Board" and k["aktiv"] is True
        assert c.patch("/api/konnektoren/gibtsnicht", json={"name": "x"}).status_code == 404


def test_verbunden_spiegelt_tresor_token(tmp_path):
    """Sobald ein passendes Token im Tresor liegt, meldet der Typ verbunden=true."""
    with _client(tmp_path) as c:
        assert c.get("/api/konnektoren/typen").json()
        c.app.state.vault.put("notion_token", "geheim")
        typen = {x["typ"]: x for x in c.get("/api/konnektoren/typen").json()["typen"]}
        assert typen["notion"]["verbunden"] is True
        assert typen["trello"]["verbunden"] is False
        # auch in der Instanz-Sicht
        c.post("/api/konnektoren", json={"typ": "notion"})
        assert c.get("/api/konnektoren").json()["konnektoren"][0]["verbunden"] is True


def test_adapter_dormant():
    """Der dormante Adapter meldet ehrlich „nicht verbunden" statt zu raten."""
    conn = kn.connector_for("notion", vault_get=lambda _n: None)
    assert conn is not None and conn.verfuegbar() is False
    with pytest.raises(kn.QuelleNichtVerbunden):
        conn.lesen()
    with pytest.raises(kn.QuelleNichtVerbunden):
        conn.ansteuern()
    # mit Token verfügbar, aber Live-Lesen bleibt dormant (W4 ausstehend)
    conn2 = kn.connector_for("notion", vault_get=lambda _n: "tok")
    assert conn2.verfuegbar() is True
    with pytest.raises(kn.QuelleNichtVerbunden):
        conn2.lesen()
    assert kn.connector_for("unbekannt") is None
