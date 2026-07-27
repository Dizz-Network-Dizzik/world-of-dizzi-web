"""test_chronist.py — der Chronist-Tick (Vertrag §4 / Test-Katalog §7).

Deckt: Übernahme + Rückstempeln · alle drei Schließregel-Trigger + nie-leer · Uhr-Rücksprung
(BZ-C-11) · Crash-Idempotenz · Fork-Stopp (C-16) · 0-Zeilen-Stempel legal (BZ-C-7) · torn-write-
Recovery · Instanz-Lock zweiter Tick / alte Lock-Datei (C-14/BZ-C-4) · Rückstand · flush_und_warte.

Konten-agnostisch, tmp-Pfade injiziert (§4.5a). Keine echten Daten-Verzeichnisse.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from appkit import chronik as C
from appkit import chronik_pruef as P
from appkit.chronist import Chronist, ChronistBesetzt, Quelle, _InstanzLock

UHR_FIX = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _kontext_reset():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _setup(tmp_path):
    """Frisches chronik-Verzeichnis + money-DB (nur Outbox). Kontext auf das Test-cdir (C-15-Pfeffer)."""
    cdir = tmp_path / "chronik"
    mdb = tmp_path / "money.sqlite"
    conn = sqlite3.connect(mdb)
    conn.executescript(C.AUSGANG_SCHEMA)
    conn.commit()
    conn.close()
    C.konfiguriere(cdir)
    return cdir, mdb


def _buchung(bid, betrag="1000", datum="2026-07-01"):
    return {"buchung_id": bid, "datum": datum, "quelle": "manuell",
            "postings": [{"konto_id": "1200", "betrag_minor": betrag},
                         {"konto_id": "8400", "betrag_minor": "-" + betrag.lstrip("-")}]}


def _schreibe(mdb, art="money.buchung", nutzlast=None, subjekt="u:" + "a" * 36):
    conn = sqlite3.connect(mdb)
    C.schreibe(conn, art=art, nutzlast=nutzlast, subjekt=subjekt)
    conn.commit()
    conn.close()


def _chronist(cdir, mdb, **kw):
    return Chronist(cdir, [Quelle("money", str(mdb))], **kw)


def _seg_zeilen(cdir):
    aus = {}
    for p in sorted((cdir / "segmente").iterdir()):
        aus[p.name] = [line for line in p.read_text("utf-8").splitlines() if line.strip()]
    return aus


def _status(cdir):
    return json.loads((cdir / "status.json").read_text("utf-8"))


# ── Übernahme + Prüfung ──────────────────────────────────────────────────────

def test_uebernahme_und_pruefe_gruen(tmp_path):
    cdir, mdb = _setup(tmp_path)
    for b in ("b1", "b2", "b3"):
        _schreibe(mdb, nutzlast=_buchung(b))
    _chronist(cdir, mdb, epoche_max=4).tick(flush=True)

    offen = sqlite3.connect(mdb).execute(
        "SELECT COUNT(*) FROM chronik_ausgang WHERE epoche IS NULL").fetchone()[0]
    assert offen == 0
    P.pruefe(cdir)                                   # wirft bei Bruch
    st = _status(cdir)
    assert st["last_n"] == 4                          # Genesis + 3 Buchungen
    assert st["rueckstand"]["offen"] == 0
    assert st["fork_verdacht"] is None


def test_genesis_ist_erste_zeile(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    _chronist(cdir, mdb).tick(flush=True)
    erste = json.loads(_seg_zeilen(cdir)["E00000001.dzc"][0])
    assert erste["n"] == 1 and erste["app"] == "chronik" and erste["art"] == "chronik.genesis"
    assert erste["prev"] == "sha256:" + "0" * 64


# ── Schließregeln (C-6): Anzahl · Zeit · Flush · nie-leer ────────────────────

def test_schliessregel_anzahl_rollt_und_nie_leer(tmp_path):
    cdir, mdb = _setup(tmp_path)
    for k in range(5):
        _schreibe(mdb, nutzlast=_buchung(f"b{k}"))
    # epoche_max=2 ⇒ [genesis,b0][b1,b2][b3,b4]
    ch = _chronist(cdir, mdb, epoche_max=2, uhr=lambda: UHR_FIX)
    siegel = ch.tick(flush=True)
    zeilen = _seg_zeilen(cdir)
    assert list(zeilen) == ["E00000001.dzc", "E00000002.dzc", "E00000003.dzc"]
    assert all(1 <= len(v) <= 2 for v in zeilen.values())          # nie-leer, Cap gehalten
    assert all(len(v) >= 1 for v in zeilen.values())
    assert len(siegel) == 3
    P.pruefe(cdir)


def test_schliessregel_zeit(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    # Uhr weit nach dem created_at ⇒ ältestes unversiegelt > 60 s ⇒ Zeit-Trigger, OHNE flush
    zukunft = lambda: datetime(2027, 1, 1, tzinfo=timezone.utc)
    siegel = _chronist(cdir, mdb, uhr=zukunft).tick(flush=False)
    assert len(siegel) == 1
    assert _status(cdir)["offene_epoche"] is None
    P.pruefe(cdir)


def test_schliessregel_flush_vs_offen(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    # Uhr == jetzt (Alter ~0 < 60 s) ⇒ ohne flush KEIN Siegel, Epoche bleibt offen
    ch = _chronist(cdir, mdb, uhr=lambda: datetime.now(timezone.utc))
    assert ch.tick(flush=False) == []
    assert _status(cdir)["offene_epoche"] == 1
    # flush ⇒ jetzt wird gesiegelt
    _schreibe(mdb, nutzlast=_buchung("b2"))
    assert len(ch.tick(flush=True)) == 1
    assert _status(cdir)["offene_epoche"] is None
    P.pruefe(cdir)


# ── Uhr-Rücksprung / Zukunfts-ts (BZ-C-11) ──────────────────────────────────

def test_zukunfts_ts_sofort_faellig_und_gelb(tmp_path):
    cdir, mdb = _setup(tmp_path)
    # Outbox-Zeile mit Zukunfts-created_at direkt einfügen (Uhr des Chronisten liegt davor)
    nutz = _buchung("b1")
    ks = C.kanon(nutz)
    conn = sqlite3.connect(mdb)
    conn.execute("INSERT INTO chronik_ausgang (art,nutzlast,nutzlast_hash,entscheid_id,subjekt,created_at) "
                 "VALUES (?,?,?,?,?,?)",
                 ("money.buchung", ks, C._sha256_hex(ks), "", "u:" + "a" * 36, "2099-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()
    siegel = _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=False)
    assert len(siegel) == 1                          # Zukunfts-ts ⇒ Alter=∞ ⇒ sofort fällig
    assert _status(cdir)["uhr_anomalie"] is True     # GELB-Merker
    P.pruefe(cdir)


# ── Crash-Idempotenz + 0-Zeilen-Stempel (C-5 / BZ-C-7) ──────────────────────

def test_crash_vor_stempel_kein_doppel_append(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    _schreibe(mdb, nutzlast=_buchung("b2"))
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    vorher = _seg_zeilen(cdir)
    # Simuliere: Zeile i=2 wurde angehängt+fsync't, aber der Stempel ging verloren
    conn = sqlite3.connect(mdb)
    conn.execute("UPDATE chronik_ausgang SET epoche=NULL WHERE i=2")
    conn.commit()
    conn.close()
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    nachher = _seg_zeilen(cdir)
    assert nachher == vorher                          # KEIN neuer Append (nur nachgestempelt)
    offen = sqlite3.connect(mdb).execute(
        "SELECT COUNT(*) FROM chronik_ausgang WHERE epoche IS NULL").fetchone()[0]
    assert offen == 0
    P.pruefe(cdir)


def test_null_zeilen_stempel_ist_legal(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    ch = _chronist(cdir, mdb, uhr=lambda: UHR_FIX)
    ch.tick(flush=True)
    # Stempel-Batch auf eine nicht existierende/gelöschte i ⇒ 0 Treffer, KEIN Fehler (BZ-C-7)
    conn = sqlite3.connect(mdb)
    ch._stempel_batch(conn, [(1, 99999)])
    conn.close()
    P.pruefe(cdir)


# ── Fork-Schutz (C-16) + Rückstand ──────────────────────────────────────────

def test_fork_stopp_statt_stempel(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    _schreibe(mdb, nutzlast=_buchung("b2"))
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    vorher = _seg_zeilen(cdir)
    # Restore-Fork: Outbox-Zeile i=2 bekommt anderen Inhalt (anderer nutzlast_hash), epoche zurück auf NULL
    anders = C.kanon(_buchung("b2", betrag="7777"))
    conn = sqlite3.connect(mdb)
    conn.execute("UPDATE chronik_ausgang SET epoche=NULL, nutzlast=?, nutzlast_hash=?, created_at=? WHERE i=2",
                 (anders, C._sha256_hex(anders), "2020-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    alarme = []
    ch = _chronist(cdir, mdb, uhr=lambda: UHR_FIX, rueckstand_alarm_s=0.0,
                   event_hook=lambda s, t, d: alarme.append((s, t, d)))
    ch.tick(flush=True)

    st = _status(cdir)
    assert st["fork_verdacht"] is not None
    assert st["fork_verdacht"]["app"] == "money" and st["fork_verdacht"]["i"] == 2
    assert _seg_zeilen(cdir) == vorher               # KEIN Fork-Append
    offen = sqlite3.connect(mdb).execute(
        "SELECT COUNT(*) FROM chronik_ausgang WHERE epoche IS NULL").fetchone()[0]
    assert offen == 1                                # der Fork-Eintrag blieb ungestempelt
    assert st["rueckstand"]["offen"] == 1 and st["rueckstand"]["alarm"] is True
    schweren = {a[0] for a in alarme}
    assert "kritisch" in schweren and "warn" in schweren    # Fork + Rückstand gemeldet
    P.pruefe(cdir)                                    # die Kette selbst bleibt intakt


def test_rueckstand_null_nach_normalem_tick(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    r = _status(cdir)["rueckstand"]
    assert r["offen"] == 0 and r["alarm"] is False


# ── torn-write-Recovery ─────────────────────────────────────────────────────

def test_torn_write_wird_gekuerzt(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    # Offene (unversiegelte) Epoche: aktuelle Uhr ⇒ kein Zeit-Trigger
    ch = _chronist(cdir, mdb, uhr=lambda: datetime.now(timezone.utc))
    ch.tick(flush=False)
    assert _status(cdir)["offene_epoche"] == 1
    # torn write: unvollständige JSON-Zeile ans offene Segment anhängen
    seg = cdir / "segmente" / "E00000001.dzc"
    with open(seg, "a", encoding="utf-8") as f:
        f.write('{"n":3,"app":"money","i')           # abgeschnitten
    _schreibe(mdb, nutzlast=_buchung("b2"))
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    assert _status(cdir)["recovery"]["torn_writes"] == 1
    P.pruefe(cdir)


# ── Instanz-Lock (C-14 / BZ-C-4) ────────────────────────────────────────────

def test_zweiter_tick_blockiert_bei_gehaltener_sperre(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    (cdir).mkdir(parents=True, exist_ok=True)
    fremd = _InstanzLock(cdir / "chronist.lock").nimm()       # jemand hält die OS-Sperre
    try:
        with pytest.raises(ChronistBesetzt):
            _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    finally:
        fremd.gib_frei()
    # Nach Freigabe läuft der Tick normal
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)
    P.pruefe(cdir)


def test_alte_lock_datei_ohne_sperre_blockiert_nicht(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    (cdir).mkdir(parents=True, exist_ok=True)
    # „alte" Lock-Datei mit Diagnose-Inhalt, aber NIEMAND hält die OS-Sperre
    (cdir / "chronist.lock").write_text("pid=99999 start=2020-01-01", "utf-8")
    _chronist(cdir, mdb, uhr=lambda: UHR_FIX).tick(flush=True)   # kein ChronistBesetzt
    P.pruefe(cdir)


# ── flush_und_warte ─────────────────────────────────────────────────────────

def test_flush_und_warte_liefert_verifiziertes_siegel(tmp_path):
    cdir, mdb = _setup(tmp_path)
    _schreibe(mdb, nutzlast=_buchung("b1"))
    ch = _chronist(cdir, mdb, uhr=lambda: datetime.now(timezone.utc))
    siegel = ch.flush_und_warte()
    assert siegel["quorum"] == 1 and siegel["zeugen"]
    # das Ereignis ist gestempelt und liegt in der versiegelten Epoche
    ep = sqlite3.connect(mdb).execute(
        "SELECT epoche FROM chronik_ausgang WHERE i=1").fetchone()[0]
    assert ep == siegel["epoche"]
    P.pruefe(cdir)


# ── CLI-Smoke ───────────────────────────────────────────────────────────────

def test_cli_tick(tmp_path):
    from appkit import chronist
    cdir, mdb = _setup(tmp_path)
    (cdir).mkdir(parents=True, exist_ok=True)
    (cdir / "quellen.json").write_text(json.dumps([{"app": "money", "db": str(mdb)}]), "utf-8")
    _schreibe(mdb, nutzlast=_buchung("b1"))
    rc = chronist._cli(["--tick", "--flush", "--dir", str(cdir)])
    assert rc == 0
    P.pruefe(cdir)
