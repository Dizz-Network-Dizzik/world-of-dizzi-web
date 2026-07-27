"""Tests RG-5 (docs/83 §4, Management-Seite): der Eval-Metrik-Rechner + agent_evals.

Die reine Schwellen-Ampel beweist sich selbst (fail-closed): dünne Daten ⇒ ungrün,
n<20 ⇒ ungrün, jede harte Verletzung (Verstoß / rote Golden-Suite) blockt, def_hash-
Wechsel + Ablauf löschen das Grün. Plus: Speicher-Round-Trip + die Karten-Projektion,
die dem Core das ``eval_gruen`` liefert (def_hash-gegated). Runtime-/Ollama-frei.
"""

from __future__ import annotations

from managementapp import agenten_eval as ev
from appkit.db import Database, default_db_path


# --- Voll-grüne Referenz-Metriken (alle Schwellen erfüllt) -----------------------

def _voll_gruen(**over) -> ev.EvalMetriken:
    """Ein Datensatz, der ALLE vier Grün-Bedingungen erfüllt — Einzeltests kippen je
    eine Bedingung über ``over`` und erwarten ungrün."""
    base = dict(entschieden=25, approved=22,            # Präzision 0.88 ≥ 0.80
                klass_stichproben=20, klass_treffer=18,  # Treffer 0.90 ≥ 0.85
                verstoesse=0, laeufe=30, laeufe_im_budget=30,  # Budget 1.0 ≥ 0.95
                golden_gruen=True)
    base.update(over)
    return ev.EvalMetriken(**base)


# --- Die reine Ampel (bewerte_metriken) ------------------------------------------

def test_voll_gruen_ist_gruen():
    r = ev.bewerte_metriken(_voll_gruen())
    assert r["gruen"] is True and r["gruende"] == []


def test_leer_ist_ungruen_fail_closed():
    """Frischer/leerer Agent (Default-Metriken) ⇒ ungrün: Stichprobe fehlt UND Golden
    nicht grün. Der sichere Default eines ungemessenen Agenten ist NICHT autonom."""
    r = ev.bewerte_metriken(ev.EvalMetriken())
    assert r["gruen"] is False
    assert any("Mindest-Stichprobe" in g for g in r["gruende"])
    assert any("Golden" in g for g in r["gruende"])


def test_n_unter_20_ist_ungruen():
    r = ev.bewerte_metriken(_voll_gruen(entschieden=19, approved=19))
    assert r["gruen"] is False
    assert any("Mindest-Stichprobe" in g and "19" in g for g in r["gruende"])


def test_praezision_unter_schwelle_ist_ungruen():
    # 15/25 = 0.60 < 0.80
    r = ev.bewerte_metriken(_voll_gruen(approved=15))
    assert r["gruen"] is False
    assert any("Präzision" in g for g in r["gruende"])


def test_budget_unter_schwelle_ist_ungruen():
    # 25/30 = 0.83 < 0.95
    r = ev.bewerte_metriken(_voll_gruen(laeufe=30, laeufe_im_budget=25))
    assert r["gruen"] is False
    assert any("Budget" in g for g in r["gruende"])


def test_ein_invarianten_verstoss_blockt_hart():
    r = ev.bewerte_metriken(_voll_gruen(verstoesse=1))
    assert r["gruen"] is False
    assert any("Invarianten-Verstöße" in g for g in r["gruende"])
    # die Verstoß-Zeile ist als HART markiert
    zeile = next(m for m in r["metriken"] if m["schluessel"] == "verstoesse")
    assert zeile["hart"] is True and zeile["status"] == ev.STATUS_UNGRUEN


def test_rote_golden_suite_blockt_hart_trotz_guter_metriken():
    """Fail-closed docs/83 §4: rote Szenarien-Suite ⇒ eval_gruen unerreichbar, egal
    was der Betrieb sagt."""
    r = ev.bewerte_metriken(_voll_gruen(golden_gruen=False))
    assert r["gruen"] is False
    assert any("Golden" in g for g in r["gruende"])


def test_klassifikation_ohne_stichprobe_blockt_nicht():
    """Die Daumen-UI liefert erst später ⇒ 0 Klass-Stichproben = ``nicht_gemessen``,
    darf ein sonst grünes Bild NICHT blockieren (Präzision ist das Ground-Truth-Gate)."""
    r = ev.bewerte_metriken(_voll_gruen(klass_stichproben=0, klass_treffer=0))
    assert r["gruen"] is True
    zeile = next(m for m in r["metriken"] if m["schluessel"] == "treffer")
    assert zeile["status"] == ev.STATUS_NICHT_GEMESSEN


def test_metriken_zeilen_vollstaendig():
    r = ev.bewerte_metriken(_voll_gruen())
    schluessel = {m["schluessel"] for m in r["metriken"]}
    assert schluessel == {"stichprobe", "praezision", "treffer", "budget",
                          "verstoesse", "golden"}


# --- Frische-Gate: eval_gueltig (def_hash + Ablauf) ------------------------------

def test_eval_gueltig_passt():
    ok, grund = ev.eval_gueltig("h1", "h1", "2999-01-01T00:00:00+00:00",
                                jetzt_iso="2026-07-13T00:00:00+00:00")
    assert ok is True and grund == ""


def test_eval_gueltig_def_hash_wechsel_erlischt():
    ok, grund = ev.eval_gueltig("h1", "h2", "2999-01-01T00:00:00+00:00",
                                jetzt_iso="2026-07-13T00:00:00+00:00")
    assert ok is False and "def_hash" in grund


def test_eval_gueltig_abgelaufen():
    ok, grund = ev.eval_gueltig("h1", "h1", "2026-01-01T00:00:00+00:00",
                                jetzt_iso="2026-07-13T00:00:00+00:00")
    assert ok is False and "abgelaufen" in grund


def test_eval_gueltig_leerer_hash_ungueltig():
    ok, _ = ev.eval_gueltig("", "h1", "2999-01-01T00:00:00+00:00",
                            jetzt_iso="2026-07-13T00:00:00+00:00")
    assert ok is False


def test_gueltig_bis_ab_addiert_tage():
    bis = ev.gueltig_bis_ab("2026-07-13T00:00:00+00:00", tage=30)
    assert bis.startswith("2026-08-12")            # +30 Tage


# --- Speicher: agent_evals (Round-Trip + Karten-Projektion) ----------------------

def _db(tmp_path) -> Database:
    return Database(default_db_path("management", data_root=tmp_path),
                    extra_schema=ev.SCHEMA_AGENT_EVALS)


def test_speichern_und_holen_roundtrip(tmp_path):
    db = _db(tmp_path)
    res = ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "hash-A",
                            _voll_gruen(), quelle="poll",
                            jetzt_iso="2026-07-13T00:00:00+00:00")
    assert res["gruen"] is True and res["gueltig_bis"].startswith("2026-08-12")
    geholt = ev.eval_holen(db, "u1", "a1")
    assert len(geholt) == 1 and geholt[0]["gruen"] is True
    assert geholt[0]["def_hash"] == "hash-A" and geholt[0]["roh"]["approved"] == 22


def test_speichern_ist_idempotent_upsert(tmp_path):
    db = _db(tmp_path)
    ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "h1", _voll_gruen(),
                      quelle="poll", jetzt_iso="2026-07-13T00:00:00+00:00")
    # erneut mit schlechteren Werten ⇒ überschreibt (eine Zeile, jetzt ungrün)
    ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "h1", _voll_gruen(approved=10),
                      quelle="poll", jetzt_iso="2026-07-14T00:00:00+00:00")
    geholt = ev.eval_holen(db, "u1", "a1", "aussenwirkung")
    assert len(geholt) == 1 and geholt[0]["gruen"] is False


def test_karte_projektion_gruen_nur_bei_passendem_def_hash(tmp_path):
    db = _db(tmp_path)
    ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "hash-A", _voll_gruen(),
                      quelle="poll", jetzt_iso="2026-07-13T00:00:00+00:00")
    jetzt = "2026-07-14T00:00:00+00:00"
    # aktueller Hash == gespeicherter ⇒ grün reist mit
    karte = ev.eval_status_fuer_karte(db, "u1", {"a1": "hash-A"}, jetzt_iso=jetzt)
    assert karte["a1"]["aussenwirkung"]["gruen"] is True
    # Definition geändert (anderer Hash) ⇒ Grün erlischt in der Karte (Core re-gatet eh)
    karte2 = ev.eval_status_fuer_karte(db, "u1", {"a1": "hash-NEU"}, jetzt_iso=jetzt)
    assert karte2["a1"]["aussenwirkung"]["gruen"] is False


def test_karte_projektion_abgelaufen_ist_ungruen(tmp_path):
    db = _db(tmp_path)
    ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "hash-A", _voll_gruen(),
                      quelle="poll", jetzt_iso="2026-01-01T00:00:00+00:00")   # gültig bis ~31.01.
    karte = ev.eval_status_fuer_karte(db, "u1", {"a1": "hash-A"},
                                      jetzt_iso="2026-07-13T00:00:00+00:00")
    assert karte["a1"]["aussenwirkung"]["gruen"] is False       # abgelaufen


def test_karte_projektion_unbekannter_agent_faellt_raus(tmp_path):
    db = _db(tmp_path)
    ev.eval_speichern(db, "u1", "a1", "aussenwirkung", "hash-A", _voll_gruen(),
                      quelle="poll", jetzt_iso="2026-07-13T00:00:00+00:00")
    # a1 nicht mehr im Wald (kein aktueller def_hash) ⇒ nicht in der Karte
    karte = ev.eval_status_fuer_karte(db, "u1", {"a2": "hash-B"},
                                      jetzt_iso="2026-07-14T00:00:00+00:00")
    assert "a1" not in karte
