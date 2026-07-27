"""Panel-Registry — das Plugin-Herz des Dashboards.

Jedes Panel liefert ein Manifest (Systemübersicht §3). Platzhalter-Panels
haben ``status='platzhalter'`` und keine Stats-Implementierung; sie sind
bewusst sichtbar („in Planung"), bis das jeweilige Unterprojekt gebaut wird.

Der ``mcp``-Slot ist ein vorbereiteter Anschluss ohne aktuellen Nutzen
(Systemübersicht §4): ab Phase 4 exponiert jedes aktive Panel dort seinen
MCP-Server-Endpoint für die KI.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from typing import Any, Callable

import httpx
import psutil
from pydantic import BaseModel

from . import __version__, db
from .config import settings

_START_TS = time.time()
_static_cache: dict[str, Any] | None = None

# Anbindung an das bestehende Trading-Bot-Projekt (Panel Phase 3, read-only).
TRADINGBOT_URL = os.environ.get("DIZZI_TRADINGBOT_URL", "http://127.0.0.1:8137")
_tb_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def _cpu_name() -> str:
    """Lesbarer CPU-Name. Windows: Registry; sonst plattform-neutral (Linux-portabel)."""
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except Exception:
            pass
    return platform.processor() or platform.machine() or "unbekannt"


def _system_static() -> dict[str, Any]:
    """Unveränderliche System-Eckdaten — einmal ermitteln, dann cachen."""
    global _static_cache
    if _static_cache is None:
        _static_cache = {
            "cpu_name": _cpu_name(),
            "cpu_cores": psutil.cpu_count(logical=False) or 0,
            "cpu_threads": psutil.cpu_count(logical=True) or 0,
            "os": f"{platform.system()} {platform.release()}",
            "hostname": platform.node(),
            "data_dir": str(settings.data_dir),
        }
    return _static_cache


class PanelManifest(BaseModel):
    id: str
    name: str                 # Funktionsname (z. B. 'Finanzmanagement')
    brand: str | None = None  # Marke (z. B. 'Dizz Money') — Marken-Lockup-Norm docs/06 §5
    icon: str
    status: str  # 'aktiv' | 'platzhalter'
    description: str
    actions: list[dict[str, str]] = []
    mcp: str | None = None  # vorbereitet: MCP-Endpoint ab Phase 4


_StatsFn = Callable[[], dict[str, Any]]
_registry: dict[str, tuple[PanelManifest, _StatsFn | None]] = {}


def register(manifest: PanelManifest, stats_fn: _StatsFn | None = None) -> None:
    _registry[manifest.id] = (manifest, stats_fn)


def manifests() -> list[PanelManifest]:
    return [m for m, _ in _registry.values()]


def stats_for(panel_id: str) -> dict[str, Any] | None:
    entry = _registry.get(panel_id)
    if entry is None:
        return None
    manifest, fn = entry
    if fn is None:
        return {"status": "platzhalter", "panel": manifest.id}
    return {"status": "ok", "panel": manifest.id, **fn()}


# --- Systeminfo: erstes echtes Panel (beweist den Stats-Pfad end-to-end) ----

def _gpu_stats() -> dict[str, Any] | None:
    """NVIDIA-Werte via nvidia-smi; auf Systemen ohne NVIDIA einfach None."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        name, util, mem_used, mem_total, temp = [p.strip() for p in out.split(",")[:5]]
        return {"name": name, "util_pct": float(util),
                "vram_used_mb": float(mem_used), "vram_total_mb": float(mem_total),
                "temp_c": float(temp)}
    except (subprocess.SubprocessError, ValueError):
        return None


def _systeminfo_stats() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    # Festplatte dort messen, wo die Daten liegen (Linux-portabel: anchor = "C:\\" bzw. "/")
    disk = psutil.disk_usage(settings.data_dir.anchor or "/")
    freq = psutil.cpu_freq()
    return {
        "cpu_pct": psutil.cpu_percent(interval=0.15),
        "cpu_ghz": round(freq.current / 1000, 2) if freq else None,
        "ram_used_gb": round(vm.used / 2**30, 1),
        "ram_total_gb": round(vm.total / 2**30, 1),
        "ram_pct": vm.percent,
        "disk_free_gb": round(disk.free / 2**30, 1),
        "disk_total_gb": round(disk.total / 2**30, 1),
        "disk_pct": disk.percent,
        "machine_uptime_s": int(time.time() - psutil.boot_time()),
        "gpu": _gpu_stats(),
        # Dizzi-eigener Status (früher im Health-Panel; gehört zum „System")
        "dizzi": _dizzi_status(),
        **_system_static(),
    }


# --- Dizzi-Status: Zustand des Systems selbst (Core, DB, Aktivität) ---------
# Teil der Systeminfo-App-Ansicht. (Das frühere Health-Panel ist jetzt
# Platzhalter für die künftige eigene Gesundheits-App.)

def _dizzi_status() -> dict[str, Any]:
    try:
        db.get_conn().execute("SELECT 1").fetchone()
        db_ok = True
        audit_count = db.get_conn().execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
    except Exception:
        db_ok, audit_count = False, 0
    db_size_mb = round(settings.db_path.stat().st_size / 2**20, 2) if settings.db_path.exists() else 0.0
    all_m = manifests()
    return {
        "version": __version__,
        "uptime_s": int(time.time() - _START_TS),
        "db_ok": db_ok,
        "db_size_mb": db_size_mb,
        "audit_count": audit_count,
        "panels_active": sum(1 for m in all_m if m.status == "aktiv"),
        "panels_total": len(all_m),
    }


# --- Trading Bot: Live-Stats vom bestehenden :8137-Projekt (read-only) ------

def _bot_row(r: dict[str, Any]) -> dict[str, Any]:
    """Eine Bot-Zeile aufs Dashboard-Nötige reduzieren (Top-5-Tabelle, alle Filter).
    Quelle: TB /api/summary `rows` (bereits pro Bot berechnet — kein Extra-Call)."""
    closed = r.get("trades_closed") or 0
    wins = r.get("wins") or 0
    return {
        "name": r.get("name"),
        "category": r.get("category"),          # Gruppe/Markt-Filter
        "running": bool(r.get("running")),       # Modus/laufend-Filter
        "dry_run": bool(r.get("dry_run")),       # demo vs. live
        "mode": r.get("trading_mode"),
        "profit_abs": round(r.get("profit_abs") or 0.0, 2),   # Profit € (live)
        "profit_pct": r.get("profit_live_pct"),               # Profit % (live)
        "trades_closed": closed,
        "win_rate": round(wins / closed * 100, 1) if closed else 0.0,  # Winrate-Filter
    }


def _map_tradingbot_summary(s: dict[str, Any]) -> dict[str, Any]:
    """Reduziert /api/summary auf die Dashboard-Kennzahlen (rein lesend)."""
    closed = s.get("trades_closed") or 0
    wins = s.get("wins") or 0
    groups = [
        {"name": name, "bots": g.get("bots", 0), "running": g.get("running", 0),
         "profit_pct": g.get("profit_pct", 0.0), "profit_abs": g.get("profit_abs", 0.0)}
        for name, g in (s.get("groups") or {}).items()
    ]
    return {
        "online": True,
        "bots": s.get("bots", 0),
        "running": s.get("running", 0),
        "trades_open": s.get("trades_open", 0),
        "trades_closed": closed,
        "win_rate": round(wins / closed * 100, 1) if closed else 0.0,
        "profit_abs": round(s.get("profit_abs") or 0.0, 2),
        "profit_pct": round(s.get("profit_pct") or 0.0, 2),
        "avg_profit_pct": s.get("avg_profit_pct"),
        "groups": groups,
        # Per-Bot-Zeilen fürs Top-5-Tabellen-Panel (Filter clientseitig: Profit/Winrate/Gruppe/Modus).
        "bot_rows": [_bot_row(r) for r in (s.get("rows") or [])],
        "categories": list(s.get("categories") or []),
        "url": TRADINGBOT_URL,
    }


def _map_mastermeta(m: dict[str, Any]) -> dict[str, Any]:
    """Meta-Trading-Bot-Übersicht (MasterMeta): eigene Linie + letzte Entscheidung
    (Autopilot/Optimierung). „Gesamt-Performance" liefert das Summary-Top-Level."""
    bot = m.get("bot") or {}
    closed = bot.get("trades_closed") or 0
    wins = bot.get("wins") or 0
    ap = m.get("autopilot") or {}
    opt = m.get("optimization") or {}
    return {
        "name": bot.get("name") or "MasterMeta",
        "running": bool(bot.get("running")),
        "profit_abs": round(bot.get("profit_abs") or 0.0, 2),
        "profit_pct": bot.get("profit_live_pct"),
        "win_rate": round(wins / closed * 100, 1) if closed else 0.0,
        "regime": m.get("current_regime"),
        # „Letzte Meta-Entscheidung" (HITL-Spur): roh durchgereicht, Shell pickt die Felder.
        "autopilot": ap,
        "optimization": opt,
    }


def _tradingbot_stats() -> dict[str, Any]:
    """Holt die Flotten-Zusammenfassung (5 s TTL-Cache, robust gegen Offline)."""
    now = time.time()
    if _tb_cache["data"] is not None and now - _tb_cache["ts"] < 5:
        return _tb_cache["data"]
    try:
        r = httpx.get(f"{TRADINGBOT_URL}/api/summary", timeout=3.0)
        r.raise_for_status()
        data = _map_tradingbot_summary(r.json())
        # Meta-Trading-Bot-Übersicht separat + fehlertolerant (eine Meta-Panne darf
        # das Flotten-Panel nicht leeren).
        try:
            rm = httpx.get(f"{TRADINGBOT_URL}/api/mastermeta", timeout=3.0)
            rm.raise_for_status()
            data["meta"] = _map_mastermeta(rm.json())
        except Exception:
            data["meta"] = None
    except Exception:
        data = {"online": False, "url": TRADINGBOT_URL}
    _tb_cache["ts"] = now
    _tb_cache["data"] = data
    return data


# --- App-Vertrag (K3): generischer Konsum vertragskonformer Apps ------------
# Jede App, die docs/16_APP_VERTRAG_SPEC.md erfüllt, liefert /api/summary im
# Kachel-Format (appkit.summary) — Dizzi rendert sie OHNE Per-App-Mapping.
# Aktivierung: env DIZZI_CONTRACT_APPS="finanzen=http://127.0.0.1:8210,..."
# (übersteuert den Platzhalter des jeweiligen Panels) oder programmatisch
# via register_contract_app().

_contract_cache: dict[str, dict[str, Any]] = {}
_contract_apps: dict[str, str] = {}  # app_id → base_url (für L4-Beobachter, K4)


def contract_apps() -> dict[str, str]:
    """Aktuell angebundene Vertrags-Apps (id → URL)."""
    return dict(_contract_apps)


def _contract_stats_factory(app_id: str, base_url: str) -> _StatsFn:
    def _stats() -> dict[str, Any]:
        now = time.time()
        cached = _contract_cache.get(app_id)
        if cached is not None and now - cached["ts"] < 5:
            return cached["data"]
        try:
            r = httpx.get(f"{base_url}/api/summary", timeout=3.0)
            r.raise_for_status()
            s = r.json()
            data: dict[str, Any] = {
                "online": True,
                "contract": s.get("contract"),
                "summary_status": s.get("status", "ok"),
                "kpis": s.get("kpis", []),
                "note": s.get("note"),
                "url": base_url,
            }
        except Exception:
            data = {"online": False, "url": base_url}
        _contract_cache[app_id] = {"ts": now, "data": data}
        return data
    return _stats


def register_contract_app(app_id: str, base_url: str) -> None:
    """Hebt ein (Platzhalter-)Panel auf eine live angebundene Vertrags-App.

    Name/Icon werden vom bestehenden Platzhalter übernommen (die Soll-Panels
    aus _seed kennen die Wunsch-Optik); unbekannte IDs bekommen Defaults.
    """
    existing = _registry.get(app_id)
    name = existing[0].name if existing else app_id
    brand = existing[0].brand if existing else None
    icon = existing[0].icon if existing else "box"
    desc = existing[0].description if existing else "Vertragskonforme Netzwerk-App."
    register(
        PanelManifest(
            id=app_id, name=name, brand=brand, icon=icon, status="aktiv", description=desc,
            actions=[{"id": "open", "label": "Zur Anwendung"}],
        ),
        _contract_stats_factory(app_id, base_url),
    )
    _contract_apps[app_id] = base_url


def _seed_contract_apps() -> None:
    """Liest DIZZI_CONTRACT_APPS (id=url, komma-/semikolon-getrennt) — Override ZUERST
    (custom Ports/Remote); die Auto-Discovery füllt danach nur, was noch fehlt."""
    raw = os.environ.get("DIZZI_CONTRACT_APPS", "")
    for pair in raw.replace(";", ",").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        app_id, _, url = pair.partition("=")
        register_contract_app(app_id.strip(), url.strip().rstrip("/"))


def discover_contract_apps() -> int:
    """KA-M2: Auto-Discovery aus der kanonischen App-Tabelle ``appkit.netz.NETZ_APPS``
    (KEINE zweite handgepflegte env-Wahrheit). Registriert jede Netz-App außer ``core``/
    ``tradingbot``, die noch NICHT angebunden ist und deren ``/api/summary`` erreichbar ist
    (timeout 2 s) — macht frisches Setup/Verkauf zero-config. Läuft periodisch (Core-Loop)
    ⇒ selbstheilend: eine später gestartete App erscheint beim nächsten Tick. Der env-Seed
    (``DIZZI_CONTRACT_APPS``) bleibt Override — Discovery überschreibt nie Bestehendes.
    Liefert die Anzahl NEU registrierter Apps."""
    from appkit.netz import NETZ_APPS
    schon = set(_contract_apps)
    neu = 0
    for a in NETZ_APPS:
        if a.id in ("core", "tradingbot") or a.id in schon:
            continue
        try:
            r = httpx.get(f"{a.url}/api/summary", timeout=2.0)
            r.raise_for_status()
            r.json()                          # muss valides JSON sein (Vertrags-Probe)
        except Exception:
            continue                          # nicht erreichbar ⇒ Platzhalter bleibt
        register_contract_app(a.id, a.url)
        neu += 1
    return neu


def _seed() -> None:
    """Registriert die Soll-Panels (Vision docs/00 §5).

    Marke (``brand``) + Funktionsname (``name``) je App = Marken-Lockup-Norm
    (docs/06 §5): das Dashboard zeigt „Dizz X" betont + Funktion dezent dahinter.
    """
    fixed: list[tuple[str, str, str, str, str]] = [
        ("health", "Dizz Healthy", "Gesundheit", "pulse", "Gesundheits-Watching. Nicht gestartet / nicht erreichbar."),
        ("memory", "Dizz Memory", "Wissensspeicher", "box", "Notizen, Wissen & Memory — Markdown-Vault + RAG."),
        ("news", "Dizz News", "News Compact", "globe", "Kompakter Nachrichten-Überblick. Nicht gestartet / nicht erreichbar."),
        ("finanzen", "Dizz Money", "Finanzmanagement", "coins", "Finanzen, Budget & Steuer-Sektor. Nicht gestartet / nicht erreichbar."),
        ("admin", "Dizz Admin", "Verwaltung", "stamp",
         "Bereiche · Tresor · Projekte · Geschäft · Studium · Fristen — die vereinte Verwaltung (Plans+Admin+Leading)."),
        ("management", "Dizz Management", "KI-Agenten", "share",
         "Die KI-Agenten-Verwaltung des Netzes (Heimat der Agenten-Regie, VO-3/D5) — "
         "erste Agenten-Domäne: Social Media (Kanäle, Bots & Posts)."),
        ("kommunikation", "Dizz Communication", "Kommunikation", "chat",
         "E-Mail, Messenger & Calls — die Kommunikations-Zentrale. Nicht gestartet / nicht erreichbar."),
        # Dizz Plans (:8211) + Dizz Leading (:8219) wurden in Dizz Admin verschmolzen
        # (vereinte Bereichs-/Verwaltungs-App, Basis-Repo admin/adminapp [vormals leading]) — abgewickelt 19.06. (docs/28).
        # Dizz Music wurde in die Creating-Suite eingeschmolzen (Musik-Modus,
        # creator/creatorapp/musik) — die eigenständige :8220-App ist abgewickelt (16.06.).
        ("creator", "Dizz Creating", "Medien-Suite", "wand", "Bild-/Video-/Musik-Erstellung & -Bearbeitung. Nicht gestartet / nicht erreichbar."),
    ]
    for pid, brand, name, icon, desc in fixed:
        register(PanelManifest(id=pid, name=name, brand=brand, icon=icon, status="platzhalter", description=desc))

    register(
        PanelManifest(
            id="systeminfo", name="Systeminfo", icon="chip", status="aktiv",
            description="Live-Werte dieses Rechners: CPU, RAM, GPU, Festplatte.",
            actions=[{"id": "refresh", "label": "Aktualisieren"}],
        ),
        _systeminfo_stats,
    )
    register(
        PanelManifest(
            id="tradingbot", name="Trading Bot", brand="Dizz Trading", icon="chart", status="aktiv",
            description="Live-Flotten-Stats des Trading-Bot-Projekts (read-only).",
            actions=[{"id": "open", "label": "Zur Anwendung"}],
        ),
        _tradingbot_stats,
    )
    # Vertragskonforme Apps zuletzt: dürfen Platzhalter live übersteuern (K3).
    _seed_contract_apps()


_seed()
