"""Lauf-Verwaltung der Agenten-Regie (Z4.2-B, docs/63 §1/§3) — Core-DB.

Ausführungszustand wohnt beim Ausführenden (E4.2): ``agent_laeufe`` (Core-DB, Schema =
Vertrag ``appkit.agenten.SCHEMA_LAEUFE_SQL``) trägt den **Definition-Snapshot** (reload-fest,
Audit, kein Cross-DB-Join — ein später editierter Agent verfälscht nie die Historie), die
**Guardrail-Zähler** und das **stop_signal**.

**Stop (P1):** der Persistenz-Wrapper prüft je konsumiertem Event das ``stop_signal`` und
schließt den Iterator (``aclose``) ⇒ Stop wirkt an der nächsten Token-/Tool-Grenze, ohne in
``stream_agent`` einzugreifen.

**nutzung (Q1-Anker ``RuntimeEreignis.ende.nutzung``):** der SLOT ist verdrahtet — ein
``('nutzung', …)``-Event der Runtime wird in die Zeile gemergt. Er bleibt leer, solange
``agent.py`` roh gegen Ollama streamt (statt über ``appkit.runtime``, FP-3 M2–M9); das ist
KEIN späteres Neu-Verkabeln, nur ein noch leerer Wert (ehrliche Q1-Vorbedingung, docs/63 §0).
Ebenso ``runden``: die Rundengrenzen sind ``agent.py``-intern und werden erst mit demselben
Q1-Umbau sichtbar; bis dahin ehrlich 0.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, AsyncIterator

from appkit.agenten import AgentBudget, AgentDef, SCHEMA_LAEUFE_SQL
from appkit import ereignis_spine

from .. import db
from . import orchestrator as orch
from .agent import AgentEvent, stream_agent
from .tools import ToolSpec

STATUS_LAEUFT = "laeuft"
STATUS_FERTIG = "fertig"
STATUS_GESTOPPT = "gestoppt"
STATUS_FEHLER = "fehler"


# RG-2c (docs/83 §1): Lauf-Telemetrie (die agenten.EREIGNISSE) fließt als ZEIGER in den
# Core-Spine. Je Typ NUR skalare Zeiger-Felder — Freitext wie der Delegations-'auftrag'
# oder der 'fehler'-Text (orchestrator.senke) bleibt DRAUSSEN (Zeiger, nie Inhalt).
_LAUF_FELDER: dict[str, tuple[str, ...]] = {
    "lauf_gestartet": ("agent",),
    "runde":          ("agent", "ebene", "nummer"),
    "delegation":     ("worker", "ebene"),
    "tool_aufruf":    ("agent", "ebene", "tool"),
    "hitl_wartet":    ("agent", "aktion"),
    "lauf_ende":      ("agent", "tool_aufrufe", "delegationen"),
    "lauf_stop":      ("grund",),
}
_EREIGNIS_REGISTER = ereignis_spine.EreignisTypRegister("core")
for _typ, _felder in _LAUF_FELDER.items():
    _EREIGNIS_REGISTER.register(_typ, _felder)


def _spine_lauf_ereignis(user_id: str, lauf_id: str, name: str,
                         daten: dict[str, Any]) -> None:
    """Ein Lauf-Ereignis als Zeiger in den Core-Spine — NUR die registrierten skalaren
    Felder je Typ (Freitext/None fliegt kommentarlos). Best-effort: Telemetrie darf
    einen Lauf NIE kippen (eigener commit, Fehler geschluckt)."""
    felder = _LAUF_FELDER.get(name)
    if felder is None:
        return
    payload = {k: daten[k] for k in felder
               if k in daten and isinstance(daten[k], (str, int, float, bool))}
    try:
        conn = db.get_conn()
        ereignis_spine.ereignis_anlegen(
            conn, user_id, name, register=_EREIGNIS_REGISTER,
            ref=f"core:lauf:{lauf_id}", payload=payload, quelle_sens="hoechst")
        conn.commit()
    except Exception:
        pass


def _ensure_schema() -> None:
    """Idempotent: legt ``agent_laeufe`` + die Spine-Tabelle ``ereignisse`` an, ohne das
    zentrale core-``_SCHEMA`` anzufassen (CREATE TABLE IF NOT EXISTS = rein additiv)."""
    conn = db.get_conn()
    conn.executescript(SCHEMA_LAEUFE_SQL)
    conn.executescript(ereignis_spine.SCHEMA_EREIGNISSE_SQL)   # RG-2c: Core-Spine (additiv)
    conn.commit()


def schnappschuss(agent: AgentDef, resolver: orch.Resolver) -> dict[str, Any]:
    """JSON-Snapshot der AUFGELÖSTEN Agent-Definition (Wurzel + erreichbarer Sub-Baum) zum
    Startzeitpunkt — Audit + reload-fest (docs/63 §1). Reuse/Zyklen sind egal (``seen``)."""
    gesehen: dict[str, Any] = {}

    def _geh(a: AgentDef) -> None:
        if a.id in gesehen:
            return
        gesehen[a.id] = asdict(a)
        for sid in a.sub_agenten:
            w = resolver(sid)
            if w is not None:
                _geh(w)

    _geh(agent)
    return {"wurzel": agent.id, "agenten": gesehen}


def lauf_anlegen(user_id: str, agent: AgentDef, definition_snapshot: dict[str, Any]) -> str:
    """Legt eine Lauf-Zeile an (status='laeuft', Definition-Snapshot eingefroren)."""
    _ensure_schema()
    lauf_id = db.new_id()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO agent_laeufe (id, user_id, agent_id, definition, status, started_at) "
        "VALUES (?,?,?,?,?,?)",
        (lauf_id, user_id, agent.id,
         json.dumps(definition_snapshot, ensure_ascii=False), STATUS_LAEUFT, db.now_iso()))
    conn.commit()
    db.audit(user_id, "system", "agent_lauf_gestartet",
             {"lauf_id": lauf_id, "agent_id": agent.id})
    return lauf_id


def stop_anfordern(user_id: str, lauf_id: str) -> bool:
    """Setzt ``stop_signal`` (P1). Wirkt nur auf laufende Läufe; True = gesetzt."""
    _ensure_schema()
    conn = db.get_conn()
    cur = conn.execute("UPDATE agent_laeufe SET stop_signal=1 WHERE id=? AND user_id=? "
                       "AND status=?", (lauf_id, user_id, STATUS_LAEUFT))
    conn.commit()
    if cur.rowcount:
        db.audit(user_id, "user", "agent_lauf_stop", {"lauf_id": lauf_id})
    return cur.rowcount > 0


def _stop_gesetzt(lauf_id: str) -> bool:
    row = db.get_conn().execute(
        "SELECT stop_signal FROM agent_laeufe WHERE id=?", (lauf_id,)).fetchone()
    return bool(row and row["stop_signal"])


def _finalisieren(lauf_id: str, status: str, zustand: orch.LaufZustand,
                  fehler: str, nutzung: dict[str, Any]) -> None:
    conn = db.get_conn()
    conn.execute(
        "UPDATE agent_laeufe SET status=?, tool_aufrufe=?, delegationen=?, nutzung=?, "
        "fehler=?, ended_at=? WHERE id=?",
        (status, zustand.tool_aufrufe, zustand.delegationen,
         json.dumps(nutzung, ensure_ascii=False), fehler or zustand.fehler,
         db.now_iso(), lauf_id))
    conn.commit()


def lauf_fehler(user_id: str, lauf_id: str, grund: str) -> bool:
    """Beendet einen NOCH LAUFENDEN Lauf ehrlich als 'fehler' — für Setup-/Katalog-Fehler
    VOR ``lauf_streamen`` (sonst bliebe die Zeile 'laeuft' hängen, §6.5 „nie hängend").
    Wirkt NUR auf ``status='laeuft'`` (schon finalisierte Läufe bleiben unangetastet ⇒
    kein falsches Rück-Kippen eines fertigen Laufs). True = finalisiert."""
    _ensure_schema()
    row = db.get_conn().execute(
        "SELECT status FROM agent_laeufe WHERE id=? AND user_id=?",
        (lauf_id, user_id)).fetchone()
    if row is None or row["status"] != STATUS_LAEUFT:
        return False
    _finalisieren(lauf_id, STATUS_FEHLER, orch.LaufZustand(budget=AgentBudget()), grund, {})
    return True


def _public(row) -> dict[str, Any]:
    return {"id": row["id"], "agent_id": row["agent_id"], "status": row["status"],
            "runden": row["runden"], "tool_aufrufe": row["tool_aufrufe"],
            "delegationen": row["delegationen"], "nutzung": json.loads(row["nutzung"] or "{}"),
            "fehler": row["fehler"], "started_at": row["started_at"],
            "ended_at": row["ended_at"]}


def lauf_holen(user_id: str, lauf_id: str) -> dict[str, Any] | None:
    _ensure_schema()
    row = db.get_conn().execute(
        "SELECT * FROM agent_laeufe WHERE id=? AND user_id=?", (lauf_id, user_id)).fetchone()
    if row is None:
        return None
    d = _public(row)
    d["definition"] = json.loads(row["definition"] or "{}")
    return d


def laeufe_liste(user_id: str, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Task-Ledger (P8): Läufe je Nutzer, jüngste zuerst."""
    _ensure_schema()
    q = "SELECT * FROM agent_laeufe WHERE user_id=?"
    params: list[Any] = [user_id]
    if status:
        q += " AND status=?"; params.append(status)
    q += " ORDER BY started_at DESC LIMIT ?"
    params.append(min(max(limit, 1), 200))
    return [_public(r) for r in db.get_conn().execute(q, params).fetchall()]


async def lauf_streamen(user_id: str, lauf_id: str, agent: AgentDef, auftrag: str, *,
                        katalog: list[ToolSpec], resolver: orch.Resolver,
                        runtime: orch.Runtime = stream_agent,
                        profil: Any = None) -> AsyncIterator[AgentEvent]:
    """Fährt den Lauf über den Orchestrator und PERSISTIERT ihn. Prüft je Event das
    ``stop_signal`` (Stop ≤1 Event später, aclose), fängt Fehler ehrlich ab (status='fehler'
    + Grund, kein Prozess-Crash) und finalisiert die Zeile IMMER (finally)."""
    zustand = orch.LaufZustand(budget=agent.budget)
    nutzung: dict[str, Any] = {}

    def senke(name: str, daten: dict[str, Any]) -> None:
        if name == "nutzung":                    # Q1-Slot: Engine-Zähler mergen, wenn geliefert
            nutzung.update(daten or {})
            return
        _spine_lauf_ereignis(user_id, lauf_id, name, daten or {})   # RG-2c: Zeiger in Core-Spine

    agen = orch.stream_lauf(agent, auftrag, katalog=katalog, resolver=resolver,
                            runtime=runtime, zustand=zustand, senke=senke, profil=profil)
    status, fehler = STATUS_FERTIG, ""
    try:
        async for ev in agen:
            if _stop_gesetzt(lauf_id):
                status = STATUS_GESTOPPT
                yield ("lauf", {"status": STATUS_GESTOPPT, "grund": "stop_signal"})
                break
            yield ev
    except Exception as e:   # noqa: BLE001 — Lauf endet ehrlich, kippt den Prozess nie
        status, fehler = STATUS_FEHLER, f"{type(e).__name__}: {e}"
        yield ("lauf", {"status": STATUS_FEHLER, "fehler": fehler})
    finally:
        await agen.aclose()                      # Runtime-Iterator schließen (Stop/Cleanup)
        _finalisieren(lauf_id, status, zustand, fehler, nutzung)
