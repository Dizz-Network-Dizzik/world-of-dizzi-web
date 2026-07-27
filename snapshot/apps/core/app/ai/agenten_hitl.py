"""HITL-Verdrahtung im Agenten-Lauf (Z4.2-C, docs/63 §3/§4) — Aktion = propose, nie direkt.

Ein Aktions-Tool im Agenten-Kontext ruft IMMER die K4-Inbox (``propose``) mit
WARUM + agent_id + lauf_id; der Agent bekommt ``{status:'pending', id}`` und formuliert
weiter — er WARTET NICHT blockierend (§3: die Inbox ist der asynchrone Ort der Entscheidung,
Läufe bleiben kurz/budgetierbar). ``wirksame_stufe`` entscheidet VOR jeder Ausführung:

- ``pre_approval`` (v1-Default — Q2-Evals fehlen ⇒ IMMER hier): Vorschlag wartet in der Inbox.
- ``monitored``/``autonom_audit`` (NUR mit ``eval_gruen``): auto-Freigabe mit Pflicht-Sicht.
- ``geld``/``gesundheit``: fest ``pre_approval`` (``KLASSEN_BODEN``, unlockbar) — kein UI-Bug
  und kein Setting lockern das.

Fail-closed durchgehend: fehlt das WARUM ⇒ keine Aktion; unbekannte Stufe ⇒ ``pre_approval``.
``propose_fn``/``freigabe_fn`` sind injizierbar — die besitzende App ist der EINZIGE Schreiber
ihrer K4-DB (kein Confused-Deputy). Hier steht nur die Politik-Verdrahtung; das Routing der
realen App-Schreib-Tools über diesen Wrapper ist die MCP-Gateway-Integration (Naht, s. Modul-
Ende / Handover).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from appkit.agenten import (klasse_von_level, stufe_erlaubt_ausfuehrung,
                            stufe_erlaubt_vorschlag, wirksame_stufe)

from .tools import ToolSpec

#: Legt einen K4-Vorschlag an: (name, params, warum) → ``{"id":…, "status":"pending"}``.
ProposeFn = Callable[[str, dict, str], Awaitable[dict]]
#: Gibt einen Vorschlag frei (nur monitored/autonom): (action_id) → ``{"status": …}``.
FreigabeFn = Callable[[str], Awaitable[dict]]
#: Protokolliert eine Schreib-ABSICHT im Beobachtungs-Modus (T0): (name, params, warum)
#: → ``{"id": …}`` — NIE ausgeführt, NIE vorgeschlagen (docs/83 §3, schatten.py).
SchattenFn = Callable[[str, dict, str], Awaitable[dict]]


def _schema_mit_warum(parameter: dict[str, Any]) -> dict[str, Any]:
    """Ergänzt das Aktions-Schema um das PFLICHT-Feld ``warum`` (§3.F Inbox-Standard)."""
    props = dict(parameter.get("properties", {}))
    props["warum"] = {"type": "string",
        "description": "Kurze Begründung, WARUM diese Aktion nötig ist (Pflicht)."}
    required = list(parameter.get("required", []))
    if "warum" not in required:
        required.append("warum")
    return {"type": "object", "properties": props, "required": required}


def aktions_tool(*, name: str, level: str, beschreibung: str, parameter: dict[str, Any],
                 propose_fn: ProposeFn, agent_id: str, lauf_id: str, klasse: str = "",
                 bereich_stufe: str | None = None, agent_stufe: str | None = None,
                 eval_gruen: bool = False, freigabe_fn: FreigabeFn | None = None,
                 schatten_fn: SchattenFn | None = None) -> ToolSpec:
    """Baut das HITL-gewrappte Aktions-Tool EINES Agenten (Worker-als-Tool-Geschwister).

    ``wirksame_stufe`` entscheidet VOR jeder Wirkung (docs/83 §3):
    - **beobachten** (T0, Default für Unkonfiguriertes/Unbekanntes) ⇒ **Schatten**:
      weder ausgeführt noch vorgeschlagen; ``schatten_fn`` protokolliert die Absicht
      (falls gegeben), der Agent erfährt es EHRLICH (kein vorgetäuschter Vollzug).
    - **pre_approval** ⇒ propose (wartet in der Inbox).
    - **monitored/autonom_audit** (nur mit ``eval_gruen``) ⇒ propose UND Auto-Freigabe
      (falls ``freigabe_fn`` gegeben). ``geld``/``gesundheit`` erreichen das NIE (Kappe).

    WARUM ist immer Pflicht (§3.F). ``klasse`` überschreibt die aus dem Level abgeleitete
    Klasse (Apps deklarieren strenger, z. B. healthy ⇒ 'gesundheit')."""
    wirk_klasse = klasse or klasse_von_level(level)

    async def run(args: dict[str, Any]) -> str:
        args = args or {}
        warum = str(args.get("warum", "")).strip()
        if not warum:                                   # §6.1/§3.F: kein Warum ⇒ keine Aktion
            return ("Aktion abgelehnt: WARUM ist Pflicht — ein Agent, der sein Warum "
                    "nicht sagen kann, hat keins.")
        params = {k: v for k, v in args.items() if k != "warum"}
        stufe = wirksame_stufe(wirk_klasse, bereich_stufe=bereich_stufe,
                               agent_stufe=agent_stufe, eval_gruen=eval_gruen)
        # beobachten (oder eine unbekannte Stufe) ⇒ Schatten: NIE propose, NIE ausführen.
        # Der Agent erfährt es ehrlich, damit sein Abschlussbericht nicht lügt (§3).
        if not stufe_erlaubt_vorschlag(stufe):
            sid = ""
            if schatten_fn is not None:
                sch = await schatten_fn(name, params, warum)
                sid = str((sch or {}).get("id", ""))
            return (f"Aktion '{name}' NICHT ausgeführt und NICHT vorgeschlagen — "
                    f"Beobachtungs-Modus (Stufe {stufe}, Klasse {wirk_klasse}). Als "
                    f"Schatten-Absicht protokolliert{f', id={sid}' if sid else ''}.")
        res = await propose_fn(name, params, warum)     # ab pre_approval: K4 (nie direkt)
        aid = str((res or {}).get("id", ""))
        # Nur monitored/autonom_audit (eval_gruen) geben zusätzlich frei; geld/gesundheit
        # erreichen das NIE (Kappe). pre_approval ⇒ wartet in der Inbox.
        if stufe_erlaubt_ausfuehrung(stufe) and freigabe_fn is not None and aid:
            frei = await freigabe_fn(aid)
            return (f"Aktion '{name}' ({stufe}, Sichtbarkeit pflicht) freigegeben: "
                    f"{(frei or {}).get('status', '?')}. id={aid}")
        return (f"Aktion '{name}' vorgeschlagen — wartet auf Freigabe in der Inbox "
                f"(Stufe {stufe}, Klasse {wirk_klasse}). id={aid}")

    return ToolSpec(
        name=name,
        description=beschreibung + " (HITL: Vorschlag mit Pflicht-Begründung, nie direkt.)",
        parameters=_schema_mit_warum(parameter), run=run,
        sensitivity="", is_action=True)


# --- Integrations-Naht (Handover) -------------------------------------------------
# Die reale Verdrahtung — welche App-Schreib-Tools ein Agent bekommt und wie ``propose_fn``
# an die K4-Registry der BESITZENDEN App bindet — läuft über das MCP-Gateway
# (mcp_gateway.py: „Schreib-Tools extern nur propose"). Z4.2-C liefert HIER die Politik
# (wirksame_stufe + WARUM/agent_id/lauf_id + fail-closed); das Gateway reicht sie beim
# Lauf-Bau (agenten_laeufe) als ``katalog`` durch. agent_id/lauf_id fließen als gebundene
# Argumente von ``propose_fn`` in ``actions.propose(…, agent_id, warum, lauf_id)`` (Z4.1-B).
