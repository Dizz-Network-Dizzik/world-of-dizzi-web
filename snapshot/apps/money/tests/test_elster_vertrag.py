"""Vertrags-Tests ELSTER-Transport (docs/65, Stufe 0) — Lib-/Netz-/DB-frei.

Prüfen den VERTRAG, nicht eine Implementierung: Zustandsmaschine fail-closed
(SENDET nur über VALIDIERT_OK, kein Abbruch nach Sendebeginn, Quittung nie
FEHLGESCHLAGEN), Fehler-/Retry-Politik, Geheimnis-Freiheit der Datentypen,
das hash-gebundene M-2-Gate, Doppel-Übermittlungs-Schutz und die Wächter-Kette
der Transport-Stubs (NichtScharf/GateRot VOR NotImplementedError).
"""

import dataclasses

import pytest

from moneyapp.elster import vertrag as v


# ------------------------------------------------------------ Zustandsmaschine

def test_uebergaenge_decken_alle_zustaende():
    assert set(v.UEBERGAENGE) == set(v.FilingZustand)


def test_terminale_sind_absorbierend():
    assert len(v.TERMINAL) == 5
    for z in v.TERMINAL:
        assert v.UEBERGAENGE[z] == frozenset()
        assert v.ist_terminal(z)


def test_sendet_nur_aus_validiert_ok():
    quellen = {von for von, ziele in v.UEBERGAENGE.items()
               if v.FilingZustand.SENDET in ziele}
    assert quellen == {v.FilingZustand.VALIDIERT_OK}  # I-5


def test_festgeschrieben_nur_ueber_quittung():
    quellen = {von for von, ziele in v.UEBERGAENGE.items()
               if v.FilingZustand.FESTGESCHRIEBEN in ziele}
    assert quellen == {v.FilingZustand.QUITTUNG_ERHALTEN}


def test_kein_abbruch_ab_sendebeginn():
    # Nutzer-Abbruch gibt es nur VOR SENDET — danach wäre der Ausgang unklar.
    for von in (v.FilingZustand.SENDET, v.FilingZustand.QUITTUNG_ERHALTEN):
        assert v.FilingZustand.ABGEBROCHEN not in v.UEBERGAENGE[von], von


def test_quittung_kennt_kein_fehlgeschlagen():
    # Übermittlung IST passiert — der Fehlerpfad danach heißt UEBERMITTELT_OFFEN.
    ziele = v.UEBERGAENGE[v.FilingZustand.QUITTUNG_ERHALTEN]
    assert v.FilingZustand.FEHLGESCHLAGEN not in ziele
    assert ziele == frozenset({v.FilingZustand.FESTGESCHRIEBEN,
                               v.FilingZustand.UEBERMITTELT_OFFEN})


def test_unklar_und_offen_nur_aus_der_sendephase():
    quellen_unklar = {von for von, ziele in v.UEBERGAENGE.items()
                      if v.FilingZustand.SENDUNG_UNKLAR in ziele}
    quellen_offen = {von for von, ziele in v.UEBERGAENGE.items()
                     if v.FilingZustand.UEBERMITTELT_OFFEN in ziele}
    assert quellen_unklar == {v.FilingZustand.SENDET}
    assert quellen_offen == {v.FilingZustand.QUITTUNG_ERHALTEN}


def test_fail_closed_vor_sendung_kann_alles_fehlschlagen():
    fuer_fehlschlag = {v.FilingZustand.BAUT_DATENSATZ, v.FilingZustand.VALIDIERT,
                       v.FilingZustand.VALIDIERT_OK, v.FilingZustand.SENDET}
    for z in fuer_fehlschlag:
        assert v.FilingZustand.FEHLGESCHLAGEN in v.UEBERGAENGE[z], z


def test_uebergang_legal_ok():
    v.pruefe_uebergang(v.FilingZustand.BEREIT, v.FilingZustand.BAUT_DATENSATZ)
    v.pruefe_uebergang(v.FilingZustand.SENDET, v.FilingZustand.QUITTUNG_ERHALTEN)


def test_uebergang_illegal_wirft():
    with pytest.raises(v.ZustandsFehler):   # Senden ohne Validate-Weg
        v.pruefe_uebergang(v.FilingZustand.BEREIT, v.FilingZustand.SENDET)
    with pytest.raises(v.ZustandsFehler):   # Validate-Sprung ohne VALIDIERT_OK
        v.pruefe_uebergang(v.FilingZustand.VALIDIERT, v.FilingZustand.SENDET)
    with pytest.raises(v.ZustandsFehler):   # aus Terminal führt kein Weg zurück
        v.pruefe_uebergang(v.FilingZustand.SENDUNG_UNKLAR, v.FilingZustand.SENDET)


# ------------------------------------------------------------ Fehler-Taxonomie

def test_alle_fehler_erben_elsterfehler():
    for k in (v.KonfigFehler, v.NichtScharf, v.GateRot, v.DoppelFilingFehler,
              v.ValidierungsFehler, v.ZertifikatFehler, v.VerbindungsFehler,
              v.SendeUnklarFehler, v.UebermittlungAbgelehnt, v.FestschreibFehler,
              v.ZustandsFehler):
        assert issubclass(k, v.ElsterFehler)


def test_retry_politik_nur_verbindung_wiederholbar():
    assert v.ElsterFehler.retry_erlaubt is False        # Basis: unbekannt ⇒ nie
    assert v.VerbindungsFehler.retry_erlaubt is True    # einzige Ausnahme
    for k in (v.KonfigFehler, v.NichtScharf, v.GateRot, v.DoppelFilingFehler,
              v.ValidierungsFehler, v.ZertifikatFehler, v.SendeUnklarFehler,
              v.UebermittlungAbgelehnt, v.FestschreibFehler, v.ZustandsFehler):
        assert k.retry_erlaubt is False, k              # Senden nie auto-retry (I-6)


# ------------------------------------------------------------------ Datentypen

def _zugang(**kw) -> v.ElsterZugang:
    basis = dict(zugang_id="z1", zertifikat_pfad=r"elster\zert\test.pfx",
                 pin_vault_key="elster_pin_z1",
                 zertifikat_typ=v.ZertifikatTyp.PERSOENLICH,
                 steuernummer="123/456/78901")
    basis.update(kw)
    return v.ElsterZugang(**basis)


def test_zugang_valide_baubar():
    z = _zugang()
    assert z.zertifikat_typ is v.ZertifikatTyp.PERSOENLICH
    assert _zugang(zertifikat_typ="organisation").zertifikat_typ is v.ZertifikatTyp.ORGANISATION


@pytest.mark.parametrize("kaputt", [
    dict(zugang_id="  "), dict(zertifikat_pfad=""),
    dict(pin_vault_key=" "), dict(zertifikat_typ="quantum")])
def test_zugang_konfigfehler(kaputt):
    with pytest.raises(v.KonfigFehler):
        _zugang(**kaputt)


def test_zugang_repr_maskiert_steuernummer_und_traegt_nie_pin():
    z = _zugang()
    r = repr(z)
    assert "123/456/78901" not in r      # Steuernummer maskiert (I-2)
    assert "12…" in r
    # Feld-Fläche trägt strukturell keinen Geheimnis-Slot:
    assert not any(f in v.ZUGANG_FELDER for f in ("pin", "passwort", "zertifikat_inhalt"))


def test_zugang_feldflaeche_eingefroren():
    assert v.ZUGANG_FELDER == {"zugang_id", "zertifikat_pfad", "pin_vault_key",
                               "zertifikat_typ", "steuernummer"}
    assert dataclasses.is_dataclass(v.ElsterZugang)


def test_scharfschaltung_zwei_schluessel():
    halb = v.Scharfschaltung(zugang_id="z1", angelegt_am="2026-07-04")
    voll = v.Scharfschaltung(zugang_id="z1", angelegt_am="2026-07-04",
                             bestaetigt_am="2026-07-05")
    assert not halb.ist_scharf and voll.ist_scharf
    with pytest.raises(v.NichtScharf):
        v.pruefe_scharf(None)
    with pytest.raises(v.NichtScharf):
        v.pruefe_scharf(halb)
    v.pruefe_scharf(voll)


def test_hersteller_id_wachter():
    with pytest.raises(v.NichtScharf):
        v.pruefe_hersteller_id(None)
    with pytest.raises(v.NichtScharf):
        v.pruefe_hersteller_id("   ")
    v.pruefe_hersteller_id("TESTKENNUNG")   # gesetzt = ok (Wert egal, kommt aus Settings)


# ------------------------------------------------------------------ SteuerFall

def test_steuerfall_euer_und_ustva():
    euer = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026)
    ust = v.SteuerFall(formular="ustva", jahr=2026, zeitraum="2026-06")
    assert not euer.ist_korrektur
    assert ust.formular is v.FormularArt.USTVA


@pytest.mark.parametrize("kaputt", [
    dict(formular=v.FormularArt.USTVA, jahr=2026),                    # UStVA ohne Zeitraum
    dict(formular=v.FormularArt.EUER, jahr=2026, zeitraum="2026-06"),  # EÜR mit Zeitraum
    dict(formular=v.FormularArt.EUER, jahr=1999),                     # Jahr unplausibel
    dict(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=-1),    # negativ
    dict(formular="grundsteuer", jahr=2026)])                         # unbekannt
def test_steuerfall_konfigfehler(kaputt):
    with pytest.raises(v.KonfigFehler):
        v.SteuerFall(**kaputt)


def test_fall_schluessel_ohne_korrektur_nr():
    a = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026)
    b = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=2)
    assert v.fall_schluessel(a) == v.fall_schluessel(b) == "euer|2026|"
    ust = v.SteuerFall(formular=v.FormularArt.USTVA, jahr=2026, zeitraum="2026-06")
    assert v.fall_schluessel(ust) == "ustva|2026|2026-06"


# -------------------------------------------------------- Datensatz + Gate

_FALL = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026)
_HASH = v.berechne_quell_stand("kanonische-quelldaten-2026")


def _datensatz(**kw) -> v.ElsterDatensatz:
    basis = dict(fall=_FALL, xml="<Nutzdaten>GEHEIM-4711</Nutzdaten>",
                 quell_stand_hash=_HASH, formular_version="EUER-2026")
    basis.update(kw)
    return v.ElsterDatensatz(**basis)


def _freigabe(**kw) -> v.PlausiFreigabe:
    basis = dict(fall_schluessel=v.fall_schluessel(_FALL), quell_stand_hash=_HASH,
                 gruen=True, geprueft_am="2026-07-04T10:00:00")
    basis.update(kw)
    return v.PlausiFreigabe(**basis)


def test_quell_stand_deterministisch():
    assert v.berechne_quell_stand("abc") == v.berechne_quell_stand(b"abc")
    assert v.berechne_quell_stand("abc") != v.berechne_quell_stand("abd")


@pytest.mark.parametrize("kaputt", [
    dict(xml="  "), dict(quell_stand_hash=""), dict(formular_version=" ")])
def test_datensatz_konfigfehler(kaputt):
    with pytest.raises(v.KonfigFehler):
        _datensatz(**kaputt)


def test_datensatz_repr_zeigt_nie_steuer_xml():
    d = _datensatz()
    assert "GEHEIM-4711" not in repr(d)     # I-2: der Datensatz IST die Erklärung
    assert "xml_laenge" in repr(d)


def test_gate_gruen_frisch_passiert():
    v.pruefe_gate(_freigabe(), _datensatz())


@pytest.mark.parametrize("freigabe", [
    None,
    "rot",          # gruen=False
    "stale",        # anderer Quell-Datenstand
    "fremd"])       # anderer Fall
def test_gate_rot_faelle(freigabe):
    f = {None: None,
         "rot": _freigabe(gruen=False, befund="3 Buchungen ohne Kategorie"),
         "stale": _freigabe(quell_stand_hash=v.berechne_quell_stand("veraltet")),
         "fremd": _freigabe(fall_schluessel="ustva|2026|2026-06")}[freigabe]
    with pytest.raises(v.GateRot):
        v.pruefe_gate(f, _datensatz())


# ----------------------------------------------- Validierung/Quittung/Ergebnis

def test_validierungsergebnis_konstruktiv_ehrlich():
    v.ValidierungsErgebnis(ok=True, hinweise=("Hinweis",))
    v.ValidierungsErgebnis(ok=False, fehler=("Feld 17 fehlt",))
    with pytest.raises(ValueError):
        v.ValidierungsErgebnis(ok=True, fehler=("widerspruch",))
    with pytest.raises(ValueError):     # nie stilles Rot
        v.ValidierungsErgebnis(ok=False)


def test_quittung_verlangt_ticket_und_repr_ohne_roh():
    with pytest.raises(v.KonfigFehler):
        v.Quittung(transferticket="  ", uebermittelt_am="2026-07-04")
    q = v.Quittung(transferticket="TT-1", uebermittelt_am="2026-07-04",
                   protokoll_roh=b"GEHEIMES-PROTOKOLL")
    assert "GEHEIMES-PROTOKOLL" not in repr(q)


def _ergebnis(**kw) -> v.FilingErgebnis:
    basis = dict(fall_schluessel="euer|2026|", zustand=v.FilingZustand.FESTGESCHRIEBEN,
                 transferticket="TT-1")
    basis.update(kw)
    return v.FilingErgebnis(**basis)


def test_ergebnis_nur_terminal():
    with pytest.raises(ValueError):
        _ergebnis(zustand=v.FilingZustand.SENDET)


def test_ergebnis_erfolg_verlangt_ticket():
    _ergebnis()     # festgeschrieben + Ticket = ok
    with pytest.raises(ValueError):     # I-4: Erfolg ⇔ Quittung
        _ergebnis(transferticket="")
    with pytest.raises(ValueError):
        _ergebnis(fehler="widerspruch")


def test_ergebnis_fehlschlag_ehrlich_und_ohne_ticket():
    _ergebnis(zustand=v.FilingZustand.FEHLGESCHLAGEN, transferticket="",
              fehler="ELSTER-Server nicht erreichbar", fehler_art="VerbindungsFehler")
    with pytest.raises(ValueError):     # Fehlertext Pflicht
        _ergebnis(zustand=v.FilingZustand.FEHLGESCHLAGEN, transferticket="")
    with pytest.raises(ValueError):     # Ticket widerspricht sauberem Fehlschlag
        _ergebnis(zustand=v.FilingZustand.FEHLGESCHLAGEN, fehler="x")


def test_ergebnis_sonder_terminale():
    _ergebnis(zustand=v.FilingZustand.SENDUNG_UNKLAR, transferticket="",
              fehler="Timeout nach Sendebeginn — Transferticket manuell prüfen")
    with pytest.raises(ValueError):
        _ergebnis(zustand=v.FilingZustand.SENDUNG_UNKLAR, transferticket="", fehler="")
    _ergebnis(zustand=v.FilingZustand.UEBERMITTELT_OFFEN,
              fehler="Festschreibung fehlgeschlagen — lokal nacharbeiten")
    with pytest.raises(ValueError):     # OFFEN ohne Ticket unmöglich
        _ergebnis(zustand=v.FilingZustand.UEBERMITTELT_OFFEN, transferticket="",
                  fehler="x")
    with pytest.raises(ValueError):     # Abbruch mit Ticket unmöglich
        _ergebnis(zustand=v.FilingZustand.ABGEBROCHEN, fehler="")


# ------------------------------------------------------------- Doppel-Schutz

def test_doppel_festgeschrieben_blockt_nur_erstlauf():
    historie = [("euer|2026|", v.FilingZustand.FESTGESCHRIEBEN)]
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(historie, _FALL)
    korrektur = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=1)
    v.pruefe_doppel(historie, korrektur)        # bewusste Korrektur darf


@pytest.mark.parametrize("zustand", [
    v.FilingZustand.SENDET,             # Crash-Leiche mitten im Senden
    v.FilingZustand.QUITTUNG_ERHALTEN,  # R-1 (docs/71): Quittung = angenommen → Doppel-Schutz
    v.FilingZustand.SENDUNG_UNKLAR,
    v.FilingZustand.UEBERMITTELT_OFFEN])
def test_doppel_ungeklaertes_blockt_auch_korrektur(zustand):
    historie = [("euer|2026|", zustand)]
    korrektur = v.SteuerFall(formular=v.FormularArt.EUER, jahr=2026, korrektur_nr=1)
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(historie, _FALL)
    with pytest.raises(v.DoppelFilingFehler):
        v.pruefe_doppel(historie, korrektur)


def test_doppel_fremder_schluessel_und_terminal_frei():
    historie = [("euer|2025|", v.FilingZustand.FESTGESCHRIEBEN),   # anderes Jahr
                ("euer|2026|", v.FilingZustand.FEHLGESCHLAGEN),    # sauber gescheitert
                ("euer|2026|", v.FilingZustand.ABGEBROCHEN)]       # abgebrochen
    v.pruefe_doppel(historie, _FALL)    # neuer Versuch erlaubt


# ------------------------------------------------- Sende-Vorbedingungs-Bündel

_SCHARF = v.Scharfschaltung(zugang_id="z1", angelegt_am="a", bestaetigt_am="b")
_GRUEN = v.ValidierungsErgebnis(ok=True)


def _sende_freigabe(**kw):
    basis = dict(hersteller_id="TESTKENNUNG", schaltung=_SCHARF, fall=_FALL,
                 datensatz=_datensatz(), validierung=_GRUEN,
                 freigabe=_freigabe(), vorhandene=())
    basis.update(kw)
    return v.pruefe_sende_freigabe(**basis)


def test_sende_freigabe_volle_kette_passiert():
    _sende_freigabe()


@pytest.mark.parametrize("kaputt,erwartet", [
    (dict(hersteller_id=""), v.NichtScharf),
    (dict(schaltung=None), v.NichtScharf),
    (dict(vorhandene=[("euer|2026|", v.FilingZustand.SENDUNG_UNKLAR)]), v.DoppelFilingFehler),
    (dict(validierung=None), v.ValidierungsFehler),
    (dict(validierung=v.ValidierungsErgebnis(ok=False, fehler=("Feld 17",))), v.ValidierungsFehler),
    (dict(freigabe=None), v.GateRot),
    (dict(freigabe="stale"), v.GateRot)])
def test_sende_freigabe_jede_bedingung_wirft(kaputt, erwartet):
    if kaputt.get("freigabe") == "stale":
        kaputt = dict(freigabe=_freigabe(quell_stand_hash=v.berechne_quell_stand("alt")))
    with pytest.raises(erwartet):
        _sende_freigabe(**kaputt)


# ------------------------------------------------------------ Transport-Stubs

def test_transport_sende_wachter_vor_notimplemented():
    t = v.EricTransport(_zugang(), None, hersteller_id="TESTKENNUNG")
    with pytest.raises(v.NichtScharf):          # Wächter VOR NotImplementedError
        t.sende(_datensatz(), _FALL, validierung=_GRUEN, freigabe=_freigabe())
    t2 = v.EricTransport(_zugang(), _SCHARF)    # keine Hersteller-ID
    with pytest.raises(v.NichtScharf):
        t2.sende(_datensatz(), _FALL, validierung=_GRUEN, freigabe=_freigabe())
    t3 = v.EricTransport(_zugang(), _SCHARF, hersteller_id="TESTKENNUNG")
    with pytest.raises(v.GateRot):              # scharf, aber Gate rot
        t3.sende(_datensatz(), _FALL, validierung=_GRUEN, freigabe=None)


def test_transport_stufe0_alles_gruen_ist_ehrlich_unimplementiert():
    t = v.EricTransport(_zugang(), _SCHARF, hersteller_id="TESTKENNUNG")
    with pytest.raises(NotImplementedError):
        t.sende(_datensatz(), _FALL, validierung=_GRUEN, freigabe=_freigabe())


def test_transport_validiere_frei_aber_unimplementiert():
    # validate-only braucht KEINE Scharfschaltung (I-5: niederschwellig halten) …
    t = v.EricTransport(_zugang(), None)
    with pytest.raises(NotImplementedError):    # … ist aber Stufe 0 ehrlich leer
        t.validiere(_datensatz())


def test_bauer_stubs_unimplementiert_und_vertragskonform():
    for bauer in (v.EuerBauer(), v.UstvaBauer()):
        assert isinstance(bauer, v.DatensatzBauer)
        with pytest.raises(NotImplementedError):
            bauer.baue(_FALL, {})
    assert v.EuerBauer.formular is v.FormularArt.EUER
    assert v.UstvaBauer.formular is v.FormularArt.USTVA
