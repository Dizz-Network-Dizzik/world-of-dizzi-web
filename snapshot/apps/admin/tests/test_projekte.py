"""Tests Dizz Admin — Projekte-Modul (aus Plans portiert, docs/28 §13): Domäne
Projekte/Aufgaben/Termine (CRUD/Fortschritt/Abhängigkeiten) + iCal-Import (Dedupe) +
Quellen-Stecker + K4-HITL + Frist-/Termin-Wächter + RRULE-Wiederkehr + V6-Archiv/
V5-Kalender-Querverbindungen. (Source-Einheiten = test_sources; Vertrag/MCP = test_admin;
KI-Vereinheitlichung = späterer Schritt.)

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from adminapp import main as lm
from adminapp.projekte import heute_iso

def _client(tmp_path, *, http_post=None, archiv_post=None, memory_get=None,
            kalender_post=None) -> TestClient:
    kw = {}
    if http_post is not None:
        kw["http_post"] = http_post
    if archiv_post is not None:
        kw["archiv_post"] = archiv_post
    if memory_get is not None:
        kw["memory_get"] = memory_get
    if kalender_post is not None:
        kw["kalender_post"] = kalender_post
    return TestClient(lm.build_app(data_dir=tmp_path, **kw))

def _memory_get_fake(treffer, store=None):
    """Mock für appkit.querverbindung.memory_suche (ruft mit keyword ``params=``)."""
    class _R:
        status_code = 200

        def __init__(self, daten):
            self._daten = daten

        def json(self):
            return self._daten

    def get(url, params):
        if store is not None:
            store.append({"url": url, "params": params})
        return _R({"ok": True, "treffer": treffer, "anzahl": len(treffer)})
    return get

def _archiv_capture(store):
    """Mock für den Querverbindungs-POST (archiviere ruft mit keyword ``json=``)."""
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "uebersprungen", "grund": "manuell"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post

def _kpis(c):
    return {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}

SAMPLE_ICS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:evt-1@dizz\r\n"
    "SUMMARY:Kickoff Dizz Plans\r\n"
    "DTSTART:20260620T130000Z\r\n"
    "DTEND:20260620T140000Z\r\n"
    "LOCATION:Online\r\n"
    "DESCRIPTION:Erstes Treffen\\, Agenda folgt\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:evt-2@dizz\r\n"
    "SUMMARY:Ganztag Workshop\r\n"
    "DTSTART;VALUE=DATE:20260622\r\n"
    "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

# ===================== Vertrag =====================

# ===================== Projekte + Fortschritt =====================
def test_projekt_crud_und_fortschritt(tmp_path):
    with _client(tmp_path) as c:
        assert _kpis(c)["projekte"] == 0
        pid = c.post("/api/projekte", json={"name": "Trading Bot", "app_id": "tradingbot"}).json()["id"]
        liste = c.get("/api/projekte").json()
        assert len(liste) == 1 and liste[0]["app_id"] == "tradingbot"
        assert liste[0]["fortschritt"] == 0 and liste[0]["aufgaben_gesamt"] == 0
        assert _kpis(c)["projekte"] == 1

        # zwei Aufgaben, eine erledigt ⇒ 50 %
        c.post("/api/aufgaben", json={"titel": "A", "projekt_id": pid})
        a2 = c.post("/api/aufgaben", json={"titel": "B", "projekt_id": pid}).json()["id"]
        c.patch(f"/api/aufgaben/{a2}", json={"status": "erledigt"})
        det = c.get(f"/api/projekte/{pid}").json()
        assert det["projekt"]["fortschritt"] == 50
        assert det["projekt"]["aufgaben_fertig"] == 1 and det["projekt"]["aufgaben_gesamt"] == 2
        assert len(det["aufgaben"]) == 2

        # Audit-Beleg + unbekannte App-Kopplung wird abgelehnt
        assert "projekt_angelegt" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/projekte", json={"name": "X", "app_id": "gibtsnicht"}).status_code == 400

# ===================== V6: Plans → Memory (docs/26) =====================
def test_projekt_archivieren_an_memory(tmp_path):
    """Der „In Memory"-Knopf schickt das Projekt explizit über den Core-Relay an
    Dizz Memory: Umschlag korrekt (app/strom/ref/explizit), Projektdaten im Body,
    keine Sektor-/Tag-Flut (Herkunftslabel kommt zentral aus Memory, §9.1)."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        pid = c.post("/api/projekte", json={
            "name": "Trading Bot", "beschreibung": "Echtgeld-Schiene härten",
            "app_id": "tradingbot"}).json()["id"]
        c.post("/api/aufgaben", json={"titel": "Passkey-Gate", "projekt_id": pid})
        a2 = c.post("/api/aufgaben", json={"titel": "Backtest", "projekt_id": pid}).json()["id"]
        c.patch(f"/api/aufgaben/{a2}", json={"status": "erledigt"})

        r = c.post(f"/api/projekte/{pid}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "admin" and u["strom"] == "projekt"
        assert u["explizit"] is True and u["ref"] == "admin:projekt:" + pid
        assert u["tags"] == []                                  # keine Tag-Flut
        assert u["titel"] == "Projekt · Trading Bot"
        assert "Echtgeld-Schiene härten" in u["inhalt"]         # Beschreibung im Body
        assert "50 %" in u["inhalt"] and "Backtest" in u["inhalt"]   # Fortschritt + Aufgabe
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        # Audit-Beleg + unbekanntes Projekt ⇒ 404
        assert "projekt_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/projekte/fehlt/archivieren").status_code == 404

def test_meilenstein_archivieren_an_memory(tmp_path):
    """Meilenstein-Strom (V6, zusätzlich zum projekt-Strom): ein Aufgaben-/
    Meilensteinpunkt geht als eigene Notiz an Memory (strom=meilenstein)."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        pid = c.post("/api/projekte", json={"name": "Release 2.0"}).json()["id"]
        aid = c.post("/api/aufgaben", json={
            "titel": "Beta-Freeze", "projekt_id": pid, "meilenstein": True,
            "faellig": "2026-09-01", "prioritaet": "hoch"}).json()["id"]
        r = c.post(f"/api/aufgaben/{aid}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        u = archiv[-1]["umschlag"]
        assert u["app"] == "admin" and u["strom"] == "meilenstein"
        assert u["explizit"] is True and u["ref"] == "admin:meilenstein:" + aid
        assert u["titel"] == "Meilenstein · Beta-Freeze"
        assert "Beta-Freeze" in u["inhalt"] and "Release 2.0" in u["inhalt"]
        assert "2026-09-01" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        assert "meilenstein_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/aufgaben/fehlt/archivieren").status_code == 404

def test_projekt_notiz_publizieren(tmp_path):
    """Projekt-Notiz-Strom (V6): freie Notiz → Memory (strom=projekt_notiz)."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        pid = c.post("/api/projekte", json={"name": "Trading Bot"}).json()["id"]
        r = c.post(f"/api/projekte/{pid}/notiz",
                   json={"text": "Idee: Regime-Filter vor dem Entry testen."})
        assert r.status_code == 200 and r.json()["ok"] is True
        u = archiv[-1]["umschlag"]
        assert u["strom"] == "projekt_notiz" and u["app"] == "admin"
        assert u["ref"].startswith("admin:projekt_notiz:" + pid + ":")
        assert u["titel"] == "Notiz · Trading Bot"
        assert u["inhalt"] == "Idee: Regime-Filter vor dem Entry testen."
        assert "projekt_notiz_publiziert" in [e["action"] for e in c.get("/api/audit").json()]
        # leerer Text ⇒ 400, unbekanntes Projekt ⇒ 404
        assert c.post(f"/api/projekte/{pid}/notiz", json={"text": "  "}).status_code == 400
        assert c.post("/api/projekte/fehlt/notiz", json={"text": "x"}).status_code == 404

# ============= V5-Rücksync: Plans → Communication (Kalender, docs/26 §4b) =============
def _kalender_capture(store):
    """Mock für den Termin-Sende-POST (sende_termin ruft mit keyword ``json=``)."""
    class _R:
        status_code = 200

        def json(self):
            return {"ok": True, "status": "eingetragen", "id": "k1"}

    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R()
    return post

def test_termin_an_komm_ruecksync(tmp_path):
    """Der „→ Kommunikation"-Knopf schickt einen Termin als read-only Erinnerung an
    Dizz Communication (V5-Rücksync): Umschlag korrekt, Ziel=kommunikation, stabiler
    idempotenter ref. Gegenrichtung zu V5 (Communication → Plans)."""
    kal: list = []
    with _client(tmp_path, kalender_post=_kalender_capture(kal)) as c:
        tid = c.post("/api/termine", json={
            "titel": "Kickoff", "beginn": "2026-07-01T15:00", "ende": "2026-07-01T16:00",
            "ort": "Büro", "notiz": "Projektstart"}).json()["id"]
        r = c.post(f"/api/termine/{tid}/an-komm")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert kal, "kein Termin-Versuch"
        u = kal[-1]["umschlag"]
        assert u["app"] == "admin" and u["titel"] == "Kickoff"
        assert u["beginn"] == "2026-07-01T15:00" and u["ende"] == "2026-07-01T16:00"
        assert u["ort"] == "Büro" and u["beschreibung"] == "Projektstart"
        assert u["ref"] == "admin:termin:" + tid
        # Core-Relay-URL trägt Ziel „kommunikation" + Kalender-Vertragstyp
        assert kal[-1]["url"].endswith("/api/querverbindung/kommunikation/kalender")
        # Audit-Beleg + unbekannter Termin ⇒ 404
        assert "termin_an_komm" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/termine/fehlt/an-komm").status_code == 404

def test_projekt_delete_kaskade(tmp_path):
    with _client(tmp_path) as c:
        pid = c.post("/api/projekte", json={"name": "Weg"}).json()["id"]
        c.post("/api/aufgaben", json={"titel": "A", "projekt_id": pid})
        c.post("/api/termine", json={"titel": "T", "beginn": "2026-07-01T10:00", "projekt_id": pid})
        assert c.delete(f"/api/projekte/{pid}").json()["ok"]
        assert c.get("/api/projekte").json() == []
        # Kaskade: Aufgaben/Termine des Projekts sind ebenfalls weg
        assert c.get(f"/api/aufgaben?projekt_id={pid}").json() == []
        assert c.get(f"/api/termine?projekt_id={pid}").json() == []
        assert c.delete(f"/api/projekte/{pid}").status_code == 404

# ===================== Aufgaben =====================
def test_aufgabe_crud_filter_und_heute(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/aufgaben", json={"titel": "Heute", "faellig": heute_iso(), "prioritaet": "hoch"})
        c.post("/api/aufgaben", json={"titel": "Spaeter", "faellig": "2030-01-01"})
        aid = c.post("/api/aufgaben", json={"titel": "Laufend", "status": "in-bearbeitung"}).json()["id"]
        assert _kpis(c)["aufgaben_offen"] == 3
        assert _kpis(c)["heute_faellig"] == 1
        assert {a["titel"] for a in c.get("/api/aufgaben?status=offen").json()} == {"Heute", "Spaeter"}
        assert [a["titel"] for a in c.get(f"/api/aufgaben?faellig_bis={heute_iso()}").json()] == ["Heute"]
        # erledigen ⇒ raus aus offen
        c.patch(f"/api/aufgaben/{aid}", json={"status": "erledigt"})
        assert _kpis(c)["aufgaben_offen"] == 2
        # unbekanntes Projekt wird abgelehnt
        assert c.post("/api/aufgaben", json={"titel": "X", "projekt_id": "nope"}).status_code == 400

def test_aufgabe_meilenstein_und_abhaengig(tmp_path):
    with _client(tmp_path) as c:
        a1 = c.post("/api/aufgaben", json={"titel": "Basis"}).json()["id"]
        a2 = c.post("/api/aufgaben", json={"titel": "Folge", "meilenstein": True,
                                           "abhaengig_von": [a1]}).json()["id"]
        ms = c.get("/api/aufgaben?meilenstein=1").json()
        assert [a["id"] for a in ms] == [a2]
        assert c.get("/api/aufgaben").json()  # smoke
        folge = next(a for a in c.get("/api/aufgaben").json() if a["id"] == a2)
        assert folge["meilenstein"] is True and folge["abhaengig_von"] == [a1]

# ===================== Termine + iCal =====================
def test_termin_crud(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/termine", json={"titel": "Call", "beginn": "2026-09-01T09:30",
                                           "ort": "Büro"}).json()["id"]
        liste = c.get("/api/termine?von=2026-01-01").json()
        assert len(liste) == 1 and liste[0]["ort"] == "Büro" and liste[0]["quelle"] == "lokal"
        c.patch(f"/api/termine/{tid}", json={"ort": "Remote"})
        assert c.get("/api/termine?von=2026-01-01").json()[0]["ort"] == "Remote"
        assert c.delete(f"/api/termine/{tid}").json()["ok"]
        assert c.get("/api/termine?von=2026-01-01").json() == []
        assert c.post("/api/termine", json={"titel": "kein beginn"}).status_code == 422 \
            or c.post("/api/termine", json={"titel": "x", "beginn": ""}).status_code == 400

def test_ical_import_und_dedupe(tmp_path):
    with _client(tmp_path) as c:
        r1 = c.post("/api/termine/import_ical", json={"ics": SAMPLE_ICS}).json()
        assert r1["importiert"] == 2 and r1["aktualisiert"] == 0 and r1["gefunden"] == 2
        assert len(c.get("/api/termine?von=2026-01-01").json()) == 2
        # erneuter Import desselben Kalenders ⇒ Update statt Duplikat (Idempotenz)
        r2 = c.post("/api/termine/import_ical", json={"ics": SAMPLE_ICS}).json()
        assert r2["importiert"] == 0 and r2["aktualisiert"] == 2
        assert len(c.get("/api/termine?von=2026-01-01").json()) == 2
        # importierte Termine tragen die Quelle 'ical'
        assert all(t["quelle"] == "ical" for t in c.get("/api/termine?von=2026-01-01").json())

def test_ical_leer(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/termine/import_ical", json={"ics": "kein kalender"}).json()
        assert r["ok"] and r["importiert"] == 0 and r["gefunden"] == 0

# ===================== Google-Adapter (dormant, Gesetz 5) =====================

def test_quellen_endpoint(tmp_path):
    with _client(tmp_path) as c:
        d = c.get("/api/quellen").json()["quellen"]
        names = {q["name"] for q in d}
        assert {"ical", "google", "caldav", "github", "gitlab"} <= names
        assert next(q for q in d if q["name"] == "ical")["status"] == "aktiv"
        # ohne Tresor-Tokens ist nichts verbunden
        assert all(q["verbunden"] is False for q in d if q["token_name"])

# ===================== K4: Aktions-Tools mit HITL (propose→approve→execute) =====
def test_k4_hitl_aufgabe_anlegen(tmp_path):
    with _client(tmp_path) as c:
        kat = {a["name"] for a in c.get("/api/actions").json()["katalog"]}
        assert {"aufgabe_anlegen", "termin_anlegen", "projekt_anlegen"} <= kat
        # KI schlägt vor ⇒ pending, NICHTS angelegt (HITL)
        r = c.post("/api/actions/propose",
                   json={"name": "aufgabe_anlegen",
                         "params": {"titel": "KI-Vorschlag", "prioritaet": "hoch"}}).json()
        assert r["status"] == "pending" and r["level"] == "lokal"
        assert c.get("/api/aufgaben").json() == []
        # Nutzer gibt frei ⇒ executed, Aufgabe existiert
        ap = c.post(f"/api/actions/{r['id']}/approve").json()
        assert ap["status"] == "executed"
        liste = c.get("/api/aufgaben").json()
        assert len(liste) == 1 and liste[0]["titel"] == "KI-Vorschlag" and liste[0]["prioritaet"] == "hoch"
        acts = [e["action"] for e in c.get("/api/audit").json()]
        assert "aktion_vorgeschlagen" in acts and "aktion_freigegeben" in acts and "aufgabe_angelegt" in acts

def test_k4_reject_legt_nichts_an(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/actions/propose",
                   json={"name": "projekt_anlegen", "params": {"name": "Verworfen"}}).json()
        assert c.post(f"/api/actions/{r['id']}/reject").json()["status"] == "rejected"
        assert c.get("/api/projekte").json() == []
        # nach reject nicht mehr pending ⇒ approve 404
        assert c.post(f"/api/actions/{r['id']}/approve").status_code == 404

def test_k4_termin_anlegen_via_hitl(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/actions/propose", json={"name": "termin_anlegen",
                   "params": {"titel": "KI-Termin", "beginn": "2026-09-01T09:00"}}).json()
        assert c.post(f"/api/actions/{r['id']}/approve").json()["status"] == "executed"
        t = c.get("/api/termine?von=2026-01-01").json()
        assert len(t) == 1 and t[0]["titel"] == "KI-Termin"

# ===================== Frist-/Termin-Wächter (/api/erinnerungen) =====================
def test_erinnerungen_waechter(tmp_path):
    import datetime
    h = heute_iso()
    morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    spaet = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    gestern = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    with _client(tmp_path) as c:
        c.post("/api/aufgaben", json={"titel": "Ueber", "faellig": gestern})
        c.post("/api/aufgaben", json={"titel": "HeuteFaellig", "faellig": h})
        c.post("/api/aufgaben", json={"titel": "Morgen", "faellig": morgen})
        c.post("/api/aufgaben", json={"titel": "Spaet", "faellig": spaet})
        erl = c.post("/api/aufgaben", json={"titel": "Erledigt", "faellig": gestern}).json()["id"]
        c.patch(f"/api/aufgaben/{erl}", json={"status": "erledigt"})   # zählt nicht
        c.post("/api/termine", json={"titel": "T heute", "beginn": h + "T10:00"})
        er = c.get("/api/erinnerungen").json()           # Default-Vorlauf 2
        assert er["vorlauf_tage"] == 2
        assert [a["titel"] for a in er["ueberfaellig"]] == ["Ueber"]
        assert [a["titel"] for a in er["heute"]] == ["HeuteFaellig"]
        assert [a["titel"] for a in er["bald"]] == ["Morgen"]          # Spaet (10 T) außerhalb Vorlauf
        assert [t["titel"] for t in er["termine"]] == ["T heute"]
        assert er["anzahl"] == 4
        # Vorlauf per Query erweitern ⇒ Spaet kommt in 'bald'
        er2 = c.get("/api/erinnerungen?vorlauf=14").json()
        assert {a["titel"] for a in er2["bald"]} == {"Morgen", "Spaet"}

# ===================== Wiederkehrend (RRULE-light) =====================
def test_aufgabe_wiederkehr_spawnt_folge(tmp_path):
    """Wiederkehrende Aufgabe: beim Abhaken entsteht deterministisch die nächste
    Instanz (faellig +1 Schritt), gleicher Titel/Regel, Status offen."""
    with _client(tmp_path) as c:
        aid = c.post("/api/aufgaben", json={
            "titel": "Wochenbericht", "faellig": "2026-06-22",
            "rrule": "FREQ=WEEKLY"}).json()["id"]
        r = c.patch(f"/api/aufgaben/{aid}", json={"status": "erledigt"}).json()
        assert "folgeaufgabe" in r and r["folgeaufgabe"]["faellig"] == "2026-06-29"
        offen = c.get("/api/aufgaben?status=offen").json()
        assert len(offen) == 1
        neu = offen[0]
        assert neu["titel"] == "Wochenbericht" and neu["rrule"] == "FREQ=WEEKLY"
        assert neu["faellig"] == "2026-06-29" and neu["id"] != aid
        # erneutes Patchen der bereits erledigten ⇒ KEIN weiterer Spawn (kein Endlos-Lauf)
        r2 = c.patch(f"/api/aufgaben/{aid}", json={"status": "erledigt"}).json()
        assert "folgeaufgabe" not in r2
        assert len(c.get("/api/aufgaben?status=offen").json()) == 1
        # auditiert
        assert any(e["action"] == "aufgabe_wiederkehr" for e in c.get("/api/audit").json())

def test_aufgabe_einmalig_kein_spawn(tmp_path):
    with _client(tmp_path) as c:
        aid = c.post("/api/aufgaben", json={"titel": "Einmal", "faellig": "2026-06-22"}).json()["id"]
        r = c.patch(f"/api/aufgaben/{aid}", json={"status": "erledigt"}).json()
        assert "folgeaufgabe" not in r
        assert c.get("/api/aufgaben?status=offen").json() == []

def test_aufgabe_rrule_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/aufgaben", json={"titel": "X", "rrule": "FREQ=STUNDE"}).status_code == 400
        ok = c.post("/api/aufgaben", json={"titel": "Y", "rrule": "FREQ=DAILY;INTERVAL=3"})
        assert ok.status_code == 200
        assert c.get("/api/aufgaben").json()[0]["rrule"] == "FREQ=DAILY;INTERVAL=3"

def test_termin_serie_expansion(tmp_path):
    with _client(tmp_path) as c:
        tid = c.post("/api/termine", json={"titel": "Standup", "beginn": "2026-06-01T09:00",
                                           "rrule": "FREQ=WEEKLY;COUNT=3"}).json()["id"]
        s = c.get(f"/api/termine/{tid}/serie").json()
        assert s["wiederkehrend"] is True
        beginne = [v["beginn"] for v in s["vorkommen"]]
        assert beginne == ["2026-06-01T09:00", "2026-06-08T09:00", "2026-06-15T09:00"]
        # einmaliger Termin ⇒ genau ein Vorkommen
        tid2 = c.post("/api/termine", json={"titel": "Einzel", "beginn": "2026-07-01T10:00"}).json()["id"]
        s2 = c.get(f"/api/termine/{tid2}/serie").json()
        assert s2["wiederkehrend"] is False and len(s2["vorkommen"]) == 1

# ===================== Netzwerk-Registry =====================

# ===================== KI (App-KI-Slot via Mini-Dizzi) =====================
class _FakeResp:
    status_code = 200

    def __init__(self, antwort):
        self._antwort = antwort

    def json(self):
        return {"message": {"content": json.dumps({"antwort": self._antwort})}}

# ===================== RÜCK-LESE: Plans-KI fragt Memory (docs/26 §10.1) =========
def test_wissen_suche_endpoint(tmp_path):
    calls: list = []
    treffer = [{"titel": "Notiz A", "auszug": "Inhalt A"}]
    with _client(tmp_path, memory_get=_memory_get_fake(treffer, store=calls)) as c:
        r = c.get("/api/wissen/suche?q=trading&limit=5").json()
        assert r["ok"] and r["anzahl"] == 1 and r["treffer"][0]["titel"] == "Notiz A"
        assert calls and calls[-1]["params"]["q"] == "trading"
        # leere Frage ⇒ keine Treffer, KEIN Relay-Call (kein Leerlauf)
        calls.clear()
        leer = c.get("/api/wissen/suche?q=").json()
        assert leer["treffer"] == [] and calls == []
        # semantisch=1 wird an Memory durchgereicht (RAG-Pfad)
        c.get("/api/wissen/suche?q=x&semantisch=1")
        assert calls[-1]["params"]["semantisch"] == "1"

# ===================== MCP-Namensraum =====================

# ===================== Frontend: UI-Kit + K2.3-Marken-Lockup =====================

# ===================== V5: Querverbindungs-Empfang Kalender (docs/26) =====================
def test_querverbindung_kalender_empfang(tmp_path):
    """Plans-Kalender-Empfänger (zweiter Vertragstyp): eine andere App trägt ein
    Event ein — als Termin angelegt, idempotent (quelle×extern_id), auditiert."""
    with _client(tmp_path) as c:
        body = {"titel": "Kickoff Call", "beginn": "2026-07-01T15:00",
                "ende": "2026-07-01T16:00", "ort": "Jitsi", "beschreibung": "Agenda folgt",
                "app": "kommunikation", "quelle": "komm:konv:42", "ref": "komm:termin:42"}
        r = c.post("/api/querverbindung/kalender", json=body).json()
        assert r["ok"] and r["status"] == "eingetragen" and r["id"]
        # Als Termin sichtbar, mit Herkunft + idempotenz-Feldern
        t = c.get("/api/termine").json()
        assert len(t) == 1 and t[0]["titel"] == "Kickoff Call"
        assert t[0]["quelle"] == "kommunikation" and t[0]["extern_id"] == "komm:termin:42"
        assert "Agenda folgt" in t[0]["notiz"] and "komm:konv:42" in t[0]["notiz"]
        # Idempotent: zweites Senden mit gleichem ref ⇒ vorhanden, kein Duplikat
        zwei = c.post("/api/querverbindung/kalender", json=body).json()
        assert zwei["status"] == "vorhanden" and zwei["id"] == r["id"]
        assert len(c.get("/api/termine").json()) == 1
        # beginn ist Pflicht
        assert c.post("/api/querverbindung/kalender", json={"titel": "X"}).status_code == 400
        # auditiert
        assert any(e["action"] == "querverbindung_kalender_empfangen"
                   for e in c.get("/api/audit").json())
