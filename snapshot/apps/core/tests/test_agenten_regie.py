"""Tests RG-3a (docs/83 §2): der Regie-Scheduler-Kern.

Pinnt die harten Zusagen: deterministischer Abo-Match (EIN Zuständiger, scharf vor
allgemein, kein Raten) · Zündungs-Idempotenz (Doppel-Ereignis zündet 1×) · Not-Aus
(Schalter AUS ⇒ 0 Zündungen, Cursor rückt trotzdem vor) · Sichtbarkeit fail-closed
(hoch/höchst-Ereignis erreicht schwächeren Agenten nie) · Cursor-Fortschritt ·
offene Zündungen zur Wiederaufnahme. DB-isolationsrobust: eindeutige quelle/user je Test.
"""

from __future__ import annotations

from app.ai import agenten_regie as regie


def _ev(seq, eid, typ, *, quelle_sens="normal", bereich_id=""):
    return {"seq": seq, "id": eid, "typ": typ,
            "quelle_sens": quelle_sens, "bereich_id": bereich_id}


def _abo(agent="mgr", quelle="kommunikation", typ="mail_eingegangen", *,
         bereich="", aktiv=True):
    return regie.Abo(agent_id=agent, quelle_app=quelle, ereignis_typ=typ,
                     bereich_id=bereich, aktiv=aktiv)


# --- Abo-Match (pure, keine DB) --------------------------------------------------

def test_abo_match_deterministisch():
    abos = [_abo()]
    assert regie.abo_fuer(abos, "kommunikation", "mail_eingegangen").agent_id == "mgr"
    assert regie.abo_fuer(abos, "kommunikation", "mail_gesendet") is None   # anderer Typ
    assert regie.abo_fuer(abos, "news", "mail_eingegangen") is None          # andere Quelle


def test_inaktives_abo_matcht_nie():
    assert regie.abo_fuer([_abo(aktiv=False)], "kommunikation", "mail_eingegangen") is None


def test_bereich_scharf_vor_allgemein():
    allg = _abo(agent="A", bereich="")
    scharf = _abo(agent="B", bereich="b1")
    abos = [allg, scharf]
    assert regie.abo_fuer(abos, "kommunikation", "mail_eingegangen", "b1").agent_id == "B"
    assert regie.abo_fuer(abos, "kommunikation", "mail_eingegangen", "b9").agent_id == "A"


# --- Tick-Kern (Core-DB) ---------------------------------------------------------

def test_zuendung_idempotent():
    q, u = "q_idem", "u_idem"
    abo = _abo(quelle=q)
    ev = [_ev(1, "e1", "mail_eingegangen")]
    neu1 = regie.plane_zuendungen(u, q, ev, [abo],
                                  agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    assert len(neu1) == 1 and neu1[0]["agent_id"] == "mgr"
    neu2 = regie.plane_zuendungen(u, q, ev, [abo],           # dasselbe Ereignis erneut
                                  agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    assert neu2 == []                                        # idempotent: kein Doppel
    offen = regie.offene_zuendungen(u)
    assert len(offen) == 1 and offen[0]["ereignis_id"] == "e1"


def test_schalter_aus_keine_zuendung_cursor_vor():
    q, u = "q_aus", "u_aus"
    ev = [_ev(5, "e5", "mail_eingegangen")]
    neu = regie.plane_zuendungen(u, q, ev, [_abo(quelle=q)],
                                 agent_sens={"mgr": "hoechst"}, ist_aktiv=False)
    assert neu == []                                        # Not-Aus: nichts gezündet
    assert regie.offene_zuendungen(u) == []
    assert regie.cursor_holen(q) == 5                       # aber Cursor rückte vor


def test_sichtbarkeit_fail_closed():
    q, u = "q_sens", "u_sens"
    ev = [_ev(1, "h1", "mail_eingegangen", quelle_sens="hoechst")]
    # Agent nur 'normal' ⇒ ein höchst-Ereignis erreicht ihn NIE.
    neu = regie.plane_zuendungen(u, q, ev, [_abo(quelle=q)],
                                 agent_sens={"mgr": "normal"}, ist_aktiv=True)
    assert neu == []
    assert regie.offene_zuendungen(u) == []


def test_hoechst_agent_bekommt_hoechst_ereignis():
    q, u = "q_ok", "u_ok"
    ev = [_ev(1, "h2", "mail_eingegangen", quelle_sens="hoechst")]
    neu = regie.plane_zuendungen(u, q, ev, [_abo(quelle=q)],
                                 agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    assert len(neu) == 1


def test_cursor_fortschritt_ohne_abo():
    # Ereignisse ohne Zuständigen sind trotzdem BEARBEITET ⇒ Cursor rückt vor.
    q, u = "q_cur", "u_cur"
    ev = [_ev(10, "a", "unabo"), _ev(12, "b", "unabo")]
    regie.plane_zuendungen(u, q, ev, [], agent_sens={}, ist_aktiv=True)
    assert regie.cursor_holen(q) == 12


def test_status_setzen_entfernt_aus_offen():
    q, u = "q_stat", "u_stat"
    regie.plane_zuendungen(u, q, [_ev(1, "e1", "mail_eingegangen")], [_abo(quelle=q)],
                           agent_sens={"mgr": "hoechst"}, ist_aktiv=True)
    from app import db
    conn = db.get_conn()
    regie.zuendung_status(conn, "e1", "mgr", regie.ZUENDUNG_GESTARTET, lauf_id="l1")
    conn.commit()
    assert regie.offene_zuendungen(u) == []                 # nicht mehr offen
