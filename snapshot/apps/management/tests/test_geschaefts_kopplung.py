"""RG-8 (docs/83 §6): Geschäfts-Kopplung management-Seite — Slots + Fristen-Wächter + Weiche.

Der geschaeft-Bereich „zeigt Slots" (das kuratierte Set, Standard-Abos fail-closed AUS); der
E-Mail-Manager trägt zusätzlich die Geschäfts-Weiche-Grants (beleg/frist vorschlagen) mit
geld ⇒ pre_approval (Boden deckelt Money — bucht nie automatisch). Fake-Core.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm


class _FakeCore:
    def __init__(self):
        self.pushes: list[dict] = []

    async def regie_karte_push(self, karte):
        self.pushes.append(karte)
        return {"ok": True, "abos": 0, "agenten": 0}


def _client(tmp_path) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path, agent_core_client=_FakeCore()))


def test_geschaefts_slots_zeigt_set_fail_closed(tmp_path):
    with _client(tmp_path) as c:
        slots = c.get("/api/agenten/geschaefts-slots").json()
        namen = {s["name"] for s in slots}
        assert namen == {"email_manager", "fristen_waechter"}
        assert all(s["aktiv"] is False for s in slots)            # Standard-Abos AUS (David schaltet)
        fw = next(s for s in slots if s["name"] == "fristen_waechter")
        assert (fw["quelle_app"], fw["ereignis_typ"]) == ("admin", "frist_naht")


def test_email_manager_hat_geschaefts_weiche_grants(tmp_path):
    with _client(tmp_path) as c:
        oid = c.post("/api/agenten/vorlagen/email_manager").json()["agent_id"]
        orch = c.get(f"/api/agenten/{oid}").json()
        # RG-8-Weiche: rechnung ⇒ Beleg (money), termin ⇒ Frist (admin):
        assert "finanzen_beleg_vorschlagen" in orch["werkzeuge"]
        assert "admin_frist_vorschlagen" in orch["werkzeuge"]
        # geld ⇒ pre_approval ⇒ beleg_vorschlagen SCHLÄGT VOR (KLASSEN_BODEN deckelt ohnehin):
        assert orch["autonomie"]["geld"] == "pre_approval"
        # Der Send-Pin bleibt unberührt (RG-7):
        assert orch["autonomie"]["aussenwirkung"] == "pre_approval"


def test_fristen_waechter_installiert_fail_closed(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/agenten/vorlagen/fristen_waechter").json()
        assert r["ok"] is True and r["aktiv"] is False
        agenten = {a["name"] for a in c.get("/api/agenten").json()}
        assert "Fristen-Wächter" in agenten
        abos = c.get("/api/agenten/abos").json()
        assert any(a["ereignis_typ"] == "frist_naht" and a["aktiv"] is False for a in abos)
