"""Trading-Steuer-Engine (V14, docs/26 §13) — rechtliche Auswertung von Krypto-
Trading-Gewinnen nach deutschem Recht (Stand 2025/2026).

⚠️ KEINE Steuerberatung. Ein Schätz- und Dokumentations-Werkzeug: es bildet die
maßgeblichen Mechaniken sauber ab, damit der Nutzer jederzeit weiß, ab wann was zu
versteuern ist und es dem Finanzamt nachvollziehbar darlegen kann. Die endgültige
Festsetzung macht das Finanzamt / der Steuerberater.

Zwei Regime (Nutzer-Entscheid 17.06.):
- **FUTURES / Perpetuals** (§ 20 Abs. 2 EStG, Termingeschäft — was der Trading-Bot
  auf Bitget handelt): pauschale Abgeltungsteuer, **KEINE** Haltefrist, Sparer-
  Pauschbetrag (Freibetrag) 1.000 €, Verluste seit JStG 2024 voll verrechenbar,
  ausländische Börse ⇒ keine automatische Einbehaltung → **Anlage KAP** (Selbsterklärung).
- **SPOT** (§ 23 EStG, privates Veräußerungsgeschäft): Gewinn nach **1 Jahr** Haltefrist
  **steuerfrei**; innerhalb der Frist Freigrenze 1.000 € (**alles-oder-nichts**),
  Versteuerung mit dem **persönlichen** Einkommensteuersatz, FIFO → **Anlage SO**.

Abgeltungsteuer mit Kirchensteuer (§ 32d Abs. 1 Satz 4 EStG): ``AbgSt = e / (4 + k)``
(k = Kirchensteuersatz als Dezimal; k=0,09 ⇒ 24,45 %, k=0 ⇒ 25 %); Soli 5,5 % auf die
AbgSt; Kirchensteuer k × AbgSt.

Alle Geldbeträge in **Minor-Units (Euro-Cent, int)** — konsistent mit dem Ledger.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

# Rechtliche Konstanten (Stand 2025/2026) — zentral, leicht pflegbar.
SPARER_PAUSCHBETRAG_CENT = 100_000   # 1.000,00 € Freibetrag (§ 20), Single
FREIGRENZE_SPOT_CENT = 100_000       # 1.000,00 € Freigrenze (§ 23, ab 2024)
SOLI_SATZ = 0.055                    # 5,5 % Solidaritätszuschlag auf die Abgeltungsteuer
HALTEFRIST_TAGE = 365               # § 23: 1 Jahr; Verkauf am 365. Tag noch steuerpflichtig
REGIME = ("futures", "spot")


def abgeltungsteuer(bemessung_cent: int, kirchensteuer_satz: float = 0.0) -> dict[str, int]:
    """§ 32d Abs. 1 EStG: ``AbgSt = e / (4 + k)`` (ohne anrechenbare Auslandssteuer),
    Soli 5,5 % darauf, Kirchensteuer ``k × AbgSt``. ``kirchensteuer_satz`` z. B. 0.09 /
    0.08 / 0.0. Negative/0-Bemessung ⇒ alles 0. Liefert gerundete Cent-Beträge."""
    e = max(0, int(bemessung_cent))
    k = max(0.0, float(kirchensteuer_satz))
    abgst = e / (4 + k)                 # k=0 ⇒ 0.25*e
    # Einzelposten runden und das Gesamt als SUMME der gerundeten Posten bilden, damit
    # eine vorgelegte Aufstellung konsistent ist (Posten summieren sich exakt zum Gesamt).
    abgst_r = round(abgst)
    soli_r = round(abgst * SOLI_SATZ)
    kist_r = round(abgst * k)
    return {
        "bemessung": e,
        "abgeltungsteuer": abgst_r,
        "soli": soli_r,
        "kirchensteuer": kist_r,
        "gesamt": abgst_r + soli_r + kist_r,
    }


def steuer_futures(netto_gewinn_cent: int, *,
                   pauschbetrag_rest_cent: int = SPARER_PAUSCHBETRAG_CENT,
                   kirchensteuer_satz: float = 0.0) -> dict[str, Any]:
    """§ 20: steuerpflichtig = ``max(0, netto − Sparer-Pauschbetrag)`` (Freibetrag!).
    Ein Jahres-**Verlust** (netto < 0) erzeugt keine Steuer, aber einen Verlustvortrag
    (mit künftigen Kapitalerträgen verrechenbar). ``pauschbetrag_rest_cent`` = der für
    Trading noch FREIE Teil des Pauschbetrags (er gilt für ALLE Kapitalerträge zusammen)."""
    netto = int(netto_gewinn_cent)
    rest = max(0, int(pauschbetrag_rest_cent))
    if netto <= 0:
        st = abgeltungsteuer(0, kirchensteuer_satz)
        return {"regime": "futures", "netto": netto, "freibetrag_genutzt": 0,
                "steuerpflichtig": 0, "verlustvortrag": -netto, "ueber_schwelle": False,
                **{k: v for k, v in st.items() if k != "bemessung"}}
    frei = min(netto, rest)
    steuerpflichtig = netto - frei
    st = abgeltungsteuer(steuerpflichtig, kirchensteuer_satz)
    return {"regime": "futures", "netto": netto, "freibetrag_genutzt": frei,
            "steuerpflichtig": steuerpflichtig, "verlustvortrag": 0,
            "ueber_schwelle": steuerpflichtig > 0,
            **{k: v for k, v in st.items() if k != "bemessung"}}


def steuer_spot(netto_frist_gewinn_cent: int, *,
                freigrenze_rest_cent: int = FREIGRENZE_SPOT_CENT,
                persoenlicher_satz: float = 0.42) -> dict[str, Any]:
    """§ 23: nur Gewinne aus Verkäufen INNERHALB der Haltefrist zählen (Aufruf-Seite
    filtert via :func:`spot_steuerpflichtig`). **Freigrenze 1.000 € = alles-oder-nichts**:
    § 23 Abs. 3 S. 5 EStG ⇒ steuerfrei nur, wenn der Gewinn **weniger als** 1.000 € ist
    (``netto < Freigrenze``); bei **genau** 1.000 € oder mehr ist der GESAMTE Gewinn
    steuerpflichtig und wird mit dem **persönlichen** Steuersatz versteuert. Ein
    Frist-Verlust (netto < 0) ist nur mit § 23-Gewinnen verrechenbar (Vortrag)."""
    netto = int(netto_frist_gewinn_cent)
    rest = max(0, int(freigrenze_rest_cent))
    satz = max(0.0, float(persoenlicher_satz))
    if netto <= 0:
        return {"regime": "spot", "netto": netto, "steuerpflichtig": 0,
                "unter_freigrenze": True, "verlustvortrag": -netto if netto < 0 else 0,
                "steuer_gesamt": 0, "ueber_schwelle": False}
    if netto < rest:                                    # „weniger als" die Freigrenze ⇒ steuerfrei
        return {"regime": "spot", "netto": netto, "steuerpflichtig": 0,
                "unter_freigrenze": True, "verlustvortrag": 0,
                "steuer_gesamt": 0, "ueber_schwelle": False}
    steuer = round(netto * satz)                        # GESAMTER Gewinn steuerpflichtig
    return {"regime": "spot", "netto": netto, "steuerpflichtig": netto,
            "unter_freigrenze": False, "verlustvortrag": 0,
            "steuer_gesamt": steuer, "ueber_schwelle": True}


def spot_steuerpflichtig(kauf_iso: str | None, verkauf_iso: str) -> bool:
    """§ 23-Haltefrist: steuerfrei nur, wenn der Verkauf **nach Ablauf eines Jahres**
    erfolgt — **kalendarisch** gerechnet (schaltjahr-sicher), nicht über 365 Tage:
    Grenze = Kauftag + 1 Jahr; ein Verkauf am Jahrestag selbst ist noch steuerpflichtig,
    erst der Tag danach ist steuerfrei. Ohne ``kauf_iso`` (unbekannt) wird **konservativ**
    als steuerpflichtig behandelt (kein stilles Steuerfrei-Annehmen)."""
    if not kauf_iso:
        return True
    try:
        k = date.fromisoformat(str(kauf_iso)[:10])
        v = date.fromisoformat(str(verkauf_iso)[:10])
    except (ValueError, TypeError):
        return True
    try:
        grenze = k.replace(year=k.year + 1)
    except ValueError:                       # 29.02. ⇒ 28.02. des Folgejahres
        grenze = k.replace(year=k.year + 1, day=28)
    return v <= grenze                       # am Grenztag noch steuerpflichtig, danach frei


def _jahr(iso: str) -> int | None:
    try:
        return date.fromisoformat(str(iso)[:10]).year
    except (ValueError, TypeError):
        return None


def jahres_auswertung(realisierungen: Iterable[dict[str, Any]], jahr: int, *,
                      pauschbetrag_rest_cent: int = SPARER_PAUSCHBETRAG_CENT,
                      freigrenze_rest_cent: int = FREIGRENZE_SPOT_CENT,
                      persoenlicher_satz: float = 0.42,
                      kirchensteuer_satz: float = 0.0) -> dict[str, Any]:
    """Aggregiert die Realisierungen eines Kalenderjahres und berechnet die geschätzte
    Steuer je Regime + die Schwellen-Vorwarnung. ``realisierungen`` = Dicts mit
    ``datum`` (ISO), ``regime`` (futures|spot), ``betrag_minor`` (+Gewinn/−Verlust in Cent),
    optional ``kauf_datum`` (ISO, für die § 23-Haltefrist). Liefert eine fürs Frontend
    + die Anlage KAP/SO taugliche Übersicht. Nur Schätzung — keine Steuerberatung."""
    fut_netto = 0
    spot_netto_steuerbar = 0          # nur Realisierungen innerhalb der Haltefrist
    spot_steuerfrei = 0               # Haltefrist erfüllt ⇒ steuerfrei (informativ)
    n_fut = n_spot = 0
    for r in realisierungen:
        if _jahr(r.get("datum", "")) != jahr:
            continue
        betrag = int(r.get("betrag_minor", 0) or 0)
        if (r.get("regime") or "futures") == "spot":
            n_spot += 1
            if spot_steuerpflichtig(r.get("kauf_datum"), r.get("datum", "")):
                spot_netto_steuerbar += betrag
            else:
                spot_steuerfrei += betrag
        else:
            n_fut += 1
            fut_netto += betrag

    fut = steuer_futures(fut_netto, pauschbetrag_rest_cent=pauschbetrag_rest_cent,
                         kirchensteuer_satz=kirchensteuer_satz)
    spot = steuer_spot(spot_netto_steuerbar, freigrenze_rest_cent=freigrenze_rest_cent,
                       persoenlicher_satz=persoenlicher_satz)
    spot["steuerfrei_haltefrist"] = spot_steuerfrei
    steuer_gesamt = fut["gesamt"] + spot["steuer_gesamt"]

    warnungen: list[str] = []
    if fut["ueber_schwelle"]:
        warnungen.append(
            "Futures-Gewinne über dem Sparer-Pauschbetrag (1.000 €) — der übersteigende "
            "Teil ist abgeltungsteuerpflichtig (Anlage KAP, ausländische Börse = Selbsterklärung).")
    elif fut_netto > 0:
        rest = max(0, pauschbetrag_rest_cent - fut_netto)
        warnungen.append(
            f"Futures-Gewinne noch im Pauschbetrag — bis zur Steuerpflicht sind es noch {rest/100:.2f} €.")
    if spot["ueber_schwelle"]:
        warnungen.append(
            "Spot-Gewinne (innerhalb Haltefrist) ÜBER der Freigrenze (1.000 €) — der "
            "GESAMTE Gewinn ist mit dem persönlichen Satz zu versteuern (Anlage SO).")
    elif spot_netto_steuerbar > 0:
        rest = max(0, freigrenze_rest_cent - spot_netto_steuerbar)
        warnungen.append(
            f"Spot-Gewinne (Frist) noch unter der Freigrenze — Puffer noch {rest/100:.2f} € "
            "(Achtung: Freigrenze = alles-oder-nichts).")

    return {
        "jahr": jahr,
        "futures": fut,
        "spot": spot,
        "steuer_gesamt": steuer_gesamt,
        "anzahl": {"futures": n_fut, "spot": n_spot},
        "parameter": {
            "pauschbetrag_rest_cent": pauschbetrag_rest_cent,
            "freigrenze_rest_cent": freigrenze_rest_cent,
            "persoenlicher_satz": persoenlicher_satz,
            "kirchensteuer_satz": kirchensteuer_satz,
        },
        "warnungen": warnungen,
        "hinweis": ("Schätzung nach deutschem Recht 2025/26 — keine Steuerberatung. "
                    "Futures = § 20 (Abgeltungsteuer, Anlage KAP), Spot = § 23 "
                    "(1-Jahr-Haltefrist, Freigrenze, Anlage SO)."),
    }


def kapital_stand(bewegungen: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Verlauf des Echtgeld-Trading-Kapitals aus den Bewegungen (``art`` ∈
    einlage|entnahme|bewertung, ``betrag_minor`` in Cent; ``bewertung`` = Snapshot des
    aktuellen Account-Werts). Liefert: investiert (Einlagen − Entnahmen), aktueller Wert
    (letzte Bewertung nach Datum), unrealisierter G/V (Wert − investiert)."""
    einlagen = entnahmen = 0
    letzte_bewertung = None
    letztes_datum = ""
    # Tiebreaker (datum, created_at): bei MEHREREN Bewertungen am selben Tag gewinnt
    # deterministisch die zuletzt ERFASSTE (höchstes created_at) — sonst hinge der
    # „aktuelle Wert" von der DB-/Iterations-Reihenfolge ab (Audit-Fund Runde 3).
    letzter_schluessel: tuple[str, str] = ("", "")
    for b in bewegungen:
        art = b.get("art")
        betrag = int(b.get("betrag_minor", 0) or 0)
        if art == "einlage":
            einlagen += betrag
        elif art == "entnahme":
            entnahmen += betrag
        elif art == "bewertung":
            schluessel = (str(b.get("datum", "")), str(b.get("created_at", "")))
            if schluessel >= letzter_schluessel:
                letzter_schluessel, letztes_datum, letzte_bewertung = (
                    schluessel, schluessel[0], betrag)
    investiert = einlagen - entnahmen
    out = {"einlagen": einlagen, "entnahmen": entnahmen, "investiert": investiert,
           "aktueller_wert": letzte_bewertung if letzte_bewertung is not None else investiert,
           "bewertet": letzte_bewertung is not None, "bewertungs_datum": letztes_datum}
    out["unrealisiert"] = out["aktueller_wert"] - investiert
    return out


def _eur(cent: int) -> str:
    """Cent → '1.234,56 €' (deutsche Schreibweise) für den Bericht."""
    s = f"{abs(int(cent)) / 100:,.2f}"            # 1,234.56 (US)
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")  # → 1.234,56 (DE)
    return ("-" if cent < 0 else "") + s + " €"


def _zelle(s: Any) -> str:
    """Freitext (z. B. Beschreibung) für eine Markdown-Tabellenzelle entschärfen:
    Pipes escapen + Zeilenumbrüche zu Leerzeichen, damit ein „A | B"- oder mehrzeiliger
    Text die Aufstellung nicht zerschießt (der Bericht geht ans Finanzamt)."""
    # Backslash ZUERST escapen (G5, 28.06.): sonst macht ein Eingabe-„\|" aus dem
    # escapeten Pipe ein „\\|" = escapeter Backslash + AKTIVER Pipe ⇒ Spalten-Injektion.
    return (str(s or "").replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ")
            .replace("\n", " ").strip() or "—")


def jahres_bericht_markdown(jahr: int, auswertung: dict[str, Any],
                            posten: list[dict[str, Any]],
                            stand: dict[str, Any] | None = None) -> str:
    """Vorzeigbarer Jahres-Bericht (Markdown) für die Trading-Steuer — gegliedert nach
    **Anlage KAP** (§ 20 Futures) und **Anlage SO** (§ 23 Spot), mit aufgelisteten
    Einzelposten, Summen und der geschätzten Steuer. ``posten`` = Realisierungen des
    Jahres (Dicts mit datum/regime/betrag_minor/beschreibung/kauf_datum). Schätzung —
    keine Steuerberatung; soll dem Finanzamt eine nachvollziehbare Aufstellung geben."""
    f = auswertung["futures"]; sp = auswertung["spot"]
    fut = [p for p in posten if (p.get("regime") or "futures") == "futures"]
    spo = [p for p in posten if (p.get("regime") or "futures") == "spot"]
    z: list[str] = [
        f"# Trading-Steuer — Aufstellung {jahr}",
        "_Schätzung nach deutschem Recht (Stand 2025/26) · KEINE Steuerberatung · "
        "Dizz Money. Maßgeblich sind realisierte Echtgeld-Gewinne._",
        "",
    ]
    if stand:
        z += ["## Eingesetztes Kapital",
              f"- Investiert (Einlagen − Entnahmen): **{_eur(stand['investiert'])}**",
              f"- Aktueller Wert: {_eur(stand['aktueller_wert'])}"
              + ("" if stand.get("bewertet") else " _(keine Bewertung erfasst)_"),
              f"- Unrealisiert (nicht steuerwirksam): {_eur(stand['unrealisiert'])}", ""]

    # § 20 — Futures/Perpetuals (Anlage KAP)
    z += ["## § 20 EStG — Futures/Perpetuals (Anlage KAP)",
          "_Termingeschäft: Abgeltungsteuer, keine Haltefrist, Verluste voll "
          "verrechenbar. Ausländische Börse ⇒ Selbsterklärung._", ""]
    if fut:
        z.append("| Datum | Beschreibung | Betrag |")
        z.append("|---|---|---|")
        for p in sorted(fut, key=lambda x: x.get("datum", "")):
            z.append(f"| {_zelle(p.get('datum',''))} | {_zelle(p.get('beschreibung'))} "
                     f"| {_eur(p.get('betrag_minor', 0))} |")
    else:
        z.append("_Keine Futures-Realisierungen erfasst._")
    z += ["",
          f"- Netto (Gewinne − Verluste): **{_eur(f['netto'])}**",
          f"- Sparer-Pauschbetrag genutzt: {_eur(f['freibetrag_genutzt'])}",
          f"- **Steuerpflichtig: {_eur(f['steuerpflichtig'])}**",
          f"- Abgeltungsteuer: {_eur(f['abgeltungsteuer'])} · Soli: {_eur(f['soli'])}"
          f" · Kirchensteuer: {_eur(f['kirchensteuer'])}",
          f"- **Steuer § 20 gesamt (geschätzt): {_eur(f['gesamt'])}**"]
    if f.get("verlustvortrag"):
        z.append(f"- Verlustvortrag ins Folgejahr: {_eur(f['verlustvortrag'])}")
    z.append("")

    # § 23 — Spot (Anlage SO)
    z += ["## § 23 EStG — Spot (Anlage SO)",
          "_Privates Veräußerungsgeschäft: nach 1 Jahr Haltefrist steuerfrei; innerhalb "
          "der Frist Freigrenze 1.000 € (**weniger als**, alles-oder-nichts), Versteuerung "
          "mit dem **persönlichen** Einkommensteuersatz. Hinweis: Solidaritätszuschlag und "
          "ggf. Kirchensteuer fallen auf die persönliche ESt **zusätzlich** an — sie sind im "
          "hier angesetzten Satz einzurechnen._", ""]
    if spo:
        z.append("| Datum | Kaufdatum | Haltefrist | Beschreibung | Betrag |")
        z.append("|---|---|---|---|---|")
        for p in sorted(spo, key=lambda x: x.get("datum", "")):
            stp = spot_steuerpflichtig(p.get("kauf_datum"), p.get("datum", ""))
            z.append(f"| {_zelle(p.get('datum',''))} | {_zelle(p.get('kauf_datum'))} "
                     f"| {'steuerpflichtig' if stp else 'steuerfrei (>1 J.)'} "
                     f"| {_zelle(p.get('beschreibung'))} | {_eur(p.get('betrag_minor', 0))} |")
    else:
        z.append("_Keine Spot-Realisierungen erfasst._")
    z += ["",
          f"- Netto innerhalb Haltefrist: **{_eur(sp['netto'])}**",
          f"- Steuerfrei (Haltefrist erfüllt): {_eur(sp.get('steuerfrei_haltefrist', 0))}",
          ("- Unter Freigrenze ⇒ **steuerfrei**" if sp["unter_freigrenze"]
           else f"- Über Freigrenze ⇒ **voll steuerpflichtig: {_eur(sp['steuerpflichtig'])}**"),
          f"- **Steuer § 23 gesamt (geschätzt): {_eur(sp['steuer_gesamt'])}**", ""]

    z += ["## Geschätzte Steuer gesamt",
          f"**{_eur(auswertung['steuer_gesamt'])}** ({jahr})", ""]
    if auswertung.get("warnungen"):
        z += ["## Hinweise"] + [f"- {w}" for w in auswertung["warnungen"]] + [""]
    z.append("_Erstellt mit Dizz Money. Schätzung ohne Gewähr — die verbindliche "
             "Festsetzung trifft das Finanzamt / der Steuerberater._")
    return "\n".join(z)
