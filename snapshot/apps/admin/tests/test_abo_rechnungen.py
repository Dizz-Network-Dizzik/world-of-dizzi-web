"""Tests Dizz Admin — A6 wiederkehrende Rechnungen / Abos (docs/30 B).
Eine Vorlage (Kunde + Positionen + RRULE-light) erzeugt getaktet ENTWURFS-
Rechnungen (Plan→Ist), deterministisch + idempotent. GoBD unberührt: Nummer
erst beim Stellen. Lauf: pytest tests/ -q
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from adminapp import main as lm


def _client(tmp_path) -> TestClient:
    return TestClient(lm.build_app(data_dir=tmp_path))


def _abo(c, **kw):
    body = {"titel": "Hosting", "rrule": "FREQ=MONTHLY",
            "positionen": [{"beschreibung": "Hosting", "menge": 1,
                            "einzelpreis_cent": 2900, "ust_satz": 19}]}
    body.update(kw)
    return c.post("/api/rechnung-abos", json=body).json()


def test_anlegen_und_faellig(tmp_path):
    with _client(tmp_path) as c:
        a = _abo(c)
        assert a["ok"] and a["naechster_lauf"] == date.today().isoformat()
        faellig = c.get("/api/rechnung-abos/faellig").json()["faellig"]
        assert len(faellig) == 1 and faellig[0]["id"] == a["id"]


def test_ausfuehren_erzeugt_entwurf_und_rueckt_vor(tmp_path):
    with _client(tmp_path) as c:
        a = _abo(c)
        res = c.post(f"/api/rechnung-abos/{a['id']}/ausfuehren").json()
        assert res["status"] == "erzeugt"
        # nächster Lauf ~1 Monat in der Zukunft
        assert res["naechster_lauf"] > date.today().isoformat()
        # erzeugte Rechnung ist ein Entwurf OHNE Nummer (GoBD)
        entwuerfe = c.get("/api/rechnungen?status=entwurf").json()
        assert len(entwuerfe) == 1
        rid = entwuerfe[0]["id"]
        assert entwuerfe[0]["nummer"] == ""
        assert entwuerfe[0]["brutto_cent"] == round(2900 * 1.19)   # live gerechnet
        # lässt sich regulär stellen ⇒ bekommt dann die lückenlose Nummer
        st = c.post(f"/api/rechnungen/{rid}/stellen").json()
        assert st["status"] == "offen" and st["nummer"].endswith("-0001")


def test_idempotent_und_force(tmp_path):
    with _client(tmp_path) as c:
        a = _abo(c)
        c.post(f"/api/rechnung-abos/{a['id']}/ausfuehren")
        # zweiter Lauf ohne force: noch nicht fällig ⇒ kein zweiter Entwurf
        again = c.post(f"/api/rechnung-abos/{a['id']}/ausfuehren").json()
        assert again["status"] == "nicht_faellig"
        assert len(c.get("/api/rechnungen?status=entwurf").json()) == 1
        # mit force: zweiter Entwurf
        forced = c.post(f"/api/rechnung-abos/{a['id']}/ausfuehren?force=1").json()
        assert forced["status"] == "erzeugt"
        assert len(c.get("/api/rechnungen?status=entwurf").json()) == 2


def test_sammel_lauf_und_bereich(tmp_path):
    with _client(tmp_path) as c:
        b = c.post("/api/bereiche", json={"name": "Mandant A", "art": "mandant"}).json()["id"]
        _abo(c, titel="A", bereich_id=b)
        _abo(c, titel="B")
        lauf = c.post("/api/rechnung-abos/lauf").json()
        assert lauf["anzahl"] == 2
        # die Rechnung aus Abo "A" erbt den Bereich
        rb = c.get(f"/api/rechnungen?bereich_id={b}").json()
        assert len(rb) == 1 and rb[0]["titel"] == "A"


def test_until_erschoepft_deaktiviert(tmp_path):
    with _client(tmp_path) as c:
        heute = date.today().isoformat()
        a = _abo(c, rrule=f"FREQ=MONTHLY;UNTIL={heute}")
        res = c.post(f"/api/rechnung-abos/{a['id']}/ausfuehren").json()
        assert res["status"] == "erzeugt" and not res["naechster_lauf"]
        abo = c.get(f"/api/rechnung-abos/{a['id']}").json()
        assert abo["aktiv"] is False
        assert c.get("/api/rechnung-abos/faellig").json()["faellig"] == []


def test_validierung(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/rechnung-abos", json={"titel": "leer", "positionen": []}).status_code == 400
        assert c.post("/api/rechnung-abos", json={
            "rrule": "MÜLL", "positionen": [{"einzelpreis_cent": 1}]}).status_code == 400


def test_vorschlaege_aus_abo_produkt(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/produkte", json={"name": "Pro-Plan", "preis_cent": 990,
                                      "abo_intervall": "monatlich"})
        c.post("/api/produkte", json={"name": "Jahres-Lizenz", "preis_cent": 12000,
                                      "abo_intervall": "jaehrlich"})
        c.post("/api/produkte", json={"name": "Einmal-Setup", "preis_cent": 5000,
                                      "abo_intervall": "einmalig"})
        v = c.get("/api/rechnung-abos/vorschlaege").json()["vorschlaege"]
        namen = {x["name"]: x for x in v}
        assert set(namen) == {"Pro-Plan", "Jahres-Lizenz"}            # einmalig fällt raus
        assert namen["Jahres-Lizenz"]["rrule"] == "FREQ=MONTHLY;INTERVAL=12"
        assert namen["Pro-Plan"]["positionen"][0]["einzelpreis_cent"] == 990
