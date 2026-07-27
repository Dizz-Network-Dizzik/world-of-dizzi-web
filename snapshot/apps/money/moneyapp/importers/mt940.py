"""MT940-Import (SWIFT-Kontoauszug) — reine Funktion, kein Fremdpaket.

MT940 ist das ältere, zeilenbasierte SWIFT-Format (``.sta``/``.txt``), das viele
DE-Banken weiterhin anbieten. Aufbau je Auszug (Felder ``:tag:``):

    :20:  Auftragsreferenz (Auszug-Kopf)
    :25:  Kontobezeichnung (IBAN/Konto)
    :28C: Auszugsnummer
    :60F: Anfangssaldo
    :61:  UMSATZ  — Valuta(JJMMTT) [Buchung(MMTT)] C|D Betrag(1,23) Buchungsart …
    :86:  Mehrzweckfeld zum vorherigen :61: (Verwendungszweck/Gegenpartei,
          oft in ?-Subfeldern: ?20..?29 Zweck, ?32/?33 Name, ?30 BLZ, ?31 Konto)
    :62F: Endsaldo

Eine Bewegung = ein ``:61:`` + zugehöriges ``:86:``. Betrag aus :61:
(C=Gutschrift +, D=Lastschrift −; RC/RD = Storno dreht das Vorzeichen). Datum =
Valuta; ist die optionale Buchungs-MMTT angegeben, nutzen wir deren Tag/Monat
mit dem Valuta-Jahr inkl. Jahreswechsel-Korrektur (Monatsdifferenz > 6 ⇒
Nachbar-Jahr, z. B. Valuta 31.12. + Buchung 02.01. → Folgejahr). Kein Geld-Float
— Beträge via ``common.parse_dezimal``.
"""

from __future__ import annotations

import re

from .common import Bewegung, ImportFehler, parse_datum, parse_dezimal

# :61: Valuta(6) [Buchung(4)] RC/RD/C/D [Währungskennbuchstabe] Betrag … RefRest
_F61 = re.compile(
    r"^(?P<valuta>\d{6})(?P<buchung>\d{4})?"
    r"(?P<storno>R?)(?P<cd>[CD])(?P<fund>[A-Z])?"
    r"(?P<betrag>[\d.,]+)"
    r"(?P<rest>.*)$")


def _felder(text: str) -> list[tuple[str, str]]:
    """Zerlegt einen MT940-Text in (tag, wert)-Paare. Fortsetzungszeilen (ohne
    führendes ``:tag:``) werden an den laufenden Wert angehängt."""
    roh = text.replace("\r\n", "\n").replace("\r", "\n")
    paare: list[tuple[str, str]] = []
    tag: str | None = None
    wert: list[str] = []
    for zeile in roh.split("\n"):
        if zeile.strip() in ("-", ""):           # Auszug-Endemarke / Leerzeile
            if zeile.strip() == "-" and tag is not None:
                paare.append((tag, "\n".join(wert)))
                tag, wert = None, []
            continue
        m = re.match(r"^:(\d{2}[A-Z]?):(.*)$", zeile)
        if m:
            if tag is not None:
                paare.append((tag, "\n".join(wert)))
            tag, wert = m.group(1), [m.group(2)]
        elif tag is not None:
            wert.append(zeile)
    if tag is not None:
        paare.append((tag, "\n".join(wert)))
    return paare


def _86_zerlegen(text: str) -> tuple[str, str, str]:
    """``:86:`` → (gegenpartei, verwendungszweck, referenz). Kennt das in DE
    übliche ?-Subfeld-Schema; ohne Subfelder gilt der ganze Text als Zweck."""
    if "?" not in text:
        flach = re.sub(r"\s+", " ", text.strip())
        return "", flach, ""
    sub: dict[str, str] = {}
    for code, inhalt in re.findall(r"\?(\d{2})([^?]*)", text):
        sub[code] = sub.get(code, "") + inhalt
    zweck = " ".join(sub[c].strip() for c in
                     ("20", "21", "22", "23", "24", "25", "26", "27", "28", "29")
                     if c in sub).strip()
    name = " ".join(sub[c].strip() for c in ("32", "33") if c in sub).strip()
    referenz = sub.get("34", "").strip() or sub.get("30", "").strip()
    return re.sub(r"\s+", " ", name), re.sub(r"\s+", " ", zweck), referenz


# :61:-Rest = [N+3 Geschäftsvorfall][Kundenreferenz]//[Bankreferenz][\n Zusatz].
# 'NONREF' (Standard-Platzhalter „keine Referenz") wird wie leer behandelt.
_REST61 = re.compile(r"^(?:N[A-Z0-9]{3})?(?P<kunde>[^/\n]*)(?://(?P<bank>[^\n]*))?")


def _ref_aus_61(rest: str) -> str:
    rest = (rest or "").strip()
    if not rest:
        return ""
    m = _REST61.match(rest)
    if not m:
        return rest
    kunde = (m.group("kunde") or "").strip()
    bank = (m.group("bank") or "").strip()
    if kunde and kunde.upper() != "NONREF":
        return kunde
    return bank


def _datum_aus_61(valuta: str, buchung: str | None) -> str:
    iso = parse_datum(valuta)                     # JJMMTT → ISO (Jahr = Valuta-Jahr)
    if buchung:                                    # MMTT: Tag/Monat ersetzen, Jahr = Valuta-Jahr
        jahr = int(iso[:4])                        # … MIT Jahreswechsel-Korrektur: Buchung
        monat, tag = buchung[:2], buchung[2:]      # liegt kalendarisch nahe der Valuta —
        diff = int(monat) - int(iso[5:7])          # Monatsdifferenz > 6 ⇒ Nachbar-Jahr.
        if diff > 6:                               # Valuta Jan, Buchung Dez → Vorjahr
            jahr -= 1
        elif diff < -6:                            # Valuta Dez, Buchung Jan → Folgejahr
            jahr += 1
        try:
            return parse_datum(f"{tag}.{monat}.{jahr}")
        except ImportFehler:
            return iso                             # unplausible MMTT → Valuta-Datum
    return iso


def parse_mt940(inhalt: str, standard_waehrung: str = "EUR") -> list[Bewegung]:
    """MT940-Text → Liste von ``Bewegung`` (ein ``:61:`` je Eintrag)."""
    if not inhalt.strip():
        raise ImportFehler("Leere MT940-Eingabe")
    felder = _felder(inhalt)
    if not any(t == "61" for t, _ in felder):
        raise ImportFehler("MT940: kein :61:-Feld gefunden — kein MT940?")

    bewegungen: list[Bewegung] = []
    i = 0
    while i < len(felder):
        tag, wert = felder[i]
        if tag != "61":
            i += 1
            continue
        # M-9: NUR die erste Zeile matchen. Eine :61:-Fortsetzungszeile (DK-üblich:
        # /OCMT/-Ursprungsbetrag, /CHGS/-Gebühren bei FX-Kartenzahlung) hängt hinter
        # einem \n; der $-Anker ohne DOTALL scheiterte sonst und machte die GANZE Datei
        # unimportierbar. Die Fortsetzung ist rein informativ.
        m = _F61.match(wert.strip().split("\n", 1)[0])
        if not m:
            raise ImportFehler(f"MT940: :61: nicht lesbar: {wert!r}")
        betrag = abs(parse_dezimal(m.group("betrag"), standard_waehrung))
        cd = m.group("cd")
        storno = bool(m.group("storno"))
        # C = Gutschrift (+), D = Lastschrift (−); R… (RC/RD) = Storno dreht um.
        vorzeichen = 1 if cd == "C" else -1
        if storno:
            vorzeichen = -vorzeichen
        betrag *= vorzeichen
        datum = _datum_aus_61(m.group("valuta"), m.group("buchung"))
        ref61 = _ref_aus_61(m.group("rest") or "")

        gegenpartei = verwendungszweck = referenz = ""
        if i + 1 < len(felder) and felder[i + 1][0] == "86":
            gegenpartei, verwendungszweck, ref86 = _86_zerlegen(felder[i + 1][1])
            referenz = ref86 or ref61
            i += 1
        else:
            referenz = ref61
        bewegungen.append(Bewegung(
            datum=datum, betrag_minor=betrag, waehrung=standard_waehrung.upper(),
            gegenpartei=gegenpartei, verwendungszweck=verwendungszweck,
            referenz=referenz, roh={"f61": wert}))
        i += 1
    return bewegungen
