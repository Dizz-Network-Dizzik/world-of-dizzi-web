"""Dizz-Defense-Verbund — Dizzi als SOC-Dach (F-DEF2, docs/20 §3.4).

Föderations-Immunität: der Hub sammelt im Takt die AKTIVEN Sperren aller
angebundenen Vertrags-Apps (GET /api/defense) und verteilt sie an ALLE
(POST /api/defense/verbund) — **ein Angriff auf eine App immunisiert alle.**
Neue Sperren und Lockdown-Lagen klingeln zusätzlich in der Glocke (notices).

Echo-Schutz (beidseitig): übernommene Verbund-Sperren tragen app-seitig das
Grund-Präfix ``verbund:`` und werden hier NICHT wieder eingesammelt — sonst
hielte sich der Verbund selbst unendlich am Leben. Loopback-Clients und
globale Maßnahmen (Lockdown/Not-Aus) werden nie geteilt: Lokal-Schonung gilt
verbund-weit, und ob eine App dichtmacht, entscheidet ihr eigener Nutzer.

Best-effort by design: nicht erreichbare Apps werden übersprungen; der Hub
darf weder den Core noch eine App je beeinträchtigen.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import db, panels

VERBUND_TTL_S = 900.0
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "testclient", ""})

# Glocken-Dedupe je Maßnahmen-ID (Prozess-Gedächtnis genügt — nach Neustart
# erneut zu melden ist akzeptabel und fail-safe; Muster wie observe._seen_actions).
_gemeldet: set[str] = set()


def _glocke(user_id: str, source: str, title: str, detail: dict[str, Any]) -> None:
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), user_id, source, "warn", title,
         json.dumps(detail, ensure_ascii=False), db.now_iso()))
    conn.commit()


def tick(user_id: str,
         http_get: Callable[[str], Any] | None = None,
         http_post: Callable[..., Any] | None = None) -> dict[str, int]:
    """Ein Verbund-Takt: sammeln → melden → verteilen. Liefert Zähler."""
    if http_get is None or http_post is None:
        import httpx
        http_get = http_get or (lambda url: httpx.get(url, timeout=3.0))
        http_post = http_post or (lambda url, json: httpx.post(url, json=json, timeout=3.0))

    apps = panels.contract_apps()
    pool: dict[str, dict[str, Any]] = {}   # client -> {grund, app, ttl_s}
    erreichbar: list[str] = []
    for app_id, base_url in apps.items():
        try:
            d = http_get(f"{base_url}/api/defense").json()
        except Exception:
            continue  # App offline ⇒ nächster Takt
        erreichbar.append(app_id)
        if d.get("lockdown") or d.get("notaus"):
            key = f"{app_id}:lage"
            if key not in _gemeldet:
                _gemeldet.add(key)
                _glocke(user_id, app_id,
                        f"Dizz Defense: {app_id} ist im "
                        f"{'Not-Aus' if d.get('notaus') else 'Lockdown'}",
                        {"lockdown": d.get("lockdown"), "notaus": d.get("notaus")})
        for m in d.get("massnahmen", []):
            client = str(m.get("client", ""))
            grund = str(m.get("grund", ""))
            if (m.get("stufe", 0) < 2 or client in _LOOPBACK or client == "*"
                    or grund.startswith("verbund:")):
                continue
            pool.setdefault(client, {
                "grund": f"{app_id}:{grund}", "app": app_id,
                "ttl_s": float(m.get("rest_s") or VERBUND_TTL_S)})
            key = f"{app_id}:{m.get('id')}"
            if key not in _gemeldet:
                _gemeldet.add(key)
                _glocke(user_id, app_id,
                        f"Dizz Defense: {app_id} hat {client} gesperrt ({grund})"
                        " — Verbund übernimmt",
                        {"client": client, "grund": grund,
                         "stufe": m.get("stufe")})

    verteilt = 0
    if pool:
        sperren = [{"client": c, "grund": v["grund"], "ttl_s": v["ttl_s"]}
                   for c, v in pool.items()]
        for app_id, base_url in apps.items():
            try:
                http_post(f"{base_url}/api/defense/verbund",
                          json={"sperren": sperren, "quelle": "dizzi"})
                verteilt += 1
            except Exception:
                continue
    return {"apps": len(erreichbar), "sperren": len(pool), "verteilt": verteilt}
