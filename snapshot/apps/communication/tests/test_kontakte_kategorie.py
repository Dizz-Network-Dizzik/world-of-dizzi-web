"""P0 — Kontakte: Kategorie + Favorit + Suche/Sortierung/Filter (Kontakte-Panel).

Migration (kategorie/favorit) + /api/smartkontakte-Erweiterung: Favoriten immer
oben, Sortierung relevanz|menge|name|kategorie, q-Suche, nur_favoriten/kategorie-
Filter; Setz-Endpoints mit Validierung gegen KONTAKT_KATEGORIEN."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kommapp.main import KONTAKT_KATEGORIEN, build_app


def _client(tmp_path):
    return TestClient(build_app(data_dir=tmp_path))


def _neu(c, name):
    return c.post("/api/smartkontakte", json={"name": name}).json()["id"]


def test_kategorien_set_definiert():
    # Nutzer-Entscheid „Erweitert"
    for k in ("freund", "familie", "geschaeft", "service", "haendler", "behoerde", "sonstiges"):
        assert k in KONTAKT_KATEGORIEN


def test_kategorie_setzen_und_validierung(tmp_path):
    with _client(tmp_path) as c:
        kid = _neu(c, "Max")
        assert c.post(f"/api/smartkontakte/{kid}/kategorie",
                      json={"kategorie": "freund"}).json()["kategorie"] == "freund"
        assert c.post(f"/api/smartkontakte/{kid}/kategorie",
                      json={"kategorie": "quatsch"}).status_code == 400
        assert c.post("/api/smartkontakte/gibtsnicht/kategorie",
                      json={"kategorie": "freund"}).status_code == 404
        k = next(x for x in c.get("/api/smartkontakte").json() if x["id"] == kid)
        assert k["kategorie"] == "freund" and k["favorit"] is False


def test_favorit_toggle_und_immer_oben(tmp_path):
    with _client(tmp_path) as c:
        a = _neu(c, "Anna"); b = _neu(c, "Bert")
        assert c.post(f"/api/smartkontakte/{b}/favorit", json={}).json()["favorit"] is True
        liste = c.get("/api/smartkontakte?sort=name").json()
        assert liste[0]["id"] == b                      # Favorit oben trotz Name-Sort (Anna<Bert)
        assert c.post(f"/api/smartkontakte/{b}/favorit",
                      json={"favorit": False}).json()["favorit"] is False
        assert c.get("/api/smartkontakte?sort=name").json()[0]["name"] == "Anna"


def test_sort_name_und_filter_kategorie_und_favoriten(tmp_path):
    with _client(tmp_path) as c:
        a = _neu(c, "Zeta"); b = _neu(c, "Alpha"); _neu(c, "Mitte")
        c.post(f"/api/smartkontakte/{a}/kategorie", json={"kategorie": "haendler"})
        c.post(f"/api/smartkontakte/{b}/favorit", json={"favorit": True})
        namen = [k["name"] for k in c.get("/api/smartkontakte?sort=name").json()]
        assert namen[0] == "Alpha"                      # Favorit zuerst, sonst alphabetisch
        assert namen[1:] == ["Mitte", "Zeta"]
        nurkat = c.get("/api/smartkontakte?kategorie=haendler").json()
        assert [k["id"] for k in nurkat] == [a]
        nurfav = c.get("/api/smartkontakte?nur_favoriten=true").json()
        assert [k["id"] for k in nurfav] == [b]


def test_suche_q_ueber_name_und_alias(tmp_path):
    with _client(tmp_path) as c:
        kid = _neu(c, "Müller")
        c.post(f"/api/smartkontakte/{kid}/aliasse",
               json={"kanal_typ": "email", "adresse": "mueller@example.org"})
        assert any(k["id"] == kid for k in c.get("/api/smartkontakte?q=müll").json())
        assert any(k["id"] == kid for k in c.get("/api/smartkontakte?q=example.org").json())
        assert c.get("/api/smartkontakte?q=zzzzz").json() == []


def test_limit_top_n(tmp_path):
    with _client(tmp_path) as c:
        for i in range(12):
            _neu(c, f"K{i:02d}")
        assert len(c.get("/api/smartkontakte?limit=10").json()) == 10
