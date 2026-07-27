"""RG-8 (docs/83 §6): der geld-Boden — ``beleg_vorschlagen`` bleibt IMMER pre_approval.

Der Boden-Beweis der Akzeptanz: die Geschäfts-Weiche schlägt Belege/Fristen VOR, Money BUCHT
(nie der Agent). Für ``finanzen`` (Klasse ``geld``, ``KLASSEN_BODEN``) pinnt ``wirksame_stufe``
das Ergebnis auf ``pre_approval`` — selbst bei Bereichs-Treppe autonom + eval grün. Bewiesen
pur UND auf dem echten Katalog-/Orchestrator-Pfad (Konserven-Runtime).
"""

from __future__ import annotations

from appkit.agenten import wirksame_stufe
from app.ai.mcp_gateway import ist_aktions_name
from eval_harness import agent, lauf_szenario

BELEG = "finanzen_beleg_vorschlagen"     # money — Klasse geld (Boden pre_approval)
FRIST = "admin_frist_vorschlagen"        # admin — Klasse entwurf


def test_geschaefts_verben_werden_als_aktion_erkannt():
    """``*_vorschlagen`` ist ein Aktions-Muster ⇒ beide Verträge werden propose-gewrappt."""
    assert ist_aktions_name(BELEG) is True
    assert ist_aktions_name(FRIST) is True


def test_geld_boden_pre_approval_auch_bei_treppe_und_eval():
    """geld: selbst Bereich ``autonom_audit`` + Agent ``autonom_audit`` + eval grün ⇒
    pre_approval (KLASSEN_BODEN als Obergrenze — kein Pfad bucht ohne Freigabe)."""
    s = wirksame_stufe("geld", bereich_stufe="autonom_audit",
                       agent_stufe="autonom_audit", eval_gruen=True)
    assert s == "pre_approval"


def test_beleg_vorschlag_proposet_nie_auto_egal_treppe():
    """Echter Pfad: ein Orchestrator mit ``beleg_vorschlagen``-Grant (geld:pre_approval), der
    Bereich lockert MAXIMAL (geld=autonom_audit) — die Aktion landet trotzdem als Inbox-
    Vorschlag (Klasse geld, pre_approval), nie Auto-Freigabe, nie Schatten. Money bucht nie
    automatisch (docs/83 §6)."""
    orch = agent("manager", werkzeuge=(BELEG,), autonomie={"geld": "pre_approval"})
    traj = lauf_szenario(orch, [orch], {"manager": [
        {"tool": BELEG, "args": {"betrag_minor": 12300, "warum": "Rechnung erkannt"}}]},
        bereich_stufen={"manager": {"geld": "autonom_audit"}})
    assert len(traj.proposes) == 1 and traj.schatten == []
    assert traj.proposes[0]["aktion"] == "beleg_vorschlagen"
    assert traj.proposes[0]["app"] == "finanzen"
