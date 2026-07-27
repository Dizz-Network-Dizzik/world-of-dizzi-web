"""DzChronist (V-BIZZI-1, B1 Runde 2) — der EINE Schreiber: Tick, Recovery, Siegel.

Der Chronist übernimmt die offenen Outbox-Zeilen (``chronik_ausgang``) aller Quellen in
append-only Segmente, verkettet + signiert sie (``chronik.py``-Bausteine), schließt fällige
Epochen und siegelt sie. Er läuft als **Tick** (``python -m appkit.chronist --tick``), nicht als
Daemon (§4.1), und hält genau EINE **OS-erzwungene Datei-Sperre** je Instanz (C-14/§4.4) — es gibt
keine Alters-Übernahme, keine PID-Heuristik.

Vertrag: ``docs/80_CHRONIK_VERTRAG.md`` §4 (Tick/Recovery/Lock/Siegel/flush_und_warte), gehärtet um
BZ-C-3 (Fork-Schutz C-16 + Restore-Verbund §4.6), BZ-C-4 (OS-Lock C-14), BZ-C-5 (flush nach Commit),
BZ-C-11 (Uhr-Anomalie). Reine appkit-Bibliothek: stdlib + ``chronik.py`` — kein App-Import.

Das ``status.json`` ist NUR Cache/Anzeige (Rückstand, letzte Epoche/Siegel, ``fork_verdacht``,
PID/Start als Diagnose) — die **Wahrheit sind immer die Segmente**; der Kopf wird bei Inkonsistenz
aus ihnen rekonstruiert. Der C-14-Assert lautet „eigene OS-Sperre wird gehalten", nie „Datei existiert".
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import chronik as C
from .db import default_db_path, now_iso
from .io_safe import atomic_write_text

# Schließregel-Defaults (C-6): 4096 Ereignisse ∨ ältestes-unversiegelt > 60 s ∨ Flush.
EPOCHE_MAX = 4096
SCHLIESS_ALTER_S = 60.0
RUECKSTAND_ALARM_S = 900.0     # > 15 min offener Rückstand ⇒ Alarm (§4.2 Schritt 5)


class ChronistBesetzt(Exception):
    """Die OS-Instanz-Sperre wird bereits gehalten (§4.4) — sauberer Abbruch, kein Fehler-Log."""


class ForkVerdacht(Exception):
    """C-16: an ``(app, i)`` steht im Segment ein anderer ``nutzlast_hash`` als in der Outbox —
    Restore-/Fork-Kollision. Der Chronist stoppt diese Quelle fail-loud (kein Stempeln)."""

    def __init__(self, app: str, i: int, segment_hash: str, outbox_hash: str):
        super().__init__(f"Fork-Verdacht {app}#{i}: Segment {segment_hash} ≠ Outbox {outbox_hash}")
        self.app, self.i = app, i
        self.segment_hash, self.outbox_hash = segment_hash, outbox_hash


@dataclass
class Quelle:
    """Eine Chronik-Quelle: App-Kennung + Pfad ihrer SQLite-DB mit ``chronik_ausgang``."""
    app: str
    db: str


@dataclass
class _Kopf:
    """Rekonstruierter Ketten-Kopf eines Ticks (aus Segmenten; status.json ist nur Cache)."""
    last_n: int = 0
    last_h: bytes = C.NULL_HASH
    letzte_epoche: int = 0
    letztes_siegel: str = C.GENESIS_PREV_SIEGEL
    per_app_i: dict[str, int] = field(default_factory=dict)
    # Offene (unversiegelte) Epoche — None, wenn die letzte Epoche versiegelt ist:
    offene_epoche: int | None = None
    offene_h: list[bytes] = field(default_factory=list)
    offene_von_n: int = 0
    offene_erste_ts: str = ""
    # Diagnose:
    torn_writes: int = 0
    uhr_anomalie: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Instanz-Lock (C-14 / §4.4) — OS-erzwungene exklusive Datei-Sperre
# ─────────────────────────────────────────────────────────────────────────────


class _InstanzLock:
    """Exklusive Datei-Sperre über ``chronist.lock`` — Windows ``msvcrt.locking`` / POSIX
    ``fcntl.flock``. Die Sperre lebt und stirbt mit dem Prozess (das OS gibt sie bei Prozess-Ende
    frei); **keine Alters-Übernahme**. ``gehalten()`` = „eigenes Handle offen + Sperre bestätigt"."""

    def __init__(self, pfad: Path):
        self.pfad = pfad
        self._fd: int | None = None

    def nimm(self, *, blockierend: bool = False, deadline_s: float = 0.0) -> "_InstanzLock":
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.pfad), os.O_RDWR | os.O_CREAT)
        ende = time.monotonic() + deadline_s
        while True:
            try:
                self._sperre(fd)
                self._fd = fd
                return self
            except OSError as e:
                if not blockierend or time.monotonic() >= ende:
                    os.close(fd)
                    raise ChronistBesetzt("Chronist läuft bereits (OS-Sperre gehalten)") from e
                time.sleep(0.05)

    @staticmethod
    def _sperre(fd: int) -> None:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def gehalten(self) -> bool:
        return self._fd is not None

    def gib_frei(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "_InstanzLock":
        return self

    def __exit__(self, *_exc) -> None:
        self.gib_frei()


# ─────────────────────────────────────────────────────────────────────────────
# Segment-Dateien (Wahrheit) — Lesen/Kürzen (Recovery)
# ─────────────────────────────────────────────────────────────────────────────

_SEG_RE = re.compile(r"^E(\d{8})\.dzc$")
_SIE_RE = re.compile(r"^S(\d{8})\.json$")


def _segment_pfade(cdir: Path) -> list[tuple[int, Path]]:
    seg = cdir / "segmente"
    treffer = []
    if seg.is_dir():
        for p in seg.iterdir():
            m = _SEG_RE.match(p.name)
            if m:
                treffer.append((int(m.group(1)), p))
    return sorted(treffer)


def _siegel_epochen(cdir: Path) -> list[int]:
    sie = cdir / "siegel"
    out = []
    if sie.is_dir():
        for p in sie.iterdir():
            m = _SIE_RE.match(p.name)
            if m:
                out.append(int(m.group(1)))
    return sorted(out)


# ─────────────────────────────────────────────────────────────────────────────
# Der Chronist
# ─────────────────────────────────────────────────────────────────────────────


class Chronist:
    """Der EINE Schreiber einer Instanz. Ein ``tick()`` = übernehmen → schließen → siegeln → enden.

    ``uhr`` (aware datetime) + ``quorum`` sind injizierbar (Tests/Editionen). ``event_hook`` bekommt
    Alarme ``(schwere, titel, detail)`` — best-effort; die durable Signal-Quelle ist ``status.json``.
    """

    def __init__(self, cdir: Path, quellen: list[Quelle], *,
                 quorum: int = 1,
                 uhr: Callable[[], datetime] | None = None,
                 event_hook: Callable[[str, str, dict], None] | None = None,
                 epoche_max: int = EPOCHE_MAX,
                 schliess_alter_s: float = SCHLIESS_ALTER_S,
                 rueckstand_alarm_s: float = RUECKSTAND_ALARM_S):
        self.cdir = Path(cdir)
        self.quellen = quellen
        self.quorum = quorum
        self._uhr = uhr or (lambda: datetime.now(timezone.utc))
        self.event_hook = event_hook
        self.epoche_max = epoche_max
        self.schliess_alter_s = schliess_alter_s
        self.rueckstand_alarm_s = rueckstand_alarm_s
        self.sk = C.konfiguriere(self.cdir)        # lädt/erzeugt Schlüssel + Pfeffer (C-12/C-15)
        self._lock = _InstanzLock(self.cdir / "chronist.lock")
        self._handles: dict[int, "os.PathLike | object"] = {}
        self._fork: dict | None = None

    # -- öffentlich ----------------------------------------------------------

    def tick(self, *, flush: bool = False, _lock_deadline_s: float = 0.0) -> list[dict]:
        """Ein Durchlauf unter dem Instanz-Lock. Gibt die in diesem Tick erzeugten Siegel zurück
        (chronologisch). ``flush=True`` schließt die offene Epoche am Ende unbedingt (Festschreibung).
        Wirft ``ChronistBesetzt``, wenn die OS-Sperre nicht frei ist (sauberer Abbruch)."""
        self._lock.nimm(blockierend=_lock_deadline_s > 0, deadline_s=_lock_deadline_s)
        try:
            return self._tick_unter_lock(flush=flush)
        finally:
            self._lock.gib_frei()

    def flush_und_warte(self, zeitraum_deadline_s: float = 10.0) -> dict:
        """Siegelpflichtiger In-Process-Flush (§4.3, BZ-C-5): schließt+siegelt alles Offene und liefert
        das **verifizierte Siegel der deckenden Epoche** (das den aktuellen ``last_n`` deckt). Wartet
        blockierend auf den Lock (falls ein Task-Tick läuft); **Timeout ⇒ Fehler, nie „ok"** (C-9).
        Aufruf-Reihenfolge: IMMER nach dem Commit der auslösenden ``db.transaktion()``."""
        self.tick(flush=True, _lock_deadline_s=max(zeitraum_deadline_s, 0.1))
        kopf = self._lies_kopf()
        if kopf.last_n <= 0:
            raise RuntimeError("flush_und_warte: keine Kette vorhanden — nichts zu siegeln (C-9)")
        epoche = self._epoche_von_n(kopf.last_n)
        if epoche is None:
            raise RuntimeError("flush_und_warte: letzte Zeile ist unversiegelt geblieben (C-9)")
        return self._lade_und_verifiziere_siegel(epoche)

    # -- Tick-Innenleben -----------------------------------------------------

    def _tick_unter_lock(self, *, flush: bool) -> list[dict]:
        assert self._lock.gehalten(), "C-14: Segment-Schreiben ohne gehaltene OS-Sperre (Programmierfehler)"
        self._fork = None
        kopf = self._lies_kopf()
        siegel_erzeugt: list[dict] = []
        try:
            for quelle in self.quellen:
                self._uebernimm(quelle, kopf, siegel_erzeugt)
            # End-of-Tick-Schließregel (Zeit ∨ Flush) auf der noch offenen Epoche:
            if kopf.offene_epoche is not None and (flush or self._faellig_zeit(kopf)):
                siegel_erzeugt.append(self._schliesse(kopf))
        finally:
            self._fsync_und_schliesse_handles()
        self._melde_rueckstand(kopf)
        self._schreibe_status(kopf)
        return siegel_erzeugt

    def _uebernimm(self, quelle: Quelle, kopf: _Kopf, siegel_erzeugt: list[dict]) -> None:
        conn = self._verbinde(quelle.db)
        try:
            rows = conn.execute(
                "SELECT i, art, nutzlast, nutzlast_hash, entscheid_id, subjekt, created_at "
                "FROM chronik_ausgang WHERE epoche IS NULL ORDER BY i").fetchall()
            if not rows:
                return
            self._ensure_genesis(kopf, siegel_erzeugt)
            zu_stempeln: list[tuple[int, int]] = []
            fork: ForkVerdacht | None = None
            for i, art, nutzlast, nutzlast_hash, entscheid_id, subjekt, created_at in rows:
                if i > kopf.per_app_i.get(quelle.app, 0):
                    ep = self._ziel_epoche(kopf, created_at, siegel_erzeugt)
                    self._append(kopf, ep, quelle.app, i, art, nutzlast, nutzlast_hash,
                                 entscheid_id, subjekt, created_at)
                    kopf.per_app_i[quelle.app] = i
                    zu_stempeln.append((ep, i))
                    continue
                # i ≤ letztes ⇒ (app,i) müsste bereits im Segment stehen (Crash-Waise oder Restore-Fork):
                fund = self._suche_zeile(quelle.app, i)
                if fund is None:
                    # defensiv: trotz per_app_i nicht auffindbar ⇒ als neu behandeln (nie still verlieren)
                    ep = self._ziel_epoche(kopf, created_at, siegel_erzeugt)
                    self._append(kopf, ep, quelle.app, i, art, nutzlast, nutzlast_hash,
                                 entscheid_id, subjekt, created_at)
                    zu_stempeln.append((ep, i))
                elif fund[1] == nutzlast_hash:
                    zu_stempeln.append((fund[0], i))          # C-5: identischer Hash ⇒ nachstempeln
                else:
                    fork = ForkVerdacht(quelle.app, i, fund[1], nutzlast_hash)  # C-16: FORK-Stopp
                    break                                     # diese Quelle fail-loud stoppen
            # C-4: fsync der Segmente VOR dem Stempel-Batch (bereits gebaute Zeilen persistieren + stempeln)
            self._fsync_handles()
            self._stempel_batch(conn, zu_stempeln)
            if fork is not None:
                self._fork_stopp(fork)
        finally:
            conn.close()

    def _stempel_batch(self, conn: sqlite3.Connection, zu_stempeln: list[tuple[int, int]]) -> None:
        """Kurze eigene Txn: ``UPDATE chronik_ausgang SET epoche=? WHERE i=? AND epoche IS NULL``.
        Ein 0-Zeilen-Treffer (Outbox-Zeile zwischenzeitlich gelöscht, §3-Naht/BZ-C-7) ist **legal**."""
        if not zu_stempeln:
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            for ep, i in zu_stempeln:
                conn.execute("UPDATE chronik_ausgang SET epoche=? WHERE i=? AND epoche IS NULL", (ep, i))
        except BaseException:
            conn.rollback()
            raise
        conn.commit()

    def _ensure_genesis(self, kopf: _Kopf, siegel_erzeugt: list[dict]) -> None:
        """Schreibt die Genesis-Zeile (n=1) beim allerersten Anschluss (leere Kette, §2.3)."""
        if kopf.last_n != 0:
            return
        ts = now_iso()
        nutz = {"version": C.FORMAT_VERSION, "angelegt": ts, "stamm_kid": self.sk.stamm["kid"]}
        ep = self._ziel_epoche(kopf, ts, siegel_erzeugt)
        self._append_roh(kopf, ep, {
            "app": "chronik", "i": 0, "ts": ts, "art": "chronik.genesis", "subjekt": "system",
            "entscheid": "", "nutzlast_hash": C._sha256_hex(C.kanon(nutz)), "nutzlast": nutz})
        kopf.per_app_i["chronik"] = 0

    def _append(self, kopf: _Kopf, ep: int, app: str, i: int, art: str, nutzlast: str,
                nutzlast_hash: str, entscheid_id: str, subjekt: str, created_at: str) -> None:
        """Baut eine Segment-Zeile aus einer Outbox-Zeile (§2.3) und hängt sie an."""
        self._append_roh(kopf, ep, {
            "app": app, "i": i, "ts": created_at, "art": art, "subjekt": subjekt,
            "entscheid": entscheid_id, "nutzlast_hash": nutzlast_hash,
            "nutzlast": (json.loads(nutzlast) if nutzlast else "")})

    def _append_roh(self, kopf: _Kopf, ep: int, kern: dict) -> None:
        assert self._lock.gehalten(), "C-14: Append ohne gehaltene OS-Sperre"
        n = kopf.last_n + 1
        zeile = dict(kern)
        zeile["n"] = n
        zeile["prev"] = "sha256:" + kopf.last_h.hex()
        h_n = C.kette_hash(kopf.last_h, zeile)
        zeile["sig"] = C.signiere(h_n, self.sk.chronist)
        self._handle(ep).write(C.kanon(zeile) + "\n")
        kopf.last_n, kopf.last_h = n, h_n
        kopf.offene_h.append(h_n)

    def _ziel_epoche(self, kopf: _Kopf, ts: str, siegel_erzeugt: list[dict]) -> int:
        """Liefert die aktive (offene) Epoche; öffnet lazy eine neue bzw. **rollt bei 4096** (C-6)."""
        if kopf.offene_epoche is None:
            kopf.letzte_epoche += 1
            kopf.offene_epoche = kopf.letzte_epoche
            kopf.offene_von_n = kopf.last_n + 1
            kopf.offene_h = []
            kopf.offene_erste_ts = ts
        elif len(kopf.offene_h) >= self.epoche_max:
            siegel_erzeugt.append(self._schliesse(kopf))
            return self._ziel_epoche(kopf, ts, siegel_erzeugt)
        return kopf.offene_epoche

    def _schliesse(self, kopf: _Kopf) -> dict:
        """Merkle + Siegel der offenen Epoche (io_safe-atomar); öffnet KEINE neue (lazy, §4.2 Schritt 4)."""
        ep = kopf.offene_epoche
        assert ep is not None and kopf.offene_h, "Schließen ohne offene Epoche (Programmierfehler)"
        self._fsync_ein_handle(ep)                 # Zeilen persistiert, BEVOR das Siegel sie behauptet
        wurzel = C.merkle_wurzel(kopf.offene_h)
        siegel = C.baue_siegel(
            epoche=ep, wurzel=wurzel, prev_siegel=kopf.letztes_siegel,
            ereignisse=len(kopf.offene_h), von_n=kopf.offene_von_n, bis_n=kopf.last_n,
            quorum=self.quorum, chronist_jwk=self.sk.chronist)
        atomic_write_text(self.cdir / "siegel" / f"S{ep:08d}.json", C.kanon(siegel))
        kopf.letztes_siegel = C.siegel_hash(siegel)
        kopf.offene_epoche, kopf.offene_h, kopf.offene_von_n, kopf.offene_erste_ts = None, [], 0, ""
        return siegel

    # -- Schließregel-Zeit + Uhr-Anomalie (C-6 / BZ-C-11) --------------------

    def _faellig_zeit(self, kopf: _Kopf) -> bool:
        if kopf.offene_epoche is None or not kopf.offene_h:
            return False
        return self._alter_s(kopf, kopf.offene_erste_ts) > self.schliess_alter_s

    def _alter_s(self, kopf: _Kopf, ts: str) -> float:
        """Alter eines Ereignisses in Sekunden. **Zukunfts-``ts`` ⇒ ∞** (sofort fällig) + GELB-Merker
        „Uhr-Anomalie" (BZ-C-11) — ein zurückgesprungener/voreilender Zeitstempel blockiert nie."""
        jetzt = self._uhr()
        try:
            t = datetime.fromisoformat(ts)
        except ValueError:
            return float("inf")
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t > jetzt:
            kopf.uhr_anomalie = True
            return float("inf")
        return (jetzt - t).total_seconds()

    # -- Rückstand + Status --------------------------------------------------

    def _melde_rueckstand(self, kopf: _Kopf) -> None:
        offen, aeltestes = 0, None
        for quelle in self.quellen:
            try:
                conn = self._verbinde(quelle.db)
            except sqlite3.Error:
                continue
            try:
                row = conn.execute(
                    "SELECT COUNT(*), MIN(created_at) FROM chronik_ausgang WHERE epoche IS NULL"
                ).fetchone()
            finally:
                conn.close()
            offen += row[0] or 0
            if row[1] and (aeltestes is None or row[1] < aeltestes):
                aeltestes = row[1]
        alter = self._alter_s(kopf, aeltestes) if aeltestes else 0.0
        alarm = offen > 0 and alter > self.rueckstand_alarm_s
        self._rueckstand = {
            "offen": offen,
            "aeltestes_alter_s": (None if alter == float("inf") else round(alter, 1)),
            "alarm": alarm}
        if alarm:
            self._alarm("warn", "Chronik-Rückstand", {"offen": offen, "alter_s": self._rueckstand["aeltestes_alter_s"]})

    def _fork_stopp(self, fv: ForkVerdacht) -> None:
        self._fork = {"app": fv.app, "i": fv.i, "segment_hash": fv.segment_hash,
                      "outbox_hash": fv.outbox_hash, "zeit": now_iso()}
        self._alarm("kritisch", "Chronik-Fork-Verdacht (C-16)", dict(self._fork))

    def _alarm(self, schwere: str, titel: str, detail: dict) -> None:
        if self.event_hook is None:
            return
        try:
            self.event_hook(schwere, titel, detail)
        except Exception:
            pass                                    # best-effort; status.json trägt die durable Wahrheit

    def _schreibe_status(self, kopf: _Kopf) -> None:
        status = {
            "version": 1,
            "last_n": kopf.last_n,
            "last_h": "sha256:" + kopf.last_h.hex(),
            "letzte_epoche": kopf.letzte_epoche,
            "letztes_siegel": kopf.letztes_siegel,
            "offene_epoche": kopf.offene_epoche,
            "per_app_i": kopf.per_app_i,
            "rueckstand": getattr(self, "_rueckstand", {"offen": 0, "aeltestes_alter_s": 0.0, "alarm": False}),
            "fork_verdacht": self._fork,
            "recovery": {"torn_writes": kopf.torn_writes},
            "uhr_anomalie": kopf.uhr_anomalie,
            "pid": os.getpid(),
            "letzter_tick": now_iso()}
        atomic_write_text(self.cdir / "status.json", json.dumps(status, ensure_ascii=False, indent=2))

    # -- Datei-Handles (append-only) -----------------------------------------

    def _handle(self, ep: int):
        h = self._handles.get(ep)
        if h is None:
            pfad = self.cdir / "segmente" / f"E{ep:08d}.dzc"
            pfad.parent.mkdir(parents=True, exist_ok=True)
            # O_APPEND, LF-fest (newline="") — der Zeilen-Terminator ist plattform-unabhängig, damit
            # Segment-Bytes reproduzierbar sind (die Signatur deckt kanon(zeile) OHNE Terminator).
            h = open(pfad, "a", encoding="utf-8", newline="")
            self._handles[ep] = h
        return h

    def _fsync_handles(self) -> None:
        for h in self._handles.values():
            h.flush()
            os.fsync(h.fileno())

    def _fsync_ein_handle(self, ep: int) -> None:
        h = self._handles.get(ep)
        if h is not None:
            h.flush()
            os.fsync(h.fileno())

    def _fsync_und_schliesse_handles(self) -> None:
        for h in self._handles.values():
            try:
                h.flush()
                os.fsync(h.fileno())
            finally:
                h.close()
        self._handles.clear()

    # -- Kopf-Rekonstruktion (Recovery + Kette-Lesen) ------------------------

    def _lies_kopf(self) -> _Kopf:
        """Rekonstruiert den Ketten-Kopf aus den Segmenten (Wahrheit). Führt die einzige erlaubte
        Nicht-Append-Operation aus: Kürzung einer torn-write-Endzeile im **unversiegelten** Segment."""
        kopf = _Kopf()
        segmente = _segment_pfade(self.cdir)
        if not segmente:
            return kopf
        siegel_eps = set(_siegel_epochen(self.cdir))
        letzte_ep, letzter_pfad = segmente[-1]
        kopf.letzte_epoche = letzte_ep
        # letztes Siegel (prev_siegel-Kette)
        vorhandene_siegel = _siegel_epochen(self.cdir)
        if vorhandene_siegel:
            s = json.loads((self.cdir / "siegel" / f"S{vorhandene_siegel[-1]:08d}.json").read_text("utf-8"))
            kopf.letztes_siegel = C.siegel_hash(s)

        offen = letzte_ep not in siegel_eps
        zeilen = self._lies_segment_zeilen(letzter_pfad, kuerzbar=offen, kopf=kopf)
        if not zeilen:
            return kopf
        # last_n / last_h aus der letzten Zeile (prev-Feld trägt h_{n-1})
        letzte = zeilen[-1]
        prev_h = bytes.fromhex(letzte["prev"].split(":", 1)[1])
        kopf.last_n = letzte["n"]
        kopf.last_h = C.kette_hash(prev_h, {k: v for k, v in letzte.items() if k != "sig"})

        if offen:
            # offene Epoche vollständig einlesen ⇒ h-Liste für den späteren Merkle
            start_h = bytes.fromhex(zeilen[0]["prev"].split(":", 1)[1])
            h = start_h
            for z in zeilen:
                h = C.kette_hash(h, {k: v for k, v in z.items() if k != "sig"})
                kopf.offene_h.append(h)
            kopf.offene_epoche = letzte_ep
            kopf.offene_von_n = zeilen[0]["n"]
            kopf.offene_erste_ts = zeilen[0]["ts"]
            kopf.last_h = kopf.offene_h[-1]

        self._fuelle_per_app_i(kopf, segmente, letzte)
        return kopf

    def _lies_segment_zeilen(self, pfad: Path, *, kuerzbar: bool, kopf: _Kopf) -> list[dict]:
        """Liest ein Segment als JSON-Lines. Eine **torn-write-Endzeile** (unvollständiges JSON) wird
        NUR bei ``kuerzbar`` (unversiegeltes Segment) abgeschnitten — die einzige Nicht-Append-Op (§4.2)."""
        roh = pfad.read_text("utf-8").splitlines()
        zeilen: list[dict] = []
        for idx, line in enumerate(roh):
            if not line.strip():
                continue
            try:
                zeilen.append(json.loads(line))
            except json.JSONDecodeError:
                if kuerzbar and idx == len(roh) - 1:
                    gueltig = [r for r in roh[:idx] if r.strip()]
                    atomic_write_text(pfad, ("\n".join(gueltig) + "\n") if gueltig else "")
                    kopf.torn_writes += 1
                    break
                raise                                # interne Korruption / versiegelt ⇒ fail-loud
        return zeilen

    def _fuelle_per_app_i(self, kopf: _Kopf, segmente: list[tuple[int, Path]], letzte: dict) -> None:
        """``per_app_i`` aus dem status.json-Cache, wenn er zur Segment-Spitze passt; sonst Voll-Scan
        über alle Segmente (Segmente = Wahrheit; §4.2 Schritt 2)."""
        cache = self._lies_status_cache()
        if (cache and cache.get("last_n") == kopf.last_n
                and cache.get("last_h") == "sha256:" + kopf.last_h.hex()
                and isinstance(cache.get("per_app_i"), dict)):
            kopf.per_app_i = {k: int(v) for k, v in cache["per_app_i"].items()}
            return
        per_app: dict[str, int] = {}
        for _ep, pfad in segmente:
            for line in pfad.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    z = json.loads(line)
                except json.JSONDecodeError:
                    continue                          # torn Endzeile bereits behandelt
                app, i = z.get("app", ""), int(z.get("i", 0))
                if app and (app not in per_app or i > per_app[app]):
                    per_app[app] = i
        kopf.per_app_i = per_app

    def _lies_status_cache(self) -> dict | None:
        p = self.cdir / "status.json"
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _suche_zeile(self, app: str, i: int) -> tuple[int, str] | None:
        """Gezielte Suche nach ``(app, i)`` in den Segmenten (neueste zuerst) ⇒ (Epoche, nutzlast_hash).
        Nur auf dem seltenen Kollisions-Pfad (Crash-Waise / Restore-Fork) — sonst nie aufgerufen."""
        for ep, pfad in reversed(_segment_pfade(self.cdir)):
            for line in pfad.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    z = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if z.get("app") == app and int(z.get("i", -1)) == i:
                    return ep, z.get("nutzlast_hash", "")
        return None

    # -- Siegel-Zugriff (flush_und_warte) ------------------------------------

    def _epoche_von_n(self, n: int) -> int | None:
        for ep, pfad in _segment_pfade(self.cdir):
            for line in pfad.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    z = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if z.get("n") == n:
                    return ep if ep in set(_siegel_epochen(self.cdir)) else None
        return None

    def _lade_und_verifiziere_siegel(self, epoche: int) -> dict:
        pfad = self.cdir / "siegel" / f"S{epoche:08d}.json"
        if not pfad.is_file():
            raise RuntimeError(f"flush_und_warte: Siegel der Epoche {epoche} fehlt (C-9)")
        siegel = json.loads(pfad.read_text("utf-8"))
        material = C.lade_pruefmaterial(self.cdir)
        pub = {material.chronist_pub["kid"]: material.chronist_pub}
        eps = _siegel_epochen(self.cdir)
        vorher = [e for e in eps if e < epoche]
        prev = C.GENESIS_PREV_SIEGEL
        if vorher:
            prev_s = json.loads((self.cdir / "siegel" / f"S{vorher[-1]:08d}.json").read_text("utf-8"))
            prev = C.siegel_hash(prev_s)
        C.verifiziere_siegel(siegel, prev, pub)     # wirft ChronikFehler bei Bruch
        return siegel

    # -- Verbindung ----------------------------------------------------------

    @staticmethod
    def _verbinde(db_pfad: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_pfad)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


# ─────────────────────────────────────────────────────────────────────────────
# Quellen-Registry + Einstieg (`python -m appkit.chronist --tick`)
# ─────────────────────────────────────────────────────────────────────────────


def lade_quellen(cdir: Path) -> list[Quelle]:
    """Quellen-Registry ``data\\chronik\\quellen.json`` (§4.1). Fehlt sie, ist money die einzige
    v1-Quelle — eine weitere App = ein Eintrag, KEIN Code-Umbau (die D1-Pointe)."""
    p = cdir / "quellen.json"
    if p.is_file():
        roh = json.loads(p.read_text("utf-8"))
        return [Quelle(app=e["app"], db=e["db"]) for e in roh]
    return [Quelle(app="money", db=str(default_db_path("money")))]


def tick_einmal(cdir: Path | None = None, *, flush: bool = False,
                event_hook: Callable[[str, str, dict], None] | None = None) -> list[dict]:
    """Bequemer Einzel-Tick (CLI/Task). Lädt Schlüssel + Quellen-Registry und läuft einmal durch."""
    cdir = cdir or C.chronik_dir()
    chronist = Chronist(cdir, lade_quellen(cdir), event_hook=event_hook)
    return chronist.tick(flush=flush)


def _cli(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="appkit.chronist", description="DzChronist-Tick (V-BIZZI-1)")
    p.add_argument("--tick", action="store_true", help="einen Übernahme-/Siegel-Durchlauf ausführen")
    p.add_argument("--flush", action="store_true", help="offene Epoche am Ende unbedingt siegeln")
    p.add_argument("--dir", type=Path, default=None, help="chronik-Verzeichnis (Default: data/chronik)")
    args = p.parse_args(argv)
    if not args.tick:
        p.print_help()
        return 2
    try:
        siegel = tick_einmal(args.dir, flush=args.flush)
    except ChronistBesetzt as e:
        print(f"übersprungen: {e}")
        return 0
    print(f"Tick ok — {len(siegel)} Siegel erzeugt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
