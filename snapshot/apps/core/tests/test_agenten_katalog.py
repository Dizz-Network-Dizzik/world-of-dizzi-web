"""Tests Z4.2-D (docs/63 §3/§4): realer Werkzeug-Katalog — read-only durchgereicht,
Schreib-Aktionen NUR als propose (nie direkt), agent_id/lauf_id gebunden, fail-closed.

Reine async Unit-Tests (Fake-Registry + Spy-propose-Factory) — kein Ollama, keine App.
"""

from __future__ import annotations

import asyncio

from appkit.agenten import AgentDef, definitions_hash
from app.ai import agenten_katalog as kat
from app.ai.tools import ToolSpec


def _tool(name: str, *, is_action=None) -> ToolSpec:
    async def run(args):
        return f"ok:{name}"
    return ToolSpec(name=name, description=name,
                    parameters={"type": "object", "properties": {}}, run=run,
                    is_action=is_action)


def _agent(aid: str, werkzeuge=(), autonomie=None) -> AgentDef:
    return AgentDef(id=aid, name=aid.upper(), werkzeuge=tuple(werkzeuge),
                    autonomie=autonomie or {})


def _spy_factory():
    calls: list[dict] = []

    def factory(app_id, aktion, agent_id, lauf_id):
        async def propose_fn(_name, params, warum):
            calls.append({"app": app_id, "aktion": aktion, "agent_id": agent_id,
                          "lauf_id": lauf_id, "params": params, "warum": warum})
            return {"id": "act-1", "status": "pending"}
        return propose_fn

    return calls, factory


def _spy_schatten():
    calls: list[dict] = []

    def factory(agent_id, lauf_id):
        async def schatten_fn(name, params, warum):
            calls.append({"agent_id": agent_id, "lauf_id": lauf_id,
                          "name": name, "params": params, "warum": warum})
            return {"id": "sch-1", "status": "schatten"}
        return schatten_fn

    return calls, factory


def _kat(agenten, *, read=(), factory, wurzel="orch", sensitive=True, schatten_factory=None,
         eval_status=None, bereich_stufen=None):
    async def reg(_sensitive):
        return list(read)
    return asyncio.run(kat.katalog_bauen(
        agenten=agenten, wurzel_id=wurzel, lauf_id="l1", sensitive=sensitive,
        propose_factory=factory, registry_fn=reg, schatten_factory=schatten_factory,
        eval_status=eval_status, bereich_stufen=bereich_stufen))


def test_read_tools_durchgereicht():
    """Read-only-Tools kommen 1:1 in den Katalog (Reihenfolge erhalten); keine Wrapper."""
    calls, fac = _spy_factory()
    katalog = _kat([_agent("orch")], read=[_tool("news_lesen"), _tool("memory_suche")],
                   factory=fac)
    assert [t.name for t in katalog] == ["news_lesen", "memory_suche"]
    assert calls == []


def test_schreib_grant_wird_propose_tool():
    """Ein Schreib-Grant (``*_senden``) eines auf pre_approval (T1) konfigurierten
    Agenten wird propose-gewrappt: Aufruf ⇒ Vorschlag an die besitzende App (nie direkt),
    agent_id/lauf_id gebunden, WAS/WARUM getrennt. (V-1: die Stufe kommt aus autonomie.)"""
    calls, fac = _spy_factory()
    orch = _agent("orch", werkzeuge=("kommunikation_email_senden",),
                  autonomie={"aussenwirkung": "pre_approval"})
    katalog = _kat([orch], read=[_tool("news_lesen")], factory=fac)
    namen = {t.name for t in katalog}
    assert namen == {"news_lesen", "kommunikation_email_senden"}   # namespaced Name bleibt
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    assert tool.is_action is True
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert "wartet auf Freigabe" in res and "pre_approval" in res
    assert len(calls) == 1
    c0 = calls[0]
    assert c0["app"] == "kommunikation" and c0["aktion"] == "email_senden"
    assert c0["params"] == {"an": "k@x.org"} and c0["warum"] == "Kunde wartet"
    assert c0["agent_id"] == "orch" and c0["lauf_id"] == "l1"


def test_unkonfiguriert_schattet_statt_propose():
    """V-1/RG-4: ein unkonfigurierter Agent (leere autonomie) ⇒ beobachten ⇒ Schatten.
    Der Katalog reicht die schatten_factory durch; propose bleibt aus."""
    p_calls, fac = _spy_factory()
    s_calls, sfac = _spy_schatten()
    katalog = _kat([_agent("orch", werkzeuge=("kommunikation_email_senden",))],
                   read=[], factory=fac, schatten_factory=sfac)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert p_calls == [] and len(s_calls) == 1
    assert s_calls[0]["agent_id"] == "orch" and s_calls[0]["lauf_id"] == "l1"
    assert "NICHT ausgeführt" in res and "beobachten" in res


def test_schreib_ohne_warum_kein_propose():
    """WARUM Pflicht (§3.F): ohne Begründung wird nichts vorgeschlagen (fail-closed)."""
    calls, fac = _spy_factory()
    katalog = _kat([_agent("orch", werkzeuge=("kommunikation_email_senden",))],
                   read=[], factory=fac)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org"}))
    assert "WARUM ist Pflicht" in res and calls == []


def test_unbekannter_nicht_aktions_grant_fliegt():
    """Deny-by-default: ein Grant, der weder read-Tool noch Aktions-Name ist, erscheint
    nirgends (der werkzeuge_filter des Orchestrators ließe ihn ohnehin fallen)."""
    calls, fac = _spy_factory()
    katalog = _kat([_agent("orch", werkzeuge=("news_lesen", "irgendwas_krude"))],
                   read=[_tool("news_lesen")], factory=fac)
    assert {t.name for t in katalog} == {"news_lesen"} and calls == []


def test_money_grant_geld_geboden():
    """Money-Schreib-Aktion ⇒ Klasse 'geld' (Obergrenze): selbst ein auf autonom_audit
    konfigurierter Agent wird auf pre_approval gedeckelt (unlockbar) und proposet nur."""
    calls, fac = _spy_factory()
    orch = _agent("orch", werkzeuge=("finanzen_order_senden",),
                  autonomie={"geld": "autonom_audit"})
    katalog = _kat([orch], read=[], factory=fac)
    tool = next(t for t in katalog if t.name == "finanzen_order_senden")
    res = asyncio.run(tool.run({"betrag": 100, "warum": "fällig"}))
    assert "geld" in res and "pre_approval" in res and len(calls) == 1


def test_health_grant_gesundheit_geboden():
    calls, fac = _spy_factory()
    orch = _agent("orch", werkzeuge=("health_wert_senden",),
                  autonomie={"gesundheit": "autonom_audit"})
    katalog = _kat([orch], read=[], factory=fac)
    tool = next(t for t in katalog if t.name == "health_wert_senden")
    res = asyncio.run(tool.run({"wert": 120, "warum": "Grenzwert"}))
    assert "gesundheit" in res and "pre_approval" in res and len(calls) == 1


def test_worker_schreib_grant_im_geteilten_katalog():
    """Auch ein WORKER bekommt seine Aktion: der Katalog ist geteilt, der Orchestrator
    filtert je Agent — die Aktion muss also für den Worker im Katalog liegen."""
    _, fac = _spy_factory()
    katalog = _kat([_agent("orch"), _agent("w1", werkzeuge=("kommunikation_email_senden",))],
                   read=[], factory=fac)
    assert any(t.name == "kommunikation_email_senden" for t in katalog)


def test_read_tool_das_als_aktion_klassifiziert_wird_gefiltert():
    """Fail-closed: ein (unerwartet) als Schreib klassifiziertes Registry-Tool erreicht
    den Agenten NIE roh — es wird aus dem Durchreich-Pfad gefiltert."""
    _, fac = _spy_factory()
    katalog = _kat([_agent("orch")],
                   read=[_tool("news_lesen"), _tool("x_senden", is_action=True)], factory=fac)
    assert [t.name for t in katalog] == ["news_lesen"]


def test_owning_app_split():
    assert kat.owning_app("kommunikation_email_senden") == ("kommunikation", "email_senden")
    assert kat.owning_app("solo") == ("solo", "solo")


# --- RG-5: eval_gruen + Bereichs-Kappe aus der Regie-Karte (docs/83 §4) -----------

def _monitored_orch() -> AgentDef:
    return AgentDef(id="orch", name="ORCH", werkzeuge=("kommunikation_email_senden",),
                    autonomie={"aussenwirkung": "monitored"})


def test_eval_gruen_hebt_stufe_bei_passendem_def_hash():
    """RG-5: die Regie-Karte meldet eval_gruen für (orch × aussenwirkung) mit dem AKTUELLEN
    def_hash ⇒ die wirksame Stufe wird endlich ``monitored`` (statt Q2-Klemme pre_approval).
    Der Katalog verdrahtet keine freigabe_fn ⇒ es bleibt beim Vorschlag, aber die Stufe im
    Tool-Text beweist die Auflösung."""
    _, fac = _spy_factory()
    orch = _monitored_orch()
    eval_status = {"orch": {"aussenwirkung": {"gruen": True,
                                              "def_hash": definitions_hash(orch)}}}
    katalog = _kat([orch], read=[], factory=fac, eval_status=eval_status)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert "monitored" in res                       # eval_gruen ⇒ Stufe gehoben


def test_ohne_eval_bleibt_pre_approval_q2_klemme():
    """Ohne Eval-Status (Default) klemmt die Q2-Regel monitored auf pre_approval zurück —
    der fail-closed Default bleibt unverändert (0-Bruch für die Bestands-Tests)."""
    _, fac = _spy_factory()
    katalog = _kat([_monitored_orch()], read=[], factory=fac)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert "pre_approval" in res


def test_eval_gruen_erlischt_bei_def_hash_mismatch():
    """Defense-in-Depth: die Karte meldet grün, aber mit einem VERALTETEN def_hash (die
    Definition wurde zwischen Push und Lauf editiert) ⇒ der Core re-gatet und klemmt auf
    pre_approval — grün gilt nur bei passender Identität."""
    _, fac = _spy_factory()
    orch = _monitored_orch()
    eval_status = {"orch": {"aussenwirkung": {"gruen": True, "def_hash": "VERALTET"}}}
    katalog = _kat([orch], read=[], factory=fac, eval_status=eval_status)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert "pre_approval" in res


def test_bereich_kappe_aus_karte_schattet():
    """Die Regie-Karte liefert die Bereichs-Kappe (docs/83 §4): steht der Bereich des
    Agenten auf ``beobachten``, wird selbst ein monitored+eval_gruen-Agent auf T0 gedeckelt
    ⇒ Schatten (nie Vorschlag). min(Agent, Bereich, Kappe) — die strengste Politik gewinnt."""
    p_calls, fac = _spy_factory()
    s_calls, sfac = _spy_schatten()
    orch = _monitored_orch()
    eval_status = {"orch": {"aussenwirkung": {"gruen": True,
                                              "def_hash": definitions_hash(orch)}}}
    bereich_stufen = {"orch": {"aussenwirkung": "beobachten"}}
    katalog = _kat([orch], read=[], factory=fac, schatten_factory=sfac,
                   eval_status=eval_status, bereich_stufen=bereich_stufen)
    tool = next(t for t in katalog if t.name == "kommunikation_email_senden")
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Kunde wartet"}))
    assert "NICHT ausgeführt" in res and "beobachten" in res
    assert p_calls == [] and len(s_calls) == 1       # Bereichs-Kappe ⇒ Schatten, kein propose
