"""Tests des universellen Connector-Gerüsts (appkit/connectors.py, docs/36 W4)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from appkit.connectors import (ConnectorRegistry, DormantConnector,
                               ExternalConnector, KonnektorNichtVerbunden,
                               TokenConnector, connectors_router)


class _Telegram(DormantConnector):
    id = "telegram"; label = "Telegram"; kind = "messenger"; richtung = "beides"
    sensitivity = "hoechst"; aktivierung = "Bot-Token im Tresor hinterlegen"
    token_name = "telegram_bot_token"; permissions = ("read:messages", "send:messages")


class _Email(ExternalConnector):
    id = "email"; label = "E-Mail"; kind = "messenger"; richtung = "beides"
    def verfuegbar(self) -> bool: return True
    def lesen(self, **kw): return [{"von": "a@b.c", "betreff": "hi"}]


def test_dormant_ist_ehrlich_nicht_verbunden():
    c = _Telegram()
    assert c.verfuegbar() is False
    info = c.info()
    assert info.verbunden is False and info.dormant is True
    assert info.kind == "messenger" and info.richtung == "beides"
    assert "Token" in info.hinweis
    with pytest.raises(KonnektorNichtVerbunden):
        c.lesen()


def test_aktiver_connector_liest():
    c = _Email()
    info = c.info()
    assert info.verbunden is True and info.dormant is False
    assert c.lesen()[0]["von"] == "a@b.c"


def test_registry_register_get_status():
    reg = ConnectorRegistry()
    reg.register(_Email())
    reg.register(_Telegram())
    assert reg.get("email") is not None
    assert {c.id for c in reg.liste()} == {"email", "telegram"}
    st = reg.status()
    verbunden = {c["id"]: c["verbunden"] for c in st}
    assert verbunden == {"email": True, "telegram": False}


def test_registry_lehnt_doppelt_und_falsche_richtung_ab():
    reg = ConnectorRegistry()
    reg.register(_Email())
    with pytest.raises(ValueError):
        reg.register(_Email())                      # doppelte id

    class _Bad(DormantConnector):
        id = "bad"; richtung = "quatsch"
    with pytest.raises(ValueError):
        reg.register(_Bad())                        # unbekannte richtung


def test_contract_senden_ist_hitl_slot():
    """P5.1: senden() ist ein DEKLARIERENDER Slot — Default wirft (Außenwirkung läuft
    über K4-HITL, nie autonom über den Konnektor)."""
    c = _Email()
    with pytest.raises(KonnektorNichtVerbunden):
        c.senden(text="hallo")


def test_contract_lesen_sicher_best_effort():
    """lesen_sicher() = die „wirft nie"-Variante: dormant ⇒ [] statt Exception."""
    assert _Telegram().lesen_sicher() == []            # nicht verbunden ⇒ leer
    assert _Email().lesen_sicher()[0]["von"] == "a@b.c"  # aktiv ⇒ Daten

    class _Kaputt(ExternalConnector):
        id = "kaputt"
        def verfuegbar(self): return True
        def lesen(self, **kw): raise RuntimeError("adapter weg")
    assert _Kaputt().lesen_sicher() == []              # Adapter-Fehler ⇒ [] (fail-safe)


def test_info_traegt_token_name_und_permissions():
    info = _Telegram().info()
    assert info.token_name == "telegram_bot_token"
    assert info.permissions == ("read:messages", "send:messages")
    # im Status-dict (UI/MCP) ebenfalls sichtbar
    st = _Telegram().status()
    assert st["token_name"] == "telegram_bot_token" and "read:messages" in st["permissions"]


def test_token_connector_vault_bewusst():
    """TokenConnector (vereint admin/konnektoren): „verbunden" ⇔ Token im Tresor."""
    class _Notion(TokenConnector):
        id = "notion"; label = "Notion"; kind = "projekt"; token_name = "notion_key"

    leer = _Notion(vault_get=lambda name: None)
    assert leer.verfuegbar() is False and leer.info().dormant is True
    verbunden = _Notion(vault_get=lambda name: "geheim" if name == "notion_key" else None)
    assert verbunden.verfuegbar() is True and verbunden.info().verbunden is True
    # Tresor-Fehler ⇒ „nicht verbunden" (fail-safe), kein Crash
    def boom(_name): raise RuntimeError("vault weg")
    assert _Notion(vault_get=boom).verfuegbar() is False
    # ohne token_name ⇒ nie verbunden
    class _OhneToken(TokenConnector):
        id = "x"
    assert _OhneToken(vault_get=lambda n: "egal").verfuegbar() is False


def test_router_listet_read_only():
    reg = ConnectorRegistry()
    reg.register(_Email()); reg.register(_Telegram())
    app = FastAPI()
    app.include_router(connectors_router(reg))
    c = TestClient(app)
    r = c.get("/api/konnektoren")
    assert r.status_code == 200
    d = r.json()
    assert d["anzahl"] == 2 and d["verbunden"] == 1
    ids = {k["id"] for k in d["konnektoren"]}
    assert ids == {"email", "telegram"}
