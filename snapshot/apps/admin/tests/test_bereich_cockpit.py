"""A5 (d, docs/34) — Bereichs-Cockpit-Backend: bündelt die drei Querverbindungs-Spuren
(Finanzspur/Money · Social/Management · Wissen/Memory) eines Bereichs über die
appkit-Helfer + Core-Relays. Read-only, best-effort (wirft nie). Die visuelle
Cockpit-Darstellung ist UI/UX (§5d) und NICHT Teil dieses Tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from adminapp import aggregat
from adminapp import main as lm


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._p = payload

    def json(self):
        return self._p


def _client(tmp_path):
    return TestClient(lm.build_app(data_dir=tmp_path))


def test_bereich_spuren_buendelt_alle_drei(tmp_path):
    """Fake-Core liefert je Relay-Pfad eine Antwort -> alle drei Spuren gefüllt."""
    def fake_get(url, params):
        if url.endswith("/finanzspur"):
            return _Resp({"ok": True, "finanzspur": {"je_waehrung": [{"waehrung": "EUR", "saldo": 100}]}})
        if url.endswith("/bereich-social"):
            return _Resp({"ok": True, "social": {"anzahl_posts": 3}})
        if url.endswith("/kategorie"):
            return _Resp({"ok": True, "notizen": [{"titel": "N"}], "anzahl": 1})
        raise AssertionError(f"unerwartete URL {url}")

    bereich = {"id": "b1", "name": "Studium", "art": "studium",
               "money_kontext": "Studium", "management_kontext": "Uni-Bot",
               "memory_ref": "Studium Informatik"}
    erg = aggregat.bereich_spuren(bereich, http_get=fake_get)
    assert erg["bereich_id"] == "b1" and erg["name"] == "Studium"
    assert erg["finanzspur"]["ok"] is True
    assert erg["finanzspur"]["finanzspur"]["je_waehrung"][0]["saldo"] == 100
    assert erg["social"]["ok"] is True and erg["social"]["social"]["anzahl_posts"] == 3
    assert erg["wissen"]["ok"] is True and erg["wissen"]["anzahl"] == 1
    assert erg["kontexte"] == {"money_kontext": "Studium",
                               "management_kontext": "Uni-Bot",
                               "memory_ref": "Studium Informatik"}


def test_bereich_spuren_leere_kontexte_keine_core_calls(tmp_path):
    """Leere Kontext-Schlüssel ⇒ Spur übersprungen, KEIN Core-Call."""
    aufgerufen = []

    def fake_get(url, params):
        aufgerufen.append(url)
        return _Resp({"ok": True})

    bereich = {"id": "b2", "name": "Leer", "money_kontext": "",
               "management_kontext": "", "memory_ref": ""}
    erg = aggregat.bereich_spuren(bereich, http_get=fake_get)
    assert aufgerufen == []
    assert erg["finanzspur"]["ok"] is False and erg["finanzspur"]["fehler"] == "kein money_kontext"
    assert erg["social"]["fehler"] == "kein management_kontext"
    assert erg["wissen"]["fehler"] == "kein memory_ref"


def test_cockpit_endpoint_404_und_best_effort(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/bereiche/gibtsnicht/cockpit").status_code == 404
        # Bereich OHNE Kontext -> leere Spuren, kein Crash, kein Netzwerk nötig
        bid = c.post("/api/bereiche", json={"name": "X"}).json()["id"]
        r = c.get(f"/api/bereiche/{bid}/cockpit").json()
        assert r["bereich_id"] == bid
        assert r["finanzspur"]["ok"] is False
        assert "social" in r and "wissen" in r


# ── BER-1: kanon-Durchreichung + Broken-Link-Wächter (docs/67) ──────────────────
def test_bereich_spuren_reicht_kanon_durch(tmp_path):
    """Die kanonische Bereichs-ID (=``id``) wird je Relay-Call ZUSÄTZLICH zum kontext
    mitgeschickt (docs/67 §3.3); der Slot-leer-Skip bleibt (test oben) — 0 Verhaltenswechsel."""
    calls = {}

    def fake_get(url, params):
        calls[url.rsplit("/", 1)[-1]] = dict(params)
        if url.endswith("/finanzspur"):
            return _Resp({"ok": True, "finanzspur": {}})
        if url.endswith("/bereich-social"):
            return _Resp({"ok": True, "social": {}})
        if url.endswith("/kategorie"):
            return _Resp({"ok": True, "notizen": [], "anzahl": 0})
        raise AssertionError(f"unerwartete URL {url}")

    bereich = {"id": "b1", "name": "Studium", "art": "studium",
               "money_kontext": "Studium", "management_kontext": "Uni-Bot",
               "memory_ref": "Studium Informatik"}
    erg = aggregat.bereich_spuren(bereich, http_get=fake_get)
    assert erg["kanon"] == "b1"
    assert calls["finanzspur"] == {"kontext": "Studium", "jahr": 0, "kanon": "b1"}
    assert calls["bereich-social"] == {"kontext": "Uni-Bot", "kanon": "b1"}
    assert calls["kategorie"]["kanon"] == "b1"


def test_bereich_waechter_klassifiziert(tmp_path):
    """Broken-Link-Wächter (docs/67 §3.4): bündelt die (injizierten) kanon-status-Feeds
    und klassifiziert je Kante — ok/alt/dangling · Feed offline ⇒ 'unbekannt' (I-6)."""
    def fake_get(url, params):
        if url.endswith("/finanzen/kanon-status"):
            return _Resp({"ok": True, "anker_extra": {}, "bereiche": [
                {"id": "m1", "name": "M1", "kanon_id": "A1", "kontext": ""},          # ⇒ ok
                {"id": "m2", "name": "M2", "kanon_id": "", "kontext": "nagelfabrik"}]})  # ⇒ alt
        if url.endswith("/management/kanon-status"):
            return _Resp({"ok": False, "bereiche": []})     # offline ⇒ Kante unbekannt
        if url.endswith("/memory/kanon-status"):
            return _Resp({"ok": True, "anker_extra": {"ordner": ["Studium Info"]},
                          "bereiche": [{"id": "x1", "name": "Anders", "kanon_id": "", "kontext": ""}]})
        raise AssertionError(f"unerwartete URL {url}")

    admin = [
        {"id": "A1", "name": "Gebunden", "money_kontext": "egal",
         "management_kontext": "", "memory_ref": ""},
        {"id": "A2", "name": "Fragil", "money_kontext": "nagelfabrik",
         "management_kontext": "", "memory_ref": ""},
        {"id": "A3", "name": "Tot", "money_kontext": "gibtsnicht",
         "management_kontext": "", "memory_ref": ""},
        {"id": "A9", "name": "Wissen", "money_kontext": "",
         "management_kontext": "", "memory_ref": "Studium Info"},
    ]
    rep = aggregat.bereich_waechter(admin, http_get=fake_get)
    v17 = {e["bereich_id"]: e for e in rep["kanten"] if e["kante"] == "V17"}
    assert v17["A1"]["befund"] == "ok" and v17["A2"]["befund"] == "alt"
    assert v17["A3"]["befund"] == "dangling" and v17["A9"]["befund"] == "ungenutzt"
    v18 = [e for e in rep["kanten"] if e["kante"] == "V18"]
    assert all(e["befund"] == "unbekannt" for e in v18)              # Feed offline
    v19 = {e["bereich_id"]: e for e in rep["kanten"] if e["kante"] == "V19"}
    assert v19["A9"]["befund"] == "alt" and v19["A9"]["quelle"] == "name"  # Ordner-Name
    assert rep["zusammenfassung"]["unbekannt"] == 4                 # 4 Bereiche × V18


def test_waechter_route_registriert_vor_bid(tmp_path):
    """Die Literal-Route /api/bereiche/waechter ist registriert und steht VOR /{bid}
    (sonst fängt der Platzhalter „waechter" als Bereichs-id ab). Hermetisch (kein Core)."""
    with _client(tmp_path) as c:
        pfade = [getattr(r, "path", "") for r in c.app.routes]
        assert "/api/bereiche/waechter" in pfade
        assert pfade.index("/api/bereiche/waechter") < pfade.index("/api/bereiche/{bid}")
