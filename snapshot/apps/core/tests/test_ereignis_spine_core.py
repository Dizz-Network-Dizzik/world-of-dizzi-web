"""RG-2c (docs/83 §1): Core speist Lauf-Telemetrie in den Ereignis-Spine — als ZEIGER.

Beweist am echten Lauf (Fake-Runtime, kein Ollama): die orchestrator-EREIGNISSE
(lauf_gestartet/delegation/tool_aufruf/lauf_ende) landen in der Core-Spine-Tabelle,
referenzieren den Lauf, und tragen NUR skalare Zeiger — der Delegations-'auftrag'
und der 'fehler'-Text (Freitext) bleiben draußen.
"""

from __future__ import annotations

import asyncio
import json

from appkit.agenten import AgentBudget, AgentDef
from appkit import ereignis_spine as es
from app import db
from app.ai import agenten_laeufe as laeufe


def _agent(aid, *, prompt="", subs=()):
    return AgentDef(id=aid, name=aid.upper(), system_prompt=prompt or aid,
                    sub_agenten=tuple(subs), budget=AgentBudget())


def _resolver(*ags):
    m = {a.id: a for a in ags}
    return lambda i: m.get(i)


async def _collect(gen):
    return [ev async for ev in gen]


def _lauf_events(lauf_id):
    return [e for e in es.ereignisse_seit(db.get_conn(), "dizzi", 0)
            if e["ref"] == f"core:lauf:{lauf_id}"]


def test_lauf_emittiert_zeiger_events():
    orch_a = _agent("orch", prompt="ORCH", subs=("w1",))
    w1 = _agent("w1", prompt="P1")
    resolver = _resolver(orch_a, w1)
    lauf_id = laeufe.lauf_anlegen("dizzi", orch_a,
                                  laeufe.schnappschuss(orch_a, resolver))

    async def rt(messages, tools, model=None):
        sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
        specs = {t.name: t for t in tools}
        if sysp == "ORCH":
            yield ("tool", {"name": "delegiere_w1", "args": {"auftrag": "GEHEIM-X"}})
            yield ("t", await specs["delegiere_w1"].run({"auftrag": "GEHEIM-X"}))
        elif sysp == "P1":
            yield ("t", "OK")

    asyncio.run(_collect(laeufe.lauf_streamen(
        "dizzi", lauf_id, orch_a, "AUFTRAG-GEHEIM-X", katalog=[],
        resolver=resolver, runtime=rt)))

    ev = _lauf_events(lauf_id)
    typen = {e["typ"] for e in ev}
    assert {"lauf_gestartet", "delegation", "lauf_ende"} <= typen
    # Zeiger, nie Inhalt: kein Delegations-'auftrag'/Auftragstext im Spine.
    assert "GEHEIM-X" not in json.dumps(ev)
    dele = next(e for e in ev if e["typ"] == "delegation")
    assert dele["payload"].get("worker") == "w1"
    assert "auftrag" not in dele["payload"]
    assert all(e["quelle_sens"] == "hoechst" for e in ev)


def test_lauf_ende_ohne_fehler_freitext():
    a = _agent("o", prompt="O")
    lauf_id = laeufe.lauf_anlegen("dizzi", a, {})

    async def rt(messages, tools, model=None):
        yield ("t", "x")

    asyncio.run(_collect(laeufe.lauf_streamen(
        "dizzi", lauf_id, a, "x", katalog=[], resolver=lambda _i: None, runtime=rt)))

    ende = [e for e in _lauf_events(lauf_id) if e["typ"] == "lauf_ende"]
    assert ende and ende[0]["payload"].get("agent") == "o"
    assert "fehler" not in ende[0]["payload"]        # Freitext bleibt draußen
