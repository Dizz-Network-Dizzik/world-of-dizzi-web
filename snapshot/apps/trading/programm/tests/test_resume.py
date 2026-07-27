"""Tests: Auto-Resume der Flotte nach Systemausfall (main._resume_fleet)."""
from types import SimpleNamespace

from backend.app import main


def _bot(bid, status):
    return SimpleNamespace(id=bid, status=status)


def _setup(monkeypatch, bots, running_ids, start_results=None):
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)            # Test nicht ausbremsen
    monkeypatch.setattr(main.audit, "record", lambda *a, **k: None)
    monkeypatch.setattr(main.registry, "list_bots", lambda: list(bots))
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": bid in running_ids})
    started = []

    def fake_start(bid):
        started.append(bid)
        return (start_results or {}).get(bid, {"ok": True})

    monkeypatch.setattr(main.runner, "start", fake_start)
    return started


def test_resume_starts_only_crashed_running_bots(monkeypatch):
    # „running"-Status aber Prozess weg -> nachstarten; gestoppte/neue/laufende NICHT anfassen.
    bots = [_bot("a", "paper_running"), _bot("b", "paper_running"), _bot("c", "stopped"),
            _bot("d", "created"), _bot("e", "live_running")]
    started = _setup(monkeypatch, bots, running_ids={"b"})              # b läuft noch
    res = main._resume_fleet(stagger_s=0, initial_delay_s=0)
    assert started == ["a", "e"]                                        # nur die gecrashten running-Bots
    assert res["resumed"] == ["a", "e"] and res["failed"] == []


def test_resume_noop_when_all_running(monkeypatch):
    bots = [_bot("a", "paper_running"), _bot("b", "paper_running")]
    started = _setup(monkeypatch, bots, running_ids={"a", "b"})
    res = main._resume_fleet(stagger_s=0, initial_delay_s=0)
    assert started == [] and res["resumed"] == [] and res["failed"] == []


def test_resume_continues_after_bot_error(monkeypatch):
    # Ein Fehler bei einem Bot darf den Resume der übrigen nicht abbrechen.
    bots = [_bot("a", "paper_running"), _bot("x", "paper_running"), _bot("z", "paper_running")]
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)
    monkeypatch.setattr(main.audit, "record", lambda *a, **k: None)
    monkeypatch.setattr(main.registry, "list_bots", lambda: list(bots))
    monkeypatch.setattr(main.runner, "status", lambda bid: {"running": False})
    started = []

    def flaky_start(bid):
        if bid == "x":
            raise RuntimeError("boom")
        started.append(bid)
        return {"ok": True}

    monkeypatch.setattr(main.runner, "start", flaky_start)
    res = main._resume_fleet(stagger_s=0, initial_delay_s=0)
    assert started == ["a", "z"]
    assert res["resumed"] == ["a", "z"] and res["failed"] == ["x"]
