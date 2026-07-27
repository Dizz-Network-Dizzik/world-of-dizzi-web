"""Schatten-Protokoll der Autonomie-Treppe (RG-4, docs/83 §3) — Core-DB.

In der Stufe ``beobachten`` (T0, die neue Null) führt ein Agent seine read-Tools aus,
aber jede SCHREIB-Absicht wird **weder ausgeführt noch vorgeschlagen** — sie landet
hier als Schatten-Eintrag (lauf-gebunden). Das ist zweierlei zugleich (docs/83 §3):

- der **sichere Karriere-Start** jedes Agenten (Zuschauen vor Handeln), und
- das **Eichungs-Rohmaterial** (§4): was HÄTTE der Agent getan — verglichen später
  gegen Davids echte Entscheidungen.

Schatten-Einträge sind bewusst KEINE Inbox-Einträge (die Inbox bleibt rauschfrei für
echte Entscheidungen). Retention 30 Tage (Betriebsdaten, nicht Beleg-Ledger). Der
Agent erfährt den Schatten-Modus EHRLICH über das Tool-Ergebnis (kein vorgetäuschter
Vollzug — sonst lügt sein Abschlussbericht); das erzwingt ``agenten_hitl.aktions_tool``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from .. import db

#: Schreibt einen Schatten-Eintrag: (aktion_name, params, warum) → ``{"id": …}``.
#: Gleiche Signatur-Idee wie ``agenten_hitl.ProposeFn`` — der HITL-Wrapper ruft je
#: nach wirksamer Stufe das eine ODER das andere (Vorschlag vs. Schatten).
SchattenFn = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]

BEHALTE_TAGE = 30                       # Retention (Betriebsdaten, docs/83 §3)

SCHEMA_SCHATTEN_SQL = """
CREATE TABLE IF NOT EXISTS agent_schatten (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  agent_id    TEXT NOT NULL,
  lauf_id     TEXT NOT NULL,
  aktion_name TEXT NOT NULL,
  params      TEXT NOT NULL DEFAULT '{}',
  warum       TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_schatten ON agent_schatten (user_id, agent_id, created_at);
"""


def _ensure_schema() -> None:
    """Idempotent: legt ``agent_schatten`` additiv in der Core-DB an (CREATE IF NOT
    EXISTS), ohne das zentrale core-``_SCHEMA`` anzufassen."""
    conn = db.get_conn()
    conn.executescript(SCHEMA_SCHATTEN_SQL)
    conn.commit()


def schatten_anlegen(user_id: str, agent_id: str, lauf_id: str, aktion_name: str,
                     params: dict[str, Any] | None = None, warum: str = "") -> str:
    """Protokolliert EINE nicht-ausgeführte Schreib-Absicht (Beobachtungs-Modus).
    Gibt die Schatten-ID zurück. ``params`` wird JSON-serialisiert (nur der Zeiger auf
    die Absicht — Inhalte holt sich später niemand daraus, das ist Betriebsdatum)."""
    _ensure_schema()
    sid = db.new_id()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO agent_schatten (id, user_id, agent_id, lauf_id, aktion_name, "
        "params, warum, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (sid, user_id, agent_id, lauf_id, aktion_name,
         json.dumps(params or {}, ensure_ascii=False), warum, db.now_iso()))
    conn.commit()
    return sid


def schatten_liste(user_id: str, *, agent_id: str = "", lauf_id: str = "",
                   limit: int = 100) -> list[dict[str, Any]]:
    """Schatten-Einträge (Eichungs-Rohmaterial, §4) — jüngste zuerst, optional je
    Agent/Lauf gefiltert. Read-only-Projektion für die Eichungs-Karte."""
    _ensure_schema()
    q = "SELECT * FROM agent_schatten WHERE user_id=?"
    params: list[Any] = [user_id]
    if agent_id:
        q += " AND agent_id=?"; params.append(agent_id)
    if lauf_id:
        q += " AND lauf_id=?"; params.append(lauf_id)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    out = []
    for r in db.get_conn().execute(q, params).fetchall():
        out.append({"id": r["id"], "agent_id": r["agent_id"], "lauf_id": r["lauf_id"],
                    "aktion_name": r["aktion_name"], "params": json.loads(r["params"] or "{}"),
                    "warum": r["warum"], "created_at": r["created_at"]})
    return out


def schatten_zaehler(user_id: str) -> dict[str, int]:
    """Anzahl Schatten-Absichten je Agent (Eichungs-Karten-Ampel: „so oft hätte der
    Agent gehandelt")."""
    _ensure_schema()
    rows = db.get_conn().execute(
        "SELECT agent_id, COUNT(*) AS n FROM agent_schatten WHERE user_id=? "
        "GROUP BY agent_id", (user_id,)).fetchall()
    return {r["agent_id"]: int(r["n"]) for r in rows}


def aufraeumen(user_id: str, behalte_tage: int = BEHALTE_TAGE,
               *, jetzt_iso: str | None = None) -> int:
    """Retention (docs/83 §3): löscht Schatten-Einträge älter als ``behalte_tage``.
    Gibt die Anzahl gelöschter Zeilen zurück. ``jetzt_iso`` injizierbar (Test)."""
    _ensure_schema()
    jetzt = datetime.fromisoformat(jetzt_iso) if jetzt_iso else datetime.now(timezone.utc)
    grenze = (jetzt - timedelta(days=behalte_tage)).isoformat(timespec="seconds")
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM agent_schatten WHERE user_id=? AND created_at<?",
                       (user_id, grenze))
    conn.commit()
    return cur.rowcount


def default_schatten_factory(user_id: str) -> Callable[[str, str], SchattenFn]:
    """Produktions-Factory: bindet (agent_id, lauf_id) an eine ``schatten_fn``, die den
    Schatten-Eintrag in die Core-DB schreibt. Muster ``default_propose_factory`` — im
    Test durch eine Fake-Factory ersetzbar."""
    def factory(agent_id: str, lauf_id: str) -> SchattenFn:
        async def schatten_fn(aktion_name: str, params: dict[str, Any],
                              warum: str) -> dict[str, Any]:
            sid = schatten_anlegen(user_id, agent_id, lauf_id, aktion_name, params, warum)
            return {"id": sid, "status": "schatten"}
        return schatten_fn
    return factory
