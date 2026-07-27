"""Identitäts-Slot des App-Vertrags — der K1-Austauschpunkt.

Das hier ist der subtile, schwer nachrüstbare Teil des Vertrags, deshalb wird
er JETZT festgelegt (Architektur-KI-Paket K3), obwohl Dizzi-ID (K1) noch nicht existiert:

- Jede Route, die einen Nutzer braucht, hängt an ``current_user`` (Dependency).
- Schutzstufen (``require_level``) sind ab Tag 1 deklarierbar; ihre Semantik
  ändert sich NIE — nur der Provider dahinter wird ausgetauscht.
- Vor K1 liefert der Standalone-Provider den Single-User mit Stufe 'lokal'
  (Vertrauensgrenze = localhost-Bindung, wie der Dizzi-Core heute).
- Stufen oberhalb 'lokal' verweigern vor K1 FAIL-CLOSED mit klarer Meldung —
  sensible/Echtgeld-Routen können also nie versehentlich offen stehen.
- K1 (Dizzi-ID als OIDC-Provider) bzw. die App als Relying Party installieren
  später per ``set_identity_provider`` die echte Prüfung (SSO-Ausweis,
  Passkey/MFA-Step-up). Kein Routen-Code ändert sich dabei.

Stufen (aufsteigend):
  'lokal'       — Standalone-Betrieb, localhost, Single-User.
  'verifiziert' — verifizierte Verbindung (Dizzi-ID-SSO oder starker lokaler
                  Login). Tor zu SENSIBLEN Daten (Manifest-Sensitivity hoch+).
  'hochsicher'  — Passkey/MFA (FIDO2). Tor zu Echtgeld-Aktionen (z. B. Trading).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request

LEVELS: dict[str, int] = {"lokal": 0, "verifiziert": 1, "hochsicher": 2}


@dataclass(frozen=True)
class UserContext:
    """Identität + erreichte Schutzstufe der aktuellen Anfrage."""

    user_id: str
    level: str = "lokal"            # Schlüssel aus LEVELS
    via: str = "standalone"         # 'standalone' | 'dizzi-id' | künftige Wege
    auth_time: float | None = None  # Unix-Zeit der letzten ECHTEN Authentifizierung
                                    # (Login/Step-up); None = nie (standalone)


# Der Provider ist pro App-Prozess global — bewusst einfach: eine App, ein
# Identitäts-Regime. K1 ersetzt ihn beim App-Start (set_identity_provider).
IdentityProvider = Callable[[Request], UserContext]

DEFAULT_USER_ID = "dizzi"


def _standalone_provider(_request: Request) -> UserContext:
    """Vor-K1-Betrieb: Single-User, Stufe 'lokal' (Vertrauensgrenze localhost)."""
    return UserContext(user_id=DEFAULT_USER_ID, level="lokal", via="standalone")


_provider: IdentityProvider = _standalone_provider


def set_identity_provider(provider: IdentityProvider) -> None:
    """K1-Anschluss: installiert die echte Identitätsprüfung (Dizzi-ID RP
    oder Standalone-Login der App). Tests nutzen dies ebenfalls."""
    global _provider
    _provider = provider


def reset_identity_provider() -> None:
    """Zurück zum Standalone-Provider (Tests/Abbau)."""
    global _provider
    _provider = _standalone_provider


def current_user(request: Request) -> UserContext:
    """FastAPI-Dependency: Identität der aktuellen Anfrage."""
    return _provider(request)


def sensitivity_level(sensitivity: str) -> str:
    """Mapping Manifest-Sensibilität → Mindest-Schutzstufe (K5-Routing-Basis):
    normal ⇒ 'lokal' · hoch (sensible Daten) ⇒ 'verifiziert' ·
    hoechst (Gesundheit/Echtgeld) ⇒ 'hochsicher'."""
    return {"normal": "lokal", "hoch": "verifiziert",
            "hoechst": "hochsicher"}[sensitivity]


def require_fresh_stepup(min_level: str = "hochsicher",
                         max_age_s: float = 300.0) -> Callable[[Request], UserContext]:
    """Re-Auth-Dependency für SENSIBLE AKTIONEN (K2.1, docs/19 §3): verlangt
    die Mindeststufe UND dass die letzte ECHTE Authentifizierung (Login/
    Step-up) höchstens ``max_age_s`` zurückliegt — auch in aktiver Session.
    Fail-closed: ohne bekannte ``auth_time`` (standalone) wird verweigert."""
    import time as _time
    if min_level not in LEVELS:
        raise ValueError(f"Unbekannte Schutzstufe: {min_level!r}")

    def _dep(request: Request) -> UserContext:
        ctx = _provider(request)
        if LEVELS.get(ctx.level, -1) < LEVELS[min_level]:
            raise HTTPException(status_code=403, detail=(
                f"Schutzstufe '{min_level}' erforderlich (aktuell: '{ctx.level}')."))
        if ctx.auth_time is None or _time.time() - ctx.auth_time > max_age_s:
            raise HTTPException(status_code=403, detail=(
                f"Frische Verifikation nötig (max. {max_age_s:.0f}s alt) — "
                "bitte erneut anmelden/Step-up: /auth/login?level=" + min_level))
        return ctx

    return _dep


def require_level(min_level: str) -> Callable[[Request], UserContext]:
    """Dependency-Fabrik: erzwingt eine Mindest-Schutzstufe (fail-closed).

    Beispiel::

        @router.get("/api/echtgeld", dependencies=[Depends(require_level("hochsicher"))])
    """
    if min_level not in LEVELS:
        raise ValueError(f"Unbekannte Schutzstufe: {min_level!r}")

    def _dep(request: Request) -> UserContext:
        ctx = _provider(request)
        if LEVELS.get(ctx.level, -1) < LEVELS[min_level]:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Schutzstufe '{min_level}' erforderlich (aktuell: '{ctx.level}'). "
                    "Verifizierte Verbindung über Dizzi-ID (Kernpaket K1) nötig."
                ),
            )
        return ctx

    return _dep
