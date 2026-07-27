"""Tests Z4.2-B (docs/63 §1/§3): Lauf-Verwaltung (Core-DB) — Snapshot, Zähler,
stop_signal (≤1 Event später), ehrliches Fehler-Ende. Fake-Runtime, kein Ollama.
"""

from __future__ import annotations

import asyncio

from appkit.agenten import AgentBudget, AgentDef
from app.ai import agenten_laeufe as laeufe


def _agent(aid, *, prompt="", subs=(), budget=None):
    return AgentDef(id=aid, name=aid.upper(), system_prompt=prompt or aid,
                    sub_agenten=tuple(subs), budget=budget or AgentBudget())


def _resolver(*ags):
    m = {a.id: a for a in ags}
    return lambda i: m.get(i)


async def _collect(gen):
    return [ev async for ev in gen]


def test_lauf_zeile_vollstaendig_nach_delegation():
    """P8: nach einem Lauf mit Delegation ist die Zeile vollständig (Snapshot, Zähler,
    Status, ended_at)."""
    orch_a = _agent("orch", prompt="ORCH", subs=("w1",))
    w1 = _agent("w1", prompt="P1")
    resolver = _resolver(orch_a, w1)
    snap = laeufe.schnappschuss(orch_a, resolver)
    lauf_id = laeufe.lauf_anlegen("dizzi", orch_a, snap)

    async def rt(messages, tools, model=None):
        sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
        specs = {t.name: t for t in tools}
        if sysp == "ORCH":
            yield ("tool", {"name": "delegiere_w1", "args": {"auftrag": "x"}})
            yield ("t", await specs["delegiere_w1"].run({"auftrag": "x"}))
        elif sysp == "P1":
            yield ("t", "WORKER-ERGEBNIS")

    events = asyncio.run(_collect(laeufe.lauf_streamen(
        "dizzi", lauf_id, orch_a, "auftrag", katalog=[], resolver=resolver, runtime=rt)))
    assert ("t", "WORKER-ERGEBNIS") in events

    row = laeufe.lauf_holen("dizzi", lauf_id)
    assert row["status"] == "fertig" and row["delegationen"] == 1
    assert row["ended_at"] and row["fehler"] == ""
    assert row["definition"]["wurzel"] == "orch"
    assert set(row["definition"]["agenten"]) == {"orch", "w1"}
    assert row["nutzung"] == {}                      # Q1-Slot leer (ehrliche Vorbedingung)


def test_stop_wirkt_hoechstens_ein_event_spaeter():
    orch_a = _agent("o", prompt="O")
    lauf_id = laeufe.lauf_anlegen("dizzi", orch_a, {})

    async def rt(messages, tools, model=None):
        for i in range(50):
            yield ("t", str(i))

    async def run():
        seen = []
        async for ev in laeufe.lauf_streamen("dizzi", lauf_id, orch_a, "x", katalog=[],
                                             resolver=lambda _i: None, runtime=rt):
            seen.append(ev)
            if sum(1 for e in seen if e[0] == "t") == 3:   # nach dem 3. Token stoppen
                laeufe.stop_anfordern("dizzi", lauf_id)
        return seen

    seen = asyncio.run(run())
    tokens = [e for e in seen if e[0] == "t"]
    assert len(tokens) == 3                          # kein 4. Token — Stop an der Grenze
    assert seen[-1] == ("lauf", {"status": "gestoppt", "grund": "stop_signal"})
    row = laeufe.lauf_holen("dizzi", lauf_id)
    assert row["status"] == "gestoppt" and row["ended_at"]


def test_lauf_fehler_endet_ehrlich():
    orch_a = _agent("o", prompt="O")
    lauf_id = laeufe.lauf_anlegen("dizzi", orch_a, {})

    async def rt(messages, tools, model=None):
        raise RuntimeError("Ollama offline")
        yield  # macht rt zum async generator (unerreichbar)

    events = asyncio.run(_collect(laeufe.lauf_streamen(
        "dizzi", lauf_id, orch_a, "x", katalog=[], resolver=lambda _i: None, runtime=rt)))
    assert any(e[0] == "lauf" and e[1].get("status") == "fehler" for e in events)
    row = laeufe.lauf_holen("dizzi", lauf_id)
    assert row["status"] == "fehler" and "Ollama offline" in row["fehler"]
    assert row["ended_at"]                           # nie hängend (Akzeptanz §6.5)


def test_stop_anfordern_unbekannt_oder_beendet():
    assert laeufe.stop_anfordern("dizzi", "gibtsnicht") is False
    orch_a = _agent("o")
    lauf_id = laeufe.lauf_anlegen("dizzi", orch_a, {})
    assert laeufe.stop_anfordern("dizzi", lauf_id) is True     # laufend ⇒ gesetzt
    laeufe._finalisieren(lauf_id, laeufe.STATUS_FERTIG,
                         laeufe.orch.LaufZustand(budget=AgentBudget()), "", {})
    assert laeufe.stop_anfordern("dizzi", lauf_id) is False    # beendet ⇒ kein Stop mehr


def test_laeufe_liste_und_isolation():
    orch_a = _agent("o")
    id1 = laeufe.lauf_anlegen("dizzi", orch_a, {})
    id2 = laeufe.lauf_anlegen("dizzi", orch_a, {})
    laeufe.lauf_anlegen("anderer", orch_a, {})       # anderer Nutzer ⇒ nicht sichtbar
    liste = laeufe.laeufe_liste("dizzi")
    assert {r["id"] for r in liste} == {id1, id2}
    assert all(r["status"] == "laeuft" for r in liste)


def test_schnappschuss_reuse_und_baum():
    o = _agent("o", subs=("a", "b"))
    a = _agent("a", subs=("w",))
    b = _agent("b", subs=("w",))          # Worker-Reuse in zwei Ästen
    w = _agent("w")
    snap = laeufe.schnappschuss(o, _resolver(o, a, b, w))
    assert snap["wurzel"] == "o"
    assert set(snap["agenten"]) == {"o", "a", "b", "w"}   # Reuse ⇒ w genau einmal
