"""V15 (docs/26 §12): Money ist die TREIBENDE Seite des bidirektionalen Beleg-Links.
- GET /api/belege-auswahl holt Admin-Dokumente (über den Core-Relay) für die Auswahl.
- POST /api/buchungen/{id}/beleg setzt die Vorwärts-Referenz UND meldet Admin die Rück-Referenz.
- DELETE entfernt die lokale Verknüpfung. Nur Daten, nie ein Echtgeld-/Aktions-Auslöser."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


class _R:
    def __init__(self, payload):
        self.status_code = 200
        self._p = payload

    def json(self):
        return self._p


def _belege_get(belege):
    def get(url, params):
        return _R({"ok": True, "belege": belege})
    return get


def _verkn_post(store):
    def post(url, json):
        store.append({"url": url, "umschlag": json})
        return _R({"ok": True, "status": "verknuepft", "id": "v1"})
    return post


def _buchung(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    ek = c.post("/api/konten", json={"name": "Einkauf", "typ": "expense"}).json()["id"]
    # Manuelle Buchung trägt keine gegenpartei (nur Import) ⇒ Beleg-Titel = Notiz.
    return c.post("/api/buchungen", json={
        "von_konto": giro, "nach_konto": ek, "betrag": "12,30",
        "datum": "2026-06-15", "notiz": "REWE Einkauf"}).json()["id"]


def test_belege_auswahl_holt_von_admin(tmp_path):
    belege = [{"ref": "admin:dokument:7", "titel": "Rechnung",
               "typ": "Rechnung", "datum": "2026-06-01"}]
    app = mm.build_app(data_dir=tmp_path, belege_get=_belege_get(belege))
    with TestClient(app) as c:
        r = c.get("/api/belege-auswahl", params={"q": "rech"}).json()
        assert r["ok"] is True
        assert r["belege"][0]["ref"] == "admin:dokument:7"


def test_buchung_beleg_setzen_bidirektional(tmp_path):
    erfasst: list = []
    app = mm.build_app(data_dir=tmp_path, verknuepfung_post=_verkn_post(erfasst))
    with TestClient(app) as c:
        bid = _buchung(c)
        r = c.post(f"/api/buchungen/{bid}/beleg",
                   json={"ref": "admin:dokument:7", "titel": "Kassenbon"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["beleg_ref"] == "admin:dokument:7"
        assert body["admin"] == "verknuepft"

        # Rück-Referenz an Admin korrekt adressiert + befüllt
        assert erfasst, "kein Verknüpfungs-Push an Admin"
        u = erfasst[-1]["umschlag"]
        assert erfasst[-1]["url"].endswith("/api/querverbindung/admin/verknuepfung")
        assert u["von_ref"] == "finanzen:buchung:" + bid
        assert u["ziel_ref"] == "admin:dokument:7"
        assert u["von_app"] == "finanzen" and u["von_titel"] == "REWE Einkauf"

        # die Buchungs-Liste trägt den Beleg
        b = next(x for x in c.get("/api/buchungen").json() if x["id"] == bid)
        assert b["beleg_ref"] == "admin:dokument:7" and b["beleg_titel"] == "Kassenbon"

        # Audit-Beleg
        assert "beleg_verknuepft" in [e["action"] for e in c.get("/api/audit").json()]

        # lösen ⇒ Buchung ohne Beleg
        assert c.delete(f"/api/buchungen/{bid}/beleg").json()["ok"] is True
        b2 = next(x for x in c.get("/api/buchungen").json() if x["id"] == bid)
        assert b2["beleg_ref"] == "" and b2["beleg_titel"] == ""


def test_storno_und_beleg_entfernen_loesen_admin_rueckref(tmp_path):
    """V15-Audit-Fix (a): das Entfernen eines Belegs UND das Stornieren einer Buchung
    mit Beleg melden Admin ein aktion=loesen ⇒ keine verwaiste Rück-Referenz."""
    erfasst: list = []
    app = mm.build_app(data_dir=tmp_path, verknuepfung_post=_verkn_post(erfasst))
    with TestClient(app) as c:
        # Fall 1: Beleg explizit entfernen
        bid = _buchung(c)
        c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:7", "titel": "x"})
        c.delete(f"/api/buchungen/{bid}/beleg")
        assert any(u["umschlag"].get("aktion") == "loesen"
                   and u["umschlag"]["ziel_ref"] == "admin:dokument:7" for u in erfasst)
        # Fall 2: Buchung mit Beleg stornieren
        erfasst.clear()
        bid2 = _buchung(c)
        c.post(f"/api/buchungen/{bid2}/beleg", json={"ref": "admin:dokument:9"})
        erfasst.clear()                                  # nur das Storno betrachten
        c.delete(f"/api/buchungen/{bid2}")
        assert any(u["umschlag"].get("aktion") == "loesen"
                   and u["umschlag"]["ziel_ref"] == "admin:dokument:9" for u in erfasst)
        # Storno einer Buchung OHNE Beleg ⇒ kein loesen-Aufruf
        erfasst.clear()
        bid3 = _buchung(c)
        c.delete(f"/api/buchungen/{bid3}")
        assert not any(u["umschlag"].get("aktion") == "loesen" for u in erfasst)


def test_beleg_wechsel_loest_alten_link(tmp_path):
    """V15-Audit-Fix (H-18): wird auf einer Buchung ein ANDERER Beleg gesetzt, meldet Money
    Admin erst ein aktion=loesen für den ALTEN Beleg (sonst bliebe dort ein verwaister
    „verwendet in N"-Hinweis). Das Setzen desselben Belegs löst KEIN loesen aus."""
    erfasst: list = []
    app = mm.build_app(data_dir=tmp_path, verknuepfung_post=_verkn_post(erfasst))
    with TestClient(app) as c:
        bid = _buchung(c)
        c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:7"})
        erfasst.clear()
        # Wechsel auf einen anderen Beleg ⇒ altes Dokument 7 wird gelöst, neues 9 verknüpft
        c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:9"})
        assert any(u["umschlag"].get("aktion") == "loesen"
                   and u["umschlag"]["ziel_ref"] == "admin:dokument:7" for u in erfasst)
        assert any(u["umschlag"].get("aktion", "anlegen") == "anlegen"
                   and u["umschlag"]["ziel_ref"] == "admin:dokument:9" for u in erfasst)
        # Denselben Beleg erneut setzen ⇒ KEIN loesen (nur idempotentes anlegen)
        erfasst.clear()
        c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:9"})
        assert not any(u["umschlag"].get("aktion") == "loesen" for u in erfasst)


def test_buchung_beleg_validierung(tmp_path):
    app = mm.build_app(data_dir=tmp_path)
    with TestClient(app) as c:
        bid = _buchung(c)
        # ungültige Referenz ⇒ 400
        assert c.post(f"/api/buchungen/{bid}/beleg",
                      json={"ref": "memory:notiz:1"}).status_code == 400
        # unbekannte Buchung ⇒ 404
        assert c.post("/api/buchungen/fehlt/beleg",
                      json={"ref": "admin:dokument:1"}).status_code == 404


def test_beleg_setzen_ohne_admin_ist_best_effort(tmp_path):
    """Ist Admin/Core offline (Default-Relay wirft), bleibt die lokale Verknüpfung
    trotzdem stehen — verknuepfe ist best-effort und stört Money nicht."""
    def boom_post(url, json):
        raise RuntimeError("Core down")
    app = mm.build_app(data_dir=tmp_path, verknuepfung_post=boom_post)
    with TestClient(app) as c:
        bid = _buchung(c)
        r = c.post(f"/api/buchungen/{bid}/beleg", json={"ref": "admin:dokument:9"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["admin"] == "fehler"
        b = next(x for x in c.get("/api/buchungen").json() if x["id"] == bid)
        assert b["beleg_ref"] == "admin:dokument:9"   # lokal trotzdem gesetzt
