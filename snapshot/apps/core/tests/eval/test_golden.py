"""Golden-Szenarien (RG-5, docs/83 §4.1): erlaubte Trajektorien, deterministisch.

Jedes Szenario prüft eine Trajektorie-Invariante des echten Katalog-/Orchestrator-Pfads:
read-only reicht durch (kein Seiteneffekt), Schreib-Aktionen sind an ihre Stufe gebunden
(pre_approval ⇒ propose, beobachten ⇒ schatten, WARUM Pflicht), das Budget endet ehrlich,
Delegation läuft. Kein Ollama — die Runtime ist eine Konserve (eval_harness).
"""

from __future__ import annotations

from appkit.agenten import AgentBudget
from eval_harness import agent, lauf_szenario, read_tool


def test_golden_read_only_kein_seiteneffekt():
    """Ein Lauf, der nur liest, verändert nichts: read-Tool läuft, 0 propose/0 schatten."""
    a = agent("orch", werkzeuge=("news_lesen",))
    traj = lauf_szenario(a, [a], {"orch": [{"tool": "news_lesen"}]},
                         read=[read_tool("news_lesen")])
    assert traj.tool_aufrufe == ["news_lesen"]
    assert traj.proposes == [] and traj.schatten == [] and traj.verweigert == []


def test_golden_schreibaktion_pre_approval_proposet():
    """T1/pre_approval: die Schreib-Aktion wird als Inbox-Vorschlag angelegt — WAS+WARUM
    getrennt, agent_id gebunden, nie direkt ausgeführt (Vorschlags-Struktur)."""
    a = agent("orch", werkzeuge=("kommunikation_email_senden",),
              autonomie={"aussenwirkung": "pre_approval"})
    traj = lauf_szenario(a, [a], {"orch": [{"tool": "kommunikation_email_senden",
                                            "args": {"an": "k@x.org", "warum": "Kunde wartet"}}]})
    assert len(traj.proposes) == 1 and traj.schatten == []
    p = traj.proposes[0]
    assert p["app"] == "kommunikation" and p["aktion"] == "email_senden"
    assert p["params"] == {"an": "k@x.org"} and p["warum"] == "Kunde wartet"
    assert p["agent_id"] == "orch"


def test_golden_unkonfiguriert_schattet_statt_propose():
    """T0/beobachten (unkonfiguriert = die neue Null, V-1): die Schreib-Absicht landet im
    Schatten-Protokoll — weder ausgeführt noch vorgeschlagen (die Inbox bleibt rauschfrei)."""
    a = agent("orch", werkzeuge=("kommunikation_email_senden",))   # leere autonomie
    traj = lauf_szenario(a, [a], {"orch": [{"tool": "kommunikation_email_senden",
                                            "args": {"an": "k@x.org", "warum": "x"}}]})
    assert traj.proposes == [] and len(traj.schatten) == 1
    assert traj.schatten[0]["name"] == "kommunikation_email_senden"


def test_golden_warum_pflicht_kein_seiteneffekt():
    """Ohne WARUM passiert nichts (fail-closed §3.F) — kein Vorschlag, kein Schatten."""
    a = agent("orch", werkzeuge=("kommunikation_email_senden",),
              autonomie={"aussenwirkung": "pre_approval"})
    traj = lauf_szenario(a, [a], {"orch": [{"tool": "kommunikation_email_senden",
                                            "args": {"an": "k@x.org"}}]})   # kein warum
    assert traj.proposes == [] and traj.schatten == []
    assert "WARUM ist Pflicht" in traj.ergebnis


def test_golden_budget_endet_ehrlich():
    """Budget-Einhaltung: bei max_tool_aufrufe=2 endet der 3. Aufruf EHRLICH (Fehlertext +
    zustand.fehler), nie stilles Kappen."""
    a = agent("orch", werkzeuge=("news_lesen",), budget=AgentBudget(max_tool_aufrufe=2))
    traj = lauf_szenario(a, [a], {"orch": [{"tool": "news_lesen"}] * 3},
                         read=[read_tool("news_lesen")])
    assert "Budget" in traj.fehler and "erschöpft" in traj.fehler


def test_golden_delegation_laeuft_und_bleibt_flach():
    """Delegation: der Orchestrator delegiert an einen Worker, der Worker liest — die
    Trajektorie zeigt beide Ebenen (Worker-als-Tool, docs/63 §3)."""
    orch_a = agent("orch", sub_agenten=("worker",))
    worker = agent("worker", werkzeuge=("news_lesen",))
    traj = lauf_szenario(orch_a, [orch_a, worker], {
        "orch": [{"tool": "delegiere_worker", "args": {"auftrag": "lies news"}}],
        "worker": [{"tool": "news_lesen"}],
    }, read=[read_tool("news_lesen")])
    assert "delegiere_worker" in traj.tool_aufrufe    # Orchestrator delegierte
    assert "news_lesen" in traj.tool_aufrufe          # der Worker lief wirklich
    assert traj.proposes == [] and traj.schatten == []
