"""Charta §B8 — Entscheid/CAS: Signatur, antrag_hash-Bindung, TTL, Einmal-Verbrauch."""
import pytest

from appkit import chronik as C
from appkit import charta as CH
from appkit import charta_speicher as S
from appkit.db import Database, now_iso

CHARTA = {"charta_version": "2026-07-13.1", "artikel": [{
    "aktion": "fibu.buchen",
    "gewaehre": [[{"p": "rolle", "w": "buchhaltung"}, {"p": "assurance_min", "w": "verifiziert"}]],
    "schranken": [{"wenn": [{"p": "betrag_ab", "w": "1000000"}], "dann": ["vier_augen"]}]}]}


@pytest.fixture(autouse=True)
def _kontext():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _db(tmp_path):
    db = Database(tmp_path / "host.sqlite", extra_schema=S.SCHEMA + C.AUSGANG_SCHEMA)
    db.get_conn()                                      # Schema anlegen
    return db


def _antrag(betrag="50000", uid="u:" + "a" * 10):
    return CH.antrag_bauen("fibu.buchen", user_id=uid, assurance="verifiziert", edition="bizzi",
                           rollen=["buchhaltung"], bereiche=["b:eigen"],
                           objekt={"betrag_minor": betrag, "bereich_id": "b:eigen"},
                           zeit="2026-07-13T09:00:00+00:00")


def _ausstellen(tmp_path, an, **kw):
    ent, urteil = S.entscheid_bauen(an, CH.Charta.aus_json(CHARTA), jetzt_iso=now_iso(),
                                    auth_ref="auth:e1", cdir=tmp_path / "chronik", **kw)
    return ent, urteil


def test_ausstellen_signiert_und_verbraucht(tmp_path):
    db = _db(tmp_path)
    ent, urteil = _ausstellen(tmp_path, _antrag())
    assert ent is not None and urteil.gewaehrt and ent["sig"].startswith("ed25519:")
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with db.transaktion() as conn:
        v = S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                    jetzt_iso=now_iso(), cdir=tmp_path / "chronik")
    assert v is not None and v["status"] == "verbraucht"
    assert v["entscheid_hash"].startswith("sha256:")


def test_doppelverbrauch_scheitert_cas(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path, _antrag())
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with db.transaktion() as conn:
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                       jetzt_iso=now_iso(), cdir=tmp_path / "chronik") is not None
    with db.transaktion() as conn:                     # zweiter Verbrauch ⇒ None
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                       jetzt_iso=now_iso(), cdir=tmp_path / "chronik") is None


def test_antrag_hash_mismatch_verweigert_und_capability_bleibt(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path, _antrag())
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with db.transaktion() as conn:
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash="sha256:deadbeef",
                                       jetzt_iso=now_iso(), cdir=tmp_path / "chronik") is None
    status = db.get_conn().execute("SELECT status FROM charta_entscheide WHERE id=?",
                                   (ent["id"],)).fetchone()["status"]
    assert status == "offen"                           # falscher Antrag verbraucht nicht


def test_ttl_verfall(tmp_path):
    db = _db(tmp_path)
    ent, _ = S.entscheid_bauen(_antrag(), CH.Charta.aus_json(CHARTA),
                               jetzt_iso="2026-07-13T09:00:00+00:00", auth_ref="auth:e1",
                               ttl_s=1, cdir=tmp_path / "chronik")
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with db.transaktion() as conn:                     # 5 min später ⇒ verfallen
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                       jetzt_iso="2026-07-13T09:05:00+00:00",
                                       cdir=tmp_path / "chronik") is None
    status = db.get_conn().execute("SELECT status FROM charta_entscheide WHERE id=?",
                                   (ent["id"],)).fetchone()["status"]
    assert status == "verfallen"


def test_signatur_bruch_verweigert_verbrauch(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path, _antrag())
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    conn = db.get_conn()                               # Signatur manipulieren
    conn.execute("UPDATE charta_entscheide SET sig='ed25519:x:AAAA' WHERE id=?", (ent["id"],))
    conn.commit()
    with db.transaktion() as conn:
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                       jetzt_iso=now_iso(), cdir=tmp_path / "chronik") is None


def test_verweigerter_antrag_kein_capability(tmp_path):
    # Kein Rolle-Match ⇒ deny-default ⇒ keine Capability, nur das Urteil.
    ohne_rolle = CH.antrag_bauen("fibu.buchen", user_id="u:" + "a" * 10, assurance="lokal",
                                 edition="bizzi", rollen=["leser"], bereiche=["b:eigen"],
                                 objekt={"betrag_minor": "50000", "bereich_id": "b:eigen"},
                                 zeit="2026-07-13T09:00:00+00:00")
    ent, urteil = _ausstellen(tmp_path, ohne_rolle)
    assert ent is None and urteil.gewaehrt is False
