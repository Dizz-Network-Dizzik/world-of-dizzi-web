"""Charta §B8 — Vier-Augen (CH-11) über charta_entscheide: happy path,
Selbst-Gegenzeichnung verboten, Reihenfolge, Frische-Pflicht, toter Artikel."""
import pytest

from appkit import chronik as C
from appkit import charta as CH
from appkit import charta_speicher as S
from appkit.db import Database, now_iso

CHARTA = {"charta_version": "t", "artikel": [{
    "aktion": "fibu.festschreiben",
    "gewaehre": [[{"p": "rolle", "w": "fibu_leitung"}, {"p": "assurance_min", "w": "hochsicher"}]],
    "schranken": [{"wenn": [{"p": "immer"}], "dann": ["vier_augen", "siegelpflichtig"]}]}]}

_ANTRAG_ZEIT = "2026-07-13T09:00:00+00:00"
_NACHHER = "2026-07-13T09:05:00+00:00"
_VORHER = "2026-07-13T08:55:00+00:00"


@pytest.fixture(autouse=True)
def _kontext():
    C.reset_kontext()
    yield
    C.reset_kontext()


def _db(tmp_path):
    db = Database(tmp_path / "host.sqlite", extra_schema=S.SCHEMA + C.AUSGANG_SCHEMA)
    db.get_conn()
    return db


def _antrag(uid="u:" + "a" * 10):
    return CH.antrag_bauen("fibu.festschreiben", user_id=uid, assurance="hochsicher",
                           edition="bizzi", rollen=["fibu_leitung"], bereiche=["b:eigen"],
                           frisch_s=100, objekt={"bereich_id": "b:eigen"}, zeit=_ANTRAG_ZEIT)


def _ausstellen(tmp_path, uid="u:" + "a" * 10):
    return S.entscheid_bauen(_antrag(uid), CH.Charta.aus_json(CHARTA), jetzt_iso=now_iso(),
                             auth_ref="auth:e1", cdir=tmp_path / "chronik")


def test_vieraugen_happy_path(tmp_path):
    db = _db(tmp_path)
    ent, urteil = _ausstellen(tmp_path)
    assert "vier_augen" in urteil.obliegenheiten
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    # Verbrauch OHNE Gegenzeichnung ⇒ None
    with db.transaktion() as conn:
        assert S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                       jetzt_iso=now_iso(), cdir=tmp_path / "chronik") is None
    # Gegenzeichnung durch zweites Subjekt (frisch/hochsicher, NACH dem Antrag)
    with db.transaktion() as conn:
        S.entscheid_gegenzeichnen(conn, ent["id"], zweit_subjekt="u:" + "b" * 10,
                                  zweit_auth_ref="auth:pruefer", zweit_auth_zeit_iso=_NACHHER,
                                  zweit_frisch_hochsicher=True)
    with db.transaktion() as conn:                     # jetzt grün
        v = S.entscheid_verbrauchen(conn, ent["id"], antrag_hash=ent["antrag_hash"],
                                    jetzt_iso=now_iso(), cdir=tmp_path / "chronik")
    assert v is not None and v["zweit_subjekt"] == "u:" + "b" * 10


def test_selbst_gegenzeichnung_verboten(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path, uid="u:" + "a" * 10)
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with pytest.raises(S.ChartaSpeicherFehler):
        with db.transaktion() as conn:
            S.entscheid_gegenzeichnen(conn, ent["id"], zweit_subjekt="u:" + "a" * 10,
                                      zweit_auth_ref="auth:x", zweit_auth_zeit_iso=_NACHHER,
                                      zweit_frisch_hochsicher=True)


def test_reihenfolge_zweit_vor_antrag_ungueltig(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path)
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with pytest.raises(S.ChartaSpeicherFehler):
        with db.transaktion() as conn:
            S.entscheid_gegenzeichnen(conn, ent["id"], zweit_subjekt="u:" + "b" * 10,
                                      zweit_auth_ref="auth:x", zweit_auth_zeit_iso=_VORHER,
                                      zweit_frisch_hochsicher=True)


def test_frische_pflicht(tmp_path):
    db = _db(tmp_path)
    ent, _ = _ausstellen(tmp_path)
    with db.transaktion() as conn:
        S.entscheid_schreiben(conn, ent)
    with pytest.raises(S.ChartaSpeicherFehler):
        with db.transaktion() as conn:
            S.entscheid_gegenzeichnen(conn, ent["id"], zweit_subjekt="u:" + "b" * 10,
                                      zweit_auth_ref="auth:x", zweit_auth_zeit_iso=_NACHHER,
                                      zweit_frisch_hochsicher=False)


def test_toter_artikel_klartext(tmp_path):
    # Kein zweites Subjekt möglich ⇒ vier_augen-Artikel ist tot ⇒ Klartext statt Downgrade.
    ent, urteil = S.entscheid_bauen(_antrag(), CH.Charta.aus_json(CHARTA), jetzt_iso=now_iso(),
                                    auth_ref="auth:e1", cdir=tmp_path / "chronik",
                                    vier_augen_moeglich=False)
    assert ent is None and urteil.gewaehrt is False and "vier_augen" in urteil.grund
