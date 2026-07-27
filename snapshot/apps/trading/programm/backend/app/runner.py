"""Prozess-Manager — startet/stoppt je Bot einen Freqtrade-Live-Loop.

Jeder Bot läuft als eigener ``freqtrade trade``-Subprozess (Dry-Run = Paper).
So laufen mehrere Bots parallel und isoliert (eigene Config, eigene Trade-DB,
eigenes Logfile). Echtgeld unterscheidet sich nur durch ``dry_run=false`` in der
Bot-Config + hinterlegte Subaccount-Keys — derselbe Code.

Hinweis: Die Popen-Handles leben im Speicher des Backend-Prozesses. Nach einem
Backend-Neustart sind laufende Bots als „unknown" markiert und können per PID
(persistiert) gestoppt werden.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import audit, jsonstore
from .config import DATA_DIR, PROJECT_ROOT
from .registry import get_bot, update_status

ENGINE_DIR = PROJECT_ROOT / "engine"
PYTHON_EXE = ENGINE_DIR / ".venv" / "Scripts" / "python.exe"
FREQTRADE_EXE = ENGINE_DIR / ".venv" / "Scripts" / "freqtrade.exe"
USERDIR = ENGINE_DIR / "user_data"
LOG_DIR = USERDIR / "logs"
PIDS_FILE = DATA_DIR / "runners.json"

# Taskmanager-Sichtbarkeit: die Bots laufen sonst als anonyme `python.exe`. Eine benannte Kopie der
# venv-Python (im selben Scripts-Ordner -> findet dasselbe pyvenv.cfg, voll funktional) lässt sie im
# Windows-Taskmanager als „DizzTrading-Bot.exe" erscheinen (Win11 gruppiert nach Name -> Bot-Anzahl
# auf einen Blick). Idempotent; bei jedem Fehler Fallback auf die normale python.exe.
BOT_EXE_NAME = "DizzTrading-Bot.exe"
# Alt-Name (vor dem „Dizz Trading"-Rename): in der Prozess-Erkennung MITGEMATCHT, damit kein Bot
# durchs Raster fällt, falls beim Rename-Cutover doch eine alt-benannte Kopie überlebt. Kann nach
# stabilem Betrieb entfernt werden.
_LEGACY_BOT_EXE_NAME = "TradingBot-Bot.exe"


def _ensure_bot_exe() -> Path:
    """Benannte Python-Kopie für die Bot-Prozesse (Taskmanager-Label). Fallback: python.exe."""
    try:
        named = PYTHON_EXE.with_name(BOT_EXE_NAME)
        if PYTHON_EXE.exists() and not named.exists():
            shutil.copy2(PYTHON_EXE, named)
        if named.exists():
            return named
    except Exception:
        pass
    return PYTHON_EXE

# In-Memory Popen-Handles (bot_id -> Popen)
_procs: dict[str, subprocess.Popen] = {}

# Serialisiert die MUTIERENDEN Operationen (start/stop): seit dem Autopilot-Thread können der
# Hintergrund-Loop und der HTTP-Threadpool gleichzeitig Bots starten/stoppen. Ohne Lock wäre das
# Check-then-act in start() nicht atomar (Doppel-Start desselben Bots) und das Read-Modify-Write der
# runners.json könnte Einträge verlieren. RLock = reentrant (start() ruft intern status()).
_state_lock = threading.RLock()


def _subprocess_env(bot) -> dict:
    """Env für den Bot-Subprozess (venv-übergreifende Brücken zur Engine).

    - ``TBT_REGIME_FILE`` (IMMER): absoluter Pfad der HMM-Regime-Bridge-Datei, die das Backend
      schreibt (``tracker.write_regime_bridge``). So koppelt die ``MasterMeta``-Engine ihre jüngste
      Kerze ans gelernte Gaussian-HMM, obwohl sie in einem anderen venv/Prozess läuft. Pfad aus
      ``tracker.REGIME_BRIDGE_FILE`` = single source of truth (kein Drift).
    - ``TBT_SIZING_FILE`` + ``TBT_BOT_ID`` (IMMER, FP-2): Pfad der Sizing-Bridge
      (``sizing.write_bridge_auto``) + Identität des Bots, damit ``custom_stake_amount`` seinen
      eigenen Plan-Stake findet (SPEC docs/KELLY_SIZING_SPEC.md §4). Ohne Engine-Opt-in
      (``use_sizing_bridge``) bleiben beide ungelesen; laufende Bots sehen die Variablen erst
      nach ihrem nächsten (gegateten) Neustart — armed-until-restart.
    - ``TBT_POLICY_FILE`` (IMMER, FP-T5): Pfad der Politik-Bridge (``policy_bridge.write_bridge_auto``)
      für die Sub-Logik-/Stake-Politik der MasterMeta-Engine (SPEC docs/POLICY_HAND_SPEC.md §4).
      Ohne Engine-Opt-in (``use_policy_bridge``) bleibt sie ungelesen — armed-until-restart wie oben.
    - ``TBT_OPT_PARAMS`` / ``TBT_INFORMATIVE_TFS`` (optional): Lern-Parameter bzw. Zusatz-Timeframes.
    """
    from .policy_bridge import POLICY_BRIDGE_FILE  # lazy: vermeidet Import-Reihenfolge-Stolpern
    from .sizing import SIZING_BRIDGE_FILE   # lazy: vermeidet Import-Reihenfolge-Stolpern
    from .tracker import REGIME_BRIDGE_FILE  # lazy: vermeidet Import-Reihenfolge-Stolpern
    extra = {"TBT_REGIME_FILE": str(REGIME_BRIDGE_FILE),
             "TBT_SIZING_FILE": str(SIZING_BRIDGE_FILE),
             "TBT_POLICY_FILE": str(POLICY_BRIDGE_FILE),
             "TBT_BOT_ID": str(getattr(bot, "id", "") or "")}
    # Lern-Parameter + manuelle Override-Ebene: manual_params gewinnt IMMER ueber Gelerntes.
    op = dict(getattr(bot, "opt_params", None) or {})
    mp = getattr(bot, "manual_params", None) or {}
    if mp:
        op.update(mp)
    if op:
        extra["TBT_OPT_PARAMS"] = json.dumps(op)
    if getattr(bot, "timeframes", None):
        extra["TBT_INFORMATIVE_TFS"] = json.dumps(list(bot.timeframes))
    lev = getattr(bot, "leverage", None)
    if lev:
        try:
            extra["TBT_LEVERAGE"] = str(max(1, min(5, int(lev))))  # hart auf 1..5x gedeckelt
        except (TypeError, ValueError):
            pass
    return {**os.environ, **extra}


def _load_pids() -> dict[str, int]:
    return jsonstore.read_json(PIDS_FILE, {})        # resilient (Ziel → .bak → {})


def _save_pids(pids: dict[str, int]) -> None:
    jsonstore.write_atomic(PIDS_FILE, pids)          # atomar + .bak (Schreiber sind via _state_lock serialisiert)


def _prune_stale_pids(pids: dict[str, int]) -> dict[str, int]:
    """Entfernt PID-Einträge gelöschter Bots (kosmetisch; cmdline-Erkennung ignoriert
    sie ohnehin). Defensiv: bei einem Registry-Fehler bleibt ``pids`` unverändert."""
    try:
        from .registry import list_bots
        valid = {b.id for b in list_bots()}
    except Exception:
        return pids
    return {bid: pid for bid, pid in pids.items() if bid in valid}


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, errors="replace",
        )
        return str(pid) in (r.stdout or "")
    except Exception:
        return False


# --- Robuste Erkennung über die Prozess-Kommandozeile (config_<id>.json) ------
# Überlebt einen uvicorn-Neustart, da nicht auf In-Memory-Handles oder die
# (evtl. täuschende) Starter-PID angewiesen. Kurz gecacht, damit ein
# Dashboard-Refresh nicht je Bot eine eigene CIM-Abfrage auslöst.
_PROC_CACHE: dict[str, object] = {"ts": 0.0, "pids": {}}
_PROC_CACHE_TTL = 3.0
_CONFIG_RE = re.compile(r"config_([0-9a-fA-F]{6,})\.json", re.IGNORECASE)


def _list_bot_processes() -> list[tuple[int, str]]:
    """``(PID, CommandLine)`` aller laufenden Bot-Prozesse aus EINER CIM-Abfrage.

    Gemeinsame Rohquelle für die Bot-Erkennung (``_scan_bot_pids``) UND die identitäts-sichere
    Kill-Verifikation (``_verified_pids_for``) — beide vertrauen ausschließlich der Kommandozeile.
    Beide Prozessnamen: anonyme ``python.exe`` (Alt-/Backend-venv) UND die benannte Bot-Kopie
    ``TradingBot-Bot.exe`` (Taskmanager-Label). Defensiv: bei jedem Fehler ``[]``.
    """
    try:
        script = (
            "Get-CimInstance Win32_Process -Filter "
            f"\"Name='python.exe' OR Name='{BOT_EXE_NAME}' OR Name='{_LEGACY_BOT_EXE_NAME}'\" "
            "| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "").strip()
        if not out:
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        res: list[tuple[int, str]] = []
        for item in data:
            pid = (item or {}).get("ProcessId")
            cmd = (item or {}).get("CommandLine") or ""
            if pid:
                res.append((int(pid), cmd))
        return res
    except Exception:
        return []


def _scan_bot_pids(force: bool = False) -> dict[str, int]:
    """Map bot_id -> PID für laufende Freqtrade-Prozesse (per Kommandozeile).

    Ordnet die Bot-Prozesse über das in der Kommandozeile referenzierte ``config_<id>.json``
    ihrem Bot zu. Kurz gecacht, damit ein Dashboard-Refresh nicht je Bot eine CIM-Abfrage auslöst.
    """
    now = time.monotonic()
    if not force and (now - float(_PROC_CACHE["ts"])) < _PROC_CACHE_TTL:
        return dict(_PROC_CACHE["pids"])  # type: ignore[arg-type]
    found: dict[str, int] = {}
    for pid, cmd in _list_bot_processes():
        m = _CONFIG_RE.search(cmd)
        if m:
            found.setdefault(m.group(1).lower(), pid)   # Erste gefundene PID je Bot genügt (Liveness)
    _PROC_CACHE["ts"] = now
    _PROC_CACHE["pids"] = found
    return dict(found)


def _verified_pids_for(bot_id: str) -> list[int]:
    """ALLE laufenden PIDs, deren Kommandozeile genau ``config_<bot_id>.json`` referenziert.

    Identitäts-sicher: kann keinen fremden Bot treffen (der ``.json``-Anker verhindert auch
    Präfix-Kollisionen). EINZIGER Vertrauensanker fürs Killen — schützt davor, eine vom OS
    recycelte Alt-PID (die inzwischen einem ANDEREN Bot gehört) zu beenden. Force-Scan ohne
    Cache (Stop ist selten + muss aktuell sein); defensiv ``[]``.
    """
    target = f"config_{bot_id}.json".lower()
    return [pid for pid, cmd in _list_bot_processes() if target in cmd.lower()]


# --- Funktionale Lebendigkeit (Heartbeat) ------------------------------------
# Prozess-Existenz allein verrät NICHT, ob der freqtrade-Loop noch arbeitet: ein
# Worker kann nach einem hängenden Exchange-/Netz-Call (z. B. nach bitget-429/DDoS-
# Backoff) einfrieren — der Prozess lebt weiter, aber der Heartbeat versiegt. freqtrade
# schreibt im Normalbetrieb ~minütlich „Bot heartbeat … state='RUNNING'" ins Logfile
# (unabhängig vom Handel). Das mtime des Logfiles ist damit ein verlässliches Lebens-
# zeichen: friert es bei laufendem Prozess ein → „stale"/Zombie (funktional tot).
LOG_STALE_AFTER_S = 300.0  # >5 min ohne Log-Fortschritt = funktional tot (Heartbeat ~60 s ⇒ 5 verpasste)


def log_age_s(bot_id: str) -> float | None:
    """Sekunden seit der letzten Schreibaktivität im Bot-Logfile (freqtrade-Heartbeat ~60 s).
    None = kein Logfile (nie gestartet / gerade erst angelaufen). Reine Lese-Operation."""
    try:
        lf = LOG_DIR / f"bot_{bot_id}.log"
        if lf.exists():
            return max(0.0, time.time() - lf.stat().st_mtime)
    except Exception:
        pass
    return None


def _health_for(bot_id: str, running: bool) -> dict:
    """Funktionale Lebendigkeit ZUSÄTZLICH zur Prozess-Existenz.

    ``health``: ``stopped`` (Prozess weg) · ``unknown`` (läuft, aber noch kein Logfile —
    frisch gestartet) · ``ok`` (läuft + frischer Heartbeat) · ``stale`` (läuft, aber Heartbeat
    seit > ``LOG_STALE_AFTER_S`` eingefroren = hängt/Zombie). ``running`` bleibt unberührt
    Prozess-Existenz (Auto-Resume etc. bauen darauf)."""
    if not running:
        return {"health": "stopped", "log_age_s": None, "healthy": None}
    age = log_age_s(bot_id)
    if age is None:
        return {"health": "unknown", "log_age_s": None, "healthy": None}
    stale = age > LOG_STALE_AFTER_S
    return {"health": "stale" if stale else "ok", "log_age_s": round(age, 1), "healthy": (not stale)}


def status(bot_id: str) -> dict:
    """Ermittelt den Laufzustand eines Bots.

    ``running`` (Prozess-Existenz) über: (1) eigenes Popen-Handle, (2) Kommandozeilen-
    Erkennung (überlebt Neustart), (3) persistierte PID als Fallback. ZUSÄTZLICH ``health``
    (funktionale Lebendigkeit aus dem Heartbeat-Alter) — ``running`` bleibt unverändert,
    damit bestehende Aufrufer (Auto-Resume, start/stop-Guards) gleich funktionieren.
    """
    handle = _procs.get(bot_id)
    if handle is not None and handle.poll() is None:
        base = {"bot_id": bot_id, "running": True, "pid": handle.pid, "source": "handle"}
    else:
        cmd_pid = _scan_bot_pids().get(bot_id.lower())
        if cmd_pid:
            base = {"bot_id": bot_id, "running": True, "pid": cmd_pid, "source": "cmdline"}
        else:
            # Identitätssicherer Fallback: die persistierte PID NUR akzeptieren, wenn ein laufender
            # Prozess wirklich ``config_<bot_id>.json`` referenziert (deckt auch nicht-hex Bots wie
            # mastermeta ab, die der hex-basierte _scan_bot_pids auslässt). Behebt den OS-PID-Recycling-
            # Fehlalarm von ``_pid_alive``: ein lautlos gestorbener Bot, dessen Alt-PID inzwischen einem
            # ANDEREN Prozess gehört, wurde sonst als running=True gemeldet → der Resume-Watchdog übersprang
            # ihn (status sah „läuft") → er blieb tot liegen (F07/O03-Muster). Force-Scan-Wahrheit statt PID-Raten.
            vpids = _verified_pids_for(bot_id)
            if vpids:
                base = {"bot_id": bot_id, "running": True, "pid": vpids[0], "source": "cmdline-verified"}
            else:
                base = {"bot_id": bot_id, "running": False, "pid": None}
    base.update(_health_for(bot_id, base["running"]))
    return base


def start(bot_id: str) -> dict:
    """Startet den Live-Loop (Dry-Run oder Echtgeld je nach Bot-Config)."""
    bot = get_bot(bot_id)
    if bot is None:
        return {"ok": False, "error": "Bot nicht gefunden"}
    if not FREQTRADE_EXE.exists():
        return {"ok": False, "error": "Engine nicht installiert"}
    if status(bot_id)["running"]:
        return {"ok": False, "error": "Bot läuft bereits"}

    config = USERDIR / f"config_{bot_id}.json"
    if not config.exists():
        return {"ok": False, "error": f"Config fehlt: {config.name} — Bot neu speichern."}

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logfile = LOG_DIR / f"bot_{bot_id}.log"
    db_url = f"sqlite:///{(USERDIR / f'tradesv3_{bot_id}.sqlite').as_posix()}"

    cmd = [
        str(_ensure_bot_exe()), "-m", "freqtrade", "trade",   # benannte Exe -> Taskmanager-Label
        "--userdir", str(USERDIR),
        "--config", str(config),
        "--strategy", bot.strategy,
        "--logfile", str(logfile),
        "--db-url", db_url,
    ]
    # Check-then-act + PID-Datei-Schreiben atomar (gegen Race mit dem Autopilot-Thread).
    with _state_lock:
        if status(bot_id)["running"]:
            return {"ok": False, "error": "Bot läuft bereits"}
        proc = subprocess.Popen(
            cmd, cwd=str(ENGINE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=_subprocess_env(bot),
        )
        _procs[bot_id] = proc
        pids = _prune_stale_pids(_load_pids()); pids[bot_id] = proc.pid; _save_pids(pids)
        _PROC_CACHE["ts"] = 0.0  # Cache invalidieren -> Status sofort korrekt
        new_status = "paper_running" if bot.dry_run else "live_running"
        update_status(bot_id, new_status)
        audit.record("bot_started", bot_id=bot_id, pid=proc.pid, mode=new_status)
        return {"ok": True, "bot_id": bot_id, "pid": proc.pid, "status": new_status}


def stop(bot_id: str) -> dict:
    """Stoppt den Live-Loop eines Bots."""
    with _state_lock:
        return _stop_locked(bot_id)


def _stop_locked(bot_id: str) -> dict:
    handle = _procs.pop(bot_id, None)
    # IDENTITÄTS-SICHER beenden: NUR Prozesse killen, deren Kommandozeile `config_<bot_id>.json`
    # referenziert. Früher flossen auch die persistierte runners.json-PID und handle.pid ROH (nur
    # `_pid_alive`-geprüft, ohne Identitätsabgleich) in den taskkill — eine vom OS recycelte Alt-PID
    # konnte so den LEBENDEN Prozess eines ANDEREN Bots treffen (Vorfall O11 am 2026-06-16: `/stop` von
    # O13 tötete O11). Der cmdline-Scan ist der einzige Vertrauensanker (kann keinen fremden Bot treffen).
    stopped = False
    for pid in _verified_pids_for(bot_id):
        if _pid_alive(pid):
            # KEIN /T: die benannte Exe wird direkt via Popen gestartet (kein Wrapper-Kind), und /T würde
            # den Identitätsschutz aushebeln (Kindprozesse sind nicht cmdline-verifiziert).
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            stopped = True
    # Das eigene Popen-Handle ist identitäts-sicher (OS-Prozess-Handle statt PID-Lookup) → Sicherheitsnetz
    # für „gerade gestartet, vom Scan noch nicht erfasst".
    if handle is not None and handle.poll() is None:
        handle.kill()
        stopped = True

    pids = _prune_stale_pids(_load_pids()); pids.pop(bot_id, None); _save_pids(pids)
    _PROC_CACHE["ts"] = 0.0  # Cache invalidieren
    update_status(bot_id, "stopped")
    audit.record("bot_stopped", bot_id=bot_id, stopped=stopped)
    return {"ok": True, "bot_id": bot_id, "stopped": stopped, "status": "stopped"}


def tail_log(bot_id: str, lines: int = 40) -> dict:
    """Liefert die letzten Logzeilen eines Bots."""
    logfile = LOG_DIR / f"bot_{bot_id}.log"
    if not logfile.exists():
        return {"bot_id": bot_id, "lines": [], "note": "Noch kein Logfile (Bot nie gestartet?)."}
    content = logfile.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"bot_id": bot_id, "lines": content[-lines:]}
