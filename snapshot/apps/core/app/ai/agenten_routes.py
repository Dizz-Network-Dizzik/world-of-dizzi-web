"""Ausführungs-API der Agenten-Regie (Z4.2-D, docs/63 §3 „Ausführungs-API Core").

Die Live-Schicht ÜBER der gebauten Engine (Orchestrator Z4.2-A · Lauf-Verwaltung Z4.2-B ·
HITL Z4.2-C). Drei Endpunkte unter ``/api/agenten``:

- ``POST /lauf`` — nimmt den **Definition-Snapshot** (Definition-Brücke: Management BESITZT die
  Definition und PUSHT den aufgelösten Wald, Core FÜHRT AUS — KEIN Core→Mgmt-Fetch), baut daraus
  Wurzel-Agent + Resolver + realen Katalog (agenten_katalog) und streamt die AgentEvents als SSE
  (heutige ``("t"|"tool", …)``-Formen + Lauf-Meta), während ``agenten_laeufe`` persistiert.
- ``POST /lauf/{id}/stop`` — setzt ``stop_signal`` (P1; wirkt ≤1 Event später, Z4.2-B).
- ``GET  /laeufe`` (+ ``/laeufe/{id}``) — Task-Ledger (P8): Läufe + Guardrail-Zähler.

``agent.py`` bleibt UNANGETASTET; ``_RUNTIME``/``_KATALOG`` sind Modul-Injektionspunkte
(Fake-Runtime/-Katalog im Test — kein Ollama, keine MCP-Subprozesse). Single-User wie der Rest
des Core (``DEFAULT_USER_ID``). Die ECHTE Live-Aktivierung (Ollama + Neustart) ist gegatet.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from appkit.agenten import AgentBudget, AgentDef

from .. import db
from ..config import DEFAULT_USER_ID
from . import agenten_katalog as kat
from . import agenten_laeufe as laeufe
from . import agenten_regie as regie
from . import orchestrator as orch
from . import schatten
from .agent import stream_agent

router = APIRouter(prefix="/api/agenten", tags=["agenten"])

# --- Test-Injektionspunkte (Modul-Ebene, wie die Fake-Runtime-Muster der Z4.2-Tests) ------
#: Runtime = agent.stream_agent (unangetastet). Test überschreibt mit einer Fake-Runtime.
_RUNTIME: orch.Runtime = stream_agent


async def _standard_katalog(agenten: list[AgentDef], wurzel_id: str, lauf_id: str,
                            sensitive: bool) -> list:
    """Produktions-Katalog: echte read-only-Tools + propose-gewrappte Schreib-Aktionen,
    Beobachtungs-Absichten (T0) ins Schatten-Protokoll (agenten_katalog). **RG-5:** die
    gepushte Regie-Karte liefert ``eval_status`` (echtes ``eval_gruen``, def_hash-re-gated)
    + ``bereich_stufen`` (Bereichs-Kappe) — W1 ließ beide offen. Fehlt die Karte, gilt der
    fail-closed Default (kein Bereichs-Deckel + ``eval_gruen=False``). Test überschreibt
    ``_KATALOG`` mit einem Fake (z. B. ``[]``)."""
    karte = regie.regie_karte_holen(DEFAULT_USER_ID)
    return await kat.katalog_bauen(
        agenten=agenten, wurzel_id=wurzel_id, lauf_id=lauf_id, sensitive=sensitive,
        propose_factory=kat.default_propose_factory(DEFAULT_USER_ID),
        schatten_factory=schatten.default_schatten_factory(DEFAULT_USER_ID),
        eval_status=karte.get("eval_status", {}),
        bereich_stufen=karte.get("bereich_stufen", {}))


_KATALOG = _standard_katalog


class LaufIn(BaseModel):
    """Lauf-Start (Definition-Brücke): ``snapshot`` = aufgelöster Wald aus Management
    (``{"wurzel": id, "agenten": {id: AgentDef-dict}}`` — Form von
    ``agenten_laeufe.schnappschuss``/``agenten_domain.schnappschuss``). ``sensitive`` lässt
    PC-verlassende Tools weg; wird fail-closed erzwungen, sobald ein Agent nicht ``normal`` ist."""
    snapshot: dict[str, Any]
    auftrag: str = ""
    sensitive: bool = True


def _agentdef_aus_dict(d: dict[str, Any]) -> AgentDef:
    """Rekonstruiert eine ``AgentDef`` aus dem ``asdict``-Snapshot (Definition-Brücke).
    Listen werden wieder zu Tupeln, das Budget-Sub-Dict zur ``AgentBudget`` (nur bekannte
    Felder ⇒ vorwärts-tolerant)."""
    b = d.get("budget") or {}
    budget = AgentBudget(**{k: b[k] for k in asdict(AgentBudget()) if k in b})
    return AgentDef(
        id=str(d.get("id", "")), name=str(d.get("name", "")), rolle=str(d.get("rolle", "")),
        system_prompt=str(d.get("system_prompt", "")),
        task_klasse=str(d.get("task_klasse", "chat")),
        modell_explizit=str(d.get("modell_explizit", "")),
        werkzeuge=tuple(d.get("werkzeuge") or ()),
        sub_agenten=tuple(d.get("sub_agenten") or ()),
        bereich_id=str(d.get("bereich_id", "")),
        sensitivitaet=str(d.get("sensitivitaet", "hoch")),
        autonomie=dict(d.get("autonomie") or {}), budget=budget,
        status=str(d.get("status", "entwurf")))


def _aus_snapshot(snapshot: dict[str, Any]) -> tuple[AgentDef | None, list[AgentDef], orch.Resolver]:
    """Wurzel + alle Agenten + Resolver aus dem gepushten Snapshot (kein Mgmt-Fetch)."""
    roh = (snapshot or {}).get("agenten") or {}
    defs = {aid: _agentdef_aus_dict(d) for aid, d in roh.items()}
    wurzel = defs.get((snapshot or {}).get("wurzel", ""))
    return wurzel, list(defs.values()), (lambda aid: defs.get(aid))


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/lauf")
async def lauf_starten(body: LaufIn) -> StreamingResponse:
    """Startet einen Lauf aus dem gepushten Definition-Snapshot und streamt ihn als SSE.
    Setup-Fehler (Katalog) beenden den Lauf EHRLICH (status='fehler'), nie hängend (§6.5)."""
    wurzel, agenten, resolver = _aus_snapshot(body.snapshot)
    if wurzel is None:
        raise HTTPException(422, "Ungültiger Definition-Snapshot: Wurzel-Agent fehlt.")
    user_id = DEFAULT_USER_ID
    # Fail-closed: sobald IRGENDein Agent nicht 'normal' ist, sensibel laufen (lokal_only).
    sensitive = body.sensitive or any(a.sensitivitaet != "normal" for a in agenten)
    lauf_id = laeufe.lauf_anlegen(user_id, wurzel, body.snapshot)

    async def gen() -> AsyncIterator[str]:
        yield _sse({"lauf_id": lauf_id, "start": True, "agent_id": wurzel.id})
        try:
            katalog = await _KATALOG(agenten, wurzel.id, lauf_id, sensitive)
            async for kind, data in laeufe.lauf_streamen(
                    user_id, lauf_id, wurzel, body.auftrag, katalog=katalog,
                    resolver=resolver, runtime=_RUNTIME):
                if kind == "t":
                    yield _sse({"t": data})
                elif kind == "tool":
                    d = data or {}
                    yield _sse({"tool": d.get("name", ""), "args": d.get("args", {})})
                elif kind == "lauf":
                    yield _sse({"lauf": data})
        except Exception as e:   # noqa: BLE001 — Setup-/Katalog-Fehler ehrlich beenden
            laeufe.lauf_fehler(user_id, lauf_id, f"{type(e).__name__}: {e}")
            yield _sse({"error": f"{type(e).__name__}: {e}"})
        row = laeufe.lauf_holen(user_id, lauf_id) or {}
        yield _sse({"done": True, "status": row.get("status", ""),
                    "runden": row.get("runden", 0),
                    "tool_aufrufe": row.get("tool_aufrufe", 0),
                    "delegationen": row.get("delegationen", 0),
                    "nutzung": row.get("nutzung", {}), "fehler": row.get("fehler", "")})

    return StreamingResponse(gen(), media_type="text/event-stream")


async def lauf_aus_regie(user_id: str, snapshot: dict[str, Any], auftrag: str,
                         *, sensitive: bool = True) -> str:
    """Startet einen **Regie-Lauf** (RG-3b, docs/83 §2) aus einem Snapshot und fährt
    ihn INTERN zu Ende — kein SSE (der Scheduler ruft, kein Browser lauscht). Nutzt
    denselben Katalog + dieselbe Runtime wie ``/lauf`` (``_KATALOG``/``_RUNTIME``, im
    Test ersetzbar), sodass die Regie durch KEINE zweite Ausführungs-Naht läuft.
    Setup-/Lauf-Fehler enden EHRLICH (status='fehler'), nie hängend (§6.5). Gibt die
    ``lauf_id`` zurück (auch bei Fehler — der Lauf ist dann als 'fehler' finalisiert)."""
    wurzel, agenten, resolver = _aus_snapshot(snapshot)
    if wurzel is None:
        raise HTTPException(422, "Ungültiger Regie-Snapshot: Wurzel-Agent fehlt.")
    sensitive = sensitive or any(a.sensitivitaet != "normal" for a in agenten)
    lauf_id = laeufe.lauf_anlegen(user_id, wurzel, snapshot)
    try:
        katalog = await _KATALOG(agenten, wurzel.id, lauf_id, sensitive)
        async for _ in laeufe.lauf_streamen(
                user_id, lauf_id, wurzel, auftrag, katalog=katalog,
                resolver=resolver, runtime=_RUNTIME):
            pass   # Ereignisse verwerfen — persistiert wird in lauf_streamen (finally)
    except Exception as e:   # noqa: BLE001 — Setup-/Katalog-Fehler ehrlich finalisieren
        laeufe.lauf_fehler(user_id, lauf_id, f"{type(e).__name__}: {e}")
    return lauf_id


@router.post("/lauf/{lauf_id}/stop")
def lauf_stoppen(lauf_id: str) -> dict[str, Any]:
    """P1-Stop: setzt ``stop_signal`` (wirkt ≤1 Event später). ``gestoppt=False`` =
    unbekannt oder schon beendet (ehrlich, kein 404-Rätsel)."""
    gestoppt = laeufe.stop_anfordern(DEFAULT_USER_ID, lauf_id)
    return {"ok": True, "gestoppt": gestoppt, "lauf_id": lauf_id}


@router.get("/laeufe")
def laeufe_liste(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Task-Ledger (P8): Läufe + Guardrail-Zähler (Runden/Tool-Aufrufe/Delegationen/nutzung),
    jüngste zuerst. ``status='laeuft'`` ⇒ der Running-Tab; leer ⇒ alle."""
    return laeufe.laeufe_liste(DEFAULT_USER_ID, status=status, limit=limit)


@router.get("/laeufe/{lauf_id}")
def lauf_holen(lauf_id: str) -> dict[str, Any]:
    row = laeufe.lauf_holen(DEFAULT_USER_ID, lauf_id)
    if row is None:
        raise HTTPException(404, "Lauf nicht gefunden.")
    return row


# --- Regie-Karte (RG-3b, docs/83 §2): Definition-Brücke der reaktiven Regie -------

class RegieKarteIn(BaseModel):
    """Die von Management gepushte Regie-Karte: Abos + aufgelöster Agent-Wald +
    agent_sens (wirksame Sensitivität je Agent, für ``ereignis_zustellbar``). Vorwärts-
    tolerant (``extra='allow'``) — RG-5 legt Eval-Status/def_hash additiv dazu."""
    model_config = ConfigDict(extra="allow")
    abos: list[dict[str, Any]] = []
    agenten: dict[str, Any] = {}
    agent_sens: dict[str, str] = {}
    eval_status: dict[str, Any] = {}       # RG-5: Agent → Klasse → {gruen, def_hash}
    bereich_stufen: dict[str, Any] = {}    # RG-5: Agent → Klasse → Bereichs-Kappe
    pushed_at: str = ""


@router.post("/regie-karte")
def regie_karte_push(body: RegieKarteIn) -> dict[str, Any]:
    """Definition-Brücke der Regie (docs/83 §2): Management BESITZT die Regie-Konfig und
    PUSHT sie server-seitig; Core legt sie als Arbeitskopie ab (KEIN Core→Mgmt-Fetch).
    Reines Speichern — gezündet wird nur im gegateten Scheduler (Master-Schalter
    ``agenten_regie_aktiv`` Default AUS)."""
    karte = body.model_dump()
    regie.regie_karte_speichern(DEFAULT_USER_ID, karte)
    return {"ok": True, "abos": len(karte.get("abos", [])),
            "agenten": len(karte.get("agenten", {}))}


@router.get("/regie/status")
def regie_status() -> dict[str, Any]:
    """Read-only Regie-Status: Master-Schalter, Tick-Intervall, Karten-Umfang, Zünd-
    Zähler je Status. Zeigt an, ändert nichts (Muster ``/api/sicherheit/lage``)."""
    karte = regie.regie_karte_holen(DEFAULT_USER_ID)
    tick = db.setting_get(DEFAULT_USER_ID, regie.SETTING_TICK_S, regie.TICK_S_DEFAULT)
    return {
        "aktiv": bool(db.setting_get(DEFAULT_USER_ID, regie.SETTING_AKTIV, False)),
        "tick_s": int(tick or regie.TICK_S_DEFAULT),
        "abos": len(karte.get("abos", [])),
        "agenten": len(karte.get("agenten", {})),
        "pushed_at": karte.get("pushed_at", ""),
        "zuendungen": regie.zuendungen_zaehler(DEFAULT_USER_ID),
    }


@router.get("/regie/zuendungen")
def regie_zuendungen(status: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Read-only Zündungs-/Lauf-Verlauf (Ereignis→Lauf-Kette, docs/83 §3) — jüngste
    zuerst, optional nach Status gefiltert."""
    return regie.zuendungen_liste(DEFAULT_USER_ID, status=status.strip(), limit=limit)


class RegieSchalterIn(BaseModel):
    """Not-Aus-Schalter (docs/83 §3): der Master-Schalter ``agenten_regie_aktiv``."""
    aktiv: bool


@router.post("/regie/schalter")
def regie_schalter(body: RegieSchalterIn) -> dict[str, Any]:
    """Not-Aus (docs/83 §3): setzt den Master-Schalter ``agenten_regie_aktiv``.
    **Ausschalten (aktiv=False) ist immer erlaubt** (die Automatik darf sich sofort
    stoppen); **Einschalten (aktiv=True) ist die gegatete Live-Zündung** (G-REGIE-LIVE):
    der Scheduler-Loop selbst läuft erst nach Davids Wort + Neustart, dieses Setting ist
    nur seine Vorbedingung. Setzt das Setting + Audit; der Schalter zündet hier nichts."""
    aktiv = bool(body.aktiv)
    db.setting_put(DEFAULT_USER_ID, regie.SETTING_AKTIV, aktiv)
    db.audit(DEFAULT_USER_ID, "user", "regie_schalter", {"aktiv": aktiv})
    return {"ok": True, "aktiv": aktiv}
