# 31 · REMOTE-MCP-GATEWAY — „die EINE Verbindung zu allem"

> **Erstellt 19.06.2026 (World-Admin-Chat). v1 GEBAUT + getestet (Core 154 grün).** Setzt die
> Nutzer-Vision um: *einmal über Dizzi/Core verbinden → darüber ist die Verbindung zu allen anderen Sachen
> gewährleistet.* Recherche/Einordnung: docs/_archiv/30 §H1/§3 · Plan: docs/11 ★★★ 19.06.

## 1. Was es ist
Der Core (`:8200`) aggregiert bereits die App-MCP-Werkzeuge für seinen **eigenen** Agenten
(`core/app/ai/tools.py` → `registry()`). Das Gateway dreht das **nach außen**: ein **MCP-Server über HTTP**
(`core/app/ai/mcp_gateway.py`, JSON-RPC 2.0 / Streamable-HTTP), an den sich eine **externe KI** (Claude
Desktop/Code, IDE-Agent, künftige Agenten) **einmal** verbindet und damit das ganze Netzwerk erreicht —
statt jede App einzeln einzubinden.

## 2. Endpunkte (Core)
| Methode/Pfad | Zweck |
|---|---|
| `POST /mcp` | Der MCP-Endpunkt (JSON-RPC 2.0): `initialize` · `tools/list` · `tools/call` · `ping` · Notifications (202). Einzel + Batch. |
| `GET /mcp/info` *(nur localhost)* | Status + Token + fertige `claude_config` (zum Einfügen in den MCP-Client). |
| `POST /mcp/enable` / `/mcp/disable` *(lokal)* | Gateway an/aus (opt-in). `enable` liefert Token + `claude_config`. |
| `POST /mcp/rotate-token` *(lokal)* | Bearer-Token neu vergeben (alter wird ungültig). |

## 3. So verbindet man Claude (sobald der Core mit dem neuen Code läuft)
1. Lokal `POST http://127.0.0.1:8200/mcp/enable` (oder über einen späteren Schalter im Core-Frontend).
2. Die Antwort enthält `claude_config` — z. B.:
   ```json
   {"mcpServers": {"dizz-network": {
     "url": "http://127.0.0.1:8200/mcp",
     "headers": {"Authorization": "Bearer dzmcp_…"}}}}
   ```
3. In den MCP-Client (Claude Desktop/Code) eintragen → die KI sieht die Netzwerk-Werkzeuge.

## 4. Sicherheitsmodell (v1)
- **Opt-in:** standardmäßig AUS (Setting `mcp_gateway_enabled`). Erst einschalten.
- **Bearer-Token-Pflicht**, sobald aktiv — auch lokal (kein anderer Prozess soll frei zugreifen). Token
  per `secrets`, rotierbar. Verwaltung (info/enable/disable/rotate/freigabe) **nur von localhost**.
- **READ-ONLY:** das Gateway exponiert `registry(sensitive=True)` ⇒ **nur die nicht-sensiblen App-/Daten-
  Tools** (Web-Suche/Boost & PC-verlassende Tools sind ausgeschlossen). **Keine** Schreib-/Aktions-Tools —
  die laufen weiter über die **App-eigene K4-HITL**-Freigabe. Eine externe KI kann also **lesen/abfragen**,
  aber **nichts eigenmächtig auslösen**.
- **★ HOCHSICHER-GATE (Nutzer-Wunsch 19.06.):** hochsicher-eingestufte Inhalte — **verschlüsselte Tresor-
  Dokumente, Echtgeld, Geheimnisse** — sind extern **gesperrt**. Mechanik: jedes Tool bekommt eine Stufe
  (`normal` < `hoch` < `hoechst` < `hochsicher`) aus der App-Sensitivität (`<app>_…`-Präfix) + Krypto-/Datei-/
  Echtgeld-**Namensmustern** (`*_datei*`, `*verschluessel*`, `*echtgeld*`, `*_secret*`, `*passwort*` …, per
  Setting erweiterbar). Standard-Höchststufe = `hoch` (Setting `mcp_gateway_ceiling`) ⇒ `hoechst`/`hochsicher`-
  Tools erscheinen **nicht** in `tools/list` und ein direkter `tools/call` wird mit „explizite Freigabe nötig"
  abgewiesen (keine Daten). **Explizite Freigabe:** lokal `POST /mcp/freigabe-hochsicher?minuten=30` schaltet
  hochsicher zeitlich befristet frei; `POST /mcp/freigabe-sperren` widerruft sofort; `/mcp/info` zeigt den
  Zustand. ⇒ Claude/externe Agenten kommen an Hochsicher-Dokumente **nur** mit deiner bewussten Freigabe.
  *(Fein-Filter v2: die Tresor-MCP-Tools schließen verschlüsselte Dokumente schon app-seitig aus den Treffern
  aus — wird beim Wiring des Admin-Connectors ergänzt; das Gateway-Gate ist der Backstop davor.)*
- **Audit:** jeder Tool-Call/-Fehler/-Sperre + jede Freigabe wird im Core auditiert (`mcp_gateway`).

## 5. Stand + Gates
- **v1 gebaut + getestet** (`core/tests/test_mcp_gateway.py`: Protokoll-Fluss + Token-/opt-in-Sicherheit;
  Core gesamt **154 grün**). Router in `main.py` verdrahtet.
- **GATED:** der **Live-Core (:8200) läuft mit altem Code im Speicher** ⇒ das Gateway wird erst nach einem
  **gegateten Core-Neustart** (Backup + Nutzer-Go; der Core trägt das Netzwerk-SSO) live.
- **Tool-Breite:** aktuell sind im Core-Tool-Bus die Connectoren aus `MCP_SERVERS` angebunden (heute
  `tradingbot`). Mehr Apps = deren `mcp_server.py` als Connector hinzufügen (mechanisch, eigener Schritt) —
  das Gateway zieht sie dann automatisch mit.

## 6. v2-Roadmap (für echtes Remote off-host)
- **OAuth 2.1 / Dynamic Client Registration über Dizzi-ID** (statt statischem Bearer-Token) — der Core ist
  bereits der OIDC-Provider (`core/app/id/`), das Gateway hängt sich an dessen Token-Prüfung. Dann auch
  `WWW-Authenticate`-Discovery (`/.well-known/oauth-protected-resource`) + TLS für Off-Host-Zugriff.
- **Schreib-/Aktions-Tools über K4-HITL** im Gateway: `tools/call` einer Aktion erzeugt einen K4-`propose`,
  der Nutzer gibt frei (Glocke), erst dann Wirkung — externe KI schlägt vor, nie eigenmächtig.
- **MCP-Tasks-Extension** (lange Läufe: Berichte/Imports) + optional **MCP-Apps** (eingebettete UI-Panels).
- **Connector-Vollausbau:** alle App-`mcp_server.py` als Core-Connectoren ⇒ das ganze Netzwerk an einem Endpunkt.

## 7. PER-APP-GATEWAY (Föderations-Konsistenz, Nutzer-Wunsch 19.06.) — ✅ v1 GEBAUT (Admin-Referenz)
**Prinzip:** Jede App ist auch **einzeln** nutz-/verkaufbar (Föderation, docs/11 §1.3). Darum bekommt **jede App
ihr EIGENES MCP-Gate** (`appkit/app_gateway.py` → `build_app_gateway`), das im **Standalone-Betrieb** greift —
eine externe KI verbindet sich dann direkt mit dieser einen App. **Sobald die App am Netzwerk hängt und der
Core sein zentrales Gateway aktiv hat, schaltet sich das App-Gate im Modus `auto` automatisch ab** (dann ist
der Core die EINE Verbindung). Genau das vom Nutzer beschriebene Verhalten.

- **Modi** (Setting `mcp_gateway_mode`, lokal über `POST /mcp/mode?wert=auto|an|aus`): `auto` (Default) =
  aktiv NUR wenn der Core das zentrale Gateway NICHT führt (Standalone-Erkennung via Probe auf `core/mcp/info`,
  60 s gecacht) · `an` = immer · `aus` = nie. Endpunkte je App: `POST /mcp`, `GET /mcp/info`, `/mcp/mode`,
  `/mcp/freigabe-hochsicher`, `/mcp/freigabe-sperren`.
- **Gleiche Sicherheit wie das Core-Gateway:** Bearer-Token, read-only, **Hochsicher-Gate** (verschlüsselte
  Dokumente/Echtgeld nur nach expliziter Freigabe; Stufe aus App-Sensitivität + Krypto-/Datei-Mustern).
- **Tool-Quelle:** dieselbe **deklarative** `(name, pfad, beschreibung)`-Liste wie der stdio-MCP — bei Admin
  zentral in `adminapp/mcp_tools.py` (`MCP_TOOLS`), genutzt von `mcp_server.py` (stdio) UND dem App-Gateway
  (`main.py`). Tool-Aufruf = GET der App-eigenen HTTP-API.
- **Stand:** Modul kanonisch in `the world of dizzi/appkit/app_gateway.py`, in **Admin als Referenz** vendort
  + verdrahtet + getestet (`leading/tests/test_app_gateway.py`, **leading 129 grün**); live verifiziert
  (Standalone: 13 Admin-Tools über `/mcp`). **OFFEN (World-Chat-Rollout):** `appkit/app_gateway.py` in die
  übrigen App-Repos vendoren + je App `mcp_tools` extrahieren + in `main.py` mounten + der Mode-/Freigabe-
  Schalter ins App-Einstellungsfenster (UI = Panel-Bautool).
