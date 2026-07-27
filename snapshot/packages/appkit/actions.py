"""Aktions-Tools mit Human-in-the-Loop (Kernpaket K4, Vertrag 1.2).

Die Sicherheits-Regel der Föderation in Code: **KI beobachtet + schlägt vor,
führt aber nie eigenmächtig aus.** Eine „Aktion" (alles mit Wirkung: posten,
Termin anlegen, Order ändern …) durchläuft IMMER:

  propose (KI/MCP) ──► pending ──Nutzer──► approve ⇒ executing ⇒ executed
                          │                  │          └─ (Fehler ⇒ failed)
                          │                  └─ Crash in 'executing' bleibt 'executing'
                          ├─ reject ⇒ rejected         (kein Re-Run, at-most-once, P1.7)
                          └─ TTL ⇒ expired

HITL-Stufen je Aktion (``level``): die Freigabe (approve) verlangt die
entsprechende Schutzstufe aus appkit.auth — `lokal` (harmlos) · `verifiziert`
(sensibel) · `hochsicher` (Echtgeld; z. B. Dizz Trading). Vor K1-Login sind
verifiziert/hochsicher fail-closed — Aktionen bleiben dann liegen statt
durchzurutschen. Alles wird auditiert.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .agenten import INBOX_ZUSATZSPALTEN
from .db import Database, new_id, now_iso

PENDING_TTL_S = 24 * 3600

Handler = Callable[[dict[str, Any]], Any]

#: Vier-Augen-Erweiterung von ``app_actions`` (§B5 / CH-11) — ADDITIV, idempotent
#: nachgerüstet mit demselben ALTER-Mechanismus wie ``INBOX_ZUSATZSPALTEN``. Der
#: Zweit-Prüfer (Checker) einer ``vier_augen``-pflichtigen Aktion: ``pruefer_id`` =
#: opake UUID des zweiten Subjekts (≠ Ersteller), ``pruefer_auth_ref`` = dessen
#: frische ``hochsicher``-Auth-Referenz. Beide wandern kryptografisch in den
#: ``charta_entscheide``-Entscheid (CH-11, ``entscheid_gegenzeichnen``); die Spalten
#: hier sind die **Inbox-Oberfläche** dazu (WER hat gegengezeichnet, sichtbar in
#: ``listing``). Leer = normale Ein-Augen-Aktion (Bestands-Verhalten unverändert).
VIERAUGEN_ZUSATZSPALTEN = (
    ("pruefer_id", "TEXT NOT NULL DEFAULT ''"),
    ("pruefer_auth_ref", "TEXT NOT NULL DEFAULT ''"),
)


def _row_get(row: Any, key: str, default: str = "") -> Any:
    """Spalten-tolerantes Lesen einer sqlite3.Row: fehlt die Spalte (Bestands-DB vor
    der Inbox-Migration), kommt ``default`` statt eines KeyError. Macht ``listing()``
    beweisbar bruchfrei über den Migrations-Übergang (0-Bruch, docs/63 §2)."""
    return row[key] if key in row.keys() else default


def migriere_actions_inbox(db: Database) -> None:
    """Additive ``app_actions``-Erweiterung: hängt die Inbox-Spalten
    ``agent_id``/``warum``/``lauf_id``/``idem`` (docs/63 §2 / RG-4, ``INBOX_ZUSATZSPALTEN``)
    **und** die Vier-Augen-Spalten ``pruefer_id``/``pruefer_auth_ref`` (§B5 / CH-11,
    ``VIERAUGEN_ZUSATZSPALTEN``) idempotent an (Muster ``migriere_bereich``). SQLite
    ``ALTER ADD COLUMN`` ist NICHT idempotent ⇒ PRAGMA-table_info-Guard. Läuft beim
    App-Start (create_app) für JEDE App und self-healend in ``propose()``/``decide()``
    (Vier-Augen) — wirkt netzweit ohne Per-App-Code."""
    conn = db.get_conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(app_actions)")}
    if not cols:            # Tabelle (noch) nicht da ⇒ _BASE_SCHEMA legt sie später an
        return
    geaendert = False
    for name, ddl in INBOX_ZUSATZSPALTEN + VIERAUGEN_ZUSATZSPALTEN:
        if name not in cols:
            conn.execute(f"ALTER TABLE app_actions ADD COLUMN {name} {ddl}")
            geaendert = True
    if geaendert:
        conn.commit()


@dataclass(frozen=True)
class ActionDef:
    name: str
    handler: Handler
    level: str                     # 'lokal' | 'verifiziert' | 'hochsicher'
    beschreibung: str = ""


class ActionRegistry:
    """Die ausführbaren Aktionen einer App (Domänen-Code registriert sie)."""

    def __init__(self) -> None:
        self._defs: dict[str, ActionDef] = {}

    def register(self, name: str, handler: Handler, level: str = "verifiziert",
                 beschreibung: str = "") -> None:
        if level not in ("lokal", "verifiziert", "hochsicher"):
            raise ValueError(f"Unbekannte HITL-Stufe: {level!r}")
        if name in self._defs:
            raise ValueError(f"Aktion doppelt registriert: {name!r}")
        self._defs[name] = ActionDef(name, handler, level, beschreibung)

    def get(self, name: str) -> ActionDef | None:
        return self._defs.get(name)

    def catalog(self) -> list[dict[str, str]]:
        return [{"name": d.name, "level": d.level, "beschreibung": d.beschreibung}
                for d in self._defs.values()]


def _expire_stale(db: Database, user_id: str) -> None:
    conn = db.get_conn()
    conn.execute(
        "UPDATE app_actions SET status='expired', updated_at=? "
        "WHERE user_id=? AND status='pending' AND expires_at<?",
        (now_iso(), user_id, time.time()))
    conn.commit()


def propose(db: Database, registry: ActionRegistry, user_id: str, name: str,
            params: dict[str, Any], source: str = "ki", *,
            agent_id: str = "", warum: str = "", lauf_id: str = "",
            idem: str = "") -> dict[str, Any]:
    """Legt einen Aktions-Vorschlag an (führt NICHTS aus).

    ``agent_id``/``warum``/``lauf_id`` (docs/63 §2, nur-Keyword mit Default '' ⇒
    Bestands-Aufrufer unverändert) tragen die Agenten-Herkunft: WAS = ``name`` +
    ``params``, WARUM = ``warum``. Bei ``source='agent'`` ist WARUM PFLICHT — ein
    Agent, der sein Warum nicht sagen kann, hat keins (leeres WARUM ⇒ ``ValueError``,
    die Inbox bleibt sauber). Die Inbox-Spalten werden self-healend nachgerüstet.

    ``idem`` (RG-4, docs/83 §2 — Wirkungs-Idempotenz): ist es gesetzt und existiert
    schon eine PENDING-Aktion gleichen Namens mit derselben ``idem`` für diesen Nutzer,
    wird die BESTEHENDE zurückgegeben (``idem_treffer=True``) statt eine Dublette
    anzulegen. So erzeugt at-least-once × Wiederanlauf (Prozess-Kill zwischen Zündung
    und Vorschlag) genau EINEN Inbox-Eintrag; der Pilot nutzt ``idem = nachricht_ref +
    aktion`` (§5.7). Leer ⇒ kein Dedup (Bestands-Aufrufer unverändert)."""
    d = registry.get(name)
    if d is None:
        raise KeyError(f"Unbekannte Aktion: {name!r}")
    if source == "agent" and not warum.strip():
        raise ValueError("Agenten-Vorschlag ohne WARUM abgelehnt "
                         "(source='agent' verlangt eine Begründung).")
    migriere_actions_inbox(db)   # Spalten existieren, bevor wir sie schreiben/lesen
    conn = db.get_conn()
    if idem.strip():
        # Dedup NUR gegen wirklich offene Vorschläge: abgelaufene erst verfallen lassen,
        # sonst dedupt man gegen eine Leiche (Muster listing/decide).
        _expire_stale(db, user_id)
        vorhanden = conn.execute(
            "SELECT id FROM app_actions WHERE user_id=? AND name=? AND idem=? "
            "AND status='pending' AND deleted_at IS NULL ORDER BY created_at LIMIT 1",
            (user_id, name, idem)).fetchone()
        if vorhanden is not None:
            db.audit(user_id, "ki", "aktion_idem_treffer",
                     {"id": vorhanden["id"], "name": name, "idem": idem})
            return {"id": vorhanden["id"], "name": name, "status": "pending",
                    "level": d.level, "beschreibung": d.beschreibung, "idem_treffer": True}
    ts = now_iso()
    action_id = new_id()
    conn.execute(
        """INSERT INTO app_actions (id, user_id, name, params, source, status,
                                    agent_id, warum, lauf_id, idem,
                                    expires_at, created_at, updated_at)
           VALUES (?,?,?,?,?,'pending',?,?,?,?,?,?,?)""",
        (action_id, user_id, name, json.dumps(params, ensure_ascii=False),
         source, agent_id, warum, lauf_id, idem, time.time() + PENDING_TTL_S, ts, ts))
    conn.commit()
    db.audit(user_id, "ki", "aktion_vorgeschlagen",
             {"id": action_id, "name": name, "source": source,
              **({"agent_id": agent_id} if agent_id else {})})
    return {"id": action_id, "name": name, "status": "pending",
            "level": d.level, "beschreibung": d.beschreibung}


def listing(db: Database, user_id: str, registry: ActionRegistry,
            status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    _expire_stale(db, user_id)
    q = "SELECT * FROM app_actions WHERE user_id=? AND deleted_at IS NULL"
    params: list[Any] = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(limit, 200))
    rows = db.get_conn().execute(q, params).fetchall()
    out = []
    for r in rows:
        d = registry.get(r["name"])
        out.append({"id": r["id"], "name": r["name"],
                    "params": json.loads(r["params"]), "source": r["source"],
                    "status": r["status"],
                    "level": d.level if d else "verifiziert",
                    # Agenten-Herkunft (docs/63 §2) — spalten-tolerant für Bestands-DBs
                    # vor der Inbox-Migration; speist inbox_eintrag (Netz-Inbox Z4.1-D).
                    "agent_id": _row_get(r, "agent_id"),
                    "warum": _row_get(r, "warum"),
                    "lauf_id": _row_get(r, "lauf_id"),
                    "idem": _row_get(r, "idem"),
                    # Vier-Augen-Oberfläche (§B5) — WER hat gegengezeichnet (leer =
                    # normale Ein-Augen-Aktion); spalten-tolerant wie die Inbox-Felder.
                    "pruefer_id": _row_get(r, "pruefer_id"),
                    "pruefer_auth_ref": _row_get(r, "pruefer_auth_ref"),
                    "result": json.loads(r["result"]) if r["result"] else None,
                    "created_at": r["created_at"]})
    return out


def _melde_entscheidung(cb: Callable[[dict[str, Any]], None] | None,
                        registry: ActionRegistry, row: Any,
                        approve: bool, status: str) -> None:
    """Ruft den optionalen Entscheidungs-Hook — die Naht für den
    ``hitl_entschieden``-Event-Spine (docs/83 §4, Eval-Ground-Truth). Bewusst
    ENTKOPPELT: appkit.actions kennt weder Spine noch Aktions-Klassen; es reicht
    nur die Roh-Zeile + Ausgang durch, der Aufrufer (app.py) baut das Ereignis.
    Best-effort: wirft der Hook, darf das die bereits gefallene Entscheidung NIE
    kippen (die Wirkung ist schon passiert)."""
    if cb is None:
        return
    d = registry.get(row["name"])
    try:
        cb({"action_id": row["id"], "name": row["name"],
            "approve": approve, "status": status,
            "level": d.level if d is not None else "",
            "agent_id": _row_get(row, "agent_id"),
            "warum": _row_get(row, "warum"),
            "lauf_id": _row_get(row, "lauf_id"),
            "user_id": row["user_id"]})
    except Exception:
        pass  # best-effort — ein kaputter Hook stoppt nie eine gefallene Entscheidung


class VierAugenFehler(ValueError):
    """Fail-loud bei verletztem Vier-Augen-Gate (§B5/CH-11) — Selbst-Freigabe,
    fehlender/zu schwacher/zu früher Zweit-Auth. ``ValueError``-Subklasse ⇒ die
    HTTP-Schicht behandelt es wie ``propose``' WARUM-Ablehnung (422), die Aktion
    bleibt ``pending`` (nie stilles Downgrade, D2-Ehrlichkeit)."""


def _vier_augen_gate(row: Any, *, pruefer_id: str, pruefer_auth_ref: str,
                     pruefer_auth_zeit_iso: str, pruefer_frisch_hochsicher: bool) -> None:
    """Strukturelles Vier-Augen-Gate für ``app_actions`` (§B5/CH-11) — deckungsgleich
    mit ``charta_speicher.entscheid_gegenzeichnen``: zweiter ≠ Ersteller (Maker≠Checker),
    frische ``hochsicher``-Auth, Zeitstempel NACH dem Antrag. Die AUTH-*Stärke*
    (hochsicher+frisch) stellt die HTTP-Schicht fest und reicht sie als ``bool`` durch
    (wie die Stufen-Prüfung); die *Reihenfolge* prüft der Kern selbst gegen
    ``created_at`` (= Antrags-/Vorschlagszeit). Wirft ``VierAugenFehler`` bei jedem
    Verstoß — nie stilles Übergehen."""
    if not pruefer_id:
        raise VierAugenFehler("vier_augen: pruefer_id fehlt (zweites Subjekt erforderlich)")
    if not pruefer_auth_ref:
        raise VierAugenFehler("vier_augen: pruefer_auth_ref fehlt (Auth-Referenz erforderlich)")
    if pruefer_id == row["user_id"]:
        raise VierAugenFehler("vier_augen: Selbst-Freigabe verboten (Maker≠Checker)")
    if not pruefer_frisch_hochsicher:
        raise VierAugenFehler("vier_augen: Prüfer-Auth nicht frisch/hochsicher")
    if not (pruefer_auth_zeit_iso and pruefer_auth_zeit_iso > row["created_at"]):
        raise VierAugenFehler("vier_augen: Prüfer-Auth nicht NACH dem Antrag")


def decide(db: Database, registry: ActionRegistry, user_id: str,
           action_id: str, approve: bool, *,
           on_entscheidung: Callable[[dict[str, Any]], None] | None = None,
           vier_augen: bool = False, pruefer_id: str = "", pruefer_auth_ref: str = "",
           pruefer_auth_zeit_iso: str = "", pruefer_frisch_hochsicher: bool = False,
           ) -> dict[str, Any] | None:
    """Nutzer-Entscheidung. approve=True ⇒ Handler wird ausgeführt (synchron).
    None = unbekannt/nicht mehr pending (auch bei verlorenem CAS-Rennen: eine
    parallele Entscheidung hat gewonnen). Stufen-Prüfung macht die HTTP-Schicht
    (sie kennt den UserContext); hier läuft nur noch die Mechanik.

    ``on_entscheidung`` (optional, Default None = 0-Bruch): Hook, der nach einer
    FINALEN Nutzer-Entscheidung (rejected / executed / failed — NIE bei verlorenem
    Rennen oder weggefallener Registrierung) best-effort gerufen wird. Naht für den
    ``hitl_entschieden``-Event-Spine (docs/83 §4); Verdrahtung + Event-Bau im
    Aufrufer (create_app).

    ``vier_augen`` (optional, §B5/CH-11 — Default False = Bestands-Verhalten byte-genau):
    ist es beim Freigeben (approve=True) gesetzt, muss ein ZWEITES Subjekt gegenzeichnen
    — ``pruefer_id`` (≠ Ersteller ``row.user_id``), ``pruefer_auth_ref``, frische
    ``hochsicher``-Auth (``pruefer_frisch_hochsicher``, von der HTTP-Schicht bestimmt)
    und ``pruefer_auth_zeit_iso`` NACH dem Vorschlag. Verletzung ⇒ ``VierAugenFehler``
    (Aktion bleibt pending). Der **CAS-Kern (pending→executing) bleibt wörtlich**
    unverändert; ``pruefer_id``/``pruefer_auth_ref`` werden erst NACH gewonnenem CAS
    auf der 'executing'-Zeile vermerkt (genau ein Schreiber). Die kryptografische
    Wahrheit hält ``charta_entscheide`` (``entscheid_gegenzeichnen``); diese Spalten
    sind die Inbox-Oberfläche dazu."""
    _expire_stale(db, user_id)
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM app_actions WHERE id=? AND user_id=? AND deleted_at IS NULL",
        (action_id, user_id)).fetchone()
    if row is None or row["status"] != "pending":
        return None
    if not approve:
        cur = conn.execute("UPDATE app_actions SET status='rejected', updated_at=? "
                           "WHERE id=? AND status='pending'", (now_iso(), action_id))
        conn.commit()
        if cur.rowcount != 1:      # Rennen verloren (parallel entschieden/ausführend)
            return None
        db.audit(user_id, "user", "aktion_abgelehnt", {"id": action_id, "name": row["name"]})
        _melde_entscheidung(on_entscheidung, registry, row, approve, "rejected")
        return {"id": action_id, "status": "rejected"}

    d = registry.get(row["name"])
    if d is None:  # Registrierung weg (App-Update) ⇒ sicher scheitern
        cur = conn.execute("UPDATE app_actions SET status='failed', result=?, updated_at=? "
                           "WHERE id=? AND status='pending'",
                     (json.dumps({"error": "Aktion nicht mehr registriert"}),
                      now_iso(), action_id))
        conn.commit()
        if cur.rowcount != 1:
            return None
        return {"id": action_id, "status": "failed"}
    if vier_augen:   # §B5/CH-11: Zweit-Prüfer PFLICHT, fail-loud VOR jedem Statuswechsel
        migriere_actions_inbox(db)          # pruefer-Spalten sicherstellen (self-healend)
        _vier_augen_gate(row, pruefer_id=pruefer_id, pruefer_auth_ref=pruefer_auth_ref,
                         pruefer_auth_zeit_iso=pruefer_auth_zeit_iso,
                         pruefer_frisch_hochsicher=pruefer_frisch_hochsicher)
    # P1.7 exactly-once: VOR dem Handler auf 'executing' committen. Crasht der Prozess
    # NACH der Seitenwirkung (z. B. Nachricht gesendet) aber VOR dem End-Commit, bleibt
    # die Aktion 'executing' (NICHT 'pending') ⇒ kein automatisches Re-Run via approve.
    cur = conn.execute("UPDATE app_actions SET status='executing', updated_at=? "
                       "WHERE id=? AND status='pending'",  # F-A CAS: at-most-once auch parallel
                       (now_iso(), action_id))
    conn.commit()
    if cur.rowcount != 1:   # Rennen verloren ⇒ None (wie 'nicht mehr pending')
        return None
    if vier_augen:   # Checker NACH gewonnenem CAS auf der 'executing'-Zeile vermerken
        conn.execute("UPDATE app_actions SET pruefer_id=?, pruefer_auth_ref=? "
                     "WHERE id=? AND status='executing'",
                     (pruefer_id, pruefer_auth_ref, action_id))
        conn.commit()
        db.audit(user_id, "user", "aktion_vieraugen_freigabe",
                 {"id": action_id, "name": row["name"], "pruefer_id": pruefer_id})
    try:
        result = d.handler(json.loads(row["params"]))
        status, payload = "executed", {"ok": True, "result": result}
    except Exception as e:
        status, payload = "failed", {"ok": False, "error": f"{type(e).__name__}: {e}"}
    cur = conn.execute("UPDATE app_actions SET status=?, result=?, updated_at=? "
                       "WHERE id=? AND status='executing'",
                 (status, json.dumps(payload, ensure_ascii=False, default=str),
                  now_iso(), action_id))
    conn.commit()
    if cur.rowcount != 1:   # externer Eingriff während der Ausführung — laut machen, nicht schlucken
        db.audit(user_id, "system", "aktion_endstatus_verfehlt",
                 {"id": action_id, "name": row["name"], "status": status})
    db.audit(user_id, "user", "aktion_freigegeben",
             {"id": action_id, "name": row["name"], "status": status})
    _melde_entscheidung(on_entscheidung, registry, row, approve, status)
    return {"id": action_id, "status": status, **payload}
