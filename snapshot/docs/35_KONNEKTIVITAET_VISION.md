# 35 · KONNEKTIVITÄT — das Kernziel (Nutzer-Leitlinie 20.06.2026)

> **Festgehalten auf ausdrücklichen Nutzer-Wunsch (20.06.2026).** Dies ist ein **Nordstern-
> Dokument**: es legt das übergeordnete Ziel fest, an dem sich alle künftigen Pakete ausrichten.
> Die **Umsetzung ist gestaffelt + vorbereitend** (dormante Slots wie bei Gesetz-5/Wearable-Prep),
> die volle Außen-Integration kommt, „wenn es nötig wird" — aber die **Architektur wird jetzt
> darauf ausgelegt.**

## 1 · Der Grundgedanke
„the world of dizzi" soll die **ultimative Vernetzungs-Plattform** sein — für das **Gesamtsystem**
UND für **jede einzelne App** (jede App ist auch ein eigenständig verkaufbares Produkt, daher trägt
jede App ihre Konnektivität + Sicherheit selbst, vgl. das per-App-`defense`/-`appkit`/-`/mcp`-Muster).
- **Lokal-zuerst bleibt Pflicht:** das System läuft vollständig lokal auf dem Rechner des Nutzers —
  und ist **trotzdem** das „Vernetzungs-Übertool". Eine spätere kommerzielle/Server-Ausprägung ist
  ein **eigenes, größeres Thema** (Architektur offenhalten), darf das Lokal-zuerst-Versprechen nie brechen.
- **Alle Wege nach außen offenhalten:** zu anderen Apps, Diensten, externen (KI-)Tools — heute
  vorbereitet, später aktivierbar. Ziel: **absolute Flexibilität, Vernetzbarkeit jedweder Art.**
- **Erlebnis:** super-funktional, effizient, übersichtlich, systematisch, **intuitiv + selbsterklärend**,
  macht Spaß. Der Nutzer bringt „den Dschungel verschiedener Apps unter einen Hut".

## 2 · Leitbeispiel — Dizz Communication = das Vernetzungs-Flaggschiff
Communication soll **alle kommunikativen Kanäle** unter einem Dach vereinen: E-Mail · Telegram ·
WhatsApp · Instagram · Snapchat · … (erweiterbar).
- **Smart Contacts (Kontakt-Unifikation):** laufen mehrere Kanäle auf **dieselbe Person**, werden sie
  zu **EINEM Kontakt** zusammengeführt. Im Dizz-Chat erscheinen die Nachrichten aus allen Kanälen
  **zusammengefasst unter diesem einen Kontakt**, jede Nachricht **mit kleinem Herkunfts-Label**
  (woher sie kam).
- **Ein Posteingang, alle Plattformen:** der Nutzer verwaltet **alle** Messenger/Mail aus **einem**
  Dizz-Chat; pro Kontakt ein durchgehender Verlauf über alle Kanäle.
- **Unified Reply (rückläufig):** eine Antwort aus dem Dizz-Chat geht **wahlweise** über einen
  **explizit gewählten Kanal** („antworte ihm über Telegram") **oder automatisch** über den Kanal der
  **zuletzt eingegangenen** Nachricht. Aus dem einen Chat heraus auf **alle** Kanäle senden.
- **Sicherheit:** Communication ist `hoechst` ⇒ Inhalte lokal, Senden bleibt **HITL** (`verifiziert`,
  fail-closed). Outbound-Konnektoren laufen nie autonom an Plattformen.

## 3 · Leitbeispiel — Dizz Admin = externe Tools im Griff
Admin soll **externe Tools/Dienste** in die eigenen **Pläne/Verwaltung** integrieren: Überblick behalten
**und** ansteuern können (z. B. fremde Kalender/Projekt-/Office-Tools in die Bereichs-/Fristen-Sicht
falten). Die Bereichs-Achse (docs/_archiv/28/34) ist der natürliche Andockpunkt.

## 4 · Trading (Solo-Projekt, aber nicht außen vor)
Beim Gesamt-Erlebnis steht TB nicht im Vordergrund (komplexer Solo-Stack), aber auch TB soll
**externe (KI-)Tools** anbinden können, die **Daten/Einflüsse** beisteuern — Konnektivität als Option.

## 5 · Architektur-Prinzipien (wie wir das bauen)
1. **Connector-Framework (universell, dormant-fähig).** Ein einheitliches Muster „externe Quelle/
   Senke" — analog zu `health/sources.py` (Wearable-Prep) + `management` ChannelSource: Interface +
   dormante Adapter + `/api/quellen`-Sichtbarkeit + Mode-Schalter im Einstellungsfenster. **In appkit**
   als wiederverwendbares Gerüst, damit JEDE App es erbt (Standalone-Konnektivität).
2. **Daten bei der Quelle, Lesen über Relay, Schreiben über HITL.** Wie V2–V19: read-only-Lesepfade
   zentral-auditiert; jede Außenwirkung (Senden/Posten/Buchen) bleibt hinter der App-HITL-Freigabe.
3. **Identitäts-/Kontakt-Unifikation als eigener Baustein** (Communication-Pionier, dann Kit-Kandidat):
   Kontakt-Matching über Kanäle (E-Mail/Handle/Telefon) → ein kanonischer Kontakt + Kanal-Aliasse.
4. **Sicherheit ist Teil der Konnektivität.** Jede neue Außen-Kante: Sensitivitäts-Routing
   (`lokal_only` für hoechst), Token/Secret im OS-Secret-Store, MCP-Hochsicher-Gate, CSP/Header,
   HITL. Konnektivität OHNE diese Härtung wird nicht ausgeliefert.
5. **Föderation: lokal vollwertig, Server-fähig offen.** Per-App-`/mcp` + zentrales Core-Gateway
   bleiben das Rückgrat; die Server-/Multi-User-Ausprägung wird als späteres Paket sauber darauf gesetzt.

## 6 · Status = VORBEREITUNG
Heute ist die **Grundlage** da (Core-Relays V2–V19, per-App-MCP-Gateway, `health/sources`-Muster,
`management` ChannelSource dormant, Communication JMAP-Slot). Dieses Dokument hebt das zum **Kernziel**
und ordnet die nächsten Pakete darauf aus (Plan: docs/_archiv/36). **Volle externe
API-Integrationen** (echte Telegram-/WhatsApp-/…-Anbindung) sind **heavy + teils Architektur-KI-Park** — sie
werden vorbereitet (Connector-Gerüst + dormante Adapter + UI-Slots), scharf geschaltet „wenn nötig".
