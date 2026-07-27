"""Wiederkehrende Posten end-to-end: Erkennung aus importierten Buchungen,
Speichern/Bestätigen einer Serie, Planung der nächsten Fälligkeiten."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.wiederkehr import erkenne_serien


def _miete(d: str) -> dict:
    return {"datum": d, "gegenpartei": "Miete GmbH", "verwendungszweck": "", "betrag": -100000}


def test_naechste_faellig_monatsende_driftet_nicht():
    """MR-1 (28.06.): eine Monatsende-Serie (letzte = 31. Jan) darf bei der Vorhersage
    der nächsten Fälligkeit NICHT auf die 29. driften, nachdem sie durch den Februar
    geschritten ist. ANKER-verankert an ``letzte`` ⇒ 31.Jan +1=29.Feb +2=31.Mär +3=30.Apr
    (NICHT iterativ 29.Feb→29.Mär→29.Apr). Konsistent mit recurrence.expandiere."""
    serien = erkenne_serien([_miete("2023-11-30"), _miete("2023-12-31"),
                             _miete("2024-01-31")], heute="2024-04-15")
    assert serien, "monatliche Serie sollte erkannt werden"
    s = serien[0]
    assert s["intervall"] == "monatlich" and s["letzte"] == "2024-01-31"
    assert s["naechste_faellig"] == "2024-04-30"     # anker-basiert, NICHT 2024-04-29 (Drift)


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _giro(c):
    return c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]


def _abo_csv():
    """6 monatliche Netflix-Lastschriften (echte Monatsabstände)."""
    d0 = date(2026, 1, 7)
    zeilen = ["Datum;Empfänger;Verwendungszweck;Kundenreferenz;Betrag;Währung"]
    for i in range(6):
        d = d0 + timedelta(days=round(i * 30.4))
        zeilen.append(f"{d.strftime('%d.%m.%Y')};Netflix;Abo;NFX-{i};-12,99;EUR")
    return "\n".join(zeilen) + "\n"


def test_erkennung_aus_import(tmp_path):
    with _client(tmp_path) as c:
        giro = _giro(c)
        c.post("/api/import", json={"inhalt": _abo_csv(), "format": "csv", "zielkonto": giro})
        j = c.get("/api/wiederkehr").json()
        netflix = [e for e in j["erkannt"] if e["name"] == "Netflix"]
        assert netflix and netflix[0]["betrag"] == -1299
        assert netflix[0]["intervall"] == "monatlich"
        assert netflix[0]["schon_gespeichert"] is False


def test_speichern_und_plan(tmp_path):
    with _client(tmp_path) as c:
        # Serie manuell speichern (monatlich, ab 2026-07-05)
        r = c.post("/api/wiederkehr", json={
            "name": "Netflix", "betrag": "12,99", "richtung": "ausgabe",
            "intervall_tage": 30, "intervall": "monatlich",
            "naechste_faelligkeit": "2026-07-05", "schluessel": "netflix"}).json()
        assert r["ok"]
        # erscheint in der gespeicherten Liste + Monatsbelastung
        liste = c.get("/api/wiederkehr").json()
        assert any(s["name"] == "Netflix" for s in liste["gespeichert"])
        assert liste["monatsbelastung"]["ausgaben"] == 1299
        # Abo-Kalender-Hilfen: Jahreskosten + „kündigen?"-Kandidat (teuerstes Abo)
        netflix = next(s for s in liste["gespeichert"] if s["name"] == "Netflix")
        assert netflix["jahres_kosten"] == round(-1299 * 365 / 30)
        assert netflix["kuendigen_kandidat"] is True       # einziges/teuerstes Ausgabe-Abo
        # Plan über Q3 → 3 Fälligkeiten
        plan = c.get("/api/wiederkehr/plan?von=2026-07-01&bis=2026-09-30").json()
        assert len(plan["termine"]) == 3
        assert plan["ausgaben"] == 1299 * 3
        assert plan["termine"][0]["betrag_text"] == "-12.99"


def test_serie_validierung_und_loeschen(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/wiederkehr", json={
            "name": "X", "betrag": "5", "richtung": "quatsch"}).status_code == 400
        sid = c.post("/api/wiederkehr", json={
            "name": "Strom", "betrag": "89,00", "richtung": "ausgabe"}).json()["id"]
        assert c.delete(f"/api/wiederkehr/{sid}").json()["ok"]
        assert not any(s["id"] == sid for s in c.get("/api/wiederkehr").json()["gespeichert"])
        assert c.delete("/api/wiederkehr/gibtsnicht").status_code == 404
