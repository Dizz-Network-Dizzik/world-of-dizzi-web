"""Vertrags-Tests M-4 (docs/68): UStVA-Datenschicht + §19 + Vorsteuer, Stufe 0.

Lib-/netz-/DB-frei — reine Typ-/Wächter-Verträge. Prüft die Härtungs-
Invarianten U-1…U-8 als Code, inkl. der e2e-Kopplung an docs/65 (M-1):
Zeitraum-Format-Roundtrip, Hash-Bindung ans M-2-Gate (stale ⇒ GateRot)."""

from __future__ import annotations

import pytest

from moneyapp.elster import vertrag as ev
from moneyapp.ustva import vertrag as v


# ------------------------------------------------------------------- Helfer

def _q1() -> v.UStVAZeitraum:
    return v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 1)


def _befund_regel() -> v.StatusBefund:
    return v.StatusBefund(2026, v.BesteuerungsForm.REGELBESTEUERUNG,
                          v.StatusGrund.VORJAHR_UEBERSCHRITTEN, "Testlage")


def _kl_umsatz19(bid: str = "b1", brutto: int = 11900) -> v.Klassifikation:
    return v.Klassifikation(
        buchung_id=bid, ust_kategorie=v.UStKategorie.UMSATZ_19,
        quelle=v.KlassifikationsQuelle.MANUELL, satz_promille=190,
        split=v.split_aus_brutto(brutto, 190))


def _kl_eingang_vst(bid: str = "b3", brutto: int = 11900) -> v.Klassifikation:
    return v.Klassifikation(
        buchung_id=bid, ust_kategorie=v.UStKategorie.EINGANG_VST,
        quelle=v.KlassifikationsQuelle.MANUELL, satz_promille=190,
        split=v.split_aus_brutto(brutto, 190),
        vorsteuer_status=v.VorsteuerStatus.ABZIEHBAR)


def _datensatz(**kw) -> v.UStVADatensatz:
    """Konsistenter Standard-Datensatz: KZ 81 = 1.000 € (Herkunft 100.056 Cent
    aus zwei Buchungen) + KZ 66 = 1.900 Cent ⇒ Zahllast 19.000 − 1.900 = 17.100."""
    basis = dict(
        zeitraum=_q1(), besteuerungsform=v.BesteuerungsForm.REGELBESTEUERUNG,
        kz_werte=(v.KzWert("81", 1000, v.KzEinheit.EURO_VOLL),
                  v.KzWert("66", 1900, v.KzEinheit.CENT)),
        herkunft=(v.HerkunftsPosten("81", "b1", 60000),
                  v.HerkunftsPosten("81", "b2", 40056),
                  v.HerkunftsPosten("66", "b3", 1900)))
    basis.update(kw)
    return v.UStVADatensatz(**basis)


KATALOG = v.katalog_fuer(2026)


# ------------------------------------------------------------ Zeitraum (U-8)

def test_zeitraum_schluessel_monat_und_quartal():
    assert v.UStVAZeitraum(2026, v.ZeitraumTyp.MONAT, 3).schluessel() == "2026-03"
    assert v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 2).schluessel() == "2026-Q2"


def test_zeitraum_grenzen_validiert():
    with pytest.raises(v.ZeitraumFehler):
        v.UStVAZeitraum(2026, v.ZeitraumTyp.MONAT, 13)
    with pytest.raises(v.ZeitraumFehler):
        v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 5)
    with pytest.raises(v.ZeitraumFehler):
        v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 0)
    with pytest.raises(v.ZeitraumFehler):
        v.UStVAZeitraum(1999, v.ZeitraumTyp.MONAT, 1)


def test_befreiung_ist_kein_zeitraum():
    with pytest.raises(v.ZeitraumFehler):
        v.UStVAZeitraum(2026, v.ZeitraumTyp.JAHR_BEFREIT, 1)


def test_zeitraum_fenster_inkl_schaltjahr():
    assert v.UStVAZeitraum(2028, v.ZeitraumTyp.MONAT, 2).grenzen() == \
        ("2028-02-01", "2028-02-29")
    assert v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 2).grenzen() == \
        ("2026-04-01", "2026-06-30")


def test_faelligkeit_nominal_mit_jahreswechsel_und_dauerfrist():
    dez = v.UStVAZeitraum(2026, v.ZeitraumTyp.MONAT, 12)
    assert dez.faelligkeit_nominal() == "2027-01-10"
    assert dez.faelligkeit_nominal(dauerfrist=True) == "2027-02-10"
    q4 = v.UStVAZeitraum(2026, v.ZeitraumTyp.QUARTAL, 4)
    assert q4.faelligkeit_nominal() == "2027-01-10"


def test_zeitraum_roundtrip_in_docs65_steuerfall():
    """DIE Format-Kopplung (U-8): der M-4-Schlüssel ist wortwörtlich der
    docs/65-``SteuerFall.zeitraum``."""
    for z in (v.UStVAZeitraum(2026, v.ZeitraumTyp.MONAT, 7), _q1()):
        fall = ev.SteuerFall(formular=ev.FormularArt.USTVA, jahr=z.jahr,
                             zeitraum=z.schluessel())
        assert fall.zeitraum == z.schluessel()
        assert ev.fall_schluessel(fall) == f"ustva|{z.jahr}|{z.schluessel()}"


def test_konfig_soll_versteuerung_gesperrt_und_default_ist():
    with pytest.raises(v.KonfigFehler):
        v.VoranmeldungsKonfig(besteuerung=v.Besteuerung.SOLL)
    k = v.VoranmeldungsKonfig()
    assert (k.zeitraum_typ, k.besteuerung, k.dauerfrist) == \
        (v.ZeitraumTyp.QUARTAL, v.Besteuerung.IST, False)


# --------------------------------------------------- §19-Schwellen (U-2/U-3)

def test_schwellen_nur_neues_recht():
    with pytest.raises(v.SchwellenUnbekannt):
        v.schwellen_fuer(2024)          # Alt-Recht bewusst NICHT modelliert
    s = v.schwellen_fuer(2026)
    assert (s.vorjahr_max_cent, s.laufend_max_cent, s.modus) == \
        (2_500_000, 10_000_000, "hart")


def test_ku_wenn_grenzen_eingehalten_inkl_exaktem_grenzwert():
    b = v.pruefe_kleinunternehmer(2026, 2_500_000, 10_000_000)
    assert b.form is v.BesteuerungsForm.KLEINUNTERNEHMER
    assert b.grund is v.StatusGrund.SCHWELLEN_EINGEHALTEN


def test_vorjahr_ueberschritten_ein_cent_reicht():
    b = v.pruefe_kleinunternehmer(2026, 2_500_001, 0)
    assert b.form is v.BesteuerungsForm.REGELBESTEUERUNG
    assert b.grund is v.StatusGrund.VORJAHR_UEBERSCHRITTEN


def test_laufend_ueberschritten_wirkt_hart():
    b = v.pruefe_kleinunternehmer(2026, 0, 10_000_001)
    assert b.grund is v.StatusGrund.LAUFEND_UEBERSCHRITTEN
    assert "SOFORT" in b.text            # der überschreitende Umsatz zählt schon


def test_verzicht_bindet_fuenf_kalenderjahre():
    verzicht = v.VerzichtsErklaerung(ab_jahr=2025)
    assert verzicht.bindet_bis_jahr == 2029
    assert verzicht.bindet_in(2029) and not verzicht.bindet_in(2030)
    b = v.pruefe_kleinunternehmer(2026, 0, 0, verzicht=verzicht)
    assert (b.form, b.grund) == \
        (v.BesteuerungsForm.REGELBESTEUERUNG, v.StatusGrund.VERZICHT)


def test_negativer_gesamtumsatz_wirft():
    with pytest.raises(v.KonfigFehler):
        v.pruefe_kleinunternehmer(2026, -1, 0)


def test_statusbefund_nie_ohne_begruendung():
    with pytest.raises(v.KonfigFehler):
        v.StatusBefund(2026, v.BesteuerungsForm.KLEINUNTERNEHMER,
                       v.StatusGrund.SCHWELLEN_EINGEHALTEN, "  ")


def test_ku_rechnung_darf_keine_ust_ausweisen():
    v.pruefe_rechnung_kleinunternehmer(0)                    # kein Ausweis: ok
    with pytest.raises(v.KleinunternehmerKonflikt):
        v.pruefe_rechnung_kleinunternehmer(1)


# ------------------------------------------------------- Split (docs/68 §7)

def test_split_fixpunkte():
    assert v.split_aus_brutto(11900, 190) == v.UstSplit(11900, 10000, 1900, 190)
    assert v.split_aus_brutto(119, 190) == v.UstSplit(119, 100, 19, 190)
    assert v.split_aus_brutto(100, 190) == v.UstSplit(100, 84, 16, 190)
    assert v.split_aus_brutto(999, 70) == v.UstSplit(999, 934, 65, 70)
    assert v.split_aus_brutto(555, 0) == v.UstSplit(555, 555, 0, 0)


def test_split_invariante_fuer_krumme_betraege():
    for brutto in (1, 3, 17, 99, 101, 12345, 999999):
        for satz in (190, 70, 0):
            s = v.split_aus_brutto(brutto, satz)
            assert s.netto_cent + s.ust_cent == s.brutto_cent == brutto


def test_split_konstruktiv_ehrlich():
    with pytest.raises(v.KonfigFehler):
        v.UstSplit(11900, 10000, 1899, 190)      # netto+ust != brutto
    with pytest.raises(v.KonfigFehler):
        v.UstSplit(100, 100, 0, 50)              # unzulässiger Satz
    with pytest.raises(v.KonfigFehler):
        v.UstSplit(100, 90, 10, 0)               # Satz 0 verträgt keine USt
    with pytest.raises(v.KonfigFehler):
        v.UstSplit(-100, -84, -16, 190)          # betragsmäßig
    with pytest.raises(v.KonfigFehler):
        v.split_aus_brutto(-1, 190)


def test_bewirtungs_regel_ist_vertragskonstante():
    """★ Die 100/70-Falle (docs/68 §7): VoSt voll, EÜR nur 70 % — die beiden
    Achsen fallen bewusst auseinander; die Konstante hält das fest."""
    assert v.BEWIRTUNG_VOST_VOLL is True


# --------------------------------------- Regel/Klassifikation — Widersprüche

def test_regel_satz_erwartung():
    with pytest.raises(v.KonfigFehler):
        v.KlassifikationsRegel("k1", v.UStKategorie.UMSATZ_19, satz_promille=70)
    with pytest.raises(v.KonfigFehler):
        v.KlassifikationsRegel("k1", v.UStKategorie.UMSATZ_STFREI_OHNE_VST,
                               satz_promille=190)


def test_vst_status_ist_pflicht_entscheid_in_der_15er_welt():
    with pytest.raises(v.KonfigFehler):        # Abzug ist ein Entscheid (U-1)
        v.KlassifikationsRegel("k1", v.UStKategorie.EINGANG_VST, satz_promille=190)
    with pytest.raises(v.KonfigFehler):        # TEILWEISE = v1 gesperrt
        v.KlassifikationsRegel("k1", v.UStKategorie.EINGANG_VST, satz_promille=190,
                               vorsteuer_status=v.VorsteuerStatus.TEILWEISE)
    with pytest.raises(v.KonfigFehler):        # NICHT_ABZIEHBAR ⇒ Grund Pflicht
        v.KlassifikationsRegel("k1", v.UStKategorie.EINGANG_VST, satz_promille=190,
                               vorsteuer_status=v.VorsteuerStatus.NICHT_ABZIEHBAR)
    with pytest.raises(v.KonfigFehler):        # ABZIEHBAR verträgt keinen Grund
        v.KlassifikationsRegel(
            "k1", v.UStKategorie.EINGANG_VST, satz_promille=190,
            vorsteuer_status=v.VorsteuerStatus.ABZIEHBAR,
            vorsteuer_verbot_grund=v.VorsteuerVerbotsGrund.PRIVAT)
    with pytest.raises(v.KonfigFehler):        # außerhalb der §15-Welt: kein Status
        v.KlassifikationsRegel("k1", v.UStKategorie.UMSATZ_19, satz_promille=190,
                               vorsteuer_status=v.VorsteuerStatus.ABZIEHBAR)


def test_klassifikation_split_matrix():
    with pytest.raises(v.KonfigFehler):        # UMSATZ_19 verlangt Split
        v.Klassifikation("b1", v.UStKategorie.UMSATZ_19,
                         v.KlassifikationsQuelle.MANUELL, satz_promille=190)
    with pytest.raises(v.KonfigFehler):        # Satz vs. Split-Satz
        v.Klassifikation("b1", v.UStKategorie.UMSATZ_7,
                         v.KlassifikationsQuelle.MANUELL, satz_promille=70,
                         split=v.split_aus_brutto(119, 190))
    with pytest.raises(v.KonfigFehler):        # ig-Erwerb: Zahlung IST Netto
        v.Klassifikation("b1", v.UStKategorie.ERWERB_IG_19,
                         v.KlassifikationsQuelle.MANUELL, satz_promille=190,
                         split=v.split_aus_brutto(119, 190),
                         vorsteuer_status=v.VorsteuerStatus.ABZIEHBAR)


def test_klassifikation_string_koersion():
    k = v.Klassifikation("b1", "umsatz_19", "manuell", satz_promille=190,
                         split=v.split_aus_brutto(119, 190))
    assert k.ust_kategorie is v.UStKategorie.UMSATZ_19
    assert k.quelle is v.KlassifikationsQuelle.MANUELL
    with pytest.raises(v.KonfigFehler):
        v.Klassifikation("b1", "gibt_es_nicht", "manuell")


# ------------------------------------------------------ klassifiziere (U-1)

def test_netto_null_ist_kein_umsatz_per_ledger_semantik():
    k = v.klassifiziere({"id": "t1", "netto": 0, "kategorie_id": "egal"}, {})
    assert k.ust_kategorie is v.UStKategorie.KEIN_UMSATZ
    assert k.quelle is v.KlassifikationsQuelle.REGEL


def test_regel_treffer_baut_split_aus_betrag():
    regeln = {"k1": v.KlassifikationsRegel("k1", v.UStKategorie.UMSATZ_19,
                                           satz_promille=190)}
    k = v.klassifiziere({"id": "b9", "netto": 11900, "kategorie_id": "k1"}, regeln)
    assert k.split == v.UstSplit(11900, 10000, 1900, 190)
    assert k.quelle is v.KlassifikationsQuelle.REGEL


def test_override_schlaegt_regel_und_muss_zur_buchung_gehoeren():
    regeln = {"k1": v.KlassifikationsRegel("k1", v.UStKategorie.UMSATZ_19,
                                           satz_promille=190)}
    override = _kl_umsatz19("b9", 500)
    k = v.klassifiziere({"id": "b9", "netto": 11900, "kategorie_id": "k1"},
                        regeln, {"b9": override})
    assert k is override and k.quelle is v.KlassifikationsQuelle.MANUELL
    with pytest.raises(v.KonfigFehler):
        v.klassifiziere({"id": "b8", "netto": 1, "kategorie_id": "k1"},
                        regeln, {"b8": override})


def test_ohne_treffer_faellt_fail_closed_mit_id():
    with pytest.raises(v.KlassifikationUnklar) as ex:
        v.klassifiziere({"id": "b7", "netto": 100, "kategorie_id": "unbekannt"}, {})
    assert ex.value.buchung_ids == ("b7",)


def test_vollstaendigkeit_blockiert_zeitraum_mit_id_liste():
    bewegungen = [
        {"id": "in", "datum": "2026-02-10", "netto": 100},     # im Fenster, offen
        {"id": "out", "datum": "2026-05-01", "netto": 100},    # außerhalb Q1
        {"id": "transfer", "datum": "2026-02-11", "netto": 0},  # Transfer: frei
        {"id": "ok", "datum": "2026-03-01", "netto": 11900},   # klassifiziert
    ]
    kl = {"ok": _kl_umsatz19("ok")}
    with pytest.raises(v.KlassifikationUnklar) as ex:
        v.pruefe_vollstaendig(bewegungen, kl, _q1())
    assert ex.value.buchung_ids == ("in",)
    kl["in"] = _kl_umsatz19("in", 100)
    v.pruefe_vollstaendig(bewegungen, kl, _q1())               # jetzt still


# --------------------------------------------------- KU-Konflikt-Matrix (U-3)

def test_ku_matrix_ust_ausweis_abzug_und_konflikt_kategorien():
    ku = v.BesteuerungsForm.KLEINUNTERNEHMER
    with pytest.raises(v.KleinunternehmerKonflikt):
        v.pruefe_ku_konflikt(ku, [_kl_umsatz19()])             # USt-Ausweis
    with pytest.raises(v.KleinunternehmerKonflikt):
        v.pruefe_ku_konflikt(ku, [_kl_eingang_vst()])          # VoSt-Abzug
    erwerb = v.Klassifikation(
        "b5", v.UStKategorie.ERWERB_IG_19, v.KlassifikationsQuelle.MANUELL,
        satz_promille=190, vorsteuer_status=v.VorsteuerStatus.NICHT_ABZIEHBAR,
        vorsteuer_verbot_grund=v.VorsteuerVerbotsGrund.KLEINUNTERNEHMER_STATUS)
    with pytest.raises(v.KleinunternehmerKonflikt):
        v.pruefe_ku_konflikt(ku, [erwerb])                     # ig-Erwerb ⇒ klären
    # Regelbesteuerung: dieselben Klassifikationen sind konfliktfrei.
    v.pruefe_ku_konflikt(v.BesteuerungsForm.REGELBESTEUERUNG,
                         [_kl_umsatz19(), _kl_eingang_vst(), erwerb])


# ------------------------------------------------------------- Katalog (U-2)

def test_katalog_nur_gepflegte_jahre():
    with pytest.raises(v.KatalogUnbekannt):
        v.katalog_fuer(2024)
    assert v.katalog_fuer(2025).kategorien == KATALOG.kategorien


def test_katalog_kern_zuordnungen_und_verify_pflicht():
    kat = KATALOG.kategorien
    assert (kat[v.UStKategorie.UMSATZ_19].kz,
            kat[v.UStKategorie.UMSATZ_19].satz_promille) == ("81", 190)
    assert (kat[v.UStKategorie.UMSATZ_7].kz,
            kat[v.UStKategorie.UMSATZ_7].satz_promille) == ("86", 70)
    assert kat[v.UStKategorie.BEZUG_13B].kz_steuer == "85"
    assert KATALOG.vorsteuer[v.UStKategorie.EINGANG_VST].kz == "66"
    assert KATALOG.vorsteuer[v.UStKategorie.EINGANG_EUST].kz == "62"
    # U-2: JEDE Zuordnung bleibt verify, bis M4-4 sie am ERiC-Schema bestätigt.
    for z in list(kat.values()) + list(KATALOG.vorsteuer.values()):
        assert z.verify is True


def test_katalog_bewusste_luecken_und_sonder_kz():
    for ohne_kz in (v.UStKategorie.KEIN_UMSATZ, v.UStKategorie.EINGANG_OHNE_VST):
        assert ohne_kz not in KATALOG.kategorien
        assert ohne_kz not in KATALOG.vorsteuer
    assert {"83", "39"} <= KATALOG.bekannte_kz()


# ---------------------------------------------------------- Rundung (U-7)

def test_euro_voll_schneidet_richtung_null():
    assert v.euro_voll(123456) == 1234
    assert v.euro_voll(-123456) == -1234     # Entgeltminderung: Richtung Null!
    assert v.euro_voll(99) == 0
    assert v.euro_voll(-99) == 0


# ------------------------------------------------------------ Datensatz (U-3/U-5)

def test_datensatz_im_ku_status_konstruktiv_unmoeglich():
    with pytest.raises(v.KleinunternehmerKonflikt):
        _datensatz(besteuerungsform=v.BesteuerungsForm.KLEINUNTERNEHMER)


def test_datensatz_verbietet_doppel_kz_und_fremde_herkunft():
    with pytest.raises(v.KonfigFehler):
        _datensatz(kz_werte=(v.KzWert("81", 1, v.KzEinheit.EURO_VOLL),
                             v.KzWert("81", 2, v.KzEinheit.EURO_VOLL)),
                   herkunft=())
    with pytest.raises(v.KonfigFehler):
        _datensatz(herkunft=(v.HerkunftsPosten("48", "b1", 1),))


def test_nullmeldung_ist_legitim():
    d = v.UStVADatensatz(zeitraum=_q1(),
                         besteuerungsform=v.BesteuerungsForm.REGELBESTEUERUNG)
    assert d.kz_werte == () and v.pruefe_summen(d, KATALOG) == 0


def test_kanonik_deterministisch_inhalt_bindet_nicht_uhrzeit():
    d1 = _datensatz(erstellt_am="2026-07-04T10:00:00")
    # Permutation von kz_werte + herkunft und andere Uhrzeit ⇒ identisch.
    d2 = v.UStVADatensatz(
        zeitraum=_q1(), besteuerungsform=v.BesteuerungsForm.REGELBESTEUERUNG,
        kz_werte=tuple(reversed(d1.kz_werte)),
        herkunft=tuple(reversed(d1.herkunft)), erstellt_am="2027-01-01T00:00:00")
    assert v.kanonische_serialisierung(d1) == v.kanonische_serialisierung(d2)
    assert v.quell_stand(d1) == v.quell_stand(d2)
    # 1 Cent Herkunfts-Änderung ⇒ anderer Hash (U-6).
    d3 = _datensatz(herkunft=(v.HerkunftsPosten("81", "b1", 60001),
                              v.HerkunftsPosten("81", "b2", 40056),
                              v.HerkunftsPosten("66", "b3", 1900)))
    assert v.quell_stand(d3) != v.quell_stand(d1)


# ------------------------------------------------------ pruefe_summen (U-5/U-7)

def test_zahllast_aus_bmg_mal_satz_exakt():
    assert v.pruefe_summen(_datensatz(), KATALOG) == 1000 * 190 // 10 - 1900


def test_kz83_muss_der_einen_rechnung_entsprechen():
    kz = (v.KzWert("81", 1000, v.KzEinheit.EURO_VOLL),
          v.KzWert("66", 1900, v.KzEinheit.CENT),
          v.KzWert("83", 17100, v.KzEinheit.CENT))
    assert v.pruefe_summen(_datensatz(kz_werte=kz), KATALOG) == 17100
    kz_falsch = kz[:2] + (v.KzWert("83", 17101, v.KzEinheit.CENT),)
    with pytest.raises(v.SummenFehler):
        v.pruefe_summen(_datensatz(kz_werte=kz_falsch), KATALOG)


def test_unbekannte_kz_und_falsche_einheit_fallen_auf():
    with pytest.raises(v.SummenFehler):
        v.pruefe_summen(_datensatz(
            kz_werte=(v.KzWert("99", 1, v.KzEinheit.CENT),), herkunft=()), KATALOG)
    with pytest.raises(v.SummenFehler):     # BMG centgenau gemeldet ⇒ U-7-Bruch
        v.pruefe_summen(_datensatz(
            kz_werte=(v.KzWert("81", 100056, v.KzEinheit.CENT),),
            herkunft=(v.HerkunftsPosten("81", "b1", 100056),)), KATALOG)


def test_herkunft_ist_pflicht_und_muss_passen():
    with pytest.raises(v.SummenFehler):     # KZ 66 ohne Manifest
        v.pruefe_summen(_datensatz(
            kz_werte=(v.KzWert("66", 1900, v.KzEinheit.CENT),), herkunft=()),
            KATALOG)
    with pytest.raises(v.SummenFehler):     # BMG ≠ euro_voll(Herkunft)
        v.pruefe_summen(_datensatz(
            kz_werte=(v.KzWert("81", 999, v.KzEinheit.EURO_VOLL),
                      v.KzWert("66", 1900, v.KzEinheit.CENT))), KATALOG)


def test_erstattung_ist_negativ_und_ehrlich():
    d = _datensatz(kz_werte=(v.KzWert("66", 1900, v.KzEinheit.CENT),),
                   herkunft=(v.HerkunftsPosten("66", "b3", 1900),))
    assert v.pruefe_summen(d, KATALOG) == -1900


def test_sondervorauszahlung_39_mindert_ohne_manifest_pflicht():
    d = _datensatz(kz_werte=(v.KzWert("81", 1000, v.KzEinheit.EURO_VOLL),
                             v.KzWert("66", 1900, v.KzEinheit.CENT),
                             v.KzWert("39", 5000, v.KzEinheit.CENT)))
    assert v.pruefe_summen(d, KATALOG) == 17100 - 5000


def test_13b_paar_bmg_info_plus_gemeldete_steuer():
    d = _datensatz(
        kz_werte=(v.KzWert("84", 500, v.KzEinheit.EURO_VOLL),
                  v.KzWert("85", 9500, v.KzEinheit.CENT)),
        herkunft=(v.HerkunftsPosten("84", "b4", 50000),
                  v.HerkunftsPosten("85", "b4", 9500)))
    assert v.pruefe_summen(d, KATALOG) == 9500   # Satz kommt aus der Meldung


# --------------------------------------------- erzeuge_ustva: Wächter-Kette

def test_erzeuge_wirft_ku_vor_allem_anderen():
    ku = v.StatusBefund(2026, v.BesteuerungsForm.KLEINUNTERNEHMER,
                        v.StatusGrund.SCHWELLEN_EINGEHALTEN, "KU")
    with pytest.raises(v.KleinunternehmerKonflikt):
        v.erzeuge_ustva(_q1(), v.VoranmeldungsKonfig(), ku, [], {})


def test_erzeuge_respektiert_befreiung_und_zeitraum_konfig():
    with pytest.raises(v.ZeitraumFehler):
        v.erzeuge_ustva(_q1(),
                        v.VoranmeldungsKonfig(zeitraum_typ=v.ZeitraumTyp.JAHR_BEFREIT),
                        _befund_regel(), [], {})
    with pytest.raises(v.ZeitraumFehler):    # Monats-Zeitraum bei Quartals-Konfig
        v.erzeuge_ustva(v.UStVAZeitraum(2026, v.ZeitraumTyp.MONAT, 1),
                        v.VoranmeldungsKonfig(), _befund_regel(), [], {})


def test_erzeuge_blockiert_unklare_buchungen():
    bewegungen = [{"id": "x1", "datum": "2026-02-01", "netto": 100}]
    with pytest.raises(v.KlassifikationUnklar):
        v.erzeuge_ustva(_q1(), v.VoranmeldungsKonfig(), _befund_regel(),
                        bewegungen, {})


def test_erzeuge_waechter_vor_notimplemented():
    """Alle Wächter grün ⇒ ERST DANN das ehrliche NotImplementedError
    (Stufe 0: Sicherheitspfad existiert vor der Funktion)."""
    bewegungen = [{"id": "b1", "datum": "2026-02-01", "netto": 11900,
                   "kategorie_id": "k1"}]
    with pytest.raises(NotImplementedError):
        v.erzeuge_ustva(_q1(), v.VoranmeldungsKonfig(), _befund_regel(),
                        bewegungen, {"b1": _kl_umsatz19()})


# ----------------------------------- Übergabe an M-1 + Hash-Gate e2e (U-6)

def test_uebergabe_baut_steuerfall_und_quelldaten():
    fall, quelle = v.uebergabe_an_filing(_datensatz(), v.VoranmeldungsKonfig(),
                                         KATALOG)
    assert fall.formular is ev.FormularArt.USTVA
    assert (fall.jahr, fall.zeitraum, fall.korrektur_nr) == (2026, "2026-Q1", 0)
    assert quelle["quell_stand_hash"] == v.quell_stand(_datensatz())
    assert quelle["zahllast_cent"] == 17100
    assert quelle["beleg_ust_summe_cent"] == 1900


def test_uebergabe_berichtigung_nur_konsistent():
    with pytest.raises(v.KonfigFehler):
        v.uebergabe_an_filing(_datensatz(berichtigung=True),
                              v.VoranmeldungsKonfig(), KATALOG)
    with pytest.raises(v.KonfigFehler):
        v.uebergabe_an_filing(_datensatz(), v.VoranmeldungsKonfig(), KATALOG,
                              korrektur_nr=1)
    fall, _ = v.uebergabe_an_filing(_datensatz(berichtigung=True),
                                    v.VoranmeldungsKonfig(), KATALOG,
                                    korrektur_nr=1)
    assert fall.ist_korrektur


def test_uebergabe_zeitraum_muss_zur_konfig_passen():
    with pytest.raises(v.ZeitraumFehler):
        v.uebergabe_an_filing(
            _datensatz(), v.VoranmeldungsKonfig(zeitraum_typ=v.ZeitraumTyp.MONAT),
            KATALOG)


def test_e2e_hash_kette_m4_m2_m1_gruen_und_stale():
    """DIE Naht des Pakets (docs/68 §8): M-4-Datensatz → M-2-Freigabe →
    M-1-Gate grün; 1 Cent Änderung ⇒ GateRot (docs/65 I-1)."""
    fall, quelle = v.uebergabe_an_filing(_datensatz(), v.VoranmeldungsKonfig(),
                                         KATALOG)
    datensatz = ev.ElsterDatensatz(fall=fall, xml="<nutzdaten/>",
                                   quell_stand_hash=quelle["quell_stand_hash"],
                                   formular_version="ustva-stufe0")
    freigabe = ev.PlausiFreigabe(fall_schluessel=ev.fall_schluessel(fall),
                                 quell_stand_hash=quelle["quell_stand_hash"],
                                 gruen=True, geprueft_am="2026-07-04")
    ev.pruefe_gate(freigabe, datensatz)          # grün: kein Wurf

    geaendert = _datensatz(herkunft=(v.HerkunftsPosten("81", "b1", 60001),
                                     v.HerkunftsPosten("81", "b2", 40056),
                                     v.HerkunftsPosten("66", "b3", 1900)))
    stale = ev.ElsterDatensatz(fall=fall, xml="<nutzdaten/>",
                               quell_stand_hash=v.quell_stand(geaendert),
                               formular_version="ustva-stufe0")
    with pytest.raises(ev.GateRot):
        ev.pruefe_gate(freigabe, stale)


# ------------------------------------------------------------ Vertrags-Anker

def test_feld_flaechen_eingefroren():
    assert v.KLASSIFIKATION_FELDER == {
        "buchung_id", "ust_kategorie", "quelle", "satz_promille", "split",
        "vorsteuer_status", "vorsteuer_verbot_grund"}
    assert v.DATENSATZ_FELDER == {
        "zeitraum", "besteuerungsform", "kz_werte", "herkunft",
        "berichtigung", "erstellt_am"}


def test_satz_menge_ist_geschlossen():
    assert v.SATZ_PROMILLE_ZULAESSIG == {190, 70, 0}
