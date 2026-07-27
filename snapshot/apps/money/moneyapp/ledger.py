"""Double-Entry-Ledger — der Kern mit erhöhter Sorgfaltspflicht (F-Q1, docs/11 §6b).

GRUNDSÄTZE (bewusst hart, weil Geld):
1. **Geld ist NIE ein Float.** Beträge sind ganzzahlige **Minor-Units** (Cent
   bei EUR) in ``int``. Float-Arithmetik (0.1 + 0.2 != 0.3) hat in einem
   Hauptbuch nichts verloren. Decimal/Strings nur an der RÄNDERN (Parsen aus
   Eingabe, Formatieren zur Anzeige) — siehe ``parse_betrag``/``format_betrag``.
2. **Doppelte Buchführung.** Eine Buchung (``Buchung``) besteht aus ≥2 Zeilen
   (``Posting``: Konto + vorzeichenbehafteter Betrag). **Invariante: die Summe
   aller Beträge einer Buchung ist 0** — jeder Cent kommt von irgendwo und geht
   irgendwohin. ``Buchung.pruefe()`` erzwingt das; eine unbalancierte Buchung
   existiert gar nicht erst (Konstruktor wirft).
3. **Salden sind abgeleitet, nie gespeichert-und-gehofft.** Der Saldo eines
   Kontos = Summe seiner Postings. Im geschlossenen System ist die Summe ALLER
   Salden 0 (Korollar aus 2) — das ist die globale Konsistenz-Probe.
4. **Vorzeichen-Konvention.** Postings tragen das Vorzeichen direkt: + erhöht
   den Saldo des Kontos, − senkt ihn. Asset/Expense steigen „natürlich" positiv,
   Liability/Income/Equity negativ — diese Norm liegt im Kontotyp (``KONTO_VZ``),
   damit die Anzeige „+120 € Einnahme" statt „−120 €" zeigen kann, OHNE die
   Buchungs-Mathematik zu verbiegen.

Reine Logik, keine DB, keine Seiteneffekte — dadurch property-testbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, Overflow
from typing import Iterable

# Unterstützte Währungen → Nachkommastellen (Minor-Unit-Exponent). Bewusst
# klein gehalten; Erweiterung ist ein Dict-Eintrag, kein Code-Umbau.
WAEHRUNG_DEZIMAL = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "BTC": 8, "JPY": 0}

KONTO_TYPEN = ("asset", "liability", "income", "expense", "equity")
# Anzeige-Vorzeichen je Typ: bei diesen Typen ist ein NEGATIVER Roh-Saldo die
# „gute/natürliche" Richtung (Einnahme, Eigenkapital, Schuld-Tilgung) → zur
# Anzeige umdrehen. Die Buchungs-Mathematik bleibt davon unberührt.
KONTO_VZ = {"asset": 1, "expense": 1, "liability": -1, "income": -1, "equity": -1}


class LedgerError(ValueError):
    """Verletzung einer Buchhaltungs-Regel (unbalanciert, falscher Typ …)."""


def dezimalstellen(waehrung: str) -> int:
    try:
        return WAEHRUNG_DEZIMAL[waehrung]
    except KeyError:
        raise LedgerError(f"Unbekannte Währung: {waehrung!r}")


# Minor-Units müssen in SQLites 64-bit-INTEGER passen (AT-1/F2) — zentrale
# Grenze für ALLE manuellen Schreibpfade (Import prüft zusätzlich in importers/common).
MAX_MINOR = 2 ** 63 - 1


def pruefe_minor(minor: int) -> int:
    """Wächter: Minor-Units außerhalb des SQLite-INTEGER-Bereichs ⇒ LedgerError
    (400 am Rand) statt OverflowError beim INSERT (500)."""
    if abs(minor) > MAX_MINOR:
        raise LedgerError("Betrag unrealistisch groß (überschreitet das Buchungs-Limit)")
    return minor


def parse_betrag(text: str | int | float, waehrung: str = "EUR") -> int:
    """Eingabe (\"12,50\" / \"12.50\" / 12.5) → Minor-Units (1250). Float wird
    NUR hier toleriert (Eingabe-Komfort) und SOFORT über Decimal exakt auf die
    Minor-Unit gerundet (kaufmännisch) — danach existiert kein Float mehr."""
    if isinstance(text, bool):  # bool ist int-Subtyp → Unfug ausschließen
        raise LedgerError("Betrag darf kein Wahrheitswert sein")
    exp = dezimalstellen(waehrung)
    try:
        d = Decimal(str(text).strip().replace(",", ".")) if not isinstance(text, int) \
            else Decimal(text)
    except (InvalidOperation, ValueError):
        raise LedgerError(f"Kein gültiger Betrag: {text!r}")
    if not d.is_finite():
        raise LedgerError("Betrag muss endlich sein")
    quant = Decimal(1).scaleb(-exp)
    try:
        # M-6: ein absurd großer Betrag (z. B. '1e999999') sprengt Decimals Emax bei
        # der Division/Quantisierung ⇒ decimal.Overflow. Sauber als LedgerError (400 am
        # Rand) abfangen statt als OverflowError durchschlagen zu lassen (→ 500).
        minor = (d / quant).to_integral_value(rounding=ROUND_HALF_UP)
    except (InvalidOperation, Overflow):
        raise LedgerError("Betrag unrealistisch groß (überschreitet das Buchungs-Limit)")
    return pruefe_minor(int(minor))


def format_betrag(minor: int, waehrung: str = "EUR") -> str:
    """Minor-Units → Anzeige-String (\"1250\" EUR → \"12.50\"). Exakt, kein Float."""
    exp = dezimalstellen(waehrung)
    if exp == 0:
        return str(minor)
    vorz = "-" if minor < 0 else ""
    s = str(abs(minor)).rjust(exp + 1, "0")
    return f"{vorz}{s[:-exp]}.{s[-exp:]}"


@dataclass(frozen=True)
class Posting:
    """Eine Zeile einer Buchung: Betrag (Minor-Units, vorzeichenbehaftet) auf
    ein Konto. ``betrag`` == 0 ist sinnlos und wird abgelehnt.

    ``waehrung`` ist optional: bei reinen Ein-Währungs-Buchungen bleibt sie
    ``None`` (Verhalten wie bisher). Bei WÄHRUNGSÜBERGREIFENDEN Buchungen trägt
    JEDE Zeile ihre Währung — dann erzwingt ``Buchung`` Balance PRO Währung
    (sonst entstünde Geld aus Wechselkurs-Magie). Die Währung einer Zeile ist
    immer die ihres Kontos; sie wird nicht zusätzlich gespeichert (aus dem Konto
    ableitbar), sondern dient hier nur der Balance-Prüfung."""
    konto_id: str
    betrag: int
    waehrung: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.betrag, int) or isinstance(self.betrag, bool):
            raise LedgerError("Posting.betrag muss ganzzahlige Minor-Units sein")
        if self.betrag == 0:
            raise LedgerError("Posting.betrag 0 ist nicht erlaubt")
        if not self.konto_id:
            raise LedgerError("Posting ohne Konto")


@dataclass(frozen=True)
class Buchung:
    """Atomare doppelte Buchung: ≥2 Postings, Summe == 0. Unbalanciert ⇒
    LedgerError im Konstruktor — eine ungültige Buchung kann nicht entstehen.

    Tragen die Postings Währungen (FX-Buchung), gilt zusätzlich die strengere
    Invariante: **jede Währung balanciert für sich auf 0**. Damit ist eine
    Zwei-Zeilen-Umbuchung über Währungen (EUR − / USD +) ausgeschlossen — eine
    FX-Buchung MUSS über Währungstausch-Gegenkonten je Währung balanciert sein."""
    postings: tuple[Posting, ...]
    notiz: str = ""

    def __post_init__(self) -> None:
        if len(self.postings) < 2:
            raise LedgerError("Eine Buchung braucht mindestens zwei Postings")
        konten = {p.konto_id for p in self.postings}
        if len(konten) < 2:
            raise LedgerError("Eine Buchung muss mindestens zwei Konten berühren")
        s = sum(p.betrag for p in self.postings)
        if s != 0:
            raise LedgerError(
                f"Buchung unbalanciert: Summe der Postings ist {s}, muss 0 sein")
        # Multi-Währung: entweder ALLE oder KEINE Zeile trägt eine Währung;
        # tragen sie welche, muss JEDE Währung für sich 0 ergeben.
        mit = [p for p in self.postings if p.waehrung is not None]
        if mit:
            if len(mit) != len(self.postings):
                raise LedgerError(
                    "Misch-Buchung: entweder ALLE oder KEINE Zeile trägt eine Währung")
            je: dict[str, int] = {}
            for p in self.postings:
                je[p.waehrung] = je.get(p.waehrung, 0) + p.betrag
            unbal = {w: v for w, v in je.items() if v != 0}
            if unbal:
                raise LedgerError(
                    f"FX-Buchung pro Währung unbalanciert: {unbal} — Gegenbuchung "
                    "über Währungstausch-Konten fehlt")

    @property
    def volumen(self) -> int:
        """Umgesetztes Volumen = Summe der positiven Beträge (= |negativen|)."""
        return sum(p.betrag for p in self.postings if p.betrag > 0)


def einfache_buchung(von_konto: str, nach_konto: str, betrag: int,
                     notiz: str = "") -> Buchung:
    """Komfort für den häufigsten Fall: ``betrag`` (Minor-Units, > 0) fließt
    von einem Konto auf ein anderes. Erzeugt die balancierte Zwei-Zeilen-Buchung."""
    if betrag <= 0:
        raise LedgerError("Betrag einer einfachen Buchung muss > 0 sein")
    return Buchung(
        postings=(Posting(nach_konto, betrag), Posting(von_konto, -betrag)),
        notiz=notiz)


def fx_buchung(von_konto: str, betrag_von: int, waehrung_von: str,
               nach_konto: str, betrag_nach: int, waehrung_nach: str,
               clearing_von: str, clearing_nach: str, notiz: str = "") -> Buchung:
    """Währungsübergreifende Umbuchung als PRO-WÄHRUNG balancierte Vier-Zeilen-
    Buchung. ``betrag_von``/``betrag_nach`` sind positive Magnitudes (Minor-Units
    in der jeweiligen Währung). Schema (textbuchhalterisch korrekt):

        von_konto      −betrag_von  (waehrung_von)
        clearing_von   +betrag_von  (waehrung_von)   ← „Währungstausch"-Topf je Whg
        clearing_nach  −betrag_nach (waehrung_nach)
        nach_konto     +betrag_nach (waehrung_nach)

    Jede Währung balanciert für sich auf 0 — kein Geld entsteht aus dem Kurs; die
    beiden Tausch-Konten halten die FX-Position (ihr EUR-Gegenwert = Kursgewinn/
    -verlust). Reale Beträge fließen korrekt: ``von`` sinkt, ``nach`` steigt."""
    if waehrung_von == waehrung_nach:
        raise LedgerError("fx_buchung verlangt verschiedene Währungen — "
                          "gleiche Währung ⇒ einfache_buchung")
    if betrag_von <= 0 or betrag_nach <= 0:
        raise LedgerError("FX-Beträge müssen > 0 sein")
    return Buchung(postings=(
        Posting(von_konto, -betrag_von, waehrung_von),
        Posting(clearing_von, betrag_von, waehrung_von),
        Posting(clearing_nach, -betrag_nach, waehrung_nach),
        Posting(nach_konto, betrag_nach, waehrung_nach),
    ), notiz=notiz)


def umrechnen(betrag_minor: int, von_waehrung: str, nach_waehrung: str,
              kurse: dict[str, str | float]) -> int:
    """Rechnet einen Minor-Unit-Betrag EXAKT (über ``Decimal``) von einer Währung
    in eine andere. ``kurse`` = Mapping Währung → Kurs als „EUR je 1 Einheit"
    (EUR selbst = 1). Berücksichtigt unterschiedliche Nachkommastellen der
    Minor-Units (EUR 2, JPY 0, BTC 8). Informativ („≈") — Kurse pflegt der Nutzer.
    """
    if von_waehrung == nach_waehrung:
        return betrag_minor
    try:
        kurs_von = Decimal(str(kurse[von_waehrung]))
        kurs_nach = Decimal(str(kurse[nach_waehrung]))
    except (KeyError, InvalidOperation):
        raise LedgerError(f"Kein Kurs für {von_waehrung}→{nach_waehrung} hinterlegt")
    # M-7: 'Infinity'/'NaN' sind gültige Decimals, passieren aber den ==0-Check und
    # sprengen später int(Decimal-Inf) ⇒ OverflowError → 500. Endlichkeit + Positivität
    # sind Pflicht (Kurs = "EUR je Einheit", muss > 0 sein).
    if not (kurs_von.is_finite() and kurs_nach.is_finite()):
        raise LedgerError(f"Wechselkurs {von_waehrung}→{nach_waehrung} ist nicht endlich")
    if kurs_von <= 0 or kurs_nach <= 0:
        raise LedgerError(f"Wechselkurs {von_waehrung}→{nach_waehrung} muss > 0 sein")
    major_von = Decimal(betrag_minor).scaleb(-dezimalstellen(von_waehrung))
    eur = major_von * kurs_von
    major_nach = eur / kurs_nach
    quant = Decimal(1).scaleb(-dezimalstellen(nach_waehrung))
    return int((major_nach / quant).to_integral_value(rounding=ROUND_HALF_UP))


def saldo(postings: Iterable[Posting], konto_id: str) -> int:
    """Roh-Saldo eines Kontos = Summe seiner Posting-Beträge (Minor-Units)."""
    return sum(p.betrag for p in postings if p.konto_id == konto_id)


def anzeige_saldo(roh_saldo: int, konto_typ: str) -> int:
    """Roh-Saldo → typ-orientierter Anzeige-Saldo (s. KONTO_VZ): eine Einnahme
    erscheint positiv, obwohl ihr Income-Konto roh negativ steht."""
    if konto_typ not in KONTO_TYPEN:
        raise LedgerError(f"Unbekannter Kontotyp: {konto_typ!r}")
    return roh_saldo * KONTO_VZ[konto_typ]


def gesamt_konsistent(postings: Iterable[Posting]) -> bool:
    """Globale Probe: in einem System aus nur balancierten Buchungen ist die
    Summe ALLER Posting-Beträge 0. Bricht das, ist irgendwo Geld aus dem Nichts
    entstanden — ein Bug, kein erlaubter Zustand."""
    return sum(p.betrag for p in postings) == 0
