"""Trading-Steuer-Engine (V14, docs/26 §13): die rechtlichen Mechaniken nach
deutschem Recht 2025/26. Referenzzahlen aus der Recherche (§ 32d EStG, § 20, § 23).
Beträge in Cent."""

from __future__ import annotations

from moneyapp import trading_steuer as ts


# ===================== Abgeltungsteuer-Formel (§ 32d Abs. 1) =====================
def test_abgeltungsteuer_ohne_kirchensteuer():
    # 1.000 € Bemessung ⇒ 25 % = 250,00 €; Soli 5,5 % = 13,75 €.
    r = ts.abgeltungsteuer(100_000, kirchensteuer_satz=0.0)
    assert r["abgeltungsteuer"] == 25_000
    assert r["soli"] == round(25_000 * 0.055)        # 1.375
    assert r["kirchensteuer"] == 0
    assert r["gesamt"] == round(25_000 * 1.055)


def test_abgeltungsteuer_mit_kirchensteuer_9_prozent():
    # Referenz: bei KiSt 9 % sinkt die AbgSt auf 24,45 % (= e/4,09).
    r = ts.abgeltungsteuer(100_000, kirchensteuer_satz=0.09)
    assert r["abgeltungsteuer"] == round(100_000 / 4.09)   # 24.450 (244,50 €)
    assert r["abgeltungsteuer"] == 24_450
    # Gesamtbelastung ~27,99 % der Bemessung
    assert abs(r["gesamt"] - 27_995) <= 2


def test_abgeltungsteuer_null_und_negativ():
    assert ts.abgeltungsteuer(0)["gesamt"] == 0
    assert ts.abgeltungsteuer(-5000)["gesamt"] == 0


def test_abgeltungsteuer_posten_summieren_exakt_zum_gesamt():
    # Audit-Fund: eine vorgelegte Aufstellung muss konsistent sein.
    for e in (50_000, 123_456, 99_999, 1_000_000, 777):
        for k in (0.0, 0.08, 0.09):
            r = ts.abgeltungsteuer(e, k)
            assert r["gesamt"] == r["abgeltungsteuer"] + r["soli"] + r["kirchensteuer"]


# ===================== § 20 Futures (Sparer-Pauschbetrag) =====================
def test_futures_unter_pauschbetrag_steuerfrei():
    r = ts.steuer_futures(80_000)                    # 800 € < 1.000 €
    assert r["steuerpflichtig"] == 0 and r["ueber_schwelle"] is False
    assert r["freibetrag_genutzt"] == 80_000 and r["gesamt"] == 0


def test_futures_ueber_pauschbetrag_nur_ueberschuss():
    # 1.500 € Netto, Pauschbetrag 1.000 € ⇒ 500 € steuerpflichtig.
    r = ts.steuer_futures(150_000, kirchensteuer_satz=0.09)
    assert r["freibetrag_genutzt"] == 100_000
    assert r["steuerpflichtig"] == 50_000 and r["ueber_schwelle"] is True
    assert r["abgeltungsteuer"] == round(50_000 / 4.09)


def test_futures_verlust_erzeugt_vortrag():
    r = ts.steuer_futures(-40_000)                   # 400 € Verlust
    assert r["steuerpflichtig"] == 0 and r["verlustvortrag"] == 40_000
    assert r["gesamt"] == 0


def test_futures_pauschbetrag_rest_kleiner():
    # Nur noch 300 € Pauschbetrag frei (Rest anderweitig genutzt) ⇒ mehr steuerpflichtig.
    r = ts.steuer_futures(100_000, pauschbetrag_rest_cent=30_000)
    assert r["freibetrag_genutzt"] == 30_000 and r["steuerpflichtig"] == 70_000


# ===================== § 23 Spot (Freigrenze alles-oder-nichts) =====================
def test_spot_unter_freigrenze_steuerfrei():
    r = ts.steuer_spot(99_999)                       # 999,99 € ≤ 1.000 €
    assert r["steuerpflichtig"] == 0 and r["unter_freigrenze"] is True
    assert r["steuer_gesamt"] == 0


def test_spot_ueber_freigrenze_alles_steuerpflichtig():
    # 1.000,01 € ⇒ Freigrenze (alles-oder-nichts) ⇒ GESAMTER Gewinn steuerpflichtig.
    r = ts.steuer_spot(100_001, persoenlicher_satz=0.42)
    assert r["unter_freigrenze"] is False
    assert r["steuerpflichtig"] == 100_001          # nicht nur der Überschuss!
    assert r["steuer_gesamt"] == round(100_001 * 0.42)


def test_spot_genau_freigrenze_steuerpflichtig():
    # Audit-Fund: § 23 „weniger als 1.000 €" ⇒ bei GENAU 1.000,00 € steuerpflichtig.
    r = ts.steuer_spot(100_000, persoenlicher_satz=0.42)
    assert r["unter_freigrenze"] is False
    assert r["steuerpflichtig"] == 100_000
    assert r["steuer_gesamt"] == round(100_000 * 0.42)
    # ein Cent darunter ⇒ steuerfrei
    assert ts.steuer_spot(99_999)["unter_freigrenze"] is True


def test_spot_verlust():
    r = ts.steuer_spot(-20_000)
    assert r["steuerpflichtig"] == 0 and r["verlustvortrag"] == 20_000


# ===================== § 23 Haltefrist (kalendarisch) =====================
def test_haltefrist_innerhalb_steuerpflichtig():
    assert ts.spot_steuerpflichtig("2025-01-01", "2025-06-01") is True


def test_haltefrist_am_jahrestag_noch_steuerpflichtig():
    # Verkauf exakt 1 Jahr später ⇒ noch steuerpflichtig (Frist „mehr als ein Jahr").
    assert ts.spot_steuerpflichtig("2025-01-01", "2026-01-01") is True
    # ein Tag später ⇒ steuerfrei
    assert ts.spot_steuerpflichtig("2025-01-01", "2026-01-02") is False


def test_haltefrist_klar_ueber_jahr_steuerfrei():
    assert ts.spot_steuerpflichtig("2024-01-01", "2025-06-01") is False


def test_haltefrist_ohne_kaufdatum_konservativ():
    assert ts.spot_steuerpflichtig(None, "2025-06-01") is True


def test_haltefrist_schaltjahr():
    # Kauf am 29.02. ⇒ Grenze 28.02. des Folgejahres (kein Crash).
    assert ts.spot_steuerpflichtig("2024-02-29", "2025-02-28") is True
    assert ts.spot_steuerpflichtig("2024-02-29", "2025-03-02") is False


# ===================== Jahres-Aggregation =====================
def _r(datum, regime, betrag, kauf=None):
    d = {"datum": datum, "regime": regime, "betrag_minor": betrag}
    if kauf:
        d["kauf_datum"] = kauf
    return d


def test_jahres_auswertung_trennt_regime_und_jahr():
    real = [
        _r("2026-02-01", "futures", 120_000),     # +1.200 €
        _r("2026-03-01", "futures", -20_000),     # −200 €  ⇒ Netto Futures 1.000 €
        _r("2026-04-01", "spot", 150_000, kauf="2026-01-01"),  # Frist ⇒ steuerbar
        _r("2026-05-01", "spot", 90_000, kauf="2024-01-01"),   # >1 J ⇒ steuerfrei
        _r("2025-12-31", "futures", 999_999),     # anderes Jahr ⇒ ignoriert
    ]
    a = ts.jahres_auswertung(real, 2026, persoenlicher_satz=0.42, kirchensteuer_satz=0.09)
    assert a["futures"]["netto"] == 100_000           # 1.200 − 200
    assert a["futures"]["steuerpflichtig"] == 0       # genau am Pauschbetrag
    assert a["spot"]["netto"] == 150_000              # nur die Frist-Position
    assert a["spot"]["steuerfrei_haltefrist"] == 90_000
    assert a["spot"]["unter_freigrenze"] is False     # 1.500 € > 1.000 €
    assert a["spot"]["steuer_gesamt"] == round(150_000 * 0.42)
    assert a["anzahl"] == {"futures": 2, "spot": 2}
    assert a["steuer_gesamt"] == a["futures"]["gesamt"] + a["spot"]["steuer_gesamt"]


def test_jahres_auswertung_warnungen():
    a = ts.jahres_auswertung([_r("2026-06-01", "futures", 150_000)], 2026)
    assert any("Pauschbetrag" in w for w in a["warnungen"])
    b = ts.jahres_auswertung([_r("2026-06-01", "futures", 50_000)], 2026)
    assert any("noch" in w for w in b["warnungen"])    # Puffer-Hinweis


def test_zelle_md_injection_backslash_pipe():
    """G5 (28.06.): _zelle muss Backslashes VOR den Pipes escapen, sonst macht eine
    Eingabe '\\|' aus dem Pipe wieder einen AKTIVEN Spalten-Trenner im Finanzamt-
    Markdown-Bericht. Jeder '|' im Output muss escaped sein (ungerade Zahl Backslashes
    davor)."""
    def aktiver_pipe(out: str) -> bool:
        for i, ch in enumerate(out):
            if ch == "|":
                bs = 0; j = i - 1
                while j >= 0 and out[j] == "\\":
                    bs += 1; j -= 1
                if bs % 2 == 0:           # gerade (inkl. 0) Backslashes davor -> Pipe aktiv
                    return True
        return False
    for boese in ["a\\|b", "evil\\|INJEKT|spalte", "x | y", "\\\\|z", "normal"]:
        assert not aktiver_pipe(ts._zelle(boese)), f"aktiver Pipe in _zelle({boese!r})"
    assert "\n" not in ts._zelle("a\nb") and "\r" not in ts._zelle("a\rb")
    assert ts._zelle("") == "—" and ts._zelle("   ") == "—"


# ===================== Kapital-Verlauf =====================
def test_kapital_stand():
    bew = [
        {"art": "einlage", "betrag_minor": 500_000, "datum": "2026-01-01"},   # 5.000 €
        {"art": "einlage", "betrag_minor": 200_000, "datum": "2026-02-01"},   # +2.000 €
        {"art": "entnahme", "betrag_minor": 100_000, "datum": "2026-03-01"},  # −1.000 €
        {"art": "bewertung", "betrag_minor": 720_000, "datum": "2026-03-15"}, # Wert 7.200 €
        {"art": "bewertung", "betrag_minor": 680_000, "datum": "2026-02-15"}, # älter ⇒ ignoriert
    ]
    s = ts.kapital_stand(bew)
    assert s["einlagen"] == 700_000 and s["entnahmen"] == 100_000
    assert s["investiert"] == 600_000
    assert s["aktueller_wert"] == 720_000             # jüngste Bewertung
    assert s["unrealisiert"] == 120_000               # 7.200 − 6.000


def test_kapital_stand_ohne_bewertung():
    s = ts.kapital_stand([{"art": "einlage", "betrag_minor": 500_000, "datum": "2026-01-01"}])
    assert s["bewertet"] is False and s["aktueller_wert"] == 500_000
    assert s["unrealisiert"] == 0


def test_kapital_stand_gleichtag_deterministisch():
    """Audit Runde 3: zwei Bewertungen am selben Tag ⇒ deterministisch gewinnt die
    zuletzt ERFASSTE (created_at), unabhängig von Eingabe-/DB-Reihenfolge."""
    bew = [
        {"art": "bewertung", "betrag_minor": 600_000, "datum": "2026-03-15",
         "created_at": "2026-03-15T10:00:00Z"},
        {"art": "bewertung", "betrag_minor": 700_000, "datum": "2026-03-15",
         "created_at": "2026-03-15T12:00:00Z"},
    ]
    assert ts.kapital_stand(bew)["aktueller_wert"] == 700_000
    assert ts.kapital_stand(list(reversed(bew)))["aktueller_wert"] == 700_000


# ===================== Jahres-Bericht (Anlage KAP/SO) =====================
def test_eur_deutsche_schreibweise():
    assert ts._eur(123_456) == "1.234,56 €"
    assert ts._eur(-5_000) == "-50,00 €"
    assert ts._eur(0) == "0,00 €"


def test_jahres_bericht_markdown():
    posten = [
        {"datum": "2026-02-01", "regime": "futures", "betrag_minor": 150_000,
         "beschreibung": "Future X", "kauf_datum": ""},
        {"datum": "2026-04-01", "regime": "spot", "betrag_minor": 120_000,
         "beschreibung": "Spot A", "kauf_datum": "2026-01-01"},
        {"datum": "2026-05-01", "regime": "spot", "betrag_minor": 50_000,
         "beschreibung": "Spot B (>1J)", "kauf_datum": "2024-01-01"},
    ]
    a = ts.jahres_auswertung(
        [{"datum": p["datum"], "regime": p["regime"], "betrag_minor": p["betrag_minor"],
          "kauf_datum": p["kauf_datum"] or None} for p in posten],
        2026, persoenlicher_satz=0.42, kirchensteuer_satz=0.09)
    stand = ts.kapital_stand([{"art": "einlage", "betrag_minor": 500_000, "datum": "2026-01-01"}])
    md = ts.jahres_bericht_markdown(2026, a, posten, stand)
    assert "Anlage KAP" in md and "Anlage SO" in md
    assert "§ 20" in md and "§ 23" in md
    assert "Future X" in md and "Spot A" in md
    assert "steuerfrei (>1 J.)" in md        # Spot B außerhalb Haltefrist
    assert "Steuerberatung" in md            # Disclaimer vorhanden
    assert "Eingesetztes Kapital" in md      # Kapital-Block, weil stand übergeben


def test_bericht_escaped_pipe_und_zeilenumbruch():
    """Audit-2-Fund: ein „A | B"- oder mehrzeiliger Beschreibungstext darf die
    Markdown-Tabelle nicht zerschießen (der Bericht geht ans Finanzamt)."""
    posten = [{"datum": "2026-02-01", "regime": "futures", "betrag_minor": 150_000,
               "beschreibung": "REWE | Edeka\nZeile2", "kauf_datum": ""}]
    a = ts.jahres_auswertung(
        [{"datum": p["datum"], "regime": p["regime"], "betrag_minor": p["betrag_minor"],
          "kauf_datum": None} for p in posten], 2026)
    md = ts.jahres_bericht_markdown(2026, a, posten)
    zeile = next(l for l in md.splitlines() if "REWE" in l)
    assert "\\|" in zeile                    # Pipe escaped (zählt nicht als Spaltentrenner)
    # nur die STRUKTUR-Pipes (ohne escaped \|) ⇒ genau 4 für 3 Spalten
    assert zeile.replace("\\|", "").count("|") == 4
    assert "Zeile2" in zeile                 # Umbruch zu Leerzeichen ⇒ alles in EINER Zeile
