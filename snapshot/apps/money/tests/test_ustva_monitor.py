"""§19-Kleinunternehmer-Monitor (M4-2, docs/68 §6/§11). Die Mess-/Warn-Schicht UNTER
dem Vertrag (``test_ustva_vertrag.py`` bleibt der Design-Zaun; ``vertrag.py``
byte-gleich). Schwerpunkte (Akzeptanz docs/68 §11 M4-2):

  * **Abgrenzungsliste Gesamtumsatz VERIFY** — welche UStKategorien in den §19-
    Gesamtumsatz zählen (und welche NIE: KEIN_UMSATZ/Trading, Eingangsseite,
    nicht-steuerbare Umsätze),
  * ``gesamtumsatz_cent`` als reine Funktion auf klassifizierten Summen,
  * **Warnung VOR Überschreiten** — die 80 %/100 %-Ampel an ``schwellen_fuer`` (U-2),
  * **Regime-Schnitt** — der unterjährige 100k-Zwangswechsel (Jahr in zwei Fenster),
  * ``ku_status``-Verwaltung (Form/Grund via ``pruefe_kleinunternehmer`` — nie Form
    ohne Grund; Default Regelbesteuerung) + ``ust_konfig`` (Quartal + Ist, umschaltbar),
  * der HTTP-Monitor über den ECHTEN Ledger (injizierte Bewegungen-Naht, U-4).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from moneyapp import main as mm
from moneyapp.ustva import monitor as mo, persistenz as up, vertrag as uv

USER = mm.DEFAULT_USER_ID
K = uv.UStKategorie


def _client(tmp_path):
    return TestClient(mm.build_app(data_dir=tmp_path))


def _stack(tmp_path):
    app = mm.build_app(data_dir=tmp_path)
    db = mm.Database(mm.default_db_path(mm.APP_ID, data_root=tmp_path))
    return app, db, up.UstSpeicher(db)


# ------------------------------------------- Abgrenzungsliste Gesamtumsatz (VERIFY)

def test_abgrenzungsliste_ist_ausgangsseite_steuerbar():
    """VERIFY erledigt: der Gesamtumsatz (§19 Abs. 2) misst die STEUERBAREN
    Ausgangs-Umsätze; NIE die Eingangsseite, KEIN_UMSATZ (Trading/Privat) oder
    nicht-steuerbare Umsätze."""
    assert mo.GESAMTUMSATZ_KATEGORIEN == frozenset({
        K.UMSATZ_19, K.UMSATZ_7, K.UMSATZ_STFREI_MIT_VST,
        K.UMSATZ_IG_LIEFERUNG, K.UMSATZ_STFREI_OHNE_VST, K.UMSATZ_13B_LEISTENDER})
    # explizit AUSSEN vor (kein „im Zweifel mitzählen"): Systematik-Ausschlüsse
    for aus in (K.KEIN_UMSATZ, K.UMSATZ_EU_B2B, K.UMSATZ_NICHT_STEUERBAR,
                K.EINGANG_VST, K.EINGANG_EUST, K.EINGANG_OHNE_VST,
                K.ERWERB_IG_19, K.ERWERB_IG_7, K.BEZUG_13B):
        assert aus not in mo.GESAMTUMSATZ_KATEGORIEN
    # Vollständigkeit: jede Kategorie ist bewusst drin ODER draußen (eine neue
    # Kategorie erzwingt hier eine Entscheidung — kein stilles Durchrutschen).
    entschieden = mo.GESAMTUMSATZ_KATEGORIEN | {
        K.KEIN_UMSATZ, K.UMSATZ_EU_B2B, K.UMSATZ_NICHT_STEUERBAR,
        K.EINGANG_VST, K.EINGANG_EUST, K.EINGANG_OHNE_VST,
        K.ERWERB_IG_19, K.ERWERB_IG_7, K.BEZUG_13B}
    assert entschieden == set(K)


def test_gesamtumsatz_cent_summiert_nur_abgrenzung():
    """Reine Funktion (docs/68 §6): KEIN_UMSATZ (Trading) + Eingangsseite zählen
    NIE mit, nur die Abgrenzungs-Kategorien."""
    posten = [
        (K.UMSATZ_19, 10_000_00),          # zählt
        (K.UMSATZ_STFREI_OHNE_VST, 5_000_00),  # zählt (konservativ voll)
        (K.KEIN_UMSATZ, 99_000_00),        # Trading/Privat — zählt NIE
        (K.EINGANG_VST, 8_000_00),         # Eingangsseite — zählt NIE
        (K.UMSATZ_EU_B2B, 7_000_00),       # nicht steuerbar — zählt NIE
    ]
    assert mo.gesamtumsatz_cent(posten) == 15_000_00


def test_entgelt_cent_netto_bei_split_vorzeichenrichtig():
    """MIT_SPLIT-Umsatz ⇒ Entgelt = Split-NETTO (ohne USt); splitlos ⇒ voller
    Zufluss. Das Vorzeichen trägt der Ledger-Netto (Entgeltminderung mindert)."""
    k_split = uv.Klassifikation(
        buchung_id="b", ust_kategorie=K.UMSATZ_19, quelle=uv.KlassifikationsQuelle.MANUELL,
        satz_promille=190, split=uv.split_aus_brutto(11900, 190))
    assert mo.entgelt_cent(k_split, 11900) == 10000       # Netto, nicht Brutto
    assert mo.entgelt_cent(k_split, -11900) == -10000     # Storno mindert
    k_frei = uv.Klassifikation(
        buchung_id="b2", ust_kategorie=K.UMSATZ_STFREI_OHNE_VST,
        quelle=uv.KlassifikationsQuelle.MANUELL)
    assert mo.entgelt_cent(k_frei, 50000) == 50000        # voller Zufluss (kein USt-Ausweis)
    k_kein = uv.Klassifikation(
        buchung_id="b3", ust_kategorie=K.KEIN_UMSATZ, quelle=uv.KlassifikationsQuelle.REGEL)
    assert mo.entgelt_cent(k_kein, 77000) == 0            # außerhalb der Abgrenzung


# ---------------------------------------------- Warn-Stufen (Warnung VOR Überschreiten)

def test_warnstufe_80_100_an_echter_schwelle():
    """Die 80 %/100 %-Ampel an der ECHTEN Jahres-Schwelle (U-2, nie Konstante):
    Warnung (GELB) VOR dem Überschreiten, ROT erst ab 100 %."""
    grenze = uv.schwellen_fuer(2026).laufend_max_cent    # 100.000 € = 10_000_000 ct
    assert mo.warnstufe(0, grenze)["ampel"] == "gruen"
    assert mo.warnstufe(7_999_999, grenze)["ampel"] == "gruen"        # 79,99 % → noch grün
    gelb = mo.warnstufe(8_000_000, grenze)                            # exakt 80 %
    assert gelb["ampel"] == "gelb" and gelb["warnung"] is True and gelb["ueberschritten"] is False
    assert mo.warnstufe(9_999_999, grenze)["ampel"] == "gelb"        # knapp drunter → noch Warnung
    rot = mo.warnstufe(grenze, grenze)                               # exakt 100 %
    assert rot["ampel"] == "rot" and rot["ueberschritten"] is True
    assert mo.warnstufe(grenze + 1, grenze)["ampel"] == "rot"


def test_warnstufe_prozent_und_grenze_null():
    s = mo.warnstufe(2_000_000, uv.schwellen_fuer(2026).vorjahr_max_cent)  # 20k von 25k
    assert s["anteil_prozent"] == 80.0 and s["ampel"] == "gelb"
    # Grenze 0 ⇒ KonfigFehler (schützt vor kaputter Schwellen-Zeile)
    import pytest
    with pytest.raises(uv.KonfigFehler):
        mo.warnstufe(1, 0)


def test_schlimmste_ampel():
    g = mo.warnstufe(0, 10_000_000)
    gelb = mo.warnstufe(8_000_000, 10_000_000)
    rot = mo.warnstufe(10_000_000, 10_000_000)
    assert mo.schlimmste_ampel(g, g) == "gruen"
    assert mo.schlimmste_ampel(g, gelb) == "gelb"
    assert mo.schlimmste_ampel(gelb, rot) == "rot"
    assert mo.schlimmste_ampel() == "gruen"


# --------------------------------------------------- Regime-Schnitt (100k-Zwangswechsel)

def test_regime_schnitt_teilt_jahr_am_ueberschreitenden_umsatz():
    """Unterjähriger 100k-Zwangswechsel: bis zum VORTAG §19, AB dem
    überschreitenden Umsatz (einschließlich) Regelbesteuerung (JStG 2024)."""
    grenze = uv.schwellen_fuer(2026).laufend_max_cent
    posten = [
        ("2026-03-01", K.UMSATZ_STFREI_OHNE_VST, 6_000_000),   # kumuliert 6M ≤ 10M
        ("2026-07-15", K.UMSATZ_19, 5_000_000),                # kumuliert 11M > 10M ⇒ Schnitt
        ("2026-09-01", K.UMSATZ_7, 1_000_000),
    ]
    r = mo.regime_schnitt(2026, posten, grenze)
    assert r["ueberschritten"] is True and r["schnitt_datum"] == "2026-07-15"
    assert r["kleinunternehmer_fenster"] == ["2026-01-01", "2026-07-14"]
    assert r["regelbesteuerung_fenster"] == ["2026-07-15", "2026-12-31"]
    assert r["kumuliert_cent"] == 11_000_000


def test_regime_schnitt_kein_ueberschreiten_ein_fenster():
    grenze = uv.schwellen_fuer(2026).laufend_max_cent
    posten = [("2026-04-01", K.UMSATZ_19, 3_000_000),
              ("2026-08-01", K.UMSATZ_7, 4_000_000)]      # kumuliert 7M ≤ 10M
    r = mo.regime_schnitt(2026, posten, grenze)
    assert r["ueberschritten"] is False and r["schnitt_datum"] == ""
    assert r["kleinunternehmer_fenster"] == ["2026-01-01", "2026-12-31"]
    assert r["regelbesteuerung_fenster"] is None


def test_regime_schnitt_erster_umsatz_ueberschreitet_kein_ku_fenster():
    """Kippt schon der erste Umsatz über 100k, gibt es kein §19-Fenster (der Vortag
    läge im Vorjahr) — das ganze Jahr ist Regelbesteuerung."""
    grenze = uv.schwellen_fuer(2026).laufend_max_cent
    r = mo.regime_schnitt(2026, [("2026-01-01", K.UMSATZ_19, 11_000_000)], grenze)
    assert r["ueberschritten"] is True and r["kleinunternehmer_fenster"] is None
    assert r["regelbesteuerung_fenster"] == ["2026-01-01", "2026-12-31"]


def test_regime_schnitt_ignoriert_nicht_abgrenzungs_kategorien():
    """KEIN_UMSATZ/Eingangsseite fließen NICHT in die Kumulation (sonst falscher
    Zwangswechsel)."""
    grenze = uv.schwellen_fuer(2026).laufend_max_cent
    posten = [("2026-02-01", K.KEIN_UMSATZ, 50_000_000),      # Trading — ignoriert
              ("2026-03-01", K.EINGANG_VST, 20_000_000),      # Eingang — ignoriert
              ("2026-06-01", K.UMSATZ_19, 4_000_000)]         # nur das zählt
    r = mo.regime_schnitt(2026, posten, grenze)
    assert r["ueberschritten"] is False and r["kumuliert_cent"] == 4_000_000


# ------------------------------------------------------ umsatz_posten (Klassifikation)

def test_umsatz_posten_klassifiziert_und_zaehlt_offene():
    """Brücke Bewegungen → Posten: klassifiziert (Regel/Override), sammelt nur
    Abgrenzungs-Posten, zählt die offenen (unklassifizierten) ehrlich mit."""
    regeln = {"kat-umsatz": uv.KlassifikationsRegel(
        kategorie_id="kat-umsatz", ust_kategorie=K.UMSATZ_STFREI_OHNE_VST)}
    bewegungen = [
        {"id": "u1", "datum": "2026-05-01", "netto": 500000, "kategorie_id": "kat-umsatz"},  # zählt
        {"id": "t1", "datum": "2026-05-02", "netto": 0, "kategorie_id": "x"},                # KEIN_UMSATZ (netto 0)
        {"id": "o1", "datum": "2026-05-03", "netto": -3000, "kategorie_id": "unbekannt"},    # offen
    ]
    posten, offen = mo.umsatz_posten(bewegungen, regeln, {})
    assert offen == 1
    assert posten == [("2026-05-01", K.UMSATZ_STFREI_OHNE_VST, 500000)]


# ------------------------------------------------------------ ku_status (HTTP-CRUD)

def test_ku_status_default_ist_regelbesteuerung_unkonfiguriert(tmp_path):
    """Gate G-M4-STATUS (David 06.07.): ohne gespeicherten Status = Regelbesteuerung
    (UStVA fällig), als ``konfiguriert=False`` markiert."""
    with _client(tmp_path) as c:
        d = c.get("/api/ust/ku-status?jahr=2026").json()
        assert d["form"] == "regelbesteuerung" and d["konfiguriert"] is False
        assert d["grund"] == "" and d["befund_text"]


def test_ku_status_leitet_form_aus_fakten_ab_nie_ohne_grund(tmp_path):
    """Form + Grund kommen IMMER aus ``pruefe_kleinunternehmer`` (nie Form ohne
    Grund). Schwellen eingehalten ⇒ KU; Vorjahr > 25 k ⇒ Regel; Verzicht ⇒ Regel."""
    with _client(tmp_path) as c:
        # unter der Vorjahres-Grenze, kein Verzicht ⇒ Kleinunternehmer
        ku = c.post("/api/ust/ku-status", json={"jahr": 2026, "vorjahr_umsatz_cent": 2_500_000}).json()
        assert ku["form"] == "kleinunternehmer" and ku["grund"] == "schwellen_eingehalten"
        assert ku["konfiguriert"] is True and ku["befund_text"]
        # Vorjahr über 25 k ⇒ Regelbesteuerung/Vorjahr (Davids Default-Weg 1)
        reg = c.post("/api/ust/ku-status", json={"jahr": 2026, "vorjahr_umsatz_cent": 2_500_001}).json()
        assert reg["form"] == "regelbesteuerung" and reg["grund"] == "vorjahr_ueberschritten"
        # Upsert je Jahr: das erneute POST hat ersetzt, keine Dublette
        assert c.get("/api/ust/ku-status?jahr=2026").json()["grund"] == "vorjahr_ueberschritten"
        # §19-Verzicht ⇒ Regelbesteuerung/Verzicht (Davids Default-Weg 2)
        vz = c.post("/api/ust/ku-status", json={
            "jahr": 2026, "vorjahr_umsatz_cent": 0, "verzicht_ab_jahr": 2025}).json()
        assert vz["form"] == "regelbesteuerung" and vz["grund"] == "verzicht"
        assert vz["verzicht_ab_jahr"] == 2025


def test_ku_status_loeschen_faellt_auf_default(tmp_path):
    with _client(tmp_path) as c:
        c.post("/api/ust/ku-status", json={"jahr": 2026, "vorjahr_umsatz_cent": 2_500_000})
        assert c.get("/api/ust/ku-status?jahr=2026").json()["konfiguriert"] is True
        assert c.delete("/api/ust/ku-status/2026").json()["ok"]
        d = c.get("/api/ust/ku-status?jahr=2026").json()
        assert d["konfiguriert"] is False and d["form"] == "regelbesteuerung"
        assert c.delete("/api/ust/ku-status/2026").status_code == 404


def test_ku_status_altrecht_und_negativ_werfen(tmp_path):
    """U-2: Jahr < 2025 ⇒ 400 (Alt-Recht nicht modelliert); negativer Umsatz ⇒ 400."""
    with _client(tmp_path) as c:
        assert c.post("/api/ust/ku-status", json={"jahr": 2024, "vorjahr_umsatz_cent": 0}).status_code == 400
        assert c.post("/api/ust/ku-status", json={"jahr": 2026, "vorjahr_umsatz_cent": -1}).status_code == 400


# ------------------------------------------------------ ust_konfig (HTTP-CRUD)

def test_konfig_default_quartal_ist_umschaltbar(tmp_path):
    """Gate G-M4-ZEITRAUM: Default Quartal + Ist + ohne Dauerfrist; umschaltbar;
    SOLL-Versteuerung ist gesperrt (v1, U-8) ⇒ 400."""
    with _client(tmp_path) as c:
        d = c.get("/api/ust/konfig").json()
        assert d["zeitraum_typ"] == "quartal" and d["besteuerung"] == "ist"
        assert d["dauerfrist"] is False and d["konfiguriert"] is False
        # umschalten auf Monat + Dauerfrist
        u = c.post("/api/ust/konfig", json={
            "zeitraum_typ": "monat", "dauerfrist": True, "besteuerung": "ist"}).json()
        assert u["zeitraum_typ"] == "monat" and u["dauerfrist"] is True and u["konfiguriert"] is True
        assert c.get("/api/ust/konfig").json()["zeitraum_typ"] == "monat"
        # SOLL ist gesperrt
        assert c.post("/api/ust/konfig", json={
            "zeitraum_typ": "quartal", "besteuerung": "soll"}).status_code == 400
        # unbekannter Typ ⇒ 400
        assert c.post("/api/ust/konfig", json={"zeitraum_typ": "quatsch"}).status_code == 400


# ------------------------------------------- Gesamtumsatz-Monitor über den echten Ledger

def test_ku_monitor_misst_klassifizierten_zufluss(tmp_path):
    """Der HTTP-Monitor liest den echten Ledger (injizierte Naht, U-4): ein
    klassifizierter Umsatz zählt, eine offene Buchung nicht (aber als Hinweis),
    Trading/KEIN_UMSATZ nie."""
    with _client(tmp_path) as c:
        bank = c.post("/api/konten", json={"name": "Bank", "typ": "asset"}).json()["id"]
        umsatz = c.post("/api/konten", json={"name": "Umsatz", "typ": "income"}).json()["id"]
        # 5.000 € Einnahme im Jahr 2026, als steuerfreier Umsatz klassifiziert
        c.post("/api/buchungen", json={"von_konto": umsatz, "nach_konto": bank,
                                       "betrag": "5000,00", "datum": "2026-05-10"})
        offen = c.get("/api/ust/offene?jahr=2026&typ=quartal&nummer=2").json()
        bid = offen["offen"][0]["id"]
        c.post("/api/ust/klassifikationen", json={"buchung_id": bid,
                                                  "ust_kategorie": "umsatz_stfrei_ohne_vst"})
        # eine zweite Einnahme bleibt OFFEN (unklassifiziert)
        c.post("/api/buchungen", json={"von_konto": umsatz, "nach_konto": bank,
                                       "betrag": "1000,00", "datum": "2026-06-01"})
        m = c.get("/api/ust/ku-monitor?jahr=2026").json()
        assert m["gemessen"]["laufend_cent"] == 500000        # nur der klassifizierte Umsatz
        assert m["gemessen"]["offen_laufend"] == 1 and m["gemessen"]["hinweis_offen"] is True
        assert m["gemessen"]["vorjahr_cent"] == 0
        assert m["ampel"] == "gruen"                          # 5.000 € weit unter 100k
        assert m["warn"]["laufend_100k"]["ampel"] == "gruen"
        assert m["befund_gemessen"]["form"] == "kleinunternehmer"
        assert m["schwellen"]["laufend_max_cent"] == 10_000_000
        assert m["regime_schnitt"]["ueberschritten"] is False
        # Status noch unkonfiguriert ⇒ erklärter Default Regelbesteuerung
        assert m["status_erklaert"]["form"] == "regelbesteuerung"


def test_ku_monitor_altrecht_400(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/ust/ku-monitor?jahr=2024").status_code == 400


# ------------------------------------------------------ U-4 + DSGVO-Lösch-Kaskade

def test_ku_status_und_konfig_tragen_dsgvo_shape(tmp_path):
    """ku_status + ust_konfig tragen user_id+deleted_at ⇒ generische DSGVO-Kaskade
    OHNE Per-App-Code; der Ledger-Kern bleibt unberührt (U-4)."""
    app, db, sp = _stack(tmp_path)
    hat_deleted = dict(db.user_tabellen())
    assert hat_deleted.get("ku_status") is True and hat_deleted.get("ust_konfig") is True
    sp.ku_status_setzen(USER, 2026, 2_500_000, 0)
    sp.konfig_setzen(USER, uv.VoranmeldungsKonfig(zeitraum_typ=uv.ZeitraumTyp.MONAT))
    exp = db.export_user(USER)
    assert exp["ku_status"] and exp["ust_konfig"]
    zaehler = db.soft_delete_user(USER)
    assert zaehler.get("ku_status") and zaehler.get("ust_konfig")
    with TestClient(app) as c:
        assert c.get("/api/ust/ku-status?jahr=2026").json()["konfiguriert"] is False
        assert c.get("/api/ust/konfig").json()["konfiguriert"] is False
