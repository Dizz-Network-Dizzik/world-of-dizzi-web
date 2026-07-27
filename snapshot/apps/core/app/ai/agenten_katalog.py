"""Realer Werkzeug-Katalog eines Agenten-Laufs (Z4.2-D, docs/63 §3/§4) — Core-Tools
lesend direkt, App-Schreib-Aktionen NUR als K4-Vorschlag (propose), nie direkt.

Zwei Quellen, EINE Klassifikation:
- **Read-only** = ``tools.registry`` (Core-interne Tools + die read-only GET-Tools der
  App-MCP-Server). Sie lesen ⇒ der Agent bekommt sie DIREKT (der Orchestrator filtert je
  Agent gegen die ``werkzeuge``-Grants, deny-by-default).
- **Schreib-Aktionen** = die ``werkzeuge``-Grants eines Agenten, die auf die Schreib-/
  Aktions-Namensmuster passen (``mcp_gateway.ist_aktions_name`` — DIESELBE „Schreib-Tools
  extern nur propose"-Wahrheit wie das Gateway). Die App-MCP-Server listen v1 nur read-only
  GET-Tools, Schreib-Aktionen tauchen also NICHT im Katalog auf; sie werden aus dem
  Grant-Namen (``<app>_<aktion>``) erkannt und über ``agenten_hitl.aktions_tool``
  propose-gewrappt: ihr Aufruf legt IMMER einen Vorschlag in der K4-Inbox der besitzenden
  App an (``propose_fn`` → deren ``POST /api/actions/propose``, ``source='agent'`` mit
  gebundenem ``agent_id``/``lauf_id``), führt aber nie selbst aus (§3 „nie blockierend").

Fail-closed durchgehend: ein (unerwartet) als Schreib klassifiziertes Katalog-Tool erreicht
den Agenten NIE roh; ein Grant, der weder ein bekanntes read-Tool noch ein Aktions-Name ist,
fliegt kommentarlos (werkzeuge_filter im Orchestrator). ``geld``/``gesundheit`` (Money/Healthy)
werden über die Klassen-Zuordnung fest auf ``pre_approval`` gebodet (``wirksame_stufe``).

Naht (docs/63, agenten_hitl.py Modul-Ende): HIER wohnt die „welche App-Schreib-Tools bekommt
ein Agent und wie bindet ``propose_fn`` an die besitzende App"-Verdrahtung; ``propose_factory``
ist injizierbar (Test = Fake, Produktion = HTTP an die App). Die ECHTE End-zu-End-Wirkung je
App (welche Aktion, exakter Name/Level) wird im gegateten Live-Lauf verifiziert.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable

from appkit import netz
from appkit.agenten import AgentDef, definitions_hash, klasse_von_level

from . import mcp_gateway as gw
from . import tools as tools_mod
from .agenten_hitl import ProposeFn, SchattenFn, aktions_tool
from .tools import ToolSpec

#: Baut aus (app_id, aktion, agent_id, lauf_id) eine gebundene ``propose_fn``. Injizierbar
#: (Test = Fake ohne HTTP; Produktion = ``default_propose_factory`` → App-Endpoint).
ProposeFactory = Callable[[str, str, str, str], ProposeFn]

#: Bindet (agent_id, lauf_id) an eine ``schatten_fn`` (Beobachtungs-Modus, docs/83 §3).
#: Injizierbar (Test = Fake; Produktion = ``schatten.default_schatten_factory``).
#: ``None`` ⇒ ohne Schatten-Persistenz (der HITL-Wrapper meldet den Modus trotzdem ehrlich).
SchattenFactory = Callable[[str, str], SchattenFn]

#: App-ID → (Klassen-Override, Default-Level) für Schreib-Aktionen. Money/Healthy sind über
#: die Klasse fest gebodet (``geld``/``gesundheit`` ⇒ ``wirksame_stufe`` immer pre_approval,
#: unlockbar). Der Rest leitet die Klasse aus dem Level ab (verifiziert ⇒ aussenwirkung).
_APP_KLASSE: dict[str, tuple[str, str]] = {
    "finanzen": ("geld", "hochsicher"),
    "health": ("gesundheit", "verifiziert"),
}

#: Registry-Signatur (injizierbar) — Default = die echte ``tools.registry``.
RegistryFn = Callable[[bool], Awaitable[list[ToolSpec]]]


def owning_app(tool_name: str) -> tuple[str, str]:
    """Zerlegt einen namespaced Werkzeug-/Grant-Namen ``<app>_<aktion>`` in
    (App-ID, Aktions-Name). Ohne ``_`` ⇒ (name, name) (kein Namespace erkennbar)."""
    teile = tool_name.split("_", 1)
    return (teile[0], teile[1]) if len(teile) == 2 else (tool_name, tool_name)


def _klasse_und_level(app_id: str) -> tuple[str, str]:
    return _APP_KLASSE.get(app_id, ("", "verifiziert"))


def default_propose_factory(user_id: str) -> ProposeFactory:
    """Produktions-Factory: die gebundene ``propose_fn`` legt einen Vorschlag in der
    K4-Inbox der BESITZENDEN App an (``POST /api/actions/propose``, ``source='agent'``) —
    der EINZIGE Schreiber ihrer DB (kein Confused-Deputy, §2). ``agent_id``/``lauf_id``
    sind gebunden; ``name`` aus ``aktions_tool`` ist der namespaced Grant, gesendet wird
    der App-seitige Aktions-Name (Closure ``aktion``). Das ist der gegatete Live-Pfad
    (braucht die App online); Tests injizieren eine Fake-Factory."""
    def factory(app_id: str, aktion: str, agent_id: str, lauf_id: str) -> ProposeFn:
        eintrag = netz.netz_app(app_id)
        base = eintrag.url if eintrag else ""

        async def propose_fn(_name: str, params: dict[str, Any], warum: str) -> dict[str, Any]:
            if not base:
                return {"id": "", "status": "fehler",
                        "fehler": f"Unbekannte App '{app_id}' — kein propose-Ziel."}
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(f"{base}/api/actions/propose", json={
                    "name": aktion, "params": params, "source": "agent",
                    "agent_id": agent_id, "warum": warum, "lauf_id": lauf_id})
                r.raise_for_status()
                return r.json()

        return propose_fn

    return factory


def _eval_je_klasse(eval_status: dict[str, Any] | None, wurzel: AgentDef) -> dict[str, bool]:
    """Core-seitiges RE-GATE des ``eval_gruen`` (Defense-in-Depth, docs/83 §4): eine grüne
    Eichung aus der Regie-Karte zählt NUR, wenn ihr ``def_hash`` zur JETZT rekonstruierten
    Definition des Wurzel-Agenten passt. Editiert jemand die Definition zwischen Karten-
    Push und Lauf, erlischt das Grün auch dann, wenn Management es (noch) grün meldete —
    der Prüfer und der Ausführende einigen sich über den Hash, nicht über Vertrauen."""
    roh = (eval_status or {}).get(wurzel.id, {})
    if not isinstance(roh, dict) or not roh:
        return {}
    aktuell = definitions_hash(wurzel)
    return {klasse: bool(v.get("gruen")) and v.get("def_hash") == aktuell
            for klasse, v in roh.items() if isinstance(v, dict)}


def _schreib_tool(grant: str, wurzel: AgentDef, lauf_id: str,
                  propose_factory: ProposeFactory,
                  schatten_factory: SchattenFactory | None, *,
                  bereich_je_klasse: dict[str, str] | None = None,
                  eval_je_klasse: dict[str, bool] | None = None) -> ToolSpec:
    """Propose-gewrapptes (bzw. im Beobachtungs-Modus Schatten-) Aktions-Tool aus einem
    Schreib-Grant. Der Werkzeug-NAME bleibt der Grant (``<app>_<aktion>``), damit
    ``werkzeuge_filter`` ihn je Agent findet; die ``propose_fn`` sendet den App-seitigen
    Aktions-Namen an die besitzende App.

    Die wirksame Autonomie-Stufe kommt aus der ``autonomie``-Karte des WURZEL-Agenten
    (Attribution = Wurzel, docs/63; unkonfiguriert ⇒ ``beobachten`` = Schatten, V-1).
    **RG-5:** die Bereichs-Kappe (``bereich_je_klasse``) und das ``eval_gruen``
    (``eval_je_klasse``, def_hash-re-gated) kommen jetzt aus der Regie-Karte — W1 ließ
    beide offen (``bereich_stufe=None`` / ``eval_gruen=False``). Fehlen sie (Karte ohne
    Eval/Bereich, Test), gilt weiter der fail-closed Default: keine Bereichs-Kappe +
    ``eval_gruen=False`` (alles über ``pre_approval`` klemmt zurück)."""
    app_id, aktion = owning_app(grant)
    klasse, level = _klasse_und_level(app_id)
    wirk_klasse = klasse or klasse_von_level(level)
    agent_stufe = wurzel.autonomie.get(wirk_klasse)     # None ⇒ beobachten (Schatten)
    bereich_stufe = (bereich_je_klasse or {}).get(wirk_klasse)  # None ⇒ keine Bereichs-Kappe
    eval_gruen = bool((eval_je_klasse or {}).get(wirk_klasse, False))
    propose_fn = propose_factory(app_id, aktion, wurzel.id, lauf_id)
    schatten_fn = schatten_factory(wurzel.id, lauf_id) if schatten_factory else None
    return aktions_tool(
        name=grant, level=level,
        beschreibung=(f"Schreib-Aktion '{aktion}' der App {app_id} — legt einen Vorschlag "
                      f"in der Inbox der besitzenden App an (nie direkte Ausführung)."),
        parameter={"type": "object", "properties": {}},
        propose_fn=propose_fn, agent_id=wurzel.id, lauf_id=lauf_id,
        klasse=klasse, bereich_stufe=bereich_stufe, agent_stufe=agent_stufe,
        eval_gruen=eval_gruen, schatten_fn=schatten_fn)


def schreib_grants(agenten: Iterable[AgentDef], read_names: set[str]) -> list[str]:
    """Alle Schreib-Aktions-Grants der Agenten (Reihenfolge-stabil, dedupe), die NICHT
    schon als read-only-Tool vorliegen. So bekommt auch ein Worker seine Aktion (der
    Katalog ist geteilt; der Orchestrator filtert je Agent gegen die Grants)."""
    out: list[str] = []
    for a in agenten:
        for grant in a.werkzeuge:
            if grant in read_names or grant in out:
                continue
            if gw.ist_aktions_name(grant):
                out.append(grant)
    return out


async def katalog_bauen(*, agenten: Iterable[AgentDef], wurzel_id: str, lauf_id: str,
                        sensitive: bool, propose_factory: ProposeFactory,
                        registry_fn: RegistryFn | None = None,
                        schatten_factory: SchattenFactory | None = None,
                        eval_status: dict[str, Any] | None = None,
                        bereich_stufen: dict[str, Any] | None = None) -> list[ToolSpec]:
    """Baut den vollen Katalog EINES Laufs: alle read-only-Tools (durchgereicht) + die
    propose-/schatten-gewrappten Schreib-Aktionen aller Agenten des Snapshots.

    ``wurzel_id`` bindet die Herkunft der Vorschläge (v1: der Lauf ist seinem Wurzel-Agenten
    zugeschrieben; ``lauf_id`` verlinkt ohnehin auf den konkreten Lauf). Die wirksame
    Autonomie-Stufe je Schreib-Aktion kommt aus der ``autonomie``-Karte dieses Wurzel-
    Agenten (unkonfiguriert ⇒ ``beobachten`` = Schatten, V-1). **RG-5:** ``eval_status``
    (je Agent × Klasse ``{gruen, def_hash}``) und ``bereich_stufen`` (je Agent × Klasse die
    Bereichs-Kappe) kommen aus der gepushten Regie-Karte (docs/83 §4) — der Wurzel-Eintrag
    liefert ``eval_gruen`` (def_hash-re-gated) und die Bereichs-Kappe; fehlen sie, gilt der
    fail-closed Default (kein Bereichs-Deckel + ``eval_gruen=False``). ``schatten_factory``
    persistiert die Beobachtungs-Absichten (docs/83 §3); ``None`` ⇒ ehrliche Meldung ohne
    Persistenz. ``sensitive=True`` (``hoch``/``höchst``-Agenten) lässt PC-verlassende Tools
    weg (tools.registry-Regel)."""
    agenten = list(agenten)
    reg = registry_fn or tools_mod.registry
    roh = await reg(sensitive)
    # Defensive (fail-closed): nur read-only direkt in den Katalog; ein als Schreib
    # klassifiziertes Tool erreicht den Agenten NIE roh (v1 liefert die Registry nur read-only).
    katalog = [t for t in roh if not gw.ist_schreib_tool(t)]
    read_names = {t.name for t in katalog}
    # Wurzel-AgentDef für die Stufen-Auflösung (Attribution = Wurzel). Fehlt sie im
    # Snapshot (Defensive), ein leerer Platzhalter ⇒ autonomie leer ⇒ beobachten.
    wurzel = next((a for a in agenten if a.id == wurzel_id),
                  AgentDef(id=wurzel_id, name=wurzel_id))
    # RG-5: Eval-/Bereichs-Auflösung für den Wurzel-Agenten (aus der Regie-Karte).
    eval_je_klasse = _eval_je_klasse(eval_status, wurzel)
    bereich_je_klasse = (bereich_stufen or {}).get(wurzel.id, {}) or {}
    for grant in schreib_grants(agenten, read_names):
        katalog.append(_schreib_tool(grant, wurzel, lauf_id, propose_factory,
                                     schatten_factory, bereich_je_klasse=bereich_je_klasse,
                                     eval_je_klasse=eval_je_klasse))
    return katalog
