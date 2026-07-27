"""Vertrags-Tests für appkit/agenten.py (FP-4-Stub — docs/63).

Pinnt den VERTRAG (fail-closed-Autonomie, Baum-Grenzen, deny-by-default-Grants,
Schema-Gültigkeit, Projektions-Formen), nicht eine Implementierung — Z4.1/Z4.2
(Bau-KI) müssen exakt diese Semantik erfüllen. Komplett Runtime-/Ollama-frei."""

from __future__ import annotations

import pytest

from appkit import agenten as ag
from appkit import modellprofil as mp


# --- Schema = Vertrag: muss heute parsen ------------------------------------------

def test_schema_agenten_parst():
    ag.schema_pruefen(ag.SCHEMA_AGENTEN_SQL)


def test_schema_laeufe_parst():
    ag.schema_pruefen(ag.SCHEMA_LAEUFE_SQL)


def test_inbox_zusatzspalten_als_alter_gueltig():
    # Der Bau (Z4.1-B) hängt sie per idempotentem ALTER an app_actions —
    # die Spalten-Definitionen müssen als SQL gültig sein.
    basis = "CREATE TABLE app_actions (id TEXT PRIMARY KEY);"
    alter = "".join(f"ALTER TABLE app_actions ADD COLUMN {n} {d};"
                    for n, d in ag.INBOX_ZUSATZSPALTEN)
    ag.schema_pruefen(basis + alter)


# --- Baum-Wächter (D5-b: flach, zyklenfrei) ---------------------------------------

def test_baum_drei_ebenen_ok():
    ag.validiere_agentenbaum("o", {"o": ["w1", "w2"], "w1": ["s1"]})


def test_baum_vierte_ebene_verweigert():
    with pytest.raises(ValueError, match="zu tief"):
        ag.validiere_agentenbaum("o", {"o": ["a"], "a": ["b"], "b": ["c"]})


def test_baum_zyklus_verweigert():
    with pytest.raises(ValueError, match="Zyklus"):
        ag.validiere_agentenbaum("o", {"o": ["a"], "a": ["o"]})


def test_baum_selbstdelegation_verweigert():
    with pytest.raises(ValueError, match="Zyklus"):
        ag.validiere_agentenbaum("o", {"o": ["o"]})


def test_baum_worker_reuse_in_zwei_aesten_erlaubt():
    # Reuse ist kein Zyklus: derselbe Worker unter zwei Ästen ist ok.
    ag.validiere_agentenbaum("o", {"o": ["a", "b"], "a": ["w"], "b": ["w"]})


# --- Autonomie: fail-closed in jeder Richtung -------------------------------------

def test_geld_und_gesundheit_boden_unlockbar():
    for klasse in ("geld", "gesundheit"):
        assert ag.wirksame_stufe(klasse, bereich_stufe="autonom_audit",
                                 agent_stufe="autonom_audit",
                                 eval_gruen=True) == "pre_approval"


def test_beobachten_ist_die_neue_null():
    # V-1 (docs/83 §3): 'beobachten' ist Index 0 — die strengste Stufe, der
    # fail-closed-Default für alles Unbekannte/Unkonfigurierte.
    assert ag.AUTONOMIE_STUFEN[0] == "beobachten"
    assert ag.AUTONOMIE_STUFEN == ("beobachten", "pre_approval", "monitored",
                                   "autonom_audit")


def test_unbekannte_klasse_fail_closed_beobachten():
    # V-1.1: unbekannte Klasse ⇒ Kappe 'beobachten' (strenger als früher pre_approval).
    assert ag.wirksame_stufe("quatsch", bereich_stufe="autonom_audit",
                             agent_stufe="autonom_audit", eval_gruen=True) == "beobachten"


def test_unkonfiguriert_ist_beobachten():
    # V-1.2: der sichere Default eines unkonfigurierten Agenten ist Zuschauen.
    assert ag.wirksame_stufe("aussenwirkung") == "beobachten"
    assert ag.wirksame_stufe("entwurf", agent_stufe=None, bereich_stufe=None) == "beobachten"


def test_geld_gesundheit_koennen_beobachten_aber_nie_hoeher():
    # V-1.1: KLASSEN_BODEN als OBERGRENZE — 'beobachten' (strenger) ist erlaubt,
    # über pre_approval kommen geld/gesundheit nie.
    for klasse in ("geld", "gesundheit"):
        assert ag.wirksame_stufe(klasse, bereich_stufe="beobachten",
                                 agent_stufe="beobachten") == "beobachten"
        assert ag.wirksame_stufe(klasse, bereich_stufe="autonom_audit",
                                 agent_stufe="autonom_audit",
                                 eval_gruen=True) == "pre_approval"


def test_bereich_none_setzt_keine_kappe_agent_regiert():
    # V-1.3: bereich_stufe=None = „Bereich setzt keine Kappe" (Obergrenze) ⇒ die
    # Agent-Stufe regiert (der Core-Katalog kennt die Bereichs-Matrix nicht). Ein
    # KONFIGURIERTER Agent kann so vorschlagen, ein unkonfigurierter bleibt beobachten.
    assert ag.wirksame_stufe("aussenwirkung", bereich_stufe=None,
                             agent_stufe="pre_approval") == "pre_approval"
    assert ag.wirksame_stufe("aussenwirkung", bereich_stufe=None,
                             agent_stufe=None) == "beobachten"


def test_restriktivste_politik_gewinnt():
    assert ag.wirksame_stufe("aussenwirkung", bereich_stufe="autonom_audit",
                             agent_stufe="monitored",
                             eval_gruen=True) == "monitored"
    assert ag.wirksame_stufe("aussenwirkung", bereich_stufe="pre_approval",
                             agent_stufe="autonom_audit",
                             eval_gruen=True) == "pre_approval"


def test_q2_klemme_ohne_eval_kein_lockern():
    # Klemme klemmt zurück auf pre_approval — NICHT tiefer (V-1.3: wer mehr wollte,
    # darf wenigstens vorschlagen).
    assert ag.wirksame_stufe("entwurf", bereich_stufe="monitored",
                             agent_stufe="monitored") == "pre_approval"
    assert ag.wirksame_stufe("entwurf", bereich_stufe="monitored",
                             agent_stufe="monitored",
                             eval_gruen=True) == "monitored"


def test_unbekannte_stufe_ist_beobachten_fail_closed():
    # Ein ungültiger (Nicht-None-)Stufenwert ⇒ Index 0 = beobachten (fail-closed),
    # nicht permissiv.
    assert ag.wirksame_stufe("entwurf", bereich_stufe="turbo",
                             agent_stufe="autonom_audit",
                             eval_gruen=True) == "beobachten"


def test_stufe_erlaubt_ausfuehrung():
    assert not ag.stufe_erlaubt_ausfuehrung("beobachten")
    assert not ag.stufe_erlaubt_ausfuehrung("pre_approval")
    assert not ag.stufe_erlaubt_ausfuehrung("unfug")
    assert ag.stufe_erlaubt_ausfuehrung("monitored")
    assert ag.stufe_erlaubt_ausfuehrung("autonom_audit")


def test_stufe_erlaubt_vorschlag():
    # V-1.4: beobachten (und Unbekanntes) ⇒ kein Vorschlag (Schatten); ab pre_approval ja.
    assert not ag.stufe_erlaubt_vorschlag("beobachten")
    assert not ag.stufe_erlaubt_vorschlag("unfug")
    assert ag.stufe_erlaubt_vorschlag("pre_approval")
    assert ag.stufe_erlaubt_vorschlag("monitored")
    assert ag.stufe_erlaubt_vorschlag("autonom_audit")


def test_stufe_ueber_kappe():
    # geld/gesundheit: monitored/autonom_audit verletzen die Obergrenze, beobachten/
    # pre_approval nicht. entwurf/aussenwirkung haben keine Kappe. Unbekannte Klasse:
    # nur beobachten ist zulässig.
    assert ag.stufe_ueber_kappe("geld", "monitored")
    assert ag.stufe_ueber_kappe("gesundheit", "autonom_audit")
    assert not ag.stufe_ueber_kappe("geld", "pre_approval")
    assert not ag.stufe_ueber_kappe("gesundheit", "beobachten")
    assert not ag.stufe_ueber_kappe("entwurf", "autonom_audit")
    assert ag.stufe_ueber_kappe("quatsch", "pre_approval")
    assert not ag.stufe_ueber_kappe("quatsch", "beobachten")


def test_boost_nur_normal_und_freigegeben():
    # G-FP4-BOOST: normal-App + freigegeben ⇒ Außenzugriff erlaubt.
    assert ag.boost_erlaubt(setting_erlaubt=True, sensitivitaet="normal")
    # nicht freigegeben (Lokal-pur-Default 'aus') ⇒ kein Außenzugriff.
    assert not ag.boost_erlaubt(setting_erlaubt=False, sensitivitaet="normal")
    # Sensitivitäts-Sperre: hoch/höchst NIE, auch wenn freigegeben (unantastbar).
    for s in ("hoch", "höchst", "hoechst", "unbekannt", ""):
        assert not ag.boost_erlaubt(setting_erlaubt=True, sensitivitaet=s)


def test_klasse_von_level_streng_bei_unbekanntem():
    assert ag.klasse_von_level("lokal") == "entwurf"
    assert ag.klasse_von_level("verifiziert") == "aussenwirkung"
    assert ag.klasse_von_level("hochsicher") == "geld"
    assert ag.klasse_von_level("???") == "geld"


# --- Tool-Grants: deny-by-default -------------------------------------------------

def test_werkzeuge_filter_schnittmenge_und_ordnung():
    assert ag.werkzeuge_filter(["b", "x", "a", "b"], ["a", "b", "c"]) == ("b", "a")
    assert ag.werkzeuge_filter([], ["a"]) == ()
    assert ag.werkzeuge_filter(["a"], []) == ()


def test_delegations_toolname_slug():
    assert ag.delegations_toolname("Mail-Triage 1") == "delegiere_mail_triage_1"
    assert ag.delegations_toolname("  ") == "delegiere_agent"


# --- Entität + Projektionen -------------------------------------------------------

def test_budget_defaults_paritaet_max_rounds():
    # Parität zu core agent.MAX_ROUNDS (=4): der Vertrag ändert kein Verhalten.
    assert ag.AgentBudget().max_runden == 4


def test_modell_praezedenz_explizit_vor_profil():
    a = ag.AgentDef(id="a1", name="A", task_klasse="chat")
    assert a.modell_fuer(mp.STUFE_0) == "qwen3:14b"          # Profil-Slot
    b = ag.AgentDef(id="a2", name="B", modell_explizit="spezial:7b")
    assert b.modell_fuer(mp.STUFE_0) == "spezial:7b"          # Override gewinnt
    c = ag.AgentDef(id="a3", name="C", task_klasse="voice")   # dormanter Slot
    assert c.modell_fuer(mp.STUFE_0) is None


def test_agent_karte_zeigt_wirksame_tools():
    a = ag.AgentDef(id="a1", name="Mailer", rolle="E-Mail-Triage",
                    werkzeuge=("kommunikation_mail_lesen", "tippfehler"),
                    autonomie={"aussenwirkung": "monitored"})
    karte = ag.agent_karte(a, werkzeug_katalog=("kommunikation_mail_lesen",))
    assert karte["rolle"] == "E-Mail-Triage"
    assert karte["tools"] == ["kommunikation_mail_lesen"]     # Tippfehler raus
    assert karte["wissen"]["bereich_id"] == ""
    assert karte["grenzen"]["max_runden"] == 4
    assert karte["grenzen"]["autonomie"] == {"aussenwirkung": "monitored"}


def test_inbox_eintrag_was_warum_argumente():
    zeile = {"id": "x1", "name": "email_senden", "warum": "Kunde wartet",
             "params": {"an": "k@example.org"}, "agent_id": "a1",
             "lauf_id": "l1", "status": "pending", "created_at": "2026-07-03"}
    e = ag.inbox_eintrag("kommunikation", zeile, "verifiziert")
    assert (e["was"], e["warum"]) == ("email_senden", "Kunde wartet")
    assert e["argumente"] == {"an": "k@example.org"}
    assert e["klasse"] == "aussenwirkung"
    assert (e["app_id"], e["agent_id"], e["lauf_id"]) == ("kommunikation", "a1", "l1")


def test_ereignis_senke_noop():
    ag.ereignis_verwerfen("lauf_gestartet", {"lauf_id": "l1"})  # wirft nie
    assert "hitl_wartet" in ag.EREIGNISSE


# --- definitions_hash: eval hängt am VERHALTEN, nicht am Namen (docs/83 §4) --------

def test_definitions_hash_stabil_und_hex():
    a = ag.AgentDef(id="a1", name="A", system_prompt="hallo",
                    werkzeuge=("t1", "t2"), task_klasse="chat")
    h1, h2 = ag.definitions_hash(a), ag.definitions_hash(a)
    assert h1 == h2 and len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)


def test_definitions_hash_ignoriert_name_status_autonomie_sensitivitaet():
    # Umbenennen/Verschieben/Stufen-Änderung ändern das gemessene Verhalten NICHT.
    a = ag.AgentDef(id="a1", name="A", rolle="x", system_prompt="p",
                    werkzeuge=("t1",), bereich_id="b1", sensitivitaet="hoch",
                    autonomie={"entwurf": "pre_approval"}, status="entwurf")
    b = ag.AgentDef(id="a2", name="ANDERS", rolle="y", system_prompt="p",
                    werkzeuge=("t1",), bereich_id="b2", sensitivitaet="höchst",
                    autonomie={"entwurf": "monitored"}, status="aktiv")
    assert ag.definitions_hash(a) == ag.definitions_hash(b)


def test_definitions_hash_aendert_sich_bei_verhaltens_edit():
    basis = ag.AgentDef(id="a1", name="A", system_prompt="p", werkzeuge=("t1",),
                        task_klasse="chat", modell_explizit="",
                        sub_agenten=("w1",), budget=ag.AgentBudget())
    h0 = ag.definitions_hash(basis)
    from dataclasses import replace
    assert ag.definitions_hash(replace(basis, system_prompt="p2")) != h0   # Prompt
    assert ag.definitions_hash(replace(basis, werkzeuge=("t1", "t2"))) != h0  # Tools
    assert ag.definitions_hash(replace(basis, werkzeuge=())) != h0
    assert ag.definitions_hash(replace(basis, task_klasse="voice")) != h0   # Modell-Slot
    assert ag.definitions_hash(replace(basis, modell_explizit="x:7b")) != h0
    assert ag.definitions_hash(replace(basis, sub_agenten=())) != h0        # Sub-Baum
    assert ag.definitions_hash(
        replace(basis, budget=ag.AgentBudget(max_runden=8))) != h0          # Budget


def test_definitions_hash_werkzeug_reihenfolge_zaehlt():
    # Umsortieren von Tools IST ein Verhaltens-Edit ⇒ Hash ändert sich (fail-closed).
    a = ag.AgentDef(id="a1", name="A", werkzeuge=("t1", "t2"))
    b = ag.AgentDef(id="a1", name="A", werkzeuge=("t2", "t1"))
    assert ag.definitions_hash(a) != ag.definitions_hash(b)
