"""Bereich-Achse (Money) — CRUD, Validierung, Zyklus-Schutz, Soft-Delete + Hierarchie.
Spiegelt Admins Bereichs-Modell (apps/admin); hier die Money-lokale Variante über den
HTTP-Pfad (``/api/bereiche``)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def test_bereich_crud(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={
            "name": "Ludwig Hülsen Nagelfabrik", "art": "geschaeft",
            "kontext": "nagelfabrik"}).json()
        bid = b["id"]
        assert b["name"] == "Ludwig Hülsen Nagelfabrik" and b["art"] == "geschaeft"
        assert b["status"] == "aktiv" and b["kontext"] == "nagelfabrik" and b["parent_id"] == ""
        # Liste + Holen
        assert any(x["id"] == bid for x in c.get("/api/bereiche").json())
        assert c.get(f"/api/bereiche/{bid}").json()["name"] == "Ludwig Hülsen Nagelfabrik"
        # Ändern (Name + Typ + Status)
        g = c.put(f"/api/bereiche/{bid}", json={
            "name": "Nagelfabrik GmbH", "art": "mandant", "status": "ruhend"}).json()
        assert g["name"] == "Nagelfabrik GmbH" and g["art"] == "mandant" and g["status"] == "ruhend"
        # Soft-Delete
        assert c.delete(f"/api/bereiche/{bid}").json()["ok"]
        assert not any(x["id"] == bid for x in c.get("/api/bereiche").json())
        assert c.get(f"/api/bereiche/{bid}").status_code == 404


def test_bereich_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/bereiche", json={"name": "  "}).status_code == 400  # Name Pflicht
        # unbekannte art ⇒ auf 'sonstiges' geklemmt (kein Fehler)
        assert c.post("/api/bereiche", json={"name": "X", "art": "quatsch"}).json()["art"] == "sonstiges"
        # unbekannter parent ⇒ 400
        assert c.post("/api/bereiche", json={"name": "Y", "parent_id": "gibtsnicht"}).status_code == 400


def test_bereich_hierarchie_und_zyklus(tmp_path):
    with _client(tmp_path) as c:
        eltern = c.post("/api/bereiche", json={"name": "Geschäft", "art": "geschaeft"}).json()["id"]
        kind = c.post("/api/bereiche", json={"name": "Mandant A", "art": "mandant",
                                             "parent_id": eltern}).json()["id"]
        # Selbst-Parent verboten
        assert c.put(f"/api/bereiche/{eltern}", json={"parent_id": eltern}).status_code == 400
        # Zyklus verboten (Eltern unter sein eigenes Kind hängen)
        assert c.put(f"/api/bereiche/{eltern}", json={"parent_id": kind}).status_code == 400
        # Eltern löschen ⇒ Kind wird zur Wurzel hochgezogen (parent_id='')
        assert c.delete(f"/api/bereiche/{eltern}").json()["ok"]
        assert c.get(f"/api/bereiche/{kind}").json()["parent_id"] == ""


def test_bereich_filter(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/bereiche", json={"name": "G1", "art": "geschaeft"})
        c.post("/api/bereiche", json={"name": "P1", "art": "privat"})
        assert len(c.get("/api/bereiche?art=geschaeft").json()) == 1
        assert len(c.get("/api/bereiche?art=privat").json()) == 1
        assert len(c.get("/api/bereiche").json()) == 2


# ── BER-2: netzweite Ober-Kategorie (additiv über dem art-Katalog, docs/67 §4) ───
def test_ober_kategorie_additiv_in_api(tmp_path):
    # jede Money-art rollt stabil auf ihre Ober-Kategorie — ``privat`` → ``persoenlich``
    # OHNE die (gegatete, destruktive) MIG-ART-1: genau der Sinn des additiven Dual-Read-Layers.
    erwartet = {"geschaeft": "geschaeftlich", "privat": "persoenlich", "projekt": "projekt",
                "mandant": "geschaeftlich", "investment": "persoenlich", "sonstiges": "sonstiges"}
    with _client(tmp_path) as c:
        for art, ok in erwartet.items():
            b = c.post("/api/bereiche", json={"name": art.title(), "art": art}).json()
            assert b["ober_kategorie"] == ok and b["art"] == art          # additiv, art unberührt
            assert c.get(f"/api/bereiche/{b['id']}").json()["ober_kategorie"] == ok


def test_ober_kategorie_mapping_vollstaendig():
    from appkit.bereich_register import (OBER_KATEGORIEN, mapping_validieren,
                                         ober_kategorie_fuer)
    from moneyapp import bereiche as mb
    mapping_validieren(mb.BEREICH_ART)                        # wirft bei Lücke (Bau-Zeit-Assert)
    assert all(ober_kategorie_fuer(a) in OBER_KATEGORIEN for a in mb.BEREICH_ART)


def test_bereich_404(tmp_path):
    with _client(tmp_path) as c:
        assert c.put("/api/bereiche/weg", json={"name": "X"}).status_code == 404
        assert c.delete("/api/bereiche/weg").status_code == 404


# ---- Schritt 2: Zuordnung (Konto-Default + Buchung-Override) -------------------

def test_konto_traegt_bereich(tmp_path):
    with _client(tmp_path) as c:
        bid = c.post("/api/bereiche", json={"name": "Geschäft", "art": "geschaeft"}).json()["id"]
        c.post("/api/konten", json={"name": "Giro", "typ": "asset", "bereich_id": bid})
        assert {k["name"]: k for k in c.get("/api/konten").json()}["Giro"]["bereich_id"] == bid
        # unbekannter Bereich am Konto ⇒ 400
        assert c.post("/api/konten", json={"name": "X", "typ": "asset",
                                           "bereich_id": "weg"}).status_code == 400


def test_zuordnung_konto_default_und_buchung_override(tmp_path):
    with _client(tmp_path) as c:
        bid = c.post("/api/bereiche", json={"name": "Nagelfabrik", "art": "geschaeft"}).json()["id"]
        bid2 = c.post("/api/bereiche", json={"name": "Privat", "art": "privat"}).json()["id"]
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        # Konto generisch zuordnen
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "konten", "id": giro, "bereich_id": bid}).json()["ok"]
        assert {k["name"]: k for k in c.get("/api/konten").json()}["Giro"]["bereich_id"] == bid
        # Buchung auf Giro ERBT den Bereich (effektiv) ⇒ im Bereich-Filter sichtbar
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                       "betrag": "100,00", "datum": "2026-06-10"})
        assert len(c.get(f"/api/buchungen?bereich={bid}").json()) == 1
        # Zweite Buchung mit OVERRIDE auf einen anderen Bereich
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro, "betrag": "50,00",
                                       "datum": "2026-06-11", "bereich_id": bid2})
        assert len(c.get(f"/api/buchungen?bereich={bid}").json()) == 1     # nur die geerbte
        assert len(c.get(f"/api/buchungen?bereich={bid2}").json()) == 1    # nur die Override
        # Konto-Zuordnung lösen ⇒ geerbte Buchung fällt aus bid, Override bleibt
        c.put("/api/bereiche/zuordnung", json={"tabelle": "konten", "id": giro, "bereich_id": ""})
        assert len(c.get(f"/api/buchungen?bereich={bid}").json()) == 0
        assert len(c.get(f"/api/buchungen?bereich={bid2}").json()) == 1


def test_zuordnung_validierung(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "konten", "id": giro, "bereich_id": "weg"}).status_code == 400
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "quatsch", "id": giro, "bereich_id": ""}).status_code == 400
        assert c.put("/api/bereiche/zuordnung",
                     json={"tabelle": "konten", "id": "weg", "bereich_id": ""}).status_code == 404


def test_buchung_unbekannter_bereich_400(tmp_path):
    with _client(tmp_path) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        r = c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                           "betrag": "10,00", "bereich_id": "weg"})
        assert r.status_code == 400


# ---- Schritt 3: Pro-Bereich-Cockpit + Geld-Sorgfalt --------------------------

def test_cockpit_module_und_geld_sorgfalt(tmp_path):
    with _client(tmp_path) as c:
        g = c.post("/api/bereiche", json={"name": "Geschäft", "art": "geschaeft"}).json()["id"]
        p = c.post("/api/bereiche", json={"name": "Privat", "art": "privat"}).json()["id"]
        giroG = c.post("/api/konten", json={"name": "GiroG", "typ": "asset", "bereich_id": g}).json()["id"]
        giroP = c.post("/api/konten", json={"name": "GiroP", "typ": "asset", "bereich_id": p}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        # Einnahme 1000 in Geschäft, Ausgabe 200 in Privat
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giroG,
                                       "betrag": "1000,00", "datum": "2026-06-10"})
        c.post("/api/buchungen", json={"von_konto": giroP, "nach_konto": ek,
                                       "betrag": "200,00", "datum": "2026-06-11"})
        ckG = c.get(f"/api/bereiche/{g}/cockpit").json()
        assert ckG["bereich"]["name"] == "Geschäft"
        assert ckG["cashflow"]["einnahmen"] == 100000 and ckG["cashflow"]["ausgaben"] == 0
        assert ckG["vermoegen"]["netto_je_waehrung"]["EUR"] == 100000
        ckP = c.get(f"/api/bereiche/{p}/cockpit").json()
        assert ckP["cashflow"]["ausgaben"] == 20000 and ckP["cashflow"]["einnahmen"] == 0
        # GELD-SORGFALT: Summe je Bereich = globale Gesamtübersicht (keine Doppelzählung,
        # kein Geldverlust durch die Sicht-Dimension).
        glob = c.get("/api/auswertung/cashflow").json()
        assert glob["einnahmen"] == ckG["cashflow"]["einnahmen"] + ckP["cashflow"]["einnahmen"]
        assert glob["ausgaben"] == ckG["cashflow"]["ausgaben"] + ckP["cashflow"]["ausgaben"]
        # Globale Sicht ist unverändert vorhanden (additiv, nicht ersetzt)
        assert glob["einnahmen"] == 100000 and glob["ausgaben"] == 20000


def test_cockpit_sparziele_und_abos(tmp_path):
    with _client(tmp_path) as c:
        g = c.post("/api/bereiche", json={"name": "Geschäft", "art": "geschaeft"}).json()["id"]
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset", "bereich_id": g}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                       "betrag": "500,00", "datum": "2026-06-10"})
        # Sparziel auf dem Bereichs-Konto
        c.post("/api/sparziele", json={"name": "Rücklage", "zielbetrag": "1000,00", "konto_id": giro})
        # Abo dem Bereich zugeordnet (monatlich 30 €)
        c.post("/api/wiederkehr", json={"name": "Hosting", "betrag": "30,00",
                                        "richtung": "ausgabe", "intervall_tage": 30, "bereich_id": g})
        ck = c.get(f"/api/bereiche/{g}/cockpit").json()
        assert len(ck["sparziele"]) == 1 and ck["sparziele"][0]["name"] == "Rücklage"
        assert ck["sparziele"][0]["fortschritt_prozent"] == 50.0   # 500 von 1000
        assert ck["abos"]["anzahl"] == 1 and ck["abos"]["fixlast_saldo"] == -3000  # 30 € Ausgabe
        assert c.get("/api/bereiche/weg/cockpit").status_code == 404


# ---- Schritt 4: V17-Finanzspur auf echte Bereich-Auflösung gehoben ------------

def test_finanzspur_bereich_aufloesung_mit_fallback(tmp_path):
    with _client(tmp_path) as c:
        bid = c.post("/api/bereiche", json={"name": "Nagelfabrik", "art": "geschaeft",
                                            "kontext": "nagelfabrik"}).json()["id"]
        giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset",
                                           "bereich_id": bid}).json()["id"]
        ek = c.post("/api/konten", json={"name": "EK", "typ": "equity"}).json()["id"]
        c.post("/api/buchungen", json={"von_konto": ek, "nach_konto": giro,
                                       "betrag": "300,00", "datum": "2026-06-10"})
        # kontext-Schlüssel löst über register.aufloesen ② auf (quelle=kontext, je Währung)
        r = c.get("/api/bereich/finanzspur?kontext=nagelfabrik").json()
        assert r["quelle"] == "kontext" and r["bereich_id"] == bid
        assert {e["waehrung"]: e for e in r["je_waehrung"]}["EUR"]["einnahmen"] == 30000
        # kontext-Auflösung ist case-insensitiv (matcht ② vor dem ③ Namens-Fallback)
        assert c.get("/api/bereich/finanzspur?kontext=NagelFabrik").json()["quelle"] == "kontext"
        # ohne passenden Bereich UND ohne Kategorie ⇒ Fallback (Kategorie-Pfad), leer
        r3 = c.get("/api/bereich/finanzspur?kontext=gibtsnicht").json()
        assert r3["quelle"] == "kategorie" and r3["je_waehrung"] == []
