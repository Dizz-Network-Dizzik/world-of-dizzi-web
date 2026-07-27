"""Posteingang-Suche (Kern-Muss „suchen"): Mehrwort-UND über Betreff/Absender/
Empfänger/Text, lokal (LIKE+ESCAPE), Filter Konto/ungelesen, ESCAPE-Sicherheit."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


def _m(betreff, mid, von="alice@example.org", text="Inhalt", an="dizzi@local"):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": an, "betreff": betreff, "text": text,
            "gesendet_at": "2026-06-12", "thread_schluessel": mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([_m("Rechnung Stadtwerke", "<a@x>",
                        text="Bitte die Rechnung bis Freitag zahlen."),
                     _m("Urlaubsfotos", "<b@x>", von="Bob <bob@example.org>",
                        text="Anbei die Bilder vom Strand."),
                     _m("Projekt Alpha", "<c@x>", von="chef@firma.de",
                        text="Status zur Rechnung im Projekt.")],
                    OrdnerZustand(4, 5))
        return ([], zustand)


def _client(tmp_path):
    return TestClient(build_app(
        data_dir=tmp_path, quelle_factory=lambda konto, geheimnis: FakeQuelle()))


def _sync(client):
    kid = client.post("/api/konten", json={
        "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
    client.post("/api/sync", json={"konto_id": kid})
    return kid


def test_suche_felder_und_treffer(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        # Betreff-Treffer
        r = client.get("/api/suche?q=urlaubsfotos").json()
        assert [m["betreff"] for m in r] == ["Urlaubsfotos"]
        # Volltext-Treffer (Wort nur im Body) + Absender-Treffer
        assert {m["betreff"] for m in client.get("/api/suche?q=strand").json()} == {"Urlaubsfotos"}
        assert {m["betreff"] for m in client.get("/api/suche?q=bob@example.org").json()} == {"Urlaubsfotos"}
        # „rechnung" steht in 2 Nachrichten (Betreff bzw. Text)
        assert len(client.get("/api/suche?q=rechnung").json()) == 2
        # Treffer trägt konversation_id (UI öffnet damit den Thread) + Snippet
        eintrag = client.get("/api/suche?q=stadtwerke").json()[0]
        assert eintrag["konversation_id"] and "Freitag" in eintrag["snippet"]


def test_suche_mehrwort_und_und_leer(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        # UND: beide Begriffe müssen vorkommen (hier: Betreff + Body derselben Mail)
        assert {m["betreff"] for m in client.get("/api/suche?q=projekt rechnung").json()} == {"Projekt Alpha"}
        assert client.get("/api/suche?q=projekt urlaub").json() == []   # kein gemeinsamer Treffer
        assert client.get("/api/suche?q=").json() == []                 # leere Anfrage


def test_suche_escape_und_filter(tmp_path):
    with _client(tmp_path) as client:
        _sync(client)
        # LIKE-Wildcards im Begriff dürfen NICHT alles matchen (ESCAPE wirkt)
        assert client.get("/api/suche?q=%").json() == []
        assert client.get("/api/suche?q=_").json() == []
        # Konto-Filter + nur_ungelesen
        kid = client.get("/api/konten").json()[0]["id"]
        assert len(client.get(f"/api/suche?q=rechnung&konto_id={kid}").json()) == 2
        assert client.get(f"/api/suche?q=rechnung&konto_id=fehlt").json() == []
        assert len(client.get("/api/suche?q=rechnung&nur_ungelesen=true").json()) == 2


def test_suche_operator_von(tmp_path):
    """P3 (Superhuman-Stil): ``von:<x>`` schränkt auf den Absender ein,
    kombinierbar mit Volltext (UND)."""
    with _client(tmp_path) as client:
        _sync(client)
        assert {m["betreff"] for m in
                client.get("/api/suche", params={"q": "von:bob"}).json()} == {"Urlaubsfotos"}
        # von: + Volltext = UND (Bob hat kein „rechnung")
        assert client.get("/api/suche", params={"q": "von:bob rechnung"}).json() == []
        assert {m["betreff"] for m in
                client.get("/api/suche", params={"q": "von:chef projekt"}).json()} == {"Projekt Alpha"}


def test_ui_suche_marker(tmp_path):
    with TestClient(build_app(data_dir=tmp_path)) as client:
        html = client.get("/").text
        for marker in ('id="f-suche"', 'function ladeSuche', '/api/suche?'):
            assert marker in html, marker
