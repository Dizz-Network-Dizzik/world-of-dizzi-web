"""Bank-Sync-VERTRAG (docs/64) — Verträge-als-Code, Stufe 0. NUR LESEND.

Normative Quelle für den FinTS/HBCI-Bank-Sync (M-6): Typen, Zustandsmaschine,
Fehler-Taxonomie und die Quelle→Import-Brücke. Stufe 0 ist wertgleich zum Ist:
die einzige lauffähige Quelle ist die ``DateiQuelle`` (lokal vorliegender
camt-/MT940-Auszug) — sie beweist den Adapter-Pfad ohne ein einziges Netz-Byte.
Die echte ``FinTSQuelle`` baut Bau-KI nach docs/64 §12; ihre Stubs hier tragen
bereits den Zwei-Schlüssel-Wächter (Sicherheitspfad existiert VOR der Funktion).

HÄRTUNGS-INVARIANTEN (docs/64 §1, hier als Code erzwungen):
  I-1  NUR LESEND: ``ERLAUBTE_SEGMENTE`` ist eine deny-by-default-Whitelist;
       Zahlungssegmente (HKCC*/HKCS*/HKCD*/HKDS*…) sind strukturell draußen.
  I-2  Geheimnisse NIE hier: ``BankZugang`` trägt nur den Vault-Schlüssel-NAMEN
       (``pin_vault_key``), nie PIN/TAN; ``repr()`` maskiert die Benutzerkennung.
  I-3  Zwei-Schlüssel: ohne ``Scharfschaltung`` (angelegt UND bestätigt) öffnet
       keine Quelle eine Verbindung (``pruefe_scharf`` ⇒ ``NichtScharf``).
  I-4  Fail-closed: jeder Fehler endet FEHLGESCHLAGEN; ABGESCHLOSSEN mit
       0 Buchungen gibt es nur mit ausdrücklicher Leer-Bestätigung der Bank;
       Teil-Abrufe erreichen die Pipeline nie (``TeilAbrufFehler``).
  I-5  Kein Parallel-Parser: Auszüge gehen als camt/MT940 in die BESTEHENDE
       importers-Pipeline (``parse_inhalt`` + ``bewegung_hash``-Dedupe);
       Format-Kürzel sind dispatch-identisch.
  I-8  Retry-Politik als Code: ``retry_erlaubt`` je Fehlerklasse; Default der
       Basis ist False (unbekannt ⇒ kein Auto-Retry) — nur Verbindungs-/
       Teil-Abruf-Fehler dürfen automatisch wiederholt werden (Backoff).
       AuthFehler NIE automatisch wiederholen (Gefahr der PIN-Sperre).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, fields
from datetime import date, timedelta
from typing import Callable, Protocol, runtime_checkable

from ..importers.dispatch import erkenne_format

# ------------------------------------------------------------------ Konstanten

#: Abruf-Fenster überlappt den letzten Erfolg — die Pipeline-Dedupe
#: (bewegung_hash + UNIQUE(import_hash)) macht den Doppel-Anteil idempotent.
UEBERLAPP_TAGE = 3

#: Erstabruf-Fenster ohne Sync-Stand: bewusst < 90 Tage, damit der Abruf nach
#: PSD2-SCA-Ausnahme i. d. R. TAN-frei bleibt; volle Historie = bewusste
#: TAN-Aktion des Nutzers (docs/64 §2).
STANDARD_FENSTER_TAGE = 60

#: Jenseits dieses Fensters verlangen Banken für Umsatz-Historie regelmäßig
#: eine TAN — reine UI-/Motor-Heuristik, das Fenster wird NIE gekappt
#: (lieber TAN-Rückfrage als stille Datenlücke, I-4).
TAN_FREI_MAX_TAGE = 89

#: I-1 — deny-by-default: NUR diese FinTS-Segmente darf der Adapter je senden.
#: Dialog-Rahmen + SCA-Mechanik + Lese-Aufträge. Alles andere ist verboten,
#: insbesondere jede Zahlungs-Familie (s. VERBOTENE_SEGMENT_PRAEFIXE).
ERLAUBTE_SEGMENTE: frozenset[str] = frozenset({
    "HKIDN", "HKVVB", "HKSYN", "HKEND",   # Dialog-Init/-Sync/-Ende
    "HKTAN", "HKTAB",                     # SCA/TAN-Mechanik (PSD2)
    "HKSAL",                              # Salden
    "HKKAZ",                              # Umsätze (MT940)
    "HKCAZ",                              # Umsätze (camt)
    "HKSPA",                              # SEPA-Kontoverbindungen
})

#: Negativ-Doku + Test-Doppelboden: Familien mit Zahlungs-/Auftragswirkung.
#: (HKCC* Überweisung · HKCS* Terminüberweisung · HKCD* Dauerauftrag ·
#:  HKDS*/HKDM* Lastschrift · HKIP* Instant Payment · HKPPD Prepaid-Laden)
VERBOTENE_SEGMENT_PRAEFIXE: tuple[str, ...] = (
    "HKCC", "HKCS", "HKCD", "HKDS", "HKDM", "HKIP", "HKPPD")


def segment_erlaubt(code: str) -> bool:
    """Deny-by-default: True NUR für Whitelist-Segmente (I-1)."""
    return (code or "").strip().upper() in ERLAUBTE_SEGMENTE


# ------------------------------------------------------------ Fehler-Taxonomie

class BankSyncFehler(Exception):
    """Basis aller Sync-Fehler. Vertrag: fail-closed — der Lauf endet als
    FEHLGESCHLAGEN, nie als stilles „0 Umsätze". ``retry_erlaubt`` ist die
    maschinenlesbare Retry-Politik; der Basis-Default ist bewusst False
    (unbekannte Fehler wiederholt kein Automat — ein Mensch schaut drauf)."""
    retry_erlaubt = False


class KonfigFehler(BankSyncFehler):
    """Zugang/Aufruf strukturell ungültig (URL, BLZ, IBAN, Format-Kürzel)."""


class NichtScharf(BankSyncFehler):
    """Zwei-Schlüssel-Wächter (I-3): Zugang ist nicht scharfgeschaltet."""


class VerbindungsFehler(BankSyncFehler):
    """Transport: offline/DNS/TLS/Timeout — automatischer Retry mit Backoff ok."""
    retry_erlaubt = True


class AuthFehler(BankSyncFehler):
    """PIN/Anmeldung abgewiesen. NIE automatisch wiederholen — wenige
    Fehlversuche sperren den Bank-Zugang (retry_erlaubt bleibt False)."""


class TanFehler(BankSyncFehler):
    """TAN abgelehnt/abgelaufen/Timeout — eine neue TAN ist eine NUTZER-Aktion,
    kein Automat wiederholt sie."""


class TeilAbrufFehler(BankSyncFehler):
    """Aufsetzpunkt-Kette gerissen / Auszug unvollständig: das GESAMTE Ergebnis
    wird verworfen (I-4); ein späterer kompletter Lauf ist dank Dedupe billig."""
    retry_erlaubt = True


class FormatFehler(BankSyncFehler):
    """Bank/Quelle lieferte Unlesbares (kein camt/MT940)."""


class ZustandsFehler(BankSyncFehler):
    """Illegaler Übergang in der Sync-Zustandsmaschine (Programmierfehler des
    Motors — fail-closed sichtbar machen statt still weiterlaufen)."""


# ---------------------------------------------------------- Zustandsmaschine

class SyncZustand(str, enum.Enum):
    BEREIT = "bereit"                      # Ruhezustand, kein Lauf
    VERBINDET = "verbindet"                # TLS/Dialog-Init (HKIDN/HKVVB)
    AUTHENTIFIZIERT = "authentifiziert"    # PIN akzeptiert, BPD/UPD da
    TAN_ERFORDERLICH = "tan_erforderlich"  # SCA: wartet auf Nutzer/Bank-App
    RUFT_AB = "ruft_ab"                    # HKKAZ/HKCAZ, Aufsetzpunkt-Schleife
    UEBERGIBT_IMPORT = "uebergibt_import"  # Auszüge → importers-Pipeline
    ABGESCHLOSSEN = "abgeschlossen"        # terminal, nur mit komplettem Abruf
    FEHLGESCHLAGEN = "fehlgeschlagen"      # terminal, fail-closed
    ABGEBROCHEN = "abgebrochen"            # terminal, Nutzer-Abbruch


TERMINAL: frozenset[SyncZustand] = frozenset({
    SyncZustand.ABGESCHLOSSEN, SyncZustand.FEHLGESCHLAGEN, SyncZustand.ABGEBROCHEN})

#: Vollständige Übergangs-Relation. Regeln (docs/64 §4): Terminale sind
#: absorbierend · ABGESCHLOSSEN ist NUR über UEBERGIBT_IMPORT erreichbar ·
#: jeder Lauf-Zustand kann direkt FEHLGESCHLAGEN (fail-closed) · RUFT_AB hat
#: eine Selbstschleife (Aufsetzpunkt-Pagination) und darf mitten im Abruf
#: erneut eine TAN verlangen (Banken tun das bei großen Zeiträumen).
UEBERGAENGE: dict[SyncZustand, frozenset[SyncZustand]] = {
    SyncZustand.BEREIT: frozenset({SyncZustand.VERBINDET}),
    SyncZustand.VERBINDET: frozenset({
        SyncZustand.AUTHENTIFIZIERT, SyncZustand.FEHLGESCHLAGEN, SyncZustand.ABGEBROCHEN}),
    SyncZustand.AUTHENTIFIZIERT: frozenset({
        SyncZustand.TAN_ERFORDERLICH, SyncZustand.RUFT_AB,
        SyncZustand.FEHLGESCHLAGEN, SyncZustand.ABGEBROCHEN}),
    SyncZustand.TAN_ERFORDERLICH: frozenset({
        SyncZustand.RUFT_AB, SyncZustand.FEHLGESCHLAGEN, SyncZustand.ABGEBROCHEN}),
    SyncZustand.RUFT_AB: frozenset({
        SyncZustand.RUFT_AB, SyncZustand.TAN_ERFORDERLICH,
        SyncZustand.UEBERGIBT_IMPORT, SyncZustand.FEHLGESCHLAGEN, SyncZustand.ABGEBROCHEN}),
    SyncZustand.UEBERGIBT_IMPORT: frozenset({
        SyncZustand.ABGESCHLOSSEN, SyncZustand.FEHLGESCHLAGEN}),
    SyncZustand.ABGESCHLOSSEN: frozenset(),
    SyncZustand.FEHLGESCHLAGEN: frozenset(),
    SyncZustand.ABGEBROCHEN: frozenset(),
}


def ist_terminal(zustand: SyncZustand) -> bool:
    return zustand in TERMINAL


def pruefe_uebergang(von: SyncZustand, nach: SyncZustand) -> None:
    """Wirft ``ZustandsFehler`` bei illegalem Übergang — der Motor darf die
    Relation nie „interpretieren", nur befolgen."""
    if nach not in UEBERGAENGE[von]:
        raise ZustandsFehler(f"Illegaler Sync-Übergang {von.value!r} → {nach.value!r}")


# ------------------------------------------------------------------ Datentypen

class TanVerfahren(str, enum.Enum):
    """Die in DE relevanten SCA-Verfahren. Zwei UI-Grundformen (docs/64 §6):
    decoupled (PUSH_TAN: Freigabe in der Bank-App, Client pollt) und
    Challenge+Eingabe (CHIP_TAN_*/PHOTO_TAN: UI zeigt Challenge, Nutzer tippt).
    PUSH_TAN deckt App-Namen wie SecureGo plus (Atruvia: Sparda/VR) ab —
    Ziel-Verfahren des Pilot-Kontos Sparda-Bank Nürnberg (G-M6-TAN, docs/64 §14)."""
    PUSH_TAN = "push_tan"
    CHIP_TAN_MANUELL = "chip_tan_manuell"
    CHIP_TAN_QR = "chip_tan_qr"
    PHOTO_TAN = "photo_tan"
    SMS_TAN = "sms_tan"          # legacy, vielerorts abgekündigt


class AuszugsFormat(str, enum.Enum):
    """Werte sind ABSICHTLICH die dispatch-Kürzel (I-5): ein RohAuszug geht
    ohne Übersetzung in ``importers.dispatch.parse_inhalt(format=…)``."""
    CAMT_053 = "camt"
    MT940 = "mt940"


def _maskiert(wert: str) -> str:
    return (wert[:2] + "…") if len(wert) > 2 else "…"


@dataclass(frozen=True)
class BankZugang:
    """Konfiguration eines FinTS-Zugangs — trägt NIE ein Geheimnis (I-2).

    ``pin_vault_key`` ist nur der Schlüssel-NAME im appkit-Vault
    (``vault.Vault``, Konvention ``banksync_pin_<zugang_id>``); die PIN selbst
    existiert ausschließlich im Vault und zur Laufzeit im Dialog-Speicher.
    Die Feld-Fläche ist eingefroren (Vertrags-Test) — eine Erweiterung ist
    eine bewusste Vertragsänderung, nie ein Nebeneffekt."""

    zugang_id: str
    bank_name: str
    blz: str
    benutzerkennung: str        # FinTS-Anmeldename — sensibel, repr maskiert
    fints_url: str              # HTTPS-Endpunkt der Bank (I-6)
    tan_verfahren: TanVerfahren
    pin_vault_key: str          # Vault-Schlüssel-NAME, nie die PIN (I-2)
    konten_iban: tuple[str, ...] = ()   # leer = alle Konten des Zugangs

    def __post_init__(self) -> None:
        if not self.zugang_id.strip():
            raise KonfigFehler("BankZugang: zugang_id fehlt")
        if not re.fullmatch(r"\d{8}", self.blz or ""):
            raise KonfigFehler(f"BankZugang: BLZ muss 8 Ziffern sein: {self.blz!r}")
        if not self.fints_url.startswith("https://"):
            raise KonfigFehler("BankZugang: fints_url muss https:// sein (I-6)")
        if not self.pin_vault_key.strip():
            raise KonfigFehler("BankZugang: pin_vault_key fehlt (PIN gehört in den Vault)")
        if isinstance(self.tan_verfahren, str) and not isinstance(self.tan_verfahren, TanVerfahren):
            try:
                object.__setattr__(self, "tan_verfahren", TanVerfahren(self.tan_verfahren))
            except ValueError:
                raise KonfigFehler(f"BankZugang: unbekanntes TAN-Verfahren {self.tan_verfahren!r}")
        for iban in self.konten_iban:
            if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban or ""):
                raise KonfigFehler(f"BankZugang: keine gültige IBAN: {iban!r}")

    def __repr__(self) -> str:  # I-2: Kennung nie voll in Logs/Tracebacks
        return (f"BankZugang(zugang_id={self.zugang_id!r}, bank={self.bank_name!r}, "
                f"blz={self.blz!r}, benutzerkennung={_maskiert(self.benutzerkennung)!r}, "
                f"tan={self.tan_verfahren.value!r})")


@dataclass(frozen=True)
class Scharfschaltung:
    """Zwei-Schlüssel-Prinzip (I-3, T5-Analogie): Schlüssel 1 = Zugang angelegt
    (PIN im Vault), Schlüssel 2 = expliziter, getrennter Bestätigungs-Akt.
    Beide Zeitstempel (ISO) müssen gesetzt sein — erst dann darf irgendeine
    Quelle eine Verbindung öffnen. Details/Übergangs-Weg: docs/64 §8."""

    zugang_id: str
    angelegt_am: str = ""       # Schlüssel 1 (ISO-Datum/-Zeit)
    bestaetigt_am: str = ""     # Schlüssel 2 (ISO-Datum/-Zeit)

    @property
    def ist_scharf(self) -> bool:
        return bool(self.angelegt_am.strip() and self.bestaetigt_am.strip())


def pruefe_scharf(schaltung: Scharfschaltung | None) -> None:
    """Fail-closed-Wächter: fehlt die Schaltung oder ein Schlüssel ⇒ NichtScharf."""
    if schaltung is None or not schaltung.ist_scharf:
        raise NichtScharf("Bank-Zugang ist nicht scharfgeschaltet "
                          "(Zwei-Schlüssel-Prinzip, docs/64 §8)")


@dataclass(frozen=True)
class TanAnfrage:
    """SCA-Rückfrage der Bank an den Nutzer (Datenträger für die UI).
    ``decoupled=True`` ⇒ keine Eingabe, nur Freigabe in der Bank-App (Motor
    pollt den HKTAN-Status); sonst rendert die UI ``challenge``/``anweisung``
    und nimmt eine TAN entgegen. Eine TAN wird NIE persistiert (I-2)."""
    verfahren: TanVerfahren
    anweisung: str
    challenge: bytes = b""      # Grafik/Matrix (chipTAN/photoTAN), leer bei decoupled
    decoupled: bool = False


@dataclass(frozen=True)
class RohAuszug:
    """Ein von einer Quelle gelieferter Auszug — roh, unangetastet (I-5).
    ``vollstaendig=False`` (gerissene Aufsetzpunkt-Kette) erreicht die
    Pipeline nie: ``als_import_auftrag`` wirft ``TeilAbrufFehler``."""
    format: AuszugsFormat
    inhalt: str | bytes
    konto_iban: str = ""
    von: str = ""               # angefragtes Fenster (ISO), informativ
    bis: str = ""
    vollstaendig: bool = True
    quelle_id: str = ""         # "datei" | "fints" | "aggregator"


@dataclass(frozen=True)
class SyncErgebnis:
    """Endzustand eines Sync-Laufs. Invarianten (I-4) werden bei Konstruktion
    erzwungen — ein Motor KANN kein stilles Leer-Ergebnis bauen:
    * ``zustand`` muss terminal sein (Ergebnis gibt es nur am Ende),
    * ABGESCHLOSSEN verlangt Buchungen/Duplikate ODER ``leer_bestaetigt``
      (Bank hat den leeren Zeitraum aktiv bestätigt) und keinen Fehlertext,
    * FEHLGESCHLAGEN verlangt einen ehrlichen ``fehler``-Text (nie Geheimnisse).
    """
    zugang_id: str
    zustand: SyncZustand
    neue_buchungen: int = 0
    duplikate: int = 0
    leer_bestaetigt: bool = False
    abgerufen_von: str = ""
    abgerufen_bis: str = ""
    fehler: str = ""
    fehler_art: str = ""        # Klassenname des BankSyncFehler (Maschine)

    def __post_init__(self) -> None:
        if not ist_terminal(self.zustand):
            raise ValueError(f"SyncErgebnis nur mit Terminal-Zustand, nicht {self.zustand.value!r}")
        if self.zustand is SyncZustand.ABGESCHLOSSEN:
            if self.fehler:
                raise ValueError("SyncErgebnis: ABGESCHLOSSEN widerspricht Fehlertext")
            if (self.neue_buchungen + self.duplikate) == 0 and not self.leer_bestaetigt:
                raise ValueError("SyncErgebnis: stilles Leer-Ergebnis (0 Umsätze) ist "
                                 "verboten (I-4) — leer nur mit leer_bestaetigt=True")
        if self.zustand is SyncZustand.FEHLGESCHLAGEN and not self.fehler.strip():
            raise ValueError("SyncErgebnis: FEHLGESCHLAGEN braucht einen ehrlichen Fehlertext")


@dataclass(frozen=True)
class SyncStand:
    """Persistenter Fortschritt je Zugang (Idempotenz-Anker, docs/64 §7)."""
    zugang_id: str
    letzter_erfolg_bis: str = ""    # ISO; "" = noch nie erfolgreich
    fehler_serie: int = 0           # aufeinanderfolgende Fehl-Läufe (Backoff)


# ------------------------------------------------------------ Fenster-Politik

def abruf_fenster(stand: SyncStand | None, heute: str) -> tuple[str, str]:
    """Deterministisches Abruf-Fenster (kein ``now()`` im Vertrag — ``heute``
    reicht der Aufrufer). Erstlauf: die letzten STANDARD_FENSTER_TAGE (bewusst
    TAN-arm). Folgelauf: ab letztem Erfolg minus UEBERLAPP_TAGE. Das Fenster
    wird NIE gekappt — eine große Lücke bedeutet eine TAN-Rückfrage, nie eine
    stille Datenlücke (I-4)."""
    ende = date.fromisoformat(heute)
    if stand is None or not stand.letzter_erfolg_bis:
        start = ende - timedelta(days=STANDARD_FENSTER_TAGE)
    else:
        start = date.fromisoformat(stand.letzter_erfolg_bis) - timedelta(days=UEBERLAPP_TAGE)
        if start > ende:            # Uhr-Anomalie: fail-safe statt von>bis
            start = ende
    return start.isoformat(), ende.isoformat()


def tan_wahrscheinlich(von: str, heute: str) -> bool:
    """UI-/Motor-Heuristik: Historie älter als TAN_FREI_MAX_TAGE ⇒ Bank wird
    voraussichtlich eine TAN verlangen (PSD2-SCA). Reine Vorwarnung."""
    return (date.fromisoformat(heute) - date.fromisoformat(von)).days > TAN_FREI_MAX_TAGE


# ------------------------------------------------------- Quelle → importers

@runtime_checkable
class UmsatzQuelle(Protocol):
    """DER Quell-Vertrag: liefert Roh-Auszüge fürs Fenster — mehr nicht.
    Parsen/Dedupe/Verbuchen gehört der bestehenden importers-Pipeline (I-5).
    Implementierungen: DateiQuelle (Stufe 0) · FinTSQuelle (M6-3) ·
    AggregatorQuelle (M6-7, gegated G-M6-AGGREGATOR)."""
    quelle_id: str

    def hole_auszuege(self, von: str, bis: str) -> list[RohAuszug]: ...


def als_import_auftrag(auszug: RohAuszug, zielkonto_id: str) -> dict:
    """RohAuszug → Auftrag für die BESTEHENDE Import-Pipeline (die Felder des
    ``POST /api/import``-Wegs; der Motor ruft die interne Funktion, nie HTTP).
    Dedupe passiert in der Pipeline (``bewegung_hash`` + UNIQUE(import_hash))
    — hier wird nur die I-4-Schranke erzwungen: Teil-Abrufe kommen nie durch."""
    if not auszug.vollstaendig:
        raise TeilAbrufFehler("Unvollständiger Auszug (Aufsetzpunkt-Kette gerissen) "
                              "— wird verworfen, nicht teil-importiert (I-4)")
    if not zielkonto_id.strip():
        raise KonfigFehler("als_import_auftrag: zielkonto_id fehlt")
    return {
        "inhalt": auszug.inhalt,
        "format": auszug.format.value,          # dispatch-Kürzel (I-5)
        "zielkonto": zielkonto_id,
        "quelle": f"banksync:{auszug.quelle_id or 'unbekannt'}",
    }


# ------------------------------------------------------------------- Quellen

class DateiQuelle:
    """Stufe-0-Quelle: ein lokal vorliegender camt-/MT940-Auszug.

    Wertgleich zum heutigen manuellen Import — beweist den Quelle→Pipeline-Pfad
    ohne Netz. Format-Erkennung = ``importers.dispatch.erkenne_format`` (I-5,
    kein Parallel-Parser); CSV gehört NICHT hierher (der bestehende CSV-Import
    bleibt der Weg dafür) ⇒ ``FormatFehler``."""

    quelle_id = "datei"

    def __init__(self, inhalt: str | bytes, konto_iban: str = "") -> None:
        if isinstance(inhalt, bytes):           # Dekodierung wie dispatch
            try:
                inhalt = inhalt.decode("utf-8-sig")
            except UnicodeDecodeError:
                inhalt = inhalt.decode("latin-1")
        self._inhalt: str = inhalt
        self._konto_iban = konto_iban

    def hole_auszuege(self, von: str, bis: str) -> list[RohAuszug]:
        fmt = erkenne_format(self._inhalt)
        if fmt not in (AuszugsFormat.CAMT_053.value, AuszugsFormat.MT940.value):
            raise FormatFehler(f"DateiQuelle: kein Bank-Auszug (erkannt: {fmt!r}) — "
                               "CSV läuft über den bestehenden CSV-Import")
        return [RohAuszug(format=AuszugsFormat(fmt), inhalt=self._inhalt,
                          konto_iban=self._konto_iban, von=von, bis=bis,
                          vollstaendig=True, quelle_id=self.quelle_id)]


class FinTSQuelle:
    """FinTS/HBCI-Quelle — Stufe 0 = WÄCHTER OHNE WIRE.

    Der Zwei-Schlüssel-Wächter (I-3) läuft schon heute VOR jedem Wire-Gedanken;
    die eigentliche Dialog-Implementierung (python-fints hinter genau dieser
    Fassade, Segment-Whitelist, TAN-Fluss) baut Bau-KI in M6-3 (docs/64 §12) —
    erst nach den Gates G-M6-LIB + G-M6-BANK. ``pin_holen`` ist die Vault-Naht:
    bekommt den Schlüssel-NAMEN, liefert die PIN NUR in den Dialog-Speicher
    (Default None ⇒ Stufe 0 hat keinerlei Geheimnis-Durchgriff)."""

    quelle_id = "fints"
    SEGMENTE = ERLAUBTE_SEGMENTE            # Audit-Anker (I-1)

    def __init__(self, zugang: BankZugang, schaltung: Scharfschaltung | None,
                 *, pin_holen: Callable[[str], str | None] | None = None) -> None:
        self._zugang = zugang
        self._schaltung = schaltung
        self._pin_holen = pin_holen

    def hole_auszuege(self, von: str, bis: str) -> list[RohAuszug]:
        pruefe_scharf(self._schaltung)      # Wächter VOR allem — auch vor NotImplemented
        raise NotImplementedError(
            "Stufe 0: FinTS-Wire ist bewusst nicht implementiert — Bau = Bau-KI "
            "M6-3 nach docs/64 §12 (Gates G-M6-LIB/G-M6-BANK).")


class AggregatorQuelle:
    """Platzhalter der gegateten Aggregator-Schiene (E-HYBRID/E-SERVER,
    docs/64 §9): lizenzierter AISP statt eigener Server-Kontozugriff.
    Existiert nur, damit die Editions-Schiene im Code sichtbar ist —
    JEDER Aufruf ist ehrlich nicht implementiert (Gate G-M6-AGGREGATOR)."""

    quelle_id = "aggregator"

    def hole_auszuege(self, von: str, bis: str) -> list[RohAuszug]:
        raise NotImplementedError(
            "Aggregator-Schiene ist gegated (G-M6-AGGREGATOR, docs/64 §9/§14) "
            "— kein Bau vor Nutzer-Entscheid.")


#: Vertrags-Anker für den Feld-Flächen-Test (I-2): Erweiterung = bewusste
#: Vertragsänderung in docs/64, nie ein stilles Zusatzfeld.
ZUGANG_FELDER: frozenset[str] = frozenset(f.name for f in fields(BankZugang))
