"""Tests Phase 3 — Watchlist (lebender Themen-Ordner).

Ebenen: (1) das deterministische Themen-Matching (`newsapp.watchlist`),
(2) CRUD-Endpoints, (3) Auto-Population beim Abruf (gated, idempotent, neu-Zähler)
inkl. KI-Kurzfassungs-Fallback bzw. injizierter Kurzfassung (kein Netz im Test)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsapp import main as nm
from newsapp import watchlist as wl


def _client(tmp_path, monkeypatch, feeds=None, kurzfassung_fn=None, archiv_post=None):
    if feeds is not None:
        monkeypatch.setattr(nm, "_lade_feed", lambda url: feeds.get(url, []))
    app = nm.build_app(data_dir=tmp_path, start_timer=False,
                       kurzfassung_fn=kurzfassung_fn, archiv_post=archiv_post)
    return TestClient(app)


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _archiv_stub():
    """Fängt ``archiviere``-Relay-Calls (kein Netz); ``.calls`` = die Umschläge."""
    calls = []

    def post(url, json):
        calls.append(json)
        return _Resp({"ok": True, "status": "archiviert", "id": "x"})
    post.calls = calls
    return post


# ----------------------------- Matching pur ---------------------------------

def test_matching_containment():
    tt = wl.thema_tokens("Klimawandel und Energie Politik")
    a_treffer = {"titel": "Studie zum Klimawandel", "zusammenfassung": "Folgen für die Energie"}
    a_daneben = {"titel": "Bundesliga Spieltag", "zusammenfassung": "Tore und Tabelle"}
    assert wl.passt(tt, wl.artikel_tokens(a_treffer)) is True
    assert wl.passt(tt, wl.artikel_tokens(a_daneben)) is False
    # leeres Thema ⇒ matcht NIE (kein „alles einsammeln")
    assert wl.passt(wl.thema_tokens(""), wl.artikel_tokens(a_treffer)) is False


def test_score_und_bewerte():
    ok, s = wl.bewerte_artikel("Bitcoin Kurs", {"titel": "Bitcoin steigt stark", "zusammenfassung": ""})
    assert ok is True and 0.0 < s <= 1.0
    assert wl.cosine([1, 0], [1, 0]) == 1.0
    assert wl.cosine([1, 0], [0, 1]) == 0.0
    assert wl.cosine([], [1]) == 0.0


# ------------------------------- CRUD ---------------------------------------

def test_watchlist_crud(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, feeds={}) as c:
        assert c.post("/api/watchlists", json={"name": "", "thema": "x"}).status_code == 400
        wid = c.post("/api/watchlists", json={"name": "Krypto", "thema": "Bitcoin Krypto"}).json()["id"]
        ls = c.get("/api/watchlists").json()
        assert len(ls) == 1 and ls[0]["name"] == "Krypto" and ls[0]["anzahl"] == 0
        # Thema ändern
        assert c.put("/api/watchlists/" + wid, json={"thema": "Bitcoin Ethereum"}).json()["ok"]
        assert c.get("/api/watchlists/" + wid).json()["thema"] == "Bitcoin Ethereum"
        # löschen
        assert c.delete("/api/watchlists/" + wid).json()["ok"]
        assert c.get("/api/watchlists").json() == []
        assert c.get("/api/watchlists/" + wid).status_code == 404


def test_watchlist_manuell_add_remove(tmp_path, monkeypatch):
    feeds = {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Irgendwas", "link": "https://x/1", "zusammenfassung": "Inhalt", "published": None}]}
    with _client(tmp_path, monkeypatch, feeds) as c:
        c.post("/api/abrufen")
        aid = c.get("/api/artikel").json()[0]["id"]
        wid = c.post("/api/watchlists", json={"name": "Manuell", "thema": ""}).json()["id"]
        # manuelles Hinzufügen (auch ohne Thema-Match)
        assert c.post(f"/api/watchlists/{wid}/artikel/{aid}").json()["ok"]
        det = c.get("/api/watchlists/" + wid).json()
        assert len(det["artikel"]) == 1 and det["artikel"][0]["artikel_id"] == aid
        # idempotent (zweiter Add legt keinen zweiten Eintrag an)
        c.post(f"/api/watchlists/{wid}/artikel/{aid}")
        assert len(c.get("/api/watchlists/" + wid).json()["artikel"]) == 1
        # entfernen
        assert c.delete(f"/api/watchlists/{wid}/artikel/{aid}").json()["ok"]
        assert c.get("/api/watchlists/" + wid).json()["artikel"] == []


# --------------------------- Auto-Population ---------------------------------

def _feeds_klima():
    return {nm.SEED_QUELLEN[0][1]: [
        {"titel": "Studie zum Klimawandel", "link": "https://x/klima",
         "zusammenfassung": "Folgen für die Energie weltweit", "published": None},
        {"titel": "Bundesliga Spieltag", "link": "https://x/fussball",
         "zusammenfassung": "Tore und Tabelle", "published": None},
    ]}


def test_autopop_und_neu_zaehler(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, _feeds_klima()) as c:
        wid = c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"}).json()["id"]
        r = c.post("/api/abrufen").json()
        assert r["watchlist"] == 1                       # genau der Klima-Artikel
        wls = c.get("/api/watchlists").json()
        assert wls[0]["anzahl"] == 1 and wls[0]["neu"] == 1
        det = c.get("/api/watchlists/" + wid).json()
        titel = {a["titel"] for a in det["artikel"]}
        assert "Studie zum Klimawandel" in titel and "Bundesliga Spieltag" not in titel
        # Karte trägt eine Zusammenfassung (Fallback Feed-Summary, kein Netz)
        assert "Energie" in det["artikel"][0]["zusammenfassung"]
        # „gesehen" setzt neu zurück
        assert c.post("/api/watchlists/" + wid + "/gesehen").json()["ok"]
        assert c.get("/api/watchlists").json()[0]["neu"] == 0
        # Re-Abruf (alles Duplikat ⇒ 0 neue Artikel) ⇒ Auto-Pop legt nichts nach
        assert c.post("/api/abrufen").json()["watchlist"] == 0


def test_autopop_gated_und_schwelle(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, _feeds_klima()) as c:
        c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"})
        # Auto aus ⇒ keine Zuordnung
        c.put("/api/settings", json={"key": "watchlist_auto", "value": False})
        assert c.post("/api/abrufen").json()["watchlist"] == 0
        assert c.get("/api/watchlists").json()[0]["anzahl"] == 0


def test_watchlist_backfill_beim_anlegen(tmp_path, monkeypatch):
    # Erst Artikel holen, DANN Watchlist anlegen ⇒ Bestand wird sofort gescannt
    # (eine neue Watchlist startet nicht leer).
    with _client(tmp_path, monkeypatch, _feeds_klima()) as c:
        c.post("/api/abrufen")
        r = c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"}).json()
        assert r["backfill"] == 1
        wid = r["id"]
        det = c.get("/api/watchlists/" + wid).json()
        assert {a["titel"] for a in det["artikel"]} == {"Studie zum Klimawandel"}
        # Thema ändern auf etwas anderes ⇒ erneuter Backfill möglich (hier 0 Treffer)
        assert c.put("/api/watchlists/" + wid, json={"thema": "Raumfahrt Mars"}).json()["backfill"] == 0


def test_autopop_kurzfassung_injektion(tmp_path, monkeypatch):
    # injizierte Kurzfassung (kein Netz) ⇒ Karte trägt die KI-Variante
    kf = lambda titel, text: "KI-Fassung: " + titel
    with _client(tmp_path, monkeypatch, _feeds_klima(), kurzfassung_fn=kf) as c:
        wid = c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"}).json()["id"]
        c.post("/api/abrufen")
        det = c.get("/api/watchlists/" + wid).json()
        assert det["artikel"][0]["zusammenfassung"].startswith("KI-Fassung: ")


# --------------------------- Phase 4: → Memory -------------------------------

def test_memory_sync_vollsync_und_aus(tmp_path, monkeypatch):
    stub = _archiv_stub()
    with _client(tmp_path, monkeypatch, _feeds_klima(), archiv_post=stub) as c:
        c.post("/api/abrufen")
        wid = c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"}).json()["id"]
        assert len(stub.calls) == 0                  # Sync noch aus ⇒ kein Push
        r = c.post(f"/api/watchlists/{wid}/memory-sync", json={"an": True}).json()
        assert r["memory_sync"] is True and r["synchronisiert"] == 1
        u = stub.calls[0]
        assert u["strom"] == "watchlist" and u["app"] == "news"
        assert u["ref"].startswith("news:watchlist:" + wid + ":")
        assert u["ordner"].startswith("News-Watchlist:")
        # Detail trägt das Sync-Flag
        assert c.get("/api/watchlists/" + wid).json()["memory_sync"] == 1
        # ausschalten
        assert c.post(f"/api/watchlists/{wid}/memory-sync", json={"an": False}).json()["memory_sync"] is False


def test_memory_sync_fortlaufend(tmp_path, monkeypatch):
    stub = _archiv_stub()
    with _client(tmp_path, monkeypatch, _feeds_klima(), archiv_post=stub) as c:
        wid = c.post("/api/watchlists", json={"name": "Klima", "thema": "Klimawandel Energie"}).json()["id"]
        # Sync an, noch keine Artikel ⇒ 0 sofort
        assert c.post(f"/api/watchlists/{wid}/memory-sync", json={"an": True}).json()["synchronisiert"] == 0
        assert len(stub.calls) == 0
        # Abruf ⇒ Klima-Treffer wird automatisch zugeordnet UND (Sync an) nach Memory gepusht
        c.post("/api/abrufen")
        assert any(u["ref"].startswith("news:watchlist:" + wid) for u in stub.calls)


def test_konto_loeschen_raeumt_watchlist_artikel_hart(tmp_path):
    """DSGVO-Audit-Fund (Kern-Dauerschleife 26.06.): ``watchlist_artikel`` hat KEIN
    ``user_id``/``deleted_at`` (Kind der ``watchlists``) ⇒ die generische
    ``soft_delete_user``-Kaskade erfasst es nicht. Der news-``on_delete``-Hook muss es
    bei der Konto-Löschung HART entfernen (sonst bleiben Artikel-Inhalte liegen)."""
    import time

    from appkit import auth
    from appkit.auth import DEFAULT_USER_ID

    auth.reset_identity_provider()
    app = nm.build_app(data_dir=tmp_path, start_timer=False)
    db = app.state.db
    with TestClient(app) as c:
        wid = c.post("/api/watchlists",
                     json={"name": "US-Gov", "thema": "shutdown"}).json()["id"]
        db.get_conn().execute(
            "INSERT INTO watchlist_artikel (id, watchlist_id, titel, link, created_at) "
            "VALUES ('a1', ?, 'T', 'http://x/1', '2026-01-01T00:00:00Z')", (wid,))
        db.get_conn().commit()
        assert db.get_conn().execute(
            "SELECT COUNT(*) AS n FROM watchlist_artikel").fetchone()["n"] == 1
        # Konto-Löschung = Step-up ⇒ verifizierte, frische Identität
        auth.set_identity_provider(lambda _r: auth.UserContext(
            DEFAULT_USER_ID, level="verifiziert", via="dizzi-id", auth_time=time.time() - 5))
        assert c.post("/api/account/loeschen").json()["ok"] is True
        # HART entfernt (keine deleted_at-Spalte ⇒ Zeile ganz weg)
        assert db.get_conn().execute(
            "SELECT COUNT(*) AS n FROM watchlist_artikel").fetchone()["n"] == 0
    auth.reset_identity_provider()
