"""camt.053-Import (ISO-20022 Bank-to-Customer Statement) — nur stdlib.

camt.053 ist der europäische XML-Standard für Kontoauszüge (SEPA): Banken wie
DKB, ING, Sparkassen und Revolut (Business) liefern ihn. Aufbau:

    Document / BkToCstmrStmt / Stmt(+) / Ntry(+)        ← eine Ntry = eine Buchung
      Ntry/Amt (Ccy=…) , Ntry/CdtDbtInd (CRDT|DBIT)     ← Betrag + Richtung
      Ntry/BookgDt|ValDt / Dt|DtTm                       ← Datum
      Ntry/NtryDtls/TxDtls/RltdPties/{Cdtr,Dbtr}/Nm      ← Gegenpartei
      Ntry/NtryDtls/TxDtls/RmtInf/Ustrd                  ← Verwendungszweck
      Ntry/NtryDtls/TxDtls/Refs/{EndToEndId,AcctSvcrRef} ← Referenz (Dedupe)

Wir lesen über ``xml.etree.ElementTree`` und ignorieren den Namespace (Tag-
LocalName-Vergleich), weil die camt-Version (.001.02 / .001.08 …) im Namespace
steckt und sonst jede Version eigenen Code bräuchte. Beträge: ``Decimal``-Text
→ Minor-Units; Vorzeichen kommt aus ``CdtDbtInd`` (CRDT = +, DBIT = −).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from appkit.xml_safe import UnsicheresXml, sichere_wurzel

from .common import Bewegung, ImportFehler, parse_datum, parse_dezimal


def _lname(tag: str) -> str:
    """LocalName ohne ``{namespace}``-Präfix."""
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element, *pfad: str) -> ET.Element | None:
    """Folgt einem LocalName-Pfad (namespace-agnostisch); erstes Kind je Stufe."""
    cur: ET.Element | None = el
    for name in pfad:
        if cur is None:
            return None
        cur = next((k for k in cur if _lname(k.tag) == name), None)
    return cur


def _findall(el: ET.Element, name: str) -> list[ET.Element]:
    return [k for k in el if _lname(k.tag) == name]


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _datum(ntry: ET.Element) -> str:
    """Buchungsdatum (BookgDt) bevorzugt, sonst Valuta (ValDt); Dt oder DtTm."""
    for feld in ("BookgDt", "ValDt"):
        dt = _find(ntry, feld)
        if dt is None:
            continue
        for art in ("Dt", "DtTm"):
            roh = _text(_find(dt, art))
            if roh:
                return parse_datum(roh)
    raise ImportFehler("camt: Buchung ohne BookgDt/ValDt")


def _gegenpartei(txdtls: ET.Element | None, cdtdbt: str) -> str:
    """Die GEGEN-Seite aus Sicht des Kontos: bei Gutschrift (CRDT) der Debitor
    (wer überwiesen hat), bei Lastschrift (DBIT) der Kreditor (an wen)."""
    if txdtls is None:
        return ""
    rel = _find(txdtls, "RltdPties")
    if rel is None:
        return ""
    reihenfolge = ("Dbtr", "Cdtr") if cdtdbt == "CRDT" else ("Cdtr", "Dbtr")
    for rolle in reihenfolge:
        partei = _find(rel, rolle)
        name = _text(_find(partei, "Nm")) if partei is not None else ""
        if name:
            return name
    return ""


def _verwendungszweck(txdtls: ET.Element | None) -> str:
    if txdtls is None:
        return ""
    rmt = _find(txdtls, "RmtInf")
    if rmt is None:
        return ""
    teile = [_text(u) for u in _findall(rmt, "Ustrd") if _text(u)]
    return " ".join(teile)


def _referenz(txdtls: ET.Element | None, ntry: ET.Element) -> str:
    quellen = []
    if txdtls is not None:
        refs = _find(txdtls, "Refs")
        if refs is not None:
            for feld in ("EndToEndId", "TxId", "AcctSvcrRef", "MsgId"):
                quellen.append(_text(_find(refs, feld)))
    quellen.append(_text(_find(ntry, "AcctSvcrRef")))
    for q in quellen:
        if q and q.upper() != "NOTPROVIDED":
            return q
    return ""


def _entry_status(ntry: ET.Element) -> str:
    """Buchungsstatus einer ``Ntry`` in Großschreibung — beide Schemata: ``<Sts>BOOK
    </Sts>`` (alt, Text) UND ``<Sts><Cd>BOOK</Cd></Sts>`` (neu, strukturiert). ``""``
    wenn kein ``Sts`` vorhanden (viele camt.053 tragen keins ⇒ dann als gebucht gelten)."""
    sts = _find(ntry, "Sts")
    if sts is None:
        return ""
    cd = _find(sts, "Cd")
    return (_text(cd) if cd is not None else _text(sts)).upper()


def parse_camt(inhalt: str | bytes, standard_waehrung: str = "EUR") -> list[Bewegung]:
    """camt.053-XML → Liste von ``Bewegung`` (eine je ``Ntry``).

    Eine ``Ntry`` kann mehrere ``TxDtls`` (Batch-Sammelbuchung) enthalten —
    wir nehmen die erste für Gegenpartei/Zweck/Referenz; der Entry-Betrag bleibt
    die gebuchte Summe (so steht sie auch auf dem Konto)."""
    try:
        # Gehärtet (docs/50 P4.1): DTD/Entities werden abgewiesen ⇒ kein XXE,
        # keine Billion-Laughs-Entity-Bombe (geteilter appkit.xml_safe-Schutz).
        wurzel = sichere_wurzel(inhalt)
    except UnsicheresXml as e:
        raise ImportFehler(f"camt: unsicheres XML abgewiesen ({e})")
    except ET.ParseError as e:
        raise ImportFehler(f"camt: kein gültiges XML ({e})")

    ntrys: list[ET.Element] = []
    for el in wurzel.iter():
        if _lname(el.tag) == "Ntry":
            ntrys.append(el)
    if not ntrys:
        raise ImportFehler("camt: keine <Ntry> gefunden — kein camt.053?")

    bewegungen: list[Bewegung] = []
    for ntry in ntrys:
        # M-12: NUR gebuchte Umsätze. camt.052 (Intraday) + manche .053 tragen
        # vorgemerkte (PDNG/INFO) Einträge; würden die als gebucht importiert und
        # später echt gebucht, entstünde eine Dublette (anderes Datum/Ref ⇒ anderer
        # Dedupe-Hash) — doppelt in der EÜR. Fehlt Sts (häufig bei .053), gilt gebucht.
        status = _entry_status(ntry)
        if status and status != "BOOK":
            continue
        amt_el = _find(ntry, "Amt")
        if amt_el is None or not _text(amt_el):
            raise ImportFehler("camt: <Ntry> ohne <Amt>")
        waehrung = (amt_el.get("Ccy") or standard_waehrung).upper()
        betrag = abs(parse_dezimal(_text(amt_el), waehrung))
        cdtdbt = _text(_find(ntry, "CdtDbtInd")).upper()
        if cdtdbt not in ("CRDT", "DBIT"):
            raise ImportFehler(f"camt: unklare Richtung CdtDbtInd={cdtdbt!r}")
        if cdtdbt == "DBIT":
            betrag = -betrag
        # Storno-Kennzeichen dreht das Vorzeichen (RvslInd = true).
        if _text(_find(ntry, "RvslInd")).lower() == "true":
            betrag = -betrag

        ntrydtls = _find(ntry, "NtryDtls")
        txdtls = _find(ntrydtls, "TxDtls") if ntrydtls is not None else None
        bewegungen.append(Bewegung(
            datum=_datum(ntry), betrag_minor=betrag, waehrung=waehrung,
            gegenpartei=_gegenpartei(txdtls, cdtdbt),
            verwendungszweck=_verwendungszweck(txdtls),
            referenz=_referenz(txdtls, ntry),
            roh={"cdtdbt": cdtdbt}))
    return bewegungen
