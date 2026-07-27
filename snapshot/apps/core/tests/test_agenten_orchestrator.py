"""Tests Z4.2-A (docs/63 §3): Worker-als-Tool-Orchestrator auf agent.stream_agent.

Fake-Runtime (kein Ollama). Deckt die Akzeptanz: 2 Worker EINER Runde laufen parallel
(gather); Worker-Fehler bleibt isoliert; Ebene 4 wird verweigert. Plus: deny-by-default,
Delegations-/Tool-Budget, Event-Emission über die Senke. agent.py bleibt unangetastet.
"""

from __future__ import annotations

import asyncio

from appkit.agenten import AgentBudget, AgentDef
from app.ai import orchestrator as orch
from app.ai.tools import ToolSpec


# --- Helfer ------------------------------------------------------------------

def _agent(aid, *, prompt="", subs=(), werkzeuge=(), budget=None):
    return AgentDef(id=aid, name=aid.upper(), system_prompt=prompt or aid,
                    sub_agenten=tuple(subs), werkzeuge=tuple(werkzeuge),
                    budget=budget or AgentBudget())


def _tool(name, fn=None):
    async def run(args):
        return fn(args) if fn else f"ok:{name}"
    return ToolSpec(name=name, description=name,
                    parameters={"type": "object", "properties": {}}, run=run)


def _resolver(*agents):
    m = {a.id: a for a in agents}
    return lambda aid: m.get(aid)


def _leaf_runtime(text_by_prompt):
    """Fake-Runtime für Blatt-Worker: liefert je System-Prompt einen Endtext."""
    async def rt(messages, tools, model=None):
        sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
        yield ("t", text_by_prompt.get(sysp, ""))
    return rt


# --- Ebene-4-Wächter (fail-closed) -------------------------------------------

def test_ebene_vier_bekommt_keine_delegation():
    w = _agent("w", subs=("tief",))
    tief = _agent("tief")
    z = orch.LaufZustand(budget=AgentBudget())
    # Worker auf Ebene 3 (== MAX_EBENEN): KEINE Delegations-Tools mehr.
    tools = orch.werkzeuge_fuer(w, 3, katalog=[], resolver=_resolver(tief),
                                runtime=_leaf_runtime({}), zustand=z,
                                senke=lambda *_: None, profil=None)
    assert not any(t.name.startswith("delegiere_") for t in tools)
    # …auf Ebene 2 dagegen schon (w->tief wäre Ebene 3, erlaubt).
    tools2 = orch.werkzeuge_fuer(w, 2, katalog=[], resolver=_resolver(tief),
                                 runtime=_leaf_runtime({}), zustand=z,
                                 senke=lambda *_: None, profil=None)
    assert any(t.name == "delegiere_tief" for t in tools2)


def test_delegation_auf_ebene_vier_liefert_fehlertext():
    """Laufzeit traut der Definition nicht: ein direkt auf Ziel-Ebene 4 gebautes
    Delegations-Tool verweigert die Ausführung (Defense-in-Depth)."""
    w = _agent("w")
    tool = orch._delegation_tool(w, 4, katalog=[], resolver=_resolver(w),
                                 runtime=_leaf_runtime({"w": "x"}),
                                 zustand=orch.LaufZustand(budget=AgentBudget()),
                                 senke=lambda *_: None, profil=None)
    res = asyncio.run(tool.run({"auftrag": "tu was"}))
    assert "verweigert" in res and "maximale Ebenentiefe" in res


# --- 2 Worker parallel + Fehler-Isolation ------------------------------------

def test_zwei_worker_einer_runde_parallel():
    """Deterministischer Nebenläufigkeits-Beweis: w2 wartet, bis w1 eingetreten ist —
    das geht NUR auf, wenn beide Delegations-Tools nebeneinander laufen (wie agent.py
    sie via gather aufruft)."""
    orch_a = _agent("orch", subs=("w1", "w2"))
    w1, w2 = _agent("w1", prompt="P1"), _agent("w2", prompt="P2")
    eingetreten: list[str] = []

    async def lauf():
        w1_da = asyncio.Event()

        async def rt(messages, tools, model=None):
            sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
            if sysp == "P1":
                eingetreten.append("w1"); w1_da.set()
                yield ("t", "R1")
            elif sysp == "P2":
                await asyncio.wait_for(w1_da.wait(), 1.0)   # wartet auf w1 ⇒ braucht Parallelität
                eingetreten.append("w2")
                yield ("t", "R2")

        z = orch.LaufZustand(budget=AgentBudget())
        tools = {t.name: t for t in orch.werkzeuge_fuer(
            orch_a, 1, katalog=[], resolver=_resolver(w1, w2), runtime=rt,
            zustand=z, senke=lambda *_: None, profil=None)}
        return await asyncio.gather(tools["delegiere_w1"].run({"auftrag": "a"}),
                                    tools["delegiere_w2"].run({"auftrag": "b"}))

    ergebnisse = asyncio.run(lauf())
    assert ergebnisse == ["R1", "R2"]
    assert eingetreten == ["w1", "w2"]          # w1 zuerst, w2 wartete ⇒ echt parallel


def test_worker_fehler_bleibt_isoliert():
    orch_a = _agent("orch", subs=("w1", "w2"))
    w1, w2 = _agent("w1", prompt="P1"), _agent("w2", prompt="P2")

    async def lauf():
        async def rt(messages, tools, model=None):
            sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
            if sysp == "P2":
                raise RuntimeError("boom")
            yield ("t", "R1")

        z = orch.LaufZustand(budget=AgentBudget())
        tools = {t.name: t for t in orch.werkzeuge_fuer(
            orch_a, 1, katalog=[], resolver=_resolver(w1, w2), runtime=rt,
            zustand=z, senke=lambda *_: None, profil=None)}
        return await asyncio.gather(tools["delegiere_w1"].run({"auftrag": "a"}),
                                    tools["delegiere_w2"].run({"auftrag": "b"}))

    r1, r2 = asyncio.run(lauf())
    assert r1 == "R1"                            # Geschwister unbeschädigt
    assert "fehlgeschlagen" in r2 and "boom" in r2


# --- Budget-Wächter ----------------------------------------------------------

def test_delegations_budget_erschoepft():
    orch_a = _agent("orch", subs=("w1", "w2"), budget=AgentBudget(max_delegationen=1))
    w1, w2 = _agent("w1", prompt="P1"), _agent("w2", prompt="P2")
    z = orch.LaufZustand(budget=orch_a.budget)
    tools = {t.name: t for t in orch.werkzeuge_fuer(
        orch_a, 1, katalog=[], resolver=_resolver(w1, w2),
        runtime=_leaf_runtime({"P1": "R1", "P2": "R2"}), zustand=z,
        senke=lambda *_: None, profil=None)}
    assert asyncio.run(tools["delegiere_w1"].run({"auftrag": "a"})) == "R1"
    zweite = asyncio.run(tools["delegiere_w2"].run({"auftrag": "b"}))
    assert "Delegations-Budget" in zweite and "erschöpft" in zweite
    assert z.delegationen == 1


def test_tool_budget_erschoepft():
    agent = _agent("a", werkzeuge=("werkzeugX",))
    katalog = [_tool("werkzeugX")]
    z = orch.LaufZustand(budget=AgentBudget(max_tool_aufrufe=1))
    tools = {t.name: t for t in orch.werkzeuge_fuer(
        agent, 1, katalog=katalog, resolver=lambda _i: None,
        runtime=_leaf_runtime({}), zustand=z, senke=lambda *_: None, profil=None)}
    assert asyncio.run(tools["werkzeugX"].run({})) == "ok:werkzeugX"
    zweite = asyncio.run(tools["werkzeugX"].run({}))
    assert "Tool-Budget" in zweite and "erschöpft" in zweite


# --- Deny-by-default ---------------------------------------------------------

def test_deny_by_default_nur_gewaehrte_tools():
    agent = _agent("a", werkzeuge=("werkzeugA", "tippfehler"))
    katalog = [_tool("werkzeugA"), _tool("werkzeugB")]
    tools = orch.werkzeuge_fuer(agent, 1, katalog=katalog, resolver=lambda _i: None,
                                runtime=_leaf_runtime({}),
                                zustand=orch.LaufZustand(budget=AgentBudget()),
                                senke=lambda *_: None, profil=None)
    namen = {t.name for t in tools}
    assert namen == {"werkzeugA"}               # B nicht gewährt, tippfehler fliegt


# --- Top-Lauf: Events + Delegation e2e ---------------------------------------

def test_stream_lauf_delegiert_und_emittiert_events():
    orch_a = _agent("orch", prompt="ORCH", subs=("w1",))
    w1 = _agent("w1", prompt="P1")
    ereignisse: list[tuple[str, dict]] = []

    async def lauf():
        async def rt(messages, tools, model=None):
            sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
            if sysp == "ORCH":
                yield ("tool", {"name": "delegiere_w1", "args": {"auftrag": "sub"}})
                specs = {t.name: t for t in tools}
                yield ("t", await specs["delegiere_w1"].run({"auftrag": "sub"}))
            elif sysp == "P1":
                yield ("t", "WORKER-ERGEBNIS")

        return [ev async for ev in orch.stream_lauf(
            orch_a, "Hauptauftrag", katalog=[], resolver=_resolver(w1), runtime=rt,
            senke=lambda n, d: ereignisse.append((n, d)))]

    events = asyncio.run(lauf())
    assert ("tool", {"name": "delegiere_w1", "args": {"auftrag": "sub"}}) in events
    assert ("t", "WORKER-ERGEBNIS") in events
    namen = [n for n, _ in ereignisse]
    assert namen[0] == "lauf_gestartet" and namen[-1] == "lauf_ende"
    assert "delegation" in namen                # Worker-Delegation emittiert
