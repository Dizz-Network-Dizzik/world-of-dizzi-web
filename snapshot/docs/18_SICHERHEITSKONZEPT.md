# Sicherheitskonzept — the world of dizzi (gesamtsystemisch) · 12.06.2026

> Die Sicherheits-Konzept-Runde (Plan §6b). Konsolidiert, was K1–K6 gebaut haben,
> benennt das Bedrohungsmodell, **ehrliche Restrisiken** und den priorisierten
> Härtungs-Backlog. Lebendes Dokument; Quellen unten. Detail: docs/16 (Vertrag),
> docs/17 (Dizzi-ID), R-B (`Trading Bot eins/programm/docs/RECHERCHE_DIZZ_TRADING.md`).

## 1. Schutzziele & Vertrauensgrenzen
- **Lokal-first:** Alle Dienste binden an 127.0.0.1; sensible Daten verlassen die
  Maschine nie (KI-Routing `lokal_only` für `hoch`/`hoechst`-Apps, K2-Default).
- **Vertrauensgrenze heute:** der lokale Windows-Nutzer-Account (Single-User
  Stufe 1). Browser-Inhalte sind AUSSERHALB der Grenze (s. §4 Rebinding/CSRF).
- **Oberste Regel (K4):** KI beobachtet + schlägt vor — **Wirkung nur nach
  menschlicher Freigabe** auf der passenden Schutzstufe.

## 2. Identitäts- & Stufenmodell (K1/K1+)
`lokal` (Standalone, localhost) < `verifiziert` (Dizzi-ID-Login: Passwort-scrypt
oder Google-Broker mit Konto-**Pinning**) < `hochsicher` (TOTP-Step-up; WebAuthn
= R1.3b). **Fail-closed:** Routen mit Stufen-Pflicht verweigern ohne Login (403)
— nichts steht „versehentlich offen". Token: Ed25519 (Alg im Verifier GEPINNT),
PKCE Pflicht, Codes single-use/60 s, **Refresh-Rotation mit Familien-Widerruf**
bei Reuse, Secrets in der DB **nur gehasht**, alles auditiert.

## 3. Bausteine im Bestand (Mapping)
| Baustein | Schützt | Wo |
|---|---|---|
| Stufen + fail-closed | sensible Daten/Echtgeld vor unautorisiertem Zugriff | appkit/auth, alle Apps |
| HITL-Aktionen (K4) | vor eigenmächtiger KI-Wirkung | appkit/actions, /api/actions |
| Token-Tresor (K2) | Dienst-Secrets vor Datei-/Backup-Leaks (Fernet; HTTP nur Namen) | appkit/vault |
| Audit-Log (Pflicht) | Nachvollziehbarkeit jeder Wirkung/Auth | appkit/db + core |
| Sensibel-Routing | private Inhalte vor Cloud-Modellen | manifest.sensitivity + K2 `ki_routing` |
| **Echtgeld-Gate (K6)** | echte Transfers: nur `hochsicher`; Paper frei | TB /api/transfer |
| Verteidigung in der Tiefe | TB transfer.py blockt zusätzlich ohne Transfer-Key; Keys NIE Withdrawal, IP-Whitelist, 90-Tage-Rotation (R-B) | TB |
| **Local-Guard (H1, NEU)** | DNS-Rebinding + Browser-CSRF gegen localhost-APIs | appkit/guard, Core, TB |

## 4. Bedrohungsmodell (Angriff → Gegenmaßnahme → Rest)
1. **Bösartige Webseite → localhost-APIs** (DNS-Rebinding bindet eine Angreifer-
   Domain auf 127.0.0.1 und wird „same-origin"; klassisches CSRF feuert blinde
   POSTs): → **H1 Local-Guard** (Host-Header-Allowlist 127.0.0.1/localhost +
   Origin-Prüfung auf schreibenden Methoden), Session-Cookies `SameSite=Lax`
   + `HttpOnly`; Rebinding-Requests tragen ohnehin keine Cookies. *Rest:* gering.
2. **Token-/DB-Leak** (Datei kopiert): Codes/Sessions/Refresh nur gehasht,
   Tresor Fernet-verschlüsselt, privater IdP-Schlüssel verlässt den Core nie.
   *Rest:* `vault.key`/`idp_key.json` liegen als Dateien beim selben Nutzer → H2.
3. **OAuth-Phishing/Verwechslung:** PKCE+state+nonce, exakter redirect-Abgleich
   (kein Open-Redirect), **Google-Konto-Pinning** (fremde sub ⇒ 403). *Rest:* gering.
4. **Backup-/Repo-Leak:** Secrets nie im Repo (.env außerhalb), Tresor-Daten
   verschlüsselt, Backup-Disziplin „snapshot secret-frei" (TB-Vorbild). *Rest:* H8.
5. **Malware mit Nutzerrechten:** kann Dateien lesen, Tastatur mitschneiden,
   selbst `hochsicher` erlangen. → **prinzipielles Restrisiko** jeder Desktop-
   Software (DPAPI-„hard limit", s. Quellen). Mildern: H2 (DPAPI/Keyring),
   Browser-/OS-Hygiene, Windows-Konto-Härtung. *Rest:* HOCH — ehrlich benannt.
6. **Brute-Force auf Login/TOTP:** scrypt verteuert Offline-Raten; online noch
   kein Lockout → H4. TOTP-Replay ist gebannt (last_counter).
7. **Supply Chain (pip):** feste venvs, kleine Dependency-Fläche im Kern
   (joserfc/cryptography/fastapi/httpx). *Rest:* H6 (Pinning/Audit-Lauf).

## 5. Ehrliche Restrisiken (nicht wegdiskutierbar)
- **Same-User-Malware = Game over** (gilt für jede lokale App; DPAPI mildert
  Datei-Exfiltration, schützt aber nicht vor Code im selben Konto).
- **Kein TLS auf Loopback** — per RFC 8252 der akzeptierte Desktop-Weg; Schutz
  hängt an der OS-Integrität, nicht an Transportverschlüsselung.
- **Single-User-Annahme**: Multi-User-Betrieb erfordert Stufe-3-Ausbau (geplant).

## 6. Härtungs-Backlog (priorisiert)
- **H1 ✅ Local-Guard (12.06. umgesetzt):** Host-Allowlist + Origin-Prüfung auf
  schreibenden Methoden — in appkit (`guard.py`, Teil von `create_app`), im
  Dizzi-Core und im TB aktiv. Tests decken Rebinding-/CSRF-Muster ab.
- **H2 ✅ Schlüssel ins OS-Schloss (12.06. umgesetzt):** `appkit/secrets_os.py`
  (DPAPI CurrentUser via ctypes, Format `DPAPI1\n`+Blob, Klartext-Bestand
  migriert TRANSPARENT beim ersten Lesen) — aktiv für `vault.key` (Vault),
  `rp_session_secret.txt` (alle RPs) und `idp_key.json` (Core/keys.py).
  Live verifiziert: alle 6 Schlüsseldateien tragen den DPAPI-Header; kopierte
  Dateien sind auf fremden Konten wertlos. Ehrlich bleibt: same-user-Code
  liest sie weiterhin (§5). Re-vendort in news/musik/TB (TB aktiv ab
  nächstem Neustart; vault.key dort bereits migriert).
- **H3 WebAuthn/Passkey (R1.3b):** Phishing-resistenter Step-up, live mit Nutzer.
- **H4 ✅ Login-/TOTP-Lockout (12.06. umgesetzt):** `id_lockout`-Tabelle +
  exponentielles Backoff (5 freie Versuche, dann 30 s ×2 je Fehlversuch,
  Deckel 1 h) — durchgesetzt DIREKT in `check_local_password`/`totp_verify`
  (eine Route kann die Bremse nicht vergessen); Erfolg setzt zurück; Sperr-
  Restzeit landet im Audit (`lockout_s`). 4 Tests (`test_lockout.py`).
- **H5 ✅ Echtgeld-Runbook (12.06. geschrieben):** verbindliche Checkliste
  `Trading Bot eins/programm/docs/RUNBOOK_ECHTGELD.md` — Vorbedingungen (H3!),
  Bitget-Sub-Account-Architektur (trade-only/IP-Whitelist/90-Tage-Rotation),
  Evidenz-Gates, staged Go-Live, Betriebs-/Incident-Plan. VOR Live abarbeiten.
- **H6 ⏳ Dependency-Pinning + `pip audit`:** Basis gelegt (12.06.):
  `ops/requirements-lock.txt` = eingefrorener Stand des dizzi-venv (98 Pakete).
  Wartungslauf (wiederkehrend): `pip freeze`-Abgleich + `pip-audit` gegen die
  Lock-Datei; Installation von pip-audit + erster Lauf stehen aus.
- **H7 ✅ Session-/Geräte-Übersicht (12.06. KOMPLETT):** Backend
  (`GET /id/sessions` + Einzel-Widerruf + „überall abmelden", auditiert,
  401 ohne Session) **+ UI**: zentrale Seite **`/id/geraete`** im IdP
  (same-origin — Apps verlinken hierher statt cross-origin am Local-Guard
  zu scheitern); verlinkt aus der /id/login-Karte, dem TB-Konto-Panel und
  der Communication-UI.
- **H8 Backup-Verschlüsselung** (Bundles/Snapshots mit Passphrase).
- **H9 ✅ IdP-`next`-Härtung (12.06. nachts, Tiefen-Review):** der ``next``-
  Parameter der /id/login- und /id/stepup-Seiten war Open-Redirect- und
  XSS-Träger (Angreifer-Link in E-Mail/Webseite ⇒ Redirect auf Fremd-URL bzw.
  Script-Injektion auf der sicherheitskritischsten Seite). Fix `routes.py`:
  `_safe_next()` (nur relative Pfade + eigene Loopback-Hosts) an JEDEM
  Eintrittspunkt + `_esc()`-HTML-Escaping + `_js_str()` (JSON-Literal,
  `<`-escaped) im Passkey-Script. 5 Tests (`test_id_next_haertung.py`).
- **H10 ✅ KANONISCHER BROWSER-HOST `localhost` (13.06. umgesetzt, appkit
  1.2.0):** Fund: RPs schickten den Browser zu `127.0.0.1`, Passkeys gehen nur
  auf `localhost` (WebAuthn: IP ist keine RP-ID) ⇒ Passkey-Step-up aus Apps
  scheiterte, IdP-Sessions zerfielen in zwei Cookie-Welten. FIX (drei Teile):
  (1) RP-Browser-Nav → `DEFAULT_NAV_ISSUER=http://localhost:8200/id`
  (iss-Claim bleibt 127.0.0.1 — nur Identifier; /token+/jwks server-seitig);
  (2) **redirect_uri HOST-KONSISTENT aus dem Request** abgeleitet (PKCE-Cookie
  lebt auf dem App-Host; im PKCE-Cookie mitgeführt, exakter Abgleich bleibt)
  + IdP-Registry mit BEIDEN Loopback-Varianten je Client (additive
  Bestands-Migration in `ensure_clients`); (3) Google-Callback-REDIRECT_URI →
  localhost (Desktop-Client: Google akzeptiert beide Loopback-Formen ohne
  Console-Eintrag). Frontend-`/id/geraete`-Links (TB/News/Komm) → localhost.
  +3 Tests (Cross-Host-Handschlag, Registry-Migration); live verifiziert:
  beide App-Hosts liefern host-konsistente URIs, authorize akzeptiert.

## 7. „Dizz Defense" — KI-Verteidigungssystem (F-DEF1 ✅ GEBAUT 12.06., Vertrag 1.4)
Die Härtungen H1–H8 sind **statisch** (Schlösser & Riegel). Darauf kommt als aktive
Schicht das **Per-App-Immunsystem „Dizz Defense"** (`appkit/defense.py`): Sensorik → Detektion
(Regel-Engine + Basislinie entscheidet, lokale LLM-Triage bewertet/erklärt) →
**gestufte autonome Gegenmaßnahmen** S0 beobachten · S1 drosseln · S2 befristet
blocken · S3 Step-up erzwingen · S4 Lockdown · S5 Not-Aus (S1–S3 autonom/reversibel
mit TTL, S4–S5 default HITL) → Vorfalls-Journal/Lernen → **Föderations-Immunität**
(Dizzi = SOC-Dach, ein Angriff auf eine App warnt alle) + **KI-Selbstschutz**
(Prompt-Injection-Prüfer vor Agenten-Aufrufen). Ehrliche Grenze: volumetrische DDoS
löst nur der Edge-Pfad (Cloudflare/CrowdSec upstream, dokumentiertes Runbook beim
Server-Gang) — die App-Schicht beherrscht L7-Missbrauch. Vollständige Recherche,
Bewertung, Architektur & Bau-Pakete (F-DEF1/F-DEF2/O-DEF): **docs/_archiv/20_RECHERCHE_DEFENSE_KI.md**.

## Quellen (Recherche 12.06.)
- [GitHub Security Lab — Localhost dangers: CORS and DNS rebinding](https://github.blog/security/application-security/localhost-dangers-cors-and-dns-rebinding/)
- [Oligo — 0.0.0.0-Day: Exploiting Localhost APIs From the Browser](https://www.oligo.security/blog/0-0-0-0-day-exploiting-localhost-apis-from-the-browser)
- [CSRF auf Dev-/Localhost-Servern](https://medium.com/@instatunnel/your-dev-server-is-not-safe-the-hidden-danger-of-csrf-on-localhost-36fed5cf0e38)
- [DPAPI-Grenzen & Best Practices (CurrentUser)](https://comcomponent.com/en/blog/2026/03/16/000-windows-app-secret-storage-best-practices-dpapi/) · [Python keyring](https://medium.com/@forsytheryan/securely-storing-credentials-in-python-with-keyring-d8972c3bd25f)
- RFC 9700 (OAuth BCP) · RFC 8252 (Native Apps) · RFC 9864 (Fully-Specified Algs) — s. docs/17
