"""ELSTER/ERiC-Transport-VERTRAG (docs/65) — Verträge-als-Code, Stufe 0. KEIN FILING.

Normative Quelle für den ELSTER-Filing-Transport (M-1, Davids D7-Endgame):
Typen, Zustandsmaschine, Fehler-Taxonomie, das Fail-closed-Gate zur (späteren,
Bau-KI-gebauten) M-2-Plausibilisierungs-Engine und die Adapter-Grenze zur nativen
ERiC-C-Bibliothek. Stufe 0 ist wertgleich zum Ist: NICHTS wird gebaut, validiert
oder übermittelt — aber jeder Wächter existiert schon VOR der Funktion
(Sicherheitspfad vor Feature, docs/64-Zwilling: dort kommen Kontodaten LESEND
rein, hier geht die Steuererklärung RAUS — höchste Sorgfaltsklasse des Netzes).

HÄRTUNGS-INVARIANTEN (docs/65 §1, hier als Code erzwungen):
  I-1  FAIL-CLOSED-GATE: kein Senden ohne GRÜNE, FRISCHE ``PlausiFreigabe``
       (M-2-Engine = einziger legitimer Produzent). Frisch = hash-gebunden an
       den Quell-Datenstand; jede Datenänderung nach der Prüfung macht die
       Freigabe stale ⇒ ``GateRot``. Kein Doku-Satz — ``pruefe_sende_freigabe``.
  I-2  GEHEIMNISSE NIE HIER: ``ElsterZugang`` trägt nur den Vault-Schlüssel-
       NAMEN (``pin_vault_key``) + eine Datei-REFERENZ aufs Zertifikat; PIN nur
       im appkit-Vault, zur Laufzeit via ``pin_holen``-Naht in den ERiC-Worker
       (stdin-Pipe, nie argv/env). ``repr`` maskiert die Steuernummer;
       ``ElsterDatensatz.__repr__`` zeigt NIE Steuer-XML (selbst sensibel).
  I-3  ZWEI-SCHLÜSSEL + HERSTELLER-ID: ohne ``Scharfschaltung`` (angelegt UND
       bestätigt) und ohne konfigurierte ERiC-Hersteller-ID (Settings, NIE
       hartkodiert) öffnet der Transport nichts (``NichtScharf``).
  I-4  NIE STILLER ERFOLG: ``FilingErgebnis`` erzwingt konstruktiv
       Erfolg ⇔ Transferticket; offline/Fehler = harter, ehrlicher Abbruch
       (M-3-Prinzip — nie still „0 übertragen").
  I-5  VALIDATE-ONLY VOR JEDEM SENDEN: ``SENDET`` ist ausschließlich aus
       ``VALIDIERT_OK`` erreichbar (Zustandsmaschine, kein Appell).
  I-6  KEINE DOPPEL-ÜBERMITTLUNG: Fall-Schlüssel (formular|jahr|zeitraum) als
       Idempotenz-Anker; Korrektur = bewusste ``korrektur_nr`` NUR über
       FESTGESCHRIEBEN hinweg; unklare Ausgänge blockieren den Zeitraum;
       Senden hat NIE ``retry_erlaubt``.
  I-9  RETRY-POLITIK ALS CODE: ``retry_erlaubt`` je Fehlerklasse, Basis-Default
       False; einzig ``VerbindungsFehler`` (ERiC meldete sauber „nichts raus")
       darf automatisch wiederholt werden.

(I-7 Nur-lokal/Editionen und I-8 Worker-Subprozess sind Architektur-
Invarianten — Enforcement-Ort: docs/65 §1 + Bau-Schritte M1-3/M1-5.)
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, fields
from typing import Callable, Iterable, Protocol, runtime_checkable

# ------------------------------------------------------------------ Konstanten

#: Vault-Schlüssel-Konvention für die Zertifikats-PIN (I-2, appkit.vault.Vault).
PIN_VAULT_PREFIX = "elster_pin_"

#: Plausible Jahres-Spanne für Steuerfälle — Tippfehler-Schranke, kein Recht.
JAHR_MIN, JAHR_MAX = 2020, 2100


# ------------------------------------------------------------ Fehler-Taxonomie

class ElsterFehler(Exception):
    """Basis aller Filing-Fehler. Vertrag: fail-closed — der Lauf endet in einem
    ehrlichen Terminal-Zustand, nie als stilles „übertragen". ``retry_erlaubt``
    ist die maschinenlesbare Retry-Politik; Basis-Default bewusst False
    (unbekannte Fehler wiederholt kein Automat — ein Mensch schaut drauf).
    Die konkrete ERiC-Code→Klasse-Tabelle wird in M1-3/M1-8 aus dem ECHTEN
    ``ericapi.h``/echten Antworten gefüllt (Codes raten = Scheingenauigkeit);
    die Zuordnungs-REGEL ist docs/65 §5 und hier je Klasse dokumentiert."""
    retry_erlaubt = False


class KonfigFehler(ElsterFehler):
    """Zugang/Fall/Datensatz strukturell ungültig (Pfad, Jahr, Zeitraum …)."""


class NichtScharf(ElsterFehler):
    """Zwei-Schlüssel-/Hersteller-ID-Wächter (I-3): Transport nicht scharf."""


class GateRot(ElsterFehler):
    """Fail-closed-Gate (I-1): M-2-Plausibilisierung fehlt, ist rot oder stale
    (Quell-Datenstand hat sich seit der Prüfung geändert). OHNE grünes Gate
    wird NIE gesendet — das ist die harte Vorbedingung, kein Hinweis."""


class DoppelFilingFehler(ElsterFehler):
    """Idempotenz-Schutz (I-6): für diesen Fall-Schlüssel existiert bereits
    eine Übermittlung/ein blockierender Lauf. Eine Korrektur ist ein bewusster
    eigener Akt (``korrektur_nr``), nie ein Retry."""


class ValidierungsFehler(ElsterFehler):
    """ERiC-Validate meldete Fehler ODER es liegt kein grünes Validate-Ergebnis
    vor. Daten korrigieren ist eine NUTZER-Aktion — kein Auto-Retry.
    Regel-Gruppe: ERiC-Plausi-/Schema-Fehlercodes."""


class ZertifikatFehler(ElsterFehler):
    """Zertifikat fehlt/abgelaufen/PIN abgewiesen. NIE automatisch wiederholen
    (Sperr-/Lockout-Risiko wie AuthFehler in docs/64); Fehlertext trägt NIE die
    PIN. Regel-Gruppe: ERiC-Zertifikats-/Security-Codes."""


class VerbindungsFehler(ElsterFehler):
    """Transport zum ELSTER-Server: offline/DNS/TLS/Timeout, von ERiC sauber
    als „nichts übertragen" gemeldet ⇒ als EINZIGE Klasse automatisch
    wiederholbar (Backoff). Offline heißt harter Abbruch des Laufs (I-4),
    nie ein leeres Erfolgs-Ergebnis. Regel-Gruppe: ERiC-Transport-Codes."""
    retry_erlaubt = True


class SendeUnklarFehler(ElsterFehler):
    """Der Sende-Ausgang ist UNBEKANNT (Abbruch/Crash/Timeout nach Sendebeginn,
    keine saubere ERiC-Antwort). NIE wiederholen — erst manuelle Klärung
    (Quittungs-/Transferticket-Prüfung), sonst droht Doppel-Übermittlung.
    Blockiert den Fall-Schlüssel (I-6)."""


class UebermittlungAbgelehnt(ElsterFehler):
    """Der ELSTER-Server hat die Einreichung fachlich abgewiesen (Antwort liegt
    vor, nichts wurde angenommen). Korrigieren + neuer Lauf; kein Auto-Retry.
    Regel-Gruppe: Server-Rückweisungs-Codes."""


class FestschreibFehler(ElsterFehler):
    """NACH erhaltener Quittung scheiterte die lokale Festschreibung (M-7).
    Die Übermittlung IST passiert — der Lauf endet UEBERMITTELT_OFFEN,
    Nacharbeit ist lokal; das Senden wird NIEMALS wiederholt."""


class ZustandsFehler(ElsterFehler):
    """Illegaler Übergang in der Filing-Zustandsmaschine (Programmierfehler des
    Motors — fail-closed sichtbar machen statt still weiterlaufen)."""


# ---------------------------------------------------------- Zustandsmaschine

class FilingZustand(str, enum.Enum):
    BEREIT = "bereit"                        # Ruhezustand, kein Lauf
    BAUT_DATENSATZ = "baut_datensatz"        # Quelldaten → ELSTER-XML (Bauer)
    VALIDIERT = "validiert"                  # ERiC validate-only läuft (lokal)
    VALIDIERT_OK = "validiert_ok"            # Validate grün — einziges Sende-Tor
    SENDET = "sendet"                        # Übermittlung läuft (Point of no return)
    QUITTUNG_ERHALTEN = "quittung_erhalten"  # Server-Quittung/Transferticket da
    FESTGESCHRIEBEN = "festgeschrieben"      # terminal: Erfolg + M-7-Einfrierung
    FEHLGESCHLAGEN = "fehlgeschlagen"        # terminal: sauber gescheitert, NICHTS raus
    ABGEBROCHEN = "abgebrochen"              # terminal: Nutzer-Abbruch VOR Sendebeginn
    SENDUNG_UNKLAR = "sendung_unklar"        # terminal: Ausgang unbekannt ⇒ manuell klären
    UEBERMITTELT_OFFEN = "uebermittelt_offen"  # terminal: Quittung da, Festschreibung offen


TERMINAL: frozenset[FilingZustand] = frozenset({
    FilingZustand.FESTGESCHRIEBEN, FilingZustand.FEHLGESCHLAGEN,
    FilingZustand.ABGEBROCHEN, FilingZustand.SENDUNG_UNKLAR,
    FilingZustand.UEBERMITTELT_OFFEN})

#: Vollständige Übergangs-Relation. Regeln (docs/65 §4): Terminale absorbierend ·
#: SENDET NUR aus VALIDIERT_OK (I-5) · ABGEBROCHEN nur VOR Sendebeginn (ab
#: SENDET gibt es kein Nutzer-Abbrechen mehr — der Ausgang wäre unklar) ·
#: QUITTUNG_ERHALTEN kennt kein FEHLGESCHLAGEN (die Übermittlung IST passiert;
#: sein Fehlerpfad ist UEBERMITTELT_OFFEN) · SENDET → FEHLGESCHLAGEN nur, wenn
#: ERiC sauber „nichts übertragen" gemeldet hat, sonst SENDUNG_UNKLAR.
UEBERGAENGE: dict[FilingZustand, frozenset[FilingZustand]] = {
    FilingZustand.BEREIT: frozenset({FilingZustand.BAUT_DATENSATZ}),
    FilingZustand.BAUT_DATENSATZ: frozenset({
        FilingZustand.VALIDIERT, FilingZustand.FEHLGESCHLAGEN, FilingZustand.ABGEBROCHEN}),
    FilingZustand.VALIDIERT: frozenset({
        FilingZustand.VALIDIERT_OK, FilingZustand.FEHLGESCHLAGEN, FilingZustand.ABGEBROCHEN}),
    FilingZustand.VALIDIERT_OK: frozenset({
        FilingZustand.SENDET, FilingZustand.FEHLGESCHLAGEN, FilingZustand.ABGEBROCHEN}),
    FilingZustand.SENDET: frozenset({
        FilingZustand.QUITTUNG_ERHALTEN, FilingZustand.FEHLGESCHLAGEN,
        FilingZustand.SENDUNG_UNKLAR}),
    FilingZustand.QUITTUNG_ERHALTEN: frozenset({
        FilingZustand.FESTGESCHRIEBEN, FilingZustand.UEBERMITTELT_OFFEN}),
    FilingZustand.FESTGESCHRIEBEN: frozenset(),
    FilingZustand.FEHLGESCHLAGEN: frozenset(),
    FilingZustand.ABGEBROCHEN: frozenset(),
    FilingZustand.SENDUNG_UNKLAR: frozenset(),
    FilingZustand.UEBERMITTELT_OFFEN: frozenset(),
}

#: Läufe/Zustände, die einen Fall-Schlüssel für JEDEN neuen Lauf blockieren
#: (I-6): erledigt (nur Korrektur darf drüber), eine erhaltene Quittung (die
#: Erklärung ist bereits ANGENOMMEN — ein neuer Lauf = Doppel-Übermittlung),
#: unklar (erst klären!) oder eine SENDET-Leiche (Crash mitten im Senden = unklar).
BLOCKIERENDE_ZUSTAENDE: frozenset[FilingZustand] = frozenset({
    FilingZustand.FESTGESCHRIEBEN, FilingZustand.QUITTUNG_ERHALTEN,
    FilingZustand.SENDET,
    FilingZustand.SENDUNG_UNKLAR, FilingZustand.UEBERMITTELT_OFFEN})

#: Teilmenge, über die auch eine KORREKTUR nicht hinweg darf: erst manuelle
#: Klärung/Nacharbeit, dann weiter (Korrektur setzt Gewissheit voraus). Eine
#: erhaltene Quittung gehört dazu — erst festschreiben, dann korrigieren.
KORREKTUR_BLOCKIERT: frozenset[FilingZustand] = frozenset({
    FilingZustand.SENDET, FilingZustand.QUITTUNG_ERHALTEN,
    FilingZustand.SENDUNG_UNKLAR,
    FilingZustand.UEBERMITTELT_OFFEN})


def ist_terminal(zustand: FilingZustand) -> bool:
    return zustand in TERMINAL


def pruefe_uebergang(von: FilingZustand, nach: FilingZustand) -> None:
    """Wirft ``ZustandsFehler`` bei illegalem Übergang — der Motor darf die
    Relation nie „interpretieren", nur befolgen."""
    if nach not in UEBERGAENGE[von]:
        raise ZustandsFehler(f"Illegaler Filing-Übergang {von.value!r} → {nach.value!r}")


# ------------------------------------------------------------------ Datentypen

class FormularArt(str, enum.Enum):
    """Erste Ausbaustufen des Filing (docs/65 §6; Reihenfolge = G-M1-FORMULARE):
    Anlage EÜR zuerst (Datenlage ``auswertung.eur_jahr`` existiert heute),
    UStVA als zweite Form (braucht erst die M-4-Datenschicht). ESt/KAP/SO
    folgen als spätere Vertragserweiterung — bewusst NICHT vorab modelliert."""
    EUER = "euer"        # Anlage EÜR (Jahresformular)
    USTVA = "ustva"      # Umsatzsteuer-Voranmeldung (Monats-/Quartalsformular)


class ZertifikatTyp(str, enum.Enum):
    """ELSTER-Zertifikatstyp — WELCHER für David richtig ist, ist Gate
    G-M1-ZERTIFIKAT (persönlich deckt Einzelunternehmer-EÜR; Organisation
    wäre der Firmen-Weg). Beide tragen denselben Transport-Vertrag."""
    PERSOENLICH = "persoenlich"
    ORGANISATION = "organisation"


def _maskiert(wert: str) -> str:
    return (wert[:2] + "…") if len(wert) > 2 else "…"


@dataclass(frozen=True)
class ElsterZugang:
    """Konfiguration des ELSTER-Zugangs — trägt NIE ein Geheimnis (I-2).

    ``zertifikat_pfad`` ist eine Datei-REFERENZ auf das ELSTER-Software-
    Zertifikat (.pfx, selbst PIN-verschlüsselt) unter der Daten-Wurzel
    (``data\\apps\\money\\elster\\…`` — nie im Repo). ``pin_vault_key`` ist nur
    der Schlüssel-NAME im appkit-Vault (Konvention ``elster_pin_<zugang_id>``);
    die PIN existiert ausschließlich im Vault und zur Laufzeit im ERiC-Worker.
    Die Feld-Fläche ist eingefroren (Vertrags-Test) — Erweiterung = bewusste
    Vertragsänderung in docs/65, nie ein Nebeneffekt."""

    zugang_id: str
    zertifikat_pfad: str        # Datei-REF (.pfx), nie Inhalt (I-2)
    pin_vault_key: str          # Vault-Schlüssel-NAME, nie die PIN (I-2)
    zertifikat_typ: ZertifikatTyp
    steuernummer: str = ""      # sensibel — repr maskiert

    def __post_init__(self) -> None:
        if not self.zugang_id.strip():
            raise KonfigFehler("ElsterZugang: zugang_id fehlt")
        if not self.zertifikat_pfad.strip():
            raise KonfigFehler("ElsterZugang: zertifikat_pfad fehlt "
                               "(Datei-Referenz aufs .pfx, nie der Inhalt)")
        if not self.pin_vault_key.strip():
            raise KonfigFehler("ElsterZugang: pin_vault_key fehlt "
                               "(PIN gehört in den Vault, I-2)")
        if isinstance(self.zertifikat_typ, str) and not isinstance(self.zertifikat_typ, ZertifikatTyp):
            try:
                object.__setattr__(self, "zertifikat_typ", ZertifikatTyp(self.zertifikat_typ))
            except ValueError:
                raise KonfigFehler(f"ElsterZugang: unbekannter Zertifikatstyp {self.zertifikat_typ!r}")

    def __repr__(self) -> str:  # I-2: Steuernummer nie voll in Logs/Tracebacks
        return (f"ElsterZugang(zugang_id={self.zugang_id!r}, "
                f"typ={self.zertifikat_typ.value!r}, "
                f"steuernummer={_maskiert(self.steuernummer)!r})")


@dataclass(frozen=True)
class Scharfschaltung:
    """Zwei-Schlüssel-Prinzip (I-3, T5-/M-6-Muster): Schlüssel 1 = Zugang
    angelegt (Zertifikat referenziert, PIN im Vault), Schlüssel 2 = expliziter,
    getrennter Bestätigungs-Akt (docs/65 §8). Beide Zeitstempel (ISO) müssen
    gesetzt sein — erst dann darf der Transport überhaupt senden wollen.
    (Bewusst dupliziert statt aus banksync importiert: zweite Instanz des
    Musters; Hebe nach appkit erst bei der dritten — docs/65 §11.)"""

    zugang_id: str
    angelegt_am: str = ""       # Schlüssel 1 (ISO-Datum/-Zeit)
    bestaetigt_am: str = ""     # Schlüssel 2 (ISO-Datum/-Zeit)

    @property
    def ist_scharf(self) -> bool:
        return bool(self.angelegt_am.strip() and self.bestaetigt_am.strip())


def pruefe_scharf(schaltung: Scharfschaltung | None) -> None:
    """Fail-closed-Wächter: fehlt die Schaltung oder ein Schlüssel ⇒ NichtScharf."""
    if schaltung is None or not schaltung.ist_scharf:
        raise NichtScharf("ELSTER-Transport ist nicht scharfgeschaltet "
                          "(Zwei-Schlüssel-Prinzip, docs/65 §8)")


def pruefe_hersteller_id(hersteller_id: str | None) -> None:
    """I-3-Wächter: ohne in den Settings hinterlegte ERiC-Hersteller-ID
    (BayLfSt-Registrierung, Gate G-M1-ERIC) sendet der Transport nichts.
    Die Kennung wird NIE hartkodiert und NIE geraten."""
    if not (hersteller_id or "").strip():
        raise NichtScharf("Keine ERiC-Hersteller-ID konfiguriert "
                          "(Registrierung = Gate G-M1-ERIC, docs/65 §14)")


@dataclass(frozen=True)
class SteuerFall:
    """WAS eingereicht wird: Formular + Besteuerungszeitraum + Korrektur-Zähler.

    ``zeitraum`` ist bei Jahresformularen (EÜR) leer — das Jahr genügt; die
    UStVA verlangt den Voranmeldungszeitraum (``"YYYY-MM"`` bzw. ``"YYYY-Qn"``).
    ``korrektur_nr`` 0 = Erst-Einreichung; >0 = bewusste Berichtigung (I-6:
    eigener Akt, nie ein Retry). Der Idempotenz-Anker ``fall_schluessel``
    enthält die Korrektur-Nr. bewusst NICHT — Korrekturen laufen auf demselben
    Schlüssel und werden über ``pruefe_doppel`` reguliert."""

    formular: FormularArt
    jahr: int
    zeitraum: str = ""
    korrektur_nr: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.formular, str) and not isinstance(self.formular, FormularArt):
            try:
                object.__setattr__(self, "formular", FormularArt(self.formular))
            except ValueError:
                raise KonfigFehler(f"SteuerFall: unbekanntes Formular {self.formular!r}")
        if not (JAHR_MIN <= int(self.jahr) <= JAHR_MAX):
            raise KonfigFehler(f"SteuerFall: unplausibles Jahr {self.jahr!r}")
        if self.formular is FormularArt.USTVA and not self.zeitraum.strip():
            raise KonfigFehler("SteuerFall: UStVA verlangt einen Voranmeldungszeitraum")
        if self.formular is FormularArt.EUER and self.zeitraum.strip():
            raise KonfigFehler("SteuerFall: EÜR ist ein Jahresformular — zeitraum muss leer sein")
        if self.korrektur_nr < 0:
            raise KonfigFehler("SteuerFall: korrektur_nr darf nicht negativ sein")

    @property
    def ist_korrektur(self) -> bool:
        return self.korrektur_nr > 0


def fall_schluessel(fall: SteuerFall) -> str:
    """DER Idempotenz-Anker (I-6): identifiziert den Besteuerungs-Fall über
    Läufe hinweg — bewusst OHNE korrektur_nr (s. ``SteuerFall``)."""
    return f"{fall.formular.value}|{fall.jahr}|{fall.zeitraum}"


def berechne_quell_stand(daten: str | bytes) -> str:
    """Deterministischer Hash des Quell-Datenstands (sha256-hex). Bindet die
    M-2-``PlausiFreigabe`` an GENAU den geprüften Datenstand (I-1) und den
    ``ElsterDatensatz`` an seine Quelle — ändert sich ein Cent, passt nichts
    mehr zusammen (stale ⇒ GateRot). Der Aufrufer liefert die kanonische
    Serialisierung der Quelldaten (Bau: M1-4/M-2)."""
    if isinstance(daten, str):
        daten = daten.encode("utf-8")
    return hashlib.sha256(daten).hexdigest()


@dataclass(frozen=True)
class ElsterDatensatz:
    """Der gebaute, versandfertige ELSTER-Datensatz (Nutzdaten-XML) — Träger
    zwischen Bauer, Validate und Senden. ``formular_version`` ist PFLICHT und
    explizit: die jährliche Formular-/Versions-Pflege ist DER Betriebs-
    Kostenfaktor (docs/58 §3.G3); eine veraltete Version fällt im
    ERiC-Validate laut, nie still. ``repr`` zeigt NIE das XML — der Datensatz
    IST die Steuererklärung (I-2)."""

    fall: SteuerFall
    xml: str                    # Nutzdaten-XML (Steuerdaten! nie loggen)
    quell_stand_hash: str       # Anker an die Quelldaten (I-1)
    formular_version: str       # z. B. Jahres-/Schema-Tag; Pflege = M1-4/M1-7

    def __post_init__(self) -> None:
        if not self.xml.strip():
            raise KonfigFehler("ElsterDatensatz: xml fehlt")
        if not self.quell_stand_hash.strip():
            raise KonfigFehler("ElsterDatensatz: quell_stand_hash fehlt (I-1-Anker)")
        if not self.formular_version.strip():
            raise KonfigFehler("ElsterDatensatz: formular_version fehlt "
                               "(jährliche Versions-Pflege ist explizit, docs/65 §6)")

    def __repr__(self) -> str:  # I-2: Steuer-XML nie in Logs/Tracebacks
        return (f"ElsterDatensatz(fall={fall_schluessel(self.fall)!r}, "
                f"version={self.formular_version!r}, xml_laenge={len(self.xml)})")


@dataclass(frozen=True)
class PlausiFreigabe:
    """Das Ergebnis-Token der M-2-Plausibilisierungs-Engine (Bau-KI-Bau) — der
    EINZIGE Schlüssel, der das Sende-Gate öffnet (I-1). Hash-gebunden an den
    geprüften Quell-Datenstand: eine Freigabe „altert" nicht über die Zeit,
    sondern über Datenänderung. Stufe 0 hat keinen Produzenten — der Vertrag
    fixiert nur die Schnittstelle; die Engine wird ihr einziger Hersteller."""

    fall_schluessel: str
    quell_stand_hash: str
    gruen: bool
    geprueft_am: str            # ISO — informativ (Anzeige), NICHT das Frische-Kriterium
    befund: str = ""            # menschenlesbare Zusammenfassung der Prüfung


def pruefe_gate(freigabe: PlausiFreigabe | None, datensatz: ElsterDatensatz) -> None:
    """DAS Fail-closed-Gate (I-1): wirft ``GateRot``, wenn die M-2-Freigabe
    fehlt, rot ist, zu einem anderen Fall gehört oder stale ist (Datensatz-
    Quellstand ≠ geprüfter Stand). Nur eine grüne, exakt passende Freigabe
    lässt den Übergang zum Senden zu."""
    if freigabe is None:
        raise GateRot("Keine Plausibilisierungs-Freigabe vorhanden — ohne grünes "
                      "M-2-Gate wird nicht gesendet (docs/65 §3)")
    if not freigabe.gruen:
        raise GateRot(f"Plausibilisierung ist ROT: {freigabe.befund or 'ohne Befundtext'}")
    if freigabe.fall_schluessel != fall_schluessel(datensatz.fall):
        raise GateRot("Freigabe gehört zu einem anderen Steuerfall")
    if freigabe.quell_stand_hash != datensatz.quell_stand_hash:
        raise GateRot("Freigabe ist STALE: Quelldaten haben sich seit der "
                      "Plausibilisierung geändert — erneut prüfen (I-1)")


@dataclass(frozen=True)
class ValidierungsErgebnis:
    """Ergebnis des ERiC-validate-only-Laufs (lokal, risikofrei, ohne
    Scharfschaltung nutzbar — I-5). Konstruktiv ehrlich: grün verträgt keine
    Fehlerliste, rot verlangt mindestens einen Fehler (nie stilles Rot).
    ``hinweise`` sind nicht-blockierende ERiC-Hinweise."""

    ok: bool
    fehler: tuple[str, ...] = ()
    hinweise: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.ok and self.fehler:
            raise ValueError("ValidierungsErgebnis: ok=True widerspricht Fehlerliste")
        if not self.ok and not self.fehler:
            raise ValueError("ValidierungsErgebnis: rot ohne Fehlertext ist verboten "
                             "(nie stilles Rot)")


@dataclass(frozen=True)
class Quittung:
    """Die Server-Quittung einer angenommenen Übermittlung. ``transferticket``
    ist der amtliche Nachweis-Anker (Pflicht); ``protokoll_roh`` ist das
    unangetastete Übertragungsprotokoll (GoBD-Archiv, M1-5). ``repr`` zeigt
    das Roh-Protokoll nie (enthält Steuerdaten)."""

    transferticket: str
    uebermittelt_am: str        # ISO
    protokoll_roh: bytes = b""

    def __post_init__(self) -> None:
        if not self.transferticket.strip():
            raise KonfigFehler("Quittung: transferticket fehlt — ohne Ticket "
                               "gibt es keine Quittung (I-4)")

    def __repr__(self) -> str:
        return (f"Quittung(transferticket={self.transferticket!r}, "
                f"uebermittelt_am={self.uebermittelt_am!r}, "
                f"protokoll_bytes={len(self.protokoll_roh)})")


@dataclass(frozen=True)
class FilingErgebnis:
    """Endzustand eines Filing-Laufs. Invarianten (I-4) werden bei Konstruktion
    erzwungen — ein Motor KANN keinen stillen Erfolg und keinen unehrlichen
    Fehlschlag bauen:
    * ``zustand`` muss terminal sein,
    * FESTGESCHRIEBEN ⇔ Transferticket vorhanden, ohne Fehlertext,
    * UEBERMITTELT_OFFEN verlangt Transferticket UND ehrlichen Fehlertext
      (übermittelt ja — Festschreibung offen),
    * SENDUNG_UNKLAR verlangt einen Fehlertext (was ist zu klären?),
    * FEHLGESCHLAGEN verlangt Fehlertext und verträgt KEIN Transferticket
      (läge eines vor, war es kein sauberer Fehlschlag),
    * ABGEBROCHEN verträgt kein Transferticket (Abbruch gibt es nur VOR Sendung).
    Fehlertexte tragen nie Geheimnisse (I-2)."""

    fall_schluessel: str
    zustand: FilingZustand
    transferticket: str = ""
    fehler: str = ""
    fehler_art: str = ""        # Klassenname des ElsterFehler (Maschine)

    def __post_init__(self) -> None:
        if not ist_terminal(self.zustand):
            raise ValueError(f"FilingErgebnis nur mit Terminal-Zustand, nicht {self.zustand.value!r}")
        z = FilingZustand
        if self.zustand is z.FESTGESCHRIEBEN:
            if not self.transferticket.strip():
                raise ValueError("FilingErgebnis: FESTGESCHRIEBEN ohne Transferticket "
                                 "ist verboten (I-4 — Erfolg ⇔ Quittung)")
            if self.fehler:
                raise ValueError("FilingErgebnis: FESTGESCHRIEBEN widerspricht Fehlertext")
        if self.zustand is z.UEBERMITTELT_OFFEN and (
                not self.transferticket.strip() or not self.fehler.strip()):
            raise ValueError("FilingErgebnis: UEBERMITTELT_OFFEN verlangt Transferticket "
                             "UND ehrlichen Fehlertext (Festschreib-Nacharbeit)")
        if self.zustand is z.SENDUNG_UNKLAR and not self.fehler.strip():
            raise ValueError("FilingErgebnis: SENDUNG_UNKLAR braucht einen ehrlichen "
                             "Klärungs-Text")
        if self.zustand in (z.FEHLGESCHLAGEN, z.ABGEBROCHEN) and self.transferticket.strip():
            raise ValueError("FilingErgebnis: Transferticket widerspricht "
                             f"{self.zustand.value!r} — das wäre kein sauberer Abbruch")
        if self.zustand is z.FEHLGESCHLAGEN and not self.fehler.strip():
            raise ValueError("FilingErgebnis: FEHLGESCHLAGEN braucht einen ehrlichen Fehlertext")


# ---------------------------------------------------- Sende-Vorbedingungen

def pruefe_doppel(vorhandene: Iterable[tuple[str, FilingZustand]],
                  fall: SteuerFall) -> None:
    """Idempotenz-Wächter (I-6) über die persistierten Läufe eines Falls.

    ``vorhandene`` = (fall_schluessel, zustand)-Paare aus der Lauf-Historie
    (M1-1-Tabelle). Regeln: ein blockierender Zustand auf demselben Schlüssel
    verhindert jeden neuen Lauf; über FESTGESCHRIEBEN hinweg darf NUR eine
    ausgewiesene Korrektur (``ist_korrektur``); über SENDET-Leichen (Crash),
    SENDUNG_UNKLAR und UEBERMITTELT_OFFEN darf NIEMAND — erst manuell klären."""
    schluessel = fall_schluessel(fall)
    for s, zustand in vorhandene:
        if s != schluessel or zustand not in BLOCKIERENDE_ZUSTAENDE:
            continue
        if zustand in KORREKTUR_BLOCKIERT:
            raise DoppelFilingFehler(
                f"Fall {schluessel!r} hat einen ungeklärten Lauf ({zustand.value}) "
                "— erst manuell klären, dann weiter (I-6)")
        if not fall.ist_korrektur:   # zustand == FESTGESCHRIEBEN
            raise DoppelFilingFehler(
                f"Fall {schluessel!r} ist bereits festgeschrieben übermittelt — "
                "eine erneute Einreichung ist nur als bewusste Korrektur "
                "(korrektur_nr) erlaubt (I-6)")


def pruefe_sende_freigabe(*, hersteller_id: str | None,
                          schaltung: Scharfschaltung | None,
                          fall: SteuerFall,
                          datensatz: ElsterDatensatz,
                          validierung: ValidierungsErgebnis | None,
                          freigabe: PlausiFreigabe | None,
                          vorhandene: Iterable[tuple[str, FilingZustand]] = ()) -> None:
    """DAS Vorbedingungs-Bündel für den Übergang VALIDIERT_OK → SENDET — der
    einzige Weg zum Senden führt hier durch (I-1/I-3/I-5/I-6, docs/65 §4).
    Prüf-Reihenfolge = Fehler-Priorität: Betriebsvoraussetzungen (Hersteller-ID,
    Zwei-Schlüssel) → Idempotenz (Doppel-Schutz) → technische Gültigkeit
    (ERiC-Validate grün) → fachliches Gate (M-2-Freigabe, frisch).
    Jede Verletzung wirft ihre Klasse; nichts davon ist überstimmbar."""
    pruefe_hersteller_id(hersteller_id)
    pruefe_scharf(schaltung)
    pruefe_doppel(vorhandene, fall)
    if validierung is None or not validierung.ok:
        gruende = "; ".join(validierung.fehler) if validierung else "kein Validate-Lauf"
        raise ValidierungsFehler(
            f"ERiC-Validate ist nicht grün ({gruende}) — validate-only ist "
            "Pflicht VOR jedem Senden (I-5)")
    pruefe_gate(freigabe, datensatz)


# ------------------------------------------------------------ Adapter-Grenze

@runtime_checkable
class DatensatzBauer(Protocol):
    """DER Serialisierungs-Vertrag: baut aus Money-Quelldaten den versand-
    fertigen ``ElsterDatensatz`` (Nutzdaten-XML). Feld-Mappings der Formulare
    sind Bau-KI-Bau (M1-4 EÜR aus ``auswertung.eur_jahr``, M1-7 UStVA nach M-4);
    der Bauer trägt seine ``formular_version`` explizit (Versions-Pflege)."""
    formular: FormularArt
    formular_version: str

    def baue(self, fall: SteuerFall, quelldaten: dict) -> ElsterDatensatz: ...


class EuerBauer:
    """Stufe 0: Anlage-EÜR-Bauer — bewusst nicht implementiert.

    Quelle des Bau-Schritts M1-4: ``auswertung.eur_jahr`` (je-Kategorie-
    Überschuss, steuer_relevant/steuer_art) → Kennziffern-Mapping der Anlage
    EÜR der jeweiligen ``formular_version``. Mapping raten = Scheingenauigkeit;
    deshalb hier NICHTS außer dem Vertrag."""

    formular = FormularArt.EUER
    formular_version = ""       # M1-4 setzt die reale Jahres-Version

    def baue(self, fall: SteuerFall, quelldaten: dict) -> ElsterDatensatz:
        raise NotImplementedError(
            "Stufe 0: EÜR-Feld-Mapping ist bewusst nicht implementiert — Bau = "
            "Bau-KI M1-4 nach docs/65 §12 (NACH den Vorstufen M-2/M-3/M-7, VO-5).")


class UstvaBauer:
    """Stufe 0: UStVA-Bauer — bewusst nicht implementiert (zweite Form;
    braucht zuerst die M-4-USt-Datenschicht + Gate G-M1-FORMULARE)."""

    formular = FormularArt.USTVA
    formular_version = ""       # M1-7 setzt die reale Version

    def baue(self, fall: SteuerFall, quelldaten: dict) -> ElsterDatensatz:
        raise NotImplementedError(
            "Stufe 0: UStVA ist bewusst nicht implementiert — Bau = Bau-KI M1-7 "
            "nach docs/65 §12 (nach M-4-Datenschicht + G-M1-FORMULARE).")


class EricTransport:
    """ERiC-Transport — Stufe 0 = WÄCHTER OHNE LIB.

    Kapselt die native ERiC-C-Bibliothek vollständig (I-8: im Bau läuft sie in
    einem eigenen Worker-SUBPROZESS — ein nativer Crash darf :8210 nie töten;
    PIN via stdin-Pipe, nie argv/env). Die ctypes-Bindung an die ECHTEN
    ``ericapi``-Symbole, das Envelope-Handling und die Code-Tabelle baut Bau-KI
    in M1-3 (docs/65 §12) — erst nach den Gates G-M1-ERIC/G-M1-LIZENZ.

    Schon heute gilt: ``validiere`` ist frei (validate-only ist lokal und
    risikofrei — bewusst OHNE Scharf-Anspruch, damit niemand die Validierung
    meidet); ``sende`` läuft IMMER zuerst durch ``pruefe_sende_freigabe``
    (Wächter VOR NotImplementedError — der Sicherheitspfad existiert vor der
    Funktion). ``pin_holen`` ist die Vault-Naht: bekommt den Schlüssel-NAMEN,
    liefert die PIN NUR in den Worker (Default None ⇒ Stufe 0 hat keinerlei
    Geheimnis-Durchgriff)."""

    def __init__(self, zugang: ElsterZugang, schaltung: Scharfschaltung | None,
                 *, hersteller_id: str = "",
                 pin_holen: Callable[[str], str | None] | None = None) -> None:
        self._zugang = zugang
        self._schaltung = schaltung
        self._hersteller_id = hersteller_id
        self._pin_holen = pin_holen

    def validiere(self, datensatz: ElsterDatensatz) -> ValidierungsErgebnis:
        """ERiC validate-only (lokal, ohne Übermittlung) — Pflicht-Vorstufe
        jedes Sendens (I-5), aber selbst jederzeit erlaubt."""
        raise NotImplementedError(
            "Stufe 0: ERiC-Validate ist bewusst nicht implementiert — Bau = "
            "Bau-KI M1-3 nach docs/65 §12 (Gates G-M1-ERIC/G-M1-LIZENZ).")

    def sende(self, datensatz: ElsterDatensatz, fall: SteuerFall, *,
              validierung: ValidierungsErgebnis | None,
              freigabe: PlausiFreigabe | None,
              vorhandene: Iterable[tuple[str, FilingZustand]] = ()) -> Quittung:
        """Echte Übermittlung — Stufe 0 wirft IMMER zuerst die Wächter
        (NichtScharf/GateRot/… VOR NotImplementedError, I-1/I-3/I-5/I-6)."""
        pruefe_sende_freigabe(
            hersteller_id=self._hersteller_id, schaltung=self._schaltung,
            fall=fall, datensatz=datensatz, validierung=validierung,
            freigabe=freigabe, vorhandene=vorhandene)
        raise NotImplementedError(
            "Stufe 0: ERiC-Senden ist bewusst nicht implementiert — Bau = Bau-KI "
            "M1-5 nach docs/65 §12; Aktivierung bleibt gegated (M-2-grün + "
            "Hersteller-ID + Nutzer-Akt).")


#: Vertrags-Anker für Feld-Flächen-Tests (I-2): Erweiterung = bewusste
#: Vertragsänderung in docs/65, nie ein stilles Zusatzfeld.
ZUGANG_FELDER: frozenset[str] = frozenset(f.name for f in fields(ElsterZugang))
ERGEBNIS_FELDER: frozenset[str] = frozenset(f.name for f in fields(FilingErgebnis))
