"""Charta §B8 — Prüfkern §B6: policy-replay (grün · Divergenz · Bruch) + erreichbarkeit."""
import json

import pytest

from appkit import chronik as C
from appkit import charta as CH
from appkit import charta_speicher as S
from appkit import charta_pruef as PR
from appkit.db import Database, now_iso

CHARTA = {"charta_version": "2026-07-13.1", "artikel": [{
    "aktion": "fibu.buchen", "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}]],
    "schranken": [{"wenn": [{"p": "betrag_ab", "w": "1000000"}], "dann": ["vier_augen"]}]}]}


@pytest.fixture(autouse=True)
def _kontext():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _setup(tmp_path):
    cdir = tmp_path / "chronik"
    C.konfiguriere(cdir)
    db = Database(tmp_path / "h.sqlite", extra_schema=S.SCHEMA + C.AUSGANG_SCHEMA)
    db.get_conn()
    return cdir, db


def _antrag(betrag="50000"):
    return CH.antrag_bauen("fibu.buchen", user_id="u:" + "a" * 10, assurance="verifiziert",
                           edition="bizzi", rollen=["buchhaltung"], bereiche=["b:eigen"],
                           objekt={"betrag_minor": betrag, "bereich_id": "b:eigen"},
                           zeit="2026-07-13T09:00:00+00:00")


def _ausstellen_verbrauchen(cdir, db, betrag="50000"):
    ent, _ = S.entscheid_bauen(_antrag(betrag), CH.Charta.aus_json(CHARTA),
                               jetzt_iso=now_iso(), auth_ref="auth:e1", cdir=cdir)
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with db.transaktion() as conn:
        S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                jetzt_iso=now_iso(), cdir=cdir)
    return ent


def test_policy_replay_gruen(tmp_path):
    cdir, db = _setup(tmp_path)
    S.aktiviere_version(db, charta=CHARTA, subjekt="u:" + "a" * 36, jetzt_iso=now_iso())
    _ausstellen_verbrauchen(cdir, db)
    rc, zeilen = PR.policy_replay(db.get_conn(), cdir=cdir)
    assert rc == PR.EXIT_GRUEN, zeilen


def test_policy_replay_divergenz_bei_versions_manipulation(tmp_path):
    cdir, db = _setup(tmp_path)
    S.aktiviere_version(db, charta=CHARTA, subjekt="u:" + "a" * 36, jetzt_iso=now_iso())
    _ausstellen_verbrauchen(cdir, db)
    # Version nachträglich entkernen ⇒ Neu-Evaluation weicht ab (Entscheid-Signatur bleibt gültig)
    leer = json.dumps([{"aktion": "fibu.buchen", "gewaehre": [[{"p": "rolle", "w": "niemand"}]]}])
    conn = db.get_conn()
    conn.execute("UPDATE charta_versionen SET artikel=? WHERE version=?", (leer, "2026-07-13.1"))
    conn.commit()
    rc, zeilen = PR.policy_replay(db.get_conn(), cdir=cdir)
    assert rc == PR.EXIT_DIVERGENZ and any("DIVERGENZ" in z for z in zeilen)


def test_policy_replay_bruch_bei_archiv_manipulation(tmp_path):
    cdir, db = _setup(tmp_path)
    S.aktiviere_version(db, charta=CHARTA, subjekt="u:" + "a" * 36, jetzt_iso=now_iso())
    ent = _ausstellen_verbrauchen(cdir, db)
    # Obliegenheiten im Entscheid-Archiv verfälschen ⇒ Signatur-Bruch (Integrität)
    conn = db.get_conn()
    conn.execute("UPDATE charta_entscheide SET obliegenheiten='[\"vier_augen\"]' WHERE id=?",
                 (ent["id"],))
    conn.commit()
    rc, _ = PR.policy_replay(db.get_conn(), cdir=cdir)
    assert rc == PR.EXIT_BRUCH


def test_erreichbarkeit_ohne_belegschaft_meldet_tote_artikel(tmp_path):
    cdir, db = _setup(tmp_path)
    S.aktiviere_version(db, charta=CHARTA, subjekt="u:" + "a" * 36, jetzt_iso=now_iso())
    rc, zeilen = PR.erreichbarkeit(db.get_conn())
    assert rc == PR.EXIT_TOTE and any("TOTE ARTIKEL" in z for z in zeilen)
