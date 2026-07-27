# 05 · Dizz Chat — UI-Umbau (26.06.2026)

> Großer UI-Umbau einer LIVE-App, nach Nutzer-Vision + Plan-Freigabe. Baut auf
> D1 (Unified-Inbox/Smart-Contacts/Unified-Reply), Meta/Telegram, CSP-strikt, V5.
> Verifiziert isoliert (Scratch :8296, Temp-Daten-Dir) — Live :8218 unberührt.

## Panel-Layout (Regel: ALLE einklappbar AUSSER Dizz Chat)
1. **Dizz Chat** (NEU, `id="dizzchat"`, **nicht einklappbar, default offen**) — der Kern.
2. **Konten & Konnektoren** (jetzt einklappbar) — E-Mail-Konten + Connector-Katalog.
3. **Posteingang** (einklappbar) — die E-Mail-3-Spalten-Ansicht bleibt.
4. **Kontakte · Smart Contacts** (einklappbar) — Kontakt-Verwaltung.
5. **Anstehende Termine** (einklappbar) — V5-Rücksync + per Triage angelegte Termine.
(Die alten Standalone-Panels „Smart Contacts·Unified Inbox", „KI-Triage", „Video-Call"
sind in Dizz Chat / Kontakte aufgegangen.)

## Dizz Chat
- **Kanalübergreifender Chat pro Kontakt:** Kontaktliste │ Verlauf (`/api/smartkontakte`
  + `…/{id}/verlauf`), jede Nachricht mit **Quellen-Icon** (`kanalIcon`, Emoji je Kanal).
- **Kanal-treue Antwort (HITL):** `…/{id}/antwort` → Aktion `nachricht_senden` (Kanal
  auto/letzter/explizit). Senden bleibt **HITL `verifiziert`, fail-closed**; dormante
  Kanäle: Vorschlag vorbereitet, aber gesperrt.
- **Videocall** integriert (Jitsi v1, on-demand; `videoFuerKontakt`/`videoFuerThread`).
- **KI-Zusammenfassung + Termine** (Knopf `chatTriage`) unten — siehe unten.

## KI-Triage — was es IST (Nutzer-Frage, Gesetz 2)
„KI-Triage" ist eine **rein lokale** Auswertung (Ollama :11434, 0 €; Inhalte verlassen
die Maschine NIE; opt-in über `ki_triage_aktiv`). Bausteine in `kommapp/triage.py`:
- **`triagiere`** = das **übergeordnete, zusammenfassende Werkzeug** (Nutzer-Vermutung
  bestätigt): liefert `{zusammenfassung (2–3 Sätze), wichtig:[…]}` über ALLE Chats
  (kanalübergreifend) — was Reaktion/Frist/Geld braucht.
- `klassifiziere` = je Nachricht Wichtigkeit (hoch/mittel/niedrig) + Kategorie.
- `zusammenfassung` (ein Thread), `entwurf` (Antwort-Entwurf), `frage` (Inbox-Q&A).
Alle JSON-Schema-erzwungen, ehrlicher Fallback ohne Ollama. **Im Dizz Chat** verbaut:
der Knopf ruft `/api/triage` → zeigt die Zusammenfassung unten (alle Chats gebündelt).

## Termin-Auto-Erkennung (Teil des Triage-Knopfs → Sammel-HITL → V5)
`/api/triage` liefert zusätzlich **`termine`** (Vorschläge, NICHT angelegt;
`triage.erkenne_termine`, relative Daten gegen heute, ISO-validiert). Die UI zeigt
„📅 X Termine erkannt — anlegen?"; **erst auf Bestätigung** (HITL) ruft
`termineAnlegen` → `POST /api/termine/anlegen` → je Termin `sende_termin` (V5) in den
**Admin-Kalender**, idempotent. ⚠ Gesetz 10: die LLM-Extraktions-/Datumslogik ist der
subtilste Teil — für robuste Zuverlässigkeit **Architektur-KI** empfohlen (Gerüst = Bau-KI).

## Kontakte · Smart Contacts (Verwaltung)
- `/api/smartkontakte` mit **Suche** (`q`), **Sortierung** (relevanz|menge|name|
  kategorie), **Kategorie-Filter**, **nur Favoriten**; **⭐ Favoriten immer oben**;
  **Top 10 + „mehr aufklappen"**.
- **Kategorie** je Kontakt (Erweitert): Freund · Familie · Geschäftskontakt ·
  Serviceanbieter · Händler · Behörde/Amt · Sonstiges (`POST …/{id}/kategorie`).
  **Favorit** (`POST …/{id}/favorit`). Merge-Vorschläge/Merge/Split/Alias/Simulieren.

## Konten & Konnektoren
E-Mail-Konten (IMAP/Gmail) + **Connector-Katalog** (`/api/konnektoren`): aktiv
(E-Mail/WhatsApp/Instagram/Telegram) + **dormante Slots** (Gesetz 5) Facebook
Messenger/Threads/X/LinkedIn/Slack/Discord/Signal/SMS-RCS/Matrix/Snapchat — je mit
ehrlichem Aktivierungs-Pfad (`connectors_katalog.py`). Tokens/Verbinden im Einstellungs-
fenster (Tresor). Keine echten Plattform-Calls ohne Tokens.

## Invarianten / Verifikation
- **Senden = HITL fail-closed** · **lokal-first** (KI nur Ollama) · **Secrets nur im
  Tresor** · **CSP voll-strikt** (0 inline-Handler, `data-dz-act`) · `appkit`/`ui-kit`
  aus `packages/` READ-ONLY.
- Tests: `C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest -q` (App-Suite **175**
  grün). Browser isoliert (Scratch-Port + Temp-Dir): 0 Konsolenfehler / 0 CSP-Verstöße.
- **Gegateter Live-Neustart :8218 = World-Chat/Nutzer.**
