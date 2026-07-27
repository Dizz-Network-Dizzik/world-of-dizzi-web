"""Kategorisierungs-Regeln — reine Matching-Logik + DB-Anwendung (Teil B).

Eine **Regel** ordnet einer Buchung anhand eines Text-Musters eine Kategorie zu
(z. B. Muster ``"rewe"`` im Feld ``gegenpartei`` → Kategorie „Lebensmittel").
Die App **lernt**: bestätigt der Nutzer eine Zuordnung, kann daraus eine Regel
entstehen/verstärkt werden (``treffer``-Zähler), sodass künftige gleichartige
Buchungen automatisch fallen.

Die Matching-Funktionen sind **rein** (kein DB-Zugriff) und damit voll
property-testbar; ``regeln_anwenden`` ist die einzige DB-gebundene Funktion und
ruft nur die reinen Helfer. Determinismus ist Pflicht: bei mehreren passenden
Regeln gewinnt **höchste Priorität**, dann **meiste Treffer**, dann **jüngste
Erstellung** — nie Zufall.
"""

from __future__ import annotations

from typing import Iterable, Optional

FELDER = ("gegenpartei", "verwendungszweck", "notiz", "beliebig")


def passt(muster: str, feld: str, felder: dict[str, str]) -> bool:
    """Trifft ``muster`` (case-insensitiver Teilstring) im gewählten ``feld``?
    ``feld='beliebig'`` prüft alle Textfelder. Leeres Muster trifft nie."""
    m = (muster or "").strip().lower()
    if not m:
        return False
    if feld == "beliebig":
        heuhaufen = " ".join(str(felder.get(k, "")) for k in
                             ("gegenpartei", "verwendungszweck", "notiz"))
    else:
        heuhaufen = str(felder.get(feld, ""))
    return m in heuhaufen.lower()


def _sortkey(regel: dict):
    # Höchste Priorität zuerst, dann meiste Treffer, dann jüngste (created_at desc).
    return (-int(regel.get("prioritaet", 100)),
            -int(regel.get("treffer", 0)),
            str(regel.get("created_at", "")))


def finde_regel(regeln: Iterable[dict], felder: dict[str, str]) -> Optional[dict]:
    """Erste passende Regel nach deterministischer Ordnung (s. Modul-Docstring)
    oder ``None``. Erwartet je Regel: ``muster``, ``feld``, ``kategorie_id`` und
    optional ``prioritaet``/``treffer``/``created_at``."""
    treffer = [r for r in regeln if passt(r.get("muster", ""), r.get("feld", "beliebig"), felder)]
    if not treffer:
        return None
    # bei mehreren: jüngste gewinnt → created_at absteigend, daher umgekehrt sortieren
    treffer.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    treffer.sort(key=lambda r: (-int(r.get("prioritaet", 100)), -int(r.get("treffer", 0))))
    return treffer[0]


def lern_muster(felder: dict[str, str]) -> tuple[str, str]:
    """Leitet aus einer bestätigten Buchung ein sinnvolles Lern-Muster ab:
    bevorzugt die Gegenpartei (stabilstes Signal), sonst den Verwendungszweck.
    Liefert ``(muster, feld)``; leeres Muster ⇒ nichts Lernbares."""
    gp = (felder.get("gegenpartei") or "").strip()
    if gp:
        return gp.lower(), "gegenpartei"
    vz = (felder.get("verwendungszweck") or "").strip()
    if vz:
        # nur die ersten markanten Wörter als Muster (kein ganzer Satz)
        kern = " ".join(vz.split()[:3]).lower()
        return kern, "verwendungszweck"
    return "", "beliebig"


# ----------------------------------------------------------- DB-Anwendung

def regeln_anwenden(db, user_id: str, nur_buchung_id: str | None = None) -> int:
    """Wendet alle aktiven Regeln auf noch UNKATEGORISIERTE Buchungen an und
    zählt die Treffer hoch. Liefert die Zahl neu zugeordneter Buchungen.

    ``nur_buchung_id`` beschränkt auf eine einzelne Buchung (für gezieltes
    Nachkategorisieren). Reine Lese-/Schreib-Mechanik; die Entscheidung trifft
    der reine ``finde_regel``-Kern."""
    conn = db.get_conn()
    regeln = [dict(r) for r in conn.execute(
        "SELECT id, muster, feld, kategorie_id, bereich_id, prioritaet, treffer, created_at "
        "FROM regeln WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()]
    if not regeln:
        return 0
    gueltige_kat = {r["id"] for r in conn.execute(
        "SELECT id FROM kategorien WHERE user_id=? AND deleted_at IS NULL",
        (user_id,)).fetchall()}
    gueltige_ber = {r["id"] for r in conn.execute(
        "SELECT id FROM bereiche WHERE user_id=? AND deleted_at IS NULL",
        (user_id,)).fetchall()}
    sql = ("SELECT id, datum, gegenpartei, verwendungszweck, notiz, bereich_id FROM buchungen "
           "WHERE user_id=? AND kategorie_id IS NULL AND deleted_at IS NULL")
    params: tuple = (user_id,)
    if nur_buchung_id:
        sql += " AND id=?"
        params = (user_id, nur_buchung_id)
    offene = conn.execute(sql, params).fetchall()

    from appkit.db import now_iso
    from . import chronik_naht          # V-BIZZI-1: auto-Kategorisierung = money.umklassung (BZ-C-2-Grep)
    geaendert = 0
    treffer_je_regel: dict[str, int] = {}
    for b in offene:
        felder = {"gegenpartei": b["gegenpartei"], "verwendungszweck": b["verwendungszweck"],
                  "notiz": b["notiz"]}
        regel = finde_regel(regeln, felder)
        if regel is None or regel["kategorie_id"] not in gueltige_kat:
            continue
        # §6.3: eine Regel fasst festgeschriebene Buchungen NICHT an (sie behalten „nicht zugeordnet").
        if chronik_naht.ist_gesperrt(conn, user_id, b["datum"]):
            continue
        # Hat die Regel einen (noch gültigen) Bereich UND die Buchung noch keinen,
        # ordnet der Treffer die Buchung auch diesem Bereich zu (nie eine bestehende
        # Zuordnung überschreiben — der Ledger bleibt unberührt, nur die Bereich-Achse).
        rber = (regel.get("bereich_id") or "")
        setze_bereich = bool(rber) and rber in gueltige_ber and not (b["bereich_id"] or "")
        if setze_bereich:
            conn.execute("UPDATE buchungen SET kategorie_id=?, bereich_id=?, updated_at=? WHERE id=?",
                         (regel["kategorie_id"], rber, now_iso(), b["id"]))
        else:
            conn.execute("UPDATE buchungen SET kategorie_id=?, updated_at=? WHERE id=?",
                         (regel["kategorie_id"], now_iso(), b["id"]))
        # money.umklassung in DERSELBEN Verbindung — der abschließende conn.commit() persistiert beides (C-1).
        chronik_naht.schreibe_umklassung(conn, user_id, buchung_id=b["id"], kategorie_id=regel["kategorie_id"])
        treffer_je_regel[regel["id"]] = treffer_je_regel.get(regel["id"], 0) + 1
        geaendert += 1
    for rid, n in treffer_je_regel.items():
        conn.execute("UPDATE regeln SET treffer=treffer+? WHERE id=?", (n, rid))
    if geaendert:
        conn.commit()
    return geaendert
