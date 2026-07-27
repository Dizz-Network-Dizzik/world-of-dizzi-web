"""integration.py — Einbettbarkeit in ein übergeordnetes Verwaltungssystem.

Standardisierte **Komponenten-Schnittstelle**, damit dieses Bot-System als beschreibbarer,
steuerbarer Knoten in eine höhere Verwaltungsinstanz eingebunden werden kann:
- ``descriptor()``  — Selbstbeschreibung + Capabilities (was die Instanz steuern kann)
- ``state()``       — konsolidierter Zustand (kompakt, standardisiert)
- ``command()``     — Direktiven der übergeordneten Instanz (owner-token-gated)
Proposal-/sicherheitsbewusst: destruktive Befehle sind als solche markiert.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import __version__, introspect, maintenance, master, stats

COMPONENT_ID = "trading-bot-eins"


def descriptor() -> dict:
    return {
        "component_id": COMPONENT_ID, "name": "Trading Bot Orchestrator", "version": __version__,
        "api_contract": "v1", "kind": "crypto-trading-bot-manager",
        "capabilities": [
            {"action": "report", "mutating": False, "desc": "Konsolidierten Zustand liefern"},
            {"action": "introspect", "mutating": False, "desc": "Selbst-Audit liefern"},
            {"action": "train_master", "mutating": True, "desc": "Master-Trainingsschritt"},
            {"action": "collect_insights", "mutating": True, "desc": "Selbst-Audit-Schlüsse ins Gedächtnis"},
            {"action": "compact", "mutating": True, "desc": "Daten-Lifecycle (Verdichtung/Pruning)"},
            {"action": "pause_all", "mutating": True, "destructive": True, "desc": "Alle Bots stoppen"},
            {"action": "resume_all", "mutating": True, "destructive": True, "desc": "Alle Bots starten"},
        ],
        "metrics": ["bots_registered", "bots_running", "echtgeldreif_count", "master_fitness",
                    "master_version", "db_kb", "data_maturity_pct"],
        "auth": {"owner_token": "Authorization: Bearer <TBT_API_TOKEN> für mutierende Befehle (wenn gesetzt)"},
        "endpoints": {"descriptor": "/api/component/descriptor", "state": "/api/component/state",
                      "command": "/api/component/command"},
    }


def _running_count(bots) -> int | None:
    try:
        from . import runner
        return sum(1 for b in bots if (runner.status(b.id) or {}).get("running"))
    except Exception:
        return None


def state() -> dict:
    from .meta import STRAT_REGIME
    from .registry import list_bots
    bots = list_bots()
    pfs = [(stats.get_strategy_validation(s) or {}).get("profit_factor") for s in STRAT_REGIME]
    ready = sum(1 for p in pfs if p and p > 1)
    mp = master.get_current()
    rep = maintenance.storage_report()
    snaps = rep.get("tables", {}).get("snapshots") or 0
    maturity = min(100, round(snaps / max(1, len(bots) * 30) * 100)) if bots else 0
    csm_m = {}
    try:
        from . import csm
        cs = csm.status()
        if cs.get("ready"):
            csm_m = {"csm_sharpe": cs["stats"].get("sharpe"), "csm_ann_pct": cs["stats"].get("ann_pct")}
    except Exception:
        pass
    return {
        "component_id": COMPONENT_ID, "ts": datetime.now(timezone.utc).isoformat(),
        "mode": ("demo" if stats and True else "demo"),
        "metrics": {
            "bots_registered": len(bots), "bots_running": _running_count(bots),
            "echtgeldreif_count": ready, "master_version": (mp or {}).get("version"),
            "master_fitness": (mp or {}).get("fitness"), "db_kb": rep.get("db_kb"),
            "data_maturity_pct": maturity, "audit_lines": rep.get("audit_lines"), **csm_m,
        },
        "health": "ok",
        "summary": f"{len(bots)} Bots · {ready} echtgeldreif · Master "
                   f"{'v'+str(mp['version']) if mp else 'n/v'} · Reife {maturity}%"
                   + (f" · CSM Sharpe {csm_m['csm_sharpe']}" if csm_m else ""),
    }


# Sichere (nicht-destruktive) Befehle, die ein übergeordnetes System frei aufrufen darf.
_SAFE = {"report", "introspect", "train_master", "collect_insights", "compact"}
# Destruktive Flotten-Befehle: zusätzlich confirm=true (hier) UND — am HTTP-Endpunkt
# (main.component_command) — Schutzstufe 'verifiziert' (vertrag.require_steuerstufe).
DESTRUCTIVE = frozenset({"pause_all", "resume_all"})


def command(action: str, params: dict | None = None) -> dict:
    """Dispatcht eine Direktive der übergeordneten Verwaltungsinstanz."""
    params = params or {}
    act = (action or "").strip().lower()
    if act == "report":
        return {"ok": True, "action": act, "result": state()}
    if act == "introspect":
        return {"ok": True, "action": act, "result": introspect.assess()}
    if act == "train_master":
        return {"ok": True, "action": act, "result": master.train_step()}
    if act == "collect_insights":
        return {"ok": True, "action": act, "result": introspect.self_collect()}
    if act == "compact":
        return {"ok": True, "action": act, "result": maintenance.run_all(dry_run=bool(params.get("dry_run", True)))}
    if act in DESTRUCTIVE:
        # Destruktiv (ändert Handelszustand): bewusst NUR mit explizitem confirm=True ausführen.
        if not params.get("confirm"):
            return {"ok": False, "action": act, "error": "Destruktiver Befehl — confirm=true erforderlich.",
                    "destructive": True}
        from .registry import list_bots
        from . import runner
        done = []
        for b in list_bots():
            try:
                (runner.start if act == "resume_all" else runner.stop)(b.id)
                done.append(b.id)
            except Exception:
                pass
        return {"ok": True, "action": act, "affected": len(done)}
    return {"ok": False, "error": f"Unbekannter Befehl: {action}",
            "known": sorted(_SAFE | DESTRUCTIVE)}
