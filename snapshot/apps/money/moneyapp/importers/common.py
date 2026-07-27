"""Gemeinsame Zwischenform aller Import-Parser + tolerante Feld-Parser.

GRUNDSÄTZE (gleicher Geist wie der Ledger-Kern):
1. **Geld bleibt exakt.** Beträge werden über ``Decimal`` aus dem Eingabe-Text
   gelesen und SOFORT in ganzzahlige **Minor-Units** gewandelt — ab da nie wieder
   Float. ``parse_dezimal`` erkennt DE (``1.234,56``) und EN (``1,234.56``).
2. **Datum normalisiert** auf ISO ``YYYY-MM-DD`` (lexikografisch sortier-/
   filterbar) — egal ob die Quelle ``31.12.2025``, ``2025-12-31`` oder
   ``12/31/2025`` liefert.
3. **Eine Bewegung ist roh-neutral.** Sie weiß noch nichts von Konten oder
   doppelter Buchung — sie trägt nur, was im Auszug stand. Die App macht daraus
   die balancierte Buchung. Dadurch sind die Parser ohne DB property-testbar.
4. **Stabiler Dedupe-Hash** über die natürlichen Merkmale einer Bewegung; ein
   erneuter Import desselben Auszugs ist damit idempotent.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, Overflow

from ..ledger import (MAX_MINOR, Buchung, LedgerError, dezimalstellen,
                      einfache_buchung)


class ImportFehler(ValueError):
    """Eine Eingabe konnte nicht als Bewegung gelesen werden (Parser-Fehler)."""


@dataclass(frozen=True)
class Bewegung:
    """Eine einzelne Konto-Bewegung aus einem Auszug — quell-neutral.

    ``betrag_minor`` ist vorzeichenbehaftet aus Sicht des importierten Kontos:
    positiv = Geldeingang (Gutschrift), negativ = Geldausgang (Lastschrift).
    Alle Text-Felder sind getrimmt; fehlende Felder sind ``""``.
    """

    datum: str                       # ISO YYYY-MM-DD
    betrag_minor: int                # vorzeichenbehaftet, Minor-Units
    waehrung: str = "EUR"
    gegenpartei: str = ""            # Name/IBAN der Gegenseite (für Regeln)
    verwendungszweck: str = ""       # Buchungstext/Zweck (für Regeln)
    referenz: str = ""               # Bank-Referenz (EndToEnd/AcctSvcrRef/:61: ref)
    roh: dict = field(default_factory=dict, compare=False)  # Originalfelder (Audit)

    def __post_init__(self) -> None:
        if not isinstance(self.betrag_minor, int) or isinstance(self.betrag_minor, bool):
            raise ImportFehler("betrag_minor muss ganzzahlige Minor-Units sein")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.datum or ""):
            raise ImportFehler(f"Datum nicht ISO-normalisiert: {self.datum!r}")

    @property
    def hash(self) -> str:
        return bewegung_hash(self)


def bewegung_hash(b: Bewegung) -> str:
    """Stabiler SHA-256 über die natürlichen Merkmale einer Bewegung.

    Trägt der Auszug eine Bank-Referenz (camt: AcctSvcrRef/EndToEndId, MT940:
    Kundenreferenz aus :61:), ist sie Teil des Hashes und macht ihn eindeutig.
    Ohne Referenz teilen zwei am selben Tag betrags- und textgleiche Bewegungen
    denselben Hash — ein erneuter Import bleibt damit idempotent (bewusster
    Trade-off; in der Praxis tragen echte Auszüge eine Referenz).
    """
    teile = (b.datum, str(b.betrag_minor), b.waehrung,
             _norm(b.gegenpartei), _norm(b.verwendungszweck), _norm(b.referenz))
    roh = "\x1f".join(teile)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    """Normalisiert Freitext für den Hash: trimmen + Mehrfach-Whitespace zu einem."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def als_buchung(b: Bewegung, bank_konto_id: str, sammel_konto_id: str) -> Buchung | None:
    """Bewegung → balancierte doppelte Buchung (Bankkonto ↔ Sammelkonto).

    Eingang (betrag > 0): Geld fließt vom Sammelkonto „Nicht zugeordnet" AUF das
    Bankkonto (Bank +). Ausgang (betrag < 0): umgekehrt. ``betrag == 0`` ergibt
    keine Buchung (``None``) — eine Null-Bewegung gibt es im Ledger nicht.
    Die Vorzeichen-/Richtungs-Mathematik bleibt im geprüften ``ledger``-Kern."""
    notiz = (b.verwendungszweck or b.gegenpartei or "Import").strip()[:200]
    if b.betrag_minor > 0:
        return einfache_buchung(sammel_konto_id, bank_konto_id, b.betrag_minor, notiz)
    if b.betrag_minor < 0:
        return einfache_buchung(bank_konto_id, sammel_konto_id, -b.betrag_minor, notiz)
    return None


# --------------------------------------------------------------- Betrag-Parsing

# Erkennt DE-Notation (Tausenderpunkt + Dezimalkomma) vs. EN (Tausenderkomma +
# Dezimalpunkt). Heuristik über das ZULETZT stehende Trennzeichen (= Dezimal).
def parse_dezimal(text: str | int | float, waehrung: str = "EUR") -> int:
    """Roh-Betrag (z. B. ``"1.234,56"``, ``"1,234.56"``, ``"-99.00"``, ``12.5``)
    → ganzzahlige Minor-Units der Währung. Float wird NUR als Eingabe-Komfort
    toleriert und sofort exakt über ``Decimal`` gerundet.

    Vorzeichen: führendes ``-`` oder ``+``; ein in Klammern stehender Betrag
    ``(1,23)`` gilt (Buchhaltungs-Konvention) als negativ.
    """
    if isinstance(text, bool):
        raise ImportFehler("Betrag darf kein Wahrheitswert sein")
    if isinstance(text, int):
        return _quant(Decimal(text), waehrung)
    if isinstance(text, float):
        d = Decimal(str(text))
        if not d.is_finite():
            raise ImportFehler("Betrag muss endlich sein")
        return _quant(d, waehrung)

    s = str(text).strip()
    if not s:
        raise ImportFehler("Leerer Betrag")
    neg = False
    if s.startswith("(") and s.endswith(")"):     # (1,23) = -1,23
        neg, s = True, s[1:-1].strip()
    # Währungssymbole / Tausender-Schutzzeichen / NBSP entfernen.
    s = s.replace(" ", " ").replace(" ", "")
    s = re.sub(r"(?i)(eur|usd|gbp|chf|btc|jpy|€|\$|£)", "", s)
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        neg = not neg
        s = s[1:]
    if not s:
        raise ImportFehler(f"Kein Betrag erkennbar: {text!r}")

    komma, punkt = s.rfind(","), s.rfind(".")
    if komma != -1 and punkt != -1:
        # Beide vorhanden: das WEITER RECHTS stehende ist das Dezimaltrennzeichen.
        if komma > punkt:                          # DE: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                                       # EN: 1,234.56
            s = s.replace(",", "")
    elif komma != -1:
        # Nur Komma: Dezimalkomma, ES SEI DENN es trennt klar Tausender (1,234).
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")                  # 1,234 / 12,345,678 = Tausender
        else:
            s = s.replace(",", ".")                 # 1,5 / 1234,56 = Dezimal
    elif punkt != -1:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")                  # 1.234 = Tausender (DE ohne Dezimal)
        # sonst: Punkt ist Dezimalpunkt (Standardfall) — unverändert lassen.

    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ImportFehler(f"Kein gültiger Betrag: {text!r}")
    if not d.is_finite():
        raise ImportFehler("Betrag muss endlich sein")
    if neg:
        d = -d
    return _quant(d, waehrung)


def _quant(d: Decimal, waehrung: str) -> int:
    try:
        exp = dezimalstellen(waehrung)
    except LedgerError:
        # M-8: eine dem Ledger unbekannte Währung (SEK/PLN/… in Multi-Währungs-CSV)
        # darf NICHT als LedgerError den GANZEN Import mit 500 abbrechen. Toleranter
        # 2-Stellen-Default reicht: der Endpoint überspringt Fremdwährung ohnehin
        # sauber (FX v1 nicht unterstützt) — der exakte Minor-Wert wird nie gebucht.
        exp = 2
    quant = Decimal(1).scaleb(-exp)
    try:
        # M-6: ein absurd großer Wert ('1e999999', kaputte/böswillige Datei) sprengt
        # Decimals Emax bei der Division ⇒ decimal.Overflow. Sauber als ImportFehler
        # (→ 400) statt als OverflowError beim INSERT (→ 500).
        minor = int((d / quant).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, Overflow):
        raise ImportFehler("Betrag unrealistisch groß (überschreitet das Buchungs-Limit)")
    # AT-1: Grenze = SQLites INTEGER-Bereich.
    if abs(minor) > MAX_MINOR:
        raise ImportFehler("Betrag unrealistisch groß (überschreitet das Buchungs-Limit)")
    return minor


# ---------------------------------------------------------------- Datum-Parsing

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})")
_COMPACT = re.compile(r"^(\d{2})(\d{2})(\d{2})$")     # MT940 :61: JJMMTT


def parse_datum(text: str, tagerst: bool = True) -> str:
    """Datum aus diversen Notationen → ISO ``YYYY-MM-DD``.

    Unterstützt: ISO (``2025-12-31``, auch mit Uhrzeit), DE (``31.12.2025`` /
    ``31.12.25``), Slash (``31/12/2025``; ``tagerst`` steuert DE- vs. US-
    Reihenfolge bei mehrdeutigen Slash-Daten) und MT940-kompakt (``251231``).
    """
    s = (text or "").strip()
    if not s:
        raise ImportFehler("Leeres Datum")

    m = _ISO.match(s)
    if m:
        return _baue(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DE.match(s)
    if m:
        return _baue(_jahr(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _SLASH.match(s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        tag, monat = (a, b) if tagerst else (b, a)
        if monat > 12 and tag <= 12:               # eindeutig vertauscht → korrigieren
            tag, monat = monat, tag
        return _baue(_jahr(m.group(3)), monat, tag)
    m = _COMPACT.match(s)
    if m:
        return _baue(_jahr(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise ImportFehler(f"Datum nicht erkannt: {text!r}")


def _jahr(roh: str) -> int:
    j = int(roh)
    if j < 100:                                     # zweistellig → 2000er-Fenster
        return 2000 + j
    return j


def _baue(jahr: int, monat: int, tag: int) -> str:
    try:
        return date(jahr, monat, tag).isoformat()
    except ValueError as e:
        raise ImportFehler(f"Ungültiges Datum {jahr}-{monat}-{tag}: {e}")


def _ts() -> str:  # nur als Default genutzt; vermeidet Import in jedem Parser
    return datetime.now().date().isoformat()
