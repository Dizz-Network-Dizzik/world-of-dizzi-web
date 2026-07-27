# 63 · AGENTEN-REGIE-VERTRAG — Bau-Spec Z4.1/Z4.2 (FP-4, VO-3/D5/D13)

> **Status: VERTRAG (FP-4, Architektur-KI 03.07.2026). REINES DESIGN — kein Vollbau.** Verträge-als-Code:
> `packages/appkit/agenten.py` (Stubs mit Docstrings, rein additiv, main.py importiert nichts Neues).
> Bau = Bau-KI-Loop (+U) nach §8; Reihenfolge verbindlich (Gesetz 4/9). Vorlage: docs/62 (FP-3-Muster).
> Quellen: docs/58 §4 VO-3 + §3.F (UX-Kanon P1–P8) · docs/52 §5 E4.1–E4.3 · docs/54 C13–C17 ·
> `core app/ai/agent.py` · `appkit/actions.py` (K4) · `appkit/runtime.py` + `modellprofil.py` (FP-3).

## §0 · Geltung, Rollen, Vorbedingungen

**Heimat = Dizz Management** (G-AGENT-HEIMAT ✅ 03.07., D13): Management ist die KI-Agenten-Verwaltung
des Netzes; Social Media = erste Agenten-Domäne darunter. **Rollen (E4.2, fixiert):** **Core** =
Agent-Runtime + Ausführung (`agent.py` als EINE Quelle) · **Management** = Regie + Governance-UI
(definieren, beobachten, freigeben) · **Apps** = Aktions-Ausführung im eigenen K4-Registry ·
**Creating-Direktor** bleibt eigenständig (wird NICHT übernommen) · **Trading :8137 wird NICHT
angeschlossen** (read-only-Gesetz; Geld-System bleibt außerhalb der Agenten-Regie).

**Bau-Voraussetzungen (für den Bau-KI-BAU, NICHT für dieses Design):**
- **Q1 Observability** — Token-/Kosten-Zähler: der Anker existiert schon (`RuntimeEreignis.ende.nutzung`);
  §1-`agent_laeufe.nutzung` nimmt ihn auf. Bau von Z4.2 setzt Q1-Sichtbarkeit voraus.
- **Q2 Evals (C14)** — Autonomie-LOCKERUNG über `pre_approval` hinaus ist im Vertrag HART an
  `eval_gruen` geklemmt (`wirksame_stufe`, §4): ohne Eval-Harness bleibt alles Pre-Approval. Das
  Design blockiert nicht — es macht die Vorbedingung im Code fail-closed.
- **Q3 Event-Spine (C13)** — Ereignisse sind als **Slot** definiert (`EventSenke`, Default = No-op):
  Z4.2 verdrahtet auf C13, ohne die Signaturen zu ändern.

## §1 · Agent-Entitätsmodell (D5/VO-3 Punkt 1)

**Agent = Datensatz, nicht Code.** Ein Agent ist vollständig durch Daten beschrieben — Erweiterung
(neue Agenten, Worker, Tools, MCP-Server) ist CRUD, nie Deployment. *Begründung: D5-d „geisteskrank
erweiterbar" geht nur, wenn Erweitern kein Code-Ereignis ist.*

Felder (Schema = `appkit/agenten.py SCHEMA_AGENTEN_SQL`, **Management-DB** — Definition = Governance,
Heimat D13):

| Feld | Vertrag | Begründung (1 Zeile) |
|---|---|---|
| `rolle`, `system_prompt`, `name` | Freitext; Karte zeigt Rolle prominent | §3.F Agent-Karte: Rolle ist das Erste, was ein Laie liest |
| `task_klasse` + `modell_explizit` | Modell-Bindung übers **Profil** (FP-3): Präzedenz `modell_explizit` > `ModellProfil.slot(task_klasse)` | Kanal-Upgrade (E1.3) hebt ALLE Agenten ohne Anfassen; Override nur für Spezialfälle (FP-3-Präzedenz gespiegelt) |
| `werkzeuge` (JSON-Liste) | **Deny-by-default**: leer = keine Tools; nur Namen aus tools.registry/MCP-Katalog; Filter `werkzeuge_filter` (Schnittmenge, Unbekanntes fliegt) | Least-Privilege + §3.F: Tool-Misuse-Cascades = schnellstwachsendes Schadensmuster 2026 |
| `sensitivitaet` | wirksam = `max(App, Agent)` — Agent kann strenger sein, nie lockerer | Manifest-Sensitivität ist Sicherheits-Schalter (lokal_only), kein Agent darf ihn unterlaufen |
| `autonomie` (JSON `{klasse: stufe}`) | pro **Aktions-Klasse**, Auflösung §4 | §3.F: Autonomie ist Eigenschaft der ENTSCHEIDUNG, nicht des Agenten |
| `sub_agenten` (JSON-Liste Agent-IDs) | Baum, **max 3 Ebenen** (`MAX_EBENEN`, Default-UI 2), zyklenfrei (`validiere_agentenbaum`); Wiederverwendung eines Workers in mehreren Ästen erlaubt | §3.F Table-Stakes „flach 2–3 Ebenen"; Anti-Muster Swarm für Laien |
| `budget` (JSON) | `max_runden` (Parität `agent.MAX_ROUNDS`=4) · `max_tool_aufrufe` · `max_delegationen` · `max_laufzeit_s` · `laeufe_pro_tag` | Runaway-Schutz gehört in die ENTITÄT, damit die Karte ihn zeigen kann (P7 sichtbare Guardrails) |
| `bereich_id` | lose Kopplung `''`=Allgemein (Hausmuster bereiche.py) | D5-e „über Bereiche vernetzt"; Autonomie-Matrix hängt am Bereich |
| `status` | `entwurf` → `aktiv` → `pausiert` (Soft-Delete Hausmuster) | Library-Tab (P1) braucht den Lebenszyklus |

**Reine Projektionen** (pure Funktionen, appkit): `agent_karte()` (P2: Rolle·Tools·Wissen·Grenzen) ·
`inbox_eintrag()` (§2) · `delegations_toolname()` (§3). *Begründung: UI liest Projektionen, nie
Roh-Zeilen — dieselbe Karte in Management, Shell und späteren Editionen.*

**Läufe** (`SCHEMA_LAEUFE_SQL`, **Core-DB** — Ausführungszustand wohnt beim Ausführenden, E4.2):
`agent_laeufe(id, user_id, agent_id, definition, status, stop_signal, runden, tool_aufrufe,
delegationen, nutzung, fehler, started_at, ended_at)`. `definition` = **JSON-Snapshot der aufgelösten
Agent-Definition zum Startzeitpunkt**. *Begründung: Audit + reload-fest + kein Cross-DB-Join — ein
später editierter Agent verfälscht nie die Historie eines alten Laufs.* `nutzung` = rohe
Engine-Zähler aus `RuntimeEreignis.ende` (Q1-Anker, nichts wird später neu verkabelt).

## §2 · Agent-Inbox-Spine (VO-3 Punkt 2) — AUF K4, nicht daneben

**Entscheidung: Die Inbox IST `appkit/actions.py`** — kein zweites Approval-System. *Begründung:
propose→pending→approve⇒executing⇒executed mit at-most-once (P1.7), TTL, Audit und Stufen-Prüfung
existiert und ist getestet; ein Parallelbau wäre ein zweiter, unauditierter Wahrheitsort.*

**Additive Erweiterung** (`INBOX_ZUSATZSPALTEN`, idempotente ALTER wie `migriere_bereich`):
`app_actions` + `agent_id TEXT DEFAULT ''` · `warum TEXT DEFAULT ''` · `lauf_id TEXT DEFAULT ''`.
`propose()` bekommt gleichnamige **nur-Keyword-Parameter mit Default `''`** — bestehende Aufrufer
kompilieren und verhalten sich unverändert (0-Bruch, Liskov-Regel aus runtime.py übernommen).
- **WAS** = `name` + `params` (existiert) · **WARUM** = `warum` (Pflicht bei `source='agent'`;
  leeres WARUM ⇒ propose lehnt ab) · **Argumente** = `params` gerendert. *Begründung: §3.F
  Inbox-Standard „WAS+WARUM+Argumente"; ein Agent, der sein Warum nicht sagen kann, hat keins.*
- **1-Klick-Approve** = bestehendes `decide(approve=True)`; Stufen-Prüfung bleibt in der HTTP-Schicht
  der **besitzenden App**. **Reload-fest** = SQLite (schon wahr). **Auditiert** = `db.audit` (schon wahr).

**Netzweite Aggregation:** Management pollt read-only die `GET /api/actions?status=pending` der Apps
(Ports aus Manifest/Panel-Registry) und projiziert via `inbox_eintrag(app_id, zeile, level)`.
**Approve/Reject gehen IMMER an den Endpoint der besitzenden App** (Browser → `:port/api/actions/
{id}/decide`, Dizzi-ID-SSO); Management proxyt NICHT. *Begründung: Stufen-Enforcement (verifiziert/
hochsicher, künftig Windows-Hello-Step-up VO-4) bleibt beim einzigen Schreiber der jeweiligen DB —
kein Confused-Deputy, exakt die §3.F-Trennung Registry=Katalog / Gateway=Enforcement.*

**API-Vertrag (Management, Z4.1-D):** `GET /api/agent-inbox` → `{eintraege: [inbox_eintrag…],
apps_offline: [ids]}` (Offline-Apps EHRLICH benannt, nie still leer — Health-Watch-Regel).

## §3 · Runtime-Bindung: Orchestrator→Worker auf `agent.py` (VO-3 Punkt 3)

**Entscheidung: Worker = Tool.** Ein Sub-Agent wird dem Orchestrator als synthetisches Tool
`delegiere_<slug>` (ToolSpec) injiziert; sein `run()` startet den Worker-Lauf (eigenes
`stream_agent` mit EIGENER Tool-Teilmenge, EIGENEM Modell-Slot, EIGENEM Budget) und liefert dessen
Endtext als Tool-Ergebnis. *Begründung: `agent.py` bleibt UNVERÄNDERT die eine Quelle (E4.1) —
Parallelität (Workers einer Runde laufen via `asyncio.gather` nebeneinander), Timeout und
Fehler-Isolation (`_run_tool` wirft nie ⇒ ein toter Worker kippt weder Geschwister noch
Orchestrator) sind geschenkt statt nachgebaut.*

- **Definitions-Schema = Baum als Daten** (`sub_agenten`, §1) — Graph-Semantik à la LangGraph nur als
  Datenmodell, nicht als Fremd-Laufzeit (docs/52-Entscheid ✓, F-Q1 kleine Dependency-Fläche).
- **Tiefen-Wächter doppelt:** Definitionszeit (`validiere_agentenbaum`) UND Laufzeit (Laufkontext
  zählt Ebene; Delegation auf Ebene ≥ `MAX_EBENEN` liefert Fehlertext statt Ausführung, fail-closed).
  *Begründung: Definition kann nach Validierung editiert werden — die Laufzeit traut niemandem.*
- **Budget-Wächter:** der Z4.2-Wrapper (`core orchestrator.py`, NEU — dünn um `stream_agent`) zählt
  Runden/Tool-Aufrufe/Delegationen/Laufzeit gegen `AgentBudget` und beendet den Lauf ehrlich
  (`status='fehler'`, Grund im Feld) statt still zu kappen. `MAX_ROUNDS` bleibt die harte Obergrenze
  je `stream_agent`-Aufruf.
- **Stop (P1):** `agent_laeufe.stop_signal=1` (Management-Klick → Core-API); der Wrapper prüft je
  konsumiertem Event und schließt den Iterator (`aclose`) ⇒ Stop wirkt an der nächsten Token-/
  Tool-Grenze. *Begründung: kein Eingriff in `stream_agent` nötig; sauberer asyncio-Abbruch.*
- **HITL im Lauf:** Aktions-Tools der Apps rufen IMMER `propose()` (K4-Gesetz „Schreib-Tools extern
  nur propose") — der Agent bekommt als Tool-Ergebnis `{status:'pending', id}` und formuliert weiter;
  er WARTET NICHT blockierend auf Approval. *Begründung: Läufe bleiben kurz und budgetierbar; die
  Inbox ist der asynchrone Ort der Entscheidung (reload-fest), nicht ein hängender Prozess.*
- **Events (Q3-Slot):** `EREIGNISSE = (lauf_gestartet, runde, delegation, tool_aufruf, hitl_wartet,
  lauf_ende, lauf_stop)`; Emission über `EventSenke` (Default `ereignis_verwerfen` = No-op). Z4.2
  verdrahtet C13, Signaturen bleiben.
- **Ausführungs-API (Core, Z4.2):** `POST /api/agenten/lauf` (Definition-Snapshot rein, SSE der
  AgentEvents raus — heutige `("t"|"tool", …)`-Formen + Lauf-Meta) · `POST /api/agenten/lauf/{id}/stop`
  · `GET /api/agenten/laeufe`. Modell je Agent via `modellprofil` aufgelöst, Transport via
  `runtime_holen()` (FP-3) — **v1-Default lokale Runtime**; Boost/Cloud nur für `normal`-Apps nach der
  Außenzugriff-Politik §4 (G-FP4-BOOST ✅), `hoch`/`höchst` bleiben lokal_only.

## §4 · Autonomie-Modell + MCP-Katalog (VO-3 Punkt 4)

**Aktions-Klassen** (`AKTIONS_KLASSEN`): `entwurf` (interne Wirkung) · `aussenwirkung` (posten,
senden) · `geld` · `gesundheit`. Ableitung aus K4-Level: lokal→entwurf, verifiziert→aussenwirkung,
hochsicher→geld (`klasse_von_level`); Apps dürfen je Aktion explizit strenger deklarieren (healthy ⇒
`gesundheit`). *Begründung: die Klasse trägt die SEMANTIK (worüber entscheide ich), das K4-Level
die AUTH-STÄRKE (wie stark muss die Freigabe sein) — zwei Achsen, nicht eine.*

**Stufen** (`AUTONOMIE_STUFEN`): `pre_approval` (Vorschlag wartet in der Inbox — heutiger K4-Pfad) →
`monitored` (führt aus + Pflicht-Sichtbarkeit: Live-Feed-Eintrag + Benachrichtigung, on-the-loop) →
`autonom_audit` (führt aus, Audit-Log). **Auflösung `wirksame_stufe` (pure, getestet):**

1. `geld`/`gesundheit` ⇒ **IMMER `pre_approval`** (`KLASSEN_BODEN`, nicht konfigurierbar, fail-closed).
   *Begründung: VO-3 „health/money fest höchste Stufe"; ein UI-Bug darf das nie lockern können.*
2. Unkonfiguriert/unbekannt ⇒ `pre_approval`. *Begründung: fail-closed ist der einzige sichere Default.*
3. Sonst `min(Bereichs-Stufe, Agent-Stufe)` (restriktivste gewinnt). *Begründung: zwei Politiken,
   ein Konfliktgesetz — nie die lockerere.*
4. Ergebnis > `pre_approval` **nur wenn `eval_gruen`** (Q2-Nachweis je Agent), sonst Klemme auf
   `pre_approval`. *Begründung: VO-3 „Q2-Evals VOR Autonomie-Lockerung" — als Code, nicht als Doku-Satz.*

Senken einer Stufe ist immer sofort erlaubt; Anheben verlangt Eval-Grün + Nutzer-Bestätigung auf
`hochsicher`-Auth. Trading bleibt gänzlich draußen (§0).

**Außenzugriff-Politik (Edition-abhängiger Default, G-FP4-BOOST ✅ 03.07.).** `normal`-Apps sollen später
NICHT künstlich lokal beschränkt sein — ihre Agenten dürfen Internet UND Boost-/Cloud-Modelle nutzen, sofern
freigegeben. Zwei getrennte Achsen: (1) die **Sensitivitäts-Sperre ist unantastbar** — `hoch`/`höchst`-Apps
(management, healthy, admin) bleiben `lokal_only`, KEIN Setting hebt das; diese Politik betrifft AUSSCHLIESSLICH
`normal`-Apps. (2) Für `normal`-Apps entscheidet die Grundeinstellung `agenten_aussenzugriff` (`aus`/`erlaubt`).
**Edition-Default (docs/56):** Lokal-pur ⇒ `aus` (fail-closed — der lokale Nutzer gibt Außenzugriff EXPLIZIT
frei) · Hybrid/Vollserver ⇒ `erlaubt` (dort läuft ohnehin alles über Server/Internet — keine Reibung nötig).
**Feingranular** („wie man wo", docs/19): global = Grundeinstellung, Detail-Overrides je Bereich/App; Senken
sofort, Anheben in Lokal-pur = bewusste Freigabe. **Fail-closed:** ungesetzt/unbekannt ⇒ wie `aus`; sobald
Boost aktiv, gelten VO-6-Offenlegung + App-Cloud-Inhaltsschranke weiter. Enforcement =
`agenten.boost_erlaubt(setting_erlaubt, sensitivitaet)` (pure, fail-closed-UND). *Begründung (Nutzer 03.07.):
normale Apps voll leistungsfähig halten, aber der lokale Nutzer behält die Hoheit — Freigabe statt
Default-offen.* Bau: settings_core.base_schema + Edition-Default-Auflösung (Z4.1, Muster VO-1
`effekt_intensitaet`); Wrapper-Check (Z4.2).

**MCP-Katalog-Vertrag (Directory→Connect→Permission-Review):** Katalog = Projektion aus App-Manifesten
(`McpInfo.tools`, namespaced) + extern registrierten MCP-Servern des Core-Hubs:
`{server, tools[], level, verbunden, quelle}`. **Connect** = Credentials in den appkit-Vault (nie
Chat/Repo) + Server erscheint als `verbunden`. **Permission-Review** = Tool-Grants je Agent sind die
EINZIGE Brücke (`werkzeuge`, deny-by-default; neuer Server gewährt NULL Tools automatisch); die
Agent-Karte zeigt Grants als Diff-Liste. *Begründung: Katalog (Sichtbarkeit) und Gateway (Core-Hub-
Enforcement, Schreib-Tools extern gesperrt/propose-only) bleiben getrennt — §3.F-Referenzmuster.*

## §5 · UX-Verordnung (§3.F-Kanon P1–P8 → Management-UI, Bau +U)

| Muster | Verordnung |
|---|---|
| P1 Mission-Control | Zwei Tabs: **Running** (`agent_laeufe status='laeuft'`, Live via SSE, **Stop je Lauf**) · **Library** (Agenten nach Status/Bereich). Haupt-Agenten zuerst, Ebenen eingeklappt (D5-b) |
| P2 Agent-Karte | `agent_karte()`-Projektion: **Rolle · Tools (Grants) · Wissen (Bereich+Prompt-Auszug) · Grenzen (Budget/Sensitivität/Autonomie)** — eine Karte, überall dieselbe |
| P3 Inbox | §2; Eintrag zeigt WAS+WARUM+Argumente + Agent + Lauf-Link; 1-Klick-Approve/Reject; leere Inbox sagt „nichts wartet", Offline-Apps ehrlich |
| P4 Bereichs-Autonomie | Matrix Bereich × Aktions-Klasse mit Stufen-Wahl; `geld`/`gesundheit`-Zeilen sichtbar GESPERRT (Schloss + Begründung) statt ausgeblendet |
| P5 Progressive Disclosure | Standard-Ansicht = Haupt-Agent + direkte Worker; Tiefe/JSON/Events nur hinter „Details" |
| P6 MCP-Katalog | Directory→Connect→Permission-Review-Flow (§4); Verbinden ohne Grant gewährt NICHTS |
| P7 Sichtbare Guardrails | Karte + Lauf-Ansicht zeigen Zähler LIVE: Runden x/y · Tool-Aufrufe x/y · Laufzeit · Token (`nutzung`) — Budget ist UI, nicht nur Abbruch |
| P8 Task-Ledger | Lauf-Historie je Agent (Läufe, Ergebnis, Kosten, HITL-Ausgang) aus `agent_laeufe` + Audit |

Anti-Muster (verbindlich): kein Swarm-Editor · keine binäre zu/offen-Governance (immer 3 Stufen ×
Klassen) · kein Approval-Overkill (`entwurf`-Klasse darf nach Eval-Grün monitored werden — Vertrauen
erodiert sonst, §3.F). **AI-Act Art. 50(1) (VO-6): jede Agent-Chat-/Lauf-UI trägt die
KI-Offenlegung** — bis 02.08.2026.

## §6 · E-Mail-Manager-Pilot (Z4.3/C17 — hier spezifiziert, später gebaut)

**Erster Workflow, HITL ÜBERALL** (E4.3: Pilot startet ohne jede Lockerung; alle Stufen
`pre_approval`, unabhängig von Evals).

- **Bereich:** eine `geschaeft`-Marke (welche: Gate G-FP4-PILOT-KONTO, §10). **Heimat der Aktionen:**
  Communication (Mail-Konnektoren docs/38); Regie in Management; Ausführung Core.
- **Baum (2 Ebenen):** Orchestrator **„E-Mail-Manager"** (`task_klasse=chat`) → Worker **„Triage"**
  (`schnell`; liest neue Mails read-only, klassifiziert nach Kategorie/Dringlichkeit) + Worker
  **„Antwort-Entwurf"** (`chat`; formuliert Entwürfe). *Begründung: kleinster echter
  Orchestrator-Fall — beweist Delegation, Parallel-Runde und HITL in einem.*
- **Aktionen (kommapp-Registry):** `email_entwurf_ablegen` (level `lokal`, Klasse `entwurf` — legt
  NUR einen Entwurf im Mail-Konto ab) · `email_senden` (level `verifiziert`, Klasse `aussenwirkung`)
  · `email_verschieben/markieren` (level `lokal`, Klasse `entwurf`). Senden geht IMMER durch die
  Inbox; der Pilot ändert daran nichts.
- **Budget:** Orchestrator `max_runden=4, max_delegationen=8, laeufe_pro_tag=12`; Worker
  `max_runden=2`. Sensitivität wirksam `hoch` (E-Mail-Inhalte ⇒ lokal_only).
- **Messbare Pilot-Akzeptanz:** (1) kein einziger `email_senden`-Vollzug ohne Inbox-Approve
  (Test: propose ⇒ pending, nie direkt executed) · (2) Triage-Worker hat `email_senden` NICHT in
  `werkzeuge` (Filter-Test) · (3) Lauf-Historie zeigt je Lauf Runden/Delegationen/Token · (4) Stop
  beendet einen laufenden Lauf an der nächsten Event-Grenze · (5) Offline-Ollama ⇒ Lauf endet
  `fehler` mit ehrlichem Text, nie hängend.

## §7 · D5-Akzeptanz-Matrix (a–e, messbar)

| D5 | Erfüllung | Messung |
|---|---|---|
| a) sichtbare KI-Agenten-Verwaltung | Mission-Control P1 + Karte P2 in Management | jeder Lauf erscheint im Running-Tab (SSE/Poll); Stop wirkt an nächster Event-Grenze; Karte zeigt Rolle·Tools·Wissen·Grenzen vollständig |
| b) Haupt-Agent + Ebenen übersichtlich | Baum flach, `MAX_EBENEN=3`, UI-Default 2, eingeklappt | `validiere_agentenbaum` lehnt Tiefe>3 + Zyklen ab (Vertrags-Test ✅ heute) |
| c) eigene Tools einbindbar | `werkzeuge`-Grants aus tools.registry + MCP-Connect-Flow | nicht gewährtes Tool erreicht den Payload nie (`werkzeuge_filter`-Test ✅ heute); neuer MCP-Server ohne Grant = 0 Tools |
| d) „geisteskrank erweiterbar" | Agent/Worker/Grant/Server = Daten-CRUD, nie Code; Grenzen nur Budget+Tiefe+Autonomie | neuer Agent inkl. Sub-Agenten ohne Neustart/Deploy anlegbar (Z4.1-C-Akzeptanz) |
| e) über Bereiche vernetzt | `bereich_id`-Achse + Bereichs-Autonomie-Matrix (P4) + Admin-Kopplung Z4.4 | `wirksame_stufe` bindet Bereichs-Politik ein (Vertrags-Test ✅ heute); Matrix-UI je Bereich (Z4.1-C) |

## §8 · Bau-Pakete (commit-groß, Bau-KI-Loop +U; Suite grün je Commit)

> **★ BAU-STATUS 05.07.: Z4.1-A/B/C/D ✅ + Z4.2-A/B/C/D ✅ GEBAUT+GEMERGT** (appkit 316 / mgmt 58 / core 218; `agent.py` unangetastet, appkit unverändert). **Z4.2-D FERTIG** (Live-Integration): Core-SSE-Ausführungs-API (`agenten_routes.py`) + realer Katalog (`agenten_katalog.py`: read-only durchgereicht, App-Schreib-Aktionen propose-gewrappt) + Definition-Brücke (Mgmt `schnappschuss()` pusht Snapshot → Core führt aus, KEIN Core→Mgmt-Fetch) + Running-Tab (+U: SSE-Live-Log · Stop · Guardrail-Zähler P7 · AI-Act). **Mit Fakes getestet + isoliert verifiziert; die ECHTE Live-Aktivierung (Ollama + :8200/:8213-Neustart) ist GEGATET = David-Go.** Ehrliche Rest-Grenzen (docs/63 §0): Q1-`nutzung` leer bis FP-3-Runtime-Umbau · C13-EventSenke no-op · Autonomie fail-closed `pre_approval` bis Q2-Evals. **Z4.3/Z4.4** später (Z4.3 gatet auf G-FP4-PILOT-KONTO). Bau-Detail: Gedächtnis `agenten-regie-bau`.

**Z4.1 — Datenmodell + Regie read-only** *(Voraussetzung: keine — rein additiv)*
- **Z4.1-A** `management agenten_domain.py`: `SCHEMA_AGENTEN_SQL` real + CRUD-API (`/api/agenten`)
  + `validiere_agentenbaum` beim Schreiben + Tests. Akzeptanz: Agent mit Sub-Agenten per API anlegbar;
  Tiefe>3/Zyklus ⇒ 422; management-Suite grün.
- **Z4.1-B** `appkit/actions.py`: `INBOX_ZUSATZSPALTEN` (idempotente ALTER) + `propose(…, agent_id='',
  warum='', lauf_id='')` + WARUM-Pflicht bei `source='agent'` + Tests. Akzeptanz: Bestands-Tests
  UNVERÄNDERT grün (0-Bruch); neue Felder in `listing()`.
- **Z4.1-C** Management Regie-UI read-only (+U): Library-Tab + Agent-Karte + Bereichs-Autonomie-Matrix
  (Stufen speichern, `geld`/`gesundheit` gesperrt) — noch KEINE Ausführung. Akzeptanz: snapshot/eval;
  D5-d-Nachweis (CRUD ohne Deploy).
- **Z4.1-D** Netz-Inbox: Management-Aggregation (`GET /api/agent-inbox`, `inbox_eintrag`-Projektion,
  Offline-ehrlich) + Inbox-UI; Approve/Reject direkt an besitzende App (SSO). Akzeptanz: pending-Aktion
  aus zwei Apps erscheint; Approve führt GENAU EINMAL aus (at-most-once geerbt).

**Z4.2 — Ausführung auf Core** *(Voraussetzungen: Z4.1 + Q1-Sichtbarkeit; C13 für Events, sonst No-op-Senke)*
- **Z4.2-A** `core app/ai/orchestrator.py`: Worker-als-Tool-Builder (`delegations_toolname`,
  Worker-`ToolSpec.run` = eigener `stream_agent`), Tiefen-/Budget-Wächter, `agent.py` UNANGETASTET
  + Tests mit Fake-Runtime. Akzeptanz: 2 Worker einer Runde laufen parallel (gather); Worker-Fehler
  isoliert; Ebene 4 verweigert.
- **Z4.2-B** Lauf-Verwaltung: `SCHEMA_LAEUFE_SQL` real (Core-DB), Definition-Snapshot, Zähler aus
  `nutzung`, `stop_signal`-Prüfung je Event + `aclose` + Events auf `EventSenke`. Akzeptanz: Stop
  beendet ≤1 Event später; Lauf-Zeile vollständig (P8).
- **Z4.2-C** HITL-Verdrahtung: App-Aktions-Tools im Agenten-Kontext IMMER via `propose`
  (WARUM+agent_id+lauf_id gefüllt); `wirksame_stufe`-Enforcement VOR Ausführung (monitored/autonom
  nur mit eval_gruen); Tests fail-closed (geld/gesundheit unlockbar). Akzeptanz: §6-Messpunkte 1–2.
- **Z4.2-D** ✅ Live-Integration: Core-SSE-Ausführungs-API (`agenten_routes.py`: `POST /api/agenten/lauf`
  streamt AgentEvents, `/lauf/{id}/stop`, `GET /laeufe`) · realer Katalog (`agenten_katalog.py`) ·
  Definition-Brücke (Mgmt `schnappschuss()` → Core, Push) · Mission-Control Running-Tab (+U): SSE-Live-Log,
  Stop-Knopf, Guardrail-Zähler (P7), AI-Act-Offenlegung. Akzeptanz: §6-Messpunkte 3–5 mit Fakes belegt
  (SSE-Stream · Stop ≤1 Event · Katalog propose-Wrap · nie hängend); Live-Aktivierung (Ollama+Neustart) gegatet.

Danach separat: **Z4.3** E-Mail-Pilot (C17, §6) · **Z4.4** Admin-Kopplung (C18).

## §9 · Bewusst NICHT im Vertrag (damit niemand es „vervollständigt")

Kein DAG-/Swarm-Editor (Baum reicht, §3.F-Anti-Muster) · kein eigenes Approval-System neben K4 ·
kein LangGraph/CrewAI zur Laufzeit (docs/52-Entscheid; Muster leihen, Laufzeit selbst) · kein
Agenten-Zugriff auf Trading · kein Boost/Cloud für `hoch`/`höchst`-Apps + kein Default-offener Außenzugriff in Lokal-pur
(Freigabe-Pflicht, §4) · kein persistenter
Agenten-Speicher über Läufe hinweg (v1: Bereich+Memory-App SIND das Wissen; eigener Speicher =
späteres Paket) · kein blockierendes Warten auf Approval im Lauf (§3) · keine Autonomie-Stufe über
`autonom_audit` hinaus.

## §10 · Gates an David (unentscheidbar — nicht geraten)

- **G-FP4-PILOT-KONTO (offen):** Welches Mail-Konto/welche `geschaeft`-Marke für den E-Mail-Pilot
  (OAuth-Zugang nötig, Tresor)?

Beantwortet (nicht mehr offen): Heimat = Management (D13) · Approve-Weg = besitzende App (§2,
Architektur-Entscheid mit Begründung) · Tiefe = max 3 (VO-3 „2–3", UI-Default 2) · **G-FP4-BOOST (03.07.,
Nutzer): `normal`-App-Agenten dürfen Internet/Boost — Edition-Default Lokal-pur=`aus` (explizite
Freigabe-Pflicht) / Hybrid+Vollserver=`erlaubt`; einstellbar in den Detail-Einstellungen je Bereich/App;
`hoch`/`höchst` bleiben lokal_only unantastbar (§4).**
