# App-Vertrag — Normative Spezifikation (Kernpaket K3) · v1.0 · 12.06.2026

> **Status: GEBAUT.** Implementierung = `appkit/` (kanonische Bibliothek) +
> `templates/refapp/` (Referenz-App zum Kopieren) + generischer Konsum im
> Dizzi-Core (`core/app/panels.py`). Der Vertrag ist **maschinell erzwungen**:
> `appkit/conformance.py::check_contract` läuft in der Test-Suite jeder App.
> Dieses Dokument ist die menschenlesbare Norm dazu; bei Widerspruch gilt der Code.

## 1. Grundsatz: Föderation
Jede App ist **eigenständig + einzeln verkaufbar** und ENTHÄLT den Vertrag selbst:
die kanonische `appkit`-Quelle liegt im Dizzi-Repo und wird per
`ops/sync_appkit.py` **versions-gestempelt vendort** (`<app>/appkit/` +
`_VENDORED.txt` mit Version/HEAD/SHA-256; `--check` erkennt Drift).
**Vendoring erst nach Vertrags-Freeze (R1.6)** — bis dahin füllen K1/K2/K4/K5
ihre Slots in der kanonischen Quelle.

## 2. Pflicht-Endpoints (HTTP, localhost-gebunden, eigener Port 8210–8217)
| Endpoint | Schema (pydantic) | Regeln |
|---|---|---|
| `GET /api/health` | `{ok, app, version, contract, ts}` | Lebenszeichen + Vertrags-Version |
| `GET /api/manifest` | `appkit.manifest.AppManifest` | maschinenlesbare Identität (s. §3) |
| `GET /api/summary` | `appkit.summary.Summary` | **IMMER HTTP 200**; Zustand in `status` (`ok`\|`leer`\|`fehler`); display-fertige `kpis` |
| `GET/PUT /api/settings` | typisiert (K2, **v1.1**) | GET = Defaults+Overrides, `sensitive` maskiert; PUT validiert bekannte Schlüssel STRIKT (Typ/Choice/Grenzen ⇒ 400), Namensraum `x_…` frei, sonst 400; auditiert |
| `GET /api/settings/schema` | `{version, kategorien}` (K2) | 6 Kategorien (konto·sicherheit·ki·vernetzung·darstellung·daten) — Quelle fürs generische Settings-Panel |
| `GET /api/account` | `{profil, identitaet, sso, tresor_eintraege}` (K2) | Konto-Übersicht: Profil + aktuelle Stufe/Weg + SSO-Zustand |
| `GET/PUT/DELETE /api/vault` | Token-Tresor (K2) | Fernet-verschlüsselt neben der App-DB; HTTP liefert NUR Namen, Werte nie; auditiert |
| `GET /api/audit` | Liste `{actor, action, detail, created_at}` | jede Aktion mit Wirkung ist protokolliert |
| `POST /api/account/export` | `{app, format, ts, tresor_namen, daten}` (K2.1b, **v1.3**) | DSGVO-Export aller Nutzer-Daten (generisch über die user_id-Konvention); **Re-Auth Pflicht** (`require_fresh_stepup('verifiziert')`, fail-closed standalone); Tresor nur NAMEN |
| `POST /api/account/loeschen` | `{ok, geloescht, tresor_geleert}` (K2.1b, **v1.3**) | Soft-Delete-Kaskade (deleted_at, generisch) + Tresor-Wipe; Audit-Log bleibt als Beleg; **Re-Auth Pflicht** |

**Versions-Chronik:** 1.0 = K3-Grundvertrag · **1.1 (K2)** = Settings typisiert/strikt + `x_`-Namensraum,
`/api/settings/schema`, `/api/account`, `/api/vault`. Sensible Apps (`hoch`/`hoechst`) starten mit
KI-Routing **`lokal_only`** (lokal-first als Default, Fragerunde 3). · **1.2 (K4)** = `/api/actions`
(HITL-Vorschläge propose→approve/reject, Freigabe verlangt Aktions-Stufe) + Event-Push App→Dizzi. ·
**1.3 (K2.1b, 12.06.)** = Datenrechte-Endpoints (Export/Löschen, s. Tabelle); Konformitäts-Suite
erzwingt zusätzlich deren fail-closed-Verhalten (403 ohne frische Verifikation). ·
**1.4 (F-DEF1, 12.06. spätabends)** = **Dizz Defense** (`appkit/defense.py`, docs/_archiv/20): Sensorik-
Middleware (äußerste Schicht, sieht auch Guard-Abweisungen) + Regel-Engine (Brute-Force/Pfad-Scan/
Köder/Injektions-Signaturen/Raten) + Last-Basislinie (EWMA/EW-Varianz) + Eskalations-Stufenwerk
S0–S5 mit **Autonomie-Politik** (S1 drosseln/S2 befristet sperren autonom mit TTL + exponentieller
Wiederholer-Verlängerung; S4 Lockdown/S5 Not-Aus als HITL-Aktionen `defense_lockdown`/`defense_notaus`,
nur „panik"-Modus schaltet S4 selbst; **Lokal-Schonung**: Loopback autonom max. S1) + Cockpit
`GET /api/defense` + `POST /api/defense/massnahmen/{id}/aufheben` + `/api/defense/lockdown` +
Settings `defense_aktiv`/`defense_autonomie` + persistentes Vorfalls-/Maßnahmen-Journal.
**Pflicht für `create_app`-Apps** (default an); Bestands-Apps rüsten via `install_defense()` nach
(TB = O-DEF). X-Forwarded-For zählt NUR bei konfigurierten vertrauten Proxy-Hops (Setting `defense_trusted_proxy_hops`, Eintrag von rechts; Default 0 = ignorieren, fail-closed auf den TCP-Peer; XFF-Werte erben nie Loopback-Rechte). ·
**1.5 (Mini-Dizzi, 12.06. spätnachts)** = KI-Stimme/Sprach-Brücke je App
(`appkit/mini_dizzi.py`, Nutzer-Auftrag): **App-KI-Slot** (`app.state.mini_dizzi.set_app_ki(fn)`
— die App hängt ihr eigenes Gehirn ein; News-Muster nutzt seine Artikel-KI) + generischer
**Ollama-Fallback** mit App-Kontext (Apps ohne eigene KI; ehrlich ohne Ollama) +
`POST /api/ki/frage` + `GET /api/ki/status`. **Verbund-Gating „es lauscht immer nur EINER"**:
`lauscht_lokal()` (Setting `voice_modus` auto|lokal|aus) — standalone lauscht die App selbst,
im Verbund (Dizzi-ID aktiv) lauscht NUR das zentrale Dizzi und leitet über Core
`POST /api/ki/app/{app_id}` an die App-KI weiter. Per-App-Mikro = vorbereiteter Slot (Gesetz 5).
create_app default an; Konformitäts-Suite prüft `/api/ki/*` wenn vorhanden. · **F-DEF2 (12.06.,
Vertrag bleibt 1.4)** = `POST /api/defense/verbund` (Dizzi-SOC-Dach verteilt geteilte Sperren,
Echo-Schutz `verbund:`-Präfix) + LLM-Triage (`defense_triage_aktiv`, Journal `ki_triage`) +
Prompt-Injection-Prüfer (`appkit.defense.pruefe_prompt`). Core-Hub: `core/app/defense_hub.py`.

**appkit 1.3.0 (K2.2, 13.06., Vertrag bleibt 1.5)** = übergreifendes Design-System: `base_schema`
trägt zwei typisierte Design-Achsen in `darstellung` — `design_vorlage` (`metall`|`neon`) +
`farb_schema` (`cyan-magenta`|`smaragd-gold`|`violett-eis`). Choice-Werte = 1:1 die
`<html data-design>`/`<html data-farbe>`-Attribute des Token-Vertrags (`ui-kit/tokens.css`),
darum mappingsfrei. **Additiv/rückwärtskompatibel** (neue optionale Settings mit Defaults ⇒
KEINE inkompatible Vertrags-Änderung, daher 1.5). Apps hängen ihre freien
`x_design_vorlage`/`x_farb_schema` beim UI-Bau nur auf die typisierten Schlüssel um.
**appkit 1.4.0→1.5.0 (K2.2-b, Katalog-Session + Nutzer-Feedback)** = Katalog auf **10 Design-
Themes × 10 Farbschemata** (Default metall+cyan-magenta; synthwave/lagune/inferno/kobalt tragen
Farbe im Grunddesign; toxic/voltage = Maximal-Intensität; feuer von koralle entkoppelt). Alle
Token-Werte im kanonischen MASTER `shared/dizz-tokens.css` (Single Source; news/ui-kit = Kopie).
Weiterhin additiv ⇒ Vertrag 1.5.

**Generischer Konsum:** Dizzi rendert jede vertragskonforme App **ohne
Per-App-Code** — Kachel aus `/api/summary.kpis`, Aktivierung über
`DIZZI_CONTRACT_APPS="id=url,…"` bzw. `panels.register_contract_app()`.
(Der historische TB-Spezial-Mapper bleibt, bis der TB in K6 angeglichen ist.)

## 3. Vernetzungs-Manifest (`AppManifest`)
`id · name · brand („Dizz …") · version · contract · host/port (+ berechneter
Deep-Link `url`) · icon · sensitivity · auth · mcp · shares · depends`.
- **`sensitivity`** ∈ `normal | hoch | hoechst` — deklariert ab Tag 1; steuert
  später (K5) das KI-Routing: `hoch+` ⇒ nie Boost-/Cloud-Modelle, Daten nur
  hinter verifizierter Verbindung.
- **`auth.status`** ∈ `vorbereitet | aktiv` — K1 stellt um, der Vertrag bleibt.
- **`shares`/`depends`** = was die App teilt (Summary/Tools/Events) und wovon
  sie liest (App-IDs) — Grundlage der Querverbindungen (docs/15).

## 4. Identitäts-Slot (K1-Austauschpunkt) — `appkit/auth.py`
- Schutzstufen (Ordnung): **`lokal` < `verifiziert` < `hochsicher`**.
  `verifiziert` = Tor zu sensiblen Daten · `hochsicher` (Passkey/MFA) = Tor zu
  Echtgeld-Aktionen.
- Routen deklarieren Stufen via `Depends(require_level(...))` — **ab Tag 1**.
- Vor K1: Standalone-Provider (Single-User, Stufe `lokal`, Vertrauensgrenze =
  localhost). Stufen darüber verweigern **fail-closed (403)** mit klarer Meldung.
- K1 installiert per `set_identity_provider()` die echte Prüfung (Dizzi-ID-SSO,
  Passkey-Step-up). **Kein Routen-Code ändert sich.** Auth-Ereignisse → `audit_log`.

## 5. Datenkonventionen — `appkit/db.py` (K5-Basis)
Für JEDE Tabelle: **UUID-PK · `user_id` · `created_at`/`updated_at` (ISO-8601
UTC) · `deleted_at` (Soft-Delete)**. Basis-Schema (`app_settings`, `audit_log`)
stellt die Bibliothek; Domänen-Tabellen via `extra_schema`. Datenpfad:
`C:\Dizzik\data\apps\<id>\<id>.sqlite` (außerhalb OneDrive). `Database`
ist eine Klasse (Test-Injektion, Koexistenz mehrerer Apps im Prozess).
**Datenhygiene (appkit 1.1.0, Review 12.06.):** das K2-Setting
`aufbewahrung_tage` wird durchgesetzt — `Database.retention_lauf` läuft im
`create_app`-Lifespan und löscht endgültig: Audit-Einträge, Defense-Journal,
beendete Defense-Maßnahmen und längst soft-gelöschte Zeilen, jeweils älter
als die Frist (aktive Maßnahmen bleiben immer).

## 6. MCP (KI-Interaktion) — `appkit/mcp.py`
Eigener **stdio-Prozess** über der HTTP-API der laufenden App (Muster
TB-Connector): `build_http_mcp(name, base_url, tools=[(name, pfad, doku)])`.
Niemals auf stdout schreiben (JSON-RPC).

### 6.1 Tool-Namensraum — Pflicht (ab appkit 1.6.0; docs/_archiv/23 R-3)
Jedes MCP-Tool trägt den App-Präfix **`<app_id>_<tool>`**. Der Präfix ist die
kanonische Manifest-`id` (z. B. `finanzen_`, `kommunikation_`, `news_`,
`tradingbot_`) — garantiert eindeutig, mappingsfrei. **Grund:** sobald EIN Host
(Leading-Aggregator, später ein Core-Agent) mehrere App-Server bündelt, würden
generische Namen (`summary`, `status`, `alerts`) kollidieren.
- **`build_http_mcp(name, …)` präfixt automatisch** mit `name` (= `app_id`):
  Apps deklarieren kurze Namen, exponiert wird `<id>_<tool>`. Idempotent.
- Helfer **`appkit.mcp.namespaced(app_id, tool)`** — auch **fürs Manifest** nutzen
  (`McpInfo.tools`/`Shares.tools`), damit deklarierte und tatsächliche Namen
  identisch sind (Muster: `templates/refapp`).
- Direkte FastMCP-Server (TB-Connector) benennen ihre Tool-**Funktionen** bereits
  präfixiert (`def tradingbot_fleet_status(): …`).

### 6.2 Least-Privilege — Prinzip (docs/_archiv/23 §1/§2)
- **Read-only ist der Default** (`build_http_mcp` macht ausschließlich GET).
- **Aktions-/Schreib-Tools** (K4) sind **separat und HITL-gegated**
  (propose→pending→approve) und werden je **Konsument explizit opt-in** geladen —
  nie pauschal alle Tools.
- **Progressiv**: ein Aggregator (Leading) bekommt zuerst nur, was er braucht
  (z. B. Money *lesen*, nicht buchen), und wird schrittweise erweitert.
- **Sensibilität reist mit** (K5): hoch/höchst-Daten nie an Cloud-Modelle; der
  Konsument erbt die Sensibilität der Quelle.

## 7. Konformität & Vorlage
- **Pflicht-Test je App:** `conformance.check_contract(client, app_id)` —
  prüft §2 vollständig (inkl. Settings-Roundtrip + Audit-Eintrag).
- **Neue App = Kopie von `templates/refapp/`** (Anleitung: dortiges README).
  Domäne steckt in genau drei Stellen: `_SCHEMA`, Domänen-Router, `summary_fn`.
- Bekannte Falle (im Template dokumentiert): Request-Modelle auf **Modul-Ebene**
  definieren (`from __future__ import annotations` + lokales Modell ⇒ FastAPI
  macht still einen Query-Parameter daraus).

## 8. Versionierung
`appkit.CONTRACT_VERSION` (aktuell **1.5**) ändert sich nur bei inkompatiblen
Änderungen; Apps melden sie in health/manifest, Dizzi kann Inkompatibilität
erkennen. Bibliotheks-Version `appkit.__version__` folgt semver (aktuell
**1.6.0** — MCP-Namensraum, additiv; Vertrag bleibt 1.5).
