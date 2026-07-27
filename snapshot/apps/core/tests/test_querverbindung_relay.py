"""Core-Relay (Phase 2, docs/26): App → Core → Ziel-Archiv-App.
Weiterleitung an Memorys Empfangs-Slot, 404 bei unbekanntem Ziel, ehrlich offline."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import panels
from app.main import app


@pytest.fixture(autouse=True)
def _registry_restore():
    snap = dict(panels._registry)
    apps = dict(panels._contract_apps)
    yield
    panels._registry.clear()
    panels._registry.update(snap)
    panels._contract_apps.clear()
    panels._contract_apps.update(apps)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}

    def json(self):
        return self._p


def test_relay_leitet_an_ziel_weiter(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")
    erfasst = {}

    def fake_post(url, json, timeout):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "archiviert", "id": "n9"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/memory", json={
            "titel": "EZB", "inhalt": "x", "app": "news",
            "tags": ["finanzen"], "ref": "news:1", "sensibel": False,
            "strom": "wochenbericht", "explizit": True})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "memory" and out["status"] == "archiviert" and out["id"] == "n9"

    assert erfasst["url"] == "http://127.0.0.1:8212/api/querverbindung/archivieren"
    assert erfasst["json"]["app"] == "news" and erfasst["json"]["ref"] == "news:1"
    assert erfasst["json"]["tags"] == ["finanzen"]
    assert erfasst["json"]["strom"] == "wochenbericht" and erfasst["json"]["explizit"] is True


def test_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/gibtsnicht",
                   json={"titel": "x", "app": "news"})
        assert r.status_code == 404


def test_relay_ziel_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")

    def boom(url, json, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/memory", json={"titel": "x", "app": "news"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False and "erreichbar" in body["fehler"]


# ===================== V5: zweiter Vertragstyp — Kalender-Relay =====================
def test_kalender_relay_leitet_an_ziel_weiter(monkeypatch):
    """Der Kalender-Relay (V5) leitet an ``{ziel}/api/querverbindung/kalender``
    weiter (eigener Umschlag mit beginn/ende/ort) — additiv zum Archiv-Relay."""
    panels._contract_apps.clear()
    panels.register_contract_app("admin", "http://127.0.0.1:8222")   # plans→Admin verschmolzen (docs/28)
    erfasst = {}

    def fake_post(url, json, timeout):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "eingetragen", "id": "t7"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/admin/kalender", json={
            "titel": "Kickoff", "beginn": "2026-07-01T15:00", "ende": "2026-07-01T16:00",
            "ort": "Jitsi", "app": "kommunikation", "ref": "komm:termin:42"})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "admin" and out["status"] == "eingetragen" and out["id"] == "t7"

    assert erfasst["url"] == "http://127.0.0.1:8222/api/querverbindung/kalender"
    assert erfasst["json"]["titel"] == "Kickoff" and erfasst["json"]["beginn"] == "2026-07-01T15:00"
    assert erfasst["json"]["ort"] == "Jitsi" and erfasst["json"]["ref"] == "komm:termin:42"
    assert erfasst["json"]["app"] == "kommunikation"


def test_kalender_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/gibtsnicht/kalender",
                   json={"titel": "x", "beginn": "2026-07-01T10:00", "app": "kommunikation"})
        assert r.status_code == 404


# ===================== Rück-Lese: GET-Such-Relay (das „↔", docs/26 §10.1) ==========
def test_suche_relay_fts_leitet_weiter(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, [{"titel": "EZB", "auszug": "…"}])

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/memory/suche", params={"q": "ezb", "limit": 5})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "memory" and out["ok"] is True and out["anzahl"] == 1
        assert out["treffer"][0]["titel"] == "EZB"

    assert erfasst["url"] == "http://127.0.0.1:8212/api/suche"  # FTS-Pfad
    assert erfasst["params"] == {"q": "ezb", "limit": 5}


def test_suche_relay_semantisch_nutzt_k(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, [])

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/memory/suche",
                  params={"q": "geld", "semantisch": "true", "limit": 3})
        assert r.status_code == 200 and r.json()["anzahl"] == 0

    assert erfasst["url"] == "http://127.0.0.1:8212/api/suche/semantisch"  # RAG-Pfad
    assert erfasst["params"] == {"q": "geld", "k": 3}  # Mengen-Param heißt k


def test_suche_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/gibtsnicht/suche", params={"q": "x"})
        assert r.status_code == 404


def test_suche_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/memory/suche", params={"q": "x"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False and body["treffer"] == [] and "erreichbar" in body["fehler"]


# ===================== V15: dritter Vertragstyp — Verknüpfung + Belege-Lookup ========
def test_verknuepfung_relay_leitet_an_ziel_weiter(monkeypatch):
    """Der Verknüpfungs-Relay (V15) leitet an ``{ziel}/api/querverbindung/verknuepfung``
    weiter (Umschlag von_app/von_ref/ziel_ref) — additiv zu Archiv- + Kalender-Relay."""
    panels._contract_apps.clear()
    panels.register_contract_app("admin", "http://127.0.0.1:8222")
    erfasst = {}

    def fake_post(url, json, timeout):
        erfasst["url"] = url
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "verknuepft", "id": "v3"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/admin/verknuepfung", json={
            "von_app": "finanzen", "von_ref": "finanzen:buchung:42",
            "von_titel": "REWE 12,30 €", "ziel_ref": "admin:dokument:7"})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "admin" and out["status"] == "verknuepft" and out["id"] == "v3"

    assert erfasst["url"] == "http://127.0.0.1:8222/api/querverbindung/verknuepfung"
    assert erfasst["json"]["von_ref"] == "finanzen:buchung:42"
    assert erfasst["json"]["ziel_ref"] == "admin:dokument:7"
    assert erfasst["json"]["von_app"] == "finanzen"


def test_verknuepfung_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/gibtsnicht/verknuepfung",
                   json={"von_app": "finanzen", "von_ref": "x", "ziel_ref": "y"})
        assert r.status_code == 404


def test_verknuepfung_relay_reicht_aktion_loesen_durch(monkeypatch):
    """V15-Audit-Fix: der Relay leitet auch ``aktion="loesen"`` weiter (Storno-Cleanup)."""
    panels._contract_apps.clear()
    panels.register_contract_app("admin", "http://127.0.0.1:8222")
    erfasst = {}

    def fake_post(url, json, timeout):
        erfasst["json"] = json
        return _Resp(200, {"ok": True, "status": "geloest", "anzahl": 1})

    monkeypatch.setattr(httpx, "post", fake_post)
    with TestClient(app) as c:
        r = c.post("/api/querverbindung/admin/verknuepfung", json={
            "von_app": "finanzen", "von_ref": "finanzen:buchung:42",
            "ziel_ref": "admin:dokument:7", "aktion": "loesen"})
        assert r.status_code == 200 and r.json()["status"] == "geloest"
    assert erfasst["json"]["aktion"] == "loesen"


def test_belege_relay_holt_vom_ziel(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("admin", "http://127.0.0.1:8222")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, [{"ref": "admin:dokument:7", "titel": "Rechnung", "typ": "pdf"}])

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/admin/belege", params={"q": "rech", "limit": 20})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "admin" and out["ok"] is True
        assert out["belege"][0]["ref"] == "admin:dokument:7"

    assert erfasst["url"] == "http://127.0.0.1:8222/api/belege"
    assert erfasst["params"] == {"q": "rech", "limit": 20}


def test_belege_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("admin", "http://127.0.0.1:8222")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/admin/belege", params={"q": "x"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False and body["belege"] == [] and "erreichbar" in body["fehler"]


# ===================== V16: EÜR-Lese-Relay (Leading-Aggregation) ====================
def test_euer_relay_holt_money_steuer_jahr(monkeypatch):
    """V16-Relay: proxyt Moneys EÜR-Auswertung (GET /api/steuer/jahr, nur_steuer=1)
    für die Leading-EÜR-Ausgabenseite — additiv zu Archiv/Kalender/Verknüpfung/Belege."""
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"jahr": 2026, "einnahmen": 0, "ausgaben": 12000,
                           "je_kategorie": [{"kategorie_name": "Miete", "ausgaben": 12000}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/finanzen/euer", params={"jahr": 2026})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "finanzen" and out["ok"] is True
        assert out["euer"]["ausgaben"] == 12000

    assert erfasst["url"] == "http://127.0.0.1:8210/api/steuer/jahr"
    assert erfasst["params"] == {"jahr": 2026, "nur_steuer": 1}  # nur steuer-relevante Ausgaben


def test_euer_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        assert c.get("/api/querverbindung/gibtsnicht/euer").status_code == 404


def test_euer_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/finanzen/euer")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False and body["euer"] == {} and "erreichbar" in body["fehler"]


# ===================== A5: Bereichs-Querverbindungen V17/V18/V19 (docs/34) ===========
def test_finanzspur_relay_holt_money_bereich(monkeypatch):
    """V17: proxyt Moneys per-Bereich-Finanzspur (GET /api/bereich/finanzspur, kontext)."""
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"kontext": "geschaeft-x", "einnahmen": 50000,
                           "ausgaben": 12000, "saldo": 38000})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/finanzen/finanzspur",
                  params={"kontext": "geschaeft-x", "jahr": 2026})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "finanzen" and out["ok"] is True
        assert out["finanzspur"]["saldo"] == 38000

    assert erfasst["url"] == "http://127.0.0.1:8210/api/bereich/finanzspur"
    assert erfasst["params"] == {"kontext": "geschaeft-x", "jahr": 2026}


def test_finanzspur_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        assert c.get("/api/querverbindung/gibtsnicht/finanzspur").status_code == 404


def test_finanzspur_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        body = c.get("/api/querverbindung/finanzen/finanzspur", params={"kontext": "x"}).json()
        assert body["ok"] is False and body["finanzspur"] == {} and "erreichbar" in body["fehler"]


def test_bereich_social_relay_holt_management(monkeypatch):
    """V18: proxyt Managements per-Bereich-Social-Aktivität (GET /api/bereich/social)."""
    panels._contract_apps.clear()
    panels.register_contract_app("management", "http://127.0.0.1:8213")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, {"kontext": "geschaeft-x", "geplant": 3,
                           "veroeffentlicht": 12, "bots": 2})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/management/bereich-social",
                  params={"kontext": "geschaeft-x"})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "management" and out["ok"] is True and out["social"]["geplant"] == 3

    assert erfasst["url"] == "http://127.0.0.1:8213/api/bereich/social"
    assert erfasst["params"] == {"kontext": "geschaeft-x"}


def test_bereich_social_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("management", "http://127.0.0.1:8213")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        body = c.get("/api/querverbindung/management/bereich-social", params={"kontext": "x"}).json()
        assert body["ok"] is False and body["social"] == {} and "erreichbar" in body["fehler"]


def test_kategorie_relay_holt_memory_ordner(monkeypatch):
    """V19: proxyt Memorys Kategorie-/Ordner-Notizen (GET /api/kategorie, ordner=memory_ref)."""
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["url"] = url
        erfasst["params"] = params
        return _Resp(200, [{"titel": "Vorlesung 1", "ordner": "Studium Informatik"}])

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        r = c.get("/api/querverbindung/memory/kategorie",
                  params={"ordner": "Studium Informatik", "limit": 5})
        assert r.status_code == 200
        out = r.json()
        assert out["ziel"] == "memory" and out["ok"] is True and out["anzahl"] == 1
        assert out["notizen"][0]["titel"] == "Vorlesung 1"

    assert erfasst["url"] == "http://127.0.0.1:8212/api/kategorie"
    assert erfasst["params"] == {"ordner": "Studium Informatik", "limit": 5}


def test_kategorie_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")

    def boom(url, params, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        body = c.get("/api/querverbindung/memory/kategorie", params={"ordner": "x"}).json()
        assert body["ok"] is False and body["notizen"] == [] and "erreichbar" in body["fehler"]


# ── BER-1: kanon-Durchreichung + kanon-status-Relay (docs/67) ───────────────────

def test_finanzspur_relay_reicht_kanon_durch(monkeypatch):
    """BER-1 (docs/67 §3.3): kanon wird durchgereicht — aber nur wenn gesetzt."""
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["params"] = params
        return _Resp(200, {"saldo": 1})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        c.get("/api/querverbindung/finanzen/finanzspur",
              params={"kontext": "x", "jahr": 2026, "kanon": "A-1"})
        assert erfasst["params"] == {"kontext": "x", "jahr": 2026, "kanon": "A-1"}
        c.get("/api/querverbindung/finanzen/finanzspur", params={"kontext": "x", "jahr": 2026})
        assert "kanon" not in erfasst["params"]


def test_bereich_social_relay_reicht_kanon_durch(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("management", "http://127.0.0.1:8213")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["params"] = params
        return _Resp(200, {"bots": 0})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        c.get("/api/querverbindung/management/bereich-social",
              params={"kontext": "x", "kanon": "A-2"})
        assert erfasst["params"] == {"kontext": "x", "kanon": "A-2"}
        c.get("/api/querverbindung/management/bereich-social", params={"kontext": "x"})
        assert "kanon" not in erfasst["params"]


def test_kategorie_relay_reicht_kanon_durch(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("memory", "http://127.0.0.1:8212")
    erfasst = {}

    def fake_get(url, params, timeout):
        erfasst["params"] = params
        return _Resp(200, [])

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        c.get("/api/querverbindung/memory/kategorie",
              params={"ordner": "o", "limit": 5, "kanon": "A-3"})
        assert erfasst["params"] == {"ordner": "o", "limit": 5, "kanon": "A-3"}
        c.get("/api/querverbindung/memory/kategorie", params={"ordner": "o", "limit": 5})
        assert "kanon" not in erfasst["params"]


def test_kanon_status_relay_holt_feed(monkeypatch):
    """BER-1 (docs/67 §3.3): Core proxyt den kanon-status-Feed der Ziel-App (OHNE params)."""
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")
    erfasst = {}

    def fake_get(url, timeout=None):        # der Relay ruft httpx.get(url, timeout=…) OHNE params
        erfasst["url"] = url
        return _Resp(200, {"ok": True,
                           "bereiche": [{"id": "m1", "kanon_id": "A1", "kontext": ""}],
                           "anker_extra": {"ordner": ["X"]}})

    monkeypatch.setattr(httpx, "get", fake_get)
    with TestClient(app) as c:
        out = c.get("/api/querverbindung/finanzen/kanon-status").json()
    assert erfasst["url"] == "http://127.0.0.1:8210/api/bereiche/kanon-status"
    assert out["ok"] is True and out["bereiche"][0]["kanon_id"] == "A1"
    assert out["anker_extra"]["ordner"] == ["X"]


def test_kanon_status_relay_unbekanntes_ziel_404():
    panels._contract_apps.clear()
    with TestClient(app) as c:
        assert c.get("/api/querverbindung/gibtsnicht/kanon-status").status_code == 404


def test_kanon_status_relay_offline_ehrlich(monkeypatch):
    panels._contract_apps.clear()
    panels.register_contract_app("finanzen", "http://127.0.0.1:8210")

    def boom(url, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(app) as c:
        body = c.get("/api/querverbindung/finanzen/kanon-status").json()
        assert body["ok"] is False and body["bereiche"] == [] and "erreichbar" in body["fehler"]
