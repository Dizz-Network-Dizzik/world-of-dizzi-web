# Anforderungsliste — Dizz Communication — Kommunikation

> Kern-Umfang, der beim Bau zu erfüllen ist. Bewusst flexibel/ergänzbar gehalten.

## Kern (Muss)
- [x] Kanal-agnostisches Nachrichten-Schema (konto/konversation/nachricht + Kontakte-Klammer)
- [x] `EmailImapSource` (IMAP/SMTP + XOAUTH2) + Gmail-Anbindung (Tokens im Tresor)
- [x] Vereinheitlichter Posteingang — lesen ✅ (Konversation/Thread, Teil B) + **suchen** ✅
      (Mehrwort-UND, lokal) + beantworten = HITL ✅ (Teil C)
- [ ] Webview-Schiene (WhatsApp Web & Co. einbetten) — Setting-Slot vorbereitet (Gesetz 5, Teil D);
      UI-Einbettung offen (Schiene A, eigene Session)
- [x] Stats-Endpoint: ungelesen je Kanal (KPI „ungelesen", Teil B), letzte Synchronisation
- [x] MCP-Tools: read-only NUR Metadaten (kachel_stats, posteingang_uebersicht, ungelesen,
      letzte_nachrichten, konten) + EIN HITL-Aktions-Tool (mail_senden_vorschlagen, schlägt nur vor)

## Stufe 2 (vorbereitet)
- [ ] **Matrix-Schiene**: lokaler Homeserver + mautrix-Bridges (opt-in je Dienst,
      Risiko-Aufklärung, KEINE Automatisierung) → `MatrixSource` — Setting-Slots vorbereitet
      (Gesetz 5, Teil D); Bau offen (Schiene B, eigene Session)
- [x] Jitsi-Video-Einbettung v1 (Setting `jitsi_domain`, self-host-fähig, on-demand iframe);
      später Element Call
- [x] lokale KI-Triage (Ollama, HITL): Zusammenfassung + Per-Nachricht Wichtigkeit/Kategorie
      (Teil D) + inbox-aware App-KI (Mini-Dizzi, set_app_ki) · JMAP-Adapter-**Slot** vorbereitet
      (Gesetz 5, `JmapQuelle` fail-closed) — Ausimplementierung offen · [ ] Antwort-Entwürfe durch KI

## Quer (aus dem App-Vertrag, gilt für alle)
- [x] Stats-Endpoint `/api/summary` (Dashboard-Kachel)
- [x] MCP-Server (read-only Tools, NUR Metadaten — Nachrichten-Volltexte bleiben lokal)
- [x] Dizzi-ID-Anbindung (SSO) + lokaler Standalone-Login
- [x] Account/Settings-Modul (K2) — OAuth-Tokens NUR im Tresor
- [x] Daten user-scoped + sync-ready; Inhalte strikt lokal (sensitivity hoechst)
- [x] Tests + Doku-Sync (Gesetz 9)

## Entschieden (bei Anlage, 12.06.)
- **Marke:** Dizz Communication · Port **8218** · sensitivity **hoechst**
- **Zwei-Schienen-Strategie** (Webview sofort / Matrix+Bridges als echte Vereinheitlichung)
- Senden/Antworten IMMER Human-in-the-Loop; keine Bridge-Automatisierung (Bann-Risiko, G2)

## Offen (Fragerunde vor Bau)
- [ ] Schienen-Reihenfolge bestätigen · konkrete E-Mail-Konten · Bridge-Auswahl · Jitsi v1
