"""RG-7 (docs/83 §5): die E-Mail-Manager-Werks-Vorlage (Regie-Seite des Piloten).

Ein Klick installiert den BAUM Orchestrator + Triage + Antwort-Entwurf mit exakt den
§5-Grants, sensitivitaet ``hoch`` (⇒ lokal_only) und der Pilot-Verfassung: entwurf bis
``monitored``, aussenwirkung HART ``pre_approval`` (email_senden bleibt IMMER pre_approval).
Fail-closed (Abo AUS, Bereichs-Treppe T0), idempotent (kein Duplikat). Fake-Core.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm


class _FakeCore:
    def __init__(self):
        self.pushes: list[dict] = []

    async def regie_karte_push(self, karte):
        self.pushes.append(karte)
        return {"ok": True, "abos": len(karte.get("abos", [])),
                "agenten": len(karte.get("agenten", {}))}


def _client(tmp_path, core=None) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path, agent_core_client=core or _FakeCore()))


def _agenten_nach_name(c) -> dict:
    return {a["name"]: a for a in c.get("/api/agenten").json()}


def test_vorlagen_liste_enthaelt_email_manager(tmp_path):
    with _client(tmp_path) as c:
        v = c.get("/api/agenten/vorlagen").json()
        em = next(x for x in v if x["name"] == "email_manager")
        assert em["quelle_app"] == "kommunikation"
        assert em["ereignis_typ"] == "mail_eingegangen"


def test_install_baut_orchestrator_und_zwei_worker(tmp_path):
    core = _FakeCore()
    with _client(tmp_path, core) as c:
        r = c.post("/api/agenten/vorlagen/email_manager").json()
        assert r["ok"] is True and r["aktiv"] is False        # Abo AUS (David schaltet)
        oid = r["agent_id"]
        agenten = _agenten_nach_name(c)
        assert set(agenten) >= {"E-Mail-Manager", "E-Mail-Triage", "E-Mail-Antwort-Entwurf"}
        orch = c.get(f"/api/agenten/{oid}").json()
        assert orch["name"] == "E-Mail-Manager" and orch["sensitivitaet"] == "hoch"
        # Baum: Orchestrator trägt die zwei Worker als sub_agenten (Tiefe 2 ≤ 3)
        worker_ids = {agenten["E-Mail-Triage"]["id"],
                      agenten["E-Mail-Antwort-Entwurf"]["id"]}
        assert set(orch["sub_agenten"]) == worker_ids
        assert core.pushes                                    # Regie-Karte reiste zum Core


def test_pilot_verfassung_send_pinned_pre_approval(tmp_path):
    with _client(tmp_path) as c:
        oid = c.post("/api/agenten/vorlagen/email_manager").json()["agent_id"]
        orch = c.get(f"/api/agenten/{oid}").json()
        # aussenwirkung HART pre_approval (email_senden IMMER pre_approval, §5/E4.3);
        # entwurf bis monitored (Entwürfe dürfen nach Eichung direkt in Drafts, §5 Phase 2).
        assert orch["autonomie"]["aussenwirkung"] == "pre_approval"
        assert orch["autonomie"]["entwurf"] == "monitored"


def test_grant_verteilung_ist_injection_schutz(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/agenten/vorlagen/email_manager")
        agenten = _agenten_nach_name(c)
        orch = agenten["E-Mail-Manager"]["werkzeuge"]
        triage = agenten["E-Mail-Triage"]["werkzeuge"]
        antwort = agenten["E-Mail-Antwort-Entwurf"]["werkzeuge"]
        # Senden lebt NUR beim Orchestrator (aussenwirkung, gepinnt); Weiche-Aktionen dort:
        assert "kommunikation_mail_senden" in orch
        assert "kommunikation_email_markieren" in orch
        assert "kommunikation_email_verschieben" in orch
        # Triage: strukturiert-only — NUR lesen, KEIN Schreib-/Sende-/Web-Tool (deny-by-default):
        assert triage == ["kommunikation_nachricht_lesen"]
        # Antwort-Entwurf: lesen + Entwurf ablegen, aber NIE senden:
        assert "kommunikation_email_entwurf_ablegen" in antwort
        assert "kommunikation_mail_senden" not in antwort
        assert not any("senden" in w for w in triage + antwort)


def test_install_idempotent_kein_duplikat(tmp_path):
    with _client(tmp_path) as c:
        r1 = c.post("/api/agenten/vorlagen/email_manager").json()
        r2 = c.post("/api/agenten/vorlagen/email_manager").json()
        assert r1["agent_id"] == r2["agent_id"] and r1["abo_id"] == r2["abo_id"]
        assert len(c.get("/api/agenten").json()) == 3          # Orchestrator + 2 Worker, kein Dup
        assert len(c.get("/api/agenten/abos").json()) == 1     # kein Dup-Abo
