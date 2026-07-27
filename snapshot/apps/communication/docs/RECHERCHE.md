# Recherche-Dossier — Dizz Communication (Kommunikation)

> Stand 12.06.2026 · web-recherchiert (Quellen unten) · Teil von „the world of dizzi".
> HOCHSENSIBLE App (private Kommunikation) → strikt lokal-first.

## 1. Feature-Baseline (Marktstandard)
Vereinheitlichter Posteingang über Konten/Kanäle, Konversations-Ansicht, Suche, Entwürfe/
Senden, Benachrichtigungen, Kontakte als Klammer, Video-Calls. Vorbilder: Thunderbird
(E-Mail-Architektur), **Beeper** (Messenger-Vereinheitlichung), Ferdium/Rambox (Webview-Aggregation).

## 2. Die zentrale Architektur-Erkenntnis: ZWEI Schienen für Messenger
**Schiene A — Webview-Einbettung (sofort, ToS-sicher):** WhatsApps offizielle Desktop-App ist
selbst nur noch ein **Web-Wrapper**; Aggregatoren wie **Ferdium** betten WhatsApp Web/Instagram
per Webview ein. Für **manuelle** Nutzung legal/toleriert — kein Bann-Risiko. Passt perfekt zur
späteren **Tauri-Schale** (Webview ist deren Kernfähigkeit); übergangsweise eingebettetes
Browser-Fenster/Edge-WebView2.
**Schiene B — Matrix + Bridges (echte Vereinheitlichung, self-hosted „Beeper-Modell"):**
Matrix-Homeserver (Synapse/Conduit, lokal) + **mautrix-Bridges** (WhatsApp via QR-Pairing,
Signal, Telegram [stabilste], Instagram/Meta, Slack/Discord) → ALLE Chats in EINEM Protokoll,
eigener Client, lokale Speicherung/Suche. Beeper (Automattic) beweist die Architektur produktiv;
Bridges sind self-hostbar. **Ehrliches Risiko (G2):** Bridges nutzen inoffizielle Protokolle —
Meta verbietet **Automatisierung**; persönliche, nicht-automatisierte Nutzung wird i. d. R.
toleriert, Rest-Bann-Risiko bleibt (dokumentierte Fälle bei whatsapp-web.js-Automation). →
**Opt-in je Dienst mit Risiko-Aufklärung; KEINE Automatisierung über Bridges; Senden immer HITL.**

## 3. E-Mail (Kern der App, risikofrei)
- **OAuth 2.0 ist Pflicht** bei allen Großen (Microsoft schaltet Basic Auth **30.04.2026** final ab;
  Gmail/Yahoo erzwingen OAuth) → `EmailSource`-Adapter mit **IMAP/SMTP + XOAUTH2** als Fundament.
- **Gmail**: via IMAP+OAuth ODER Gmail-API; unser Google-OAuth-Client (Dizzi-ID, K1) kann um
  Mail-Scopes erweitert werden — Tokens in den **K2-Token-Tresor**.
- **JMAP** (RFC-Familie, Fastmail/Stalwart/Cyrus; Thunderbird rollt aus) als zukunftssicherer
  Adapter-Slot; JSContact/JSCalendar folgen → Brücke zu Dizz Plans.
- Verbindungs-Disziplin: IMAP-Connection-Limits je Provider beachten (Pooling, ein Sync-Worker).

## 4. Video-Calls
**Jitsi Meet** einbetten (iframe-API, self-hostbar, 0 €) = Schiene A; mit Matrix später
**Element Call / Matrix RTC** = Schiene B. Eigener WebRTC-Stack ist unnötig (Rad nicht neu erfinden).

## 5. Verbindungs-Vorbereitungen (Gesetz 5 — jetzt vorsehen)
- **`KanalSource`-Adapter-Interface** (analog BankSource/HealthSource): `EmailImapSource`,
  `GmailApiSource`, `JmapSource`, `MatrixSource` (deckt ALLE Bridge-Messenger ab!), `WebviewKanal`
  (nur UI-Einbettung, keine Daten). Ein Interface, viele Stecker.
- **Nachrichten-Schema kanal-agnostisch**: konto → konversation → nachricht (UUID/user_id/
  Timestamps/Soft-Delete), `kanal_typ` + `extern_id` — damit E-Mail und Chat in EINER Struktur leben.
- **Kontakte-Tabelle** als kanalübergreifende Klammer (Person ↔ Adressen/Handles je Kanal).
- **Matrix-Slot**: Homeserver-URL + Zugangsdaten im Tresor; Bridge-Verwaltung als Settings-Sektion.
- **Tauri-Webview-Slot** für Schiene A (Abhängigkeit Rust/Tauri — wie Health notiert).

## 6. Sensibilität & Sicherheit
sensitivity **hoechst**: Inhalte NIE an Boost/Cloud-Modelle (KI-Triage nur lokal via Ollama);
OAuth-/Matrix-Tokens nur im Fernet-Tresor; Zugriff hinter verifizierter Verbindung; **Senden =
HITL-Aktion** (K4) auf Stufe `verifiziert`+. Lokale Mail-/Chat-Kopien verschlüsselt at-rest (H2/H8).

## 7. Offene Entscheidungsfragen → vor dem Bau (R2.x)
1. **Schienen-Reihenfolge**: A (Webview, sofort nutzbar) zuerst, B (Matrix) als Stufe 2 — ok?
2. Welche **E-Mail-Konten** konkret (nur Gmail? + weitere IMAP-Anbieter)?
3. Matrix-Homeserver lokal (Conduit, leichtgewichtig) vs. später — und welche Bridges zuerst
   (WhatsApp? Signal? Telegram=stabilste)?
4. Video: reicht Jitsi-Einbettung v1?

## Quellen
- [Matrix.org — Bridges-Ökosystem](https://matrix.org/ecosystem/bridges/) · [mautrix-whatsapp Setup (QR-Pairing)](https://docs.mau.fi/bridges/go/setup.html?bridge=whatsapp)
- [Beeper — Bridges & Self-Hosting](https://developers.beeper.com/bridges) · [How Beeper Android Works (lokale Bridges)](https://blog.beeper.com/2024/04/09/how-beeper-android-works/)
- [WhatsApp Desktop wird Web-Wrapper](https://www.ghacks.net/2025/07/21/whatsapp-desktop-uwp-app-is-being-replaced-by-a-web-wrapper/) · [Bann-Fälle bei whatsapp-web.js-Automation](https://github.com/wwebjs/whatsapp-web.js/issues/3594)
- [OAuth-Pflicht/Microsoft Basic-Auth-Ende 2026](https://www.getmailbird.com/microsoft-modern-authentication-enforcement-email-guide/) · [JMAP-Stand 2026](https://www.getmailbird.com/email-sync-protocol-changes-performance-security/)
