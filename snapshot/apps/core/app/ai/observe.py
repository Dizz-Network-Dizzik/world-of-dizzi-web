"""Memory-Ebene L4: Tool-/Panel-Beobachtungen über die Zeit.

Ein periodischer Beobachter (Core-Lifespan) zieht Schnappschüsse der
Panel-KI-Zustände über deren MCP-Tools und legt sie hier ab. Dizzi kann
damit Trend-Fragen beantworten („wie hat sich das Regime entwickelt?")
und später aktiv Auffälligkeiten melden.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db

OBSERVE_INTERVAL_S = 30 * 60
RETENTION_DAYS = 14  # Rohbeobachtungen; Verdichtung übernimmt später die Konsolidierung


def record(user_id: str, source: str, data: dict[str, Any]) -> None:
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO observations (id, user_id, source, data, created_at) VALUES (?,?,?,?,?)",
        (db.new_id(), user_id, source, json.dumps(data, ensure_ascii=False, default=str),
         db.now_iso()),
    )
    conn.commit()                       # Retention läuft periodisch (s. observations_retention, P1.5)


def observations_retention(user_id: str, tage: int = RETENTION_DAYS) -> int:
    """Soft-Delete von Beobachtungen älter als ``tage`` — PERIODISCH aus dem Tages-Loop
    (docs/50 P1.5), NICHT mehr pro Insert. Vermeidet den O(rows)-Voll-Scan im heißen
    Schreibpfad (Skalierung). Liefert die Anzahl geräumter Zeilen."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=tage)).isoformat(timespec="seconds")
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE observations SET deleted_at=? WHERE user_id=? AND created_at<? AND deleted_at IS NULL",
        (db.now_iso(), user_id, cutoff))
    conn.commit()
    return cur.rowcount


def recent(user_id: str, hours: int = 24, source: str | None = None,
           limit: int = 50) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    q = ("SELECT source, data, created_at FROM observations "
         "WHERE user_id=? AND created_at>=? AND deleted_at IS NULL")
    params: list[Any] = [user_id, cutoff]
    if source:
        q += " AND source=?"
        params.append(source)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = db.get_conn().execute(q, params).fetchall()
    return [
        {"zeit": r["created_at"], "quelle": r["source"], "daten": json.loads(r["data"])}
        for r in rows
    ]


# Vorschlags-Pipeline (K4): bereits gemeldete pending-Aktionen je App, damit
# die Glocke je Vorschlag nur EINMAL klingelt (Prozess-Gedächtnis genügt —
# nach Neustart erneut zu melden ist akzeptabel und fail-safe).
_seen_actions: set[str] = set()


def observe_contract_apps(user_id: str) -> int:
    """L4-Schnappschuss ALLER angebundenen Vertrags-Apps (K4-Generalisierung
    des Trading-Bot-Musters): Kachel-Summary als Beobachtung; neue pending
    Aktions-Vorschläge ⇒ Meldung in der Glocke. Liefert Anzahl Schnappschüsse."""
    import httpx

    from .. import panels
    if len(_seen_actions) > 5000:        # Deckel (docs/50 P1.6): Prozess-Set nie unbegrenzt;
        _seen_actions.clear()            # nach Reset evtl. Re-Melden ist akzeptabel (fail-safe)
    count = 0
    for app_id, base_url in panels.contract_apps().items():
        try:
            s = httpx.get(f"{base_url}/api/summary", timeout=3.0).json()
            if s.get("status") == "fehler":
                continue
            record(user_id, app_id,
                   {"kpis": s.get("kpis", []), "status": s.get("status")})
            count += 1
        except Exception:
            continue  # App offline ⇒ kein Müll-Schnappschuss
        try:
            acts = httpx.get(f"{base_url}/api/actions?status=pending",
                             timeout=3.0).json()
            for a in acts.get("liste", []):
                key = f"{app_id}:{a['id']}"
                if key in _seen_actions:
                    continue
                _seen_actions.add(key)
                conn = db.get_conn()
                conn.execute(
                    "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (db.new_id(), user_id, app_id, "vorschlag",
                     f"Aktions-Vorschlag: {a['name']}",
                     json.dumps({"action_id": a["id"], "level": a["level"],
                                 "params": a["params"]}, ensure_ascii=False),
                     db.now_iso()))
                conn.commit()
        except Exception:
            continue
    return count


async def observe_tradingbot(user_id: str) -> bool:
    """Ein Schnappschuss über die MCP-Tools des Trading-Bot-Panels (roh,
    ungekappt — die Kappung gilt nur für Modell-Kontext)."""
    from . import tools  # spät importieren (Zyklus tools↔observe vermeiden)
    snapshot: dict[str, Any] = {}
    for tool_name, key in (("mastermeta_status", "mastermeta"),
                           ("governor_status", "governor"),
                           ("fleet_status", "flotte")):
        try:
            snapshot[key] = await tools.call_mcp("tradingbot", tool_name)
        except Exception:
            return False
    if any(isinstance(v, dict) and "error" in v for v in snapshot.values()):
        return False  # Bot offline → kein Müll-Schnappschuss
    record(user_id, "tradingbot", snapshot)
    db.audit(user_id, "ki", "observation_recorded", {"source": "tradingbot"})
    return True
