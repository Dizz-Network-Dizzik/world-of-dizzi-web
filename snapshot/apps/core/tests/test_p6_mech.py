"""P6 mechanische Charge — Core-Teil: KA-M2 (Auto-Discovery aus NETZ_APPS),
KA-N1 (Settings-Token-Maske), KA-N3 (Ollama-Offline-Einrichtungshinweis)."""
from __future__ import annotations

from app import db, panels
from app.ai import analyst, health_watch
from app.config import DEFAULT_USER_ID


# --- KA-M2: Auto-Discovery -------------------------------------------------------------

def test_discover_registriert_nur_erreichbare(monkeypatch):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"contract": "1.5", "status": "ok", "kpis": []}

    def fake_get(url, timeout=None):
        if ":8216/" in url:                 # nur news (:8216) antwortet
            return _Resp()
        raise RuntimeError("nicht erreichbar")

    # State isolieren (panels-Globals werden nicht vom conftest zurückgesetzt).
    monkeypatch.setattr(panels, "_contract_apps", {})
    monkeypatch.setattr(panels, "_registry", dict(panels._registry))
    monkeypatch.setattr(panels.httpx, "get", fake_get)

    neu = panels.discover_contract_apps()
    assert neu == 1 and "news" in panels.contract_apps()
    assert "core" not in panels.contract_apps()          # Zentrale nie
    assert "tradingbot" not in panels.contract_apps()    # Legacy nie über Discovery
    assert panels.discover_contract_apps() == 0          # kein Doppel-Register


def test_discover_ueberschreibt_env_override_nicht(monkeypatch):
    def fake_get(url, timeout=None):
        class _R:
            def raise_for_status(self): pass
            def json(self): return {"status": "ok", "kpis": []}
        return _R()                          # alles „erreichbar"

    monkeypatch.setattr(panels, "_contract_apps", {"news": "http://custom:9999"})
    monkeypatch.setattr(panels, "_registry", dict(panels._registry))
    monkeypatch.setattr(panels.httpx, "get", fake_get)
    panels.discover_contract_apps()
    assert panels.contract_apps()["news"] == "http://custom:9999"   # Override bleibt


# --- KA-N1: Settings-Token-Maske -------------------------------------------------------

def test_settings_maskiert_geheime_keys():
    from app.main import get_settings
    db.setting_put(DEFAULT_USER_ID, "mcp_gateway_token", "s3cr3t")
    db.setting_put(DEFAULT_USER_ID, "api_secret", "abc")
    db.setting_put(DEFAULT_USER_ID, "llm_modell", "qwen3:4b")
    db.setting_put(DEFAULT_USER_ID, "leerer_token", "")
    s = get_settings()
    assert s["mcp_gateway_token"] == "•••"   # token ⇒ maskiert
    assert s["api_secret"] == "•••"          # secret ⇒ maskiert
    assert s["llm_modell"] == "qwen3:4b"     # harmlos ⇒ roh
    assert s["leerer_token"] == ""           # nicht gesetzt ⇒ nicht maskiert


# --- KA-N3: Ollama-Offline-Hinweis -----------------------------------------------------

def test_ollama_offline_gibt_genau_einen_hinweis():
    health_watch._state.clear()              # Prozess-State isolieren
    for t in (100.0, 200.0):                 # zwei Ticks, Ollama down
        health_watch.tick(DEFAULT_USER_ID, checks={"ollama": lambda: False},
                          reanimate=lambda n: False, now=t)
    hinweise = [n for n in analyst.notices(DEFAULT_USER_ID)
                if n["title"] == "Lokale KI (Ollama) nicht erreichbar"]
    assert len(hinweise) == 1                # 12-h-Dedupe deckelt trotz 2 Ticks
