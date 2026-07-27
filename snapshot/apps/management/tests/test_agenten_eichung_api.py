"""Tests RG-5 (docs/83 §4): die Eichungs-Endpunkte (poll + eval-Lesen) end-to-end.

Fake-Spine (injizierbarer ``eichung_fetch`` über einen MUTABLEN Store — so kann der Test
den Agenten anlegen und DANN Ereignisse für dessen id einspeisen) + Fake-Core. Ein POST
/eichung/poll zieht ``hitl_entschieden``, rechnet die Eichung und legt agent_evals an; GET
/api/agenten/{aid}/eval liest die Karte MIT def_hash-Frische — ein Prompt-Edit macht
``aktuell_gruen`` sofort False. Golden-Gate-Setting fail-closed. Ollama-frei.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm
from managementapp.agenten_domain import EICHUNG_GOLDEN_SETTING


class _FakeCore:
    def __init__(self, laeufe=None):
        self.pushes: list[dict] = []
        self._laeufe = laeufe or []

    async def regie_karte_push(self, karte):
        self.pushes.append(karte)
        return {"ok": True, "abos": len(karte.get("abos", [])),
                "agenten": len(karte.get("agenten", {}))}

    async def laeufe(self, status=""):
        return self._laeufe


def _spine(store: dict):
    """Fake-Spine-Fetcher über einen mutablen Store (nach dem Agent-Anlegen befüllbar)."""
    def fetch(quelle, seit):
        return [e for e in store.get(quelle, []) if int(e["seq"]) > seit]
    return fetch


def _ev(seq, agent_id, approve, klasse="aussenwirkung"):
    return {"seq": seq, "id": f"e{seq}", "typ": "hitl_entschieden", "klasse": klasse,
            "payload": {"aktion": "mail_senden", "approve": approve,
                        "status": "executed" if approve else "rejected",
                        "agent_id": agent_id, "lauf_id": f"l{seq}"}}


def _client(tmp_path, store, core=None) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path, agent_core_client=core or _FakeCore(),
                                   agent_eichung_fetch=_spine(store)))


def _agent(c, name, **kw) -> str:
    return c.post("/api/agenten", json={"name": name, **kw}).json()["id"]


def _25_events(aid, ok=22, reject=3):
    return [_ev(i, aid, True) for i in range(1, ok + 1)] + \
           [_ev(ok + j, aid, False) for j in range(1, reject + 1)]


def test_poll_endpoint_legt_eval_an_und_pusht(tmp_path):
    core, store = _FakeCore(), {}
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "E-Mail-Manager", status="aktiv")
        c.put("/api/settings", json={"key": EICHUNG_GOLDEN_SETTING, "value": True})
        store["kommunikation"] = _25_events(aid)             # 22/25 approved = 0.88
        res = c.post("/api/agenten/eichung/poll").json()
        assert res["verbucht"] == 25 and res["gepusht"] is True
        z = next(z for z in c.get(f"/api/agenten/{aid}/eval").json()["evals"]
                 if z["klasse"] == "aussenwirkung")
        assert z["gruen"] is True and z["aktuell_gruen"] is True
        # der Push trägt den Eval-Status zum Core (RG-5 — Wiring in Slice 3 geprüft)
        assert core.pushes


def test_prompt_edit_macht_eval_ungruen_ueber_def_hash(tmp_path):
    """Selbstbeweis: grüne Eichung + Prompt-Edit ⇒ aktuell_gruen False (def_hash wechselt)."""
    core, store = _FakeCore(), {}
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "Manager", system_prompt="v1", status="aktiv")
        c.put("/api/settings", json={"key": EICHUNG_GOLDEN_SETTING, "value": True})
        store["kommunikation"] = _25_events(aid, ok=25, reject=0)
        c.post("/api/agenten/eichung/poll")
        vorher = next(z for z in c.get(f"/api/agenten/{aid}/eval").json()["evals"]
                      if z["klasse"] == "aussenwirkung")
        assert vorher["aktuell_gruen"] is True
        # Prompt ändern ⇒ def_hash wechselt ⇒ gespeicherte Eichung erlischt
        c.patch(f"/api/agenten/{aid}", json={"system_prompt": "v2 GEÄNDERT"})
        nachher = next(z for z in c.get(f"/api/agenten/{aid}/eval").json()["evals"]
                       if z["klasse"] == "aussenwirkung")
        assert nachher["gruen"] is True and nachher["aktuell_gruen"] is False
        assert "def_hash" in nachher["frische"]


def test_poll_ohne_golden_bleibt_ungruen(tmp_path):
    """Golden-Gate fail-closed: ohne bestätigte Golden-Suite bleibt die Ampel ungrün,
    egal wie gut die Präzision ist (Leitplanke — nichts geht eigenmächtig live)."""
    core, store = _FakeCore(), {}
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "Manager", status="aktiv")
        store["kommunikation"] = _25_events(aid, ok=25, reject=0)
        c.post("/api/agenten/eichung/poll")                  # Golden-Setting bleibt Default False
        z = next(z for z in c.get(f"/api/agenten/{aid}/eval").json()["evals"]
                 if z["klasse"] == "aussenwirkung")
        assert z["gruen"] is False and any("Golden" in g for g in z["gruende"])


def test_budget_disziplin_aus_core_laeufen(tmp_path):
    """Budget-Disziplin fließt aus den Core-Läufen: viele Budget-Abbrüche ⇒ ungrün."""
    store: dict = {}
    core = _FakeCore(laeufe=[])
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "Manager", status="aktiv")
        core._laeufe = [{"agent_id": aid, "fehler": "Tool-Budget erschöpft"}] * 20  # 0/20 im Budget
        c.put("/api/settings", json={"key": EICHUNG_GOLDEN_SETTING, "value": True})
        store["kommunikation"] = _25_events(aid, ok=25, reject=0)
        c.post("/api/agenten/eichung/poll")
        z = next(z for z in c.get(f"/api/agenten/{aid}/eval").json()["evals"]
                 if z["klasse"] == "aussenwirkung")
        assert z["gruen"] is False and any("Budget" in g for g in z["gruende"])


def test_regie_karte_traegt_eval_status_und_bereich(tmp_path):
    """RG-5 Slice 3: nach dem Poll trägt die Regie-Karte den Eval-Status (def_hash-gegated)
    + die Bereichs-Kappen zum Core — das ist die Naht, an der Cores wirksame_stufe endlich
    echtes eval_gruen bekommt."""
    core, store = _FakeCore(), {}
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "E-Mail-Manager", status="aktiv")
        c.post("/api/agenten/abos", json={"agent_id": aid, "quelle_app": "kommunikation",
               "ereignis_typ": "mail_eingegangen", "aktiv": True})   # in den Wald
        c.put("/api/settings", json={"key": EICHUNG_GOLDEN_SETTING, "value": True})
        store["kommunikation"] = _25_events(aid)
        c.post("/api/agenten/eichung/poll")
        karte = c.get("/api/agenten/regie-karte").json()
        assert karte["eval_status"][aid]["aussenwirkung"]["gruen"] is True
        assert karte["eval_status"][aid]["aussenwirkung"]["def_hash"]
        # Bereichs-Kappe je Klasse (unkonfigurierter Bereich ⇒ beobachten, fail-closed V-1)
        assert karte["bereich_stufen"][aid]["geld"] == "beobachten"


def test_eichung_uebersicht_gruppiert_mit_frische(tmp_path):
    """Die Eine-Fetch-Projektion der Eichungs-Karten (+U): je Agent Name + Karten mit
    aktuell_gruen. Prompt-Edit ⇒ aktuell_gruen kippt (Frische gegen die aktuelle def_hash)."""
    core, store = _FakeCore(), {}
    with _client(tmp_path, store, core) as c:
        aid = _agent(c, "E-Mail-Manager", system_prompt="v1", status="aktiv")
        c.put("/api/settings", json={"key": EICHUNG_GOLDEN_SETTING, "value": True})
        store["kommunikation"] = _25_events(aid)
        c.post("/api/agenten/eichung/poll")
        d = c.get("/api/agenten/eichung").json()
        agent = next(a for a in d if a["agent_id"] == aid)
        assert agent["name"] == "E-Mail-Manager"
        z = next(z for z in agent["evals"] if z["klasse"] == "aussenwirkung")
        assert z["aktuell_gruen"] is True and z["frische"] == "aktuell"
        # Prompt ändern ⇒ Frische kippt (die Karte zeigt es ehrlich)
        c.patch(f"/api/agenten/{aid}", json={"system_prompt": "v2"})
        z2 = next(z for z in next(a for a in c.get("/api/agenten/eichung").json()
                                  if a["agent_id"] == aid)["evals"]
                  if z["klasse"] == "aussenwirkung")
        assert z2["aktuell_gruen"] is False and "def_hash" in z2["frische"]


def test_evals_liste_leer_und_agent_404(tmp_path):
    with _client(tmp_path, {}) as c:
        assert c.get("/api/agenten/evals").json() == []
        assert c.get("/api/agenten/eichung").json() == []
        assert c.get("/api/agenten/ghost/eval").status_code == 404
