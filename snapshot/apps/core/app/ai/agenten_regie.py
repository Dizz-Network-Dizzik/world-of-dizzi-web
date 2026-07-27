"""Regie-Scheduler der Agenten-Regie (Welle 2, RG-3 — docs/83 §2) — Core.

**Das Herz der reaktiven Regie.** Zieht Ereignisse aus dem Spine (Cursor je Quelle),
matcht sie **deterministisch** gegen die Abo-Tabelle (EIN Zuständiger je
``quelle × typ × bereich`` — KEIN LLM-Router: die Zuordnung ist entscheidbar, ein
Modell-Router wäre nur eine Halluzinations-Fläche, docs/83 §2), prüft die
Zustell-Sichtbarkeit (``ereignis_zustellbar``, fail-closed) und legt Zündungen
**idempotent** an (``regie_zuendungen`` PK ``ereignis_id × agent_id``).

Crash-Festigkeit (docs/83 §2, Selbst-Check 1): **Cursor + Zündungen wandern in EINER
Transaktion**, die Läufe startet der Aufrufer DANACH. Stirbt der Prozess vor dem
Commit, wurde weder der Cursor vorgerückt noch eine Zündung persistiert ⇒ dieselben
Ereignisse werden erneut gezogen und — dank ``INSERT OR IGNORE`` — höchstens einmal
gezündet. Ein ``offen`` gebliebener Lauf-Start wird beim Anlauf wieder aufgenommen.

**Master-Schalter (Not-Aus, docs/83 §3):** die Regie zündet NUR, wenn sie aktiv ist
(Default AUS). Die reine Kern-Logik hier nimmt ihn als ``ist_aktiv``-Parameter; die
Setting-/HTTP-Pull-/asyncio-Loop-Anbindung ist die Verdrahtung (RG-3b). So bleibt der
Kern ohne Infrastruktur testbar — und AUS heißt: **schauen (Cursor rückt vor), aber
nicht zünden.**
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Sequence

from appkit import ereignis_spine

from .. import db

# --- Zündungs-Status (Core-DB) ---------------------------------------------------

ZUENDUNG_OFFEN = "offen"            # Zündung angelegt, Lauf noch nicht gestartet
ZUENDUNG_GESTARTET = "gestartet"    # Lauf läuft/lief (lauf_id gesetzt)
ZUENDUNG_BUDGET = "budget_erschoepft"
ZUENDUNG_VERFALLEN = "verfallen"    # zu lange offen geblieben (ehrlich statt Spuk)

#: Setting-Key der Core-Arbeitskopie der Regie-Karte (von Management gepusht, RG-3b).
#: Bewusst ein Setting statt eigener Tabelle: EIN JSON-Blob je Nutzer, reload-fest,
#: keine Migration — „Core hält die Arbeitskopie" (docs/83 §2).
REGIE_KARTE_KEY = "regie_karte"

#: Grundeinstellungen der Live-Verdrahtung (RG-3b). Master-Schalter Default AUS
#: (docs/83 §3 Not-Aus): die Regie EXISTIERT dann vollständig, zündet aber nichts.
SETTING_AKTIV = "agenten_regie_aktiv"
SETTING_TICK_S = "regie_tick_s"
TICK_S_DEFAULT = 10
VERFALL_STUNDEN = 24               # offene Zündung älter ⇒ verfallen + Glocke

SCHEMA_REGIE_SQL = """
CREATE TABLE IF NOT EXISTS regie_zuendungen (
  ereignis_id  TEXT NOT NULL,
  agent_id     TEXT NOT NULL,
  user_id      TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'offen',
  lauf_id      TEXT NOT NULL DEFAULT '',
  grund        TEXT NOT NULL DEFAULT '',
  quelle_app   TEXT NOT NULL DEFAULT '',
  ereignis_typ TEXT NOT NULL DEFAULT '',
  ereignis_ref TEXT NOT NULL DEFAULT '',
  bereich_id   TEXT NOT NULL DEFAULT '',
  auftrag      TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  PRIMARY KEY (ereignis_id, agent_id)
);
CREATE INDEX IF NOT EXISTS idx_regie_zuendungen ON regie_zuendungen (user_id, status);
CREATE TABLE IF NOT EXISTS regie_cursor (
  quelle_app TEXT PRIMARY KEY,
  seq        INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
"""

#: Additive Spalten der Zündungs-Tabelle (RG-3b): der **Zünd-Kontext** (Quelle,
#: Ereignis-Typ/-Ref, Bereich, Abo-Auftrag) reist auf der Zündungs-Zeile mit —
#: so ist der Lauf-Start self-contained UND crash-fest (eine nach Neustart wieder
#: aufgenommene Zündung trägt ihren Kontext selbst, ohne das schon konsumierte
#: Ereignis erneut zu ziehen). ``CREATE`` oben deckt frische DBs; ``_migriere``
#: rüstet Bestands-DBs nach (SQLite-ALTER ist nicht idempotent ⇒ PRAGMA-Wächter).
_ZUSATZSPALTEN: tuple[tuple[str, str], ...] = (
    ("quelle_app", "TEXT NOT NULL DEFAULT ''"),
    ("ereignis_typ", "TEXT NOT NULL DEFAULT ''"),
    ("ereignis_ref", "TEXT NOT NULL DEFAULT ''"),
    ("bereich_id", "TEXT NOT NULL DEFAULT ''"),
    ("auftrag", "TEXT NOT NULL DEFAULT ''"),
)


def _migriere(conn) -> None:
    """Rüstet den Zünd-Kontext (``_ZUSATZSPALTEN``) an einer Bestands-DB nach.
    PRAGMA-gewächtert je Spalte (SQLite-ALTER wirft bei Doppelung) — Hausmuster
    ``migriere_bereich``."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(regie_zuendungen)")}
    for name, ddl in _ZUSATZSPALTEN:
        if name not in have:
            conn.execute(f"ALTER TABLE regie_zuendungen ADD COLUMN {name} {ddl}")


def _ensure_schema() -> None:
    """Idempotent: legt die Regie-Tabellen additiv in der Core-DB an (CREATE IF NOT
    EXISTS) und rüstet den Zünd-Kontext nach, ohne das zentrale core-``_SCHEMA``
    anzufassen."""
    conn = db.get_conn()
    conn.executescript(SCHEMA_REGIE_SQL)
    _migriere(conn)
    conn.commit()


# --- Abo-Modell (Core-Arbeitskopie; Governance-Heimat = Management-DB, docs/83 §2) --

@dataclass(frozen=True)
class Abo:
    """Ein Abo bindet einen Fach-Orchestrator an einen Ereignis-Strom. Definiert in
    Management (Governance), als Teil der Regie-Karte an den Core gepusht (RG-3b) —
    hier die Core-Arbeitskopie. ``bereich_id=''`` = Allgemein (matcht jedes Ereignis
    des Typs); ``aktiv`` entsteht als False (fail-closed, David schaltet)."""
    agent_id: str
    quelle_app: str
    ereignis_typ: str
    bereich_id: str = ""
    auftrag: str = ""
    max_pro_tag: int = 20
    aktiv: bool = False


def abo_fuer(abos: Sequence[Abo], quelle_app: str, ereignis_typ: str,
             bereich_id: str = "") -> Abo | None:
    """Deterministischer Match: das EINE aktive Abo für ``(quelle, typ, bereich)``.
    Ein bereichs-scharfes Abo (``bereich_id == ereignis.bereich``) gewinnt vor dem
    Allgemein-Abo (``bereich_id == ''``). ``None`` = kein Zuständiger — dann passiert
    nichts (kein Raten, kein Default-Agent)."""
    treffer = [a for a in abos if a.aktiv and a.quelle_app == quelle_app
               and a.ereignis_typ == ereignis_typ
               and a.bereich_id in ("", bereich_id)]
    if not treffer:
        return None
    # scharf vor allgemein: True (== bereich) sortiert vor False.
    treffer.sort(key=lambda a: a.bereich_id == bereich_id, reverse=True)
    return treffer[0]


# --- Cursor je Quelle (Core-DB) --------------------------------------------------

def cursor_holen(quelle_app: str) -> int:
    _ensure_schema()
    row = db.get_conn().execute(
        "SELECT seq FROM regie_cursor WHERE quelle_app=?", (quelle_app,)).fetchone()
    return int(row["seq"]) if row else 0


def _cursor_setzen(conn, quelle_app: str, seq: int) -> None:
    conn.execute(
        "INSERT INTO regie_cursor (quelle_app, seq, updated_at) VALUES (?,?,?) "
        "ON CONFLICT (quelle_app) DO UPDATE SET seq=excluded.seq, "
        "updated_at=excluded.updated_at",
        (quelle_app, int(seq), db.now_iso()))


# --- Zündungen (Core-DB) ---------------------------------------------------------

def _zuendung_anlegen(conn, user_id: str, ev: dict[str, Any], abo: "Abo") -> bool:
    """``INSERT OR IGNORE`` — True, wenn NEU (erste Zündung dieses Ereignisses für
    diesen Agenten). False bei bestehender Zündung ⇒ at-least-once-Dedup: ein
    Ereignis zündet einen Agenten höchstens einmal, egal wie oft der Tick es sieht.
    Der **Zünd-Kontext** (Quelle/Typ/Ref/Bereich + Abo-Auftrag) wird mitgeschrieben,
    damit der Lauf-Start (RG-3b) ihn ohne erneuten Pull hat — crash-fest auch nach
    Neustart (docs/83 §2)."""
    ts = db.now_iso()
    cur = conn.execute(
        "INSERT OR IGNORE INTO regie_zuendungen "
        "(ereignis_id, agent_id, user_id, status, quelle_app, ereignis_typ, "
        " ereignis_ref, bereich_id, auftrag, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ev.get("id", ""), abo.agent_id, user_id, ZUENDUNG_OFFEN, abo.quelle_app,
         ev.get("typ", ""), ev.get("ref", ""), ev.get("bereich_id", ""),
         abo.auftrag, ts, ts))
    return cur.rowcount > 0


def offene_zuendungen(user_id: str) -> list[dict[str, Any]]:
    """Die noch nicht gestarteten Zündungen (Wiederaufnahme beim Anlauf, docs/83 §2),
    inklusive Zünd-Kontext (Quelle/Typ/Ref/Bereich/Auftrag) für den Lauf-Start."""
    _ensure_schema()
    rows = db.get_conn().execute(
        "SELECT ereignis_id, agent_id, user_id, status, quelle_app, ereignis_typ, "
        "ereignis_ref, bereich_id, auftrag, created_at FROM regie_zuendungen "
        "WHERE user_id=? AND status=? ORDER BY created_at",
        (user_id, ZUENDUNG_OFFEN)).fetchall()
    return [dict(r) for r in rows]


def zuendung_status(conn, ereignis_id: str, agent_id: str, status: str,
                    *, lauf_id: str = "", grund: str = "") -> None:
    """Setzt den Status einer Zündung (gestartet/budget_erschoepft/verfallen) —
    vom Lauf-Start bzw. der Verfalls-Hygiene aufgerufen (RG-3b)."""
    conn.execute(
        "UPDATE regie_zuendungen SET status=?, lauf_id=?, grund=?, updated_at=? "
        "WHERE ereignis_id=? AND agent_id=?",
        (status, lauf_id, grund, db.now_iso(), ereignis_id, agent_id))


# --- Der Tick-Kern (docs/83 §2) --------------------------------------------------

def plane_zuendungen(user_id: str, quelle_app: str, events: Sequence[dict[str, Any]],
                     abos: Sequence[Abo], *, agent_sens: dict[str, str],
                     ist_aktiv: bool) -> list[dict[str, Any]]:
    """Verarbeitet die Ereignisse EINER Quelle und persistiert Cursor + Zündungen in
    EINER Transaktion (crash-fest). Gibt die NEU angelegten offenen Zündungen zurück
    (``[{ereignis_id, agent_id, abo}]``) — die Läufe startet der Aufrufer DANACH.

    Pro Ereignis: das zuständige aktive Abo finden → Zustell-Sichtbarkeit prüfen
    (``ereignis_zustellbar``, fail-closed: ein hoch/höchst-Ereignis erreicht nie einen
    schwächeren Agenten) → Zündung idempotent anlegen. Der Cursor rückt IMMER auf die
    höchste gesehene ``seq`` — auch bei ``ist_aktiv=False`` (Not-Aus = schauen, nicht
    zünden) und für nicht-abonnierte Ereignisse (sie sind bearbeitet: niemand
    zuständig). ``agent_sens`` unbekannt ⇒ ``hoechst`` (streng)."""
    _ensure_schema()
    conn = db.get_conn()
    neu: list[dict[str, Any]] = []
    max_seq = cursor_holen(quelle_app)
    for ev in events:
        seq = int(ev.get("seq", 0))
        if seq > max_seq:
            max_seq = seq
        if not ist_aktiv:
            continue                       # Not-Aus: Cursor rückt vor, aber nicht zünden
        abo = abo_fuer(abos, quelle_app, ev.get("typ", ""), ev.get("bereich_id", ""))
        if abo is None:
            continue                       # kein Zuständiger ⇒ nichts (kein Raten)
        sens = agent_sens.get(abo.agent_id, "hoechst")
        if not ereignis_spine.ereignis_zustellbar(ev.get("quelle_sens", "hoechst"), sens):
            continue                       # fail-closed: Sichtbarkeit verweigert
        if _zuendung_anlegen(conn, user_id, ev, abo):
            neu.append({"ereignis_id": ev.get("id", ""), "agent_id": abo.agent_id,
                        "abo": abo})
    _cursor_setzen(conn, quelle_app, max_seq)
    conn.commit()                          # Cursor + Zündungen GEMEINSAM (eine Tx)
    return neu


# --- Regie-Karte: die Core-Arbeitskopie (von Management gepusht, docs/83 §2) ------

def regie_karte_speichern(user_id: str, karte: dict[str, Any]) -> None:
    """Legt die von Management gepushte Regie-Karte als Core-Arbeitskopie ab
    (Abos + Agent-Wald + agent_sens; Eval-Status/def_hash ab RG-5). EIN Setting,
    reload-fest. Mgmt down ⇒ Core zündet mit letztem Stand — ``pushed_at`` macht das
    sichtbar statt heimlich."""
    db.setting_put(user_id, REGIE_KARTE_KEY, dict(karte or {}))
    db.audit(user_id, "system", "regie_karte_gespeichert",
             {"abos": len(karte.get("abos", []) if karte else []),
              "agenten": len(karte.get("agenten", {}) if karte else {})})


def regie_karte_holen(user_id: str) -> dict[str, Any]:
    """Die aktuelle Regie-Karte (leer, solange Management nie gepusht hat)."""
    return db.setting_get(user_id, REGIE_KARTE_KEY, {}) or {}


def _abos_aus_karte(karte: dict[str, Any]) -> list[Abo]:
    """Rekonstruiert die ``Abo``-Objekte aus der Karte (nur bekannte Felder ⇒
    vorwärts-tolerant gegen spätere Zusatzfelder)."""
    out: list[Abo] = []
    for a in karte.get("abos", []) or []:
        if not isinstance(a, dict):
            continue
        out.append(Abo(
            agent_id=str(a.get("agent_id", "")),
            quelle_app=str(a.get("quelle_app", "")),
            ereignis_typ=str(a.get("ereignis_typ", "")),
            bereich_id=str(a.get("bereich_id", "")),
            auftrag=str(a.get("auftrag", "")),
            max_pro_tag=int(a.get("max_pro_tag", 20) or 20),
            aktiv=bool(a.get("aktiv", False))))
    return out


# --- Tages-Budget (docs/83 §2: laeufe_pro_tag [Agent] UND max_pro_tag [Abo]) ------

def _tag_start_iso() -> str:
    """Beginn des heutigen UTC-Tages als ISO-String (lexikografisch vergleichbar mit
    den ``now_iso``-Stempeln des Hauses)."""
    heute = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return heute.isoformat(timespec="seconds")


def _zaehle(sql: str, params: tuple) -> int:
    """COUNT-Helfer, defensiv gegen eine noch fehlende Tabelle (vor dem ersten Lauf
    existiert ``agent_laeufe`` evtl. noch nicht) ⇒ dann 0 (Budget frei)."""
    import sqlite3
    try:
        row = db.get_conn().execute(sql, params).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def budget_frei(user_id: str, agent_id: str, quelle_app: str, ereignis_typ: str,
                bereich_id: str, *, laeufe_pro_tag: int,
                max_pro_tag: int) -> tuple[bool, str]:
    """Ist heute noch Budget für einen weiteren Lauf? Zwei Deckel (docs/83 §2):
    ``laeufe_pro_tag`` (Agent-Budget, über ALLE echten Läufe des Agenten) UND
    ``max_pro_tag`` (Abo, über die schon **gestarteten** Zündungen dieses Ereignis-
    Stroms). Erschöpft ⇒ (False, Grund) — der Aufrufer setzt ``budget_erschoepft`` +
    Glocke, NIE stiller Drop."""
    seit = _tag_start_iso()
    n_agent = _zaehle(
        "SELECT COUNT(*) FROM agent_laeufe WHERE user_id=? AND agent_id=? AND started_at>=?",
        (user_id, agent_id, seit))
    if n_agent >= laeufe_pro_tag:
        return (False, f"laeufe_pro_tag {laeufe_pro_tag} erreicht ({n_agent} heute)")
    n_abo = _zaehle(
        "SELECT COUNT(*) FROM regie_zuendungen WHERE user_id=? AND agent_id=? AND "
        "quelle_app=? AND ereignis_typ=? AND status=? AND created_at>=?",
        (user_id, agent_id, quelle_app, ereignis_typ, ZUENDUNG_GESTARTET, seit))
    if n_abo >= max_pro_tag:
        return (False, f"max_pro_tag {max_pro_tag} erreicht ({n_abo} heute)")
    return (True, "")


def _abo_max_pro_tag(karte: dict[str, Any], agent_id: str, quelle_app: str,
                     ereignis_typ: str, bereich_id: str) -> int:
    """``max_pro_tag`` des zuständigen Abos (scharf vor allgemein, wie ``abo_fuer``);
    Default 20, wenn kein Abo passt (defensiv)."""
    treffer = [a for a in _abos_aus_karte(karte)
               if a.agent_id == agent_id and a.quelle_app == quelle_app
               and a.ereignis_typ == ereignis_typ and a.bereich_id in ("", bereich_id)]
    if not treffer:
        return 20
    treffer.sort(key=lambda a: a.bereich_id == bereich_id, reverse=True)
    return treffer[0].max_pro_tag


# --- Glocke (Mensch-Meldung; docs/83 §2: nie stiller Drop) -----------------------

def _glocke(user_id: str, title: str, detail: dict[str, Any],
            *, severity: str = "warn") -> None:
    """Schreibt eine Glocken-Meldung (``notices``, Core-DB) — dieselbe Schiene wie
    ``/api/events``. Budget-Erschöpfung/Verfall werden so EHRLICH sichtbar statt still
    verschluckt. Best-effort (eine Glocke darf den Tick nie kippen)."""
    try:
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO notices (id, user_id, source, severity, title, detail, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (db.new_id(), user_id, "regie", severity, title,
             json.dumps(detail, ensure_ascii=False), db.now_iso()))
        conn.commit()
    except Exception:
        pass


# --- Verfalls-Hygiene (docs/83 §2: offen >24 h ⇒ verfallen + Glocke) -------------

def verfalls_hygiene(user_id: str, *, jetzt_iso: str | None = None,
                     stunden: int = VERFALL_STUNDEN) -> int:
    """Setzt offene Zündungen, die länger als ``stunden`` warten, auf ``verfallen``
    (+ EINE Sammel-Glocke) — ehrlich statt Spuk (docs/83 §2). ``jetzt_iso`` injizierbar
    (Test). Gibt die Anzahl verfallener Zündungen zurück."""
    _ensure_schema()
    jetzt = datetime.fromisoformat(jetzt_iso) if jetzt_iso else datetime.now(timezone.utc)
    grenze = (jetzt - timedelta(hours=stunden)).isoformat(timespec="seconds")
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT ereignis_id, agent_id FROM regie_zuendungen "
        "WHERE user_id=? AND status=? AND created_at<?",
        (user_id, ZUENDUNG_OFFEN, grenze)).fetchall()
    for r in rows:
        zuendung_status(conn, r["ereignis_id"], r["agent_id"], ZUENDUNG_VERFALLEN,
                        grund=f"verfallen (>{stunden} h offen)")
    conn.commit()
    if rows:
        _glocke(user_id, "Regie: Zündungen verfallen",
                {"anzahl": len(rows), "stunden": stunden})
    return len(rows)


# --- Lauf-Start je Zündung (docs/83 §2: enger Zünd-Kontext = Ereignis-Karte) ------

#: Der Lauf-Treiber (injiziert): (snapshot, auftrag, sensitive) → lauf_id. Prod =
#: ``agenten_routes.lauf_aus_regie`` (echter Katalog+Runtime); Test = Fake.
RunFn = Callable[[dict[str, Any], str, bool], Awaitable[str]]

#: Der Ereignis-Pull (injiziert): (quelle_app, cursor) → Ereignis-Liste | None. None =
#: Quelle offline/unerreichbar (ehrlich überspringen). Prod = HTTP-Pull (main.py).
PullFn = Callable[[str, int], Awaitable["list[dict[str, Any]] | None"]]


def _snapshot_aus_karte(karte: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Baut den Lauf-Snapshot (``{"wurzel": id, "agenten": {...}}``) für einen Wurzel-
    Agenten aus dem Karten-Wald — nur der erreichbare Sub-Baum (wie
    ``agenten_laeufe.schnappschuss``). ``None`` ⇒ der Agent fehlt in der Karte
    (gelöscht/nie gepusht)."""
    agenten = karte.get("agenten", {}) or {}
    if agent_id not in agenten:
        return None
    sub: dict[str, Any] = {}

    def _geh(aid: str) -> None:
        if aid in sub or aid not in agenten:
            return
        d = agenten[aid]
        sub[aid] = d
        for sid in (d.get("sub_agenten") or ()):
            _geh(str(sid))

    _geh(agent_id)
    return {"wurzel": agent_id, "agenten": sub}


def _zuend_auftrag(z: dict[str, Any]) -> str:
    """Der enge Zünd-Kontext als Auftrags-Satz (die **Ereignis-Karte**, nicht die
    Daten): Ereignis-Typ + Zeiger + Bereich + 1-Satz-Abo-Auftrag. Inhalte holt der
    Lauf selbst über seine read-Tools (Pull-Kontext gegen Kontext-Drift, §2)."""
    teile = [f"Ereignis '{z.get('ereignis_typ', '')}'"]
    if z.get("ereignis_ref"):
        teile.append(f"(Zeiger {z['ereignis_ref']})")
    if z.get("bereich_id"):
        teile.append(f"im Bereich {z['bereich_id']}")
    satz = " ".join(teile) + "."
    if z.get("auftrag"):
        satz += f" Auftrag: {z['auftrag']}"
    return satz


async def _starte_eine(user_id: str, z: dict[str, Any], karte: dict[str, Any],
                       *, run_fn: RunFn) -> str | None:
    """Startet EINEN Lauf für eine offene Zündung — nach Budget-Prüfung. Setzt den
    Zündungs-Status fail-closed (gestartet/budget_erschoepft/verfallen). Gibt die
    ``lauf_id`` zurück oder ``None`` (Budget erschöpft / Agent aus der Karte weg)."""
    agent_id = z.get("agent_id", "")
    ereignis_id = z.get("ereignis_id", "")
    snap = _snapshot_aus_karte(karte, agent_id)
    if snap is None:                                   # Agent aus der Karte verschwunden
        conn = db.get_conn()
        zuendung_status(conn, ereignis_id, agent_id, ZUENDUNG_VERFALLEN,
                        grund="Agent nicht (mehr) in der Regie-Karte")
        conn.commit()
        return None
    agent_def = (karte.get("agenten", {}) or {}).get(agent_id, {})
    lpt = int((agent_def.get("budget") or {}).get("laeufe_pro_tag", 20) or 20)
    mpt = _abo_max_pro_tag(karte, agent_id, z.get("quelle_app", ""),
                           z.get("ereignis_typ", ""), z.get("bereich_id", ""))
    frei, grund = budget_frei(user_id, agent_id, z.get("quelle_app", ""),
                              z.get("ereignis_typ", ""), z.get("bereich_id", ""),
                              laeufe_pro_tag=lpt, max_pro_tag=mpt)
    if not frei:
        conn = db.get_conn()
        zuendung_status(conn, ereignis_id, agent_id, ZUENDUNG_BUDGET, grund=grund)
        conn.commit()
        _glocke(user_id, "Regie: Budget erschöpft", {"agent_id": agent_id, "grund": grund})
        return None
    lauf_id = await run_fn(snap, _zuend_auftrag(z), True)   # Regie-Läufe = immer sensibel
    conn = db.get_conn()
    zuendung_status(conn, ereignis_id, agent_id, ZUENDUNG_GESTARTET, lauf_id=lauf_id)
    conn.commit()
    return lauf_id


async def tick(user_id: str, *, ist_aktiv: bool, pull_fn: PullFn, run_fn: RunFn,
               jetzt_iso: str | None = None) -> list[str]:
    """EIN Regie-Tick (docs/83 §2 — die Verdrahtung über dem RG-3a-Kern):

    1. Regie-Karte laden (Abos + Wald + agent_sens).
    2. Je AKTIVER Quelle: Ereignisse ab Cursor ziehen (``pull_fn``; ``None`` = offline,
       ehrlich überspringen) → ``plane_zuendungen`` (Cursor + Zündungen in einer Tx).
    3. Verfalls-Hygiene (offen >24 h ⇒ verfallen + Glocke).
    4. NUR wenn ``ist_aktiv``: für jede offene Zündung einen Lauf starten (budget-
       geprüft, sequenziell). Not-Aus (``ist_aktiv=False``) = schauen (Cursor rückt
       vor), nicht zünden.

    Gibt die Liste der gestarteten ``lauf_id`` zurück (Diagnose/Test)."""
    karte = regie_karte_holen(user_id)
    abos = _abos_aus_karte(karte)
    agent_sens = {str(k): str(v) for k, v in (karte.get("agent_sens") or {}).items()}
    for quelle in sorted({a.quelle_app for a in abos if a.aktiv}):
        events = await pull_fn(quelle, cursor_holen(quelle))
        if events is None:
            continue                       # Quelle offline ⇒ ehrlich überspringen
        plane_zuendungen(user_id, quelle, events, abos,
                         agent_sens=agent_sens, ist_aktiv=ist_aktiv)
    verfalls_hygiene(user_id, jetzt_iso=jetzt_iso)
    if not ist_aktiv:
        return []
    gestartet: list[str] = []
    for z in offene_zuendungen(user_id):
        lauf_id = await _starte_eine(user_id, z, karte, run_fn=run_fn)
        if lauf_id:
            gestartet.append(lauf_id)
    return gestartet


# --- Read-only-Projektionen (Regie-Zentrale, docs/83 §3) -------------------------

def zuendungen_liste(user_id: str, *, status: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
    """Zündungs-/Lauf-Verlauf (Ereignis→Lauf-Kette), jüngste zuerst. Read-only —
    speist die Regie-Zentrale (Ereignis→Lauf→Vorschlag→Entscheidung klickbar)."""
    _ensure_schema()
    q = ("SELECT ereignis_id, agent_id, status, lauf_id, grund, quelle_app, "
         "ereignis_typ, ereignis_ref, bereich_id, created_at, updated_at "
         "FROM regie_zuendungen WHERE user_id=?")
    params: list[Any] = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    return [dict(r) for r in db.get_conn().execute(q, params).fetchall()]


def zuendungen_zaehler(user_id: str) -> dict[str, int]:
    """Zündungs-Zähler je Status (offen/gestartet/budget_erschoepft/verfallen) —
    die Not-Aus-/Budget-Ampel der Regie-Zentrale."""
    _ensure_schema()
    rows = db.get_conn().execute(
        "SELECT status, COUNT(*) AS n FROM regie_zuendungen WHERE user_id=? "
        "GROUP BY status", (user_id,)).fetchall()
    return {r["status"]: int(r["n"]) for r in rows}
