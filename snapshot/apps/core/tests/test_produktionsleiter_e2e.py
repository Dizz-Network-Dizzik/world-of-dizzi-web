"""E2E K-9 (RG-5, docs/83 §2/§5): der Produktionsleiter-Fluss durch die Core-Regie.

Creating legt ``drop_bereit`` in den Spine → die Core-Regie zieht es (Cursor), zündet
über das Abo (creator × drop_bereit) den Produktionsleiter → dessen Lauf schlägt — HITL —
ein Zertifikat vor (``pending``). Fake-Spine (Pull-Konserve) + Fake-Runtime + Spy-propose
(kein HTTP an Creating, kein Ollama). Zeigt die K-9-Naht lebendig, ohne irgendetwas live
zu aktivieren (der Test setzt das Abo aktiv; produktiv installiert die Vorlage es AUS).
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from appkit.agenten import AgentBudget, AgentDef
from app.config import DEFAULT_USER_ID
from app.ai import agenten_katalog as kat
from app.ai import agenten_regie as regie
from app.ai import agenten_routes as ar

U = DEFAULT_USER_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _karte(*, autonomie) -> dict:
    """Regie-Karte mit dem Produktionsleiter (Zertifikat-Grant) + aktivem drop_bereit-Abo."""
    pl = asdict(AgentDef(id="pl", name="Produktionsleiter", system_prompt="PL",
                         sensitivitaet="hoch", werkzeuge=("creator_zertifikat_vorschlagen",),
                         autonomie=autonomie, budget=AgentBudget()))
    return {"abos": [{"agent_id": "pl", "quelle_app": "creator", "ereignis_typ": "drop_bereit",
                      "bereich_id": "", "auftrag": "Zertifikat", "max_pro_tag": 20,
                      "aktiv": True}],
            "agenten": {"pl": pl}, "agent_sens": {"pl": "hoch"},
            "eval_status": {}, "bereich_stufen": {},
            "pushed_at": "2026-07-13T00:00:00+00:00"}


def _drop_event(seq=1) -> dict:
    """Ein drop_bereit-Ereignis (Zeiger, quelle_sens=hoch wie die Creating-App)."""
    return {"seq": seq, "id": "drop1", "typ": "drop_bereit", "quelle_sens": "hoch",
            "ref": "creator:werk:w1", "bereich_id": ""}


def _pull(events):
    async def p(quelle, cursor):
        return [e for e in events if e["seq"] > cursor]
    return p


def _fake_katalog(monkeypatch, sink, *, schatten_sink=None):
    """Ersetzt ``_KATALOG`` durch den ECHTEN katalog_bauen mit Spy-propose (statt HTTP an
    Creating) — so wird die Zertifikat-Aktion propose-gewrappt und ihr Aufruf aufgezeichnet."""
    async def fake_kat(agenten, wurzel_id, lauf_id, sensitive):
        def pfac(app_id, aktion, agent_id, lid):
            async def fn(_n, params, warum):
                sink.append({"app": app_id, "aktion": aktion, "warum": warum, "params": params})
                return {"id": "act-1", "status": "pending"}
            return fn

        def sfac(agent_id, lid):
            async def fn(name, params, warum):
                if schatten_sink is not None:
                    schatten_sink.append({"name": name, "warum": warum})
                return {"id": "sch-1", "status": "schatten"}
            return fn

        async def leer(_sensitive):
            return []

        karte = regie.regie_karte_holen(U)
        return await kat.katalog_bauen(
            agenten=agenten, wurzel_id=wurzel_id, lauf_id=lauf_id, sensitive=sensitive,
            propose_factory=pfac, registry_fn=leer,
            schatten_factory=sfac if schatten_sink is not None else None,
            eval_status=karte.get("eval_status", {}),
            bereich_stufen=karte.get("bereich_stufen", {}))
    monkeypatch.setattr(ar, "_KATALOG", fake_kat)


def _fake_runtime(monkeypatch):
    """Der Produktionsleiter (Fake-Modell) ruft sein Zertifikat-Tool mit WARUM."""
    async def fake_rt(messages, tools, model=None):
        by = {t.name: t for t in tools}
        tool = by.get("creator_zertifikat_vorschlagen")
        if tool is not None:
            yield ("t", await tool.run({"werk": "w1", "warum": "Drop sichtungsreif"}))
        else:
            yield ("t", "kein Zertifikat-Tool im Katalog")
    monkeypatch.setattr(ar, "_RUNTIME", fake_rt)


async def _run_fn(snap, auftrag, sensitive):
    return await ar.lauf_aus_regie(U, snap, auftrag, sensitive=sensitive)


@pytest.mark.anyio
async def test_drop_bereit_zuendet_produktionsleiter_und_proposet_zertifikat(monkeypatch):
    """Der volle K-9-Fluss bei T1 (pre_approval): drop_bereit ⇒ Zündung ⇒ Zertifikat als
    pending-Vorschlag (HITL). Die Ereignis→Lauf-Kette ist in der Zündungs-Liste sichtbar."""
    regie.regie_karte_speichern(U, _karte(autonomie={"aussenwirkung": "pre_approval"}))
    proposes: list[dict] = []
    _fake_katalog(monkeypatch, proposes)
    _fake_runtime(monkeypatch)

    started = await regie.tick(U, ist_aktiv=True, pull_fn=_pull([_drop_event()]),
                               run_fn=_run_fn)
    assert len(started) == 1                              # genau ein Lauf gezündet
    kette = regie.zuendungen_liste(U)
    assert any(z["ereignis_typ"] == "drop_bereit" and z["agent_id"] == "pl"
               and z["status"] == "gestartet" for z in kette)
    assert len(proposes) == 1                             # Zertifikat als pending (HITL)
    assert proposes[0]["app"] == "creator"
    assert proposes[0]["aktion"] == "zertifikat_vorschlagen"
    assert proposes[0]["warum"] == "Drop sichtungsreif"


@pytest.mark.anyio
async def test_drop_bereit_t0_schattet_statt_propose(monkeypatch):
    """Wie die Vorlage produktiv installiert (unkonfiguriert ⇒ beobachten/T0): das Zertifikat
    wird nur BEOBACHTET (Schatten), nie vorgeschlagen — die sichere Ruhe-Naht (Leitplanke)."""
    regie.regie_karte_speichern(U, _karte(autonomie={}))   # T0
    proposes: list[dict] = []
    schatten: list[dict] = []
    _fake_katalog(monkeypatch, proposes, schatten_sink=schatten)
    _fake_runtime(monkeypatch)

    await regie.tick(U, ist_aktiv=True, pull_fn=_pull([_drop_event()]), run_fn=_run_fn)
    assert proposes == [] and len(schatten) == 1           # eingedämmt: nur Schatten
    assert schatten[0]["name"] == "creator_zertifikat_vorschlagen"
