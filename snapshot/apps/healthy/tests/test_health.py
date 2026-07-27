"""Tests Dizz Healthy [HE]: Vertrags-Konformität + Domäne (Messwerte/Supplements/
Verletzungen/Training/Termine) + deterministische Trends + FHIR-Observation +
HealthSource-Adapter (dormant, Gesetz 5) + KI-Frage/-Analyse-Smoke + MCP-Namensraum
+ UI-Kit/Marken-Lockup + HOCHSENSIBEL-Routing (lokal_only).

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from appkit import conformance
from healthapp import fhir
from healthapp import main as hm
from healthapp.domain import heute_iso
from healthapp.sources import (AppleHealthSource, BLEHeartRateSource,
                               HealthConnectSource, HealthSample, ManualSource,
                               QuelleNichtVerbunden, UnifiedApiSource,
                               ble_lesen, ble_scan, ble_stack_verfuegbar,
                               parse_blood_pressure, parse_heart_rate,
                               parse_temperature, parse_weight, quellen_status)


def _client(tmp_path, *, http_post=None, archiv_post=None) -> TestClient:
    kw = {}
    if http_post is not None:
        kw["http_post"] = http_post
    if archiv_post is not None:
        kw["archiv_post"] = archiv_post
    return TestClient(hm.build_app(data_dir=tmp_path, **kw))


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


# ===================== V13: Healthy → Plans (Kalender, nur Meta) =====================
def _kalender_capture(store):
    class _R:
        status_code = 200
        @staticmethod
        def json():
            return {"ok": True, "status": "eingetragen", "id": "k1"}
    def post(url, json):
        store.append({"url": url, "payload": json})
        return _R()
    return post


def test_termin_an_plans_sendet_nur_meta(tmp_path):
    """V13: 'an Plans' reicht Titel/Datum/Ort/Kategorie an Dizz Plans — `hoechst`-konform
    OHNE notiz/Werte (Diagnose bleibt in Healthy)."""
    cal: list = []
    app = hm.build_app(data_dir=tmp_path, kalender_post=_kalender_capture(cal))
    with TestClient(app) as c:
        tid = c.post("/api/termine", json={
            "titel": "Kardiologie Kontrolle", "beginn": "2026-07-01",
            "kategorie": "arzt", "ort": "Praxis Dr. Müller",
            "notiz": "Blutdruck 160/95 besprechen"}).json()["id"]
        r = c.post(f"/api/termine/{tid}/an-plans").json()
        assert r.get("ok") is True
        assert cal and cal[0]["url"].endswith("/api/querverbindung/admin/kalender")
        p = cal[0]["payload"]
        assert p["app"] == "health" and p["ref"] == "health:termin:" + tid
        assert p["beginn"] == "2026-07-01" and p["titel"] == "Kardiologie Kontrolle"
        assert p["ort"] == "Praxis Dr. Müller"
        # hoechst: KEINE Werte/Notiz im Umschlag
        flat = " ".join(str(v) for v in p.values())
        assert "160/95" not in flat and "Blutdruck" not in flat


def test_termin_an_plans_unbekannt_sendet_nicht(tmp_path):
    cal: list = []
    app = hm.build_app(data_dir=tmp_path, kalender_post=_kalender_capture(cal))
    with TestClient(app) as c:
        r = c.post("/api/termine/nope/an-plans").json()
        assert r.get("ok") is False and cal == []


def _kpis(c):
    return {k["id"]: k["value"] for k in c.get("/api/summary").json()["kpis"]}


def test_verletzung_archivieren_an_memory(tmp_path):
    """V10 (docs/26): der „⇲ Memory"-Knopf schickt eine Verletzung explizit über den
    Core-Relay an Dizz Memory. Health = `hoechst` ⇒ IMMER ``sensibel=True`` (Memory-KI
    nur lokal); Umschlag korrekt, Beschreibung/Notiz im Body, Körperregion als Tag."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        vid = c.post("/api/verletzungen", json={
            "koerperregion": "Knie links", "schweregrad": "mittel",
            "beschreibung": "Meniskusreizung", "notiz": "Physio ab Juli"}).json()["id"]

        r = c.post(f"/api/verletzungen/{vid}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "health" and u["strom"] == "verletzung"
        assert u["explizit"] is True and u["ref"] == "health:verletzung:" + vid
        assert u["sensibel"] is True                  # hoechst ⇒ IMMER sensibel
        assert u["tags"] == ["Knie links"]
        assert u["titel"] == "Verletzung · Knie links"
        assert "Meniskusreizung" in u["inhalt"] and "Physio ab Juli" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        assert "verletzung_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/verletzungen/fehlt/archivieren").status_code == 404


def _vor(tage: int) -> str:
    return (date.today() - timedelta(days=tage)).isoformat()


# ===================== Vertrag =====================
def test_vertrag_konform(tmp_path):
    with _client(tmp_path) as c:
        conformance.check_contract(c, "health")
        # Dizzi-ID-Anschluss installiert; ohne Login = Standalone-Stufe 'lokal'.
        assert c.get("/auth/me").json() == {"angemeldet": False, "level": "lokal"}


def test_hochsensibel_routing_lokal_only(tmp_path):
    """HOCHSENSIBEL: Manifest sensitivity='hoechst' ⇒ KI-Routing-Default lokal_only
    (nie Cloud/Boost). Sicherheits-Kern der App (docs/RECHERCHE §5)."""
    with _client(tmp_path) as c:
        m = c.get("/api/manifest").json()
        assert m["sensitivity"] == "hoechst"
        vals = c.get("/api/settings").json()
        assert vals["ki_routing"] == "lokal_only"


# ===================== Messwerte + Trends + FHIR =====================
def test_messwert_crud_und_kachel(tmp_path):
    with _client(tmp_path) as c:
        assert _kpis(c)["gewicht"] == "—"
        mid = c.post("/api/messwerte",
                     json={"art": "gewicht", "wert": 78.5}).json()["id"]
        liste = c.get("/api/messwerte?art=gewicht").json()
        assert len(liste) == 1 and liste[0]["einheit"] == "kg"   # Einheit aus Katalog
        assert _kpis(c)["gewicht"] == "78.5"
        assert _kpis(c)["messwerte_30t"] == 1
        # Audit-Beleg + unbekannte Art wird abgelehnt
        assert "messwert_angelegt" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/messwerte", json={"art": "quatsch", "wert": 1}).status_code == 400
        # nicht-numerischer Wert ⇒ 422 (Pydantic) oder 400 (Domäne)
        assert c.post("/api/messwerte", json={"art": "gewicht", "wert": "viel"}).status_code in (400, 422)
        assert c.delete(f"/api/messwerte/{mid}").json()["ok"]
        assert c.get("/api/messwerte?art=gewicht").json() == []


def test_messwert_referenzbereich(tmp_path):
    with _client(tmp_path) as c:
        # SpO2 94–100 ⇒ 88 ist außerhalb (orientierend, keine Diagnose)
        c.post("/api/messwerte", json={"art": "spo2", "wert": 88})
        c.post("/api/messwerte", json={"art": "spo2", "wert": 97})
        liste = {m["wert"]: m["im_referenzbereich"] for m in c.get("/api/messwerte?art=spo2").json()}
        assert liste[88.0] is False and liste[97.0] is True


def test_trends_deterministisch(tmp_path):
    with _client(tmp_path) as c:
        # drei Gewichtswerte, klar fallend
        for tag, w in ((10, 82.0), (5, 80.0), (1, 78.0)):
            c.post("/api/messwerte", json={"art": "gewicht", "wert": w,
                                           "gemessen_am": _vor(tag) + "T08:00:00"})
        t = c.get("/api/trends?tage=30").json()["trends"]
        gw = next(x for x in t if x["art"] == "gewicht")
        assert gw["letzter_wert"] == 78.0 and gw["anzahl"] == 3
        assert gw["richtung"] == "fallend" and gw["delta"] == -4.0
        assert gw["mittel"] == 80.0


def test_messwert_fhir_observation(tmp_path):
    with _client(tmp_path) as c:
        mid = c.post("/api/messwerte",
                     json={"art": "puls", "wert": 62,
                           "gemessen_am": "2026-06-15T07:30:00+00:00"}).json()["id"]
        obs = c.get(f"/api/messwerte/{mid}/fhir").json()
        assert obs["resourceType"] == "Observation"
        assert obs["code"]["coding"][0]["code"] == "8867-4"        # LOINC Heart rate
        assert obs["code"]["coding"][0]["system"] == "http://loinc.org"
        assert obs["valueQuantity"]["value"] == 62
        assert obs["valueQuantity"]["code"] == "/min"              # UCUM
        assert obs["category"][0]["coding"][0]["code"] == "vital-signs"


def test_fhir_unit_builder_direkt():
    obs = fhir.to_fhir_observation("blutdruck_sys", 122, "2026-06-15", extern_id="x1")
    assert obs["code"]["coding"][0]["code"] == "8480-6"
    assert obs["valueQuantity"]["unit"] == "mmHg"
    assert obs["identifier"][0]["value"] == "x1"
    # unbekannte Art: tolerant, ohne LOINC-Coding, Daten bleiben erhalten
    roh = fhir.to_fhir_observation("unbekannt", 5, "2026-06-15")
    assert "coding" not in roh["code"] and roh["valueQuantity"]["value"] == 5


def test_messwert_katalog_endpoint(tmp_path):
    with _client(tmp_path) as c:
        arten = c.get("/api/messwerte/arten").json()["arten"]
        keys = {a["art"] for a in arten}
        assert {"gewicht", "blutdruck_sys", "puls", "spo2", "glukose"} <= keys
        gw = next(a for a in arten if a["art"] == "gewicht")
        assert gw["einheit"] == "kg"


# ===================== Supplements =====================
def test_supplement_crud(tmp_path):
    with _client(tmp_path) as c:
        sid = c.post("/api/supplements",
                     json={"name": "Vitamin D3", "dosis": "2000", "einheit": "IE",
                           "frequenz": "taeglich"}).json()["id"]
        assert _kpis(c)["supplements"] == 1
        assert c.get("/api/supplements?aktiv=1").json()[0]["name"] == "Vitamin D3"
        # deaktivieren ⇒ raus aus aktiv
        c.patch(f"/api/supplements/{sid}", json={"aktiv": False})
        assert _kpis(c)["supplements"] == 0
        assert c.get("/api/supplements?aktiv=0").json()[0]["aktiv"] is False
        assert c.delete(f"/api/supplements/{sid}").json()["ok"]
        assert c.post("/api/supplements", json={"name": "  "}).status_code == 400


# ===================== Verletzungen =====================
def test_verletzung_crud_und_status(tmp_path):
    with _client(tmp_path) as c:
        vid = c.post("/api/verletzungen",
                     json={"koerperregion": "Knie links", "schweregrad": "mittel"}).json()["id"]
        assert _kpis(c)["verletzungen"] == 1
        assert c.get("/api/verletzungen?status=akut").json()[0]["koerperregion"] == "Knie links"
        # heilen lassen ⇒ raus aus „offen"
        c.patch(f"/api/verletzungen/{vid}", json={"status": "verheilt"})
        assert _kpis(c)["verletzungen"] == 0
        assert c.delete(f"/api/verletzungen/{vid}").json()["ok"]
        assert c.post("/api/verletzungen", json={"koerperregion": ""}).status_code == 400


# ===================== Training =====================
def test_training_crud(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/trainings", json={"art": "Laufen", "dauer_min": 45,
                                       "intensitaet": "moderat", "kennzahl_name": "Distanz",
                                       "kennzahl_wert": 8.2, "kennzahl_einheit": "km",
                                       "trainiert_am": heute_iso()})
        liste = c.get("/api/trainings").json()
        assert len(liste) == 1 and liste[0]["art"] == "Laufen" and liste[0]["kennzahl_wert"] == 8.2
        assert c.get("/api/stats").json()["trainings_7t"] == 1
        tid = liste[0]["id"]
        assert c.delete(f"/api/trainings/{tid}").json()["ok"]
        assert c.post("/api/trainings", json={"art": ""}).status_code == 400


# ===================== Termine =====================
def test_termin_crud_und_kommend(tmp_path):
    with _client(tmp_path) as c:
        morgen = (date.today() + timedelta(days=1)).isoformat()
        tid = c.post("/api/termine",
                     json={"titel": "Hausarzt Kontrolle", "kategorie": "vorsorge",
                           "beginn": morgen + "T09:00", "ort": "Praxis Dr. X"}).json()["id"]
        # Kachel zeigt den nächsten Termin
        assert _kpis(c)["termine"] == morgen
        assert c.get("/api/stats").json()["termine_kommend"] == 1
        # „kommend"-Filter (auch vom MCP genutzt)
        komm = c.get("/api/termine?kommend=1").json()
        assert len(komm) == 1 and komm[0]["titel"] == "Hausarzt Kontrolle"
        c.patch(f"/api/termine/{tid}", json={"ort": "Neue Praxis"})
        assert c.get("/api/termine?kommend=1").json()[0]["ort"] == "Neue Praxis"
        assert c.delete(f"/api/termine/{tid}").json()["ok"]
        # Pflichtfelder
        assert c.post("/api/termine", json={"titel": "x"}).status_code == 422 \
            or c.post("/api/termine", json={"titel": "x", "beginn": ""}).status_code == 400


# ===================== HealthSource-Adapter (dormant, Gesetz 5) =====================
def test_manual_source_v1_echt():
    s = ManualSource([HealthSample("gewicht", 80.0, "2026-06-10"),
                      HealthSample("gewicht", 79.0, "2026-06-14")])
    assert s.verfuegbar() is True
    assert len(s.list_samples()) == 2
    assert len(s.list_samples(since="2026-06-12")) == 1


def test_wearable_adapter_dormant():
    # Apple/Health Connect: ohne Mobile-Brücke nicht verbunden, ehrlicher Fehler
    for Src in (AppleHealthSource, HealthConnectSource):
        a = Src()
        assert a.verfuegbar() is False
        with pytest.raises(QuelleNichtVerbunden):
            a.list_samples()
    # Terra/Unified: Token-Tresor-gated (wie Plans' Google-Adapter)
    leer = UnifiedApiSource(vault_get=lambda _n: None)
    assert leer.verfuegbar() is False
    mit = UnifiedApiSource(vault_get=lambda _n: "api-key-xyz")
    assert mit.verfuegbar() is True and mit.status()["verbunden"] is True
    with pytest.raises(QuelleNichtVerbunden):
        mit.list_samples()
    # BLE/GATT-Slot: dormant ohne Stack, aber Profile dokumentiert
    ble = BLEHeartRateSource()
    assert ble.verfuegbar() is False
    assert ble.status()["profile"]["heart_rate"]["service"] == "0x180D"


def test_quellen_endpoint_sichtbar(tmp_path):
    with _client(tmp_path) as c:
        q = c.get("/api/quellen").json()["quellen"]
        namen = {x["name"] for x in q}
        assert {"manuell", "apple_health", "health_connect", "terra", "ble"} <= namen
        manuell = next(x for x in q if x["name"] == "manuell")
        assert manuell["verbunden"] is True
        assert all(x["verbunden"] is False for x in q if x["name"] != "manuell")


def test_quellen_status_direkt():
    out = quellen_status(vault_get=lambda _n: None)
    assert {x["name"] for x in out} >= {"manuell", "ble"}


# ===================== KI (App-KI-Slot + Analyse, lokal) =====================
class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return {"message": {"content": json.dumps(self._payload)}}


def test_ki_frage_smoke(tmp_path):
    def fake_post(url, daten):                 # Signatur wie ki._post(url, daten)
        return _FakeResp({"antwort": "Dein Gewicht ist zuletzt leicht gefallen."})
    with _client(tmp_path, http_post=fake_post) as c:
        c.post("/api/messwerte", json={"art": "gewicht", "wert": 79})
        r = c.post("/api/ki/frage", json={"frage": "Wie steht mein Gewicht?"}).json()
        assert r["antwort"] == "Dein Gewicht ist zuletzt leicht gefallen."
        assert r["quelle"] == "app_ki"


def test_ki_analyse_smoke_und_disclaimer(tmp_path):
    def fake_post(url, daten):
        return _FakeResp({"hinweise": ["Ruhepuls beobachten.", "Vorsorge steht an."]})
    with _client(tmp_path, http_post=fake_post) as c:
        c.post("/api/messwerte", json={"art": "ruhepuls", "wert": 58})
        r = c.post("/api/analyse").json()
        assert r["hinweise"] == ["Ruhepuls beobachten.", "Vorsorge steht an."]
        assert "Diagnose" in r["disclaimer"]        # nie Diagnose
        assert "trends" in r and r["quelle"] == "lokale_ki"
        assert "analyse_erstellt" in [e["action"] for e in c.get("/api/audit").json()]


# ===================== MCP-Namensraum =====================
def test_mcp_server_tools_namespaced(tmp_path):
    pytest.importorskip("fastmcp")
    from healthapp import mcp_server   # Import beweist: kein stdout-Schreiben
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"health_kachel_stats", "health_gesundheits_trend",
            "health_naechste_termine", "health_aktive_supplements"} <= names
    assert "kachel_stats" not in names      # nackter Name kollidiert NICHT


# ===================== Frontend: UI-Kit + K2.3-Marken-Lockup =====================
def test_frontend_uikit_und_lockup(tmp_path):
    with _client(tmp_path) as c:
        css = c.get("/ui-kit/controls.css")
        assert css.status_code == 200 and "dz-check" in css.text and "dz-panel" in css.text
        js = c.get("/ui-kit/collapse.js")
        assert js.status_code == 200 and "initControls" in js.text
        html = c.get("/").text
        assert "/ui-kit/controls.css" in html and "/ui-kit/collapse.js" in html
        assert "data-dz-collapsible" in html                  # Panels einklappbar
        assert 'class="dz-appkopf"' in html and 'class="dz-kopf-brand">Dizz Healthy' in html
        assert "<title>Dizz Healthy — Gesundheit</title>" in html
        assert "/api/ki/frage" in html                        # Mini-Dizzi verdrahtet
        assert "/api/messwerte" in html and "/api/analyse" in html


# ===================== P1: Katalog/Kategorie/FHIR (Aktivität) =====================
def test_katalog_kategorie_und_aktivitaet(tmp_path):
    with _client(tmp_path) as c:
        arten = {a["art"]: a for a in c.get("/api/messwerte/arten").json()["arten"]}
        # Aktivitäts-Arten vorhanden + als 'aktivitaet' kategorisiert
        for a in ("schritte", "distanz", "etagen", "aktive_minuten", "kalorien", "stehstunden"):
            assert arten[a]["kategorie"] == "aktivitaet", a
        assert arten["gewicht"]["kategorie"] == "vital"
        assert arten["schritte"]["ziel"] == 8000        # Ring-Default aus dem Katalog
        # Distanz hat keinen etablierten LOINC ⇒ leer (ehrlich)
        assert arten["distanz"]["loinc"] == ""


def test_fhir_ohne_loinc_bei_aktivitaet():
    obs = fhir.to_fhir_observation("distanz", 5.2, "2026-06-19", einheit="km")
    assert "coding" not in obs["code"]               # kein erfundenes Coding
    assert obs["code"]["text"] == "Distanz"
    assert obs["valueQuantity"]["unit"] == "km" and obs["valueQuantity"]["value"] == 5.2


def test_trends_tragen_kategorie_und_verlauf(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/messwerte", json={"art": "gewicht", "wert": 80})
        c.post("/api/messwerte", json={"art": "gewicht", "wert": 79})
        gw = next(t for t in c.get("/api/trends").json()["trends"] if t["art"] == "gewicht")
        assert gw["kategorie"] == "vital"
        assert gw["verlauf"] == [80.0, 79.0]          # Sparkline-Serie (älteste→neueste)


# ===================== P1d: Aktivitäts-Tracker (Hybrid) =====================
def test_aktivitaet_eintragen_ringe_und_roh(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/aktivitaet", json={"schritte": 8000, "distanz": 5.2,
                                            "aktive_minuten": 40, "stehstunden": 10}).json()
        assert r["ok"] is True and set(r["geschrieben"]) == {"schritte", "distanz",
                                                             "aktive_minuten", "stehstunden"}
        tag = c.get("/api/aktivitaet/tag").json()
        ringe = {x["key"]: x for x in tag["ringe"]}
        assert set(ringe) == {"schritte", "aktive_minuten", "stehstunden"}   # Apple-Muster
        assert ringe["schritte"]["erreicht"] is True and ringe["schritte"]["prozent"] == 100
        assert ringe["aktive_minuten"]["erreicht"] is True       # 40 >= Ziel 30
        assert ringe["stehstunden"]["erreicht"] is False         # 10 < Ziel 12
        assert tag["werte"]["distanz"] == 5.2
        # Hybrid: roh als Messwert vorhanden (FHIR/Sync-fähig) + in den Stats
        roh = c.get("/api/messwerte?art=schritte").json()
        assert len(roh) == 1 and roh[0]["wert"] == 8000
        assert c.get("/api/stats").json()["schritte_heute"] == 8000


def test_aktivitaet_ersetzt_tageswert(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/aktivitaet", json={"schritte": 8000})
        c.post("/api/aktivitaet", json={"schritte": 9500})       # gleicher Tag ⇒ ersetzen
        roh = c.get("/api/messwerte?art=schritte").json()
        assert len(roh) == 1 and roh[0]["wert"] == 9500          # kein Anhäufen
        assert c.get("/api/aktivitaet/tag").json()["werte"]["schritte"] == 9500


def test_aktivitaet_verlauf_tagesreihe(tmp_path):
    with _client(tmp_path) as c:
        heute = date.today().isoformat()
        gestern = (date.today() - timedelta(days=1)).isoformat()
        c.post("/api/aktivitaet", json={"datum": gestern, "schritte": 6000})
        c.post("/api/aktivitaet", json={"datum": heute, "schritte": 8200})
        p = c.get("/api/aktivitaet/verlauf?art=schritte&tage=7").json()["punkte"]
        assert [x["datum"] for x in p] == [gestern, heute]       # aufsteigend
        assert [x["wert"] for x in p] == [6000, 8200]


def test_aktivitaet_ziel_aus_setting(tmp_path):
    with _client(tmp_path) as c:
        c.put("/api/settings", json={"key": "ziel_schritte", "value": 5000})
        c.post("/api/aktivitaet", json={"schritte": 5000})
        ring = next(x for x in c.get("/api/aktivitaet/tag").json()["ringe"]
                    if x["key"] == "schritte")
        assert ring["ziel"] == 5000 and ring["erreicht"] is True


# ===================== P1: Mini-Chart-Kit + Frontend =====================
def test_chartkit_und_metrik_frontend(tmp_path):
    with _client(tmp_path) as c:
        # Kit-Dateien werden ausgeliefert
        js = c.get("/ui-kit/charts.js")
        assert js.status_code == 200 and "DzCharts" in js.text and "activityRings" in js.text
        css = c.get("/ui-kit/charts.css")
        assert css.status_code == 200 and "dz-metric" in css.text and "dz-ring" in css.text
        html = c.get("/").text
        assert "/ui-kit/charts.css" in html and "/ui-kit/charts.js" in html
        assert "dz-metric-list" in html                          # Metrik-Karten-Grid (P1a)
        assert 'data-pkey="aktivitaet"' in html                  # Aktivitäts-Panel (P1d)
        assert 'id="ki-lokal-badge"' in html and "Keine Diagnose" in html   # P1c
        assert "/api/aktivitaet" in html


# ===================== P2: Unified Timeline =====================
def test_timeline_merge_domaenen(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/messwerte", json={"art": "gewicht", "wert": 80})
        c.post("/api/trainings", json={"art": "Laufen", "dauer_min": 30,
                                       "trainiert_am": date.today().isoformat()})
        c.post("/api/termine", json={"titel": "Arzt",
                                     "beginn": (date.today() + timedelta(days=2)).isoformat()})
        c.post("/api/verletzungen", json={"koerperregion": "Knie"})
        c.post("/api/supplements", json={"name": "Zink"})
        c.post("/api/aktivitaet", json={"schritte": 8000})
        ev = c.get("/api/timeline").json()["events"]
        doms = {e["domaene"] for e in ev}
        assert {"messwert", "training", "termin", "verletzung", "supplement", "aktivitaet"} <= doms
        # neueste zuerst + Farb-Token je Domäne gesetzt
        datums = [e["datum"] for e in ev]
        assert datums == sorted(datums, reverse=True)
        assert all(e.get("farbe") for e in ev)
        # Aktivität als EINE Tagesbilanz (nicht je Rohwert) — Schritte nicht als 'messwert'
        assert not any(e["domaene"] == "messwert" and "Schritte" in e["titel"] for e in ev)


# ===================== P2: Korrelation (deterministisch, nicht-medizinisch) =====================
def test_pearson_unit():
    from healthapp.domain import Domain
    assert Domain._pearson([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0     # perfekt linear
    assert Domain._pearson([1, 2], [1, 2]) is None                # <3 Punkte
    assert Domain._pearson([1, 1, 1], [2, 3, 4]) is None          # keine x-Streuung


def test_spearman_unit():
    """P3.3c: Spearman = Rangkorrelation (Monotonie). Robuster als Pearson bei
    nicht-linearen, aber streng monotonen Zusammenhängen + sauberes Tie-Handling."""
    from healthapp.domain import Domain
    # streng monoton, aber NICHT linear (kubisch) ⇒ Spearman 1.0, Pearson < 1.0
    xs, ys = [1, 2, 3, 4, 5], [1, 8, 27, 64, 125]
    assert Domain._spearman(xs, ys) == 1.0
    assert Domain._pearson(xs, ys) < 1.0                          # linear „sieht" weniger
    # monoton fallend ⇒ -1.0
    assert Domain._spearman([1, 2, 3, 4], [9, 7, 5, 1]) == -1.0
    # Tie-Mittelung: gleiche Werte teilen den Mittel-Rang
    assert Domain._raenge([10, 10, 20]) == [1.5, 1.5, 3.0]
    # Grenzen: <3 Punkte / keine Streuung ⇒ None (ehrlich)
    assert Domain._spearman([1, 2], [1, 2]) is None
    assert Domain._spearman([5, 5, 5], [1, 2, 3]) is None


def test_korrelation_metriken_gruppen(tmp_path):
    with _client(tmp_path) as c:
        m = c.get("/api/korrelation/metriken").json()["metriken"]
        belastung = {x["key"] for x in m if x["gruppe"] == "belastung"}
        erholung = {x["key"] for x in m if x["gruppe"] == "erholung"}
        assert {"aktive_minuten", "schritte", "training_min"} <= belastung
        assert {"ruhepuls", "hrv", "schlaf"} <= erholung


def test_korrelation_paarung_und_r(tmp_path):
    with _client(tmp_path) as c:
        am, rp = [20, 30, 40, 50], [50, 55, 60, 65]              # perfekt linear ⇒ r=1.0
        for i in range(4):
            d = (date.today() - timedelta(days=i)).isoformat()
            c.post("/api/aktivitaet", json={"datum": d, "aktive_minuten": am[i]})
            c.post("/api/messwerte", json={"art": "ruhepuls", "wert": rp[i],
                                           "gemessen_am": d + "T08:00:00"})
        k = c.get("/api/korrelation?x=aktive_minuten&y=ruhepuls&tage=30").json()
        assert k["n"] == 4 and len(k["punkte"]) == 4
        assert k["x_label"] == "Aktive Minuten" and k["y_label"] == "Ruhepuls"
        assert k["r"] == 1.0
        assert k["r_spearman"] == 1.0          # P3.3c: monoton ⇒ ebenfalls 1.0


def test_korrelation_zu_wenig_punkte(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/aktivitaet", json={"aktive_minuten": 30})
        c.post("/api/messwerte", json={"art": "ruhepuls", "wert": 55})
        k = c.get("/api/korrelation").json()                     # nur heute = 1 gemeinsamer Tag
        assert k["r"] is None and k["n"] <= 1


# ===================== P2: Scatter-Kit + Frontend =====================
def test_p2_scatter_kit_und_frontend(tmp_path):
    with _client(tmp_path) as c:
        js = c.get("/ui-kit/charts.js").text
        assert "mountScatter" in js
        css = c.get("/ui-kit/charts.css").text
        assert "dz-scatter-dot" in css and "dz-timeline" in css
        html = c.get("/").text
        assert 'data-pkey="timeline"' in html and 'data-pkey="korrelation"' in html
        assert "/api/timeline" in html and "/api/korrelation" in html
        assert 'id="korr-chart"' in html and "Kein Kausalzusammenhang" in html


# ===================== P3: Composite-Scores (nicht-medizinisch) =====================
def test_readiness_score(tmp_path):
    with _client(tmp_path) as c:
        for i, (rp, hrv) in enumerate([(60, 40), (59, 42), (57, 46)]):
            d = (date.today() - timedelta(days=2 - i)).isoformat()
            c.post("/api/messwerte", json={"art": "ruhepuls", "wert": rp, "gemessen_am": d + "T07:00:00"})
            c.post("/api/messwerte", json={"art": "hrv", "wert": hrv, "gemessen_am": d + "T07:00:00"})
        c.post("/api/aktivitaet", json={"schlaf": 8, "aktive_minuten": 30})
        rd = c.get("/api/scores").json()["readiness"]
        assert rd["verfuegbar"] is True and 0 <= rd["score"] <= 100
        keys = {k["key"] for k in rd["komponenten"]}
        assert {"ruhepuls", "hrv", "schlaf"} <= keys
        assert rd["konfidenz"] == "hoch"                     # >=3 Komponenten
        assert "Diagnose" in rd["disclaimer"]                # nie Diagnose


def test_readiness_leer(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/scores").json()["readiness"]["verfuegbar"] is False


def test_bio_alter_braucht_geburtsjahr(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/messwerte", json={"art": "ruhepuls", "wert": 55})
        c.post("/api/aktivitaet", json={"schritte": 11000, "aktive_minuten": 45})
        assert c.get("/api/scores").json()["bio_alter"]["verfuegbar"] is False
        c.put("/api/settings", json={"key": "geburtsjahr", "value": 1990})
        ba = c.get("/api/scores").json()["bio_alter"]
        assert ba["verfuegbar"] is True
        assert ba["chrono_alter"] == date.today().year - 1990
        assert "bio_alter" in ba and ba["komponenten"]
        assert ba["differenz"] <= 0                          # fit ⇒ tendenziell jünger


def test_korrelation_lag_folgetag(tmp_path):
    with _client(tmp_path) as c:
        days = [(date.today() - timedelta(days=i)).isoformat() for i in range(4)]
        c.post("/api/aktivitaet", json={"datum": days[3], "aktive_minuten": 20})
        c.post("/api/aktivitaet", json={"datum": days[2], "aktive_minuten": 40})
        c.post("/api/messwerte", json={"art": "ruhepuls", "wert": 50, "gemessen_am": days[2] + "T07:00:00"})
        c.post("/api/messwerte", json={"art": "ruhepuls", "wert": 55, "gemessen_am": days[1] + "T07:00:00"})
        k = c.get("/api/korrelation?x=aktive_minuten&y=ruhepuls&lag=1&tage=30").json()
        assert k["lag"] == 1
        # Belastung Tag d ↔ Erholung Tag d+1
        paare = {p["x"]: p["y"] for p in k["punkte"]}
        assert paare.get(20) == 50 and paare.get(40) == 55


# ===================== P3: GPS-Routen-Slot (Gesetz 5, vorbereitet) =====================
def test_gps_route_slot():
    from healthapp.sources import GPSRoute, RoutePunkt
    r = GPSRoute(extern_id="rt1", art="lauf", distanz_km=5.0,
                 punkte=[RoutePunkt(48.1, 11.5, "2026-06-19T08:00:00", hoehe=520.0)])
    assert r.quelle == "apple_health" and r.distanz_km == 5.0
    assert r.punkte[0].lat == 48.1 and r.punkte[0].hoehe == 520.0


# ===================== P3: Gauge-Kit + Frontend =====================
def test_p3_scores_kit_und_frontend(tmp_path):
    with _client(tmp_path) as c:
        assert "gauge" in c.get("/ui-kit/charts.js").text
        css = c.get("/ui-kit/charts.css").text
        assert "dz-gauge" in css and "dz-score-card" in css
        html = c.get("/").text
        assert 'data-pkey="scores"' in html and "/api/scores" in html
        assert 'id="kf-lag"' in html                         # Korrelations-Lag
        assert "Keine medizinische Aussage" in html


# ===================== UI-Systematisierung (Gruppen + Übersichts-Dashboard) =====================
def test_ui_gruppen_und_uebersicht(tmp_path):
    with _client(tmp_path) as c:
        html = c.get("/").text
        # 3 Gruppen-Panels + fettes Übersichts-Dashboard (oben)
        for pk in ("uebersicht", "grp-tagebuch", "grp-auswertung", "quellen"):
            assert 'data-pkey="' + pk + '"' in html, pk
        # Unter-Panels (dz-subpanel, dz-panel-Collapse-Muster, KEIN .card)
        assert "dz-subpanel-list" in html and html.count('class="dz-panel dz-subpanel"') == 10
        for pk in ("messwerte", "supplements", "verletzungen", "training", "termine",
                   "aktivitaet", "scores", "timeline", "korrelation", "ki-auswertung"):
            assert 'data-pkey="' + pk + '"' in html, pk
        # Konfigurierbarer KPI-Slot (Gerüst — finale Auswahl via UI Builder Tool)
        assert 'id="dash-kpis"' in html and "dashKonfigToggle" in html and "DASH_KATALOG" in html
        # Layout-Gerüst (News-Shell, docs/14 v4.3): .wrap (overflow:visible, zentriert) = Spin-Grid-
        # Umfeld; Top-Karten als Block-Fluss (KEIN Grid mehr ⇒ fixt Clip-/Überlapp-Bug). Voll-breit
        # ergibt sich aus dem Block-Fluss; KPI-Kachel-Grid bleibt token-basiert.
        assert "dz-kpi-grid" in html and 'class="wrap"' in html and "main>.card{margin-bottom" in html
        # Collapse-Muster bleibt (Gruppen + Unter-Panels einklappbar)
        assert html.count("data-dz-collapsible") >= 13       # 3 Gruppen + 10 Unter-Panels


# ===================== CSP voll-strikt (Nonce, docs/37) =====================
def test_csp_voll_strikt(tmp_path):
    import re as _re
    with _client(tmp_path) as c:
        r = c.get("/")
        csp = r.headers.get("content-security-policy", "")
        # script-src trägt den Nonce und KEIN 'unsafe-inline'
        assert "script-src 'self' 'nonce-" in csp
        script_dir = csp.split("script-src", 1)[1].split(";", 1)[0]
        assert "'unsafe-inline'" not in script_dir
        html = r.text
        # inline <script> bekommt das Per-Request-Nonce injiziert
        assert _re.search(r'<script nonce="[^"]+"', html)
        # 0 echte Inline-Handler-Attribute (onclick="/onchange="/onkeydown=") — Delegation aktiv
        assert not _re.search(r'\son(click|change|keydown|input|submit|mousedown)="', html)
        assert "data-dz-act=" in html and "data-dz-enter=" in html
        assert "javascript:" not in html


# ===================== Lokale Vorschläge / Erinnerungen (in-App, NIE Diagnose) =====
def test_vorschlaege_deterministisch_und_abschaltbar(tmp_path):
    with _client(tmp_path) as c:
        # leer: Regel-Quelle + Disclaimer; ohne Training ein sanfter Onboarding-Nudge (info)
        d0 = c.get("/api/vorschlaege").json()
        assert d0["quelle"] == "regel" and "Diagnose" in d0["disclaimer"]
        tr0 = [v for v in d0["vorschlaege"] if v["typ"] == "training"]
        assert tr0 and tr0[0]["prio"] == "info"     # "Noch kein Training erfasst …"
        # Training vor 9 Tagen ⇒ Trainingslücke-Nudge (Default-Grenze 4)
        alt = (date.today() - timedelta(days=9)).isoformat()
        assert c.post("/api/trainings", json={"art": "Laufen", "intensitaet": "locker",
                                              "trainiert_am": alt}).status_code in (200, 201)
        d1 = c.get("/api/vorschlaege").json()
        typen = {v["typ"] for v in d1["vorschlaege"]}
        assert "training" in typen
        tr = next(v for v in d1["vorschlaege"] if v["typ"] == "training")
        assert tr["prio"] == "warn" and "Training" in tr["text"]
        # abschaltbar: erinnerung_training=False ⇒ Nudge weg
        assert c.put("/api/settings", json={"key": "erinnerung_training", "value": False}).status_code == 200
        d2 = c.get("/api/vorschlaege").json()
        assert "training" not in {v["typ"] for v in d2["vorschlaege"]}


def test_vorschlaege_ki_schicht_ollama_frei(tmp_path):
    # Fake-Ollama liefert konkrete Vorschläge ⇒ KI-Schicht normiert auf <=3 Strings.
    def fake_post(url, daten):
        class _R:
            status_code = 200
            @staticmethod
            def json():
                return {"message": {"content": json.dumps(
                    {"vorschlaege": ["Eine ausgewogene Mahlzeit mit Eiweiß.",
                                     "Kurzer Spaziergang am Abend.", "Genug trinken.", "extra"]})}}
        return _R()
    with _client(tmp_path, http_post=fake_post) as c:
        d = c.post("/api/vorschlaege/ki").json()
        assert d["quelle"] == "lokale_ki" and len(d["vorschlaege"]) == 3
        assert "Diagnose" in d["disclaimer"]


# ===================== Wearables: BLE lokal + Ingest (Gesetz 5 scharf) =========
def test_parse_heart_rate_uint8_und_uint16():
    assert parse_heart_rate(bytes([0x00, 62])) == 62          # Flags Bit0=0 ⇒ uint8
    assert parse_heart_rate(bytes([0x01, 0x2C, 0x01])) == 300  # Bit0=1 ⇒ uint16 LE
    assert parse_heart_rate(b"") is None


def test_ble_scan_und_lesen_ohne_hardware():
    # Fake-Scanner + Fake-Client ⇒ der BLE-Pfad ist ohne Stack/Hardware testbar.
    class _Dev:
        def __init__(self, a, n, r): self.address, self.name, self.rssi = a, n, r

    class _Scanner:
        @staticmethod
        async def discover(timeout=5.0):
            return [_Dev("AA:BB:CC:DD", "Polar H10", -55)]

    geraete = asyncio.run(ble_scan(scanner=_Scanner))
    assert geraete and geraete[0]["address"] == "AA:BB:CC:DD" and "Polar" in geraete[0]["name"]

    class _Client:                       # ohne __aenter__ ⇒ Nicht-Context-Pfad
        def __init__(self, addr): self.addr = addr
        async def start_notify(self, char, cb):
            cb(0, bytearray([0x00, 62])); cb(0, bytearray([0x00, 65]))
        async def stop_notify(self, char): pass

    async def _nosleep(_s): return None
    proben = asyncio.run(ble_lesen("AA:BB:CC:DD", "heart_rate", 0.1,
                                   client_factory=_Client, sleep=_nosleep))
    assert len(proben) == 2 and all(p.art == "puls" and p.quelle == "ble" for p in proben)
    assert [int(p.wert) for p in proben] == [62, 65]
    # glucose ist angebunden, aber ehrlich noch ohne Frame-Parser
    with pytest.raises(QuelleNichtVerbunden):
        asyncio.run(ble_lesen("AA:BB", "glucose", 0.1, client_factory=_Client, sleep=_nosleep))


def test_gatt_frame_parser_ieee11073():
    # Heart Rate: uint8 / uint16 (oben schon); hier Temp/Gewicht/Blutdruck (IEEE-11073).
    # Temperatur 36.5 °C: FLOAT 32-bit = Mantisse 365 * 10^-1, Flags=0 (Celsius).
    temp = bytes([0x00]) + (365).to_bytes(3, "little") + bytes([0xFF])  # exp -1 = 0xFF
    assert parse_temperature(temp) == 36.5
    # Fahrenheit-Flag (Bit0=1): 98.6 °F = 37.0 °C. 986 * 10^-1 °F.
    tf = bytes([0x01]) + (986).to_bytes(3, "little") + bytes([0xFF])
    assert parse_temperature(tf) == 37.0
    # Gewicht SI: uint16 * 0.005 kg ⇒ 15640 * 0.005 = 78.2 kg.
    assert parse_weight(bytes([0x00]) + (15640).to_bytes(2, "little")) == 78.2
    # Blutdruck systolisch: SFLOAT 120 (Mantisse 120, Exp 0) mmHg.
    assert parse_blood_pressure(bytes([0x00]) + (120).to_bytes(2, "little") + b"\x00\x00\x00\x00") == 120
    # ble_lesen mit weight-Profil ⇒ Probe art=gewicht
    class _C:
        def __init__(self, a): pass
        async def start_notify(self, ch, cb): cb(0, bytearray(bytes([0x00]) + (15000).to_bytes(2, "little")))
        async def stop_notify(self, ch): pass
    async def _ns(_s): return None
    pr = asyncio.run(ble_lesen("X", "weight", 0.1, client_factory=_C, sleep=_ns))
    assert len(pr) == 1 and pr[0].art == "gewicht" and pr[0].wert == 75.0


def test_samples_ingest_dedupe_und_validierung(tmp_path):
    with _client(tmp_path) as c:
        body = {"samples": [
            {"art": "puls", "wert": 60, "quelle": "ble", "extern_id": "x1",
             "gemessen_am": "2026-06-26T08:00"},
            {"art": "schritte", "wert": 3000, "quelle": "apple_health", "extern_id": "s1",
             "gemessen_am": "2026-06-26T09:00"},
            {"art": "unbekannt", "wert": 1, "extern_id": "u1"},   # unbekannte Art ⇒ skip
        ]}
        d = c.post("/api/samples/ingest", json=body).json()
        assert d["geschrieben"] == 2 and d["uebersprungen"] == 1
        # gleiche extern_id erneut ⇒ Dedupe (übersprungen, kein Doppel)
        d2 = c.post("/api/samples/ingest", json={"samples": [body["samples"][0]]}).json()
        assert d2["geschrieben"] == 0 and d2["uebersprungen"] == 1
        # gelandet als Messwert (lokal)
        puls = c.get("/api/messwerte?art=puls").json()
        assert any(m["wert"] == 60 and m["quelle"] == "ble" for m in puls)


def test_ble_scan_endpoint_ohne_stack(tmp_path):
    # Im Test-venv ist `bleak` nicht installiert ⇒ Endpunkt antwortet ehrlich.
    with _client(tmp_path) as c:
        d = c.get("/api/ble/scan").json()
        assert d["verfuegbar"] == ble_stack_verfuegbar()        # False ohne Stack
        if not d["verfuegbar"]:
            assert "bleak" in d["hinweis"]
