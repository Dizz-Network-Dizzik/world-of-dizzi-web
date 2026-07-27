"""Tests Z4.2-D (docs/63 §3 „Ausführungs-API"): Core-SSE-Endpunkt + Definition-Brücke.

Fake-Runtime + Fake-Katalog (Modul-Injektionspunkte ``_RUNTIME``/``_KATALOG``) — kein Ollama,
keine MCP-Subprozesse. Deckt: SSE-Stream + Persistenz · Snapshot-Rekonstruktion inkl.
Delegation · ungültiger Snapshot ⇒ 422 · Offline-Runtime ⇒ ehrliches Fehler-Ende (§6.5) ·
Katalog-Setup-Fehler nie hängend · Stop-Endpunkt · Task-Ledger (GET /laeufe).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi.testclient import TestClient

from appkit.agenten import AgentDef
from app.config import DEFAULT_USER_ID
from app.main import app
from app.ai import agenten_laeufe as laeufe
from app.ai import agenten_routes as ar

client = TestClient(app)


def _snap(*agenten: AgentDef, wurzel: str | None = None) -> dict:
    """Definition-Snapshot in der Form von ``schnappschuss`` (Definition-Brücke-Push)."""
    return {"wurzel": wurzel or agenten[0].id, "agenten": {a.id: asdict(a) for a in agenten}}


def _events(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def _leer_katalog():
    async def fake_kat(agenten, wurzel_id, lauf_id, sensitive):
        return []
    return fake_kat


def test_lauf_sse_und_persistenz(monkeypatch):
    async def fake_rt(messages, tools, model=None):
        yield ("t", "hallo")
        yield ("t", " welt")

    monkeypatch.setattr(ar, "_RUNTIME", fake_rt)
    monkeypatch.setattr(ar, "_KATALOG", _leer_katalog())
    snap = _snap(AgentDef(id="o", name="O", system_prompt="O", sensitivitaet="normal"))
    r = client.post("/api/agenten/lauf", json={"snapshot": snap, "auftrag": "hi"})
    assert r.status_code == 200
    evs = _events(r.text)
    assert evs[0]["start"] is True and evs[0]["agent_id"] == "o"
    lauf_id = evs[0]["lauf_id"]
    assert "".join(e["t"] for e in evs if "t" in e) == "hallo welt"
    assert evs[-1]["done"] is True and evs[-1]["status"] == "fertig"

    row = laeufe.lauf_holen(DEFAULT_USER_ID, lauf_id)
    assert row and row["status"] == "fertig" and row["ended_at"]
    assert row["definition"]["wurzel"] == "o"          # Snapshot eingefroren (P8/Audit)


def test_definition_bruecke_delegation(monkeypatch):
    """Der gepushte Snapshot (Wurzel + Worker) wird rekonstruiert; die Delegation läuft
    über den Orchestrator — KEIN Core→Mgmt-Fetch, alles aus dem Push."""
    async def fake_rt(messages, tools, model=None):
        sysp = next((m["content"] for m in messages if m["role"] == "system"), "")
        if sysp == "ORCH":
            specs = {t.name: t for t in tools}
            yield ("tool", {"name": "delegiere_w1", "args": {"auftrag": "x"}})
            yield ("t", await specs["delegiere_w1"].run({"auftrag": "x"}))
        elif sysp == "P1":
            yield ("t", "WORKER-OK")

    monkeypatch.setattr(ar, "_RUNTIME", fake_rt)
    monkeypatch.setattr(ar, "_KATALOG", _leer_katalog())
    orch = AgentDef(id="orch", name="O", system_prompt="ORCH", sub_agenten=("w1",))
    w1 = AgentDef(id="w1", name="W1", system_prompt="P1")
    r = client.post("/api/agenten/lauf", json={"snapshot": _snap(orch, w1, wurzel="orch")})
    evs = _events(r.text)
    assert any(e.get("tool") == "delegiere_w1" for e in evs)
    assert any(e.get("t") == "WORKER-OK" for e in evs)
    row = laeufe.lauf_holen(DEFAULT_USER_ID, evs[0]["lauf_id"])
    assert row["delegationen"] == 1
    assert set(row["definition"]["agenten"]) == {"orch", "w1"}


def test_ungueltiger_snapshot_422():
    r = client.post("/api/agenten/lauf", json={"snapshot": {"wurzel": "x", "agenten": {}}})
    assert r.status_code == 422


def test_runtime_offline_endet_ehrlich(monkeypatch):
    async def fake_rt(messages, tools, model=None):
        raise RuntimeError("Ollama offline")
        yield  # macht rt zum async generator (unerreichbar)

    monkeypatch.setattr(ar, "_RUNTIME", fake_rt)
    monkeypatch.setattr(ar, "_KATALOG", _leer_katalog())
    snap = _snap(AgentDef(id="o", name="O", system_prompt="O"))
    r = client.post("/api/agenten/lauf", json={"snapshot": snap})
    evs = _events(r.text)
    done = evs[-1]
    assert done["done"] is True and done["status"] == "fehler"
    assert "Ollama offline" in done["fehler"]
    row = laeufe.lauf_holen(DEFAULT_USER_ID, evs[0]["lauf_id"])
    assert row["status"] == "fehler" and row["ended_at"]     # nie hängend (§6.5)


def test_katalog_fehler_endet_ehrlich(monkeypatch):
    async def kaputt(agenten, wurzel_id, lauf_id, sensitive):
        raise RuntimeError("Katalog kaputt")

    monkeypatch.setattr(ar, "_KATALOG", kaputt)
    snap = _snap(AgentDef(id="o", name="O", system_prompt="O"))
    r = client.post("/api/agenten/lauf", json={"snapshot": snap})
    evs = _events(r.text)
    assert any("error" in e for e in evs)
    assert evs[-1]["status"] == "fehler"
    row = laeufe.lauf_holen(DEFAULT_USER_ID, evs[0]["lauf_id"])
    assert row["status"] == "fehler" and row["ended_at"]     # Setup-Fehler ⇒ nicht hängend


def test_stop_endpunkt():
    a = AgentDef(id="o", name="O")
    lauf_id = laeufe.lauf_anlegen(DEFAULT_USER_ID, a, {})
    assert client.post(f"/api/agenten/lauf/{lauf_id}/stop").json()["gestoppt"] is True
    assert client.post("/api/agenten/lauf/gibtsnicht/stop").json()["gestoppt"] is False


def test_laeufe_ledger_und_holen():
    a = AgentDef(id="o", name="O")
    lauf_id = laeufe.lauf_anlegen(DEFAULT_USER_ID, a, {})
    liste = client.get("/api/agenten/laeufe").json()
    assert any(r["id"] == lauf_id for r in liste)
    einzeln = client.get(f"/api/agenten/laeufe/{lauf_id}").json()
    assert einzeln["id"] == lauf_id and einzeln["status"] == "laeuft"
    assert client.get("/api/agenten/laeufe/nope").status_code == 404
    assert all(r["status"] == "laeuft"
               for r in client.get("/api/agenten/laeufe?status=laeuft").json())
