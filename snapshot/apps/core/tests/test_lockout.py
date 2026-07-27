"""H4: Login-/TOTP-Lockout — Versuchszähler, exponentielles Backoff,
Reset bei Erfolg. Durchsetzung sitzt am Credential-Check selbst."""

from __future__ import annotations

from app.id import store, totp


def _sperre_aufheben(zweck: str) -> None:
    conn = store._conn()
    conn.execute("UPDATE id_lockout SET gesperrt_bis=0 WHERE zweck=?", (zweck,))
    conn.commit()


def test_passwort_lockout_greift_und_blockt_auch_richtiges():
    store.set_local_password("korrekt-123")
    for _ in range(store.LOCKOUT_SCHWELLE):
        assert store.check_local_password("falsch") is False
    assert store.lockout_rest("passwort") > 0
    # Im Sperrfenster scheitert auch das RICHTIGE Passwort (Bremse, kein Orakel)
    assert store.check_local_password("korrekt-123") is False


def test_passwort_erfolg_setzt_zurueck():
    store.set_local_password("korrekt-123")
    for _ in range(store.LOCKOUT_SCHWELLE - 1):
        store.check_local_password("falsch")
    assert store.lockout_rest("passwort") == 0
    assert store.check_local_password("korrekt-123") is True
    # Zähler ist weg: erneute Fehlversuche starten bei null
    store.check_local_password("falsch")
    assert store.lockout_rest("passwort") == 0


def test_backoff_waechst_exponentiell():
    store.set_local_password("korrekt-123")
    sperren = []
    for _ in range(store.LOCKOUT_SCHWELLE + 2):
        store.check_local_password("falsch")
        rest = store.lockout_rest("passwort")
        if rest:
            sperren.append(rest)
            _sperre_aufheben("passwort")     # Fenster ablaufen lassen (Test)
    assert len(sperren) == 3
    assert sperren[0] < sperren[1] < sperren[2]
    assert sperren[-1] <= store.LOCKOUT_MAX_S


def test_totp_lockout():
    secret = totp.new_secret()
    store.totp_begin_enroll(secret)
    for _ in range(store.LOCKOUT_SCHWELLE):
        assert store.totp_verify("000000") is False
    assert store.lockout_rest("totp") > 0
    # Auch der RICHTIGE Code scheitert im Sperrfenster …
    gueltig = totp.code_now(secret)
    assert store.totp_verify(gueltig) is False
    # … nach Ablauf des Fensters greift er wieder (+ Reset)
    _sperre_aufheben("totp")
    assert store.totp_verify(gueltig) is True
    assert store.lockout_rest("totp") == 0
