"""UStVA-VERTRAG (docs/68) — Verträge-als-Code, Stufe 0. KEINE ECHTE UStVA.

Normative Quelle für die USt-Datenschicht von Dizz Money (M-4, die zweite
Steuer-Filing-Schiene): Klassifikations-Modell Buchung → ``UStKategorie`` →
Kennziffern-Katalog, §19-Kleinunternehmer-Status, Vorsteuer-Abzugs-Modell und
die hash-gebundene Übergabe an M-2 (Plausibilisierung, Bau-KI) / M-1 (Transport,
docs/65). Stufe 0 ist wertgleich zum Ist: NICHTS rechnet gegen Echtdaten,
nichts wird erzeugt oder übermittelt — aber jeder Wächter existiert schon VOR
der Funktion (Sicherheitspfad vor Feature; Zwilling-Muster docs/64/65).

HÄRTUNGS-INVARIANTEN (docs/68 §1, hier als Code erzwungen):
  U-1  FAIL-CLOSED-KLASSIFIKATION: eine Buchung ohne expliziten Regel-Treffer
       oder manuellen Entscheid blockiert den GESAMTEN Zeitraum
       (``KlassifikationUnklar`` trägt die Buchungs-IDs). Keine Heuristik,
       kein Betrags-/Text-Raten, keine KI — geld-/rechtskritisch gibt es
       kein stilles Default.
  U-2  KEIN RECHT RATEN: Schwellen (§19) und KZ-Zuordnungen leben in
       JAHRES-Tabellen; ein Jahr ohne Eintrag wirft ``SchwellenUnbekannt``/
       ``KatalogUnbekannt``. Jede KZ trägt ``verify=True``, bis M4-4 sie am
       ECHTEN ERiC-Jahres-Schema abgeglichen hat (Nummern aus dem Gedächtnis
       sind semantisch begründet, aber nie Vertrauens-Basis).
  U-3  §19-KONFLIKTE SIND HART: im Kleinunternehmer-Status ist ein
       ``UStVADatensatz`` NICHT KONSTRUIERBAR, USt-Ausweis und
       Vorsteuer-Abzug werfen ``KleinunternehmerKonflikt``; ig-Erwerbe/
       §13b-Bezüge im KU-Status werfen ebenfalls (die Steuerschuld kann
       trotz §19 real entstehen — v1 klärt das ein Mensch).
  U-5  HERKUNFTS-MANIFEST: jeder gemeldete KZ-Betrag zerfällt in
       Buchungs-IDs; ``pruefe_summen`` verlangt die lückenlose Herkunft
       (GoBD-Geist: hergeleitet, nie behauptet).
  U-6  HASH-BINDUNG: ``kanonische_serialisierung`` + ``quell_stand`` (sha256
       via ``elster.vertrag.berechne_quell_stand`` — EINE Hash-Konvention für
       die ganze Steuer-Strecke) binden die M-2-``PlausiFreigabe`` an GENAU
       diesen Datenstand; 1 Cent Änderung ⇒ ``GateRot`` in M-1 (docs/65 I-1).
  U-7  RUNDUNG IST GESETZ: BMG in vollen Euro, Centbeträge Richtung Null
       abgeschnitten (``euro_voll``); Steuer aus voll-Euro-BMG ist bei
       19 %/7 % EXAKT ganzzahlig in Cent; die Zahllast ist EINE Funktion
       (``pruefe_summen``), nie verstreute Arithmetik.
  U-8  ZEITRAUM-INTEGRITÄT: ``UStVAZeitraum`` validiert konstruktiv und
       erzeugt exakt das ``SteuerFall.zeitraum``-Format aus docs/65;
       Soll-Versteuerung ist in v1 gesperrt (Money ist der Ist-/Kassen-Pfad).

(U-4 Ledger-unberührt und U-9 Nur-lokal/HITL sind Architektur-Invarianten —
Enforcement: keine Ledger-Spalte, keine Endpoints, kein Cloud-/Auto-Pfad in
diesem Modul; docs/68 §1/§9.)"""

from __future__ import annotations

import calendar
import enum
import json
from dataclasses import dataclass, fields
from typing import Iterable, Mapping

from ..elster.vertrag import (FormularArt, SteuerFall,          # U-6/U-8-Naht
                              berechne_quell_stand)

# ------------------------------------------------------------------ Konstanten

#: Zulässige USt-Sätze in Promille — der Code kennt nur die MENGE; WELCHER Satz
#: für welche Kategorie gilt, ist immer Nutzer-Regel (docs/68 §2), nie Konstante.
SATZ_PROMILLE_ZULAESSIG: frozenset[int] = frozenset({190, 70, 0})

#: ★ Bewirtungs-Falle (docs/68 §7): Vorsteuer aus angemessener, nachgewiesener
#: Bewirtung ist zu 100 % abziehbar, obwohl ertragsteuerlich nur 70 %
#: Betriebsausgabe sind (§15 Abs. 1a S. 2 UStG) — EÜR-Achse und USt-Achse
#: fallen hier BEWUSST auseinander.
BEWIRTUNG_VOST_VOLL = True

#: Plausible Jahres-Spanne für Zeiträume — Tippfehler-Schranke, kein Recht.
JAHR_MIN, JAHR_MAX = 2020, 2100


# ------------------------------------------------------------ Fehler-Taxonomie

class UstvaFehler(Exception):
    """Basis aller USt-Datenschicht-Fehler. Vertrag: fail-closed — unklare
    Klassifikation, unbekanntes Rechts-Jahr oder Summen-Bruch beenden den
    Vorgang sichtbar; NIE stilles Default (geld-/rechtskritisch, docs/68 §1)."""


class KonfigFehler(UstvaFehler):
    """Regel/Klassifikation/Zeitraum/Datensatz strukturell ungültig."""


class KlassifikationUnklar(UstvaFehler):
    """U-1: mindestens eine Buchung des Zeitraums hat keine eindeutige
    USt-Klassifikation (kein Override, keine Kategorie-Regel). Trägt die
    betroffenen Buchungs-IDs — das ist der Arbeitsvorrat der UI (M4-6),
    nie ein Grund zum Raten."""

    def __init__(self, meldung: str, buchung_ids: Iterable[str] = ()) -> None:
        super().__init__(meldung)
        self.buchung_ids: tuple[str, ...] = tuple(buchung_ids)


class SchwellenUnbekannt(UstvaFehler):
    """U-2: für das Jahr existiert kein §19-Schwellen-Eintrag (auch bewusst:
    Jahre < 2025 — das alte 22k/50k-Prognose-Recht wird NICHT modelliert)."""


class KatalogUnbekannt(UstvaFehler):
    """U-2: für das Jahr existiert kein KZ-Katalog — Recht ist Datenstand
    mit jährlichem Pflege-Slot, nie Code-Annahme."""


class KleinunternehmerKonflikt(UstvaFehler):
    """U-3: Vorgang widerspricht dem §19-Status (UStVA-Erzeugung, USt-Ausweis,
    Vorsteuer-Abzug im KU-Status; ig-Erwerb/§13b-Bezug ⇒ manuelle Klärung)."""


class ZeitraumFehler(UstvaFehler):
    """U-8: Zeitraum ungültig oder passt nicht zur Voranmeldungs-Konfiguration
    (z. B. Monats-Zeitraum bei Quartals-Konfig, Erzeugung trotz Befreiung)."""


class SummenFehler(UstvaFehler):
    """U-5/U-7: Datensatz-Arithmetik verletzt — unbekannte/doppelte KZ, falsche
    Einheit, lückenhafte Herkunft oder Zahllast-Widerspruch. Ein Datensatz,
    der hier scheitert, verlässt Money nie."""


# ------------------------------------------------------------------- Zeitraum

class ZeitraumTyp(str, enum.Enum):
    """Voranmeldungs-Rhythmus (docs/68 §2): WELCHER gilt, legt das Finanzamt
    fest (Vorjahres-Zahllast-Schwellen) — Konfiguration + Gate G-M4-ZEITRAUM,
    nie Ableitung im Code."""
    MONAT = "monat"
    QUARTAL = "quartal"
    JAHR_BEFREIT = "jahr_befreit"   # FA-Befreiung: keine Voranmeldungen


class Besteuerung(str, enum.Enum):
    """Ist- vs. Soll-Versteuerung (§20 UStG). Money ist ein Zahlungs-Ledger ⇒
    Ist ist der natürliche Pfad; SOLL bräuchte Leistungs-/Rechnungsdaten, die
    Money nicht führt ⇒ in v1 gesperrt (U-8, ``VoranmeldungsKonfig``)."""
    IST = "ist"
    SOLL = "soll"


@dataclass(frozen=True)
class UStVAZeitraum:
    """EIN Voranmeldungszeitraum (Monat oder Quartal — eine FA-Befreiung ist
    KEIN Zeitraum, sondern die Abwesenheit von Zeiträumen).

    ``schluessel()`` liefert exakt das docs/65-``SteuerFall``-Format
    (``"YYYY-MM"`` / ``"YYYY-Qn"``) — der Kopplungs-Roundtrip ist
    Vertrags-Test (U-8)."""

    jahr: int
    typ: ZeitraumTyp
    nummer: int                 # Monat 1–12 bzw. Quartal 1–4

    def __post_init__(self) -> None:
        if isinstance(self.typ, str) and not isinstance(self.typ, ZeitraumTyp):
            try:
                object.__setattr__(self, "typ", ZeitraumTyp(self.typ))
            except ValueError:
                raise ZeitraumFehler(f"Unbekannter Zeitraum-Typ {self.typ!r}")
        if not (JAHR_MIN <= int(self.jahr) <= JAHR_MAX):
            raise ZeitraumFehler(f"Unplausibles Jahr {self.jahr!r}")
        if self.typ is ZeitraumTyp.JAHR_BEFREIT:
            raise ZeitraumFehler("Befreiung ist kein Voranmeldungszeitraum — "
                                 "es gibt nichts anzumelden (docs/68 §3)")
        grenze = 12 if self.typ is ZeitraumTyp.MONAT else 4
        if not (1 <= int(self.nummer) <= grenze):
            raise ZeitraumFehler(
                f"{self.typ.value}: nummer {self.nummer!r} außerhalb 1–{grenze}")

    def schluessel(self) -> str:
        """docs/65-kompatibler Zeitraum-Schlüssel für ``SteuerFall.zeitraum``."""
        if self.typ is ZeitraumTyp.MONAT:
            return f"{self.jahr}-{self.nummer:02d}"
        return f"{self.jahr}-Q{self.nummer}"

    def grenzen(self) -> tuple[str, str]:
        """(von, bis) als ISO-Datum — das Buchungs-Fenster des Zeitraums
        (Ist-Versteuerung: Periodisierung = Buchungsdatum im Ledger)."""
        if self.typ is ZeitraumTyp.MONAT:
            m_von = m_bis = self.nummer
        else:
            m_von, m_bis = 3 * self.nummer - 2, 3 * self.nummer
        letzter = calendar.monthrange(self.jahr, m_bis)[1]
        return (f"{self.jahr}-{m_von:02d}-01", f"{self.jahr}-{m_bis:02d}-{letzter:02d}")

    def faelligkeit_nominal(self, dauerfrist: bool = False) -> str:
        """NOMINALE Abgabe-Fälligkeit: 10. Tag nach Zeitraum-Ende, +1 Monat
        bei Dauerfristverlängerung. Bewusst „nominal": die Verschiebung auf
        den nächsten Werktag (§108 AO, Feiertage je Land) braucht eine echte
        Feiertags-Quelle — Bau M4-6, hier NICHT geraten (docs/68 §14)."""
        _, bis = self.grenzen()
        jahr, monat = int(bis[:4]), int(bis[5:7])
        monat += 2 if dauerfrist else 1
        while monat > 12:
            monat -= 12
            jahr += 1
        return f"{jahr}-{monat:02d}-10"


@dataclass(frozen=True)
class VoranmeldungsKonfig:
    """Die Zeitraum-/Besteuerungs-Konfiguration (Gate G-M4-ZEITRAUM liefert
    die Fakten; Vertrags-Default = QUARTAL + IST + ohne Dauerfrist — nur ein
    Konfig-Default, nichts rechnet damit)."""

    zeitraum_typ: ZeitraumTyp = ZeitraumTyp.QUARTAL
    dauerfrist: bool = False
    besteuerung: Besteuerung = Besteuerung.IST

    def __post_init__(self) -> None:
        if isinstance(self.zeitraum_typ, str) and not isinstance(self.zeitraum_typ, ZeitraumTyp):
            try:
                object.__setattr__(self, "zeitraum_typ", ZeitraumTyp(self.zeitraum_typ))
            except ValueError:
                raise KonfigFehler(f"Unbekannter Zeitraum-Typ {self.zeitraum_typ!r}")
        if isinstance(self.besteuerung, str) and not isinstance(self.besteuerung, Besteuerung):
            try:
                object.__setattr__(self, "besteuerung", Besteuerung(self.besteuerung))
            except ValueError:
                raise KonfigFehler(f"Unbekannte Besteuerungs-Art {self.besteuerung!r}")
        if self.besteuerung is Besteuerung.SOLL:
            raise KonfigFehler(
                "Soll-Versteuerung ist in v1 gesperrt (U-8): Money führt keine "
                "Leistungs-/Rechnungsdaten — Ist-Versteuerung ist der Kassen-Pfad; "
                "§20-Antrag ist Teil von Gate G-M4-ZEITRAUM (docs/68 §2)")


# ------------------------------------------------------- §19-Kleinunternehmer

class BesteuerungsForm(str, enum.Enum):
    KLEINUNTERNEHMER = "kleinunternehmer"    # §19: steuerfrei, keine UStVA
    REGELBESTEUERUNG = "regelbesteuerung"


class StatusGrund(str, enum.Enum):
    """Maschinenlesbarer Grund eines ``StatusBefund`` — nie Form ohne Grund."""
    SCHWELLEN_EINGEHALTEN = "schwellen_eingehalten"
    VERZICHT = "verzicht"                            # §19 Abs. 3, 5-J-Bindung
    VORJAHR_UEBERSCHRITTEN = "vorjahr_ueberschritten"    # > 25 000 € Vorjahr
    LAUFEND_UEBERSCHRITTEN = "laufend_ueberschritten"    # > 100 000 € HART


@dataclass(frozen=True)
class Schwellen:
    """§19-Jahres-Grenzen (Cent). Modus „hart" = die 100 000er-Grenze wirkt
    unterjährig SOFORT; der Umsatz, mit dem sie überschritten wird, unterliegt
    bereits der Regelbesteuerung (JStG-2024-Recht, docs/68 §2/§6)."""
    vorjahr_max_cent: int
    laufend_max_cent: int
    modus: str = "hart"


#: NUR neues Recht (ab 2025). Jahre davor werfen bewusst ``SchwellenUnbekannt``
#: — das alte Prognose-Modell (22k/50k) wird nicht nachgebaut (U-2, docs/68 §14).
SCHWELLEN: dict[int, Schwellen] = {
    2025: Schwellen(vorjahr_max_cent=2_500_000, laufend_max_cent=10_000_000),
    2026: Schwellen(vorjahr_max_cent=2_500_000, laufend_max_cent=10_000_000),
}


def schwellen_fuer(jahr: int) -> Schwellen:
    """Fail-closed-Zugriff auf die §19-Jahres-Tabelle (U-2)."""
    try:
        return SCHWELLEN[int(jahr)]
    except KeyError:
        raise SchwellenUnbekannt(
            f"Keine §19-Schwellen für {jahr!r} hinterlegt — Rechts-Tabelle "
            "pflegen statt raten (U-2, docs/68 §6)")


@dataclass(frozen=True)
class VerzichtsErklaerung:
    """Option zur Regelbesteuerung (§19 Abs. 3): bindet 5 Kalenderjahre."""

    ab_jahr: int
    erklaert_am: str = ""       # ISO — informativ

    def __post_init__(self) -> None:
        if not (JAHR_MIN <= int(self.ab_jahr) <= JAHR_MAX):
            raise KonfigFehler(f"VerzichtsErklaerung: unplausibles Jahr {self.ab_jahr!r}")

    @property
    def bindet_bis_jahr(self) -> int:
        return self.ab_jahr + 4     # 5 Kalenderjahre einschließlich ab_jahr

    def bindet_in(self, jahr: int) -> bool:
        return self.ab_jahr <= jahr <= self.bindet_bis_jahr


@dataclass(frozen=True)
class StatusBefund:
    """Ergebnis der §19-Prüfung: Form + Grund + menschlicher Text — eine Form
    ohne Begründung ist konstruktiv unmöglich (Ehrlichkeit vor Aktivität)."""

    jahr: int
    form: BesteuerungsForm
    grund: StatusGrund
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise KonfigFehler("StatusBefund: text fehlt — nie Form ohne Begründung")


def pruefe_kleinunternehmer(jahr: int, vorjahresumsatz_cent: int,
                            laufender_umsatz_cent: int,
                            verzicht: VerzichtsErklaerung | None = None) -> StatusBefund:
    """DIE §19-Weiche (docs/68 §6). Prüf-Reihenfolge: Rechts-Tabelle (U-2) →
    Verzichts-Bindung → Vorjahres-Grenze (wirkt ab Jahresbeginn) → laufende
    Grenze (wirkt HART unterjährig — der überschreitende Umsatz selbst ist
    bereits steuerpflichtig; den präzisen Schnitt am Ledger-Datum baut M4-2).

    Gesamtumsatz-Maß: vereinnahmte Entgelte (§19 Abs. 2); Abgrenzungs-Detail
    ist VERIFY (M4-2) — bis dahin gilt: im Zweifel MITZÄHLEN (der konservative
    Fehler führt zu „eher UStVA abgeben", nie zu „fälschlich keine")."""
    schwellen = schwellen_fuer(jahr)
    if vorjahresumsatz_cent < 0 or laufender_umsatz_cent < 0:
        raise KonfigFehler("Gesamtumsatz kann nicht negativ sein")
    if verzicht is not None and verzicht.bindet_in(jahr):
        return StatusBefund(jahr, BesteuerungsForm.REGELBESTEUERUNG, StatusGrund.VERZICHT,
                            f"Verzicht nach §19 Abs. 3 bindet bis {verzicht.bindet_bis_jahr}")
    if vorjahresumsatz_cent > schwellen.vorjahr_max_cent:
        return StatusBefund(jahr, BesteuerungsForm.REGELBESTEUERUNG,
                            StatusGrund.VORJAHR_UEBERSCHRITTEN,
                            "Vorjahres-Gesamtumsatz über der §19-Grenze — "
                            "Regelbesteuerung ab Jahresbeginn")
    if laufender_umsatz_cent > schwellen.laufend_max_cent:
        return StatusBefund(jahr, BesteuerungsForm.REGELBESTEUERUNG,
                            StatusGrund.LAUFEND_UEBERSCHRITTEN,
                            "Laufende §19-Grenze überschritten — Regelbesteuerung "
                            "SOFORT; bereits der überschreitende Umsatz ist steuerpflichtig")
    return StatusBefund(jahr, BesteuerungsForm.KLEINUNTERNEHMER,
                        StatusGrund.SCHWELLEN_EINGEHALTEN,
                        "Beide §19-Grenzen eingehalten — Umsätze steuerfrei, "
                        "keine UStVA, kein Vorsteuerabzug")


def pruefe_rechnung_kleinunternehmer(ust_ausgewiesen_cent: int) -> None:
    """Rechnungs-Wächter (U-3): ein Kleinunternehmer weist NIE USt aus —
    ausgewiesene Steuer würde nach §14c geschuldet. Naht für jedes künftige
    Rechnungs-Modul; heute von den Klassifikations-Wächtern mitgetragen."""
    if ust_ausgewiesen_cent > 0:
        raise KleinunternehmerKonflikt(
            "USt-Ausweis im Kleinunternehmer-Status ist verboten — ausgewiesene "
            "Steuer würde nach §14c geschuldet (docs/68 §6)")


# ------------------------------------------------------------- Klassifikation

class UStKategorie(str, enum.Enum):
    """Semantische Zwischenschicht Buchung → KZ (docs/68 §4). GESCHLOSSEN:
    Sachverhalte außerhalb (z. B. §13b-Bau-Detailfälle, §25/§25a, Fahrzeuge,
    §15a, §14c-Ausweis) bleiben unklassifiziert und laufen auf U-1-Rot —
    bewusst, statt falscher Kennziffer."""

    # Ausgangs-/Umsatzseite
    UMSATZ_19 = "umsatz_19"
    UMSATZ_7 = "umsatz_7"
    UMSATZ_STFREI_MIT_VST = "umsatz_stfrei_mit_vst"      # Ausfuhr u. a.
    UMSATZ_IG_LIEFERUNG = "umsatz_ig_lieferung"          # §4 Nr. 1b (ZM!)
    UMSATZ_STFREI_OHNE_VST = "umsatz_stfrei_ohne_vst"    # §4 Nr. 8–29
    UMSATZ_13B_LEISTENDER = "umsatz_13b_leistender"      # Empfänger schuldet
    UMSATZ_EU_B2B = "umsatz_eu_b2b"                      # §18b, nicht steuerbar (ZM!)
    UMSATZ_NICHT_STEUERBAR = "umsatz_nicht_steuerbar"
    # Eingangs-/Erwerbsseite
    ERWERB_IG_19 = "erwerb_ig_19"                        # Steuer entsteht ZUSÄTZLICH
    ERWERB_IG_7 = "erwerb_ig_7"
    BEZUG_13B = "bezug_13b"                              # WIR schulden die Steuer
    EINGANG_VST = "eingang_vst"                          # Rechnung mit USt-Ausweis
    EINGANG_EUST = "eingang_eust"                        # Zahlung = EUSt-Betrag
    EINGANG_OHNE_VST = "eingang_ohne_vst"                # keine USt da (KU-Lieferant …)
    # Neutral
    KEIN_UMSATZ = "kein_umsatz"                          # kein Leistungsaustausch


#: Kategorien, deren Klassifikation einen Brutto-Split trägt (Rechnungs-
#: Zerlegung eines ZAHLBETRAGS). ig-Erwerb/§13b sind bewusst NICHT dabei:
#: dort IST die Zahlung das Netto, die Steuer entsteht per Gesetz zusätzlich
#: (rechnerisch, M4-4) — ein Split wäre die falsche Physik.
MIT_SPLIT: frozenset[UStKategorie] = frozenset({
    UStKategorie.UMSATZ_19, UStKategorie.UMSATZ_7, UStKategorie.EINGANG_VST})

#: Erwarteter Satz je Kategorie (Promille) — Widerspruchs-Schranke, kein Recht.
SATZ_ERWARTUNG: dict[UStKategorie, frozenset[int]] = {
    UStKategorie.UMSATZ_19: frozenset({190}),
    UStKategorie.UMSATZ_7: frozenset({70}),
    UStKategorie.ERWERB_IG_19: frozenset({190}),
    UStKategorie.ERWERB_IG_7: frozenset({70}),
    UStKategorie.BEZUG_13B: frozenset({190, 70}),
    UStKategorie.EINGANG_VST: frozenset({190, 70}),
}

#: Kategorien, an denen ein Vorsteuer-Status hängt (§15-Welt, docs/68 §7).
VST_KATEGORIEN: frozenset[UStKategorie] = frozenset({
    UStKategorie.EINGANG_VST, UStKategorie.EINGANG_EUST,
    UStKategorie.ERWERB_IG_19, UStKategorie.ERWERB_IG_7, UStKategorie.BEZUG_13B})

#: Kategorien, die im Kleinunternehmer-Status auf U-3-Rot laufen: Steuer-
#: Ausweis/Abzug ist verboten; ig-Erwerb/§13b kann trotz §19 Steuer auslösen
#: (Erwerbsschwelle etc.) ⇒ manuelle Klärung, nie still ignoriert.
KU_KONFLIKT_KATEGORIEN: frozenset[UStKategorie] = frozenset({
    UStKategorie.ERWERB_IG_19, UStKategorie.ERWERB_IG_7, UStKategorie.BEZUG_13B})


class KlassifikationsQuelle(str, enum.Enum):
    REGEL = "regel"         # Kategorie-Default (``ust_regeln``)
    MANUELL = "manuell"     # Buchungs-Override (schlägt Regel)


class VorsteuerStatus(str, enum.Enum):
    ABZIEHBAR = "abziehbar"
    NICHT_ABZIEHBAR = "nicht_abziehbar"     # verlangt Verbots-Grund
    TEILWEISE = "teilweise"                 # v1: wirft (§15 Abs. 4 = Bau M4-3)


class VorsteuerVerbotsGrund(str, enum.Enum):
    """Geschlossener Gründe-Katalog (docs/68 §7) — ein NICHT_ABZIEHBAR ohne
    Grund ist konstruktiv unmöglich (Plausi-Futter für M-2)."""
    KEINE_ORDNUNGSGEMAESSE_RECHNUNG = "keine_ordnungsgemaesse_rechnung"
    PARAGRAF_15_1A = "paragraf_15_1a"        # Geschenke > 50 €, Repräsentation …
    KLEINUNTERNEHMER_STATUS = "kleinunternehmer_status"
    PRIVAT = "privat"
    STEUERFREIE_VERWENDUNG = "steuerfreie_verwendung"    # §15 Abs. 2


@dataclass(frozen=True)
class UstSplit:
    """Rechnungs-Zerlegung eines Zahlbetrags: brutto = netto + ust,
    konstruktiv erzwungen (nie zwei unabhängige Rundungen). Beträge sind
    betragsmäßig (>= 0) — die RICHTUNG steckt in der ``UStKategorie``;
    Entgeltminderungen wirken erst auf Aggregations-Ebene (Bau M4-4)."""

    brutto_cent: int
    netto_cent: int
    ust_cent: int
    satz_promille: int

    def __post_init__(self) -> None:
        if self.satz_promille not in SATZ_PROMILLE_ZULAESSIG:
            raise KonfigFehler(f"UstSplit: unzulässiger Satz {self.satz_promille!r} ‰")
        if min(self.brutto_cent, self.netto_cent, self.ust_cent) < 0:
            raise KonfigFehler("UstSplit: Beträge sind betragsmäßig (>= 0) — "
                               "Richtung trägt die UStKategorie")
        if self.netto_cent + self.ust_cent != self.brutto_cent:
            raise KonfigFehler("UstSplit: netto + ust != brutto — die Summen-"
                               "Invariante ist konstruktiv, nie Toleranz")
        if self.satz_promille == 0 and self.ust_cent != 0:
            raise KonfigFehler("UstSplit: Satz 0 verträgt keine USt")


def split_aus_brutto(brutto_cent: int, satz_promille: int) -> UstSplit:
    """DIE Split-Konvention (docs/68 §7): Netto = brutto/(1+Satz) kaufmännisch
    auf den Cent, USt = brutto − netto (Rest — EINE Rundung, Summen-Invariante
    konstruktiv). Weist der Beleg die USt abweichend aus, gilt der Beleg
    (manueller Override, ``quelle=MANUELL``)."""
    if brutto_cent < 0:
        raise KonfigFehler("split_aus_brutto: brutto ist betragsmäßig (>= 0)")
    if satz_promille not in SATZ_PROMILLE_ZULAESSIG:
        raise KonfigFehler(f"split_aus_brutto: unzulässiger Satz {satz_promille!r} ‰")
    nenner = 1000 + satz_promille
    netto = (2 * brutto_cent * 1000 + nenner) // (2 * nenner)   # kaufmännisch
    return UstSplit(brutto_cent=brutto_cent, netto_cent=netto,
                    ust_cent=brutto_cent - netto, satz_promille=satz_promille)


@dataclass(frozen=True)
class KlassifikationsRegel:
    """Kategorie-Default (Hausmuster „Default + Buchung-Override", hier auf
    der Money-Kategorie-Achse — NEBEN ``steuer_relevant``/``steuer_art``,
    der ESt-Achse, die unberührt bleibt)."""

    kategorie_id: str
    ust_kategorie: UStKategorie
    satz_promille: int = 0
    vorsteuer_status: VorsteuerStatus | None = None
    vorsteuer_verbot_grund: VorsteuerVerbotsGrund | None = None

    def __post_init__(self) -> None:
        if not self.kategorie_id.strip():
            raise KonfigFehler("KlassifikationsRegel: kategorie_id fehlt")
        _coerce_enums(self)
        _pruefe_fachlogik(self.ust_kategorie, self.satz_promille,
                          self.vorsteuer_status, self.vorsteuer_verbot_grund,
                          kontext="KlassifikationsRegel")


@dataclass(frozen=True)
class Klassifikation:
    """DER Entscheid je Buchung (Audit-Spur: ``quelle`` sagt Regel oder
    Mensch). Feld-Fläche eingefroren (Vertrags-Test) — Erweiterung = bewusste
    Vertragsänderung in docs/68, nie ein Nebeneffekt."""

    buchung_id: str
    ust_kategorie: UStKategorie
    quelle: KlassifikationsQuelle
    satz_promille: int = 0
    split: UstSplit | None = None
    vorsteuer_status: VorsteuerStatus | None = None
    vorsteuer_verbot_grund: VorsteuerVerbotsGrund | None = None

    def __post_init__(self) -> None:
        if not self.buchung_id.strip():
            raise KonfigFehler("Klassifikation: buchung_id fehlt")
        _coerce_enums(self)
        if isinstance(self.quelle, str) and not isinstance(self.quelle, KlassifikationsQuelle):
            try:
                object.__setattr__(self, "quelle", KlassifikationsQuelle(self.quelle))
            except ValueError:
                raise KonfigFehler(f"Klassifikation: unbekannte Quelle {self.quelle!r}")
        _pruefe_fachlogik(self.ust_kategorie, self.satz_promille,
                          self.vorsteuer_status, self.vorsteuer_verbot_grund,
                          kontext="Klassifikation")
        if self.ust_kategorie in MIT_SPLIT:
            if self.split is None:
                raise KonfigFehler(
                    f"Klassifikation: {self.ust_kategorie.value} verlangt einen "
                    "UstSplit (Rechnungs-Zerlegung des Zahlbetrags)")
            if self.split.satz_promille != self.satz_promille:
                raise KonfigFehler("Klassifikation: Satz und Split-Satz widersprechen sich")
        elif self.split is not None:
            raise KonfigFehler(
                f"Klassifikation: {self.ust_kategorie.value} trägt keinen Split — "
                "bei ig-Erwerb/§13b IST die Zahlung das Netto (Steuer entsteht "
                "zusätzlich, rechnerisch in M4-4); sonst gibt es nichts zu zerlegen")


def _coerce_enums(obj) -> None:
    """String→Enum-Koersion für ust_kategorie/vorsteuer_status/-grund
    (Hausmuster docs/65: tolerant annehmen, hart validieren)."""
    k = obj.ust_kategorie
    if isinstance(k, str) and not isinstance(k, UStKategorie):
        try:
            object.__setattr__(obj, "ust_kategorie", UStKategorie(k))
        except ValueError:
            raise KonfigFehler(f"Unbekannte UStKategorie {k!r}")
    s = obj.vorsteuer_status
    if isinstance(s, str) and not isinstance(s, VorsteuerStatus):
        try:
            object.__setattr__(obj, "vorsteuer_status", VorsteuerStatus(s))
        except ValueError:
            raise KonfigFehler(f"Unbekannter VorsteuerStatus {s!r}")
    g = obj.vorsteuer_verbot_grund
    if isinstance(g, str) and not isinstance(g, VorsteuerVerbotsGrund):
        try:
            object.__setattr__(obj, "vorsteuer_verbot_grund", VorsteuerVerbotsGrund(g))
        except ValueError:
            raise KonfigFehler(f"Unbekannter VorsteuerVerbotsGrund {g!r}")


def _pruefe_fachlogik(kategorie: UStKategorie, satz: int,
                      vst: VorsteuerStatus | None,
                      grund: VorsteuerVerbotsGrund | None, *, kontext: str) -> None:
    """Gemeinsame Widerspruchs-Schranken für Regel + Klassifikation:
    Satz-Erwartung (U-2-Schranke, kein Recht) · Vorsteuer-Status nur in der
    §15-Welt · NICHT_ABZIEHBAR ⇔ Grund · TEILWEISE wirft (v1, docs/68 §7)."""
    erwartet = SATZ_ERWARTUNG.get(kategorie, frozenset({0}))
    if satz not in erwartet:
        raise KonfigFehler(
            f"{kontext}: Satz {satz} ‰ widerspricht {kategorie.value} "
            f"(erwartet: {sorted(erwartet)})")
    if kategorie in VST_KATEGORIEN:
        if vst is None:
            raise KonfigFehler(
                f"{kontext}: {kategorie.value} verlangt einen expliziten "
                "VorsteuerStatus — Abzug ist ein Entscheid, kein Default (U-1)")
        if vst is VorsteuerStatus.TEILWEISE:
            raise KonfigFehler(
                f"{kontext}: TEILWEISE ist in v1 gesperrt — §15-Abs.-4-Aufteilung "
                "braucht erfasste Doku (Bau M4-3, docs/68 §7)")
        if vst is VorsteuerStatus.NICHT_ABZIEHBAR and grund is None:
            raise KonfigFehler(f"{kontext}: NICHT_ABZIEHBAR verlangt einen Verbots-Grund")
        if vst is VorsteuerStatus.ABZIEHBAR and grund is not None:
            raise KonfigFehler(f"{kontext}: ABZIEHBAR verträgt keinen Verbots-Grund")
    else:
        if vst is not None or grund is not None:
            raise KonfigFehler(
                f"{kontext}: {kategorie.value} trägt keinen Vorsteuer-Status "
                "(nicht die §15-Welt)")


def klassifiziere(buchung: Mapping, regeln: Mapping[str, KlassifikationsRegel],
                  overrides: Mapping[str, Klassifikation] | None = None) -> Klassifikation:
    """REINE Lookup-Klassifikation (U-1): Buchungs-Override → Kategorie-Regel →
    sonst ``KlassifikationUnklar``. Keine Heuristik, kein Raten, keine KI.

    ``buchung`` ist das Auswertungs-dict des Hauses (``id``, ``netto``
    Minor-Units signiert, ``kategorie_id`` — wie ``auswertung.eur_jahr``).
    GENAU EINE Zuordnung ist automatisch: ``netto == 0`` (interner Transfer
    zwischen eigenen Konten, Ledger-Semantik) ⇒ ``KEIN_UMSATZ`` — das ist
    dokumentierte Strukturaussage, kein Default."""
    bid = str(buchung.get("id", "") or "")
    if not bid:
        raise KonfigFehler("klassifiziere: Buchung ohne id")
    if overrides and bid in overrides:
        k = overrides[bid]
        if k.buchung_id != bid:
            raise KonfigFehler("klassifiziere: Override gehört zu anderer Buchung")
        return k
    netto = int(buchung.get("netto", 0))
    if netto == 0:
        return Klassifikation(buchung_id=bid, ust_kategorie=UStKategorie.KEIN_UMSATZ,
                              quelle=KlassifikationsQuelle.REGEL)
    kat_id = buchung.get("kategorie_id") or ""
    regel = regeln.get(kat_id)
    if regel is None:
        raise KlassifikationUnklar(
            f"Buchung {bid!r}: keine USt-Regel für Kategorie {kat_id!r} und kein "
            "manueller Entscheid — Zeitraum bleibt blockiert (U-1)", [bid])
    split = (split_aus_brutto(abs(netto), regel.satz_promille)
             if regel.ust_kategorie in MIT_SPLIT else None)
    return Klassifikation(
        buchung_id=bid, ust_kategorie=regel.ust_kategorie,
        quelle=KlassifikationsQuelle.REGEL, satz_promille=regel.satz_promille,
        split=split, vorsteuer_status=regel.vorsteuer_status,
        vorsteuer_verbot_grund=regel.vorsteuer_verbot_grund)


def _im_fenster(datum: str, von: str, bis: str) -> bool:
    d = (datum or "")[:10]
    return bool(d) and von <= d <= bis


def pruefe_vollstaendig(bewegungen: Iterable[Mapping],
                        klassifikationen: Mapping[str, Klassifikation],
                        zeitraum: UStVAZeitraum) -> None:
    """DER Vollständigkeits-Wächter (U-1): JEDE Buchung des Zeitraums mit
    ``netto != 0`` braucht eine Klassifikation; sonst fliegt
    ``KlassifikationUnklar`` mit der ID-Liste (Arbeitsvorrat der UI).
    Erst danach darf ``erzeuge_ustva`` überhaupt rechnen."""
    von, bis = zeitraum.grenzen()
    offene = [str(b.get("id", "") or f"<ohne id #{i}>")
              for i, b in enumerate(bewegungen)
              if _im_fenster(str(b.get("datum", "")), von, bis)
              and int(b.get("netto", 0)) != 0
              and str(b.get("id", "")) not in klassifikationen]
    if offene:
        raise KlassifikationUnklar(
            f"{len(offene)} Buchung(en) im Zeitraum {zeitraum.schluessel()} ohne "
            "USt-Klassifikation — kein Datensatz ohne Vollständigkeit (U-1)", offene)


def pruefe_ku_konflikt(form: BesteuerungsForm,
                       klassifikationen: Iterable[Klassifikation]) -> None:
    """U-3-Matrix: im Kleinunternehmer-Status verboten — USt-Ausweis
    (UMSATZ_19/7 mit ust > 0), Vorsteuer-Abzug (ABZIEHBAR) und die
    Konflikt-Kategorien (ig-Erwerb/§13b: Steuerschuld kann trotz §19
    entstehen ⇒ manuelle Klärung, v1 spielt nicht Steuerberater)."""
    if form is not BesteuerungsForm.KLEINUNTERNEHMER:
        return
    for k in klassifikationen:
        if (k.ust_kategorie in (UStKategorie.UMSATZ_19, UStKategorie.UMSATZ_7)
                and k.split is not None and k.split.ust_cent > 0):
            raise KleinunternehmerKonflikt(
                f"Buchung {k.buchung_id!r}: USt-Ausweis im §19-Status — verboten "
                "(§14c-Risiko); Umsätze des Kleinunternehmers sind steuerfrei (U-3)")
        if k.vorsteuer_status is VorsteuerStatus.ABZIEHBAR:
            raise KleinunternehmerKonflikt(
                f"Buchung {k.buchung_id!r}: Vorsteuer-Abzug im §19-Status — "
                "verboten (kein Abzug für Kleinunternehmer, U-3)")
        if k.ust_kategorie in KU_KONFLIKT_KATEGORIEN:
            raise KleinunternehmerKonflikt(
                f"Buchung {k.buchung_id!r}: {k.ust_kategorie.value} im §19-Status — "
                "die Steuerschuld kann trotz §19 entstehen (Erwerbsschwelle/§13b); "
                "v1: manuell klären, nie still ignorieren (U-3)")


# ------------------------------------------------------------ KZ-Katalog (U-2)

class KzRichtung(str, enum.Enum):
    """Wirkung einer KZ in der Zahllast (macht ``pruefe_summen`` generisch):
    BMG_MIT_SATZ = Steuer rechnerisch aus voll-Euro-BMG × Satz (exakt, U-7) ·
    BMG_INFO = nur Meldung · STEUER = centgenau gemeldet, erhöht · VORSTEUER =
    centgenau, mindert · ABZUG = mindert (Sondervorauszahlung, KZ 39)."""
    BMG_MIT_SATZ = "bmg_mit_satz"
    BMG_INFO = "bmg_info"
    STEUER = "steuer"
    VORSTEUER = "vorsteuer"
    ABZUG = "abzug"


@dataclass(frozen=True)
class KzZuordnung:
    """UStKategorie → Kennziffer(n). ``kz_steuer`` != "" heißt: die Steuer wird
    zusätzlich centgenau als eigene KZ gemeldet (13b-Muster; Satz kommt dann
    aus der Klassifikation, nicht aus dem Katalog). ``verify`` bleibt True,
    bis M4-4 die Nummer am ECHTEN ERiC-Schema bestätigt hat (U-2)."""
    kz: str
    richtung: KzRichtung
    satz_promille: int = 0
    kz_steuer: str = ""
    verify: bool = True

    def __post_init__(self) -> None:
        if not self.kz.strip():
            raise KonfigFehler("KzZuordnung: kz fehlt")
        if self.richtung is KzRichtung.BMG_MIT_SATZ and not self.satz_promille and not self.kz_steuer:
            raise KonfigFehler("KzZuordnung: BMG_MIT_SATZ braucht Satz ODER Steuer-KZ")


#: Kennziffern je UStKategorie und Jahr — Zahlen semantisch begründet
#: (docs/68 §5), aber ALLE verify bis zum ERiC-Schema-Abgleich (M4-4).
#: §13b-Differenzierung (46/47, 73/74) = Zuordnungs-REGEL in docs/68 §5,
#: hier bewusst die Sammel-KZ; Sonder-Tatbestände fehlen bewusst (U-1-Rot).
_KATALOG_2025: dict[UStKategorie, KzZuordnung] = {
    UStKategorie.UMSATZ_19: KzZuordnung("81", KzRichtung.BMG_MIT_SATZ, 190),
    UStKategorie.UMSATZ_7: KzZuordnung("86", KzRichtung.BMG_MIT_SATZ, 70),
    UStKategorie.UMSATZ_IG_LIEFERUNG: KzZuordnung("41", KzRichtung.BMG_INFO),
    UStKategorie.UMSATZ_STFREI_MIT_VST: KzZuordnung("43", KzRichtung.BMG_INFO),
    UStKategorie.UMSATZ_STFREI_OHNE_VST: KzZuordnung("48", KzRichtung.BMG_INFO),
    UStKategorie.UMSATZ_13B_LEISTENDER: KzZuordnung("60", KzRichtung.BMG_INFO),
    UStKategorie.UMSATZ_EU_B2B: KzZuordnung("21", KzRichtung.BMG_INFO),
    UStKategorie.UMSATZ_NICHT_STEUERBAR: KzZuordnung("45", KzRichtung.BMG_INFO),
    UStKategorie.ERWERB_IG_19: KzZuordnung("89", KzRichtung.BMG_MIT_SATZ, 190),
    UStKategorie.ERWERB_IG_7: KzZuordnung("93", KzRichtung.BMG_MIT_SATZ, 70),
    UStKategorie.BEZUG_13B: KzZuordnung("84", KzRichtung.BMG_MIT_SATZ, 0, kz_steuer="85"),
}

#: Vorsteuer-KZ je Kategorie (mindernd; centgenau).
_VORSTEUER_KZ_2025: dict[UStKategorie, KzZuordnung] = {
    UStKategorie.EINGANG_VST: KzZuordnung("66", KzRichtung.VORSTEUER),
    UStKategorie.ERWERB_IG_19: KzZuordnung("61", KzRichtung.VORSTEUER),
    UStKategorie.ERWERB_IG_7: KzZuordnung("61", KzRichtung.VORSTEUER),
    UStKategorie.BEZUG_13B: KzZuordnung("67", KzRichtung.VORSTEUER),
    UStKategorie.EINGANG_EUST: KzZuordnung("62", KzRichtung.VORSTEUER),
}

KZ_SONDERVORAUSZAHLUNG = KzZuordnung("39", KzRichtung.ABZUG)   # letzter Zeitraum
KZ_ZAHLLAST = "83"                                             # berechnet (U-7)


@dataclass(frozen=True)
class KzKatalog:
    """Der vollständige Jahres-Katalog: Umsatz-/Erwerbs-Seite + Vorsteuer-Seite
    + Sonder-KZ. `KEIN_UMSATZ`/`EINGANG_OHNE_VST` haben BEWUSST keine KZ
    (nichts zu melden) — der Test friert das ein."""
    jahr: int
    kategorien: Mapping[UStKategorie, KzZuordnung]
    vorsteuer: Mapping[UStKategorie, KzZuordnung]

    def bekannte_kz(self) -> frozenset[str]:
        kz = {z.kz for z in self.kategorien.values()}
        kz |= {z.kz_steuer for z in self.kategorien.values() if z.kz_steuer}
        kz |= {z.kz for z in self.vorsteuer.values()}
        kz |= {KZ_SONDERVORAUSZAHLUNG.kz, KZ_ZAHLLAST}
        return frozenset(kz)


KZ_KATALOG: dict[int, KzKatalog] = {
    2025: KzKatalog(2025, _KATALOG_2025, _VORSTEUER_KZ_2025),
    2026: KzKatalog(2026, _KATALOG_2025, _VORSTEUER_KZ_2025),   # inhaltsgleich
}


def katalog_fuer(jahr: int) -> KzKatalog:
    """Fail-closed-Zugriff auf den KZ-Jahres-Katalog (U-2)."""
    try:
        return KZ_KATALOG[int(jahr)]
    except KeyError:
        raise KatalogUnbekannt(
            f"Kein KZ-Katalog für {jahr!r} — Jahres-Pflege ist ein bewusster "
            "Wartungs-Slot (U-2, docs/68 §5), nie eine Code-Annahme")


# ------------------------------------------------------------------- Datensatz

class KzEinheit(str, enum.Enum):
    EURO_VOLL = "euro_voll"     # Bemessungsgrundlagen (U-7)
    CENT = "cent"               # Steuer-/Vorsteuer-/Abzugs-Beträge


def euro_voll(cent: int) -> int:
    """U-7: volle Euro, Centbeträge Richtung NULL abgeschnitten — auch für
    negative Beträge (Entgeltminderung: −1234,56 € → −1234 €)."""
    return cent // 100 if cent >= 0 else -((-cent) // 100)


@dataclass(frozen=True)
class KzWert:
    """Ein gemeldeter Kennziffern-Betrag. Einheit ist explizit — BMG-KZ in
    vollen Euro, alles andere centgenau; ``pruefe_summen`` erzwingt die
    richtige Einheit je KZ-Richtung."""
    kz: str
    betrag: int
    einheit: KzEinheit

    def __post_init__(self) -> None:
        if not self.kz.strip():
            raise KonfigFehler("KzWert: kz fehlt")
        if isinstance(self.einheit, str) and not isinstance(self.einheit, KzEinheit):
            try:
                object.__setattr__(self, "einheit", KzEinheit(self.einheit))
            except ValueError:
                raise KonfigFehler(f"KzWert: unbekannte Einheit {self.einheit!r}")


@dataclass(frozen=True)
class HerkunftsPosten:
    """Eine Manifest-Zeile (U-5): KZ ← Buchung ← Betrag (Cent). Der Datensatz
    verlangt Herkunft nur zu vorhandenen KZ; ``pruefe_summen`` verlangt sie
    lückenlos für alles außer KZ 83/39 (berechnet/Bescheid-Wert)."""
    kz: str
    buchung_id: str
    betrag_cent: int

    def __post_init__(self) -> None:
        if not self.kz.strip() or not self.buchung_id.strip():
            raise KonfigFehler("HerkunftsPosten: kz und buchung_id sind Pflicht")


@dataclass(frozen=True)
class UStVADatensatz:
    """DER Produkt-Typ von M-4 (docs/68 §3): ein Voranmeldungs-Datensatz mit
    Herkunfts-Manifest. Konstruktiv unmöglich: KU-Status (U-3), doppelte KZ,
    Herkunft zu fremden KZ. ``kz_werte == ()`` ist die ehrliche NULLMELDUNG
    (auch die ist eine Abgabe). ``erstellt_am`` ist informativ und geht NICHT
    in die Kanonik ein (Inhalt bindet, nicht Uhrzeit — sonst wäre jeder
    Re-Build „stale")."""

    zeitraum: UStVAZeitraum
    besteuerungsform: BesteuerungsForm
    kz_werte: tuple[KzWert, ...] = ()
    herkunft: tuple[HerkunftsPosten, ...] = ()
    berichtigung: bool = False
    erstellt_am: str = ""       # ISO — informativ, NICHT kanonisch

    def __post_init__(self) -> None:
        if isinstance(self.besteuerungsform, str) and not isinstance(self.besteuerungsform, BesteuerungsForm):
            try:
                object.__setattr__(self, "besteuerungsform", BesteuerungsForm(self.besteuerungsform))
            except ValueError:
                raise KonfigFehler(f"Unbekannte Besteuerungsform {self.besteuerungsform!r}")
        if self.besteuerungsform is BesteuerungsForm.KLEINUNTERNEHMER:
            raise KleinunternehmerKonflikt(
                "Ein Kleinunternehmer gibt keine UStVA ab — ein UStVADatensatz "
                "im §19-Status ist konstruktiv unmöglich (U-3, docs/68 §6)")
        object.__setattr__(self, "kz_werte", tuple(self.kz_werte))
        object.__setattr__(self, "herkunft", tuple(self.herkunft))
        kz_liste = [w.kz for w in self.kz_werte]
        if len(kz_liste) != len(set(kz_liste)):
            raise KonfigFehler("UStVADatensatz: doppelte KZ — je Kennziffer EIN Wert")
        fremd = {h.kz for h in self.herkunft} - set(kz_liste)
        if fremd:
            raise KonfigFehler(
                f"UStVADatensatz: Herkunft zu nicht gemeldeten KZ {sorted(fremd)}")


def kanonische_serialisierung(d: UStVADatensatz) -> str:
    """DIE Quelldaten-Kanonik der UStVA-Strecke (U-6, docs/68 §8): kompaktes
    JSON, feste Feld-Reihenfolge, KZ + Herkunft deterministisch sortiert,
    Cent-Ints (nie Float). EIN Produzent, EIN Format — M-2 konsumiert sie,
    M1-7 übernimmt sie (docs/65 §3-Handschlag für den UStVA-Pfad)."""
    payload = {
        "art": "ustva",
        "zeitraum": d.zeitraum.schluessel(),
        "form": d.besteuerungsform.value,
        "berichtigung": d.berichtigung,
        "kz": [[w.kz, w.betrag, w.einheit.value]
               for w in sorted(d.kz_werte, key=lambda w: (len(w.kz), w.kz))],
        "herkunft": [[h.kz, h.buchung_id, h.betrag_cent]
                     for h in sorted(d.herkunft,
                                     key=lambda h: (len(h.kz), h.kz, h.buchung_id))],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def quell_stand(d: UStVADatensatz) -> str:
    """sha256 der Kanonik — DERSELBE Hash-Weg wie M-1 (``berechne_quell_stand``,
    bewusst importiert statt kopiert): die M-2-``PlausiFreigabe`` bindet an
    GENAU diesen Stand; 1 Cent Änderung ⇒ ``GateRot`` (docs/65 I-1)."""
    return berechne_quell_stand(kanonische_serialisierung(d))


def pruefe_summen(d: UStVADatensatz, katalog: KzKatalog) -> int:
    """DIE Zahllast-/Konsistenz-Prüfung (U-5/U-7) — liefert die Zahllast in
    Cent (negativ = Überschuss/Erstattung, ehrlich auszuweisen):

    * jede gemeldete KZ ist im Jahres-Katalog bekannt (sonst ``SummenFehler``),
    * BMG-KZ in EURO_VOLL, Steuer/Vorsteuer/Abzug in CENT,
    * Herkunft lückenlos für jede gemeldete KZ außer 83/39; BMG-Herkunft passt
      nach ``euro_voll`` (Cent-Summe → volle Euro), Cent-KZ centgenau,
    * Zahllast = Σ(BMG_MIT_SATZ: bmg_€ × Satz — bei 19 %/7 % EXAKT ganzzahlig)
      + Σ(STEUER-KZ) − Σ(VORSTEUER-KZ) − KZ 39; ist KZ 83 gemeldet, muss sie
      der Rechnung entsprechen.

    Bekannte, dokumentierte Differenz: Steuer aus abgeschnittener Perioden-BMG
    ≠ Summe der centgenauen Beleg-USt — die Beleg-Summe (Manifest) ist der
    Plausi-Vergleichswert für M-2; die Toleranzregel definiert M-2."""
    bekannte = katalog.bekannte_kz()
    steuer_kz = {z.kz_steuer for z in katalog.kategorien.values() if z.kz_steuer}
    vst_kz = {z.kz for z in katalog.vorsteuer.values()}
    bmg_mit_satz = {z.kz: z.satz_promille for z in katalog.kategorien.values()
                    if z.richtung is KzRichtung.BMG_MIT_SATZ and z.satz_promille}
    bmg_kz = {z.kz for z in katalog.kategorien.values()}

    herkunft_je_kz: dict[str, int] = {}
    for h in d.herkunft:
        herkunft_je_kz[h.kz] = herkunft_je_kz.get(h.kz, 0) + h.betrag_cent

    zahllast = 0
    gemeldet_83: int | None = None
    for w in d.kz_werte:
        if w.kz not in bekannte:
            raise SummenFehler(f"KZ {w.kz!r} ist im Katalog {katalog.jahr} unbekannt "
                               "— nie eine ungeprüfte Kennziffer melden (U-2)")
        ist_bmg = w.kz in bmg_kz
        soll_einheit = KzEinheit.EURO_VOLL if ist_bmg else KzEinheit.CENT
        if w.einheit is not soll_einheit:
            raise SummenFehler(f"KZ {w.kz!r}: Einheit {w.einheit.value!r}, "
                               f"verlangt ist {soll_einheit.value!r} (U-7)")
        if w.kz == KZ_ZAHLLAST:
            gemeldet_83 = w.betrag
            continue
        if w.kz == KZ_SONDERVORAUSZAHLUNG.kz:
            zahllast -= w.betrag
            continue
        summe = herkunft_je_kz.get(w.kz)
        if summe is None:
            raise SummenFehler(f"KZ {w.kz!r} ohne Herkunfts-Manifest — jeder "
                               "Betrag zerfällt in Buchungs-IDs (U-5)")
        if ist_bmg:
            if euro_voll(summe) != w.betrag:
                raise SummenFehler(
                    f"KZ {w.kz!r}: BMG {w.betrag} € entspricht nicht der "
                    f"Herkunft ({summe} Cent → {euro_voll(summe)} €) (U-5/U-7)")
            satz = bmg_mit_satz.get(w.kz, 0)
            if satz:
                zahllast += w.betrag * satz // 10   # €×‰ → Cent, exakt (U-7)
        else:
            if summe != w.betrag:
                raise SummenFehler(
                    f"KZ {w.kz!r}: {w.betrag} Cent entspricht nicht der "
                    f"Herkunfts-Summe {summe} Cent (U-5)")
            if w.kz in steuer_kz:
                zahllast += w.betrag
            elif w.kz in vst_kz:
                zahllast -= w.betrag

    if gemeldet_83 is not None and gemeldet_83 != zahllast:
        raise SummenFehler(
            f"KZ 83 gemeldet {gemeldet_83} Cent, gerechnet {zahllast} Cent — "
            "die Zahllast ist EINE Funktion, kein zweiter Rechenweg (U-7)")
    return zahllast


# ------------------------------------------------------ Erzeugung + Übergabe

def erzeuge_ustva(zeitraum: UStVAZeitraum, konfig: VoranmeldungsKonfig,
                  befund: StatusBefund, bewegungen: Iterable[Mapping],
                  klassifikationen: Mapping[str, Klassifikation]) -> UStVADatensatz:
    """DER Rechner-Einstieg — Stufe 0: ALLE Wächter laufen VOR dem
    NotImplementedError (Sicherheitspfad vor Feature, Hausmuster docs/65):
    §19-Status (U-3) → Befreiung/Zeitraum-Konfig (U-8) → KU-Konflikt-Matrix →
    Vollständigkeit (U-1). Die Aggregation (KZ-Summen, Manifest, beide
    Summen-Sichten) baut Bau-KI in M4-4 — NACH dem ERiC-Schema-Abgleich."""
    if befund.form is BesteuerungsForm.KLEINUNTERNEHMER:
        raise KleinunternehmerKonflikt(
            "Kleinunternehmer (§19): keine UStVA zu erzeugen — der Status ruht, "
            "der Schwellen-Wächter (M4-2) meldet, wenn Regelbesteuerung naht (U-3)")
    if konfig.zeitraum_typ is ZeitraumTyp.JAHR_BEFREIT:
        raise ZeitraumFehler(
            "Voranmeldungs-Befreiung konfiguriert — es gibt keinen Zeitraum "
            "anzumelden (nur Jahreserklärung; docs/68 §3)")
    if zeitraum.typ is not konfig.zeitraum_typ:
        raise ZeitraumFehler(
            f"Zeitraum {zeitraum.schluessel()!r} ({zeitraum.typ.value}) passt "
            f"nicht zur Konfiguration ({konfig.zeitraum_typ.value}) (U-8)")
    pruefe_ku_konflikt(befund.form, klassifikationen.values())
    pruefe_vollstaendig(bewegungen, klassifikationen, zeitraum)
    raise NotImplementedError(
        "Stufe 0: die UStVA-Aggregation ist bewusst nicht implementiert — Bau = "
        "Bau-KI M4-4 nach docs/68 §11 (KZ-Katalog erst am echten ERiC-Schema "
        "verifizieren; VO-5-Reihenfolge bleibt verbindlich).")


def uebergabe_an_filing(d: UStVADatensatz, konfig: VoranmeldungsKonfig,
                        katalog: KzKatalog, *, korrektur_nr: int = 0
                        ) -> tuple[SteuerFall, dict]:
    """Die Naht zu M-1 (docs/68 §8): baut den docs/65-``SteuerFall`` + das
    Quelldaten-dict für den M1-7-``UstvaBauer``. Wächter VOR der Übergabe
    (Defense in depth — M-1 prüft sein Gate selbst erneut):
    Summen/Herkunft (U-5/U-7) · Zeitraum passt zur Konfig (U-8) ·
    Berichtigung ⇔ korrektur_nr (M-1 I-6 regelt den Ablauf).
    KEINE Gate-Prüfung hier: die M-2-``PlausiFreigabe`` prüft ausschließlich
    ``elster.pruefe_gate`` (EIN Gate-Prüfer im Netz, keine zweite Logik)."""
    if d.zeitraum.typ is not konfig.zeitraum_typ:
        raise ZeitraumFehler(
            f"Übergabe: Zeitraum {d.zeitraum.schluessel()!r} passt nicht zur "
            f"Konfiguration ({konfig.zeitraum_typ.value}) (U-8)")
    if d.berichtigung != (korrektur_nr > 0):
        raise KonfigFehler(
            "Übergabe: berichtigung und korrektur_nr widersprechen sich — eine "
            "Berichtigung ist ein bewusster eigener Akt (docs/65 I-6)")
    zahllast = pruefe_summen(d, katalog)
    fall = SteuerFall(formular=FormularArt.USTVA, jahr=d.zeitraum.jahr,
                      zeitraum=d.zeitraum.schluessel(), korrektur_nr=korrektur_nr)
    kanonisch = kanonische_serialisierung(d)
    return fall, {
        "kanonisch": kanonisch,
        "quell_stand_hash": berechne_quell_stand(kanonisch),
        "zahllast_cent": zahllast,
        "beleg_ust_summe_cent": sum(
            k.betrag_cent for k in d.herkunft
            if k.kz in {z.kz_steuer for z in katalog.kategorien.values() if z.kz_steuer}
            | {z.kz for z in katalog.vorsteuer.values()}),
    }


#: Vertrags-Anker für Feld-Flächen-Tests (docs/68 §3): Erweiterung = bewusste
#: Vertragsänderung, nie ein stilles Zusatzfeld.
KLASSIFIKATION_FELDER: frozenset[str] = frozenset(f.name for f in fields(Klassifikation))
DATENSATZ_FELDER: frozenset[str] = frozenset(f.name for f in fields(UStVADatensatz))
