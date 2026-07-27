"""Agenten-Orchestrator (Z4.2-A, docs/63 §3) — Worker-als-Tool auf ``agent.stream_agent``.

``agent.py`` bleibt die EINE Runtime (UNANGETASTET). Ein Sub-Agent wird dem Orchestrator
als synthetisches Tool ``delegiere_<slug>`` injiziert; sein ``run()`` startet den Worker-Lauf
(EIGENE Tool-Teilmenge, EIGENES Modell, EIGENES Budget) und liefert dessen Endtext als
Tool-Ergebnis. So erbt die Delegation Parallelität (``agent.py`` gathert die Tool-Calls einer
Runde), Timeout und Fehler-Isolation — nichts davon wird nachgebaut.

Zwei Wächter kommen HINZU (der Vertrag verlangt sie fail-closed):
- **Tiefe:** ein Agent auf Ebene ``>= MAX_EBENEN`` bekommt KEINE Delegations-Tools, und der
  Delegations-Handler weigert sich zusätzlich, auf Ebene ``> MAX_EBENEN`` zu starten — die
  Laufzeit traut der Definition nicht (sie kann nach ``validiere_agentenbaum`` editiert sein).
- **Budget:** Delegations-/Tool-/Laufzeit-Grenzen aus ``AgentBudget``; Überschreitung ⇒
  EHRLICHER Fehlertext ans Modell (nie stilles Kappen).

Deny-by-default: ein Agent sieht exakt ``werkzeuge_filter(grants, katalog)`` — Tippfehler und
entfernte Tools fliegen kommentarlos. Events (Q3-Slot) laufen über ``EventSenke`` (Default no-op
``ereignis_verwerfen``); Z4.2-B verdrahtet Persistenz/C13, ohne die Signaturen zu ändern.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from appkit import agenten as ag
from appkit.agenten import AgentBudget, AgentDef, EventSenke, ereignis_verwerfen

from .agent import AgentEvent, stream_agent
from .tools import ToolSpec

#: Runtime-Signatur = ``agent.stream_agent`` (injizierbar für Fake-Runtime-Tests).
Runtime = Callable[..., AsyncIterator[AgentEvent]]
#: Löst eine Sub-Agenten-ID zur vollen Definition auf (None = unbekannt ⇒ kein Tool).
Resolver = Callable[[str], "AgentDef | None"]


@dataclass
class LaufZustand:
    """Mutabler Laufzeit-Zustand: Zähler + Budget + Deadline. Trägt HIER nur die
    Wächter; Z4.2-B persistiert ihn nach ``agent_laeufe`` (Definition-Snapshot + nutzung).
    ``fehler`` = ehrlicher Grund bei Budget-/Laufzeit-Ende (nie stilles Kappen)."""

    budget: AgentBudget
    tool_aufrufe: int = 0
    delegationen: int = 0
    fehler: str = ""
    _deadline: float = 0.0

    def start_uhr(self) -> None:
        self._deadline = time.monotonic() + max(1, self.budget.max_laufzeit_s)

    def zeit_ueberschritten(self) -> bool:
        return self._deadline > 0.0 and time.monotonic() > self._deadline


def _messages(agent: AgentDef, auftrag: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    if agent.system_prompt.strip():
        msgs.append({"role": "system", "content": agent.system_prompt})
    msgs.append({"role": "user", "content": auftrag or "Erfülle deine Rolle."})
    return msgs


def _auftrag_schema() -> dict[str, Any]:
    return {"type": "object",
            "properties": {"auftrag": {"type": "string",
                "description": "Die Teilaufgabe für den Worker — klar und in sich geschlossen."}},
            "required": ["auftrag"]}


def _budget_tool(spec: ToolSpec, zustand: LaufZustand) -> ToolSpec:
    """Umschließt ein echtes Tool mit dem Budget-/Laufzeit-Wächter (max_tool_aufrufe)."""
    async def run(args: dict[str, Any]) -> str:
        if zustand.zeit_ueberschritten():
            zustand.fehler = zustand.fehler or "Laufzeit-Budget erschöpft"
            return f"Tool {spec.name} übersprungen: Laufzeit-Budget erschöpft."
        if zustand.tool_aufrufe >= zustand.budget.max_tool_aufrufe:
            zustand.fehler = zustand.fehler or "Tool-Budget erschöpft"
            return f"Tool {spec.name} übersprungen: Tool-Budget ({zustand.budget.max_tool_aufrufe}) erschöpft."
        zustand.tool_aufrufe += 1
        return await spec.run(args)
    return ToolSpec(name=spec.name, description=spec.description,
                    parameters=spec.parameters, run=run,
                    sensitivity=spec.sensitivity, is_action=spec.is_action)


def _eigene_tools(agent: AgentDef, katalog: list[ToolSpec],
                  zustand: LaufZustand) -> list[ToolSpec]:
    """Deny-by-default: nur die GEWÄHRTEN Tools (Schnittmenge mit dem Katalog), jedes
    mit Budget-Wächter. Ein toter/getippter Grant fliegt kommentarlos (werkzeuge_filter)."""
    by_name = {t.name: t for t in katalog}
    erlaubt = ag.werkzeuge_filter(agent.werkzeuge, [t.name for t in katalog])
    return [_budget_tool(by_name[name], zustand) for name in erlaubt]


def _delegation_tool(worker: AgentDef, ziel_ebene: int, *, katalog: list[ToolSpec],
                     resolver: Resolver, runtime: Runtime, zustand: LaufZustand,
                     senke: EventSenke, profil: Any) -> ToolSpec:
    """Synthetisches Tool ``delegiere_<slug>``: startet den Worker-Lauf auf ``ziel_ebene``
    und liefert dessen Endtext. Fail-closed bei Tiefe/Budget; Worker-Fehler bleibt isoliert
    (wird zu Text, kippt weder Geschwister noch Orchestrator — wie ``agent._run_tool``)."""
    async def run(args: dict[str, Any]) -> str:
        if ziel_ebene > ag.MAX_EBENEN:
            return (f"Delegation an {worker.name!r} verweigert: maximale Ebenentiefe "
                    f"{ag.MAX_EBENEN} erreicht (fail-closed).")
        if zustand.delegationen >= zustand.budget.max_delegationen:
            zustand.fehler = zustand.fehler or "Delegations-Budget erschöpft"
            return (f"Delegation an {worker.name!r} verweigert: Delegations-Budget "
                    f"({zustand.budget.max_delegationen}) erschöpft.")
        if zustand.zeit_ueberschritten():
            zustand.fehler = zustand.fehler or "Laufzeit-Budget erschöpft"
            return f"Delegation an {worker.name!r} verweigert: Laufzeit-Budget erschöpft."
        zustand.delegationen += 1
        auftrag = str((args or {}).get("auftrag", "")).strip()
        senke("delegation", {"worker": worker.id, "ebene": ziel_ebene, "auftrag": auftrag})
        try:
            return await _lauf_text(worker, auftrag, ebene=ziel_ebene, katalog=katalog,
                                    resolver=resolver, runtime=runtime, zustand=zustand,
                                    senke=senke, profil=profil)
        except Exception as e:   # Fehler-Isolation: ein toter Worker kippt nichts
            return f"Worker {worker.name!r} fehlgeschlagen: {type(e).__name__}: {e}"
    return ToolSpec(
        name=ag.delegations_toolname(worker.id),
        description=f"Delegiere eine Teilaufgabe an Worker {worker.name!r} "
                    f"({worker.rolle or 'Sub-Agent'}).",
        parameters=_auftrag_schema(), run=run, is_action=False)


def werkzeuge_fuer(agent: AgentDef, ebene: int, *, katalog: list[ToolSpec],
                   resolver: Resolver, runtime: Runtime, zustand: LaufZustand,
                   senke: EventSenke, profil: Any) -> list[ToolSpec]:
    """Wirksame Tool-Menge eines Agenten auf ``ebene``: eigene (gewährte) Tools +
    Delegations-Tools der Sub-Agenten. Ab ``ebene >= MAX_EBENEN`` KEINE Delegation mehr
    (fail-closed Tiefen-Wächter, doppelt zur Definitionszeit-Prüfung)."""
    tools = _eigene_tools(agent, katalog, zustand)
    if ebene < ag.MAX_EBENEN:
        for sub_id in agent.sub_agenten:
            worker = resolver(sub_id)
            if worker is not None:
                tools.append(_delegation_tool(
                    worker, ebene + 1, katalog=katalog, resolver=resolver, runtime=runtime,
                    zustand=zustand, senke=senke, profil=profil))
    return tools


async def _lauf_text(agent: AgentDef, auftrag: str, *, ebene: int, katalog: list[ToolSpec],
                     resolver: Resolver, runtime: Runtime, zustand: LaufZustand,
                     senke: EventSenke, profil: Any) -> str:
    """Führt einen (Sub-)Lauf und liefert seinen Endtext (Worker-als-Tool-Ergebnis)."""
    tools = werkzeuge_fuer(agent, ebene, katalog=katalog, resolver=resolver, runtime=runtime,
                           zustand=zustand, senke=senke, profil=profil)
    model = agent.modell_fuer(profil) if profil is not None else None
    parts: list[str] = []
    async for kind, data in runtime(_messages(agent, auftrag), tools, model):
        if kind == "t":
            parts.append(data)
        elif kind == "tool":
            senke("tool_aufruf", {"agent": agent.id, "ebene": ebene,
                                  "tool": (data or {}).get("name", "")})
    return "".join(parts).strip()


async def stream_lauf(agent: AgentDef, auftrag: str, *, katalog: list[ToolSpec],
                      resolver: Resolver, runtime: Runtime = stream_agent,
                      zustand: LaufZustand | None = None,
                      senke: EventSenke = ereignis_verwerfen,
                      profil: Any = None) -> AsyncIterator[AgentEvent]:
    """Top-Lauf des Orchestrators (Ebene 1): streamt die AgentEvents (``("t"|"tool", …)``)
    für SSE/UI und emittiert die Lauf-Ereignisse über die ``senke`` (Q3-Slot). Der
    ``zustand`` trägt die Budget-Zähler; ``agent.py`` bleibt unberührt."""
    zustand = zustand or LaufZustand(budget=agent.budget)
    zustand.start_uhr()
    senke("lauf_gestartet", {"agent": agent.id})
    tools = werkzeuge_fuer(agent, 1, katalog=katalog, resolver=resolver, runtime=runtime,
                           zustand=zustand, senke=senke, profil=profil)
    model = agent.modell_fuer(profil) if profil is not None else None
    try:
        async for ev in runtime(_messages(agent, auftrag), tools, model):
            kind, data = ev
            if kind == "tool":
                senke("tool_aufruf", {"agent": agent.id, "ebene": 1,
                                      "tool": (data or {}).get("name", "")})
            yield ev
    finally:
        senke("lauf_ende", {"agent": agent.id, "tool_aufrufe": zustand.tool_aufrufe,
                            "delegationen": zustand.delegationen, "fehler": zustand.fehler})
