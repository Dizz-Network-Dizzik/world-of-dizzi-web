"""§B5 / CH-11 — Vier-Augen-Oberfläche auf ``app_actions`` (``actions.decide``).

Pinnt die Inbox-Naht zum kryptografischen ``charta_entscheide`` (dort ist CH-11 voll
geprüft, ``test_charta_vieraugen.py``): happy path (Checker≠Maker führt aus + ``pruefer_id``
vermerkt) · Selbst-Freigabe verboten · fehlender/zu schwacher/zu früher Zweit-Auth ·
CAS-Kern (pending→executing) unverändert · Ein-Augen-Bestandsverhalten byte-genau ·
idem/RG-4-Naht unberührt. Runtime-/HTTP-frei — reine Mechanik wie ``test_actions_inbox``.
"""

from __future__ import annotations

import pytest

from appkit.actions import (ActionRegistry, VierAugenFehler, decide, listing,
                            migriere_actions_inbox, propose)
from appkit.db import Database

_MAKER = "u:" + "a" * 10
_CHECKER = "u:" + "b" * 10
_NACH = "2099-01-01T00:00:00+00:00"     # immer NACH dem Vorschlag (now)
_VOR = "2000-01-01T00:00:00+00:00"      # immer VOR dem Vorschlag


def _setup(tmp_path):
    ausgefuehrt: list[dict] = []
    reg = ActionRegistry()
    reg.register("fibu_festschreiben",
                 lambda p: ausgefuehrt.append(p) or {"ok": True},
                 level="hochsicher", beschreibung="Periode festschreiben (vier_augen)")
    db = Database(tmp_path / "bizzi.sqlite")
    db.get_conn()
    return db, reg, ausgefuehrt


def _pending(db, reg, user_id=_MAKER):
    return propose(db, reg, user_id, "fibu_festschreiben", {"zeitraum": "2026-06"},
                   source="user")["id"]


def _freigabe(db, reg, aid, **kw):
    """Vier-Augen-Freigabe: ``user_id`` = Maker (Zeilen-Eigner ⇒ CAS-Lookup byte-stabil),
    das zweite Subjekt kommt als ``pruefer_id`` — genau die §B5-Naht."""
    return decide(db, reg, _MAKER, aid, approve=True, vier_augen=True, **kw)


def test_vieraugen_happy_path(tmp_path):
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    r = _freigabe(db, reg, aid, pruefer_id=_CHECKER, pruefer_auth_ref="auth:pruefer",
                  pruefer_auth_zeit_iso=_NACH, pruefer_frisch_hochsicher=True)
    assert r["status"] == "executed"
    assert ausgefuehrt == [{"zeitraum": "2026-06"}]
    eintrag = {a["id"]: a for a in listing(db, _MAKER, reg)}[aid]
    assert eintrag["pruefer_id"] == _CHECKER
    assert eintrag["pruefer_auth_ref"] == "auth:pruefer"


def test_selbst_freigabe_verboten(tmp_path):
    """Maker≠Checker (CH-11): dasselbe Subjekt darf nicht gegenzeichnen — fail-loud,
    Aktion bleibt pending (nie stilles Downgrade)."""
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    with pytest.raises(VierAugenFehler):
        _freigabe(db, reg, aid, pruefer_id=_MAKER, pruefer_auth_ref="auth:x",
                  pruefer_auth_zeit_iso=_NACH, pruefer_frisch_hochsicher=True)
    assert not ausgefuehrt
    assert {a["id"]: a for a in listing(db, _MAKER, reg)}[aid]["status"] == "pending"


def test_pruefer_fehlt(tmp_path):
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    with pytest.raises(VierAugenFehler):
        _freigabe(db, reg, aid, pruefer_id="", pruefer_auth_ref="auth:x",
                  pruefer_auth_zeit_iso=_NACH, pruefer_frisch_hochsicher=True)
    with pytest.raises(VierAugenFehler):        # Auth-Referenz PFLICHT
        _freigabe(db, reg, aid, pruefer_id=_CHECKER, pruefer_auth_ref="",
                  pruefer_auth_zeit_iso=_NACH, pruefer_frisch_hochsicher=True)
    assert not ausgefuehrt


def test_auth_nicht_hochsicher_frisch(tmp_path):
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    with pytest.raises(VierAugenFehler):
        _freigabe(db, reg, aid, pruefer_id=_CHECKER, pruefer_auth_ref="auth:x",
                  pruefer_auth_zeit_iso=_NACH, pruefer_frisch_hochsicher=False)
    assert not ausgefuehrt


def test_auth_nicht_nach_antrag(tmp_path):
    """Reihenfolge (CH-11): Zweit-Auth VOR dem Vorschlag ⇒ ungültig (Replay-Schutz)."""
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    with pytest.raises(VierAugenFehler):
        _freigabe(db, reg, aid, pruefer_id=_CHECKER, pruefer_auth_ref="auth:x",
                  pruefer_auth_zeit_iso=_VOR, pruefer_frisch_hochsicher=True)
    assert not ausgefuehrt


def test_ein_augen_bestand_byte_genau(tmp_path):
    """Ohne ``vier_augen`` bleibt ``decide`` das Bestands-Verhalten: führt aus,
    kein Prüfer, kein Gate — 0-Bruch für alle heutigen Aufrufer."""
    db, reg, ausgefuehrt = _setup(tmp_path)
    aid = _pending(db, reg)
    r = decide(db, reg, _MAKER, aid, approve=True)      # kein vier_augen, kein pruefer
    assert r["status"] == "executed"
    assert ausgefuehrt == [{"zeitraum": "2026-06"}]
    assert {a["id"]: a for a in listing(db, _MAKER, reg)}[aid]["pruefer_id"] == ""


def test_migration_fuegt_pruefer_spalten(tmp_path):
    db, reg, _ = _setup(tmp_path)
    migriere_actions_inbox(db)
    cols = {r["name"] for r in db.get_conn().execute("PRAGMA table_info(app_actions)")}
    assert {"pruefer_id", "pruefer_auth_ref"} <= cols   # §B5 additiv
    assert {"agent_id", "warum", "lauf_id", "idem"} <= cols   # RG-4-Inbox unberührt
