"""Vorsteuer-Rechner — §15-Abzugs-Modell + §15-Abs.-4-Aufteilung (M4-3, docs/68 §7).
KEINE echte UStVA, KEINE Steuer-BERATUNG.

Die Rechen-/Erfassungs-Schicht UNTER dem Vertrag (``vertrag.py`` bleibt normativ +
UNANGETASTET — genau wie ``monitor.py`` unter M4-2). Der Vertrag liefert das
Vorsteuer-MODELL (``VorsteuerStatus``, ``VorsteuerVerbotsGrund``, ``UstSplit``,
``split_aus_brutto``, ``BEWIRTUNG_VOST_VOLL``) und SPERRT ``TEILWEISE`` in der
Klassifikation (v1: ``_pruefe_fachlogik`` wirft) — die §15-Abs.-4-Aufteilung darf
kein stiller Prozentsatz in einem Klassifikations-Feld sein. Dieses Modul baut das,
was der Vertrag M4-3 ausdrücklich überlässt (docs/68 §7/§11/§14):

  * ``abziehbare_vorsteuer`` — der abziehbare Betrag einer Eingangs-Klassifikation
    (``ABZIEHBAR`` ⇒ volle Beleg-USt aus dem Split · ``NICHT_ABZIEHBAR`` ⇒ 0),
  * ``VorsteuerAufteilung`` — die §15-Abs.-4-Aufteilung als EIGENER, dokumentierter
    Datensatz (nicht als gesperrtes Klassifikations-``TEILWEISE``): die volle
    Vorsteuer zerfällt nach einem DOKUMENTIERTEN Schlüssel in abziehbar +
    nicht-abziehbar; die ``begruendung`` ist PFLICHT (nie ein stiller %),
  * ``beleg_pflicht_verletzt`` — die Warnregel „ABZIEHBAR ohne Beleg-Ref": ein
    Abzug ohne die Beleg-Kante ``buchungen.beleg_ref`` (V15, ``admin:dokument:<id>``)
    ist formal nicht nachgewiesen (§15 Abs. 1 verlangt eine ordnungsgemäße Rechnung),
  * ``bewirtung_vorsteuer`` / ``bewirtung_vergleich`` — die dokumentierte
    Bewirtungs-Falle: Vorsteuer zu 100 % abziehbar, obwohl ertragsteuerlich nur
    70 % Betriebsausgabe (§15 Abs. 1a S. 2 — die USt-Achse und die EÜR-Achse fallen
    BEWUSST auseinander; wer die 70 % auf die Vorsteuer durchschlägt, verschenkt Geld).

REINE LOGIK: kein DB-Zugriff, kein FastAPI, keine Ledger-Berührung (U-4). Die
Orchestrierung (Persistenz, Bewegungen über die injizierte Naht, HTTP) liegt in
``persistenz.py``; der Vertrag bleibt die EINE Wahrheit über Split/Status/Gründe.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, fields

from .vertrag import (
    BEWIRTUNG_VOST_VOLL,
    Klassifikation,
    KonfigFehler,
    UstSplit,
    VorsteuerStatus,
    VorsteuerVerbotsGrund,
    split_aus_brutto,
)

# --------------------------------------------------------------- Anteils-Konstanten

#: Voller / kein Abzug in Promille (0..1000). Eine echte Aufteilung liegt STRIKT
#: dazwischen: 100 % ist ``ABZIEHBAR``, 0 % ist ``NICHT_ABZIEHBAR`` — beides gehört
#: in die normale Klassifikation, nicht in eine §15-Abs.-4-Aufteilung (s. u.).
VOLL_ABZIEHBAR_PROMILLE = 1000
NICHT_ABZIEHBAR_PROMILLE = 0

#: ★ Bewirtungs-Falle (docs/68 §7): der ertragsteuerliche Betriebsausgaben-Anteil
#: (§4 Abs. 5 Nr. 2 EStG) sind 70 % — er lebt AUSSCHLIESSLICH auf der EÜR-Achse
#: (``steuer_art``), NIE auf der Vorsteuer. Anker für die Gegenüberstellung, nie
#: ein Vorsteuer-Faktor.
BEWIRTUNG_EUER_PROMILLE = 700


class AufteilungsSchluessel(str, enum.Enum):
    """Der DOKUMENTIERTE Aufteilungs-Maßstab (§15 Abs. 4): die Vorsteuer aus einem
    gemischt (unternehmerisch abziehbar / abzugsschädlich) verwendeten Eingang wird
    nach einem SACHGERECHTEN Schlüssel zerlegt. Der Schlüssel ist Teil der
    Doku-Pflicht — nie ein stiller Prozentsatz. Geschlossene Enum: ``UMSATZSCHLUESSEL``
    ist nach §15 Abs. 4 S. 3 NACHRANGIG (nur zulässig, wenn keine andere
    wirtschaftliche Zurechnung möglich ist) — der Vertrag/dieses Modul erzwingt die
    Rangfolge NICHT (das ist Sachverhalts-Würdigung des Menschen), macht die Wahl
    aber sichtbar und dokumentiert."""
    FLAECHENSCHLUESSEL = "flaechenschluessel"    # z. B. Gebäude nach genutzten m²
    ZEITSCHLUESSEL = "zeitschluessel"            # nach Nutzungs-/Verwendungszeit
    INDIVIDUELL = "individuell"                  # anderer sachgerechter Maßstab (begründet)
    UMSATZSCHLUESSEL = "umsatzschluessel"        # nach Verwendungs-Umsätzen (§15 Abs.4 S.3, nachrangig)


#: Zulässige Gründe für den NICHT-abziehbaren Teil einer Aufteilung (§15 Abs. 4):
#: der Rest dient entweder steuerfreien (abzugsschädlichen) Umsätzen (§15 Abs. 2)
#: oder der nichtunternehmerischen/privaten Sphäre. Die übrigen ``VorsteuerVerbotsGrund``
#: (keine Rechnung, §15 Abs. 1a) sind KEINE Aufteilungs-, sondern Voll-Verbots-Gründe.
AUFTEILUNG_GRUENDE: frozenset[VorsteuerVerbotsGrund] = frozenset({
    VorsteuerVerbotsGrund.STEUERFREIE_VERWENDUNG,
    VorsteuerVerbotsGrund.PRIVAT,
})


# ----------------------------------------------------------------- Aufteilungs-Mathe

def aufteilen(ust_cent: int, abziehbar_promille: int) -> int:
    """Der abziehbare Vorsteuer-Betrag aus dem dokumentierten Schlüssel-Anteil
    (Promille, 0..1000). **Konservativ ABGERUNDET** (Richtung Null): nie mehr
    Vorsteuer ziehen als der Schlüssel exakt hergibt — dieselbe fail-closed-Richtung
    wie das §19-Gesamtumsatz-Maß (docs/68 §6: der zulässige Fehler zeigt nie Richtung
    „zu viel gezogen"). Der Anteil SELBST ist Doku (``VorsteuerAufteilung.begruendung``),
    diese Funktion rechnet nur — sie rät nichts."""
    if ust_cent < 0:
        raise KonfigFehler("aufteilen: ust_cent ist betragsmäßig (>= 0)")
    if not (0 <= abziehbar_promille <= 1000):
        raise KonfigFehler(
            f"aufteilen: abziehbar_promille {abziehbar_promille!r} außerhalb 0..1000")
    return ust_cent * abziehbar_promille // 1000    # abgerundet (konservativ)


@dataclass(frozen=True)
class VorsteuerAufteilung:
    """§15-Abs.-4-Aufteilung einer TEILWEISE abziehbaren Vorsteuer — die M4-3-Antwort
    auf das vom Vertrag bewusst gesperrte Klassifikations-``TEILWEISE`` (docs/68
    §7/§14). Ein EIGENER, dokumentierter Datensatz: die volle Vorsteuer (``ust_cent``,
    aus dem Beleg-Split) zerfällt nach einem DOKUMENTIERTEN Schlüssel in
    ``abziehbar_cent`` + ``nicht_abziehbar_cent``.

    Konstruktive Invarianten (wie ``UstSplit`` — Summe & Ableitung sind Gesetz,
    nie Toleranz):
      * ``begruendung`` ist PFLICHT (nie leer) — §15 Abs. 4 verlangt einen
        nachvollziehbaren Schlüssel, kein stiller Prozentsatz,
      * der Anteil ist STRIKT partiell (0 < promille < 1000): 100 % ist ``ABZIEHBAR``,
        0 % ist ``NICHT_ABZIEHBAR`` — beides gehört in die normale Klassifikation,
      * ``abziehbar_cent == aufteilen(ust_cent, abziehbar_promille)`` (der Betrag ist
        aus dem dokumentierten Anteil ABGELEITET, nie frei daneben gesetzt),
      * ``grund_nicht_abziehbar`` ∈ {steuerfreie Verwendung, privat} — die zwei
        echten §15-Abs.-4-Fälle."""

    buchung_id: str
    ust_cent: int                       # volle Vorsteuer aus dem Beleg-Split
    abziehbar_promille: int             # der DOKUMENTIERTE Schlüssel-Anteil (0<..<1000)
    abziehbar_cent: int                 # abgeleitet: aufteilen(ust_cent, promille)
    schluessel: AufteilungsSchluessel
    begruendung: str                    # Doku-Pflicht — nie leer
    grund_nicht_abziehbar: VorsteuerVerbotsGrund = VorsteuerVerbotsGrund.STEUERFREIE_VERWENDUNG

    def __post_init__(self) -> None:
        if not str(self.buchung_id).strip():
            raise KonfigFehler("VorsteuerAufteilung: buchung_id fehlt")
        if isinstance(self.schluessel, str) and not isinstance(self.schluessel, AufteilungsSchluessel):
            try:
                object.__setattr__(self, "schluessel", AufteilungsSchluessel(self.schluessel))
            except ValueError:
                raise KonfigFehler(f"VorsteuerAufteilung: unbekannter Schlüssel {self.schluessel!r}")
        if isinstance(self.grund_nicht_abziehbar, str) and not isinstance(
                self.grund_nicht_abziehbar, VorsteuerVerbotsGrund):
            try:
                object.__setattr__(self, "grund_nicht_abziehbar",
                                   VorsteuerVerbotsGrund(self.grund_nicht_abziehbar))
            except ValueError:
                raise KonfigFehler(
                    f"VorsteuerAufteilung: unbekannter Grund {self.grund_nicht_abziehbar!r}")
        if not str(self.begruendung).strip():
            raise KonfigFehler(
                "VorsteuerAufteilung: begruendung ist PFLICHT — §15 Abs. 4 verlangt "
                "einen dokumentierten Schlüssel, nie einen stillen Prozentsatz (docs/68 §7)")
        if self.ust_cent < 0:
            raise KonfigFehler("VorsteuerAufteilung: ust_cent ist betragsmäßig (>= 0)")
        if not (NICHT_ABZIEHBAR_PROMILLE < self.abziehbar_promille < VOLL_ABZIEHBAR_PROMILLE):
            raise KonfigFehler(
                "VorsteuerAufteilung: abziehbar_promille muss STRIKT zwischen 0 und 1000 "
                "liegen (eine echte Aufteilung ist partiell) — 100 % ist ABZIEHBAR, "
                "0 % ist NICHT_ABZIEHBAR, beides gehört in die normale Klassifikation")
        soll = aufteilen(self.ust_cent, self.abziehbar_promille)
        if self.abziehbar_cent != soll:
            raise KonfigFehler(
                f"VorsteuerAufteilung: abziehbar_cent {self.abziehbar_cent} != aus dem "
                f"Schlüssel abgeleiteten {soll} — der Betrag folgt dem dokumentierten "
                "Anteil, wird nie frei daneben gesetzt")
        if self.grund_nicht_abziehbar not in AUFTEILUNG_GRUENDE:
            raise KonfigFehler(
                f"VorsteuerAufteilung: grund_nicht_abziehbar {self.grund_nicht_abziehbar.value!r} "
                "ist kein §15-Abs.-4-Aufteilungsgrund — zulässig sind steuerfreie "
                "Verwendung (§15 Abs. 2) oder privat/nichtunternehmerisch")

    @property
    def nicht_abziehbar_cent(self) -> int:
        return self.ust_cent - self.abziehbar_cent

    @property
    def anteil_prozent(self) -> float:
        """Der abziehbare Anteil in Prozent (informativ, aus dem Promille-Schlüssel)."""
        return round(self.abziehbar_promille / 10, 1)


def aufteilung_aus_brutto(buchung_id: str, brutto_cent: int, satz_promille: int,
                          abziehbar_promille: int, schluessel: AufteilungsSchluessel | str,
                          begruendung: str,
                          grund_nicht_abziehbar: VorsteuerVerbotsGrund | str
                          = VorsteuerVerbotsGrund.STEUERFREIE_VERWENDUNG,
                          *, ust_cent: int | None = None) -> tuple[UstSplit, VorsteuerAufteilung]:
    """Baut Split + dokumentierte Aufteilung aus dem ZAHLBETRAG (docs/68 §7): der
    Vertrags-Split (``split_aus_brutto``) zerlegt das Brutto in netto/ust — ``ust_cent``
    gesetzt ⇒ **Belegausweis schlägt Rechenweg** (§7). Der abziehbare Betrag wird aus
    dem dokumentierten ``abziehbar_promille`` ABGELEITET (``aufteilen``). Wirft
    ``KonfigFehler`` bei fehlender Doku / unzulässigem Anteil (der Vertrag/dieser Bau
    ist der Torwächter — nichts Ungültiges entsteht)."""
    if ust_cent is None:
        split = split_aus_brutto(int(brutto_cent), int(satz_promille))
    else:
        # Belegausweis (§7): der ausgewiesene USt-Betrag gilt, netto = brutto − ust.
        split = UstSplit(brutto_cent=int(brutto_cent), netto_cent=int(brutto_cent) - int(ust_cent),
                         ust_cent=int(ust_cent), satz_promille=int(satz_promille))
    if split.ust_cent <= 0:
        raise KonfigFehler(
            "aufteilung_aus_brutto: kein USt-Betrag zum Aufteilen (Satz 0 / Beleg 0) — "
            "eine §15-Abs.-4-Aufteilung setzt ausgewiesene Vorsteuer voraus")
    aufteilung = VorsteuerAufteilung(
        buchung_id=buchung_id, ust_cent=split.ust_cent,
        abziehbar_promille=int(abziehbar_promille),
        abziehbar_cent=aufteilen(split.ust_cent, int(abziehbar_promille)),
        schluessel=schluessel, begruendung=begruendung,
        grund_nicht_abziehbar=grund_nicht_abziehbar)
    return split, aufteilung


# --------------------------------------------------------- Abzug aus Klassifikation

def abziehbare_vorsteuer(k: Klassifikation) -> int:
    """Der abziehbare Vorsteuer-Betrag einer Eingangs-Klassifikation aus ihrem
    Beleg-Split (§15): ``ABZIEHBAR`` ⇒ die volle Beleg-USt · sonst 0. **Kein Abzug
    ohne expliziten Status** (docs/68 §7): ``None``/``NICHT_ABZIEHBAR`` liefern 0, es
    gibt kein stilles Default. Kategorien ohne Split (ig-Erwerb/§13b/EUSt) tragen ihre
    Vorsteuer nicht im Zahlbetrag — deren rechnerische Vorsteuer (Satz × Netto bzw.
    EUSt-Betrag) aggregiert M4-4 am KZ-Katalog; hier zählt nur der belegte Split."""
    if k.vorsteuer_status is not VorsteuerStatus.ABZIEHBAR:
        return 0
    return k.split.ust_cent if k.split is not None else 0


# ------------------------------------------------------------------ Bewirtungs-Falle

def bewirtung_vorsteuer(ust_cent: int) -> int:
    """★ Bewirtungs-Falle (docs/68 §7, §15 Abs. 1a S. 2 UStG): die Vorsteuer aus
    angemessener, nachgewiesener Bewirtung ist zu **100 % abziehbar** — obwohl
    ertragsteuerlich nur 70 % Betriebsausgabe sind. Wer die 70 % auf die Vorsteuer
    durchschlägt, verschenkt Geld. Anker = die Vertrags-Konstante ``BEWIRTUNG_VOST_VOLL``
    (die USt- und die EÜR-Achse fallen hier BEWUSST auseinander)."""
    if not BEWIRTUNG_VOST_VOLL:     # Vertrags-Konstante — dreht sie je, dreht sie hier mit
        raise KonfigFehler("bewirtung_vorsteuer: BEWIRTUNG_VOST_VOLL ist aus — Rechtsstand prüfen")
    if ust_cent < 0:
        raise KonfigFehler("bewirtung_vorsteuer: ust_cent ist betragsmäßig (>= 0)")
    return ust_cent     # volle Vorsteuer, NIE die 70 %-Kürzung


def bewirtung_vergleich(netto_cent: int, ust_cent: int) -> dict:
    """Die dokumentierte Gegenüberstellung der beiden Achsen für eine Bewirtung —
    rein informativ (KEINE EÜR-Buchung, kein Vorsteuer-Faktor): Vorsteuer **voll**
    (§15 Abs. 1a S. 2), Betriebsausgabe nur **70 %** (§4 Abs. 5 Nr. 2 EStG). Macht die
    Falle in der UI sichtbar; die 70 %-Kürzung lebt allein auf ``steuer_art`` (EÜR)."""
    if min(netto_cent, ust_cent) < 0:
        raise KonfigFehler("bewirtung_vergleich: Beträge sind betragsmäßig (>= 0)")
    return {
        "vorsteuer_abziehbar_cent": bewirtung_vorsteuer(ust_cent),      # 100 %
        "euer_betriebsausgabe_cent": int(netto_cent) * BEWIRTUNG_EUER_PROMILLE // 1000,  # 70 %
        "hinweis": "Vorsteuer 100 % abziehbar (§15 Abs. 1a S. 2) — ertragsteuerlich nur "
                   "70 % Betriebsausgabe (§4 Abs. 5 Nr. 2 EStG). Die USt- und die "
                   "EÜR-Achse fallen bewusst auseinander; die 70 % NIE auf die Vorsteuer.",
    }


# -------------------------------------------------- Beleg-Ref-Kopplung (V15-Warnregel)

def hat_beleg_ref(beleg_ref: str) -> bool:
    """Trägt die Buchung eine V15-Beleg-Kante (``buchungen.beleg_ref`` =
    ``admin:dokument:<id>``)? Der Nachweis-Anker für §15-Abs.-1-Vorsteuer."""
    return (beleg_ref or "").strip().startswith("admin:dokument:")


def beleg_pflicht_verletzt(status: VorsteuerStatus | None, beleg_ref: str) -> bool:
    """Warnregel „ABZIEHBAR ohne Beleg-Ref" (docs/68 §7): ein ABZIEHBARER
    Vorsteuer-Abzug braucht eine ordnungsgemäße Rechnung (§15 Abs. 1) — der
    Nachweis-Anker ist die Beleg-Kante ``buchungen.beleg_ref``. Fehlt sie, ist der
    Abzug formal nicht belegt ⇒ WARNUNG (kein Block: Kleinbetragsrechnungen ≤ 250 €
    genügen erleichtert, der Beleg kann auch außerhalb Money liegen; aber ehrlich
    gewarnt wird). Nur ``ABZIEHBAR`` ist betroffen — ``NICHT_ABZIEHBAR``/kein Status
    zieht nichts, braucht also keinen Beleg."""
    return status is VorsteuerStatus.ABZIEHBAR and not hat_beleg_ref(beleg_ref)


#: Vertrags-Anker für den Feld-Flächen-Test (docs/68 §3-Geist): eine Erweiterung der
#: Aufteilung ist eine bewusste Änderung, nie ein stilles Zusatzfeld.
AUFTEILUNG_FELDER: frozenset[str] = frozenset(f.name for f in fields(VorsteuerAufteilung))
