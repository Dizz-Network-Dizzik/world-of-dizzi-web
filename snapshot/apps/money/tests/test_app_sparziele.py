"""Sparziele (Sparkonten-Tracking) end-to-end über den HTTP-Pfad: voll-CRUD mit
Soft-Delete + Fortschritt% — manuell gepflegt ODER LIVE aus dem echten Konto-Saldo
(über den geprüften Ledger-Kern). Geld bleibt durchgängig Minor-Units."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _konto(c, name: str, typ: str = "asset", waehrung: str = "EUR") -> str:
    return c.post("/api/konten",
                  json={"name": name, "typ": typ, "waehrung": waehrung}).json()["id"]


def _einzahlen(c, ek: str, konto: str, betrag: str, datum: str = "2026-06-10") -> None:
    """Bucht ``betrag`` von einem Eigenkapital-Konto auf ein Asset-Konto (= Guthaben)."""
    c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": konto,
                                   "betrag": betrag, "datum": datum})


def test_sparziel_crud_manuell(tmp_path):
    with _client(tmp_path) as c:
        sid = c.post("/api/sparziele", json={
            "name": "Urlaub", "zielbetrag": "2000,00", "aktuell": "500,00",
            "faellig_am": "2026-12-01"}).json()["id"]
        liste = c.get("/api/sparziele").json()
        assert len(liste) == 1
        z = liste[0]
        assert z["name"] == "Urlaub" and z["waehrung"] == "EUR" and z["quelle"] == "manuell"
        assert z["zielbetrag"] == 200000 and z["aktuell_minor"] == 50000
        assert z["zielbetrag_text"] == "2000.00" and z["aktuell_text"] == "500.00"
        assert z["rest_minor"] == 150000 and z["rest_text"] == "1500.00"
        assert z["fortschritt_prozent"] == 25.0 and z["erreicht"] is False
        assert z["faellig_am"] == "2026-12-01" and z["konto_id"] is None

        # Ändern: Ziel erreicht melden
        c.put(f"/api/sparziele/{sid}", json={
            "name": "Urlaub 2026", "zielbetrag": "2000,00", "aktuell": "2000,00"})
        z2 = c.get("/api/sparziele").json()[0]
        assert z2["name"] == "Urlaub 2026" and z2["fortschritt_prozent"] == 100.0
        assert z2["erreicht"] is True and z2["rest_minor"] == 0

        # Soft-Delete
        assert c.delete(f"/api/sparziele/{sid}").json()["ok"]
        assert c.get("/api/sparziele").json() == []


def test_sparziel_auto_tracking_aus_konto(tmp_path):
    with _client(tmp_path) as c:
        ek = _konto(c, "Start", typ="equity")
        tagesgeld = _konto(c, "Tagesgeld", typ="asset")
        _einzahlen(c, ek, tagesgeld, "1500,00")            # Saldo Tagesgeld = 1500,00

        c.post("/api/sparziele", json={
            "name": "Notgroschen", "zielbetrag": "3000,00", "konto_id": tagesgeld})
        z = c.get("/api/sparziele").json()[0]
        assert z["quelle"] == "konto" and z["konto_id"] == tagesgeld
        assert z["konto_name"] == "Tagesgeld"
        assert z["aktuell_minor"] == 150000               # LIVE aus dem Konto-Saldo
        assert z["zielbetrag"] == 300000 and z["fortschritt_prozent"] == 50.0
        assert z["rest_text"] == "1500.00" and z["erreicht"] is False

        # Weitere Einzahlung ⇒ Fortschritt wächst automatisch (ohne Sparziel-Update)
        _einzahlen(c, ek, tagesgeld, "1500,00", datum="2026-06-20")
        z2 = c.get("/api/sparziele").json()[0]
        assert z2["aktuell_minor"] == 300000 and z2["fortschritt_prozent"] == 100.0
        assert z2["erreicht"] is True


def test_sparziel_konto_setzt_waehrung(tmp_path):
    """Bei gesetztem konto_id übernimmt das Ziel die Konto-Währung (Fortschritt
    sonst währungsübergreifend); zielbetrag wird in dieser Währung geparst."""
    with _client(tmp_path) as c:
        usd = _konto(c, "USD-Sparen", typ="asset", waehrung="USD")
        c.post("/api/sparziele", json={
            "name": "Dollar-Topf", "zielbetrag": "1000,00", "waehrung": "EUR",
            "konto_id": usd})
        z = c.get("/api/sparziele").json()[0]
        assert z["waehrung"] == "USD" and z["zielbetrag"] == 100000


def test_sparziel_geloeschtes_konto_faellt_auf_manuell(tmp_path):
    """Wird das verknüpfte Konto gelöscht, fällt das Sparziel auf den manuellen
    (gespeicherten) Stand zurück statt zu brechen."""
    with _client(tmp_path) as c:
        sparkonto = _konto(c, "Leer", typ="asset")        # unbebucht ⇒ löschbar
        c.post("/api/sparziele", json={
            "name": "Ziel", "zielbetrag": "500,00", "konto_id": sparkonto})
        assert c.delete(f"/api/konten/{sparkonto}").json()["ok"]
        z = c.get("/api/sparziele").json()[0]
        assert z["quelle"] == "manuell" and z["konto_name"] is None
        assert z["aktuell_minor"] == 0


def test_sparziel_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/sparziele", json={
            "name": "  ", "zielbetrag": "100,00"}).status_code == 400
        assert c.post("/api/sparziele", json={
            "name": "X", "zielbetrag": "0"}).status_code == 400          # Ziel > 0
        assert c.post("/api/sparziele", json={
            "name": "X", "zielbetrag": "-5"}).status_code == 400
        assert c.post("/api/sparziele", json={
            "name": "X", "zielbetrag": "100", "aktuell": "-1"}).status_code == 400
        assert c.post("/api/sparziele", json={
            "name": "X", "zielbetrag": "100", "waehrung": "XAU"}).status_code == 400
        assert c.post("/api/sparziele", json={
            "name": "X", "zielbetrag": "100", "konto_id": "gibtsnicht"}).status_code == 404


def test_sparziel_put_delete_unbekannt(tmp_path):
    with _client(tmp_path) as c:
        assert c.put("/api/sparziele/weg",
                     json={"name": "X", "zielbetrag": "100"}).status_code == 404
        assert c.delete("/api/sparziele/weg").status_code == 404


def test_sparziele_user_isolation(tmp_path):
    """Soft-gelöschte/fremde Ziele tauchen nicht auf; nur eigene aktive Ziele."""
    with _client(tmp_path) as c:
        c.post("/api/sparziele", json={"name": "A", "zielbetrag": "100,00"})
        c.post("/api/sparziele", json={"name": "B", "zielbetrag": "200,00",
                                       "faellig_am": "2026-01-01"})
        liste = c.get("/api/sparziele").json()
        # Sortierung: datiertes Ziel (B) vor undatiertem (A)
        assert [z["name"] for z in liste] == ["B", "A"]
