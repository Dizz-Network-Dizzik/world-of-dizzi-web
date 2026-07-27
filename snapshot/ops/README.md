# ops — Betrieb & Werkzeuge

| Skript | Zweck |
|---|---|
| `start_core.ps1` | Core-Service starten (liefert auch das gebaute Dashboard unter http://127.0.0.1:8200) |
| `build_shell.ps1` | Frontend bauen (portable Node aus `C:\Dizzik\data\tools\node`) |
| `launch_dizzi.ps1` | Desktop-Starter: startet den Core bei Bedarf (versteckt) und öffnet das Dashboard im Browser — Ziel der Desktop-Verknüpfung |
| `make_icon.py` | Erzeugt `assets/dizzi.ico` + `dizzi_256.png` + `shell/public/favicon.png` (Welt+Orbit, Cyan/Magenta auf Graphit) |
| `mirror_export.py` | Interner **Voll-Spiegel** je App (subtree-split + komplettes appkit/ui-kit) → `data\_backups\mirrors` — Backup-Schiene, KEIN Verkaufs-Bündel |
| `appexport/` | **Produkt-Export (C-1, docs/66):** Carving + Lizenz-Ampel + Editionen + Nullzustand als Schemata/Regelwerke + 89 Vertrags-Tests; Bau-Teile (AST-Scan/Generator/Builder) = Bau-KI C1-1…C1-7. Tests: `venv-python -m pytest -q ops\appexport` |
| `backup_apps.py` | **Nächtliches App-Backup** (AES-ZIP → OneDrive): je App `data\apps\<id>` hot-Copy + Retention; seit V-BIZZI-1 zusätzlich der **DzChronik-Restore-Verbund** `data\chronik\` im SELBEN Snapshot (docs/80 §4.6). Passphrase: `backup_apps.py --set-passphrase`. Verify: `backup_apps.py --verify <zip>` |

## DzChronist (V-BIZZI-1) — Scheduled Task ⚠️ Live-Zündung gegatet (docs/80 §10.7)

Der **Chronist** (`appkit/chronist.py`) übernimmt die Money-Outbox in die append-only Chronik. Er läuft
als **Tick** (kein Daemon) über einen Windows Scheduled Task — **Muster `backup_apps`** (venv-Python,
Minuten-Trigger, unter dem Nutzer-Konto). **Anlage ist gegatet** (Kardinal-Regel 6 + docs/80 §10.7): erst
nach Davids Go + der Erst-Anschluss-Migration (`money.uebernahme`), dann `:8210`-Neustart. Der Tick liest
`data\chronik\quellen.json` (`[{"app":"money","db":"…\finanzen.sqlite"}]`).

```powershell
# NUR nach Freigabe ausführen (legt den Minuten-Task an; ein Lauf = ein Übernahme-/Siegel-Durchlauf):
$py = "C:\Dizzik\data\tools\venv\Scripts\python.exe"
$cmd = "cmd /c set PYTHONPATH=C:\Dizzik\code\dizz-network\packages && `"$py`" -m appkit.chronist --tick"
schtasks /Create /TN "DizzNetwork-Chronist" /TR $cmd /SC MINUTE /MO 1 /RL LIMITED /F
# Prüfen (jederzeit, read-only, auch an den Prüfer herausgebbar):
& $py -m appkit.chronik_pruef --dir C:\Dizzik\data\chronik pruefe
```

Nach **jedem** Restore ist `bizzi-pruef pruefe` + `salden-replay` **Pflicht, VOR** dem nächsten Tick
(docs/80 §4.6). Der Instanz-Lock (OS-Datei-Sperre) stellt sicher, dass nie zwei Ticks gleichzeitig schreiben.

Desktop-Verknüpfung „the world of dizzi" (mit eigenem Icon) liegt auf dem Desktop;
neu erzeugen bei Bedarf: WScript.Shell-Einzeiler in der Projekt-Historie bzw. einfach
Verknüpfung auf `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden
-File "<repo>\ops\launch_dizzi.ps1"` mit Icon `assets\dizzi.ico`.

## Umgebung (außerhalb des Repos, außerhalb OneDrive)
- `C:\Dizzik\data\db\` — SQLite-Laufzeitdaten
- `C:\Dizzik\data\tools\venv\` — Python-venv (fastapi, uvicorn, psutil, pytest, …)
- `C:\Dizzik\data\tools\node\` — portables Node LTS v24 (kein Admin nötig)

## Tests
```powershell
cd core
C:\Dizzik\data\tools\venv\Scripts\python.exe -m pytest tests -q
```

## Noch offen (Teil C, braucht Admin-Installation)
Rust + MSVC Build Tools + Tauri-CLI → natives Desktop-Fenster.
restic-Backup-Einrichtung folgt, sobald erste echte Nutzdaten entstehen.
