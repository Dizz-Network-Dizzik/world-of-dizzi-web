"""Tests der funktionalen Lebendigkeit (freqtrade-Heartbeat-Alter → health ok/stale/unknown/stopped).

Rein, ohne Popen/Netz/DB: ``_health_for``/``log_age_s`` lesen nur das Logfile-mtime im (gepatchten)
LOG_DIR. Deckt die „tot-aber-läuft"-Lücke ab: Prozess lebt, aber der Heartbeat ist eingefroren.
"""
import os
import time

from backend.app import runner


def _mk_log(tmp_path, bot_id, age_s):
    lf = tmp_path / f"bot_{bot_id}.log"
    lf.write_text("... Bot heartbeat. state='RUNNING'\n", encoding="utf-8")
    t = time.time() - age_s
    os.utime(lf, (t, t))
    return lf


def test_health_ok_when_log_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    _mk_log(tmp_path, "aaa111", age_s=30)                 # frischer Heartbeat (~30 s)
    h = runner._health_for("aaa111", running=True)
    assert h["health"] == "ok" and h["healthy"] is True
    assert h["log_age_s"] is not None and h["log_age_s"] < runner.LOG_STALE_AFTER_S


def test_health_stale_when_heartbeat_frozen(tmp_path, monkeypatch):
    """Der Kernfall: Prozess läuft, aber das Log ist seit > Schwelle eingefroren = Zombie."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    _mk_log(tmp_path, "bbb222", age_s=runner.LOG_STALE_AFTER_S + 120)
    h = runner._health_for("bbb222", running=True)
    assert h["health"] == "stale" and h["healthy"] is False
    assert h["log_age_s"] > runner.LOG_STALE_AFTER_S


def test_health_unknown_when_running_without_log(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)      # leer → kein Logfile (frisch gestartet)
    h = runner._health_for("ccc333", running=True)
    assert h["health"] == "unknown" and h["log_age_s"] is None and h["healthy"] is None


def test_health_stopped_ignores_old_log(tmp_path, monkeypatch):
    """Nicht laufend → 'stopped', selbst bei uraltem Logfile (kein Fehlalarm als 'stale')."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    _mk_log(tmp_path, "ddd444", age_s=99999)
    h = runner._health_for("ddd444", running=False)
    assert h["health"] == "stopped" and h["healthy"] is None and h["log_age_s"] is None


def test_log_age_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    assert runner.log_age_s("nope999") is None


def test_status_merges_health_keys(tmp_path, monkeypatch):
    """status() trägt die health-Felder zusätzlich; 'running' bleibt Prozess-Existenz (hier: nicht laufend)."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "_procs", {})
    monkeypatch.setattr(runner, "_scan_bot_pids", lambda *a, **k: {})
    monkeypatch.setattr(runner, "_load_pids", lambda: {})
    st = runner.status("eee555")
    assert st["running"] is False and st["health"] == "stopped"
    assert "log_age_s" in st and "healthy" in st


def test_status_no_pid_reuse_false_positive(tmp_path, monkeypatch):
    """Regression: ein lautlos toter Bot, dessen Alt-PID vom OS recycelt wurde (lebt, gehört aber
    inzwischen einem ANDEREN Prozess), darf NICHT als running=True gemeldet werden — sonst übersieht
    ihn der Resume-Watchdog und er bleibt tot liegen (F07/O03-Muster). running muss identitätssicher
    über die cmdline (config_<id>.json) bestimmt werden, nicht über die nackte PID-Lebendigkeit."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "_procs", {})                          # kein Popen-Handle
    monkeypatch.setattr(runner, "_scan_bot_pids", lambda *a, **k: {})  # cmdline-Cache-Miss
    monkeypatch.setattr(runner, "_load_pids", lambda: {"ghost777": 4242})  # persistierte Alt-PID
    monkeypatch.setattr(runner, "_pid_alive", lambda pid: True)        # PID lebt (recycelt = Fremdprozess)
    monkeypatch.setattr(runner, "_verified_pids_for", lambda bid: [])  # ABER kein echter Bot-Prozess
    st = runner.status("ghost777")
    assert st["running"] is False, "PID-Reuse-Fehlalarm: toter Bot fälschlich als running gemeldet"


def test_status_running_via_verified_cmdline(tmp_path, monkeypatch):
    """Positivfall: ein laufender Bot ohne Popen-Handle und ohne Cache-Treffer (z. B. nicht-hex
    'mastermeta', den der hex-basierte _scan_bot_pids auslässt) wird über die identitätssicher
    verifizierte cmdline-PID korrekt als running erkannt."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "_procs", {})
    monkeypatch.setattr(runner, "_scan_bot_pids", lambda *a, **k: {})
    monkeypatch.setattr(runner, "_load_pids", lambda: {})
    monkeypatch.setattr(runner, "_verified_pids_for", lambda bid: [9999])
    st = runner.status("mastermeta")
    assert st["running"] is True and st["pid"] == 9999 and st["source"] == "cmdline-verified"
