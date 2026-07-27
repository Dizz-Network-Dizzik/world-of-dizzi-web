"""Brücke zur Freqtrade-Engine — Backtests anstoßen und Kennzahlen lesen.

Das Backend hat eine eigene venv; die Engine läuft in ``engine/.venv``. Wir
rufen die Engine daher als Subprozess auf (sauber getrennte Abhängigkeiten).
Die Kennzahlen werden nicht aus der Textausgabe geparst (die rendert nur am
TTY zuverlässig), sondern aus Freqtrades strukturierter JSON-Ergebnisdatei via
``engine/read_backtest_stats.py``. Live-Prozess-Steuerung folgt in M3/M4.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone

from . import audit
from .config import PROJECT_ROOT
from .registry import get_bot

# Serialisiert Backtest-Lauf + Ergebnis-Lesen: Freqtrade schreibt "das letzte Ergebnis" in einen
# gemeinsamen Results-Ordner — ohne Lock kann ein paralleler Lauf (Autopilot-Tick vs. manueller
# API-Backtest) das falsche Ergebnis zuordnen.
_BT_LOCK = threading.Lock()

ENGINE_DIR = PROJECT_ROOT / "engine"
PYTHON_EXE = ENGINE_DIR / ".venv" / "Scripts" / "python.exe"
FREQTRADE_EXE = ENGINE_DIR / ".venv" / "Scripts" / "freqtrade.exe"
USERDIR = ENGINE_DIR / "user_data"
RESULTS_DIR = USERDIR / "backtest_results"
READ_STATS = ENGINE_DIR / "read_backtest_stats.py"


def engine_available() -> bool:
    return FREQTRADE_EXE.exists()


def _bt_config(config) -> object:
    """Backtest-sichere Config-Variante: Freqtrade kann mit dynamischen Pairlists
    (VolumePairList/SpreadFilter, seit „Pairs streuen") NICHT backtesten — jeder Backtest gegen
    eine Dynamik-Config schlug still fehl („Pairlist Handlers … do not support backtesting").
    Für Backtests wird die Kette auf StaticPairList reduziert; die ``pair_whitelist`` (kuratiertes
    Universum) bleibt die Datenbasis. Live-Configs bleiben unberührt (Overlay ``bt_<name>``)."""
    cfg_path = config
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return cfg_path
    pl = data.get("pairlists") or []
    if all((p or {}).get("method") == "StaticPairList" for p in pl):
        return cfg_path
    data["pairlists"] = [{"method": "StaticPairList"}]
    out = USERDIR / f"bt_{cfg_path.name}"
    try:
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        return cfg_path
    return out


def run_backtest(bot_id: str, days: int = 180) -> dict:
    """Führt einen Backtest für den Bot aus und liefert strukturierte Kennzahlen."""
    bot = get_bot(bot_id)
    if bot is None:
        return {"ok": False, "error": f"Bot {bot_id} nicht gefunden."}
    if not engine_available():
        return {"ok": False, "error": "Engine (Freqtrade) nicht installiert — siehe engine/README.md."}

    config = USERDIR / f"config_{bot_id}.json"
    if not config.exists():
        config = USERDIR / "config_bot1_dryrun.json"
    config = _bt_config(config)

    # Daten fuer den Timeframe sicherstellen (z. B. 5m) — sonst schlaegt der Backtest fehl.
    subprocess.run(
        [str(PYTHON_EXE), "-m", "freqtrade", "download-data", "--userdir", str(USERDIR),
         "--config", str(config), "--timeframe", bot.timeframe, "--days", str(days)],
        cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=900,
    )

    cmd = [
        str(PYTHON_EXE), "-m", "freqtrade", "backtesting",
        "--userdir", str(USERDIR),
        "--config", str(config),
        "--strategy", bot.strategy,
        "--timerange", _timerange(days),
    ]
    audit.record("backtest_started", bot_id=bot_id, strategy=bot.strategy, days=days)
    with _BT_LOCK:
        proc = subprocess.run(cmd, cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=600)
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
            audit.record("backtest_finished", bot_id=bot_id, ok=False)
            return {"ok": False, "error": "Backtest fehlgeschlagen", "report_tail": tail}
        metrics = _read_stats()
    ok = bool(metrics) and "_error" not in metrics
    audit.record("backtest_finished", bot_id=bot_id, ok=ok, metrics=metrics)
    return {"ok": ok, "bot_id": bot_id, "strategy": bot.strategy, "metrics": metrics}


def run_strategy_backtest(strategy: str, days: int = 120) -> dict:
    """Backtest fuer eine Engine-Strategie unabhaengig von einem konkreten Bot.

    Nutzt die Config eines vorhandenen Bots, der diese Strategie faehrt (korrekter
    Markt/Timeframe), sonst die Vorlage-Config. Dient dem Validierungs-Gate vor
    der Freigabe einer (aktivierten) Strategie.
    """
    from .registry import list_bots

    if not engine_available():
        return {"ok": False, "error": "Engine (Freqtrade) nicht installiert."}

    config, tf = None, "5m"
    for b in list_bots():
        if b.strategy == strategy:
            c = USERDIR / f"config_{b.id}.json"
            if c.exists():
                config, tf = c, b.timeframe
                break
    if config is None:
        config = USERDIR / "config_bot1_dryrun.json"
    config = _bt_config(config)

    subprocess.run(
        [str(PYTHON_EXE), "-m", "freqtrade", "download-data", "--userdir", str(USERDIR),
         "--config", str(config), "--timeframe", tf, "--days", str(days)],
        cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=900,
    )
    audit.record("validation_backtest_started", strategy=strategy, days=days)
    with _BT_LOCK:
        proc = subprocess.run(
            [str(PYTHON_EXE), "-m", "freqtrade", "backtesting", "--userdir", str(USERDIR),
             "--config", str(config), "--strategy", strategy, "--timerange", _timerange(days)],
            cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=600,
        )
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
            return {"ok": False, "error": "Backtest fehlgeschlagen", "report_tail": tail}
        metrics = _read_stats()
    ok = bool(metrics) and "_error" not in metrics
    return {"ok": ok, "strategy": strategy, "metrics": metrics}


def run_backtest_with_params(strategy: str, params: dict, days: int = 90) -> dict:
    """Backtest einer Strategie mit injizierten Parametern (via Env TBT_OPT_PARAMS).

    Kern des Lern-Loops: ermöglicht es, Parameter-Kandidaten real gegeneinander zu
    testen. Wirkt nur auf diesen Subprozess — laufende Live-Bots bleiben unberührt.
    """
    if not engine_available():
        return {"ok": False, "error": "Engine (Freqtrade) nicht installiert."}
    config, tf = _find_strategy_config(strategy)
    config = _bt_config(config)
    env = {**os.environ, "TBT_OPT_PARAMS": json.dumps(params or {})}
    subprocess.run(
        [str(PYTHON_EXE), "-m", "freqtrade", "download-data", "--userdir", str(USERDIR),
         "--config", str(config), "--timeframe", tf, "--days", str(days + 5)],
        cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=900, env=env,
    )
    with _BT_LOCK:
        proc = subprocess.run(
            # --cache none: env-injizierte Params (TBT_OPT_PARAMS) aendern die Strategie-DATEI nicht,
            # daher wuerde Freqtrade sonst ein altes Ergebnis wiederverwenden (Cache-Kollision) und
            # Param-Aenderungen, die kein gehashtes Attribut betreffen (z. B. min_bars_between), ignorieren.
            [str(PYTHON_EXE), "-m", "freqtrade", "backtesting", "--userdir", str(USERDIR),
             "--config", str(config), "--strategy", strategy, "--timerange", _timerange(days),
             "--cache", "none"],
            cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=600, env=env,
        )
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
            return {"ok": False, "error": "Backtest fehlgeschlagen", "report_tail": tail}
        m = _read_stats()
    return {"ok": bool(m) and "_error" not in m, "strategy": strategy, "params": params, "metrics": m}


def ensure_data(strategy: str, timeframe: str | None = None, days: int = 120,
                config_name: str | None = None) -> tuple:
    """Stellt die Kerzendaten für ``days`` Tage sicher (EIN download-data-Lauf) und liefert
    (config, timeframe) — damit Mehrfach-Backtests (Lern-Loop) nicht je Kandidat neu laden."""
    config, base_tf = _find_strategy_config(strategy)
    if config_name:
        cand = USERDIR / config_name
        if cand.exists():
            config = cand
    config = _bt_config(config)
    tf = timeframe or base_tf
    subprocess.run(
        [str(PYTHON_EXE), "-m", "freqtrade", "download-data", "--userdir", str(USERDIR),
         "--config", str(config), "--timeframe", tf, "--days", str(days)],
        cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=900,
    )
    return config, tf


def run_backtest_range(strategy: str, params: dict | None, timerange: str,
                       timeframe: str | None = None, config=None) -> dict:
    """Backtest mit Param-Injektion auf einem EXPLIZITEN Zeitfenster (``YYYYMMDD-YYYYMMDD``).

    Baustein des **anchored Walk-Forward**: der Lern-Loop selektiert Kandidaten auf dem
    Trainings-Fenster und testet NUR den Gewinner auf dem späteren, ungesehenen Test-Fenster.
    Lädt selbst keine Daten (vorher einmal ``ensure_data``); ``--cache none`` wie üblich."""
    if not engine_available():
        return {"ok": False, "error": "Engine (Freqtrade) nicht installiert."}
    if config is None:
        config, base_tf = _find_strategy_config(strategy)
        timeframe = timeframe or base_tf
    config = _bt_config(config)
    env = {**os.environ, "TBT_OPT_PARAMS": json.dumps(params or {})}
    cmd = [str(PYTHON_EXE), "-m", "freqtrade", "backtesting", "--userdir", str(USERDIR),
           "--config", str(config), "--strategy", strategy, "--timerange", timerange,
           "--cache", "none"]
    if timeframe:
        cmd += ["--timeframe", timeframe]
    try:
        with _BT_LOCK:
            # 1800s wie run_walkforward: 1m-Scalping x 14 Universum-Pairs ueberschreitet 600s. Der
            # anchored Lern-Loop ruft das je Kandidat in einer Schleife ohne try — ein ungefangener
            # Timeout wuerde sonst den ganzen run_optimization/run_evolution sprengen (HTTP 500).
            proc = subprocess.run(cmd, cwd=str(ENGINE_DIR), capture_output=True, text=True,
                                  errors="replace", timeout=1800, env=env)
            if proc.returncode != 0:
                tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
                return {"ok": False, "error": "Backtest fehlgeschlagen", "report_tail": tail}
            m = _read_stats()
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "strategy": strategy, "timerange": timerange}
    return {"ok": bool(m) and "_error" not in m, "strategy": strategy, "params": params,
            "timerange": timerange, "metrics": m}


def _find_strategy_config(strategy: str) -> tuple:
    """Config + Timeframe eines Bots, der diese Strategie faehrt (sonst Vorlage)."""
    from .registry import list_bots
    for b in list_bots():
        if b.strategy == strategy:
            c = USERDIR / f"config_{b.id}.json"
            if c.exists():
                return c, b.timeframe
    return USERDIR / "config_bot1_dryrun.json", "5m"


def run_walkforward(strategy: str, windows: int = 2, window_days: int = 45,
                    params: dict | None = None, timeframe: str | None = None,
                    embargo_days: int = 0, config_name: str | None = None) -> dict:
    """Leichte Walk-Forward-Validierung: N aufeinanderfolgende Out-of-Sample-Fenster.

    Pro Fenster gilt „bestanden": Trades > 0 UND Drawdown < 50 % UND **Profit > 0** — eine
    Verluststrategie kann nicht mehr „validiert" sein (das alte Gate ohne Profit-Bedingung ließ
    das zu). Gesamt-Validierung = Mehrheit der Fenster bestanden. Optionale `params` werden per
    Env TBT_OPT_PARAMS injiziert (Lern-Loop). HINWEIS: dient der ROBUSTHEITS-Prüfung EINES festen
    Parametersatzes über die Zeit; die Kandidaten-SELEKTION läuft separat anchored
    (``meta.run_optimization``: Auswahl auf dem Trainings-, Test nur auf dem Test-Fenster).
    """
    if not engine_available():
        return {"ok": False, "error": "Engine (Freqtrade) nicht installiert."}
    windows = max(1, min(int(windows), 4))
    config, base_tf = _find_strategy_config(strategy)
    if config_name:  # optionaler Config-Override (z. B. breitere Research-Pairliste fuer robuste Statistik)
        cand = USERDIR / config_name
        if cand.exists():
            config = cand
    config = _bt_config(config)
    tf = timeframe or base_tf  # optionaler Override (z. B. '15m'/'1h' fuer tiefe Historie)
    env = {**os.environ, "TBT_OPT_PARAMS": json.dumps(params or {})}
    total_days = windows * window_days + max(0, windows - 1) * max(0, embargo_days) + 5
    try:
        subprocess.run(
            [str(PYTHON_EXE), "-m", "freqtrade", "download-data", "--userdir", str(USERDIR),
             "--config", str(config), "--timeframe", tf, "--days", str(total_days)],
            cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=900, env=env,
        )
    except subprocess.TimeoutExpired:
        pass  # vorhandene (Teil-)Daten nutzen — die Fenster melden sonst selbst failed
    audit.record("walkforward_started", strategy=strategy, windows=windows)
    now = datetime.now(timezone.utc)
    results, ms, passed = [], [], 0
    for i in range(windows):
        end = now - timedelta(days=i * (window_days + max(0, embargo_days)))
        start = end - timedelta(days=window_days)
        tr = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
        try:
            with _BT_LOCK:
                proc = subprocess.run(
                    # --cache none: erzwingt frische Rechnung je Fenster/Kandidat (sonst Cache-Kollision,
                    # da env-injizierte Params die Strategie-Datei nicht aendern — s. run_backtest_with_params).
                    [str(PYTHON_EXE), "-m", "freqtrade", "backtesting", "--userdir", str(USERDIR),
                     "--config", str(config), "--strategy", strategy, "--timeframe", tf, "--timerange", tr,
                     "--cache", "none"],
                    # 1800s: 1m-Scalping x 14 Universum-Pairs x 40-Tage-Fenster ueberschreitet 600s.
                    cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=1800, env=env,
                )
                if proc.returncode != 0:
                    results.append({"window": i + 1, "timerange": tr, "ok": False, "passed": False})
                    continue
                m = _read_stats()
        except subprocess.TimeoutExpired:
            # Ein haengendes/zu langsames Fenster bricht NICHT die ganze Validierung (Fenster = failed).
            results.append({"window": i + 1, "timerange": tr, "ok": False, "passed": False,
                            "error": "timeout"})
            continue
        ok = bool(m) and "_error" not in m
        p = (ok and int(m.get("total_trades") or 0) > 0
             and float(m.get("max_drawdown_pct") or 0) < 50.0
             and float(m.get("profit_total_pct") or 0) > 0.0)
        passed += 1 if p else 0
        if ok:
            ms.append(m)
        results.append({"window": i + 1, "timerange": tr, "ok": ok, "passed": p, "metrics": m})
    keys = ["profit_total_pct", "max_drawdown_pct", "winrate_pct", "profit_factor", "sharpe"]
    agg = {k: (round(sum(float(x.get(k) or 0) for x in ms) / len(ms), 2) if ms else None) for k in keys}
    agg["total_trades"] = sum(int(x.get("total_trades") or 0) for x in ms)
    overall = passed >= (windows + 1) // 2
    return {"ok": True, "strategy": strategy, "windows": windows, "passed_windows": passed,
            "validated": overall, "windows_detail": results, "metrics": agg}


def _read_stats() -> dict:
    """Liest die letzten Backtest-Kennzahlen via Engine-Skript (JSON)."""
    proc = subprocess.run(
        [str(PYTHON_EXE), str(READ_STATS), str(RESULTS_DIR)],
        cwd=str(ENGINE_DIR), capture_output=True, text=True, errors="replace", timeout=120,
    )
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"_error": "Kennzahlen konnten nicht gelesen werden", "raw": line[:200]}


def _timerange(days: int) -> str:
    """Erzeugt einen offenen Timerange der letzten ``days`` Tage (YYYYMMDD-)."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    return f"{start}-"
