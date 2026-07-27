"""Tests: Flotten-Reconcile + Resume-Watchdog.

Schließt die Lücke aus dem Vorfall O15 „Eröffnung US": ein toter ``paper_running``-Bot wird nachgestartet,
ein Fehlschlag wird MIT GRUND auditiert (vorher still als ``failed=1`` gezählt), und der Watchdog hämmert
nicht endlos auf einen kaputten Bot (Crash-Loop-Backoff). Rein, ohne echte Prozesse/DB (alles gemockt).
"""
from types import SimpleNamespace

import pytest

from backend.app import main


def _bot(bid, status="paper_running", name=None):
    return SimpleNamespace(id=bid, status=status, name=name or bid)


@pytest.fixture
def audit_log(monkeypatch):
    log = []
    monkeypatch.setattr(main.audit, "record", lambda ev, **kw: log.append((ev, kw)))
    return log


def test_reconcile_restarts_dead_running_bot(monkeypatch, audit_log):
    monkeypatch.setattr(main.registry, "list_bots", lambda: [_bot("a")])
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": False})
    started = []
    monkeypatch.setattr(main.runner, "start", lambda bid: (started.append(bid) or {"ok": True}))
    res = main._reconcile_fleet("startup", stagger_s=0)
    assert res["resumed"] == ["a"] and res["failed"] == [] and started == ["a"]


def test_reconcile_skips_stopped_and_already_running(monkeypatch, audit_log):
    bots = [_bot("stopped1", status="stopped"), _bot("running1")]
    monkeypatch.setattr(main.registry, "list_bots", lambda: bots)
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": True})  # running1 läuft schon
    monkeypatch.setattr(main.runner, "start", lambda bid: pytest.fail("start darf nicht aufgerufen werden"))
    res = main._reconcile_fleet("startup", stagger_s=0)
    assert res["resumed"] == [] and res["failed"] == []   # gestoppt = aus, laufend = übersprungen


def test_reconcile_logs_failure_reason(monkeypatch, audit_log):
    monkeypatch.setattr(main.registry, "list_bots", lambda: [_bot("x", name="O15 Eroeffnung US")])
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": False})
    monkeypatch.setattr(main.runner, "start", lambda bid: {"ok": False, "error": "Config fehlt"})
    res = main._reconcile_fleet("startup", stagger_s=0)
    assert res["failed"] == ["x"]
    fails = [kw for ev, kw in audit_log if ev == "fleet_resume_failed"]
    assert fails and fails[0]["bot_id"] == "x" and fails[0]["reason"] == "Config fehlt"   # NICHT mehr still


def test_watchdog_crashloop_backoff(monkeypatch, audit_log):
    monkeypatch.setattr(main.registry, "list_bots", lambda: [_bot("z")])
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": False})
    monkeypatch.setattr(main.runner, "start", lambda bid: {"ok": False, "error": "boom"})
    monkeypatch.setattr(main, "_resume_attempts", {})   # frischer Versuchszähler
    for _ in range(main.RESUME_MAX_TRIES_PER_HOUR):
        main._reconcile_fleet("watchdog", stagger_s=0)
    res = main._reconcile_fleet("watchdog", stagger_s=0)   # Limit erreicht → Backoff
    assert res["skipped"] == ["z"] and res["failed"] == []


def test_startup_trigger_has_no_backoff(monkeypatch, audit_log):
    # Der Crash-Loop-Schutz gilt nur im Watchdog-Modus; der Startup-Resume versucht IMMER (Backoff egal).
    monkeypatch.setattr(main.registry, "list_bots", lambda: [_bot("s")])
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": False})
    monkeypatch.setattr(main.runner, "start", lambda bid: {"ok": False, "error": "x"})
    monkeypatch.setattr(main, "_resume_attempts", {"s": [main.time.time()] * 99})  # „viele" frühere Versuche
    res = main._reconcile_fleet("startup", stagger_s=0)
    assert res["failed"] == ["s"] and res["skipped"] == []   # Startup ignoriert den Watchdog-Backoff
