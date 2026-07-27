"""report.py — V11 Trading→Memory (NUR die Sendeseite).

Baut aus BEREITS BERECHNETEN, READ-ONLY-Status-Daten (Flotte/Bot-Gesundheit/Master-Ensemble/Evidenz)
einen Markdown-Report und legt ihn — best-effort — über den **Core-Relay** in Dizz Memory ab.

SICHERHEITS-SCHIENEN (nicht verhandelbar, docs/26 §11.2):
1. Fasst NIE Trading-Logik / Bot-Configs / Freqtrade / Trade-/Lern-DBs an. Es wird NUR gelesen + Text gesendet.
   Niemals ein Trade-/Transfer-/Aktions-Auslöser.
2. Additiv + isoliert: kein bestehendes Verhalten ändert sich.
3. Best-effort / fail-safe: der GANZE Sende-Pfad ist in try/except, kurzer Timeout (5 s), **wirft NIE** in den
   Trading-Pfad. Core/Memory offline ⇒ der Bot läuft identisch weiter (nur Audit-Log-Hinweis).
4. HITL: ausgelöst NUR durch den expliziten Nutzer-Knopf (``explizit=True``) — kein Auto-Versand.

Transport-/Empfangsseite (Core-Relay + Memory-Empfang) ist World-Chat-seitig fertig + live bewiesen
(docs/26 §10.1/§11); hier wird daran NICHTS getan.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from . import audit, master, registry, runner

# Core-Relay (dummer, auditierender Durchgang → Memory). Env-überschreibbar, Default lokaler Core.
CORE_BASE = os.environ.get("DIZZI_CORE_URL", "http://127.0.0.1:8200").rstrip("/")
RELAY_PATH = "/api/querverbindung/memory"
RELAY_TIMEOUT_S = 5.0


def _gather() -> dict:
    """READ-ONLY Status-Aufnahme. Jede Quelle einzeln abgesichert — fehlende Teile = Defaults,
    NIE eine Exception nach außen (der Aufrufer wäre ohnehin best-effort)."""
    fleet = {"total": 0, "running": 0, "stale": 0, "stopped": 0, "stale_names": []}
    try:
        bots = list(registry.list_bots())
        fleet["total"] = len(bots)
        for b in bots:
            try:
                st = runner.status(b.id)
                if st.get("running"):
                    fleet["running"] += 1
                else:
                    fleet["stopped"] += 1
                if st.get("health") == "stale":
                    fleet["stale"] += 1
                    fleet["stale_names"].append(getattr(b, "name", b.id))
            except Exception:
                continue
    except Exception:
        pass
    m = {}
    try:
        m = master.status() or {}
    except Exception:
        m = {}
    pol = m.get("policy") or {}
    ens = pol.get("ensemble") or {}
    ev = m.get("evidence") or {}
    sl = m.get("mn_sleeve_live") or {}
    return {
        "fleet": fleet,
        "master": {"fitness": pol.get("fitness"), "version": pol.get("version"),
                   "dir_edge": ens.get("dir_edge"), "mn_share": ens.get("mn_share"),
                   "mn_active": sl.get("active")},
        "evidence": {"strategies": ev.get("strategies"), "validated": ev.get("validated"),
                     "mn_engines": ev.get("mn_engines")},
    }


def build_markdown(data: dict, now: datetime | None = None) -> tuple[str, str, str]:
    """Pure Funktion (testbar): Status-Dict → (titel, markdown, ref). Stabiles Tages-``ref`` ⇒ Idempotenz
    (mehrfaches Archivieren am selben Tag = derselbe Eintrag)."""
    now = now or datetime.now(timezone.utc)
    ref = f"trading:report:{now:%Y-%m-%d}"
    titel = f"Dizz Trading — Status-Report {now:%Y-%m-%d}"
    f = data.get("fleet") or {}
    ms = data.get("master") or {}
    ev = data.get("evidence") or {}

    def s(v):
        return "–" if v is None else str(v)

    mn_pct = "–"
    if ms.get("mn_share") is not None:
        try:
            mn_pct = f"{round(float(ms['mn_share']) * 100)}%"
        except (TypeError, ValueError):
            pass

    lines = [
        f"# {titel}",
        f"_Read-only-Snapshot · {now:%Y-%m-%d %H:%M} UTC · proposal-only, 0 Echtgeld._",
        "",
        "## Flotte",
        f"- Bots gesamt: **{s(f.get('total'))}** · laufend **{s(f.get('running'))}** · "
        f"hängt **{s(f.get('stale'))}** · gestoppt **{s(f.get('stopped'))}**",
    ]
    if f.get("stale_names"):
        lines.append(f"- ⚠️ Hängende Bots (kein Heartbeat): {', '.join(map(str, f['stale_names'][:8]))}")
    lines += [
        "",
        "## Master-Ensemble",
        f"- Fitness: **{s(ms.get('fitness'))}** (v{s(ms.get('version'))})",
        f"- Gerichteter Edge: **{s(ms.get('dir_edge'))}** · MN-Sockel-Anteil: **{mn_pct}** · "
        f"aktive MN-Engines: **{s(ms.get('mn_active'))}**",
        "",
        "## Evidenz",
        f"- Validierte Strategien: **{s(ev.get('validated'))}** / {s(ev.get('strategies'))} · "
        f"MN-Engines: {s(ev.get('mn_engines'))}",
    ]
    return titel, "\n".join(lines), ref


def _post_relay(payload: dict, timeout: float = RELAY_TIMEOUT_S) -> dict:
    """Roher urllib-POST an den Core-Relay (stdlib, wie fundamental.py). Wirft bei Netz-/HTTP-Fehler —
    der Aufrufer (``archivieren``) fängt das ab (best-effort)."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(CORE_BASE + RELAY_PATH, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def archivieren(explizit: bool = True) -> dict:
    """Baut den Report und legt ihn best-effort in Memory ab. **Wirft NIE.** Gibt ein UI-freundliches
    Ergebnis zurück (auch im Fehlerfall ``{ok: False, error}``). NUR über expliziten Nutzer-Knopf."""
    try:
        data = _gather()
        titel, inhalt, ref = build_markdown(data)
        payload = {
            "app": "tradingbot",            # feste Absender-Kennung (Memory-Herkunftslabel „Trading")
            "strom": "report",
            "ref": ref,                     # stabil ⇒ idempotent
            "sensibel": True,               # IMMER (Trading = sensitivity hoechst ⇒ Memory-KI lokal_only)
            "explizit": bool(explizit),     # Nutzer-Zuruf schlägt jede Memory-Auto-Regel
            "titel": titel,
            "inhalt": inhalt,
        }
        resp = _post_relay(payload) or {}
        try:
            audit.record("report_archived", ref=ref, status=resp.get("status"),
                         ziel=resp.get("ziel"), ok=resp.get("ok"))
        except Exception:
            pass
        return {"ok": bool(resp.get("ok", True)), "ref": ref, "titel": titel,
                "status": resp.get("status"), "id": resp.get("id"), "ziel": resp.get("ziel")}
    except Exception as exc:  # best-effort: NIE in den Trading-/HTTP-Pfad werfen
        try:
            audit.record("report_archive_error", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
