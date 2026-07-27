"""V15 (docs/26 §12): Admin ist die ZIEL-Seite des bidirektionalen Beleg-Links.
- GET /api/belege liefert verknüpfbare Dokumente (ref/titel/typ/datum) für Money.
- POST /api/querverbindung/verknuepfung legt die Rück-Referenz an (idempotent).
- GET /api/verknuepfungen + DELETE für die „verwendet in N Buchungen"-Sicht."""

from __future__ import annotations

from fastapi.testclient import TestClient

from adminapp import main as am

def _client(tmp_path) -> TestClient:
    return TestClient(am.build_app(data_dir=tmp_path, start_wachter=False))

def _pdf(titel="Rechnung", typ="Rechnung"):
    return {"files": {"datei": ("r.pdf", b"%PDF-1.4 x", "application/pdf")},
            "data": {"titel": titel, "typ": typ}}

def test_belege_liste_liefert_refs(tmp_path):
    with _client(tmp_path) as c:
        did = c.post("/api/dokumente/upload", **_pdf(titel="Stromrechnung")).json()["id"]
        belege = c.get("/api/belege").json()
        assert len(belege) == 1
        b = belege[0]
        assert b["ref"] == "admin:dokument:" + did
        assert b["titel"] == "Stromrechnung" and b["typ"] == "Rechnung"
        # Volltext-/Titel-Filter
        assert c.get("/api/belege", params={"q": "strom"}).json()[0]["ref"] == "admin:dokument:" + did
        assert c.get("/api/belege", params={"q": "gibtsnicht"}).json() == []

def test_verknuepfung_empfang_idempotent_und_sicht(tmp_path):
    with _client(tmp_path) as c:
        did = c.post("/api/dokumente/upload", **_pdf()).json()["id"]
        umschlag = {"von_app": "finanzen", "von_ref": "finanzen:buchung:42",
                    "von_titel": "REWE 12,30", "ziel_ref": "admin:dokument:" + did}
        r1 = c.post("/api/querverbindung/verknuepfung", json=umschlag).json()
        assert r1["ok"] is True and r1["status"] == "verknuepft"

        # idempotent (gleiche von_ref × dok_id)
        r2 = c.post("/api/querverbindung/verknuepfung", json=umschlag).json()
        assert r2["status"] == "vorhanden" and r2["id"] == r1["id"]

        # Sicht: verwendet in 1 Buchung
        vk = c.get("/api/verknuepfungen", params={"dok_id": did}).json()
        assert len(vk) == 1
        assert vk[0]["von_ref"] == "finanzen:buchung:42" and vk[0]["von_app"] == "finanzen"
        assert vk[0]["von_titel"] == "REWE 12,30"

        # lösen ⇒ Sicht leer
        assert c.delete(f"/api/verknuepfungen/{r1['id']}").json()["ok"] is True
        assert c.get("/api/verknuepfungen", params={"dok_id": did}).json() == []
        assert c.delete(f"/api/verknuepfungen/{r1['id']}").status_code == 404

def test_verknuepfung_loesen_raeumt_rueckref(tmp_path):
    """V15-Audit-Fix (a): aktion=loesen räumt die Rück-Referenz (Quelle storniert) ⇒
    kein verwaister „verwendet in N"-Hinweis. Idempotent (zweites Lösen ⇒ anzahl 0)."""
    with _client(tmp_path) as c:
        did = c.post("/api/dokumente/upload", **_pdf()).json()["id"]
        umschlag = {"von_app": "finanzen", "von_ref": "finanzen:buchung:42",
                    "von_titel": "REWE", "ziel_ref": "admin:dokument:" + did}
        c.post("/api/querverbindung/verknuepfung", json=umschlag)
        assert len(c.get("/api/verknuepfungen", params={"dok_id": did}).json()) == 1
        r = c.post("/api/querverbindung/verknuepfung",
                   json={**umschlag, "aktion": "loesen"}).json()
        assert r["status"] == "geloest" and r["anzahl"] == 1
        assert c.get("/api/verknuepfungen", params={"dok_id": did}).json() == []
        # idempotent: zweites Lösen ⇒ nichts mehr da
        r2 = c.post("/api/querverbindung/verknuepfung",
                    json={**umschlag, "aktion": "loesen"}).json()
        assert r2["status"] == "geloest" and r2["anzahl"] == 0

def test_verknuepfung_relink_nach_loesen_reaktiviert(tmp_path):
    """V15-Audit-Fix (H-18): wird dieselbe Verknüpfung (von_ref × dok_id) nach einem loesen
    ERNEUT angelegt (Nutzer entfernt den Beleg und knüpft ihn wieder an), muss Admin die
    weich gelöschte Zeile WIEDERBELEBEN — kein UNIQUE-Crash (vorher HTTP 500) und die
    Rück-Referenz steht wieder. Ohne den Fix kollidiert das INSERT mit der UNIQUE-Spalte."""
    with _client(tmp_path) as c:
        did = c.post("/api/dokumente/upload", **_pdf()).json()["id"]
        u = {"von_app": "finanzen", "von_ref": "finanzen:buchung:42",
             "von_titel": "REWE", "ziel_ref": "admin:dokument:" + did}
        id1 = c.post("/api/querverbindung/verknuepfung", json=u).json()["id"]
        assert c.post("/api/querverbindung/verknuepfung",
                      json={**u, "aktion": "loesen"}).json()["anzahl"] == 1
        assert c.get("/api/verknuepfungen", params={"dok_id": did}).json() == []
        # erneut anknüpfen ⇒ 200 + wiederbelebt (gleiche id), KEIN 500
        r = c.post("/api/querverbindung/verknuepfung", json={**u, "von_titel": "REWE neu"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["id"] == id1                     # dieselbe Zeile reaktiviert
        vk = c.get("/api/verknuepfungen", params={"dok_id": did}).json()
        assert len(vk) == 1 and vk[0]["von_titel"] == "REWE neu"   # Rück-Ref + Feld aktualisiert

def test_verknuepfung_empfang_validierung(tmp_path):
    with _client(tmp_path) as c:
        # unbekanntes Dokument ⇒ 404
        r = c.post("/api/querverbindung/verknuepfung", json={
            "von_app": "finanzen", "von_ref": "finanzen:buchung:1",
            "ziel_ref": "admin:dokument:fehlt"})
        assert r.status_code == 404
        # ungültige ziel_ref ⇒ 400
        r2 = c.post("/api/querverbindung/verknuepfung", json={
            "von_app": "finanzen", "von_ref": "x", "ziel_ref": "memory:notiz:1"})
        assert r2.status_code == 400
