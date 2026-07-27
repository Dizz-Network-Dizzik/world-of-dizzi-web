"""Core-Health-Watch (R-4/R-5): Zustands-Wechsel-Meldungen + Ollama-Reanimation.
Deterministisch — Checks/Reanimator/Zeit werden injiziert (kein echtes httpx/Ollama)."""

from __future__ import annotations

import pytest

from app import db
from app.ai import health_watch

U = "test-user"


@pytest.fixture(autouse=True)
def _reset_state():
    health_watch._state.clear()
    health_watch._last_reanimate = 0.0
    yield
    health_watch._state.clear()


def _notices():
    return db.get_conn().execute(
        "SELECT severity, title FROM notices WHERE source='health-watch' ORDER BY created_at"
    ).fetchall()


def test_grundzustand_meldet_nichts():
    """Erster Lauf etabliert den Grundzustand — keine Glocke (nur echte Wechsel)."""
    health_watch.tick(U, checks={"app:x": lambda: True, "ollama": lambda: True},
                      reanimate=lambda now: False)
    assert _notices() == []
    assert health_watch.status() == {"app:x": True, "ollama": True}


def test_ausfall_dann_erholung_melden():
    health_watch.tick(U, checks={"app:x": lambda: True, "ollama": lambda: True}, reanimate=lambda n: False)
    health_watch.tick(U, checks={"app:x": lambda: False, "ollama": lambda: True}, reanimate=lambda n: False)
    n = _notices()
    assert len(n) == 1 and n[0]["severity"] == "warn" and "Ausfall: app:x" in n[0]["title"]
    health_watch.tick(U, checks={"app:x": lambda: True, "ollama": lambda: True}, reanimate=lambda n: False)
    n = _notices()
    assert len(n) == 2 and n[1]["severity"] == "info" and "Wieder" in n[1]["title"]


def test_ollama_ausfall_reanimiert_auch_ohne_wechsel():
    calls: list[float] = []
    health_watch.tick(U, checks={"ollama": lambda: False},
                      reanimate=lambda now: (calls.append(now) or True), now=100.0)
    assert calls == [100.0]
    assert any("Ollama neu gestartet" in r["title"] for r in _notices())


def test_ollama_up_keine_reanimation():
    calls: list[float] = []
    health_watch.tick(U, checks={"ollama": lambda: True},
                      reanimate=lambda now: (calls.append(now) or True))
    assert calls == []


def test_check_wirft_gilt_als_offline():
    def kaputt() -> bool:
        raise RuntimeError("Netz weg")
    health_watch.tick(U, checks={"app:y": lambda: True}, reanimate=lambda n: False)
    health_watch.tick(U, checks={"app:y": kaputt}, reanimate=lambda n: False)
    n = _notices()
    assert len(n) == 1 and "Ausfall: app:y" in n[0]["title"]


def test_default_checks_enthaelt_tradingbot_und_ollama():
    """F3: Die Legacy-Trading-Kachel wird jetzt zentral mit überwacht (eigenes /health)."""
    checks = health_watch._default_checks()
    assert "app:tradingbot" in checks
    assert "ollama" in checks


def test_ollama_alive_nutzt_runtime_selbstauskunft(monkeypatch):
    """docs/62 runtime-Konsistenz: die Ollama-Probe läuft über die LocalRuntime-
    Selbstauskunft (``providers.runtime().health().ok``) statt direktem ``/api/tags``.
    Kein echtes httpx — die Runtime wird gefakt; ``health().ok`` steuert das Ergebnis."""
    from app.ai import providers
    from appkit.runtime import RuntimeHealth

    class _FakeRT:
        def __init__(self, ok: bool):
            self._ok = ok

        def health(self) -> RuntimeHealth:
            return RuntimeHealth(ok=self._ok, laufzeit="ollama")

    monkeypatch.setattr(providers, "runtime", lambda: _FakeRT(True))
    assert health_watch._ollama_alive() is True
    monkeypatch.setattr(providers, "runtime", lambda: _FakeRT(False))
    assert health_watch._ollama_alive() is False


def test_ollama_alive_fail_safe_bei_runtime_fehler(monkeypatch):
    """Fail-safe (der Wächter darf nie werfen): fällt der Runtime-/DB-Zugriff aus,
    gilt Ollama als offline (False) statt einer Exception."""
    from app.ai import providers

    def _boom():
        raise RuntimeError("DB/Runtime weg")

    monkeypatch.setattr(providers, "runtime", _boom)
    assert health_watch._ollama_alive() is False


def test_reanimate_cooldown(monkeypatch):
    popen_calls: list = []
    monkeypatch.setattr(health_watch.subprocess, "Popen", lambda *a, **k: popen_calls.append(a))
    assert health_watch._reanimate_ollama(now=1000.0) is True            # erster Versuch
    assert health_watch._reanimate_ollama(now=1010.0) is False           # Cooldown aktiv
    assert health_watch._reanimate_ollama(now=1000.0 + health_watch.REANIMATE_COOLDOWN_S + 1) is True
    assert len(popen_calls) == 2
