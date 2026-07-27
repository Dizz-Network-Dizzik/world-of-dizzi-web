# Vision — Dizz Communication — Kommunikation

**Die Kommunikations-Zentrale**: der komplette persönliche Nachrichtenverkehr an einem
Ort — E-Mail (Gmail + alle Anbieter), Messenger (WhatsApp, Signal, Telegram, …),
Kommunikations-Teile sozialer Medien (Instagram-DMs, …) und Video-Calls.

**Datenschutz:** SENSIBLE App — private Kommunikation bleibt standardmäßig lokal,
Zugriff nur bei verifizierter Verbindung; Inhalte gehen NIE an Cloud-/Boost-Modelle.

## Was die App leisten soll
- **Vereinheitlichter Posteingang** über E-Mail-Konten (IMAP/SMTP + OAuth2, Gmail-API,
  JMAP-Slot) — lesen, beantworten, durchsuchen
- **Messenger-Anbindung in zwei Schienen** (Recherche docs/RECHERCHE.md):
  (a) **Webview-Einbettung** (WhatsApp Web, Instagram, …) — sofort, ToS-sicher;
  (b) **Matrix-Homeserver + Bridges** (Beeper-Architektur, self-hosted) — echte
  Vereinheitlichung, optional je Dienst mit ehrlicher Risiko-Aufklärung
- **Video-Calls**: Jitsi-Meet-Einbettung (iframe-API), später Element Call (Matrix RTC)
- **KI-Wächter** (lokal!): Posteingangs-Triage, Antwort-Entwürfe (HITL), Follow-up-Erinnerungen
- Kontakte als verbindende Klammer über alle Kanäle

## Eigenständig + vernetzt
Diese App läuft eigenständig (eigenes Konto + Einstellungen, eigener Login als Rückfall) und ist
einzeln verkaufbar. Im Verbund meldet sie sich per Dizzi-ID an (Single-Sign-On), erscheint als
Panel in Dizzis Dashboard und ist über ihren MCP-Server für Dizzis KI ansprechbar.
