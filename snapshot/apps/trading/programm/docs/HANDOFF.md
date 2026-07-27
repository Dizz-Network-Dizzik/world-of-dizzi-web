> # ⚠️ HISTORISCH (Stand 06.06.2026) — SUPERSEDED
> Detaillierter, chronologischer Stand des **5-Bot-Prototyps vor der Monorepo-Migration**. Wertvoll
> als Entwicklungs-Historie (M0–M5-Aufbau, frühe Design-Entscheidungen), aber **nicht** als aktueller
> Stand lesen. **Aktueller Einstieg = `programm/Übergabe/`** (4 Dateien); voller Live-Stand =
> Gedächtnis-Notiz `trading-bot-eins-stand`.

# HANDOFF — Stand & Wiedereinstieg (HISTORISCH, 06.06.2026)

**Stand:** 06.06.2026 · Meilensteine **M0 ✅, M1 ✅, M2 ✅, M3 ✅, M4 ✅, M5 ✅** ·
UI v3.1 ✅ · Futures ✅ · Prio 1 (Stats Futures/Spot) ✅ · Prio 2 (Status-Erkennung) ✅ ·
**UI v4 (kategorisierte Parameter + Inline-UI + Glassmorphism-Design) ✅** · nächster Schritt: Restliste / **M6**

> 📦 **Backup-Punkt 06.06.2026:** Schwester-Ordner `../Trading Bot eins/` angelegt (Backup-/Restart-/
> M6-Basis): `00_STRUKTUR_UEBERSICHT.md` + `01_NOTIZEN.md` (komprimierte Top-Ebene) + `programm/`
> (Quellcode + State, **ohne** venvs/Trade-DBs/OHLCV — aus `requirements.txt` regenerierbar). 25 Bots laufen.

Dieses Dokument ist der Einstiegspunkt für die nächste Session. Es beschreibt,
was läuft, wie man es startet, und was als Nächstes ansteht.

---

## Was funktioniert (verifiziert)

- **Python 3.12.10** installiert (`%LOCALAPPDATA%\Programs\Python\Python312`).
- **Backend-venv** (`.venv`) mit FastAPI, ccxt, anthropic, pytest.
- **Engine-venv** (`engine/.venv`) mit **Freqtrade 2026.5.1** (TA-Lib als Wheel).
- **Strategie** `TrendFollowEma` (Trendfolge) + Bitget-Daten (BTC/ETH/SOL, 1h, 180T).
- **Backtest** läuft Ende-zu-Ende; Kennzahlen werden strukturiert aus Freqtrades
  JSON-Ergebnis gelesen (`engine/read_backtest_stats.py`).
- **Orchestrator-Backend** (FastAPI, Port 8137) mit Endpunkten:
  `/health`, `/api/bots` (CRUD), `/api/bots/{id}/backtest`, `/api/account`,
  `/api/risk`, `/api/audit`, `/api/console`.
- **Web-Dashboard** (`backend/app/static/index.html`): Übersicht, Bot-Verwaltung,
  Konto/Wallet, Risiko, Audit-Log, Kommandozeile.
- **Desktop-Icon**: „Trading Bot Trial" auf dem Desktop → startet Backend + öffnet
  Dashboard (`scripts/launch.ps1`, `scripts/create_desktop_shortcut.ps1`).
- **Audit-Log** (`data/audit.log`, JSONL) protokolliert alle relevanten Aktionen.
- **Statistik-DB** (`data/stats.sqlite`, stdlib sqlite3): jeder Backtest wird je
  Bot gespeichert (`backend/app/stats.py`); Abruf via `/api/bots/{id}/stats`.
- **Aktiver Risiko-Wächter + Kill-Switch** (`backend/app/risk.py`): nach jedem
  Backtest wird der Drawdown gegen das Bot-Limit geprüft; bei Verstoß → Bot
  `stopped` + Audit. Manuell: `POST /api/bots/{id}/kill`. **Verifiziert.**
- **Editierbare Parameter** pro Bot: `PUT /api/bots/{id}` (inkl. `risk`); im
  Dashboard via Button „Parameter".
- **Multi-Bot Live-Dry-Run** (`backend/app/runner.py`): je Bot ein
  `python -m freqtrade trade`-Subprozess (eigene Config, eigene Trade-DB, eigenes
  Logfile). Start/Stop/Logs über API + Dashboard. **Verifiziert** (state=RUNNING,
  sauberer Stop ohne Waisen via `taskkill /T`). Bots starten dank
  `initial_state: running` aktiv.
- **Transfers** (`backend/app/transfer.py`): `POST /api/transfer` mit
  **Pflicht-Bestätigung** (2-Schritt) + Audit; ohne Keys Paper-simuliert,
  echter Transfer bewusst blockiert (read-only). Dashboard-Panel „Transfer".
- **KI-Module** (`backend/app/ai.py`): **Krypto-Strategie-Katalog**
  (`data/strategy_catalog.json`, 7 Systeme) in **zwei Gruppen** —
  `krypto` (krypto-spezifisch: Grid, DCA, Funding-Rate) und `allgemein`
  (klassisch, aber krypto-tauglich). Nicht krypto-taugliche Strategien werden
  beim Refresh **herausgefiltert** (`crypto_applicable`). Refreshbar, einzelne
  Systeme **anpinnbar**. **Performance-Analyse** je Bot aus der Statistik-DB.
  **Key-aware:** ohne `ANTHROPIC_API_KEY` Seed/Regeln (0 Token), mit Key
  Live-Recherche (bezieht **Recherche-Quellen** ein). **Verifiziert.**
- **Recherche-Quellen** (`data/research_sources.json`): Standardquellen + eigene
  (z. B. ein YouTuber, der Strategien backtestet) per `/api/research/sources`
  (GET/POST/DELETE). Im Dashboard als ein-/ausklappbares Unterfenster.
- **UI v3** (`backend/app/static/index.html`): weicheres Design; oben
  **Statistik-Übersicht** mit **getrennten Tabellen Demo / Echtgeld**; Bot-Anlage
  mit **Modus-Umschalter (Demo/Echtgeld)** inkl. Warnhinweis + Kapital-Cap im
  Echtgeld-Modus; **Strategie-Auswahl** zeigt **strategie-spezifische Parameter**;
  Bots-Liste zeigt **Limits je Bot immer** (Max-DD · Kapital-Cap · Tagesverlust ·
  „Kill-Switch aktiv") + **DEMO/ECHTGELD-Badge**; **Detail-Drawer rechts** mit
  **Kontoverlauf-Grafik** (SVG aus Trade-DB), editierbaren Parametern,
  Stats/Analyse/Logs/Backtest; **KI-Chat-Assistent** (statt starrer Konsole;
  „/" = Befehl); Audit-Log dt. Uhrzeit; Transfer mit „Hauptkonto"=Bitget-Haupt­
  konto-Klarstellung; Konto/Wallet unten. Begriff **„Paper" → „Demo"**.
  Neue Endpunkte: `/api/chat`, `/api/bots/{id}/equity`, `/api/strategies` (mit
  Gruppe+Params), `/api/summary`, `/api/research/sources`.
- **3 nutzbare Strategien**: `TrendFollowEma`, **`MeanReversionRsi`**,
  **`MomentumMacd`** (neue Engine-Vorlagen in `engine/user_data/strategies/`).
  Katalog-Seed-Versionierung (`SEED_VERSION` in `ai.py`) → Auto-Reseed bei
  Struktur-/Vorlagen-Änderungen.
- **Backtest-Fix:** `engine.run_backtest` lädt fehlende Daten (z. B. 5m) vorab
  automatisch herunter (vorher Fehlschlag bei abweichendem Timeframe). Backtest
  löst **keinen** Live-Stopp mehr aus (nur Risikohinweis im Ergebnis).
- **Trade-Übersicht je Bot**: `/api/bots/{id}/trades` (+ Zähler in `/api/summary`);
  im Dashboard kompakt in der Statistik, aufklappbar zum vollen Trade-Fenster.
- **Audit-Log in Klartext** (Event→deutscher Satz), gekürzt; **Konto/Wallet**
  als ausklappbares Fenster.
- **3 Demo-Bots laufen** (gleiche Parameter, 5m): `Auto-Trend-Demo` (27d84c90),
  `Auto-MeanRev-Demo` (9b453b57), `Auto-Momentum-Demo` (06ec195c).
  Übernacht-Report: `scripts/overnight_report.ps1`.
- **Recherche-Tool (Ausbau, LIVE):** `ai._research_with_ai` nutzt jetzt das
  Anthropic **`web_search`-Tool** (Console-Web-Suche ist freigeschaltet, getestet
  ✅) → echte Web-Recherche, Start-Suche „recent crypto trading strategy". Volles
  Schema je System (context, entry/exit_rules, params mit `role`, timeframe,
  horizon, market_type spot/futures, leverage, session, regime, validated,
  sources). Scope: nur Krypto, Horizont ≤ 1 Tag, Futures nur wenn erlaubt.
  Einstellungen: `data/research_config.json` (`allow_futures`, `horizon_scope`,
  `max_systems`) via `/api/research/config`. Konzept: **`docs/RESEARCH_TOOL.md`**.
  Implementierte (lauffähige) Strategien immer wählbar via `IMPLEMENTED_STRATEGIES`
  in `main.py`; Recherche-Systeme brauchen noch eigene Engine-Vorlagen.
  **Alters-Verwaltung:** je System `added_at`/`last_seen`; `max_age_days`
  (Default 30) in `research_config` → veraltete (nicht mehr gefundene)
  nicht-gepinnte Systeme werden beim Refresh aussortiert.
  **Offen:** echte YouTube-Quellen des Nutzers eintragen (kamen 3× als
  `127.0.0.1:8137` an — Einfügen/Autofill-Problem; Nutzer soll Handle als
  Klartext tippen).

> Letzter Backtest-Befund (Referenz): Strategie −11,73 % vs. Markt −42,78 %
> (Bärenmarkt). Pipeline-Beweis, **keine** fertige profitable Strategie.

## App starten

- **Bequem:** Desktop-Icon „Trading Bot Trial" doppelklicken.
- **Manuell:**
  ```powershell
  cd "C:\Dizzik\code\Trading Bot eins\programm"
  .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8137
  # Browser: http://127.0.0.1:8137
  ```
- **Engine-Befehle** (Backtest/Dry-Run): siehe `engine/README.md`.

## Wichtige Pfade

| Zweck | Pfad |
|---|---|
| Backend-Code | `backend/app/` (main, models, registry, exchange, risk, engine, stats, runner, transfer, ai, audit, config) |
| Statistik-DB | `data/stats.sqlite` |
| Strategie-Katalog | `data/strategy_catalog.json` (Krypto, 2 Gruppen) |
| Recherche-Quellen | `data/research_sources.json` |
| Laufende PIDs | `data/runners.json` |
| Bot-Logs / Trade-DB | `engine/user_data/logs/bot_<id>.log` · `engine/user_data/tradesv3_<id>.sqlite` |
| Dashboard | `backend/app/static/index.html` |
| Engine-Config (Vorlage) | `engine/user_data/config_bot1_dryrun.json` |
| Generierte Bot-Configs | `engine/user_data/config_<botid>.json` |
| Strategie | `engine/user_data/strategies/trend_follow_ema.py` |
| Bot-Registry (Daten) | `data/bots.json` |
| Audit-Log | `data/audit.log` |
| Secrets | `.env` (aus `.env.example`; noch NICHT angelegt) |

---

## Offene Punkte für den Nutzer

1. **`.env` anlegen**: `Copy-Item .env.example .env`, dann **read-only**
   Bitget-Key eintragen (für echte Kontostände im Dashboard). Withdraw NIE aktiv.
2. Entscheidungen (Defaults im Plan): Spot-only ja/nein, Subaccount-je-Bot vs.
   gemeinsames Konto, KI-Recherche-Takt, separater `ANTHROPIC_API_KEY`.

## Nächste Schritte — M6 (Echtgeld klein + Subaccounts)

> ⚠️ Erst nach bestandener Paper-Phase. Mini-Beträge, enge Limits.

1. **Bitget read-only-Key** in `.env` → echte Salden im Dashboard (siehe
   `docs/SETUP_USER.md`). Danach optional Key MIT Trade-Recht für Echtgeld.
2. **Subaccounts**: Feld `subaccount` je Bot existiert. Muster: pro Subaccount
   eigene Env-Vars (z. B. `BITGET_API_KEY__<SUB>`) → Injektion in die Bot-Config
   in `registry._write_engine_config`.
3. **Echtgeld-Schalter**: pro Bot `dry_run=false` (über `PUT /api/bots/{id}`),
   nur mit gesetztem Kapital-Cap + globalem Drawdown-Stop.
4. **Steuer-/CSV-Export** aus Audit-Log + Trade-DBs (DAC8/§23 EStG).

### Optional / offen
- KI-Live-Recherche testen, sobald `ANTHROPIC_API_KEY` gesetzt (Modell-ID in
  `TBT_AI_MODEL` ggf. anpassen).
- Eigene Freqtrade-Vorlagen für die übrigen Katalog-Systeme (aktuell nur
  Trendfolge vorhanden; Rest „(Vorlage folgt)").
- Kennzahlen-Panel je Bot direkt in der Tabelle.

## Futures (NEU, läuft)
- `BotCreate.trading_mode` + `registry._write_engine_config` setzen bei Futures
  `margin_mode=isolated`; Futures-Paare im `:USDT`-Format.
- **3 Futures-Demo-Bots laufen** (5m, Hebel 3×, long-only, dry-run): `Fut-MacdRsi-Demo`
  (1a1fc5c3), `Fut-Breakout-Demo` (4c39d958), `Fut-BBands-Demo` (32ffc3af).
  Strategien: `engine/user_data/strategies/futures_*.py`. In `IMPLEMENTED_STRATEGIES`
  (main.py) mit `market_type`/`leverage`. Plus 2 Spot-Demos = **5 Bots aktiv**.
- `/api/strategies` liefert jetzt `market_type` + `leverage`.

### Erledigt (UI v3.1, frontend-only, kein Restart nötig)
- ✅ Katalog **nach Futures/Spot gegliedert** (Futures = Hauptsektor), jede
  Strategie **anklickbar → Detail-Report** (Kontext, Ein-/Ausstiegsregeln,
  Parameter mit Rolle+Spanne, Session, Hebel, Quellen, Alter) im Drawer.
- ✅ **Bot-Liste** zeigt **Futures/Spot + Hebel** (Badge) je Bot.
- ✅ Mehr Farbe (Futures-Badge lila, Hover-Effekte, Section-Header).
> Hinweis Prozesse: venv-`python.exe` ist ein Starter → **2 OS-Prozesse pro Bot**
> (und pro uvicorn). 5 Bots = 10 Prozesse ist normal. Bei „zu vielen": alle
> `*freqtrade*`/`*uvicorn*` killen, uvicorn neu, Bots neu starten (am robustesten
> per `python -c "from backend.app import runner; runner.start('<id>')"`).
- ✅ **Bugfix `runner._pid_alive`**: stürzte mit `TypeError (NoneType)` ab, wenn
  `tasklist` im hidden/umgeleiteten Server-Prozess keinen stdout lieferte → 500
  bei jedem Start. Jetzt mit `(stdout or "")` + try/except abgesichert.
- ✅ **Anlage-Formular: Spot/Futures wird automatisch aus der gewählten Strategie
  gesetzt** (Futures-Strategie → `trading_mode=futures` + `:USDT`-Paare) +
  Timeframe-Auswahl. Behebt das frühere „Bot lässt sich nicht (als Futures)
  starten".
- **5 Demo-Bots laufen verifiziert** (2 Spot + 3 Futures, state=RUNNING).

### Erledigt (06.06.2026) — Prio 1 + 2
- ✅ **Statistik-Übersicht nach Futures/Spot getrennt.** `/api/summary` liefert je
  Zeile `trading_mode` + `leverage` und zusätzlich `groups` (Aggregate je Markt:
  `bots`, `running`, `with_stats`, `avg_profit_pct`). Hebel kommt aus
  `IMPLEMENTED_STRATEGIES` via `main._strategy_leverage`. Frontend
  (`static/index.html`, `loadSummary`): obere Übersicht jetzt primär nach
  **🟣 Futures / 🟢 Spot** gegliedert (je Section mit Meta-Zeile), Spalte **Markt**
  (Futures-Hebel-Badge / Spot-Badge), **DEMO/ECHTGELD** als Badge je Zeile, zwei
  zusätzliche Übersichts-Karten (Futures-/Spot-Bots). Backward-kompatibel
  (alte Top-Level-Keys bleiben).
- ✅ **Status-Erkennung robuster (überlebt uvicorn-Neustart).** `runner.py` erkennt
  laufende Bots jetzt per **Prozess-Kommandozeile** (`config_<id>.json`) via
  CIM (`Get-CimInstance Win32_Process`, PowerShell) — `runner._scan_bot_pids()`,
  3 s gecacht. `status()`-Reihenfolge: Handle → **cmdline** → persistierte PID
  (Fallback). `stop()` killt zusätzlich die per Kommandozeile gefundene PID.
  **Verifiziert:** nach vollständigem uvicorn-Neustart zeigen alle 5 Bots
  `running=true` mit `source="cmdline"`. Nebeneffekt: veraltete `runners.json`-
  Einträge (gelöschte Test-Bots) führen nicht mehr zu Falsch-„läuft".
- ⚠️ **Wichtig (Betrieb):** uvicorn **muss mit der Projekt-`.venv`** gestartet
  werden (`.\.venv\Scripts\python.exe -m uvicorn …`). Das Basis-Python312 hat
  **kein** FastAPI → `ModuleNotFoundError`. `scripts/launch.ps1` nutzt korrekt die
  `.venv`; nicht versehentlich das Basis-Python verwenden.

### Erledigt (06.06.2026) — UI v4: Parameter-Modell, Inline-UI & Design
- ✅ **Kategorisiertes Parameter-Modell.** Jeder Strategie-Parameter hat jetzt
  `category` (`indikator`/`volumen`/`risiko`/`session`/`krypto`) + `optional` (bool).
  `ai._normalize_param` setzt Defaults (rückwärtskompatibel); `SEED_VERSION` 3 → 4.
  Seed-Katalog + Recherche-Prompt (`_research_with_ai`) liefern das erweiterte Schema.
  **Nur relevante** Parameter werden gelistet → irrelevante Kategorien entfallen je
  Strategie. Recherche zu Parametern dokumentiert (Quellen im Plan/`RESEARCH_TOOL.md`).
- ✅ **Echte Param-Specs für die 6 lauffähigen Strategien** (`main.STRATEGY_PARAMS`,
  Helfer `main._p`). `/api/strategies` liefert sie jetzt (vorher leer, weil
  AI-Katalog-Einträge `freqtrade_template="(Vorlage folgt)"` haben). Treibt die
  **Parameter-Vorschau im Anlage-Formular** (`renderStratParams` → `renderParams`).
- ✅ **Inline-UI statt rechtem Drawer.** Strategie-Details (`openStrategy`) klappen
  **inline unter der Strategie-Karte** auf (Accordion), Bot-Details (`openDetails`) +
  Trades (`openTrades`) als **Detail-Zeile unter dem Bot** (`toggleRowDetail`).
  Parameter nach Kategorie gruppiert (`renderParams`), optionale unter „Weitere
  Parameter" eingeklappt. **Drawer komplett entfernt** (Markup/CSS/`openDrawer`).
- ✅ **Backtest entfernt** (UI-Button + `backtest()` JS + Console-Befehl).
  **`/api/bots/{id}/backtest`-Endpoint bleibt** (harmlos, später nutzbar).
- ✅ **Design-Overhaul (Dark Glassmorphism, violett-neon, matt/weich).** Glas-Panels
  (`backdrop-filter`, transluzente Ränder, weiche Schatten), ambient violett/blaue
  Orbs (`body::before`), Bento-Karten mit Metallic-Gradient, weichere Radien (18 px),
  neon-Akzent-Buttons; Transfer-Panel einklappbar. Reines CSS/Markup.
  **Verifiziert** (zweite uvicorn-Instanz auf :8139 als Preview): keine Konsolenfehler,
  Inline-Aufklappen für Strategie + Bot funktioniert, Param-Gruppen sichtbar.
- ⚠️ Hinweis: Der **gespeicherte AI-Katalog** (`strategy_catalog.json`, source=ai)
  bekommt `category`/`optional` erst beim **nächsten Refresh** (wird nicht
  auto-reseedet). Anzeige fällt sonst graceful auf `indikator`/nicht-optional zurück.

### ✅ Recherche-Tool gehärtet + Max-Power-Refresh gelaufen (06.06.2026)
- **Probe-Run-Befund:** `refresh_catalog` fiel wiederholt auf Seed zurück, weil die KI-Antwort
  durch `max_tokens=8000` **abgeschnitten** wurde (`JSONDecodeError`), und der Fallback den
  bestehenden AI-Katalog mit Seed **überschrieb** (Datenverlust). Bei großem `max_tokens` lehnte
  das SDK den nicht-gestreamten Request zudem sofort ab („Streaming required >10 min"); sehr lange
  Läufe brachen mit `RemoteProtocolError` ab.
- **Umgesetzte Verbesserungen** (`ai.py`): (1) **Streaming** (`client.messages.stream` +
  `get_final_message`) → kein 10-Min-Limit, große Outputs möglich; (2) **1 Retry** bei transienten
  Stream-/Verbindungsfehlern (`catalog_ai_retry`); (3) **JSON-Salvage** `_salvage_objects` rettet
  vollständige Objekte aus abgeschnittenem Array (`catalog_ai_salvaged`); (4) **kein Daten-Downgrade**
  — scheitert die Recherche, bleibt der bestehende Katalog erhalten (`catalog_refresh_kept`), Seed nur
  beim allerersten Lauf; (5) `web_search max_uses` 8→6 (kürzerer, stabiler Request); (6) Endpoint
  `POST /api/catalog/refresh?max_systems=&max_tokens=` reicht „Power"-Parameter durch (Default 16000).
- **Verifiziert:** Max-Power-Lauf (`max_systems=12&max_tokens=16000`, 207 s) → `source=ai`, **12 Systeme**
  (9 Futures / 3 Spot), Timeframes 1min/5min/15min/1h/8h, 7–12 Params je System.
- **Mehrschichtige Katalog-UI** (`index.html`, `loadCatalog`): Markt (Futures/Spot) → **Timeframe**
  (sortiert via formatrobustem `tfMin`, erkennt `5m`/`5min`/`1h`/`8h`) → Strategie-Karte → Inline-Detail.
  Native `<details>`-Layer (CSS `.layer`). Verifiziert (2. uvicorn :8139 + Preview): korrekte
  Schichtung/Sortierung, Detail-Accordion ok, keine Konsolenfehler.

### ✅ Recherche-Vertiefung (Qualität + Certainty) & Reaktivitäts-Maß (06.06.2026)
- **Recherche-Prompt vertieft** (`ai._research_with_ai`): YouTube-Backtest-Videos sollen **konkret
  getestete Parameter/Regeln** liefern; nur **klar strukturierte, bot-umsetzbare** Systeme (vage
  weglassen); Mengen-Ziel ≥15–20, ~10 Scalping, ≥4 je Regime. `web_search max_uses` 6→8.
- **Certainty/Backtest-Beleg je System** (`certainty` hoch/mittel/niedrig/unbekannt +
  `backtest_evidence` + `backtest_count`), in `_FIELD_DEFAULTS` + `_normalize_system` (Clamp).
  UI: farbige Pill (`certPill`, CSS `.cert-low/.cert-mid`) auf der Karte + Sektion im Detail (`certText`).
- **Reaktivitäts-Maß** (Loop-Tempo, gegen zu träges Scalping): `BotConfig.reactivity`
  (hoch/standard/ruhig) → `registry.REACTIVITY_THROTTLE` {1,5,15} → `internals.process_throttle_secs`
  in `_write_engine_config`. `create_bot` leitet aus dem Timeframe ab (`_derive_reactivity`:
  1m/3m→hoch, 5m/15m→standard, sonst ruhig); `update_bot` erlaubt Override. Katalog-Systeme tragen
  empfohlene `reactivity` (Prompt + `_normalize_system`-Ableitung). UI-Pill auf Karte/Detail/Bot-Detail.
- **Finaler Max-Power-Lauf verifiziert** (`max_systems=22&max_tokens=32000`, 444 s, Streaming+Retry):
  **25 AI-Systeme** (20 Futures/5 Spot), 17 Scalping, certainty 13 hoch/9 mittel/3 niedrig,
  reactivity 16 hoch/6 standard/3 ruhig, konkrete Beleg-Quellen. UI (Preview) ok, keine Fehler.

### ✅ Bot-Welle angelegt (20 Bots aus dem AI-Katalog) — Daten sammeln
- **20 zusätzliche Demo-Bots** (nach Certainty hoch→mittel, Scalping bevorzugt) via Wave-Skript
  angelegt+gestartet: jedes gewählte System auf die best-passende der 6 Engines gemappt
  (Heuristik nach Name/Logik), Timeframe aus dem System normalisiert (Bereiche wie „3m–5m"→„3m";
  Config-`timeframe` überschreibt das Strategie-Attribut — verifiziert: 1m-Bot startet sauber),
  Reaktivität aus dem System. Namen `AI-<system_id>`. Stake 50, Wallet 1000, max 2 offen.
  **Gesamt jetzt 25 Bots** (5 Alt + 20 Welle), alle `paper_running` (19 Futures/6 Spot).
- ⚠️ Ressourcen: 25 Bots ≈ 50 OS-Prozesse — spürbare CPU-Last. Bei Bedarf einzelne Bots stoppen.
- Hinweis Mapping-Heuristik: einzelne Spot-Mean-Reversion-Systeme landeten auf `TrendFollowEma`
  (Kontext-Keyword „trend") statt `MeanReversionRsi` — kosmetisch (Ausführung = Engine-Logik,
  Datensammlung unberührt).

## Offene Wünsche (priorisiert) — als Nächstes
1. ✅ **erledigt:** Katalog-Refresh mit API-Key (live `web_search`) liefert kategorisierte
   Parameter + reichere Regeln; Tool gehärtet (s. o.). Erneut auslösbar via UI „Refresh" oder
   `POST /api/catalog/refresh?max_systems=&max_tokens=`.
2. **Anlage-Formular: Spot/Futures-Auswahl + Hebel + Timeframe** explizit übersteuerbar
   (Auto-Setzung aus Strategie existiert bereits).
3. **Tiefere Recherche** mit den zwei YouTube-Kanälen stärker gewichten; Futures
   als primärer Fokus.
4. Engine-Vorlagen für weitere recherchierte Systeme; später Futures-Echtgeld (M6).
5. ✅ **erledigt:** veraltete `runners.json`-Einträge gelöschter Bots werden beim
   Start/Stop automatisch bereinigt (`runner._prune_stale_pids`, defensiv gegen
   Registry-Fehler). Verifiziert: 3 Leichen (27d84c90/15505321/602270ab) entfernt, 5/5.

## v5 — Große Wunschliste & offene Fragen (06.06.2026) — WARTET AUF „LOS"

> Status: **A + B-günstig umgesetzt & verifiziert (Preview, keine Konsolenfehler).**
> Offen: A3-Rest (Live-Detailstats je Bot), B (on-demand-Aktivierung, Recherche-
> Deep-Dive), C (Daten/Lernen — Fundament unten spezifiziert).

### Entscheidungen des Nutzers (Antworten auf die Frageketten)
- **Q1:** Tages-Aggregat + optional Stunden-Markt-Snapshot bestätigt machbar/billig
  (< wenige MB/Jahr, keine Tickdaten).
- **Q2:** Lern-Bot = **nur Vorschläge**, läuft anfangs **Demo**; später per **Schalter
  den Algorithmus in eine Echtgeld-Runde** übernehmbar (einstellbar).
- **Q3 (über meine Empfehlung):** **kuratiert + on-demand**-Aktivierung.
- **Q4:** Die **2 YouTube-Kanäle einbinden** ("Trading Strategie Analyse",
  "Trading Strategy Testing") — liefern klar definierte, getestete Systeme.
- **Q5:** **max. Intraday**, Default Scalp+Intraday, Längeres opt-in.
- **Q6 (über meine Empfehlung):** **Daten-Schema zuerst**, Lern-KI danach.

### ✅ Erledigt in dieser Session (frontend + ai.py)
- **Anlegen-Modal**: Hauptformular minimal (Name/Strategie/Demokapital); `b-params`
  zeigt **Strategie-Beschreibung** (`STRAT_DESC`); Klick „anlegen" öffnet **Popup**
  (`openCreateModal`/`confirmCreate`) mit Detailfeldern + **farblich markierten
  Strategie-Vorgaben** (`.vorgabe`), Coins-Anzeige, Spannen-Legende.
- **Ausklappbar**: Audit-Log, Strategie-Katalog (Refresh-Button bleibt klickbar),
  **Assistent** (klein, wächst bei Input-Fokus via `.chatlog.big`), Futures/Spot-
  Gruppen in der Statistik. Helfer `.psummary`.
- **Bot-Details**: gehandelte **Coins** + Timeframe-Badge; **Backtest unter „Analyse"**
  (`dBacktest`), **verständliche Kennzahlen** (`dStats` mit Erklär-Tooltips statt JSON),
  **Equity-Graf mit ROI %**.
- **Parameter-Legende** (Wert=Default, [min–max]=Spanne) in `renderParams`.
- **Design-Boost**: Schimmer hinter Buttons/Karten (`::after`-Sweep), betonte
  Akzent-Zahlen, matt-metallische Panels, ambient Orbs.
- **ai.py**: 2 YouTube-Kanäle in `DEFAULT_SOURCES` + Prompt-Priorisierung;
  `RESEARCH_DEFAULTS` = Kurzfrist (allow_futures=True, horizon_scope=intraday).
- ⚠️ **Bots mussten neu gestartet werden** (über Nacht beendet) — `/api/bots/{id}/start`
  je Bot; danach 5/5. Standing-Check bleibt: bei Session-Start Bots prüfen/starten.

### C — Daten/Lernen: schlankes Schema (umzusetzen, Reihenfolge zuerst)
- **`stats.sqlite` Tabelle `snapshots`**: `(bot_id, ts, equity, profit_pct,
  trades_closed, winrate_pct, max_drawdown_pct)` — 1×/Tag je Bot (debounced).
- **`market_snapshots`**: `(ts, symbol, price, regime, volatility)` — optional 1×/h.
- **`tracker.py`**: schreibt Snapshots (Aufruf bei Refresh/Stunden-Tick, debounced);
  liest Per-Trade aus den Freqtrade-Trade-DBs (keine Duplikate, keine Tickdaten).
- **Lern-Tab + `meta.py`** (später): liest Snapshots+Trades → Vorschläge (proposal-only)
  → Demo → „auf Echtgeld heben"-Schalter. Eigener Dashboard-Reiter.

### ✅ C-Fundament IMPLEMENTIERT (diese Session)
- `stats.sqlite`: Tabellen **`snapshots`** (1 Zeile/Bot/Tag, UPSERT via `UNIQUE(bot_id,day)`)
  + **`market_snapshots`** (optional). Funktionen `save_snapshot/has_snapshot_today/
  get_snapshots/save_market_snapshot` in `stats.py`.
- **`tracker.py`**: `snapshot_bot/snapshot_all/maybe_snapshot_all` (Prozess-Debounce
  15 min + „1×/Tag/Bot"-DB-Check), liest Equity/Trades aus vorhandenen Quellen,
  **keine Tickdaten/Duplikate**. Aufruf debounced aus `/api/summary`.
- Endpoint **`/api/bots/{id}/snapshots`**. Verifiziert: Snapshot geschrieben & abrufbar.

### ✅ On-demand-Aktivierung IMPLEMENTIERT (löst „Vorlage folgt")
- `ai.activate_system(system_id, engine_template)` + Endpoint
  **`POST /api/catalog/{id}/activate`** (validiert gegen `IMPLEMENTED_STRATEGIES`).
  Setzt `freqtrade_template` + `activated=True` → Strategie wird `runnable`.
- UI: im Strategie-Detail (wenn noch nicht lauffähig) **Aktivieren-Block**
  (`activationBlock`/`activateStrategy`): Engine-Vorlage wählen → freigeben; klare
  Kennzeichnung „läuft über Engine X", Backtest-Hinweis vor Echtgeld. Verifiziert.
- **Bewusst KEIN** NL→Code-Gen (zu fehleranfällig). **Offen/nächster Schritt:**
  (a) **Validierungs-Gate** — Pflicht-Backtest/Walk-Forward vor „echter" Freigabe;
  (b) recherchierte **Param-Overrides** wirklich an die Engine-Config durchreichen
  (Strategien müssen Params aus Config lesen); (c) aktivierte Research-Systeme als
  eigenständig benannte, wählbare Einträge in `/api/strategies`.

### ✅ Validierungs-Gate IMPLEMENTIERT
- `engine.run_strategy_backtest(strategy, days)`: Backtest einer Engine-Strategie
  unabhängig vom Bot (nutzt Config eines Bots mit dieser Engine, sonst Vorlage).
- `ai.set_validation(system_id, validated, metrics)` persistiert `validated` +
  `validation{ts,metrics}` am Katalog.
- Endpoint **`POST /api/catalog/{id}/validate?days=120`**: verlangt aktivierte
  Engine-Vorlage, fährt Backtest, **Pass = Trades>0 & Drawdown<50 %** (Profit NICHT
  erzwungen — Bärenmärkte bleiben valide), speichert Kennzahlen. Guard für
  nicht-aktivierte Systeme. UI: „⏱ Validieren"-Button + Status-Badge im Detail.
- **Verifiziert end-to-end:** FuturesMacdRsiScalp → bestanden (−9,54 % / DD 10,42 % /
  223 Trades).

### ✅ Echtgeld-Gate + Walk-Forward IMPLEMENTIERT
- **Validierung je Strategie/Engine** persistiert: `stats.strategy_validations`
  (`save_/get_strategy_validation`). `/api/strategies` liefert `validated` je Vorlage.
- **Echtgeld-Gate (hart):** `create_bot` lehnt Live-Bots (`dry_run=false`) mit
  **HTTP 400** ab, wenn die Strategie nicht validiert ist. Demo bleibt frei.
  **Verifiziert** (Live → 400, Demo → ok).
- **Direkter Strategie-Endpoint:** `POST /api/strategies/{template}/validate?days=&windows=`.
- **Walk-Forward (light):** `engine.run_walkforward(strategy, windows, window_days)` —
  N aufeinanderfolgende Out-of-Sample-Fenster, Pass = Mehrheit bestanden
  (`?windows=2..4` an den Validate-Endpoints; Default 1 = Einzel-Backtest).
- **UI:** Anlege-Modal (Live) zeigt Validierungs-Status + „Strategie validieren"-Button
  (`liveValidationBlock`/`validateEngine`); `confirmCreate` fängt die 400-Blockade ab.
- **Nächster Schritt:** Walk-Forward als Default für Echtgeld-Freigabe schärfen
  (z. B. windows≥3) + `meta`-Lern-Loop Stufe 2 (Mutationen → WF → Gewinner behalten).

### ✅ Lern-Bot / Meta-KI Stufe 1 IMPLEMENTIERT (proposal-only)
- **`meta.py`**: `aggregate()` (Kennzahlen je Strategie über alle Bots),
  `learning_status()` (Daten-Reife in %, Ziel ~30 Snapshots/Bot), `proposals()`
  (regelbasiert: Drawdown nahe Limit, Profit-Faktor < 1, niedrige Winrate,
  Strategie-Ranking) — **kein Auto-Apply**, nur Empfehlungen. `report()`.
- Endpoint **`GET /api/meta`**. UI: einklappbares Panel **„🧠 Lern-Bot"** (Reife-Balken,
  Strategie-Ranking, Vorschläge, gesperrter „Algorithmus auf Echtgeld heben"-Hinweis).
  Verifiziert (keine Konsolenfehler).
- **Stufe 2 (proposal-only) IMPLEMENTIERT:** `meta.optimize_proposals(strategy, params)`
  erzeugt ein **Kandidaten-Raster** (konservativ/Standard/aggressiv aus min/default/max).
  Endpoint `GET /api/meta/optimize/{template}`; UI im Lern-Tab (Strategie wählen →
  „Kandidaten zeigen"). **Kein** Auto-Backtest. Verifiziert (keine Konsolenfehler).
### ✅ Lern-Loop GESCHLOSSEN (vertikaler Prototyp: MeanReversionRsi)
- **`MeanReversionRsi` parametrisierbar gemacht** (`engine/user_data/strategies/
  mean_reversion_rsi.py`): liest `rsi_period/rsi_oversold/rsi_exit/stop_loss_pct` aus
  **Env `TBT_OPT_PARAMS`** (nur im Optimierungs-Backtest gesetzt) — **Live-Bots
  unberührt** (kein Env → IntParameter-Defaults).
- **`engine.run_backtest_with_params(strategy, params, days)`**: injiziert Params per
  Env in den Backtest-Subprozess.
- **`meta.run_optimization(...)`**: testet die 3 Kandidaten-Raster real, kürt
  **Gewinner** (Ranking Profit, Tie-break Drawdown), **proposal-only**.
- Endpoint **`POST /api/meta/optimize/{template}/run?days=`** (Guard:
  `PARAMETRIZABLE_STRATEGIES` = derzeit nur `MeanReversionRsi`). UI: „▶ Loop ausführen"
  im Lern-Tab → Ergebnis-Tabelle + 🏆 Gewinner.
- **Verifiziert end-to-end:** Varianten unterscheiden sich real (Profit −10,09 /
  −8,66 / −6,70 %, Trades 276/246/148 @45T) → Injektion wirkt, Gewinner korrekt.
### ✅ Walk-Forward je Kandidat + Persistenz + Anwendung IMPLEMENTIERT
- **Walk-Forward je Kandidat:** `engine.run_walkforward(..., params=)` ist parameter-
  fähig; `meta.run_optimization(..., windows=N)` nutzt bei `windows>1` WF statt Einzel-
  Backtest. Endpoint `POST /api/meta/optimize/{tpl}/run?days=&windows=`.
- **Gewinner persistiert:** `stats.optimizations` (Tabelle) + `save_/get_optimization`;
  `run_optimization` speichert den Gewinner je Strategie.
- **Anwendung auf Demo-Bot:** `BotConfig.opt_params` (neu) + Registry-Whitelist;
  `runner.start` injiziert `opt_params` per Env **TBT_OPT_PARAMS** in den Bot-Prozess
  (nur parametrisierbare Strategien wirksam, Live-Bots unberührt). Endpoint
  **`POST /api/strategies/{tpl}/apply_opt`** wendet den Gewinner auf alle DEMO-Bots der
  Strategie an (Neustart). UI: „✓ Gewinner auf Demo-Bot(s) anwenden" im Lern-Tab;
  Bot-Detail zeigt „🧠 Lern-Parameter aktiv".
- **Verifiziert end-to-end:** Loop → Gewinner persistiert → auf Demo-Bot `9b453b57`
  angewandt (`opt_params` gesetzt, Bot läuft mit optimierten Params), Bots 5/5.
  ℹ️ Hinweis: `9b453b57` trug zeitweise die „aggressiv"-Params als Demonstration; inzwischen
  per **Reset-Button** (`POST /api/bots/{id}/reset_opt`) zurückgesetzt → läuft wieder Defaults.
### ✅ ALLE 6 Engine-Vorlagen parametrisierbar (Lern-Loop überall nutzbar)
- `trend_follow_ema.py`, `momentum_macd.py`, `futures_macd_rsi_scalp.py`,
  `futures_breakout_vol.py`, `futures_bbands_bounce.py` lesen jetzt ebenfalls
  `TBT_OPT_PARAMS` (Defaults unverändert → Live-Bots gleich). `PARAMETRIZABLE_STRATEGIES`
  in `main.py` = alle 6. **Mapping je Strategie** auf die echte Engine-Logik (z. B.
  Breakout nutzt Donchian: `bb_period`→Kanal-Länge, `volume_multiplier`→Faktor).
- **Verifiziert** (Varianten unterscheiden sich real): TrendFollowEma
  (−3,24/−2,59/−0,34 %, 44/28/2 Trades), FuturesBbandsBounce (−41/−26/−17 %,
  1008/665/441 Trades). Übrige 3: gleiches Muster, syntaktisch geprüft.
### ✅ „Algorithmus auf Echtgeld heben" (Q2) IMPLEMENTIERT
- Endpoint **`POST /api/bots/{id}/promote`** (`{capital_cap_eur, stake_amount}`):
  erzeugt aus einem Demo-Bot einen **neuen Echtgeld-Bot** (`dry_run=false`) mit
  gleicher Strategie/Paaren + **übernommenen `opt_params`** + Kapital-Cap.
  **Gate:** Strategie muss validiert sein (`stats.get_strategy_validation`).
  **Startet NICHT automatisch** (Status `created`/gestoppt) — bewusster Start nötig.
- UI: Bot-Detail (nur Demo) Button **„🚀 Auf Echtgeld heben"** (`promoteBot`) mit
  Warn-Dialog + Kapital-Cap-Abfrage.
- **Verifiziert end-to-end:** validate MeanReversionRsi → promote `9b453b57` →
  neuer Bot (`dry_run=false`, opt_params übernommen, gestoppt, Cap 50€) → Test-Bot
  wieder gelöscht; Bots 5/5. Gate greift (unvalidiert → blockiert).
- ⚠️ Echtgeld handelt real erst bei `TBT_DRY_RUN=false` **und** Trade-fähigem
  Bitget-Key (aktuell global Dry-Run + read-only → keine echten Orders).

### ✅ Konsistenz-Gate + Walk-Forward-Default IMPLEMENTIERT
- **Konsistenz-Gate vor Promote:** `meta.consistency(bot_id, min_days=3)` (Tages-
  Snapshots + Ø-Profit nicht stark negativ). `promote_bot` blockt zusätzlich zur
  Validierung, bis genug **stabile Historie** vorliegt. **Verifiziert:** Promote von
  `9b453b57` → Validierung ok, aber „Konsistenz-Gate: 1/3 Tages-Snapshots" → blockiert.
  (Greift automatisch durch, sobald ≥3 Tages-Snapshots akkumuliert sind.)
  Konstante `CONSISTENCY_MIN_DAYS` in `meta.py` (anpassbar).
- **Walk-Forward als Default:** `meta_optimize_run` nutzt jetzt `windows=2` (mehrere
  Out-of-Sample-Fenster je Kandidat → robuster gegen Overfitting). UI-Label angepasst.

### ✅ Lern-Tab sichtbar gemacht
- `meta.report()` liefert zusätzlich **`readiness`** (je Demo-Bot: validiert? Historie
  x/min, Ø Profit, `ready`) und **`optimizations`** (zuletzt persistierter Gewinner je
  Strategie). UI im Lern-Tab: Tabellen „Echtgeld-Reife (Demo-Bots)" (Status „bereit 🚀"
  / „sammelt …") und „Gelernte Gewinner je Strategie". Verifiziert (keine Konsolenfehler).
- Bekannte Anzeige-Lücke: `optimizations` listet nur Strategien, die ein Bot fährt
  (TrendFollowEma ohne Bot wird nicht gezeigt, obwohl persistiert) — kosmetisch.

### Parameter-Mapping: Katalog-Key → Engine-Logik (TBT_OPT_PARAMS)
| Strategie | gelesene Keys → Wirkung |
|---|---|
| MeanReversionRsi | rsi_period, rsi_oversold, rsi_exit (Indikator); stop_loss_pct→stoploss |
| TrendFollowEma | ema_fast, ema_slow, rsi_period, rsi_entry_min; stop_loss_pct; trailing_start_pct→offset, trailing_distance_pct→positive |
| MomentumMacd | macd_fast/slow/signal; stop_loss_pct |
| FuturesMacdRsiScalp | macd_fast/slow/signal, rsi_period, rsi_buy_threshold→Entry-RSI-Min; stop_loss_pct |
| FuturesBreakoutVol | **bb_period→Donchian-Kanal-Länge**, volume_multiplier→Vol-Faktor; stop_loss_pct (Engine = Donchian, nicht Bollinger) |
| FuturesBbandsBounce | bb_period→BBANDS-Periode, bb_std→nbdev; stop_loss_pct |
> Nicht gemappte Katalog-Keys (z. B. squeeze/range_multiplier/rsi_sell_threshold) werden
> von der jeweiligen Engine ignoriert — bei Bedarf Engine-Logik erweitern.

### ✅ Markt-Snapshots / Regime-Lernen IMPLEMENTIERT
- `tracker.market_snapshot()` zieht via **ccxt Public** (keine Keys) BTC/USDT-1h-OHLCV,
  berechnet **Regime** (Preis vs. SMA20 → trend_up/down/range) + **Volatilität**
  (Stdev der 20 letzten Returns, %), schreibt nach `stats.market_snapshots`.
  Stündlich debounced, aus `/api/summary` (defensiv). `stats.get_market_snapshots`;
  `meta.report()` liefert `market`; Lern-Tab zeigt „📡 Markt (BTC): Regime · Preis · Vol".
- **Verifiziert (Live-Fetch):** BTC/USDT 60.933,68 · `range` · Vol 0,786 %.

### ✅ Regime-bewusste Empfehlung IMPLEMENTIERT (regelbasiert)
- `meta.regime_advice()`: aktuelles Markt-Regime (aus `market_snapshots`) × Strategie-
  Regime-Tags (`STRAT_REGIME`: trend/range/volatil) → **empfohlene Strategien**
  (bei hoher Vola zusätzlich „volatil"-Strategien). In `meta.report()` als
  `regime_advice`; Lern-Tab zeigt „🎯 Regime-Empfehlung (…): …".
- **Verifiziert:** Markt `range` → empfohlen MeanReversionRsi + FuturesBbandsBounce.
- **Nächste Stufe:** empirische Verfeinerung — Ø Performance je (Strategie × Regime)
  aus `snapshots` × `market_snapshots` korrelieren, sobald Historie vorliegt.

### ✅ Empirisches Regime-Lernen IMPLEMENTIERT (selbst-aktivierend)
- `meta.regime_performance()`: verknüpft **Tages-Renditen** (Equity-Delta aufeinander-
  folgender `snapshots`) mit dem **dominanten Tages-Regime** (aus `market_snapshots`)
  → Ø-Rendite je (Strategie × Regime), `data_sufficient` ab ≥10 Datenpunkten.
- `regime_advice()` nutzt **empirisch** (beste Ø-Rendite im aktuellen Regime), sobald
  genug Daten, sonst **regelbasiert** — `source`-Feld zeigt welches. UI zeigt Quelle +
  Datenpunkte.
- **Verifiziert:** aktuell `data_points=0` → Fallback `regelbasiert` (range →
  MeanReversionRsi + FuturesBbandsBounce). Springt automatisch auf `empirisch`, sobald
  über mehrere Tage Bot- und Markt-Snapshots akkumulieren.

### ✅ Lern-Tab-Feinschliff
- `stats.get_all_optimizations()` + `meta.report().optimizations` zeigt **alle**
  persistierten Gewinner (auch Strategien ohne aktiven Bot — Verifiziert: 3 Einträge).
- **Regime-Performance-Tabelle** im Lern-Tab (`meta.report().regime_performance`),
  erscheint automatisch, sobald `data_points>0`.

### ✅ Per-Bot „Gewinner anwenden"
- Endpoint `POST /api/bots/{id}/apply_opt` (wendet den persistierten Gewinner der
  Bot-Strategie auf genau diesen Bot an + Neustart). UI: Bot-Detail (Demo) Button
  „🧠 Gelernte Parameter anwenden". **Verifiziert:** 9b453b57 angewandt; Strategie
  ohne Gewinner sauber abgelehnt.

### ✅ Per-Trade-Regime IMPLEMENTIERT (feinere Empirik, selbst-aktivierend)
- **`stats.closed_trades_for_regime(bot_id)`**: liest geschlossene Trades je Bot aus der
  Freqtrade-Trade-DB (`close_date`-Rohstring + `profit_pct` aus `close_profit`), schlank.
- **`meta.regime_performance_per_trade(tolerance_hours=6)`**: ordnet **jedem** geschlossenen
  Trade das Regime des **zeitlich nächsten** `market_snapshots`-Eintrags zu (nur binnen
  Toleranz, Default ±6 h via `PER_TRADE_TOLERANCE_H`), mittelt **Ø Trade-Profit je
  (Strategie × Regime)**. Feiner als das Tages-Equity-Delta in `regime_performance()` —
  erfasst Intraday-Regimewechsel. `_to_utc()` parst Trade-Stempel (naiv = UTC) und
  Markt-Stempel (ISO+TZ) einheitlich auf aware-UTC. `data_sufficient` ab ≥10 Trades.
- **`regime_advice()` priorisiert jetzt**: empirisch **(Trades)** → empirisch **(Tage)** →
  **regelbasiert**. `source`-Feld zeigt welches; nutzt Empirik nur für das **aktuelle**
  Markt-Regime (n≥3).
- **`report()`** liefert zusätzlich `regime_performance_trades`, `regime_trade_data_points`,
  `regime_trade_tolerance_h`. UI (`loadMeta` in `index.html`): neue Tabelle
  „Regime-Performance · pro Trade" unter der Tages-Tabelle.
- **Verifiziert end-to-end (06.06.2026):** 20 von 26 geschlossenen Trades im ±6 h-Fenster
  dem Regime `range` zugeordnet (Ø/Trade: MeanReversionRsi +0,57 %, MomentumMacd −1,01 %,
  FuturesMacdRsiScalp −1,36 %, FuturesBbandsBounce −1,39 %). Frühe Trades außerhalb der
  Toleranz korrekt verworfen. `regime_advice` schaltet automatisch auf „empirisch (Trades)",
  sobald das **aktuelle** Regime Trade-Historie hat (sonst sauberer Fallback — beim Test
  wechselte BTC live auf `trend_down`, für das es noch keine Trades gab → regelbasiert).

### ✅ Konsistenz-Metrik verfeinert (Trend + Stabilität, härteres Echtgeld-Gate)
- **`meta.consistency()`** bewertet jetzt zusätzlich zur Historie+Ø: **Trend** =
  Least-squares-Steigung der Equity je Tag, normiert auf % der mittleren Equity
  (Helfer `_slope_per_step`); **Stabilität** = Stdev der Tagesrenditen %
  (Helfer `_stdev`). Neue Gates (Konstanten in `meta.py`):
  `CONSISTENCY_MAX_DECLINE_PCT=-2.0` (Trend stark fallend → blockt) und
  `CONSISTENCY_MAX_VOL_PCT=8.0` (zu unruhig → blockt). Defensive None-Behandlung:
  unberechenbare Kriterien (< 2 Equity-Punkte/Tagesrenditen) blockieren nicht →
  greifen selbst-aktivierend mit wachsender Historie. Reason-Text nennt das verletzte
  Kriterium (priorisiert: Historie → Ø → Trend → Stabilität).
- **`report().readiness`** + Lern-Tab-Tabelle „Echtgeld-Reife" zeigen neue Spalte
  **„Trend · Stabil."** (`trend_slope_pct` %/Tag, farbig; `volatility_pct` σ).
  Rückwärtskompatibel — `promote_bot`-Gate (main.py) nutzt unverändert `consistent`/`reason`.
- **Verifiziert (deterministisch, synthetische Serien):** ruhig-steigend → consistent;
  stark fallend (−5 %/T) → „Equity-Trend fällt" blockt; sehr volatil (σ 22 %) → „zu
  unruhig" blockt; zu kurz/1 Snapshot → Historie-Gate, Trend/σ graceful None. Live nach
  uvicorn-Neustart: 5/5, `/api/meta` liefert neue Felder, UI-Spalte da, Log sauber.

### ✅ `opt_params`-Reset-Button je Bot
- Endpoint **`POST /api/bots/{id}/reset_opt`**: setzt `opt_params=null` (Bot läuft wieder
  mit Engine-Defaults); war der Bot aktiv, wird er neu gestartet (damit die Engine ohne
  `TBT_OPT_PARAMS` neu lädt), sonst nur State-Update. Bot ohne Lern-Parameter → `ok:false`
  mit klarer Meldung. UI: Bot-Detail-Button **„↺ Lern-Parameter zurücksetzen"**
  (`resetBotOpt`), nur sichtbar wenn `opt_params` gesetzt.
- **Verifiziert end-to-end:** Reset von `9b453b57` (trug die „aggressiv"-Demo-Params) →
  `opt_params=null`, Bot neu gestartet, 5/5; Negativ-Pfad (Bot ohne Params) → `ok:false`.
  Damit ist das bekannte Demo-Artefakt auf `9b453b57` **bereinigt** (läuft wieder Defaults).

### Offene nächste Schritte (überwiegend datenabhängig — brauchen Laufzeit)
1. Per-Trade-Regime + verfeinerte Konsistenz (Trend/Stabilität) werden mit mehreren Tagen
   Markt-/Trade-/Snapshot-Historie über alle Regime (trend_up/down/range) hinweg belastbar —
   Mechanik fertig, aktiviert sich selbst.
2. **Katalog-Refresh** mit gesetztem `ANTHROPIC_API_KEY` → AI-Katalog erhält kategorisierte
   Parameter + reichere Regeln (Prompt vorbereitet; braucht den Key).
> Hinweis: Die Kern-Vision ist vollständig gebaut & verifiziert. Der größte Mehrwert
> der restlichen Punkte entsteht erst mit **mehreren Tagen Laufzeit-Daten** — sinnvoll,
> die Bots erst sammeln zu lassen.

### Recherche-Mechanismus — Bewertung (eigene Web-Recherche, 2025) + Optionen
**Befund (Literatur 2025):** State of the art ist **Multi-Agent + evolutionäre**
Strategie-Generierung (AlphaAgents, FinRobot, QuantEvolve, „Automate Strategy Finding
with LLM in Quant Investment") mit **Validierungs-Filter** (Kandidaten nach Marktphase
+ Prognosegüte filtern). Zentrale Risiken: **LLM-Halluzination** und — bei Krypto
(niedriges Signal/Rausch, hohe Vola) — **Backtest-Overfitting**. Best Practice gegen
Overfitting: **Walk-Forward mit rollierenden Fenstern + striktes Out-of-Sample**, NICHT
nur ein Validierungs-Set; teils Overfitting-Hypothesentest, der überangepasste Agenten
verwirft. YouTube-Transkript-Extraktion ist in der Literatur **nicht** abgedeckt →
eigener Ingest-Pfad (technisch machbar, aber selbst zu bauen).

**Bewertung des Ist-Standes:** günstig/einfach, echte Web-Suche, sauber gescoped
(Krypto, ≤1 Tag, Futures-Fokus), Alters-Aussortierung. **Schwächen:** (1) **keine
Validierung/Backtest-Gate** generierter Strategien → Halluzinations-/Overfit-Risiko;
(2) YouTube nur als Hinweis, **kein** echter Inhalt; (3) keine iterative Verfeinerung;
(4) „Vorlage folgt"-Lücke (nicht aktivierbar).

**Optionen (priorisiert):**
1. **Validierungs-Gate (höchster Hebel):** jede zu aktivierende Strategie muss
   Backtest + **Walk-Forward/Out-of-Sample** bestehen, bevor sie laufen/lernen darf.
2. **YouTube-Transkripte** der 2 Kanäle real einlesen (yt-dlp/Transcript-API) →
   Parameter direkt extrahieren.
3. **On-demand-Aktivierung**: Katalog-Strategie → „aktivieren" erzeugt Freqtrade-Vorlage
   aus `entry/exit_rules/params` (kuratierter Template-Baukasten) → löst „Vorlage folgt".
4. **Evolutionärer Meta-Loop (→ C/Lern-KI):** Parameter-Mutationen vorschlagen, per
   Walk-Forward validieren, Gewinner behalten — Single-Validation-Overfit vermeiden.
5. Optional: **geplanter Takt** (Cron) + **Scoring** nach Quellen-Qualität + Backtest.

> Quellen: arXiv 2409.06289 (LLM Strategy Finding), arXiv 2510.18569 (QuantEvolve),
> arXiv 2209.05559 (DRL Crypto / Backtest-Overfitting), arXiv 2512.12924 (Walk-Forward).

### A. UI/UX (überwiegend frontend, günstig)
- **Anlegen-Formular minimal** (Name/Strategie/Demokapital); Param-Vorschau →
  Strategie-**Beschreibung**. **Popup beim Anlegen** mit Detailfeldern (Einsatz/Trade,
  Max-DD, Timeframe, Max offene Trades), Strategie-**Vorgaben farblich** markiert.
  (CSS-Gerüst `.modal`/`.vorgabe` vorhanden; JS/Markup fehlt noch.)
- Mehr **Ausklapp-Fenster**: Audit-Log, Strategie-Katalog, **Assistent** klein
  (wächst bei Eingabe). Insgesamt spielerischeres Kasten-Design, matt-metallischer
  Glanz, Effekte weiter betonen.
- **Statistik-Übersicht**: Futures-/Spot-Gruppen ausklappbar; je Bot
  **Detail-Statistik** aufklappbar; **Live-Trades** beim Aufklappen; **Live-Gesamt­
  verlauf** der Bot-Trades sichtbar.
- **Bot-Details/Trades**: Equity-Graf mit **Zahlen + ROI** beschriften.
- **Backtest manuell** unter „Analyse" anbieten (Endpoint `/api/bots/{id}/backtest`
  existiert noch).
- **Stats-Ausgabe** verständlich aufbereiten (statt rohem JSON).
- **Parameter erklären**: die zwei Zahlen = **Spanne min–max**, Default separat
  (v. a. Indikatoren).
- **Coins anzeigen**, die die Bots traden (aktuell BTC/ETH/SOL — Spot `…/USDT`,
  Futures `…/USDT:USDT`).

### B. Recherche-Mechanismus (Backend + KI)
- Erklärung des Mechanismus (s. Chat-Antwort dieser Session) + **eigene neue
  Web-Recherche** zur Beurteilung + **Verbesserungs-Optionen** liefern.
- **Kurzfrist-Fokus** + **Auswahlmenü**: überwiegend Scalp/Intraday, **max. Intraday**
  (keine Mehrtages-/Positions-Strategien), aber wenige längere (bis Intraday) zuschaltbar.
- **Strategie-Aktivierung per Freigabe**: „Vorlage folgt" auflösen — Strategie in der
  Beschreibung lesen und **selbst aktivieren**, statt fester Vorab-Implementierung.

### C. Daten & Lernen (NORDSTERN — jetzt architektonisch vorbereiten)
- **Effizientes Stats-Tracking**: Detaildaten, aber speicher-/leistungsschonend.
  Vorschlag: pro geschlossenem Trade ein kompakter Datensatz + **tägliche Aggregat-
  Snapshots** je Bot in `stats.sqlite`; **keine Tickdaten**.
- **Eigener Reiter „Lern-Bot / Meta-KI"**: lernt aus gesammelten Statistiken **und**
  Eigenbeobachtung der Märkte (über die Bots), entwickelt/verfeinert **laufend** einen
  eigenen Algorithmus/eigene Strategien (Conclusion aus allen Daten) → kontinuierliche
  Selbstverbesserung. Datenhaltung + Tracking + Algorithmus-Verfeinerung dafür vorbereiten.

### Offene Fragen (vor Umsetzung klären — Frageketten)
1. **Stats-Granularität:** pro-Trade + Tages-Aggregat genug, oder zusätzlich
   periodische **Markt-Kontext-Snapshots** (z. B. stündlich BTC-Regime/Volatilität)?
2. **Lern-Bot-Autonomie/Sicherheit:** nur **Vorschläge zur manuellen Freigabe** →
   Demo → (später) Echtgeld? Oder Auto-Deploy auf Demo-Bots?
3. **Strategie-Aktivierung:** kuratierter Satz + „on-demand implementieren", oder
   Versuch **automatischer** Template-Generierung aus NL-Regeln (riskanter, fehleranfällig)?
4. **Recherche-Takt:** nur manuell (Button) oder **geplant** (Cron)? YouTube wirklich
   per **Transkript** einbeziehen (mehr Aufwand/Tokens) oder weiter als Quellen-Hinweis?
5. **Kurzfrist-Cutoff:** „max. Intraday" = bis ~1 Tag Haltedauer? Default-Auswahl
   Scalp+Intraday, längeres opt-in?
6. **Reihenfolge Lern-Bot:** zuerst nur **Daten sammeln + Analyse-Dashboard**, KI-
   Strategiebildung später? (empfohlen, weil daten-getrieben sinnvoller)

### Effizienz-Einschätzung (kurz)
- A ist überwiegend günstig (CSS/JS, kein Restart) → in 1–2 Meilensteinen machbar.
- B: Erklärung + neue Recherche günstig; **Auto-Aktivierung beliebiger Strategien**
  ist der teure/riskante Teil → kuratiert + on-demand bevorzugen.
- C ist das Große: zuerst **schlankes Daten-Schema** festklopfen (Frage 1+6), dann
  iterativ Lern-Reiter. Lieber klein & erweiterbar starten als alles auf einmal.

## Danach (Roadmap)
- **M7:** Docker-Compose + `docs/DEPLOY.md` (Server-Auslagerung).
- **Optional:** Native Tauri-Hülle statt Browser-Launcher (Rust+Node-Toolchain).

## Tech-Schulden / Notizen

- Backend startet aktuell ohne `.env` (nutzt Defaults). Mit Keys werden echte
  Bitget-Salden gezogen.
- `freqtrade`-Report-Text wird NICHT geparst (nur am TTY zuverlässig) — Kennzahlen
  kommen aus der JSON-Ergebnisdatei. Beibehalten.
- PowerShell 5.1 liest `.ps1` als ANSI: **keine Nicht-ASCII-Zeichen in `.ps1`**.
- `freqtrade` nutzt `@app.on_event("startup")` (deprecation-Warnung) — bei
  Gelegenheit auf Lifespan-Handler umstellen.
- ✅ **Subprozess-Encoding-Fix (Windows):** Alle `subprocess.run(..., text=True)` in
  `runner.py` (`_pid_alive` tasklist, `_scan_bot_pids` PowerShell-CIM) und `engine.py`
  (9× Backtest/Validierung/Walk-Forward/`_read_stats`) nutzen jetzt zusätzlich
  `errors="replace"`. Vorher dekodierte Python die Subprozess-Ausgabe mit dem ANSI-
  Default (cp1252); fremde `python.exe`-Kommandozeilen mit Byte 0x81 ließen die
  `_readerthread`-Threads mit `UnicodeDecodeError` abstürzen (Bot startete zwar mit
  HTTP 200, aber Tracebacks im Log + evtl. verschluckte Ausgabe). **Verifiziert:**
  deterministischer Repro (Byte 0x81) + Live-Bot-Start nach uvicorn-Neustart → null
  `_readerthread`/`UnicodeDecodeError` im Log, 5/5 Bots.
  ⚠️ Beim Neustart uvicorn **gezielt per PID ohne `/T`** beenden (nur Worker+Starter),
  dann überleben die Bot-Kindprozesse (kein Baum-Kill → kein Bot-Verlust).
