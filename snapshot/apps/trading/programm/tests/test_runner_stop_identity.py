"""Regressionstests: ``runner._stop_locked`` killt NUR identitäts-verifizierte Prozesse.

Hintergrund (Vorfall O11, 2026-06-16): der Stop sammelte Kill-Kandidaten u.a. aus der persistierten
``runners.json``-PID und killte jede PID, die bloß existierte (``_pid_alive``) — OHNE Abgleich, dass die
PID noch zu DIESEM Bot gehört. Windows recycelt PIDs ⇒ eine veraltete Eintrags-PID konnte den lebenden
Prozess eines ANDEREN Bots treffen (``/stop`` von O13 tötete O11). Fix: nur Prozesse killen, deren
Kommandozeile ``config_<bot_id>.json`` referenziert (``_verified_pids_for``).

Rein/ohne Netz/DB: alle Prozess-/IO-Berührungen sind gemockt.
"""
import subprocess

from backend.app import runner


def _fake_run_capture(killed):
    """Ersetzt ``subprocess.run`` und protokolliert jeden (taskkill-)Aufruf."""
    def _run(cmd, *a, **k):
        killed.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return _run


def _patch_common(monkeypatch):
    """IO/Registry/Audit neutralisieren — die Tests prüfen nur, WELCHE PIDs getaskkillt werden."""
    monkeypatch.setattr(runner, "_load_pids", lambda: {})
    monkeypatch.setattr(runner, "_save_pids", lambda d: None)
    monkeypatch.setattr(runner, "_prune_stale_pids", lambda d: d)
    monkeypatch.setattr(runner, "_procs", {})
    monkeypatch.setattr(runner, "update_status", lambda *a, **k: None)
    monkeypatch.setattr(runner.audit, "record", lambda *a, **k: None)


def test_stop_does_not_kill_foreign_recycled_pid(monkeypatch):
    """Kern-Regression: eine veraltete runners.json-PID, die inzwischen einem FREMDEN lebenden Bot
    gehört, darf von ``/stop`` NICHT gekillt werden."""
    FOREIGN_PID = 33872   # gehört Bot B (config_bbb222.json) — der lebt und soll weiterlaufen
    # Nur Bot B läuft. Bot A ('aaa111') hat KEINEN eigenen Prozess, aber runners.json zeigt (stale)
    # ausgerechnet auf die recycelte FOREIGN_PID.
    monkeypatch.setattr(runner, "_list_bot_processes",
                        lambda: [(FOREIGN_PID, r'TradingBot-Bot.exe -m freqtrade trade '
                                               r'--config "X\config_bbb222.json" --db-url sqlite:///b')])
    _patch_common(monkeypatch)
    monkeypatch.setattr(runner, "_load_pids", lambda: {"aaa111": FOREIGN_PID})  # STALE → fremde PID
    monkeypatch.setattr(runner, "_pid_alive", lambda pid: pid == FOREIGN_PID)
    killed = []
    monkeypatch.setattr(runner.subprocess, "run", _fake_run_capture(killed))

    res = runner._stop_locked("aaa111")

    assert killed == [], f"Es durfte KEIN taskkill abgesetzt werden (fremde PID!), war: {killed}"
    assert res["stopped"] is False
    assert res["status"] == "stopped"


def test_stop_kills_own_verified_pid_without_tree_flag(monkeypatch):
    """Positiv: der eigene (cmdline-verifizierte) Prozess WIRD gekillt — und zwar ohne ``/T``."""
    OWN_PID = 12345
    monkeypatch.setattr(runner, "_list_bot_processes",
                        lambda: [(OWN_PID, r'TradingBot-Bot.exe -m freqtrade trade '
                                           r'--config "X\config_aaa111.json" --db-url sqlite:///a')])
    _patch_common(monkeypatch)
    monkeypatch.setattr(runner, "_pid_alive", lambda pid: True)
    killed = []
    monkeypatch.setattr(runner.subprocess, "run", _fake_run_capture(killed))

    res = runner._stop_locked("aaa111")

    flat = [tok for cmd in killed for tok in cmd]
    assert str(OWN_PID) in flat, f"Eigener Prozess wurde NICHT gekillt: {killed}"
    assert "/T" not in flat, "/T (Baum-Kill) muss entfernt sein — hebelt den Identitätsschutz aus"
    assert res["stopped"] is True


def test_verified_pids_for_no_prefix_collision(monkeypatch):
    """Der ``.json``-Anker verhindert Präfix-Kollisionen: 'deadbe' trifft nicht 'deadbeef'."""
    monkeypatch.setattr(runner, "_list_bot_processes", lambda: [
        (111, r'... --config "X\config_deadbeef.json" ...'),
        (222, r'... --config "X\config_deadbe.json" ...'),
    ])
    assert runner._verified_pids_for("deadbe") == [222]
    assert runner._verified_pids_for("deadbeef") == [111]


def test_verified_pids_for_empty_when_no_match(monkeypatch):
    """Kein laufender Prozess dieses Bots → leere Liste (nichts zu killen)."""
    monkeypatch.setattr(runner, "_list_bot_processes",
                        lambda: [(1, r'--config "X\config_other1.json"')])
    assert runner._verified_pids_for("aaa111") == []
