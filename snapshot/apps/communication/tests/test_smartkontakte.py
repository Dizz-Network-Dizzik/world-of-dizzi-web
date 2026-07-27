"""Paket D1 (2/4) — Smart Contacts: Kontakt-Unifikation über Kanäle (docs/35 §2/§5.3).

Ein kanonischer Kontakt bündelt mehrere Kanal-Identitäten. Getestet: die reine
Matching-Logik (kontakte.py) + die Pflege-Endpoints (Alias hinzufügen/umhängen/
entfernen, Merge, Split) + die kanonische Sicht /api/smartkontakte mit
Aktivitäts-Zählern, die den AKTUELLEN Aliassen folgen (Merge/Split = Aliasse
verschieben, Verlauf folgt automatisch)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp import kontakte
from kommapp.main import build_app
from kommapp.mail import KanalQuelle, OrdnerZustand


# ── Reine Matching-Logik ──────────────────────────────────────────────────────
def test_normalisiere_und_localpart():
    assert kontakte.normalisiere_name("  Max  Muster ") == "max muster"
    assert kontakte.local_part("Max.Muster@gmx.de") == "max.muster"
    assert kontakte.local_part("@maxmuster") == "maxmuster"
    assert kontakte.local_part("+49123") == "49123"


def test_vorschlag_gleicher_name():
    v = kontakte.finde_merge_vorschlaege([
        {"id": "1", "name": "Max Muster", "aliasse": [{"kanal_typ": "email", "adresse": "a@x"}]},
        {"id": "2", "name": "max muster", "aliasse": [{"kanal_typ": "telegram", "adresse": "@m"}]},
    ])
    assert len(v) == 1 and {v[0]["a"], v[0]["b"]} == {"1", "2"}
    assert v[0]["score"] == 3 and "Name" in v[0]["grund"]


def test_vorschlag_cross_channel_stamm():
    v = kontakte.finde_merge_vorschlaege([
        {"id": "1", "name": "A", "aliasse": [{"kanal_typ": "email", "adresse": "nutzer@example.com"}]},
        {"id": "2", "name": "B", "aliasse": [{"kanal_typ": "telegram", "adresse": "@maxi"}]},
    ])
    assert len(v) == 1 and v[0]["score"] == 2 and "Kanäle" in v[0]["grund"]


def test_vorschlag_dedupe_und_kein_selbstvorschlag():
    # ein Kontakt mit zwei gleich-stammigen Aliassen schlägt sich NICHT selbst vor
    v = kontakte.finde_merge_vorschlaege([
        {"id": "1", "name": "A", "aliasse": [
            {"kanal_typ": "email", "adresse": "max@x"},
            {"kanal_typ": "telegram", "adresse": "@max"}]},
    ])
    assert v == []


# ── Endpoints (über die App) ──────────────────────────────────────────────────
def _mail(betreff, mid, von):
    return {"kanal_typ": "email", "extern_id": mid, "von_adresse": von,
            "an_adressen": "dizzi@local", "betreff": betreff,
            "text": "Inhalt " + betreff, "gesendet_at": "2026-06-12",
            "thread_schluessel": mid}


class FakeQuelle(KanalQuelle):
    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([_mail("Projekt", "<a@x>", "alice@example.org"),
                     _mail("Hallo", "<b@x>", "Bob <bob@example.org>"),
                     _mail("Anderes", "<c@x>", "carol@example.org")],
                    OrdnerZustand(3, 4))
        return ([], zustand)


def _client_mit_sync(tmp_path):
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeQuelle())
    client = TestClient(app)
    kid = client.post("/api/konten", json={
        "name": "K", "host": "h", "benutzer": "u", "geheimnis": "g"}).json()["id"]
    client.post("/api/sync", json={"konto_id": kid})
    return client


def _by_name(client):
    return {k["name"]: k for k in client.get("/api/smartkontakte").json()}


def test_smartkontakte_grundsicht(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        ks = _by_name(client)
        assert set(ks) == {"alice@example.org", "Bob", "carol@example.org"}
        assert ks["Bob"]["kanaele"] == ["email"]
        assert ks["Bob"]["nachrichten"] == 1 and ks["Bob"]["ungelesen"] == 1


def test_alias_hinzufuegen_macht_kontakt_multikanal(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        alice = _by_name(client)["alice@example.org"]
        r = client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                        json={"kanal_typ": "telegram", "adresse": "@alice_tg"})
        assert r.json()["status"] == "hinzugefuegt"
        alice2 = _by_name(client)["alice@example.org"]
        assert set(alice2["kanaele"]) == {"email", "telegram"}
        # unbekannter Kanal ⇒ 400
        assert client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                           json={"kanal_typ": "fax", "adresse": "x"}).status_code == 400


def test_alias_umhaengen_von_anderem_kontakt(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        ks = _by_name(client)
        alice, carol = ks["alice@example.org"], ks["carol@example.org"]
        # carols E-Mail explizit zu alice umhängen
        r = client.post(f"/api/smartkontakte/{alice['id']}/aliasse",
                        json={"kanal_typ": "email", "adresse": "carol@example.org"})
        assert r.json()["status"] == "umgehaengt"
        ks2 = _by_name(client)
        # carol hat ihren Alias verloren (0 Kanäle / 0 Nachrichten), alice hat 2 Mails
        assert ks2["carol@example.org"]["kanaele"] == []
        assert ks2["alice@example.org"]["nachrichten"] == 2


def test_merge_buendelt_verlauf_und_split_loest_wieder(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        ks = _by_name(client)
        alice, bob = ks["alice@example.org"], ks["Bob"]
        # MERGE: Bob geht in alice auf
        m = client.post(f"/api/smartkontakte/{alice['id']}/zusammenfuehren",
                        json={"anderer_id": bob["id"]}).json()
        assert m["ok"] and m["verschobene_aliasse"] == 1
        ks2 = _by_name(client)
        assert "Bob" not in ks2                                  # Bob soft-gelöscht
        alice2 = ks2["alice@example.org"]
        assert alice2["nachrichten"] == 2                        # Verlauf folgt den Aliassen
        bob_alias = next(a for a in alice2["aliasse"] if a["adresse"] == "bob@example.org")
        # SPLIT: Bobs E-Mail wieder herauslösen
        s = client.post(f"/api/smartkontakte/{alice2['id']}/trennen",
                        json={"adress_id": bob_alias["id"]}).json()
        assert s["ok"] and s["name"] == "bob@example.org"
        ks3 = {k["id"]: k for k in client.get("/api/smartkontakte").json()}
        assert ks3[alice2["id"]]["nachrichten"] == 1            # alice wieder allein
        assert ks3[s["neuer_id"]]["nachrichten"] == 1          # neuer Kontakt trägt Bobs Mail


def test_merge_unbekannt_404_und_self_400(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        alice = _by_name(client)["alice@example.org"]
        assert client.post(f"/api/smartkontakte/{alice['id']}/zusammenfuehren",
                           json={"anderer_id": alice["id"]}).status_code == 400
        assert client.post(f"/api/smartkontakte/{alice['id']}/zusammenfuehren",
                           json={"anderer_id": "gibtsnicht"}).status_code == 404


def test_vorschlaege_endpoint_cross_channel(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        alice = _by_name(client)["alice@example.org"]
        # Telegram-Handle mit demselben Stamm wie alices E-Mail-Localpart an einen
        # NEUEN Kontakt → der Vorschlags-Endpoint soll das Paar vorschlagen.
        neu = client.post("/api/smartkontakte", json={"name": "Telegram-Alice"}).json()["id"]
        client.post(f"/api/smartkontakte/{neu}/aliasse",
                    json={"kanal_typ": "telegram", "adresse": "@alice"})
        v = client.get("/api/smartkontakte/vorschlaege").json()
        paare = [{x["a"], x["b"]} for x in v]
        assert {alice["id"], neu} in paare


def test_alias_entfernen(tmp_path):
    with _client_mit_sync(tmp_path) as client:
        alice = _by_name(client)["alice@example.org"]
        aid = alice["aliasse"][0]["id"]
        assert client.delete(
            f"/api/smartkontakte/{alice['id']}/aliasse/{aid}").json()["entfernt"] == 1
        assert _by_name(client)["alice@example.org"]["kanaele"] == []
