"""Tests Z4.2-C (docs/63 §3/§4): HITL-Verdrahtung — Aktion = propose, nie direkt.

Deckt §6-Messpunkt 1 (kein Vollzug ohne Inbox-Approve: propose ⇒ pending, nie direkt
executed) + die fail-closed-Achsen: WARUM Pflicht, geld/gesundheit unlockbar, Q2-Klemme.
Reine async Unit-Tests (injizierte propose_fn/freigabe_fn), kein Ollama/keine App.
"""

from __future__ import annotations

import asyncio

from app.ai.agenten_hitl import aktions_tool


def _spy():
    """Fake-propose/-freigabe/-schatten, die ihre Aufrufe protokollieren."""
    calls = {"propose": [], "freigabe": [], "schatten": []}

    async def propose_fn(name, params, warum):
        calls["propose"].append({"name": name, "params": params, "warum": warum})
        return {"id": "act-1", "status": "pending"}

    async def freigabe_fn(aid):
        calls["freigabe"].append(aid)
        return {"status": "executed"}

    async def schatten_fn(name, params, warum):
        calls["schatten"].append({"name": name, "params": params, "warum": warum})
        return {"id": "sch-1", "status": "schatten"}

    return calls, propose_fn, freigabe_fn, schatten_fn


def _tool(**kw):
    calls, propose_fn, freigabe_fn, schatten_fn = _spy()
    defaults = dict(name="email_senden", level="verifiziert",
                    beschreibung="E-Mail senden", parameter={"type": "object",
                    "properties": {"an": {"type": "string"}}, "required": ["an"]},
                    propose_fn=propose_fn, agent_id="triage-1", lauf_id="lauf-9",
                    freigabe_fn=freigabe_fn, schatten_fn=schatten_fn)
    defaults.update(kw)
    return calls, aktions_tool(**defaults)


def test_aktion_proposet_bei_pre_approval_nie_direkt():
    """§6.1: aussenwirkung auf pre_approval ⇒ propose ⇒ pending; KEINE Auto-Freigabe.
    (V-1: die Stufe muss konfiguriert sein — unkonfiguriert wäre beobachten/Schatten.)"""
    calls, tool = _tool(bereich_stufe="pre_approval", agent_stufe="pre_approval")
    res = asyncio.run(tool.run({"an": "kunde@x.org", "warum": "Rechnung überfällig"}))
    assert len(calls["propose"]) == 1 and calls["schatten"] == []
    assert calls["propose"][0]["params"] == {"an": "kunde@x.org"}   # warum getrennt
    assert calls["propose"][0]["warum"] == "Rechnung überfällig"
    assert calls["freigabe"] == []                                  # nie direkt ausgeführt
    assert "wartet auf Freigabe" in res and "pre_approval" in res


def test_beobachten_schattet_statt_propose():
    """V-1/RG-4: unkonfiguriert ⇒ beobachten ⇒ Schatten — NIE propose, NIE Freigabe;
    der Agent erfährt den Beobachtungs-Modus EHRLICH (kein vorgetäuschter Vollzug)."""
    calls, tool = _tool()                                          # keine Stufen ⇒ beobachten
    res = asyncio.run(tool.run({"an": "kunde@x.org", "warum": "Rechnung überfällig"}))
    assert calls["propose"] == [] and calls["freigabe"] == []
    assert len(calls["schatten"]) == 1
    assert calls["schatten"][0]["params"] == {"an": "kunde@x.org"}
    assert "NICHT ausgeführt" in res and "NICHT vorgeschlagen" in res
    assert "beobachten" in res and "sch-1" in res


def test_beobachten_ohne_schatten_fn_meldet_trotzdem_ehrlich():
    """Ohne schatten_fn (None) wird nichts persistiert — aber der Agent bekommt trotzdem
    die ehrliche Meldung (kein stiller Vollzug), und propose bleibt aus."""
    calls, tool = _tool(schatten_fn=None)
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "test"}))
    assert calls["propose"] == [] and "NICHT ausgeführt" in res


def test_warum_ist_pflicht():
    calls, tool = _tool()
    res = asyncio.run(tool.run({"an": "k@x.org"}))                  # kein warum
    assert "WARUM ist Pflicht" in res
    assert calls["propose"] == []                                   # nichts vorgeschlagen
    # das Schema erzwingt warum zusätzlich deklarativ:
    assert "warum" in tool.parameters["required"]


def test_geld_bleibt_pre_approval_trotz_eval_und_monitored():
    """geld (level hochsicher) ist unlockbar — selbst mit eval_gruen + monitored."""
    calls, tool = _tool(level="hochsicher", name="kapital_zuweisen",
                        bereich_stufe="autonom_audit", agent_stufe="autonom_audit",
                        eval_gruen=True)
    res = asyncio.run(tool.run({"betrag": 100, "warum": "Order fällig"}))
    assert calls["freigabe"] == []                                  # NIE ausgeführt
    assert "pre_approval" in res and "geld" in res


def test_gesundheit_klasse_override_bleibt_pre_approval():
    """healthy deklariert explizit klasse='gesundheit' (strenger als das Level) ⇒ Boden."""
    calls, tool = _tool(name="vitalwert_melden", level="verifiziert", klasse="gesundheit",
                        bereich_stufe="monitored", agent_stufe="monitored", eval_gruen=True)
    res = asyncio.run(tool.run({"wert": 120, "warum": "Grenzwert"}))
    assert calls["freigabe"] == [] and "pre_approval" in res


def test_monitored_mit_eval_fuehrt_aus_mit_sichtbarkeit():
    """Wired für Q2: aussenwirkung + monitored + eval_gruen ⇒ propose UND Auto-Freigabe."""
    calls, tool = _tool(bereich_stufe="monitored", agent_stufe="monitored", eval_gruen=True)
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Follow-up"}))
    assert len(calls["propose"]) == 1 and calls["freigabe"] == ["act-1"]
    assert "freigegeben" in res and "monitored" in res


def test_monitored_ohne_eval_bleibt_pending_q2_klemme():
    """Ohne Eval-Grün klemmt wirksame_stufe zurück auf pre_approval (Q2 vor Autonomie)."""
    calls, tool = _tool(bereich_stufe="monitored", agent_stufe="monitored", eval_gruen=False)
    res = asyncio.run(tool.run({"an": "k@x.org", "warum": "Follow-up"}))
    assert calls["freigabe"] == [] and "pre_approval" in res
