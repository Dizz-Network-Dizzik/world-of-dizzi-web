"""Tests RG-5 (K-9-Naht, Management-Seite): die Produktionsleiter-Werks-Vorlage.

Ein Klick installiert den Produktionsleiter-Agenten + sein Abo (creator × drop_bereit) —
fail-closed (Abo AUS, Autonomie leer ⇒ T0/beobachten), idempotent (genau EINE Naht), und
die Regie-Karte reist an den Core. Fake-Core (kein HTTP).
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


def test_vorlagen_liste_enthaelt_produktionsleiter(tmp_path):
    with _client(tmp_path) as c:
        v = c.get("/api/agenten/vorlagen").json()
        pl = next(x for x in v if x["name"] == "produktionsleiter")
        assert pl["quelle_app"] == "creator" and pl["ereignis_typ"] == "drop_bereit"


def test_install_legt_agent_und_abo_fail_closed_an(tmp_path):
    core = _FakeCore()
    with _client(tmp_path, core) as c:
        r = c.post("/api/agenten/vorlagen/produktionsleiter").json()
        assert r["ok"] is True and r["aktiv"] is False       # Abo AUS (David schaltet)
        aid = r["agent_id"]
        a = c.get(f"/api/agenten/{aid}").json()
        assert a["name"] == "Produktionsleiter" and a["sensitivitaet"] == "hoch"
        assert a["autonomie"] == {}                          # leer ⇒ beobachten/T0 (sicher)
        assert "creator_zertifikat_vorschlagen" in a["werkzeuge"]
        abos = c.get("/api/agenten/abos").json()
        assert len(abos) == 1
        assert (abos[0]["quelle_app"], abos[0]["ereignis_typ"]) == ("creator", "drop_bereit")
        assert abos[0]["aktiv"] is False and abos[0]["agent_id"] == aid
        assert core.pushes                                   # Regie-Karte an Core


def test_install_ist_idempotent_genau_eine_naht(tmp_path):
    with _client(tmp_path) as c:
        r1 = c.post("/api/agenten/vorlagen/produktionsleiter").json()
        r2 = c.post("/api/agenten/vorlagen/produktionsleiter").json()
        assert r1["agent_id"] == r2["agent_id"] and r1["abo_id"] == r2["abo_id"]
        assert len(c.get("/api/agenten").json()) == 1        # kein Duplikat-Agent
        assert len(c.get("/api/agenten/abos").json()) == 1   # kein Duplikat-Abo


def test_install_unbekannte_vorlage_404(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/agenten/vorlagen/gibtsnicht").status_code == 404
