#!/usr/bin/env python3
"""
backup_kern.py — Nightly Kern-Backup TB → OneDrive (WAL-safe, kein Live-Sync).

Was gesichert wird (Klasse E — essenziell, nicht regenerierbar):
  • git bundle (komplette Code-History)
  • programm/data/  (bots.json, autopilot.json, hmm_regime.json, strategy_catalog.json,
                     governor.json, cull.json, sizing.json, alle *.jsonl, stats.sqlite usw.)
  • C:\\Dizzik\\data\\apps\\tradingbot\\tradingbot.sqlite  (App-DB inkl. Lern-/Optimierungs-Stand)
  • engine/user_data/tradesv3_*.sqlite  (Trade-Historie 51 Bots)
  • engine/user_data/strategies/

Was NICHT gesichert wird (regenerierbar oder sicherheitskritisch):
  • .venv/            — pip install -r requirements.txt
  • backtest_results/ — re-runnable (~339 MB)
  • logs/             — kein Langzeitwert (~293 MB)
  • data/  (OHLCV)   — re-fetchbar via Bitget-API (~61 MB)
  • .env              — NICHT nach OneDrive (API-Keys! → KeePass/Bitwarden)

Ablauf:
  hot-copy (sqlite3 Backup-API, WAL-sicher) + file-copy → Staging (außerhalb OneDrive)
  → ZIP/LZMA compress → einmalige .zip nach OneDrive → Staging löschen → Retention.

Aufruf:
  .venv\\Scripts\\python.exe scripts\\backup_kern.py
"""
import sqlite3
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── Pfade ─────────────────────────────────────────────────────────────────────
PROGRAMM     = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROGRAMM.parent
USER_DATA    = PROGRAMM / "engine" / "user_data"

APP_DB_SRC   = Path(r"C:\Dizzik\data\apps\tradingbot\tradingbot.sqlite")
APP_DIR_SRC  = APP_DB_SRC.parent          # rp_session_secret.txt + vault.key
DATA_DIR     = PROGRAMM / "data"          # JSON-Configs + stats.sqlite
STRATEGIES   = USER_DATA / "strategies"

STAGING_ROOT = Path(r"C:\Dizzik\data\tools\backup_staging\tb_kern")
ONEDRIVE_OUT = Path(r"%USERPROFILE%\OneDrive\Backups\TradingBot")
RETENTION    = 7                          # letzte N Backups behalten


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def _hot_sqlite(src: Path, dst: Path) -> None:
    """WAL-sicherer Hot-Copy via sqlite3 Backup-API (kein Stop nötig)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_con = sqlite3.connect(str(src))
    dst_con = sqlite3.connect(str(dst))
    with dst_con:
        src_con.backup(dst_con, pages=256)
    src_con.close()
    dst_con.close()


def _copy_data_dir(src: Path, staging: Path) -> None:
    """
    Kopiert programm/data/ nach staging/data/.
    SQLite-Dateien werden per Hot-Backup gesichert, alle anderen direkt kopiert.
    .gitkeep wird übersprungen.
    """
    dst = staging / "data"
    dst.mkdir(exist_ok=True)
    for f in src.iterdir():
        if not f.is_file() or f.name == ".gitkeep":
            continue
        if f.suffix == ".sqlite":
            _hot_sqlite(f, dst / f.name)
        else:
            shutil.copy2(str(f), str(dst / f.name))


# ── Haupt-Backup ──────────────────────────────────────────────────────────────

def run() -> Path:
    ts      = datetime.now().strftime("%Y%m%d_%H%M")
    staging = STAGING_ROOT / ts
    staging.mkdir(parents=True, exist_ok=True)

    print(f"[backup_kern] {ts}  staging={staging}", flush=True)

    # 1 — Git-Bundle (komplette History, komprimiert)
    _log("git bundle …")
    subprocess.run(
        ["git", "bundle", "create", str(staging / "tb_code.bundle"), "--all"],
        cwd=str(PROJECT_ROOT), check=True, capture_output=True,
    )

    # 2 — App-DB (WAL aktiv → zwingend Hot-Backup)
    _log("tradingbot.sqlite (App-DB) …")
    _hot_sqlite(APP_DB_SRC, staging / "tradingbot.sqlite")

    # 3 — App-Begleitdateien (session secret + vault key)
    _log("App-Begleitdateien …")
    for fname in ("rp_session_secret.txt", "vault.key"):
        src_f = APP_DIR_SRC / fname
        if src_f.exists():
            shutil.copy2(str(src_f), str(staging / fname))

    # 4 — programm/data/ (JSON-Configs + stats.sqlite)
    _log(f"programm/data/ ({DATA_DIR}) …")
    _copy_data_dir(DATA_DIR, staging)

    # 5 — Trade-Historie per Bot (51× tradesv3_*.sqlite)
    trade_dbs = sorted(USER_DATA.glob("tradesv3_*.sqlite"))
    _log(f"{len(trade_dbs)} Bot-Trade-DBs …")
    trades_dst = staging / "trades"
    trades_dst.mkdir(exist_ok=True)
    for db in trade_dbs:
        _hot_sqlite(db, trades_dst / db.name)

    # 6 — Strategie-Dateien
    if STRATEGIES.exists() and any(STRATEGIES.iterdir()):
        _log("strategies/ …")
        shutil.copytree(str(STRATEGIES), str(staging / "strategies"), dirs_exist_ok=True)

    # 7 — Komprimieren: LZMA (7z-ähnlich, kein Extra-Install nötig)
    _log("Komprimiere (LZMA) …")
    ONEDRIVE_OUT.mkdir(parents=True, exist_ok=True)
    archive = ONEDRIVE_OUT / f"tb_kern_{ts}.zip"
    with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA) as zf:
        for f in staging.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(staging))

    # 8 — Staging löschen
    shutil.rmtree(str(staging))

    # 9 — Retention (letzte RETENTION Backups behalten, ältere löschen)
    archives = sorted(ONEDRIVE_OUT.glob("tb_kern_*.zip"))
    for old in archives[:-RETENTION]:
        old.unlink()
        _log(f"Altes Backup entfernt: {old.name}")

    size_mb = archive.stat().st_size / 1_048_576
    print(f"[backup_kern] FERTIG: {archive.name}  ({size_mb:.1f} MB)", flush=True)
    return archive


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"[backup_kern] FEHLER: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
