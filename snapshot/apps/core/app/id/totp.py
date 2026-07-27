"""TOTP (RFC 6238) — Zweitfaktor für die Stufe ``hochsicher``. Stdlib-pur.

Designentscheidung R1.3 (ehrlich dokumentiert): TOTP ist der JETZT voll
baubare und testbare MFA-Weg (jede Authenticator-App kann enrollen);
**WebAuthn/Passkey** ist der vorbereitete Ausbau (R1.3b, braucht die echte
Nutzer-Geste + Browser-Ceremony — Slot: gleiche Step-up-Mechanik, amr
``webauthn`` statt ``totp``).

Parameter: SHA-1, 30-s-Fenster, 6 Ziffern (Industriestandard, kompatibel mit
Google Authenticator/Aegis/1Password …), ±1 Fenster Uhren-Drift.
Replay-Schutz: der zuletzt akzeptierte Zeit-Zähler wird gespeichert; Codes
desselben oder eines älteren Fensters werden abgelehnt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

STEP_S = 30
DIGITS = 6
DRIFT_WINDOWS = 1  # ±1 Fenster Toleranz


def new_secret() -> str:
    """160-bit-Geheimnis, Base32 (Standard der Authenticator-Apps)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def otpauth_uri(secret: str, account: str = "dizzi",
                issuer: str = "Dizzi-ID") -> str:
    """Provisionierungs-URI (QR-Inhalt) für Authenticator-Apps."""
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}"
            f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1"
            f"&digits={DIGITS}&period={STEP_S}")


def _code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def code_now(secret: str, at: float | None = None) -> str:
    """Aktueller Code (für Tests/Anzeige)."""
    return _code_at(secret, int((at if at is not None else time.time()) // STEP_S))


def verify(secret: str, code: str, last_counter: int,
           at: float | None = None) -> int | None:
    """Prüft einen Code (±DRIFT_WINDOWS) mit Replay-Schutz.

    Liefert den akzeptierten Zähler (> last_counter) oder None. Vergleich
    konstantzeitig; Eingabe wird normalisiert (Leerzeichen erlaubt).
    """
    code = code.replace(" ", "").strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    now_counter = int((at if at is not None else time.time()) // STEP_S)
    for counter in range(now_counter - DRIFT_WINDOWS, now_counter + DRIFT_WINDOWS + 1):
        if counter <= last_counter:                       # Replay/zu alt
            continue
        if hmac.compare_digest(_code_at(secret, counter), code):
            return counter
    return None
