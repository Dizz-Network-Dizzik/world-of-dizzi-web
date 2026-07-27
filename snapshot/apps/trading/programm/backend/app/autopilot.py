"""autopilot.py — selbst-verbessernder Hintergrund-Loop für den MasterMeta-Bot.

Führt in einem Daemon-Thread **periodisch** einen Verbesserungs-Schritt aus (vom Aufrufer als
``step_fn`` injiziert — die eigentliche Optimierungs-/Anwendungs-Logik lebt in ``main.py``, damit
dieses Modul frei von schweren Abhängigkeiten/Zyklen bleibt). Der Schritt ist proposal-only auf der
Engine-Seite: er testet Parameter per Walk-Forward und wendet nur **OOS-validierte** Gewinner an.

Eigenschaften: nicht-blockierend (eigener Thread), debounced/serialisiert (nie zwei Schritte
gleichzeitig), exception-fest (ein Fehler bricht den Loop nie ab), Zustand in ``data/autopilot.json``
persistiert (überlebt Neustarts). 0 Risiko (nur Demo/Paper).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from . import audit, jsonstore
from .config import DATA_DIR

STATE_FILE = DATA_DIR / "autopilot.json"

# Standard: aktiv, alle 6 h ein Schritt. interval_h/enabled sind zur Laufzeit setzbar.
_DEFAULTS = {"enabled": True, "interval_h": 6.0}
_MAX_HISTORY = 30
_TICK_S = 30.0  # Schlaf-Granularität des Loops (damit stop()/Config zeitnah greifen)

_lock = threading.Lock()          # serialisiert State-Datei-Zugriffe
_step_lock = threading.Lock()     # garantiert: nie zwei Schritte gleichzeitig
_thread: threading.Thread | None = None
_stop = threading.Event()
_step_fn: Callable[[str], dict] | None = None
_running_step = False
_last_error: str | None = None


def _load() -> dict:
    try:  # State ist entbehrlich → bei jedem Fehler leer starten (nie den Loop brechen)
        return jsonstore.read_json(STATE_FILE, {})
    except Exception:
        return {}


def _save(state: dict) -> None:
    try:
        jsonstore.write_atomic(STATE_FILE, state)   # atomar + .bak
    except Exception:
        pass


def get_state() -> dict:
    with _lock:
        s = {**_DEFAULTS, **_load()}
    return s


def set_state(patch: dict) -> dict:
    """Aktualisiert erlaubte Felder (enabled/interval_h). Gibt den neuen Zustand zurück."""
    with _lock:
        s = {**_DEFAULTS, **_load()}
        if "enabled" in patch:
            s["enabled"] = bool(patch["enabled"])
        if "interval_h" in patch:
            try:
                s["interval_h"] = max(0.25, float(patch["interval_h"]))
            except (TypeError, ValueError):
                pass
        _save(s)
    audit.record("autopilot_config", enabled=s["enabled"], interval_h=s["interval_h"])
    return s


def status() -> dict:
    s = get_state()
    interval_s = float(s.get("interval_h", 6.0)) * 3600.0
    last = s.get("last_run_ts")
    next_run = (last + interval_s) if last else None
    now = time.time()
    return {
        **s,
        "running_step": _running_step,
        "thread_alive": bool(_thread and _thread.is_alive()),
        "last_error": _last_error,
        "next_run_ts": next_run,
        "next_run_in_s": (max(0, round(next_run - now)) if next_run else None),
        "history": (s.get("history") or [])[-_MAX_HISTORY:][::-1],  # neueste zuerst
    }


def _record_result(reason: str, result: dict, error: str | None) -> None:
    with _lock:
        s = {**_DEFAULTS, **_load()}
        entry = {"ts": time.time(), "reason": reason, "error": error,
                 "result": (result or {})}
        s["last_run_ts"] = entry["ts"]
        s["last_result"] = entry
        hist = (s.get("history") or [])
        hist.append(entry)
        s["history"] = hist[-_MAX_HISTORY:]
        _save(s)


def _run_step(reason: str) -> dict:
    """Führt EINEN Schritt aus (serialisiert). Gibt das Ergebnis-Dict zurück."""
    global _running_step, _last_error
    if not _step_fn:
        return {"ok": False, "error": "kein step_fn registriert"}
    if not _step_lock.acquire(blocking=False):
        return {"ok": False, "skipped": "läuft bereits"}
    _running_step = True
    result: dict = {}
    error: str | None = None
    try:
        audit.record("autopilot_step_start", reason=reason)
        result = _step_fn(reason) or {}
        _last_error = None
    except Exception as exc:  # ein Fehler darf den Loop nie töten
        error = f"{type(exc).__name__}: {exc}"
        _last_error = error
        result = {"ok": False, "error": error}
        audit.record("autopilot_step_error", reason=reason, error=error)
    finally:
        _running_step = False
        _step_lock.release()
        _record_result(reason, result, error)
    return result


def trigger_now(reason: str = "manual") -> dict:
    """Stößt sofort einen Schritt in einem eigenen Thread an (nicht-blockierend)."""
    if _running_step:
        return {"ok": False, "started": False, "note": "Ein Verbesserungs-Schritt läuft bereits."}
    threading.Thread(target=_run_step, args=(reason,), daemon=True).start()
    return {"ok": True, "started": True, "note": "Verbesserungs-Schritt im Hintergrund gestartet."}


def _loop() -> None:
    # Kleiner Anlauf-Versatz: nicht direkt beim Backend-Start einen schweren Backtest fahren.
    initial_delay = 120.0
    waited = 0.0
    while not _stop.is_set() and waited < initial_delay:
        _stop.wait(_TICK_S)
        waited += _TICK_S
    while not _stop.is_set():
        try:
            s = get_state()
            if s.get("enabled"):
                interval_s = float(s.get("interval_h", 6.0)) * 3600.0
                last = s.get("last_run_ts") or 0
                if (time.time() - last) >= interval_s:
                    _run_step("schedule")
        except Exception:
            pass
        _stop.wait(_TICK_S)


def start(step_fn: Callable[[str], dict]) -> None:
    """Registriert die Schritt-Funktion und startet den Daemon-Loop (idempotent)."""
    global _step_fn, _thread
    _step_fn = step_fn
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="mastermeta-autopilot", daemon=True)
    _thread.start()
    audit.record("autopilot_started")


def stop() -> None:
    _stop.set()
