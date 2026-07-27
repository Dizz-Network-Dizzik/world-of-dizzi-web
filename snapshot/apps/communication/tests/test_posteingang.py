"""Teil B — Posteingang-Tiefe: Konversations-Liste (Zähler/letzter Absender),
Thread-Detail (chronologisch), Lesen/als-gelesen, Filter (Konto/Ordner/
ungelesen), Kontakte-Klammer (aus Absendern aufgebaut)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


def _mail(betreff, mid, schluessel=None, von="alice@example.org"):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": "dizzi@local", "betreff": betreff,
            "text": "Inhalt " + betreff, "gesendet_at": "2026-06-12",
            "thread_schluessel": schluessel or mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:             # 3 Mails, 2 Threads, 3 Absender
            return ([_mail("Projekt", "<a@x>"),
                     _mail("Re: Projekt", "<b@x>", schluessel="<a@x>",
                           von="Bob <bob@example.org>"),
                     _mail("Anderes", "<c@x>", von="carol@example.org")],
                    OrdnerZustand(3, 4))
        return ([], zustand)


def _client(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    return TestClient(app)


def _sync(client):
    kid = client.post("/api/konten", json={
        "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
    client.post("/api/sync", json={"konto_id": kid})
    return kid


def _projekt_id(client):
    konvs = client.get("/api/konversationen").json()
    return next(k["id"] for k in konvs if k["titel"] == "Projekt")


def test_konversationsliste_zaehler_und_letzter_absender(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        konvs = {k["titel"]: k for k in client.get("/api/konversationen").json()}
        assert set(konvs) == {"Projekt", "Anderes"}
        assert konvs["Projekt"]["nachrichten"] == 2
        assert konvs["Projekt"]["ungelesen"] == 2
        assert "bob@example.org" in konvs["Projekt"]["letzter_von"]   # jüngste Mail
        assert konvs["Anderes"]["nachrichten"] == 1


def test_konversation_letzte_ist_juengste_nachricht(tmp_path):
    """Regression: ``letzte``/``letzter_von`` kommen aus der JÜNGSTEN Nachricht
    (per rowid), NICHT aus MAX(gesendet_at) — rohe RFC-Datumsstrings sortieren
    lexikografisch ('Wed…' > 'Mon…') und würden den falschen wählen."""
    class Quelle(KanalQuelle):
        art = "fake"

        def hole_neue(self, ordner, zustand):
            if zustand.uidnext == 0:
                return ([{"kanal_typ": "email", "extern_id": "<a@x>",
                          "von_adresse": "alt@example.org", "an_adressen": "d",
                          "betreff": "Start", "text": "x",
                          "gesendet_at": "Wed, 31 Dec 2025 23:59:00",
                          "thread_schluessel": "<a@x>"},
                         {"kanal_typ": "email", "extern_id": "<b@x>",
                          "von_adresse": "neu@example.org", "an_adressen": "d",
                          "betreff": "Re: Start", "text": "y",
                          "gesendet_at": "Mon, 06 Jan 2026 08:00:00",
                          "thread_schluessel": "<a@x>"}], OrdnerZustand(3, 4))
            return ([], zustand)

    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: Quelle())
    with TestClient(app) as client:
        kid = client.post("/api/konten", json={
            "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
        client.post("/api/sync", json={"konto_id": kid})
        konv = client.get("/api/konversationen").json()[0]
        assert konv["letzte"] == "Mon, 06 Jan 2026 08:00:00"   # jüngste, nicht MAX
        assert "neu@example.org" in konv["letzter_von"]


def test_thread_detail_chronologisch(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        pid = _projekt_id(client)
        detail = client.get(f"/api/konversationen/{pid}").json()
        assert detail["konversation"]["titel"] == "Projekt"
        # älteste zuerst (Wurzel vor Antwort)
        assert [n["betreff"] for n in detail["nachrichten"]] == [
            "Projekt", "Re: Projekt"]
        assert all(n["gelesen"] == 0 for n in detail["nachrichten"])
        assert client.get("/api/konversationen/fehlt").status_code == 404


def test_als_gelesen_markieren_wirkt_auf_zaehler(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        pid = _projekt_id(client)
        r = client.post(f"/api/konversationen/{pid}/gelesen",
                        json={"gelesen": True}).json()
        assert r == {"ok": True, "geaendert": 2, "gelesen": True}
        konvs = {k["titel"]: k for k in client.get("/api/konversationen").json()}
        assert konvs["Projekt"]["ungelesen"] == 0
        # Kachel: noch 1 ungelesen (die „Anderes"-Mail)
        kpis = {k["id"]: k["value"] for k in client.get("/api/summary").json()["kpis"]}
        assert kpis["ungelesen"] == 1
        # wieder auf ungelesen
        client.post(f"/api/konversationen/{pid}/gelesen", json={"gelesen": False})
        assert {k["titel"]: k for k in client.get("/api/konversationen").json()
                }["Projekt"]["ungelesen"] == 2
        assert client.post("/api/konversationen/fehlt/gelesen",
                           json={"gelesen": True}).status_code == 404


def test_filter_ungelesen_und_ordner(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        assert len(client.get("/api/posteingang?nur_ungelesen=true").json()) == 3
        assert len(client.get("/api/posteingang?ordner=INBOX").json()) == 3
        assert client.get("/api/posteingang?ordner=Gesendet").json() == []
        # Konversations-Filter ungelesen: beide Threads haben Ungelesene
        assert len(client.get("/api/konversationen?nur_ungelesen=true").json()) == 2
        pid = _projekt_id(client)
        client.post(f"/api/konversationen/{pid}/gelesen", json={"gelesen": True})
        rest = client.get("/api/posteingang?nur_ungelesen=true").json()
        assert {m["betreff"] for m in rest} == {"Anderes"}
        assert len(client.get("/api/konversationen?nur_ungelesen=true").json()) == 1


def test_sektion_heuristik():
    """P1b: deterministische Sektion aus der Absender-Adresse (Spark-Muster)."""
    from kommapp.main import sektion_aus_absender as s
    assert s("newsletter@shop.de") == "newsletter"
    assert s("Acme <no-reply@acme.com>") == "newsletter"
    assert s("notifications@github.com") == "benachrichtigung"
    assert s("alerts@bank.de") == "benachrichtigung"
    assert s("alice@example.org") == "wichtig"
    assert s("") == "wichtig"


def test_konversationen_tragen_sektion(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        konvs = client.get("/api/konversationen").json()
        assert konvs and all("sektion" in k for k in konvs)
        assert {k["sektion"] for k in konvs} <= {
            "wichtig", "benachrichtigung", "newsletter"}


def test_snooze_blendet_aus_und_weckt(tmp_path):
    """P2-Snooze: geschlummerte Konversation verschwindet aus dem Posteingang,
    erscheint in der geschlummert-Sicht und kommt nach Aufwecken/Ablauf zurück."""
    with _client(tmp_path) as client:
        _sync(client)
        konvs = client.get("/api/konversationen").json()
        n0 = len(konvs); kid = konvs[0]["id"]
        assert client.post(f"/api/konversationen/{kid}/schlummern",
                           json={"bis": "2999-01-01T00:00"}).json()["ok"] is True
        rest = client.get("/api/konversationen").json()
        assert all(k["id"] != kid for k in rest) and len(rest) == n0 - 1
        geschl = client.get("/api/konversationen?geschlummert=true").json()
        g = next(k for k in geschl if k["id"] == kid)
        assert g["schlummern_bis"] == "2999-01-01T00:00"
        # aufwecken (leeres bis)
        client.post(f"/api/konversationen/{kid}/schlummern", json={"bis": ""})
        assert any(k["id"] == kid for k in client.get("/api/konversationen").json())
        # vergangene Schlummerzeit ⇒ wieder sichtbar
        client.post(f"/api/konversationen/{kid}/schlummern", json={"bis": "2000-01-01T00:00"})
        assert any(k["id"] == kid for k in client.get("/api/konversationen").json())
        assert client.post("/api/konversationen/fehlt/schlummern",
                           json={"bis": ""}).status_code == 404


def test_labels_zuweisen_filtern_entfernen(tmp_path):
    """P2-Labels: Label anlegen+zuweisen, am Listing/an der Konversation sichtbar,
    nach Label filtern, entfernen; name Pflicht + 404."""
    with _client(tmp_path) as client:
        _sync(client)
        kid = client.get("/api/konversationen").json()[0]["id"]
        r = client.post(f"/api/konversationen/{kid}/labels",
                        json={"name": "Projekt", "farbe": "mg"}).json()
        assert r["ok"] and r["name"] == "Projekt" and r["farbe"] == "mg"
        lid = r["id"]
        assert any(l["name"] == "Projekt" for l in client.get("/api/labels").json())
        assert [l["name"] for l in
                client.get(f"/api/konversationen/{kid}/labels").json()] == ["Projekt"]
        konv = next(k for k in client.get("/api/konversationen").json() if k["id"] == kid)
        assert any(l["name"] == "Projekt" for l in konv["labels"])
        assert any(k["id"] == kid
                   for k in client.get("/api/konversationen?label=Projekt").json())
        assert client.get("/api/konversationen?label=Unbekannt").json() == []
        assert client.delete(f"/api/konversationen/{kid}/labels/{lid}").json()["entfernt"] == 1
        assert client.get(f"/api/konversationen/{kid}/labels").json() == []
        assert client.post(f"/api/konversationen/{kid}/labels",
                           json={"name": ""}).status_code == 400
        assert client.post("/api/konversationen/fehlt/labels",
                           json={"name": "X"}).status_code == 404


def test_ui_posteingang_tiefe_marker(tmp_path):
    """Die Seite trägt die Teil-B-Bausteine: Filterleiste, Konversations-/
    Thread-Render, Kontakte-Karte."""
    with _client(tmp_path) as client:
        html = client.get("/").text
        for marker in ('id="konvliste"', 'id="thread"', 'function oeffneThread',
                       'function ladeKontakte', 'id="kontakte"', 'id="f-ungelesen"',
                       '/api/konversationen/', 'id="f-geschlummert"',
                       'function schlummernForm', '/schlummern',
                       'function renderLabels', 'id="thread-labels"', 'class="lbl'):
            assert marker in html, marker


def test_kontakte_klammer_aus_absendern(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        kontakte = {k["adresse"]: k for k in client.get("/api/kontakte").json()}
        assert set(kontakte) == {"alice@example.org", "bob@example.org",
                                 "carol@example.org"}
        assert kontakte["bob@example.org"]["name"] == "Bob"      # Display-Name
        assert all(k["kanal_typ"] == "email" for k in kontakte.values())
        assert all(k["nachrichten"] >= 1 for k in kontakte.values())
        # zweiter Sync legt KEINE Dubletten an (Dedupe über die Adresse)
        kid = client.get("/api/konten").json()[0]["id"]
        client.post("/api/sync", json={"konto_id": kid})
        assert len(client.get("/api/kontakte").json()) == 3
