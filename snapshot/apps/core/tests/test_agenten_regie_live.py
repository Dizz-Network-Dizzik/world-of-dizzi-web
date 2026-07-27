"""Tests RG-3b (docs/83 §2/§3): die Live-Verdrahtung über dem RG-3a-Scheduler-Kern.

Deckt die harten Zusagen der Verdrahtung — mit FAKES (kein HTTP, kein Ollama):
Regie-Karte-Round-Trip (Push→Arbeitskopie) · ``tick`` zündet bei aktiv, schaut bei
Not-Aus (Cursor rückt vor, kein Lauf) · offline-Quelle (Pull=None) ehrlich übersprungen
· Wiederaufnahme einer offenen Zündung (Crash-Sim: geplant, dann später gestartet) ·
Budget-Deckel (Abo max_pro_tag ⇒ budget_erschoepft + Glocke, nie stiller Drop) ·
Verfalls-Hygiene (offen >24 h ⇒ verfallen) · Snapshot aus dem Karten-Wald (erreichbarer
Sub-Baum) · ``lauf_aus_regie`` fährt einen echten Lauf zu Ende (Fake-Runtime).
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from appkit.agenten import AgentBudget, AgentDef
from app.config import DEFAULT_USER_ID
from app.main import app
from app.ai import agenten_laeufe as laeufe
from app.ai import agenten_regie as regie
from app.ai import agenten_routes as ar

U = DEFAULT_USER_ID
client = TestClient(app)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Bau-Helfer ------------------------------------------------------------------

def _agent(aid="mgr", *, sens="hoechst", subs=(), lpt=20) -> dict:
    return asdict(AgentDef(id=aid, name=aid.upper(), system_prompt="P",
                           sensitivitaet=sens, sub_agenten=tuple(subs),
                           budget=AgentBudget(laeufe_pro_tag=lpt)))


def _abo(agent="mgr", quelle="kommunikation", typ="mail_eingegangen", *,
         bereich="", auftrag="", max_pro_tag=20, aktiv=True) -> dict:
    return {"agent_id": agent, "quelle_app": quelle, "ereignis_typ": typ,
            "bereich_id": bereich, "auftrag": auftrag, "max_pro_tag": max_pro_tag,
            "aktiv": aktiv}


def _karte(abos, agenten, *, agent_sens=None) -> dict:
    ag = {a["id"]: a for a in agenten}
    sens = agent_sens or {a["id"]: a["sensitivitaet"] for a in agenten}
    return {"abos": abos, "agenten": ag, "agent_sens": sens, "pushed_at": "2026-07-13T00:00:00+00:00"}


def _ev(seq, eid, typ="mail_eingegangen", *, quelle_sens="hoechst", ref="", bereich=""):
    return {"seq": seq, "id": eid, "typ": typ, "quelle_sens": quelle_sens,
            "ref": ref, "bereich_id": bereich}


def _pull_fest(events):
    """Fake-Pull: liefert die Ereignisse mit ``seq > cursor`` (wie der echte HTTP-Pull)."""
    async def _pull(quelle, cursor):
        return [e for e in events if e["seq"] > cursor]
    return _pull


def _pull_offline():
    async def _pull(quelle, cursor):
        return None                       # Quelle unerreichbar
    return _pull


class _RunRec:
    """Fake-Runner: zeichnet (snapshot, auftrag, sensitive) auf und vergibt lauf_ids."""
    def __init__(self):
        self.calls: list[tuple] = []

    async def __call__(self, snapshot, auftrag, sensitive) -> str:
        self.calls.append((snapshot, auftrag, sensitive))
        return f"lauf_{len(self.calls)}"


# --- Regie-Karte: Push → Core-Arbeitskopie --------------------------------------

def test_regie_karte_round_trip():
    karte = _karte([_abo()], [_agent()])
    regie.regie_karte_speichern(U, karte)
    zurueck = regie.regie_karte_holen(U)
    assert zurueck["abos"][0]["agent_id"] == "mgr"
    assert "mgr" in zurueck["agenten"]
    abos = regie._abos_aus_karte(zurueck)
    assert len(abos) == 1 and abos[0].aktiv and abos[0].quelle_app == "kommunikation"


def test_regie_karte_push_endpoint():
    karte = _karte([_abo(), _abo(agent="a2", typ="mail_gesendet")], [_agent(), _agent("a2")])
    r = client.post("/api/agenten/regie-karte", json=karte)
    assert r.status_code == 200 and r.json()["abos"] == 2 and r.json()["agenten"] == 2
    st = client.get("/api/agenten/regie/status").json()
    assert st["aktiv"] is False and st["abos"] == 2 and st["tick_s"] == 10
    assert st["pushed_at"] == "2026-07-13T00:00:00+00:00"


def test_push_endpoint_vorwaerts_tolerant():
    """RG-5 legt Eval-Status additiv dazu — der Push darf Zusatzfelder tragen (extra=allow)."""
    karte = _karte([_abo()], [_agent()])
    karte["evals"] = {"mgr": {"gruen": False}}
    client.post("/api/agenten/regie-karte", json=karte)
    assert regie.regie_karte_holen(U).get("evals") == {"mgr": {"gruen": False}}


def test_not_aus_schalter_setzt_master():
    """RG-4 Not-Aus (docs/83 §3): der Schalter setzt agenten_regie_aktiv; Einschalten
    ist die gegatete Live-Vorbedingung, Ausschalten immer. Der Status spiegelt es."""
    r = client.post("/api/agenten/regie/schalter", json={"aktiv": True})
    assert r.status_code == 200 and r.json()["aktiv"] is True
    assert client.get("/api/agenten/regie/status").json()["aktiv"] is True
    r2 = client.post("/api/agenten/regie/schalter", json={"aktiv": False})
    assert r2.json()["aktiv"] is False
    assert client.get("/api/agenten/regie/status").json()["aktiv"] is False


# --- tick: zünden bei aktiv, schauen bei Not-Aus --------------------------------

@pytest.mark.anyio
async def test_tick_zuendet_und_startet_lauf():
    regie.regie_karte_speichern(U, _karte([_abo()], [_agent()]))
    run = _RunRec()
    gestartet = await regie.tick(U, ist_aktiv=True, pull_fn=_pull_fest([_ev(1, "e1")]),
                                 run_fn=run)
    assert gestartet == ["lauf_1"]
    assert len(run.calls) == 1
    snap, auftrag, sensitive = run.calls[0]
    assert snap["wurzel"] == "mgr" and sensitive is True
    assert "mail_eingegangen" in auftrag                 # Ereignis-Karte als Zünd-Kontext
    assert regie.offene_zuendungen(U) == []              # Zündung ist gestartet, nicht mehr offen
    assert regie.zuendungen_zaehler(U).get("gestartet") == 1


@pytest.mark.anyio
async def test_tick_not_aus_schaut_zuendet_nicht():
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_na")], [_agent()]))
    run = _RunRec()
    gestartet = await regie.tick(U, ist_aktiv=False,
                                 pull_fn=_pull_fest([_ev(7, "e7")]), run_fn=run)
    assert gestartet == [] and run.calls == []           # Not-Aus: kein Lauf
    assert regie.offene_zuendungen(U) == []              # keine Zündung angelegt
    assert regie.cursor_holen("q_na") == 7               # aber Cursor rückte vor (schauen)


@pytest.mark.anyio
async def test_tick_offline_quelle_ehrlich_uebersprungen():
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_off")], [_agent()]))
    run = _RunRec()
    gestartet = await regie.tick(U, ist_aktiv=True, pull_fn=_pull_offline(), run_fn=run)
    assert gestartet == [] and run.calls == []
    assert regie.cursor_holen("q_off") == 0              # offline ⇒ Cursor unberührt, kein Drop


@pytest.mark.anyio
async def test_tick_wiederaufnahme_offener_zuendung():
    """Crash-Sim: eine Zündung wurde geplant (aktiver Kern), der Prozess starb vor dem
    Lauf-Start. Ein späterer aktiver Tick OHNE neue Ereignisse nimmt sie wieder auf."""
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_wa")], [_agent()]))
    regie.plane_zuendungen(U, "q_wa", [_ev(1, "e_wa")], regie._abos_aus_karte(regie.regie_karte_holen(U)),
                           agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    assert len(regie.offene_zuendungen(U)) == 1          # offen, noch nicht gestartet
    run = _RunRec()
    gestartet = await regie.tick(U, ist_aktiv=True, pull_fn=_pull_fest([]), run_fn=run)
    assert gestartet == ["lauf_1"]                       # wieder aufgenommen
    assert regie.offene_zuendungen(U) == []


# --- Budget-Deckel: nie stiller Drop --------------------------------------------

@pytest.mark.anyio
async def test_budget_abo_deckel_glocke():
    """max_pro_tag=1: das zweite Ereignis desselben Stroms ⇒ budget_erschoepft + Glocke."""
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_bud", max_pro_tag=1)], [_agent()]))
    run = _RunRec()
    gestartet = await regie.tick(U, ist_aktiv=True,
                                 pull_fn=_pull_fest([_ev(1, "b1"), _ev(2, "b2")]), run_fn=run)
    assert len(gestartet) == 1                           # nur EIN Lauf gestartet
    z = regie.zuendungen_zaehler(U)
    assert z.get("gestartet") == 1 and z.get("budget_erschoepft") == 1
    # Glocke geschrieben (ehrlich statt still verschluckt):
    from app import db
    row = db.get_conn().execute(
        "SELECT COUNT(*) AS c FROM notices WHERE user_id=? AND source='regie'", (U,)).fetchone()
    assert row["c"] >= 1


def test_budget_frei_agent_deckel():
    """laeufe_pro_tag (Agent-Budget) zählt über echte Läufe — bei Erreichen fail-closed."""
    a = AgentDef(id="ag_bud", name="AG")
    laeufe.lauf_anlegen(U, a, {})                        # 1 echter Lauf heute
    frei, grund = regie.budget_frei(U, "ag_bud", "kommunikation", "mail_eingegangen", "",
                                    laeufe_pro_tag=1, max_pro_tag=99)
    assert frei is False and "laeufe_pro_tag" in grund
    frei2, _ = regie.budget_frei(U, "ag_bud", "kommunikation", "mail_eingegangen", "",
                                 laeufe_pro_tag=5, max_pro_tag=99)
    assert frei2 is True


# --- Verfalls-Hygiene ------------------------------------------------------------

@pytest.mark.anyio
async def test_verfall_offener_zuendung():
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_vf")], [_agent()]))
    regie.plane_zuendungen(U, "q_vf", [_ev(1, "vf1")], regie._abos_aus_karte(regie.regie_karte_holen(U)),
                           agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    assert len(regie.offene_zuendungen(U)) == 1
    # 25 h nach dem (echten) Anlege-Zeitpunkt: die offene Zündung verfällt (zeit-robust,
    # unabhängig von der Tageszeit des Testlaufs).
    from datetime import datetime, timedelta, timezone
    spaeter = (datetime.now(timezone.utc) + timedelta(hours=25)).isoformat(timespec="seconds")
    n = regie.verfalls_hygiene(U, jetzt_iso=spaeter)
    assert n == 1 and regie.offene_zuendungen(U) == []
    assert regie.zuendungen_zaehler(U).get("verfallen") == 1


def test_verfall_frische_zuendung_bleibt():
    regie.regie_karte_speichern(U, _karte([_abo(quelle="q_fr")], [_agent()]))
    regie.plane_zuendungen(U, "q_fr", [_ev(1, "fr1")], regie._abos_aus_karte(regie.regie_karte_holen(U)),
                           agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    n = regie.verfalls_hygiene(U)                        # jetzt = echt jetzt ⇒ nichts verfällt
    assert n == 0 and len(regie.offene_zuendungen(U)) == 1


# --- Snapshot aus dem Karten-Wald (erreichbarer Sub-Baum) -----------------------

def test_snapshot_aus_karte_subbaum():
    karte = _karte([_abo()], [_agent("orch", subs=("w1",)), _agent("w1"), _agent("fremd")])
    snap = regie._snapshot_aus_karte(karte, "orch")
    assert snap["wurzel"] == "orch"
    assert set(snap["agenten"]) == {"orch", "w1"}        # 'fremd' bleibt draußen (nicht erreichbar)
    assert regie._snapshot_aus_karte(karte, "gibtsnicht") is None


# --- lauf_aus_regie fährt einen echten Lauf zu Ende (Fake-Runtime) --------------

@pytest.mark.anyio
async def test_lauf_aus_regie_faehrt_zu_ende(monkeypatch):
    async def fake_rt(messages, tools, model=None):
        yield ("t", "OK")

    async def fake_kat(agenten, wurzel_id, lauf_id, sensitive):
        return []

    monkeypatch.setattr(ar, "_RUNTIME", fake_rt)
    monkeypatch.setattr(ar, "_KATALOG", fake_kat)
    snap = {"wurzel": "o", "agenten": {"o": asdict(AgentDef(id="o", name="O", system_prompt="O"))}}
    lauf_id = await ar.lauf_aus_regie(U, snap, "hi", sensitive=True)
    row = laeufe.lauf_holen(U, lauf_id)
    assert row and row["status"] == "fertig" and row["ended_at"]
