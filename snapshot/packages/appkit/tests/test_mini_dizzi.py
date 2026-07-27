"""Tests Mini-Dizzi (Vertrag 1.5): App-KI-Slot, Ollama-Fallback, Verbund-Gating.
Netzfrei — Ollama wird injiziert; die App-KI ist eine Test-Funktion."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit import auth
from appkit.app import create_app
from appkit.auth import DEFAULT_USER_ID
from appkit.db import Database
from appkit.manifest import AppManifest, AuthInfo
from appkit.mini_dizzi import MiniDizzi
from appkit.summary import Kpi


@pytest.fixture(autouse=True)
def _clean_auth():
    auth.reset_identity_provider()
    yield
    auth.reset_identity_provider()


def _manifest(status="vorbereitet"):
    return AppManifest(id="mdapp", name="MD-App", brand="Dizz MD",
                       version="0.1.0", port=8295, auth=AuthInfo(status=status))


def _memory_stub(treffer):
    """Netzfreier Rück-Lese-Stub (statt echtem Core-Relay): liefert feste Treffer."""
    def _get(url, params):
        class R:
            status_code = 200
            @staticmethod
            def json():
                return {"ok": True, "treffer": list(treffer), "anzahl": len(treffer)}
        return R()
    return _get


_no_memory = _memory_stub([])   # Default: keine Treffer ⇒ Rück-Lese netzfrei + leer


def _md(tmp_path, status="vorbereitet"):
    db = Database(tmp_path / "md.sqlite")
    return MiniDizzi(_manifest(status), db,
                     summary_fn=lambda: [Kpi(id="n", label="Artikel", value=42)],
                     memory_get=_no_memory), db


# ------------------------------------------------------- App-KI-Slot

def test_app_ki_wird_bevorzugt(tmp_path):
    md, _ = _md(tmp_path)
    md.set_app_ki(lambda f: f"Antwort auf: {f}")
    out = md.frage("Wie viele Artikel?")
    assert out["quelle"] == "app_ki"
    assert "Wie viele Artikel?" in out["antwort"]


def test_app_ki_dict_form(tmp_path):
    md, _ = _md(tmp_path)
    md.set_app_ki(lambda f: {"antwort": "42 Artikel", "belege": ["x"]})
    assert md.frage("?")["antwort"] == "42 Artikel"


def test_kaputte_app_ki_faellt_zurueck(tmp_path):
    md, _ = _md(tmp_path)
    def kaputt(f):
        raise RuntimeError("Modell weg")
    md.set_app_ki(kaputt)
    # Kein Ollama injiziert ⇒ ehrlicher Fallback-Hinweis, kein Absturz
    out = md.frage("?")
    assert out["quelle"] in ("kein_ollama", "fallback_ollama")


def test_leere_frage(tmp_path):
    md, _ = _md(tmp_path)
    assert md.frage("   ")["quelle"] == "leer"


# ------------------------------------------------------- Ollama-Fallback

def test_ollama_fallback_mit_app_kontext(tmp_path):
    md, _ = _md(tmp_path)
    gesehen = {}

    def fake_ollama(url, json):
        gesehen["system"] = json["messages"][0]["content"]
        gesehen["format"] = json["format"]

        class R:
            status_code = 200
            @staticmethod
            def json():
                return {"message": {"content": '{"antwort":"Es sind 42 Artikel."}'}}
        return R()

    md._http_post = fake_ollama
    out = md.frage("Wie viele Artikel?")
    assert out["quelle"] == "fallback_ollama" and "42" in out["antwort"]
    assert "Dizz MD" in gesehen["system"]              # App-Kontext im Prompt
    assert "Artikel=42" in gesehen["system"]            # KPI im Kontext
    assert isinstance(gesehen["format"], dict)          # JSON-Schema, nicht "json"


def test_ollama_aus_ehrlich(tmp_path):
    md, _ = _md(tmp_path)
    def kaputt(url, json):
        raise ConnectionError("Ollama aus")
    md._http_post = kaputt
    assert md.frage("?")["quelle"] == "kein_ollama"     # kein Erfinden


# ------------------------------------------------------- Rück-Lese (docs/26 §4c)

def test_rueck_lese_ergaenzt_kontext(tmp_path):
    """Bei aktivem Setting fließen Memory-Treffer in den Fallback-Prompt (app-übergreifend)."""
    md, _ = _md(tmp_path)
    md._memory_get = _memory_stub([{"titel": "EZB-Zinsentscheid", "auszug": "Leitzins 4,25 %"}])
    gesehen = {}
    def fake_ollama(url, json):
        gesehen["system"] = json["messages"][0]["content"]
        class R:
            status_code = 200
            @staticmethod
            def json(): return {"message": {"content": '{"antwort":"ok"}'}}
        return R()
    md._http_post = fake_ollama
    md.frage("Was war mit der EZB?")
    assert "EZB-Zinsentscheid" in gesehen["system"]      # Rück-Lese-Treffer im Prompt
    assert "Dizz Memory" in gesehen["system"]


def test_rueck_lese_aus_kein_zugriff(tmp_path):
    """Setting aus ⇒ memory_get wird NICHT befragt (rein lokal)."""
    md, db = _md(tmp_path)
    db.setting_put(DEFAULT_USER_ID, "ki_wissen_rueck_lese", False)
    befragt = {"n": 0}
    def zaehl_get(url, params):
        befragt["n"] += 1
        class R:
            status_code = 200
            @staticmethod
            def json(): return {"ok": True, "treffer": [], "anzahl": 0}
        return R()
    md._memory_get = zaehl_get
    assert md._rueck_lese("egal") == ""
    assert befragt["n"] == 0                              # gar nicht erst gefragt


# ------------------------------------------------------- Verbund-Gating

def test_lauscht_lokal_standalone_vs_verbund(tmp_path):
    md_solo, db1 = _md(tmp_path / "a", status="vorbereitet")  # standalone
    md_verb, db2 = _md(tmp_path / "b", status="aktiv")        # im Verbund
    assert md_solo.lauscht_lokal() is True    # standalone ⇒ App lauscht selbst
    assert md_verb.lauscht_lokal() is False   # im Verbund ⇒ zentral Dizzi
    # Override: 'lokal' lauscht immer, 'aus' nie
    db2.setting_put(DEFAULT_USER_ID, "voice_modus", "lokal")
    assert md_verb.lauscht_lokal() is True
    db1.setting_put(DEFAULT_USER_ID, "voice_modus", "aus")
    assert md_solo.lauscht_lokal() is False


# ------------------------------------------------------- HTTP / create_app

def _app(tmp_path, status="vorbereitet"):
    db = Database(tmp_path / "app.sqlite")
    app = create_app(_manifest(status), db,
                     summary_fn=lambda: [Kpi(id="n", label="Artikel", value=42)])
    if getattr(app.state, "mini_dizzi", None) is not None:
        app.state.mini_dizzi._memory_get = _no_memory   # Rück-Lese netzfrei halten
    return app, db


def test_endpoints_und_gate(tmp_path):
    app, db = _app(tmp_path)
    c = TestClient(app)
    st = c.get("/api/ki/status").json()
    assert st["app"] == "mdapp" and st["lauscht_lokal"] is True
    assert st["wort"] == "hey_dizzi"
    # Frage liefert IMMER 200 + Antwort (Fallback ohne Ollama ⇒ ehrlicher Hinweis)
    a = c.post("/api/ki/frage", json={"frage": "Status?"})
    assert a.status_code == 200 and a.json()["antwort"]
    # Settings im Schema (KI + Vernetzung)
    schema = c.get("/api/settings/schema").json()["kategorien"]
    ki = {d["key"] for d in schema["ki"]}
    netz = {d["key"] for d in schema["vernetzung"]}
    assert {"mini_dizzi_aktiv", "ki_wissen_rueck_lese"} <= ki
    assert {"voice_modus", "voice_wort"} <= netz


def test_deaktiviert(tmp_path):
    app, db = _app(tmp_path)
    db.setting_put(DEFAULT_USER_ID, "mini_dizzi_aktiv", False)
    a = TestClient(app).post("/api/ki/frage", json={"frage": "x"})
    assert a.json()["quelle"] == "aus"
