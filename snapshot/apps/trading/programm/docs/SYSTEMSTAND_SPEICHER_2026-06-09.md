# 🗄️ Systemstand & Speicher-/Ordner-Struktur (2026-06-09)

Nach dem kurzen :8137-Ausfall: Voll-Check + frische Doppel-Sicherung. Git-Repo **`Trading Bot eins`**
HEAD `efaa76b`, **148 pytest grün**, **:8137 30/30**, Code kompiliert.

## 1. Wie die Speicherung aktuell funktioniert (HYBRID über 3 Ordner)
Alle unter `…\Code Projekte\`:

| Ordner | Rolle | Git? | venvs/Daten |
|---|---|---|---|
| **`Trading Bot eins`** (mit `programm/`) | **Quelle der Wahrheit** — hier wird editiert & committet | ✅ eigenes Git (`efaa76b`) | **keine venvs** (nur Code, 2.8 MB) |
| **`trading-bot-trial`** | **Live-Betrieb** — :8137 + die 30 Freqtrade-Bots laufen hier | ❌ kein Git | venvs + Live-`data` (SQLite/Bot-DBs) |
| **`Trading Bot Backup`** | **Externe Sicherung** (eigenes Git) | ✅ eigenes Git | Code-Mirror, keine venvs |

**Workflow:** editieren in `Trading Bot eins/programm` → `git commit` → **kopieren** (Deploy) nach
`trading-bot-trial` → bei Backend-`.py` :8137 neu starten. Also **hybrid**: Quelle + Live getrennt.

## 2. Ist das Backup wirklich „extern"?
- Es ist ein **separater Ordner + separates Git-Repo** — also unabhängig vom Arbeits-Repo.
- ABER: auf **derselben Maschine/Platte** (kein anderer Datenträger). **Off-Machine-Kopie nur über die
  OneDrive-Cloud-Synchronisation** (der ganze Pfad liegt unter `OneDrive\…`) → faktisch in der Cloud
  gespiegelt, aber kein dediziertes externes Laufwerk.
- **Stand vorher:** Backup war auf `a4a22e9` (08.06.) eingefroren → die gesamte Nacht-Arbeit fehlte.
- **Jetzt frisch:** neuer Snapshot `Trading Bot Backup/programm_2026-06-09_efaa76b` (+ Backup-Repo-Commit
  `7cee27b`); der alte eingefrorene Stand bleibt daneben erhalten.

## 3. Diese Backup-Runde (durchgeführt)
1. **Voll-Check:** 148 Tests grün, alle Backend-Module + Engine-Strategien kompilieren, 30/30 live.
2. **trial frisch synchronisiert:** Code-Drift gefunden & behoben — `ai.py` (R3/R4-Prompt war committet,
   aber nicht nach-deployed); alle Backend-`.py` + `index.html` + Engine-Strategien neu kopiert
   (Live-`data` bewusst NICHT überschrieben), :8137 neu gestartet → 30/30.
3. **„Trading Bot eins" frisch:** war via Git bereits aktuell (`efaa76b`, sauber).
4. **Backup frisch:** datierter Voll-Snapshot des Quellcodes + Commit im Backup-Repo.

## 4. Kann man das vereinfachen? — JA, empfohlen
**Problem heute:** Der manuelle Kopier-/Deploy-Schritt (programm→trial) ist die Quelle von **Drift-Bugs**
(genau das war die `ai.py`-Drift). Zwei Arbeitsordner = doppelte Pflege.

**Empfehlung (1 Arbeitsordner + 1 Backup):**
- Live direkt aus `Trading Bot eins/programm` betreiben → venvs dort anlegen (Backend- + Engine-venv),
  :8137 von dort starten, Bot-Configs umzeigen. Dann **entfällt der Deploy-/Kopier-Schritt komplett** →
  **keine Drift mehr**, halbe Pflege. `trading-bot-trial` wird stillgelegt (einmal als Archiv behalten).
- `Trading Bot Backup` bleibt als **einziges externes Backup** (Git-Snapshots, via OneDrive in der Cloud).
- **Cleanup:** in `trading-bot-trial` liegen alte `*.bak` + `_backup_*`-Ordner als Ballast — bei der
  Stilllegung mit aufräumen.
- **Trade-off:** Edits treffen dann sofort das Live-System (kein Staging) — bei Demo/0-Risiko + Git +
  Backup vertretbar. **Migration ist ein struktureller Schritt** (venvs neu, 30 Bots umstarten) → mache
  ich nur auf ausdrückliche Freigabe.

**Bonus-Beobachtung (Vorfall):** :8137 war kurz down + einmaliger PowerShell-Fehler `0x800705af`
(Commit-/Pagefile-Limit, trotz 49 GB freiem RAM). Falls wiederkehrend: Pagefile/Commit-Limit erhöhen
(62 python-Prozesse committen viel Speicher).
