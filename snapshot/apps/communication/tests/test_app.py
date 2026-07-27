"""End-to-End: Konto→Tresor, Sync→kanal-agnostisches Schema (Threading,
Dedupe), HITL-Gate fürs Senden, hoechst-Defaults, Vertrag."""

from __future__ import annotations

from fastapi.testclient import TestClient

from appkit import conformance
from kommapp.main import APP_ID, build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


def _mail(betreff, mid, schluessel=None, von="alice@example.org"):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": "dizzi@local", "betreff": betreff, "text": "Inhalt",
            "gesendet_at": "2026-06-12", "thread_schluessel": schluessel or mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:         # erster Lauf: 3 Mails, 2 Threads
            return ([_mail("Projekt", "<a@x>"),
                     _mail("Re: Projekt", "<b@x>", schluessel="<a@x>"),
                     _mail("Anderes", "<c@x>")], OrdnerZustand(3, 4))
        return ([], zustand)


def _factory_bauen(erwartetes_geheimnis):
    def factory(konto, geheimnis):
        assert geheimnis == erwartetes_geheimnis    # kam aus dem Tresor
        return FakeQuelle()
    return factory


def test_vertrag_konform(tmp_path):
    app = build_app(data_dir=tmp_path)
    with TestClient(app) as client:
        conformance.check_contract(client, APP_ID)
        assert client.get("/auth/me").json() == {"angemeldet": False,
                                                 "level": "lokal"}


def test_hoechst_defaults(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        settings = client.get("/api/settings").json()
        assert settings["ki_routing"] == "lokal_only"   # hoechst ⇒ nie Cloud
        assert settings["ki_triage_aktiv"] is False


def test_vorbereitete_kanal_slots(tmp_path):
    """Gesetz 5: die Zwei-Schienen-Anschlüsse existieren als MARKIERTE,
    funktionslose Slots (Default aus/leer) und sind in der Kategorie
    'vernetzung' sichtbar — Bewusstsein über die Vorbereitung."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        vals = client.get("/api/settings").json()
        for key in ("webview_schiene_vorbereitet", "bridge_whatsapp_vorbereitet",
                    "bridge_signal_vorbereitet", "bridge_telegram_vorbereitet"):
            assert vals[key] is False
        assert vals["matrix_homeserver"] == ""
        schema = client.get("/api/settings/schema").json()
        vernetzung = {d["key"] for d in schema["kategorien"]["vernetzung"]}
        assert {"webview_schiene_vorbereitet", "matrix_homeserver",
                "bridge_telegram_vorbereitet"} <= vernetzung
        # Slot ist echt setzbar (validiert), bleibt aber ohne Backend-Wirkung.
        assert client.put("/api/settings", json={
            "key": "bridge_signal_vorbereitet", "value": True}).status_code == 200


def test_jitsi_video_v1(tmp_path):
    """Jitsi-Video v1: Server-Domain als Setting (self-host-fähig), UI bettet
    on-demand ein (kein Auto-Load, kein Runtime-CDN-Script)."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        vals = client.get("/api/settings").json()
        assert vals["jitsi_domain"] == "meet.jit.si"   # öffentliche Default-Instanz
        schema = client.get("/api/settings/schema").json()
        assert "jitsi_domain" in {d["key"] for d in schema["kategorien"]["vernetzung"]}
        # self-hosted Domain ist setzbar
        assert client.put("/api/settings", json={
            "key": "jitsi_domain", "value": "meet.example.org"}).status_code == 200
        html = client.get("/").text
        for marker in ('id="jitsi-raum"', 'function videoBeitreten',
                       'id="jitsi-frame"', 'ladeVideoKonfig',
                       'function videoFuerThread', 'JMAP (vorbereitet)'):
            assert marker in html, marker


def test_ui_k2_4_controls_und_collapse(tmp_path):
    """K2.4-(b): native Controls durch die .dz-Familie ersetzt + große Panels
    einklappbar (dz-panel), tokenbasiert + collapse.js eingehängt. Native
    Texteingaben (Passwort/Textarea) bleiben erhalten (Zugänglichkeit)."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        # Controls/Collapse-Markup im HTML
        for marker in ('class="dz-select"', 'class="dz-field"', 'class="dz-check"',
                       'data-dz-collapsible', 'dz-panel-kopf', 'dz-panel-kurz',
                       'data-dz-step', 'DzControls'):
            assert marker in html, marker
        # Konvergenz 18.06.: collapse.js + K2.4-Komponenten-Tokens liegen im VERLINKTEN Kit
        assert '/ui-kit/collapse.js' in html
        assert 'initControls' in client.get('/ui-kit/collapse.js').text
        tokens = client.get('/ui-kit/tokens.css').text
        assert '--control-akzent' in tokens and '--panel-kurz' in tokens
        # Posteingang + Kontakte = einklappbare Panels mit Kurzanzeige-Slot
        assert 'id="posteingang-kurz"' in html and 'id="kontakte-kurz"' in html
        # native Eingaben bleiben (Zugänglichkeit): Passwort-Feld + Textarea (Compose)
        assert 'type="password"' in html and "<textarea" in html


def test_ui_command_palette_und_verknuepfungs_chip(tmp_path):
    """P1: Command-Palette (Cmd/Strg+K) + tokenisierter Verknüpfungs-Chip als
    feste Thread-Aktionsleiste (V4/V5 sichtbar)."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in ('id="cmdk"', 'id="cmdk-input"', 'function openPalette',
                       'function paletteRender', 'ctrlKey', "e.key==='k'",
                       'function renderChipbar', 'class="chipbar"', 'dz-chip',
                       '/verknuepfungen'):
            assert marker in html, marker


def test_ui_drei_spalten_und_thread_zusammenfassung(tmp_path):
    """P1c: Drei-Spalten-Arbeitsfläche (Liste│Thread│Lesen) + Lesebereich +
    KI-Thread-Zusammenfassung + Tastatur-Navigation (j/k/Enter)."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in ('class="mail3"', 'id="konvliste"', 'id="thread"', 'id="lesen"',
                       'mail3-read', 'function zeigeNachricht', 'function msgRow',
                       'function konvNav', "e.key==='j'", 'thread-summary',
                       '/zusammenfassung', 'function threadZusammenfassung',
                       'id="f-split"', 'function toggleSplit', 'sek-kopf',
                       'Tracking-Pixel blockiert'):
            assert marker in html, marker
        # Privacy-Vorbereitung (Gesetz 5): Screener-Slot im Schema (Kategorie sicherheit)
        schema = client.get("/api/settings/schema").json()
        assert "absender_screener_vorbereitet" in {
            d["key"] for d in schema["kategorien"]["sicherheit"]}


def test_konto_sync_threading_dedupe(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=_factory_bauen("geheim-123"))
    with TestClient(app) as client:
        r = client.post("/api/konten", json={
            "name": "Privat", "host": "imap.example.org",
            "benutzer": "dizzi@example.org", "geheimnis": "geheim-123"}).json()
        kid = r["id"]
        # Geheimnis NUR im Tresor, nie in der Konten-Antwort
        assert client.get("/api/vault").json() == [f"konto_{kid}"]
        assert "geheimnis" not in client.get("/api/konten").json()[0]

        s1 = client.post("/api/sync", json={"konto_id": kid}).json()
        assert s1 == {"geholt": 3, "neu": 3, "uidnext": 4}
        # Threading: Antwort hängt an der Wurzel ⇒ 2 Konversationen
        konvs = client.get("/api/konversationen").json()
        assert {k["titel"]: k["nachrichten"] for k in konvs} == {
            "Projekt": 2, "Anderes": 1}
        # zweiter Lauf: Zustand persistiert ⇒ nichts Neues, nichts doppelt
        s2 = client.post("/api/sync", json={"konto_id": kid}).json()
        assert s2["geholt"] == 0 and s2["neu"] == 0
        assert len(client.get("/api/posteingang").json()) == 3

        assert client.post("/api/sync",
                           json={"konto_id": "fehlt"}).status_code == 404


def test_senden_ist_hitl_und_fail_closed(tmp_path):
    """Die EINZIGE Außenwirkung (Senden) verlangt Stufe 'verifiziert' —
    standalone (lokal) wird die Freigabe verweigert: K4 hält."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        katalog = {a["name"]: a["level"]
                   for a in client.get("/api/actions").json()["katalog"]}
        # Domänen-Aktion + die Dizz-Defense-Aktionen aus dem Vertrag 1.4:
        assert katalog["mail_senden"] == "verifiziert"
        assert {"defense_lockdown", "defense_notaus"} <= set(katalog)
        vorschlag = client.post("/api/actions/propose", json={
            "name": "mail_senden",
            "params": {"konto_id": "x", "an": "ziel@example.org"}}).json()
        r = client.post(f"/api/actions/{vorschlag['id']}/approve")
        assert r.status_code == 403
        assert "verifiziert" in r.json()["error"]


def test_ui_und_gmail_start(tmp_path, monkeypatch):
    monkeypatch.delenv("DIZZI_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIZZI_GOOGLE_CLIENT_SECRET", raising=False)
    with TestClient(build_app(data_dir=tmp_path)) as client:
        r = client.get("/")
        assert r.status_code == 200 and "Dizz Communication" in r.text
        # Gmail-Start ohne konfigurierten Google-Client ⇒ ehrliche 409
        r = client.get("/api/konten/gmail/start", follow_redirects=False)
        assert r.status_code == 409 and "DIZZI_GOOGLE_CLIENT_ID" in r.json()["error"]
        # Callback ohne gestarteten Flow ⇒ 400
        assert client.get("/api/konten/gmail/callback?code=x&state=y",
                          follow_redirects=False).status_code == 400


def test_ui_rollout_tokenbasiert(tmp_path):
    """R-Rollout (Teil A): die Seite trägt die News-Muster-Bausteine —
    Zwei-Achsen-Tokens, #kontoModal mit Gotcha-1-Regel, schwebende Knöpfe +
    Float-Treiber, Mini-Dizzi-Sprechblase auf /api/ki/frage."""
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in ('data-design="metall"', 'data-farbe="cyan-magenta"',
                       'id="kontoModal"', '.kmwrap[hidden]{display:none!important}',
                       'id="floatAcct"', 'id="floatDizzi"',
                       'id="dizziBubble"', "/api/ki/frage", "/api/settings/schema"):
            assert marker in html, marker
        # Spin/Float-Mechanik liegt im VERLINKTEN geteilten Kit (Konvergenz 18.06.):
        assert "/ui-kit/floats.js" in html and "DizzFloats" in html
        assert "initFloat" in client.get("/ui-kit/floats.js").text
        # KEINE hartkodierten Hex-Farben in den Karten — alles über Tokens.
        assert "var(--panel)" in html
        assert "--cy-rgb" in client.get("/ui-kit/tokens.css").text


def test_konto_entfernen_wiped_tresor(tmp_path):
    """Konto trennen (DELETE): Zeile soft-deleted UND Geheimnis aus dem Tresor —
    kein orphaned Konto (Footgun-Schutz)."""
    app = build_app(data_dir=tmp_path, quelle_factory=_factory_bauen("s3cret"))
    with TestClient(app) as client:
        kid = client.post("/api/konten", json={
            "name": "Weg", "host": "h", "benutzer": "u",
            "geheimnis": "s3cret"}).json()["id"]
        assert client.get("/api/vault").json() == [f"konto_{kid}"]
        assert client.delete(f"/api/konten/{kid}").json() == {"ok": True, "id": kid}
        assert client.get("/api/konten").json() == []      # weg aus der Liste
        assert client.get("/api/vault").json() == []        # Tresor geleert
        assert client.delete(f"/api/konten/{kid}").status_code == 404  # idempotent-ehrlich


def test_gmail_callback_legt_konto_an(tmp_path, monkeypatch):
    """Voller Gmail-Anschluss gegen Fake-Google: Refresh-Token in den Tresor,
    Konto art='gmail', Sync nutzt frisches Access-Token."""
    import kommapp.gmail as gm
    monkeypatch.setattr(gm, "client_aus_env", lambda root=None: ("cid", "sec"))

    import base64 as b64
    import json as js

    def fake_post(url, data):
        class A:
            status_code = 200

            def json(self):
                if data.get("grant_type") == "authorization_code":
                    payload = b64.urlsafe_b64encode(
                        js.dumps({"email": "nutzer@example.com"}).encode()).rstrip(b"=").decode()
                    return {"refresh_token": "r-tok", "access_token": "a-tok",
                            "id_token": f"k.{payload}.s"}
                return {"access_token": "frisch"}
        return A()

    erhaltene = {}

    def quelle_factory(konto, geheimnis):
        erhaltene.update(konto=dict(konto), geheimnis=geheimnis)
        return FakeQuelle()

    app = build_app(data_dir=tmp_path, http_post=fake_post,
                    quelle_factory=quelle_factory)
    with TestClient(app) as client:
        start = client.get("/api/konten/gmail/start", follow_redirects=False)
        assert start.status_code == 302 and "accounts.google.com" in start.headers["location"]
        from urllib.parse import parse_qs, urlsplit
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]

        cb = client.get(f"/api/konten/gmail/callback?code=c1&state={state}",
                        follow_redirects=False)
        assert cb.status_code == 302 and cb.headers["location"] == "/?gmail=ok"
        konten = client.get("/api/konten").json()
        assert konten[0]["art"] == "gmail" and konten[0]["benutzer"] == "nutzer@example.com"
        assert client.get("/api/vault").json() == [f"konto_{konten[0]['id']}"]

        s = client.post("/api/sync", json={"konto_id": konten[0]["id"]}).json()
        assert s["neu"] == 3
        # Die injizierte Factory bekam das TRESOR-Geheimnis (Refresh-Token)
        assert erhaltene["geheimnis"] == "r-tok"


def test_kachel(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=_factory_bauen("g"))
    with TestClient(app) as client:
        kid = client.post("/api/konten", json={
            "name": "K", "host": "h", "benutzer": "u",
            "geheimnis": "g"}).json()["id"]
        client.post("/api/sync", json={"konto_id": kid})
        kpis = {k["id"]: k["value"]
                for k in client.get("/api/summary").json()["kpis"]}
        # frisch gesyncte Nachrichten sind ungelesen (Default) ⇒ ungelesen == nachrichten
        assert kpis == {"konten": 1, "konversationen": 2,
                        "nachrichten": 3, "ungelesen": 3}
