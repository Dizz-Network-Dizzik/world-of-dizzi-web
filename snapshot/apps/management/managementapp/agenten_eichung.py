"""Eichungs-Poll — Management misst, Core zündet (RG-5, docs/83 §4).

**Der Prüfer hängt nicht vom Geprüften ab.** Zwei unabhängige Konsumenten desselben
replaybaren Spine-Logs sind der Sinn des Spine-Musters (docs/83 §1): der Core zündet
Läufe (``regie_cursor``), das Management misst die Eichung (EIGENER Cursor hier). Beide
lesen ``hitl_entschieden`` — die Label-Maschine: jede Approve/Reject-Entscheidung Davids
ist ein Ground-Truth-Datenpunkt, kostenlos und unverfälscht.

Der Poll (read-only, injizierbarer Fetcher wie die Netz-Inbox):
1. Je Quelle: Ereignisse ab dem EIGENEN Cursor ziehen (``fetch_fn``; Offline ⇒ ehrlich
   überspringen), je ``hitl_entschieden`` die laufende Beobachtung je (Agent × Klasse)
   fortschreiben, Cursor + Beobachtung in EINER Transaktion (idempotent: Re-Poll ohne
   neue Ereignisse zählt nicht doppelt).
2. Aus den Beobachtungen (+ optional Budget-Disziplin aus den Core-Läufen) die Eichung je
   (Agent × Klasse) rechnen und in ``agent_evals`` ablegen (``agenten_eval``).

**def_hash-Isolation:** die Beobachtung trägt den ``def_hash``, unter dem sie zählt.
Ändert sich die Definition (Prompt-/Tool-/Modell-Edit), setzt die nächste gezählte
Entscheidung die Beobachtung zurück — das gemessene Verhalten des alten Agenten zählt nie
für den neuen (Einzel-Nutzer-Realität [A-8]; strenger als bloß das ``eval_gueltig``-Gate).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from . import agenten_eval as ev

#: Fetcher-Signatur (injizierbar, wie ``InboxFetch``): (quelle_app, seit_seq) → Liste
#: roher Ereignisse (Form ``ereignis_spine.ereignisse_seit``). WIRFT bei Offline/Timeout
#: ⇒ die Quelle wird ehrlich übersprungen (nie still als „leer" gewertet).
EichungFetch = Callable[[str, int], "list[dict[str, Any]]"]

HITL_TYP = "hitl_entschieden"

#: Cursor je Quelle (Management-DB — der EIGENE, vom Core-``regie_cursor`` unabhängig) +
#: laufende Beobachtung je (Agent × Klasse) mit dem ``def_hash``, unter dem sie zählt.
#: ``deleted_at`` trägt jede user_id-Tabelle (Management-Konvention): die Soft-Delete-
#: Kaskade (``db.soft_delete_user``, KA-H1) räumt Cursor + Beobachtungen bei Konto-
#: Löschung mit — kein eigener on_delete-Hook nötig.
SCHEMA_EVAL_POLL = """
CREATE TABLE IF NOT EXISTS eval_cursor (
  user_id    TEXT NOT NULL,
  quelle_app TEXT NOT NULL,
  seq        INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  PRIMARY KEY (user_id, quelle_app)
);
CREATE TABLE IF NOT EXISTS eval_beobachtungen (
  user_id     TEXT NOT NULL,
  agent_id    TEXT NOT NULL,
  klasse      TEXT NOT NULL,
  def_hash    TEXT NOT NULL DEFAULT '',
  entschieden INTEGER NOT NULL DEFAULT 0,
  approved    INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT NOT NULL,
  deleted_at  TEXT,
  PRIMARY KEY (user_id, agent_id, klasse)
);
"""


def _cursor_holen(conn, user_id: str, quelle_app: str) -> int:
    row = conn.execute("SELECT seq FROM eval_cursor WHERE user_id=? AND quelle_app=? "
                       "AND deleted_at IS NULL", (user_id, quelle_app)).fetchone()
    return int(row["seq"]) if row else 0


def _cursor_setzen(conn, user_id: str, quelle_app: str, seq: int, jetzt_iso: str) -> None:
    conn.execute(
        "INSERT INTO eval_cursor (user_id, quelle_app, seq, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT (user_id, quelle_app) DO UPDATE SET seq=excluded.seq, "
        "updated_at=excluded.updated_at, deleted_at=NULL",
        (user_id, quelle_app, int(seq), jetzt_iso))


def _verbuchen(conn, user_id: str, agent_id: str, klasse: str, def_hash: str,
               approve: bool, jetzt_iso: str) -> None:
    """Schreibt EINE ``hitl_entschieden``-Entscheidung in die laufende Beobachtung fort.
    **def_hash-Isolation:** trägt die Bestands-Zeile einen ANDEREN ``def_hash`` (die
    Definition hat sich seit der letzten Zählung geändert), wird sie auf 0 zurückgesetzt,
    bevor gezählt wird — alte Verhaltens-Evidenz zählt nie für den neuen Agenten."""
    row = conn.execute(
        "SELECT def_hash, entschieden, approved FROM eval_beobachtungen "
        "WHERE user_id=? AND agent_id=? AND klasse=? AND deleted_at IS NULL",
        (user_id, agent_id, klasse)).fetchone()
    if row is None:
        entschieden, approved = 0, 0
    elif row["def_hash"] != def_hash:
        entschieden, approved = 0, 0            # Definition geändert ⇒ frisch zählen
    else:
        entschieden, approved = int(row["entschieden"]), int(row["approved"])
    entschieden += 1
    approved += 1 if approve else 0
    conn.execute(
        "INSERT INTO eval_beobachtungen (user_id, agent_id, klasse, def_hash, entschieden, "
        "approved, updated_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT (user_id, agent_id, klasse) DO UPDATE SET def_hash=excluded.def_hash, "
        "entschieden=excluded.entschieden, approved=excluded.approved, "
        "updated_at=excluded.updated_at, deleted_at=NULL",
        (user_id, agent_id, klasse, def_hash, entschieden, approved, jetzt_iso))


def poll_quelle(db, user_id: str, quelle_app: str, fetch_fn: EichungFetch,
                def_hash_fuer: Mapping[str, str], *, jetzt_iso: str) -> int:
    """Zieht die neuen Ereignisse EINER Quelle ab dem eigenen Cursor und verbucht die
    ``hitl_entschieden``-Entscheidungen (Cursor + Beobachtungen in EINER Tx — crash-fest,
    idempotent). Ereignisse zu unbekannten Agenten (nicht im gepushten Wald) werden
    übersprungen, aber der Cursor rückt über sie (sie sind bearbeitet). Gibt die Anzahl
    verbuchter Entscheidungen zurück. ``fetch_fn`` wirft bei Offline ⇒ der Aufrufer fängt."""
    conn = db.get_conn()
    seit = _cursor_holen(conn, user_id, quelle_app)
    events = fetch_fn(quelle_app, seit)
    verbucht = 0
    max_seq = seit
    for e in events or []:
        seq = int(e.get("seq", 0))
        if seq > max_seq:
            max_seq = seq
        if e.get("typ") != HITL_TYP:
            continue
        payload = e.get("payload") or {}
        agent_id = str(payload.get("agent_id") or "")
        if not agent_id or agent_id not in def_hash_fuer:
            continue                             # kein zugeordneter/lebender Agent
        klasse = str(e.get("klasse") or "")
        if not klasse:
            continue                             # ohne Klasse nicht zuordenbar
        _verbuchen(conn, user_id, agent_id, klasse, def_hash_fuer[agent_id],
                   bool(payload.get("approve")), jetzt_iso)
        verbucht += 1
    _cursor_setzen(conn, user_id, quelle_app, max_seq, jetzt_iso)
    conn.commit()                                # Cursor + Beobachtungen GEMEINSAM
    return verbucht


def budget_aus_laeufen(laeufe: Sequence[Mapping[str, Any]]) -> dict[str, tuple[int, int]]:
    """Aggregiert die Budget-Disziplin je Agent aus Core-Lauf-Zeilen (``agent_laeufe``):
    (Läufe, davon im Budget). „Im Budget" = der Lauf endete NICHT an einer Budget-/
    Laufzeit-Grenze (``fehler`` ohne ``budget``/``erschöpft``). Best-effort: fehlt die
    Core-Antwort, reicht der Aufrufer ``{}`` (Budget bleibt dann „nicht gemessen")."""
    out: dict[str, list[int]] = {}
    for r in laeufe or []:
        aid = str(r.get("agent_id") or "")
        if not aid:
            continue
        fehler = str(r.get("fehler") or "").lower()
        im_budget = not ("budget" in fehler or "erschöpft" in fehler or "laufzeit" in fehler)
        eintrag = out.setdefault(aid, [0, 0])
        eintrag[0] += 1
        eintrag[1] += 1 if im_budget else 0
    return {aid: (n, ok) for aid, (n, ok) in out.items()}


def eichung_rechnen(db, user_id: str, def_hash_fuer: Mapping[str, str], *,
                    golden_gruen: bool, jetzt_iso: str,
                    budget_fuer: Mapping[str, tuple[int, int]] | None = None,
                    verstoesse_fuer: Mapping[str, int] | None = None) -> list[dict[str, Any]]:
    """Rechnet aus den laufenden Beobachtungen (+ optional Budget/Verstöße) die Eichung je
    (Agent × Klasse) und legt sie in ``agent_evals`` ab (``agenten_eval.eval_speichern``).
    Nur Beobachtungen, deren ``def_hash`` zum AKTUELLEN passt (``def_hash_fuer``), werden
    gerechnet (veraltete zählen nicht). ``golden_gruen`` = das (deploy-/CI-gesetzte)
    Golden-Gate; ``budget_fuer``/``verstoesse_fuer`` = Agent-ID → (Läufe, im Budget) bzw.
    Verstoß-Zahl (fehlt ⇒ nicht gemessen bzw. 0). Gibt die gespeicherten Projektionen."""
    budget_fuer = budget_fuer or {}
    verstoesse_fuer = verstoesse_fuer or {}
    rows = db.get_conn().execute(
        "SELECT agent_id, klasse, def_hash, entschieden, approved FROM eval_beobachtungen "
        "WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        aid = r["agent_id"]
        aktuell = def_hash_fuer.get(aid)
        if not aktuell or r["def_hash"] != aktuell:
            continue                             # veraltete/verwaiste Beobachtung
        laeufe, im_budget = budget_fuer.get(aid, (0, 0))
        metriken = ev.EvalMetriken(
            entschieden=int(r["entschieden"]), approved=int(r["approved"]),
            verstoesse=int(verstoesse_fuer.get(aid, 0)),
            laeufe=int(laeufe), laeufe_im_budget=int(im_budget),
            golden_gruen=bool(golden_gruen))
        out.append(ev.eval_speichern(db, user_id, aid, r["klasse"], aktuell, metriken,
                                     quelle="eichung_poll", jetzt_iso=jetzt_iso))
    return out


def eichung_lauf(db, user_id: str, quellen: Sequence[str], fetch_fn: EichungFetch,
                 def_hash_fuer: Mapping[str, str], *, golden_gruen: bool, jetzt_iso: str,
                 budget_fuer: Mapping[str, tuple[int, int]] | None = None,
                 verstoesse_fuer: Mapping[str, int] | None = None) -> dict[str, Any]:
    """EIN vollständiger Eichungs-Lauf (docs/83 §4): alle Quellen pollen (Offline ehrlich
    überspringen), dann die Eichung rechnen. Gibt ``{gepollt, quellen_offline, verbucht,
    evals}`` — die Regie-Zentrale zeigt Offline-Quellen ehrlich statt still leer."""
    verbucht = 0
    offline: list[str] = []
    for quelle in quellen:
        try:
            verbucht += poll_quelle(db, user_id, quelle, fetch_fn, def_hash_fuer,
                                    jetzt_iso=jetzt_iso)
        except (OSError, ValueError, TimeoutError):
            offline.append(quelle)
    evals = eichung_rechnen(db, user_id, def_hash_fuer, golden_gruen=golden_gruen,
                            jetzt_iso=jetzt_iso, budget_fuer=budget_fuer,
                            verstoesse_fuer=verstoesse_fuer)
    return {"gepollt": len(quellen) - len(offline), "quellen_offline": offline,
            "verbucht": verbucht, "evals": evals}
