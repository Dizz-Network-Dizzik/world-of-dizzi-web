"""Tests RG-3b (docs/83 §2, Management-Seite): agent_abos-CRUD + Regie-Karte-Push.

Deckt: Abo-CRUD-Round-Trip + Audit · genau EIN Zuständiger je Strom (UNIQUE ⇒ 409) ·
Agent muss existieren (404) · Soft-Delete + Wiederbelebung desselben Stroms ·
Regie-Karte-Assemblierung (Abos + aufgelöster Wald + agent_sens = max(App,Agent)) ·
Push an Core (best-effort auto-push nach jedem Edit + expliziter Push; Core offline
ehrlich). Fake-Core (kein HTTP/Ollama) — protokolliert die gepushten Karten.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from managementapp import main as mm


class _FakeCore:
    """Fake der Core-Regie-Push-API — zeichnet die gepushten Regie-Karten + Schalter auf."""

    def __init__(self, offline=False):
        self._offline = offline
        self.pushes: list[dict] = []
        self.aktiv = False

    async def regie_karte_push(self, karte):
        if self._offline:
            raise RuntimeError("core offline")
        self.pushes.append(karte)
        return {"ok": True, "abos": len(karte.get("abos", [])),
                "agenten": len(karte.get("agenten", {}))}

    async def regie_status(self):
        if self._offline:
            raise RuntimeError("core offline")
        return {"aktiv": self.aktiv, "tick_s": 10, "abos": 0, "agenten": 0,
                "pushed_at": "", "zuendungen": {}}

    async def regie_schalter(self, aktiv):
        if self._offline:
            raise RuntimeError("core offline")
        self.aktiv = bool(aktiv)
        return {"ok": True, "aktiv": self.aktiv}


def _spy_push():
    """Spy für die Glocke (appkit.events.push_event-Signatur)."""
    calls: list[dict] = []

    def push(app_id, severity, title, detail=None):
        calls.append({"app": app_id, "severity": severity, "title": title,
                      "detail": detail or {}})
        return True

    return calls, push


def _client(tmp_path, fake=None, event_push=None) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path, agent_core_client=fake or _FakeCore(),
                                   agent_event_push=event_push))


def _agent(c, name, **kw) -> str:
    return c.post("/api/agenten", json={"name": name, **kw}).json()["id"]


# --- Abo-CRUD --------------------------------------------------------------------

def test_abo_crud_roundtrip(tmp_path):
    fake = _FakeCore()
    with _client(tmp_path, fake) as c:
        assert c.get("/api/agenten/abos").json() == []
        aid = _agent(c, "E-Mail-Manager", status="aktiv")
        r = c.post("/api/agenten/abos", json={
            "agent_id": aid, "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen", "auftrag": "Triagiere neue Mails.",
            "max_pro_tag": 5, "aktiv": True})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["gepusht"] is True                 # auto-push an (Fake-)Core
        abo_id = r.json()["id"]

        liste = c.get("/api/agenten/abos").json()
        assert len(liste) == 1
        a = liste[0]
        assert a["agent_id"] == aid and a["quelle_app"] == "kommunikation"
        assert a["ereignis_typ"] == "mail_eingegangen" and a["max_pro_tag"] == 5
        assert a["aktiv"] is True and a["auftrag"] == "Triagiere neue Mails."

        # PATCH: deaktivieren + Deckel senken
        assert c.patch(f"/api/agenten/abos/{abo_id}",
                       json={"aktiv": False, "max_pro_tag": 3}).json()["ok"]
        a2 = c.get("/api/agenten/abos").json()[0]
        assert a2["aktiv"] is False and a2["max_pro_tag"] == 3

        # DELETE (soft)
        assert c.delete(f"/api/agenten/abos/{abo_id}").json()["ok"]
        assert c.get("/api/agenten/abos").json() == []

        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert {"agent_abo_angelegt", "agent_abo_geaendert",
                "agent_abo_geloescht"} <= set(actions)
        # jeder Edit hat gepusht (create + patch + delete):
        assert len(fake.pushes) >= 3


def test_abo_pflichtfelder_und_agent_existenz(tmp_path):
    with _client(tmp_path) as c:
        # fehlende Pflichtfelder ⇒ 400
        assert c.post("/api/agenten/abos", json={
            "agent_id": "", "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen"}).status_code == 400
        # unbekannter Agent ⇒ 404
        assert c.post("/api/agenten/abos", json={
            "agent_id": "ghost", "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen"}).status_code == 404


def test_abo_genau_ein_zustaendiger_409(tmp_path):
    with _client(tmp_path) as c:
        a1 = _agent(c, "Manager A")
        a2 = _agent(c, "Manager B")
        body = {"quelle_app": "kommunikation", "ereignis_typ": "mail_eingegangen"}
        assert c.post("/api/agenten/abos", json={"agent_id": a1, **body}).status_code == 200
        # zweiter Zuständiger für denselben Strom ⇒ 409 (UNIQUE, genau EINER)
        assert c.post("/api/agenten/abos", json={"agent_id": a2, **body}).status_code == 409
        # anderer Bereich = anderer Strom ⇒ ok
        assert c.post("/api/agenten/abos",
                      json={"agent_id": a2, "bereich_id": "b1", **body}).status_code == 200


def test_abo_wiederbelebung_nach_soft_delete(tmp_path):
    with _client(tmp_path) as c:
        aid = _agent(c, "M")
        body = {"agent_id": aid, "quelle_app": "kommunikation",
                "ereignis_typ": "mail_eingegangen"}
        first = c.post("/api/agenten/abos", json=body).json()["id"]
        assert c.delete(f"/api/agenten/abos/{first}").json()["ok"]
        # denselben Strom neu anlegen ⇒ dieselbe Zeile wiederbelebt (kein UNIQUE-Bruch)
        r = c.post("/api/agenten/abos", json={**body, "aktiv": True})
        assert r.status_code == 200 and r.json()["id"] == first
        abos = c.get("/api/agenten/abos").json()
        assert len(abos) == 1 and abos[0]["aktiv"] is True


# --- Regie-Karte: Assemblierung + Push ------------------------------------------

def test_regie_karte_assemblierung(tmp_path):
    with _client(tmp_path) as c:
        worker = _agent(c, "Triage", sensitivitaet="normal")
        orch = _agent(c, "E-Mail-Manager", sensitivitaet="höchst", sub_agenten=[worker])
        c.post("/api/agenten/abos", json={
            "agent_id": orch, "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen", "aktiv": True})
        karte = c.get("/api/agenten/regie-karte").json()
        assert len(karte["abos"]) == 1 and karte["abos"][0]["agent_id"] == orch
        # Wald = Orchestrator + erreichbarer Worker
        assert set(karte["agenten"]) == {orch, worker}
        # agent_sens = wirksame Sensitivität max(App=hoch, Agent):
        assert karte["agent_sens"][orch] == "höchst"       # Agent strenger
        assert karte["agent_sens"][worker] == "hoch"       # normal-Agent ⇒ App-Boden hoch
        assert karte["pushed_at"]


def test_regie_karte_push_explizit(tmp_path):
    fake = _FakeCore()
    with _client(tmp_path, fake) as c:
        aid = _agent(c, "M")
        c.post("/api/agenten/abos", json={
            "agent_id": aid, "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen", "aktiv": True})
        fake.pushes.clear()
        r = c.post("/api/agenten/regie-karte/push").json()
        assert r["ok"] is True and r["core_offline"] is False and r["abos"] == 1
        assert len(fake.pushes) == 1 and fake.pushes[0]["abos"][0]["agent_id"] == aid


def test_regie_karte_push_core_offline_ehrlich(tmp_path):
    with _client(tmp_path, _FakeCore(offline=True)) as c:
        aid = _agent(c, "M")
        # auto-push scheitert best-effort ⇒ Edit gilt trotzdem, gepusht=False
        r = c.post("/api/agenten/abos", json={
            "agent_id": aid, "quelle_app": "kommunikation",
            "ereignis_typ": "mail_eingegangen"})
        assert r.status_code == 200 and r.json()["gepusht"] is False
        assert len(c.get("/api/agenten/abos").json()) == 1     # Edit trotzdem persistiert
        # expliziter Push meldet core_offline ehrlich
        assert c.post("/api/agenten/regie-karte/push").json()["core_offline"] is True


def test_wirksame_sens_max_regel(tmp_path):
    from managementapp.agenten_domain import AgentenDomaene as AD
    assert AD._wirksame_sens("normal") == "hoch"           # App-Boden hoch
    assert AD._wirksame_sens("hoch") == "hoch"
    assert AD._wirksame_sens("höchst") == "höchst"         # Agent strenger gewinnt
    assert AD._wirksame_sens("quatsch") == "höchst"        # unbekannt ⇒ streng (fail-closed)


# --- RG-4: Not-Aus + Auto-Rückstufung (Endpoints) --------------------------------

def test_not_aus_schalter_proxy(tmp_path):
    """Not-Aus (docs/83 §3): der Management-Endpoint reicht den Master-Schalter an den
    Core weiter; der Status spiegelt ihn. Core offline ⇒ 502 (Schalter nicht gesetzt)."""
    fake = _FakeCore()
    with _client(tmp_path, fake) as c:
        assert c.get("/api/agenten/regie/status").json()["aktiv"] is False
        assert c.post("/api/agenten/regie/schalter", json={"aktiv": True}).json()["aktiv"] is True
        assert fake.aktiv is True
        assert c.get("/api/agenten/regie/status").json()["aktiv"] is True
        assert c.post("/api/agenten/regie/schalter", json={"aktiv": False}).json()["aktiv"] is False
    with _client(tmp_path, _FakeCore(offline=True)) as c:
        assert c.get("/api/agenten/regie/status").json()["core_offline"] is True
        assert c.post("/api/agenten/regie/schalter", json={"aktiv": True}).status_code == 502


def test_rueckstufung_endpoint_setzt_t0_und_glocke(tmp_path):
    """Trigger (Ablehnungsquote) ⇒ Agent geht auf T0 (alle Klassen beobachten), Audit +
    Glocke (warn), Regie-Karte-Push. Metriken kommen als Body (messbar/prüfbar)."""
    fake = _FakeCore()
    calls, push = _spy_push()
    with _client(tmp_path, fake, event_push=push) as c:
        aid = _agent(c, "E-Mail-Manager", autonomie={"aussenwirkung": "monitored"},
                     status="aktiv")
        r = c.post(f"/api/agenten/{aid}/rueckstufen",
                   json={"ablehnungen": 3, "entscheidungen": 10})
        assert r.status_code == 200 and r.json()["rueckgestuft"] is True
        assert r.json()["treppe"] == "T0" and "Ablehnungsquote" in r.json()["grund"]
        assert r.json()["gepusht"] is True                 # Regie-Karte an (Fake-)Core
        # Agent steht jetzt auf T0 (alle Klassen beobachten)
        auto = c.get(f"/api/agenten/{aid}").json()["autonomie"]
        assert auto == {"entwurf": "beobachten", "aussenwirkung": "beobachten",
                        "geld": "beobachten", "gesundheit": "beobachten"}
        # Glocke (warn) mit Klartext-Grund + Audit-Ereignis
        assert len(calls) == 1 and calls[0]["severity"] == "warn"
        assert "agent_rueckgestuft" in [e["action"] for e in c.get("/api/audit").json()]


def test_rueckstufung_endpoint_kein_trigger_laesst_agent(tmp_path):
    fake = _FakeCore()
    calls, push = _spy_push()
    with _client(tmp_path, fake, event_push=push) as c:
        aid = _agent(c, "M", autonomie={"aussenwirkung": "monitored"}, status="aktiv")
        r = c.post(f"/api/agenten/{aid}/rueckstufen",
                   json={"ablehnungen": 1, "entscheidungen": 10})
        assert r.json()["rueckgestuft"] is False
        assert c.get(f"/api/agenten/{aid}").json()["autonomie"] == {"aussenwirkung": "monitored"}
        assert calls == []                                 # keine Glocke, kein Downgrade
