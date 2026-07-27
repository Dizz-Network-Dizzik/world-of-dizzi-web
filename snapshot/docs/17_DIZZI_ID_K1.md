# Dizzi-ID — Identitäts-Dienst (Kernpaket K1) · gebaut 12.06.2026 (Architektur-KI)

> **Das SSO der Föderation:** einmal auf Dizzi anmelden ⇒ in allen verbundenen
> Apps angemeldet. Implementierung: `core/app/id/` (Provider) +
> `appkit/dizzi_id.py` (Relying-Party-Anschluss jeder App).

## 1. Architektur
- **OIDC-Provider im Dizzi-Core** (Issuer `http://127.0.0.1:8200/id`):
  Discovery (`/.well-known/openid-configuration`), JWKS, Authorize, Token,
  Userinfo, Login-Seite, Logout, Status.
- **Login-Wege:** lokales Passwort (scrypt, Setup beim ersten Besuch) und
  **Google-Brokering** (System-Browser, Loopback :8200, PKCE — RFC 8252).
  Beide ⇒ Stufe **`verifiziert`**; `hochsicher` kommt mit Passkey/MFA (R1.3).
- **RP-Anschluss in einer App = EINE Zeile:** `install_dizzi_id(app, manifest,
  data_root)` → Routen `/auth/login|callback|logout|me` + Identitäts-Provider
  am K3-Austauschpunkt (`require_level`-Routen werden automatisch scharf;
  ohne Login bleibt die App standalone auf Stufe `lokal`).

## 2. Sicherheits-Eigenschaften (Recherche 12.06.: RFC 9700/8252/9864)
- **PKCE S256 Pflicht**, Codes single-use + 60 s, exakter redirect_uri-Abgleich
  gegen die Client-Registry (kein Open-Redirect), state+nonce geprüft.
- Tokens **Ed25519-signiert** (vollspezifizierter Alg, RFC 9864 — „EdDSA" ist
  deprecated); Verifier **pinnen** den Algorithmus, nie Header-gesteuert.
  Privater Schlüssel: `C:\Dizzik\data\id\idp_key.json` (verlässt den Core
  nie — Apps können Tokens nur prüfen, nicht ausstellen).
- **Refresh-Rotation mit Familien-Reuse-Erkennung**: Wiederverwendung eines
  alten Tokens widerruft die gesamte Familie (auditiert).
- Geheimnisse (Codes/Sessions/Refresh) liegen **nur gehasht** in der DB;
  lokales Passwort scrypt (n=2¹⁴); **Google-Konto-Pinning** (erste Anmeldung
  bindet die Google-`sub`; fremde Konten ⇒ 403).
- Alle Auth-Ereignisse im Audit-Log (`id_login_ok`, `id_refresh_REUSE_…`, …).
- RP-Session = HMAC-signiertes Cookie; App-Geheimnis in Datei im App-Daten-
  Verzeichnis (bewusst NICHT in app_settings — /api/settings würde es zeigen).

## 3. ✅ Live-Schaltung Google — ERLEDIGT (12.06., mit Nutzer)
OAuth-Client (Desktop) angelegt, Keys in `.env`, **Live-Login verifiziert und
Konto GEPINNT**; SSO-Handschlag zu Dizz Trading (:8137) end-to-end bewiesen
(Audit: id_code/token_ausgestellt für client tradingbot). Ebenfalls live:
lokales Passwort gesetzt + **TOTP-MFA aktiv** (Stufe `hochsicher` real nutzbar).
Referenz-Anleitung (für Neuaufsetzen):
1. https://console.cloud.google.com → Projekt wählen/anlegen →
   „APIs & Dienste" → „Anmeldedaten" → „Anmeldedaten erstellen" →
   **OAuth-Client-ID** → Typ **Desktop-App**, Name z. B. „Dizzi-ID".
   (Beim ersten Mal: OAuth-Zustimmungsbildschirm „Extern", nur E-Mail-Scope,
   dich selbst als Testnutzer eintragen.)
2. Client-ID + Client-Secret in `C:\Dizzik\data\.env` eintragen:
   `DIZZI_GOOGLE_CLIENT_ID=…` und `DIZZI_GOOGLE_CLIENT_SECRET=…`
3. Core neu starten → `http://127.0.0.1:8200/id/login` → „Mit Google anmelden".
Ohne diesen Schritt funktioniert alles per lokalem Passwort.

## 4. Endpunkte (Kurzreferenz)
`GET /id/.well-known/openid-configuration` · `GET /id/jwks.json` ·
`GET /id/authorize` (code+PKCE) · `POST /id/token` (authorization_code |
refresh_token) · `GET /id/userinfo` (Bearer) · `GET /id/login` (UI) ·
`POST /id/login/local` · `POST /id/local/setup` (nur einmal) ·
`GET /id/login/google` + `GET /id/callback/google` · `POST /id/logout` ·
`GET /id/status`.

## 4b. Stufe `hochsicher` — Step-up (R1.3, gebaut)
- **TOTP-MFA (RFC 6238)**: Enrollment unter `GET /id/stepup` (Secret + otpauth-
  URI für jede Authenticator-App; erster gültiger Code aktiviert), danach
  Code-Eingabe je Step-up. Replay-Schutz über fortgeschriebenen Zeit-Zähler.
- **Erzwingung**: App fordert `/auth/login?level=hochsicher` an (→
  `acr_values`); reicht die Session-Stufe nicht, leitet `authorize` zum
  Step-up um. Tokens tragen `dizzi_level` + `amr` (z. B. `["pwd","totp"]`).
- `sensitivity_level()` (appkit.auth): Manifest-Sensibilität → Mindeststufe
  (normal→lokal, hoch→verifiziert, hoechst→hochsicher).
- **WebAuthn/Passkey = R1.3b ✅ GEBAUT (12.06.)**: eigener Verifier `core/app/id/
  webauthn.py` (CBOR/COSE-Parser + Ceremony-Prüfungen selbst, ECDSA-P256/Ed25519 +
  SHA-256 aus `cryptography` — **keine neue Abhängigkeit**, F-Q1-konform). Routen
  `/id/webauthn/register/begin|finish` (Enrollment ab `verifiziert`-Session) +
  `/id/webauthn/stepup/begin|finish` (Assertion ⇒ Session-Upgrade `hochsicher`,
  amr `webauthn`); Credentials/Challenges im Store (`id_webauthn`/`id_webauthn_chal`),
  H4-Lockout (`webauthn`), Audit. **Sicherheits-Substanz**: Challenge-Bindung,
  Origin + RP-ID-Hash (aus Host-Header, nie dem Client geglaubt), User-Presence,
  **Assertion-Signaturprüfung** + **Klon-Schutz** (sign_count-Regression). Bewusst
  KEINE Attestation-Prüfung (Single-User, eigenes Gerät — docs/18). UI: `/id/geraete`
  (Passkey hinzufügen/entfernen) + `/id/stepup` (Passkey-Freigabe vor TOTP). 6 Tests
  (Software-Authenticator deterministisch). **✅ LIVE VERIFIZIERT (12.06., Nutzer):**
  Passkey „Mein PC" (ES256) per Windows Hello registriert, Hochsicher-Step-up per
  Geste durchlaufen — DB belegt `level=hochsicher amr=[pwd,webauthn]`, `sign_count`
  1 (Klon-Schutz greift real), Audit `id_webauthn_registriert`→`id_stepup_ok`.
- **Browser-Navigation HOST-RELATIV (`_NAV='/id'`, 12.06.):** alle Redirects/Links/
  fetch bleiben auf dem aufgerufenen Host. Grund: Session-Cookies sind host-gebunden
  und **WebAuthn akzeptiert eine IP (127.0.0.1) nicht als RP-ID, `localhost` aber ja** —
  feste absolute Redirects warfen den Nutzer von localhost auf 127.0.0.1 ⇒ „invalid
  domain". ISSUER bleibt absolut, aber NUR für Discovery + `iss`-Claim. **Passkeys
  daher immer über `http://localhost:8200` nutzen.**

## 5. Tests
`core/tests/test_dizzi_id.py` (9: Discovery/JWKS, Voll-Flow, PKCE-Negativ,
Code-TTL/Single-Use, Rotation+Reuse⇒Familien-Widerruf, Userinfo, Passwort,
Google+Pinning+State, Logout) · `appkit/tests/test_dizzi_id_rp.py` (3:
voller SSO-Handschlag beider Seiten, State-Manipulation, Logout⇒fail-closed).

## Handy-Biometrie (02.07., docs/58 VO-4)
Sofort: Windows-Hello-Step-up (RP localhost) + `userVerification=required` für hochsicher (A-7).
Welle 1: feste RP-ID auf Tailscale-MagicDNS-HTTPS-Domain (+ROR localhost∥ts.net) → Handy = vollwertiger
syncbarer Passkey. **caBLE-gegen-localhost ist eine Sackgasse** (nicht syncbar, braucht Cloud-Tunnel).
Gate **G-TAILNET** (Nutzer). **→ Architektur-Entscheid final: Anhang FP-5e unten.**

## ★ Anhang FP-5e · RP-ID/TLS-Architektur — ENTSCHEID (Architektur-KI-Spot 03.07.2026, VO-4 Schiene 2)

> Design final; **Bau = Welle 1 (Bau-KI, nach der 50-%-Grenze), gegated auf G-TAILNET.** 0 Code jetzt.

### E1 · Kanonische RP-ID = feste, KONFIGURIERTE Domain (nicht Host-Header)
Neuer Config-Wert `rp_id` im Core (+ explizite Origin-Allowlist). Die heutige Ableitung des RP-ID-Hashs
aus dem Host-Header (`webauthn.py`, §4b) wird für Registrierung UND Assertion durch die Config ersetzt —
Host-Header bleibt nur Plausibilitäts-Check. **Wahl der Domain:** der stabile Tailscale-MagicDNS-Name des
PCs, `<pc-name>.<tailnet>.ts.net`. Konsequenz ehrlich benannt: **Maschine umbenennen = RP-ID-Bruch =
alle Passkeys neu** — Name nach G-TAILNET-Go als eingefroren behandeln.

### E2 · ROR-Doppel-Origin (EIN Credential-Bestand für beide Zugänge)
`GET https://<rp_id>/.well-known/webauthn` → `{"origins": ["https://<rp_id>", "http://localhost:8200"]}`.
Damit sind NEUE Passkeys (RP-ID = ts.net-Domain) vom Tailnet-Origin UND von `http://localhost:8200`
nutzbar (localhost bleibt der PC-Alltagszugang; 127.0.0.1 ist als RP unverändert ungültig, §4b).
**Ehrlich/Pilot-Punkt:** dass Chromium einen `http://localhost`-Origin in der ROR-Liste akzeptiert, ist
plausibel (trustworthy origin), aber VOR dem Bau real zu verifizieren; falls nein ⇒ localhost läuft
dauerhaft über die Doppelspur E3 (funktional gleichwertig, nur zwei Credential-Generationen).

### E3 · Migration bestehender localhost-Passkeys (Doppelspur statt Big-Bang)
WebAuthn-Credentials sind RP-ID-gebunden: der bestehende Passkey „Mein PC" (RP `localhost`) kann vom
ts.net-Origin **prinzipiell nie** verwendet werden. Deshalb: (1) Credential-Datensatz (`id_webauthn`)
bekommt ein `rp_id`-Feld, Bestand = `localhost`; (2) Assertion akzeptiert je Aufruf-Origin die passende
RP-ID — localhost-Origin: beide Generationen erlaubt · ts.net-Origin: nur kanonische; (3) NEU-Registrierung
IMMER unter kanonischer RP-ID; (4) beim nächsten hochsicher-Step-up mit Alt-Credential: Hinweis „Passkey
erneuern" → Re-Enroll via `/id/geraete`, Alt-Credential danach löschbar. **Kein erzwungener Bruch, kein
stiller Verlust; Windows-Hello-Schiene-1 (A-7) bleibt sofort nutzbar.**

### E4 · TLS-Beschaffung
Default: `tailscale cert` (Let's-Encrypt für den ts.net-Namen, **Private Key bleibt lokal**) +
`tailscale serve` als Reverse-Proxy auf :8200 — tailnet-only, kein Public-Exposure, kein Port-Forwarding.
OIDC bleibt unangetastet: ISSUER/Discovery/`iss` weiter absolut `127.0.0.1:8200` (server-zu-server der
lokalen Apps, kein Handy-Pfad); Login-UI ist host-relativ (`_NAV`, §4b) und funktioniert damit auch vom
ts.net-Origin.

### E5 · Fallback ohne Tailscale (Lokal-pur-Edition / Ausfall)
mkcert-Lokal-CA + feste hosts-Eintrag-Domain (z. B. `id.dizzi.local` → 127.0.0.1), `rp_id` dann
`id.dizzi.local` — **gleiche Code-Pfade** (feste RP-ID + ROR), nur die Cert-Quelle wechselt. Handy-Trust
erfordert manuelle CA-Installation am Telefon (dokumentiert mühsam) ⇒ bewusst Fallback, nicht Default.
Fällt Tailscale nur temporär aus: localhost-Betrieb am PC läuft unverändert weiter (E2/E3).

**Bau-Reihenfolge (ein Bau-KI-Paket):** Config-`rp_id` + Origin-Allowlist + `rp_id`-Feld/Doppelspur →
ROR-well-known-Route → tailscale-serve-Einrichtung (Anleitung + Settings-Slot) → Migrations-UX in
`/id/geraete`. Tests: Software-Authenticator-Suite um RP-ID-Fälle erweitern (falsche RP-ID ⇒ fail-closed).

### ★ G-TAILNET — die Frage an David (präzise, JA/NEIN)
> **„Soll ich Tailscale (kostenloses Personal-Tailnet) als feste Identitäts-Infrastruktur des Netzes
> setzen?** Das heißt konkret: (1) Du installierst Tailscale auf PC + Handy, beide hängen im selben
> privaten Tailnet (kein Port-Forwarding, nichts öffentlich). (2) Die Passkey-Identität des Netzes wird
> DAUERHAFT an den Tailnet-Namen `<pc-name>.<tailnet>.ts.net` gebunden — PC-Umbenennen bricht danach alle
> Passkeys. (3) Handy-Login/Biometrie funktioniert nur, während Tailscale läuft (PC-Alltag über localhost
> bleibt davon unabhängig). — **JA** ⇒ Welle-1-Paket wie oben. **NEIN** ⇒ Handy-Biometrie via
> mkcert-Fallback (manuelle Zertifikat-Installation am Handy, fummeliger) oder verschoben;
> Windows Hello am PC geht in jedem Fall sofort."

**Trade-off:** Die feste ts.net-RP-ID kauft syncbare, phishing-resistente Handy-Passkeys ohne jedes
Public-Exposure — zum Preis einer Infrastruktur-Ehe mit Tailscale (Name = Identität; Ausfall ⇒ nur-
localhost-Betrieb). Bewusst gewählt, weil caBLE-gegen-localhost als tragender Faktor VERBOTEN ist
(Sackgasse, §3.H) und mkcert-only den Handy-Trust unzumutbar macht.
