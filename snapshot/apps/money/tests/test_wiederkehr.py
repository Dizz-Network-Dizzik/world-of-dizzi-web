"""Tests der reinen Wiederkehr-Erkennung/Planung — deterministisch, ohne DB.
Beträge sind netto-Minor-Units (signiert: − = Ausgabe)."""

from __future__ import annotations

from datetime import date, timedelta

from moneyapp.wiederkehr import (erkenne_serien, monatsbelastung, plane)


def _monatsreihe(name, betrag, n, start="2026-01-05", tag_jitter=0):
    """n monatliche Buchungen ab start (echte Monatsabstände ~30 Tage)."""
    d0 = date.fromisoformat(start)
    out = []
    for i in range(n):
        d = d0 + timedelta(days=round(i * 30.4) + (i % 2) * tag_jitter)
        out.append({"datum": d.isoformat(), "betrag": betrag,
                    "gegenpartei": name, "verwendungszweck": ""})
    return out


def test_erkennt_monatliches_abo():
    bs = _monatsreihe("Netflix", -1299, 6)
    serien = erkenne_serien(bs, heute="2026-07-01")
    assert len(serien) == 1
    s = serien[0]
    assert s["name"] == "Netflix" and s["betrag"] == -1299
    assert s["richtung"] == "ausgabe" and s["intervall"] == "monatlich"
    assert s["anzahl"] == 6 and s["konfidenz"] >= 0.7
    # nächste Fälligkeit liegt in der Zukunft
    assert s["naechste_faellig"] > "2026-06-01"


def test_unregelmaessige_einkaeufe_kein_abo():
    # REWE: schwankende Beträge + unregelmäßige Abstände → keine Serie
    tage = ["2026-01-03", "2026-01-04", "2026-01-19", "2026-02-02", "2026-02-03"]
    betr = [-4329, -1290, -8800, -2100, -6500]
    bs = [{"datum": t, "betrag": b, "gegenpartei": "REWE", "verwendungszweck": ""}
          for t, b in zip(tage, betr)]
    serien = erkenne_serien(bs, heute="2026-03-01")
    assert serien == []                              # zu unregelmäßig/instabil


def test_einnahme_und_ausgabe_getrennt():
    lohn = [{"datum": d, "betrag": 250000, "gegenpartei": "Arbeitgeber", "verwendungszweck": ""}
            for d in ("2026-01-28", "2026-02-26", "2026-03-30", "2026-04-29")]
    serien = erkenne_serien(lohn, heute="2026-05-10")
    assert len(serien) == 1 and serien[0]["richtung"] == "einnahme"
    assert serien[0]["betrag"] == 250000


def test_weniger_als_min_treffer():
    bs = _monatsreihe("X", -500, 2)
    assert erkenne_serien(bs, heute="2026-04-01") == []


def test_plane_expandiert_termine():
    serien = [{"name": "Netflix", "betrag": -1299, "intervall_tage": 30,
               "naechste_faelligkeit": "2026-07-05", "schluessel": "netflix",
               "richtung": "ausgabe"}]
    plan = plane(serien, "2026-07-01", "2026-09-30")
    # 05.07, 04.08, 03.09 → 3 Termine
    assert len(plan["termine"]) == 3
    assert plan["ausgaben"] == 1299 * 3 and plan["saldo"] == -1299 * 3
    assert plan["termine"][0]["datum"] == "2026-07-05"


def test_plane_monatlich_kalender_bewusst():
    """P2.2b: monatlich benannte Serie schreitet ECHTE Kalendermonate (gleicher
    Tag-im-Monat) statt +30 Tage — kein Drift."""
    serien = [{"name": "Netflix", "betrag": -1299, "intervall": "monatlich",
               "intervall_tage": 30, "naechste_faelligkeit": "2026-07-05",
               "schluessel": "netflix", "richtung": "ausgabe"}]
    plan = plane(serien, "2026-07-01", "2026-10-31")
    assert [t["datum"] for t in plan["termine"]] == [
        "2026-07-05", "2026-08-05", "2026-09-05", "2026-10-05"]   # nicht 08-04/09-03


def test_plane_monatlich_31er_driftfrei():
    """31.-Anker: 28. Feb geklemmt, danach wieder 31. (DTSTART-verankert über den
    geteilten recurrence-Kern) — nicht 28. März."""
    serien = [{"name": "Miete", "betrag": -90000, "intervall": "monatlich",
               "intervall_tage": 30, "naechste_faelligkeit": "2026-01-31",
               "schluessel": "miete", "richtung": "ausgabe"}]
    plan = plane(serien, "2026-01-01", "2026-04-30")
    assert [t["datum"] for t in plan["termine"]] == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_plane_jaehrlich_kalender_bewusst():
    serien = [{"name": "Versicherung", "betrag": -12000, "intervall": "jaehrlich",
               "intervall_tage": 365, "naechste_faelligkeit": "2026-03-15",
               "schluessel": "v", "richtung": "ausgabe"}]
    plan = plane(serien, "2026-01-01", "2028-12-31")
    assert [t["datum"] for t in plan["termine"]] == [
        "2026-03-15", "2027-03-15", "2028-03-15"]                 # gleicher Tag, nicht +365 d-Drift


def test_plane_tages_serie_unveraendert():
    """Ohne Kalender-Label (nur intervall_tage) bleibt der Tages-Schritt 1:1."""
    serien = [{"name": "X", "betrag": -500, "intervall_tage": 14,
               "naechste_faelligkeit": "2026-07-06", "schluessel": "x",
               "richtung": "ausgabe"}]
    plan = plane(serien, "2026-07-01", "2026-08-15")
    assert [t["datum"] for t in plan["termine"]] == [
        "2026-07-06", "2026-07-20", "2026-08-03"]                 # +14 d, tagesgenau


def test_monatsbelastung_normiert():
    serien = [
        {"betrag": -1299, "intervall_tage": 30},       # ~ -1299/Monat
        {"betrag": -12000, "intervall_tage": 365},     # jährlich → ~ -986/Monat
        {"betrag": 250000, "intervall_tage": 30},      # Gehalt
    ]
    mb = monatsbelastung(serien)
    assert mb["ausgaben"] == 1299 + round(12000 * 30 / 365)
    assert mb["einnahmen"] == 250000
    assert mb["saldo"] == mb["einnahmen"] - mb["ausgaben"]
