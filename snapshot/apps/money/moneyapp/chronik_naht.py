"""Chronik-Naht (V-BIZZI-1, B1 Runde 3) — Dizz Money ↔ DzChronik.

Kapselt die B1-Verdrahtung (docs/80 §6), damit ``main.py`` schlank bleibt:
- **Schema-Konstanten** (`AUSGANG_SCHEMA` + `FESTSCHREIBUNGEN_SCHEMA`) für moneys ``extra_schema``
  (KEIN `_BASE_SCHEMA`-Eingriff, C-10).
- **Ereignis-Schreiber** (`schreibe_buchung/storno/umklassung/beleg/uebernahme`) mit den §3-Nutzlasten —
  INSERT ohne Commit auf der ÜBERGEBENEN offenen Verbindung (C-1). **Geld-Semantik heilig:** Beträge als
  Dezimal-String (C-2), Freitexte NUR als gepfefferte Feld-Hashes (C-15).
- **Festschreibungs-Wächter** (`pruefe_offen`/`ist_gesperrt`, §6.3) + Salden-/Beweisgrad-Helfer (§6.0/§6.3).
- **Chronist-Fabrik** (`baue_chronist`) für den In-Process-`flush_und_warte`.

Der Chronik-Kontext (Schlüssel + Pfeffer) wird lazy an moneys Datenwurzel gebunden (`setze_chronik_dir`),
damit Tests ihr tmp-Verzeichnis erben und die reale ``data\\chronik`` nie berühren.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from appkit import chronik
from appkit.chronist import Chronist, Quelle

# ── Schema (moneys extra_schema) ────────────────────────────────────────────
AUSGANG_SCHEMA = chronik.AUSGANG_SCHEMA

FESTSCHREIBUNGEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS festschreibungen (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  zeitraum      TEXT NOT NULL,          -- 'YYYY-MM'
  status        TEXT NOT NULL,          -- offen | versiegelt
  bis_i         INTEGER,
  salden_hash   TEXT,
  beweisgrad    TEXT,                   -- voll | db-stand (§6.0)
  siegel_epoche INTEGER,
  siegel_hash   TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  deleted_at    TEXT,
  UNIQUE (user_id, zeitraum)
);
CREATE INDEX IF NOT EXISTS idx_festschreibungen ON festschreibungen (user_id, zeitraum);
"""

# BZ-C-7 / §147 AO: diese Tabellen nimmt money von der DSGVO-Lösch-Kaskade AUS (Art. 17(3)(b) deckt es);
# das Buchungs-Gerippe bleibt pseudonym (subjekt-UUID ohne Auflösungstabelle).
BEWAHRE_BEI_LOESCHUNG = ("buchungen", "postings", "festschreibungen")


class ZeitraumGesperrt(Exception):
    """§6.3: der Zeitraum ist festgeschrieben (offen|versiegelt) — Schreibpfad muss 409 melden."""
    def __init__(self, zeitraum: str):
        super().__init__(zeitraum)
        self.zeitraum = zeitraum


# ── Chronik-Kontext (lazy an moneys Datenwurzel) ────────────────────────────
_CDIR: Path | None = None
_KONFIGURIERT_FUER: Path | None = None


def setze_chronik_dir(cdir: Path) -> None:
    """Bindet den Chronik-Kontext (Schlüssel/Pfeffer/Segmente) an ``cdir`` (moneys ``<root>/chronik``)."""
    global _CDIR
    _CDIR = Path(cdir)


def chronik_dir() -> Path:
    return _CDIR if _CDIR is not None else chronik.chronik_dir()


def _sicherstellen() -> None:
    """Konfiguriert den Chronik-Kontext lazy (erst beim ersten Schreiben ⇒ keine Schlüssel-Erzeugung
    für Money-Starts/Tests, die die Chronik nie berühren)."""
    global _KONFIGURIERT_FUER
    if _CDIR is not None and _KONFIGURIERT_FUER != _CDIR:
        chronik.konfiguriere(_CDIR)
        _KONFIGURIERT_FUER = _CDIR


def _subjekt(user_id: str) -> str:
    """BZ-C-10: eine **opake, stabile** Subjekt-Kennung — nie ein Login-/Anzeigename in der
    (unlöschbaren) Kette. Deterministisch aus der ``user_id`` abgeleitet ⇒ die Kette bleibt pseudonym
    (das Buchungs-Gerippe = subjekt-Token ohne Auflösungstabelle) und erfüllt die ``u:<hex>``-Regex
    unabhängig vom ``user_id``-Format (z. B. ``'dizzi'`` in der persönlichen Edition)."""
    return "u:" + hashlib.sha256(("dizz-money:" + str(user_id)).encode("utf-8")).hexdigest()[:32]


# ── Wächter (§6.3) ──────────────────────────────────────────────────────────
def zeitraum_von(datum: str) -> str:
    return (datum or "")[:7]


def pruefe_offen(conn, user_id: str, datum: str) -> None:
    """Blockt ``datum`` in einem festgeschriebenen Zeitraum (status offen|versiegelt, BZ-C-5) —
    IN derselben Schreib-Transaktion aufzurufen. Wirft ``ZeitraumGesperrt`` (⇒ 409)."""
    z = zeitraum_von(datum)
    row = conn.execute(
        "SELECT status FROM festschreibungen WHERE user_id=? AND zeitraum=? AND deleted_at IS NULL",
        (user_id, z)).fetchone()
    if row and row[0] in ("offen", "versiegelt"):
        raise ZeitraumGesperrt(z)


def ist_gesperrt(conn, user_id: str, datum: str) -> bool:
    """Nicht-werfende Variante (Batch-Pfade: sealed-Zeilen überspringen statt die ganze Aktion zu kippen)."""
    z = zeitraum_von(datum)
    return conn.execute(
        "SELECT 1 FROM festschreibungen WHERE user_id=? AND zeitraum=? "
        "AND status IN ('offen','versiegelt') AND deleted_at IS NULL", (user_id, z)).fetchone() is not None


# ── Ereignis-Schreiber (§3) — INSERT ohne Commit auf conn (C-1) ─────────────
def _postings(paare) -> list[dict]:
    """[(konto_id, betrag_minor:int)] → [{konto_id, betrag_minor: Dezimal-String}] (C-2)."""
    return [{"konto_id": k, "betrag_minor": str(int(b))} for k, b in paare]


def schreibe_buchung(conn, user_id: str, *, buchung_id: str, datum: str, quelle: str, postings,
                     bereich_id: str = "", kategorie_id: str | None = None,
                     notiz: str | None = None, gegenpartei: str | None = None,
                     verwendungszweck: str | None = None) -> None:
    _sicherstellen()
    nutz: dict = {"buchung_id": buchung_id, "datum": datum, "quelle": quelle,
                  "postings": _postings(postings)}
    if bereich_id:
        nutz["bereich_id"] = bereich_id
    if kategorie_id:
        nutz["kategorie_id"] = kategorie_id
    for feld, wert in (("notiz_hash", notiz), ("gegenpartei_hash", gegenpartei),
                       ("verwendungszweck_hash", verwendungszweck)):
        h = chronik.feld_hash(wert)          # leer/None ⇒ None ⇒ Feld entfällt (§3-Freitext-Regel)
        if h:
            nutz[feld] = h
    chronik.schreibe(conn, art="money.buchung", nutzlast=nutz, subjekt=_subjekt(user_id))


def schreibe_storno(conn, user_id: str, *, buchung_id: str, datum_storno: str, gegen_postings) -> None:
    """``gegen_postings`` = die Original-Postings der stornierten Buchung; sie werden INVERTIERT in die
    Nutzlast geschrieben (self-contained ⇒ Salden-Replay braucht die Original-Buchung nicht, BZ-C-1)."""
    _sicherstellen()
    nutz = {"buchung_id": buchung_id, "datum_storno": datum_storno,
            "postings": [{"konto_id": k, "betrag_minor": str(-int(b))} for k, b in gegen_postings]}
    chronik.schreibe(conn, art="money.storno", nutzlast=nutz, subjekt=_subjekt(user_id))


def schreibe_umklassung(conn, user_id: str, *, buchung_id: str, kategorie_id: str | None) -> None:
    _sicherstellen()
    chronik.schreibe(conn, art="money.umklassung",
                     nutzlast={"buchung_id": buchung_id, "kategorie_id": kategorie_id or ""},
                     subjekt=_subjekt(user_id))


def schreibe_beleg(conn, user_id: str, *, buchung_id: str, titel: str | None = None,
                   ref: str | None = None) -> None:
    """money.beleg: leere Hashes = Entfernung (§6.2). Titel/Ref-Hashes IMMER präsent (self-describing)."""
    _sicherstellen()
    nutz = {"buchung_id": buchung_id,
            "beleg_titel_hash": chronik.feld_hash(titel) or "",
            "beleg_ref_hash": chronik.feld_hash(ref) or ""}
    chronik.schreibe(conn, art="money.beleg", nutzlast=nutz, subjekt=_subjekt(user_id))


# ── Übernahme-Anschluss (§6.0) ──────────────────────────────────────────────
def uebernahme_noetig(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM chronik_ausgang WHERE art='money.uebernahme'").fetchone()[0] == 0


def _konto_salden(conn, *, zeitraum: str | None = None) -> list[dict]:
    """Netto-Salden je Konto aus den aktiven Postings; optional auf einen Buchungs-Zeitraum begrenzt.
    Nur Konten mit Bewegung (≠ 0), stabil sortiert — der Kanon-Anker."""
    if zeitraum is None:
        rows = conn.execute(
            "SELECT konto_id, SUM(betrag) FROM postings WHERE deleted_at IS NULL "
            "GROUP BY konto_id HAVING SUM(betrag) <> 0 ORDER BY konto_id").fetchall()
    else:
        rows = conn.execute(
            "SELECT p.konto_id, SUM(p.betrag) FROM postings p JOIN buchungen b ON b.id=p.buchung_id "
            "WHERE p.deleted_at IS NULL AND b.deleted_at IS NULL AND substr(b.datum,1,7)=? "
            "GROUP BY p.konto_id HAVING SUM(p.betrag) <> 0 ORDER BY p.konto_id", (zeitraum,)).fetchall()
    return [{"konto_id": r[0], "saldo_minor": str(int(r[1]))} for r in rows]


def schreibe_uebernahme(conn, *, stichtag: str) -> None:
    """§6.0: EIN ``money.uebernahme``-Anker (Ist-Salden aller Konten + letzte_buchung_rowid). Idempotent —
    tut nichts, wenn bereits ein Anker existiert. subjekt=system (technischer Anschluss, kein Nutzer-Akt)."""
    _sicherstellen()
    if not uebernahme_noetig(conn):
        return
    max_rowid = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM buchungen").fetchone()[0]
    nutz = {"stichtag": stichtag, "letzte_buchung_rowid": int(max_rowid), "konten": _konto_salden(conn)}
    chronik.schreibe(conn, art="money.uebernahme", nutzlast=nutz, subjekt="system")


def lies_stichtag(conn) -> str | None:
    row = conn.execute(
        "SELECT nutzlast FROM chronik_ausgang WHERE art='money.uebernahme' ORDER BY i LIMIT 1").fetchone()
    return json.loads(row[0]).get("stichtag") if row else None


# ── Festschreibung (§6.3) ───────────────────────────────────────────────────
def salden_hash_des_zeitraums(conn, zeitraum: str) -> tuple[str, list[dict]]:
    salden = _konto_salden(conn, zeitraum=zeitraum)
    return chronik._sha256_hex(chronik.kanon(salden)), salden


def schreibe_festschreibung(conn, user_id: str, *, zeitraum: str, bis_i: int,
                            salden_hash: str, beweisgrad: str) -> None:
    _sicherstellen()
    chronik.schreibe(conn, art="money.festschreibung", subjekt=_subjekt(user_id),
                     nutzlast={"zeitraum": zeitraum, "bis_i": int(bis_i),
                               "salden_hash": salden_hash, "beweisgrad": beweisgrad})


def beweisgrad_fuer(zeitraum: str, stichtag: str | None) -> str:
    """§6.0: ``voll``, wenn der Zeitraum vollständig NACH dem Übernahme-Stichtag liegt; sonst ``db-stand``.
    Ohne Anker (Erst-Anschluss auf leerer/voll-verketteter DB) deckt die Kette alles ⇒ ``voll``."""
    if not stichtag:
        return "voll"
    return "voll" if (zeitraum + "-01") > stichtag[:10] else "db-stand"


def outbox_spitze(conn) -> int:
    return conn.execute("SELECT COALESCE(MAX(i), 0) FROM chronik_ausgang").fetchone()[0]


def offene_vormonate_mit_buchungen(conn, user_id: str, zeitraum: str) -> list[str]:
    """Lücken-Ehrlichkeit (§6.3 Wächter, kein Zwang): frühere Monate mit Buchungen, die weder
    festgeschrieben noch leer sind."""
    monate = [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(datum,1,7) AS m FROM buchungen WHERE user_id=? AND deleted_at IS NULL "
        "AND substr(datum,1,7) < ? ORDER BY m", (user_id, zeitraum)).fetchall()]
    fest = {r[0] for r in conn.execute(
        "SELECT zeitraum FROM festschreibungen WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()}
    return [m for m in monate if m not in fest]


# ── Chronist-Fabrik (In-Process-flush) ──────────────────────────────────────
def baue_chronist(money_db_path, *, event_hook=None) -> Chronist:
    _sicherstellen()
    return Chronist(chronik_dir(), [Quelle("money", str(money_db_path))], event_hook=event_hook)


# ── Status (/api/chronik/status) ────────────────────────────────────────────
def chronik_status(conn) -> dict:
    """Rückstand · letzte Epoche/Siegel-Zeit · Chronist-Zustand · fork_verdacht (§6.3-UI)."""
    cdir = chronik_dir()
    sp = cdir / "status.json"
    st = json.loads(sp.read_text("utf-8")) if sp.is_file() else {}
    offen, aeltestes = conn.execute(
        "SELECT COUNT(*), MIN(created_at) FROM chronik_ausgang WHERE epoche IS NULL").fetchone()
    letzte_siegel_zeit = None
    sd = cdir / "siegel"
    if sd.is_dir():
        siegel = sorted(p for p in sd.iterdir() if p.name.endswith(".json"))
        if siegel:
            letzte_siegel_zeit = json.loads(siegel[-1].read_text("utf-8")).get("zeit")
    return {
        "chronist_gelaufen": bool(st),
        "letzter_tick": st.get("letzter_tick"),
        "letzte_epoche": st.get("letzte_epoche"),
        "letzte_siegel_zeit": letzte_siegel_zeit,
        "rueckstand": offen or 0,
        "aeltestes_offen": aeltestes,
        "fork_verdacht": st.get("fork_verdacht"),
        "uhr_anomalie": st.get("uhr_anomalie", False),
    }
