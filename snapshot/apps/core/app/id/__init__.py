"""Dizzi-ID — der Identitäts-Dienst des Netzwerks (Kernpaket K1).

Schlanker OIDC-Provider im Dizzi-Core: EIN Login (Google-Brokering oder
lokales Passwort) → signierter Ausweis → jede vertragskonforme App akzeptiert
ihn als Relying Party (appkit/dizzi_id.py). Das ist das Single-Sign-On der
Föderation: einmal auf Dizzi anmelden ⇒ überall angemeldet.

Sicherheits-Linie (Recherche 12.06., RFC 9700 / RFC 8252 / OAuth 2.1):
- Authorization-Code-Flow mit **PKCE (S256) Pflicht**, Codes single-use + 60 s.
- **EdDSA (Ed25519)** signierte ID-/Access-Tokens; Verifier pinnen den Alg.
- **Refresh-Rotation** mit Familien-Reuse-Erkennung ⇒ Familie wird widerrufen.
- Loopback-HTTP (127.0.0.1) ist per RFC 8252 der legitime Desktop-Weg.
- Schutzstufen: Login (pwd/google) ⇒ ``verifiziert``; Passkey/MFA-Step-up
  (Kernpaket K1+/R1.3) ⇒ ``hochsicher``. Alle Auth-Ereignisse ⇒ Audit-Log.
"""

from __future__ import annotations

# Aussteller-Kennung des Providers. Discovery liegt unter
# {ISSUER}/.well-known/openid-configuration (Pfad-Präfix /id im Core).
ISSUER = "http://127.0.0.1:8200/id"
