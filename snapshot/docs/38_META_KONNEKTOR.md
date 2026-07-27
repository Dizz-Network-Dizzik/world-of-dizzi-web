# 38 · META-KONNEKTOR (WhatsApp + Instagram) — Spec + Onboarding-Checkliste

> **Ziel:** Communications Unified-Inbox um die großen Meta-Kanäle erweitern (WhatsApp Business
> Cloud API + Instagram-DMs). Aufbauend auf dem W4-Connector-Gerüst (`appkit/connectors.py`) + D1
> (Unified-Inbox/Smart-Contacts/Unified-Reply). **Bau im Communication-Chat; dormant gegen die echte
> API, scharf sobald die Meta-Tokens da sind.** Stand 21.06.2026.
>
> ⚠️ **API-Version gegenchecken:** Graph-API-Versionen + exakte Permission-Namen ändern sich; der
> Communication-Chat verifiziert die konkreten Endpunkte/Felder/Versionen gegen Metas Live-Doku
> (developers.facebook.com/docs/whatsapp/cloud-api + .../instagram-platform). Diese Spec gibt das
> Gerüst + die belastbaren Grundlagen.

## ★★ STATUS 21.06. (später) — META-KONNEKTOR GEBAUT + ABSORBIERT (Communication-Chat → World-Chat, Gesetz 9)
Der Communication-Chat hat das §3-Paket **fertig gebaut**; der World-Admin-Chat hat es verifiziert:
`kommunikation` HEAD `2f3e760`, Repo clean, **253 grün / 1 skip** (venv-pytest), 5 Commits (`meta.py` ·
`channels.py`-Kopplung · `main.py` /api/konnektoren+Webhook+Verbinden-Flow · Config-UI CSP-strikt · Doku-Sync).
**Gebaut gegen die echte Graph-API, DORMANT bis Token im Tresor:**
- `kommapp/meta.py` — Outbound-Body-Builder WA (`whatsapp_body`: Session-Text vs `template`, 24-h-Regel) +
  IG (`instagram_body`) + `graph_send` (Bearer-Token, `MetaApiFehler` bei HTTP≥400); Webhook `webhook_verify`
  (hub.verify_token) + `pruefe_signatur` (X-Hub-Signature-256 über Roh-Body) + `webhook_parse` (WA+IG →
  normiertes Unified-Inbox-Schema); `WhatsAppConnector`/`InstagramConnector` über W4 `ExternalConnector`
  (`verfuegbar()` = Token im Tresor vorhanden; `senden` = Außen-Kante, in der App nur hinter K4-HITL).
- Tresor-Schlüssel `meta_whatsapp_token`/`meta_instagram_token`; Settings `whatsapp_phone_number_id`/
  `instagram_user_id`/`graph_version` (Default `v23.0`). **Das appkit-W4-Gerüst reichte — keine Master-Änderung.**
- `main.py`: `GET/POST /api/kanaele/meta/webhook` + `GET /api/konnektoren` + Verbinden-Flow + Config-UI
  (Token→Tresor, Status, Test-Sende) im Einstellungsfenster (CSP-strikt).
⇒ **§3 (Bauen) erledigt.** **OFFEN = Betrieb/Aktivierung (Nutzer/gated):** (a) gegateter **:8218-Neustart**
(lädt CSP-strikt + D1 Unified-Inbox + Meta-Webhook-Route; läuft sonst noch alter Code) · (b) Token + IDs über
die **Config-UI** in den Tresor → **Outbound live** (Testnummer, ~5 verifizierte Empfänger) · (c) Inbound erst
mit **Tunnel/Server** (Webhook-Empfänger ist gebaut) · (d) Instagram-Produkt anhängen + Business-Verifizierung.

## ★ STATUS 21.06. — WhatsApp Test-Setup LIVE-BEWIESEN (mit Nutzer, computer-use-geführt)
Im Meta-Portal gemeinsam eingerichtet + Sende-Pfad **end-to-end bewiesen** (echte WhatsApp-Nachricht aufs Handy):
- Meta-App **„Dizz Communication"** erstellt · Use-Case „Über WhatsApp …" · Business-Portfolio **„Dizz Network"**
  angelegt (UNverifiziert — Verifizierung später, §1/§3, für Produktiv).
- WhatsApp **Test-Telefonnummer** aktiv · eigene Handynummer als Empfänger verifiziert · `hello_world`-Template
  erfolgreich gesendet ✓.
- **Systemnutzer `dizz-connector`** (Admin) angelegt, App + WhatsApp-Konto zugewiesen, **dauerhafter Token erzeugt
  + sicher beim Nutzer abgelegt** (Passwort-Manager → später in den Communication-Tresor; Token = Geheimnis, NICHT im Repo).
- Die konkreten IDs (Telefonnummer-ID / WABA-ID / Testnummer) liegen beim Nutzer (lokal/Übergabe) — bewusst NICHT
  hier im Repo (account-spezifisch; jede App ist standalone-verkaufbar).
⇒ Test-/Build-Voraussetzungen stehen. **OFFEN:** Connector im Communication-Chat bauen (§3, dormant gegen genau dieses
Setup); Inbound-Webhook braucht öffentliche URL (Tunnel/Server, §2); Instagram an dieselbe App anhängen; Business-
Verifizierung für Produktiv (§1/§3).

## 1 · Der eigentliche Engpass = Metas Business-Onboarding (DU, nicht der Code)
Der Code ist baubar; aktivierbar wird er erst nach Metas Freigaben. **Onboarding-Checkliste (Nutzer):**

**WhatsApp Business Cloud API:**
1. Meta-Konto + **Meta Business Portfolio** (business.facebook.com).
2. **Business-Verifizierung** (Meta prüft die Geschäfts-Identität per Dokumenten) — nötig für
   produktives Messaging über die Test-Limits hinaus.
3. **WhatsApp Business Account (WABA)** + eine **Telefonnummer** (noch nicht bei WhatsApp / migriert).
4. **Meta-App** (developers.facebook.com) mit Produkt „WhatsApp".
5. **Dauerhafter Token via System-User** (Business-Einstellungen → System-User), Rechte
   `whatsapp_business_messaging` + `whatsapp_business_management` (temporäre Tokens laufen in 24 h ab).
6. **App-Review** für `whatsapp_business_messaging` (um an echte Nummern statt nur Test-Nummern zu senden).
7. Spielregeln: **24-h-Kundendienst-Fenster** (frei antworten nur ≤24 h nach der letzten Nutzer-Nachricht);
   außerhalb nur **vorab genehmigte Message-Templates**.

**Instagram-DMs:**
1. **Instagram-Profikonto** (Business/Creator), verknüpft mit einer **Facebook-Seite**.
2. Meta-App mit **Instagram-Platform/Messenger**-Produkt.
3. Rechte `instagram_basic` + `instagram_manage_messages` (+ Seiten-Rechte) — via **App-Review** + Business-Verifizierung.
4. Webhook auf der Seite für Messaging-Events; ähnliches 24-h-Fenster.

## 2 · ★ Lokal-zuerst-Spannung (wichtig, Konzept) — Eingang braucht eine öffentliche URL
- **Senden (Outbound)** geht **lokal** problemlos: die App ruft `graph.facebook.com` (ausgehend).
- **Empfangen (Inbound)** läuft bei Meta **NUR über Webhooks** (Meta pusht an eine öffentliche HTTPS-URL).
  Eine reine 127.0.0.1-App hat keine öffentliche URL ⇒ Eingang braucht entweder **(a)** einen Tunnel
  (cloudflared/ngrok) im Lokalbetrieb **oder (b)** die spätere Server-/kommerzielle Ausprägung.
- ⇒ **Plan:** Outbound + die ganze Verarbeitung (Normierung/Smart-Contacts/HITL) lokal bauen; Inbound-
  **Webhook-Empfänger bauen**, aber das tatsächliche Empfangen hängt am Tunnel/Server (dokumentierter Slot,
  passt zur docs/35-Linie „lokal-zuerst + Server offen"). Das ist KEIN Code-Blocker, nur eine Betriebs-Frage.

## 3 · Was der Communication-Chat baut (dormant, gegen die echte API)
- `MetaChannelConnector` (gemeinsame Basis über W4 `ExternalConnector`) + `WhatsAppConnector` + `InstagramConnector`.
- **Outbound (Senden):** Graph-API-Aufruf (`POST /<version>/<phone-number-id>/messages` für WA; IG analog
  über die Seite). **Session-** vs. **Template-Nachrichten** (WA-24-h-Regel) abbilden. **Senden = K4-HITL
  `verifiziert`, fail-closed** (nie autonom).
- **Inbound:** Webhook-Empfänger `GET/POST /api/kanaele/meta/webhook` (GET = Verify-Challenge mit
  `hub.verify_token`; POST = Nachrichten-Events) → normieren auf das Unified-Inbox-Modell + **Smart-Contact-
  Unifikation** (Telefonnummer/IG-Handle → kanonischer Kontakt) + Herkunfts-Label.
- **Secrets:** WABA-/IG-Token + App-Secret + Webhook-Verify-Token im **Tresor** (OS-Secret-Store), NIE in DB/Settings.
- **Config-UI:** Verbinden-Flow im Communication-Einstellungsfenster (Token eintragen, Status, Test-Sende).
- **Alles DORMANT** (`verfuegbar()==False` bis Tokens da) + `/api/kanaele` zeigt den Status ehrlich (wie health/sources).
- Echte Plattform-Calls erst nach Tresor-Tokens + (für Inbound) Tunnel/Server.

## 4 · Reihenfolge
1. **Nutzer:** Onboarding §1 starten (Business-Verifizierung + WABA/IG + App-Review laufen Wochen — parallel).
2. **Communication-Chat:** §3 dormant bauen + testen (Mock-Webhook-Payloads, Unit-Tests; Outbound gegen einen
   Test-Token wenn vorhanden). 
3. **Aktivierung:** Tokens in den Tresor → Outbound live; Inbound sobald Tunnel/Server steht.
> **Schneller Gegenbeweis optional:** Telegram (nur Bot-Token, kein Review, Webhook ODER Long-Polling möglich
> ⇒ läuft auch rein lokal) wäre der end-to-end-Beweis ohne Wochen-Wartezeit — kann parallel als Pilot laufen.
