"""Auswertungen — reine, deterministische Berechnungsfunktionen (Teil B + D).

Trennung wie im Ledger: die Funktionen hier rechnen NUR auf einfachen Strukturen
(Listen von dicts), die der HTTP-Layer aus der DB lädt. Dadurch sind sie ohne
DB/HTTP testbar und liefern bei gleicher Eingabe immer dasselbe Ergebnis.

Grundgrößen:
- **netto** einer Buchung = Summe ihrer Postings auf VERMÖGENS-Konten (asset +
  liability). > 0 ⇒ Geldzufluss (Einnahme), < 0 ⇒ Abfluss (Ausgabe), == 0 ⇒
  reiner Umbuchung/Transfer zwischen eigenen Konten (zählt NICHT als Cashflow).
- **Cashflow** über einen Zeitraum = Summe der netto-Werte, getrennt nach
  Einnahmen/Ausgaben, optional je Kategorie.
- **Vermögen** = Roh-Saldo-Summe der Vermögenskonten (Asset − Liability).
- **Budget** = Soll (Limit) gegen Ist (tatsächliche Ausgabe) je Kategorie/Monat.

Alle Beträge sind ganzzahlige Minor-Units (nie Float)."""

from __future__ import annotations

from typing import Iterable, Optional

from datetime import date, timedelta

from .ledger import KONTO_VZ, anzeige_saldo, format_betrag

NICHT_ZUGEORDNET = "_nicht_zugeordnet"


def _im_zeitraum(datum: str, von: Optional[str], bis: Optional[str]) -> bool:
    d = (datum or "")[:10]                          # auf Datums-Präfix normalisieren
    if von and d < von:
        return False
    if bis and d > bis:
        return False
    return True


def cashflow(bewegungen: Iterable[dict], von: Optional[str] = None,
             bis: Optional[str] = None) -> dict:
    """Cashflow über ``bewegungen`` (je: ``datum``, ``netto`` Minor-Units,
    optional ``kategorie_id``/``kategorie_name``). Liefert Einnahmen/Ausgaben/
    Saldo gesamt + je Kategorie (deterministisch sortiert)."""
    einnahmen = ausgaben = 0
    kat: dict[str, dict] = {}
    for b in bewegungen:
        if not _im_zeitraum(b.get("datum", ""), von, bis):
            continue
        netto = int(b.get("netto", 0))
        if netto == 0:
            continue                                # interner Transfer
        kid = b.get("kategorie_id") or NICHT_ZUGEORDNET
        eintrag = kat.setdefault(kid, {
            "kategorie_id": None if kid == NICHT_ZUGEORDNET else kid,
            "kategorie_name": b.get("kategorie_name") or "Nicht zugeordnet",
            "einnahmen": 0, "ausgaben": 0, "saldo": 0, "anzahl": 0})
        if netto > 0:
            einnahmen += netto
            eintrag["einnahmen"] += netto
        else:
            ausgaben += -netto
            eintrag["ausgaben"] += -netto
        eintrag["saldo"] += netto
        eintrag["anzahl"] += 1
    # Sortierung deterministisch: größtes Volumen (|saldo|) zuerst, dann Name.
    je_kategorie = sorted(
        kat.values(),
        key=lambda e: (-(e["einnahmen"] + e["ausgaben"]), e["kategorie_name"]))
    return {"von": von, "bis": bis,
            "einnahmen": einnahmen, "ausgaben": ausgaben,
            "saldo": einnahmen - ausgaben, "je_kategorie": je_kategorie}


def finanzspur(bewegungen_w: Iterable[dict]) -> list[dict]:
    """Per-Bereich-Finanzspur (A5/V17, docs/34): aggregiert netto **PRO WÄHRUNG**
    (nie gemischt — die Ledger-Invariante; keine EUR-Umrechnung hier). ``bewegungen_w``
    je: ``waehrung``, ``netto_w`` (Minor-Units, signiert: > 0 Einnahme, < 0 Ausgabe,
    == 0 interner Transfer ⇒ ignoriert). Liefert je Währung Einnahmen/Ausgaben/Saldo +
    Anzahl, deterministisch sortiert (größtes Volumen zuerst, dann Währung)."""
    je_w: dict[str, dict] = {}
    for b in bewegungen_w:
        netto = int(b.get("netto_w", 0))
        if netto == 0:
            continue
        w = b.get("waehrung", "EUR")
        e = je_w.setdefault(w, {"waehrung": w, "einnahmen": 0, "ausgaben": 0,
                                "saldo": 0, "anzahl": 0})
        if netto > 0:
            e["einnahmen"] += netto
        else:
            e["ausgaben"] += -netto
        e["saldo"] += netto
        e["anzahl"] += 1
    return sorted(je_w.values(),
                  key=lambda x: (-(x["einnahmen"] + x["ausgaben"]), x["waehrung"]))


def vermoegen(konten: Iterable[dict]) -> dict:
    """Vermögensübersicht aus Konten (je: ``id``, ``name``, ``typ``, ``waehrung``,
    ``roh_saldo`` Minor-Units). Liefert je Konto den ANZEIGE-Saldo (typ-orientiert)
    und das Nettovermögen je Währung (Asset − Liability, Roh-Saldo-Summe)."""
    zeilen = []
    netto_je_waehrung: dict[str, int] = {}
    for k in konten:
        typ, waehrung, roh = k["typ"], k.get("waehrung", "EUR"), int(k.get("roh_saldo", 0))
        zeilen.append({
            "id": k.get("id"), "name": k.get("name", ""), "typ": typ,
            "waehrung": waehrung, "saldo_minor": anzeige_saldo(roh, typ)})
        if typ in ("asset", "liability"):
            netto_je_waehrung[waehrung] = netto_je_waehrung.get(waehrung, 0) + roh
    zeilen.sort(key=lambda z: (z["typ"], z["name"]))
    return {"konten": zeilen, "netto_je_waehrung": netto_je_waehrung}


def budget_status(budgets: Iterable[dict], ist_ausgaben: dict[str, int]) -> list[dict]:
    """Soll/Ist je Budget. ``budgets`` (je: ``kategorie_id``, ``kategorie_name``,
    ``monat``, ``betrag`` Soll-Limit Minor-Units); ``ist_ausgaben`` = Mapping
    kategorie_id → bereits ausgegebene Minor-Units im Zeitraum. ``rest`` < 0 ⇒
    überzogen. ``prozent`` ganzzahlig (0 bei Soll 0)."""
    out = []
    for b in budgets:
        soll = int(b.get("betrag", 0))
        ist = int(ist_ausgaben.get(b.get("kategorie_id"), 0))
        # ganzzahlige Prozent, kaufmännisch aufgerundet (kein Float, kein Bankers-Rounding)
        prozent = (ist * 100 + soll // 2) // soll if soll > 0 else 0
        out.append({
            "kategorie_id": b.get("kategorie_id"),
            "kategorie_name": b.get("kategorie_name", ""),
            "monat": b.get("monat", ""),
            "soll": soll, "ist": ist, "rest": soll - ist,
            "prozent": prozent, "ueberzogen": ist > soll})
    out.sort(key=lambda e: (-e["prozent"], e["kategorie_name"]))
    return out


def eur_jahr(bewegungen: Iterable[dict], jahr: int,
             nur_steuer: bool = False) -> dict:
    """EÜR-artige Jahres-Auswertung (Teil D): Einnahmen-Überschuss je Kategorie
    für ein Kalenderjahr. ``bewegungen`` wie bei ``cashflow`` plus optional
    ``steuer_relevant`` (bool) / ``steuer_art`` (str). ``nur_steuer`` filtert auf
    steuerrelevante Kategorien. KEINE Steuererklärung — nur eine Übersicht."""
    von, bis = f"{jahr}-01-01", f"{jahr}-12-31"
    einnahmen = ausgaben = 0
    kat: dict[str, dict] = {}
    for b in bewegungen:
        if not _im_zeitraum(b.get("datum", ""), von, bis):
            continue
        if nur_steuer and not b.get("steuer_relevant"):
            continue
        netto = int(b.get("netto", 0))
        if netto == 0:
            continue
        kid = b.get("kategorie_id") or NICHT_ZUGEORDNET
        eintrag = kat.setdefault(kid, {
            "kategorie_id": None if kid == NICHT_ZUGEORDNET else kid,
            "kategorie_name": b.get("kategorie_name") or "Nicht zugeordnet",
            "steuer_relevant": bool(b.get("steuer_relevant")),
            "steuer_art": b.get("steuer_art") or "",
            "einnahmen": 0, "ausgaben": 0, "ueberschuss": 0})
        if netto > 0:
            einnahmen += netto
            eintrag["einnahmen"] += netto
        else:
            ausgaben += -netto
            eintrag["ausgaben"] += -netto
        eintrag["ueberschuss"] += netto
    je_kategorie = sorted(kat.values(),
                          key=lambda e: (not e["steuer_relevant"], e["kategorie_name"]))
    return {"jahr": jahr, "einnahmen": einnahmen, "ausgaben": ausgaben,
            "ueberschuss": einnahmen - ausgaben, "nur_steuer": nur_steuer,
            "je_kategorie": je_kategorie}


def spending_insights(bewegungen: Iterable[dict], heute: str,
                      budget_ueberzogen: Optional[list[dict]] = None,
                      projektion_marken: Optional[list[dict]] = None) -> list[dict]:
    """Deterministische Ausgaben-Hinweise (App-Wächter-KI visualisiert, P3):
    Budget-Überzug, Liquiditäts-Warnung, Kategorie-ANOMALIE (laufender Monat
    deutlich über dem Schnitt der drei Vormonate), Sparquote, größte Ausgabe.
    Rein rechnerisch (kein Modell, keine Cloud); jeder Hinweis ``{art, schwere,
    text}`` mit schwere info|warn|bad. Sortiert: bad → warn → info."""
    bewegungen = list(bewegungen)
    h = date.fromisoformat(heute[:10])
    out: list[dict] = []
    e = lambda c: format_betrag(c, "EUR")

    for b in (budget_ueberzogen or []):
        name = b.get("kategorie_name", "?")
        out.append({"art": "budget", "schwere": "warn",
                    "text": f"Budget {name} überzogen ({b.get('prozent', 0)} %)."})
    for m in (projektion_marken or []):
        if m.get("negativ"):
            out.append({"art": "liquiditaet", "schwere": "bad",
                        "text": f"Liquidität in {m.get('tage')} Tagen negativ "
                                f"({e(m.get('saldo', 0))} €) — Fixposten prüfen."})
            break

    # Kategorie-Anomalie: laufender Monat vs. Monatsschnitt der drei Vormonate.
    monat = h.isoformat()[:7]
    akt = {x["kategorie_id"]: x for x in
           cashflow(bewegungen, von=f"{monat}-01", bis=f"{monat}-31")["je_kategorie"]
           if x["ausgaben"] > 0 and x["kategorie_id"]}
    monat_start = h.replace(day=1)
    vor_bis = (monat_start - timedelta(days=1)).isoformat()
    vor_von = (monat_start - timedelta(days=92)).isoformat()
    vor = {x["kategorie_id"]: x["ausgaben"] for x in
           cashflow(bewegungen, von=vor_von, bis=vor_bis)["je_kategorie"]
           if x["ausgaben"] > 0 and x["kategorie_id"]}
    for kid, x in sorted(akt.items(), key=lambda kv: -kv[1]["ausgaben"]):
        schnitt = round(vor.get(kid, 0) / 3)
        if schnitt > 0 and x["ausgaben"] > schnitt * 1.5 and (x["ausgaben"] - schnitt) >= 5000:
            out.append({"art": "anomalie", "schwere": "warn",
                        "text": f"{x['kategorie_name']} diesen Monat ungewöhnlich hoch: "
                                f"{e(x['ausgaben'])} € (Schnitt ~{e(schnitt)} €)."})

    cf30 = cashflow(bewegungen, von=(h - timedelta(days=30)).isoformat(), bis=h.isoformat())
    if cf30["einnahmen"] > 0:
        q = round(cf30["saldo"] * 100 / cf30["einnahmen"])
        if q < 0:
            out.append({"art": "sparquote", "schwere": "warn",
                        "text": f"Sparquote (30T) negativ ({q} %) — mehr ausgegeben als eingenommen."})
        elif q < 10:
            out.append({"art": "sparquote", "schwere": "info",
                        "text": f"Sparquote (30T) niedrig ({q} %)."})
    top = [x for x in cf30["je_kategorie"] if x["ausgaben"] > 0]
    if top:
        out.append({"art": "top", "schwere": "info",
                    "text": f"Größte Ausgabe (30T): {top[0]['kategorie_name']} "
                            f"{e(top[0]['ausgaben'])} €."})
    if not out:
        out.append({"art": "ok", "schwere": "info",
                    "text": "Keine Auffälligkeiten — alles im grünen Bereich."})
    rang = {"bad": 0, "warn": 1, "info": 2}
    out.sort(key=lambda i: rang.get(i["schwere"], 3))
    return out
