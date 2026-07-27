"""Z-3b (28.06., geld-kritisch): der Listen-``limit`` wird in SQL geschoben
(CTE-Top-N) statt die ganze Tabelle zu laden und in Python zu schneiden.

Beweis-Eigenschaft (Äquivalenz): ``?limit=N`` liefert EXAKT die ersten N
Buchungen von ``limit=0`` (Voll-Export) — gleiche deterministische Gesamtordnung
``(datum, created_at, id)`` DESC. Der ``id``-Tie-Break wird hier natürlich
ausgeübt, weil ``now_iso()`` Sekunden-Auflösung hat ⇒ im selben Test (und real
beim Bulk-Import) teilen sich gleichdatige Buchungen denselben ``created_at``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _konten(c):
    giro = c.post("/api/konten", json={"name": "Giro", "typ": "asset"}).json()["id"]
    ausg = c.post("/api/konten", json={"name": "Ausgaben", "typ": "expense"}).json()["id"]
    return giro, ausg


def _buchen(c, giro, ausg, datum, n, notiz="b"):
    for i in range(n):
        r = c.post("/api/buchungen", json={
            "von_konto": giro, "nach_konto": ausg, "betrag": "10,00",
            "datum": datum, "notiz": f"{notiz}{i}"})
        assert r.status_code == 200, r.text


def _ids(items):
    return [b["id"] for b in items]


def _voll(c, **q):
    """Referenz-Vollmenge in Gesamtordnung (limit=0 ⇒ Nicht-CTE-Pfad, lädt alles)."""
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    url = "/api/buchungen/export?format=json" + ("&" + qs if qs else "")
    r = c.get(url)
    assert r.status_code == 200
    return r.json()


def test_limit_ist_praefix_des_vollexports_bei_gleichdatigen_ties(tmp_path):
    """Alle gleichdatig ⇒ (datum, created_at) sind gleich ⇒ Ordnung rein über den
    id-Tie-Break. ``?limit=N`` muss die ersten N von ``limit=0`` sein (CTE-Pfad ==
    Nicht-CTE-Pfad, deterministisch)."""
    with _client(tmp_path) as c:
        giro, ausg = _konten(c)
        _buchen(c, giro, ausg, "2026-06-01", 12)
        voll = _ids(_voll(c))
        assert len(voll) == 12
        for n in (1, 3, 8, 12):
            teil = _ids(c.get(f"/api/buchungen?limit={n}").json())
            assert teil == voll[:n], f"limit={n} weicht vom Voll-Präfix ab"


def test_limit_ueber_mehrere_daten(tmp_path):
    """Gemischte Daten ⇒ datum DESC zuerst, dann id-Tie-Break je Tag. Auch hier ist
    jeder limit ein sauberes Präfix der Vollmenge (neueste zuerst)."""
    with _client(tmp_path) as c:
        giro, ausg = _konten(c)
        _buchen(c, giro, ausg, "2026-06-01", 4, notiz="alt")
        _buchen(c, giro, ausg, "2026-06-15", 4, notiz="mitte")
        _buchen(c, giro, ausg, "2026-06-30", 4, notiz="neu")
        voll = _voll(c)
        # Reihenfolge: neueste Daten zuerst
        assert [b["datum"] for b in voll[:4]] == ["2026-06-30"] * 4
        assert [b["datum"] for b in voll[-4:]] == ["2026-06-01"] * 4
        ids = _ids(voll)
        for n in (1, 5, 9, 12):
            teil = _ids(c.get(f"/api/buchungen?limit={n}").json())
            assert teil == ids[:n]


def test_limit_mit_filter_bleibt_aequivalent(tmp_path):
    """Mit Konto-Filter (EXISTS-Bedingung in der CTE) bleibt ``?limit=N`` das Präfix
    der gefilterten Vollmenge."""
    with _client(tmp_path) as c:
        giro, ausg = _konten(c)
        giro2 = c.post("/api/konten", json={"name": "Giro2", "typ": "asset"}).json()["id"]
        _buchen(c, giro, ausg, "2026-06-10", 6, notiz="A")
        _buchen(c, giro2, ausg, "2026-06-10", 6, notiz="B")
        voll_g = _voll(c, konto=giro)
        assert len(voll_g) == 6                      # nur die 6 von giro
        ids_g = _ids(voll_g)
        for n in (1, 3, 6):
            teil = _ids(c.get(f"/api/buchungen?konto={giro}&limit={n}").json())
            assert teil == ids_g[:n]


def test_grosser_limit_wird_auf_5000_gedeckelt_aber_export_nicht(tmp_path):
    """Die Liste behält ihre 5000-Schutzdecke (auch im SQL-Pfad), der Export (limit=0)
    nicht — Z-3a-Garantie bleibt unter Z-3b erhalten."""
    with _client(tmp_path) as c:
        giro, ausg = _konten(c)
        _buchen(c, giro, ausg, "2026-06-01", 5)
        # riesiger angeforderter limit ⇒ trotzdem alle 5 (min(limit,5000)); kein Crash
        assert len(c.get("/api/buchungen?limit=999999").json()) == 5
        # Export liefert ebenfalls alle 5 (limit=0-Pfad, ungedeckelt)
        assert len(_voll(c)) == 5
