"""Tests Agenten-Regie Z4.1-A (docs/63 §1/§8): Agent-Definitions-CRUD + Baum-Wächter.

Deckt die Akzeptanz: „Agent mit Sub-Agenten per API anlegbar; Tiefe>3/Zyklus ⇒ 422;
management-Suite grün." Rein additiv — keine Ausführung (die ist Z4.2, Core).
"""

from __future__ import annotations

import json
from urllib.error import URLError

from fastapi.testclient import TestClient

from managementapp import agenten_domain as ad
from managementapp import main as mm


def _client(tmp_path) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path))


def _pending(aid, name, level, *, source="agent", agent_id="a1", warum="weil",
             lauf_id="", params=None):
    """Eine rohe pending-Zeile wie appkit.actions.listing() sie liefert."""
    return {"id": aid, "name": name, "params": params or {}, "source": source,
            "status": "pending", "level": level, "agent_id": agent_id,
            "warum": warum, "lauf_id": lauf_id, "created_at": "2026-07-05T10:00:00"}


def test_agent_crud_roundtrip(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/agenten").json() == []
        r = c.post("/api/agenten", json={
            "name": "E-Mail-Manager", "rolle": "Orchestrator",
            "system_prompt": "Du koordinierst Triage und Antwort-Entwurf.",
            "task_klasse": "chat", "werkzeuge": ["mail_lesen", "mail_lesen", "x"],
            "autonomie": {"aussenwirkung": "monitored"}, "budget": {"max_runden": 3},
            "status": "aktiv"})
        assert r.status_code == 200 and r.json()["ok"] is True
        aid = r.json()["id"]

        liste = c.get("/api/agenten").json()
        assert len(liste) == 1 and liste[0]["id"] == aid

        got = c.get(f"/api/agenten/{aid}").json()
        assert got["name"] == "E-Mail-Manager" and got["rolle"] == "Orchestrator"
        assert got["werkzeuge"] == ["mail_lesen", "x"]          # dedupe, Reihenfolge
        assert got["budget"]["max_runden"] == 3                 # override
        assert got["budget"]["max_tool_aufrufe"] == 32          # Default bleibt
        # Karte-Projektion (P2): Rolle · wirksame Tools · Grenzen
        assert got["karte"]["rolle"] == "Orchestrator"
        assert got["karte"]["tools"] == ["mail_lesen", "x"]
        assert got["karte"]["grenzen"]["autonomie"] == {"aussenwirkung": "monitored"}

        # PATCH
        assert c.patch(f"/api/agenten/{aid}", json={"status": "pausiert"}).json()["ok"]
        assert c.get(f"/api/agenten/{aid}").json()["status"] == "pausiert"
        assert c.get("/api/agenten?status=aktiv").json() == []
        assert len(c.get("/api/agenten?status=pausiert").json()) == 1

        # DELETE (soft)
        assert c.delete(f"/api/agenten/{aid}").json()["ok"]
        assert c.get("/api/agenten").json() == []
        assert c.get(f"/api/agenten/{aid}").status_code == 404

        actions = [e["action"] for e in c.get("/api/audit").json()]
        assert {"agent_angelegt", "agent_geaendert", "agent_geloescht"} <= set(actions)


def test_agent_name_pflicht(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/agenten", json={"name": "  "}).status_code == 400


def test_baum_drei_ebenen_ok_vier_verweigert(tmp_path):
    """Akzeptanz: Sub-Agenten-Baum bis 3 Ebenen anlegbar; die 4. ⇒ 422."""
    with _client(tmp_path) as c:
        x = c.post("/api/agenten", json={"name": "X"}).json()["id"]
        s1 = c.post("/api/agenten", json={"name": "S1", "sub_agenten": [x]}).json()["id"]
        w1 = c.post("/api/agenten", json={"name": "W1", "sub_agenten": [s1]}).json()["id"]
        # o→w1→s1→x = 4 Ebenen ⇒ 422 (Anti-Swarm, VO-3 flach)
        r = c.post("/api/agenten", json={"name": "O", "sub_agenten": [w1]})
        assert r.status_code == 422 and "zu tief" in r.json()["detail"]
        # nur bis 3 Ebenen: o2→w1→s1 ist ok (w1 wird wiederverwendet)
        r2 = c.post("/api/agenten", json={"name": "O2", "sub_agenten": [w1]})
        # w1→s1→x ist selbst schon 3 Ebenen ⇒ o2 darüber wäre 4 ⇒ ebenfalls 422
        assert r2.status_code == 422


def test_baum_drei_ebenen_flach_ok(tmp_path):
    with _client(tmp_path) as c:
        w1 = c.post("/api/agenten", json={"name": "Triage"}).json()["id"]
        w2 = c.post("/api/agenten", json={"name": "Antwort"}).json()["id"]
        s1 = c.post("/api/agenten", json={"name": "Sub", "sub_agenten": []}).json()["id"]
        c.patch(f"/api/agenten/{w1}", json={"sub_agenten": [s1]})     # w1→s1 (2 Ebenen)
        r = c.post("/api/agenten", json={"name": "Manager", "sub_agenten": [w1, w2]})
        assert r.status_code == 200                                   # Manager→w1→s1 = 3 Ebenen
        got = c.get(f"/api/agenten/{r.json()['id']}").json()
        assert got["sub_agenten"] == [w1, w2]


def test_baum_zyklus_und_selbstdelegation_verweigert(tmp_path):
    with _client(tmp_path) as c:
        a = c.post("/api/agenten", json={"name": "A"}).json()["id"]
        # Selbst-Delegation ⇒ Zyklus ⇒ 422
        r = c.patch(f"/api/agenten/{a}", json={"sub_agenten": [a]})
        assert r.status_code == 422 and "Zyklus" in r.json()["detail"]
        # gegenseitig: b→a, dann a→b ⇒ Zyklus
        b = c.post("/api/agenten", json={"name": "B", "sub_agenten": [a]}).json()["id"]
        r2 = c.patch(f"/api/agenten/{a}", json={"sub_agenten": [b]})
        assert r2.status_code == 422 and "Zyklus" in r2.json()["detail"]


def test_autonomie_deny_by_default_und_boden_gespeichert(tmp_path):
    """Unbekannte (Klasse/Stufe) fliegen; geld/gesundheit DÜRFEN gespeichert werden
    (die fail-closed-Bodung macht ``wirksame_stufe`` in Z4.2, nicht die Speicherung)."""
    with _client(tmp_path) as c:
        aid = c.post("/api/agenten", json={"name": "A", "autonomie": {
            "aussenwirkung": "monitored", "geld": "autonom_audit",
            "quatsch": "monitored", "entwurf": "turbo"}}).json()["id"]
        auto = c.get(f"/api/agenten/{aid}").json()["autonomie"]
        assert auto == {"aussenwirkung": "monitored", "geld": "autonom_audit"}


def test_katalog(tmp_path):
    with _client(tmp_path) as c:
        k = c.get("/api/agenten/katalog").json()
        assert k["aktions_klassen"] == ["entwurf", "aussenwirkung", "geld", "gesundheit"]
        assert k["autonomie_stufen"] == ["beobachten", "pre_approval", "monitored",
                                         "autonom_audit"]
        assert k["klassen_boden"] == {"geld": "pre_approval", "gesundheit": "pre_approval"}
        assert k["treppe_stufen"] == ["T0", "T1", "T2", "T3"]     # RG-4 begehbare Treppe
        assert k["treppe_presets"]["T0"]["aussenwirkung"] == "beobachten"
        assert "chat" in k["task_klassen"] and "schnell" in k["task_klassen"]
        assert k["max_ebenen"] == 3
        assert k["budget_default"]["max_runden"] == 4


# ===================== Z4.1-C: Bereichs-Autonomie-Matrix (P4) =====================
def test_autonomie_matrix_default_beobachten_und_setzen(tmp_path):
    with _client(tmp_path) as c:
        m = {row["klasse"]: row for row in c.get("/api/agenten/autonomie").json()["matrix"]}
        # 4 Klassen; V-1: alle Default beobachten; geld/gesundheit sichtbar GEDECKELT
        assert set(m) == {"entwurf", "aussenwirkung", "geld", "gesundheit"}
        assert all(r["stufe"] == "beobachten" for r in m.values())
        assert m["geld"]["gesperrt"] is True and m["gesundheit"]["gesperrt"] is True
        assert m["geld"]["kappe"] == "pre_approval"
        assert m["entwurf"]["gesperrt"] is False and m["aussenwirkung"]["gesperrt"] is False

        # freie Klasse anheben ⇒ gespeichert
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "aussenwirkung", "stufe": "monitored"}).json()["ok"]
        m2 = {r["klasse"]: r for r in c.get("/api/agenten/autonomie").json()["matrix"]}
        assert m2["aussenwirkung"]["stufe"] == "monitored"

        # geld über pre_approval ⇒ 422 (Obergrenze, nicht lockerbar) …
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "geld", "stufe": "monitored"}).status_code == 422
        # … aber geld auf beobachten (STRENGER) ⇒ erlaubt (V-1)
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "geld", "stufe": "beobachten"}).json()["ok"]
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "geld", "stufe": "pre_approval"}).json()["ok"]
        # unbekannte Klasse/Stufe ⇒ 400
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "quatsch", "stufe": "monitored"}).status_code == 400
        assert c.put("/api/agenten/autonomie",
                     json={"klasse": "entwurf", "stufe": "turbo"}).status_code == 400
        assert "agent_autonomie_gesetzt" in [e["action"] for e in c.get("/api/audit").json()]


def test_autonomie_matrix_je_bereich_isoliert(tmp_path):
    with _client(tmp_path) as c:
        bid = c.post("/api/bereiche", json={"name": "Kunde A"}).json()["id"]
        c.put("/api/agenten/autonomie",
              json={"bereich_id": bid, "klasse": "aussenwirkung", "stufe": "monitored"})
        # nur der Bereich trägt die Stufe; Allgemein bleibt V-1-Default beobachten
        mb = {r["klasse"]: r for r in
              c.get(f"/api/agenten/autonomie?bereich_id={bid}").json()["matrix"]}
        assert mb["aussenwirkung"]["stufe"] == "monitored"
        ma = {r["klasse"]: r for r in c.get("/api/agenten/autonomie").json()["matrix"]}
        assert ma["aussenwirkung"]["stufe"] == "beobachten"


# ===================== RG-4: Autonomie-Treppe (docs/83 §3) =======================
def test_treppe_erkennen_default_t0_und_anwenden(tmp_path):
    with _client(tmp_path) as c:
        # frischer Bereich (alles beobachten) ⇒ steht auf T0
        t = c.get("/api/agenten/treppe").json()
        assert t["treppe"] == "T0" and t["stufen"] == ["T0", "T1", "T2", "T3"]
        # T2 anwenden ⇒ alle vier Klassen pre_approval; erkannt als T2
        assert c.put("/api/agenten/treppe", json={"treppe": "T2"}).json()["ok"]
        t2 = c.get("/api/agenten/treppe").json()
        assert t2["treppe"] == "T2"
        m = {r["klasse"]: r["stufe"] for r in t2["matrix"]}
        assert m == {"entwurf": "pre_approval", "aussenwirkung": "pre_approval",
                     "geld": "pre_approval", "gesundheit": "pre_approval"}
        # T1 anwenden ⇒ entwurf pre_approval, Rest beobachten
        c.put("/api/agenten/treppe", json={"treppe": "T1"})
        m1 = {r["klasse"]: r["stufe"] for r in c.get("/api/agenten/treppe").json()["matrix"]}
        assert m1["entwurf"] == "pre_approval" and m1["aussenwirkung"] == "beobachten"
        # unbekannte Treppe ⇒ 400
        assert c.put("/api/agenten/treppe", json={"treppe": "T9"}).status_code == 400


def test_treppe_t3_deckelt_geld_gesundheit(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/agenten/treppe", json={"treppe": "T3"})
        m = {r["klasse"]: r["stufe"] for r in c.get("/api/agenten/treppe").json()["matrix"]}
        # T3: entwurf autonom_audit, aussenwirkung monitored — geld/gesundheit BODEN
        assert m["entwurf"] == "autonom_audit" and m["aussenwirkung"] == "monitored"
        assert m["geld"] == "pre_approval" and m["gesundheit"] == "pre_approval"


# ===================== RG-4: Auto-Rückstufungs-Trigger (pure) ====================
def test_rueckstufung_noetig_trigger():
    # Invarianten-Verstoß ⇒ sofort (höchste Priorität).
    ok, grund = ad.rueckstufung_noetig(invarianten_verstoss=True)
    assert ok and "Invarianten-Verstoß" in grund
    # Ablehnungsquote ≥3 der letzten 10.
    ok, grund = ad.rueckstufung_noetig(ablehnungen=3, entscheidungen=10)
    assert ok and "Ablehnungsquote" in grund
    assert not ad.rueckstufung_noetig(ablehnungen=2, entscheidungen=10)[0]
    # Lauf-Fehlerquote >50% ab 2 Läufen …
    assert ad.rueckstufung_noetig(lauf_fehler=2, laeufe=3)[0]        # 2/3 > 50%
    assert not ad.rueckstufung_noetig(lauf_fehler=1, laeufe=3)[0]    # 1/3 < 50%
    # … ein einzelner Fehlschlag stuft NICHT zurück (min. 2 Läufe).
    assert not ad.rueckstufung_noetig(lauf_fehler=1, laeufe=1)[0]
    # nichts Auffälliges ⇒ kein Trigger.
    assert not ad.rueckstufung_noetig(ablehnungen=1, entscheidungen=8,
                                      lauf_fehler=0, laeufe=5)[0]


def test_frontend_agenten_surface(tmp_path):
    """+U: die Agenten-Regie-Oberfläche ist verdrahtet (Library + Matrix + AI-Act-Hinweis)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'data-pkey="agenten"' in html and "Agenten-Regie" in html
        assert "ladeAgenten" in html and "renderAgentenPanel" in html
        assert "renderAutonomieMatrix" in html and "autonomieSetzen" in html
        assert "/api/agenten" in html and "/api/agenten/autonomie" in html
        assert "AI-Act" in html                      # KI-Offenlegung (§5/VO-6)
        assert "pre_approval" in html                # gedeckelte geld/gesundheit-Zeilen
        # RG-4 +U: begehbare Treppe + Not-Aus verdrahtet
        assert "renderTreppe" in html and "treppeSetzen" in html
        assert "/api/agenten/treppe" in html
        assert "renderNotAus" in html and "/api/agenten/regie/schalter" in html
        assert "Not-Aus" in html and "beobachten" in html


# ===================== Z4.1-D: Netz-Inbox-Aggregation (§2 P3) =====================
def _fetch(pending_by_app, offline=("news",)):
    """Injizierter Poll: pending je App-ID; ``offline``-Apps werfen (⇒ apps_offline)."""
    def fetch(app):
        if app.id in offline:
            raise URLError("connection refused")
        return list(pending_by_app.get(app.id, []))
    return fetch


def test_agent_inbox_aggregiert_zwei_apps_und_offline(tmp_path):
    """Akzeptanz: pending-Aktion aus ZWEI Apps erscheint; Offline-Apps ehrlich benannt."""
    fetch = _fetch({
        "kommunikation": [_pending("k1", "email_senden", "verifiziert",
                                   agent_id="triage-1", warum="Kunde wartet", lauf_id="l1",
                                   params={"an": "k@x.org"})],
        "creator": [_pending("c1", "bild_generieren", "lokal", agent_id="art-1",
                             warum="Auftrag offen")],
    })
    with TestClient(mm.build_app(data_dir=tmp_path, agent_inbox_fetch=fetch)) as c:
        d = c.get("/api/agent-inbox").json()
        was = {e["was"] for e in d["eintraege"]}
        assert {"email_senden", "bild_generieren"} <= was
        k = next(e for e in d["eintraege"] if e["was"] == "email_senden")
        assert k["app_id"] == "kommunikation" and k["warum"] == "Kunde wartet"
        assert k["agent_id"] == "triage-1" and k["lauf_id"] == "l1"
        assert k["klasse"] == "aussenwirkung"                 # aus Level abgeleitet
        assert k["argumente"] == {"an": "k@x.org"}
        assert k["app_url"].endswith(":8218")                 # Browser-Ziel für Approve (§2)
        assert "news" in d["apps_offline"]                    # ehrlich, nie still leer
        assert d["eintraege"][0]["agent_id"]                  # agent-originierte zuerst


def test_agent_inbox_eigene_pending_ohne_self_http(tmp_path):
    """Managements EIGENE agent-Aktion erscheint (direkt aus der DB, app_url='')."""
    from appkit.actions import propose
    with TestClient(mm.build_app(data_dir=tmp_path,
                                 agent_inbox_fetch=lambda app: [])) as c:
        db = c.app.state.db
        reg = c.app.state.domain.registry
        propose(db, reg, "dizzi", "post_veroeffentlichen", {"post_id": "p1"},
                source="agent", warum="geplanter Post fällig", agent_id="social-1")
        d = c.get("/api/agent-inbox").json()
        eigen = [e for e in d["eintraege"] if e["app_id"] == "management"]
        assert len(eigen) == 1 and eigen[0]["warum"] == "geplanter Post fällig"
        assert eigen[0]["app_url"] == ""                      # eigene App ⇒ same-origin
        assert d["apps_offline"] == []


def test_frontend_inbox_surface(tmp_path):
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'data-pkey="netzinbox"' in html and "Netz-Inbox" in html
        assert "ladeInbox" in html and "inboxEntscheiden" in html
        assert "/api/agent-inbox" in html
        assert "inboxApprove" in html and "inboxReject" in html


# ===================== Z4.2-D: Definition-Brücke + Running-Tab-Relay =====================
class _FakeCore:
    """Fake der Core-Ausführungs-API (kein HTTP/Ollama) — protokolliert die Aufrufe."""

    def __init__(self, laeufe_data=None, offline=False):
        self._laeufe = laeufe_data or []
        self._offline = offline
        self.stops: list[str] = []
        self.streams: list[tuple[dict, str]] = []

    async def laeufe(self, status=""):
        if self._offline:
            raise RuntimeError("core offline")
        return [r for r in self._laeufe if not status or r.get("status") == status]

    async def stop(self, lauf_id):
        if self._offline:
            raise RuntimeError("core offline")
        self.stops.append(lauf_id)
        return {"ok": True, "gestoppt": True, "lauf_id": lauf_id}

    async def lauf_stream(self, snapshot, auftrag):
        self.streams.append((snapshot, auftrag))
        for obj in ({"lauf_id": "L1", "start": True, "agent_id": snapshot["wurzel"]},
                    {"t": "hallo"}, {"done": True, "status": "fertig"}):
            yield f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


def _client_core(tmp_path, fake) -> TestClient:
    return TestClient(mm.build_app(data_dir=tmp_path, agent_core_client=fake))


def test_schnappschuss_definition_bruecke(tmp_path):
    """Definition-Brücke: der aufgelöste Wald-Snapshot (Wurzel + Worker) ist Push-fertig."""
    with _client(tmp_path) as c:
        w = c.post("/api/agenten", json={"name": "Triage"}).json()["id"]
        o = c.post("/api/agenten", json={
            "name": "E-Mail-Manager", "system_prompt": "koordiniere", "sub_agenten": [w]}).json()["id"]
        snap = c.get(f"/api/agenten/{o}/snapshot").json()
        assert snap["wurzel"] == o and set(snap["agenten"]) == {o, w}
        assert snap["agenten"][o]["name"] == "E-Mail-Manager"
        assert snap["agenten"][o]["sub_agenten"] == [w]     # asdict: tuple → list (JSON-fest)
        assert c.get("/api/agenten/gibtsnicht/snapshot").status_code == 404


def test_laeufe_ledger_relay_und_filter(tmp_path):
    fake = _FakeCore(laeufe_data=[{"id": "L1", "agent_id": "o", "status": "laeuft",
                                   "runden": 0, "tool_aufrufe": 2, "delegationen": 1,
                                   "nutzung": {}, "fehler": "", "started_at": "t",
                                   "ended_at": None}])
    with _client_core(tmp_path, fake) as c:
        d = c.get("/api/agenten/laeufe").json()
        assert d["core_offline"] is False and len(d["laeufe"]) == 1
        assert d["laeufe"][0]["tool_aufrufe"] == 2 and d["laeufe"][0]["delegationen"] == 1
        assert c.get("/api/agenten/laeufe?status=laeuft").json()["laeufe"][0]["id"] == "L1"


def test_laeufe_core_offline_ehrlich(tmp_path):
    """Core offline ⇒ ehrlich leer + Flagge (nie still, Health-Watch-Regel)."""
    with _client_core(tmp_path, _FakeCore(offline=True)) as c:
        d = c.get("/api/agenten/laeufe").json()
        assert d["core_offline"] is True and d["laeufe"] == []


def test_stop_relay_und_offline_502(tmp_path):
    fake = _FakeCore()
    with _client_core(tmp_path, fake) as c:
        assert c.post("/api/agenten/lauf/L1/stop").json()["gestoppt"] is True
        assert fake.stops == ["L1"]
    with _client_core(tmp_path, _FakeCore(offline=True)) as c:
        assert c.post("/api/agenten/lauf/L1/stop").status_code == 502


def test_lauf_start_sse_relay_und_push(tmp_path):
    """POST …/{aid}/lauf: Snapshot aus dem Wald (Definition-Brücke) an Core gepusht +
    dessen SSE durchgestreamt (Live-Log). Core bekommt Wurzel-ID + Auftrag."""
    fake = _FakeCore()
    with _client_core(tmp_path, fake) as c:
        aid = c.post("/api/agenten", json={"name": "Solo", "status": "aktiv"}).json()["id"]
        r = c.post(f"/api/agenten/{aid}/lauf", json={"auftrag": "tu was"})
        assert r.status_code == 200
        assert "hallo" in r.text and '"done": true' in r.text
        assert fake.streams and fake.streams[0][0]["wurzel"] == aid
        assert fake.streams[0][1] == "tu was"
    with _client_core(tmp_path, _FakeCore()) as c:
        assert c.post("/api/agenten/gibtsnicht/lauf", json={"auftrag": "x"}).status_code == 404


def test_frontend_running_surface(tmp_path):
    """+U: der Running-Tab ist verdrahtet (SSE-Live-Log, Stop, Guardrail-Zähler, AI-Act)."""
    with _client(tmp_path) as c:
        html = c.get("/").text
        assert 'data-pkey="running"' in html and "Running" in html
        assert "ladeLaeufe" in html and "laufStarten" in html and "laufStoppen" in html
        assert "/api/agenten/laeufe" in html and "/lauf" in html
        assert "AI-Act" in html                              # KI-Offenlegung (§5/VO-6)
        assert "Runden" in html and "Tool-Aufrufe" in html   # Guardrail-Zähler (P7)
