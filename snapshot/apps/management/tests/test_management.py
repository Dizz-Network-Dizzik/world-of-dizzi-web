"""Tests Dizz Management [MG]: Vertrags-Konformität + Domäne (Kanäle/Social-Bots/
Posts/Zeitplan) + Creating-Empfang (idempotent, REV-3) + HITL-Veröffentlichung
(propose + fail-closed approve + dormant Handler) + ChannelSource-Adapter (dormant,
Gesetz 5) + KI-Frage/-Plan-Smoke + MCP-Namensraum + UI-Kit/Marken-Lockup +
SENSIBEL-Routing (lokal_only).

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from appkit import conformance
from managementapp import main as mm
from managementapp.channels import (PLATTFORMEN, BlueskySource, InstagramSource,
                                     KanalNichtVerbunden, OutboundPost,
                                     PostizSource, TikTokSource,
                                     UnifiedProviderSource, adapter_fuer,
                                     kanaele_status)


def _client(tmp_path, *, http_post=None, archiv_post=None) -> TestClient:
    kw = {}
    if http_post is not None:
        kw["http_post"] = http_post
    if archiv_post is not None:
        kw["archiv_post"] = archiv_post
    return TestClient(mm.build_app(data_dir=tmp_path, **kw))


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


def test_post_archivieren_an_memory(tmp_path):
    """V8 (docs/26): der „⇲ Memory"-Knopf schickt den Post explizit über den
    Core-Relay an Dizz Memory — Umschlag korrekt (app/strom/ref/explizit), Text +
    Hashtags im Body, Plattform als Tag, HEIKEL ⇒ sensibel."""
    archiv: list = []
    with _client(tmp_path, archiv_post=_archiv_capture(archiv)) as c:
        pid = c.post("/api/posts", json={
            "titel": "Sommer-Launch", "text": "Neue Kollektion ist da!",
            "plattform": "instagram", "hashtags": "#sommer #launch"}).json()["id"]

        r = c.post(f"/api/posts/{pid}/archivieren")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert archiv, "kein Archiv-Versuch"
        u = archiv[-1]["umschlag"]
        assert u["app"] == "management" and u["strom"] == "post_log"
        assert u["explizit"] is True and u["ref"] == "management:post:" + pid
        assert u["tags"] == ["instagram"]                 # Plattform als ein Tag
        assert u["sensibel"] is False
        assert u["titel"] == "Post · Sommer-Launch"
        assert "Neue Kollektion ist da!" in u["inhalt"] and "#sommer" in u["inhalt"]
        assert archiv[-1]["url"].endswith("/api/querverbindung/memory")
        # Audit-Beleg + unbekannter Post ⇒ 404
        assert "post_archiviert" in [e["action"] for e in c.get("/api/audit").json()]
        assert c.post("/api/posts/fehlt/archivieren").status_code == 404


# ===================== Vertrag =====================
def test_vertrag_konform(tmp_path):
    with _client(tmp_path) as c:
        conformance.check_contract(c, "management")
        # Dizzi-ID-Anschluss installiert; ohne Login = Standalone-Stufe 'lokal'.
        assert c.get("/auth/me").json() == {"angemeldet": False, "level": "lokal"}


def test_sensibel_routing_lokal_first(tmp_path):
    """SENSIBEL: Manifest sensitivity='hoch' ⇒ KI-Routing-Default lokal_only
    (lokal-first, nie Cloud/Boost). OAuth-Tokens + Außenwirkung (docs/RECHERCHE §5)."""
    with _client(tmp_path) as c:
        m = c.get("/api/manifest").json()
        assert m["sensitivity"] == "hoch" and m["port"] == 8213
        vals = c.get("/api/settings").json()
        assert vals["ki_routing"] == "lokal_only"


# ===================== Kanäle =====================
def test_kanal_crud_und_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert _kpis(c)["kanaele"] == 0
        kid = c.post("/api/kanaele",
                     json={"plattform": "tiktok", "handle": "@dizz"}).json()["id"]
        assert _kpis(c)["kanaele"] == 1
        liste = c.get("/api/kanaele?plattform=tiktok").json()
        assert len(liste) == 1 and liste[0]["status"] == "getrennt"
        # verbinden ⇒ Status-Zähler in stats
        c.patch(f"/api/kanaele/{kid}", json={"status": "verbunden"})
        assert c.get("/api/stats").json()["kanaele_verbunden"] == 1
        # unbekannte Plattform abgelehnt
        assert c.post("/api/kanaele", json={"plattform": "myspace"}).status_code == 400
        assert c.delete(f"/api/kanaele/{kid}").json()["ok"]
        assert c.get("/api/kanaele").json() == []
        assert "kanal_angelegt" in [e["action"] for e in c.get("/api/audit").json()]


# ===================== Social-Bots =====================
def test_bot_crud(tmp_path):
    with _client(tmp_path) as c:
        bid = c.post("/api/bots",
                     json={"name": "TechBot", "thema": "KI", "ton": "locker"}).json()["id"]
        assert _kpis(c)["bots"] == 1
        assert c.get("/api/bots?aktiv=1").json()[0]["name"] == "TechBot"
        # deaktivieren ⇒ raus aus aktiv
        c.patch(f"/api/bots/{bid}", json={"aktiv": False})
        assert _kpis(c)["bots"] == 0
        assert c.get("/api/bots?aktiv=0").json()[0]["aktiv"] is False
        assert c.delete(f"/api/bots/{bid}").json()["ok"]
        assert c.post("/api/bots", json={"name": "  "}).status_code == 400


# ===================== Posts + Zeitplan =====================
def test_post_crud_planen_und_zeitplan(tmp_path):
    with _client(tmp_path) as c:
        pid = c.post("/api/posts",
                     json={"titel": "Hallo Welt", "plattform": "instagram",
                           "text": "Erster Post"}).json()["id"]
        assert _kpis(c)["entwuerfe"] == 1
        # planen ⇒ status geplant + im Zeitplan. Datum DYNAMISCH in der Zukunft:
        # der „nächste Slot" zeigt nur kommende Termine — ein Fix-Datum wurde am
        # 01.07.2026 zur Zeitbombe (Fund Gesamtnetz-Sweep 03.07., App war korrekt).
        slot_tag = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        c.post(f"/api/posts/{pid}/planen",
               json={"geplant_fuer": f"{slot_tag}T18:00:00+00:00"})
        assert _kpis(c)["geplant"] == 1
        zp = c.get("/api/zeitplan").json()
        assert len(zp["geplant"]) == 1 and zp["geplant"][0]["titel"] == "Hallo Welt"
        # Kachel zeigt den nächsten Slot
        assert _kpis(c)["naechster_slot"].startswith(slot_tag)
        # unbekannte Plattform im Patch abgelehnt
        assert c.patch(f"/api/posts/{pid}", json={"plattform": "orkut"}).status_code == 400
        assert c.delete(f"/api/posts/{pid}").json()["ok"]


def test_post_mit_geplant_fuer_startet_geplant(tmp_path):
    with _client(tmp_path) as c:
        r = c.post("/api/posts", json={"titel": "X", "geplant_fuer": "2026-08-01T10:00"}).json()
        assert r["status"] == "geplant"


# ===================== Creating-Empfang (REV-3) =====================
def test_creating_empfang_derivate_und_idempotent(tmp_path):
    with _client(tmp_path) as c:
        # Kanal vorbereiten ⇒ tiktok-Derivat wird ihm zugeordnet
        c.post("/api/kanaele", json={"plattform": "tiktok", "handle": "@dizz"})
        payload = {
            "asset_id": "A1", "titel": "Clip", "pfad": "/dam/a1.mp4", "heikel": True,
            "text_vorschlag": "Schau dir das an", "hashtags": "#ki",
            "derivate": [
                {"zweck": "tiktok_9_16", "format": "9:16", "pfad": "/dam/a1_tt.mp4"},
                {"zweck": "yt_16_9", "format": "16:9", "pfad": "/dam/a1_yt.mp4"},
            ],
        }
        r1 = c.post("/api/creating/empfang", json=payload).json()
        assert len(r1["angelegt"]) == 2 and r1["uebersprungen"] == []
        # idempotent: derselbe Call legt nichts doppelt an
        r2 = c.post("/api/creating/empfang", json=payload).json()
        assert r2["angelegt"] == [] and len(r2["uebersprungen"]) == 2
        # Entwürfe tragen quelle='creating', HEIKEL-Flag, Herkunft + tiktok hat Kanal
        posts = c.get("/api/posts?quelle=creating").json()
        assert {p["plattform"] for p in posts} == {"tiktok", "youtube"}
        assert all(p["status"] == "entwurf" and p["heikel"] is True for p in posts)
        assert all(p["herkunft_asset_id"] == "A1" for p in posts)
        tt = next(p for p in posts if p["plattform"] == "tiktok")
        assert tt["kanal_id"]                       # dem bestehenden Kanal zugeordnet
        assert "creating_empfangen" in [e["action"] for e in c.get("/api/audit").json()]


def test_creating_empfang_fallback_plattformen(tmp_path):
    """Ohne Derivate: pro genannter Plattform ein Entwurf (Kanal-Derivat-Anlage)."""
    with _client(tmp_path) as c:
        r = c.post("/api/creating/empfang", json={
            "asset_id": "B2", "titel": "Bild", "pfad": "/dam/b2.png",
            "kanal_plattformen": ["instagram", "x"]}).json()
        assert len(r["angelegt"]) == 2
        assert {p["plattform"] for p in c.get("/api/posts?quelle=creating").json()} == {"instagram", "x"}


# ===================== HITL-Veröffentlichung (K4) =====================
def test_freigabe_anfordern_und_fail_closed(tmp_path):
    """Veröffentlichen = Außenwirkung: vorschlagen ist harmlos, approve verlangt
    Stufe 'verifiziert' ⇒ standalone fail-closed (403). Nie eigenmächtig."""
    with _client(tmp_path) as c:
        pid = c.post("/api/posts", json={"titel": "P", "plattform": "x"}).json()["id"]
        # Aktion ist im Katalog registriert
        kat = {a["name"]: a for a in c.get("/api/actions").json()["katalog"]}
        assert kat["post_veroeffentlichen"]["level"] == "verifiziert"
        # Freigabe anfordern ⇒ pending
        aid = c.post(f"/api/posts/{pid}/freigabe-anfordern").json()["id"]
        pend = c.get("/api/actions?status=pending").json()["liste"]
        assert any(a["id"] == aid for a in pend)
        # approve ohne verifizierte Verbindung ⇒ 403 (fail-closed)
        assert c.post(f"/api/actions/{aid}/approve").status_code == 403
        # ablehnen geht (lokal)
        assert c.post(f"/api/actions/{aid}/reject").json()["status"] == "rejected"


def test_publish_handler_dormant(tmp_path):
    """Der Handler hinter der HITL-Freigabe: v1 DORMANT ⇒ Freigabe gespeichert
    (status 'freigegeben'), echtes Posten bleibt aus (kein verbundener Kanal)."""
    with _client(tmp_path) as c:
        pid = c.post("/api/posts", json={"titel": "P", "plattform": "tiktok",
                                         "text": "hi"}).json()["id"]
        dom = c.app.state.domain
        res = dom._handle_veroeffentlichen({"post_id": pid})
        assert res["status"] == "freigegeben" and res["dormant"] is True
        assert c.get("/api/posts?status=freigegeben").json()[0]["id"] == pid
        assert "post_freigegeben_dormant" in [e["action"] for e in c.get("/api/audit").json()]


# ===================== ChannelSource-Adapter (dormant, Gesetz 5) =====================
def test_channel_adapter_dormant():
    # Direkte Plattform-Adapter: ohne Token nicht verbunden, ehrlicher Fehler
    for Src in (InstagramSource, TikTokSource, BlueskySource):
        a = Src(vault_get=lambda _n: None)
        assert a.verbunden() is False
        with pytest.raises(KanalNichtVerbunden):
            a.publish(OutboundPost(text="x"))
    # Token im Tresor ⇒ verbunden, aber Live-Posten v1 weiterhin dormant
    mit = InstagramSource(vault_get=lambda _n: "tok")
    assert mit.verbunden() is True and mit.status()["verbunden"] is True
    with pytest.raises(KanalNichtVerbunden):
        mit.publish(OutboundPost(text="x"))
    # Unified (Ayrshare) + Postiz: Tresor-gated, opt-in
    assert UnifiedProviderSource(vault_get=lambda _n: None).verbunden() is False
    assert PostizSource(vault_get=lambda _n: "k").verbunden() is True


def test_adapter_factory_und_registry():
    assert adapter_fuer("tiktok").plattform == "tiktok"
    assert adapter_fuer("ayrshare").plattform == "unified"
    assert adapter_fuer("postiz").plattform == "postiz"
    assert adapter_fuer("unbekannt") is None
    namen = {q["plattform"] for q in kanaele_status(vault_get=lambda _n: None)}
    assert set(PLATTFORMEN) <= namen and {"unified", "postiz"} <= namen


def test_kanal_quellen_endpoint_sichtbar(tmp_path):
    with _client(tmp_path) as c:
        q = c.get("/api/kanaele/quellen").json()["quellen"]
        assert len(q) == len(PLATTFORMEN) + 2          # direkte + Ayrshare + Postiz
        assert all(x["verbunden"] is False for x in q)  # v1 alle dormant
        assert all(x["posten_scharf"] is False for x in q)


# ===================== KI (App-KI-Slot + Plan, lokal) =====================
class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return {"message": {"content": json.dumps(self._payload)}}


def test_ki_frage_smoke(tmp_path):
    def fake_post(url, daten):                 # Signatur wie ki._post(url, daten)
        return _FakeResp({"antwort": "Du hast 1 Entwurf für Instagram."})
    with _client(tmp_path, http_post=fake_post) as c:
        c.post("/api/posts", json={"titel": "x", "plattform": "instagram"})
        r = c.post("/api/ki/frage", json={"frage": "Was steht an?"}).json()
        assert r["antwort"] == "Du hast 1 Entwurf für Instagram."
        assert r["quelle"] == "app_ki"


def test_ki_plan_smoke_und_hitl_hinweis(tmp_path):
    def fake_post(url, daten):
        return _FakeResp({"vorschlaege": ["Plane den Entwurf für 18 Uhr.",
                                          "Recycle das Video als Reel."]})
    with _client(tmp_path, http_post=fake_post) as c:
        r = c.post("/api/plan").json()
        assert r["vorschlaege"][0].startswith("Plane")
        assert r["quelle"] == "lokale_ki" and "Freigabe" in r["hinweis"]
        assert "plan_erstellt" in [e["action"] for e in c.get("/api/audit").json()]


def test_ki_pydantic_single_source_validierung(tmp_path):
    """P2.1: Schema = Pydantic-Modell (EINE Quelle für format= UND Validierung).
    Liefert das Modell schema-ungültiges JSON, fällt die KI ehrlich zurück
    (frage ⇒ leere Antwort/app_ki-Quelle vom Endpoint; plane ⇒ kein_ollama),
    statt Müll durchzureichen."""
    from managementapp import ki

    class _Resp:
        status_code = 200

        def __init__(self, content):
            self._c = content

        def json(self):
            return {"message": {"content": self._c}}

    # frage: 'antwort' fehlt ⇒ ValidationError ⇒ {"antwort": ""}
    bad = lambda url, daten: _Resp(json.dumps({"falsch": "feld"}))
    assert ki.frage({}, "Was steht an?", http_post=bad) == {"antwort": ""}
    # plane: schema-ungültig ⇒ ehrlicher kein_ollama-Fallback + HITL-Hinweis bleibt
    p = ki.plane({}, http_post=lambda url, daten: _Resp("kein json"))
    assert p["vorschlaege"] == [] and p["quelle"] == "kein_ollama" and "Freigabe" in p["hinweis"]
    # Gültiges Schema ⇒ Werte kommen durch (format=schema aus DEMSELBEN Modell)
    ok = lambda url, daten: _Resp(json.dumps({"vorschlaege": ["A", "  ", "B"]}))
    assert ki.plane({}, http_post=ok)["vorschlaege"] == ["A", "B"]   # leere getrimmt


# ===================== MCP-Namensraum =====================
def test_mcp_server_tools_namespaced(tmp_path):
    pytest.importorskip("fastmcp")
    from managementapp import mcp_server   # Import beweist: kein stdout-Schreiben
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"management_kachel_stats", "management_redaktionsplan",
            "management_kanal_status", "management_social_bots",
            "management_auswertung"} <= names
    assert "kachel_stats" not in names      # nackter Name kollidiert NICHT


# ===================== P2: Auswertung / Analytics / Heatmap =====================
def test_plattformen_zeichen_limits(tmp_path):
    """P2: /api/plattformen liefert die Zeichen-Limits (Single Source fürs Frontend)."""
    with _client(tmp_path) as c:
        cat = c.get("/api/plattformen").json()
        assert cat["zeichen_limits"]["x"] == 280 and cat["zeichen_limits"]["instagram"] == 2200
        assert cat["zeichen_limit_default"] == 2200


def test_analytics_und_heatmap(tmp_path):
    """P2: redaktionelle Auswertung aus dem eigenen Bestand — je Plattform, Status,
    Posting-Zeiten-Heatmap; Reichweite ist ein DORMANT-Slot (Gesetz 5)."""
    with _client(tmp_path) as c:
        # zwei Posts am selben Wochentag/Stunde (2026-07-07 + 07-14 = Dienstage 18:00)
        for tag in ("2026-07-07", "2026-07-14"):
            pid = c.post("/api/posts", json={"titel": "P", "plattform": "instagram"}).json()["id"]
            c.post(f"/api/posts/{pid}/planen", json={"geplant_fuer": tag + "T18:00:00+00:00"})
        c.post("/api/posts", json={"titel": "D", "plattform": "x"})        # Entwurf
        a = c.get("/api/analytics").json()
        # je Plattform
        plat = {p["plattform"]: p for p in a["je_plattform"]}
        assert plat["instagram"]["geplant"] == 2 and plat["x"]["entwurf"] == 1
        # Status-Verteilung
        assert a["status_verteilung"]["geplant"] == 2 and a["status_verteilung"]["entwurf"] == 1
        # Heatmap 7×24, Dienstag(1) 18 Uhr = 2
        assert len(a["heatmap"]) == 7 and len(a["heatmap"][0]) == 24
        assert a["heatmap"][1][18] == 2
        assert a["beste_zeiten"][0] == {"wochentag": 1, "stunde": 18, "label": "Di 18:00", "anzahl": 2}
        # Reichweite/Engagement DORMANT (kein Kanal verbunden)
        assert a["reichweite"]["verfuegbar"] is False and a["reichweite"]["verbundene_kanaele"] == 0


def test_auto_zeit_vorschlag(tmp_path):
    """P3 KI-Auto-Scheduling: Vorschlag = häufigste eigene Zeit; nächstes Auftreten in
    der Zukunft. REIN VORSCHLAG (HITL) — verändert keinen Post."""
    with _client(tmp_path) as c:
        # ohne Historie ⇒ Default Di 18:00
        leer = c.get("/api/auto-zeit").json()
        assert leer["wochentag"] == "Di" and leer["stunde"] == 18 and "Standard" in leer["basis"]
        # mit Historie (Donnerstag 09:00) ⇒ Vorschlag folgt der Historie
        for tag in ("2026-07-02", "2026-07-09"):     # Donnerstage
            pid = c.post("/api/posts", json={"titel": "P"}).json()["id"]
            c.post(f"/api/posts/{pid}/planen", json={"geplant_fuer": tag + "T09:00:00+00:00"})
        v = c.get("/api/auto-zeit").json()
        assert v["wochentag"] == "Do" and v["stunde"] == 9
        assert v["vorschlag"].endswith("T09:00:00+00:00")


def test_bulk_csv_import(tmp_path):
    """P3 Bulk-Import: CSV → nur Entwürfe (kein Posten); Kopfzeile erkannt; fehlerhafte
    Zeilen werden gemeldet statt still verworfen."""
    with _client(tmp_path) as c:
        csv = ("titel,text,plattform,hashtags,geplant_fuer\n"
               "Reel A,Hallo,instagram,#a,\n"
               "Tweet B,Hi,x,,2026-09-01T10:00\n"
               "Kaputt,X,myspace,,\n")
        r = c.post("/api/posts/bulk", json={"csv": csv}).json()
        assert len(r["angelegt"]) == 2 and len(r["fehler"]) == 1
        assert r["fehler"][0]["zeile"] == 4 and "myspace" in r["fehler"][0]["grund"]
        # angelegt sind ENTWÜRFE bzw. geplant; nichts veröffentlicht
        posts = c.get("/api/posts").json()
        assert {p["status"] for p in posts} <= {"entwurf", "geplant"}
        tweet = next(p for p in posts if p["titel"] == "Tweet B")
        assert tweet["status"] == "geplant" and tweet["plattform"] == "x"
        assert c.post("/api/posts/bulk", json={"csv": "   "}).status_code == 400


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
        assert 'class="dz-appkopf"' in html and 'class="dz-kopf-brand">Dizz Management' in html
        assert "<title>Dizz Management — Social Media</title>" in html
        assert "/api/ki/frage" in html                        # Mini-Dizzi verdrahtet
        assert "/api/creating/empfang" in html                # Creating-Eingang erklärt
        assert "/api/kanaele" in html and "/api/posts" in html


# ===================== Frontend P1: Netzwerk-Kit + Redaktion-Surface =====================
def test_frontend_p1_netkit_und_redaktion(tmp_path):
    """P1 UI/UX (docs/27 §8): geteiltes Netzwerk-Kit (DzNetKit) eingebunden, große
    Redaktion-Arbeitsfläche mit Ansicht-Umschalter (Kalender/Queue/Composer),
    Multi-Plattform-Composer mit Zeichen-Zähler + Verknüpfungs-Chips (Creating/Memory)."""
    with _client(tmp_path) as c:
        # Geteiltes Netzwerk-Kit wird same-origin ausgeliefert + verlinkt (EXTRAHIERBAR).
        nk_css = c.get("/ui-kit/netkit.css")
        nk_js = c.get("/ui-kit/netkit.js")
        assert nk_css.status_code == 200 and "dz-linkchip" in nk_css.text and "dz-viewswitch" in nk_css.text
        assert nk_js.status_code == 200 and "DzNetKit" in nk_js.text and "linkchip" in nk_js.text
        html = c.get("/").text
        assert "/ui-kit/netkit.css" in html and "/ui-kit/netkit.js" in html
        # Hybrid-Arbeitsfläche + Ansicht-Umschalter (Kalender/Queue/Composer)
        assert 'data-pkey="redaktion"' in html and "rk-switch" in html
        assert "viewSwitch" in html and "renderKalender" in html
        # Kalender mit Drag-Umplanen über /api/posts/{id}/planen
        assert "Monat" in html and "Woche" in html
        assert "replanPost" in html and "/planen" in html and "attachCalDnD" in html
        # Multi-Plattform-Composer: Zeichen-Zähler-Validierung (CHAR_LIMITS) + Instagram-Grid
        assert "CHAR_LIMITS" in html and "compPreview" in html and "ig-grid" in html
        # Queue mit sichtbarem HITL-Veröffentlich-Gate
        assert "renderQueue" in html and "q-gate" in html and "Veröffentlich-Gate" in html
        # Verknüpfungs-Chips: 📥 Creating-Lineage (REV-3) + ⇲ Memory (V8)
        assert "creatingLineage" in html and "ic-download" in html
        assert "postArchivieren" in html and "ic-archive" in html
        # Command-Palette aus dem geteilten Kit (Strg/Cmd+K)
        assert "initCmdPalette" in html and "cmdkCommands" in html


# ===================== Frontend P2/P3: Mini-Chart-Kit + Auswertung =====================
def test_frontend_p2_charts_und_auswertung(tmp_path):
    """P2/P3: Mini-Chart-Kit (DzCharts mit bar/donut/heatmap) eingebunden; Auswertung-
    Ansicht + KI-Auto-Scheduling + Bulk-CSV im Frontend verdrahtet."""
    with _client(tmp_path) as c:
        ch_css = c.get("/ui-kit/charts.css")
        ch_js = c.get("/ui-kit/charts.js")
        assert ch_css.status_code == 200 and "dz-heat-cell" in ch_css.text and "dz-bar-fill" in ch_css.text
        assert ch_js.status_code == 200 and "DzCharts" in ch_js.text
        # die drei im Management-Chat ergänzten Chart-Typen (Promotion-Kandidat)
        for fn in ("barChart", "donut", "heatmap"):
            assert fn in ch_js.text
        html = c.get("/").text
        assert "/ui-kit/charts.css" in html and "/ui-kit/charts.js" in html
        # Auswertung-Ansicht (4. View) + Renderer + Charts
        assert 'id="rk-auswertung"' in html and "renderAuswertung" in html
        assert "DzCharts.barChart" in html and "DzCharts.donut" in html and "DzCharts.heatmap" in html
        # KI-Auto-Scheduling (Best-Time übernehmen) + Bulk-CSV-Import + Bot-Viz
        assert "autoPlanen" in html and "/api/auto-zeit" in html and "Beste Zeit" in html
        assert "bulkImport" in html and "/api/posts/bulk" in html and "bulk-csv" in html
        assert "botviz" in html
        # Zeichen-Limits nicht mehr hartkodiert ⇒ aus dem Katalog
        assert "d.zeichen_limits" in html
