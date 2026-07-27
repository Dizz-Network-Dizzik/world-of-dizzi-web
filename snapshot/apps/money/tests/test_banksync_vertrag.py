"""Vertrags-Tests Bank-Sync (docs/64, Stufe 0) — Ollama-/Netz-/DB-frei.

Prüfen den VERTRAG, nicht eine Implementierung: Zustandsmaschine fail-closed,
Fehler-/Retry-Politik, Geheimnis-Freiheit der Datentypen, Zwei-Schlüssel-
Wächter, Quelle→dispatch-Kompatibilität (I-5) und die Fenster-Politik.
"""

import dataclasses

import pytest

from moneyapp.importers import dispatch
from moneyapp.banksync import vertrag as v


# ------------------------------------------------------------ Zustandsmaschine

def test_uebergaenge_decken_alle_zustaende():
    assert set(v.UEBERGAENGE) == set(v.SyncZustand)


def test_terminale_sind_absorbierend():
    for z in v.TERMINAL:
        assert v.UEBERGAENGE[z] == frozenset()
        assert v.ist_terminal(z)


def test_abgeschlossen_nur_ueber_uebergabe():
    quellen = {von for von, ziele in v.UEBERGAENGE.items()
               if v.SyncZustand.ABGESCHLOSSEN in ziele}
    assert quellen == {v.SyncZustand.UEBERGIBT_IMPORT}


def test_fail_closed_jeder_laufzustand_kann_fehlschlagen():
    laufzustaende = set(v.SyncZustand) - v.TERMINAL - {v.SyncZustand.BEREIT}
    for z in laufzustaende:
        assert v.SyncZustand.FEHLGESCHLAGEN in v.UEBERGAENGE[z], z


def test_aufsetzpunkt_selbstschleife_und_tan_im_abruf():
    assert v.SyncZustand.RUFT_AB in v.UEBERGAENGE[v.SyncZustand.RUFT_AB]
    assert v.SyncZustand.TAN_ERFORDERLICH in v.UEBERGAENGE[v.SyncZustand.RUFT_AB]


def test_uebergang_legal_ok():
    v.pruefe_uebergang(v.SyncZustand.BEREIT, v.SyncZustand.VERBINDET)
    v.pruefe_uebergang(v.SyncZustand.RUFT_AB, v.SyncZustand.RUFT_AB)


def test_uebergang_illegal_wirft():
    with pytest.raises(v.ZustandsFehler):
        v.pruefe_uebergang(v.SyncZustand.BEREIT, v.SyncZustand.RUFT_AB)
    with pytest.raises(v.ZustandsFehler):
        v.pruefe_uebergang(v.SyncZustand.ABGESCHLOSSEN, v.SyncZustand.VERBINDET)
    with pytest.raises(v.ZustandsFehler):  # aus FEHLGESCHLAGEN führt kein Weg zurück
        v.pruefe_uebergang(v.SyncZustand.FEHLGESCHLAGEN, v.SyncZustand.ABGESCHLOSSEN)


# ------------------------------------------------------------ Fehler-Taxonomie

def test_fehler_erben_von_banksyncfehler():
    for klasse in (v.KonfigFehler, v.NichtScharf, v.VerbindungsFehler, v.AuthFehler,
                   v.TanFehler, v.TeilAbrufFehler, v.FormatFehler, v.ZustandsFehler):
        assert issubclass(klasse, v.BankSyncFehler)


def test_retry_politik_fail_closed():
    # Default der Basis: KEIN Auto-Retry (unbekannter Fehler ⇒ Mensch schaut drauf).
    assert v.BankSyncFehler.retry_erlaubt is False
    # AuthFehler darf NIE automatisch wiederholt werden (PIN-Sperre!).
    assert v.AuthFehler.retry_erlaubt is False
    assert v.TanFehler.retry_erlaubt is False
    assert v.NichtScharf.retry_erlaubt is False
    assert v.KonfigFehler.retry_erlaubt is False
    assert v.FormatFehler.retry_erlaubt is False
    # Nur Transport-/Teil-Abruf-Fehler sind automatisch (Backoff) wiederholbar.
    assert v.VerbindungsFehler.retry_erlaubt is True
    assert v.TeilAbrufFehler.retry_erlaubt is True


# -------------------------------------------------------------- SyncErgebnis

def _ergebnis(**kw):
    basis = dict(zugang_id="z1", zustand=v.SyncZustand.ABGESCHLOSSEN,
                 neue_buchungen=3, duplikate=1)
    basis.update(kw)
    return v.SyncErgebnis(**basis)


def test_ergebnis_nur_terminal():
    with pytest.raises(ValueError):
        _ergebnis(zustand=v.SyncZustand.RUFT_AB)


def test_ergebnis_stilles_leer_verboten():
    with pytest.raises(ValueError):
        _ergebnis(neue_buchungen=0, duplikate=0, leer_bestaetigt=False)


def test_ergebnis_leer_nur_mit_bestaetigung():
    e = _ergebnis(neue_buchungen=0, duplikate=0, leer_bestaetigt=True)
    assert e.leer_bestaetigt


def test_ergebnis_abgeschlossen_widerspricht_fehlertext():
    with pytest.raises(ValueError):
        _ergebnis(fehler="kaputt")


def test_ergebnis_fehlgeschlagen_braucht_text():
    with pytest.raises(ValueError):
        _ergebnis(zustand=v.SyncZustand.FEHLGESCHLAGEN, fehler="")
    e = _ergebnis(zustand=v.SyncZustand.FEHLGESCHLAGEN,
                  neue_buchungen=0, duplikate=0,
                  fehler="Bank nicht erreichbar", fehler_art="VerbindungsFehler")
    assert e.fehler_art == "VerbindungsFehler"


# ---------------------------------------------------------------- BankZugang

def _zugang(**kw):
    basis = dict(zugang_id="hausbank", bank_name="Testbank", blz="12345678",
                 benutzerkennung="superkennung12345",
                 fints_url="https://fints.testbank.example/fints",
                 tan_verfahren=v.TanVerfahren.PUSH_TAN,
                 pin_vault_key="banksync_pin_hausbank")
    basis.update(kw)
    return v.BankZugang(**basis)


def test_zugang_feldflaeche_eingefroren():
    # I-2: Die Fläche ist Vertrag — kein pin-/tan-Wertfeld, keine stillen Zusätze.
    erwartet = {"zugang_id", "bank_name", "blz", "benutzerkennung", "fints_url",
                "tan_verfahren", "pin_vault_key", "konten_iban"}
    assert {f.name for f in dataclasses.fields(v.BankZugang)} == erwartet
    assert v.ZUGANG_FELDER == frozenset(erwartet)


def test_zugang_repr_maskiert_kennung():
    z = _zugang()
    text = repr(z)
    assert "superkennung12345" not in text
    assert "su…" in text and "hausbank" in text


def test_zugang_https_pflicht():
    with pytest.raises(v.KonfigFehler):
        _zugang(fints_url="http://fints.testbank.example/fints")


def test_zugang_blz_und_iban_format():
    with pytest.raises(v.KonfigFehler):
        _zugang(blz="1234")
    with pytest.raises(v.KonfigFehler):
        _zugang(konten_iban=("NICHT-IBAN",))
    z = _zugang(konten_iban=("DE02120300000000202051",))
    assert z.konten_iban == ("DE02120300000000202051",)


def test_zugang_tan_verfahren_aus_string():
    z = _zugang(tan_verfahren="chip_tan_qr")
    assert z.tan_verfahren is v.TanVerfahren.CHIP_TAN_QR
    with pytest.raises(v.KonfigFehler):
        _zugang(tan_verfahren="iris_scan")


# ---------------------------------------------------------- Segment-Whitelist

def test_segment_whitelist_nur_lesend():
    for lesend in ("HKKAZ", "HKCAZ", "HKSAL", "HKTAN", "HKIDN", "HKEND"):
        assert v.segment_erlaubt(lesend), lesend
    for zahlung in ("HKCCS", "HKCCM", "HKCSE", "HKCDE", "HKDSE", "HKIPZ", "HKPPD"):
        assert not v.segment_erlaubt(zahlung), zahlung
    # Doppelboden: kein Whitelist-Eintrag gehört zu einer verbotenen Familie.
    for seg in v.ERLAUBTE_SEGMENTE:
        assert not seg.startswith(v.VERBOTENE_SEGMENT_PRAEFIXE), seg


def test_segment_erlaubt_deny_by_default():
    assert not v.segment_erlaubt("")
    assert not v.segment_erlaubt("HKXYZ")
    assert v.segment_erlaubt(" hkkaz ")      # tolerant in der Form, strikt im Inhalt


# ------------------------------------------------------------- Zwei-Schlüssel

def test_scharfschaltung_braucht_beide_schluessel():
    assert not v.Scharfschaltung("z1").ist_scharf
    assert not v.Scharfschaltung("z1", angelegt_am="2026-07-03").ist_scharf
    assert not v.Scharfschaltung("z1", bestaetigt_am="2026-07-03").ist_scharf
    assert v.Scharfschaltung("z1", angelegt_am="2026-07-03",
                             bestaetigt_am="2026-07-03").ist_scharf


def test_pruefe_scharf_fail_closed():
    with pytest.raises(v.NichtScharf):
        v.pruefe_scharf(None)
    with pytest.raises(v.NichtScharf):
        v.pruefe_scharf(v.Scharfschaltung("z1", angelegt_am="2026-07-03"))


def test_fints_quelle_wachter_vor_wire():
    # I-3: Der Zwei-Schlüssel-Wächter greift VOR dem (fehlenden) Wire.
    quelle = v.FinTSQuelle(_zugang(), v.Scharfschaltung("hausbank"))
    with pytest.raises(v.NichtScharf):
        quelle.hole_auszuege("2026-06-01", "2026-07-03")


def test_fints_quelle_stufe0_ehrlich_nicht_implementiert():
    scharf = v.Scharfschaltung("hausbank", angelegt_am="2026-07-03",
                               bestaetigt_am="2026-07-03")
    quelle = v.FinTSQuelle(_zugang(), scharf)
    with pytest.raises(NotImplementedError):
        quelle.hole_auszuege("2026-06-01", "2026-07-03")


def test_aggregator_quelle_gegated():
    with pytest.raises(NotImplementedError):
        v.AggregatorQuelle().hole_auszuege("2026-06-01", "2026-07-03")


# ------------------------------------------------------- DateiQuelle (Stufe 0)

_CAMT_MINI = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
              '<BkToCstmrStmt><Stmt></Stmt></BkToCstmrStmt></Document>')
_MT940_MINI = ":20:REF123\n:25:12345678/0000202051\n:28C:1/1\n:60F:C260701EUR100,00\n:61:2607010701C123,45NTRF//BANKREF\n:86:?20Testzweck?32Absender\n:62F:C260701EUR223,45\n-"


def test_datei_quelle_erkennt_camt():
    auszuege = v.DateiQuelle(_CAMT_MINI).hole_auszuege("2026-06-01", "2026-07-03")
    assert len(auszuege) == 1
    assert auszuege[0].format is v.AuszugsFormat.CAMT_053
    assert auszuege[0].vollstaendig and auszuege[0].quelle_id == "datei"


def test_datei_quelle_erkennt_mt940_auch_aus_bytes():
    auszuege = v.DateiQuelle(_MT940_MINI.encode("latin-1")).hole_auszuege("", "")
    assert auszuege[0].format is v.AuszugsFormat.MT940


def test_datei_quelle_lehnt_csv_ab():
    with pytest.raises(v.FormatFehler):
        v.DateiQuelle("datum;betrag\n01.07.2026;-9,99").hole_auszuege("", "")


def test_quellen_erfuellen_umsatzquelle_protokoll():
    assert isinstance(v.DateiQuelle(_CAMT_MINI), v.UmsatzQuelle)
    assert isinstance(v.FinTSQuelle(_zugang(), None), v.UmsatzQuelle)
    assert isinstance(v.AggregatorQuelle(), v.UmsatzQuelle)


# ------------------------------------------------- Quelle → importers-Brücke

def test_als_import_auftrag_dispatch_kompatibel():
    auszug = v.DateiQuelle(_CAMT_MINI).hole_auszuege("2026-06-01", "2026-07-03")[0]
    auftrag = v.als_import_auftrag(auszug, zielkonto_id="k42")
    assert auftrag["format"] in dispatch.FORMATE          # I-5: kein Übersetzen
    assert auftrag["zielkonto"] == "k42"
    assert auftrag["quelle"] == "banksync:datei"
    assert auftrag["inhalt"] == _CAMT_MINI


def test_als_import_auftrag_verwirft_teilabruf():
    teil = v.RohAuszug(format=v.AuszugsFormat.MT940, inhalt=":20:x",
                       vollstaendig=False, quelle_id="fints")
    with pytest.raises(v.TeilAbrufFehler):
        v.als_import_auftrag(teil, "k42")


def test_format_kuerzel_sind_dispatch_kuerzel():
    for fmt in v.AuszugsFormat:
        assert fmt.value in dispatch.FORMATE


# ------------------------------------------------------------ Fenster-Politik

def test_abruf_fenster_erstlauf_tan_arm():
    von, bis = v.abruf_fenster(None, heute="2026-07-03")
    assert bis == "2026-07-03"
    assert von == "2026-05-04"                            # 60 Tage, < 90 ⇒ TAN-arm
    assert not v.tan_wahrscheinlich(von, "2026-07-03")


def test_abruf_fenster_folge_mit_ueberlapp():
    stand = v.SyncStand("z1", letzter_erfolg_bis="2026-07-01")
    von, bis = v.abruf_fenster(stand, heute="2026-07-03")
    assert (von, bis) == ("2026-06-28", "2026-07-03")     # 3 Tage Überlapp


def test_abruf_fenster_uhranomalie_fail_safe():
    stand = v.SyncStand("z1", letzter_erfolg_bis="2026-07-10")
    von, bis = v.abruf_fenster(stand, heute="2026-07-03")
    assert von == bis == "2026-07-03"


def test_tan_wahrscheinlich_bei_grosser_historie():
    assert v.tan_wahrscheinlich("2026-01-01", "2026-07-03")
